package com.stockapp.config;

import com.stockapp.strategy.BuiltinStrategy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Configuration
public class StrategyConfig {

    @Bean
    public Map<String, BuiltinStrategy> builtinStrategyMap(List<BuiltinStrategy> strategies) {
        Map<String, BuiltinStrategy> map = new LinkedHashMap<>();
        for (BuiltinStrategy s : strategies) {
            map.put(s.getKey(), s);
        }
        return map;
    }
}
