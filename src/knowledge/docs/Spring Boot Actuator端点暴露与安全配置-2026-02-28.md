# Spring Boot Actuator 端点暴露与安全配置技术文档

## 1. 概述

Spring Boot Actuator 是 Spring Boot 提供的生产级功能模块，用于监控和管理应用程序。它通过一系列 HTTP 端点暴露应用程序的运行状况、指标、配置等信息。然而，不当的端点暴露可能导致安全风险，因此需要合理配置。

## 2. Actuator 端点分类

### 2.1 常用内置端点
- `/actuator/health` - 应用健康状态
- `/actuator/info` - 应用自定义信息
- `/actuator/metrics` - 应用指标
- `/actuator/env` - 环境变量和配置属性
- `/actuator/loggers` - 日志配置
- `/actuator/threaddump` - 线程转储
- `/actuator/httptrace` - HTTP 请求追踪
- `/actuator/beans` - Spring Beans 信息
- `/actuator/mappings` - 请求映射

### 2.2 端点分类（按敏感程度）
- **非敏感端点**: `/health`, `/info`, `/metrics`（部分）
- **敏感端点**: `/env`, `/configprops`, `/loggers`, `/heapdump`, `/threaddump`
- **高敏感端点**: `/shutdown`, `/caches`

## 3. 端点暴露配置

### 3.1 基础配置

```yaml
# application.yml
management:
  endpoints:
    web:
      exposure:
        # 暴露所有端点（不推荐生产环境）
        include: "*"
        
        # 仅暴露特定端点
        include: health,info,metrics
        
        # 排除敏感端点
        exclude: env,beans,mappings
      
      # 自定义基础路径
      base-path: /monitor
      
      # 端口配置（可与应用端口分离）
  server:
    port: 8081
```

### 3.2 按配置文件区分配置

```yaml
# application-dev.yml
management:
  endpoints:
    web:
      exposure:
        include: "*"

# application-prod.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info
```

## 4. 安全配置策略

### 4.1 使用 Spring Security 保护端点

```java
@Configuration
@EnableWebSecurity
public class ActuatorSecurityConfig extends WebSecurityConfigurerAdapter {
    
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                // 健康检查端点允许匿名访问
                .antMatchers("/actuator/health").permitAll()
                // info端点允许内部网络访问
                .antMatchers("/actuator/info").hasIpAddress("192.168.0.0/24")
                // 其他监控端点需要认证和特定角色
                .antMatchers("/actuator/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            .and()
            .httpBasic()
            .and()
            .csrf().disable(); // 注意：为端点禁用CSRF需要评估风险
    }
    
    @Bean
    @Override
    public UserDetailsService userDetailsService() {
        UserDetails user = User.builder()
            .username("actuator")
            .password(passwordEncoder().encode("secure-password"))
            .roles("ADMIN")
            .build();
        return new InMemoryUserDetailsManager(user);
    }
    
    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
```

### 4.2 独立管理端口的安全配置

```java
@Configuration
@Order(1) // 高优先级配置
public class ManagementSecurityConfig extends WebSecurityConfigurerAdapter {
    
    @Value("${management.server.port:8081}")
    private int managementPort;
    
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .antMatcher("/actuator/**")
            .authorizeRequests()
                .anyRequest().hasRole("MONITOR")
            .and()
            .httpBasic();
    }
    
    @Override
    public void configure(WebSecurity web) {
        web.ignoring().antMatchers("/actuator/health");
    }
    
    // 配置独立的认证管理器
    @Bean(name = "managementAuthenticationManager")
    @Override
    public AuthenticationManager authenticationManagerBean() throws Exception {
        return super.authenticationManagerBean();
    }
}
```

## 5. 高级安全配置

### 5.1 基于角色的端点访问控制

```java
@Configuration
public class RoleBasedEndpointFilter {
    
    @Bean
    public EndpointFilter<ExposableWebEndpoint> endpointFilter() {
        return endpoint -> {
            Set<String> roles = getRequiredRoles(endpoint);
            return SecurityContextHolder.getContext()
                .getAuthentication()
                .getAuthorities()
                .stream()
                .anyMatch(authority -> roles.contains(authority.getAuthority()));
        };
    }
    
    private Set<String> getRequiredRoles(ExposableWebEndpoint endpoint) {
        Map<String, Set<String>> endpointRoles = new HashMap<>();
        endpointRoles.put("health", Set.of("ROLE_USER", "ROLE_ADMIN"));
        endpointRoles.put("info", Set.of("ROLE_USER"));
        endpointRoles.put("env", Set.of("ROLE_ADMIN"));
        endpointRoles.put("beans", Set.of("ROLE_ADMIN"));
        
        return endpointRoles.getOrDefault(
            endpoint.getEndpointId().toLowerCase(),
            Set.of("ROLE_ADMIN")
        );
    }
}
```

### 5.2 IP 白名单限制

