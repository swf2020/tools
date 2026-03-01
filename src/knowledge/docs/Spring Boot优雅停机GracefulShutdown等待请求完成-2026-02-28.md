# Spring Boot优雅停机实现指南

## 概述

### 什么是优雅停机
优雅停机（Graceful Shutdown）是指在应用关闭时，系统不会立即终止进程，而是等待当前正在处理的请求完成后再安全关闭。这种机制确保了：
- 已接收的请求能够正常完成处理
- 客户端不会收到连接中断错误
- 数据库连接、文件句柄等资源能够正确释放
- 分布式系统中的服务注册能够正常注销

### 为什么需要优雅停机
1. **避免数据不一致**：突然关闭可能导致事务中断
2. **提升用户体验**：避免用户看到错误页面
3. **维护系统稳定性**：在微服务架构中，避免连锁故障
4. **平滑发布更新**：在滚动更新时确保流量正常迁移

## 实现方案

### 方案一：使用Spring Boot内置的优雅停机（推荐）

#### 1. 版本要求
- Spring Boot 2.3.0+ 原生支持优雅停机
- 早期版本需要自定义实现

#### 2. 配置步骤

**application.yml/application.properties配置：**

```yaml
# 开启优雅停机
server:
  shutdown: graceful

# 设置等待时间（默认30秒）
spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
```

```properties
# 开启优雅停机
server.shutdown=graceful

# 设置等待时间（默认30秒）
spring.lifecycle.timeout-per-shutdown-phase=30s
```

#### 3. 工作原理

1. **收到关闭信号**（如kill -2，Ctrl+C）
2. **停止接收新请求**：停止接收新的HTTP请求
3. **等待进行中的请求完成**：等待现有请求处理完毕
4. **关闭应用上下文**：超过等待时间后强制关闭

### 方案二：自定义优雅停机实现

#### 1. 创建优雅停机端点

```java
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "graceful-shutdown")
public class GracefulShutdownEndpoint {
    
    private final ApplicationContext context;
    
    public GracefulShutdownEndpoint(ApplicationContext context) {
        this.context = context;
    }
    
    @WriteOperation
    public String gracefulShutdown() {
        new Thread(() -> {
            try {
                Thread.sleep(5000); // 等待5秒让端点响应返回
                ((ConfigurableApplicationContext) context).close();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }).start();
        
        return "Graceful shutdown initiated";
    }
}
```

#### 2. 自定义GracefulShutdown组件

```java
import org.apache.catalina.connector.Connector;
import org.springframework.boot.web.embedded.tomcat.TomcatConnectorCustomizer;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.stereotype.Component;

import java.util.concurrent.Executor;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

@Component
public class GracefulShutdown implements TomcatConnectorCustomizer, 
        ApplicationListener<ContextClosedEvent> {
    
    private volatile Connector connector;
    private final int waitTime = 30;
    
    @Override
    public void customize(Connector connector) {
        this.connector = connector;
    }
    
    @Override
    public void onApplicationEvent(ContextClosedEvent event) {
        if (connector == null) {
            return;
        }
        
        // 暂停接收新请求
        connector.pause();
        
        // 获取Tomcat线程池
        Executor executor = connector.getProtocolHandler().getExecutor();
        
        if (executor instanceof ThreadPoolExecutor) {
            try {
                ThreadPoolExecutor threadPoolExecutor = (ThreadPoolExecutor) executor;
                
                // 停止接收新任务
                threadPoolExecutor.shutdown();
                
                // 等待现有任务完成
                if (!threadPoolExecutor.awaitTermination(waitTime, TimeUnit.SECONDS)) {
                    log.warn("Tomcat thread pool did not shut down gracefully within " 
                            + waitTime + " seconds. Proceeding with forceful shutdown");
                    
                    // 强制关闭
                    threadPoolExecutor.shutdownNow();
                    
                    // 继续等待
                    if (!threadPoolExecutor.awaitTermination(waitTime, TimeUnit.SECONDS)) {
                        log.error("Tomcat thread pool did not terminate");
                    }
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }
    }
}
```

#### 3. 配置自定义GracefulShutdown

```java
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TomcatConfiguration {
    
    @Bean
    public GracefulShutdown gracefulShutdown() {
        return new GracefulShutdown();
    }
    
    @Bean
    public WebServerFactoryCustomizer tomcatCustomizer(GracefulShutdown gracefulShutdown) {
        return factory -> {
            if (factory instanceof TomcatServletWebServerFactory) {
                ((TomcatServletWebServerFactory) factory)
                    .addConnectorCustomizers(gracefulShutdown);
            }
        };
    }
}
```

### 方案三：使用Undertow服务器的优雅停机

```yaml
# 使用Undertow服务器
server:
  undertow:
    # 优雅停机相关配置
    threads:
      io: 16
      worker: 256
    # 等待请求完成的超时时间
    no-request-timeout: 60000
```

