# Spring Security OAuth2 资源服务器JWT验证技术文档

## 1. 概述

### 1.1 背景与目的
本文档详细阐述如何在Spring Security框架中配置OAuth2资源服务器，实现对JWT（JSON Web Token）格式访问令牌的验证。通过本方案，资源服务器能够独立验证客户端请求的合法性，无需频繁与授权服务器交互，实现无状态的身份验证与授权。

### 1.2 核心概念
- **OAuth2资源服务器**：托管受保护资源的服务器，能够验证访问令牌并响应受保护的资源请求
- **JWT**：一种开放标准（RFC 7519），用于在各方之间安全传输信息作为JSON对象
- **公钥/私钥机制**：授权服务器使用私钥签名JWT，资源服务器使用公钥验证签名

## 2. 工作原理

### 2.1 JWT验证流程
```
客户端请求 → 携带Bearer Token → 资源服务器验证JWT签名 → 提取声明信息 → 建立安全上下文 → 授权访问资源
```

### 2.2 核心验证步骤
1. **Token解析**：从Authorization头部提取JWT
2. **签名验证**：使用授权服务器的公钥验证JWT签名
3. **声明验证**：检查令牌有效期、受众(aud)、颁发者(iss)等声明
4. **权限提取**：从JWT的scope或authorities声明中提取权限信息

## 3. 实现方案

### 3.1 依赖配置

```xml
<!-- Maven依赖 -->
<dependencies>
    <!-- Spring Security OAuth2资源服务器 -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
    
    <!-- JWT支持 -->
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-oauth2-jose</artifactId>
    </dependency>
</dependencies>
```

### 3.2 核心配置类

```java
@Configuration
@EnableWebSecurity
public class ResourceServerConfig {
    
    @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
    private String jwkSetUri;
    
    @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
    private String issuerUri;
    
    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/user/**").hasAnyRole("USER", "ADMIN")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt
                    .jwkSetUri(jwkSetUri)
                    .jwtAuthenticationConverter(jwtAuthenticationConverter())
                )
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );
        
        return http.build();
    }
    
    /**
     * 自定义JWT转换器，从JWT声明中提取权限
     */
    private JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter grantedAuthoritiesConverter = new JwtGrantedAuthoritiesConverter();
        grantedAuthoritiesConverter.setAuthoritiesClaimName("authorities");
        grantedAuthoritiesConverter.setAuthorityPrefix("ROLE_");
        
        JwtAuthenticationConverter jwtAuthenticationConverter = new JwtAuthenticationConverter();
        jwtAuthenticationConverter.setJwtGrantedAuthoritiesConverter(grantedAuthoritiesConverter);
        
        return jwtAuthenticationConverter;
    }
}
```

### 3.3 配置文件

```yaml
# application.yml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          # 方式1: 使用JWK Set URI（推荐）
          jwk-set-uri: ${AUTH_SERVER_URL}/oauth2/jwks
          
          # 方式2: 使用颁发者URI（Spring Boot 2.4+）
          issuer-uri: ${AUTH_SERVER_URL}
          
          # JWT验证相关配置
          audiences: api-service-1,api-service-2
          
          # 自定义声明映射
          claim-set-converter:
            authorities-claim: authorities
            username-claim: sub
```

### 3.4 JWT验证配置详解

#### 3.4.1 公钥配置方式

**方式一：JWK Set URI（推荐）**
```java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt
        .jwkSetUri("http://auth-server/oauth2/jwks")
    )
)
```

**方式二：直接配置公钥**
```java
@Bean
public JwtDecoder jwtDecoder() {
    String publicKey = "-----BEGIN PUBLIC KEY-----\n" +
                      "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA..." +
                      "-----END PUBLIC KEY-----";
    
    return NimbusJwtDecoder.withPublicKey(parsePublicKey(publicKey))
            .signatureAlgorithm(SignatureAlgorithm.RS256)
            .build();
}
```

**方式三：使用颁发者URI（自动发现）**
```java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt
        .issuerLocation("http://auth-server")
    )
)
```

#### 3.4.2 自定义声明验证

```java
@Bean
public JwtDecoder jwtDecoder() {
    NimbusJwtDecoder jwtDecoder = NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();
    
    // 添加自定义验证器
    jwtDecoder.setJwtValidator(jwtValidator());
    
    return jwtDecoder;
}

private OAuth2TokenValidator<Jwt> jwtValidator() {
    List<OAuth2TokenValidator<Jwt>> validators = new ArrayList<>();
    
    // 验证颁发者
    validators.add(new JwtIssuerValidator(issuerUri));
    
    // 验证受众
    validators.add(new JwtAudienceValidator(Arrays.asList("api-service-1", "api-service-2")));
    
    // 验证有效期
    validators.add(new JwtTimestampValidator());
    
    // 自定义验证逻辑
    validators.add(token -> {
        if (!token.getClaimAsString("client_id").equals("allowed-client")) {
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Client not allowed", null)
            );
        }
        return OAuth2TokenValidatorResult.success();
    });
    
    return new DelegatingOAuth2TokenValidator<>(validators);
}
```

