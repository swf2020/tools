# Kubernetes调度器优先级与抢占机制技术文档

## 1. 概述

### 1.1 文档目的
本文档详细阐述Kubernetes调度器中优先级（Priority）与抢占（Preemption）机制的工作原理、配置方法和最佳实践，为集群管理员和开发人员提供深入的技术指导。

### 1.2 功能简介
优先级与抢占机制允许Kubernetes调度器在资源紧张时，优先保证高优先级Pod的调度需求，必要时通过驱逐低优先级Pod（抢占）为高优先级Pod腾出资源。

## 2. 核心概念

### 2.1 优先级（Priority）
- **定义**：Pod的属性，表示其在集群中的相对重要性
- **范围**：整数数值，范围通常为0-1000000000（10亿）
- **系统预设**：
  - `system-cluster-critical`: 2000000000
  - `system-node-critical`: 2000001000
  - 用户可自定义优先级类

### 2.2 抢占（Preemption）
- **定义**：当高优先级Pod因资源不足无法调度时，调度器驱逐一个或多个低优先级Pod以释放资源的过程
- **触发条件**：仅当Pod无法通过正常调度找到合适节点时触发
- **执行原则**：最小化抢占影响，优先选择驱逐后释放资源最多的节点

## 3. 优先级配置

### 3.1 优先级类（PriorityClass）
```yaml
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: high-priority
value: 1000000          # 优先级数值
globalDefault: false    # 是否作为全局默认值
description: "用于关键业务应用"
```

### 3.2 Pod优先级指定
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: nginx
spec:
  containers:
  - name: nginx
    image: nginx
  priorityClassName: high-priority  # 引用优先级类
```

## 4. 抢占机制详解

### 4.1 抢占流程
```
1. 调度队列检查 → 2. 过滤节点 → 3. 评分节点 → 4. 无合适节点 → 
5. 触发抢占评估 → 6. 选择牺牲Pod → 7. 提名节点 → 8. 执行驱逐
```

### 4.2 抢占算法逻辑

```go
// 伪代码示例
func findPreemptionVictims(pod *v1.Pod, nodes []*v1.Node) (*v1.Node, []*v1.Pod) {
    var feasibleNodes []*v1.Node
    var victims []*v1.Pod
    
    for _, node := range nodes {
        // 检查节点是否满足Pod需求
        if fits, tempVictims := podFitsOnNode(pod, node); !fits {
            // 计算需要驱逐的Pod
            candidates := selectVictims(pod, node, tempVictims)
            if len(candidates) < len(victims) || len(victims) == 0 {
                victims = candidates
                feasibleNodes = append(feasibleNodes, node)
            }
        }
    }
    
    // 选择最优节点（驱逐Pod最少、优先级最低）
    return selectBestNode(feasibleNodes, victims), victims
}
```

### 4.3 抢占约束与限制
- **PDB约束**：不会抢占受PodDisruptionBudget保护的Pod
- **节点选择限制**：考虑节点亲和性、反亲和性规则
- **优雅终止**：被抢占Pod获得30秒（可配置）优雅终止期

## 5. 配置参数

### 5.1 kube-scheduler配置
```yaml
apiVersion: kubescheduler.config.k8s.io/v1beta3
kind: KubeSchedulerConfiguration
profiles:
  - schedulerName: default-scheduler
    pluginConfig:
      - name: PrioritySort
        args:
          apiVersion: kubescheduler.config.k8s.io/v1beta3
          kind: PrioritySortArgs
      - name: DefaultPreemption
        args:
          apiVersion: kubescheduler.config.k8s.io/v1beta3
          kind: DefaultPreemptionArgs
          minCandidateNodesPercentage: 10
          minCandidateNodesAbsolute: 100
