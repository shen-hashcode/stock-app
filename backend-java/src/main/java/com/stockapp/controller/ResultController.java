package com.stockapp.controller;

import com.stockapp.dto.ApiResponse;
import com.stockapp.entity.StrategyResult;
import com.stockapp.service.StrategyService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@Slf4j
@RestController
@RequestMapping("/api/results")
@RequiredArgsConstructor
public class ResultController {

    private final StrategyService strategyService;

    @GetMapping("/{strategyId}")
    public ApiResponse<?> getResults(
            @PathVariable Integer strategyId,
            @RequestParam(value = "limit", defaultValue = "10") int limit) {
        log.info("查询策略执行结果, strategyId={}, limit={}", strategyId, limit);
        List<StrategyResult> results = strategyService.getResults(strategyId, limit);
        log.info("策略执行结果查询完成, strategyId={}, resultCount={}", strategyId, results.size());
        return ApiResponse.success(results);
    }
}
