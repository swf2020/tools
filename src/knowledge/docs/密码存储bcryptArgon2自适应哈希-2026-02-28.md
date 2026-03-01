# 密码安全存储技术文档
## 使用bcrypt与Argon2自适应哈希算法

---

## 1. 概述

### 1.1 文档目的
本文档旨在为开发人员提供关于安全密码存储的最佳实践指南，重点介绍bcrypt和Argon2两种自适应哈希算法的原理、实现和选择标准。

### 1.2 密码存储的重要性
- 防止密码泄露导致的连锁安全事件
- 满足合规性要求（GDPR、PCI DSS等）
- 保护用户隐私和系统安全

---

## 2. 密码存储基本原则

### 2.1 禁止的做法
- ❌ 明文存储密码
- ❌ 使用简单哈希（MD5、SHA-1、SHA-256等）
- ❌ 自行设计加密方案
- ❌ 使用弱盐值（固定盐、短盐）

### 2.2 必需的特性
- ✅ 使用加密安全的随机盐值
- ✅ 应用自适应哈希算法
- ✅ 足够的工作因子（迭代次数/内存消耗）
- ✅ 密码验证时的恒定时间比较

---

## 3. bcrypt算法详解

### 3.1 算法特性
```
算法类型：基于Blowfish的自适应哈希
主要特性：
  - 内置盐值机制
  - 可调节的工作因子（迭代次数）
  - 输出格式包含算法标识、工作因子和盐值
  - 抗GPU/ASIC攻击设计
```

### 3.2 工作因子选择建议
```plaintext
当前推荐配置：
  - 最小工作因子：12（2024年标准）
  - 新系统建议：13-15
  - 根据硬件性能调整，验证时间应在250-500ms
```

### 3.3 示例哈希结构
```
$2b$12$jPuJ0vPEG4t7s98FQJQZp.6oI2dQ5F3LbQ6Q1VjWkXpN9mRlS2tT4u
├─┬───┼─┬───────────────────────────────
  │   │ │
  │   │ └─ 盐值 + 哈希值（22字符Base64）
  │   └─ 工作因子（12 = 2^12次迭代）
  └─ 算法版本（2b = bcrypt）
```

---

## 4. Argon2算法详解

### 4.1 算法类型
```
Argon2d：抗GPU破解，但可能受侧信道攻击
Argon2i：抗侧信道攻击，但GPU破解稍易
Argon2id：混合模式（推荐），结合两者优点
```

### 4.2 关键参数
```yaml
timeCost:    # 迭代次数（1-10）
  建议值: 3-5
  
memoryCost:  # 内存消耗（KB）
  建议值: 65536-131072 KB（64-128MB）
  
parallelism: # 并行线程数
  建议值: 2-4
  
hashLength:  # 输出哈希长度
  建议值: 32字节（256位）
```

### 4.3 算法优势
- **内存硬特性**：需要大量内存，抗ASIC/GPU攻击
- **参数灵活性**：可调整内存、时间和并行度
- **标准化**：密码哈希竞赛（PHC）获胜者

---

## 5. 实现指南

### 5.1 环境准备
```bash
# Node.js
npm install bcrypt argon2

# Python
pip install bcrypt argon2-cffi

# PHP
composer require ircmaxell/password-compat
```

### 5.2 bcrypt实现示例

#### Node.js
```javascript
const bcrypt = require('bcrypt');

// 生成哈希
async function hashPassword(password) {
    const saltRounds = 12;
    return await bcrypt.hash(password, saltRounds);
}

// 验证密码
async function verifyPassword(password, hash) {
    return await bcrypt.compare(password, hash);
}
```

#### Python
```python
import bcrypt

def hash_password(password: str) -> bytes:
    # 自动生成盐值
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode(), salt)

def verify_password(password: str, hashed: bytes) -> bool:
    return bcrypt.checkpw(password.encode(), hashed)
```

### 5.3 Argon2实现示例

