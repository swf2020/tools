好的，遵照您的要求，这是一份关于 **Kubernetes NetworkPolicy 网络隔离规则** 的技术文档。

---

## **Kubernetes NetworkPolicy 网络隔离规则技术文档**

### **1. 文档概述**

#### **1.1 目的**
本文档旨在详细阐述 Kubernetes 中 NetworkPolicy 资源的工作原理、核心配置、典型应用场景及最佳实践。目标是帮助集群管理员和开发者理解并正确使用 NetworkPolicy 来实现 Pod 间的网络隔离与安全策略。

#### **1.2 适用范围**
*   Kubernetes 集群管理员、安全运维人员。
*   需要为微服务定义网络访问控制的开发人员。
*   使用支持 Kubernetes NetworkPolicy API 的 CNI 网络插件（如 Calico, Cilium, Antrea, Weave Net 等）的环境。

#### **1.3 重要前提**
*   **网络插件支持**：您的 Kubernetes CNI 网络插件**必须**支持 NetworkPolicy。默认的 `kubenet` 或不支持策略的插件无法生效。
*   **命名空间选择**：NetworkPolicy 是命名空间级别的资源。
*   **默认行为**：
    *   如果命名空间内**没有任何** NetworkPolicy，则所有 Pod 默认**允许所有**入站和出站流量（允许所有流量）。
    *   一旦在命名空间内创建了**任何一条** NetworkPolicy，该命名空间内的所有 Pod 将进入“默认拒绝”模式（针对未匹配任何规则的流量）。具体规则取决于 `policyTypes` 的定义。

---

### **2. 核心概念**

#### **2.1 什么是 NetworkPolicy？**
NetworkPolicy 是一种 Kubernetes 资源，用于声明性地规定一组 Pod 之间以及与其他网络端点之间如何进行网络通信。它通过标签选择器（Label Selector）来定义目标 Pod 和流量规则。

#### **2.2 关键组件**
一个 NetworkPolicy 规则主要包含以下几个部分：

1.  **`podSelector`**：
    *   用于选择本命名空间内此策略所适用的 Pod。如果为空 `{}`，则选择该命名空间下的**所有 Pod**。

2.  **`policyTypes`**：
    *   指定此策略适用于哪种类型的流量。可选值：`Ingress`（入站）、`Egress`（出站），或两者同时指定。如果不指定，则：
        *   如果定义了 `ingress` 规则，则自动包含 `Ingress`。
        *   如果定义了 `egress` 规则，则自动包含 `Egress`。

3.  **`ingress`**：入站规则数组。定义允许哪些来源访问 `podSelector` 选中的 Pod。
    *   `from`： 流量来源。可以是以下四种之一的组合：
        *   `podSelector`： 选择**同一命名空间内**的 Pod 作为来源。
        *   `namespaceSelector`： 选择特定命名空间（通过标签）内的所有 Pod 作为来源。
        *   `ipBlock`： 指定 CIDR 网段作为来源（例如集群外 IP）。
        *   （**注意**：`podSelector` 和 `namespaceSelector` 可以**同时**在一个 `from` 项中定义，表示“来自指定命名空间且匹配指定 Pod 标签”的 Pod。在较新 API 版本中，它们位于 `namespaceSelector` 和 `podSelector` 字段下。）

4.  **`egress`**：出站规则数组。定义 `podSelector` 选中的 Pod 允许访问哪些目的地。
    *   `to`： 流量目的地。结构与 `from` 类似，支持 `podSelector`, `namespaceSelector`, `ipBlock`。
    *   `ports`： 允许访问的目标端口列表。

---

### **3. 配置规则详解与 YAML 示例**

#### **3.1 基本结构**
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: <策略名称>
  namespace: <目标命名空间> # 默认为 default
spec:
  podSelector: # 选择本策略要管理的Pod
    matchLabels:
      <标签键>: <标签值>
  policyTypes: # 策略类型，可选 Ingress, Egress 或两者
  - Ingress
  - Egress
  ingress: # 入站规则列表
  - from: # 允许的流量来源列表
    - ...
    ports: # 允许的端口列表（可选）
    - protocol: TCP
      port: 80
  egress: # 出站规则列表
  - to: # 允许的流量目的地列表
    - ...
    ports: # 允许的端口列表（可选）
    - protocol: TCP
      port: 53
    - protocol: UDP
      port: 53
