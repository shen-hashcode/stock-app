package com.stockapp.service;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.stockapp.entity.Strategy;
import com.stockapp.entity.StrategyResult;
import com.stockapp.mapper.StrategyResultMapper;
import com.stockapp.strategy.BuiltinStrategy;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;

@Slf4j
@Service
@RequiredArgsConstructor
public class SchedulerService {

    private final StrategyService strategyService;
    private final StockService stockService;
    private final StrategyResultMapper resultMapper;
    private final Map<String, BuiltinStrategy> builtinStrategyMap;

    @Scheduled(cron = "0 ${app.schedule.minute:0} ${app.schedule.hour:16} * * ?")
    public void dailyStrategyRun() {
        log.info("开始每日策略执行...");
        List<Strategy> strategies = strategyService.getActiveStrategies();
        List<Map<String, Object>> stockList = stockService.getStockList();
        String today = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd"));

        for (Strategy strategy : strategies) {
            try {
                JSONObject conditions = JSON.parseObject(
                        strategy.getConditions() != null ? strategy.getConditions() : "{}");
                String type = conditions.getString("type");

                List<Map<String, Object>> results = new ArrayList<>();

                if ("custom".equals(type) && strategy.getScriptCode() != null) {
                    log.info("执行自定义策略: {} (id={})", strategy.getName(), strategy.getId());
                    // 自定义策略暂时跳过（需Python环境）
                } else if (builtinStrategyMap.containsKey(type)) {
                    BuiltinStrategy builtin = builtinStrategyMap.get(type);
                    Map<String, Object> params = new HashMap<>(builtin.getDefaultParams());
                    JSONObject userParams = conditions.getJSONObject("params");
                    if (userParams != null) params.putAll(userParams);

                    log.info("执行内置策略: {} (id={})", strategy.getName(), strategy.getId());
                    for (Map<String, Object> stock : stockList) {
                        try {
                            if (builtin.check(stock, params, stockService)) {
                                Map<String, Object> quote = stockService.getRealtimeQuote(
                                        (String) stock.get("code"), (String) stock.get("market"));
                                Map<String, Object> result = new HashMap<>(stock);
                                result.put("quote", quote);
                                results.add(result);
                            }
                        } catch (Exception ignored) {}
                    }
                }

                StrategyResult record = new StrategyResult();
                record.setStrategyId(strategy.getId());
                record.setRunDate(today);
                record.setStocksJson(JSON.toJSONString(results));
                record.setCreatedAt(LocalDateTime.now());
                resultMapper.insert(record);

                log.info("策略 {} 执行完成，筛选出 {} 只股票", strategy.getName(), results.size());
            } catch (Exception e) {
                log.error("策略执行失败: {} - {}", strategy.getName(), e.getMessage());
            }
        }
        log.info("每日策略执行完成");
    }
}
