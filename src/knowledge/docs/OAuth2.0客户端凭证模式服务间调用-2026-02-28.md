# OAuth 2.0 客户端凭证模式（服务间调用）技术文档

## 1. 概述

### 1.1 文档目的
本文档旨在详细说明OAuth 2.0客户端凭证模式（Client Credentials Grant）的实现方案，重点描述服务间无用户参与的API访问场景。

### 1.2 适用范围
适用于微服务架构、服务间API调用、机器对机器（M2M）通信等需要服务身份认证和授权的场景。

## 2. 模式简介

### 2.1 基本概念
客户端凭证模式是OAuth 2.0定义的四种授权模式之一，专门用于：
- 服务端到服务端的认证
- 无用户参与的API调用
- 服务自身需要访问受保护资源

### 2.2 与其它模式对比
| 特性 | 客户端凭证模式 | 授权码模式 | 密码模式 |
|------|---------------|-----------|----------|
| 用户参与 | 否 | 是 | 是 |
| 适用场景 | 服务间调用 | Web应用 | 受信任客户端 |
| 安全性 | 高 | 高 | 中 |

## 3. 核心流程

### 3.1 时序图
```
客户端应用 → 授权服务器 → 资源服务器
     |           |            |
     |--1.请求令牌-->|           |
     |           |--2.验证凭证--|
     |<--3.返回令牌--|           |
     |-----------4.携带令牌访问资源-->|
     |<--------5.返回资源数据--------|
```

### 3.2 详细步骤

#### 步骤1：客户端凭据准备
```yaml
客户端信息:
  - client_id: 唯一客户端标识符
  - client_secret: 客户端密钥
  - scope: 请求的权限范围（可选）
  - grant_type: client_credentials
```

#### 步骤2：令牌请求
```http
POST /oauth/token HTTP/1.1
Host: auth-server.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id=s6BhdRkqt3
&client_secret=gX1fBat3bV
&scope=api.read api.write
```

#### 步骤3：令牌响应
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "api.read api.write"
}
```

#### 步骤4：资源访问
```http
GET /api/protected-resource HTTP/1.1
Host: resource-server.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

## 4. 实现要求

### 4.1 客户端实现
```python
# Python示例
import requests
from typing import Optional

class OAuth2Client:
    def __init__(self, client_id: str, client_secret: str, token_url: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self.access_token: Optional[str] = None
        
    def get_access_token(self, scopes: list = None) -> str:
        """获取访问令牌"""
        payload = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        
        if scopes:
            payload['scope'] = ' '.join(scopes)
            
        response = requests.post(self.token_url, data=payload)
        response.raise_for_status()
        
        token_data = response.json()
        self.access_token = token_data['access_token']
        return self.access_token
    
    def call_api(self, url: str, method: str = 'GET', **kwargs):
        """调用受保护的API"""
        if not self.access_token:
            self.get_access_token()
            
        headers = kwargs.get('headers', {})
        headers['Authorization'] = f'Bearer {self.access_token}'
        kwargs['headers'] = headers
        
        response = requests.request(method, url, **kwargs)
        return response
```

### 4.2 服务端实现要点

#### 4.2.1 授权服务器
```java
// Java Spring Security示例
@Configuration
@EnableAuthorizationServer
public class AuthServerConfig extends AuthorizationServerConfigurerAdapter {
    
    @Override
    public void configure(ClientDetailsServiceConfigurer clients) throws Exception {
        clients.inMemory()
            .withClient("service-client")
            .secret(passwordEncoder().encode("client-secret"))
            .authorizedGrantTypes("client_credentials")
            .scopes("read", "write")
            .accessTokenValiditySeconds(3600);
    }
    
    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
```

#### 4.2.2 资源服务器
```yaml
# 配置示例
security:
  oauth2:
    resource:
      token-info-uri: http://auth-server/oauth/check_token
    client:
      client-id: resource-server
      client-secret: resource-secret
```

## 5. 安全考量

### 5.1 凭证安全
1. **客户端密钥存储**
   - 使用安全的密钥管理系统
   - 避免硬编码在源代码中
   - 定期轮换密钥

