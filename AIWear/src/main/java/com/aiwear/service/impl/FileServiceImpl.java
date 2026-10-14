package com.aiwear.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.aiwear.dto.request.EditImageRequest;
import com.aiwear.dto.request.MergeImageRequest;
import com.aiwear.dto.request.SearchImageRequest;
import com.aiwear.dto.response.EditImageResponse;
import com.aiwear.dto.response.MergeImageResponse;
import com.aiwear.dto.response.PythonAnalyzeImageResponse;
import com.aiwear.dto.response.SearchImageResponse;
import com.aiwear.dto.response.UploadImageResponse;
import com.aiwear.entity.ImageFile;
import com.aiwear.mapper.ImageFileMapper;
import com.aiwear.service.FileService;
import com.aiwear.service.ImageIndexService;
import com.aiwear.service.PythonImageService;
import com.aiwear.service.RecordService;
import com.aiwear.util.JwtUtil;
import com.aiwear.util.OssService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.web.multipart.MultipartFile;

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.util.*;

// 文件上传实现类
@Slf4j
@Service
public class FileServiceImpl implements FileService {

    // 向量状态取值：只有 READY 的图片才可能出现在检索结果里
    private static final String VECTOR_STATUS_READY = "READY";
    private static final String VECTOR_STATUS_PENDING = "PENDING";

    @Autowired
    private ImageFileMapper imageFileMapper;

    @Autowired
    private OssService ossService;

    @Autowired
    private PythonImageService pythonImageService;

    @Value("${file.upload.dir:uploads}")
    private String uploadBaseDir;

    @Autowired
    private JwtUtil jwtUtil;

    @Autowired
    private RecordService recordService;

