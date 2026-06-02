package com.stockapp.strategy;

import com.stockapp.service.StockService;
import java.util.Map;

public interface BuiltinStrategy {
    String getKey();
    String getName();
    String getDescription();
    Map<String, Object> getDefaultParams();
    boolean check(Map<String, Object> stockInfo, Map<String, Object> params, StockService stockService);
}
