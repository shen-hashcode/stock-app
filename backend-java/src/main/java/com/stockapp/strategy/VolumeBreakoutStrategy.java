package com.stockapp.strategy;

import com.stockapp.service.StockService;
import org.springframework.stereotype.Component;
import java.util.*;

@Component
public class VolumeBreakoutStrategy implements BuiltinStrategy {

    @Override public String getKey() { return "volume_breakout"; }
    @Override public String getName() { return "放量突破"; }
    @Override public String getDescription() { return "成交量突然放大，且价格上涨"; }

    @Override
    public Map<String, Object> getDefaultParams() {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("days", Map.of("type", "int", "default", 20, "label", "均量天数"));
        params.put("volume_ratio", Map.of("type", "float", "default", 2.0, "label", "量比阈值"));
        params.put("market_cap_min", Map.of("type", "float", "default", 50, "label", "最低市值(亿)"));
        return params;
    }

    @Override
    public boolean check(Map<String, Object> stockInfo, Map<String, Object> params, StockService stockService) {
        String code = (String) stockInfo.get("code");
        String market = (String) stockInfo.get("market");
        double marketCap = toDouble(stockInfo.get("market_cap"));

        int days = toInt(params.getOrDefault("days", 20));
        double volumeRatio = toDouble(params.getOrDefault("volume_ratio", 2.0));
        double marketCapMin = toDouble(params.getOrDefault("market_cap_min", 50));

        if (marketCap < marketCapMin) return false;

        List<Map<String, Object>> klines = stockService.getKlineData(code, market, days + 1);
        if (klines == null || klines.size() < days + 1) return false;

        double avgVolume = 0;
        for (int i = klines.size() - days - 1; i < klines.size() - 1; i++) {
            avgVolume += toDouble(klines.get(i).get("volume"));
        }
        avgVolume /= days;
        if (avgVolume == 0) return false;

        double todayVolume = toDouble(klines.get(klines.size() - 1).get("volume"));
        double todayClose = toDouble(klines.get(klines.size() - 1).get("close"));
        double yesterdayClose = toDouble(klines.get(klines.size() - 2).get("close"));

        return todayVolume > avgVolume * volumeRatio && todayClose > yesterdayClose;
    }

    private double toDouble(Object v) { return v instanceof Number ? ((Number) v).doubleValue() : 0; }
    private int toInt(Object v) { return v instanceof Number ? ((Number) v).intValue() : 0; }
}
