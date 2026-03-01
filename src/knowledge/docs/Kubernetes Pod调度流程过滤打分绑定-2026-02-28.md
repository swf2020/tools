# Kubernetes Pod调度流程详解：过滤、打分、绑定

## 1. 概述

Kubernetes调度器（kube-scheduler）负责将新创建的Pod分配到集群中的合适节点上运行。调度决策是一个多阶段的过程，主要分为三个核心阶段：**过滤（Filtering）**、**打分（Scoring）** 和**绑定（Binding）**。

## 2. 调度流程总览

```
创建Pod → 加入调度队列 → 调度周期开始 → 过滤阶段 → 打分阶段 → 绑定阶段 → 调度完成
```

## 3. 详细阶段解析

### 3.1 过滤阶段（Filtering/Predicates）

**目的**：从所有可用节点中筛选出符合Pod运行要求的候选节点

**关键检查项**：

| 检查类型 | 说明 |
|---------|------|
| **资源检查** | 节点是否有足够的CPU、内存、存储资源 |
| **节点选择器** | 节点标签是否匹配Pod的nodeSelector |
| **节点亲和性** | 检查节点亲和性规则（nodeAffinity） |
| **污点和容忍** | 检查Pod是否容忍节点的污点（Taints） |
| **端口冲突** | 节点上请求的端口是否已被占用 |
| **卷限制** | 节点是否支持Pod请求的卷类型 |
| **拓扑约束** | 检查拓扑域限制（如zone、region分布） |

**示例**：
```yaml
# Pod的节点亲和性示例
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
      - matchExpressions:
        - key: gpu-type
          operator: In
          values: ["nvidia-tesla-v100"]
```

### 3.2 打分阶段（Scoring/Priorities）

**目的**：对过滤后的候选节点进行评分，选择最优节点

**评分策略**：

| 评分策略 | 权重 | 说明 |
|---------|------|------|
| **LeastRequestedPriority** | 默认 | 选择资源使用率最低的节点 |
| **BalancedResourceAllocation** | 默认 | 平衡CPU和内存使用率 |
| **NodeAffinityPriority** | 可变 | 基于节点亲和性规则评分 |
| **TaintTolerationPriority** | 可变 | 基于污点容忍度评分 |
| **ImageLocalityPriority** | 低 | 优先选择已缓存所需镜像的节点 |
| **InterPodAffinityPriority** | 高 | 检查Pod间亲和性/反亲和性 |

**评分计算**：
```
最终得分 = ∑(评分函数权重 × 评分函数结果)
```

### 3.3 绑定阶段（Binding）

**目的**：将Pod绑定到选定的节点

**执行步骤**：
1. 调度器向API Server发送绑定请求
2. API Server更新Pod的nodeName字段
3. 目标节点的kubelet检测到新Pod
4. kubelet执行Pod创建流程

**注意**：绑定是异步操作，如果失败会重新调度

## 4. 调度器扩展机制

### 4.1 调度框架（Scheduling Framework）
Kubernetes 1.15+引入了可插拔的调度框架

**扩展点**：
 - **QueueSort**：自定义排序策略
 - **PreFilter**：预处理检查
 - **Filter**：替换/增强过滤逻辑
 - **PostFilter**：无合适节点时的处理
 - **Score**：自定义评分逻辑
 - **Bind**：自定义绑定逻辑

### 4.2 调度器配置
```yaml
apiVersion: kubescheduler.config.k8s.io/v1beta3
kind: KubeSchedulerConfiguration
profiles:
  - schedulerName: default-scheduler
    plugins:
      filter:
        enabled:
          - name: NodeAffinity
          - name: NodeResourcesFit
      score:
        enabled:
          - name: NodeResourcesBalancedAllocation
            weight: 1
          - name: ImageLocality
            weight: 1
```

## 5. 高级调度特性

### 5.1 Pod亲和性/反亲和性
```yaml
affinity:
  podAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
    - labelSelector:
        matchExpressions:
        - key: app
          operator: In
          values: ["store"]
      topologyKey: "kubernetes.io/hostname"
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
    - weight: 100
      podAffinityTerm:
        labelSelector:
          matchExpressions:
          - key: app
            operator: In
            values: ["web"]
        topologyKey: "kubernetes.io/hostname"
```

### 5.2 污点和容忍
```yaml
# 节点污点
kubectl taint nodes node1 key=value:NoSchedule

# Pod容忍
tolerations:
- key: "key"
  operator: "Equal"
  value: "value"
  effect: "NoSchedule"
```

## 6. 故障排除

### 常见问题及解决方案

| 问题现象 | 可能原因 | 检查方法 |
|---------|---------|---------|
| Pod处于Pending状态 | 无合适节点 | `kubectl describe pod <name>` |
| 调度延迟 | 调度队列积压 | 检查调度器日志 |
| 节点选择错误 | 亲和性规则配置错误 | 验证节点标签 |

### 调试命令
```bash
# 查看调度事件
kubectl describe pod <pod-name>

# 查看调度器日志
kubectl logs -n kube-system <scheduler-pod>

# 模拟调度
kubectl create -f pod.yaml --dry-run=server
```

## 7. 最佳实践

1. **合理设置资源请求和限制**
2. **使用节点亲和性而非nodeSelector**
3. **避免过度使用Pod反亲和性**
4. **为关键Pod设置高优先级**
5. **定期监控调度器性能**

## 8. 总结

Kubernetes调度器通过精心设计的过滤-打分-绑定流程，实现了高效、智能的Pod调度。理解这一流程有助于优化应用部署策略，提高集群资源利用率，确保应用的高可用性。随着调度框架的成熟，用户可以通过自定义插件进一步扩展调度能力，满足特定业务需求。

---

**注意**：本文基于Kubernetes 1.23+版本，不同版本的具体实现可能有所差异。建议查阅对应版本的官方文档获取最准确的信息。