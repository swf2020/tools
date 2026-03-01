# TiDB Region热点分裂与负载均衡技术文档

## 1. 概述

### 1.1 文档目的
本文档详细阐述TiDB中Region热点问题的产生机理、检测方法，以及通过Region分裂与负载均衡机制解决热点问题的技术方案和实施策略。

### 1.2 适用范围
- TiDB v4.0及以上版本
- 生产环境热点问题诊断与优化
- 集群容量规划与性能调优

## 2. Region基础概念

### 2.1 Region定义
Region是TiDB中数据分布和调度的基本单位：
- 每个Region默认大小约96MB~144MB
- 以Key Range形式划分数据空间
- 通过Raft协议实现多副本一致性

### 2.2 Region组成
```
Region结构：
├── Leader副本（处理读写请求）
├── Follower副本（同步数据）
└── Learner副本（只读副本，可选）
```

### 2.3 Region生命周期
```
创建 → 写入数据 → 大小增长 → 达到阈值 → 分裂 → 调度均衡
```

## 3. Region热点问题分析

### 3.1 热点产生原因

#### 3.1.1 业务层面
- **单调递增主键**：INSERT顺序写入同一Region
  ```sql
  -- 示例：自增主键导致热点
  CREATE TABLE orders (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,  -- 热点风险
    user_id INT,
    amount DECIMAL(10,2)
  );
  ```

- **时间序列数据**：按时间范围查询和写入
- **小表频繁访问**：配置表、字典表被频繁读取
- **不均衡的分区键**：分区键分布不均匀

#### 3.1.2 数据分布层面
- Region分布不均匀
- 副本分布不合理
- 存储节点配置差异

#### 3.1.3 查询模式
- 高频点查（Point Query）
- 范围扫描集中在特定区间
- 频繁更新同一数据行

### 3.2 热点识别方法

#### 3.2.1 监控指标
```sql
-- 1. 查询热点Region信息
SELECT * FROM information_schema.TIDB_HOT_REGIONS 
WHERE TABLE_NAME = 'your_table'
ORDER BY READ_BYTES DESC, WRITE_BYTES DESC
LIMIT 10;

-- 2. 查看Region读写流量
SELECT 
    store_id,
    region_id,
    read_bytes/1024/1024 as read_mb,
    write_bytes/1024/1024 as write_mb,
    read_keys,
    write_keys
FROM information_schema.TIKV_REGION_STATUS
WHERE table_name = 'your_table'
ORDER BY read_bytes + write_bytes DESC
LIMIT 20;
```

#### 3.2.2 Grafana监控面板
- **TiDB-Dashboard → Hot Region**：可视化热点Region
- **TiKV → Region Heartbeat**：Region心跳信息
- **PD → Statistics**：调度统计信息

#### 3.2.3 日志分析
```bash
# 查看PD调度日志
grep "split\|balance\|hot" /path/to/pd.log | tail -100

# 查看TiKV Region相关日志
grep "region.*split\|region.*heartbeat" /path/to/tikv.log
```

## 4. Region分裂机制

### 4.1 自动分裂策略

#### 4.1.1 大小触发分裂
```toml
# PD配置（pd.toml）
[schedule]
# Region分裂大小阈值（默认96MB）
max-merge-region-size = 20
max-merge-region-keys = 200000
split-merge-interval = "1h"

# Region大小阈值（默认144MB）
region-split-size = 144MB
# Region键值对数量阈值
region-split-keys = 960000
```

#### 4.1.2 QPS触发分裂
```toml
# 热点Region自动分裂配置
hot-region-schedule-limit = 4
hot-region-cache-hits-threshold = 3
```

#### 4.1.3 分裂算法
```go
// Region分裂点选择算法（简化示例）
func findSplitPoint(region *RegionInfo) ([]byte, error) {
    // 1. 基于大小分裂
    if region.Size > regionSplitSize {
        return splitBySize(region)
    }
    
    // 2. 基于QPS分裂
    if region.QPS > hotRegionThreshold {
        return splitByLoad(region)
    }
    
    // 3. 基于Key分布分裂
    return splitByKeyDistribution(region)
}
```

### 4.2 手动分裂操作

#### 4.2.1 通过PD API分裂
```bash
# 1. 查看Region信息
curl http://{pd-ip}:{pd-port}/pd/api/v1/region/id/{region_id}

# 2. 手动分裂Region
curl -X POST http://{pd-ip}:{pd-port}/pd/api/v1/regions/{region_id}/split \
  -d '{"split_keys": ["key1", "key2"]}'

# 3. 按比例分裂
curl -X POST http://{pd-ip}:{pd-port}/pd/api/v1/regions/{region_id}/split \
  -d '{"policy": "approximate", "keys": 10000}'
```

