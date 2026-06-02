package com.stockapp.strategy;

import com.stockapp.service.StockService;
import org.springframework.stereotype.Component;
import java.util.*;

@Component
public class MaGoldenCrossStrategy implements BuiltinStrategy {

    @Override public String getKey() { return "ma_golden_cross"; }
    @Override public String getName() { return "均线金叉"; }
    @Override public String getDescription() { return "短期均线上穿长期均线"; }

    @Override
    public Map<String, Object> getDefaultParams() {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("short_ma", Map.of("type", "int", "default", 5, "label", "短期均线"));
        params.put("long_ma", Map.of("type", "int", "default", 20, "label", "长期均线"));
        params.put("market_cap_min", Map.of("type", "float", "default", 50, "label", "最低市值(亿)"));
        return params;
    }

    @Override
    public boolean check(Map<String, Object> stockInfo, Map<String, Object> params, StockService stockService) {
        String code = (String) stockInfo.get("code");
        String market = (String) stockInfo.get("market");
        double marketCap = toDouble(stockInfo.get("market_cap"));

        int shortMa = toInt(params.getOrDefault("short_ma", 5));
        int longMa = toInt(params.getOrDefault("long_ma", 20));
        double marketCapMin = toDouble(params.getOrDefault("market_cap_min", 50));

        if (marketCap < marketCapMin) return false;

        List<Map<String, Object>> klines = stockService.getKlineData(code, market, longMa + 2);
        if (klines == null || klines.size() < longMa + 2) return false;

        List<Double> closes = new ArrayList<>();
        for (Map<String, Object> k : klines) closes.add(toDouble(k.get("close")));

        // 昨日均线
        double shortYesterday = ma(closes.subList(0, closes.size() - 1), shortMa);
        double longYesterday = ma(closes.subList(0, closes.size() - 1), longMa);
        // 今日均线
        double shortToday = ma(closes, shortMa);
        double longToday = ma(closes, longMa);

        if (shortYesterday == 0 || longYesterday == 0 || shortToday == 0 || longToday == 0) return false;

        return shortYesterday <= longYesterday && shortToday > longToday;
    }

    private double ma(List<Double> data, int period) {
        if (data.size() < period) return 0;
        double sum = 0;
        for (int i = data.size() - period; i < data.size(); i++) sum += data.get(i);
        return sum / period;
    }

    private double toDouble(Object v) { return v instanceof Number ? ((Number) v).doubleValue() : 0; }
    private int toInt(Object v) { return v instanceof Number ? ((Number) v).intValue() : 0; }
}
