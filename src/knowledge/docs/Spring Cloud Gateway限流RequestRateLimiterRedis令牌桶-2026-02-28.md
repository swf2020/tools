# Spring Cloud Gateway 基于 RequestRateLimiter + Redis 的令牌桶限流方案

## 1. 概述

### 1.1 限流需求背景
在高并发场景下，API网关需要具备流量控制能力，防止后端服务被突发流量压垮。Spring Cloud Gateway 提供了 `RequestRateLimiter` 过滤器，结合 Redis 实现分布式令牌桶限流方案。

### 1.2 技术方案特点
- **分布式限流**：基于 Redis 实现，适用于集群环境
- **令牌桶算法**：支持突发流量处理
- **灵活配置**：支持按路由、按用户等多维度限流
- **实时响应**：超限立即返回 HTTP 429 状态码

## 2. 环境准备

### 2.1 依赖配置
```xml
<!-- pom.xml -->
<dependencies>
    <!-- Spring Cloud Gateway -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway</artifactId>
    </dependency>
    
    <!-- Redis Reactive -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis-reactive</artifactId>
    </dependency>
    
    <!-- 配置处理器 -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-configuration-processor</artifactId>
        <optional>true</optional>
    </dependency>
</dependencies>
```

### 2.2 Redis 配置
```yaml
# application.yml
spring:
  redis:
    host: localhost
    port: 6379
    password: 
    database: 0
    timeout: 2000ms
    lettuce:
      pool:
        max-active: 8
        max-wait: -1ms
        max-idle: 8
        min-idle: 0
```

## 3. 核心实现

### 3.1 限流配置类
```java
@Configuration
public class RateLimitConfig {
    
    /**
     * 创建 Redis 连接工厂
     */
    @Bean
    public ReactiveRedisTemplate<String, String> redisTemplate(
            ReactiveRedisConnectionFactory factory) {
        StringRedisSerializer serializer = new StringRedisSerializer();
        RedisSerializationContext<String, String> context = 
            RedisSerializationContext.<String, String>newSerializationContext(serializer)
                .key(serializer)
                .value(serializer)
                .hashKey(serializer)
                .hashValue(serializer)
                .build();
        return new ReactiveRedisTemplate<>(factory, context);
    }
    
    /**
     * 基于 IP 的限流解析器
     */
    @Bean(name = "ipKeyResolver")
    public KeyResolver ipKeyResolver() {
        return exchange -> Mono.just(
            exchange.getRequest()
                .getRemoteAddress()
                .getAddress()
                .getHostAddress()
        );
    }
    
    /**
     * 基于用户的限流解析器
     */
    @Bean(name = "userKeyResolver")
    public KeyResolver userKeyResolver() {
        return exchange -> {
            // 从请求头获取用户ID
            String userId = exchange.getRequest()
                .getHeaders()
                .getFirst("X-User-Id");
            if (StringUtils.isEmpty(userId)) {
                return Mono.just("anonymous");
            }
            return Mono.just(userId);
        };
    }
    
    /**
     * 基于 API 路径的限流解析器
     */
    @Bean(name = "apiKeyResolver")
    public KeyResolver apiKeyResolver() {
        return exchange -> Mono.just(
            exchange.getRequest()
                .getPath()
                .value()
        );
    }
}
```

### 3.2 网关路由配置
```yaml
# application.yml 路由配置
spring:
  cloud:
    gateway:
      routes:
        - id: user-service
          uri: lb://user-service
          predicates:
            - Path=/api/users/**
          filters:
            - name: RequestRateLimiter
              args:
                # 使用 Redis 限流器
                redis-rate-limiter.replenishRate: 10  # 每秒令牌生成数
                redis-rate-limiter.burstCapacity: 20  # 令牌桶容量
                redis-rate-limiter.requestedTokens: 1 # 每次请求消耗令牌数
                key-resolver: "#{@ipKeyResolver}"     # 限流键解析器
        
        - id: order-service
          uri: lb://order-service
          predicates:
            - Path=/api/orders/**
          filters:
            - name: RequestRateLimiter
              args:
                redis-rate-limiter.replenishRate: 5
                redis-rate-limiter.burstCapacity: 10
                redis-rate-limiter.requestedTokens: 1
                key-resolver: "#{@userKeyResolver}"
                
        # 特殊接口单独配置
        - id: payment-service-critical
          uri: lb://payment-service
          predicates:
            - Path=/api/payment/critical/**
          filters:
            - name: RequestRateLimiter
              args:
                redis-rate-limiter.replenishRate: 2
                redis-rate-limiter.burstCapacity: 5
                redis-rate-limiter.requestedTokens: 1
                key-resolver: "#{@ipKeyResolver}"
```

