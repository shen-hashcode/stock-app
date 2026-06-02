package com.stockapp.service;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.stockapp.entity.User;
import com.stockapp.mapper.UserMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;

@Slf4j
@Service
@RequiredArgsConstructor
public class UserService {

    private final UserMapper userMapper;
    private final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

    public User findByOpenid(String openid) {
        return userMapper.selectOne(new QueryWrapper<User>().eq("openid", openid));
    }

    public User findByPhone(String phone) {
        return userMapper.selectOne(new QueryWrapper<User>().eq("phone", phone));
    }

    public User createByOpenid(String openid, String nickname, String phone) {
        log.info("创建用户, openid={}, nickname={}", openid, nickname);
        User user = new User();
        user.setOpenid(openid);
        user.setNickname(nickname != null ? nickname : "");
        user.setPhone(phone != null ? phone : "");
        user.setCreatedAt(LocalDateTime.now());
        user.setIsActive(true);
        userMapper.insert(user);
        log.info("用户创建完成, id={}", user.getId());
        return user;
    }

    public User register(String phone, String password, String nickname) {
        log.info("用户注册, phone={}", phone);
        String hash = passwordEncoder.encode(password);
        User user = new User();
        user.setOpenid("phone_" + phone);
        user.setPhone(phone);
        user.setNickname(nickname != null && !nickname.isEmpty() ? nickname : "用户" + phone.substring(phone.length() - 4));
        user.setPasswordHash(hash);
        user.setCreatedAt(LocalDateTime.now());
        user.setIsActive(true);
        userMapper.insert(user);
        log.info("用户注册完成, id={}, phone={}", user.getId(), user.getPhone());
        return user;
    }

    public boolean checkPassword(User user, String rawPassword) {
        if (user.getPasswordHash() == null) return false;
        return passwordEncoder.matches(rawPassword, user.getPasswordHash());
    }
}