#### Node.js
```javascript
const argon2 = require('argon2');

// 生成哈希
async function hashPassword(password) {
    return await argon2.hash(password, {
        type: argon2.argon2id,
        memoryCost: 65536, // 64MB
        timeCost: 3,
        parallelism: 4,
        hashLength: 32
    });
}

// 验证密码
async function verifyPassword(password, hash) {
    return await argon2.verify(hash, password);
}
```

#### Python
```python
from argon2 import PasswordHasher

ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16
)

# 生成哈希
hash = ph.hash("password")

# 验证密码
try:
    ph.verify(hash, "password")
    # 如果需要重新哈希（参数更新）
    if ph.check_needs_rehash(hash):
        new_hash = ph.hash("password")
except:
    # 验证失败
    pass
```

---

## 6. 算法选择决策矩阵

| 评估维度 | bcrypt | Argon2id | 建议 |
|---------|--------|----------|------|
| 安全强度 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Argon2更优 |
| 抗GPU攻击 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Argon2更优 |
| 内存要求 | 低 | 可配置（高） | 根据资源选择 |
| 标准化 | 是 | 是（PHC标准） | 两者皆可 |
| 语言支持 | 广泛 | 较广泛 | bcrypt更成熟 |
| 参数灵活性 | 有限 | 高度灵活 | Argon2更优 |

### 6.1 选择建议
1. **新系统首选**：Argon2id（内存充足的情况下）
2. **兼容性要求高**：bcrypt（库支持更广泛）
3. **资源受限环境**：bcrypt（内存消耗更低）
4. **最高安全要求**：Argon2id + 合理参数配置

---

## 7. 自适应策略实现

### 7.1 密码哈希验证器
```python
class PasswordHasher:
    def __init__(self):
        self.algorithm = self.detect_best_algorithm()
        
    def detect_best_algorithm(self):
        """自动检测最佳可用算法"""
        try:
            import argon2
            return 'argon2id'
        except ImportError:
            try:
                import bcrypt
                return 'bcrypt'
            except ImportError:
                raise RuntimeError("No suitable hashing library found")
    
    def hash(self, password: str) -> dict:
        """生成哈希，包含元数据"""
        if self.algorithm == 'argon2id':
            # Argon2实现
            return {
                'hash': argon2_hash,
                'algorithm': 'argon2id',
                'version': 'v19',
                'params': {'m': 65536, 't': 3, 'p': 4}
            }
        else:
            # bcrypt实现
            return {
                'hash': bcrypt_hash,
                'algorithm': 'bcrypt',
                'version': '2b',
                'params': {'cost': 12}
            }
    
    def verify(self, password: str, stored_hash: dict) -> bool:
        """验证密码，支持多种算法"""
        algorithm = stored_hash.get('algorithm')
        
        if algorithm == 'argon2id':
            return argon2_verify(password, stored_hash['hash'])
        elif algorithm == 'bcrypt':
            return bcrypt_verify(password, stored_hash['hash'])
        else:
            # 旧系统迁移路径
            return self.upgrade_and_verify(password, stored_hash)
```

### 7.2 渐进式升级策略
```yaml
升级流程:
  1. 验证现有哈希（支持旧算法）
  2. 检查是否需要重新哈希：
     - 工作因子不足
     - 使用过时算法
     - 安全参数变更
  3. 静默升级：下次成功登录时更新哈希
  4. 记录升级历史
  
迁移路径示例:
  MD5/SHA → bcrypt → Argon2id
```

---

## 8. 数据库设计建议

### 8.1 用户表结构
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    -- 密码哈希存储
    password_hash VARCHAR(255) NOT NULL,
    -- 算法标识
    hash_algorithm VARCHAR(20) DEFAULT 'argon2id',
    -- 哈希参数（JSON格式）
    hash_params JSONB,
    -- 创建和更新时间
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- 安全相关
    last_password_change TIMESTAMP,
    password_attempts INT DEFAULT 0,
    locked_until TIMESTAMP
);