### 3.3 自定义限流配置
```java
@Component
@ConfigurationProperties(prefix = "gateway.rate-limiter")
@Data
public class RateLimiterProperties {
    
    /**
     * 默认限流配置
     */
    private DefaultConfig defaultConfig = new DefaultConfig();
    
    /**
     * 自定义限流规则
     */
    private Map<String, CustomConfig> customs = new HashMap<>();
    
    @Data
    public static class DefaultConfig {
        private Integer replenishRate = 10;
        private Integer burstCapacity = 20;
        private Integer requestedTokens = 1;
    }
    
    @Data
    public static class CustomConfig {
        private Integer replenishRate;
        private Integer burstCapacity;
        private Integer requestedTokens = 1;
        private String keyResolver = "ipKeyResolver";
    }
}

@Configuration
public class DynamicRateLimitConfig {
    
    @Autowired
    private RateLimiterProperties properties;
    
    @Autowired
    private ApplicationContext context;
    
    @Bean
    public RouteLocator customRouteLocator(RouteLocatorBuilder builder) {
        return builder.routes()
            .route("dynamic-route", r -> r
                .path("/api/**")
                .filters(f -> f
                    .requestRateLimiter(config -> {
                        config
                            .setRateLimiter(redisRateLimiter())
                            .setKeyResolver(dynamicKeyResolver());
                    })
                )
                .uri("lb://backend-service")
            )
            .build();
    }
    
    @Bean
    public RedisRateLimiter redisRateLimiter() {
        // 可根据配置动态创建限流器
        return new RedisRateLimiter(
            properties.getDefaultConfig().getReplenishRate(),
            properties.getDefaultConfig().getBurstCapacity(),
            properties.getDefaultConfig().getRequestedTokens()
        );
    }
    
    @Bean
    public KeyResolver dynamicKeyResolver() {
        return exchange -> {
            String path = exchange.getRequest().getPath().value();
            
            // 查找匹配的自定义配置
            for (Map.Entry<String, RateLimiterProperties.CustomConfig> entry : 
                 properties.getCustoms().entrySet()) {
                if (path.matches(entry.getKey())) {
                    String resolverName = entry.getValue().getKeyResolver();
                    KeyResolver resolver = context.getBean(resolverName, KeyResolver.class);
                    return resolver.resolve(exchange);
                }
            }
            
            // 使用默认的 IP 限流
            return context.getBean("ipKeyResolver", KeyResolver.class)
                .resolve(exchange);
        };
    }
}
```

## 4. 高级功能

### 4.1 自定义限流响应
```java
@Configuration
public class RateLimitResponseConfig {
    
    @Bean
    public GatewayFilterFactory<Config> customRateLimitFilter() {
        return new AbstractGatewayFilterFactory<Config>(Config.class) {
            
            @Override
            public GatewayFilter apply(Config config) {
                return (exchange, chain) -> {
                    return chain.filter(exchange)
                        .onErrorResume(RedisLimitException.class, e -> {
                            // 自定义限流响应
                            ServerHttpResponse response = exchange.getResponse();
                            response.setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
                            response.getHeaders().add("Content-Type", "application/json");
                            
                            Map<String, Object> result = new HashMap<>();
                            result.put("code", 429);
                            result.put("message", config.getErrorMessage());
                            result.put("timestamp", System.currentTimeMillis());
                            result.put("path", exchange.getRequest().getPath().value());
                            
                            DataBuffer buffer = response.bufferFactory()
                                .wrap(JsonUtils.toJson(result).getBytes());
                            return response.writeWith(Mono.just(buffer));
                        });
                };
            }
        };
    }
    
    @Data
    public static class Config {
        private String errorMessage = "请求过于频繁，请稍后再试";
    }
}
```

