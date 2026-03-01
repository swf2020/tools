# Sentinel滑动窗口统计（LeapArray时间窗口）技术文档

## 1. 概述

### 1.1 文档目的
本文档详细描述Sentinel中基于LeapArray实现的滑动时间窗口统计算法，该算法是Sentinel流量控制、熔断降级等核心功能的基础组件。

### 1.2 背景介绍
在分布式系统流量控制场景中，需要对特定时间窗口内的请求进行精确统计。传统固定时间窗口存在边界突变问题，而滑动时间窗口能够提供更平滑、更精确的统计数据。

## 2. 核心概念

### 2.1 LeapArray数据结构
LeapArray是Sentinel实现滑动窗口的核心数据结构，本质是一个环状数组，将连续的时间线分割成多个时间片段。

**关键特性：**
- **固定窗口长度**：每个时间窗口的长度固定
- **环状存储**：避免内存无限增长
- **时间分片**：将总时间窗口划分为多个小窗口
- **无锁设计**：通过CAS操作保证线程安全

### 2.2 时间窗口模型
```
总统计时长: 10秒
窗口数量: 10个
单个窗口时长: 1秒
滑动步长: 统计时向前滑动
```

## 3. 架构设计

### 3.1 整体架构
```
+---------------------+
|    Metric计算层     |
+---------------------+
          ↓
+---------------------+
|   LeapArray管理器   |
+---------------------+
          ↓
+---------------------+
|    Window桶存储     |
+---------------------+
          ↓
+---------------------+
|   Atomic数据操作    |
+---------------------+
```

### 3.2 类关系图
```java
// 核心接口定义
interface WindowWrap<T> {
    long windowLength();  // 窗口长度
    long windowStart();   // 窗口开始时间
    T value();           // 窗口数据
}

class LeapArray<T> {
    // 存储时间窗口的环状数组
    private final AtomicReferenceArray<WindowWrap<T>> array;
    // 窗口长度（毫秒）
    private final int windowLengthInMs;
    // 采样窗口数量
    private final int sampleCount;
    // 总时间间隔（毫秒）
    private final int intervalInMs;
}
```

## 4. 核心算法实现

### 4.1 时间窗口定位算法
```java
/**
 * 计算给定时间戳对应的窗口索引
 * @param timeMillis 当前时间戳
 * @return 窗口在数组中的索引
 */
private int calculateTimeIdx(long timeMillis) {
    // 通过时间戳计算数组索引
    long timeId = timeMillis / windowLengthInMs;
    return (int)(timeId % array.length());
}

/**
 * 计算窗口的开始时间
 * @param timeMillis 时间戳
 * @return 窗口的开始时间
 */
private long calculateWindowStart(long timeMillis) {
    return timeMillis - timeMillis % windowLengthInMs;
}
```

### 4.2 滑动窗口统计流程
```java
public class SlidingWindowMetric {
    
    public long getSuccessCount() {
        // 1. 获取当前时间
        long currentTime = TimeUtil.currentTimeMillis();
        
        // 2. 计算有效窗口的起始时间
        long oldestValidTime = currentTime - intervalInMs;
        
        // 3. 遍历所有窗口
        List<WindowWrap<MetricBucket>> list = new ArrayList<>();
        for (int i = 0; i < array.length(); i++) {
            WindowWrap<MetricBucket> windowWrap = array.get(i);
            if (windowWrap == null || isWindowDeprecated(windowWrap, oldestValidTime)) {
                continue;
            }
            list.add(windowWrap);
        }
        
        // 4. 聚合统计结果
        long total = 0;
        for (WindowWrap<MetricBucket> window : list) {
            total += window.value().success();
        }
        return total;
    }
    
    private boolean isWindowDeprecated(WindowWrap<?> windowWrap, long oldestValidTime) {
        return windowWrap.windowStart() + windowWrap.windowLength() < oldestValidTime;
    }
}
```

