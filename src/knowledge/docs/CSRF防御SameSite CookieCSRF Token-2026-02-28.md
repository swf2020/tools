# CSRF防御技术文档：SameSite Cookie与CSRF Token

## 1. 文档概述

### 1.1 目的
本文档旨在详细阐述跨站请求伪造(CSRF)攻击的原理，并系统介绍两种主流防御机制：SameSite Cookie属性与CSRF Token技术，为开发人员提供全面的防护实施方案。

### 1.2 适用对象
- Web应用开发人员
- 安全工程师
- 系统架构师
- 质量控制人员

## 2. CSRF攻击原理分析

### 2.1 攻击定义
CSRF(Cross-Site Request Forgery)是一种利用用户已登录状态，在用户不知情的情况下执行非授权操作的攻击方式。

### 2.2 攻击流程
```
1. 用户登录受信任网站A，获得认证Cookie
2. 用户未退出情况下访问恶意网站B
3. 网站B的页面包含针对网站A的恶意请求
4. 用户浏览器自动携带网站A的Cookie执行请求
5. 网站A服务器误认为用户合法操作，执行攻击者意图
```

### 2.3 攻击示例
```html
<!-- 恶意网站中的代码 -->
<img src="https://bank.com/transfer?to=attacker&amount=10000">
<form action="https://bank.com/change-password" method="POST">
  <input type="hidden" name="new_password" value="hacked">
</form>
<script>document.forms[0].submit();</script>
```

## 3. SameSite Cookie防御机制

### 3.1 SameSite属性概述
SameSite是Cookie的一种属性，用于控制Cookie在跨站请求中的发送行为。

### 3.2 属性取值及作用

#### 3.2.1 Strict（严格模式）
```http
Set-Cookie: sessionid=abc123; SameSite=Strict; Secure; HttpOnly
```
- **行为**：仅在同站点请求中发送Cookie
- **适用场景**：敏感操作（如支付、密码修改）
- **用户体验影响**：从外部链接跳转时需重新登录

#### 3.2.2 Lax（宽松模式）
```http
Set-Cookie: sessionid=abc123; SameSite=Lax; Secure; HttpOnly
```
- **行为**：
  - 允许顶级导航GET请求发送Cookie（如点击链接）
  - 阻止跨站POST请求和嵌入资源请求
- **适用场景**：大多数用户会话Cookie
- **兼容性**：现代浏览器默认值

#### 3.2.3 None（无限制）
```http
Set-Cookie: sessionid=abc123; SameSite=None; Secure; HttpOnly
```
- **要求**：必须同时设置Secure属性
- **使用场景**：需要跨站共享的Cookie（如第三方服务）

### 3.3 服务端配置示例

#### 3.3.1 Node.js/Express
```javascript
app.use(session({
  secret: 'your-secret',
  cookie: {
    sameSite: 'strict', // 或 'lax', 'none'
    secure: process.env.NODE_ENV === 'production',
    httpOnly: true
  }
}));
```

#### 3.3.2 Django
```python
# settings.py
SESSION_COOKIE_SAMESITE = 'Lax'  # 或 'Strict', 'None'
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
```

#### 3.3.3 PHP
```php
session_set_cookie_params([
  'lifetime' => 0,
  'path' => '/',
  'domain' => $_SERVER['HTTP_HOST'],
  'secure' => true,
  'httponly' => true,
  'samesite' => 'Lax'
]);
```

### 3.4 浏览器兼容性
- Chrome 51+、Firefox 60+、Edge 79+、Safari 12.1+ 全面支持
- 旧版本浏览器会忽略该属性（安全降级）

## 4. CSRF Token防御机制

### 4.1 基本原理
CSRF Token是一种服务器生成的随机令牌，要求客户端在每个状态变更请求中携带验证。

### 4.2 实现架构

#### 4.2.1 同步令牌模式
```
客户端请求表单 → 服务器生成Token → 嵌入表单隐藏域
客户端提交表单 → 携带Token → 服务器验证Token
```

