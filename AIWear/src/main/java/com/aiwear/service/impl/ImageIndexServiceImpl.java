package com.aiwear.service.impl;

import com.aiwear.dto.response.PythonAnalyzeImageResponse;
import com.aiwear.dto.response.PythonReconcileUserResponse;
import com.aiwear.entity.ImageFile;
import com.aiwear.mapper.ImageFileMapper;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.aiwear.service.ImageIndexService;
import com.aiwear.service.PythonImageService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

// 图片检索索引对账实现
//
// 一致性模型：MySQL 是唯一事实来源，Redis 是可随时重建的索引。
// 「重建」是纯搬运（把库里存的向量写回 Redis，毫秒级），不重新下载图片也不调大模型——
// 后者每张要 4 秒且消耗大模型额度，不可能放在请求链路上。
@Slf4j
@Service
public class ImageIndexServiceImpl implements ImageIndexService {

    // 启动时最多重算多少张「库里有图但没有向量」的图片，避免大模型额度被一次性打光
    @Value("${aiwear.vector.startup-recompute-limit:20}")
    private int startupRecomputeLimit;

    @Autowired
    private ImageFileMapper imageFileMapper;

    @Autowired
    private PythonImageService pythonImageService;

    @Override
    public void indexQuietly(ImageFile imageFile) {
        String vector = imageFile == null ? null : imageFile.getVector();
        if (imageFile == null || imageFile.getOssUrl() == null || vector == null || vector.isBlank()) {
            return; // 没有向量就没什么可索引的，交给对账处理
        }
        try {
            pythonImageService.indexImage(imageFile.getUserId(), imageFile.getOssUrl(),
                    imageFile.getDescription(), imageFile.getCategory(), vector);
        } catch (Exception e) {
            log.warn("同步检索索引失败（不影响上传结果，稍后由对账补上）：ossUrl={}，原因={}",
                    imageFile.getOssUrl(), e.getMessage());
        }
    }

    @Override
    public boolean reconcileUser(Long userId) {
        if (userId == null) {
            return false;
        }
        try {
            // 先用轻量查询拿图片地址（不带 7KB 向量）：对账大多数时候只需要地址，
            // 只有确实缺记录时才把向量读出来，避免每次检索/列表都白读几十 KB。
            List<ImageFile> rows = imageFileMapper.selectList(
                    new LambdaQueryWrapper<ImageFile>().eq(ImageFile::getUserId, userId));
            List<String> keepUrls = rows.stream()
                    .map(ImageFile::getOssUrl)
                    .filter(Objects::nonNull)
                    .toList();
            if (keepUrls.isEmpty()) {
                return true; // 没有图片就没什么可对账的，也避免误删
            }

            PythonReconcileUserResponse result = pythonImageService.reconcileUser(userId, keepUrls);
            if (result == null || result.getSuccess() == null || !result.getSuccess()) {
                log.warn("检索索引对账未成功：userId={}", userId);
                return false;
            }

            List<String> missing = result.getMissing() == null ? List.of() : result.getMissing();
            int healed = 0;
            int withoutVector = 0;

            if (!missing.isEmpty()) {
                Map<String, ImageFile> byUrl = new HashMap<>();
                for (ImageFile row : imageFileMapper.selectWithVectorByUserId(userId)) {
                    byUrl.putIfAbsent(row.getOssUrl(), row);
                }
                for (String url : missing) {
                    ImageFile row = byUrl.get(url);
                    if (row == null) {
                        continue;
                    }
                    if (row.getVector() == null || row.getVector().isBlank()) {
                        // 库里也没有向量（上传时分析失败的图），留给启动时的限额重算
                        withoutVector++;
                        continue;
                    }
                    try {
                        pythonImageService.indexImage(userId, url, row.getDescription(), row.getCategory(),
                                row.getVector());
                        healed++;
                    } catch (Exception e) {
                        log.warn("补写索引失败：userId={}，ossUrl={}，原因={}", userId, url, e.getMessage());
                    }
                }
            }

            int removed = result.getRemoved() == null ? 0 : result.getRemoved().size();
            if (healed > 0 || withoutVector > 0 || removed > 0) {
                log.info("检索索引对账完成：userId={}，补写={}，库内无向量={}，清理孤儿={}",
                        userId, healed, withoutVector, removed);
            }
            return true;
        } catch (Exception e) {
            // 对账失败不影响检索本身（Python 不可用时会由检索自己报错）
            log.warn("检索索引对账异常：userId={}，原因={}", userId, e.getMessage());
            return false;
        }
    }

    @Override
    public void reconcileAllOnStartup() {
        // 独立线程执行，不阻塞应用启动
        Thread worker = new Thread(() -> {
            try {
                recomputeMissingVectors();
                List<Long> userIds = imageFileMapper.selectAllUserIds();
                for (Long userId : userIds) {
                    reconcileUser(userId);
                }
                log.info("启动对账完成，共处理 {} 个用户", userIds.size());
            } catch (Exception e) {
                log.warn("启动对账异常：{}", e.getMessage());
            }
        }, "vector-index-startup-reconcile");
        worker.setDaemon(true);
        worker.start();
    }

    // 库里有图、但没有向量的行（上传时分析失败，或历史遗留）：限额重算一次。
    // 没有这一步它们会永远搜不到，只能人工介入。
    private void recomputeMissingVectors() {
        List<ImageFile> rows = imageFileMapper.selectRowsMissingVector(startupRecomputeLimit);
        if (rows.isEmpty()) {
            return;
        }
        log.info("发现 {} 张图片缺少向量，开始限额重算", rows.size());
        for (ImageFile row : rows) {
            try {
                PythonAnalyzeImageResponse analyzed =
                        pythonImageService.analyzeImage(row.getUserId(), row.getOssUrl());
                if (analyzed == null || analyzed.getSuccess() == null || !analyzed.getSuccess()
                        || analyzed.getVector() == null) {
                    saveVectorStatus(row.getId(), "FAILED");
                    log.warn("重算向量未成功：id={}，ossUrl={}", row.getId(), row.getOssUrl());
                    continue;
                }
                String vector = analyzed.getVector().toString();
                saveVector(row.getId(), analyzed.getDescription(), analyzed.getCategory(), vector, "READY");
                // 顺手同步进索引，省掉一次对账往返
                pythonImageService.indexImage(row.getUserId(), row.getOssUrl(),
                        analyzed.getDescription(), analyzed.getCategory(), vector);
            } catch (Exception e) {
                String message = e.getMessage() == null ? "" : e.getMessage();
                if (message.contains(PythonImageService.ERROR_PYTHON_TOO_OLD)) {
                    // 旧版 Python 没有 /api/analyze-image，重算这条路走不通，别刷屏
                    log.warn("Python 版本过旧，跳过向量重算");
                    return;
                }
                saveVectorStatus(row.getId(), "FAILED");
                log.warn("重算向量失败：id={}，ossUrl={}，原因={}", row.getId(), row.getOssUrl(), message);
            }
        }
    }

    private void saveVector(Long id, String description, String category, String vector, String status) {
        ImageFile update = new ImageFile();
        update.setId(id);
        update.setDescription(description == null ? "" : description);
        update.setCategory(category == null ? "" : category);
        update.setVector(vector);
        update.setVectorStatus(status);
        update.setVectorUpdatedAt(LocalDateTime.now());
        imageFileMapper.updateById(update);
    }

    private void saveVectorStatus(Long id, String status) {
        ImageFile update = new ImageFile();
        update.setId(id);
        update.setVectorStatus(status);
        update.setVectorUpdatedAt(LocalDateTime.now());
        imageFileMapper.updateById(update);
    }
}
