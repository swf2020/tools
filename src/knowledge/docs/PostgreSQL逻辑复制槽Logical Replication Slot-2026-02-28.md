# PostgreSQL逻辑复制槽技术文档

## 1. 概述

### 1.1 什么是逻辑复制槽
逻辑复制槽（Logical Replication Slot）是PostgreSQL中的一种高级功能，它允许数据库系统跟踪已经发送给客户端的WAL（Write-Ahead Logging）日志信息。与物理复制槽不同，**逻辑复制槽** 关注的是逻辑层面的数据变更，可以将特定数据库对象的修改以逻辑形式传输到其他数据库实例。

### 1.2 与物理复制槽的区别
| 特性 | 逻辑复制槽 | 物理复制槽 |
|------|-----------|-----------|
| 复制粒度 | 表级别 | 整个数据库集群 |
| 数据格式 | 逻辑解码后的变更 | 原始WAL记录 |
| 跨版本支持 | 支持不同版本间复制 | 要求主备版本严格一致 |
| 网络传输 | 可选择性传输部分表 | 必须传输所有数据 |
| 使用场景 | 逻辑复制、CDC | 物理流复制 |

## 2. 工作原理

### 2.1 核心组件
1. **WAL日志**：记录所有数据变更
2. **逻辑解码插件**（如pgoutput、wal2json）：将WAL记录转换为逻辑格式
3. **复制槽维护进程**：跟踪已发送和待发送的变更
4. **输出插件**：将逻辑变更序列化为可传输格式

### 2.2 数据流
```
写入操作 → WAL记录 → 逻辑解码 → 逻辑变更记录 → 复制槽缓存 → 订阅者消费
```

### 2.3 关键特性
- **持久化**：复制槽信息存储在磁盘，重启后保留
- **精确一次传递**：确保变更不被丢失或重复
- **进度跟踪**：记录已确认的LSN（Log Sequence Number）

## 3. 创建与管理

### 3.1 前置条件
```sql
-- 1. 修改postgresql.conf
wal_level = logical
max_replication_slots = 10  -- 根据需求调整

-- 2. 重启PostgreSQL服务

-- 3. 创建具有复制权限的用户
CREATE ROLE repl_user WITH LOGIN REPLICATION PASSWORD 'secure_password';
```

### 3.2 创建逻辑复制槽
```sql
-- 使用默认输出插件pgoutput
SELECT * FROM pg_create_logical_replication_slot(
    'my_logical_slot', 
    'pgoutput'
);

-- 使用wal2json插件（需预先安装）
SELECT * FROM pg_create_logical_replication_slot(
    'json_slot',
    'wal2json'
);

-- 带参数的创建方式
SELECT * FROM pg_create_logical_replication_slot(
    'custom_slot',
    'pgoutput',
    false,  -- 是否临时槽
    'include-xids=true, include-timestamp=true'  -- 输出插件参数
);
```

### 3.3 查看复制槽信息
```sql
-- 查看所有复制槽
SELECT * FROM pg_replication_slots;

-- 查看详细信息
SELECT 
    slot_name,
    plugin,
    slot_type,
    database,
    active,
    pg_size_pretty(pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        restart_lsn
    )) as replication_lag
FROM pg_replication_slots
WHERE slot_type = 'logical';
```

### 3.4 删除复制槽
```sql
-- 安全删除复制槽
SELECT pg_drop_replication_slot('my_logical_slot');

-- 强制删除（谨慎使用）
SELECT pg_drop_replication_slot('stuck_slot');
```

## 4. 使用示例

### 4.1 基础发布-订阅模式
```sql
-- 在发布者端创建发布
CREATE PUBLICATION my_publication 
FOR TABLE users, orders, products;

-- 将复制槽与发布关联
-- （当创建订阅时自动完成）

-- 在订阅者端创建订阅
CREATE SUBSCRIPTION my_subscription
CONNECTION 'host=192.168.1.100 port=5432 dbname=mydb user=repl_user'
PUBLICATION my_publication
WITH (
    copy_data = true,
    create_slot = true,  -- 自动创建复制槽
    slot_name = 'my_logical_slot'
);
```

### 4.2 使用pg_recvlogical工具
```bash
# 实时接收逻辑变更
pg_recvlogical \
    -d mydatabase \
    --slot=my_slot \
    --start \
    -f -

# 输出为JSON格式
pg_recvlogical \
    -d mydatabase \
    --slot=json_slot \
    --plugin=wal2json \
    --start \
    -f /tmp/changes.json
```

### 4.3 编程接口使用（Python示例）
```python
import psycopg2
from psycopg2.extras import LogicalReplicationConnection

conn = psycopg2.connect(
    database="mydb",
    connection_factory=LogicalReplicationConnection
)

cur = conn.cursor()
cur.start_replication(
    slot_name='my_slot',
    decode=True,
    options={
        'include-xids': True,
        'include-timestamp': True,
        'include-types': True
    }
)

def consume(msg):
    print(f"LSN: {msg.data_start}")
    print(f"Payload: {msg.payload}")
    msg.cursor.send_feedback(flush_lsn=msg.data_start)

cur.consume_stream(consume)
```

