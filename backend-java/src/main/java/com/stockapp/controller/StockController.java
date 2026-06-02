package com.stockapp.controller;

import com.stockapp.dto.ApiResponse;
import com.stockapp.service.StockService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/stock")
@RequiredArgsConstructor
public class StockController {

    private final StockService stockService;

    @GetMapping("/{code}")
    public ApiResponse<?> getStockInfo(@PathVariable String code, @RequestParam String market) {
        Map<String, Object> quote = stockService.getRealtimeQuote(code, market);
        List<Map<String, Object>> kline = stockService.getKlineData(code, market, 10);

        Map<String, Object> data = new HashMap<>();
        data.put("quote", quote);
        data.put("kline", kline.size() > 10 ? kline.subList(kline.size() - 10, kline.size()) : kline);
        return ApiResponse.success(data);
    }
}
