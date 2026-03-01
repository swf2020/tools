好的，遵照您的要求，我为您生成一份关于“接口签名防重放（timestamp+nonce+sign）”的技术文档。本文档结构清晰，内容完整，可直接用于项目参考或团队分享。

---

## **接口签名防重放攻击技术方案文档**

**文档版本：** V1.0
**最后更新日期：** 2023-10-27
**作者：** 技术架构部
**适用对象：** 后端开发工程师、客户端开发工程师、测试工程师

---

### **1. 文档摘要**

本文档旨在定义一套基于 **时间戳（timestamp）、随机数（nonce）和签名（sign）** 的接口安全通信与防重放攻击方案。通过该方案，可有效确保请求的**新鲜性、完整性与不可否认性**，防止数据在传输过程中被篡改或恶意重复提交。

### **2. 背景与目标**

#### **2.1 背景**
在Web API、移动端API等接口调用中，常面临以下安全威胁：
*   **数据篡改**：攻击者截获请求，修改参数后重新发送。
*   **重放攻击**：攻击者原样截获合法请求，在有效期内多次重复发送，导致业务异常（如重复下单、重复扣款）。
*   **数据泄漏**：敏感参数以明文形式传输。

#### **2.2 目标**
*   **防篡改**：确保请求数据自客户端发出后未被修改。
*   **防重放**：确保同一请求在一定时间内只能被成功处理一次。
*   **身份验证**：间接验证调用方的合法性（拥有合法密钥）。
*   **时效性**：确保请求在合理的时间窗口内。

### **3. 核心设计原理**

本方案通过三个核心参数协同工作：
1.  **Timestamp（时间戳）**：标识请求发起的时间，用于服务端验证请求的时效性，过期则拒绝。
2.  **Nonce（一次性随机数）**：一个全局唯一的字符串，用于唯一标识单次请求，服务端通过存储机制防止其被重复使用。
3.  **Sign（签名）**：客户端使用约定的算法和密钥，对所有业务参数、`timestamp`、`nonce`进行加密处理得到的密文。服务端以相同规则生成签名并比对，以此验证请求的完整性和调用方身份。

**核心流程：**
```
客户端生成请求 -> 加入timestamp和nonce -> 计算签名sign -> 发送请求
       ↓
服务端接收请求 -> 检查timestamp时效 -> 检查nonce是否已存在 -> 验证签名 -> 处理业务
```

### **4. 详细技术规范**

#### **4.1 参数定义**

| 参数名 | 类型 | 是否必须 | 描述 |
| :--- | :--- | :--- | :--- |
| `timestamp` | Long | 是 | 请求发起时的Unix时间戳（单位：秒或毫秒，需统一）。例如：`1698393920`。 |
| `nonce` | String | 是 | 随机字符串，建议使用UUID或足够长度的随机数，确保全局唯一。例如：`a1b2c3d4-e5f6-7890-g1h2-i3j4k5l6m7n8`。 |
| `sign` | String | 是 | 根据签名算法计算出的字符串，用于校验。 |
| `app_id` / `api_key` | String | 是 | 应用标识，用于服务端查找对应的`app_secret`（密钥）。密钥不参与传输。 |

#### **4.2 签名（Sign）生成算法（客户端）**

1.  **参数排序**：将所有待签名的参数（包括`timestamp`, `nonce`, `app_id`和所有业务参数，但不包括`sign`本身）按键名进行**升序排序**（ASCII码）。
2.  **参数拼接**：将排序后的参数按 `键=值` 的格式用 `&` 连接，形成待签名字符串。
    *   **格式**：`key1=value1&key2=value2&...&keyN=valueN`
    *   **注意**：值为空或不传的参数也应参与签名，`value`为空字符串。
3.  **拼接密钥**：在待签名字符串的**末尾**拼接上分配的应用密钥 `app_secret`。
    *   **格式**：`待签名字符串&app_secret=your_secret_key`
    *   *另一种常见做法是直接 `待签名字符串 + app_secret`，但`&`拼接更统一。*
