# Envoy HTTP过滤器链执行顺序技术文档

## 1. 概述

Envoy HTTP过滤器链是Envoy代理的核心功能之一，它允许开发者在请求/响应处理流水线中插入自定义的处理逻辑。本文档详细说明HTTP过滤器链的执行顺序、工作原理及最佳实践。

## 2. 过滤器链基础概念

### 2.1 过滤器链组成
- **L4/L7过滤器**：HTTP过滤器属于L7过滤器
- **编码器过滤器**：处理请求和响应
- **解码器过滤器**：主要处理请求
- **双向过滤器**：同时处理请求和响应

### 2.2 过滤器类型
```cpp
enum class FilterType {
  Decoder,  // 请求处理
  Encoder,  // 响应处理
  Both      // 双向处理
};
```

## 3. 过滤器链执行顺序

### 3.1 整体执行流程
```
客户端请求 → 网络层接收 → HTTP连接管理器 → 过滤器链执行 → 上游集群
                                 ↓
客户端响应 ← 网络层发送 ← HTTP连接管理器 ← 过滤器链执行 ← 上游响应
```

### 3.2 请求处理阶段（下行流）

#### 3.2.1 执行顺序
```
1. 接收HTTP请求头
2. 按配置顺序执行Decoder过滤器
   - Router过滤器通常最后执行
3. 接收HTTP请求体（如果存在）
4. 继续执行Decoder过滤器对body的处理
5. 转发到上游
```

#### 3.2.2 典型Decoder过滤器顺序
```
1. 外部授权过滤器 (ext_authz)
2. 速率限制过滤器 (ratelimit)
3. CORS过滤器
4. JWT认证过滤器
5. RBAC过滤器
6. 压缩器过滤器
7. Router过滤器（必须为最后一个）
```

### 3.3 响应处理阶段（上行流）

#### 3.3.1 执行顺序
```
1. 接收上游响应头
2. 按反向顺序执行Encoder过滤器
3. 接收上游响应体（如果存在）
4. 继续执行Encoder过滤器对body的处理
5. 返回给客户端
```

#### 3.3.2 典型Encoder过滤器顺序
```
1. Router过滤器（最先处理响应）
2. 压缩器过滤器
3. 响应头修改过滤器
4. 统计过滤器
```

### 3.4 双向过滤器执行
双向过滤器在两个阶段都会执行：
- 请求阶段：按Decoder顺序执行
- 响应阶段：按Encoder反向顺序执行

## 4. 配置示例

### 4.1 静态配置示例
```yaml
http_filters:
  - name: envoy.filters.http.ext_authz
    typed_config:
      "@type": type.googleapis.com/envoy.extensions.filters.http.ext_authz.v3.ExtAuthz
  - name: envoy.filters.http.ratelimit
    typed_config:
      "@type": type.googleapis.com/envoy.extensions.filters.http.ratelimit.v3.RateLimit
  - name: envoy.filters.http.cors
    typed_config:
      "@type": type.googleapis.com/envoy.extensions.filters.http.cors.v3.Cors
  - name: envoy.filters.http.jwt_authn
    typed_config:
      "@type": type.googleapis.com/envoy.extensions.filters.http.jwt_authn.v3.JwtAuthentication
  - name: envoy.filters.http.router
    typed_config:
      "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router
```

### 4.2 动态配置
支持通过xDS API动态配置过滤器链顺序

## 5. 关键过滤器说明

### 5.1 Router过滤器
- **位置**：必须作为最后一个Decoder过滤器
- **功能**：负责请求路由、重试、超时、负载均衡
- **特殊性**：是唯一能与上游建立连接的过滤器

### 5.2 终止型过滤器
某些过滤器可能终止请求流程：
- **ext_authz**：认证失败返回403
- **ratelimit**：限流返回429
- **rbac**：权限不足返回403

### 5.3 流式处理过滤器
支持流式处理请求/响应体：
- 压缩过滤器
- Buffer过滤器
- Grpc-Web过滤器

## 6. 执行流程图

```
┌─────────────────────────────────────────────────────────────┐
│                    HTTP请求到达                             │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                   解码器过滤器链执行                         │
│  ext_authz → ratelimit → cors → jwt_authn → ... → router    │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                    向上游发送请求                            │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                   接收上游响应                              │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                   编码器过滤器链执行                         │
│  router → ... → jwt_authn → cors → ratelimit → ext_authz    │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                    向客户端发送响应                          │
└─────────────────────────────────────────────────────────────┘
```

## 7. 最佳实践

### 7.1 过滤器顺序建议
1. **安全检查优先**：认证、授权、限流等安全过滤器应放在前面
2. **路由最后**：Router过滤器必须是最后一个Decoder过滤器
3. **性能考虑**：高频次操作的过滤器尽量靠前，减少无效处理

### 7.2 配置建议
```yaml
# 推荐的过滤器顺序
http_filters:
  # 1. 安全相关
  - name: envoy.filters.http.ext_authz      # 外部认证
  - name: envoy.filters.http.ratelimit      # 限流
  - name: envoy.filters.http.rbac           # 基于角色的访问控制
  
  # 2. 协议处理
  - name: envoy.filters.http.grpc_web       # gRPC-Web转换
  - name: envoy.filters.http.cors           # CORS处理
  
  # 3. 数据处理
  - name: envoy.filters.http.buffer         # 缓冲区管理
  - name: envoy.filters.http.compressor     # 压缩
  
  # 4. 监控与跟踪
  - name: envoy.filters.http.dynamo         # DynamoDB统计
  - name: envoy.filters.http.tap            # 流量捕获
  
  # 5. 路由（必须最后）
  - name: envoy.filters.http.router
```

### 7.3 调试技巧
1. 使用`envoy.http_conn_manager`的详细日志
2. 通过Tap过滤器捕获流量
3. 使用管理接口查看过滤器状态

## 8. 常见问题

### 8.1 过滤器执行中断
当过滤器返回`StopIteration`时，后续过滤器暂停执行，直到调用`continueDecoding()`或`continueEncoding()`

### 8.2 过滤器依赖关系
某些过滤器有隐式依赖关系，需要确保正确顺序：
- JWT认证在RBAC之前
- 压缩过滤器在缓存过滤器之后

### 8.3 性能影响
过滤器链长度直接影响性能，建议：
- 仅启用必要的过滤器
- 避免在过滤器中执行耗时操作
- 考虑使用WASM过滤器实现复杂逻辑

## 9. 扩展与自定义

### 9.1 自定义过滤器开发
开发自定义过滤器时需注意：
- 明确定义过滤器类型（Decoder/Encoder/Both）
- 正确处理流式数据
- 实现适当的生命周期管理

### 9.2 WASM过滤器
Envoy支持WASM过滤器，提供更灵活的扩展能力：
- 支持多语言开发
- 支持热更新
- 更好的隔离性

## 10. 参考资源

- [Envoy官方文档 - HTTP过滤器](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/http_filters)
- [Envoy过滤器仓库](https://github.com/envoyproxy/envoy/tree/main/source/extensions/filters/http)
- [xDS API规范](https://github.com/envoyproxy/data-plane-api)

---

**文档版本**: 1.0  
**最后更新**: 2024年1月  
**适用Envoy版本**: v1.20+