# Kubernetes HPA基于自定义指标（Prometheus Adapter）扩缩容技术文档

## 1. 概述

### 1.1 背景
Kubernetes Horizontal Pod Autoscaler (HPA) 默认支持基于CPU和内存使用率的自动扩缩容。但在实际生产环境中，业务负载往往与CPU/内存指标相关性较弱，需要基于自定义业务指标（如QPS、消息队列长度、应用内部指标等）进行弹性伸缩。

### 1.2 解决方案架构
本方案通过Prometheus监控系统收集应用自定义指标，再通过Prometheus Adapter将指标转换为Kubernetes Metrics API格式，最终实现HPA基于自定义指标的自动扩缩容。

## 2. 组件说明

### 2.1 Prometheus
- **角色**：监控系统，负责收集和存储时序指标
- **数据源**：通过ServiceMonitor/PodMonitor收集应用暴露的指标
- **存储**：时序数据库，支持PromQL查询

### 2.2 Prometheus Adapter
- **角色**：Kubernetes Metrics API的适配器
- **功能**：
  - 从Prometheus查询指标
  - 将Prometheus指标转换为Kubernetes Metrics API格式
  - 注册为API Aggregator，扩展Kubernetes API

### 2.3 Kubernetes HPA
- **角色**：自动扩缩容控制器
- **工作机制**：
  - 定期查询Metrics API获取指标
  - 根据指标值和目标阈值计算期望副本数
  - 调整Deployment/StatefulSet的副本数量

## 3. 部署与配置

### 3.1 前提条件
```bash
# 环境要求
Kubernetes集群版本 ≥ 1.23
Helm 3.x
Prometheus Operator已部署
```

### 3.2 部署Prometheus Adapter
```yaml
# values-adapter.yaml
prometheus:
  url: http://prometheus-operated.monitoring.svc
  port: 9090

rules:
  default: false
  custom:
  - seriesQuery: 'http_requests_total{namespace!="",pod!=""}'
    resources:
      overrides:
        namespace: {resource: "namespace"}
        pod: {resource: "pod"}
    name:
      matches: "^(.*)_total"
      as: "${1}_per_second"
    metricsQuery: 'sum(rate(<<.Series>>{<<.LabelMatchers>>}[2m])) by (<<.GroupBy>>)'
```

使用Helm部署：
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus-adapter prometheus-community/prometheus-adapter \
  -f values-adapter.yaml \
  -n monitoring
```

### 3.3 配置RBAC权限
```yaml
# rbac.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: custom-metrics-reader
rules:
- apiGroups: ["custom.metrics.k8s.io"]
  resources: ["*"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: hpa-custom-metrics-reader
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: custom-metrics-reader
subjects:
- kind: ServiceAccount
  name: default
  namespace: default
```

## 4. 应用指标暴露

### 4.1 应用侧配置
```python
# Flask应用示例 - metrics.py
from prometheus_client import Counter, Histogram, generate_latest
from flask import Flask, Response

app = Flask(__name__)

# 定义自定义指标
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP Requests',
    ['method', 'endpoint', 'status']
)

REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP Request Duration',
    ['method', 'endpoint']
)

@app.route('/metrics')
def metrics():
    return Response(generate_latest(), mimetype='text/plain')

@app.route('/api')
@REQUEST_DURATION.time()
def api_endpoint():
    REQUEST_COUNT.labels('GET', '/api', '200').inc()
    return "Hello World"
```

### 4.2 ServiceMonitor配置
```yaml
# servicemonitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: sample-app
  namespace: default
spec:
  selector:
    matchLabels:
      app: sample-app
  endpoints:
  - port: web
    interval: 30s
    path: /metrics
```

## 5. HPA配置示例

### 5.1 基于QPS的扩缩容
```yaml
# hpa-custom-metrics.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: sample-app-hpa
  namespace: default
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: sample-app
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Pods
    pods:
      metric:
        name: http_requests_per_second
      target:
        type: AverageValue
        averageValue: 100  # 每个Pod平均每秒100个请求
```

### 5.2 多指标扩缩容
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: multi-metrics-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: sample-app
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Pods
    pods:
      metric:
        name: http_requests_per_second
      target:
        type: AverageValue
        averageValue: 100
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 10
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 100
        periodSeconds: 60
```

## 6. 验证与测试

