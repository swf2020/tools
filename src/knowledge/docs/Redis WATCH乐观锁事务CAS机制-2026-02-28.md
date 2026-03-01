# Redis WATCH乐观锁事务（CAS机制）

## 1. 概述

### 1.1 乐观锁与悲观锁
- **悲观锁**：假定并发冲突大概率发生，在操作数据前先加锁（如SELECT...FOR UPDATE）
- **乐观锁**：假定并发冲突概率较低，通过版本号/时间戳机制实现无锁并发控制
- **CAS（Compare And Swap）**：乐观锁的核心实现机制，先检查后修改

### 1.2 Redis事务特点
Redis事务与传统关系型数据库事务（ACID）有本质区别：
- **不支持回滚**：命令执行错误会继续执行后续命令
- **无隔离级别概念**：所有命令在EXEC时按顺序原子执行
- **WATCH机制**：提供CAS风格的乐观锁支持

## 2. WATCH机制详解

### 2.1 核心命令
```redis
WATCH key [key ...]      # 监视一个或多个键
MULTI                    # 开始事务块
# ... 多个命令 ...
EXEC                     # 执行事务（如果被监视键未被修改）
DISCARD                  # 取消事务，取消对所有键的监视
UNWATCH                  # 取消所有WATCH
```

### 2.2 工作流程
```
客户端A                          Redis服务器                      客户端B
    |                               |                               |
WATCH stock_count                  记录监视键                       |
    |----------------------------->|                               |
    |                               |                               |
MULTI                             准备事务队列                      |
    |----------------------------->|                               |
    |                               |                               |
DECR stock_count                   命令入队                         |
    |----------------------------->|                               |
    |                               |                               |
    |                               |<------------------------------|
    |                               |   客户端B修改了stock_count    |
    |                               |                               |
EXEC                              检测到监视键被修改                 |
    |----------------------------->|                               |
    |                               |                               |
    |<- (nil) 事务执行失败 ---------|                               |
```

### 2.3 执行结果
- **EXEC成功**：返回事务中所有命令执行结果的数组
- **EXEC失败**：返回`nil`，所有命令都不执行

## 3. 代码示例

### 3.1 Python示例
```python
import redis
import time
import threading

class RedisOptimisticLock:
    def __init__(self, host='localhost', port=6379):
        self.redis = redis.Redis(host=host, port=port, decode_responses=True)
        
    def safe_decrement_with_retry(self, key, max_retries=5):
        """安全的递减操作，带重试机制"""
        for retry in range(max_retries):
            try:
                # 1. 开始监视
                self.redis.watch(key)
                
                # 2. 获取当前值并检查
                current_value = int(self.redis.get(key) or 0)
                if current_value <= 0:
                    self.redis.unwatch()
                    return False, "库存不足"
                
                # 3. 开启事务
                pipe = self.redis.pipeline()
                
                # 4. 命令入队
                pipe.multi()
                pipe.decr(key)
                
                # 5. 执行事务
                result = pipe.execute()
                
                # 如果result不为None，说明执行成功
                if result is not None:
                    print(f"第{retry + 1}次尝试成功: 新值={result[0]}")
                    return True, result[0]
                else:
                    print(f"第{retry + 1}次尝试失败，重试中...")
                    time.sleep(0.1)  # 短暂等待后重试
                    
            except Exception as e:
                print(f"操作异常: {e}")
                return False, str(e)
                
        return False, "超过最大重试次数"

# 并发测试
def test_concurrent_update():
    r = redis.Redis(decode_responses=True)
    r.set('inventory', 10)  # 初始化库存
    
    lock = RedisOptimisticLock()
    
    def worker(worker_id):
        success, result = lock.safe_decrement_with_retry('inventory')
        print(f"Worker {worker_id}: {'成功' if success else '失败'} - {result}")
    
    # 启动15个线程并发操作（库存只有10）
    threads = []
    for i in range(15):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    print(f"最终库存: {r.get('inventory')}")

if __name__ == "__main__":
    test_concurrent_update()
```

### 3.2 Java示例（Jedis）
```java
import redis.clients.jedis.Jedis;
import redis.clients.jedis.Response;
import redis.clients.jedis.Transaction;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class RedisWatchExample {
    
    public static class InventoryService {
        private Jedis jedis;
        
        public InventoryService(String host, int port) {
            this.jedis = new Jedis(host, port);
        }
        
        public boolean safePurchase(String productKey, int quantity) {
            int maxRetries = 3;
            int retryCount = 0;
            
            while (retryCount < maxRetries) {
                try {
                    // 监视库存键
                    jedis.watch(productKey);
                    
                    // 获取当前库存
                    String currentStock = jedis.get(productKey);
                    int stock = currentStock == null ? 0 : Integer.parseInt(currentStock);
                    
                    // 库存检查
                    if (stock < quantity) {
                        jedis.unwatch();
                        return false; // 库存不足
                    }
                    
                    // 开始事务
                    Transaction tx = jedis.multi();
                    tx.decrBy(productKey, quantity);
                    
                    // 执行事务
                    List<Object> results = tx.exec();
                    
                    // 检查执行结果
                    if (results == null || results.isEmpty()) {
                        // 事务执行失败，重试
                        retryCount++;
                        System.out.println("事务冲突，第" + retryCount + "次重试");
                        Thread.sleep(50); // 短暂等待
                    } else {
                        // 执行成功
                        Long newStock = (Long) results.get(0);
                        System.out.println("购买成功，新库存: " + newStock);
                        return true;
                    }
                } catch (Exception e) {
                    e.printStackTrace();
                    jedis.unwatch();
                    break;
                }
            }
            return false; // 超过最大重试次数
        }
    }
    
    public static void main(String[] args) {
        // 测试代码
        InventoryService service = new InventoryService("localhost", 6379);
        
        // 初始化库存
        service.jedis.set("product:001:stock", "100");
        
        // 模拟并发购买
        ExecutorService executor = Executors.newFixedThreadPool(10);
        for (int i = 0; i < 20; i++) {
            final int threadId = i;
            executor.submit(() -> {
                boolean success = service.safePurchase("product:001:stock", 15);
                System.out.println("线程" + threadId + ": " + (success ? "购买成功" : "购买失败"));
            });
        }
        
        executor.shutdown();
    }
}
```

