# Redis大Key治理方案：扫描、拆分与异步删除(UNLINK)

## 1. 概述

Redis中的"大Key"通常指存储了大量数据的Key，例如：
- String类型：值大小超过10KB
- Hash/Set/Zset/List类型：元素数量超过5000个

大Key会带来以下问题：
- 内存分配不均，影响集群数据均衡
- 操作耗时增加，可能阻塞Redis单线程
- 网络传输延迟，影响客户端响应
- 数据迁移困难，影响扩缩容效率

## 2. 大Key扫描与识别

### 2.1 内置工具扫描

**Redis内置命令：**
```bash
# 分析当前数据库的Key空间
redis-cli --bigkeys

# 带采样限制的扫描（避免阻塞）
redis-cli --bigkeys -i 0.1  # 每100个key休眠0.1秒
```

**输出示例：**
```
[00.00%] Biggest string found so far 'user:1000:data' with 102400 bytes
[12.34%] Biggest hash   found so far 'product:8888:tags' with 50000 fields
```

### 2.2 内存分析工具

**使用redis-rdb-tools分析RDB文件：**
```bash
# 安装
pip install rdbtools

# 生成内存报告
rdb -c memory dump.rdb --bytes 10240 --largest 20 > memory_report.csv
```

### 2.3 自定义扫描脚本

```python
import redis
from concurrent.futures import ThreadPoolExecutor

class BigKeyScanner:
    def __init__(self, host='localhost', port=6379):
        self.client = redis.Redis(host=host, port=port, decode_responses=True)
    
    def scan_big_keys(self, threshold_kb=10, batch_size=1000):
        """扫描大Key"""
        cursor = 0
        big_keys = []
        
        while True:
            cursor, keys = self.client.scan(
                cursor=cursor,
                count=batch_size
            )
            
            for key in keys:
                key_type = self.client.type(key)
                size = self._get_key_size(key, key_type)
                
                if size > threshold_kb * 1024:
                    big_keys.append({
                        'key': key,
                        'type': key_type,
                        'size_kb': size / 1024
                    })
            
            if cursor == 0:
                break
        
        return sorted(big_keys, key=lambda x: x['size_kb'], reverse=True)
    
    def _get_key_size(self, key, key_type):
        """获取Key大小（近似值）"""
        if key_type == 'string':
            return self.client.memory_usage(key)
        elif key_type == 'hash':
            return self.client.hlen(key) * 100  # 近似估算
        elif key_type == 'list':
            return self.client.llen(key) * 100
        elif key_type == 'set':
            return self.client.scard(key) * 100
        elif key_type == 'zset':
            return self.client.zcard(key) * 100
        
        return 0
```

## 3. 大Key拆分策略

### 3.1 String类型拆分

**原始大Key：**
```bash
SET user:1000:profile "{...很大的JSON数据...}"
```

**拆分方案：**
```python
def split_large_string(key, chunk_size=10240):
    """拆分大字符串"""
    data = client.get(key)
    chunks = [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]
    
    # 存储分片
    for i, chunk in enumerate(chunks):
        client.set(f"{key}:chunk:{i}", chunk)
    
    # 存储元数据
    metadata = {
        'chunk_count': len(chunks),
        'total_size': len(data)
    }
    client.hset(f"{key}:metadata", mapping=metadata)
    
    # 删除原Key
    client.delete(key)
```

### 3.2 Hash类型拆分

**按字段前缀拆分：**
```python
def split_large_hash(key, shard_count=10):
    """拆分大Hash"""
    all_items = client.hgetall(key)
    
    for field, value in all_items.items():
        # 使用字段名的hash决定分片
        shard_index = hash(field) % shard_count
        shard_key = f"{key}:shard_{shard_index}"
        client.hset(shard_key, field, value)
    
    # 维护分片路由
    routing_key = f"{key}:routing"
    client.set(routing_key, shard_count)
    
    client.delete(key)

# 读取时按路由查询
def get_hash_value(key, field):
    routing_key = f"{key}:routing"
    shard_count = int(client.get(routing_key))
    shard_index = hash(field) % shard_count
    shard_key = f"{key}:shard_{shard_index}"
    return client.hget(shard_key, field)
```

### 3.3 List/Set/Zset拆分

