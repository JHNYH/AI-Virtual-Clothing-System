package com.aiwear.dto.response;

import lombok.Data;

import java.io.Serializable;
import java.util.List;

// Python /api/reconcile-user 的返回体
// missing：MySQL 里有、但索引里没有的图片地址（需要调用方用库里的向量补写）
// removed：索引里有、但 MySQL 里已经没有的图片地址（本次已清理）
// skipped：安全阀生效（调用方没给出图片列表，此时不做任何删除）
@Data
public class PythonReconcileUserResponse implements Serializable {
    private Boolean success;
    private String userId;
    private List<String> missing;
    private List<String> removed;
    private Integer indexed;
    private Boolean skipped;
    private String error;
}
