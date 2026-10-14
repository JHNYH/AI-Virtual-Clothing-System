package com.aiwear.dto.request;

import lombok.Data;

import java.io.Serializable;

// 调用 Python /api/index-image 的请求体（把已知记录幂等地写入检索索引）
// 注意：vector 直接传 MySQL 里存的 JSON 文本，不在 Java 侧解析成 512 个 double 再拼回去
@Data
public class PythonIndexImageRequest implements Serializable {
    private Long userId;
    private String ossUrl;
    private String description;
    private String category;
    private String vector;
}
