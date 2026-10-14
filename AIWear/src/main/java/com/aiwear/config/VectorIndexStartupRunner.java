package com.aiwear.config;

import com.aiwear.service.ImageIndexService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

// 启动时对检索索引做一次全量对账。
//
// 为什么放在启动时：Redis 是可随时重建的索引，但如果没人触发重建，
// 索引丢了就会表现为「图片看得见、搜不到」。应用启动是最自然的触发点，
// 不需要额外的定时任务。
//
// 本地开发与线上共用同一个 Redis 实例时，启动对账会直接改动线上数据，
// 所以用 aiwear.vector.startup-reconcile 开关控制，本地务必置 false。
@Slf4j
@Component
public class VectorIndexStartupRunner implements ApplicationRunner {

    @Value("${aiwear.vector.startup-reconcile:true}")
    private boolean startupReconcile;

    @Autowired
    private ImageIndexService imageIndexService;

    @Override
    public void run(ApplicationArguments args) {
        if (!startupReconcile) {
            log.info("启动对账已关闭（aiwear.vector.startup-reconcile=false），跳过检索索引对账");
            return;
        }
        imageIndexService.reconcileAllOnStartup();
    }
}
