package com.aiwear.exception;

import com.aiwear.common.Result;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

// 全局异常处理
// 兜住 DispatcherServlet 层的异常：ApiLogAspect 的切点是 Controller 方法，
// 而 multipart 解析异常在 handler 解析之前就已抛出，切面接不住，必须在这里统一转成 Result。
@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    // 上传文件超过 spring.servlet.multipart.max-file-size / max-request-size 时抛出
    // 注意：此时请求体尚未读完，必须配合 server.tomcat.max-swallow-size 才能把响应真正送达客户端
    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public Result<Void> handleMaxUploadSizeExceeded(MaxUploadSizeExceededException e) {
        log.warn("上传文件超过大小限制：{}", e.getMessage());
        return Result.serverError("图片大小超过限制");
    }
}
