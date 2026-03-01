# Seata AT模式全局锁与undo_log技术文档

## 1. 概述

### 1.1 Seata AT模式简介
Seata AT（Auto Transaction）模式是一种无侵入的分布式事务解决方案，通过拦截并解析业务SQL，自动生成反向补偿操作，实现分布式事务的一阶段提交和二阶段回滚/提交。

### 1.2 核心组件关系
```
全局事务
    │
    ├── 分支事务1 ─── undo_log1 ─── 全局锁1
    ├── 分支事务2 ─── undo_log2 ─── 全局锁2
    └── 分支事务3 ─── undo_log3 ─── 全局锁3
```

## 2. 全局锁机制

### 2.1 全局锁的定义与作用
**全局锁**是Seata AT模式下保证分布式事务隔离性的核心机制，用于防止不同分布式事务同时修改同一数据。

#### 主要作用：
- 保证写写隔离：防止脏写
- 保证读已提交隔离级别
- 协调跨服务数据访问的一致性

### 2.2 全局锁存储结构

```sql
-- 全局锁表结构（seata库中的global_table）
CREATE TABLE IF NOT EXISTS `global_table` (
  `xid` VARCHAR(128) NOT NULL,
  `transaction_id` BIGINT,
  `status` TINYINT NOT NULL,
  `application_id` VARCHAR(32),
  `transaction_service_group` VARCHAR(32),
  `transaction_name` VARCHAR(128),
  `timeout` INT,
  `begin_time` BIGINT,
  `application_data` VARCHAR(2000),
  `gmt_create` DATETIME,
  `gmt_modified` DATETIME,
  PRIMARY KEY (`xid`),
  KEY `idx_gmt_modified_status` (`gmt_modified`, `status`),
  KEY `idx_transaction_id` (`transaction_id`)
);

-- 分支事务锁表结构（seata库中的lock_table）
CREATE TABLE IF NOT EXISTS `lock_table` (
  `row_key` VARCHAR(128) NOT NULL,
  `xid` VARCHAR(96) NOT NULL,
  `transaction_id` LONG ,
  `branch_id` LONG,
  `resource_id` VARCHAR(256) ,
  `table_name` VARCHAR(32) ,
  `pk` VARCHAR(36) ,
  `gmt_create` DATETIME ,
  `gmt_modified` DATETIME,
  PRIMARY KEY(`row_key`),
  KEY `idx_branch_id` (`branch_id`)
);
```

### 2.3 全局锁获取流程

```java
// 伪代码示例：全局锁获取逻辑
public boolean acquireGlobalLock() {
    // 1. 生成锁资源标识
    String lockKey = buildLockKey(tableName, pkValue);
    
    // 2. 查询是否已存在锁
    LockDO existingLock = lockDAO.queryLock(lockKey);
    
    if (existingLock != null) {
        // 3. 检查锁是否属于当前事务
        if (existingLock.getXid().equals(currentXid)) {
            return true; // 可重入锁
        }
        
        // 4. 锁冲突处理
        if (isLockTimeout(existingLock)) {
            // 超时清理并重试
            lockDAO.deleteLock(existingLock);
            return retryAcquireLock();
        }
        
        // 5. 等待或抛出锁冲突异常
        throw new LockConflictException();
    }
    
    // 6. 插入新锁记录
    LockDO newLock = buildLockDO(lockKey);
    return lockDAO.insertLock(newLock);
}
```

### 2.4 全局锁冲突解决策略

| 冲突类型 | 检测机制 | 解决策略 | 重试策略 |
|---------|---------|---------|---------|
| 同记录跨事务冲突 | 锁记录已存在且xid不同 | 回滚当前操作，抛出LockConflictException | 指数退避重试 |
| 死锁检测 | 事务等待图检测 | 选择回滚代价最小的事务 | 无 |
| 锁超时 | 锁持有时间 > 配置阈值 | 强制释放锁 | 立即重试 |

## 3. undo_log机制

### 3.1 undo_log的定义与作用
**undo_log**是AT模式实现事务回滚的关键组件，记录了数据修改前的镜像，用于事务回滚时的数据恢复。

#### 核心作用：
- 记录数据修改前的状态
- 提供事务回滚能力
- 支持事务提交后的异步清理

### 3.2 undo_log表结构

