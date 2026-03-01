# Spring Cloud Gateway路由断言与过滤器链技术文档

## 1. 概述

### 1.1 Spring Cloud Gateway简介
Spring Cloud Gateway是基于Spring 5、Spring Boot 2和Project Reactor等技术构建的API网关，提供了一种简单而有效的方式来路由请求，并提供了丰富的断言和过滤器功能。

### 1.2 核心概念
- **路由(Route)**: 网关的基本构建块，由ID、目标URI、断言集合和过滤器集合组成
- **断言(Predicate)**: 匹配HTTP请求中的任何内容（如请求头、参数等）
- **过滤器(Filter)**: 修改请求和响应的处理逻辑

## 2. 路由断言详解

### 2.1 断言基础
路由断言用于判断请求是否匹配特定路由，所有断言必须满足才会执行路由。

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: example_route
          uri: http://example.org
          predicates:
            - Path=/api/**
```

### 2.2 常用内置断言

#### 2.2.1 路径断言 (Path)
```yaml
predicates:
  - Path=/red/{segment},/blue/{segment}
```

#### 2.2.2 方法断言 (Method)
```yaml
predicates:
  - Method=GET,POST
```

#### 2.2.3 头部断言 (Header)
```yaml
predicates:
  - Header=X-Request-Id, \d+
```

#### 2.2.4 查询参数断言 (Query)
```yaml
predicates:
  - Query=green, gree.
```

#### 2.2.5 Cookie断言 (Cookie)
```yaml
predicates:
  - Cookie=chocolate, ch.p
```

#### 2.2.6 主机断言 (Host)
```yaml
predicates:
  - Host=**.somehost.org,**.anotherhost.org
```

#### 2.2.7 时间断言
```yaml
predicates:
  # 在指定时间之后
  - After=2017-01-20T17:42:47.789-07:00[America/Denver]
  # 在指定时间之前
  - Before=2017-01-20T17:42:47.789-07:00[America/Denver]
  # 在指定时间段之间
  - Between=2017-01-20T17:42:47.789-07:00[America/Denver], 2017-01-21T17:42:47.789-07:00[America/Denver]
```

#### 2.2.8 远程地址断言
```yaml
predicates:
  - RemoteAddr=192.168.1.1/24
```

### 2.3 自定义断言

```java
@Component
public class CustomRoutePredicateFactory extends 
    AbstractRoutePredicateFactory<CustomRoutePredicateFactory.Config> {
    
    public CustomRoutePredicateFactory() {
        super(Config.class);
    }
    
    @Override
    public Predicate<ServerWebExchange> apply(Config config) {
        return exchange -> {
            // 自定义断言逻辑
            String customHeader = exchange.getRequest()
                .getHeaders()
                .getFirst("X-Custom-Header");
            return customHeader != null && 
                   customHeader.equals(config.getValue());
        };
    }
    
    public static class Config {
        private String value;
        
        // getters and setters
    }
}
```

## 3. 过滤器链详解

### 3.1 过滤器类型

#### 3.1.1 GatewayFilter
作用于单个路由的过滤器。

#### 3.1.2 GlobalFilter
作用于所有路由的全局过滤器。

### 3.2 内置过滤器

#### 3.2.1 请求头修改过滤器
```yaml
filters:
  - AddRequestHeader=X-Request-red, blue
  - RemoveRequestHeader=X-Request-Foo
  - SetRequestHeader=X-Request-Red, Blue
```

#### 3.2.2 响应头修改过滤器
```yaml
filters:
  - AddResponseHeader=X-Response-Red, Blue
  - RemoveResponseHeader=X-Response-Foo
  - SetResponseHeader=X-Response-Red, Blue
```

#### 3.2.3 路径重写过滤器
```yaml
filters:
  - RewritePath=/red/(?<segment>.*), /$\{segment}
```

#### 3.2.4 请求参数过滤器
```yaml
filters:
  - AddRequestParameter=red, blue
```

#### 3.2.5 重试过滤器
```yaml
filters:
  - name: Retry
    args:
      retries: 3
      statuses: BAD_GATEWAY, INTERNAL_SERVER_ERROR
      methods: GET,POST
```

#### 3.2.6 断路器过滤器
```yaml
filters:
  - name: CircuitBreaker
    args:
      name: myCircuitBreaker
      fallbackUri: forward:/fallback
```

#### 3.2.7 请求限流过滤器
```yaml
filters:
  - name: RequestRateLimiter
    args:
      redis-rate-limiter.replenishRate: 10
      redis-rate-limiter.burstCapacity: 20
      key-resolver: "#{@userKeyResolver}"
```

### 3.3 自定义过滤器

#### 3.3.1 自定义GatewayFilter
```java
@Component
public class CustomGatewayFilterFactory extends 
    AbstractGatewayFilterFactory<CustomGatewayFilterFactory.Config> {
    
    @Override
    public GatewayFilter apply(Config config) {
        return (exchange, chain) -> {
            // 前置处理
            ServerHttpRequest request = exchange.getRequest()
                .mutate()
                .header("X-Custom-Filter", "processed")
                .build();
            
            return chain.filter(exchange.mutate().request(request).build())
                .then(Mono.fromRunnable(() -> {
                    // 后置处理
                    ServerHttpResponse response = exchange.getResponse();
                    response.getHeaders().add("X-Custom-Response", "completed");
                }));
        };
    }
    
    public static class Config {
        // 配置属性
    }
}
```

#### 3.3.2 自定义GlobalFilter
```java
@Component
@Order(-1)
public class CustomGlobalFilter implements GlobalFilter {
    
    @Override
    public Mono<Void> filter(ServerWebExchange exchange, 
                             GatewayFilterChain chain) {
        // 全局过滤器逻辑
        String traceId = UUID.randomUUID().toString();
        ServerHttpRequest request = exchange.getRequest()
            .mutate()
            .header("X-Trace-Id", traceId)
            .build();
        
        return chain.filter(exchange.mutate().request(request).build())
            .then(Mono.fromRunnable(() -> {
                // 记录日志等后置处理
                log.info("Request completed with traceId: {}", traceId);
            }));
    }
}
```

## 4. 综合配置示例

### 4.1 完整路由配置示例
```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: user_service
          uri: lb://user-service
          predicates:
            - Path=/api/users/**
            - Method=GET,POST
            - After=2024-01-01T00:00:00.000+08:00[Asia/Shanghai]
          filters:
            - StripPrefix=2
            - AddRequestHeader=X-Source, gateway
            - name: Retry
              args:
                retries: 3
                statuses: SERVICE_UNAVAILABLE
            - name: CircuitBreaker
              args:
                name: userServiceCB
                fallbackUri: forward:/fallback/user
        
        - id: product_service
          uri: lb://product-service
          predicates:
            - Path=/api/products/**
            - Header=X-Requested-With, XMLHttpRequest
          filters:
            - RewritePath=/api/products/(?<segment>.*), /$\{segment}
            - SetResponseHeader=X-Response-Time, "$(response.headers['X-Response-Time'] ?: 'unknown')"
```

### 4.2 Java DSL配置示例
```java
@Configuration
public class GatewayConfiguration {
    
    @Bean
    public RouteLocator customRouteLocator(RouteLocatorBuilder builder) {
        return builder.routes()
            .route("custom_route", r -> r
                .path("/custom/**")
                .and()
                .header("X-Custom-Header", ".*")
                .filters(f -> f
                    .addRequestHeader("X-Processed", "true")
                    .circuitBreaker(config -> config
                        .setName("customCB")
                        .setFallbackUri("forward:/fallback/custom"))
                )
                .uri("lb://custom-service"))
            .build();
    }
}
```

## 5. 高级特性

### 5.1 过滤器执行顺序
```java
@Component
@Order(0)
public class FirstGlobalFilter implements GlobalFilter {
    // 最先执行
}

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class HighPriorityFilter implements GlobalFilter {
    // 高优先级执行
}

@Component
@Order(Ordered.LOWEST_PRECEDENCE)
public class LowPriorityFilter implements GlobalFilter {
    // 低优先级执行
}
```

### 5.2 动态路由
```java
@Component
public class DynamicRouteService {
    
    @Autowired
    private RouteDefinitionWriter routeDefinitionWriter;
    
    public void addRoute(String id, String uri, List<PredicateDefinition> predicates) {
        RouteDefinition routeDefinition = new RouteDefinition();
        routeDefinition.setId(id);
        routeDefinition.setUri(URI.create(uri));
        routeDefinition.setPredicates(predicates);
        
        routeDefinitionWriter.save(Mono.just(routeDefinition)).subscribe();
    }
    
    public void deleteRoute(String id) {
        routeDefinitionWriter.delete(Mono.just(id)).subscribe();
    }
}
```

### 5.3 监控与度量
```yaml
management:
  endpoints:
    web:
      exposure:
        include: gateway,health,metrics
  metrics:
    export:
      prometheus:
        enabled: true
```

## 6. 最佳实践

### 6.1 性能优化建议
1. **合理使用断言**: 避免过于复杂的断言逻辑
2. **过滤器顺序优化**: 将轻量级过滤器前置
3. **响应缓存**: 对静态资源启用缓存
4. **连接池配置**: 调整HTTP客户端连接池参数

### 6.2 安全注意事项
1. **输入验证**: 对所有传入参数进行验证
2. **速率限制**: 防止DDoS攻击
3. **认证授权**: 统一身份验证
4. **日志审计**: 记录关键操作日志

### 6.3 故障处理
1. **超时配置**: 合理设置连接和读取超时
2. **熔断降级**: 配置断路器防止级联故障
3. **重试策略**: 为可重试操作配置重试逻辑
4. **健康检查**: 实现下游服务健康检查

## 7. 调试与排查

### 7.1 日志配置
```yaml
logging:
  level:
    org.springframework.cloud.gateway: DEBUG
    reactor.netty.http.client: DEBUG
```

### 7.2 Actuator端点
- `/actuator/gateway/routes`: 查看所有路由
- `/actuator/gateway/globalfilters`: 查看全局过滤器
- `/actuator/gateway/routefilters`: 查看路由过滤器

## 8. 版本兼容性

| Spring Cloud Gateway | Spring Boot | Spring Cloud |
|---------------------|-------------|--------------|
| 4.0.x               | 3.1.x       | 2022.0.x     |
| 3.1.x               | 2.7.x       | 2021.0.x     |
| 2.2.x               | 2.3.x       | Hoxton       |

## 总结

Spring Cloud Gateway通过强大的路由断言和过滤器链机制，提供了灵活、高效的API网关解决方案。合理配置和使用这些特性可以显著提升系统的可维护性、安全性和性能。建议结合实际业务需求，选择适合的断言和过滤器组合，并遵循最佳实践进行配置和管理。