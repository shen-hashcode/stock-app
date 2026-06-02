package com.stockapp.controller;

import com.alibaba.fastjson2.JSON;
import com.stockapp.dto.*;
import com.stockapp.entity.Strategy;
import com.stockapp.service.LlmService;
import com.stockapp.service.StrategyService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/strategies")
@RequiredArgsConstructor
public class StrategyController {

    private final StrategyService strategyService;
    private final LlmService llmService;

    @GetMapping("/builtin")
    public ApiResponse<?> getBuiltinStrategies() {
        return ApiResponse.success(strategyService.getBuiltinStrategies());
    }

    @PostMapping("")
    public ApiResponse<?> createStrategy(@RequestParam("user_id") Integer userId, @RequestBody StrategyCreateRequest req) {
        Strategy strategy = strategyService.createStrategy(userId, req.getName(), req.getDescription(), req.getConditions());
        return ApiResponse.success(Map.of("id", strategy.getId()));
    }

    @PostMapping("/custom")
    public ApiResponse<?> createCustomStrategy(@RequestParam("user_id") Integer userId, @RequestBody CustomStrategyRequest req) {
        try {
            String scriptCode = llmService.generateStrategyScript(req.getDescription());
            String name = req.getName() != null && !req.getName().trim().isEmpty()
                    ? req.getName().trim().substring(0, Math.min(req.getName().trim().length(), 50))
                    : "自定义策略";
            String conditions = JSON.toJSONString(Map.of("type", "custom", "description", req.getDescription()));
            Strategy strategy = strategyService.createCustomStrategy(userId, name, req.getDescription(), scriptCode, conditions);
            return ApiResponse.success(Map.of("id", strategy.getId(), "script", scriptCode));
        } catch (Exception e) {
            return ApiResponse.error(e.getMessage());
        }
    }

    @GetMapping("/{userId}")
    public ApiResponse<?> getUserStrategies(@PathVariable Integer userId) {
        List<Strategy> strategies = strategyService.getUserStrategies(userId);
        return ApiResponse.success(strategies);
    }

    @PostMapping("/{strategyId}/run")
    public ApiResponse<?> runStrategy(@PathVariable Integer strategyId) {
        try {
            Map<String, Object> data = strategyService.runStrategyById(strategyId);
            return ApiResponse.success(data);
        } catch (Exception e) {
            return ApiResponse.error(e.getMessage());
        }
    }

    @PostMapping("/builtin/{strategyKey}/run")
    public ApiResponse<?> runBuiltinStrategy(
            @PathVariable String strategyKey,
            @RequestParam(value = "stock_limit", defaultValue = "0") int stockLimit,
            @RequestBody(required = false) Map<String, Object> params) {
        Map<String, Object> data = strategyService.runBuiltinStrategy(strategyKey, params, stockLimit);
        if (data == null) {
            return ApiResponse.error("策略不存在");
        }
        return ApiResponse.success(data);
    }
}
