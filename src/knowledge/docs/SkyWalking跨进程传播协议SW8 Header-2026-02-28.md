# SkyWalking 跨进程传播协议 (SW8 Header) 技术文档

## 1. 概述

SkyWalking 跨进程传播协议（通常称为 SW8 Header）是 Apache SkyWalking APM 系统用于实现分布式链路追踪的核心上下文传播机制。该协议通过在服务间调用时传递特定的 HTTP 头部信息，将离散的服务调用串联成完整的分布式事务链路。

## 2. 协议设计目标

### 2.1 主要目标
- **上下文传播**：在微服务架构中跨进程传递追踪上下文
- **低侵入性**：尽量减少对业务代码的影响
- **高性能**：头部信息精简，序列化/反序列化开销小
- **可扩展性**：支持自定义扩展字段

### 2.2 协议特点
- 基于 HTTP Header 的标准传播方式
- 支持文本格式的序列化
- 向后兼容的设计
- 支持多种语言和框架

## 3. SW8 Header 格式详解

### 3.1 核心头部字段

```
sw8: {Sample}-{TraceId}-{ParentSegmentId}-{ParentSpanId}-{ParentService}-{ParentServiceInstance}-{ParentEndpoint}-{Peer}-{NetworkAddress}
```

### 3.2 字段说明

| 字段序号 | 字段名称 | 描述 | 示例 |
|---------|---------|------|------|
| 1 | Sample | 采样标志位 | 1 (采样) / 0 (不采样) |
| 2 | TraceId | 全局追踪ID | 全局唯一的UUID格式 |
| 3 | ParentSegmentId | 父段ID | 父服务段的唯一标识 |
| 4 | ParentSpanId | 父跨度ID | 父跨度在段内的序号 |
| 5 | ParentService | 父服务名称 | service-a |
| 6 | ParentServiceInstance | 父服务实例 | service-a-instance-1 |
| 7 | ParentEndpoint | 父服务端点 | /api/v1/users |
| 8 | Peer | 对端地址 | 下游服务的网络标识 |
| 9 | NetworkAddress | 网络地址 | 目标服务的实际地址 |

### 3.3 子字段说明

**8.1 SW8-Correlation-Context**
```
sw8-correlation: key1=value1,key2=value2
```
用于传递业务相关的上下文信息，支持自定义键值对。

**8.2 SW8-Extension**
```
sw8-x: custom_data
```
扩展字段，用于传递特定于应用程序的额外信息。

## 4. 协议工作流程

### 4.1 传播过程
```
客户端 → [SW8 Header] → 服务端
   ↓                         ↓
创建Span                  接收Header
   ↓                         ↓
注入Header                提取上下文
   ↓                         ↓
发送请求                  继续传播
```

### 4.2 生命周期管理
1. **起始阶段**：根服务创建初始追踪上下文
2. **传播阶段**：通过SW8 Header在服务间传递
3. **接收阶段**：下游服务解析Header并创建本地上下文
4. **上报阶段**：各服务将追踪数据上报至SkyWalking后端

## 5. 具体实现示例

### 5.1 HTTP 请求示例
```http
GET /api/v1/orders HTTP/1.1
Host: order-service:8080
sw8: 1-1234567890abcdef1234567890abcdef-9876543210-fedcba-1-service-a-service-a-instance-1-/api/v1/users-order-service:8080-order-service:8080
sw8-correlation: user_id=12345,session_id=abcde
sw8-x: custom_info=some_value
```

### 5.2 代码实现片段

**Java Agent 自动注入**：
```java
// SkyWalking Agent 自动处理SW8 Header注入
// 无需业务代码手动干预
```

**手动注入示例**：
```java
HttpURLConnection connection = (HttpURLConnection) url.openConnection();
connection.setRequestProperty("sw8", 
    "1-" + context.getTraceId() + "-" +
    context.getParentSegmentId() + "-" +
    context.getParentSpanId() + "-" +
    // ... 其他字段
);
```

## 6. 协议扩展与自定义

### 6.1 自定义扩展字段
```java
// 通过SkyWalking API 添加自定义上下文
ContextManager.getRuntimeContext().put("custom_key", "custom_value");
```

### 6.2 采样率控制
通过Sample字段控制是否采样：
- `1`：采样并上报
- `0`：仅传播不采样

## 7. 最佳实践

### 7.1 配置建议
```yaml
# agent.config
agent.sample_n_per_3_secs: -1  # 全部采样
agent.force_sample_error: true # 错误强制采样
```

### 7.2 性能优化
1. 合理设置采样率，避免全量采样对性能的影响
2. 控制扩展字段的数量和大小
3. 使用HTTP/2减少头部传输开销

### 7.3 安全考虑
1. SW8 Header可能暴露内部架构信息，建议在网关层过滤
2. 避免在扩展字段中传递敏感数据
3. 实施适当的访问控制和监控

## 8. 常见问题与排查

### 8.1 链路断开
**可能原因**：
- SW8 Header被中间件过滤
- 采样标志位设置为0
- 协议版本不兼容

**解决方案**：
1. 检查代理配置
2. 验证网络设备（如负载均衡器）是否保留了自定义Header
3. 确认各服务使用的SkyWalking版本兼容性

### 8.2 性能问题
**优化建议**：
1. 调整采样率
2. 减少扩展字段使用
3. 使用更高效的数据序列化方式

## 9. 协议演进

| 版本 | 主要改进 | 兼容性 |
|------|---------|--------|
| v1.0 | 基础协议定义 | - |
| v2.0 | 支持扩展字段 | 向后兼容v1.0 |
| v3.0 | 优化序列化格式 | 向后兼容v2.0 |

## 10. 总结

SW8 Header 协议作为 SkyWalking 分布式追踪的核心传播机制，通过轻量级的HTTP头部设计，实现了高效的上下文传播。该协议在保证功能完整性的同时，最大限度地减少了对业务系统的侵入性，是微服务架构下链路追踪的重要基础设施。

### 核心优势：
1. **标准化**：基于HTTP标准，通用性强
2. **灵活性**：支持扩展和自定义
3. **高性能**：设计简洁，开销极小
4. **生态完善**：支持多种语言和框架

### 使用建议：
- 在生产环境中合理配置采样率
- 遵循最小化原则使用扩展字段
- 定期监控和审计追踪数据的完整性

---

*文档版本：v1.2*
*最后更新：2024年*
*适用SkyWalking版本：8.0.0+*