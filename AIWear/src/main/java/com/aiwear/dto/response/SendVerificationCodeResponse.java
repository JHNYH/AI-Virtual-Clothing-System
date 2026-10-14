package com.aiwear.dto.response;

import lombok.Builder;
import lombok.Data;

// 发送验证码的响应实体类
@Data
@Builder
public class SendVerificationCodeResponse {

    private String sendTo;

    private Integer expireTime;
}
