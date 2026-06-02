package com.stockapp.service;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import lombok.extern.slf4j.Slf4j;
import okhttp3.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

@Slf4j
@Service
public class LlmService {

    @Value("${app.llm.api-key:}")
    private String apiKey;

    @Value("${app.llm.api-url:https://api.deepseek.com/v1/chat/completions}")
    private String apiUrl;

    @Value("${app.llm.model:deepseek-chat}")
    private String model;

    private final OkHttpClient httpClient = new OkHttpClient.Builder()
            .connectTimeout(60, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .build();

    private static final String STRATEGY_PROMPT = """
            你是一个Python量化选股脚本生成器。用户会描述选股条件，你需要生成一个Python函数。

            要求：
            1. 函数名必须为 check_stock(stock_info)
            2. stock_info 是一个字典，包含: code(股票代码), name(名称), market(市场sh/sz), market_cap(市值,亿)
            3. 可以调用以下已导入的函数:
               - get_kline_data(code, market, days=10): 返回K线列表，每项为dict含 day,open,close,high,low,volume
               - get_realtime_quote(code, market): 返回dict含 price,change_pct,volume,open,high,low,market_cap
            4. 函数返回 True 表示符合条件，False 表示不符合
            5. 只输出纯Python代码，不要markdown标记，不要解释

            用户条件：%s
            """;

    public String generateStrategyScript(String description) throws Exception {
        if (apiKey == null || apiKey.isEmpty()) {
            throw new RuntimeException("未配置LLM_API_KEY环境变量，无法生成AI策略");
        }

        JSONObject payload = new JSONObject();
        payload.put("model", model);
        payload.put("temperature", 0.3);
        payload.put("max_tokens", 2000);
        payload.put("messages", List.of(
                Map.of("role", "system", "content", "你是一个专业的Python量化选股脚本生成器，只输出代码。"),
                Map.of("role", "user", "content", String.format(STRATEGY_PROMPT, description))
        ));

        RequestBody body = RequestBody.create(
                payload.toJSONString(),
                MediaType.get("application/json; charset=utf-8")
        );

        Request request = new Request.Builder()
                .url(apiUrl)
                .header("Authorization", "Bearer " + apiKey)
                .post(body)
                .build();

        try (Response response = httpClient.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new RuntimeException("LLM API调用失败: " + response.code());
            }
            String respBody = response.body().string();
            JSONObject json = JSON.parseObject(respBody);
            String content = json.getJSONArray("choices")
                    .getJSONObject(0)
                    .getJSONObject("message")
                    .getString("content");

            // 去除markdown代码块标记
            content = content.trim();
            content = content.replaceAll("^```python\\s*\\n?", "");
            content = content.replaceAll("\\n?```\\s*$", "");
            return content.trim();
        }
    }
}