#### 4.2.2 通过SQL分裂
```sql
-- TiDB v5.0+ 支持SPLIT REGION语法
-- 1. 分裂表的所有Region
SPLIT TABLE table_name BETWEEN ("2023-01-01") AND ("2023-12-31") REGIONS 16;

-- 2. 分裂索引Region
SPLIT INDEX index_name ON table_name BETWEEN ("a") AND ("z") REGIONS 10;

-- 3. 分裂特定Region
SPLIT REGION {region_id} AT ("split_key");
```

#### 4.2.3 分裂预分区
```sql
-- 创建表时预分区，避免初始热点
CREATE TABLE orders (
    id BIGINT AUTO_INCREMENT,
    order_date DATE,
    amount DECIMAL(10,2),
    PRIMARY KEY (id)
) 
PARTITION BY RANGE (id) (
    PARTITION p0 VALUES LESS THAN (1000000),
    PARTITION p1 VALUES LESS THAN (2000000),
    PARTITION p2 VALUES LESS THAN (3000000),
    PARTITION p3 VALUES LESS THAN (4000000),
    PARTITION p4 VALUES LESS THAN MAXVALUE
);

-- 或者使用SHARD_ROW_ID_BITS
CREATE TABLE orders (
    id BIGINT AUTO_INCREMENT,
    user_id INT,
    amount DECIMAL(10,2),
    PRIMARY KEY (id)
) SHARD_ROW_ID_BITS = 4;  -- 分散到16个Region
```

## 5. 负载均衡策略

### 5.1 PD调度器架构

```
PD调度器架构：
├── 调度器控制器
│   ├── Balance Region Scheduler
│   ├── Hot Region Scheduler
│   ├── Leader Scheduler
│   └── Region Scheduler
├── 过滤器链
└── 计分器
```

### 5.2 调度策略配置

```toml
# PD调度配置（pd.toml）
[schedule]
# 最大调度并发数
max-snapshot-count = 3
max-pending-peer-count = 16
max-merge-region-size = 20
max-merge-region-keys = 200000

# Leader调度
leader-schedule-limit = 4
leader-schedule-policy = "count"  # 或 "size"

# Region调度
region-schedule-limit = 2048
tolerant-size-ratio = 0  # 容差比例

# 存储权重（用于均衡）
[schedule.store-limit]
# 每个Store的调度限制
store-id = 100
add-peer = 10
remove-peer = 10
```

### 5.3 热点Region调度

#### 5.3.1 Hot Region Scheduler
```toml
# 热点调度配置
[schedule.hot-region]
# 热点阈值（每秒字节数）
hot-region-write-bytes-threshold = 100MB
hot-region-read-bytes-threshold = 100MB
hot-region-write-keys-threshold = 100000
hot-region-read-keys-threshold = 100000

# 调度限制
hot-region-schedule-limit = 4
hot-region-cache-hits-threshold = 3
```

#### 5.3.2 调度过程
1. **检测阶段**：PD收集TiKV上报的Region流量统计
2. **识别阶段**：标记超过阈值的Region为热点Region
3. **调度阶段**：创建迁移Peer任务，分散热点
4. **执行阶段**：TiKV执行Region迁移

### 5.4 均衡调度算法

#### 5.4.1 Score-based负载均衡
```go
// 存储节点得分计算（简化）
func calculateStoreScore(store *StoreInfo) float64 {
    // 基于容量得分
    capacityScore := float64(store.Available) / float64(store.Capacity)
    
    // 基于Region数量得分
    regionScore := 1.0 - float64(store.RegionCount)/float64(avgRegionCount)
    
    // 基于流量得分
    loadScore := 1.0 - normalize(store.Load)
    
    // 综合得分
    totalScore := capacityWeight*capacityScore + 
                  regionWeight*regionScore + 
                  loadWeight*loadScore
    
    return totalScore
}
```

#### 5.4.2 调度优先级
```
调度优先级（从高到低）：
1. 副本数不均衡（有Region副本缺失）
2. 热点Region调度
3. Region数量不均衡
4. Leader分布不均衡
5. 存储空间不均衡
```

## 6. 实战优化案例

### 6.1 案例一：自增主键热点优化

#### 问题现象
- orders表写入集中在最新Region
- TiKV节点写入压力不均衡
- 写入QPS达到瓶颈

#### 解决方案
```sql
-- 1. 修改表结构，使用SHARD_ROW_ID_BITS
ALTER TABLE orders SHARD_ROW_ID_BITS = 4;

-- 2. 或者使用AUTO_RANDOM
CREATE TABLE orders_new (
    id BIGINT AUTO_RANDOM(5) PRIMARY KEY,  -- 分散到32个Region
    user_id INT,
    amount DECIMAL(10,2),
    INDEX idx_user(user_id)
);

-- 3. 数据迁移
INSERT INTO orders_new SELECT * FROM orders;
```