### 4.3 窗口创建与更新
```java
/**
 * 获取或创建当前时间对应的窗口
 */
public WindowWrap<T> currentWindow(long timeMillis) {
    if (timeMillis < 0) {
        return null;
    }
    
    // 计算窗口索引
    int idx = calculateTimeIdx(timeMillis);
    
    // 计算窗口开始时间
    long windowStart = calculateWindowStart(timeMillis);
    
    while (true) {
        WindowWrap<T> old = array.get(idx);
        
        if (old == null) {
            // 创建新窗口
            WindowWrap<T> window = new WindowWrap<>(windowLengthInMs, windowStart, newEmptyBucket());
            if (array.compareAndSet(idx, null, window)) {
                return window;
            } else {
                Thread.yield();
            }
        } else if (windowStart == old.windowStart()) {
            // 找到对应窗口
            return old;
        } else if (windowStart > old.windowStart()) {
            // 窗口已过期，需要重置
            if (lock.tryLock()) {
                try {
                    return resetWindowTo(old, windowStart);
                } finally {
                    lock.unlock();
                }
            } else {
                Thread.yield();
            }
        } else if (windowStart < old.windowStart()) {
            // 不应发生的情况，返回新窗口
            return new WindowWrap<>(windowLengthInMs, windowStart, newEmptyBucket());
        }
    }
}
```

## 5. 性能优化策略

### 5.1 内存优化
- **固定大小数组**：避免动态扩容开销
- **对象复用**：窗口数据对象复用，减少GC压力
- **缓存行填充**：防止伪共享

### 5.2 并发优化
```java
// 使用LongAdder替代AtomicLong提高并发性能
class MetricBucket {
    // 使用LongAdder进行计数统计
    private LongAdder[] counters;
    
    public void addSuccess(int count) {
        counters[SUCCESS_INDEX].add(count);
    }
    
    public long success() {
        return counters[SUCCESS_INDEX].sum();
    }
}
```

### 5.3 时间窗口优化策略
```java
// 可配置的时间窗口参数
public enum WindowStrategy {
    FIXED(0),     // 固定窗口
    SLIDING(1),   // 滑动窗口
    ADAPTIVE(2);  // 自适应窗口
    
    private final int code;
    
    // 根据系统负载自动调整窗口大小
    public int getOptimalWindowSize(double systemLoad) {
        if (systemLoad > 0.8) {
            return 500; // 高负载时使用更小的窗口
        } else {
            return 1000; // 正常负载使用标准窗口
        }
    }
}
```

## 6. 使用示例

### 6.1 基本使用
```java
public class FlowControlExample {
    
    // 创建滑动窗口统计器：10秒内分为10个窗口
    private SlidingWindowMetric metric = new SlidingWindowMetric(10000, 10);
    
    public void handleRequest(Request request) {
        // 1. 获取当前窗口
        long currentTime = System.currentTimeMillis();
        MetricBucket currentBucket = metric.getCurrentWindow(currentTime).value();
        
        // 2. 累加统计
        currentBucket.addSuccess(1);
        
        // 3. 检查是否超过阈值
        long totalSuccess = metric.getSuccessCount();
        if (totalSuccess > MAX_THRESHOLD) {
            // 触发流控
            throw new FlowException("请求过多");
        }
        
        // 4. 处理业务逻辑
        processBusiness(request);
    }
}
```

### 6.2 高级配置
```java
@Configuration
public class SentinelConfig {
    
    @Bean
    public LeapArray<MetricBucket> createLeapArray() {
        // 配置：1秒时间窗口，分为2个500ms的小窗口
        return new LeapArray<MetricBucket>() {
            @Override
            public MetricBucket newEmptyBucket(long time) {
                return new MetricBucket();
            }
            
            @Override
            protected WindowWrap<MetricBucket> resetWindowTo(
                WindowWrap<MetricBucket> w, long startTime) {
                w.resetTo(startTime);
                w.value().reset();
                return w;
            }
        };
    }
}
```

## 7. 监控与调优

### 7.1 监控指标
```java
public class WindowMonitor {
    
    // 窗口命中率监控
    public double getWindowHitRate() {
        long totalAccess = totalAccessCount.get();
        long windowHit = windowHitCount.get();
        return totalAccess > 0 ? (double) windowHit / totalAccess : 0;
    }
    
    // 内存使用监控
    public MemoryStats getMemoryUsage() {
        return new MemoryStats(
            array.length() * windowSize,
            Runtime.getRuntime().totalMemory()
        );
    }
    
    // 性能统计
    public PerformanceStats getPerformanceStats() {
        return new PerformanceStats(
            averageCalculateTime.get(),
            maxCalculateTime.get()
        );
    }
}
```

