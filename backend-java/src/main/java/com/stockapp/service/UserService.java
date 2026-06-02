package com.stockapp.service;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.stockapp.entity.User;
import com.stockapp.mapper.UserMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;

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
        User user = new User();
        user.setOpenid(openid);
        user.setNickname(nickname != null ? nickname : "");
        user.setPhone(phone != null ? phone : "");
        user.setCreatedAt(LocalDateTime.now());
        user.setIsActive(true);
        userMapper.insert(user);
        return user;
    }

    public User register(String phone, String password, String nickname) {
        String hash = passwordEncoder.encode(password);
        User user = new User();
        user.setOpenid("phone_" + phone);
        user.setPhone(phone);
        user.setNickname(nickname != null && !nickname.isEmpty() ? nickname : "用户" + phone.substring(phone.length() - 4));
        user.setPasswordHash(hash);
        user.setCreatedAt(LocalDateTime.now());
        user.setIsActive(true);
        userMapper.insert(user);
        return user;
    }

    public boolean checkPassword(User user, String rawPassword) {
        if (user.getPasswordHash() == null) return false;
        return passwordEncoder.matches(rawPassword, user.getPasswordHash());
    }
}
