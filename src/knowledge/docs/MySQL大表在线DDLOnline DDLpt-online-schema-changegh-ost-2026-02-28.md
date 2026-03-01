# MySQL大表在线DDL技术文档

## 1. 概述

随着业务发展，MySQL中的表可能增长到亿级甚至更大规模。对这些"大表"进行结构变更（DDL操作）时，传统直接执行`ALTER TABLE`的方式会带来严重的生产环境问题，包括：长时间锁表导致业务不可用、主从延迟剧增、数据库负载过高等。为此，业界发展出多种在线DDL方案，在保证业务连续性的同时完成表结构变更。

## 2. 方案对比总览

| 特性 | MySQL原生Online DDL | pt-online-schema-change | gh-ost |
|------|-------------------|-------------------------|---------|
| 实现原理 | 原地修改，记录增量变更 | 触发器同步数据，原子切换 | 无触发器，binlog流式同步 |
| 锁机制 | 部分操作仅需元数据锁 | 原表上短暂锁（交换时） | 原表无写锁，原子切换 |
| 资源占用 | 中等（需临时空间） | 较高（触发器+影子表） | 可调（控制复制负载） |
| 回滚能力 | 困难（需提前备份） | 灵活（可中断保留原表） | 优秀（可随时中断） |
| 主从影响 | 可能造成延迟 | 可能增加延迟 | 可控制延迟影响 |
| 适用版本 | MySQL 5.6+ | 所有版本 | 所有版本 |

## 3. MySQL原生Online DDL

### 3.1 原理机制
MySQL 5.6+引入了Online DDL特性，通过以下机制减少锁表时间：
- **In-Place算法**：直接修改原表数据文件，而非创建临时表
- **行格式复制**：在修改期间，DML操作被记录到临时日志
- **元数据锁**：仅需短暂获取元数据锁，而非表级锁

### 3.2 支持的操作类型
```sql
-- 完全在线操作（仅需元数据锁）
ALTER TABLE t1 ADD COLUMN col1 INT, ALGORITHM=INPLACE, LOCK=NONE;

-- 部分在线操作（共享锁）
ALTER TABLE t1 ADD FULLTEXT INDEX idx_name (name), ALGORITHM=INPLACE, LOCK=SHARED;

-- 离线操作（重建表）
ALTER TABLE t1 DROP PRIMARY KEY, ALGORITHM=COPY;
```

### 3.3 使用限制
- 仍可能产生大量I/O和CPU负载
- 某些操作（如修改列类型）不支持INPLACE
- 临时日志空间可能耗尽（需监控`innodb_online_alter_log_max_size`）
- 主从延迟风险依然存在

## 4. pt-online-schema-change

### 4.1 工作原理
Percona Toolkit中的`pt-online-schema-change`采用经典的"影子表"模式：

1. **创建影子表**：按新结构创建`_table_new`
2. **建立触发器**：在原表上创建三个触发器（INSERT/UPDATE/DELETE）
3. **分批复制数据**：将原表数据分块复制到影子表
4. **原子切换**：通过RENAME TABLE交换表名
5. **清理**：删除旧表和触发器

### 4.2 基础用法
```bash
pt-online-schema-change \
  --alter="ADD COLUMN email VARCHAR(255), ADD INDEX idx_email(email)" \
  D=database,t=users \
  --execute \
  --critical-load="Threads_running=50" \
  --max-load="Threads_running=25" \
  --chunk-size=1000 \
  --max-lag=10
```

### 4.3 关键配置参数
```bash
# 负载控制
--max-load=Threads_running:25  # 设置负载阈值
--critical-load=Threads_running:50  # 临界负载阈值

# 复制延迟控制
--max-lag=10  # 最大允许的复制延迟（秒）
--check-interval=1  # 检查延迟的频率

# 执行控制
--chunk-size=1000  # 每个数据块的大小
--chunk-time=0.5  # 每块的目标执行时间
--set-vars="lock_wait_timeout=2"  # 设置会话变量
```

### 4.4 优点与缺点
**优点：**
- 兼容性好，支持所有MySQL版本
- 提供丰富的监控和流控机制
- 可随时中断，回滚简单
- 社区成熟，文档丰富

**缺点：**
- 触发器增加数据库负载
- 可能影响写入性能
- 需要额外存储空间（影子表）
- 外键处理复杂

## 5. gh-ost

### 5.1 设计理念
GitHub开源的gh-ost采用无触发器的架构，通过解析binlog实现数据同步：

1. **创建影子表**：在目标数据库或测试实例上创建新表
2. **binlog流式同步**：伪装为从库，持续读取和应用binlog
3. **分批迁移历史数据**：使用低优先级拷贝现有数据
4. **原子切换**：通过两步RENAME完成表切换
5. **清理**：根据配置保留或清理旧表

