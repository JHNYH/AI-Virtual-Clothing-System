package com.aiwear.dto.response;

import lombok.Data;

import java.io.Serializable;

// Python /api/index-image 的返回体
@Data
public class PythonIndexImageResponse implements Serializable {
    private Boolean success;
    private String imageId;
    private String userId;
    private String error;
}
