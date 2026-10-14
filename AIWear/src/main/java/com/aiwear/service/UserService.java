package com.aiwear.service;

import com.aiwear.dto.request.AuthRequest;
import com.aiwear.dto.request.SendVerificationCodeRequest;
import com.aiwear.dto.response.AuthResponse;
import jakarta.validation.Valid;

// 用户模块服务接口
public interface UserService {

    // 发送验证码
    boolean sendVerificationCode(SendVerificationCodeRequest request);

    // 认证注册/登录
    AuthResponse auth(@Valid AuthRequest request);

    // 用户登出系统
    boolean logut(String authorization);
}