### 4.2 限流监控
```java
@Component
public class RateLimitMonitor {
    
    private final MeterRegistry meterRegistry;
    
    public RateLimitMonitor(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }
    
    @EventListener
    public void handleRateLimitEvent(RateLimitExceededEvent event) {
        // 记录限流事件
        Counter counter = Counter.builder("gateway.rate_limit.exceeded")
            .tag("route", event.getRouteId())
            .tag("key", event.getKey())
            .description("Rate limit exceeded count")
            .register(meterRegistry);
        counter.increment();
        
        // 记录日志
        log.warn("Rate limit exceeded - Route: {}, Key: {}, Time: {}", 
            event.getRouteId(), event.getKey(), LocalDateTime.now());
    }
    
    /**
     * 获取限流统计数据
     */
    @Scheduled(fixedDelay = 60000)
    public void collectMetrics() {
        Map<String, Double> metrics = new HashMap<>();
        
        // 从 Redis 获取各限流键的剩余令牌数
        // 实现具体的监控逻辑
        
        log.info("Rate limit metrics: {}", metrics);
    }
}
```

### 4.3 动态配置更新
```java
@RestController
@RefreshScope
@RequestMapping("/admin/rate-limit")
public class RateLimitAdminController {
    
    @Autowired
    private RateLimiterProperties properties;
    
    @Autowired
    private RedisRateLimiterRegistry limiterRegistry;
    
    /**
     * 动态更新限流配置
     */
    @PostMapping("/update")
    public ResponseEntity<?> updateConfig(@RequestBody UpdateRequest request) {
        // 更新内存配置
        RateLimiterProperties.CustomConfig config = 
            properties.getCustoms().computeIfAbsent(
                request.getPattern(), 
                k -> new RateLimiterProperties.CustomConfig()
            );
        config.setReplenishRate(request.getReplenishRate());
        config.setBurstCapacity(request.getBurstCapacity());
        
        // 刷新 Redis 限流器
        limiterRegistry.refresh();
        
        return ResponseEntity.ok("配置更新成功");
    }
    
    /**
     * 获取当前限流配置
     */
    @GetMapping("/configs")
    public ResponseEntity<Map<String, Object>> getConfigs() {
        Map<String, Object> result = new HashMap<>();
        result.put("default", properties.getDefaultConfig());
        result.put("customs", properties.getCustoms());
        return ResponseEntity.ok(result);
    }
    
    @Data
    public static class UpdateRequest {
        private String pattern;
        private Integer replenishRate;
        private Integer burstCapacity;
        private Integer requestedTokens;
    }
}
```

## 5. 测试验证

### 5.1 单元测试
```java
@SpringBootTest
@AutoConfigureWebTestClient
public class RateLimiterTest {
    
    @Autowired
    private WebTestClient webClient;
    
    @Test
    public void testRateLimit() {
        // 连续发送请求
        for (int i = 0; i < 30; i++) {
            if (i < 20) {
                // 前20个请求应该成功（令牌桶容量为20）
                webClient.get()
                    .uri("/api/users/1")
                    .exchange()
                    .expectStatus().isOk();
            } else {
                // 后续请求应该被限流
                webClient.get()
                    .uri("/api/users/1")
                    .exchange()
                    .expectStatus().isEqualTo(HttpStatus.TOO_MANY_REQUESTS);
            }
        }
    }
    
    @Test
    public void testDifferentKeys() {
        // 测试不同 IP 的独立限流
        webClient.mutate()
            .defaultHeader("X-Forwarded-For", "192.168.1.1")
            .build()
            .get()
            .uri("/api/users/1")
            .exchange()
            .expectStatus().isOk();
            
        webClient.mutate()
            .defaultHeader("X-Forwarded-For", "192.168.1.2")
            .build()
            .get()
            .uri("/api/users/1")
            .exchange()
            .expectStatus().isOk(); // 不同IP，应该也成功
    }
}
```

