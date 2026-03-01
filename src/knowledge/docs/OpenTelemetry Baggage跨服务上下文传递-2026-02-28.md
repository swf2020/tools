# OpenTelemetry Baggage 跨服务上下文传递技术文档

## 1. 概述

### 1.1 什么是 Baggage？
Baggage 是 OpenTelemetry 中用于在分布式系统的服务之间传递键值对数据的机制。它允许在请求的整个生命周期中携带任意上下文信息，这些信息会随着请求在各个服务间传播。

### 1.2 Baggage 与 Trace Context 的关系
- **Trace Context**：用于维护分布式追踪的上下文（Trace ID, Span ID, Trace Flags等）
- **Baggage**：用于传递用户自定义的业务上下文数据
- 两者相互独立但可以协同工作，共同构成完整的分布式上下文传递体系

## 2. 核心概念

### 2.1 Baggage 项 (Baggage Items)
```javascript
// Baggage 项示例
"user-id": "12345",
"tenant": "enterprise-a",
"feature-flags": "new-ui,beta-feature",
"correlation-id": "req-789abc"
```

### 2.2 Baggage 元数据 (Metadata)
每个 Baggage 项可以包含元数据：
- 值 (Value)：字符串类型的值
- 属性 (Properties)：可选的键值对，如版本、来源等

## 3. 工作原理

### 3.1 Baggage 传播流程
```
Service A → [注入Baggage] → HTTP/gRPC请求 → Service B → [读取Baggage] → 处理逻辑
      ↑                                                              ↓
[设置Baggage] ←--- [可选：修改Baggage] ←--- 继续传播到 Service C
```

### 3.2 传播协议支持
- **W3C Baggage 协议**：标准化的 HTTP 头部格式
- **自定义传播器**：支持 gRPC 元数据、消息队列头等

## 4. 实现与使用

### 4.1 基本 API 操作

#### Java 示例
```java
import io.opentelemetry.api.baggage.Baggage;
import io.opentelemetry.api.baggage.BaggageBuilder;

// 创建 Baggage
Baggage baggage = Baggage.builder()
    .put("user-id", "user-123")
    .put("tenant", "premium", 
         BaggageEntryMetadata.create("version=1;source=auth"))
    .build();

// 获取当前上下文中的 Baggage
Baggage currentBaggage = Baggage.current();

// 读取值
String userId = currentBaggage.getEntryValue("user-id");

// 在指定范围内使用 Baggage
try (Scope scope = baggage.makeCurrent()) {
    // 在此范围内，Baggage.current() 返回上面创建的 baggage
    // 执行相关操作
}
```

#### Python 示例
```python
from opentelemetry import baggage
from opentelemetry.context import attach, detach

# 设置 Baggage
context = baggage.set_baggage("user-id", "user-123")
context = baggage.set_baggage("tenant", "premium", context=context)

# 获取 Baggage
user_id = baggage.get_baggage("user-id", context=context)

# 获取所有 Baggage
all_baggage = baggage.get_all(context=context)
```

### 4.2 跨服务传播示例

#### HTTP 服务间传播（Node.js）
```javascript
// 服务A：发送请求
const { baggage, propagation } = require('@opentelemetry/api');
const axios = require('axios');

// 设置 Baggage
const context = baggage.setBaggage(
  baggage.context.active(),
  'user-id',
  { value: '12345' }
);

// 注入到 HTTP 头部
const headers = {};
propagation.inject(context, headers);

// 发送请求
axios.get('http://service-b/api/data', { headers });

// 服务B：接收请求
app.get('/api/data', (req, res) => {
  // 提取 Baggage
  const context = propagation.extract(context.active(), req.headers);
  const userBaggage = baggage.getBaggage(context);
  const userId = userBaggage.getEntry('user-id')?.value;
  
  // 使用 Baggage 数据
  console.log(`Processing request for user: ${userId}`);
});
```

#### gRPC 服务间传播（Go）
```go
// 客户端
import (
    "go.opentelemetry.io/otel/baggage"
    "google.golang.org/grpc/metadata"
)

// 创建 Baggage
bag, _ := baggage.New(
    baggage.Member{Key: "user-id", Value: "12345"},
    baggage.Member{Key: "tenant", Value: "enterprise"},
)

// 注入到上下文
ctx := baggage.ContextWithBaggage(context.Background(), bag)

// 注入到 gRPC 元数据
md := metadata.New(nil)
propagator.Inject(ctx, metadata.NewCarrier(md))

// 服务端
func (s *Server) Process(ctx context.Context, req *Request) (*Response, error) {
    // 提取 Baggage
    bag := baggage.FromContext(ctx)
    
    // 读取值
    member := bag.Member("user-id")
    if member.Key() != "" {
        userID := member.Value()
        // 使用 userID
    }
}
```

## 5. 配置与传播器

### 5.1 配置 Baggage 传播
```java
// 配置 W3C Baggage 传播器
OpenTelemetrySdk.builder()
    .setPropagators(
        ContextPropagators.create(
            TextMapPropagator.composite(
                W3CTraceContextPropagator.getInstance(),
                W3CBaggagePropagator.getInstance()
            )
        )
    )
    .build();
```

