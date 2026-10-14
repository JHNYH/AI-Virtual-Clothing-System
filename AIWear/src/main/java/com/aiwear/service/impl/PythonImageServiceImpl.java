package com.aiwear.service.impl;

import com.aiwear.dto.request.EditImageRequest;
import com.aiwear.dto.request.MergeImageRequest;
import com.aiwear.dto.request.PythonAnalyzeImageRequest;
import com.aiwear.dto.request.PythonIndexImageRequest;
import com.aiwear.dto.request.PythonReconcileUserRequest;
import com.aiwear.dto.request.PythonUploadImageRequest;
import com.aiwear.dto.request.SearchImageRequest;
import com.aiwear.dto.response.EditImageResponse;
import com.aiwear.dto.response.MergeImageResponse;
import com.aiwear.dto.response.PythonAnalyzeImageResponse;
import com.aiwear.dto.response.PythonIndexImageResponse;
import com.aiwear.dto.response.PythonReconcileUserResponse;
import com.aiwear.dto.response.PythonUploadImageResponse;
import com.aiwear.dto.response.SearchImageResponse;
import com.aiwear.service.PythonImageService;
import com.aiwear.util.OssService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.URL;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Slf4j
@Service
public class PythonImageServiceImpl implements PythonImageService {

    @Value("${python.service.base-url:http://127.0.0.1:5000}")
    private String pythonBaseUrl;

    // 多数 Python 调用要连带等大模型，读超时用配置项。
    // 原先方法内 new RestTemplate() 没设任何超时，Python 一卡住就会无限等待，把 Tomcat 线程一起拖死。
    @Value("${python.service.read-timeout-ms:120000}")
    private int readTimeoutMs;

    // 这里使用 Java 内置 HttpClient，避免额外依赖
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;

    @Autowired
    private OssService ossService;

