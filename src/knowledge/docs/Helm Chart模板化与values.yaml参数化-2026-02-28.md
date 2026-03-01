# Helm Chart 模板化与 values.yaml 参数化技术文档

## 1. 概述

### 1.1 Helm Chart 简介
Helm 是 Kubernetes 的包管理器，Chart 是 Helm 的打包格式。Chart 包含了一组 Kubernetes 资源的定义文件，可以通过模板化和参数化实现配置的动态生成。

### 1.2 模板化与参数化的价值
- **可复用性**：同一 Chart 可适配不同环境
- **可维护性**：集中管理配置，避免重复
- **安全性**：分离敏感配置与模板代码
- **灵活性**：支持环境差异和定制化需求

## 2. Helm Chart 目录结构

```
my-chart/
├── Chart.yaml          # Chart 元数据
├── values.yaml         # 默认配置值
├── values-*.yaml       # 环境特定配置
├── templates/          # 模板文件目录
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   └── _helpers.tpl    # 辅助模板
└── charts/             # 子Chart目录
```

## 3. values.yaml 参数化设计

### 3.1 基本参数结构

```yaml
# values.yaml
replicaCount: 3

image:
  repository: nginx
  tag: "1.20"
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 80
  targetPort: 80

ingress:
  enabled: false
  className: nginx
  hosts:
    - host: chart-example.local
      paths:
        - path: /
          pathType: Prefix

resources:
  requests:
    memory: "128Mi"
    cpu: "250m"
  limits:
    memory: "256Mi"
    cpu: "500m"

autoscaling:
  enabled: false
  minReplicas: 1
  maxReplicas: 10
  targetCPUUtilizationPercentage: 80

nodeSelector: {}
tolerations: []
affinity: {}

config:
  logLevel: "info"
  featureFlags:
    - "FEATURE_A"
    - "FEATURE_B"
```

### 3.2 环境特定配置

```yaml
# values-dev.yaml
replicaCount: 1
image:
  tag: "latest"
resources:
  requests:
    memory: "64Mi"
    cpu: "100m"
config:
  logLevel: "debug"
```

```yaml
# values-prod.yaml
replicaCount: 5
image:
  tag: "1.20-stable"
autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 20
```

## 4. 模板文件编写

### 4.1 基础模板语法

```yaml
# templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "my-chart.fullname" . }}
  labels:
    {{- include "my-chart.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      {{- include "my-chart.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "my-chart.labels" . | nindent 8 }}
        {{- with .Values.podLabels }}
        {{ toYaml . | nindent 8 }}
        {{- end }}
    spec:
      containers:
      - name: {{ .Chart.Name }}
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
        imagePullPolicy: {{ .Values.image.pullPolicy }}
        ports:
        - containerPort: {{ .Values.service.targetPort }}
        env:
        {{- range $key, $value := .Values.env }}
        - name: {{ $key }}
          value: {{ $value | quote }}
        {{- end }}
        {{- if .Values.config }}
        - name: LOG_LEVEL
          value: {{ .Values.config.logLevel | quote }}
        {{- end }}
```

### 4.2 条件语句

```yaml
# templates/ingress.yaml
{{- if .Values.ingress.enabled -}}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ include "my-chart.fullname" . }}
  labels:
    {{- include "my-chart.labels" . | nindent 4 }}
  {{- with .Values.ingress.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  {{- if .Values.ingress.className }}
  ingressClassName: {{ .Values.ingress.className }}
  {{- end }}
  rules:
  {{- range .Values.ingress.hosts }}
    - host: {{ .host | quote }}
      http:
        paths:
        {{- range .paths }}
          - path: {{ .path }}
            pathType: {{ .pathType }}
            backend:
              service:
                name: {{ include "my-chart.fullname" $ }}
                port:
                  number: {{ $.Values.service.port }}
        {{- end }}
  {{- end }}
{{- end }}
```

### 4.3 循环与范围

```yaml
# templates/configmap.yaml
{{- if .Values.configMap.enabled }}
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "my-chart.fullname" . }}-config
  labels:
    {{- include "my-chart.labels" . | nindent 4 }}
data:
  app.conf: |
    {{- range $key, $value := .Values.config }}
    {{ $key }} = {{ $value | quote }}
    {{- end }}
    
  features.conf: |
    {{- range .Values.config.featureFlags }}
    enable_{{ . }} = true
    {{- end }}
{{- end }}
```

### 4.4 辅助模板 (_helpers.tpl)

```yaml
# templates/_helpers.tpl
{{/* 生成Chart的完整名称 */}}
{{- define "my-chart.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/* 通用标签定义 */}}
{{- define "my-chart.labels" -}}
helm.sh/chart: {{ include "my-chart.chart" . }}
{{ include "my-chart.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/* 选择器标签 */}}
{{- define "my-chart.selectorLabels" -}}
app.kubernetes.io/name: {{ include "my-chart.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
```

## 5. 高级模板技术

### 5.1 模板函数与管道

```yaml
# 使用函数处理值
image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default "latest" | trimSuffix "-" }}"

# 值验证
{{- $port := .Values.service.port }}
{{- if and (ge $port 1) (le $port 65535) }}
port: {{ $port }}
{{- else }}
{{- fail "Port must be between 1 and 65535" }}
{{- end }}

# 复杂字符串处理
{{- $domain := .Values.domain | default "example.com" }}
host: "{{ .Values.subdomain }}.{{ $domain | trimPrefix "www." | lower }}"
```

### 5.2 变量与作用域