### 5.2 自定义传播器
```python
from opentelemetry import propagate
from opentelemetry.propagators.textmap import CarrierT

class CustomBaggagePropagator:
    """自定义 Baggage 传播器示例"""
    
    def extract(self, carrier: CarrierT, context=None):
        # 从自定义载体提取 Baggage
        pass
    
    def inject(self, carrier: CarrierT, context=None):
        # 将 Baggage 注入自定义载体
        pass
```

## 6. 实际应用场景

### 6.1 分布式追踪增强
```java
// 在 Span 中记录 Baggage 信息
Span currentSpan = Span.current();
Baggage currentBaggage = Baggage.current();

currentBaggage.forEach((key, baggageEntry) -> {
    currentSpan.setAttribute("baggage." + key, baggageEntry.getValue());
});
```

### 6.2 功能开关与实验
```python
# 基于 Baggage 的功能开关
def is_feature_enabled(feature_name, context):
    flags = baggage.get_baggage("feature-flags", context=context)
    if flags:
        return feature_name in flags.split(',')
    return False

# 使用
if is_feature_enabled("new-checkout", context):
    # 启用新功能
    process_new_checkout()
else:
    # 使用旧逻辑
    process_legacy_checkout()
```

### 6.3 多租户上下文传递
```go
// 中间件：从 Baggage 提取租户信息
func TenantMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        ctx := r.Context()
        bag := baggage.FromContext(ctx)
        
        // 获取租户信息
        if member := bag.Member("tenant"); member.Key() != "" {
            tenantID := member.Value()
            // 设置租户上下文
            ctx = context.WithValue(ctx, "tenantID", tenantID)
        }
        
        next.ServeHTTP(w, r.WithContext(ctx))
    })
}
```

## 7. 最佳实践

### 7.1 数据大小限制
- 建议单个 Baggage 项值不超过 4096 字节
- 总 Baggage 大小应考虑传输协议限制（如 HTTP 头部大小限制）

### 7.2 安全考虑
```java
// 敏感数据不应放在 Baggage 中
// 错误示例
Baggage.builder()
    .put("auth-token", sensitiveToken)  // 不安全！
    .build();

// 正确做法：传递引用而非敏感数据本身
Baggage.builder()
    .put("session-id", sessionId)  // 仅传递标识符
    .build();
```

### 7.3 性能优化
```python
# 懒加载模式：只在需要时解析复杂 Baggage
def get_user_preferences(context):
    """从 Baggage 获取用户偏好（按需解析）"""
    prefs_json = baggage.get_baggage("user-preferences", context=context)
    if prefs_json:
        # 只有需要时才解析 JSON
        return json.loads(prefs_json)
    return {}
```

## 8. 常见问题与调试

### 8.1 Baggage 丢失问题排查
1. **检查传播器配置**：确保发送端和接收端使用相同的传播器
2. **验证头部名称**：确认使用的 HTTP 头部名称正确（默认：`baggage`）
3. **检查中间件处理**：确保代理或网关不会删除 Baggage 头部

### 8.2 调试工具
```javascript
// 调试函数：打印所有 Baggage
function debugBaggage(context) {
  const bag = baggage.getBaggage(context);
  if (bag) {
    bag.getAllEntries().forEach(([key, entry]) => {
      console.log(`Baggage: ${key}=${entry.value}`);
    });
  }
}
```

## 9. 与其他技术的集成

### 9.1 与 Spring Cloud Sleuth 集成
```yaml
# application.yml
opentelemetry:
  baggage:
    enabled: true
    correlation:
      enabled: true
      fields:
        - userId
        - tenantId
```

### 9.2 与消息队列集成
```java
// RabbitMQ 示例
public void sendMessage(String message) {
    // 获取当前 Baggage
    Baggage currentBaggage = Baggage.current();
    
    // 创建消息属性
    AMQP.BasicProperties.Builder propsBuilder = new AMQP.BasicProperties.Builder();
    
    // 将 Baggage 注入消息头
    Map<String, Object> headers = new HashMap<>();
    TextMapSetter<Map<String, Object>> setter = (carrier, key, value) -> {
        carrier.put(key, value);
    };
    
    propagator.inject(Context.current().with(currentBaggage), headers, setter);
    
    // 发送消息
    channel.basicPublish(exchange, routingKey, 
        propsBuilder.headers(headers).build(),
        message.getBytes());
}
```

## 10. 总结

OpenTelemetry Baggage 提供了灵活、标准的跨服务上下文传递机制。通过合理使用 Baggage，可以：
1. 增强分布式追踪的可观察性
2. 实现基于上下文的功能控制
3. 传递业务相关的上下文信息
4. 保持服务间的关注点分离

在实际应用中，应注意数据大小、安全性，并遵循最小必要原则传递数据，以确保系统的性能和安全性。

---

**文档版本**：1.0  
**最后更新**：2024年  
**适用版本**：OpenTelemetry 1.0+