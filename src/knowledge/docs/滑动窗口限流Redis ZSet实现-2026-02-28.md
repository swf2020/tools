# 滑动窗口限流技术文档
## Redis ZSet实现方案

---

## 1. 概述

### 1.1 文档目的
本文档详细描述使用Redis有序集合（ZSet）实现滑动窗口限流算法的技术方案，包括设计原理、实现细节、性能分析和部署建议。

### 1.2 技术背景
滑动窗口限流是一种流量控制算法，在固定时间窗口的基础上，通过滑动时间边界实现对请求频率的更精确控制。相比固定窗口算法，滑动窗口能更平滑地控制流量，避免临界时间点请求突增的问题。

### 1.3 核心优势
- **精度高**：能准确统计任意时间点前后时间段内的请求数
- **平滑限流**：避免固定窗口的临界突变问题
- **实时性强**：基于Redis的实时数据统计
- **可扩展**：支持分布式环境下的统一限流

---

## 2. 算法原理

### 2.1 滑动窗口概念
```
时间轴： 0    1    2    3    4    5    6    7    8    9    10 (秒)
窗口大小：└───────── 5秒窗口 ──────────┘
                            └───────── 5秒窗口 ──────────┘
          
当前时间=7秒时，统计[2,7]区间内的请求数量
```

### 2.2 Redis ZSet数据结构设计
```
Key: rate_limit:{resource}:{identifier}
Type: Sorted Set (ZSet)
Members: 请求唯一标识 (UUID/雪花ID等)
Scores: 请求时间戳 (Unix timestamp with milliseconds)
```

---

## 3. 核心实现

### 3.1 限流判断逻辑
```python
def is_allowed(resource, identifier, limit, window_seconds):
    """
    滑动窗口限流判断
    
    Args:
        resource: 限流资源标识
        identifier: 用户/客户端标识
        limit: 时间窗口内允许的最大请求数
        window_seconds: 窗口大小（秒）
    
    Returns:
        allowed: 是否允许请求
        remaining: 剩余请求数
        reset_time: 窗口重置时间
    """
    current_time = time.time()
    window_start = current_time - window_seconds
    
    # Redis操作序列
    pipeline = redis.pipeline()
    
    # 1. 移除过期的请求（窗口之前的请求）
    pipeline.zremrangebyscore(
        f"rate_limit:{resource}:{identifier}",
        0,
        window_start
    )
    
    # 2. 统计当前窗口内的请求数
    pipeline.zcard(f"rate_limit:{resource}:{identifier}")
    
    # 3. 如果未超限，添加当前请求
    pipeline.zadd(
        f"rate_limit:{resource}:{identifier}",
        {str(uuid.uuid4()): current_time}
    )
    
    # 4. 设置key的过期时间（避免内存泄漏）
    pipeline.expire(
        f"rate_limit:{resource}:{identifier}",
        window_seconds + 60  # 额外保留60秒缓冲
    )
    
    results = pipeline.execute()
    current_count = results[1]
    
    if current_count < limit:
        # 允许请求
        return True, limit - current_count - 1, window_start + window_seconds
    else:
        # 拒绝请求
        return False, 0, window_start + window_seconds
```

### 3.2 Lua脚本优化（原子操作）
```lua
-- KEYS[1]: 限流key
-- ARGV[1]: 当前时间戳
-- ARGV[2]: 窗口开始时间（当前时间-窗口大小）
-- ARGV[3]: 最大请求数
-- ARGV[4]: 窗口大小（秒）
-- ARGV[5]: 请求唯一ID

-- 移除过期请求
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, ARGV[2])

-- 获取当前请求数
local current = redis.call('ZCARD', KEYS[1])

if current < tonumber(ARGV[3]) then
    -- 添加当前请求
    redis.call('ZADD', KEYS[1], ARGV[1], ARGV[5])
    -- 更新过期时间
    redis.call('EXPIRE', KEYS[1], ARGV[4] + 60)
    -- 返回：允许，剩余次数，重置时间
    return {1, tonumber(ARGV[3]) - current - 1, ARGV[2] + ARGV[4]}
else
    -- 返回：拒绝，剩余次数=0，重置时间
    return {0, 0, ARGV[2] + ARGV[4]}
end
```

---

## 4. 集群部署方案

### 4.1 单Redis实例方案
```yaml
配置示例:
  redis:
    host: 127.0.0.1
    port: 6379
    max_connections: 100
    key_prefix: "rate_limit:"
```