```

### 5.2 关键参数说明
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `minCandidateNodesPercentage` | 10% | 参与抢占评估的最小节点比例 |
| `minCandidateNodesAbsolute` | 100 | 参与抢占评估的最小节点数 |
| `podPreemptionTimeout` | 24h | Pod进入抢占状态的最长时间 |

## 6. 应用场景

### 6.1 关键业务保障
```yaml
# 关键业务应用使用高优先级
apiVersion: apps/v1
kind: Deployment
metadata:
  name: critical-app
spec:
  template:
    spec:
      priorityClassName: system-cluster-critical
      containers:
      - name: app
        image: critical-app:latest
        resources:
          requests:
            cpu: "2"
            memory: "4Gi"
```

### 6.2 批处理任务优化
```yaml
# 批处理任务使用低优先级
apiVersion: batch/v1
kind: Job
metadata:
  name: batch-job
spec:
  template:
    spec:
      priorityClassName: low-priority  # 自定义低优先级类
      containers:
      - name: worker
        image: batch-worker:latest
```

## 7. 最佳实践

### 7.1 优先级策略设计
1. **层级化设计**：
   - 系统级（>1,000,000,000）
   - 生产关键级（100,000,000-999,999,999）
   - 常规业务级（1,000,000-99,999,999）
   - 开发测试级（<1,000,000）

2. **命名规范**：
   ```
   {环境}-{业务域}-{优先级级别}
   示例：prod-payment-high, dev-test-low
   ```

### 7.2 避免抢占风暴
```yaml
# 使用Pod反亲和性避免多副本被同时抢占
spec:
  affinity:
    podAntiAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchLabels:
            app: critical-app
        topologyKey: kubernetes.io/hostname
```

### 7.3 监控与告警
```bash
# 监控抢占事件
kubectl get events --field-selector reason=Preempted

# 查询抢占统计
kubectl get pods -o json | jq '[.items[] | select(.status.reason=="Preempted")] | length'
```

## 8. 故障排查

### 8.1 常见问题

| 问题现象 | 可能原因 | 解决方案 |
|----------|----------|----------|
| Pod处于Pending状态 | 优先级配置错误 | 检查PriorityClass是否存在 |
| 抢占未触发 | 资源请求过大 | 检查Pod资源请求是否合理 |
| 频繁抢占 | 资源配置不足 | 增加集群资源或优化调度 |

### 8.2 诊断命令
```bash
# 查看调度器日志
kubectl logs -n kube-system <kube-scheduler-pod> --tail=100

# 检查Pod调度失败原因
kubectl describe pod <pod-name> | grep -A10 Events

# 查看优先级类
kubectl get priorityclass
```

## 9. 安全注意事项

1. **权限控制**：
   ```yaml
   # RBAC配置示例
   apiVersion: rbac.authorization.k8s.io/v1
   kind: ClusterRole
   metadata:
     name: priority-limited-user
   rules:
   - apiGroups: ["scheduling.k8s.io"]
     resources: ["priorityclasses"]
     verbs: ["use"]
     resourceNames: ["low-priority", "medium-priority"]  # 限制可用优先级类
   ```

2. **审计配置**：
   ```yaml
   # 审计优先级变更
   - level: RequestResponse
     resources:
     - group: "scheduling.k8s.io"
       resources: ["priorityclasses"]
   ```

## 10. 版本兼容性

| Kubernetes版本 | 功能特性 |
|----------------|----------|
| 1.8+ | 引入Alpha版优先级/抢占 |
| 1.11+ | Beta版，默认启用 |
| 1.14+ | GA稳定版 |
| 1.22+ | 移除PodPriority特性门控 |

## 11. 参考资料

1. [Kubernetes官方文档 - Pod优先级和抢占](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/)
2. [调度器配置指南](https://kubernetes.io/docs/reference/scheduling/config/)
3. [KEP-902: Pod优先级和抢占](https://github.com/kubernetes/enhancements/tree/master/keps/sig-scheduling/902-pod-priority)

---

**文档版本**: 1.0  
**最后更新**: 2024年1月  
**适用版本**: Kubernetes 1.20+