```sql
-- 业务库中的undo_log表（每个参与分布式事务的业务库都需要）
CREATE TABLE `undo_log` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `branch_id` bigint(20) NOT NULL,
  `xid` varchar(100) NOT NULL,
  `context` varchar(128) NOT NULL,
  `rollback_info` longblob NOT NULL,
  `log_status` int(11) NOT NULL,
  `log_created` datetime NOT NULL,
  `log_modified` datetime NOT NULL,
  `ext` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ux_undo_log` (`xid`,`branch_id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8;
```

### 3.3 undo_log数据结构

```json
{
  "undoLog": {
    "branchId": 123456789,
    "xid": "192.168.1.100:8091:123456789",
    "context": "serializer=jackson",
    "rollbackInfo": {
      "beforeImage": {
        "tableName": "product",
        "rows": [
          {
            "fields": [
              {"name": "id", "type": 4, "value": 1},
              {"name": "stock", "type": 4, "value": 100},
              {"name": "price", "type": 3, "value": 99.99}
            ]
          }
        ]
      },
      "afterImage": {
        "tableName": "product",
        "rows": [
          {
            "fields": [
              {"name": "id", "type": 4, "value": 1},
              {"name": "stock", "type": 4, "value": 95},
              {"name": "price", "type": 3, "value": 99.99}
            ]
          }
        ]
      },
      "sqlType": "UPDATE"
    }
  }
}
```

### 3.4 undo_log生命周期管理

#### 3.4.1 生成阶段（一阶段）
```java
public class UndoLogManager {
    
    public void addUndoLog(String xid, long branchId, 
                          Connection conn, SQLRecognizer sqlRecognizer) {
        
        // 1. 获取前镜像
        TableRecords beforeImage = queryBeforeImage(conn, sqlRecognizer);
        
        // 2. 执行业务SQL
        int result = executeBusinessSQL(conn, sqlRecognizer);
        
        // 3. 获取后镜像
        TableRecords afterImage = queryAfterImage(conn, sqlRecognizer, beforeImage);
        
        // 4. 构建undo_log记录
        UndoLogDO undoLog = buildUndoLog(xid, branchId, 
                                        beforeImage, afterImage);
        
        // 5. 插入undo_log表
        insertUndoLog(conn, undoLog);
    }
}
```

#### 3.4.2 回滚阶段（二阶段回滚）
```java
public void rollback(String xid, long branchId) {
    Connection conn = null;
    try {
        // 1. 获取数据库连接
        conn = dataSource.getConnection();
        
        // 2. 查询undo_log
        UndoLogDO undoLog = queryUndoLog(conn, xid, branchId);
        
        // 3. 验证数据一致性
        if (!validateUndoLog(undoLog)) {
            // 数据不一致，需要人工干预
            reportDataInconsistency();
            return;
        }
        
        // 4. 执行反向SQL
        executeCompensationSQL(conn, undoLog.getRollbackInfo());
        
        // 5. 删除undo_log记录
        deleteUndoLog(conn, xid, branchId);
        
        conn.commit();
    } catch (Exception e) {
        // 6. 回滚失败处理
        handleRollbackFailure(xid, branchId, e);
    }
}
```

#### 3.4.3 清理阶段
```java
// 异步清理任务
@Scheduled(fixedDelay = 3600000) // 每小时执行一次
public void cleanExpiredUndoLogs() {
    // 1. 查询需要清理的undo_log
    List<UndoLogDO> expiredLogs = queryExpiredUndoLogs();
    
    // 2. 分批清理
    for (UndoLogDO log : expiredLogs) {
        // 检查事务状态
        if (isTransactionFinished(log.getXid())) {
            deleteUndoLog(log);
        }
    }
}
```

## 4. 全局锁与undo_log的协同工作

### 4.1 事务执行流程

```
┌─────────────────────────────────────────────────────────────┐
│                       事务开始                               │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  阶段一：业务SQL执行                                         │
│  1. 解析SQL，获取前镜像(before image)                       │
│  2. 执行业务SQL                                             │
│  3. 获取后镜像(after image)                                 │
│  4. 生成undo_log并插入业务库                                │
│  5. 注册分支事务到TC                                        │
│  6. 获取全局锁（针对修改的记录）                            │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
              ┌─────────────────┐
              │  全局提交/回滚？ │
              └────────┬────────┘
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
┌───────────────┐             ┌───────────────┐
│  二阶段提交    │             │  二阶段回滚    │
│               │             │               │
│ 1. 异步删除   │             │ 1. 根据undo_log│
│    undo_log   │             │    生成反向SQL │
│ 2. 释放全局锁 │             │ 2. 执行反向SQL │
│               │             │ 3. 删除undo_log│
│               │             │ 4. 释放全局锁  │
└───────────────┘             └───────────────┘
```

### 4.2 关键协同点

#### 4.2.1 锁与日志的原子性保证
```java
public class BranchTransactionProcessor {
    
    public BranchRegisterResponse registerBranch(BranchRegisterRequest request) {
        try {
            // 1. 开启本地事务
            Connection conn = beginLocalTransaction();
            
            // 2. 插入undo_log（业务库）
            undoLogManager.addUndoLog(conn, request);
            
            // 3. 获取全局锁（TC端）
            boolean lockAcquired = lockManager.acquireLock(request);
            
            if (lockAcquired) {
                // 4. 提交本地事务
                conn.commit();
                return successResponse();
            } else {
                // 5. 回滚本地事务（包含undo_log）
                conn.rollback();
                return failResponse("Acquire global lock failed");
            }
        } catch (Exception e) {
            // 异常处理
            handleException(e);
        }
    }
}
```

#### 4.2.2 回滚时的锁校验
```java
public void rollbackBranch(String xid, long branchId) {
    // 1. 校验当前事务是否持有锁
    if (!lockManager.isLockOwner(xid, branchId)) {
        throw new IllegalStateException("Not lock owner, cannot rollback");
    }
    
    // 2. 执行回滚
    undoLogManager.rollback(xid, branchId);
    
    // 3. 释放锁
    lockManager.releaseLock(xid, branchId);
}
```

## 5. 配置与优化

### 5.1 关键配置参数

```properties
# 全局锁配置
seata.client.lock.retryInterval=10
seata.client.lock.retryTimes=30
seata.client.lock.lockRetryPolicy=exponential

# undo_log配置
seata.client.undo.logTable=undo_log
seata.client.undo.logSerialization=jackson
seata.client.undo.onlyCareUpdateColumns=true

# 日志保留策略
seata.client.undo.logSaveDays=7
seata.client.undo.logDeletePeriod=86400000
```

### 5.2 性能优化建议

#### 5.2.1 全局锁优化
- **锁粒度优化**：尽量使用行级锁而非表级锁
- **锁超时设置**：根据业务特点设置合理的锁超时时间
- **锁重试策略**：配置合适的重试间隔和次数

#### 5.2.2 undo_log优化
- **序列化优化**：使用高效的序列化方式（如fst）
- **批量操作**：支持批量插入undo_log
- **异步清理**：配置合理的清理周期和策略

### 5.3 高可用设计

```yaml
seata:
  lock:
    mode: db # 支持db、redis、zookeeper等模式
    db:
      datasource: lock-db
      table: lock_table
    redis:
      host: ${redis.host}
      port: ${redis.port}
      database: 0
      
  undo:
    log-table: undo_log
    serialization: fst
    compression: gzip # 支持gzip压缩减少存储空间
```

## 6. 故障处理与监控

### 6.1 常见问题处理

#### 6.1.1 全局锁冲突
```java
// 锁冲突处理策略
@Retryable(value = LockConflictException.class, 
           maxAttempts = 3,
           backoff = @Backoff(delay = 1000, multiplier = 2))
public void processWithTransaction(OrderDTO order) {
    // 业务处理
}
```

#### 6.1.2 undo_log清理失败
```sql
-- 手动清理过期undo_log
DELETE FROM undo_log 
WHERE log_created < DATE_SUB(NOW(), INTERVAL 7 DAY)
  AND log_status = 1; -- 1表示已完成
```

### 6.2 监控指标

| 监控项 | 指标名称 | 告警阈值 | 监控频率 |
|-------|---------|---------|---------|
| 全局锁数量 | seata.lock.count | > 10000 | 1分钟 |
| 锁等待时间 | seata.lock.wait.time | > 3000ms | 实时 |
| undo_log大小 | seata.undo.log.size | > 10GB | 1小时 |
| 回滚率 | seata.transaction.rollback.rate | > 5% | 5分钟 |

### 6.3 日志分析
```sql
-- 分析锁竞争情况
SELECT table_name, COUNT(*) as lock_count
FROM lock_table 
WHERE gmt_modified > DATE_SUB(NOW(), INTERVAL 1 HOUR)
GROUP BY table_name 
ORDER BY lock_count DESC;

-- 分析undo_log增长趋势
SELECT DATE(log_created) as log_date, 
       COUNT(*) as log_count,
       AVG(LENGTH(rollback_info)) as avg_size
FROM undo_log
GROUP BY DATE(log_created)
ORDER BY log_date DESC;
```

## 7. 最佳实践

### 7.1 设计原则
1. **最小化锁范围**：尽量缩小事务涉及的数据范围
2. **短事务原则**：避免长事务持有锁过久
3. **索引优化**：确保查询条件有合适索引，减少锁冲突

### 7.2 代码示例
```java
@Service
public class OrderServiceImpl implements OrderService {
    
    @GlobalTransactional
    public void createOrder(OrderDTO order) {
        // 1. 扣减库存（会生成undo_log和获取锁）
        productService.reduceStock(order.getProductId(), order.getQuantity());
        
        // 2. 创建订单
        orderDAO.insert(order);
        
        // 3. 扣减余额
        accountService.reduceBalance(order.getUserId(), order.getAmount());
    }
}
```

### 7.3 注意事项
1. **避免跨服务循环调用**：可能导致死锁
2. **合理设置超时时间**：避免资源长时间占用
3. **定期监控清理**：防止undo_log表无限增长

## 8. 总结

Seata AT模式通过全局锁和undo_log的协同工作，提供了高效的分布式事务解决方案：
- **全局锁**保证了分布式事务的隔离性
- **undo_log**提供了事务回滚的能力
- 两者结合确保了数据的一致性和系统的可用性

在实际应用中，需要根据业务特点合理配置相关参数，并建立完善的监控体系，才能充分发挥Seata AT模式的优势。