### 6.2 案例二：时间序列数据热点

#### 问题现象
- 按时间范围查询最近数据
- 最新分区Region成为热点
- 历史数据Region冷访问

#### 解决方案
```sql
-- 1. 使用时间分区
CREATE TABLE logs (
    id BIGINT AUTO_RANDOM,
    log_time DATETIME,
    content TEXT,
    PRIMARY KEY (id, log_time)
)
PARTITION BY RANGE (UNIX_TIMESTAMP(log_time)) (
    PARTITION p202301 VALUES LESS THAN (UNIX_TIMESTAMP('2023-02-01')),
    PARTITION p202302 VALUES LESS THAN (UNIX_TIMESTAMP('2023-03-01')),
    PARTITION p202303 VALUES LESS THAN (UNIX_TIMESTAMP('2023-04-01')),
    PARTITION pCurrent VALUES LESS THAN (MAXVALUE)
);

-- 2. 定期分裂新分区
SPLIT TABLE logs PARTITION pCurrent 
BETWEEN (UNIX_TIMESTAMP('2023-04-01')) 
AND (UNIX_TIMESTAMP('2023-05-01')) 
REGIONS 8;
```

### 6.3 案例三：小表频繁读取热点

#### 问题现象
- 配置表被全集群频繁读取
- Region Leader集中在少数节点
- 读延迟增加

#### 解决方案
```sql
-- 1. 增加Region副本数
ALTER TABLE config SET TIKV_REGION_REPLICA = 5;

-- 2. 手动调度Leader分布
-- 通过PD API将Leader分散到不同节点

-- 3. 启用Follower Read
SET tidb_replica_read = 'follower';

-- 4. 使用缓存层（应用层优化）
```

## 7. 监控与告警

### 7.1 关键监控指标

#### 7.1.1 Region分布监控
```sql
-- 查看Region分布均衡度
SELECT 
    store_id,
    COUNT(*) as region_count,
    SUM(approximate_size)/1024/1024 as total_size_mb,
    AVG(approximate_size)/1024/1024 as avg_size_mb
FROM information_schema.TIKV_REGION_STATUS
GROUP BY store_id
ORDER BY region_count DESC;
```

#### 7.1.2 热点监控
```bash
# 使用tiup工具监控热点
tiup ctl:v{version} pd -u http://{pd-ip}:{pd-port} hot read
tiup ctl:v{version} pd -u http://{pd-ip}:{pd-port} hot write
```

### 7.2 告警规则配置

```yaml
# Prometheus告警规则示例
groups:
  - name: tidb_hot_region
    rules:
      - alert: HotWriteRegion
        expr: sum(rate(pd_hotspot_status{type="region_write"}[5m])) by (instance) > 100
        for: 5m
        labels:
          severity: warning
        annotations:
          description: "实例 {{ $labels.instance }} 有热点写入Region"
          
      - alert: RegionBalanceIssue
        expr: stddev(pd_regions_status{type="region_count"}) > 50
        for: 10m
        labels:
          severity: critical
        annotations:
          description: "Region分布不均衡，标准差超过50"
```

### 7.3 性能基准测试

```sql
-- Region分裂性能测试
-- 1. 创建测试表
CREATE TABLE test_hotspot (
    id BIGINT AUTO_RANDOM PRIMARY KEY,
    data VARCHAR(1000),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) SHARD_ROW_ID_BITS = 4;

-- 2. 批量写入数据
INSERT INTO test_hotspot (data) 
SELECT REPEAT('x', 1000) 
FROM generate_series(1, 1000000);

-- 3. 监控分裂过程
-- 观察grafana的PD → Operator面板
```

## 8. 最佳实践

### 8.1 设计阶段优化
1. **表设计原则**
   - 避免单调递增主键
   - 合理使用AUTO_RANDOM和SHARD_ROW_ID_BITS
   - 根据查询模式设计分区键

2. **索引设计**
   - 热点索引考虑哈希前缀
   - 避免过度索引
   - 定期重建碎片化索引

### 8.2 运行阶段调优
1. **定期健康检查**
   ```sql
   -- 每周执行Region健康检查
   ANALYZE TABLE mysql.stats_meta;
   CHECK TABLE important_table;
   ```

2. **调度参数调优**
   ```toml
   # 根据业务特点调整调度参数
   [schedule]
   # 写入密集型业务
   max-snapshot-count = 5
   hot-region-schedule-limit = 8
   
   # 读取密集型业务
   leader-schedule-limit = 8
   replica-schedule-limit = 4
   ```