2. **传输安全**
   - 必须使用HTTPS/TLS
   - 建议使用mTLS双向认证

### 5.2 令牌安全
```python
# 令牌验证最佳实践
def validate_token(access_token: str) -> dict:
    """
    验证令牌的有效性
    返回令牌包含的声明信息
    """
    # 1. 验证签名
    # 2. 检查有效期
    # 3. 验证颁发者
    # 4. 验证受众
    # 5. 检查吊销状态
    pass
```

### 5.3 审计与监控
- 记录所有令牌颁发请求
- 监控异常访问模式
- 实施速率限制

## 6. 性能优化

### 6.1 令牌缓存策略
```python
# Redis缓存示例
import redis
import json
from datetime import datetime, timedelta

class TokenCache:
    def __init__(self, redis_client):
        self.redis = redis_client
        
    def get_cached_token(self, client_id: str, scopes: str) -> Optional[str]:
        cache_key = f"token:{client_id}:{scopes}"
        token_data = self.redis.get(cache_key)
        
        if token_data:
            return json.loads(token_data)['access_token']
        return None
    
    def cache_token(self, client_id: str, scopes: str, token_data: dict):
        cache_key = f"token:{client_id}:{scopes}"
        expires_in = token_data.get('expires_in', 3600)
        
        # 缓存时间略短于实际有效期
        cache_ttl = expires_in - 60
        self.redis.setex(
            cache_key,
            cache_ttl,
            json.dumps(token_data)
        )
```

### 6.2 连接池管理
```yaml
# HTTP连接池配置
http-client:
  max-connections: 100
  max-connections-per-route: 20
  connection-timeout: 5000
  socket-timeout: 10000
```

## 7. 故障处理

### 7.1 错误响应
```json
{
  "error": "invalid_client",
  "error_description": "Client authentication failed",
  "error_uri": "https://docs.example.com/errors#invalid_client"
}
```

### 7.2 重试机制
```python
# 带退避的重试逻辑
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
def get_token_with_retry(client):
    return client.get_access_token()
```

## 8. 部署配置

### 8.1 环境变量配置
```bash
# .env文件示例
OAUTH_CLIENT_ID=your-client-id
OAUTH_CLIENT_SECRET=your-client-secret
OAUTH_TOKEN_URL=https://auth.example.com/oauth/token
OAUTH_SCOPES=api.read api.write
```

### 8.2 Docker配置
```dockerfile
FROM python:3.9-slim

# 设置环境变量
ENV OAUTH_CLIENT_ID=${CLIENT_ID}
ENV OAUTH_CLIENT_SECRET=${CLIENT_SECRET}

# 安全实践：使用非root用户
RUN useradd -m -u 1000 appuser
USER appuser

COPY . /app
WORKDIR /app
```

## 9. 监控指标

### 9.1 关键指标
```prometheus
# Prometheus指标示例
oauth_token_requests_total{client_id, status}
oauth_token_response_time_seconds{quantile}
oauth_api_calls_total{client_id, endpoint, status}
oauth_active_tokens
```

### 9.2 告警规则
```yaml
groups:
  - name: oauth_alerts
    rules:
      - alert: HighTokenErrorRate
        expr: rate(oauth_token_errors_total[5m]) > 0.1
        for: 5m
```

## 10. 附录

### 10.1 RFC参考
- RFC 6749: OAuth 2.0授权框架
- RFC 6750: Bearer令牌用法
- RFC 8414: OAuth 2.0授权服务器元数据

### 10.2 工具推荐
1. **测试工具**
   - Postman
   - OAuth 2.0 Playground
   
2. **监控工具**
   - Prometheus + Grafana
   - ELK Stack

### 10.3 常见问题解答
**Q: 客户端凭证模式是否支持刷新令牌？**
A: 不支持。客户端凭证模式只颁发访问令牌，需要重新请求获取新令牌。

**Q: 如何处理密钥泄露？**
A: 立即撤销受影响凭证，调查泄露原因，轮换所有相关密钥。

---

*文档版本：1.0*
*最后更新日期：2024年*
*维护团队：架构组*