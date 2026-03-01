# 敏感数据加密方案：AES-256-GCM与RSA-OAEP综合应用技术文档

## 1. 文档概述

### 1.1 文档目的
本文档旨在提供一套完整的敏感数据加密解决方案，综合运用AES-256-GCM对称加密和RSA-OAEP非对称加密技术，确保数据在传输和存储过程中的机密性、完整性与认证性。

### 1.2 适用范围
适用于需要处理以下敏感数据的系统：
- 个人身份信息（PII）
- 金融交易数据
- 医疗健康信息
- 企业核心业务数据
- 认证凭据和密钥材料

## 2. 加密方案架构

### 2.1 混合加密体系
```
┌─────────────────────────────────────────────────┐
│                  敏感原始数据                    │
└─────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│           步骤1：生成随机AES密钥(256位)         │
└─────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│  步骤2：使用AES-256-GCM加密数据（高效对称加密）  │
│  - 输出：密文 + 认证标签(GCM标签)              │
└─────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│   步骤3：使用RSA-OAEP加密AES密钥（安全密钥交换） │
│   - 使用接收方RSA公钥加密                      │
└─────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│        最终传输/存储包：                        │
│        RSA(加密的AES密钥) + AES-GCM(加密数据)   │
└─────────────────────────────────────────────────┘
```

### 2.2 组件职责
- **AES-256-GCM**：数据主体加密，提供高效的大数据加密和完整性验证
- **RSA-OAEP**：密钥加密，解决密钥安全分发问题
- **GCM认证标签**：防止密文被篡改

## 3. AES-256-GCM技术详述

### 3.1 算法特性
```
算法类型：对称加密/认证加密
密钥长度：256位（32字节）
块大小：128位
工作模式：GCM（Galois/Counter Mode）
安全特性：
  ✓ 机密性：AES-CTR模式加密
  ✓ 完整性：GMAC认证
  ✓ 认证性：生成认证标签
  ✓ 无需填充：CTR模式避免填充Oracle攻击
```

### 3.2 关键参数
```python
# 伪代码示例
aes_key = generate_random(32)      # 32字节 = 256位
nonce = generate_random(12)        # 推荐12字节
additional_data = b"metadata"      # 附加认证数据(AAD)
```

### 3.3 安全要点
1. **Nonce管理**：每个密钥下nonce必须唯一
2. **密钥生命周期**：定期轮换加密密钥
3. **认证标签验证**：解密时必须验证标签

## 4. RSA-OAEP技术详述

### 4.1 算法特性
```
算法类型：非对称加密
填充方案：OAEP（Optimal Asymmetric Encryption Padding）
哈希函数：SHA-256（推荐）
密钥长度：≥2048位（推荐3072或4096位）
安全特性：
  ✓ 抵抗选择密文攻击
  ✓ 确定性填充增强安全性
  ✓ 与PKCS#1 v1.5相比更安全
```

### 4.2 密钥规格
```python
# 密钥对生成要求
rsa_key_size = 3072               # 最小2048，推荐3072+
hash_algorithm = "SHA-256"        # OAEP使用的哈希算法
mgf_hash = "SHA-256"              # 掩码生成函数哈希
```

### 4.3 容量限制
- 最大加密数据长度：`密钥长度(字节) - 2*哈希长度 - 2`
- 示例：3072位RSA密钥可加密约190字节数据

## 5. 组合实施方案

### 5.1 加密流程
```python
"""
完整加密流程伪代码
"""
def hybrid_encrypt(plaintext: bytes, rsa_public_key) -> dict:
    # 1. 生成随机AES密钥
    aes_key = generate_random_aes_key(256)
    
    # 2. 生成GCM nonce
    nonce = generate_random_nonce(12)
    
    # 3. AES-GCM加密数据
    ciphertext, auth_tag = aes_gcm_encrypt(
        plaintext=plaintext,
        key=aes_key,
        nonce=nonce,
        aad=b"context_data"
    )
    
    # 4. RSA-OAEP加密AES密钥
    encrypted_key = rsa_oaep_encrypt(
        plaintext=aes_key,
        public_key=rsa_public_key,
        hash_algo="SHA-256"
    )
    
    return {
        "version": "1.0",
        "encrypted_key": encrypted_key,      # RSA加密的AES密钥
        "nonce": nonce,                      # GCM nonce
        "ciphertext": ciphertext,           # AES加密的数据
        "auth_tag": auth_tag,               # GCM认证标签
        "aad": b"context_data",             # 附加认证数据
        "timestamp": current_timestamp()
    }
```

