package com.stockapp.strategy;

import com.stockapp.service.StockService;
import org.springframework.stereotype.Component;
import java.util.*;

@Component
public class LimitUpOpenStrategy implements BuiltinStrategy {

    @Override public String getKey() { return "limit_up_open"; }
    @Override public String getName() { return "涨停开板"; }
    @Override public String getDescription() { return "昨日涨停，今日开板低开"; }

    @Override
    public Map<String, Object> getDefaultParams() {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("market_cap_min", Map.of("type", "float", "default", 50, "label", "最低市值(亿)"));
        return params;
    }

    @Override
    public boolean check(Map<String, Object> stockInfo, Map<String, Object> params, StockService stockService) {
        String code = (String) stockInfo.get("code");
        String market = (String) stockInfo.get("market");
        double marketCap = toDouble(stockInfo.get("market_cap"));

        double marketCapMin = toDouble(params.getOrDefault("market_cap_min", 50));
        if (marketCap < marketCapMin) return false;

        List<Map<String, Object>> klines = stockService.getKlineData(code, market, 3);
        if (klines == null || klines.size() < 3) return false;

        double dayBeforeClose = toDouble(klines.get(klines.size() - 3).get("close"));
        double yesterdayClose = toDouble(klines.get(klines.size() - 2).get("close"));
        if (dayBeforeClose == 0) return false;

        double yesterdayChange = (yesterdayClose - dayBeforeClose) / dayBeforeClose * 100;

        double todayOpen = toDouble(klines.get(klines.size() - 1).get("open"));
        double todayClose = toDouble(klines.get(klines.size() - 1).get("close"));

        return yesterdayChange >= 9.8 && todayClose > todayOpen;
    }

    private double toDouble(Object v) { return v instanceof Number ? ((Number) v).doubleValue() : 0; }
}