4.  **计算签名**：将上一步得到的字符串，使用约定的哈希算法（如 **HMAC-SHA256**、MD5、SHA1等，推荐HMAC-SHA256）进行加密，并将结果转换为**小写十六进制字符串**，即为 `sign`。
5.  **添加至请求**：将计算出的 `sign` 连同 `timestamp`、`nonce`、`app_id` 等参数，**一同放入请求头（Header）或请求体（Body）** 中发送。推荐使用Header，以区分业务参数。

#### **4.3 服务端验证流程**

对于每一个到达的请求，服务端需按顺序执行以下验证：

1.  **基本检查**
    *   检查必要参数（`timestamp`, `nonce`, `sign`, `app_id`）是否存在。
    *   根据 `app_id` 从安全存储中查询对应的 `app_secret`。若不存在，直接拒绝。

2.  **时效性验证（防重放基础）**
    *   获取当前服务器时间戳 `current_timestamp`。
    *   计算时间差：`delta = |current_timestamp - request_timestamp|`。
    *   判断 `delta` 是否大于预设的允许时间漂移窗口（如 **5分钟，300秒**）。若超出，视为过期请求，拒绝。
    *   *目的：限制请求的有效期，即使被截获，也只在很短时间内可利用。*

3.  **Nonce唯一性验证（防重放核心）**
    *   以 `app_id:nonce` 或 `nonce` 本身作为键，查询分布式缓存（如 **Redis**）。
    *   **如果存在**：说明此 `nonce` 已经被使用过，判定为重放攻击，拒绝请求。
    *   **如果不存在**：将 `app_id:nonce` 写入缓存，并设置一个略大于时间窗口的过期时间（如 `窗口时间+60秒`，例如360秒）。随后放行。
    *   *目的：确保同一 `nonce` 在有效期内绝对唯一，从根源上防止重放。*

4.  **签名验证（防篡改与身份校验）**
    *   按照 **4.2** 节描述的**完全相同**的步骤（排序、拼接、加秘、哈希），使用服务端存储的 `app_secret` 重新计算一次签名 `server_sign`。
    *   将计算得到的 `server_sign` 与客户端传来的 `sign` 进行**安全的字符串比较**（避免计时攻击，如Java的 `MessageDigest.isEqual`）。
    *   如果一致，通过验证；否则，判定为签名无效（可能参数被篡改或密钥错误），拒绝请求。

5.  **业务处理**
    *   所有安全验证通过后，执行正常的业务逻辑。

### **5. 示例**

假设：
*   `app_id` = `20231027`
*   `app_secret` = `MySecretKey123!@#`
*   请求API：`/api/v1/user/update`
*   业务参数：`name=张三&age=25`
*   `timestamp` = `1698393920`
*   `nonce` = `550e8400-e29b-41d4-a716-446655440000`

**客户端生成签名步骤：**
1.  所有待签名参数集合：`{“app_id”: “20231027”， “name”:“张三”， “age”:“25”， “timestamp”: “1698393920”， “nonce”: “550e8400...”}`
2.  按key排序后：`age=25&app_id=20231027&name=张三&nonce=550e8400...&timestamp=1698393920`
3.  拼接密钥：`age=25&app_id=20231027&name=张三&nonce=550e8400...&timestamp=1698393920&app_secret=MySecretKey123!@#`
4.  计算HMAC-SHA256（假设结果）：`sign = “f7a3c8b1d4e5a6f7890c1b2a3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8091a2b3c”`

**最终发送的HTTP请求：**
```http
POST /api/v1/user/update HTTP/1.1
Content-Type: application/json
X-App-Id: 20231027
X-Timestamp: 1698393920
X-Nonce: 550e8400-e29b-41d4-a716-446655440000
X-Sign: f7a3c8b1d4e5a6f7890c1b2a3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8091a2b3c

{
  "name": "张三",
  "age": 25
}
```
*(注意：参数也可以全部放在Body中，但签名计算需包含它们)*

### **6. 服务器端实现要点（伪代码/思路）**

