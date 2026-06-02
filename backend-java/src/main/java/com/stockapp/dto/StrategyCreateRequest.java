package com.stockapp.dto;

import lombok.Data;

@Data
public class StrategyCreateRequest {
    private String name;
    private String description;
    private String conditions;
}
