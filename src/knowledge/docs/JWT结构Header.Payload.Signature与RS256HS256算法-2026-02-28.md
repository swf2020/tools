# JWT结构（Header.Payload.Signature）与RS256/HS256算法技术文档

## 1. 概述

JSON Web Token（JWT）是一种开放标准（RFC 7519），用于在各方之间安全地传输信息作为JSON对象。JWT广泛应用于身份验证和授权场景，特别在RESTful API和微服务架构中。

## 2. JWT核心结构

JWT由三部分组成，以点号分隔：`Header.Payload.Signature`

### 2.1 Header（头部）

头部通常包含两部分信息：
- 令牌类型（typ）：固定为"JWT"
- 签名算法（alg）：如HS256、RS256等

**示例：**
```json
{
  "alg": "HS256",
  "typ": "JWT"
}
```

编码后（Base64Url）：`eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9`

### 2.2 Payload（载荷）

载荷包含声明（claims），声明是关于实体（通常是用户）和其他数据的声明。声明分为三类：

1. **注册声明**（预定义但不强制使用）：
   - `iss`（issuer）：签发者
   - `exp`（expiration time）：过期时间
   - `sub`（subject）：主题
   - `aud`（audience）：受众
   - `iat`（issued at）：签发时间
   - `nbf`（not before）：生效时间
   - `jti`（JWT ID）：唯一标识

2. **公共声明**：可自定义，但需避免冲突

3. **私有声明**：用于在各方之间共享信息

**示例：**
```json
{
  "sub": "1234567890",
  "name": "John Doe",
  "admin": true,
  "iat": 1516239022
}
```

编码后（Base64Url）：`eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0`

### 2.3 Signature（签名）

签名是用于验证消息在传输过程中未被篡改的部分。创建签名需要：
- 编码后的header
- 编码后的payload
- 密钥（secret）
- 头部指定的算法

**签名生成公式：**
```
HMACSHA256(
  base64UrlEncode(header) + "." + base64UrlEncode(payload),
  secret
)
```

完整JWT示例：`Header.Payload.Signature`

## 3. 签名算法详解

### 3.1 HS256算法

**算法全称：** HMAC with SHA-256  
**算法类型：** 对称加密算法  
**工作原理：** 使用同一个密钥进行签名和验证

**特点：**
- 加密解密使用相同密钥
- 计算速度快，性能高
- 密钥管理是关键安全考虑
- 不适合多方系统（密钥需共享）

**实现示例（伪代码）：**
```
signature = HMAC-SHA256(base64UrlEncode(header) + "." + base64UrlEncode(payload), secret_key)
```

### 3.2 RS256算法

**算法全称：** RSA Signature with SHA-256  
**算法类型：** 非对称加密算法  
**工作原理：** 使用私钥签名，公钥验证

**特点：**
- 公钥/私钥对：私钥签名，公钥验证
- 无需共享私钥，安全性更高
- 计算开销较大
- 适合多方系统和分布式环境

**实现示例（伪代码）：**
```
signature = RSA-SHA256(base64UrlEncode(header) + "." + base64UrlEncode(payload), private_key)
verification = RSA-Verify(signature, public_key)
```

## 4. HS256 vs RS256对比分析

| 特性 | HS256 | RS256 |
|------|-------|-------|
| **算法类型** | 对称加密 | 非对称加密 |
| **密钥管理** | 单一共享密钥 | 公钥/私钥对 |
| **性能** | 快（哈希运算） | 较慢（RSA运算） |
| **适用场景** | 单方签发验证 | 多方系统、微服务 |
| **安全性** | 依赖密钥保密性 | 私钥保密，公钥可公开 |
| **密钥泄露风险** | 高（单点失效） | 低（只需保护私钥） |
| **标准化支持** | 广泛支持 | 广泛支持 |

## 5. 安全考虑与最佳实践

### 5.1 通用安全建议

1. **令牌有效期**：设置合理的过期时间（exp claim）
2. **敏感数据**：不要在Payload中存储敏感信息（JWT可解码）
3. **HTTPS传输**：始终通过HTTPS传输JWT
4. **存储安全**：客户端妥善存储（避免XSS攻击）

### 5.2 算法选择指南

**选择HS256当：**
- 单服务架构
- 性能要求高
- 可以安全管理共享密钥
- 签发方和验证方相同

**选择RS256当：**
- 微服务/分布式系统
- 第三方身份提供者（如Auth0、AWS Cognito）
- 需要公钥分发验证的场景
- 安全要求更高的系统

### 5.3 密钥管理

**HS256密钥管理：**
- 使用强随机密钥（至少256位）
- 定期轮换密钥
- 使用密钥管理系统

**RS256密钥管理：**
- 私钥严格保密
- 公钥可安全分发
- 实施密钥轮换策略
- 考虑使用证书管理

## 6. 实际应用示例

### 6.1 Node.js实现示例

```javascript
// RS256示例（使用jsonwebtoken库）
const jwt = require('jsonwebtoken');
const fs = require('fs');

// 读取密钥
const privateKey = fs.readFileSync('private.key');
const publicKey = fs.readFileSync('public.key');

// 生成令牌（RS256）
const token = jwt.sign(
  { userId: '123', role: 'admin' },
  privateKey,
  { algorithm: 'RS256', expiresIn: '1h' }
);

// 验证令牌
jwt.verify(token, publicKey, { algorithms: ['RS256'] }, (err, decoded) => {
  if (err) throw err;
  console.log(decoded);
});

// HS256示例
const secret = 'your-256-bit-secret';
const hs256Token = jwt.sign(
  { userId: '123' },
  secret,
  { algorithm: 'HS256', expiresIn: '1h' }
);
```

### 6.2 算法混淆攻击防护

**风险：** 攻击者可能修改头部算法为"none"或从RS256改为HS256

**防护措施：**
```javascript
// 明确指定接受的算法
jwt.verify(token, publicKey, { algorithms: ['RS256'] }, callback);

// 或使用库的自动验证功能
jwt.verify(token, publicKey, callback); // 自动使用头部指定算法
```

## 7. 结论

JWT提供了一种简洁、自包含的身份验证机制。HS256和RS256是两种最常用的签名算法，各有适用场景：

- **HS256** 适合对性能要求高、架构简单的系统
- **RS256** 适合安全性要求高、涉及多方参与的分布式系统

在实际应用中，应根据具体需求、安全要求和系统架构选择合适的算法，并遵循安全最佳实践，确保JWT的安全使用。

## 8. 参考文献

1. RFC 7519 - JSON Web Token (JWT)
2. RFC 7518 - JSON Web Algorithms (JWA)
3. OWASP JWT Cheat Sheet
4. NIST Special Publication 800-57 (密钥管理指南)

---

**文档版本：** 1.0  
**更新日期：** 2024年1月  
**适用范围：** 开发人员、架构师、安全工程师