package com.aiwear.dto.response;

import com.fasterxml.jackson.databind.JsonNode;
import lombok.Data;

import java.io.Serializable;

// Python /api/analyze-image 的返回体
// vector 用 JsonNode 接住数组原文，落库时 toString() 即为 MySQL 里该存的 JSON 文本
@Data
public class PythonAnalyzeImageResponse implements Serializable {
    private Boolean success;
    private String imageId;
    private String userId;
    private String ossUrl;
    private String description;
    private String category;
    private JsonNode vector;
    private String error;
}
