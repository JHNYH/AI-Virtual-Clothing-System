package com.aiwear.service;

import com.aiwear.dto.request.EditImageRequest;
import com.aiwear.dto.request.MergeImageRequest;
import com.aiwear.dto.request.SearchImageRequest;
import com.aiwear.dto.response.EditImageResponse;
import com.aiwear.dto.response.MergeImageResponse;
import com.aiwear.dto.response.PythonAnalyzeImageResponse;
import com.aiwear.dto.response.PythonReconcileUserResponse;
import com.aiwear.dto.response.SearchImageResponse;

import java.nio.file.Path;
import java.util.List;

// Python 图片向量化服务（后续可能会复用在搜索等功能）
public interface PythonImageService {

    // 「新 Java + 旧 Python」时接口不存在会拿到 404/405，用这个标记让上层识别并降级
    String ERROR_PYTHON_TOO_OLD = "PYTHON_TOO_OLD";

    // 上传图片后的 OSS URL 与 userId 发给 Python /api/upload-image
    void uploadImage(Long userId, String ossUrl);

    // 审核图片 （上传之前先添加审核）
    boolean validateImage(Path filePath);

    // 分析图片：返回描述/类别/CLIP 向量，不落任何存储。
    // 上传链路改成「先落库、后建索引」后，用它拿计算结果自己持久化。
    PythonAnalyzeImageResponse analyzeImage(Long userId, String ossUrl);

    // 把一条已知记录幂等地写入检索索引（对账时搬运 MySQL 里的向量，不重新计算）
    void indexImage(Long userId, String ossUrl, String description, String category, String vector);

    // 对账：让该用户的检索索引与 MySQL 里的图片列表一致，返回缺失/清理情况
    PythonReconcileUserResponse reconcileUser(Long userId, List<String> keepOssUrls);

    // 搜索图片
    List<SearchImageResponse> search(Long userId, SearchImageRequest searchImageRequest);

    // 编辑图片
    EditImageResponse edit(EditImageRequest editImageRequest);

    // 合并图片
    MergeImageResponse merge(MergeImageRequest mergeImageRequest);
}

