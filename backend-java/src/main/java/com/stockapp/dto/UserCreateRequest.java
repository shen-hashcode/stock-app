package com.stockapp.dto;

import lombok.Data;

@Data
public class UserCreateRequest {
    private String openid;
    private String nickname;
    private String phone;
}
