package com.stockapp.service;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONArray;
import com.alibaba.fastjson2.JSONObject;
import lombok.extern.slf4j.Slf4j;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.*;
import java.util.concurrent.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Slf4j
@Service
public class StockService {

    private static final String QQ_QUOTE_URL = "https://qt.gtimg.cn/q=";
    private static final String QQ_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get";
    private static final int BATCH_SIZE = 80;
    private static final long CACHE_DURATION = 3600_000L;

    private final OkHttpClient httpClient = new OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(10, TimeUnit.SECONDS)
            .build();

    private List<Map<String, Object>> cachedStockList = null;
    private long cacheTimestamp = 0;

    /**
     * 获取实时行情
     */
    public Map<String, Object> getRealtimeQuote(String code, String market) {
        try {
            String url = QQ_QUOTE_URL + market + code;
            Request request = new Request.Builder().url(url).build();
            try (Response response = httpClient.newCall(request).execute()) {
                String body = response.body().string();
                String[] parts = body.split("~");
                if (parts.length < 46) return null;

                Map<String, Object> quote = new HashMap<>();
                quote.put("price", parseDouble(parts[3]));
                quote.put("change_pct", parseDouble(parts[32]));
                quote.put("volume", parseDouble(parts[36]));
                quote.put("open", parseDouble(parts[5]));
                quote.put("high", parseDouble(parts[33]));
                quote.put("low", parseDouble(parts[34]));
                quote.put("market_cap", parseDouble(parts[45]));
                return quote;
            }
        } catch (Exception e) {
            log.warn("获取行情失败: {}_{} - {}", market, code, e.getMessage());
            return null;
        }
    }

    /**
     * 获取K线数据
     */
    public List<Map<String, Object>> getKlineData(String code, String market, int days) {
        try {
            String param = market + code + ",day,,," + days + ",qfq";
            String url = QQ_KLINE_URL + "?_var=kline_dayqfq&param=" + param;
            Request request = new Request.Builder()
                    .url(url)
                    .header("User-Agent", "Mozilla/5.0")
                    .header("Referer", "https://web.ifzq.gtimg.cn/")
                    .build();

            try (Response response = httpClient.newCall(request).execute()) {
                String body = response.body().string();
                Pattern pattern = Pattern.compile("=(\\{.*\\})");
                Matcher matcher = pattern.matcher(body);
                if (!matcher.find()) return Collections.emptyList();

                JSONObject json = JSON.parseObject(matcher.group(1));
                if (json.getIntValue("code") != 0) return Collections.emptyList();

                JSONObject data = json.getJSONObject("data");
                if (data == null) return Collections.emptyList();

                JSONObject stockData = data.getJSONObject(market + code);
                if (stockData == null) return Collections.emptyList();

                JSONArray klineArray = stockData.getJSONArray("qfqday");
                if (klineArray == null) klineArray = stockData.getJSONArray("day");
                if (klineArray == null) return Collections.emptyList();

                List<Map<String, Object>> result = new ArrayList<>();
                for (int i = 0; i < klineArray.size(); i++) {
                    JSONArray item = klineArray.getJSONArray(i);
                    if (item.size() < 6) continue;
                    Map<String, Object> kline = new HashMap<>();
                    kline.put("day", item.getString(0));
                    kline.put("open", Double.parseDouble(item.getString(1)));
                    kline.put("close", Double.parseDouble(item.getString(2)));
                    kline.put("high", Double.parseDouble(item.getString(3)));
                    kline.put("low", Double.parseDouble(item.getString(4)));
                    kline.put("volume", Double.parseDouble(item.getString(5)));
                    result.add(kline);
                }
                return result;
            }
        } catch (Exception e) {
            log.warn("获取K线失败: {}_{} - {}", market, code, e.getMessage());
            return Collections.emptyList();
        }
    }

    /**
     * 快速获取股票列表（限制数量）
     */
    public List<Map<String, Object>> getStockListQuick(int limit) {
        List<Map<String, Object>> fullList = getStockList();
        if (limit <= 0 || limit >= fullList.size()) return fullList;
        return fullList.subList(0, limit);
    }

    /**
     * 获取全量股票列表（带缓存）
     */
    public synchronized List<Map<String, Object>> getStockList() {
        if (cachedStockList != null && System.currentTimeMillis() - cacheTimestamp < CACHE_DURATION) {
            return cachedStockList;
        }

        log.info("开始刷新股票列表缓存...");
        List<String[]> allCodes = generateStockCodes();
        List<Map<String, Object>> validStocks = new ArrayList<>();

        for (int i = 0; i < allCodes.size(); i += BATCH_SIZE) {
            int end = Math.min(i + BATCH_SIZE, allCodes.size());
            List<String[]> batch = allCodes.subList(i, end);
            List<Map<String, Object>> batchResult = validateBatch(batch);
            validStocks.addAll(batchResult);

            try { Thread.sleep(100); } catch (InterruptedException ignored) {}
        }

        log.info("股票列表缓存完成，共 {} 只", validStocks.size());
        cachedStockList = validStocks;
        cacheTimestamp = System.currentTimeMillis();
        return cachedStockList;
    }

    private List<String[]> generateStockCodes() {
        List<String[]> codes = new ArrayList<>();
        // 上海主板 600000-603999
        for (int i = 600000; i <= 603999; i++) codes.add(new String[]{String.valueOf(i), "sh"});
        // 上海科创板 688000-689999
        for (int i = 688000; i <= 689999; i++) codes.add(new String[]{String.valueOf(i), "sh"});
        // 深圳主板 000001-002999
        for (int i = 1; i <= 2999; i++) codes.add(new String[]{String.format("%06d", i), "sz"});
        // 深圳创业板 300000-301999
        for (int i = 300000; i <= 301999; i++) codes.add(new String[]{String.valueOf(i), "sz"});
        return codes;
    }

    private List<Map<String, Object>> validateBatch(List<String[]> batch) {
        List<Map<String, Object>> results = new ArrayList<>();
        StringBuilder sb = new StringBuilder();
        for (String[] code : batch) {
            if (sb.length() > 0) sb.append(",");
            sb.append(code[1]).append(code[0]);
        }

        try {
            String url = QQ_QUOTE_URL + sb;
            Request request = new Request.Builder().url(url).build();
            try (Response response = httpClient.newCall(request).execute()) {
                String body = response.body().string();
                String[] lines = body.split(";");
                for (String line : lines) {
                    if (line.isBlank() || !line.contains("~")) continue;
                    String[] parts = line.split("~");
                    if (parts.length < 46) continue;

                    String name = parts[1].replace("\"", "").trim();
                    String code = parts[2];
                    if (name.isEmpty() || name.contains("ST") || name.contains("退")) continue;
                    if (code.startsWith("8")) continue;

                    double marketCap = parseDouble(parts[45]);
                    String market = code.startsWith("6") ? "sh" : "sz";

                    Map<String, Object> stock = new HashMap<>();
                    stock.put("code", code);
                    stock.put("name", name);
                    stock.put("market", market);
                    stock.put("market_cap", marketCap);
                    results.add(stock);
                }
            }
        } catch (Exception e) {
            log.warn("批量验证失败: {}", e.getMessage());
        }
        return results;
    }

    private double parseDouble(String s) {
        try {
            return Double.parseDouble(s.trim());
        } catch (Exception e) {
            return 0.0;
        }
    }
}
