package com.aiwear.dto.request;

import lombok.Data;

import java.io.Serializable;
import java.util.List;

// 调用 Python /api/reconcile-user 的请求体
// keepOssUrls = 该用户在 MySQL 里的全部图片地址，是判断索引是否一致的唯一事实来源
@Data
public class PythonReconcileUserRequest implements Serializable {
    private Long userId;
    private List<String> keepOssUrls;
}
