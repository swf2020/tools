# Kubernetes ResourceQuota与LimitRange资源治理技术文档

## 1. 概述

### 1.1 文档目的
本文档旨在详细说明Kubernetes中ResourceQuota和LimitRange两种资源治理机制的原理、配置方法及最佳实践，帮助集群管理员有效管理多租户环境下的计算资源分配。

### 1.2 背景与价值
随着Kubernetes在企业的广泛应用，多团队、多项目共享同一集群成为常态。缺乏有效的资源治理会导致：
- 资源争用引发的应用性能问题
- "嘈杂邻居"效应影响关键业务
- 资源浪费与成本不可控
- 安全风险（资源耗尽攻击）

ResourceQuota和LimitRange提供了Namespace级别的资源治理能力，是实现集群资源公平分配、成本控制和稳定运行的关键机制。

## 2. ResourceQuota详解

### 2.1 核心概念
ResourceQuota用于限制Namespace级别的资源总量，确保单个Namespace不会消耗过多集群资源。

### 2.2 支持限制的资源类型

#### 2.2.1 计算资源
```yaml
# 示例：计算资源配额
resources:
  requests.cpu: "4"           # CPU请求总量限制
  requests.memory: "8Gi"      # 内存请求总量限制
  limits.cpu: "8"             # CPU限制总量
  limits.memory: "16Gi"       # 内存限制总量
```

#### 2.2.2 存储资源
```yaml
# 示例：存储资源配额
resources:
  requests.storage: "100Gi"   # 存储请求总量
  persistentvolumeclaims: "10" # PVC数量限制
  <storage-class-name>.storageclass.storage.k8s.io/requests.storage: "50Gi" # 特定存储类限制
```

#### 2.2.3 对象数量
```yaml
# 示例：Kubernetes对象数量配额
resources:
  pods: "30"                  # Pod数量
  services: "10"              # Service数量
  services.loadbalancers: "2" # 负载均衡器类型Service
  services.nodeports: "5"     # NodePort类型Service
  configmaps: "20"            # ConfigMap数量
  secrets: "20"               # Secret数量
  replicationcontrollers: "5" # ReplicationController数量
  resourcequotas: "2"         # ResourceQuota数量（限制配额对象自身）
```

### 2.3 ResourceQuota配置示例

#### 2.3.1 基础配额配置
```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-a-quota
  namespace: team-a
spec:
  hard:
    # 计算资源
    requests.cpu: "2"
    requests.memory: "4Gi"
    limits.cpu: "4"
    limits.memory: "8Gi"
    
    # 对象数量
    pods: "20"
    services: "5"
    persistentvolumeclaims: "5"
    
    # 存储资源
    requests.storage: "50Gi"
```

#### 2.3.2 作用域配额（Scoped Quotas）
```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: scoped-quota
  namespace: production
spec:
  hard:
    pods: "50"
    requests.cpu: "10"
    requests.memory: "20Gi"
  scopes:
  - BestEffort      # 仅限制未设置资源请求的Pod
  # - NotTerminating # 仅限制非终止状态的Pod
  # - Terminating    # 仅限制终止状态的Pod
  # - PriorityClass  # 按优先级类限制（需指定优先级类名）
```

#### 2.3.3 按优先级配额
```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: priority-quota
  namespace: critical
spec:
  hard:
    pods: "10"
    requests.cpu: "4"
    requests.memory: "8Gi"
  scopeSelector:
    matchExpressions:
    - operator: In
      scopeName: PriorityClass
      values: ["high-priority"]  # 仅限制使用high-priority优先级类的资源
```

### 2.4 配额管理与监控

#### 2.4.1 查看配额使用情况
```bash
# 查看特定Namespace的配额
kubectl describe resourcequota <quota-name> -n <namespace>

# 查看所有Namespace的配额使用
kubectl get resourcequota --all-namespaces

# 获取详细JSON格式信息
kubectl get resourcequota <quota-name> -n <namespace> -o json
```

#### 2.4.2 配额使用示例输出
```
Name:            team-a-quota
Namespace:       team-a
Resource         Used   Hard
--------         ----   ----
limits.cpu       3      4
limits.memory    6Gi    8Gi
pods             15     20
requests.cpu     1.5    2
requests.memory  3Gi    4Gi
```

## 3. LimitRange详解

### 3.1 核心概念
LimitRange为Namespace中的Pod和容器设置默认的资源请求和限制，并验证资源设置的合规性。

### 3.2 支持的限制类型

