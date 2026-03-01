# Guava RateLimiter令牌桶算法实现技术文档

## 1. 概述

Guava RateLimiter是Google Guava库提供的一个基于令牌桶算法的限流器实现，用于控制系统的访问速率，防止突发流量对系统造成冲击。

## 2. 核心算法原理

### 2.1 令牌桶算法基础
令牌桶算法包含以下核心概念：
- **令牌桶**：容量固定的容器，按恒定速率向桶中添加令牌
- **令牌**：每次请求需要获取一个或多个令牌才能执行
- **获取规则**：请求到达时，桶中有足够令牌则立即执行，否则等待或拒绝

### 2.2 Guava RateLimiter变体
Guava提供了两种实现：

| 实现类型 | 特性 | 适用场景 |
|---------|------|---------|
| SmoothBursty | 允许突发流量，支持预消费令牌 | 需要应对突发请求的场景 |
| SmoothWarmingUp | 预热模式，流量逐渐增加到设定速率 | 需要系统预热避免冷启动冲击 |

## 3. 关键特性

### 3.1 主要功能
- **限流控制**：精确控制QPS（每秒查询率）
- **突发处理**：支持处理短时间内的突发请求
- **预热机制**：避免冷系统直接承受高流量
- **阻塞与非阻塞**：支持阻塞等待和立即返回两种模式
- **动态调整**：运行时动态调整限流速率

### 3.2 技术特点
- 基于漏桶算法的变体实现
- 支持微秒级精度控制
- 线程安全设计
- 无额外调度线程开销

## 4. 使用示例

### 4.1 基础使用
```java
import com.google.common.util.concurrent.RateLimiter;

// 创建每秒允许10个请求的限流器
RateLimiter limiter = RateLimiter.create(10.0);

public void processRequest() {
    // 阻塞直到获取令牌
    limiter.acquire();
    
    // 执行业务逻辑
    executeBusinessLogic();
}
```

### 4.2 带突发处理
```java
// 创建支持突发的限流器
RateLimiter limiter = RateLimiter.create(5.0); // 5 QPS

// 一次性处理10个请求（会消耗积累的令牌）
if (limiter.tryAcquire(10)) {
    batchProcess();
} else {
    // 处理不足情况
    fallback();
}
```

### 4.3 预热模式
```java
// 创建预热限流器：5秒内从冷启动达到10QPS
RateLimiter limiter = RateLimiter.create(10.0, 5, TimeUnit.SECONDS);

// 预热期间请求速率会逐步增加
for (int i = 0; i < 20; i++) {
    limiter.acquire();
    processRequest();
}
```

### 4.4 非阻塞模式
```java
// 尝试获取令牌，立即返回结果
if (limiter.tryAcquire()) {
    // 成功获取令牌
    processRequest();
} else {
    // 获取失败，执行降级逻辑
    rateLimitFallback();
}

// 带超时尝试
if (limiter.tryAcquire(1, TimeUnit.SECONDS)) {
    processRequest();
}
```

## 5. 配置参数详解

### 5.1 创建参数
```java
// SmoothBursty构造参数
RateLimiter.create(double permitsPerSecond);

// SmoothWarmingUp构造参数
RateLimiter.create(double permitsPerSecond, 
                   long warmupPeriod, 
                   TimeUnit unit);
```

### 5.2 参数说明
| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| permitsPerSecond | double | 每秒产生的令牌数 | 必须指定 |
| warmupPeriod | long | 预热时间 | SmoothWarmingUp专用 |
| unit | TimeUnit | 预热时间单位 | SmoothWarmingUp专用 |
| maxBurstSeconds | double | 最大突发秒数（SmoothBursty） | 1.0秒 |

## 6. 内部实现剖析

### 6.1 核心数据结构
```java
// 关键字段说明
abstract class SmoothRateLimiter extends RateLimiter {
    // 当前存储的令牌数
    double storedPermits;
    
    // 最大允许存储的令牌数
    double maxPermits;
    
    // 添加令牌的时间间隔（稳定速率时）
    double stableIntervalMicros;
    
    // 下一个允许获取令牌的时间
    long nextFreeTicketMicros;
}
```

### 6.2 令牌生成机制
```
令牌生成公式：
新的令牌数 = min(最大令牌数, 
                当前令牌数 + (当前时间 - 上次更新时间) / 添加间隔)

时间计算基于System.nanoTime()，保证单调递增，不受系统时间调整影响
```

### 6.3 等待时间计算
```java
// 计算需要等待的时间
long reserveEarliestAvailable(int requiredPermits, long nowMicros) {
    // 1. 刷新令牌桶
    resync(nowMicros);
    
    // 2. 计算可以立即提供的令牌
    long returnValue = nextFreeTicketMicros;
    
    // 3. 计算本次请求需要消耗的令牌
    double storedPermitsToSpend = min(requiredPermits, this.storedPermits);
    
    // 4. 计算需要的等待时间
    double freshPermits = requiredPermits - storedPermitsToSpend;
    long waitMicros = (long) (freshPermits * stableIntervalMicros);
    
    // 5. 更新下次可用时间
    this.nextFreeTicketMicros = nextFreeTicketMicros + waitMicros;
    
    return returnValue;
}
```

