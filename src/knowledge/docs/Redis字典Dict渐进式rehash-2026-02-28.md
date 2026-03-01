# Redis字典(Dict)渐进式rehash机制详解

## 1. 概述

Redis字典（Dict）是Redis中用于实现键值对存储的核心数据结构，采用哈希表实现。当哈希表需要扩容或缩容时，Redis采用**渐进式rehash**机制来保证服务的高可用性和性能。

## 2. 为什么需要渐进式rehash

### 2.1 传统rehash的问题
传统的rehash操作需要一次性完成所有键的重新哈希和迁移，当哈希表中包含大量键值对时（如百万级别），这个过程会导致：
- **服务长时间阻塞**：Redis是单线程模型，rehash期间无法处理其他请求
- **响应延迟激增**：客户端请求会经历显著的延迟

### 2.2 Redis的解决方案
渐进式rehash将rehash过程分摊到多个操作中逐步完成，避免长时间阻塞。

## 3. 数据结构设计

### 3.1 哈希表结构
```c
typedef struct dictht {
    dictEntry **table;       // 哈希表数组
    unsigned long size;      // 哈希表大小
    unsigned long sizemask;  // 大小掩码，用于计算索引值
    unsigned long used;      // 已有节点数量
} dictht;

typedef struct dict {
    dictType *type;          // 类型特定函数
    void *privdata;          // 私有数据
    dictht ht[2];            // 两个哈希表
    long rehashidx;          // rehash索引，-1表示未进行rehash
    int16_t pauserehash;     // rehash暂停标识
} dict;
```

### 3.2 关键字段说明
- `ht[0]`：日常使用的哈希表
- `ht[1]`：rehash过程中使用的临时哈希表
- `rehashidx`：记录rehash进度，从0开始，每完成一个桶的迁移就加1

## 4. 渐进式rehash流程

### 4.1 触发条件
```python
# 伪代码：检查是否需要rehash
def dictCheckIfNeedsResize(dict):
    # 扩容条件：负载因子 >= 1且允许resize
    if load_factor >= 1 and dict_can_resize:
        return EXPAND
    
    # 缩容条件：负载因子 < 0.1
    if load_factor < 0.1:
        return SHRINK
    
    return NO_RESIZE_NEEDED
```

### 4.2 rehash过程
1. **初始化阶段**：
   - 为`ht[1]`分配空间（扩容为`ht[0].used * 2`的2^n，缩容为能容纳所有元素的最小2^n）
   - 设置`rehashidx = 0`，开始rehash

2. **渐进迁移阶段**：
   - 每次对字典的**增删改查操作**都会触发一个桶的迁移
   - 每次迁移`ht[0].table[rehashidx]`桶中的所有元素到`ht[1]`
   - `rehashidx`递增，直到所有桶迁移完成

3. **完成阶段**：
   - 释放`ht[0]`的空间
   - 将`ht[1]`设置为`ht[0]`
   - 创建新的`ht[1]`为空表
   - 设置`rehashidx = -1`

### 4.3 操作期间的查找逻辑
```c
// 伪代码：rehash期间的查找操作
dictEntry *dictFind(dict *d, const void *key) {
    // 如果正在rehash，执行一次渐进式rehash步骤
    if (dictIsRehashing(d)) _dictRehashStep(d);
    
    // 先在ht[0]中查找
    h = dictHashKey(d, key);
    for (table = 0; table <= 1; table++) {
        idx = h & d->ht[table].sizemask;
        he = d->ht[table].table[idx];
        while(he) {
            if (dictCompareKeys(d, key, he->key))
                return he;
            he = he->next;
        }
        // 如果不在rehash，不需要检查ht[1]
        if (!dictIsRehashing(d)) break;
    }
    return NULL;
}
```

## 5. 定时任务辅助rehash

除了操作触发的渐进迁移外，Redis还通过定时任务加速rehash过程：

```c
// 服务器定时任务中调用
void databasesCron(void) {
    // 如果服务器未运行，跳过rehash
    if (server.inactive) return;
    
    // 对每个数据库进行渐进式rehash
    for (j = 0; j < server.dbnum; j++) {
        // 每次最多迁移N个空桶
        int work_done = incrementallyRehash(server.db[j].dict, N);
        if (work_done) break; // 一次循环只处理一个数据库
    }
}
```

## 6. 优势分析

### 6.1 性能优势
- **无感知扩容**：客户端基本感受不到rehash带来的延迟
- **平滑迁移**：将计算开销分摊到多个操作中
- **避免内存峰值**：不需要同时保存三份数据（旧表、新表、迁移中的数据）

### 6.2 可用性优势
- **服务不中断**：整个rehash过程中Redis持续提供服务
- **响应时间可控**：单次迁移操作的时间复杂度为O(1)

## 7. 注意事项与优化

### 7.1 rehash期间的特别处理
1. **新增操作**：直接写入`ht[1]`，确保新数据不会丢失
2. **删除操作**：同时检查两个哈希表
3. **更新操作**：先删除旧值，再添加新值到`ht[1]`

### 7.2 内存管理优化
```c
// 批量迁移空桶优化
int dictRehashMilliseconds(dict *d, int ms) {
    long long start = timeInMilliseconds();
    int empty_visits = 0;
    
    while(dictRehash(d, 100)) {
        // 每次迁移100个桶
        if (timeInMilliseconds() - start > ms) break;
        
        // 如果遇到空桶，计数并继续
        if (d->ht[0].table[d->rehashidx] == NULL) {
            empty_visits++;
            if (empty_visits > 10) break; // 避免过多空桶遍历
        }
    }
    return 1;
}
```

### 7.3 监控指标
```bash
# Redis info命令输出的相关指标
redis-cli info stats | grep rehash
# 重要指标：
# - instantaneous_ops_per_sec: 每秒操作数
# - keyspace_hits: 命中次数
# - keyspace_misses: 未命中次数
# - used_memory: 内存使用量
```

## 8. 实际应用场景

### 8.1 大键迁移
当包含数百万键的哈希表需要rehash时：
```python
# 监控rehash进度示例
def monitor_rehash_progress(redis_client, key):
    info = redis_client.info('stats')
    # 通过比较used_memory和键数量估算进度
    
    # 或者使用自定义脚本
    progress = redis_client.eval("""
        local dict = redis.call('DEBUG', 'HTSTATS', KEYS[1])
        return dict['rehashidx'] or -1
    """, 1, key)
    return progress
```

### 8.2 性能调优建议
1. **避免在高峰期触发rehash**：通过`CONFIG SET activerehashing no`临时关闭
2. **预扩容机制**：在业务低峰期主动触发扩容
3. **监控告警**：设置内存使用率和操作延迟的监控阈值

## 9. 总结

Redis的渐进式rehash机制是其高性能设计的重要组成部分，它通过：
- 将rehash操作分摊到多次请求中
- 在rehash期间保持服务可用性
- 结合定时任务加速迁移过程

这种设计使得Redis能够在不影响服务的前提下，动态调整哈希表大小，适应不同负载场景，是Redis高可用、高性能架构的关键支撑技术之一。

---

**附录：相关配置参数**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `hash-max-ziplist-entries` | 512 | 使用ziplist编码的最大元素数 |
| `hash-max-ziplist-value` | 64 | 使用ziplist编码的最大值大小 |
| `activerehashing` | yes | 是否启用主动rehash |
| `hz` | 10 | 定时任务执行频率 |

*注：本文基于Redis 6.2+版本，不同版本实现细节可能有所差异。*