### 5.2 压力测试配置
```yaml
# test/application-test.yml
spring:
  redis:
    embedded:
      enabled: true
  cloud:
    gateway:
      routes:
        - id: test-route
          uri: http://localhost:${mock.server.port}
          predicates:
            - Path=/test/**
          filters:
            - name: RequestRateLimiter
              args:
                redis-rate-limiter.replenishRate: 100
                redis-rate-limiter.burstCapacity: 200
                key-resolver: "#{@ipKeyResolver}"
```

## 6. 生产部署建议

### 6.1 Redis 优化配置
```yaml
# Redis 生产配置
spring:
  redis:
    cluster:
      nodes:
        - redis-node1:6379
        - redis-node2:6379
        - redis-node3:6379
    timeout: 3000ms
    lettuce:
      pool:
        max-active: 32
        max-idle: 16
        min-idle: 8
        max-wait: 5000ms
      shutdown-timeout: 200ms
```

### 6.2 限流参数调优建议
| 场景类型 | replenishRate | burstCapacity | 说明 |
|---------|--------------|---------------|------|
| 严格限制 | 10-50 | 20-100 | 核心接口，防止滥用 |
| 一般限制 | 50-200 | 100-500 | 普通业务接口 |
| 宽松限制 | 200-1000 | 500-2000 | 公开接口，允许突发 |

### 6.3 异常处理策略
```java
@ControllerAdvice
public class GatewayExceptionHandler {
    
    @ExceptionHandler(RedisConnectionFailureException.class)
    public ResponseEntity<Map<String, Object>> handleRedisDown(
            ServerWebExchange exchange) {
        // Redis 宕机时的降级策略
        log.error("Redis connection failed, using fallback strategy");
        
        // 方案1: 直接放行（风险较高）
        // return chain.filter(exchange);
        
        // 方案2: 本地限流（需要额外实现）
        // return localRateLimiter(exchange, chain);
        
        // 方案3: 返回服务降级响应（推荐）
        Map<String, Object> result = new HashMap<>();
        result.put("code", 503);
        result.put("message", "系统限流服务暂时不可用");
        result.put("suggestion", "请稍后重试");
        
        return ResponseEntity
            .status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(result);
    }
}
```

## 7. 监控告警

### 7.1 Prometheus 指标
```yaml
# Micrometer 配置
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus,metrics
  metrics:
    export:
      prometheus:
        enabled: true
    distribution:
      percentiles-histogram:
        http.server.requests: true
    tags:
      application: ${spring.application.name}
```

### 7.2 关键监控指标
```promql
# 限流触发次数
rate(gateway_rate_limit_exceeded_total[5m])

# 请求成功率
sum(rate(http_server_requests_seconds_count{status!~"5.."}[5m])) 
/ 
sum(rate(http_server_requests_seconds_count[5m]))

# 各接口限流情况
gateway_rate_limit_exceeded_total{route="user-service"}
```

## 8. 总结

本方案实现了基于 Spring Cloud Gateway 和 Redis 的分布式令牌桶限流，具备以下特点：

1. **分布式支持**：通过 Redis 实现集群环境下的统一限流
2. **灵活配置**：支持多维度（IP、用户、接口）限流策略
3. **动态调整**：支持运行时配置更新
4. **监控完善**：集成指标收集和告警机制
5. **容错降级**：Redis 异常时的降级策略

实际部署时，需要根据业务特点和系统压力，合理调整令牌桶参数，并结合监控数据进行持续优化。

## 附录

### A. Redis Lua 脚本
Spring Cloud Gateway 使用的 Redis 限流 Lua 脚本位于：
`org.springframework.cloud.gateway.filter.ratelimit.RedisRateLimiter`

### B. 性能测试报告
建议在生产环境部署前，使用 JMeter 或 Gatling 进行压力测试，验证限流效果和系统性能。

### C. 相关文档
- [Spring Cloud Gateway 官方文档](https://spring.io/projects/spring-cloud-gateway)
- [Redis 官方文档](https://redis.io/documentation)
- [令牌桶算法原理](https://en.wikipedia.org/wiki/Token_bucket)