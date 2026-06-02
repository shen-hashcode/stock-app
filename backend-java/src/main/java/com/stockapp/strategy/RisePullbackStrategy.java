package com.stockapp.strategy;

import com.stockapp.service.StockService;
import org.springframework.stereotype.Component;
import java.util.*;

@Component
public class RisePullbackStrategy implements BuiltinStrategy {

    @Override public String getKey() { return "rise_pullback"; }
    @Override public String getName() { return "涨幅回调"; }
    @Override public String getDescription() { return "前N日累计涨幅超过阈值，当日出现回调"; }

    @Override
    public Map<String, Object> getDefaultParams() {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("days", Map.of("type", "int", "default", 3, "label", "上涨天数"));
        params.put("rise_pct", Map.of("type", "float", "default", 13, "label", "涨幅阈值(%)"));
        params.put("market_cap_min", Map.of("type", "float", "default", 50, "label", "最低市值(亿)"));
        return params;
    }

    @Override
    public boolean check(Map<String, Object> stockInfo, Map<String, Object> params, StockService stockService) {
        String code = (String) stockInfo.get("code");
        String market = (String) stockInfo.get("market");
        double marketCap = toDouble(stockInfo.get("market_cap"));

        int days = toInt(params.getOrDefault("days", 3));
        double risePct = toDouble(params.getOrDefault("rise_pct", 13));
        double marketCapMin = toDouble(params.getOrDefault("market_cap_min", 50));

        if (marketCap < marketCapMin) return false;

        List<Map<String, Object>> klines = stockService.getKlineData(code, market, days + 2);
        if (klines == null || klines.size() < days + 1) return false;

        klines = klines.subList(klines.size() - (days + 1), klines.size());

        double openDay1 = toDouble(klines.get(0).get("open"));
        double closeDayN = toDouble(klines.get(days - 1).get("close"));
        if (openDay1 == 0) return false;
        double cumulativeGain = (closeDayN - openDay1) / openDay1 * 100;

        double todayClose = toDouble(klines.get(days).get("close"));
        double todayOpen = toDouble(klines.get(days).get("open"));

        return cumulativeGain > risePct && todayClose < todayOpen;
    }

    private double toDouble(Object v) { return v instanceof Number ? ((Number) v).doubleValue() : 0; }
    private int toInt(Object v) { return v instanceof Number ? ((Number) v).intValue() : 0; }
}