#### 3.2.1 容器级别限制
```yaml
# 容器资源限制配置
limits:
- type: Container
  default:
    cpu: "500m"      # 容器默认CPU限制
    memory: "512Mi"  # 容器默认内存限制
  defaultRequest:
    cpu: "100m"      # 容器默认CPU请求
    memory: "128Mi"  # 容器默认内存请求
  max:
    cpu: "2"         # 容器最大CPU限制
    memory: "2Gi"    # 容器最大内存限制
  min:
    cpu: "50m"       # 容器最小CPU请求
    memory: "64Mi"   # 容器最小内存请求
  maxLimitRequestRatio:
    cpu: "4"         # 限制与请求的最大比率（CPU）
    memory: "4"      # 限制与请求的最大比率（内存）
```

#### 3.2.2 Pod级别限制
```yaml
# Pod资源限制配置
limits:
- type: Pod
  max:
    cpu: "4"         # Pod所有容器CPU限制总和最大值
    memory: "4Gi"    # Pod所有容器内存限制总和最大值
```

#### 3.2.3 持久卷声明限制
```yaml
# PVC资源限制配置
limits:
- type: PersistentVolumeClaim
  min:
    storage: "1Gi"   # PVC最小存储请求
  max:
    storage: "10Gi"  # PVC最大存储请求
```

### 3.3 LimitRange配置示例

#### 3.3.1 完整配置示例
```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: standard-limits
  namespace: application
spec:
  limits:
  # 容器资源限制
  - type: Container
    default:
      cpu: "500m"
      memory: "512Mi"
    defaultRequest:
      cpu: "100m"
      memory: "128Mi"
    max:
      cpu: "2"
      memory: "2Gi"
    min:
      cpu: "50m"
      memory: "64Mi"
    maxLimitRequestRatio:
      cpu: "4"
      memory: "3"
  
  # Pod资源限制
  - type: Pod
    max:
      cpu: "4"
      memory: "4Gi"
  
  # PVC资源限制
  - type: PersistentVolumeClaim
    min:
      storage: "1Gi"
    max:
      storage: "10Gi"
```

#### 3.3.2 按容器类型差异化配置
```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: workload-specific-limits
  namespace: production
spec:
  limits:
  # 初始化容器限制
  - type: Container
    max:
      cpu: "1"
      memory: "512Mi"
    min:
      cpu: "10m"
      memory: "16Mi"
    default:
      cpu: "100m"
      memory: "128Mi"
    defaultRequest:
      cpu: "10m"
      memory: "16Mi"
  
  # 应用容器限制
  - type: Container
    max:
      cpu: "2"
      memory: "2Gi"
    min:
      cpu: "100m"
      memory: "128Mi"
    default:
      cpu: "500m"
      memory: "512Mi"
    defaultRequest:
      cpu: "200m"
      memory: "256Mi"
```

### 3.4 LimitRange验证机制

#### 3.4.1 创建时验证
当创建或更新Pod、容器、PVC时，LimitRange会验证：
1. 资源请求和限制是否在min/max范围内
2. 限制与请求比率是否合规
3. 是否设置了必要的资源请求/限制

#### 3.4.2 默认值注入
如果Pod/容器未设置资源请求或限制，LimitRange会自动注入默认值：
```yaml
# 用户创建的Pod（未设置资源）
apiVersion: v1
kind: Pod
metadata:
  name: example-pod
spec:
  containers:
  - name: app
    image: nginx:latest

# LimitRange注入后的Pod
apiVersion: v1
kind: Pod
metadata:
  name: example-pod
spec:
  containers:
  - name: app
    image: nginx:latest
    resources:
      requests:
        cpu: "100m"    # 来自defaultRequest
        memory: "128Mi"
      limits:
        cpu: "500m"    # 来自default
        memory: "512Mi"
```

## 4. ResourceQuota与LimitRange协同工作

### 4.1 联合使用场景

#### 4.1.1 完整资源治理方案
```yaml
# 步骤1：创建Namespace
apiVersion: v1
kind: Namespace
metadata:
  name: project-alpha

---
# 步骤2：应用LimitRange（设置默认值和约束）
apiVersion: v1
kind: LimitRange
metadata:
  name: project-alpha-limits
  namespace: project-alpha
spec:
  limits:
  - type: Container
    default:
      cpu: "200m"
      memory: "256Mi"
    defaultRequest:
      cpu: "50m"
      memory: "64Mi"
    max:
      cpu: "1"
      memory: "1Gi"

---
# 步骤3：应用ResourceQuota（设置总量限制）
apiVersion: v1
kind: ResourceQuota
metadata:
  name: project-alpha-quota
  namespace: project-alpha
spec:
  hard:
    requests.cpu: "4"
    requests.memory: "8Gi"
    limits.cpu: "8"
    limits.memory: "16Gi"
    pods: "20"
```