    @Autowired
    public PythonImageServiceImpl(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(30))
                .build();
    }

    // 带超时的 RestTemplate（multipart 场景用）
    private RestTemplate rest() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(5000);
        factory.setReadTimeout(readTimeoutMs);
        return new RestTemplate(factory);
    }

    // 统一的 JSON 调用：按端点给不同超时，404/405 视为「Python 版本过旧」交给上层降级
    private <T> T callJson(String path, Object requestBody, Class<T> responseType, long timeoutSeconds) {
        String requestJson;
        try {
            requestJson = objectMapper.writeValueAsString(requestBody);
        } catch (Exception e) {
            throw new RuntimeException("构造 Python 请求体失败：" + path);
        }

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(pythonBaseUrl + path))
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(timeoutSeconds))
                .POST(HttpRequest.BodyPublishers.ofString(requestJson, StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> response;
        try {
            response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        } catch (Exception e) {
            log.error("调用 Python {} 失败：{}", path, e.getMessage());
            throw new RuntimeException("Python 服务不可用：" + path);
        }

        if (response.statusCode() == 404 || response.statusCode() == 405) {
            // 旧版 Python 没有这些接口，用可识别的标记让上层降级，而不是当成故障
            throw new RuntimeException(ERROR_PYTHON_TOO_OLD + "：" + path);
        }
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            log.error("Python {} 返回非 2xx：status={}, body={}", path, response.statusCode(), response.body());
            throw new RuntimeException("Python 服务返回错误：" + path);
        }

        try {
            return objectMapper.readValue(response.body(), responseType);
        } catch (Exception e) {
            log.error("解析 Python {} 响应失败：{}", path, e.getMessage());
            throw new RuntimeException("解析 Python 响应失败：" + path);
        }
    }

    @Override
    public PythonAnalyzeImageResponse analyzeImage(Long userId, String ossUrl) {
        PythonAnalyzeImageRequest requestBody = new PythonAnalyzeImageRequest();
        requestBody.setUserId(userId);
        requestBody.setOssUrl(ossUrl);
        // 一次调用里要做「大模型生成描述 + 类别判定 + CLIP 编码」，给足超时
        return callJson("/api/analyze-image", requestBody, PythonAnalyzeImageResponse.class, 90);
    }

    @Override
    public void indexImage(Long userId, String ossUrl, String description, String category, String vector) {
        PythonIndexImageRequest requestBody = new PythonIndexImageRequest();
        requestBody.setUserId(userId);
        requestBody.setOssUrl(ossUrl);
        requestBody.setDescription(description);
        requestBody.setCategory(category);
        requestBody.setVector(vector);
        PythonIndexImageResponse response =
                callJson("/api/index-image", requestBody, PythonIndexImageResponse.class, 10);
        if (response == null || response.getSuccess() == null || !response.getSuccess()) {
            throw new RuntimeException("写入检索索引失败");
        }
    }

    @Override
    public PythonReconcileUserResponse reconcileUser(Long userId, List<String> keepOssUrls) {
        PythonReconcileUserRequest requestBody = new PythonReconcileUserRequest();
        requestBody.setUserId(userId);
        requestBody.setKeepOssUrls(keepOssUrls);
        return callJson("/api/reconcile-user", requestBody, PythonReconcileUserResponse.class, 10);
    }

    @Override
    public void uploadImage(Long userId, String ossUrl) {
        if (userId == null) {
            throw new RuntimeException("缺少 userId");
        }
        if (ossUrl == null || ossUrl.isBlank()) {
            throw new RuntimeException("缺少 ossUrl");
        }

        PythonUploadImageRequest requestBody = new PythonUploadImageRequest();
        requestBody.setUserId(userId);
        requestBody.setOssUrl(ossUrl);

        String requestJson;
        try {
            requestJson = objectMapper.writeValueAsString(requestBody);
        } catch (Exception e) {
            throw new RuntimeException("构造 Python 请求体失败");
        }

        String url = pythonBaseUrl + "/api/upload-image";
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(30))
                .POST(HttpRequest.BodyPublishers.ofString(requestJson, StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> response;
        try {
            response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        } catch (Exception e) {
            log.error("调用 Python /api/upload-image 失败：{}", e.getMessage());
            throw new RuntimeException("调用 Python 服务失败");
        }

        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            log.error("Python 服务返回非 2xx：status={}, body={}", response.statusCode(), response.body());
            throw new RuntimeException("Python 服务返回错误");
        }

        try {
            PythonUploadImageResponse pythonResponse =
                    objectMapper.readValue(response.body(), PythonUploadImageResponse.class);
            if (pythonResponse.getSuccess() == null || !pythonResponse.getSuccess()) {
                throw new RuntimeException("Python 上传失败");
            }
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            log.error("解析 Python 响应失败：{}", e.getMessage());
            throw new RuntimeException("解析 Python 响应失败");
        }
    }

    @Override
    public boolean validateImage(Path filePath) {
        String url = pythonBaseUrl + "/api/validate-image";
        HttpHeaders httpHeaders = new HttpHeaders();
        httpHeaders.setContentType(MediaType.MULTIPART_FORM_DATA);

        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("file", new FileSystemResource(filePath));
        HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, httpHeaders);
        try {
            ResponseEntity<String> response = rest().postForEntity(url, requestEntity, String.class);
            return objectMapper.readTree(response.getBody()).path("allow").asBoolean(false);
        } catch (Exception e) {
            // 这里必须抛出，不能静默 return false：
            // 「调用失败」和「审核不通过」是两件事，静默吞掉会把服务故障伪装成内容问题，
            // 用户只会看到"图片审核不通过"，完全无从排查。
            log.error("调用 Python 审核接口失败：{}", e.getMessage());
            throw new RuntimeException("图片审核服务不可用，请稍后重试");
        }
    }

    @Override
    public List<SearchImageResponse> search(Long userId, SearchImageRequest searchImageRequest) {
        String url = pythonBaseUrl + "/api/search-image";
        String query = searchImageRequest.getQuery();
        MultipartFile file = searchImageRequest.getFile();

        HttpHeaders httpHeaders = new HttpHeaders();
        httpHeaders.setContentType(MediaType.MULTIPART_FORM_DATA);
        try {
            MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
            body.add("userId", userId);
            if (query != null && !query.isBlank()) {
                body.add("query", query);
            }

            if (file != null) {
                byte[] fileBytes = file.getBytes();
                String filename = file.getOriginalFilename();
                ByteArrayResource fileResource = new ByteArrayResource(fileBytes) {
                    @Override
                    public String getFilename() {
                        return filename;
                    }
                };
                body.add("file", fileResource);
            }

            HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, httpHeaders);
            ResponseEntity<String> response = rest().postForEntity(url, requestEntity, String.class);
            JsonNode result = objectMapper.readTree(response.getBody())
                    .path("data");
            List<SearchImageResponse> searchImageResponseList = new ArrayList<>();
            for (JsonNode node : result) {
                SearchImageResponse searchImageResponse = new SearchImageResponse();
                searchImageResponse.setFilePath(node.path("filePath").asText(""));
                searchImageResponseList.add(searchImageResponse);
            }
            return searchImageResponseList;

        } catch (Exception e) {
            // 不能静默返回空列表：那会让「检索服务故障」和「确实没搜到」在前端长得一模一样，
            // 用户只看到"暂无相关数据"，排查时完全找不到方向。
            log.error("调用 python 服务的搜索图片接口失败：{}", e.getMessage());
            throw new RuntimeException("检索服务不可用，请稍后重试");
        }
    }

    @Override
    public EditImageResponse edit(EditImageRequest editImageRequest) {
        // 1. 考虑转换  oss url -> file资源
        String sourceImageUrl = editImageRequest.getImage();
        String instruction = editImageRequest.getInstruction();
        Path sourceTemp = null;
        Path editTemp = null;

        sourceTemp = downloadToTempFile(sourceImageUrl);
        // 2. 构造请求参数去访问python服务的编辑图片接口
        String url = pythonBaseUrl + "/api/skill/image";
        HttpHeaders httpHeaders = new HttpHeaders();
        httpHeaders.setContentType(MediaType.MULTIPART_FORM_DATA);

        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("file", new FileSystemResource(sourceTemp.toFile()));
        body.add("instruction", instruction);

        HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, httpHeaders);
        RestTemplate restTemplate = new RestTemplate();

        // 3. 拿到python服务返回的响应之后需要处理数据
        ResponseEntity<String> response = restTemplate.postForEntity(url, requestEntity, String.class);
        try {
            JsonNode result = objectMapper.readTree(response.getBody());
            String pythonUrl = result.path("url").asText("");
            // 4. 图片地址需要二次保存
            editTemp = downloadToTempFile(pythonUrl);
            String contentType = Files.probeContentType(editTemp);
            String extension = ".png";
            String objectKey = "image/edited/" + UUID.randomUUID().toString().replace("-", "") + extension;
            String saveUrl = ossService.upload(objectKey, editTemp.toFile(), contentType);
            // 5. 封装一个返回对象
            EditImageResponse editImageResponse = new EditImageResponse();
            editImageResponse.setUrl(pythonUrl);
            editImageResponse.setSaveUrl(saveUrl);
            return editImageResponse;
        } catch (JsonProcessingException e) {
            throw new RuntimeException(e);
        } catch (IOException e) {
            throw new RuntimeException(e);
        } finally {
            // 6. 处理无论成功与否，都应该删掉临时
            try {
                Files.deleteIfExists(sourceTemp);
                Files.deleteIfExists(editTemp);
            } catch (IOException e) {
                log.error("删除临时文件失败");
                throw new RuntimeException(e);
            }
        }
    }

    @Override
    public MergeImageResponse merge(MergeImageRequest mergeImageRequest) {
        // 1. 文件转换   oss url   -> file 资源
        String source1ImageUrl = mergeImageRequest.getImage1();
        String source2ImageUrl = mergeImageRequest.getImage2();
        String instruction = mergeImageRequest.getInstruction();
        Path source1Temp = downloadToTempFile(source1ImageUrl);
        Path source2Temp = downloadToTempFile(source2ImageUrl);
        Path mergeTemp = null;
        // 2. 构造请求参数去访问python服务的合并图片接口
        String url = pythonBaseUrl + "/api/skill-image";
        HttpHeaders httpHeaders = new HttpHeaders();
        httpHeaders.setContentType(MediaType.MULTIPART_FORM_DATA);

        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("file1", new FileSystemResource(source1Temp.toFile()));
        body.add("file2", new FileSystemResource(source2Temp.toFile()));
        body.add("instruction", instruction);

        HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, httpHeaders);
        RestTemplate restTemplate = new RestTemplate();

        // 3. 拿到python服务返回的响应
        ResponseEntity<String> response = restTemplate.postForEntity(url, requestEntity, String.class);
        try {
            JsonNode result = objectMapper.readTree(response.getBody());
            String pythonUrl = result.path("url").asText("");
            // 4. 拿到的图片进行二次保存到oss
            mergeTemp = downloadToTempFile(pythonUrl);
            String contentType = Files.probeContentType(mergeTemp);
            String extension = ".png";
            String objectKey = "image/merged/" + UUID.randomUUID().toString().replace("-", "") + extension;
            String saveUrl = ossService.upload(objectKey, mergeTemp.toFile(), contentType);
            // 5. 封装一个返回的对象
            MergeImageResponse mergeImageResponse = new MergeImageResponse();
            mergeImageResponse.setUrl(pythonUrl);
            mergeImageResponse.setSaveUrl(saveUrl);
            return mergeImageResponse;

        } catch (JsonProcessingException e) {
            throw new RuntimeException(e);
        } catch (IOException e) {
            throw new RuntimeException(e);
        } finally {
            // 6. 删掉临时文件
            try {
                Files.deleteIfExists(source1Temp);
                Files.deleteIfExists(source2Temp);
                Files.deleteIfExists(mergeTemp);
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        }
    }

    // 下载远程地址的url文件
    private Path downloadToTempFile(String fileUrl) {
        try {
            URL url = URI.create(fileUrl).toURL();
            Path tempFile = Files.createTempFile("image-edit-", ".tmp");
            InputStream inputStream = url.openStream();
            Files.copy(inputStream, tempFile, StandardCopyOption.REPLACE_EXISTING);
            return tempFile;
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }
}

