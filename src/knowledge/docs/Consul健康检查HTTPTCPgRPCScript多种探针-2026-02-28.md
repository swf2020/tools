# Consul健康检查技术文档：HTTP/TCP/gRPC/Script多种探针详解

## 1. 概述

Consul是一个分布式、高可用的服务发现与配置管理工具，其健康检查机制是确保服务可靠性的核心功能。健康检查允许Consul定期验证服务实例是否正常运行，自动将不健康的实例从服务发现中移除，从而保证流量只被路由到健康的服务节点。

## 2. 健康检查类型

### 2.1 HTTP健康检查
HTTP健康检查是最常用的检查方式，通过向服务端点发送HTTP请求并验证响应来判断服务状态。

**配置示例：**
```json
{
  "check": {
    "id": "api-health-check",
    "name": "API Health Status",
    "http": "https://localhost:8080/health",
    "method": "GET",
    "header": {
      "Authorization": ["Bearer xyz"]
    },
    "tls_skip_verify": false,
    "interval": "10s",
    "timeout": "5s",
    "success_before_passing": 3,
    "failures_before_critical": 2
  }
}
```

**关键参数说明：**
- `http`：检查的URL地址
- `method`：HTTP方法（GET、POST等），默认为GET
- `header`：自定义请求头
- `tls_skip_verify`：是否跳过TLS证书验证
- `interval`：检查间隔时间
- `timeout`：请求超时时间
- `success_before_passing`：连续成功次数后才标记为健康
- `failures_before_critical`：连续失败次数后标记为严重

### 2.2 TCP健康检查
TCP健康检查通过建立TCP连接来验证服务是否可访问。

**配置示例：**
```json
{
  "check": {
    "id": "redis-tcp-check",
    "name": "Redis TCP Connectivity",
    "tcp": "localhost:6379",
    "interval": "30s",
    "timeout": "10s",
    "deregister_critical_service_after": "5m"
  }
}
```

**关键参数说明：**
- `tcp`：主机名和端口号
- `deregister_critical_service_after`：服务处于严重状态多长时间后自动注销

### 2.3 gRPC健康检查
gRPC健康检查专门用于gRPC服务，使用gRPC的健康检查协议。

**配置示例：**
```json
{
  "check": {
    "id": "grpc-service-check",
    "name": "gRPC Service Health",
    "grpc": "localhost:9090",
    "grpc_use_tls": true,
    "interval": "15s",
    "timeout": "5s"
  }
}
```

**关键参数说明：**
- `grpc`：gRPC服务的地址和端口
- `grpc_use_tls`：是否使用TLS连接
- `grpc_service`：可选，指定检查的特定gRPC服务名称

### 2.4 Script健康检查
Script健康检查通过执行自定义脚本来判断服务状态。

**配置示例：**
```json
{
  "check": {
    "id": "custom-script-check",
    "name": "Custom Script Check",
    "args": ["/usr/local/bin/check_service.sh", "--timeout", "5"],
    "interval": "60s",
    "timeout": "30s"
  }
}
```

**注意：**
- 脚本必须以退出码表示状态：0=通过，1=警告，其他=严重
- 脚本应在超时时间内完成执行
- 考虑使用Docker容器时，确保脚本在容器内可用

## 3. 健康状态与处理

### 3.1 健康状态等级
- **passing**：服务健康，可正常接收流量
- **warning**：服务有潜在问题，但仍可处理请求
- **critical**：服务不健康，不应接收流量

### 3.2 状态转换逻辑
```
启动 → 检查失败 → critical → 检查成功 → passing
                          ↓
                    连续失败超阈值
                          ↓
               deregister_critical_service_after
```

## 4. 最佳实践

### 4.1 检查频率与超时设置
- 生产环境建议：HTTP检查间隔10-30秒，超时3-5秒
- TCP检查可适当延长间隔（30-60秒）
- 避免过于频繁的检查导致服务负载过高

### 4.2 检查端点设计
```go
// HTTP健康检查端点示例
func healthHandler(w http.ResponseWriter, r *http.Request) {
    // 检查数据库连接
    if err := db.Ping(); err != nil {
        w.WriteHeader(http.StatusServiceUnavailable)
        json.NewEncoder(w).Encode(map[string]string{
            "status": "unhealthy",
            "error": err.Error()
        })
        return
    }
    
    // 检查缓存连接
    if err := cache.Ping(); err != nil {
        w.WriteHeader(http.StatusServiceUnavailable)
        json.NewEncoder(w).Encode(map[string]string{
            "status": "degraded",
            "error": err.Error()
        })
        return
    }
    
    w.WriteHeader(http.StatusOK)
    json.NewEncoder(w).Encode(map[string]string{
        "status": "healthy"
    })
}
```

### 4.3 多级健康检查策略
```json
{
  "checks": [
    {
      "id": "quick-liveness",
      "name": "Liveness Check",
      "http": "http://localhost:8080/health/live",
      "interval": "5s",
      "timeout": "2s"
    },
    {
      "id": "detailed-readiness",
      "name": "Readiness Check",
      "http": "http://localhost:8080/health/ready",
      "interval": "30s",
      "timeout": "10s"
    }
  ]
}
```

## 5. 高级配置

### 5.1 检查模板（Service Mesh）
```hcl
check {
  id       = "service-mesh-http"
  name     = "HTTP check on port 8080"
  http     = "http://{{.ServiceAddress}}:{{.ServicePort}}/health"
  interval = "10s"
  timeout  = "5s"
  
  # 使用服务标签
  header {
    x-consul-token = ["{{key "service/token"}}"]
  }
}
```

### 5.2 权重检查
```json
{
  "check": {
    "id": "weighted-check",
    "name": "Weighted Health Check",
    "http": "http://localhost:8080/health",
    "interval": "10s",
    "success_before_passing": 2,
    "failures_before_critical": 1,
    "weight": 50
  }
}
```

## 6. 监控与告警

### 6.1 集成Prometheus监控
```yaml
# Prometheus配置示例
scrape_configs:
  - job_name: 'consul-health-checks'
    consul_sd_configs:
      - server: 'consul-server:8500'
    metrics_path: /v1/agent/metrics
    params:
      format: ['prometheus']
```

### 6.2 告警规则示例
```yaml
groups:
  - name: consul-health
    rules:
      - alert: ServiceUnhealthy
        expr: consul_health_check_status{status="critical"} == 1
        for: 2m
        annotations:
          summary: "服务 {{ $labels.service }} 健康检查失败"
```

## 7. 故障排查

### 7.1 常见问题
1. **检查失败但服务正常**
   - 检查网络连通性
   - 验证防火墙规则
   - 检查Consul agent日志

2. **检查超时**
   - 调整timeout参数
   - 检查服务响应时间
   - 考虑网络延迟

3. **状态抖动**
   - 增加success_before_passing值
   - 调整检查间隔
   - 实现健康检查端点缓存

### 7.2 调试命令
```bash
# 查看服务健康状态
consul catalog services
consul health check --service <service-name>

# 查看agent状态
consul members
consul monitor

# 强制重新运行检查
consul debug -interval=-1s -server-id=<id>
```

## 8. 总结

Consul的健康检查系统提供了灵活的多协议支持，能够适应各种服务类型的监控需求。正确的健康检查配置是构建 resilient 微服务架构的基础，建议根据服务特性和业务需求，选择合适的检查类型和参数配置，并建立完善的监控告警机制。

**配置原则：**
- 根据服务SLA要求确定检查频率
- 设置合理的超时和重试机制
- 实现分级的健康检查（存活vs就绪）
- 定期评审和优化检查配置