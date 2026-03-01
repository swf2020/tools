好的，这是一份根据您的提示词生成的、结构完整且内容详实的技术文档。

---

## **技术文档：日志采样降噪策略（INFO降采样 / ERROR全量）**

| **文档版本** | **修订日期** | **修订内容** | **作者** |
| :--- | :--- | :--- | :--- |
| V1.0 | 2023-10-27 | 初稿创建 | [您的姓名/团队] |

### **摘要**

本文档阐述了一种旨在平衡日志数据价值与系统开销的日志采样降噪策略。其核心原则是：**对 INFO 及以上级别的常规日志进行降采样，同时对 ERROR 及以上级别的异常日志进行全量记录**。该策略能有效减少日志体积、降低存储与传输成本，并确保关键故障信息不丢失，提升日志数据的信噪比和可观测性效率。

### **1. 背景与目标**

#### **1.1 背景**
在现代分布式系统中，应用通常会生成海量日志。其中，绝大部分为 INFO 级别的程序运行轨迹、业务状态记录等。这些日志在排查问题时具有重要上下文价值，但在系统正常运行时，全量输出会导致：
* **存储成本激增**：日志占用的磁盘、对象存储空间巨大。
* **网络带宽压力**：日志收集（如通过 Fluentd、Logstash）占用大量内网带宽。
* **分析效率低下**：在 Elasticsearch、SLS 等日志平台中，过多的低价值信息会干扰关键问题的定位，降低查询与聚合性能。
* **日志滚动频繁**：本地磁盘日志文件快速轮转，可能覆盖仍有价值的旧日志。

#### **1.2 目标**
* **降本**：显著减少非关键日志的存储与处理资源消耗。
* **增效**：提高日志系统的信噪比，使运维和开发人员能更专注于异常和错误信息。
* **保真**：确保所有错误（ERROR）、严重错误（FATAL）以及关键警告（WARN，可选）日志被**100%记录**，不遗漏任何故障线索。
* **可调试**：在需要时，仍能通过采样到的 INFO 日志了解系统的正常运行状态和业务流程。

### **2. 核心策略设计**

#### **2.1 策略规则**
本策略遵循一个清晰的分级处理规则：

| **日志级别** | **处理策略** | **说明** |
| :--- | :--- | :--- |
| **FATAL / ERROR** | **全量记录** | 系统错误、异常失败。必须完整保留，用于根因分析、告警触发。 |
| **WARN** | **通常全量，可配置采样** | 潜在问题、非预期但可恢复的状态。建议全量，若数量极大可考虑降采样。 |
| **INFO** | **降采样记录** | 常规运行信息、业务流程节点。通过采样算法仅记录一部分。 |
| **DEBUG / TRACE** | **通常在线上环境关闭** | 调试信息。开发环境启用，线上环境默认关闭，需调试时动态开启。 |

#### **2.2 策略优势**
* **简单有效**：规则直观，易于在各类日志框架中实现。
* **成本可控**：采样率可动态调整，直接影响日志输出量。
* **风险可控**：关键错误信息无丢失风险，保障了系统可观测性的底线。

### **3. 实现方案**

#### **3.1 应用层实现（推荐）**
在应用程序代码或配置中实现，最为灵活精准。

**方案A：概率采样（例如采样率10%）**
```java
// Java (Logback / Log4j2 示例思路)
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import java.util.concurrent.ThreadLocalRandom;

public class SamplingLogger {
    private static final Logger LOGGER = LoggerFactory.getLogger(SamplingLogger.class);
    private static final double SAMPLING_RATE = 0.1; // 10%采样率

    public void logInfo(String message, Object... args) {
        if (ThreadLocalRandom.current().nextDouble() < SAMPLING_RATE) {
            LOGGER.info(message, args);
        }
        // 否则，丢弃这条INFO日志
    }

    // ERROR日志直接调用原生的error方法，全量记录
    public void logError(String message, Throwable t) {
        LOGGER.error(message, t);
    }
}
```

**方案B：基于日志速率的动态采样**
更高级的方案，例如使用 `Reservoir Sampling` 或令牌桶算法，保证在固定时间窗口内（如每秒）最多输出 N 条 INFO 日志，避免突发流量产生大量日志。

