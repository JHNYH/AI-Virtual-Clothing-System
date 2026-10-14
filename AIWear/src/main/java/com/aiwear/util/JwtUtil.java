package com.aiwear.util;

import com.aiwear.entity.User;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.SignatureAlgorithm;
import io.jsonwebtoken.security.Keys;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

// jwt工具类
@Component
@Slf4j
public class JwtUtil {

    @Autowired
    private StringRedisTemplate redisTemplate;

    @Value(("${jwt.secret}"))
    private String secret;

    @Value(("${jwt.expiration}"))
    private Long expiration;

    // 缓存前缀key
    private static final String USER_TOKEN_KEY_PREFIX = "jwt:user:";

    public String generateToken(User user) {

        String userKey = USER_TOKEN_KEY_PREFIX + user.getId();
        if (redisTemplate.hasKey(userKey)) {
            return redisTemplate.opsForValue().get(userKey);
        }

        Map<String, Object> claims = new HashMap<>();
        claims.put("userId", user.getId());
        claims.put("username", user.getUsername());

        Date now = new Date();
        // jwt.expiration 单位为小时，与下面 Redis 的存活时间保持一致（原来这里多乘了 2）
        Date expireDate = new Date(now.getTime() + expiration * 1000 * 60 * 60);

        SecretKey key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));

        // 生成的令牌
        String token = Jwts.builder()
                .setClaims(claims)
                .setIssuedAt(now)
                .setExpiration(expireDate)
                .signWith(key, SignatureAlgorithm.HS256)
                .compact();
        redisTemplate.opsForValue()
                .set(
                        userKey,
                        token,
                        expiration,
                        TimeUnit.HOURS
                );

        return token;
    }

    // 先来获取token
    public String parseToken(String authorization) {
        if (authorization == null || authorization.isBlank()) {
            throw new RuntimeException("缺少请求头令牌！");
        }
        return authorization.substring(7);
    }

    // 从token中解析userId
    private Claims getClaims(String token) {
        SecretKey key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
        return Jwts.parserBuilder()
                .setSigningKey(key)
                .build()
                .parseClaimsJws(token)
                .getBody();
    }

    // 根据token获取userId
    public Long getUserId(String token) {
        Claims claims = getClaims(token);
        Long userId = Long.valueOf(claims.get("userId").toString());
        return userId;
    }

    // 删除令牌
    public boolean removeToken(String token) {
        if (token == null || token.isBlank()) {
            return true;
        }
        Claims claims = getClaims(token);
        Long userId = Long.valueOf(claims.get("userId").toString());
        String tokenKey = USER_TOKEN_KEY_PREFIX + userId;
        if (redisTemplate.hasKey(tokenKey)) {
            return redisTemplate.delete(tokenKey);
        }
        return false;
    }

}