### 7.2 调优参数
| 参数名 | 默认值 | 建议范围 | 说明 |
|--------|--------|----------|------|
| windowLengthInMs | 1000ms | 500-2000ms | 单个窗口长度 |
| sampleCount | 2 | 2-10 | 采样窗口数量 |
| intervalInMs | 1000ms | 1000-10000ms | 统计间隔 |
| array.length | 采样窗口数 | 2的n次方 | 数组长度（推荐） |

## 8. 最佳实践

### 8.1 窗口大小选择
- **高流量场景**：使用较小的窗口（500ms）获得更实时的统计
- **低流量场景**：使用较大的窗口（2000ms）减少内存开销
- **混合场景**：使用自适应窗口策略

### 8.2 内存管理
```java
// 定期清理过期窗口
public void cleanExpiredWindows() {
    long currentTime = System.currentTimeMillis();
    long oldestValidTime = currentTime - intervalInMs;
    
    for (int i = 0; i < array.length(); i++) {
        WindowWrap<T> window = array.get(i);
        if (window != null && isWindowDeprecated(window, oldestValidTime)) {
            // 重置窗口数据，而非移除，避免频繁创建对象
            resetWindow(window, currentTime);
        }
    }
}
```

### 8.3 异常处理
```java
public class ResilientLeapArray<T> extends LeapArray<T> {
    
    @Override
    public WindowWrap<T> currentWindow(long timeMillis) {
        try {
            return super.currentWindow(timeMillis);
        } catch (Exception e) {
            // 降级策略：返回一个空的统计窗口
            log.warn("获取时间窗口失败，使用降级窗口", e);
            return createFallbackWindow(timeMillis);
        }
    }
    
    private WindowWrap<T> createFallbackWindow(long timeMillis) {
        // 创建不影响主流程的临时窗口
        return new WindowWrap<>(windowLengthInMs, 
                               calculateWindowStart(timeMillis), 
                               createEmptyBucket());
    }
}
```

## 9. 扩展与集成

### 9.1 自定义窗口实现
```java
public class CustomLeapArray<T> extends LeapArray<T> {
    
    // 添加权重支持
    private final Map<Long, Double> windowWeights = new ConcurrentHashMap<>();
    
    @Override
    public T getWindowValue(long timeMillis) {
        WindowWrap<T> window = currentWindow(timeMillis);
        T value = window.value();
        
        // 应用权重
        Double weight = windowWeights.get(window.windowStart());
        if (weight != null) {
            return applyWeight(value, weight);
        }
        
        return value;
    }
}
```

### 9.2 与监控系统集成
```java
public class MetricsExporter {
    
    public void exportToPrometheus(LeapArray<?> leapArray) {
        // 将窗口统计数据导出到Prometheus
        Gauge gauge = Gauge.build()
            .name("sentinel_window_metrics")
            .help("Sentinel时间窗口统计指标")
            .register();
            
        gauge.set(leapArray.getTotalCount());
    }
    
    public void exportToELK(WindowData data) {
        // 将详细窗口数据发送到ELK
        elkClient.indexDocument("sentinel-windows", data);
    }
}
```

## 10. 故障排查

### 10.1 常见问题
1. **内存泄漏**：检查窗口是否被正确清理
2. **统计不准确**：验证时间同步和窗口对齐
3. **性能下降**：监控锁竞争和GC情况

### 10.2 诊断工具
```java
public class WindowDiagnosticTool {
    
    public void diagnose(LeapArray<?> array) {
        // 检查窗口对齐
        checkWindowAlignment(array);
        
        // 检查内存使用
        checkMemoryUsage(array);
        
        // 检查并发问题
        checkConcurrencyIssues(array);
        
        // 生成诊断报告
        generateDiagnosticReport(array);
    }
}
```

## 11. 总结

Sentinel的LeapArray滑动窗口算法通过精巧的数据结构设计和并发控制，实现了高效、准确的时间窗口统计。该方案具有以下优势：

1. **高精度**：通过滑动窗口避免边界突变问题
2. **高性能**：无锁设计和对象复用保证低开销
3. **可扩展**：支持自定义窗口策略和统计维度
4. **稳定可靠**：完善的异常处理和降级策略

在实际使用中，应根据具体业务场景合理配置窗口参数，并结合监控系统进行持续优化，以达到最佳的性能和准确性平衡。

---

**文档版本**: v1.2  
**最后更新**: 2024年1月  
**适用版本**: Sentinel 1.8+