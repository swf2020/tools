# Webhook 事件签名验证（HMAC-SHA256）技术文档

## 1. 概述

Webhook 签名验证是一种安全机制，用于确保从第三方服务发送到您服务器的 Webhook 事件数据的**完整性**和**真实性**。通过使用 HMAC-SHA256 算法，您可以验证接收到的数据确实来自可信的发送方，且在传输过程中未被篡改。

## 2. 核心概念

### 2.1 HMAC（Hash-based Message Authentication Code）
- 基于密钥的哈希算法，用于验证消息的完整性和真实性
- 结合加密哈希函数（SHA256）和密钥生成消息认证码

### 2.2 SHA256
- 安全哈希算法，生成 256 位（32 字节）的哈希值
- 具有抗碰撞性和单向性特点

## 3. 验证流程

### 3.1 签名生成流程（发送方）
1. **准备数据**：获取 Webhook 事件的原始请求体（payload）
2. **获取密钥**：使用预先共享的密钥（secret）
3. **计算签名**：`HMAC-SHA256(secret, payload)`
4. **编码结果**：通常转换为十六进制字符串或 Base64 编码
5. **设置请求头**：将签名添加到 HTTP 请求头（如 `X-Webhook-Signature`）

### 3.2 签名验证流程（接收方）
```plaintext
接收 Webhook 请求
    ↓
提取请求头中的签名
    ↓
获取原始请求体（保持原始格式）
    ↓
使用共享密钥计算 HMAC-SHA256
    ↓
比较计算的签名与接收的签名
    ↓
    匹配 → 验证成功，处理请求
    不匹配 → 验证失败，拒绝请求
```

## 4. 实现示例

### 4.1 发送方实现示例（Python）

```python
import hmac
import hashlib
import json

def generate_webhook_signature(payload, secret):
    """
    生成 Webhook 签名
    
    Args:
        payload (dict/str): Webhook 数据
        secret (str): 共享密钥
    
    Returns:
        str: 十六进制格式的签名
    """
    if isinstance(payload, dict):
        payload_str = json.dumps(payload, separators=(',', ':'))
    else:
        payload_str = str(payload)
    
    # 计算 HMAC-SHA256
    signature = hmac.new(
        secret.encode('utf-8'),
        payload_str.encode('utf-8'),
        hashlib.sha256
    )
    
    # 返回十六进制字符串
    return signature.hexdigest()

# 使用示例
secret = "your-shared-secret-key-12345"
payload = {
    "event": "user.created",
    "id": "evt_123456789",
    "data": {
        "user_id": "usr_123",
        "email": "user@example.com"
    },
    "timestamp": 1625097600
}

signature = generate_webhook_signature(payload, secret)
# 设置请求头：X-Webhook-Signature: {signature}
```

### 4.2 接收方实现示例（Python/Flask）

```python
from flask import Flask, request, jsonify
import hmac
import hashlib
import json

app = Flask(__name__)
WEBHOOK_SECRET = "your-shared-secret-key-12345"

def verify_webhook_signature(payload, received_signature, secret):
    """
    验证 Webhook 签名
    
    Args:
        payload (bytes/str): 原始请求体
        received_signature (str): 接收到的签名
        secret (str): 共享密钥
    
    Returns:
        bool: 验证是否通过
    """
    # 计算期望的签名
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload if isinstance(payload, bytes) else payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # 安全比较签名（防止时序攻击）
    return hmac.compare_digest(expected_signature, received_signature)

@app.route('/webhook', methods=['POST'])
def webhook_handler():
    # 获取请求头中的签名
    received_signature = request.headers.get('X-Webhook-Signature')
    
    if not received_signature:
        return jsonify({"error": "Missing signature"}), 401
    
    # 获取原始请求体数据
    raw_payload = request.get_data()
    
    # 验证签名
    if not verify_webhook_signature(raw_payload, received_signature, WEBHOOK_SECRET):
        return jsonify({"error": "Invalid signature"}), 401
    
    # 签名验证通过，解析并处理数据
    try:
        payload = json.loads(raw_payload.decode('utf-8'))
        # 处理 Webhook 事件
        process_webhook_event(payload)
        return jsonify({"status": "success"}), 200
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON payload"}), 400

def process_webhook_event(payload):
    """处理 Webhook 事件"""
    event_type = payload.get('event')
    # 根据事件类型进行相应处理
    # ...

if __name__ == '__main__':
    app.run(debug=True)
```

### 4.3 Node.js 实现示例

