好的，遵照您的要求，我将为您生成一份关于 Kubernetes RBAC（基于角色的访问控制）权限模型的技术文档。这份文档将涵盖核心概念、API对象、最佳实践及配置示例。

---

# Kubernetes RBAC (Role/ClusterRole/RoleBinding) 权限模型技术文档

## 1. 概述

**RBAC (Role-Based Access Control，基于角色的访问控制)** 是 Kubernetes 中用于精细化管理集群资源访问权限的标准授权模型。其核心思想是将权限（能做什么）与角色绑定，再将角色与主体（用户、组、ServiceAccount）绑定，而非直接将权限赋予主体。

## 2. 核心概念与 API 对象

RBAC 模型主要包含以下四种 API 对象，它们可以分为两类：**规则定义对象** 和 **绑定对象**。

| 对象类型 | 名称 | 命名空间 | 作用 |
| :--- | :--- | :--- | :--- |
| **规则定义** | `Role` | 是 | 定义在**单个命名空间**内的一组权限规则。 |
| **规则定义** | `ClusterRole` | 否 | 定义在**集群级别**（可跨所有命名空间）的一组权限规则，也可用于非资源端点（如 `/healthz`）或聚合到其他角色。 |
| **绑定** | `RoleBinding` | 是 | 将 `Role` 或 `ClusterRole` 的权限授予一个或多个主体（Subject），**生效范围仅限于该绑定所在的命名空间**。 |
| **绑定** | `ClusterRoleBinding` | 否 | 将 `ClusterRole` 的权限授予一个或多个主体（Subject），**生效范围是整个集群**（所有命名空间）。 |

### 2.1 主体 (Subject)
绑定对象中可以授权的主体有三种：
1.  **User (用户)**：外部系统（如客户端证书、OIDC）管理的用户标识。
2.  **Group (用户组)**：一组用户。
3.  **ServiceAccount (服务账号)**：Kubernetes 内部的身份，供 Pod 中的进程用于与 API Server 通信。这是最常用的主体类型。

## 3. RBAC API 对象详解

### 3.1 Role 与 ClusterRole

`Role` 和 `ClusterRole` 本质上都是**权限规则的集合**。一个规则就是一组对特定 API 资源可执行的操作（动词）。

**YAML 定义示例：**
```yaml
# Role 示例 (namespace: default)
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  namespace: default # Role 必须指定命名空间
  name: pod-reader
rules:
- apiGroups: [""] # 核心 API 组，空字符串表示核心资源（如 pods）
  resources: ["pods"] # 资源类型
  verbs: ["get", "list", "watch"] # 允许的操作

# ClusterRole 示例
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  # 无 namespace 字段
  name: node-viewer
rules:
- apiGroups: [""]
  resources: ["nodes"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["apps"] # 扩展 API 组
  resources: ["deployments"]
  verbs: ["get", "list"]
```

**关键字段说明：**
- **`apiGroups`**: 指定资源所属的 API 组（如 `""`, `"apps"`, `"networking.k8s.io"`）。
- **`resources`**: 指定资源类型（如 `"pods"`, `"deployments"`, `"services"`）。可以使用 `resourceNames` 字段进一步限制到特定实例。
- **`verbs`**: 指定允许的操作。常见动词包括：`get`, `list`, `watch`, `create`, `update`, `patch`, `delete`, `deletecollection`。

### 3.2 RoleBinding 与 ClusterRoleBinding

绑定对象建立了 `Role/ClusterRole` 与 `Subject` 之间的联系。

**YAML 定义示例：**
```yaml
# RoleBinding 示例：将 default 命名空间的 `pod-reader` Role 授予一个 ServiceAccount
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: read-pods
  namespace: default # 绑定生效的命名空间
subjects:
- kind: ServiceAccount
  name: myapp-sa # ServiceAccount 名称
  namespace: default # ServiceAccount 所在的命名空间（必须指定）
roleRef:
  kind: Role # 也可以是 ClusterRole
  name: pod-reader # 引用的 Role 名称，必须与 roleRef.kind 匹配
  apiGroup: rbac.authorization.k8s.io

# ClusterRoleBinding 示例：将集群级别的 `cluster-admin` ClusterRole 授予一个用户组
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: cluster-admins-binding
subjects:
- kind: Group
  name: system:masters # Kubernetes 内置的高权限组
  apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: cluster-admin # 内置的超级管理员角色
  apiGroup: rbac.authorization.k8s.io
```

**关键字段说明：**
- **`subjects`**: 要授权的主体列表。
- **`roleRef`**: 指向要绑定的 `Role` 或 `ClusterRole`。**注意**：`roleRef` 一旦创建不可修改。

## 4. 权限生效范围与组合规则

理解权限生效范围是 RBAC 的关键，遵循以下规则：

1.  **`Role` + `RoleBinding`**：
    - **作用域**：`Role` 和 `RoleBinding` 必须在**同一命名空间**。
    - **效果**：授予主体在该特定命名空间内，执行 `Role` 所定义权限的能力。

2.  **`ClusterRole` + `ClusterRoleBinding`**：
    - **作用域**：两者都是集群级别。
    - **效果**：授予主体在**所有命名空间**（及集群级资源）中，执行 `ClusterRole` 所定义权限的能力。

3.  **`ClusterRole` + `RoleBinding`** (常用组合)：
    - **作用域**：`RoleBinding` 在某个特定命名空间。
    - **效果**：授予主体在**该特定命名空间内**，执行 `ClusterRole` 所定义权限的能力。这是一种权限的“降级”使用，便于复用全局定义的 `ClusterRole`。

## 5. 最佳实践与建议

1.  **遵循最小权限原则**：只授予执行任务所必需的权限。
2.  **优先使用 ServiceAccount**：为在集群中运行的应用程序（Pod）创建专用的 `ServiceAccount` 并绑定相应角色，而非使用个人凭证。
3.  **利用内置角色**：Kubernetes 提供了一些预设的 `ClusterRole`，如 `view`、`edit`、`admin`、`cluster-admin`。在满足需求时优先使用。
4.  **为命名空间分配管理员**：使用 `ClusterRole` `admin` 与 `RoleBinding` 组合，授予用户管理某个特定命名空间的全部权限。
5.  **使用标签选择器进行聚合**：可以通过 `aggregationRule` 将多个 `ClusterRole` 的规则聚合到一个新的 `ClusterRole` 中，便于管理。
6.  **定期审计权限**：使用 `kubectl auth can-i` 命令或安全工具检查权限分配情况。

## 6. 常用命令示例

```bash
# 检查当前用户是否具有创建 Pod 的权限
kubectl auth can-i create pods

# 检查特定 ServiceAccount 在某个命名空间是否具有列出 Pod 的权限
kubectl auth can-i list pods --as=system:serviceaccount:<namespace>:<sa-name> -n <namespace>

# 查看针对某个主体的所有绑定
kubectl get rolebindings,clusterrolebindings --all-namespaces -o jsonpath='{range .items[?(@.subjects[0].name=="<subject-name>")]}[{.kind},{.metadata.name}]{end}'

# 描述一个 Role 的详细规则
kubectl describe role <role-name> -n <namespace>
```

## 7. 总结

Kubernetes RBAC 提供了一个强大、灵活且声明式的权限管理模型。通过清晰分离 `Role/ClusterRole`（定义“能做什么”）和 `RoleBinding/ClusterRoleBinding`（定义“谁来做”），并结合命名空间隔离，可以构建出满足复杂企业级安全需求的精细化权限体系。在设计时，务必从最小权限出发，并善用绑定组合规则来简化管理。