3. **容量规划**
   - 单Region大小控制在100MB左右
   - 单TiKV节点Region数量建议<10万
   - 预留20%存储空间用于分裂和均衡

### 8.3 故障处理流程
```
Region热点故障处理流程：
1. 识别确认：通过监控确认热点Region
2. 根本原因分析：业务模式 vs 数据分布
3. 应急处理：
   - 手动分裂热点Region
   - 临时增加副本数
   - 调整调度参数
4. 长期优化：
   - 修改表结构设计
   - 优化查询模式
   - 调整数据分布策略
5. 验证监控：确认热点消除，性能恢复
```

## 9. 常见问题与解决方案

### 9.1 Region分裂失败
**问题**：Region分裂操作失败或超时

**解决方案**：
1. 检查PD和TiKV日志
2. 确认Region状态正常
3. 调整分裂参数
   ```toml
   [coprocessor]
   region-split-size = "96MiB"
   region-split-keys = 960000
   ```

### 9.2 调度不生效
**问题**：调度任务创建但未执行

**排查步骤**：
1. 检查调度限制
   ```bash
   curl http://{pd-ip}:{pd-port}/pd/api/v1/config/schedule
   ```
2. 查看操作符状态
   ```bash
   curl http://{pd-ip}:{pd-port}/pd/api/v1/operators
   ```
3. 检查TiKV状态和版本兼容性

### 9.3 分裂抖动问题
**问题**：频繁分裂导致性能抖动

**优化方案**：
```toml
# 调整分裂敏感度
[schedule]
split-merge-interval = "2h"  # 增加分裂合并间隔
patrol-region-interval = "100ms"  # 调整巡检间隔

[region-split]
split-ratio = 0.75  # 分裂比例阈值
```

## 10. 工具与命令汇总

### 10.1 PD控制工具
```bash
# 查看调度配置
tiup ctl:v{version} pd -u http://{pd-ip}:{pd-port} config show schedule

# 手动调度Region
tiup ctl:v{version} pd -u http://{pd-ip}:{pd-port} operator add transfer-peer {region-id} {from-store} {to-store}

# 查看热点Region
tiup ctl:v{version} pd -u http://{pd-ip}:{pd-port} hotspot
```

### 10.2 TiDB SQL命令
```sql
-- Region信息查询
SHOW TABLE table_name REGIONS;
SHOW TABLE table_name INDEX index_name REGIONS;

-- 分裂相关
SPLIT REGION {region_id} AT ("split_key");
SPLIT TABLE table_name BETWEEN (...) AND (...) REGIONS n;

-- 调度控制
ADMIN SHOW DDL JOBS;
ADMIN CHECK TABLE table_name;
```

### 10.3 监控API
```bash
# PD状态API
curl http://{pd-ip}:{pd-port}/pd/api/v1/stores
curl http://{pd-ip}:{pd-port}/pd/api/v1/regions
curl http://{pd-ip}:{pd-port}/pd/api/v1/hotspot/regions
```

## 11. 版本特性差异

| 版本 | Region分裂特性 | 负载均衡改进 |
|------|---------------|-------------|
| v4.0 | 基础自动分裂 | 基础热点调度 |
| v5.0 | SPLIT REGION语法 | 智能热点识别 |
| v6.0 | 更精确的分裂点 | 基于QPS的均衡 |
| v7.0 | 自适应分裂阈值 | 预测性调度 |

## 12. 总结

TiDB通过Region分裂与负载均衡机制，有效解决了分布式数据库中的数据热点问题。关键在于：

1. **预防优于治疗**：在表设计阶段考虑数据分布
2. **监控先行**：建立完善的热点监控体系
3. **分层治理**：业务层、数据层、存储层协同优化
4. **动态调整**：根据业务变化及时调整策略

通过本文档介绍的技术方案和最佳实践，可以构建高性能、高可用的TiDB集群，有效应对各种热点场景。

---

**附录A：相关参数参考表**

| 参数 | 默认值 | 建议范围 | 说明 |
|------|--------|----------|------|
| region-split-size | 144MB | 96MB-256MB | Region分裂大小阈值 |
| region-split-keys | 960k | 500k-2M | Region键值对数量阈值 |
| hot-region-schedule-limit | 4 | 4-12 | 热点Region调度并发数 |
| max-snapshot-count | 3 | 3-10 | 最大快照并发数 |
| leader-schedule-limit | 4 | 4-16 | Leader调度并发数 |
| tolerant-size-ratio | 0 | 0-5 | 调度容差比例 |

**附录B：诊断检查清单**

- [ ] Region分布是否均衡（各Store差异<20%）
- [ ] 是否存在持续热点Region
- [ ] 调度操作是否正常执行
- [ ] 分裂合并频率是否合理
- [ ] 监控告警是否配置完善
- [ ] 业务表设计是否优化