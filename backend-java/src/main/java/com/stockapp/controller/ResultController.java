package com.stockapp.controller;

import com.stockapp.dto.ApiResponse;
import com.stockapp.entity.StrategyResult;
import com.stockapp.service.StrategyService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/results")
@RequiredArgsConstructor
public class ResultController {

    private final StrategyService strategyService;

    @GetMapping("/{strategyId}")
    public ApiResponse<?> getResults(
            @PathVariable Integer strategyId,
            @RequestParam(value = "limit", defaultValue = "10") int limit) {
        List<StrategyResult> results = strategyService.getResults(strategyId, limit);
        return ApiResponse.success(results);
    }
}