### 5.2 架构特色
- **无触发器设计**：避免触发器对性能的影响
- **可控制的负载**：通过参数调节对主库和从库的影响
- **测试模式**：可在从库测试后再到主库执行
- **动态控制**：运行时可通过交互命令调整参数

### 5.3 基础用法
```bash
# 直接在主库执行
gh-ost \
  --host="127.0.0.1" \
  --database="mydb" \
  --table="big_table" \
  --alter="ADD COLUMN new_column INT NOT NULL DEFAULT 0" \
  --execute \
  --allow-on-master \
  --cut-over=default \
  --max-load=Threads_running=30 \
  --critical-load=Threads_running=100 \
  --chunk-size=1000 \
  --max-lag-millis=2000 \
  --postpone-cut-over-flag-file=/tmp/ghost-postpone.flag
```

### 5.4 运行模式
```bash
# 模式1：连接从库，在主库执行（推荐）
gh-ost --host=slave_host --database=db --table=tbl --alter="..." --execute

# 模式2：直接在主库执行
gh-ost --host=master_host --database=db --table=tbl --alter="..." --allow-on-master --execute

# 模式3：在从库测试
gh-ost --host=slave_host --database=db --table=tbl --alter="..." --test-on-replica --execute

# 模式4：迁移到其他服务器
gh-ost --host=source_host --database=db --table=tbl --alter="..." --execute \
  --assume-master-host=target_host
```

### 5.5 交互式控制
```bash
# 创建控制文件实现交互
echo throttle | socat - /tmp/gh-ost.sock  # 暂停数据复制
echo no-throttle | socat - /tmp/gh-ost.sock  # 恢复复制
echo panic | socat - /tmp/gh-ost.sock  # 紧急停止
echo "chunk-size=500" | socat - /tmp/gh-ost.sock  # 修改参数
```

### 5.6 优点与缺点
**优点：**
- 无触发器，对写入性能影响小
- 精细的负载控制机制
- 支持在线参数调整
- 灵活的测试和回滚方案

**缺点：**
- 需要binlog格式为ROW
- 配置相对复杂
- 社区支持较pt-osc略少

## 6. 方案选择指南

### 6.1 选择矩阵
| 场景 | 推荐方案 | 理由 |
|------|---------|------|
| 小表简单操作 | MySQL原生Online DDL | 简单快速，无需工具依赖 |
| MySQL 5.5或以下版本 | pt-online-schema-change | 原生不支持Online DDL |
| 写入敏感型业务 | gh-ost | 无触发器，写入影响最小 |
| 有外键约束的表 | pt-online-schema-change | 外键支持更成熟 |
| 需要频繁调整参数 | gh-ost | 支持运行时动态调整 |
| 资源紧张环境 | 原生Online DDL | 额外资源消耗最少 |

### 6.2 通用最佳实践

#### 6.2.1 前期准备
```sql
-- 1. 备份原表结构
SHOW CREATE TABLE big_table\G

-- 2. 评估表大小和结构
SELECT 
  TABLE_NAME,
  TABLE_ROWS,
  DATA_LENGTH/1024/1024/1024 AS data_size_gb,
  INDEX_LENGTH/1024/1024/1024 AS index_size_gb
FROM information_schema.TABLES 
WHERE TABLE_SCHEMA = 'your_db' AND TABLE_NAME = 'big_table';

-- 3. 检查表碎片
SELECT ENGINE, DATA_FREE/1024/1024/1024 AS data_free_gb
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'your_db' AND TABLE_NAME = 'big_table';

-- 4. 创建测试环境验证
```

#### 6.2.2 执行时机选择
- 业务低峰期（通常凌晨）
- 避开批量任务执行时间
- 监控业务周期和特殊活动

#### 6.2.3 监控指标
```bash
# 数据库负载监控
watch -n 1 "mysql -e 'SHOW GLOBAL STATUS LIKE \"Threads_running\"'"

# 复制延迟监控
pt-heartbeat --monitor --database=percona --interval=1

# 磁盘空间监控
df -h /var/lib/mysql

# 进程监控
pt-ioprofile --profile-pid=$(pidof mysqld)
```

#### 6.2.4 回滚计划
1. **方案预演**：在从库或测试环境完整演练
2. **备份策略**：执行前全量备份
3. **中断预案**：明确各种异常情况的处理流程
4. **验证脚本**：准备数据一致性验证脚本

## 7. 典型案例