#### 4.1.2 工作流程
1. **创建资源时**：
   - LimitRange验证并设置默认值
   - ResourceQuota检查Namespace剩余配额
   - 配额充足则创建成功

2. **更新资源时**：
   - LimitRange验证新值合规性
   - ResourceQuota检查配额变化
   - 符合限制则更新成功

3. **删除资源时**：
   - 释放的资源会计入Namespace可用配额

### 4.2 优先级与冲突处理

#### 4.2.1 配置优先级
1. **LimitRange验证优先**：先验证单个资源合规性
2. **ResourceQuota检查次之**：再验证Namespace总量
3. **拒绝策略**：任一检查失败则拒绝操作

#### 4.2.2 常见冲突场景
```yaml
# 场景：LimitRange允许但ResourceQuota不允许
# LimitRange配置
max.cpu: "2"          # 允许单个容器使用最多2核CPU

# ResourceQuota配置
requests.cpu: "3"     # Namespace总共只允许3核CPU

# 结果：第一个使用2核CPU的Pod可以创建
#       第二个请求1.5核CPU的Pod会被拒绝（超出总量限制）
```

## 5. 最佳实践与策略

### 5.1 配额设计原则

#### 5.1.1 按团队/项目分配
```yaml
# 开发环境：宽松配额
开发团队：
  requests.cpu: "8"
  requests.memory: "16Gi"
  pods: "50"

# 测试环境：中等配额
测试团队：
  requests.cpu: "4"
  requests.memory: "8Gi"
  pods: "30"

# 生产环境：严格配额
生产应用：
  requests.cpu: "16"
  requests.memory: "32Gi"
  pods: "20"          # 较少但更稳定的Pod
```

#### 5.1.2 按应用类型分配
```yaml
# Web服务
resources:
  requests.cpu: "2"
  requests.memory: "4Gi"
  pods: "10"

# 批处理任务
resources:
  requests.cpu: "8"
  requests.memory: "16Gi"
  pods: "5"           # 较少但资源密集的Pod

# 数据库服务
resources:
  requests.cpu: "4"
  requests.memory: "8Gi"
  persistentvolumeclaims: "3"
```

### 5.2 监控与告警

#### 5.2.1 配额使用率监控
```yaml
# Prometheus监控规则示例
groups:
- name: quota_usage
  rules:
  - alert: HighQuotaUsage
    expr: |
      # CPU请求使用率 > 80%
      sum(kube_resourcequota{resource="requests.cpu", type="used"})
      / sum(kube_resourcequota{resource="requests.cpu", type="hard"})
      > 0.8
    for: 10m
    annotations:
      description: 'Namespace {{ $labels.namespace }} CPU请求使用率超过80%'
  
  - alert: QuotaExhausted
    expr: |
      # 任何资源配额已用尽
      kube_resourcequota{resource=~"requests\\.(cpu|memory)", type="used"}
      == kube_resourcequota{resource=~"requests\\.(cpu|memory)", type="hard"}
    annotations:
      description: 'Namespace {{ $labels.namespace }} {{ $labels.resource }}配额已用尽'
```

#### 5.2.2 资源使用趋势分析
```bash
# 获取配额使用趋势
kubectl get resourcequota --all-namespaces -w

# 使用kubectl-top监控实际使用
kubectl top pods --all-namespaces
kubectl top nodes
```

### 5.3 动态配额调整策略

#### 5.3.1 基于时间调整
```yaml
# 工作日与周末差异配置（通过配置管理工具实现）
workday_quota:
  requests.cpu: "10"
  requests.memory: "20Gi"

weekend_quota:
  requests.cpu: "4"
  requests.memory: "8Gi"
```

#### 5.3.2 基于事件调整
```python
# 伪代码：基于事件的自动配额扩展
def auto_scale_quota(namespace, metric, threshold):
    current_usage = get_quota_usage(namespace, metric)
    current_limit = get_quota_limit(namespace, metric)
    
    if current_usage > threshold * current_limit:
        new_limit = current_limit * 1.5  # 扩展50%
        update_quota(namespace, metric, new_limit)
        send_alert(f"Quota expanded for {namespace}: {metric}")
```

## 6. 故障排查与常见问题

### 6.1 常见错误与解决方案

