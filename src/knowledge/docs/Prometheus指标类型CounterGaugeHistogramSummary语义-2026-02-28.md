# Prometheus核心指标类型详解：Counter、Gauge、Histogram与Summary

## 1. 概述

Prometheus作为云原生领域主流的监控系统，其数据模型基于多维时间序列，并通过四种核心指标类型来描述不同类型的监控数据。每种类型都有特定的语义和适用场景，理解这些类型对于设计有效的监控指标至关重要。

## 2. Counter（计数器）

### 2.1 基本语义
Counter是一种**只增不减**的累积指标，表示单调递增的计数器值。

### 2.2 核心特性
- **单调递增**：值只会增加或重置为0（重启等情况）
- **累积性**：记录从开始到现在发生的总次数
- **不适合**：表示当前瞬时值或可能减少的值

### 2.3 典型使用场景
```promql
# HTTP请求总数
http_requests_total{method="POST", handler="/api"}
# CPU时间消耗（秒）
process_cpu_seconds_total
# 应用启动次数
app_restarts_total
```

### 2.4 PromQL操作示例
```promql
# 计算QPS（每秒查询率）
rate(http_requests_total[5m])
# 计算增量（过去5分钟的变化量）
increase(http_requests_total[5m])
```

## 3. Gauge（仪表盘）

### 3.1 基本语义
Gauge表示**可任意变化**的数值，可以增加、减少或保持不变。

### 3.2 核心特性
- **非单调**：可增可减，反映当前瞬时状态
- **瞬时性**：表示某一时刻的测量值
- **适合**：表示资源使用情况、温度、内存等

### 3.3 典型使用场景
```promql
# 内存使用量（字节）
node_memory_MemFree_bytes
# 当前活跃连接数
nginx_connections_active
# 温度测量值
sensor_temperature_celsius
```

### 3.4 PromQL操作示例
```promql
# 直接查询当前值
node_memory_MemFree_bytes
# 计算一段时间内的变化
delta(node_memory_MemFree_bytes[2h])
# 聚合操作
avg(nginx_connections_active)
```

## 4. Histogram（直方图）

### 4.1 基本语义
Histogram对**观测值进行采样**，并在可配置的桶（bucket）中进行计数，用于分析数据分布。

### 4.2 数据结构
一个Histogram指标实际上会生成多个时间序列：
```
# 基础指标
request_duration_seconds
# 自动生成的序列
request_duration_seconds_bucket{le="0.1"}    # ≤0.1秒的请求数
request_duration_seconds_bucket{le="0.5"}    # ≤0.5秒的请求数
request_duration_seconds_bucket{le="1.0"}    # ≤1.0秒的请求数
request_duration_seconds_bucket{le="+Inf"}   # 总请求数
request_duration_seconds_sum                # 响应时间总和
request_duration_seconds_count              # 请求总数
```

### 4.3 典型使用场景
```promql
# 请求延迟分布
http_request_duration_seconds_bucket
# 响应大小分布
http_response_size_bytes_bucket
```

### 4.4 PromQL操作示例
```promql
# 计算95分位数
histogram_quantile(0.95, 
  rate(http_request_duration_seconds_bucket[5m])
)
# 计算平均响应时间
rate(http_request_duration_seconds_sum[5m]) / 
rate(http_request_duration_seconds_count[5m])
```

## 5. Summary（摘要）

### 5.1 基本语义
Summary在客户端计算**分位数**，直接提供预计算的分位数结果。

### 5.2 数据结构
```
# 基础指标
http_request_duration_seconds
# 自动生成的序列
http_request_duration_seconds{quantile="0.5"}  # 中位数
http_request_duration_seconds{quantile="0.9"}  # 90分位数
http_request_duration_seconds{quantile="0.99"} # 99分位数
http_request_duration_seconds_sum             # 总和
http_request_duration_seconds_count           # 总数
```

### 5.3 与Histogram的关键区别
| 特性 | Histogram | Summary |
|------|-----------|---------|
| 分位数计算 | 服务端（PromQL） | 客户端 |
| 可聚合性 | 支持跨实例聚合 | 不支持聚合 |
| 配置灵活性 | 可动态调整分位数 | 需客户端预定义 |
| 存储开销 | 相对较大 | 相对较小 |

### 5.4 典型使用场景
```promql
# 客户端预计算的分位数指标
go_gc_duration_seconds{quantile="0.5"}
# 不需要跨实例聚合的延迟监控
service_latency_seconds{quantile="0.95"}
```

## 6. 类型选择指南

### 6.1 决策流程图
```
是否计数类事件？ → 是 → Counter
否
↓
是否瞬时可变量？ → 是 → Gauge
否
↓
是否分析数据分布？ → 是 → 继续判断
否
↓
考虑其他类型
↓
需要跨实例聚合？ → 是 → Histogram
否
↓
客户端计算更高效？ → 是 → Summary
```

### 6.2 最佳实践建议

#### Counter使用建议
- 始终使用`_total`后缀命名
- 配合`rate()`或`increase()`函数使用
- 避免用于可能减少的指标

#### Gauge使用建议
- 适合表示资源利用率
- 可使用`delta()`查看变化
- 注意采样频率与业务需求匹配

#### Histogram使用建议
- 精心设计桶边界（le标签值）
- 使用`histogram_quantile()`计算分位数
- 桶数量不宜过多（通常5-10个）

#### Summary使用建议
- 当客户端计算更合适时使用
- 明确分位数需求（如0.5, 0.9, 0.99）
- 注意不支持聚合的限制

## 7. 常见错误模式

### 7.1 错误用法示例
```promql
# 错误：将Gauge当作Counter使用
rate(current_connections[5m])  # current_connections是Gauge

# 错误：误解Histogram分位数精度
# histogram_quantile的结果是估算值，非精确值

# 错误：尝试聚合Summary分位数
avg(http_request_duration_seconds{quantile="0.9"})  # 无意义
```

### 7.2 正确的监控指标设计
```yaml
# 好的指标命名示例
- name: http_requests_total        # Counter
  type: counter
  help: "Total HTTP requests"
  
- name: memory_usage_bytes         # Gauge
  type: gauge
  help: "Current memory usage"
  
- name: request_duration_seconds   # Histogram
  type: histogram
  help: "Request latency distribution"
  buckets: [0.1, 0.5, 1, 2, 5]
```

## 8. 总结

Prometheus的四种指标类型构成了其监控数据模型的基础：
- **Counter**：用于累积计数，适合请求数、错误数等
- **Gauge**：用于瞬时测量，适合资源使用量等
- **Histogram**：用于服务端计算分位数，支持聚合
- **Summary**：用于客户端计算分位数，精度更高但不支持聚合

正确选择和使用这些指标类型，能够构建出高效、准确的监控体系，为系统可观测性提供坚实基础。在实际应用中，建议结合具体业务场景和性能要求，灵活选择和组合使用不同的指标类型。