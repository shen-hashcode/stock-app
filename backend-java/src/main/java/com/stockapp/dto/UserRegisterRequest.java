package com.stockapp.dto;

import lombok.Data;

@Data
public class UserRegisterRequest {
    private String phone;
    private String password;
    private String nickname;
}