#### 6.1.1 资源创建失败
```bash
# 错误：超出ResourceQuota限制
Error from server (Forbidden): pods "web-app" is forbidden:
exceeded quota: team-quota, requested: requests.cpu=500m,
used: requests.cpu=1.8, limited: requests.cpu=2

# 解决方案：
1. 查看当前配额使用：kubectl describe resourcequota -n <namespace>
2. 释放不需要的资源
3. 调整配额限制（如有必要）
4. 优化应用资源请求
```

#### 6.1.2 资源配置被拒绝
```bash
# 错误：违反LimitRange限制
Error from server (Forbidden): pods "high-mem-pod" is forbidden:
maximum memory usage per Container is 1Gi, but limit is 2Gi

# 解决方案：
1. 查看LimitRange限制：kubectl describe limitrange -n <namespace>
2. 调整资源配置至允许范围内
3. 或修改LimitRange配置（谨慎操作）
```

### 6.2 诊断工具与命令

#### 6.2.1 配额诊断命令
```bash
# 查看Namespace所有限制
kubectl describe namespace <namespace-name>

# 查看配额详细信息
kubectl get resourcequota -n <namespace> -o yaml

# 查看LimitRange配置
kubectl get limitrange -n <namespace> -o yaml

# 模拟创建资源（dry-run）
kubectl create -f pod.yaml -n <namespace> --dry-run=client
```

#### 6.2.2 资源使用分析
```bash
# 分析资源请求与限制
kubectl get pods -n <namespace> -o=custom-columns=\
'NAME:.metadata.name,\
CPU_REQ:.spec.containers[*].resources.requests.cpu,\
CPU_LIM:.spec.containers[*].resources.limits.cpu,\
MEM_REQ:.spec.containers[*].resources.requests.memory,\
MEM_LIM:.spec.containers[*].resources.limits.memory'

# 导出配额报告
kubectl get resourcequota --all-namespaces -o json > quota-report.json
```

## 7. 安全与权限管理

### 7.1 RBAC配置示例

#### 7.1.1 管理员权限
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: quota-admin
rules:
- apiGroups: [""]
  resources: ["resourcequotas", "limitranges"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: quota-admin-binding
subjects:
- kind: User
  name: "cluster-admin@company.com"
  apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: quota-admin
  apiGroup: rbac.authorization.k8s.io
```

#### 7.1.2 开发团队权限
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  namespace: team-a
  name: quota-viewer
rules:
- apiGroups: [""]
  resources: ["resourcequotas", "limitranges"]
  verbs: ["get", "list", "watch"]  # 仅查看权限
```

### 7.2 配额审计

#### 7.2.1 审计日志配置
```yaml
# kube-apiserver审计策略
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
- level: RequestResponse
  resources:
  - group: ""  # core API group
    resources: ["resourcequotas", "limitranges"]
```

#### 7.2.2 审计日志分析
```bash
# 查看配额相关操作
kubectl logs kube-apiserver-node-1 | grep -E "(resourcequota|limitrange)"

# 使用审计工具分析
kubectl-audit --resource resourcequota --action create
```

## 8. 附录

### 8.1 资源单位说明
- CPU单位：`1` = 1核，`500m` = 0.5核，`100m` = 0.1核
- 内存单位：`1Gi` = 1024Mi，`1Mi` = 1024Ki，`1Ki` = 1024字节
- 存储单位：同上，支持Ki/Mi/Gi/Ti/Pi/Ei二进制前缀

### 8.2 版本兼容性
| Kubernetes版本 | ResourceQuota特性 | LimitRange特性 |
|---------------|------------------|---------------|
| 1.9+ | 作用域配额，优先级类配额 | 完整功能支持 |
| 1.6-1.8 | 基础配额支持 | 基础功能支持 |
| <1.6 | 有限支持 | 有限支持 |

### 8.3 相关工具与扩展
- **Kubecost**：成本分析与配额优化
- **Goldilocks**：资源请求推荐工具
- **Krane**：配额管理与报告
- **自定义控制器**：动态配额调整

---

## 总结

ResourceQuota和LimitRange是Kubernetes多租户资源治理的核心组件，通过合理的配置和使用，可以实现：

1. **资源公平分配**：确保各团队/项目获得合理资源份额
2. **成本控制**：防止资源浪费，优化集群使用效率
3. **稳定性保障**：避免资源耗尽导致的集群故障
4. **安全隔离**：限制潜在风险的影响范围

建议在生产环境中结合监控、告警和定期审计，构建完整的资源治理体系，并根据实际使用情况持续优化配额策略。

**文档版本**: 1.0  
**最后更新**: 2024年1月  
**适用版本**: Kubernetes 1.20+