```javascript
const crypto = require('crypto');
const express = require('express');
const app = express();

const WEBHOOK_SECRET = 'your-shared-secret-key-12345';

// 生成签名
function generateSignature(payload, secret) {
    return crypto
        .createHmac('sha256', secret)
        .update(payload)
        .digest('hex');
}

// 验证签名
function verifySignature(payload, signature, secret) {
    const expectedSignature = crypto
        .createHmac('sha256', secret)
        .update(payload)
        .digest('hex');
    
    // 安全比较签名
    return crypto.timingSafeEqual(
        Buffer.from(expectedSignature, 'hex'),
        Buffer.from(signature, 'hex')
    );
}

// Webhook 端点
app.post('/webhook', express.raw({ type: 'application/json' }), (req, res) => {
    const signature = req.headers['x-webhook-signature'];
    const payload = req.body;
    
    if (!signature) {
        return res.status(401).json({ error: 'Missing signature' });
    }
    
    if (!verifySignature(payload, signature, WEBHOOK_SECRET)) {
        return res.status(401).json({ error: 'Invalid signature' });
    }
    
    // 签名验证通过，处理事件
    const event = JSON.parse(payload.toString());
    console.log('Received event:', event.event);
    
    res.json({ status: 'success' });
});

app.listen(3000, () => {
    console.log('Webhook server listening on port 3000');
});
```

## 5. 最佳实践

### 5.1 密钥管理
- **安全存储**：将密钥存储在环境变量或密钥管理服务中
- **定期轮换**：定期更新密钥，并确保新旧密钥在过渡期间都能使用
- **不同环境使用不同密钥**：开发、测试、生产环境使用不同的密钥

### 5.2 实现注意事项
1. **使用原始请求体**：验证签名时应使用原始、未解析的请求体
2. **防止时序攻击**：使用安全的比较函数（如 `hmac.compare_digest`）
3. **添加时间戳验证**：防止重放攻击
4. **记录验证失败**：监控和记录签名验证失败的请求

### 5.3 时间戳验证（防重放攻击）
```python
import time

def verify_timestamp(payload, max_age_seconds=300):
    """
    验证时间戳，防止重放攻击
    
    Args:
        payload (dict): Webhook 数据
        max_age_seconds (int): 最大允许的时间差（秒）
    
    Returns:
        bool: 时间戳是否有效
    """
    timestamp = payload.get('timestamp')
    if not timestamp:
        return False
    
    current_time = int(time.time())
    time_diff = abs(current_time - timestamp)
    
    return time_diff <= max_age_seconds
```

### 5.4 多签名支持
```python
def verify_signature_with_variants(payload, received_signature, secret):
    """
    支持多种签名格式的验证
    """
    # 可能的签名前缀变体
    signature_variants = [
        received_signature,
        received_signature.replace('sha256=', ''),
        f"sha256={received_signature}"
    ]
    
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    # 检查所有变体
    for variant in signature_variants:
        if hmac.compare_digest(expected_signature, variant):
            return True
    
    return False
```

## 6. 故障排除

### 6.1 常见问题
1. **签名不匹配**
   - 检查密钥是否正确
   - 验证是否使用原始请求体（而非解析后的 JSON）
   - 确认编码方式一致（十六进制 vs Base64）

2. **特殊字符处理**
   - 确保 payload 中的特殊字符被正确处理
   - 注意空格和换行符的一致性

3. **时间戳问题**
   - 检查服务器时间同步
   - 验证时区设置

### 6.2 调试方法
```python
def debug_signature_verification(payload, received_signature, secret):
    """调试签名验证过程"""
    print(f"Received signature: {received_signature}")
    print(f"Payload length: {len(payload)}")
    print(f"Payload preview: {payload[:100]}...")
    
    # 计算签名
    calculated = hmac.new(
        secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    print(f"Calculated signature: {calculated}")
    print(f"Match: {hmac.compare_digest(calculated, received_signature)}")
```

## 7. 安全建议

1. **HTTPS 必需**：Webhook 端点必须使用 HTTPS
2. **IP 白名单**：如果可能，限制发送方的 IP 地址
3. **请求限流**：防止暴力攻击
4. **详细的日志记录**：记录验证成功/失败的请求
5. **监控和告警**：设置异常活动的监控和告警

## 8. 总结

HMAC-SHA256 签名验证为 Webhook 提供了可靠的安全保障。通过正确实现签名验证机制，您可以确保接收到的 Webhook 事件来自可信的发送方，并且在传输过程中未被篡改。建议结合实际业务需求，实施包括时间戳验证、密钥轮换和监控在内的完整安全策略。

---

**附录：相关工具和库**

- **Python**：标准库 `hmac`、`hashlib`
- **Node.js**：标准库 `crypto`
- **Java**：`javax.crypto.Mac`
- **Go**：`crypto/hmac` 包
- **Ruby**：`OpenSSL::HMAC`
- **PHP**：`hash_hmac()` 函数