### 6.4 预热算法（SmoothWarmingUp）
```
预热阶段采用不同的令牌消耗策略：
1. 初始阶段：较长的令牌间隔时间
2. 随着时间推移，间隔逐渐缩短
3. 达到稳定阶段后，使用固定的间隔时间

预热曲线采用分段函数，确保平滑过渡
```

## 7. 性能特点

### 7.1 时间复杂度
- **令牌获取**：O(1)时间复杂度
- **令牌更新**：惰性更新，仅在请求时计算
- **内存占用**：固定大小，与并发数无关

### 7.2 线程安全
- 使用synchronized关键字保证线程安全
- 无锁设计优化：大部分操作无需同步
- 适用于高并发场景

## 8. 适用场景

### 8.1 推荐使用场景
- **API限流**：保护后端服务免受突发流量冲击
- **资源控制**：控制数据库、缓存等资源访问频率
- **客户端限速**：控制对第三方服务的调用频率
- **队列削峰**：平滑处理请求队列，避免系统过载

### 8.2 不适用场景
- 需要分布式限流的场景（单机实现）
- 需要严格按时间窗口计数的场景
- 需要复杂规则（如黑白名单、动态规则）的场景

## 9. 注意事项与最佳实践

### 9.1 使用注意事项
```java
// 1. 注意精度问题
RateLimiter limiter = RateLimiter.create(0.5); // 每2秒1个请求

// 2. 避免在热点路径频繁创建
// 错误示例
public void process() {
    RateLimiter limiter = RateLimiter.create(10.0); // 每次创建新实例
    limiter.acquire();
}

// 正确示例
private static final RateLimiter LIMITER = RateLimiter.create(10.0);

// 3. 合理设置突发参数
// 根据系统承受能力调整maxBurstSeconds
```

### 9.2 最佳实践
1. **监控与调整**：监控实际QPS，动态调整限流参数
2. **分级限流**：结合不同重要性API设置不同限流策略
3. **异常处理**：正确处理限流异常，提供友好降级
4. **配置外部化**：将限流参数配置化，便于动态调整

### 9.3 与其他限流方案对比
| 方案 | 优点 | 缺点 |
|------|------|------|
| Guava RateLimiter | 实现简单、无外部依赖、性能好 | 单机限流、不支持集群 |
| Redis限流 | 支持分布式、灵活性强 | 有网络开销、依赖Redis |
| Sentinel | 功能丰富、支持熔断降级 | 学习成本高、较重 |

## 10. 扩展与集成

### 10.1 与Spring集成
```java
@Component
public class RateLimitService {
    private final RateLimiter limiter;
    
    public RateLimitService(@Value("${rate.limit.qps:10}") double qps) {
        this.limiter = RateLimiter.create(qps);
    }
    
    @Aspect
    @Component
    public static class RateLimitAspect {
        @Around("@annotation(rateLimited)")
        public Object rateLimit(ProceedingJoinPoint pjp, RateLimited rateLimited) {
            if (limiter.tryAcquire()) {
                return pjp.proceed();
            }
            throw new RateLimitException("请求过于频繁");
        }
    }
}
```

### 10.2 自定义扩展
```java
// 实现可动态调整的限流器
public class DynamicRateLimiter {
    private volatile RateLimiter limiter;
    private double currentQps;
    
    public DynamicRateLimiter(double initialQps) {
        this.limiter = RateLimiter.create(initialQps);
        this.currentQps = initialQps;
    }
    
    public void updateRate(double newQps) {
        if (newQps != currentQps) {
            synchronized (this) {
                this.limiter = RateLimiter.create(newQps);
                this.currentQps = newQps;
            }
        }
    }
}
```

## 11. 版本兼容性

| Guava版本 | RateLimiter特性 |
|-----------|----------------|
| 22.0+ | 稳定版本，API基本稳定 |
| 16.0-21.0 | 早期版本，API可能有变化 |
| 31.0+ | 最新版本，推荐使用 |

## 12. 总结

Guava RateLimiter是一个轻量级、高性能的限流工具，适合单机限流场景。其令牌桶算法的实现兼顾了流量控制和突发处理能力，预热模式特别适合需要避免冷启动冲击的系统。虽然不支持分布式限流，但在大多数单机或微服务场景下，它提供了简单有效的流量控制解决方案。

**推荐使用场景**：单服务实例限流、客户端限流、资源访问控制等不需要分布式协调的限流需求。对于分布式系统限流，建议结合Redis或使用专门的限流中间件。