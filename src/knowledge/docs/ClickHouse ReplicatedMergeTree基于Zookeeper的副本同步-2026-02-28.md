# ClickHouse ReplicatedMergeTree基于ZooKeeper的副本同步技术文档

## 1. 概述

### 1.1 文档目的
本文档详细描述ClickHouse ReplicatedMergeTree表引擎如何利用ZooKeeper实现分布式副本同步机制，涵盖架构设计、同步流程、配置管理和故障处理等方面。

### 1.2 核心概念
- **ReplicatedMergeTree**: ClickHouse的复制表引擎，支持多副本数据同步
- **ZooKeeper**: 分布式协调服务，作为副本同步的元数据存储和协调中心
- **副本**: 相同数据的多个物理拷贝，分布在不同的ClickHouse节点上
- **分片**: 数据水平分区的逻辑单元

## 2. 架构设计

### 2.1 整体架构
```
┌─────────────────────────────────────────────────────┐
│                 ClickHouse集群                        │
├─────────────┬─────────────┬─────────────┬─────────────┤
│  节点A      │  节点B      │  节点C      │  节点D      │
│ ┌─────────┐ │ ┌─────────┐ │ ┌─────────┐ │ ┌─────────┐ │
│ │ 副本1   │ │ │ 副本2   │ │ │ 副本3   │ │ │ 副本4   │ │
│ └─────────┘ │ └─────────┘ │ └─────────┘ │ └─────────┘ │
└──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┘
       │              │              │              │
       └──────────────┼──────────────┼──────────────┘
                      │
           ┌──────────┴──────────┐
           │     ZooKeeper集群    │
           │  ┌───┐  ┌───┐  ┌───┐ │
           │  │ZK1│  │ZK2│  │ZK3│ │
           │  └───┘  └───┘  └───┘ │
           └───────────────────────┘
```

### 2.2 ZooKeeper目录结构
```
/clickhouse
├── tables/
│   ├── {uuid}/                          # 表唯一标识
│   │   ├── replicas/                    # 副本目录
│   │   │   ├── {replica_name}/          # 副本名称（如：ch01）
│   │   │   │   ├── host                 # 主机信息
│   │   │   │   ├── log_pointer          # 操作日志指针
│   │   │   │   ├── metadata             # 表元数据
│   │   │   │   ├── parts/               # 数据块信息
│   │   │   │   │   ├── {partition_name}_{block_number}_{level}/
│   │   │   │   │   │   ├── checksums    # 校验和文件
│   │   │   │   │   │   ├── columns.txt  # 列信息
│   │   │   │   │   │   └── ...
│   │   │   │   ├── queue/               # 待执行操作队列
│   │   │   │   │   ├── log-0000000000  # 操作日志条目
│   │   │   │   │   └── ...
│   │   │   │   └── is_active            # 副本活跃状态
│   │   │   └── ...
│   │   ├── blocks/                      # 数据块全局信息
│   │   ├── leader_election              # 主副本选举
│   │   ├── mutations/                   # mutation操作
│   │   └── log/                         # 全局操作日志
└── ...
```

## 3. 副本同步机制

### 3.1 数据写入流程

#### 3.1.1 写入时序
```
1. 客户端写入数据到任意副本（如：副本1）
2. 副本1在本地形成part数据块
3. 副本1在ZooKeeper的blocks节点注册part信息
4. 副本1在ZooKeeper的log节点添加操作日志
5. 其他副本（副本2,3...）监听log节点变化
6. 副本2发现新日志，将part加入自己的queue
7. 副本2从副本1下载part数据
8. 副本2验证checksum并本地保存
9. 副本2在ZooKeeper标记part完成
10. 副本1收到所有副本确认后，清理blocks信息
```

