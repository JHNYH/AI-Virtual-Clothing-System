package com.aiwear.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.aiwear.dto.request.AuthRequest;
import com.aiwear.dto.request.SendVerificationCodeRequest;
import com.aiwear.dto.response.AuthResponse;
import com.aiwear.entity.User;
import com.aiwear.mapper.UserMapper;
import com.aiwear.service.UserService;
import com.aiwear.util.EmailService;
import com.aiwear.util.JwtUtil;
import com.aiwear.util.VerificationCodeService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

// 用户实现类
@Slf4j
@Service
public class UserServiceImpl implements UserService {

    @Autowired
    private EmailService emailService;

    @Autowired
    private VerificationCodeService verificationCodeService;

    @Autowired
    private UserMapper userMapper;

    @Autowired
    private JwtUtil jwtUtil;

    // 做密码加解密、校验的对象
    private final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder();


    @Override
    public boolean sendVerificationCode(SendVerificationCodeRequest request) {
        String email = request.getEmail();
        if (verificationCodeService.hasCode(email)) {
            throw new RuntimeException("验证码尚未过期，请勿重复发送");
        }
        String code = verificationCodeService.generateCode();
        verificationCodeService.saveCode(email, code);

        return emailService.sendVerificationCode(email, code);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AuthResponse auth(AuthRequest request) {
        // 1. 获取用户名
        String account = request.getAccount();
        // 2. 判断当前认证方式
        boolean isEmail = account.contains("@");
        // 3. 查询用户是否存在
        LambdaQueryWrapper<User> queryWrapper = new LambdaQueryWrapper<>();
        queryWrapper.eq(User::getUsername, account);
        User user = userMapper.selectOne(queryWrapper);
        // 4. 邮箱+验证码的方式
        if (isEmail) {
            String code = request.getVerificationCode();
            if (code == null || code.isEmpty()) {
                throw new RuntimeException("验证码不能为空");
            }
            // 5. 验证一下验证码
            if (!verificationCodeService.verifyCode(account, code)) {
                throw new RuntimeException("验证码不存在或者已经过期");
            }
            // 6. 处理新老用户
            if (user == null) {
                user = new User();
                user.setUsername(account);
                user.setEmail(account);
                userMapper.insert(user);
                log.info("新用户注册成功，邮箱{}", user.getEmail());
            }
        } else {
            // 7. 用户名+密码
            if (user == null) {
                user = new User();
                user.setUsername(account);
                if (request.getPassword() == null || request.getPassword() == "") {
                    throw new RuntimeException("密码不能为空");
                }
                user.setPasswordhash(passwordEncoder.encode(request.getPassword()));
                userMapper.insert(user);
            } else {
                // 8. 校验请求参数中的密码
                if (user.getPasswordhash() == null || !passwordEncoder.matches(request.getPassword(), user.getPasswordhash())) {
                    throw new RuntimeException("用户名或密码错误");
                }
            }
        }

        return createResponse(user);
    }

    @Override
    public boolean logut(String authorization) {
        String token = jwtUtil.parseToken(authorization);
        return jwtUtil.removeToken(token);
    }

    // 返回认证的响应
    private AuthResponse createResponse(User user) {
        AuthResponse response = new AuthResponse();
        response.setUserId(user.getId());
        response.setUsername(user.getUsername());
        response.setEmail(user.getEmail());
        response.setToken(jwtUtil.generateToken(user));
        return response;
    }
}