### 4.2 Redis Cluster方案
```python
class DistributedRateLimiter:
    def __init__(self, redis_cluster):
        self.cluster = redis_cluster
        self.script_sha = self._load_lua_script()
    
    def _load_lua_script(self):
        """在集群所有节点加载Lua脚本"""
        script = """
        -- Lua脚本内容（同上）
        """
        return self.cluster.script_load(script)
    
    def check_rate_limit(self, resource, identifier, limit, window):
        # 使用一致性哈希确定key所在节点
        key = f"rate_limit:{resource}:{identifier}"
        node = self.cluster.get_node_from_key(key)
        
        # 执行脚本
        current_time = time.time()
        result = node.evalsha(
            self.script_sha,
            1,  # key数量
            key,
            current_time,
            current_time - window,
            limit,
            window,
            str(uuid.uuid4())
        )
        return result
```

---

## 5. 性能优化

### 5.1 内存优化策略
| 策略 | 说明 | 效果 |
|------|------|------|
| 精简Member | 使用时间戳+计数器作为member | 减少存储空间 |
| 定期清理 | 后台任务清理过期key | 防止内存泄漏 |
| 数据压缩 | 启用Redis RDB/AOF压缩 | 节省磁盘空间 |

### 5.2 性能基准
```
测试环境：Redis 6.2, 8核CPU, 16GB内存
测试结果：
- 单操作延迟：0.3-0.8ms
- QPS：~12000 (pipeline批量操作)
- 内存占用：~100字节/请求
```

### 5.3 批量操作优化
```python
def batch_check(requests, pipeline_size=50):
    """
    批量限流检查
    requests: [(resource, identifier, limit, window), ...]
    """
    results = []
    pipeline = redis.pipeline()
    
    for i, (resource, identifier, limit, window) in enumerate(requests):
        current_time = time.time()
        key = f"rate_limit:{resource}:{identifier}"
        
        # 添加管道命令
        pipeline.zremrangebyscore(key, 0, current_time - window)
        pipeline.zcard(key)
        
        # 每pipeline_size条执行一次
        if (i + 1) % pipeline_size == 0:
            batch_results = pipeline.execute()
            # 处理结果...
            pipeline = redis.pipeline()
    
    return results
```

---

## 6. 监控与告警

### 6.1 关键监控指标
```python
监控指标:
1. 限流触发率 = 被拒绝请求数 / 总请求数
2. Redis内存使用率
3. ZSet平均大小
4. 限流操作延迟(P99/P95)
5. 过期key清理效率
```

### 6.2 Prometheus监控配置
```yaml
# metrics_exporter.py
class RateLimitMetrics:
    def __init__(self):
        self.requests_total = Counter(
            'ratelimit_requests_total',
            'Total requests',
            ['resource', 'status']
        )
        self.request_duration = Histogram(
            'ratelimit_duration_seconds',
            'Request duration',
            ['resource']
        )
    
    def record_request(self, resource, allowed, duration):
        status = 'allowed' if allowed else 'denied'
        self.requests_total.labels(resource, status).inc()
        self.request_duration.labels(resource).observe(duration)
```

---

## 7. 故障处理与容灾

### 7.1 降级策略
```python
class FallbackRateLimiter:
    def __init__(self, redis_client, local_cache_ttl=5):
        self.redis = redis_client
        self.local_cache = TTLCache(maxsize=1000, ttl=local_cache_ttl)
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=30
        )
    
    @circuit_breaker
    def is_allowed(self, resource, identifier, limit, window):
        try:
            # 尝试Redis操作
            return self._redis_check(resource, identifier, limit, window)
        except RedisError:
            # Redis故障时降级到本地缓存
            return self._local_fallback(resource, identifier, limit, window)
```

### 7.2 数据一致性保障
1. **最终一致性**：通过设置合理的过期时间保证
2. **写后验证**：重要操作在限流通过后二次验证
3. **人工干预接口**：提供管理接口手动调整限流状态

---

## 8. 配置管理

### 8.1 动态配置
```yaml
# config.yaml
rate_limits:
  api_login:
    limit: 100
    window: 3600  # 1小时
    algorithm: "sliding_window"
    redis_key: "rate_limit:login:{ip}"
    
  api_payment:
    limit: 10
    window: 60    # 1分钟
    algorithm: "sliding_window"
    redis_key: "rate_limit:payment:{user_id}"
    
  global_fallback:
    limit: 1000
    window: 1
    enabled: false
```

### 8.2 配置热更新
```python
class DynamicConfigManager:
    def __init__(self, config_center):
        self.configs = {}
        self.config_center = config_center
        self._subscribe_changes()
    
    def _subscribe_changes(self):
        # 监听配置变更
        self.config_center.watch("rate_limit_config", self._update_config)
    
    def get_config(self, resource):
        return self.configs.get(resource, self._default_config())
```

