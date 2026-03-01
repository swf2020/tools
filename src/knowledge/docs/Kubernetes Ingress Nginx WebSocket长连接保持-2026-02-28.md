# Kubernetes Ingress Nginx WebSocket 长连接保持技术文档

## 1. 概述

### 1.1 文档目的
本文档旨在为使用 Kubernetes Ingress Nginx 的用户提供配置和优化 WebSocket 长连接的完整指南，确保 WebSocket 连接在 Ingress 层能够稳定、高效地工作。

### 1.2 WebSocket 协议简介
WebSocket 是一种在单个 TCP 连接上进行全双工通信的协议，与传统的 HTTP 请求-响应模式不同，它支持服务器主动向客户端推送数据，适用于实时应用程序。

## 2. WebSocket 在 Ingress Nginx 中的工作原理

### 2.1 连接升级机制
WebSocket 连接通过 HTTP 升级机制建立：
1. 客户端发送包含 `Upgrade: websocket` 和 `Connection: Upgrade` 头的 HTTP 请求
2. Ingress Nginx 识别这些头并将请求代理到后端服务
3. 建立持久化的双向通信通道

### 2.2 Ingress Nginx 代理行为
默认情况下，Nginx 会：
- 为 HTTP 连接设置较短的超时时间
- 可能中断长时间空闲的连接
- 对连接数有限制

## 3. 核心配置参数

### 3.1 Ingress Annotation 配置

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: websocket-ingress
  annotations:
    # 启用 WebSocket 支持
    nginx.ingress.kubernetes.io/websocket-services: "websocket-service"
    
    # 连接超时设置
    nginx.ingress.kubernetes.io/proxy-connect-timeout: "3600"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
    
    # 缓冲区配置
    nginx.ingress.kubernetes.io/proxy-buffer-size: "16k"
    nginx.ingress.kubernetes.io/proxy-buffers: "4 32k"
    
    # 保持连接
    nginx.ingress.kubernetes.io/upstream-hash-by: "$remote_addr"
    nginx.ingress.kubernetes.io/affinity: "cookie"
    nginx.ingress.kubernetes.io/session-cookie-name: "route"
    nginx.ingress.kubernetes.io/session-cookie-expires: "172800"
    nginx.ingress.kubernetes.io/session-cookie-max-age: "172800"
    
    # 禁用请求缓冲
    nginx.ingress.kubernetes.io/proxy-request-buffering: "off"
    
    # 启用 HTTP/1.1 保持连接
    nginx.ingress.kubernetes.io/proxy-http-version: "1.1"
    nginx.ingress.kubernetes.io/proxy-set-headers: |
      Upgrade $http_upgrade
      Connection "upgrade"
spec:
  ingressClassName: nginx
  rules:
  - host: websocket.example.com
    http:
      paths:
      - path: /ws
        pathType: Prefix
        backend:
          service:
            name: websocket-service
            port:
              number: 80
```

### 3.2 ConfigMap 全局配置

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: nginx-configuration
  namespace: ingress-nginx
data:
  # WebSocket 超时设置
  proxy-read-timeout: "3600"
  proxy-send-timeout: "3600"
  
  # 保持活动连接
  keep-alive: "75"
  keep-alive-requests: "100"
  
  # 上游服务器配置
  upstream-keepalive-connections: "100"
  upstream-keepalive-timeout: "3600"
  upstream-keepalive-requests: "100"
  
  # 大型客户端头缓冲区
  large-client-header-buffers: "4 32k"
  
  # 禁用代理缓冲
  proxy-buffering: "off"
  proxy-buffer-size: "16k"
  
  # WebSocket 特定配置
  map-hash-bucket-size: "128"
```

## 4. 详细配置说明

### 4.1 超时配置详解

#### 4.1.1 关键超时参数
```
proxy-connect-timeout: 后端连接建立超时（默认60s）
proxy-read-timeout: 从后端读取响应超时（默认60s）
proxy-send-timeout: 向后端发送请求超时（默认60s）
```

#### 4.1.2 WebSocket 推荐值
```yaml
nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"  # 1小时
nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"  # 1小时
nginx.ingress.kubernetes.io/proxy-connect-timeout: "75" # 快速失败
```

### 4.2 负载均衡和会话保持

#### 4.2.1 基于 IP 的会话保持
```yaml
nginx.ingress.kubernetes.io/upstream-hash-by: "$remote_addr"
```

#### 4.2.2 Cookie 会话保持
```yaml
nginx.ingress.kubernetes.io/affinity: "cookie"
nginx.ingress.kubernetes.io/session-cookie-name: "websocket_route"
nginx.ingress.kubernetes.io/session-cookie-expires: "172800"
nginx.ingress.kubernetes.io/session-cookie-max-age: "172800"
```

### 4.3 缓冲区优化

```yaml
# 禁用请求缓冲，立即转发 WebSocket 数据
nginx.ingress.kubernetes.io/proxy-request-buffering: "off"

# 适当增加缓冲区大小
nginx.ingress.kubernetes.io/proxy-buffer-size: "32k"
nginx.ingress.kubernetes.io/proxy-buffers: "8 32k"
```

## 5. 完整示例配置

### 5.1 Deployment 配置

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: websocket-server
spec:
  replicas: 3
  selector:
    matchLabels:
      app: websocket-server
  template:
    metadata:
      labels:
        app: websocket-server
    spec:
      containers:
      - name: websocket
        image: your-websocket-server:latest
        ports:
        - containerPort: 8080
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /readyz
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
```

### 5.2 Service 配置

```yaml
apiVersion: v1
kind: Service
metadata:
  name: websocket-service
  annotations:
    # 启用长连接保持
    service.alpha.kubernetes.io/app-protocols: '{"websocket":"HTTP"}'
