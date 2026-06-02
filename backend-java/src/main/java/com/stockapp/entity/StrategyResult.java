package com.stockapp.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import java.time.LocalDateTime;

@Data
@TableName("strategy_results")
public class StrategyResult {
    @TableId(type = IdType.AUTO)
    private Integer id;
    private Integer strategyId;
    private String runDate;
    private String stocksJson;
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}
