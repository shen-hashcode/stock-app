package com.stockapp.controller;

import com.stockapp.dto.*;
import com.stockapp.entity.User;
import com.stockapp.service.UserService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class UserController {

    private final UserService userService;

    @PostMapping("/users")
    public ApiResponse<?> createUser(@RequestBody UserCreateRequest req) {
        log.info("用户创建/查询请求, openid={}", req.getOpenid());
        User user = userService.findByOpenid(req.getOpenid());
        if (user != null) {
            log.info("用户已存在, id={}, openid={}", user.getId(), user.getOpenid());
            return ApiResponse.success(Map.of("id", user.getId(), "openid", user.getOpenid()));
        }
        user = userService.createByOpenid(req.getOpenid(), req.getNickname(), req.getPhone());
        log.info("新用户创建成功, id={}, openid={}", user.getId(), user.getOpenid());
        return ApiResponse.success(Map.of("id", user.getId(), "openid", user.getOpenid()));
    }

    @PostMapping("/register")
    public ApiResponse<?> register(@RequestBody UserRegisterRequest req) {
        log.info("用户注册请求, phone={}", req.getPhone());
        if (req.getPhone() == null || req.getPhone().length() != 11) {
            log.warn("注册失败: 手机号格式错误, phone={}", req.getPhone());
            return ApiResponse.error("请输入正确的11位手机号");
        }
        if (req.getPassword() == null || req.getPassword().length() < 6) {
            log.warn("注册失败: 密码过短, phone={}", req.getPhone());
            return ApiResponse.error("密码至少6位");
        }
        User existing = userService.findByPhone(req.getPhone());
        if (existing != null) {
            log.warn("注册失败: 手机号已注册, phone={}", req.getPhone());
            return ApiResponse.error("该手机号已注册");
        }
        User user = userService.register(req.getPhone(), req.getPassword(), req.getNickname());
        log.info("用户注册成功, id={}, phone={}", user.getId(), user.getPhone());
        return ApiResponse.success(Map.of("id", user.getId(), "phone", user.getPhone(), "nickname", user.getNickname()));
    }

    @PostMapping("/login")
    public ApiResponse<?> login(@RequestBody UserLoginRequest req) {
        log.info("用户登录请求, phone={}", req.getPhone());
        User user = userService.findByPhone(req.getPhone());
        if (user == null || !userService.checkPassword(user, req.getPassword())) {
            log.warn("登录失败: 手机号或密码错误, phone={}", req.getPhone());
            return ApiResponse.error("手机号或密码错误");
        }
        log.info("用户登录成功, id={}, phone={}", user.getId(), user.getPhone());
        return ApiResponse.success(Map.of("id", user.getId(), "phone", user.getPhone(), "nickname", user.getNickname() != null ? user.getNickname() : ""));
    }
}
