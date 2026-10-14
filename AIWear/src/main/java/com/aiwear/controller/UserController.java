package com.aiwear.controller;

import com.aiwear.common.Result;
import com.aiwear.dto.request.AuthRequest;
import com.aiwear.dto.request.SendVerificationCodeRequest;
import com.aiwear.dto.response.AuthResponse;
import com.aiwear.dto.response.SendVerificationCodeResponse;
import com.aiwear.log.ApiLog;
import com.aiwear.service.UserService;
import jakarta.validation.Valid;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

// 用户模块的控制器
@RestController
@Slf4j
@RequestMapping("/api/user")
public class UserController {

    @Autowired
    private UserService userService;


    // 发送邮箱验证码
    @ApiLog
    @PostMapping("/send-code")
    public Result<SendVerificationCodeResponse> sendVerificationCode(@RequestBody @Valid SendVerificationCodeRequest request) {
        boolean success = userService.sendVerificationCode(request);
        if (success) {
            return Result.success("验证码发送成功", SendVerificationCodeResponse.builder().sendTo("***").expireTime(300).build());
        } else {
            return Result.serverError("验证码发送失败，请稍后重试");
        }
    }

    // 统一认证接口
    @ApiLog
    @PostMapping("/auth")
    public Result<AuthResponse> auth(@RequestBody @Valid AuthRequest request) {
        return Result.success("操作成功", userService.auth(request));
    }

    // 用户登出
    @ApiLog
    @PostMapping("/logout")
    public Result<String> logout(@RequestHeader(value = "Authorization") String authorization) {
        boolean success = userService.logut(authorization);
        if (success) {
            return Result.success("退出成功", "退出成功");
        } else {
            return Result.serverError("退出失败，请稍后重试");
        }
    }
}
