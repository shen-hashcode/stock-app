package com.stockapp.strategy;

import com.stockapp.service.StockService;
import org.springframework.stereotype.Component;
import java.util.*;

@Component
public class ConsecutiveRiseStrategy implements BuiltinStrategy {

    @Override public String getKey() { return "consecutive_rise"; }
    @Override public String getName() { return "连续上涨"; }
    @Override public String getDescription() { return "连续N天收阳线"; }

    @Override
    public Map<String, Object> getDefaultParams() {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("days", Map.of("type", "int", "default", 3, "label", "连续天数"));
        params.put("market_cap_min", Map.of("type", "float", "default", 50, "label", "最低市值(亿)"));
        return params;
    }

    @Override
    public boolean check(Map<String, Object> stockInfo, Map<String, Object> params, StockService stockService) {
        String code = (String) stockInfo.get("code");
        String market = (String) stockInfo.get("market");
        double marketCap = toDouble(stockInfo.get("market_cap"));

        int days = toInt(params.getOrDefault("days", 3));
        double marketCapMin = toDouble(params.getOrDefault("market_cap_min", 50));

        if (marketCap < marketCapMin) return false;

        List<Map<String, Object>> klines = stockService.getKlineData(code, market, days + 1);
        if (klines == null || klines.size() < days + 1) return false;

        List<Map<String, Object>> recent = klines.subList(klines.size() - (days + 1), klines.size());
        for (int i = 1; i <= days; i++) {
            if (toDouble(recent.get(i).get("close")) <= toDouble(recent.get(i - 1).get("close"))) {
                return false;
            }
        }
        return true;
    }

    private double toDouble(Object v) { return v instanceof Number ? ((Number) v).doubleValue() : 0; }
    private int toInt(Object v) { return v instanceof Number ? ((Number) v).intValue() : 0; }
}
