package com.aiwear.controller;

import com.aiwear.common.Result;
import com.aiwear.entity.Record;
import com.aiwear.log.ApiLog;
import com.aiwear.service.RecordService;
import com.aiwear.util.JwtUtil;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.List;

// 历史调用记录的控制器
@Slf4j
@RestController
@RequestMapping("/api/record")
public class RecordController {

    @Autowired
    private JwtUtil jwtUtil;

    @Autowired
    private RecordService recordService;

    // 查看调用记录
    @ApiLog
    @GetMapping("/my")
    public Result<List<Record>> my(
            @RequestHeader(value = "Authorization") String authorization,
            @RequestParam(value = "action", required = false) String action
    ) {
        String token = jwtUtil.parseToken(authorization);
        Long userId = jwtUtil.getUserId(token);
        return Result.success("查询成功", recordService.my(userId, action));
    }
}
