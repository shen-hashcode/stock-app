package com.stockapp.service;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.stockapp.entity.Strategy;
import com.stockapp.entity.StrategyResult;
import com.stockapp.mapper.StrategyMapper;
import com.stockapp.mapper.StrategyResultMapper;
import com.stockapp.strategy.BuiltinStrategy;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.concurrent.*;

@Slf4j
@Service
@RequiredArgsConstructor
public class StrategyService {

    private final StrategyMapper strategyMapper;
    private final StrategyResultMapper resultMapper;
    private final StockService stockService;
    private final Map<String, BuiltinStrategy> builtinStrategyMap;

    public List<Map<String, Object>> getBuiltinStrategies() {
        List<Map<String, Object>> list = new ArrayList<>();
        for (BuiltinStrategy s : builtinStrategyMap.values()) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("key", s.getKey());
            item.put("name", s.getName());
            item.put("description", s.getDescription());
            item.put("params", s.getDefaultParams());
            list.add(item);
        }
        return list;
    }

    public Strategy createStrategy(Integer userId, String name, String description, String conditions) {
        Strategy strategy = new Strategy();
        strategy.setUserId(userId);
        strategy.setName(name);
        strategy.setDescription(description);
        strategy.setConditions(conditions != null ? conditions : "{}");
        strategy.setIsActive(true);
        strategy.setCreatedAt(LocalDateTime.now());
        strategy.setUpdatedAt(LocalDateTime.now());
        strategyMapper.insert(strategy);
        return strategy;
    }

    public Strategy createCustomStrategy(Integer userId, String name, String description, String scriptCode, String conditions) {
        Strategy strategy = new Strategy();
        strategy.setUserId(userId);
        strategy.setName(name != null && !name.trim().isEmpty() ? name.trim().substring(0, Math.min(name.trim().length(), 50)) : "自定义策略");
        strategy.setDescription(description);
        strategy.setScriptCode(scriptCode);
        strategy.setConditions(conditions);
        strategy.setIsActive(true);
        strategy.setCreatedAt(LocalDateTime.now());
        strategy.setUpdatedAt(LocalDateTime.now());
        strategyMapper.insert(strategy);
        return strategy;
    }

    public List<Strategy> getUserStrategies(Integer userId) {
        return strategyMapper.selectList(new QueryWrapper<Strategy>().eq("user_id", userId));
    }

    public List<Strategy> getActiveStrategies() {
        return strategyMapper.selectList(new QueryWrapper<Strategy>().eq("is_active", true));
    }

    /**
     * 执行内置策略
     */
    public Map<String, Object> runBuiltinStrategy(String strategyKey, Map<String, Object> customParams, int stockLimit) {
        BuiltinStrategy builtinStrategy = builtinStrategyMap.get(strategyKey);
        if (builtinStrategy == null) {
            log.warn("内置策略不存在: {}", strategyKey);
            return null;
        }

        Map<String, Object> params = new HashMap<>(builtinStrategy.getDefaultParams());
        if (customParams != null) params.putAll(customParams);

        int limit = stockLimit > 0 ? stockLimit : 200;
        log.info("开始执行内置策略: {}, 股票池大小: {}", strategyKey, limit);
        List<Map<String, Object>> stockList = stockService.getStockListQuick(limit);
        log.info("获取股票列表完成, 实际数量: {}", stockList.size());

        List<Map<String, Object>> results = runConcurrent(stockList, builtinStrategy, params);
        log.info("内置策略 {} 执行完成, 命中 {} 只股票", strategyKey, results.size());

        Map<String, Object> data = new HashMap<>();
        data.put("count", results.size());
        data.put("stocks", results);
        data.put("params", params);
        return data;
    }

    /**
     * 根据策略ID执行
     */
    public Map<String, Object> runStrategyById(Integer strategyId) throws Exception {
        log.info("开始执行策略, strategyId={}", strategyId);
        Strategy strategy = strategyMapper.selectById(strategyId);
        if (strategy == null) {
            log.warn("策略不存在, strategyId={}", strategyId);
            throw new RuntimeException("策略不存在");
        }

        com.alibaba.fastjson2.JSONObject conditions = com.alibaba.fastjson2.JSON.parseObject(
                strategy.getConditions() != null ? strategy.getConditions() : "{}");
        String type = conditions.getString("type");
        log.info("策略类型: {}, 策略名称: {}", type, strategy.getName());

        List<Map<String, Object>> stockList = stockService.getStockListQuick(200);
        List<Map<String, Object>> results;

        if ("custom".equals(type) && strategy.getScriptCode() != null) {
            log.info("执行自定义Python脚本策略, 股票池大小: {}", stockList.size());
            results = runCustomStrategy(strategy.getScriptCode(), stockList);
        } else if (builtinStrategyMap.containsKey(type)) {
            BuiltinStrategy builtin = builtinStrategyMap.get(type);
            Map<String, Object> params = new HashMap<>(builtin.getDefaultParams());
            com.alibaba.fastjson2.JSONObject userParams = conditions.getJSONObject("params");
            if (userParams != null) params.putAll(userParams);
            log.info("执行内置策略: {}, 股票池大小: {}", type, stockList.size());
            results = runConcurrent(stockList, builtin, params);
        } else {
            log.error("未知策略类型: {}, strategyId={}", type, strategyId);
            throw new RuntimeException("未知策略类型");
        }

        // 保存结果
        String today = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd"));
        StrategyResult record = new StrategyResult();
        record.setStrategyId(strategyId);
        record.setRunDate(today);
        record.setStocksJson(com.alibaba.fastjson2.JSON.toJSONString(results));
        record.setCreatedAt(LocalDateTime.now());
        resultMapper.insert(record);

        log.info("策略执行结果已保存, strategyId={}, 命中{}只股票", strategyId, results.size());

        Map<String, Object> data = new HashMap<>();
        data.put("count", results.size());
        data.put("stocks", results);
        return data;
    }

    /**
     * 多线程并发执行内置策略
     */
    private List<Map<String, Object>> runConcurrent(List<Map<String, Object>> stockList, BuiltinStrategy strategy, Map<String, Object> params) {
        List<Map<String, Object>> results = Collections.synchronizedList(new ArrayList<>());
        ExecutorService executor = Executors.newFixedThreadPool(10);
        List<Future<?>> futures = new ArrayList<>();
        long start = System.currentTimeMillis();

        for (Map<String, Object> stock : stockList) {
            futures.add(executor.submit(() -> {
                try {
                    if (strategy.check(stock, params, stockService)) {
                        Map<String, Object> quote = stockService.getRealtimeQuote(
                                (String) stock.get("code"), (String) stock.get("market"));
                        Map<String, Object> result = new HashMap<>(stock);
                        result.put("quote", quote);
                        results.add(result);
                    }
                } catch (Exception e) {
                    log.debug("策略检查异常, stock={}, error={}", stock.get("code"), e.getMessage());
                }
            }));
        }

        int timeoutCount = 0;
        for (Future<?> f : futures) {
            try { f.get(120, TimeUnit.SECONDS); } catch (Exception e) { timeoutCount++; }
        }
        executor.shutdown();

        if (timeoutCount > 0) {
            log.warn("并发执行中有 {} 个任务超时或异常", timeoutCount);
        }
        log.debug("并发策略执行完成, 总耗时{}ms, 检查{}只, 命中{}只",
                System.currentTimeMillis() - start, stockList.size(), results.size());
        return results;
    }

    /**
     * 执行自定义Python脚本策略（通过子进程）
     */
    private List<Map<String, Object>> runCustomStrategy(String scriptCode, List<Map<String, Object>> stockList) {
        List<Map<String, Object>> results = new ArrayList<>();
        int errorCount = 0;
        int timeoutCount = 0;
        long start = System.currentTimeMillis();

        for (Map<String, Object> stock : stockList) {
            try {
                String code = (String) stock.get("code");
                String market = (String) stock.get("market");
                String pythonCode = "import json,sys\n" +
                        "sys.path.insert(0,'.')\n" +
                        scriptCode + "\n" +
                        "stock_info=" + com.alibaba.fastjson2.JSON.toJSONString(stock) + "\n" +
                        "print(json.dumps(check_stock(stock_info)))";

                ProcessBuilder pb = new ProcessBuilder("python3", "-c", pythonCode);
                pb.redirectErrorStream(true);
                Process process = pb.start();
                boolean finished = process.waitFor(10, TimeUnit.SECONDS);
                if (!finished) {
                    timeoutCount++;
                    process.destroyForcibly();
                    continue;
                }
                if (process.exitValue() == 0) {
                    String output = new String(process.getInputStream().readAllBytes()).trim();
                    if ("true".equalsIgnoreCase(output)) {
                        Map<String, Object> quote = stockService.getRealtimeQuote(code, market);
                        Map<String, Object> result = new HashMap<>(stock);
                        result.put("quote", quote);
                        results.add(result);
                    }
                } else {
                    errorCount++;
                }
            } catch (Exception e) {
                errorCount++;
                log.debug("自定义策略执行异常, stock={}, error={}", stock.get("code"), e.getMessage());
            }
        }

        log.info("自定义策略执行完成, 总耗时{}ms, 检查{}只, 命中{}只, 错误{}, 超时{}",
                System.currentTimeMillis() - start, stockList.size(), results.size(), errorCount, timeoutCount);
        return results;
    }

    public List<StrategyResult> getResults(Integer strategyId, int limit) {
        return resultMapper.selectList(
                new QueryWrapper<StrategyResult>()
                        .eq("strategy_id", strategyId)
                        .orderByDesc("created_at")
                        .last("LIMIT " + limit)
        );
    }
}