**基于元素范围拆分：**
```python
def split_large_list(key, batch_size=1000):
    """拆分大List"""
    total_len = client.llen(key)
    
    for i in range(0, total_len, batch_size):
        chunk_key = f"{key}:chunk:{i//batch_size}"
        # 获取并存储分片
        elements = client.lrange(key, i, min(i+batch_size-1, total_len-1))
        if elements:
            client.rpush(chunk_key, *elements)
    
    # 存储分片信息
    chunk_count = (total_len + batch_size - 1) // batch_size
    client.set(f"{key}:metadata", chunk_count)
    client.delete(key)
```

## 4. 异步删除(UNLINK)

### 4.1 DEL vs UNLINK

**传统DEL命令（同步阻塞）：**
```bash
# 同步删除，对于大Key可能阻塞Redis
DEL large_hash_key
```

**UNLINK命令（异步非阻塞）：**
```bash
# 异步删除，立即返回，后台线程执行删除
UNLINK large_hash_key

# 批量异步删除
UNLINK key1 key2 key3
```

### 4.2 渐进式删除方案

**对于超大型Key，使用渐进式删除：**
```python
def gradual_delete_hash(key, batch_size=100):
    """渐进式删除大Hash"""
    while True:
        # 每次扫描并删除一批字段
        cursor, fields = client.hscan(key, count=batch_size)
        
        if fields:
            client.hdel(key, *fields.keys())
        
        if cursor == 0:
            break
    
    # 最后删除空Key
    client.unlink(key)

def gradual_delete_list(key, batch_size=100):
    """渐进式删除大List"""
    while client.llen(key) > 0:
        # 从左侧批量弹出
        client.ltrim(key, batch_size, -1)
    
    client.unlink(key)
```

### 4.3 内存回收配置

**Redis配置优化：**
```conf
# 启用惰性删除（默认已启用）
lazyfree-lazy-eviction yes
lazyfree-lazy-expire yes
lazyfree-lazy-server-del yes

# 异步删除参数配置
lazyfree-lazy-user-del yes

# 最大内存策略
maxmemory 16gb
maxmemory-policy allkeys-lru
```

## 5. 监控与预防

### 5.1 实时监控脚本

```python
import time
from prometheus_client import Gauge, start_http_server

class BigKeyMonitor:
    def __init__(self):
        self.big_key_count = Gauge('redis_big_key_count', 
                                  'Number of big keys detected')
        self.key_size_distribution = Gauge('redis_key_size_bytes',
                                          'Key size distribution',
                                          ['type'])
    
    def continuous_monitor(self, interval=300):
        """持续监控大Key"""
        while True:
            big_keys = scanner.scan_big_keys()
            self.big_key_count.set(len(big_keys))
            
            for key_info in big_keys:
                self.key_size_distribution.labels(
                    type=key_info['type']
                ).set(key_info['size_kb'] * 1024)
            
            time.sleep(interval)

# 启动监控服务
monitor = BigKeyMonitor()
start_http_server(8000)
monitor.continuous_monitor()
```

### 5.2 写入时检查

```python
class SafeRedisClient:
    def __init__(self, max_size_kb=10):
        self.client = redis.Redis()
        self.max_size = max_size_kb * 1024
    
    def safe_hset(self, key, field, value):
        """安全的Hash写入"""
        current_size = self.client.hlen(key) * 100  # 近似计算
        if current_size + len(value) > self.max_size:
            raise ValueError(f"Key {key} will exceed size limit")
        
        return self.client.hset(key, field, value)
    
    def safe_rpush(self, key, *values):
        """安全的List写入"""
        current_size = self.client.llen(key) * 100
        new_data_size = sum(len(str(v)) for v in values)
        
        if current_size + new_data_size > self.max_size:
            raise ValueError(f"Key {key} will exceed size limit")
        
        return self.client.rpush(key, *values)
```

## 6. 最佳实践建议

### 6.1 设计阶段预防
- 合理设计数据结构，避免单个Key存储过多数据
- 预估数据增长，提前规划分片方案
- 使用合适的数据类型，避免用String存储复杂结构

### 6.2 运维阶段管理
- 建立定期扫描机制，每周至少扫描一次
- 设置监控告警，当出现大Key时及时通知
- 建立大Key处理流程，规范拆分和删除操作

### 6.3 代码规范
- 封装Redis客户端，加入大小检查
- 关键操作添加日志记录
- 实现自动拆分机制

## 7. 总结

Redis大Key治理是一个系统性的工程，需要：
1. **定期扫描**：及时发现潜在问题
2. **合理拆分**：根据业务特点选择分片策略
3. **异步删除**：使用UNLINK避免阻塞服务
4. **监控预防**：建立长效机制防止问题复现

通过上述方案的实施，可以有效解决大Key带来的性能问题，保障Redis服务的稳定运行。