spec:
  selector:
    app: websocket-server
  ports:
  - name: websocket
    port: 80
    targetPort: 8080
    protocol: TCP
  type: ClusterIP
```

### 5.3 高级 Ingress 配置

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: advanced-websocket-ingress
  annotations:
    nginx.ingress.kubernetes.io/backend-protocol: "HTTP"
    nginx.ingress.kubernetes.io/configuration-snippet: |
      # WebSocket 特定配置
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto $scheme;
      
      # 禁用压缩（某些 WebSocket 实现需要）
      proxy_set_header Accept-Encoding "";
      
      # 心跳检测
      proxy_set_header X-Heartbeat "true";
    
    # 负载均衡策略
    nginx.ingress.kubernetes.io/load-balance: "ip_hash"
    
    # SSL 配置（如果使用 wss://）
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/force-ssl-redirect: "true"
    nginx.ingress.kubernetes.io/ssl-ciphers: "ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES128-GCM-SHA256"
    
    # 限流配置
    nginx.ingress.kubernetes.io/limit-connections: "100"
    nginx.ingress.kubernetes.io/limit-rps: "10"
    
    # 监控和日志
    nginx.ingress.kubernetes.io/enable-access-log: "true"
    nginx.ingress.kubernetes.io/enable-rewrite-log: "false"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - websocket.example.com
    secretName: websocket-tls
  rules:
  - host: websocket.example.com
    http:
      paths:
      - path: /ws
        pathType: ImplementationSpecific
        backend:
          service:
            name: websocket-service
            port:
              number: 80
```

## 6. 监控和诊断

### 6.1 连接状态检查

```bash
# 检查 Ingress Controller 日志
kubectl logs -n ingress-nginx deployment/ingress-nginx-controller --tail=100

# 检查活跃连接
kubectl exec -n ingress-nginx deployment/ingress-nginx-controller -- \
  nginx -T | grep -A5 -B5 "websocket"

# 监控连接数
kubectl exec -n ingress-nginx deployment/ingress-nginx-controller -- \
  netstat -an | grep -i estab | wc -l
```

### 6.2 Prometheus 监控指标

```yaml
# 配置 Prometheus 监控
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: ingress-nginx-websocket
  namespace: monitoring
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: ingress-nginx
  endpoints:
  - port: metrics
    interval: 30s
    params:
      match[]:
      - '{job="ingress-nginx",host="websocket.example.com"}'
```

### 6.3 关键监控指标
- `nginx_ingress_controller_connections`: 当前连接数
- `nginx_ingress_controller_bytes_sent`: 发送字节数
- `nginx_ingress_controller_bytes_received`: 接收字节数
- `nginx_ingress_controller_request_duration_seconds`: 请求持续时间

## 7. 故障排查

### 7.1 常见问题及解决方案

#### 问题1: WebSocket 连接频繁断开
```
原因: 超时时间设置过短
解决: 增加 proxy-read-timeout 和 proxy-send-timeout
```

#### 问题2: 连接无法建立
```
原因: 缺少 Upgrade 和 Connection 头
解决: 确保配置中包含正确的 proxy_set_header
```

#### 问题3: 性能问题
```
原因: 缓冲区配置不当
解决: 调整 proxy-buffer-size 和 proxy-buffers
```

### 7.2 诊断命令

```bash
# 1. 验证配置
kubectl exec -n ingress-nginx deployment/ingress-nginx-controller -- nginx -t

# 2. 检查生效的配置
kubectl exec -n ingress-nginx deployment/ingress-nginx-controller -- \
  cat /etc/nginx/nginx.conf | grep -i websocket

# 3. 实时监控连接
watch -n 1 'kubectl exec -n ingress-nginx deployment/ingress-nginx-controller -- \
  netstat -an | grep -c :80'

# 4. 测试 WebSocket 连接
wscat -c wss://websocket.example.com/ws
```

## 8. 最佳实践

### 8.1 配置建议
1. **适度超时**: 根据业务需求设置，避免过长或过短
2. **启用访问日志**: 便于调试和监控
3. **使用 ConfigMap**: 全局配置通过 ConfigMap 管理
4. **版本兼容性**: 确保 Ingress Nginx 版本支持 WebSocket

### 8.2 安全考虑
1. **使用 WSS**: 生产环境始终使用 WebSocket Secure
2. **限流保护**: 防止 DoS 攻击
3. **认证授权**: 在应用层实现连接验证
4. **网络策略**: 限制不必要的网络访问

### 8.3 性能优化
1. **连接池**: 合理配置上游连接保持
2. **资源限制**: 为 Pod 设置合理的资源请求和限制
3. **水平扩展**: 根据连接数动态调整副本数
4. **区域感知**: 在多区域部署时优化路由

## 9. 版本兼容性

| Ingress Nginx 版本 | WebSocket 支持 | 备注 |
|-------------------|---------------|------|
| 0.x | 基本支持 | 需要手动配置头信息 |
| 1.x | 完整支持 | 内置 WebSocket 代理支持 |
| 2.x+ | 增强支持 | 改进的连接管理和监控 |

## 10. 参考资料
- [Kubernetes Ingress Nginx 官方文档](https://kubernetes.github.io/ingress-nginx/)
- [Nginx WebSocket 代理文档](http://nginx.org/en/docs/http/websocket.html)
- [WebSocket 协议 RFC 6455](https://tools.ietf.org/html/rfc6455)

---

**文档维护**: 技术架构团队  
**最后更新**: $(date)  
**适用版本**: Ingress Nginx ≥ 1.0.0, Kubernetes ≥ 1.19