#### 3.1.2 ZooKeeper节点说明
- **blocks/{block_id}**: 存储数据块源信息，包含源副本和checksum
- **log/log-{seq}**: 操作日志，包含操作类型和block_id
- **queue/**: 每个副本的待处理队列，存储需要执行的操作

### 3.2 数据同步类型

#### 3.2.1 全量同步
当新副本加入或旧副本恢复时触发：
```sql
-- 系统自动执行以下流程：
1. 从ZooKeeper获取元数据创建表结构
2. 从其他活跃副本下载所有数据块
3. 验证数据完整性
4. 注册到ZooKeeper开始增量同步
```

#### 3.2.2 增量同步
正常运行时的工作模式：
```python
# 伪代码：副本同步监听逻辑
def replica_sync_listener():
    while True:
        # 监听ZooKeeper log节点变化
        log_entries = watch_zk_log(last_log_pointer)
        
        for entry in log_entries:
            operation = parse_operation(entry)
            
            if operation.type == "GET_PART":
                # 添加到本地队列
                add_to_local_queue(operation.block_id)
                
            elif operation.type == "MERGE_PARTS":
                # 计划合并操作
                schedule_merge(operation.parts)
                
            # 更新log指针
            update_log_pointer(entry.seq)
```

## 4. 配置与部署

### 4.1 ZooKeeper配置

#### 4.1.1 ClickHouse配置文件
```xml
<!-- /etc/clickhouse-server/config.xml -->
<zookeeper>
    <node index="1">
        <host>zk1.example.com</host>
        <port>2181</port>
    </node>
    <node index="2">
        <host>zk2.example.com</host>
        <port>2181</port>
    </node>
    <node index="3">
        <host>zk3.example.com</host>
        <port>2181</port>
    </node>
    <session_timeout_ms>30000</session_timeout_ms>
    <operation_timeout_ms>10000</operation_timeout_ms>
    <root>/clickhouse</root>
    <identity>user:password</identity> <!-- 可选认证 -->
</zookeeper>
```

#### 4.1.2 ZooKeeper服务器配置
```properties
# zoo.cfg
tickTime=2000
initLimit=10
syncLimit=5
dataDir=/var/lib/zookeeper
clientPort=2181
server.1=zk1.example.com:2888:3888
server.2=zk2.example.com:2888:3888
server.3=zk3.example.com:2888:3888
maxClientCnxns=60
autopurge.snapRetainCount=3
autopurge.purgeInterval=1
```

### 4.2 ReplicatedMergeTree表创建

#### 4.2.1 基本语法
```sql
CREATE TABLE replicated_table
(
    event_date Date,
    event_time DateTime,
    user_id UInt64,
    event_type String
)
ENGINE = ReplicatedMergeTree(
    '/clickhouse/tables/{shard}/replicated_table', -- ZooKeeper路径
    '{replica}'                                     -- 副本标识
)
PARTITION BY toYYYYMM(event_date)
ORDER BY (event_date, event_time, user_id)
SETTINGS index_granularity = 8192;
```

#### 4.2.2 分片副本配置示例
```sql
-- 在ch01节点上执行
CREATE TABLE metrics
(
    timestamp DateTime,
    metric_name String,
    value Float64
)
ENGINE = ReplicatedMergeTree(
    '/clickhouse/tables/shard1/metrics',
    'ch01'
)
ORDER BY timestamp;

-- 在ch02节点上执行
CREATE TABLE metrics
(
    timestamp DateTime,
    metric_name String,
    value Float64
)
ENGINE = ReplicatedMergeTree(
    '/clickhouse/tables/shard1/metrics',
    'ch02'
)
ORDER BY timestamp;
```

### 4.3 集群配置
```xml
<!-- /etc/clickhouse-server/config.d/cluster.xml -->
<remote_servers>
    <cluster_3shards_2replicas>
        <shard>
            <internal_replication>true</internal_replication>
            <replica>
                <host>ch01</host>
                <port>9000</port>
            </replica>
            <replica>
                <host>ch02</host>
                <port>9000</port>
            </replica>
        </shard>
        <shard>
            <internal_replication>true</internal_replication>
            <replica>
                <host>ch03</host>
                <port>9000</port>
            </replica>
            <replica>
                <host>ch04</host>
                <port>9000</port>
            </replica>
        </shard>
    </cluster_3shards_2replicas>
</remote_servers>
```

## 5. 故障处理与恢复

### 5.1 常见问题排查

#### 5.1.1 副本不同步
```sql
-- 检查副本状态
SELECT database, table, is_leader, is_readonly, 
       absolute_delay, queue_size, inserts_in_queue,
       merges_in_queue, part_mutations_in_queue
FROM system.replicas
WHERE is_readonly OR queue_size > 0 OR absolute_delay > 60;

-- 检查ZooKeeper连接
SELECT * FROM system.zookeeper 
WHERE path = '/clickhouse/tables' 
FORMAT Vertical;
```

#### 5.1.2 ZooKeeper连接问题
```bash
# 检查ZooKeeper状态
echo ruok | nc zk1.example.com 2181
echo mntr | nc zk1.example.com 2181

# 查看ClickHouse日志
tail -f /var/log/clickhouse-server/clickhouse-server.log | grep -i zookeeper
```

### 5.2 手动恢复操作

#### 5.2.1 副本重新同步
```sql
-- 停止副本同步
SYSTEM STOP FETCHES replicated_table;
SYSTEM STOP MERGES replicated_table;
SYSTEM STOP REPLICATED SENDS replicated_table;
SYSTEM STOP REPLICATION QUEUES replicated_table;

-- 重置副本状态（谨慎操作）
SYSTEM RESTART REPLICA replicated_table;

-- 或完全重新同步
SYSTEM DROP REPLICA 'ch02' FROM ZKPATH '/clickhouse/tables/shard1/metrics';
-- 然后在ch02节点重新创建表
```

#### 5.2.2 ZooKeeper元数据修复
```bash
# 使用clickhouse-zookeeper-cli工具
clickhouse zookeeper-cli --host zk1.example.com

# 清理孤儿节点
rmr /clickhouse/tables/shard1/metrics/replicas/ch02/queue

# 检查并修复元数据
ls /clickhouse/tables/shard1/metrics
get /clickhouse/tables/shard1/metrics/replicas/ch01/metadata
```

### 5.3 监控指标

#### 5.3.1 ClickHouse系统表
```sql
-- 副本同步延迟
SELECT 
    database,
    table,
    replica_name,
    last_queue_update,
    log_pointer - last_queue_update AS delay_entries,
    absolute_delay AS delay_seconds
FROM system.replicas
ORDER BY delay_seconds DESC
LIMIT 10;

-- ZooKeeper监控
SELECT name, value, description
FROM system.asynchronous_metrics
WHERE name LIKE '%ZooKeeper%' OR name LIKE '%Replica%';
```

#### 5.3.2 Prometheus监控配置
```yaml
# clickhouse_exporter配置
scrape_configs:
  - job_name: 'clickhouse'
    static_configs:
      - targets: ['ch01:9363', 'ch02:9363']
    
# 关键告警规则
groups:
  - name: clickhouse_alerts
    rules:
      - alert: ClickHouseReplicaDelayHigh
        expr: clickhouse_replica_delay > 300
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "ClickHouse replica delay high on {{ $labels.instance }}"
          
      - alert: ZooKeeperConnectionError
        expr: up{job="clickhouse"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "ClickHouse instance down: {{ $labels.instance }}"
```

## 6. 性能优化建议

### 6.1 ZooKeeper优化
```xml
<!-- ClickHouse配置优化 -->
<distributed_ddl>
    <path>/clickhouse/task_queue/ddl</path>
    <pool_size>10</pool_size>
    <task_max_lifetime>86400</task_max_lifetime>
</distributed_ddl>

<replication>
    <max_parallel_fetches>16</max_parallel_fetches>
    <max_parallel_sends>16</max_parallel_sends>
    <parallel_fetch_parts>1</parallel_fetch_parts>
</replication>
```

### 6.2 网络与磁盘优化
```bash
# 调整网络参数
sysctl -w net.core.rmem_max=134217728
sysctl -w net.core.wmem_max=134217728
sysctl -w net.ipv4.tcp_rmem="4096 87380 134217728"
sysctl -w net.ipv4.tcp_wmem="4096 65536 134217728"

# 使用高性能存储
# 推荐：NVMe SSD for data, RAM disk for /tmp
```

### 6.3 表设计优化
```sql
-- 合理设置分区和索引
CREATE TABLE optimized_table
(
    dt Date,
    user_id UInt64,
    event_type LowCardinality(String),
    payload String
)
ENGINE = ReplicatedMergeTree(
    '/clickhouse/tables/shard1/optimized',
    '{replica}'
)
PARTITION BY toYYYYMM(dt)  -- 按月分区
ORDER BY (dt, user_id, event_type)  -- 复合索引
SETTINGS 
    index_granularity = 8192,
    min_rows_for_wide_part = 1000000,  -- 小分区使用compact格式
    min_bytes_for_wide_part = 1073741824;  -- 1GB以上使用wide格式
```

## 7. 最佳实践

### 7.1 部署建议
1. **ZooKeeper集群**: 至少3节点，部署在独立服务器
2. **网络拓扑**: 副本间网络延迟<10ms，带宽≥10Gbps
3. **监控覆盖**: 监控ZooKeeper、网络、磁盘和副本状态
4. **备份策略**: 定期备份ZooKeeper数据和ClickHouse元数据

### 7.2 运维建议
1. **版本管理**: ClickHouse和ZooKeeper版本匹配
2. **容量规划**: 预留30% ZooKeeper存储空间
3. **变更流程**: 表结构变更使用ON CLUSTER语法
4. **灾难恢复**: 定期测试副本恢复流程

### 7.3 注意事项
1. ZooKeeper会话超时不宜设置过短
2. 避免在ZooKeeper存储大量小文件
3. 监控副本队列积压情况
4. 定期清理已完成mutation的ZooKeeper节点

## 附录

### A. 常用命令参考
```sql
-- 管理副本
SYSTEM SYNC REPLICA table_name;           -- 强制同步
SYSTEM RESTART REPLICA table_name;        -- 重启副本
SYSTEM FLUSH DISTRIBUTED table_name;      -- 刷新分布式表

-- 查看状态
SHOW CREATE TABLE table_name;             -- 查看表结构
SELECT * FROM system.parts;               -- 查看数据块
SELECT * FROM system.replication_queue;   -- 查看复制队列

-- 维护操作
OPTIMIZE TABLE table_name FINAL;          -- 合并数据块
ALTER TABLE table_name DETACH PARTITION;  -- 卸载分区
ALTER TABLE table_name ATTACH PARTITION;  -- 加载分区
```

### B. 故障诊断流程图
```
开始诊断
    ↓
检查ZooKeeper连接状态
    ├─ 连接失败 → 检查网络和ZK服务
    └─ 连接正常 → 检查副本状态
            ↓
    检查system.replicas表
            ↓
    判断具体问题类型
    ├─ 队列积压 → 检查网络带宽和磁盘IO
    ├─ 同步延迟 → 检查日志指针和log节点
    ├─ 副本失效 → 重启副本或重新同步
    └─ 数据不一致 → 校验checksum并修复
            ↓
    执行相应恢复操作
            ↓
    验证恢复结果
```

### C. 版本兼容性
| ClickHouse版本 | ZooKeeper版本 | 关键特性 |
|---------------|--------------|---------|
| 22.3+         | 3.4.13+      | 增强的副本恢复逻辑 |
| 21.8+         | 3.4.13+      | 并行副本获取优化 |
| 20.3+         | 3.4.10+      | 基础复制功能 |

---

**文档版本**: 1.2  
**更新日期**: 2024-01-15  
**适用版本**: ClickHouse 22.3+，ZooKeeper 3.4.13+  
**维护团队**: ClickHouse运维组  
**联系方式**: infra-team@example.com