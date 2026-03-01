# Redis Cluster哈希槽CRC16分配与迁移技术文档

## 1. 引言

Redis Cluster是Redis官方提供的分布式解决方案，通过分片（sharding）机制将数据分布到多个节点。为了在集群中均匀分布数据并实现动态扩展，Redis Cluster采用了**哈希槽（Hash Slot）**的概念，配合CRC16算法实现键到槽的映射。本文将深入探讨Redis Cluster中哈希槽的分配机制、迁移过程及相关实现细节。

---

## 2. Redis Cluster概述

Redis Cluster是一个去中心化的分布式系统，具有以下关键特性：
- **自动分片**：数据被分割到16384个哈希槽中
- **高可用性**：支持主从复制和故障自动转移
- **无代理架构**：客户端直接与集群节点通信
- **线性扩展**：可动态添加或删除节点

---

## 3. 哈希槽与CRC16算法

### 3.1 哈希槽的概念
- Redis Cluster将整个数据集划分为**16384个固定数量的槽位**（0-16383）
- 每个键通过哈希函数映射到特定的槽
- 每个节点负责处理分配给它的槽位集合

### 3.2 CRC16算法实现
Redis使用CRC16算法计算键的哈希值，具体实现如下：

```c
// Redis中的CRC16实现（简化版）
unsigned int crc16(const char *buf, int len) {
    unsigned int crc = 0;
    static const unsigned int crc16tab[256] = { /* 预计算表 */ };
    
    for (int i = 0; i < len; i++) {
        crc = (crc >> 8) ^ crc16tab[(crc ^ buf[i]) & 0xff];
    }
    return crc;
}

// 计算槽位
unsigned int keyHashSlot(const char *key, int keylen) {
    // 查找第一个'{'和'}'之间的内容作为哈希标签
    int s, e;
    for (s = 0; s < keylen; s++) {
        if (key[s] == '{') break;
    }
    
    // 没有找到有效的哈希标签，使用整个键
    if (s == keylen) return crc16(key, keylen) & 16383;
    
    for (e = s+1; e < keylen; e++) {
        if (key[e] == '}') break;
    }
    
    // 找到有效的哈希标签，使用标签内容计算
    if (e < keylen && e != s+1) {
        return crc16(key+s+1, e-s-1) & 16383;
    }
    
    // 使用整个键
    return crc16(key, keylen) & 16383;
}
```

### 3.3 哈希标签（Hash Tags）
为了提高相关键在同一个槽中的可能性，Redis支持**哈希标签**：
- 格式：`{tag}...`
- 示例：`user:{1000}:profile`和`user:{1000}:orders`会被分配到同一槽

---

## 4. 哈希槽的分配

### 4.1 槽位分配机制
```python
# 槽位分配算法示例
def assign_slots(nodes_count, slots_per_node=16384):
    slots_per_node = 16384 // nodes_count
    remainder = 16384 % nodes_count
    
    assignments = {}
    slot = 0
    for i in range(nodes_count):
        node_slots = slots_per_node
        if i < remainder:
            node_slots += 1
        
        assignments[f"node-{i}"] = list(range(slot, slot + node_slots))
        slot += node_slots
    
    return assignments
```

### 4.2 集群配置信息
每个节点维护的集群状态信息包括：
- **clusterState**：记录集群中所有节点的信息
- **clusterNode**：记录单个节点的信息，包括负责的槽位

```c
typedef struct clusterState {
    clusterNode *myself;      // 当前节点
    clusterNode *slots[16384]; // 槽位到节点的映射
    dict *nodes;              // 集群中所有节点
} clusterState;

typedef struct clusterNode {
    char *name;               // 节点ID
    unsigned char slots[16384/8]; // 位图表示负责的槽位
    clusterNode **slots_info; // 槽位详细信息
} clusterNode;
```

---

## 5. 哈希槽的迁移

### 5.1 迁移触发场景
1. **集群扩容**：添加新节点后重新分配槽位
2. **集群缩容**：移除节点前迁移槽位
3. **负载均衡**：调整节点间的槽位分布
4. **故障恢复**：主节点故障后重新分配槽位

### 5.2 迁移过程详解

#### 步骤1：准备迁移
```bash
# 启动槽16384迁移
redis-cli --cluster reshard <host>:<port>
# 或使用命令
CLUSTER SETSLOT <slot> IMPORTING <source-node-id>
CLUSTER SETSLOT <slot> MIGRATING <target-node-id>
```

#### 步骤2：数据迁移
```c
// 迁移单个键的伪代码
void migrateKey(redisDb *db, robj *key, clusterNode *target) {
    // 1. 序列化键值对
    rio payload;
    rioInitWithBuffer(&payload, sdsempty());
    rdbSaveObject(&payload, key, db->dict[key]);
    
    // 2. 发送到目标节点
    clusterSendMigrate(target, key->ptr, sdslen(key->ptr), 
                      payload.io.buffer.ptr, 
                      sdslen(payload.io.buffer.ptr));
    
    // 3. 从源节点删除（异步）
    dbDelete(db, key);
}
```