-- 创建索引
CREATE INDEX idx_users_username ON users(username);
```

### 8.2 哈希参数存储示例
```json
{
  "algorithm": "argon2id",
  "version": "v19",
  "params": {
    "memory_cost": 65536,
    "time_cost": 3,
    "parallelism": 4,
    "salt": "base64_encoded_salt"
  },
  "created": "2024-01-15T10:30:00Z"
}
```

---

## 9. 安全最佳实践

### 9.1 密码策略
- 最小长度：12字符
- 禁用常见密码（top 1000密码列表）
- 实施密码强度计（zxcvbn库）
- 允许密码管理器生成的长密码

### 9.2 操作安全
```python
# 恒定时间比较
def constant_time_compare(val1, val2):
    """防止时序攻击的比较函数"""
    if len(val1) != len(val2):
        return False
    result = 0
    for x, y in zip(val1, val2):
        result |= ord(x) ^ ord(y)
    return result == 0
```

### 9.3 日志与监控
- 记录密码失败尝试（不含密码内容）
- 监控异常登录模式
- 设置密码尝试限制
- 实施账户锁定机制

---

## 10. 性能与可扩展性

### 10.1 基准测试建议
```python
def benchmark_hashing():
    """测试不同参数下的哈希性能"""
    test_cases = [
        ('bcrypt', 12, 'bcrypt哈希'),
        ('argon2id', {'m': 32768, 't': 2}, '低内存配置'),
        ('argon2id', {'m': 65536, 't': 3}, '推荐配置'),
    ]
    
    for algorithm, params, description in test_cases:
        start = time.time()
        # 执行哈希操作
        elapsed = time.time() - start
        print(f"{description}: {elapsed:.3f}秒")
        
    # 目标：单次哈希200-500ms
```

### 10.2 大规模部署考虑
- 使用硬件安全模块（HSM）存储主密钥
- 分布式系统中的盐值管理
- 缓存策略避免重复哈希
- 负载均衡下的参数一致性

---

## 11. 合规性要求

### 11.1 相关标准
- **NIST SP 800-63B**：数字身份指南
- **OWASP ASVS**：应用程序安全验证标准
- **PCI DSS**：支付卡行业数据安全标准
- **GDPR**：通用数据保护条例

### 11.2 审计要点
- 验证工作因子符合当前安全标准
- 检查盐值是否随机生成
- 确认无密码日志记录
- 验证哈希升级流程

---

## 12. 故障排除

### 12.1 常见问题
1. **性能问题**
   - 降低工作因子（临时方案）
   - 优化硬件资源
   - 实现异步哈希操作

2. **兼容性问题**
   - 跨平台盐值编码
   - 版本差异处理
   - 数据库编码设置

3. **升级问题**
   - 旧哈希迁移策略
   - 用户无密码重新设置流程
   - 回滚计划

### 12.2 调试检查清单
- [ ] 哈希验证返回预期结果
- [ ] 盐值每次唯一生成
- [ ] 工作因子符合安全要求
- [ ] 无敏感信息日志泄露
- [ ] 抗时序攻击实现

---

## 13. 附录

### 13.1 工作因子计算器
```python
def calculate_work_factor(target_ms=300):
    """
    根据目标时间计算合适的工作因子
    target_ms: 目标哈希时间（毫秒）
    返回：推荐的工作因子
    """
    base_time = 10  # 基础因子10的耗时
    # 实际实现需要基准测试数据
    # 返回调整后的工作因子
```

### 13.2 资源参考
- **Argon2规范**：https://github.com/P-H-C/phc-winner-argon2
- **bcrypt实现**：https://github.com/pyca/bcrypt
- **密码哈希指南**：https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- **安全建议**：https://www.nist.gov/itl/tig/projects/special-publication-800-63

---

## 文档更新记录

| 版本 | 日期 | 修改内容 | 修改人 |
|------|------|----------|--------|
| 1.0 | 2024-01-15 | 初始版本 | 安全团队 |
| 1.1 | 2024-01-20 | 添加Argon2参数建议 | 安全团队 |

---

**免责声明**：本文档提供技术指导，实际实施应根据具体安全需求、合规要求和性能测试结果进行调整。建议定期审查和更新密码存储策略以应对新的安全威胁。