```yaml
{{- $root := . -}}
{{- range $index, $service := .Values.additionalServices }}
---
apiVersion: v1
kind: Service
metadata:
  name: {{ include "my-chart.fullname" $root }}-{{ $service.name }}
spec:
  ports:
  - port: {{ $service.port }}
    targetPort: {{ $service.targetPort }}
  selector:
    app: {{ include "my-chart.fullname" $root }}
{{- end }}
```

### 5.3 Secret 安全处理

```yaml
# templates/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: {{ include "my-chart.fullname" . }}
type: Opaque
data:
  {{- if .Values.secret.password }}
  password: {{ .Values.secret.password | b64enc }}
  {{- else }}
  password: {{ randAlphaNum 32 | b64enc }}
  {{- end }}
  
  # 从外部文件读取
  {{- if .Values.secret.tls.enabled }}
  tls.crt: {{ .Files.Get .Values.secret.tls.certFile | b64enc }}
  tls.key: {{ .Files.Get .Values.secret.tls.keyFile | b64enc }}
  {{- end }}
```

### 5.4 依赖图表值引用

```yaml
# Chart.yaml
dependencies:
  - name: postgresql
    version: "12.x"
    repository: "https://charts.bitnami.com/bitnami"
    condition: postgresql.enabled

# values.yaml 中引用子Chart
postgresql:
  enabled: true
  auth:
    username: "appuser"
    database: "appdb"
  
# 主Chart模板中引用
env:
  - name: DB_HOST
    value: {{ include "my-chart.fullname" . }}-postgresql
  - name: DB_NAME
    value: {{ .Values.postgresql.auth.database }}
```

## 6. 最佳实践

### 6.1 配置组织原则
1. **分层设计**：基础配置 → 环境配置 → 实例配置
2. **敏感数据分离**：Secret 单独管理，不放入 values.yaml
3. **向后兼容**：新增参数提供默认值，避免破坏现有部署
4. **文档注释**：在 values.yaml 中添加参数说明

```yaml
# 带有注释的 values.yaml
## 副本数量配置
## 参考: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/
replicaCount: 3

## 容器镜像配置
image:
  ## 镜像仓库地址
  repository: nginx
  ## 镜像标签（默认使用Chart版本）
  tag: ""
  ## 镜像拉取策略
  ## 可选值: Always, Never, IfNotPresent
  pullPolicy: IfNotPresent
```

### 6.2 验证与调试
```bash
# 模板渲染测试
helm template my-release ./my-chart --values values-prod.yaml

# 模板验证（语法检查）
helm lint ./my-chart

# 试运行（模拟安装）
helm install my-release ./my-chart --dry-run --debug

# 值文件验证
helm install my-release ./my-chart --values custom-values.yaml --set replicaCount=5
```

### 6.3 版本管理策略
```yaml
# Chart.yaml
apiVersion: v2
name: my-chart
description: A Helm chart for Kubernetes
type: application
version: 1.2.3
appVersion: "2.1.0"

# 版本控制建议
# - 主版本（Major）：不兼容的API变化
# - 次版本（Minor）：向后兼容的功能性新增
# - 修订版本（Patch）：向后兼容的问题修正
```

## 7. 示例：完整应用配置

### 7.1 多环境部署示例

```bash
# 开发环境
helm install my-app ./my-chart -f values.yaml -f values-dev.yaml

# 测试环境
helm install my-app ./my-chart -f values.yaml -f values-test.yaml \
  --set image.tag="test-build-123"

# 生产环境
helm install my-app ./my-chart -f values.yaml -f values-prod.yaml \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host="app.company.com"
```

### 7.2 CI/CD 集成示例

```yaml
# GitLab CI 配置示例
deploy:
  stage: deploy
  script:
    # 生成环境特定值
    - cat values.yaml values-$ENVIRONMENT.yaml > combined-values.yaml
    
    # 添加动态值
    - echo "image.tag: $CI_COMMIT_SHA" >> combined-values.yaml
    
    # 部署
    - helm upgrade --install
      my-app ./my-chart
      -f combined-values.yaml
      --atomic
      --timeout 5m
```

## 8. 故障排除与调试

### 8.1 常见问题

1. **模板渲染错误**
   ```bash
   # 详细错误信息
   helm template . --debug
   
   # 检查特定文件
   helm template . -x templates/deployment.yaml
   ```

2. **值未定义处理**
   ```yaml
   # 安全取值方式
   value: {{ .Values.some.nested.value | default "default-value" }}
   
   # 使用 required 强制提供
   value: {{ required "some.nested.value is required" .Values.some.nested.value }}
   ```

3. **类型转换问题**
   ```yaml
   # 确保字符串类型
   port: {{ .Values.port | toString }}
   
   # 数字比较
   {{- if gt (.Values.replicas | int) 1 }}
   # 多个副本的逻辑
   {{- end }}
   ```

## 9. 总结

Helm Chart 的模板化和 values.yaml 参数化是 Kubernetes 应用部署标准化的关键技术。通过合理的模板设计、层次化的配置管理和严格的最佳实践，可以实现：

1. **一次编写，多处部署**：同一 Chart 适配不同环境
2. **配置即代码**：版本控制所有配置变更
3. **安全合规**：敏感数据与模板代码分离
4. **运维友好**：清晰的配置结构和文档

随着云原生生态的发展，良好的 Helm Chart 设计已成为 Kubernetes 应用分发和管理的核心能力。

---

**文档版本**: 1.0  
**最后更新**: 2024年1月  
**适用 Helm 版本**: v3.8+  
**Kubernetes 版本**: v1.20+