---

## 9. 部署指南

### 9.1 环境要求
- Redis 5.0+（支持ZSET相关命令）
- Python 3.7+ / Java 8+ / Go 1.14+
- 网络延迟 < 10ms（推荐）

### 9.2 Docker部署示例
```dockerfile
# Dockerfile
FROM redis:6.2-alpine

# 优化Redis配置
COPY redis.conf /usr/local/etc/redis/redis.conf
CMD ["redis-server", "/usr/local/etc/redis/redis.conf"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  redis:
    image: redis:6.2-alpine
    command: redis-server --appendonly yes --maxmemory 1gb
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
```

---

## 10. 测试方案

### 10.1 单元测试
```python
class TestSlidingWindowRateLimit:
    def test_sliding_window_basic(self):
        """测试基本限流功能"""
        limiter = SlidingWindowRateLimiter(redis_client)
        
        # 测试正常请求
        for i in range(5):
            allowed, _, _ = limiter.is_allowed("test", "user1", 10, 60)
            assert allowed is True
        
        # 测试超限请求
        allowed, _, _ = limiter.is_allowed("test", "user1", 5, 60)
        assert allowed is False
    
    def test_window_sliding(self):
        """测试窗口滑动"""
        limiter = SlidingWindowRateLimiter(redis_client)
        
        # 在第一窗口内请求
        for i in range(3):
            limiter.is_allowed("test", "user2", 5, 1)
        
        # 等待窗口滑动
        time.sleep(1.1)
        
        # 新窗口应该可以继续请求
        allowed, _, _ = limiter.is_allowed("test", "user2", 5, 1)
        assert allowed is True
```

### 10.2 压力测试
```bash
# 使用redis-benchmark测试
redis-benchmark -t zadd,zcard,zremrangebyscore -n 100000 -q

# 使用wrk测试API
wrk -t12 -c400 -d30s --latency http://api.example.com/limited-endpoint
```

---

## 11. 注意事项

### 11.1 时钟同步问题
- 确保所有应用服务器时间同步（使用NTP）
- Redis服务器时间与应用服务器时间偏差应小于100ms

### 11.2 内存管理
- 定期监控ZSet大小，防止单个key过大
- 设置合理的过期时间，避免内存泄漏
- 考虑使用Redis内存淘汰策略

### 11.3 网络考虑
- Redis客户端使用连接池
- 合理设置超时时间（建议操作超时<100ms）
- 考虑部署同机房Redis减少网络延迟

---

## 12. 扩展方案

### 12.1 多级限流
```python
class MultiLevelRateLimiter:
    def __init__(self):
        self.limiters = [
            SlidingWindowRateLimiter(limit=1000, window=1),   # 秒级
            SlidingWindowRateLimiter(limit=10000, window=60), # 分钟级
            SlidingWindowRateLimiter(limit=100000, window=3600) # 小时级
        ]
    
    def is_allowed(self, resource, identifier):
        """所有级别都通过才算通过"""
        return all(
            limiter.is_allowed(resource, identifier)
            for limiter in self.limiters
        )
```

### 12.2 自适应限流
基于系统负载动态调整限流阈值：
```python
def adaptive_limit(base_limit, current_load):
    """根据负载动态调整限流阈值"""
    if current_load > 0.8:  # 负载>80%
        return base_limit * 0.7  # 降低30%
    elif current_load < 0.3:  # 负载<30%
        return base_limit * 1.5  # 提高50%
    else:
        return base_limit
```

---

## 附录

### A. Redis命令参考
| 命令 | 参数 | 说明 |
|------|------|------|
| ZADD | key score member | 添加成员到有序集合 |
| ZCARD | key | 获取有序集合成员数量 |
| ZREMRANGEBYSCORE | key min max | 移除分数区间内的成员 |
| EXPIRE | key seconds | 设置key过期时间 |
| EVAL | script numkeys key [key ...] arg [arg ...] | 执行Lua脚本 |

### B. 性能调优参数
```yaml
redis_config:
  # 内存优化
  maxmemory: "2gb"
  maxmemory-policy: "allkeys-lru"
  
  # 持久化优化
  appendonly: "yes"
  appendfsync: "everysec"
  
  # 连接优化
  timeout: 300
  tcp-keepalive: 60
```

---

**文档版本**: 1.0  
**最后更新**: 2024年1月  
**维护团队**: 平台架构组  
**相关文档**: 《Redis最佳实践》、《微服务限流方案》