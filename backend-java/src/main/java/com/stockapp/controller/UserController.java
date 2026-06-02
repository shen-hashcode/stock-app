package com.stockapp.controller;

import com.stockapp.dto.*;
import com.stockapp.entity.User;
import com.stockapp.service.UserService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class UserController {

    private final UserService userService;

    @PostMapping("/users")
    public ApiResponse<?> createUser(@RequestBody UserCreateRequest req) {
        User user = userService.findByOpenid(req.getOpenid());
        if (user != null) {
            return ApiResponse.success(Map.of("id", user.getId(), "openid", user.getOpenid()));
        }
        user = userService.createByOpenid(req.getOpenid(), req.getNickname(), req.getPhone());
        return ApiResponse.success(Map.of("id", user.getId(), "openid", user.getOpenid()));
    }

    @PostMapping("/register")
    public ApiResponse<?> register(@RequestBody UserRegisterRequest req) {
        if (req.getPhone() == null || req.getPhone().length() != 11) {
            return ApiResponse.error("请输入正确的11位手机号");
        }
        if (req.getPassword() == null || req.getPassword().length() < 6) {
            return ApiResponse.error("密码至少6位");
        }
        User existing = userService.findByPhone(req.getPhone());
        if (existing != null) {
            return ApiResponse.error("该手机号已注册");
        }
        User user = userService.register(req.getPhone(), req.getPassword(), req.getNickname());
        return ApiResponse.success(Map.of("id", user.getId(), "phone", user.getPhone(), "nickname", user.getNickname()));
    }

    @PostMapping("/login")
    public ApiResponse<?> login(@RequestBody UserLoginRequest req) {
        User user = userService.findByPhone(req.getPhone());
        if (user == null || !userService.checkPassword(user, req.getPassword())) {
            return ApiResponse.error("手机号或密码错误");
        }
        return ApiResponse.success(Map.of("id", user.getId(), "phone", user.getPhone(), "nickname", user.getNickname() != null ? user.getNickname() : ""));
    }
}
