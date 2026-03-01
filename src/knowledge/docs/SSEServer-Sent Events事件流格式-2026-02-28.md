# SSE（Server-Sent Events）事件流格式技术文档

## 1. 概述

Server-Sent Events（SSE）是一种基于HTTP的单向服务器到客户端通信协议，允许服务器主动向客户端推送实时数据。与WebSocket不同，SSE仅支持服务器向客户端单向通信，但其实现更简单，且天然支持HTTP/HTTPS协议。

## 2. 协议特性

### 2.1 核心特点
- **单向通信**：仅支持服务器到客户端的推送
- **基于HTTP/HTTPS**：无需特殊协议或端口
- **自动重连**：内置连接恢复机制
- **轻量级**：实现简单，浏览器原生支持
- **文本协议**：使用UTF-8编码的文本格式

### 2.2 适用场景
- 实时通知和提醒
- 新闻、股票行情推送
- 社交媒体动态更新
- 服务器日志实时查看
- 进度报告和状态更新

## 3. 事件流格式规范

### 3.1 HTTP响应头要求
```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
Access-Control-Allow-Origin: *  # 如需跨域
```

### 3.2 基本消息格式

每条消息由以下部分组成，以**两个换行符**（`\n\n`）作为消息结束标志：

```
field: value\n
```

### 3.3 核心字段

#### 3.3.1 必需字段：data
```
data: 消息内容\n
```
或跨行数据：
```
data: 第一行\n
data: 第二行\n
```

#### 3.3.2 可选字段

**事件类型（event）**
```
event: 自定义事件名称\n
```
客户端可通过 `addEventListener('自定义事件名称', handler)` 监听

**消息ID（id）**
```
id: 唯一标识符\n
```
用于客户端重连时恢复，浏览器会自动发送 `Last-Event-ID` 头部

**重连时间（retry）**
```
retry: 毫秒数\n
```
指定连接中断后的重连延迟时间（默认3000毫秒）

### 3.4 注释行
以冒号开头的行被视为注释，客户端应忽略：
```
: 这是一条注释\n
```

## 4. 完整消息示例

### 4.1 简单消息
```
data: 服务器时间更新\n
\n
```

### 4.2 包含所有字段的消息
```
id: 12345\n
event: statusUpdate\n
retry: 10000\n
data: {"status": "processing", "progress": 75}\n
\n
```

### 4.3 多行数据消息
```
event: logEntry\n
data: 开始处理请求...\n
data: 验证用户权限...\n
data: 查询数据库记录...\n
\n
```

### 4.4 实际数据流示例
```
: 连接已建立\n
\n
id: 1\n
event: welcome\n
data: 欢迎使用SSE服务\n
\n
id: 2\n
event: update\n
data: {"time": "2024-01-15T10:30:00Z", "value": 42}\n
\n
: 心跳保持连接\n
data: \n
\n
```

## 5. 客户端实现

### 5.1 JavaScript API 基础用法
```javascript
// 创建EventSource连接
const eventSource = new EventSource('/sse-endpoint');

// 监听默认消息
eventSource.onmessage = function(event) {
    console.log('收到消息:', event.data);
    console.log('最后ID:', event.lastEventId);
};

// 监听自定义事件
eventSource.addEventListener('statusUpdate', function(event) {
    const data = JSON.parse(event.data);
    console.log('状态更新:', data);
});

// 错误处理
eventSource.onerror = function(error) {
    console.error('连接错误:', error);
    // 注意：EventSource会自动尝试重连
};

// 关闭连接
// eventSource.close();
```

### 5.2 处理重连机制
```javascript
eventSource.addEventListener('open', function() {
    console.log('连接已建立');
});

eventSource.addEventListener('error', function(event) {
    if (eventSource.readyState === EventSource.CLOSED) {
        console.log('连接已关闭');
    } else {
        console.log('连接错误，将自动重连');
    }
});
```

## 6. 服务器端实现要点

### 6.1 响应格式要求
- 保持连接持久化
- 定期发送空注释作为心跳
- 正确设置响应头
- 正确处理客户端断开

### 6.2 基础Node.js示例
```javascript
const http = require('http');

http.createServer((req, res) => {
    if (req.url === '/events') {
        res.writeHead(200, {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*'
        });

        let id = 0;
        
        // 发送初始消息
        res.write(`id: ${id}\n`);
        res.write(`data: 连接已建立\n\n`);
        
        // 定期发送更新
        const interval = setInterval(() => {
            id++;
            res.write(`id: ${id}\n`);
            res.write(`event: update\n`);
            res.write(`data: ${JSON.stringify({
                time: new Date().toISOString(),
                value: Math.random()
            })}\n\n`);
        }, 2000);

        // 处理客户端断开
        req.on('close', () => {
            clearInterval(interval);
            res.end();
        });
    }
}).listen(3000);
```

## 7. 高级特性与最佳实践

### 7.1 消息分界
- 每条消息必须由两个换行符终止
- 空行（仅包含换行符）会触发空消息事件
- 建议使用显式 `data` 字段而非空消息

### 7.2 性能优化
- 合理设置 `retry` 时间避免频繁重连
- 使用心跳机制保持连接活跃
- 考虑消息批处理减少请求数量

### 7.3 错误处理策略
- 实现指数退避重连策略
- 记录连接状态和错误日志
- 提供降级方案（如轮询）

## 8. 限制与注意事项

### 8.1 浏览器限制
- 最大并发连接数（通常每个域名6个）
- 部分旧浏览器不支持
- 不支持二进制数据，仅限UTF-8文本

### 8.2 安全性考虑
- 同源策略限制（可通过CORS解决）
- 避免敏感信息泄露
- 实现身份验证机制

### 8.3 与其他技术对比
| 特性 | SSE | WebSocket | 长轮询 |
|------|-----|-----------|--------|
| 通信方向 | 单向 | 双向 | 单向 |
| 协议 | HTTP | WebSocket | HTTP |
| 实现复杂度 | 简单 | 中等 | 复杂 |
| 浏览器支持 | 良好 | 良好 | 广泛 |
| 数据格式 | 文本 | 文本/二进制 | 文本 |

## 9. 兼容性与浏览器支持

### 9.1 支持情况
- Chrome 6+
- Firefox 6+
- Safari 5+
- Edge 79+
- iOS Safari 5+
- Android Browser 4.4+

### 9.2 特性检测
```javascript
if (typeof EventSource !== 'undefined') {
    // 浏览器支持SSE
    const eventSource = new EventSource('/events');
} else {
    // 降级方案，如长轮询
    console.log('浏览器不支持SSE，使用降级方案');
}
```

## 10. 总结

SSE事件流格式提供了一种简单、高效的服务器到客户端实时通信方案。其基于HTTP的设计使得实现和部署相对简单，特别适合只需要单向数据推送的场景。虽然功能上不如WebSocket全面，但在许多实际应用中，SSE因其简单性和可靠性成为理想选择。

通过遵循正确的事件流格式规范，结合合理的心跳和重连机制，可以构建稳定、高效的实时数据推送服务。