### 3.5 控制器示例

```java
@RestController
@RequestMapping("/api")
public class ResourceController {
    
    @GetMapping("/public/hello")
    public String publicEndpoint() {
        return "Public Hello";
    }
    
    @GetMapping("/user/profile")
    @PreAuthorize("hasRole('USER')")
    public ResponseEntity<UserProfile> getUserProfile(@AuthenticationPrincipal Jwt jwt) {
        String username = jwt.getSubject();
        String email = jwt.getClaim("email");
        
        UserProfile profile = new UserProfile(username, email);
        return ResponseEntity.ok(profile);
    }
    
    @GetMapping("/admin/stats")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<AdminStats> getAdminStats() {
        // 方法级别的权限控制
        return ResponseEntity.ok(new AdminStats());
    }
    
    /**
     * 直接从SecurityContext获取认证信息
     */
    @GetMapping("/me")
    public ResponseEntity<Map<String, Object>> getCurrentUser() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        
        Map<String, Object> userInfo = new HashMap<>();
        userInfo.put("principal", authentication.getPrincipal());
        userInfo.put("authorities", authentication.getAuthorities());
        userInfo.put("authenticated", authentication.isAuthenticated());
        
        return ResponseEntity.ok(userInfo);
    }
}
```

### 3.6 异常处理

```java
@ControllerAdvice
public class OAuth2ExceptionHandler {
    
    @ExceptionHandler({JwtValidationException.class, BadJwtException.class})
    public ResponseEntity<ErrorResponse> handleJwtValidationException(Exception ex) {
        ErrorResponse error = new ErrorResponse(
            "INVALID_TOKEN",
            "JWT validation failed: " + ex.getMessage(),
            HttpStatus.UNAUTHORIZED.value()
        );
        return new ResponseEntity<>(error, HttpStatus.UNAUTHORIZED);
    }
    
    @ExceptionHandler(AccessDeniedException.class)
    public ResponseEntity<ErrorResponse> handleAccessDeniedException(AccessDeniedException ex) {
        ErrorResponse error = new ErrorResponse(
            "ACCESS_DENIED",
            "Insufficient permissions",
            HttpStatus.FORBIDDEN.value()
        );
        return new ResponseEntity<>(error, HttpStatus.FORBIDDEN);
    }
    
    @ExceptionHandler(AuthenticationException.class)
    public ResponseEntity<ErrorResponse> handleAuthenticationException(AuthenticationException ex) {
        ErrorResponse error = new ErrorResponse(
            "AUTHENTICATION_FAILED",
            "Authentication failed: " + ex.getMessage(),
            HttpStatus.UNAUTHORIZED.value()
        );
        return new ResponseEntity<>(error, HttpStatus.UNAUTHORIZED);
    }
}

@Data
@AllArgsConstructor
class ErrorResponse {
    private String code;
    private String message;
    private int status;
}
```

## 4. 测试与验证

### 4.1 测试配置

```java
@SpringBootTest
@AutoConfigureMockMvc
class ResourceServerTests {
    
    @Autowired
    private MockMvc mockMvc;
    
    @Test
    void testPublicEndpoint() throws Exception {
        mockMvc.perform(get("/api/public/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Public Hello"));
    }
    
    @Test
    void testProtectedEndpointWithoutToken() throws Exception {
        mockMvc.perform(get("/api/user/profile"))
                .andExpect(status().isUnauthorized());
    }
    
    @Test
    void testProtectedEndpointWithValidToken() throws Exception {
        String validJwt = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...";
        
        mockMvc.perform(get("/api/user/profile")
                .header("Authorization", "Bearer " + validJwt))
                .andExpect(status().isOk());
    }
}
```

### 4.2 手动测试命令

```bash
# 获取访问令牌（假设授权服务器支持密码模式）
curl -X POST http://auth-server/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&username=user&password=pass&client_id=client"

# 使用令牌访问资源
curl -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..." \
  http://resource-server/api/user/profile
```

## 5. 高级配置

### 5.1 多租户支持