#### 步骤3：迁移流程
```
┌─────────┐    1.设置迁移状态    ┌─────────┐
│ 源节点  │◄───────────────────►│ 目标节点 │
│         │    2.批量迁移键      │         │
└────┬────┘                     └────┬────┘
     │3.原子设置槽位所有权            │
     └───────────────────────────────┘
```

### 5.3 渐进式迁移策略
Redis采用渐进式迁移避免服务中断：
1. **分批次迁移**：每次迁移少量键
2. **双写机制**：迁移期间客户端可向源节点或目标节点写入
3. **原子切换**：迁移完成后原子更新槽位映射

### 5.4 迁移状态管理
迁移过程中槽位有三种状态：
- **STABLE**：槽位稳定，由单一节点服务
- **MIGRATING**：槽位正在从当前节点迁出
- **IMPORTING**：槽位正在被目标节点导入

---

## 6. 客户端在迁移期间的处理

### 6.1 智能客户端行为
```java
public class RedisClusterClient {
    public Object handleCommand(String key, String command) {
        int slot = calculateSlot(key);
        RedisNode node = slotCache.get(slot);
        
        try {
            return executeOnNode(node, command);
        } catch (MovedException e) {
            // 更新槽位映射
            slotCache.update(e.getSlot(), e.getNewNode());
            return retry(command);
        } catch (AskException e) {
            // 临时重定向到目标节点
            RedisNode target = getNode(e.getTarget());
            executeOnNode(target, "ASKING");
            return executeOnNode(target, command);
        }
    }
}
```

### 6.2 重定向机制
- **MOVED重定向**：槽位已永久迁移，更新客户端映射表
  ```
  MOVED <slot> <node-ip>:<node-port>
  ```
- **ASK重定向**：槽位正在迁移，临时重定向到目标节点
  ```
  ASK <slot> <node-ip>:<node-port>
  ```

### 6.3 多键操作限制
在迁移期间，多键操作需要确保所有键在同一个节点：
```python
# 有效操作（相同槽位）
MGET user:{1000}:name user:{1000}:email

# 无效操作（不同槽位）
MGET user:1000:name order:2000:status
```

---

## 7. 故障恢复与数据一致性

### 7.1 迁移失败处理
- **部分失败**：已迁移的数据在目标节点，未迁移的留在源节点
- **完整回滚**：使用CLUSTER FAILOVER回滚迁移
- **增量同步**：通过复制流继续迁移

### 7.2 一致性保证
Redis Cluster在迁移期间提供**最终一致性**：
- 异步迁移可能导致短暂的数据不一致
- 客户端通过重定向机制获取最新数据
- 写入操作在迁移期间被正确路由

### 7.3 数据验证
迁移完成后可验证数据完整性：
```bash
# 检查槽位状态
redis-cli CLUSTER SLOTS

# 验证槽位数据
redis-cli --cluster check <host>:<port>
```

---

## 8. 性能优化建议

### 8.1 迁移参数调优
```redis
# 调整迁移速度（默认10）
config set cluster-migration-barrier 5

# 批量大小调整
config set cluster-allow-multiple-migration yes
```

### 8.2 监控指标
- **迁移速率**：keys migrated per second
- **网络使用**：迁移期间的带宽消耗
- **延迟影响**：客户端请求的P99延迟

### 8.3 最佳实践
1. 在低峰期执行迁移操作
2. 提前预估迁移时间：`总数据量 / 迁移速率`
3. 监控网络带宽和节点负载
4. 使用流水线（pipeline）减少迁移RTT

---

## 9. 总结

Redis Cluster通过CRC16哈希槽机制实现了高效的数据分片和动态再平衡。哈希槽迁移是集群运维中的核心操作，需要深入理解其工作机制和客户端交互模式。通过合理的迁移策略和监控，可以确保集群在扩展和收缩过程中保持高可用性和数据一致性。

---

## 附录

### A. 相关命令参考
| 命令 | 描述 |
|------|------|
| `CLUSTER SLOTS` | 查看槽位分配 |
| `CLUSTER SETSLOT` | 设置槽位状态 |
| `CLUSTER GETKEYSINSLOT` | 获取槽位中的键 |
| `MIGRATE` | 迁移键值对 |

### B. 故障排查指南
1. **迁移卡住**：检查网络连通性和节点状态
2. **数据不一致**：验证槽位映射和客户端缓存
3. **性能下降**：调整迁移参数和监控资源使用

### C. 参考资料
1. Redis官方文档：https://redis.io/docs/management/scaling/
2. Redis Cluster规范：https://redis.io/topics/cluster-spec
3. CRC16算法：https://redis.io/docs/reference/cluster-spec/#appendix-a-crc16-reference-implementation-in-ansi-c

---

*文档版本：1.1*
*最后更新：2024年1月*
*适用版本：Redis 5.0+*