## 5. 监控与维护

### 5.1 关键监控指标
```sql
-- 复制延迟监控
SELECT
    slot_name,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            confirmed_flush_lsn
        )
    ) as replication_lag_bytes,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        confirmed_flush_lsn
    ) < 16 * 1024 * 1024 as within_16MB  -- 告警阈值
FROM pg_replication_slots
WHERE slot_type = 'logical';

-- WAL保留情况
SELECT
    slot_name,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            restart_lsn
        )
    ) as wal_retained
FROM pg_replication_slots;
```

### 5.2 日常维护任务
```sql
-- 1. 定期检查失效的复制槽
SELECT slot_name, active 
FROM pg_replication_slots 
WHERE NOT active AND slot_type = 'logical';

-- 2. 监控WAL磁盘使用
SELECT 
    slot_name,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)
    ) as pending_wal
FROM pg_replication_slots;

-- 3. 更新复制槽进度
-- （通常由订阅者自动完成）
```

### 5.3 性能调优参数
```ini
# postgresql.conf中的重要参数
max_replication_slots = 20          # 最大复制槽数量
max_wal_senders = 20               # 最大WAL发送进程
wal_sender_timeout = 60s           # 发送超时时间
wal_keep_size = 1GB                # 额外保留的WAL大小
logical_decoding_work_mem = 64MB   # 逻辑解码内存
```

## 6. 故障处理

### 6.1 常见问题及解决方案

#### 问题1：WAL磁盘空间不足
**症状**：磁盘空间快速增长，pg_wal目录过大
```sql
-- 诊断
SELECT slot_name, 
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn))
FROM pg_replication_slots;

-- 解决方案
-- a. 恢复挂起的订阅者连接
-- b. 如果订阅者不再需要，删除复制槽
SELECT pg_drop_replication_slot('stale_slot');
```

#### 问题2：复制槽卡住
**症状**：复制槽状态为inactive但WAL持续增长
```bash
# 强制断开连接
SELECT pg_terminate_backend(pid)
FROM pg_stat_replication
WHERE application_name = 'problematic_subscriber';

# 然后重新建立订阅
```

#### 问题3：逻辑解码失败
**症状**：错误日志中出现解码相关错误
```sql
-- 检查输出插件兼容性
SELECT name, version FROM pg_available_extension_versions 
WHERE name LIKE '%logical%';

-- 重新创建复制槽
SELECT pg_drop_replication_slot('faulty_slot');
SELECT * FROM pg_create_logical_replication_slot('new_slot', 'pgoutput');
```

## 7. 最佳实践

### 7.1 安全建议
1. **最小权限原则**：复制用户只需REPLICATION权限
2. **网络加密**：使用SSL连接保护数据传输
3. **定期审计**：监控复制槽使用情况
4. **访问控制**：限制可创建复制槽的用户

### 7.2 性能优化
1. **批量处理**：适当调整`logical_decoding_work_mem`
2. **选择性复制**：只发布需要的表
3. **连接池**：对大量订阅使用连接池
4. **监控告警**：设置复制延迟告警阈值

### 7.3 高可用考虑
1. **主备切换**：逻辑复制槽不会自动转移到备机
2. **监控脚本**：实现复制槽状态监控
3. **清理策略**：建立自动清理失效复制槽的机制
4. **备份恢复**：复制槽信息包含在基础备份中

## 8. 使用场景

### 8.1 实时数据同步
- 跨数据库版本的数据迁移
- 报表数据库实时更新
- 微服务架构中的数据共享

### 8.2 变更数据捕获（CDC）
- 数据仓库ETL流程
- 缓存更新（如Redis）
- 搜索引擎索引更新

### 8.3 数据审计与回滚
- 记录所有数据变更历史
- 实现时间点恢复
- 合规性数据追踪

## 9. 限制与注意事项

### 9.1 当前版本限制
1. DDL变更不会自动复制
2. 序列数据需要额外处理
3. 大对象（TOAST）的更新可能有限制
4. 某些数据类型可能不完全支持

### 9.2 重要提醒
- 未使用的复制槽会导致WAL无限增长
- 复制槽信息不会被`pg_dump`备份
- 逻辑复制不影响物理复制
- 订阅端表结构必须与发布端兼容

## 10. 附录

### 10.1 相关系统表
- `pg_replication_slots`：复制槽信息
- `pg_stat_replication`：复制连接状态
- `pg_publication`：发布信息
- `pg_subscription`：订阅信息

### 10.2 参考资料
1. PostgreSQL官方文档：逻辑复制章节
2. pgoutput插件源码
3. wal2json项目文档
4. PostgreSQL源码：src/backend/replication/logical/

---

*文档版本：1.0*
*最后更新日期：2024年*
*适用版本：PostgreSQL 10+*