    @Autowired
    private ImageIndexService imageIndexService;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public UploadImageResponse uploadImage(MultipartFile file, String authorization) {
        if (file == null) {
            throw new RuntimeException("缺少上传文件");
        }
        if (file.isEmpty()) {
            throw new RuntimeException("上传文件为空");
        }
        if (file.getContentType() == null || !file.getContentType().startsWith("image/")) {
            throw new RuntimeException("仅支持图片上传");
        }
        // 这里是 OSS 侧的大小保护（aliyun.oss.max-size）。
        // 当前 uploadImage 走不到这个分支：max-file-size 与 aliyun.oss.max-size 同为 50MB，
        // 超限文件在 multipart 解析阶段就被容器拒了（由 GlobalExceptionHandler 返回同样文案）。
        // 但该限制一旦放宽，本方法必须继续挡住超限文件，故保留为兜底。
        long fileSize = file.getSize();
        if (fileSize > ossService.getMaxSize()) {
            throw new RuntimeException("图片大小超过限制");
        }

        String token = jwtUtil.parseToken(authorization);

        Long userId = jwtUtil.getUserId(token);

        String originalFileName = file.getOriginalFilename();
        if (originalFileName == null || originalFileName.isBlank()) {
            originalFileName = "image";
        }

        String extension = getFileExtension(originalFileName, file.getContentType());
        String uuid = UUID.randomUUID().toString().replace("-", "");

        // 本地“系统”存储路径：uploads/images/{uuid}.ext
        Path localDir = Paths.get(uploadBaseDir, "images");
        try {
            Files.createDirectories(localDir);
        } catch (Exception e) {
            throw new RuntimeException("创建本地存储目录失败");
        }

        String finalLocalFileName = uuid + extension;
        Path localFilePath = localDir.resolve(finalLocalFileName);

        boolean uploaded = false;
        try {
            // 1) 上传到系统（本地存储）
            file.transferTo(localFilePath);
            if (!pythonImageService.validateImage(localFilePath)) {
                throw new RuntimeException("图片审核不通过！");
            }
            // 2) 同步到OSS
            String objectKey = "images/" + finalLocalFileName;
            File localFile = localFilePath.toFile();
            String url = ossService.upload(objectKey, localFile, file.getContentType());

            // 3) 计算描述/类别/向量。失败不阻断上传：OSS 已经传上去了且没有删除能力，
            //    回滚只会白留一个孤儿对象，所以降级为 PENDING 落库，由启动时对账限额重算。
            PythonAnalyzeImageResponse analyzed = null;
            try {
                analyzed = pythonImageService.analyzeImage(userId, url);
            } catch (Exception e) {
                String message = e.getMessage() == null ? "" : e.getMessage();
                if (message.contains(PythonImageService.ERROR_PYTHON_TOO_OLD)) {
                    log.warn("Python 版本过旧，跳过向量计算，该图片暂时不可检索：ossUrl={}", url);
                } else {
                    log.error("向量计算失败，图片以 PENDING 落库（稍后由对账重算）：ossUrl={}，原因={}", url, message);
                }
            }
            boolean vectorReady = analyzed != null && Boolean.TRUE.equals(analyzed.getSuccess())
                    && analyzed.getVector() != null;

            // 4) 落库：图片与向量在同一个事务里写入，从此不会再出现「有图无向量」
            ImageFile record = new ImageFile();
            record.setUserId(userId);
            record.setFileName(originalFileName);
            record.setFileSize(fileSize);
            record.setOssUrl(url);
            record.setDescription(vectorReady ? analyzed.getDescription() : "");
            record.setCategory(vectorReady ? analyzed.getCategory() : "");
            record.setVector(vectorReady ? analyzed.getVector().toString() : null);
            record.setVectorStatus(vectorReady ? VECTOR_STATUS_READY : VECTOR_STATUS_PENDING);
            record.setVectorUpdatedAt(vectorReady ? LocalDateTime.now() : null);
            imageFileMapper.insert(record);

            // 5) 事务提交之后再同步检索索引：万一事务回滚，Redis 里不会多出一条记录。
            //    索引同步失败不影响上传成败，下一轮对账会补上。
            if (vectorReady) {
                TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        imageIndexService.indexQuietly(record);
                    }
                });
            }

            UploadImageResponse response = new UploadImageResponse();
            response.setUrl(url);
            response.setFileName(originalFileName);
            response.setFileSize(fileSize);
            uploaded = true;
            return response;
        } catch (Exception e) {
            log.error("图片上传失败，原因：{}", e.getMessage());
            // 保留原始 cause，并且不能让 message 为 null——前端是拿 message 直接展示的
            String message = (e.getMessage() == null || e.getMessage().isBlank())
                    ? "图片上传失败" : e.getMessage();
            throw new RuntimeException(message, e);
        } finally {
            // OSS成功后可删除；失败时尽量保留方便排查
            try {
                if (uploaded) {
                    Files.deleteIfExists(localFilePath);
                }
            } catch (Exception ignore) {
            }
        }
    }

    @Override
    public List<ImageFile> myImages(String authorization) {
        String token = jwtUtil.parseToken(authorization);
        Long userId = jwtUtil.getUserId(token);
        List<ImageFile> imageFiles = listMyImages(userId);
        // 顺带对账一次：索引里缺的当场用库里存的向量补齐（毫秒级，不重新调大模型）。
        // 对账没跑通（Python 不可用等）时 indexed 保持 null，前端不显示角标，避免误报。
        if (imageIndexService.reconcileUser(userId)) {
            for (ImageFile imageFile : imageFiles) {
                imageFile.setIndexed(VECTOR_STATUS_READY.equals(imageFile.getVectorStatus()));
            }
        }
        return imageFiles;
    }

    // 只查本用户的图片列表（不带 7KB 的向量字段）。
    // 抽出来是为了让 edit/merge/search 复用，避免它们也被动触发对账。
    private List<ImageFile> listMyImages(Long userId) {
        LambdaQueryWrapper<ImageFile> queryWrapper = new LambdaQueryWrapper<>();
        queryWrapper.eq(ImageFile::getUserId, userId).orderByDesc(ImageFile::getId);
        return imageFileMapper.selectList(queryWrapper);
    }

    @Override
    public List<SearchImageResponse> search(String authorization, SearchImageRequest searchImageRequest) {
        // 1. 先去获取用户id
        String token = jwtUtil.parseToken(authorization);
        Long userId = jwtUtil.getUserId(token);
        List<ImageFile> imageFiles = listMyImages(userId);
        Map<String, String> map = new HashMap<>();
        for (ImageFile imageFile : imageFiles) {
            map.put(imageFile.getOssUrl(), imageFile.getFileName());
        }
        // 2. 检索前对账一次：索引如果丢过，这里用库里存的向量毫秒级补回来。
        //    对账失败不阻断检索——检索服务自己不可用时会明确报错，不再静默返回空列表。
        imageIndexService.reconcileUser(userId);
        // 3. 调用python服务
        List<SearchImageResponse> searchImageResponseList = pythonImageService.search(userId, searchImageRequest);
        for (SearchImageResponse searchImageResponse : searchImageResponseList) {
            searchImageResponse.setFileName(map.get(searchImageResponse.getFilePath()));
        }
        // 3. 拿到数据，进行封装
        return searchImageResponseList;
    }

    @Override
    public EditImageResponse edit(String authorization, EditImageRequest editImageRequest) {
        // 1. 鉴权 -> 用户只能编辑自己上传的图片
        List<ImageFile> imageFiles = listMyImages(jwtUtil.getUserId(jwtUtil.parseToken(authorization)));
        // 2. 判断当前图片地址是否包含在imageFiles的ossUrl字段集合中
        List<String> urls = imageFiles.stream().map(ImageFile::getOssUrl).toList();
        if (!urls.contains(editImageRequest.getImage())) {
            throw new RuntimeException("只能编辑自己上传的图片");
        }
        // 3. 调用python服务，封装最后的返回结果
        EditImageResponse editImageResponse = pythonImageService.edit(editImageRequest);

        // 新增调用记录
        Long userId = jwtUtil.getUserId(jwtUtil.parseToken(authorization));
        recordService.editSave(userId, editImageRequest, editImageResponse);
        return editImageResponse;
    }

    @Override
    public MergeImageResponse merge(String authorization, MergeImageRequest mergeImageRequest) {
        // 1. 鉴权 -> 用户只能合并自己上传的图片
        List<ImageFile> imageFiles = listMyImages(jwtUtil.getUserId(jwtUtil.parseToken(authorization)));
        // 2. 判断上传的图片是否包含在imageFiles的ossUrl字段集合中
        List<String> urls = imageFiles.stream().map(ImageFile::getOssUrl).toList();
        if (!urls.contains(mergeImageRequest.getImage1()) || !urls.contains(mergeImageRequest.getImage2())) {
            throw new RuntimeException("只能合并自己上传的图片");
        }
        // 3. 调用python服务
        MergeImageResponse mergeImageResponse = pythonImageService.merge(mergeImageRequest);
        // 新增调用记录
        Long userId = jwtUtil.getUserId(jwtUtil.parseToken(authorization));
        recordService.mergeSave(userId, mergeImageRequest, mergeImageResponse);
        return mergeImageResponse;
    }

    private String getFileExtension(String originalFileName, String contentType) {
        if (originalFileName != null && originalFileName.contains(".")) {
            String ext = originalFileName.substring(originalFileName.lastIndexOf(".")).toLowerCase(Locale.ROOT);
            if (ext.length() <= 10) {
                return ext;
            }
        }
        if (contentType == null) {
            return ".png";
        }
        if (contentType.equalsIgnoreCase("image/png")) {
            return ".png";
        }
        if (contentType.equalsIgnoreCase("image/jpeg") || contentType.equalsIgnoreCase("image/jpg")) {
            return ".jpg";
        }
        if (contentType.equalsIgnoreCase("image/gif")) {
            return ".gif";
        }
        if (contentType.equalsIgnoreCase("image/webp")) {
            return ".webp";
        }
        return ".png";
    }
}