```java
@Component
public class IpWhitelistFilter extends OncePerRequestFilter {
    
    private final List<String> whitelist = Arrays.asList(
        "127.0.0.1",
        "192.168.1.0/24",
        "10.0.0.0/8"
    );
    
    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                  HttpServletResponse response,
                                  FilterChain filterChain) throws ServletException, IOException {
        
        if (request.getRequestURI().startsWith("/actuator")) {
            String clientIp = getClientIp(request);
            
            if (!isAllowed(clientIp)) {
                response.setStatus(HttpStatus.FORBIDDEN.value());
                response.getWriter().write("Access denied");
                return;
            }
        }
        
        filterChain.doFilter(request, response);
    }
    
    private boolean isAllowed(String ip) {
        return whitelist.stream().anyMatch(range -> 
            matchesRange(ip, range)
        );
    }
    
    private boolean matchesRange(String ip, String range) {
        // 实现IP范围匹配逻辑
        return true;
    }
    
    private String getClientIp(HttpServletRequest request) {
        // 从请求头获取真实IP（考虑代理情况）
        String xForwardedFor = request.getHeader("X-Forwarded-For");
        return xForwardedFor != null ? xForwardedFor : request.getRemoteAddr();
    }
}
```

## 6. 生产环境推荐配置

### 6.1 最小化暴露配置

```yaml
# application-prod.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
      base-path: /internal/monitor
      path-mapping:
        health: status
        prometheus: metrics-data
      
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
    info:
      env:
        enabled: true
    metrics:
      enabled: true
      
  # 启用仅内部访问
  server:
    port: 8081
    address: 127.0.0.1  # 仅本地访问
    
  # 启用健康检查分组
  health:
    defaults:
      enabled: false
    db:
      enabled: true
    disk:
      enabled: true
    readiness:
      enabled: true
    liveness:
      enabled: true
      
  # 指标配置
  metrics:
    export:
      prometheus:
        enabled: true
    distribution:
      sla:
        http.server.requests: 100ms,200ms,500ms
```

### 6.2 安全配置组合

```java
@Configuration
public class ProductionSecurityConfig {
    
    @Bean
    public SecurityFilterChain actuatorFilterChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/internal/monitor/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/internal/monitor/status").permitAll()
                .requestMatchers("/internal/monitor/info").hasRole("MONITOR")
                .requestMatchers("/internal/monitor/**").hasRole("ADMIN")
            )
            .httpBasic(withDefaults())
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .addFilterBefore(ipWhitelistFilter(), BasicAuthenticationFilter.class);
        
        return http.build();
    }
    
    @Bean
    public ClientIpFilter ipWhitelistFilter() {
        return new ClientIpFilter();
    }
}
```

## 7. Kubernetes 环境最佳实践

```yaml
# deployment.yaml 配置示例
apiVersion: apps/v1
kind: Deployment
metadata:
  name: spring-boot-app
spec:
  template:
    spec:
      containers:
      - name: app
        image: myapp:latest
        ports:
        - containerPort: 8080
        - containerPort: 8081  # Actuator端口
        livenessProbe:
          httpGet:
            path: /internal/monitor/status/liveness
            port: 8081
          initialDelaySeconds: 60
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /internal/monitor/status/readiness
            port: 8081
          initialDelaySeconds: 30
          periodSeconds: 5
---
# 网络策略：限制Actuator端口访问
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: actuator-access
spec:
  podSelector:
    matchLabels:
      app: spring-boot-app
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: monitoring
    ports:
    - protocol: TCP
      port: 8081
```

## 8. 监控与审计

### 8.1 端点访问日志

```java
@Component
public class ActuatorAccessLogger {
    
    private static final Logger logger = LoggerFactory.getLogger("ACTUATOR_ACCESS");
    
    @EventListener
    public void onAuditEvent(AuditApplicationEvent event) {
        AuditEvent auditEvent = event.getAuditEvent();
        
        if (auditEvent.getType().startsWith("ACTUATOR")) {
            logger.info("Actuator endpoint accessed: {}, Principal: {}, IP: {}", 
                auditEvent.getData(),
                auditEvent.getPrincipal(),
                auditEvent.getSource()
            );
        }
    }
    
    @Bean
    public AuditEventRepository auditEventRepository() {
        return new InMemoryAuditEventRepository(100);
    }
}
```

### 8.2 端点健康状态告警

```java
@Component
public class HealthCheckAlert {
    
    @EventListener
    public void onHealthChanged(HealthChangedEvent event) {
        if (event.getStatus() != Status.UP) {
            // 发送告警通知
            sendAlert(String.format(
                "Health status changed: %s -> %s, Details: %s",
                event.getPreviousStatus(),
                event.getStatus(),
                event.getHealth()
            ));
        }
    }
}
```

## 9. 常见问题与解决方案

### 9.1 端点无法访问
- **问题**: 端点返回404
- **解决**: 检查`management.endpoints.web.exposure.include`配置

### 9.2 认证失败
- **问题**: 返回401 Unauthorized
- **解决**: 验证Spring Security配置和用户凭证

### 9.3 性能影响
- **问题**: Actuator端点响应慢
- **解决**: 
  - 使用独立的监控端口
  - 限制敏感端点的访问频率
  - 启用端点缓存

### 9.4 信息泄露
- **问题**: 敏感信息通过端点暴露
- **解决**:
  - 使用`@ConfigurationProperties`的`security`属性
  - 配置敏感属性掩码
  - 禁用危险端点

## 10. 总结

Spring Boot Actuator 提供了强大的监控能力，但必须配合适当的安全配置：

1. **最小暴露原则**: 仅暴露必要的端点
2. **分层安全**: 不同端点采用不同安全级别
3. **网络隔离**: 使用独立端口和网络策略
4. **访问控制**: 结合认证、授权和IP限制
5. **审计监控**: 记录所有监控端点访问

通过合理的配置，可以在提供有效监控能力的同时，确保应用程序的安全性。

---
**文档版本**: 1.0  
**最后更新**: 2024年1月  
**适用版本**: Spring Boot 2.7.x+