### 6.1 验证指标可用性
```bash
# 验证自定义指标API
kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta1" | jq .

# 查询特定指标
kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta1/namespaces/default/pods/*/http_requests_per_second"

# 查看HPA状态
kubectl describe hpa sample-app-hpa
```

### 6.2 压力测试
```bash
# 使用wrk进行压力测试
wrk -t12 -c400 -d300s http://sample-app.default.svc.cluster.local/api

# 观察扩缩容过程
watch -n 5 'kubectl get hpa,pods -l app=sample-app'
```

## 7. 最佳实践

### 7.1 指标选择原则
- **相关性**：指标应与业务负载强相关
- **敏感性**：指标应对负载变化敏感
- **稳定性**：指标应避免剧烈波动
- **可预测性**：指标变化应具有一定规律

### 7.2 HPA配置建议
1. **冷却时间设置**：
   ```yaml
   behavior:
     scaleDown:
       stabilizationWindowSeconds: 300  # 缩容冷却5分钟
     scaleUp:
       stabilizationWindowSeconds: 60   # 扩容冷却1分钟
   ```

2. **副本数边界**：
   - 设置合理的minReplicas和maxReplicas
   - 考虑应用启动时间

3. **多指标策略**：
   - 结合资源指标和自定义指标
   - 使用Pods/Object/External等多种类型指标

### 7.3 监控告警配置
```yaml
# Prometheus告警规则
groups:
- name: hpa-alerts
  rules:
  - alert: HPAScalingFailed
    expr: kube_hpa_status_condition{condition="ScalingLimited",status="true"} == 1
    for: 5m
    annotations:
      description: HPA {{ $labels.name }} in namespace {{ $labels.namespace }} has been unable to scale for 5 minutes
```

## 8. 故障排查

### 8.1 常见问题
1. **指标不可见**
   ```bash
   # 检查Prometheus数据
   kubectl port-forward svc/prometheus-operated 9090:9090
   # 浏览器访问 localhost:9090 查询指标
   
   # 检查Adapter日志
   kubectl logs -l app=prometheus-adapter -n monitoring
   ```

2. **HPA不伸缩**
   ```bash
   # 查看HPA事件
   kubectl describe hpa <hpa-name>
   
   # 检查Metrics API
   kubectl get apiservice v1beta1.custom.metrics.k8s.io
   ```

3. **指标延迟**
   - 调整Prometheus抓取间隔
   - 优化Adapter查询参数

## 9. 性能优化

### 9.1 Prometheus Adapter调优
```yaml
# adapter-config.yaml
cache:
  refreshInterval: 60s  # 缓存刷新间隔
  expiresInterval: 5m   # 缓存过期时间

prometheus:
  query:
    concurrent: 20      # 并发查询数
    timeout: 30s        # 查询超时时间
```

### 9.2 指标聚合优化
```yaml
rules:
  - seriesQuery: 'custom_metric{namespace!="",pod!=""}'
    resources:
      template: "<<.Resource>>"
    metricsQuery: |
      label_replace(
        sum by (<<.GroupBy>>) (
          rate(<<.Series>>{<<.LabelMatchers>>}[5m])
        ),
        "metric_name",
        "custom_metric_per_second",
        "",
        ""
      )
```

## 10. 总结

基于Prometheus Adapter的HPA自定义指标扩缩容方案提供了以下优势：

1. **灵活性**：支持任意Prometheus指标
2. **标准化**：基于Kubernetes Metrics API标准
3. **生态完善**：与Prometheus监控体系无缝集成
4. **生产就绪**：经过大规模生产环境验证

### 注意事项：
- 确保指标数据的准确性和及时性
- 合理设置扩缩容阈值和冷却时间
- 实施前充分测试不同负载场景
- 建立完善的监控和告警机制

## 附录

### A. 相关命令速查
```bash
# 查看自定义指标
kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta1" | jq '.resources[] | select(.name | contains("requests"))'

# 模拟流量
kubectl run -i --tty load-generator --image=busybox -- sh
while true; do wget -q -O- http://sample-app.default.svc.cluster.local/api; done
```

### B. 参考文档
- [Kubernetes HPA官方文档](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)
- [Prometheus Adapter GitHub](https://github.com/kubernetes-sigs/prometheus-adapter)
- [Prometheus Client Libraries](https://prometheus.io/docs/instrumenting/clientlibs/)