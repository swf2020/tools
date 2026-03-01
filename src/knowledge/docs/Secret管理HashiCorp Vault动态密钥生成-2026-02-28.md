# HashiCorp Vault 动态密钥生成技术文档

## 1. 概述

### 1.1 文档目的
本文档详细阐述基于 HashiCorp Vault 的动态密钥管理方案，重点介绍动态密钥生成机制、架构设计、实施流程和最佳实践。

### 1.2 动态密钥与静态密钥对比

| 特性 | 静态密钥 | 动态密钥 |
|------|----------|----------|
| 生命周期 | 长期有效 | 短期临时 |
| 存储方式 | 持久化存储 | 按需生成，可配置生存时间 |
| 安全风险 | 泄露风险高 | 时间窗口有限，风险低 |
| 管理复杂度 | 轮换困难 | 自动轮换，管理简单 |
| 审计追踪 | 难以追溯使用情况 | 完整的使用审计日志 |

## 2. 架构设计

### 2.1 核心组件

```
┌─────────────────────────────────────────────────────────┐
│                   客户端应用                              │
├─────────────────────────────────────────────────────────┤
│                    Vault API 客户端                       │
├─────────────────────────────────────────────────────────┤
│                动态密钥生成引擎                          │
│  ├────────────────┬─────────────────┬─────────────────┤ │
│  │  数据库密钥    │  云服务凭证      │  SSH证书        │ │
│  │  (Database)    │  (Cloud)        │  (SSH CA)       │ │
│  └────────────────┴─────────────────┴─────────────────┘ │
├─────────────────────────────────────────────────────────┤
│                 策略与权限控制层                          │
├─────────────────────────────────────────────────────────┤
│                 存储后端                                 │
│  ├────────────────┬─────────────────┬─────────────────┤ │
│  │  加密存储      │  审计日志       │  租约管理       │ │
│  │  (Encrypted)   │  (Audit)        │  (Lease)        │ │
│  └────────────────┴─────────────────┴─────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 2.2 密钥生命周期管理

```
创建请求 → 验证授权 → 生成密钥 → 分发密钥 → 使用密钥 → 自动撤销
    ↓          ↓          ↓          ↓          ↓          ↓
  [TTL]      [策略]     [算法]     [传输]     [监控]     [清理]
```

## 3. 核心功能实现

### 3.1 数据库动态密钥生成

#### 3.1.1 配置数据库密钥引擎
```bash
# 启用数据库密钥引擎
vault secrets enable database

# 配置 PostgreSQL 连接
vault write database/config/postgresql \
  plugin_name=postgresql-database-plugin \
  allowed_roles="readonly,readwrite" \
  connection_url="postgresql://{{username}}:{{password}}@postgres:5432/myapp?sslmode=disable" \
  username="vaultadmin" \
  password="secure-password"

# 创建只读角色
vault write database/roles/readonly \
  db_name=postgresql \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; \
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
  default_ttl="1h" \
  max_ttl="24h"
```

#### 3.1.2 动态密钥获取流程
```python
import hvac
from sqlalchemy import create_engine

class VaultDatabaseCredentialManager:
    def __init__(self, vault_url, token):
        self.client = hvac.Client(url=vault_url, token=token)
    
    def get_temporary_credentials(self, role_name="readonly"):
        """获取临时数据库凭据"""
        try:
            # 请求动态密钥
            response = self.client.secrets.database.generate_credentials(
                name=role_name
            )
            
            credentials = response['data']
            return {
                'username': credentials['username'],
                'password': credentials['password'],
                'lease_id': credentials['lease_id'],
                'lease_duration': credentials['lease_duration']
            }
        except Exception as e:
            raise VaultCredentialError(f"Failed to get credentials: {str(e)}")
    
    def renew_lease(self, lease_id):
        """续租密钥"""
        return self.client.sys.renew_lease(lease_id)
```

### 3.2 AWS IAM 动态凭证

#### 3.2.1 AWS 密钥引擎配置
```bash
# 启用 AWS 密钥引擎
vault secrets enable aws

# 配置 AWS 访问
vault write aws/config/root \
  access_key=AKIAIOSFODNN7EXAMPLE \
  secret_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY \
  region=us-east-1