### 5.2 解密流程
```python
def hybrid_decrypt(encrypted_package: dict, rsa_private_key) -> bytes:
    # 1. RSA-OAEP解密AES密钥
    aes_key = rsa_oaep_decrypt(
        ciphertext=encrypted_package["encrypted_key"],
        private_key=rsa_private_key,
        hash_algo="SHA-256"
    )
    
    # 2. AES-GCM解密并验证数据
    plaintext = aes_gcm_decrypt(
        ciphertext=encrypted_package["ciphertext"],
        key=aes_key,
        nonce=encrypted_package["nonce"],
        auth_tag=encrypted_package["auth_tag"],
        aad=encrypted_package.get("aad", b"")
    )
    
    return plaintext
```

## 6. 密钥管理方案

### 6.1 分层密钥体系
```
┌─────────────────┐
│  主密钥(HSM)    │  ← 存储在硬件安全模块
└─────────────────┘
        │
        ▼
┌─────────────────┐
│ 数据加密密钥    │  ← AES-256密钥，定期轮换
└─────────────────┘
        │
        ▼
┌─────────────────┐
│  用户会话密钥   │  ← 临时密钥，单次使用
└─────────────────┘
```

### 6.2 密钥生命周期管理
| 阶段 | RSA密钥 | AES密钥 |
|------|---------|---------|
| 生成 | 安全随机生成 | 安全随机生成 |
| 存储 | HSM或KMS | 加密存储 |
| 使用 | 密钥交换 | 数据加密 |
| 轮换 | 1-2年 | 90天或特定数据量 |
| 撤销 | 证书吊销列表 | 从活动密钥库移除 |
| 销毁 | 安全擦除 | 安全擦除 |

## 7. 性能与安全考量

### 7.1 性能比较
```
操作                相对性能     适用场景
─────────────────────────────────────────────
AES-256-GCM        非常高       大数据体加密
RSA-OAEP-3072       低         小数据/密钥加密
RSA解密              中         密钥解密
```

### 7.2 安全配置建议
```yaml
security_configuration:
  aes_gcm:
    key_size: 256
    nonce_size: 12
    auth_tag_size: 16
    max_encryptions_per_key: 2^32
    
  rsa_oaep:
    key_size: 3072
    hash_algorithm: SHA-256
    mgf_hash: SHA-256
    label: "key_encryption"
    
  key_management:
    key_rotation:
      aes: "90d OR 2^32 encryptions"
      rsa: "365d"
    key_storage: "HSM or KMS"
    key_backup: "encrypted with master key"
```

## 8. 实施指南

### 8.1 代码示例（Python）
```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
import os
import time

class HybridEncryptionSystem:
    def __init__(self, rsa_key_size=3072):
        self.rsa_key_size = rsa_key_size
        
    def generate_rsa_keypair(self):
        """生成RSA密钥对"""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=self.rsa_key_size
        )
        public_key = private_key.public_key()
        return private_key, public_key
    
    def encrypt_data(self, plaintext: bytes, public_key) -> dict:
        """混合加密数据"""
        # 生成AES密钥
        aes_key = os.urandom(32)  # 256-bit key
        
        # 生成nonce
        nonce = os.urandom(12)
        
        # AES-GCM加密
        aesgcm = AESGCM(aes_key)
        aad = b"authenticated but unencrypted data"
        ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
        
        # 分离密文和认证标签（GCM自动处理）
        # 注意：实际实现中需要正确处理标签
        
        # RSA-OAEP加密AES密钥
        encrypted_key = public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        return {
            "version": "1.0",
            "encrypted_key": encrypted_key,
            "nonce": nonce,
            "ciphertext": ciphertext,
            "aad": aad,
            "timestamp": int(time.time())
        }
    
    def decrypt_data(self, encrypted_package: dict, private_key) -> bytes:
        """解密数据"""
        # RSA解密AES密钥
        aes_key = private_key.decrypt(
            encrypted_package["encrypted_key"],
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        # AES-GCM解密
        aesgcm = AESGCM(aes_key)
        plaintext = aesgcm.decrypt(
            encrypted_package["nonce"],
            encrypted_package["ciphertext"],
            encrypted_package["aad"]
        )
        
        return plaintext
```