```

#### **3.2 典型场景示例**

**场景一：拒绝所有入站流量（默认拒绝）**
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all-ingress
  namespace: production
spec:
  podSelector: {} # 选择该命名空间下所有Pod
  policyTypes:
  - Ingress
  # 没有定义具体的 ingress 规则，意味着所有入站流量都被拒绝。
```

**场景二：仅允许来自指定 Pod 的访问**
假设前端 Pod (`app: frontend`) 需要访问后端 Pod (`app: backend`, `role: api`) 的 8080 端口。
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-to-backend
  namespace: app-ns
spec:
  podSelector:
    matchLabels:
      app: backend
      role: api
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector: # 仅允许来自带有 app=frontend 标签的Pod的流量
        matchLabels:
          app: frontend
    ports:
    - protocol: TCP
      port: 8080
```

**场景三：允许来自其他命名空间的访问**
允许来自命名空间 `monitoring`（带标签 `purpose: monitoring`）的所有 Pod 访问当前命名空间中带标签 `app: myapp` 的 Pod 的 9100 端口（常用于 Prometheus 抓取 metrics）。
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-monitoring
spec:
  podSelector:
    matchLabels:
      app: myapp
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          purpose: monitoring # 选择特定标签的命名空间
    ports:
    - protocol: TCP
      port: 9100
```

**场景四：允许 Pod 访问外部网络/特定 IP**
允许带标签 `app: external-client` 的 Pod 访问互联网（例如，访问一个外部 API `203.0.113.0/24` 网段）的 HTTPS 端口。
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-egress-external-api
spec:
  podSelector:
    matchLabels:
      app: external-client
  policyTypes:
  - Egress
  egress:
  - to:
    - ipBlock:
        cidr: 203.0.113.0/24
    ports:
    - protocol: TCP
      port: 443
  # 通常还需要允许访问集群DNS
  - to:
    - podSelector: {}
      namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: kube-system # 假设DNS在kube-system
    ports:
    - protocol: UDP
      port: 53
```

**场景五：允许 Pod 访问 Kubernetes DNS**
这是几乎所有需要出站规则的策略都必须包含的。
```yaml
# 这是场景四的一部分，单独列出以示重要
egress:
- to:
  - namespaceSelector: {} # 选择所有命名空间
    podSelector:
      matchLabels:
        k8s-app: kube-dns # CoreDNS 的常用标签
  ports:
  - protocol: UDP
    port: 53
  - protocol: TCP
    port: 53
```

---

### **4. 最佳实践与注意事项**

1.  **最小权限原则**：始终从“默认拒绝”开始，只添加必要的允许规则。
2.  **清晰的标签体系**：NetworkPolicy 严重依赖标签（Label）。为 Pod、命名空间设计清晰、一致的标签是有效管理网络策略的基础。
3.  **策略测试**：应用策略后，务必使用 `kubectl exec` 或其他工具从相关 Pod 内部进行网络连通性测试（如 `curl`, `nc`, `ping`）。
4.  **命名空间隔离**：为不同的团队、项目或环境使用不同的命名空间，并结合 `namespaceSelector` 进行隔离和跨空间访问控制。
5.  **组合策略**：一个 Pod 可能被多个 NetworkPolicy 选中，规则是**叠加（Additive）**的。只要任意一个策略允许该流量，则允许通过。没有一个策略能“拒绝”另一个策略允许的流量。
6.  **出站策略谨慎使用**：定义出站策略（`Egress`）时，务必记得放行访问集群核心服务（如 DNS）的流量，否则可能导致服务发现失败。
7.  **特定 CNI 插件的高级特性**：像 Calico、Cilium 这样的 CNI 提供商通常有自己扩展的 CRD（如 `GlobalNetworkPolicy`, `CiliumNetworkPolicy`），提供更强大的功能（如 L7 策略、服务网格集成等）。在复杂场景下可考虑使用。

---

### **5. 命令与诊断**

*   **查看策略**：
    ```bash
    kubectl get networkpolicy -n <namespace>
    kubectl describe networkpolicy <policy-name> -n <namespace>
    ```
*   **临时诊断容器**：使用一个临时 Pod 测试网络策略。
    ```bash
    kubectl run test-pod --image=nicolaka/netshoot --rm -it --restart=Never -- /bin/bash
    # 进入容器后，使用 curl, nc, dig 等命令测试
    ```

通过遵循以上指南，您可以有效地利用 Kubernetes NetworkPolicy 在集群内实施精细化的网络微隔离，从而显著提升工作负载的安全性和合规性。