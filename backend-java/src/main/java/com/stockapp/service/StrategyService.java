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
        if (builtinStrategy == null) return null;

        Map<String, Object> params = new HashMap<>(builtinStrategy.getDefaultParams());
        if (customParams != null) params.putAll(customParams);

        List<Map<String, Object>> stockList = stockService.getStockListQuick(stockLimit > 0 ? stockLimit : 200);
        List<Map<String, Object>> results = runConcurrent(stockList, builtinStrategy, params);

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
        Strategy strategy = strategyMapper.selectById(strategyId);
        if (strategy == null) throw new RuntimeException("策略不存在");

        com.alibaba.fastjson2.JSONObject conditions = com.alibaba.fastjson2.JSON.parseObject(
                strategy.getConditions() != null ? strategy.getConditions() : "{}");
        String type = conditions.getString("type");

        List<Map<String, Object>> stockList = stockService.getStockListQuick(200);
        List<Map<String, Object>> results;

        if ("custom".equals(type) && strategy.getScriptCode() != null) {
            results = runCustomStrategy(strategy.getScriptCode(), stockList);
        } else if (builtinStrategyMap.containsKey(type)) {
            BuiltinStrategy builtin = builtinStrategyMap.get(type);
            Map<String, Object> params = new HashMap<>(builtin.getDefaultParams());
            com.alibaba.fastjson2.JSONObject userParams = conditions.getJSONObject("params");
            if (userParams != null) params.putAll(userParams);
            results = runConcurrent(stockList, builtin, params);
        } else {
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
                } catch (Exception ignored) {}
            }));
        }

        for (Future<?> f : futures) {
            try { f.get(120, TimeUnit.SECONDS); } catch (Exception ignored) {}
        }
        executor.shutdown();
        return results;
    }

    /**
     * 执行自定义Python脚本策略（通过子进程）
     */
    private List<Map<String, Object>> runCustomStrategy(String scriptCode, List<Map<String, Object>> stockList) {
        List<Map<String, Object>> results = new ArrayList<>();
        // 自定义策略通过Python子进程执行
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
                if (finished && process.exitValue() == 0) {
                    String output = new String(process.getInputStream().readAllBytes()).trim();
                    if ("true".equalsIgnoreCase(output)) {
                        Map<String, Object> quote = stockService.getRealtimeQuote(code, market);
                        Map<String, Object> result = new HashMap<>(stock);
                        result.put("quote", quote);
                        results.add(result);
                    }
                }
            } catch (Exception ignored) {}
        }
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
