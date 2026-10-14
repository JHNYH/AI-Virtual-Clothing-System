package com.aiwear.dto.request;

import lombok.Data;

import java.io.Serializable;

// 调用 Python /api/analyze-image 的请求体（只分析、不入库）
@Data
public class PythonAnalyzeImageRequest implements Serializable {
    private Long userId;
    private String ossUrl;
}
