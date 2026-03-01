# HTTP/2 服务端推送（Server Push）技术文档

## 1. 概述

### 1.1 什么是服务端推送
HTTP/2 服务端推送是一种服务器主动向客户端推送资源的机制，允许服务器在客户端明确请求某个资源之前，预测并提前发送相关资源到客户端缓存中。

### 1.2 解决的问题
传统 HTTP/1.x 的请求-响应模式中，客户端必须解析 HTML 文档后，才能发现所需的子资源（CSS、JavaScript、图片等）并逐个发起请求。这种串行过程导致页面加载延迟。服务端推送旨在减少这些往返时间（RTT），提升页面加载性能。

## 2. 核心概念

### 2.1 推送流（Push Stream）
- 服务器通过新建的推送流发送承诺资源
- 每个推送流与原始请求流关联，共享同一个连接
- 推送流具有独立的流ID（偶数编号）

### 2.2 推送承诺（Push Promise）
- 服务器发送 PUSH_PROMISE 帧，声明将要推送的资源
- 包含承诺资源的请求头信息
- 客户端可选择接受或拒绝推送

### 2.3 缓存相关
- 推送的资源存储在客户端缓存中
- 遵循常规的HTTP缓存机制
- 可避免重复传输已缓存的资源

## 3. 技术实现

### 3.1 协议层面
```http
客户端请求: GET /index.html
服务器响应: 
1. 发送 index.html 的响应头
2. 发送 PUSH_PROMISE 帧（承诺 style.css）
3. 发送 index.html 内容
4. 通过新流发送 style.css 的响应头和内容
```

### 3.2 推送条件
服务器在以下情况可触发推送：
1. 接收到对主资源的请求
2. 识别出该主资源依赖的其他资源
3. 确认客户端尚未缓存这些资源
4. 推送的优先级合理

## 4. 实现示例

### 4.1 基于Link头的推送（HTTP/2标准方式）
```http
HTTP/2 200 OK
content-type: text/html
link: </style.css>; rel=preload; as=style

[HTML内容]
```

服务器检测到Link头后，自动推送相关资源。

### 4.2 Node.js实现示例
```javascript
const http2 = require('http2');
const fs = require('fs');

const server = http2.createSecureServer({
  key: fs.readFileSync('server.key'),
  cert: fs.readFileSync('server.crt')
});

server.on('stream', (stream, headers) => {
  if (headers[':path'] === '/') {
    // 推送CSS文件
    stream.pushStream({ ':path': '/style.css' }, (err, pushStream) => {
      pushStream.respondWithFile('style.css', {
        'content-type': 'text/css'
      });
    });
    
    // 推送JS文件
    stream.pushStream({ ':path': '/app.js' }, (err, pushStream) => {
      pushStream.respondWithFile('app.js', {
        'content-type': 'application/javascript'
      });
    });
    
    // 响应主请求
    stream.respondWithFile('index.html', {
      'content-type': 'text/html'
    });
  }
});
```

## 5. 缓存控制策略

### 5.1 智能推送
- 使用缓存摘要（Cache Digest）避免推送已缓存资源
- 通过客户端发送的缓存摘要判断资源状态
- 实现条件性推送

### 5.2 推送限制
```http
客户端可设置 SETTINGS 帧参数：
SETTINGS_ENABLE_PUSH (0x2): 1 启用 / 0 禁用
SETTINGS_MAX_CONCURRENT_STREAMS: 限制并发推送数
```

## 6. 优势与挑战

### 6.1 优势
1. **减少延迟**：消除额外RTT，特别对高延迟网络显著
2. **并行处理**：资源并行推送，充分利用带宽
3. **优先级控制**：可与流优先级配合，优化资源加载顺序
4. **网络友好**：减少连接数和请求数

### 6.2 挑战与注意事项
1. **过度推送风险**：推送不必要资源浪费带宽
2. **缓存失效问题**：推送已缓存的资源造成浪费
3. **带宽竞争**：可能影响关键资源的加载
4. **实现复杂性**：需要服务器智能预测资源依赖

## 7. 最佳实践

### 7.1 适用场景
- 明确静态资源依赖关系的页面
- 高延迟网络环境
- 首次访问用户（冷缓存）
- 关键渲染路径资源

### 7.2 不建议场景
- 移动网络（带宽敏感）
- 已存在有效缓存的用户
- 动态或个性化资源
- 大文件资源（可能阻塞关键资源）

### 7.3 优化策略
1. **选择性推送**：仅推送关键路径资源
2. **使用缓存摘要**：避免重复推送
3. **监控推送效果**：分析实际性能提升
4. **动态调整**：根据网络条件调整推送策略
5. **与预加载结合**：作为预加载的补充机制

## 8. 调试与监控

### 8.1 Chrome开发者工具
- Network面板查看"Initiator"列为"Push"的资源
- 瀑布流显示推送时序
- 检查推送资源大小和节省的RTT

### 8.2 性能指标
```javascript
// 检测推送使用情况
performance.getEntriesByType('resource')
  .filter(r => r.initiatorType === 'http2-push');
```

## 9. 与其他技术对比

| 特性 | Server Push | HTTP Preload | Browser Prefetch |
|------|-------------|--------------|------------------|
| 主动性 | 服务器主动 | 服务器建议 | 浏览器启发式 |
| 缓存位置 | HTTP缓存 | HTTP缓存 | 独立缓存 |
| 优先级 | 可配置 | 高优先级 | 最低优先级 |
| 控制方 | 服务器 | 服务器 | 浏览器 |

## 10. 未来展望

HTTP/3对推送机制进行了改进：
- 更早的推送承诺（0-RTT场景）
- 改进的取消机制
- 更好的流量控制

## 11. 总结

HTTP/2服务端推送是一个强大的性能优化工具，但需要谨慎使用。正确的实施应该：
1. 基于实际用户数据分析资源依赖
2. 配合缓存策略避免浪费
3. 持续监控和调整推送策略
4. 考虑与HTTP/3的兼容性

推送不是万能的，而应该是Web性能优化工具箱中的一个选择性工具，与其他技术（如预加载、预连接、智能缓存）配合使用，才能达到最佳效果。

---
*文档版本：1.1*
*最后更新：2024年1月*
*适用协议：HTTP/2 RFC 7540*