### 7.1 添加索引（十亿级用户表）
```bash
# 使用gh-ost添加索引，最小化业务影响
gh-ost \
  --host=slave1.company.com \
  --assume-master-host=master.company.com \
  --database=user_db \
  --table=user_profile \
  --alter="ADD INDEX idx_created_at (created_at)" \
  --execute \
  --max-load=Threads_running=40 \
  --critical-load=Threads_running=80 \
  --chunk-size=2000 \
  --max-lag-millis=1500 \
  --cut-over-lock-timeout-seconds=10 \
  --dml-batch-size=100 \
  --default-retries=3
```

### 7.2 修改字段类型（高并发交易表）
```bash
# 使用pt-online-schema-change，逐步迁移
pt-online-schema-change \
  --alter="MODIFY COLUMN amount DECIMAL(20,6) NOT NULL" \
  D=finance_db,t=transactions \
  --execute \
  --chunk-size=500 \
  --chunk-time=0.3 \
  --max-lag=5 \
  --check-interval=2 \
  --set-vars="innodb_lock_wait_timeout=2" \
  --no-check-alter \
  --progress=time,30
```

### 7.3 分区表改造（日志表）
```bash
# 原生Online DDL创建分区
ALTER TABLE log_data 
PARTITION BY RANGE (YEAR(created_at)) (
    PARTITION p2020 VALUES LESS THAN (2021),
    PARTITION p2021 VALUES LESS THAN (2022),
    PARTITION p2022 VALUES LESS THAN (2023),
    PARTITION p2023 VALUES LESS THAN (2024),
    PARTITION p_max VALUES LESS THAN MAXVALUE
) ALGORITHM=INPLACE, LOCK=NONE;
```

## 8. 故障处理与优化

### 8.1 常见问题解决

#### 问题1：复制延迟过大
```bash
# gh-ost解决方案
gh-ost ... --throttle-control-replicas="slave1:3306,slave2:3306" --max-lag-millis=2000

# pt-osc解决方案
pt-online-schema-change ... --max-lag=10 --check-slave-lag="slave1,slave2"
```

#### 问题2：磁盘空间不足
```sql
-- 清理前检查
SELECT TABLE_SCHEMA, TABLE_NAME, 
  DATA_LENGTH/1024/1024/1024 as data_gb,
  INDEX_LENGTH/1024/1024/1024 as index_gb
FROM information_schema.TABLES 
ORDER BY (DATA_LENGTH+INDEX_LENGTH) DESC LIMIT 10;

-- 预留足够空间
-- gh-ost: 需要原表大小的额外空间
-- pt-osc: 需要原表大小的额外空间
-- 原生Online DDL: 视操作类型而定
```

#### 问题3：外键约束冲突
```sql
-- 临时禁用外键检查
SET FOREIGN_KEY_CHECKS=0;
-- 执行变更
-- 恢复外键检查
SET FOREIGN_KEY_CHECKS=1;
```

### 8.2 性能优化建议
1. **批量处理调优**：根据系统负载动态调整chunk-size
2. **索引策略**：变更前删除冗余索引，变更后重建
3. **存储引擎**：确保使用InnoDB以获得最佳Online DDL支持
4. **参数优化**：适当增加`innodb_online_alter_log_max_size`

## 9. 未来趋势

1. **云原生支持**：AWS RDS、Aurora等云数据库的托管DDL服务
2. **自动化运维**：基于机器学习的DDL智能调度
3. **并行处理**：多线程并行数据迁移技术
4. **无缝切换**：零感知的DDL切换技术

## 附录：工具安装与配置

### gh-ost安装
```bash
# 下载最新版本
wget https://github.com/github/gh-ost/releases/download/v1.1.6/gh-ost_1.1.6_amd64.deb
# 安装
dpkg -i gh-ost_1.1.6_amd64.deb
# 或使用二进制文件
wget https://github.com/github/gh-ost/releases/download/v1.1.6/gh-ost-binary-linux-1.1.6.tgz
tar xvf gh-ost-binary-linux-1.1.6.tgz
sudo mv gh-ost /usr/local/bin/
```

### Percona Toolkit安装
```bash
# CentOS/RHEL
sudo yum install https://repo.percona.com/yum/percona-release-latest.noarch.rpm
sudo yum install percona-toolkit

# Ubuntu/Debian
wget https://repo.percona.com/apt/percona-release_latest.$(lsb_release -sc)_all.deb
sudo dpkg -i percona-release_latest.$(lsb_release -sc)_all.deb
sudo apt-get update
sudo apt-get install percona-toolkit
```

---

**文档版本**：1.0  
**更新日期**：2024年  
**适用环境**：MySQL 5.6+，生产环境大表DDL变更  
**注意事项**：所有生产环境变更前务必在测试环境充分验证