# 创建动态 IAM 角色
vault write aws/roles/s3-readonly \
  credential_type=iam_user \
  policy_document=-<<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::my-bucket/*",
        "arn:aws:s3:::my-bucket"
      ]
    }
  ]
}
EOF
```

#### 3.2.2 动态 AWS 凭证获取
```python
import boto3
from botocore.config import Config

class VaultAWSManager:
    def __init__(self, vault_client):
        self.vault = vault_client
    
    def get_temp_aws_credentials(self, role_name, ttl="3600s"):
        """获取临时 AWS 凭证"""
        creds = self.vault.secrets.aws.generate_credentials(
            name=role_name,
            ttl=ttl
        )
        
        return {
            'access_key': creds['data']['access_key'],
            'secret_key': creds['data']['secret_key'],
            'security_token': creds['data']['security_token'],
            'lease_id': creds['lease_id']
        }
    
    def create_s3_client(self, role_name):
        """创建使用临时凭证的 S3 客户端"""
        creds = self.get_temp_aws_credentials(role_name)
        
        session = boto3.Session(
            aws_access_key_id=creds['access_key'],
            aws_secret_access_key=creds['secret_key'],
            aws_session_token=creds['security_token']
        )
        
        return session.client('s3', config=Config(
            signature_version='s3v4',
            retries={'max_attempts': 3}
        ))
```

### 3.3 SSH CA 动态证书

#### 3.3.1 SSH 密钥引擎配置
```bash
# 启用 SSH 密钥引擎
vault secrets enable -path=ssh-client-signer ssh

# 生成 CA 密钥对
vault write ssh-client-signer/config/ca generate_signing_key=true

# 创建签名角色
vault write ssh-client-signer/roles/my-role \
  key_type=ca \
  allow_user_certificates=true \
  allowed_users="ubuntu,ec2-user" \
  default_extensions='{"permit-pty":""}' \
  ttl="30m"
```

#### 3.3.2 动态 SSH 证书签发
```python
import paramiko
from datetime import datetime, timedelta

class VaultSSHCertificateManager:
    def __init__(self, vault_client, public_key_path):
        self.vault = vault_client
        with open(public_key_path, 'r') as f:
            self.public_key = f.read()
    
    def sign_ssh_key(self, username, role="my-role"):
        """签发 SSH 证书"""
        response = self.vault.write(
            f"ssh-client-signer/sign/{role}",
            public_key=self.public_key,
            valid_principals=username,
            ttl="30m"
        )
        
        return response['data']['signed_key']
    
    def create_ssh_connection(self, hostname, username):
        """使用动态证书建立 SSH 连接"""
        signed_key = self.sign_ssh_key(username)
        
        # 创建临时证书文件
        with open('/tmp/temp_cert', 'w') as f:
            f.write(signed_key)
        
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        private_key = paramiko.RSAKey.from_private_key_file(
            '/path/to/private/key'
        )
        
        ssh.connect(
            hostname=hostname,
            username=username,
            pkey=private_key,
            passphrase=None,
            sock=None,
            look_for_keys=False,
            timeout=10,
            allow_agent=False,
            banner_timeout=30
        )
        
        return ssh
```

## 4. 高级配置

### 4.1 租约管理与续租

```yaml
# vault-config.hcl
storage "raft" {
  path = "/vault/data"
  node_id = "node1"
}

listener "tcp" {
  address = "0.0.0.0:8200"
  tls_disable = false
  tls_cert_file = "/vault/certs/cert.pem"
  tls_key_file = "/vault/certs/key.pem"
}

api_addr = "https://vault.example.com:8200"
cluster_addr = "https://node1.vault.example.com:8201"

# 租约配置
default_lease_ttl = "1h"
max_lease_ttl = "24h"

# 自动续租配置
enable_auto_renew = true
lease_renewal_threshold = "15m"
```

### 4.2 策略与权限控制

```hcl
# dynamic-secrets-policy.hcl
# 数据库密钥策略
path "database/creds/readonly" {
  capabilities = ["read"]
}

path "database/creds/readwrite" {
  capabilities = ["read"]
}

# AWS 凭证策略
path "aws/creds/s3-readonly" {
  capabilities = ["read"]
}

# SSH 证书策略
path "ssh-client-signer/sign/my-role" {
  capabilities = ["create", "update"]
}

# 租约管理策略
path "sys/renew/*" {
  capabilities = ["update"]
}

path "sys/leases/renew/*" {
  capabilities = ["update"]
}
```

## 5. 监控与审计

### 5.1 监控指标

```prometheus
# Prometheus 监控配置
vault_token_creation_total{type="dynamic"}
vault_lease_active_count{backend="database"}
vault_lease_expired_count{backend="aws"}
vault_secret_generation_duration_seconds{operation="generate"}
vault_audit_log_failed_events_total
```

### 5.2 审计日志配置

```bash
# 启用文件审计日志
vault audit enable file file_path=/vault/logs/audit.log

# 启用 Syslog 审计日志
vault audit enable syslog tag="vault" facility="LOCAL7"

# 查询审计日志
vault audit list -detailed
```

## 6. 安全最佳实践

### 6.1 网络与访问控制
1. **网络隔离**：Vault 集群部署在私有网络
2. **TLS 加密**：所有通信启用 TLS 1.3
3. **访问限制**：基于 IP 白名单限制访问
4. **防火墙规则**：仅开放必要的 API 端口

### 6.2 密钥管理策略
1. **最小权限原则**：按需分配最低必要权限
2. **短生命周期**：动态密钥 TTL 不超过 24 小时
3. **自动轮换**：定期自动轮换根密钥
4. **多因素认证**：敏感操作启用 MFA

### 6.3 灾难恢复
1. **自动备份**：定期备份加密的存储后端
2. **密钥分片**：使用 Shamir 密钥分片方案
3. **地理分布**：多区域部署提高可用性
4. **恢复演练**：定期进行灾难恢复演练

## 7. 故障排除

### 常见问题与解决方案

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| 密钥生成失败 | 权限不足 | 检查策略绑定和 token 权限 |
| 租约过期 | 未及时续租 | 实现自动续租机制 |
| 连接超时 | 网络问题 | 检查网络连通性和防火墙规则 |
| 性能下降 | 存储后端压力 | 监控存储性能，考虑分片 |
| 认证失败 | token 过期 | 实现 token 自动刷新逻辑 |

### 诊断命令
```bash
# 检查 Vault 状态
vault status

# 检查密钥引擎状态
vault secrets list -detailed

# 查看租约信息
vault list sys/leases/lookup/database/creds/readonly/

# 检查审计日志
tail -f /vault/logs/audit.log | jq .
```

## 8. 性能优化建议

### 8.1 缓存策略
```go
// 实现带缓存的凭证管理器
type CachedCredentialManager struct {
    vaultClient *hvac.Client
    cache       *ristretto.Cache
    ttl         time.Duration
}

func (c *CachedCredentialManager) GetCredentials(role string) (*Credentials, error) {
    // 先从缓存获取
    if creds, found := c.cache.Get(role); found {
        return creds.(*Credentials), nil
    }
    
    // 缓存未命中，从 Vault 获取
    creds, err := c.fetchFromVault(role)
    if err != nil {
        return nil, err
    }
    
    // 设置缓存
    c.cache.SetWithTTL(role, creds, 1, c.ttl/2)
    return creds, nil
}
```

### 8.2 连接池配置
```yaml
# Vault 客户端配置
vault:
  address: "https://vault.example.com:8200"
  token: "{{ vault_token }}"
  max_retries: 3
  timeout: "30s"
  
  # 连接池配置
  connection_pool:
    max_connections: 100
    max_connections_per_host: 10
    idle_timeout: "5m"
  
  # 重试策略
  retry:
    base_wait: "1s"
    max_wait: "30s"
```

## 9. 集成示例

### 9.1 Kubernetes 集成
```yaml
# vault-agent-sidecar.yaml
apiVersion: v1
kind: Pod
metadata:
  name: myapp
spec:
  serviceAccountName: myapp-sa
  containers:
  - name: myapp
    image: myapp:latest
    env:
    - name: DB_PASSWORD
      valueFrom:
        secretKeyRef:
          name: db-creds
          key: password
    - name: AWS_ACCESS_KEY_ID
      valueFrom:
        secretKeyRef:
          name: aws-creds
          key: access_key
  
  # Vault Agent Sidecar
  - name: vault-agent
    image: vault:latest
    env:
    - name: VAULT_ADDR
      value: "https://vault:8200"
    volumeMounts:
    - name: vault-token
      mountPath: /var/run/secrets/vaultproject.io
    args:
    - "agent"
    - "-config=/etc/vault/config.hcl"
```

### 9.2 CI/CD 流水线集成
```groovy
// Jenkins Pipeline 示例
pipeline {
    agent any
    
    environment {
        VAULT_ADDR = 'https://vault.company.com'
        VAULT_ROLE_ID = credentials('vault-role-id')
        VAULT_SECRET_ID = credentials('vault-secret-id')
    }
    
    stages {
        stage('Get Dynamic Credentials') {
            steps {
                script {
                    // 获取 Vault token
                    sh '''
                        VAULT_TOKEN=$(vault write -field=token auth/approle/login \
                            role_id=${VAULT_ROLE_ID} \
                            secret_id=${VAULT_SECRET_ID})
                        
                        # 获取数据库凭证
                        DB_CREDS=$(curl -s -H "X-Vault-Token: ${VAULT_TOKEN}" \
                            ${VAULT_ADDR}/v1/database/creds/readonly)
                        
                        export DB_USERNAME=$(echo ${DB_CREDS} | jq -r '.data.username')
                        export DB_PASSWORD=$(echo ${DB_CREDS} | jq -r '.data.password')
                    '''
                }
            }
        }
        
        stage('Run Database Migration') {
            steps {
                sh 'flyway migrate -user=${DB_USERNAME} -password=${DB_PASSWORD}'
            }
        }
    }
    
    post {
        always {
            // 清理敏感数据
            sh 'unset DB_USERNAME DB_PASSWORD VAULT_TOKEN'
        }
    }
}
```

## 10. 总结

HashiCorp Vault 的动态密钥生成机制提供了安全、可控、可审计的密钥管理方案。通过实施本方案，组织可以：

1. **显著降低密钥泄露风险**：密钥生命周期短，自动回收
2. **简化密钥管理**：自动化轮换和分发
3. **增强审计能力**：完整的密钥使用日志
4. **提高合规性**：满足安全标准和监管要求
5. **提升开发效率**：自助式密钥服务，减少运维依赖

建议在生产环境部署前，先在测试环境充分验证，并根据具体业务需求调整配置参数。定期审查和更新安全策略，确保密钥管理方案持续有效。