package com.aiwear;

// 服务启动类

import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@Slf4j
// 服务启动类
public class AIWearApplication {
    public static void main(String[] args) {
        log.info("衣览无余项目启动成功");
        SpringApplication.run(AIWearApplication.class, args);
    }
}