## 4. 应用场景

### 4.1 典型用例
1. **库存扣减**
   - 电商秒杀场景
   - 票务系统座位锁定

2. **余额操作**
   - 转账业务（检查余额是否充足）
   - 账户扣款

3. **计数器控制**
   - 限制用户操作频率
   - 全局序列生成

4. **配置更新**
   - 确保配置的原子更新
   - 避免并发修改导致的配置不一致

### 4.2 使用模式
```python
# 通用模板
def optimistic_update(key, update_logic, max_retries=3):
    for attempt in range(max_retries):
        try:
            redis.watch(key)
            
            # 读取当前状态
            current_state = redis.get(key)
            
            # 业务逻辑判断
            if not business_check(current_state):
                redis.unwatch()
                return False
            
            # 开始事务
            pipe = redis.pipeline()
            pipe.multi()
            
            # 应用更新逻辑
            update_logic(pipe)
            
            # 执行事务
            result = pipe.execute()
            
            if result is not None:
                return True  # 成功
            else:
                continue  # 冲突，重试
                
        except Exception as e:
            redis.unwatch()
            raise e
    
    return False  # 超过最大重试次数
```

## 5. 注意事项与最佳实践

### 5.1 性能考虑
1. **WATCH键数量**
   - 避免监视大量键，会增加冲突概率
   - 只监视真正需要检查的键

2. **事务复杂度**
   - 事务中的命令不宜过多
   - 避免在事务中执行耗时操作

3. **重试策略**
   - 设置合理的最大重试次数（通常3-5次）
   - 重试间添加随机延迟，避免活锁
   ```python
   # 指数退避策略
   delay = min(0.1 * (2 ** retry_count), 1.0)  # 最大1秒
   time.sleep(delay + random.uniform(0, 0.1))   # 添加随机性
   ```

### 5.2 正确性保证
1. **连接管理**
   - WATCH与事务必须在同一个连接中执行
   - 使用连接池时确保连接的正确获取和释放

2. **异常处理**
   ```python
   try:
       redis.watch('key')
       # ... 业务逻辑
       redis.unwatch()  # 成功时明确取消监视
   except Exception as e:
       redis.unwatch()  # 异常时也要取消监视
       raise
   ```

3. **ABA问题**
   - Redis的WATCH机制不解决ABA问题
   - 如果业务需要严格的版本控制，需自行实现版本号机制
   ```redis
   WATCH item:stock item:version
   current_version = GET item:version
   MULTI
   SET item:stock new_value
   INCR item:version
   EXEC
   ```

### 5.3 限制与替代方案
1. **Redis WATCH的限制**
   - 不适合高冲突场景（重试开销大）
   - 无法实现跨键的复杂约束检查
   - 集群模式下WATCH限制更严格（需确保键在同一slot）

2. **替代方案**
   - **Lua脚本**：真正的原子操作，适合简单逻辑
     ```lua
     local current = redis.call('GET', KEYS[1])
     if tonumber(current) >= tonumber(ARGV[1]) then
         return redis.call('DECRBY', KEYS[1], ARGV[1])
     else
         return -1
     end
     ```
   - **分布式锁**：Redlock算法，适合复杂业务逻辑
   - **Redis 6.2+**：`GETEX`、`GETDEL`等新命令提供更多原子操作

## 6. 监控与调试

### 6.1 监控指标
```bash
# 查看Redis监控信息
redis-cli info stats | grep -E "(rejected_connections|sync_full|sync_partial)"

# 监控事务相关指标
redis-cli info stats | grep -E "(total_commands_processed|total_connections_received)"
```

### 6.2 调试技巧
```python
# 1. 启用Redis慢查询日志
redis.config_set('slowlog-log-slower-than', 10000)  # 10毫秒
redis.slowlog_get(10)  # 获取最近10条慢查询

# 2. 事务追踪
import logging
logging.basicConfig(level=logging.DEBUG)

# 3. 模拟并发测试
def stress_test():
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(update_function) for _ in range(1000)]
        results = [f.result() for f in futures]
        success_rate = sum(results) / len(results)
        print(f"成功率: {success_rate:.2%}")
```

## 7. 总结

Redis WATCH机制提供了基于乐观锁的轻量级事务支持，适用于低冲突并发场景：

**优点：**
- 无锁设计，性能较好
- 实现简单，易于理解
- 避免死锁问题

**缺点：**
- 高冲突场景下性能下降明显
- 需要客户端实现重试逻辑
- 功能相对有限（相比关系型数据库事务）

**选择建议：**
- 低冲突、简单操作用WATCH
- 复杂原子操作用Lua脚本
- 分布式强一致需求用分布式锁+WATCH组合
- Redis 7.0+考虑使用Redis事务的增强功能

在实际应用中，应根据具体业务场景、并发程度和数据一致性要求，选择合适的并发控制方案。