#### 4.2.2 双重Cookie验证
```
服务器设置CSRF Cookie → 客户端JS读取Cookie值
客户端请求时添加自定义Header → 服务器验证Header与Cookie匹配
```

### 4.3 详细实现方案

#### 4.3.1 服务器端Token生成与验证
```java
// Java Spring示例
@Configuration
@EnableWebSecurity
public class SecurityConfig extends WebSecurityConfigurerAdapter {
  
  @Override
  protected void configure(HttpSecurity http) throws Exception {
    http
      .csrf()
        .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
        .and()
      .authorizeRequests()
        .anyRequest().authenticated();
  }
}
```

#### 4.3.2 客户端Token集成
```html
<!-- 表单中嵌入Token -->
<form action="/transfer" method="POST">
  <input type="hidden" 
         name="_csrf" 
         value="{{csrfToken}}">
  <input type="text" name="amount">
  <button type="submit">提交</button>
</form>

<!-- AJAX请求处理 -->
<script>
// 从Cookie或Meta标签获取Token
const csrfToken = document.querySelector('meta[name="csrf-token"]').content;

fetch('/api/transfer', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRF-Token': csrfToken
  },
  body: JSON.stringify({ amount: 100 })
});
</script>
```

#### 4.3.3 Token存储策略对比
| 存储方式 | 优点 | 缺点 | 适用场景 |
|---------|------|------|---------|
| Session存储 | 安全性高 | 增加服务器负担 | 高安全要求系统 |
| Cookie存储 | 实现简单 | 需防XSS攻击 | 单页应用 |
| 加密Cookie | 无状态验证 | 加密开销 | 分布式系统 |

### 4.4 安全注意事项
1. **Token随机性**：使用加密安全的随机数生成器
2. **生命周期管理**：合理设置Token有效期
3. **每会话唯一**：确保每个会话使用不同Token
4. **绑定用户上下文**：Token与用户身份关联

## 5. 组合防御策略

### 5.1 深度防御架构
```
           SameSite Cookie (第一层防御)
                    ↓
            CSRF Token验证 (第二层防御)
                    ↓
        关键操作二次认证 (第三层防御)
```

### 5.2 实施建议

#### 5.2.1 基础安全层（所有请求）
```nginx
# Nginx配置SameSite属性
proxy_cookie_path / "/; secure; HttpOnly; SameSite=Lax";
```

#### 5.2.2 增强安全层（敏感操作）
```javascript
// 关键操作添加额外验证
function protectSensitiveOperation(request, response) {
  // 1. 验证SameSite Cookie
  if (!request.cookies.sessionid) {
    return response.status(403).json({ error: 'Invalid session' });
  }
  
  // 2. 验证CSRF Token
  const csrfToken = request.headers['x-csrf-token'];
  if (!validateCSRFToken(request.session.userId, csrfToken)) {
    return response.status(403).json({ error: 'Invalid CSRF token' });
  }
  
  // 3. 验证操作频率
  if (isRateLimited(request.ip, request.path)) {
    return response.status(429).json({ error: 'Too many requests' });
  }
  
  // 执行操作
  return processRequest(request);
}
```

#### 5.2.3 特定场景处理
- **文件上传**：使用FormData自动包含CSRF Token
- **API网关**：在网关层统一添加CSRF防护
- **移动端应用**：使用App专属Token机制

## 6. 测试验证方案

### 6.1 自动化测试脚本
```python
# CSRF防护测试示例
import requests
from urllib.parse import urlparse

def test_csrf_protection(target_url):
    # 测试1: 检查SameSite属性
    session = requests.Session()
    response = session.get(f"{target_url}/login")
    cookies = response.cookies
    
    for cookie in cookies:
        if 'session' in cookie.name.lower():
            assert 'SameSite' in str(cookie), "Missing SameSite attribute"
            assert 'Secure' in str(cookie), "Missing Secure attribute"
            assert 'HttpOnly' in str(cookie), "Missing HttpOnly attribute"
    
    # 测试2: 验证CSRF Token机制
    response = session.get(f"{target_url}/form")
    assert '_csrf' in response.text, "CSRF Token not found in form"
    
    # 测试3: 尝试CSRF攻击
    malicious_payload = {'amount': 10000, 'to': 'attacker'}
    attack_response = session.post(f"{target_url}/transfer", 
                                   data=malicious_payload)
    assert attack_response.status_code == 403, "CSRF protection failed"
    
    return "All tests passed"
```