```java
@Bean
public JwtDecoder jwtDecoder() {
    return new TenantJwtDecoder(
        Map.of(
            "tenant1", "http://auth-tenant1/jwks",
            "tenant2", "http://auth-tenant2/jwks"
        )
    );
}

class TenantJwtDecoder implements JwtDecoder {
    private final Map<String, JwtDecoder> tenantDecoders;
    
    public TenantJwtDecoder(Map<String, String> tenantJwkSetUris) {
        this.tenantDecoders = tenantJwkSetUris.entrySet().stream()
            .collect(Collectors.toMap(
                Map.Entry::getKey,
                e -> NimbusJwtDecoder.withJwkSetUri(e.getValue()).build()
            ));
    }
    
    @Override
    public Jwt decode(String token) throws JwtException {
        // 从JWT中提取租户信息
        String tenant = extractTenantFromToken(token);
        JwtDecoder decoder = tenantDecoders.get(tenant);
        
        if (decoder == null) {
            throw new JwtException("Unknown tenant: " + tenant);
        }
        
        return decoder.decode(token);
    }
}
```

### 5.2 缓存JWT解码器

```java
@Configuration
public class JwtDecoderCacheConfig {
    
    @Bean
    public JwtDecoder cachingJwtDecoder() {
        return new CachingJwtDecoder(
            NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build(),
            3600, // 缓存1小时
            TimeUnit.SECONDS
        );
    }
}

class CachingJwtDecoder implements JwtDecoder {
    private final JwtDecoder delegate;
    private final Cache<String, Jwt> cache;
    
    public CachingJwtDecoder(JwtDecoder delegate, long duration, TimeUnit unit) {
        this.delegate = delegate;
        this.cache = Caffeine.newBuilder()
            .expireAfterWrite(duration, unit)
            .maximumSize(10000)
            .build();
    }
    
    @Override
    public Jwt decode(String token) throws JwtException {
        return cache.get(token, k -> delegate.decode(k));
    }
}
```

### 5.3 自定义JWT声明映射

```java
@Component
public class CustomJwtAuthenticationConverter 
        implements Converter<Jwt, AbstractAuthenticationToken> {
    
    @Override
    public AbstractAuthenticationToken convert(Jwt jwt) {
        // 自定义权限提取逻辑
        Collection<GrantedAuthority> authorities = extractAuthorities(jwt);
        
        // 自定义Principal
        CustomUserPrincipal principal = new CustomUserPrincipal(
            jwt.getSubject(),
            jwt.getClaim("email"),
            jwt.getClaim("department")
        );
        
        return new JwtAuthenticationToken(jwt, authorities, principal);
    }
    
    private Collection<GrantedAuthority> extractAuthorities(Jwt jwt) {
        List<String> scopes = jwt.getClaimAsStringList("scope");
        List<String> roles = jwt.getClaimAsStringList("authorities");
        
        Set<GrantedAuthority> authorities = new HashSet<>();
        
        if (scopes != null) {
            scopes.forEach(scope -> 
                authorities.add(new SimpleGrantedAuthority("SCOPE_" + scope))
            );
        }
        
        if (roles != null) {
            roles.forEach(role -> 
                authorities.add(new SimpleGrantedAuthority("ROLE_" + role))
            );
        }
        
        return authorities;
    }
}
```

## 6. 安全最佳实践

### 6.1 配置建议
1. **使用HTTPS**：所有令牌传输必须通过TLS加密
2. **令牌有效期**：设置合理的令牌过期时间（通常15-60分钟）
3. **密钥轮换**：定期轮换JWK签名密钥
4. **日志记录**：记录认证失败但不记录完整令牌

### 6.2 监控与审计
```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    tags:
      application: ${spring.application.name}
```

### 6.3 常见问题排查

| 问题现象 | 可能原因 | 解决方案 |
|---------|---------|---------|
| 401 Unauthorized | 令牌过期 | 检查令牌有效期，刷新令牌 |
| 401 Invalid Token | 签名验证失败 | 验证公钥配置，检查JWK URI |
| 403 Forbidden | 权限不足 | 检查JWT中的scope/authorities声明 |
| 500 Internal Error | 网络问题 | 检查授权服务器连通性 |

## 7. 总结

本文档详细介绍了Spring Security OAuth2资源服务器中JWT验证的完整实现方案。通过合理配置，可以实现：

1. **无状态认证**：基于JWT的无状态会话管理
2. **细粒度授权**：基于JWT声明的权限控制
3. **高可用性**：资源服务器独立验证，减少对授权服务器的依赖
4. **标准化兼容**：遵循OAuth 2.0和JWT标准

此方案适用于微服务架构、前后端分离应用等需要分布式认证授权的场景。