```java
// 示例：Spring Boot 拦截器实现
@Component
public class ApiSecurityInterceptor implements HandlerInterceptor {

    @Autowired
    private RedisTemplate<String, String> redisTemplate;
    @Autowired
    private AppSecretService appSecretService; // 查询密钥的服务

    private static final long TIME_WINDOW = 300L; // 5分钟
    private static final String NONCE_KEY_PREFIX = "api:nonce:";

    @Override
    public boolean preHandle(HttpServletRequest request， HttpServletResponse response， Object handler) {
        // 1. 获取参数
        String appId = request.getHeader("X-App-Id");
        String timestampStr = request.getHeader("X-Timestamp");
        String nonce = request.getHeader("X-Nonce");
        String clientSign = request.getHeader("X-Sign");

        // 2. 基本检查
        if (StringUtils.isEmpty(appId) || ... ) {
            return error(response, 400， “缺少必要参数”);
        }

        // 3. 获取密钥
        String appSecret = appSecretService.getSecretById(appId);
        if (appSecret == null) {
            return error(response, 401， “无效的应用标识”);
        }

        // 4. 验证时间戳
        long timestamp = Long.parseLong(timestampStr);
        long currentTime = System.currentTimeMillis() / 1000; // 假设用秒
        if (Math.abs(currentTime - timestamp) > TIME_WINDOW) {
            return error(response, 403， “请求已过期”);
        }

        // 5. 验证Nonce
        String redisKey = NONCE_KEY_PREFIX + appId + ":" + nonce;
        Boolean isAbsent = redisTemplate.opsForValue().setIfAbsent(redisKey， "used"， Duration.ofSeconds(TIME_WINDOW + 60));
        if (Boolean.FALSE.equals(isAbsent)) {
            return error(response, 403， “请求重复”);
        }

        // 6. 验证签名
        // 6.1 从request中提取所有参与签名的参数（Header中的特定参数+Body），并排序
        Map<String, String> params = extractAndSortParams(request);
        // 6.2 生成服务端签名
        String serverSign = generateSign(params， appSecret);
        // 6.3 安全比较
        if (!MessageDigest.isEqual(serverSign.getBytes(StandardCharsets.UTF_8),
                                   clientSign.getBytes(StandardCharsets.UTF_8))) {
            // 可记录日志，监控异常签名
            return error(response, 403， “签名验证失败”);
        }

        // 7. 所有验证通过
        return true;
    }

    private String generateSign(Map<String, String> sortedParams， String secret) {
        // 实现签名算法，同客户端
        // ...
    }
}
```

### **7. 安全建议与注意事项**

1.  **密钥管理**：`app_secret` 必须安全存储。服务端使用配置中心或密钥管理服务，客户端（如移动端）需做好代码混淆，但需认识到 native 客户端的密钥存在被提取的风险。非常敏感的操作应使用OAuth 2.0等更高级别认证。
2.  **时间同步**：确保客户端和服务端时钟基本同步。可使用网络时间协议（NTP）同步服务器时间。
3.  **时间窗口选择**：根据业务特点选择合适窗口。太短可能因网络延迟导致合法请求被拒，太长则增大重放攻击风险。通常60-300秒。
4.  **哈希算法**：推荐使用 **HMAC-SHA256**，它比简单的MD5或SHA1更安全。避免自行拼接哈希。
5.  **防Nonce爆库**：`nonce`应有足够长度和随机性（如UUID）。在极高并发下，需注意Redis等存储的性能。
6.  **HTTPS**：**本方案必须与HTTPS（TLS）结合使用**，以防止通信链路上的窃听和中间人攻击。签名解决的是应用层问题，HTTPS解决传输层问题。
7.  **日志与监控**：记录签名失败、重放攻击的日志，并设置告警，有助于发现潜在的攻击行为。

### **8. 方案优缺点总结**

*   **优点**：
    *   实现相对简单，安全性较高。
    *   能有效防御常见的重放、篡改攻击。
    *   无状态（依赖缓存），易于在分布式系统中扩展。
*   **缺点**：
    *   增加了客户端和服务端的计算与网络开销（一次缓存读写）。
    *   服务端需要维护密钥和nonce缓存。
    *   无法防御HTTPS链路内的中间人攻击（需依赖TLS证书安全）。

---
**附录：**
*   各语言（Python, Go, JavaScript）的签名生成示例代码。
*   Redis缓存键设计规范。

---
如果您需要附录中的示例代码或对本方案的任何部分有进一步的疑问，请随时提出。