### 6.2 手动测试清单
- [ ] Cookie是否设置Secure和HttpOnly标志
- [ ] 敏感Cookie是否使用SameSite=Strict
- [ ] 所有状态变更请求是否验证CSRF Token
- [ ] Token是否在每个会话中唯一
- [ ] Token是否绑定用户身份
- [ ] 错误请求是否返回适当的HTTP状态码

## 7. 常见问题与解决方案

### 7.1 SameSite Cookie问题
**问题**：第三方集成服务无法正常工作
**解决方案**：
```http
# 为特定路径设置例外
Set-Cookie: third_party_session=xyz; 
           SameSite=None; 
           Secure; 
           Path=/third-party-integration/
```

### 7.2 CSRF Token问题
**问题**：多标签页操作导致Token失效
**解决方案**：实现Token轮换机制
```javascript
// Token刷新策略
let currentToken = null;

async function refreshCSRFToken() {
  const response = await fetch('/api/csrf-refresh', {
    credentials: 'include'
  });
  currentToken = await response.json().token;
  
  // 更新所有表单
  document.querySelectorAll('input[name="_csrf"]')
    .forEach(input => input.value = currentToken);
}

// 页面可见性变化时刷新Token
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) {
    refreshCSRFToken();
  }
});
```

### 7.3 性能优化
**问题**：Token验证增加服务器负载
**解决方案**：
```redis
# 使用Redis缓存Token验证结果
# 键: csrf:user:{userId}:{tokenHash}
# 值: {valid: true, timestamp: 1625097600}
# 过期时间: 30分钟
```

## 8. 最佳实践总结

### 8.1 必做事项
1. **Cookie安全配置**：始终使用Secure、HttpOnly和适当的SameSite属性
2. **深度防御**：结合使用多种CSRF防护机制
3. **全面覆盖**：确保所有状态变更端点都受到保护
4. **安全日志**：记录所有CSRF验证失败事件

### 8.2 推荐配置
```yaml
# 安全配置参考
security:
  csrf:
    # SameSite配置
    cookie-samesite: "Lax"
    sensitive-routes-samesite: "Strict"
    
    # Token配置
    token-header: "X-CSRF-Token"
    token-cookie: "csrf_token"
    token-expiry: 3600  # 1小时
    
    # 例外配置
    exclude-paths:
      - "/health"
      - "/public-api/*"
    
    # 验证策略
    require-referer: true
    allowed-origins:
      - "https://example.com"
```

### 8.3 监控指标
- CSRF攻击尝试次数
- Token验证失败率
- SameSite Cookie兼容性问题
- 防护机制响应时间

## 9. 附录

### 9.1 参考标准
- OWASP CSRF防护指南
- RFC 6265: HTTP状态管理机制
- 各浏览器SameSite实现文档

### 9.2 工具推荐
- **CSRF测试工具**：Burp Suite、OWASP ZAP
- **Cookie分析器**：EditThisCookie、Cookie-Editor
- **安全头扫描**：SecurityHeaders.com

### 9.3 更新记录
| 版本 | 日期 | 修改内容 | 负责人 |
|------|------|----------|--------|
| 1.0 | 2024-01-15 | 初始版本创建 | 安全团队 |
| 1.1 | 2024-03-20 | 添加组合防御策略 | 架构组 |

---

**文档维护说明**：
本技术文档应每季度复审一次，及时更新浏览器兼容性信息和最新攻击防护技术。所有CSRF防护策略的变更需经过安全团队评审，并在预发环境充分测试后方可上线。