## 配置详情

### 1. 完整配置示例

```yaml
server:
  shutdown: graceful
  port: 8080
  tomcat:
    # 连接相关配置
    connection-timeout: 2s
    keep-alive-timeout: 15s
    max-connections: 8192
    threads:
      max: 200
      min-spare: 10
    accept-count: 100

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
  
  # 健康检查配置
  management:
    endpoint:
      health:
        show-details: always
    endpoints:
      web:
        exposure:
          include: health,info,graceful-shutdown
    health:
      livenessstate:
        enabled: true
      readinessstate:
        enabled: true
```

### 2. 超时时间配置策略

| 业务场景 | 推荐超时时间 | 说明 |
|---------|-------------|------|
| 短请求服务 | 10-30秒 | API网关、简单查询服务 |
| 长请求服务 | 60-120秒 | 文件上传、大数据处理 |
| 批处理服务 | 300秒以上 | 批量数据处理 |

## 最佳实践

### 1. 结合健康检查
```yaml
# 配置Kubernetes探针
management:
  endpoints:
    web:
      exposure:
        include: health
  health:
    probes:
      enabled: true
```

### 2. 容器化部署配置
```dockerfile
# Dockerfile中设置优雅停机
STOPSIGNAL SIGTERM
```

```yaml
# Kubernetes部署配置
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: app
        lifecycle:
          preStop:
            exec:
              command: ["sh", "-c", "sleep 10"]
        readinessProbe:
          httpGet:
            path: /actuator/health/readiness
            port: 8080
        livenessProbe:
          httpGet:
            path: /actuator/health/liveness
            port: 8080
```

### 3. 监控和告警
```java
// 监控优雅停机事件
@Component
public class ShutdownEventListener {
    
    private static final Logger log = LoggerFactory.getLogger(ShutdownEventListener.class);
    
    @EventListener
    public void onApplicationEvent(ContextClosedEvent event) {
        log.info("Application is shutting down gracefully...");
        
        // 发送监控指标
        Metrics.counter("application.shutdown.graceful")
               .increment();
    }
}
```

### 4. 处理特殊场景

#### 处理WebSocket连接
```java
@Component
public class WebSocketGracefulShutdown {
    
    @PreDestroy
    public void cleanupWebSockets() {
        // 关闭所有WebSocket连接
        // 发送关闭帧
        // 等待确认
    }
}
```

#### 处理数据库事务
```java
@Component
public class TransactionGracefulShutdown {
    
    @PreDestroy
    public void waitForTransactions() {
        // 等待进行中的事务完成
        // 或执行回滚
    }
}
```

## 测试验证

### 1. 本地测试
```bash
# 启动应用
java -jar your-application.jar

# 发送关闭信号
kill -2 <PID>  # SIGINT
# 或
kill -15 <PID> # SIGTERM

# 观察日志输出
tail -f application.log
```

### 2. 自动化测试
```java
@SpringBootTest
@AutoConfigureMockMvc
class GracefulShutdownTest {
    
    @Autowired
    private MockMvc mockMvc;
    
    @Test
    void testGracefulShutdown() throws Exception {
        // 发送长耗时请求
        CompletableFuture<MvcResult> future = CompletableFuture.supplyAsync(() -> {
            return mockMvc.perform(get("/long-running"))
                         .andReturn();
        });
        
        // 触发关闭
        Thread.sleep(1000);
        SpringApplication.exit(applicationContext);
        
        // 验证请求是否完成
        MvcResult result = future.get(10, TimeUnit.SECONDS);
        assertThat(result.getResponse().getStatus()).isEqualTo(200);
    }
}
```

## 故障排查

### 常见问题及解决方案

1. **等待超时后强制关闭**
   - 原因：某些请求处理时间过长
   - 解决：调整`timeout-per-shutdown-phase`或优化慢请求

2. **线程池拒绝关闭**
   - 原因：线程死锁或无限循环
   - 解决：添加线程转储分析

3. **数据库连接未释放**
   - 原因：连接池未正确关闭
   - 解决：配置连接池优雅关闭

### 监控指标
```yaml
# 建议监控的指标
metrics:
  - application.shutdown.duration
  - application.requests.active
  - tomcat.threads.busy
  - jdbc.connections.active
```

## 总结

Spring Boot优雅停机的实现要点：

1. **推荐使用Spring Boot 2.3+内置方案**，配置简单可靠
2. **合理设置超时时间**，根据业务特点调整
3. **结合健康检查**，在容器化环境中实现零停机部署
4. **处理特殊资源**，如数据库连接、WebSocket等
5. **完善监控告警**，确保可观测性

通过实施优雅停机，可以显著提升系统的可靠性和用户体验，特别是在微服务架构和容器化部署环境中。