### 8.2 错误处理与验证
```python
class EncryptionError(Exception):
    """加密相关异常基类"""
    pass

class IntegrityError(EncryptionError):
    """完整性验证失败"""
    pass

def safe_decrypt(encrypted_data: dict, private_key) -> bytes:
    """
    安全的解密操作，包含完整验证
    """
    try:
        # 验证必要字段存在
        required_fields = ["encrypted_key", "nonce", "ciphertext"]
        for field in required_fields:
            if field not in encrypted_data:
                raise ValueError(f"Missing required field: {field}")
        
        # 验证nonce长度
        if len(encrypted_data["nonce"]) != 12:
            raise ValueError("Invalid nonce length")
        
        # 解密
        decrypted = decrypt_data(encrypted_data, private_key)
        
        # 记录解密成功（审计日志）
        log_decryption_event(encrypted_data.get("timestamp"))
        
        return decrypted
        
    except Exception as e:
        # 记录解密失败（安全监控）
        log_decryption_failure(e)
        raise IntegrityError("Decryption failed") from e
```

## 9. 合规性与最佳实践

### 9.1 合规标准参考
- **NIST SP 800-57**：密钥管理建议
- **FIPS 140-3**：加密模块验证
- **PCI DSS**：支付卡行业数据安全
- **GDPR**：个人数据保护
- **HIPAA**：医疗信息安全

### 9.2 实施检查清单
- [ ] 使用安全随机数生成器
- [ ] 实现完整的密钥生命周期管理
- [ ] 启用完整性验证（GCM标签）
- [ ] 记录所有加密/解密操作
- [ ] 定期进行安全审计
- [ ] 实现密钥轮换机制
- [ ] 使用HSM存储根密钥
- [ ] 实施访问控制和最小权限原则

## 10. 监控与审计

### 10.1 关键监控指标
```python
encryption_metrics = {
    "encryption_operations": "加密操作次数",
    "decryption_operations": "解密操作次数",
    "failed_decryptions": "解密失败次数",
    "key_rotation_events": "密钥轮换事件",
    "encryption_latency": "加密延迟分布",
    "decryption_latency": "解密延迟分布"
}
```

### 10.2 审计日志要求
```
时间戳 | 操作类型 | 密钥ID | 数据标识 | 操作状态 | 执行者 | IP地址
-------------------------------------------------------------------
2024-01-15T10:30:00Z | ENCRYPT | key_abc123 | user_456 | SUCCESS | app_srv | 10.0.1.5
2024-01-15T10:31:00Z | DECRYPT | key_abc123 | user_456 | SUCCESS | app_srv | 10.0.1.5
2024-01-15T10:32:00Z | DECRYPT | key_abc123 | unknown  | FAILURE | app_srv | 10.0.2.8
```

## 11. 总结

AES-256-GCM与RSA-OAEP的组合提供了一种安全、高效的敏感数据加密方案：

1. **安全性**：同时满足机密性、完整性和认证性要求
2. **性能**：利用对称加密处理大数据，非对称加密解决密钥分发
3. **标准化**：采用行业认可的标准算法
4. **灵活性**：适用于多种应用场景和合规要求

实施本方案时，需重点关注密钥管理、安全配置和监控审计，确保加密体系的全生命周期安全。

---

**文档版本**: 1.0  
**最后更新**: 2024年1月  
**作者**: 加密技术架构组  
**批准状态**: 草案/已批准  
**适用范围**: 公司内部技术规范