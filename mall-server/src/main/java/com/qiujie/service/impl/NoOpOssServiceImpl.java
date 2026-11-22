package com.qiujie.service.impl;

import cn.hutool.core.io.FileUtil;
import cn.hutool.core.util.IdUtil;
import cn.hutool.core.util.StrUtil;
import com.qiujie.service.OssService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.Set;

@Slf4j
@Service
@ConditionalOnExpression("'${aliyun.oss.access-key-id:}'.isEmpty() || '${aliyun.oss.endpoint:}'.isEmpty()")
public class NoOpOssServiceImpl implements OssService {

    private static final Set<String> ALLOWED_EXTS = Set.of(".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp");

    @Value("${mall.oss.local-dir:img}")
    private String localDir;

    private Path resolvePath(String key) {
        Path base = Paths.get(localDir).toAbsolutePath();
        Path p = base.resolve(key).normalize();
        if (!p.startsWith(base.normalize())) {
            throw new IllegalArgumentException("非法路径: " + key);
        }
        return p;
    }

    private String normalizeKey(String key) {
        if (StrUtil.isBlank(key)) return key;
        while (key.startsWith("/")) key = key.substring(1);
        return key;
    }

    @Override
    public String upload(MultipartFile file, String dir) throws IOException {
        String originalName = file.getOriginalFilename() == null ? "file" : file.getOriginalFilename();
        String ext = "";
        int dot = originalName.lastIndexOf('.');
        if (dot > 0) ext = originalName.substring(dot).toLowerCase();
        if (!ext.isEmpty() && !ALLOWED_EXTS.contains(ext) && !ALLOWED_EXTS.contains(ext + ".")) {
            log.warn("文件类型 {} 不在白名单，但本地降级模式允许", ext);
        }
        String key = (StrUtil.isNotBlank(dir) ? dir + "/" : "") + IdUtil.simpleUUID() + ext;
        return upload(file.getInputStream(), key);
    }

    @Override
    public String upload(InputStream inputStream, String fileName) {
        try {
            String key = normalizeKey(fileName);
            Path p = resolvePath(key);
            Files.createDirectories(p.getParent());
            Files.copy(inputStream, p, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
            log.info("[本地OSS] 上传成功: {}", p);
            return key;
        } catch (IOException e) {
            throw new RuntimeException("本地OSS上传失败: " + e.getMessage(), e);
        }
    }

    @Override
    public String getUrl(String fileName, long expireMs) {
        return "/oss/local/" + normalizeKey(fileName);
    }

    @Override
    public String getUrl(String fileName) {
        return getUrl(fileName, 0);
    }

    @Override
    public void delete(String fileName) {
        try {
            String key = normalizeKey(fileName);
            Path p = resolvePath(key);
            Files.deleteIfExists(p);
            log.info("[本地OSS] 删除: {}", p);
        } catch (IOException e) {
            log.warn("[本地OSS] 删除失败 {}: {}", fileName, e.getMessage());
        }
    }

    @Override
    public void deleteBatch(List<String> fileNames) {
        for (String f : fileNames) delete(f);
    }

    @Override
    public String getETag(String fileName) {
        try {
            Path p = resolvePath(normalizeKey(fileName));
            if (Files.exists(p)) {
                return String.valueOf(Files.size(p));
            }
        } catch (Exception ignored) {}
        return null;
    }

    @Override
    public byte[] download(String fileName) throws IOException {
        String key = normalizeKey(fileName);
        Path p = resolvePath(key);
        if (!Files.exists(p)) return new byte[0];
        return Files.readAllBytes(p);
    }
}