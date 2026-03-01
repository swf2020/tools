# **Prometheus Recording Rule 预计算优化查询 技术文档**

## **文档目录**
1. 摘要  
2. 引言  
3. Recording Rule 核心概念  
4. 为什么需要预计算优化查询  
5. Recording Rule 配置与语法详解  
6. 设计原则与最佳实践  
7. 实际应用场景与案例  
8. 性能优化效果评估  
9. 常见问题与解决方案  
10. 总结与参考资料  

---

## **1. 摘要**
Prometheus Recording Rule 允许预先计算常用或复杂的查询表达式，并将结果存储为新的时间序列，从而显著降低查询时的计算开销、提升查询速度与面板渲染效率，同时减轻 Prometheus Server 负载。本文档系统介绍 Recording Rule 的设计方法、配置语法、最佳实践及典型应用场景，帮助用户实现高效、稳定的监控查询优化。

---

## **2. 引言**
Prometheus 作为流行的监控与告警工具，支持强大的 PromQL 进行数据查询。然而，当数据量庞大或查询涉及多级聚合、跨指标运算时，实时查询可能带来较高延迟，并增加服务端压力。Recording Rule 通过“空间换时间”策略，将频繁使用的查询结果预先计算并持久化，优化查询性能与系统资源利用率。

---

## **3. Recording Rule 核心概念**
- **Recording Rule**：在 Prometheus 配置中定义规则，定期对现有时间序列进行 PromQL 运算，将结果保存为新指标。
- **规则文件**：通常以 `.rules.yml` 或 `.rules.yaml` 为后缀，由 `rule_files` 字段在 `prometheus.yml` 中引用。
- **规则组（Rule Group）**：
  - 包含一组相关规则，共享执行间隔与参数。
  - 支持并发控制与容错策略。

---

## **4. 为什么需要预计算优化查询**
- **降低查询延迟**：复杂查询转换为直接读取预计算结果。
- **减少重复计算**：相同查询在多个面板或告警中重复使用时避免重复运算。
- **资源优化**：降低 Prometheus Query Engine 的 CPU 与内存压力。
- **提升用户体验**：仪表板加载更快，实时交互更流畅。

---

## **5. Recording Rule 配置与语法详解**

### **5.1 规则文件示例**
```yaml
groups:
  - name: example_rules
    interval: 30s
    rules:
      - record: job:http_requests:rate5m
        expr: rate(http_requests_total[5m])
      - record: instance:cpu_usage:ratio
        expr: (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) by (instance)) * 100
```

### **5.2 配置字段说明**
- `groups[]`：规则组列表。
- `name`：规则组名称，用于日志与状态页面。
- `interval`：规则执行间隔（覆盖全局 `evaluation_interval`）。
- `rules[]`：具体规则列表。
  - `record`：新生成的时间序列名称（建议符合命名规范）。
  - `expr`：PromQL 表达式，计算结果将写入 `record`。

### **5.3 命名规范建议**
- 使用层次化命名，如 `<metric_name>:<aggregation>:<interval>`。
- 示例：`job:request_errors:rate5m`。

---

## **6. 设计原则与最佳实践**

### **6.1 规则设计原则**
1. **高频查询优先**：为仪表板中频繁刷新的查询定义规则。
2. **复杂度优先**：针对多级聚合、跨指标运算的查询进行预计算。
3. **避免过度设计**：仅对确实影响性能的查询创建规则，避免无意义序列膨胀。

### **6.2 最佳实践**
- **规则分组策略**：将相关业务或性能关注点的规则放在同一组。
- **执行间隔选择**：根据数据更新频率与精度需求设置 `interval`（通常 30s-5m）。
- **标签保留与聚合**：
  ```yaml
  - record: job:request_duration_seconds:p99_rate5m
    expr: histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, job))
  ```
- **避免高基数标签**：预计算时尽量使用 `by` 或 `without` 减少标签维度，防止序列数量爆炸。
- **规则测试验证**：先用临时记录规则验证结果正确性，再正式上线。

---

## **7. 实际应用场景与案例**

### **7.1 场景一：聚合业务指标**
**原始查询**：  
`sum(rate(order_created_total[5m])) by (service, region)`

**Recording Rule**：
```yaml
- record: service:order_created:rate5m
  expr: sum(rate(order_created_total[5m])) by (service, region)
```
**优化后查询**：直接使用 `service:order_created:rate5m`。

### **7.2 场景二：计算资源使用率**
**原始查询**：  
`(1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) by (instance)) * 100`

**Recording Rule**：
```yaml
- record: instance:cpu_usage:percent
  expr: (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) by (instance)) * 100
```

### **7.3 场景三：复杂统计分位数**
**原始查询**：  
`histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, service))`

**Recording Rule**：
```yaml
- record: service:request_duration_seconds:histogram_quantile_95_rate5m
  expr: histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, service))
```

---

## **8. 性能优化效果评估**

### **8.1 评估指标**
- **查询延迟**：通过 Prometheus 查询日志或 `prometheus_engine_query_duration_seconds` 对比优化前后。
- **内存与 CPU 使用率**：观察 `process_resident_memory_bytes` 与 `process_cpu_seconds_total` 变化。
- **时间序列数量**：通过 `prometheus_tsdb_head_series` 监控规则引入的新序列数。

### **8.2 典型优化效果**
- 复杂聚合查询延迟可从数百毫秒降至个位数毫秒。
- 高并发查询场景下 Prometheus 服务器负载下降 30%-60%。

---

## **9. 常见问题与解决方案**

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| 规则未生效 | 配置文件未加载或语法错误 | 检查 `prometheus.yml` 中 `rule_files` 路径；使用 `promtool check rules` 验证语法 |
| 序列数量爆炸 | 规则中保留高基数标签（如 IP、URL） | 预计算时使用 `without()` 或 `by()` 减少标签 |
| 查询结果不一致 | 规则执行间隔与查询范围不匹配 | 确保 `interval` 与面板的 `interval` 及查询范围协调 |
| 内存使用过高 | 规则过多或表达式过于复杂 | 精简规则，优化 PromQL，增加 Prometheus 内存配置 |

---

## **10. 总结与参考资料**

### **10.1 总结**
Recording Rule 是 Prometheus 查询性能优化的重要工具，通过预计算将复杂查询转化为直接指标读取，显著提升查询效率并降低系统负载。合理设计规则、遵循最佳实践、持续监控效果，可构建高效、稳定的监控体系。

### **10.2 参考资料**
- [Prometheus Official Documentation: Recording Rules](https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/)
- [Prometheus Best Practices: Rules and Labels](https://prometheus.io/docs/practices/rules/)
- [PromQL Tutorial: Advanced Aggregations](https://prometheus.io/docs/prometheus/latest/querying/basics/)

---

**文档版本**：1.0  
**最后更新**：2023年10月  
**适用版本**：Prometheus 2.0+