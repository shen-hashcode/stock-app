package com.stockapp.controller;

import com.alibaba.fastjson2.JSON;
import com.stockapp.dto.*;
import com.stockapp.entity.Strategy;
import com.stockapp.service.LlmService;
import com.stockapp.service.StrategyService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/strategies")
@RequiredArgsConstructor
public class StrategyController {

    private final StrategyService strategyService;
    private final LlmService llmService;

    @GetMapping("/builtin")
    public ApiResponse<?> getBuiltinStrategies() {
        log.info("获取内置策略列表");
        return ApiResponse.success(strategyService.getBuiltinStrategies());
    }

    @PostMapping("")
    public ApiResponse<?> createStrategy(@RequestParam("user_id") Integer userId, @RequestBody StrategyCreateRequest req) {
        log.info("创建策略请求, userId={}, name={}", userId, req.getName());
        Strategy strategy = strategyService.createStrategy(userId, req.getName(), req.getDescription(), req.getConditions());
        log.info("策略创建成功, strategyId={}", strategy.getId());
        return ApiResponse.success(Map.of("id", strategy.getId()));
    }

    @PostMapping("/custom")
    public ApiResponse<?> createCustomStrategy(@RequestParam("user_id") Integer userId, @RequestBody CustomStrategyRequest req) {
        log.info("创建自定义AI策略, userId={}, description={}", userId, req.getDescription());
        try {
            String scriptCode = llmService.generateStrategyScript(req.getDescription());
            String name = req.getName() != null && !req.getName().trim().isEmpty()
                    ? req.getName().trim().substring(0, Math.min(req.getName().trim().length(), 50))
                    : "自定义策略";
            String conditions = JSON.toJSONString(Map.of("type", "custom", "description", req.getDescription()));
            Strategy strategy = strategyService.createCustomStrategy(userId, name, req.getDescription(), scriptCode, conditions);
            log.info("自定义AI策略创建成功, strategyId={}, scriptLength={}", strategy.getId(), scriptCode.length());
            return ApiResponse.success(Map.of("id", strategy.getId(), "script", scriptCode));
        } catch (Exception e) {
            log.error("自定义AI策略创建失败, userId={}, error={}", userId, e.getMessage(), e);
            return ApiResponse.error(e.getMessage());
        }
    }

    @GetMapping("/{userId}")
    public ApiResponse<?> getUserStrategies(@PathVariable Integer userId) {
        log.info("查询用户策略列表, userId={}", userId);
        List<Strategy> strategies = strategyService.getUserStrategies(userId);
        log.info("用户策略列表查询完成, userId={}, count={}", userId, strategies.size());
        return ApiResponse.success(strategies);
    }

    @PostMapping("/{strategyId}/run")
    public ApiResponse<?> runStrategy(@PathVariable Integer strategyId) {
        log.info("执行策略请求, strategyId={}", strategyId);
        try {
            long start = System.currentTimeMillis();
            Map<String, Object> data = strategyService.runStrategyById(strategyId);
            log.info("策略执行完成, strategyId={}, 筛选出{}只股票, 耗时{}ms",
                    strategyId, data.get("count"), System.currentTimeMillis() - start);
            return ApiResponse.success(data);
        } catch (Exception e) {
            log.error("策略执行失败, strategyId={}, error={}", strategyId, e.getMessage(), e);
            return ApiResponse.error(e.getMessage());
        }
    }

    @PostMapping("/builtin/{strategyKey}/run")
    public ApiResponse<?> runBuiltinStrategy(
            @PathVariable String strategyKey,
            @RequestParam(value = "stock_limit", defaultValue = "0") int stockLimit,
            @RequestBody(required = false) Map<String, Object> params) {
        log.info("执行内置策略, key={}, stockLimit={}, params={}", strategyKey, stockLimit, params);
        long start = System.currentTimeMillis();
        Map<String, Object> data = strategyService.runBuiltinStrategy(strategyKey, params, stockLimit);
        if (data == null) {
            log.warn("内置策略不存在, key={}", strategyKey);
            return ApiResponse.error("策略不存在");
        }
        log.info("内置策略执行完成, key={}, 筛选出{}只股票, 耗时{}ms",
                strategyKey, data.get("count"), System.currentTimeMillis() - start);
        return ApiResponse.success(data);
    }
}