```python
# Python 简单计数器示例
import logging
import time

class RateLimitedLogger:
    def __init__(self, logger, max_per_second=10):
        self.logger = logger
        self.max_per_second = max_per_second
        self.count = 0
        self.window_start = time.time()

    def info(self, msg):
        now = time.time()
        if now - self.window_start >= 1.0:
            self.count = 0
            self.window_start = now

        if self.count < self.max_per_second:
            self.logger.info(msg)
            self.count += 1
        # 否则丢弃
```

#### **3.2 使用日志框架的过滤器**
许多日志框架原生支持过滤器和采样器。

* **Logback**： 使用 `SamplingFilter`。
    ```xml
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>ERROR</level>
        </filter>
        <filter class="ch.qos.logback.core.filter.EvaluatorFilter">
            <evaluator class="ch.qos.logback.classic.boolex.OnMarkerEvaluator">
                <!-- 配置标记或表达式 -->
            </evaluator>
            <onMatch>ACCEPT</onMatch>
            <onMismatch>DENY</onMismatch>
        </filter>
        <!-- 可结合TurboFilter实现概率采样 -->
    </appender>
    ```
* **Log4j2**： 使用 `BurstFilter` 和 `SamplingFilter`。
    ```xml
    <Filters>
        <!-- 首先，允许所有ERROR及以上 -->
        <ThresholdFilter level="ERROR" onMatch="ACCEPT" onMismatch="NEUTRAL"/>
        <!-- 然后，对INFO进行采样（这里1/10） -->
        <SamplingFilter samplingRate="0.1" onMatch="ACCEPT" onMismatch="DENY"/>
    </Filters>
    ```

#### **3.3 日志收集代理层实现**
在 Fluentd、Filebeat、Logstash 等代理中配置过滤规则。

```yaml
# Filebeat 示例 (7.x+)
processors:
  - drop_event:
      when:
        and:
          - equals:
              log.level: "info"
          - less_than: { random: 0.1 } # 随机数大于0.1时丢弃，即采样10%
  # 注意：此配置会丢弃90%的INFO，但ERROR会顺利通过。
```

```ruby
# Fluentd 示例
<filter app.**>
  @type grep
  <exclude>
    key level
    pattern ^INFO$
  </exclude>
</filter>
# 先过滤掉所有INFO，但这不是采样。Fluentd需配合`sample`插件实现。
<filter app.**>
  @type sample
  rate 10 # 每10条输出1条
  unless level == "ERROR" # 对非ERROR日志进行采样
</filter>
```

### **4. 关键注意事项**

1. **采样随机性与调试**：
   * 采样可能导致问题排查时上下文日志不连续。建议在每条日志中**固定包含`trace_id`/`request_id`**。一旦发现某个ERROR，可通过此ID在全量日志中检索该请求的所有相关日志（无论是否被采样）。
   * 可考虑**关键路径强制记录**：对于核心交易链路的关键步骤（如“支付成功”），即使为INFO级别，也通过业务规则或特殊标记（Marker）绕过采样，确保其100%记录。

2. **采样率的调整**：
   * 采样率（如1%，10%）不是固定的，应根据实际日志量、存储成本和排查需求动态调整。新系统上线初期可设置较高采样率（如50%）。
   * 可通过配置中心（如Nacos， Apollo）动态调整采样率，无需重启应用。

3. **监控与告警**：
   * 监控日志量（条数/体积）的瞬时和周期变化。采样策略实施后，应有明显的下降曲线。
   * 监控ERROR日志的绝对数量和增长率，这是系统健康度的关键指标。
   * 设置针对`ERROR突增`、`FATAL出现`的实时告警。

4. **与全量调试日志的平衡**：
   * 保留在特定条件下（如启动参数、配置开关、动态日志级别）临时开启全量INFO日志的能力，用于复现和调试棘手问题。

### **5. 总结**

“INFO降采样 + ERROR全量”是一种在实践中被广泛验证的有效日志治理策略。它通过牺牲一部分非关键日志的完整性，换取了系统整体可观测性成本的显著下降和运维效率的提升。成功实施该策略的关键在于：
* **清晰的日志级别规范**。
* **贯穿请求链路的唯一追踪标识**。
* **灵活可调的采样实现**。
* **配套的监控与应急调试手段**。

建议团队在应用此策略前，对现有日志进行一轮分析，明确INFO和ERROR日志的构成比例，从而制定出最适合当前业务的初始采样参数。