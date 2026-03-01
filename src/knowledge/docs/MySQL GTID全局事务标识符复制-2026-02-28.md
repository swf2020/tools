# MySQL GTID（全局事务标识符）复制技术文档

## 1. 概述

### 1.1 GTID复制简介
GTID（Global Transaction Identifier，全局事务标识符）是MySQL 5.6版本引入的复制技术，它为每个提交的事务分配一个全局唯一的标识符。与传统基于二进制日志文件和位置的复制相比，GTID复制简化了复制配置和故障转移过程。

### 1.2 与传统复制的对比
| 特性 | 传统复制 | GTID复制 |
|------|---------|---------|
| 标识方式 | 二进制日志文件名和位置 | 全局唯一事务ID |
| 故障转移 | 需要手动定位位置 | 自动识别位置 |
| 主从切换 | 复杂，需重新定位 | 简单，自动跟踪 |
| 一致性 | 可能不一致 | 保证全局一致 |
| 配置复杂度 | 较高 | 相对简单 |

## 2. GTID工作原理

### 2.1 GTID格式
```
GTID = source_id:transaction_id
```
- **source_id**：源服务器UUID，格式如：3E11FA47-71CA-11E1-9E33-C80AA9429562
- **transaction_id**：事务序列号，从1开始递增

### 2.2 GTID生命周期
1. **事务提交时**：主库为事务生成GTID
2. **写入二进制日志**：GTID与事务内容一同记录
3. **从库应用**：从库读取GTID并记录已执行GTID集合
4. **故障恢复**：根据GTID集合确定复制位置

### 2.3 GTID集合
- **已执行GTID集合**：记录从库已执行的所有GTID
- **已接收GTID集合**：记录从库已接收但未执行的GTID
- **已清除GTID集合**：记录已从二进制日志清除的GTID

## 3. 配置GTID复制

### 3.1 环境要求
- MySQL 5.6.5或更高版本
- 建议所有服务器版本一致
- 启用二进制日志

### 3.2 主服务器配置（my.cnf）
```ini
[mysqld]
# 基础配置
server_id = 1
log_bin = mysql-bin
binlog_format = ROW

# GTID配置
gtid_mode = ON
enforce_gtid_consistency = ON
log_slave_updates = ON

# 可选：简化故障转移
binlog_checksum = NONE  # 5.6兼容性
```

### 3.3 从服务器配置
```ini
[mysqld]
server_id = 2
relay_log = relay-log
read_only = ON

gtid_mode = ON
enforce_gtid_consistency = ON
log_slave_updates = ON
```

### 3.4 初始化数据同步

#### 方法一：使用mysqldump
```bash
# 主库备份
mysqldump --single-transaction --master-data=2 \
  --triggers --routines --events \
  --all-databases > backup.sql

# 从库恢复
mysql -u root -p < backup.sql
```

#### 方法二：使用Percona XtraBackup（推荐生产环境）
```bash
# 备份主库
innobackupex --user=root --password=xxx /backup/
innobackupex --apply-log /backup/YYYY-MM-DD_HH-MM-SS/

# 恢复从库
systemctl stop mysql
mv /var/lib/mysql /var/lib/mysql_old
innobackupex --copy-back /backup/YYYY-MM-DD_HH-MM-SS/
chown -R mysql:mysql /var/lib/mysql
systemctl start mysql
```

### 3.5 配置复制通道

```sql
-- 在从库执行
STOP SLAVE;

-- 基于GTID的复制配置
CHANGE MASTER TO
  MASTER_HOST = 'master_host',
  MASTER_PORT = 3306,
  MASTER_USER = 'repl_user',
  MASTER_PASSWORD = 'repl_password',
  MASTER_AUTO_POSITION = 1;

START SLAVE;

-- 验证复制状态
SHOW SLAVE STATUS\G
```

## 4. 监控与管理

### 4.1 监控命令

```sql
-- 查看GTID状态
SHOW GLOBAL VARIABLES LIKE '%gtid%';

-- 查看GTID执行情况
SELECT * FROM mysql.gtid_executed;

-- 查看主库GTID信息
SHOW MASTER STATUS;

-- 查看从库复制状态
SHOW SLAVE STATUS\G

-- 查看GTID相关变量
SELECT 
  @@GLOBAL.gtid_executed AS executed_gtids,
  @@GLOBAL.gtid_purged AS purged_gtids,
  @@GLOBAL.gtid_owned AS owned_gtids;
```

### 4.2 监控指标
```sql
-- GTID复制延迟监控
SELECT 
  SUBSTRING_INDEX(SUBSTRING_INDEX(ts.trx_state, ':', 1), ':', -1) AS source_uuid,
  MAX(SUBSTRING_INDEX(SUBSTRING_INDEX(ts.trx_state, ':', 2), ':', -1)) AS max_transaction_id,
  NOW() AS current_time
FROM performance_schema.replication_connection_status rcs
JOIN performance_schema.replication_applier_status_by_worker rasbw 
  ON rcs.channel_name = rasbw.channel_name
JOIN performance_schema.transaction_state ts 
  ON rasbw.thread_id = ts.thread_id
GROUP BY source_uuid;
```

## 5. 运维操作

### 5.1 主从切换

#### 计划内切换
```sql
-- 1. 原主库设置只读
SET GLOBAL read_only = ON;

-- 2. 等待从库追平
SHOW SLAVE STATUS\G  -- 确保Seconds_Behind_Master为0

-- 3. 提升从库为主库
STOP SLAVE;
RESET SLAVE ALL;
SET GLOBAL read_only = OFF;

-- 4. 其他从库指向新主库
STOP SLAVE;
CHANGE MASTER TO MASTER_HOST='new_master', MASTER_AUTO_POSITION=1;
START SLAVE;
```

### 5.2 跳过错误事务
```sql
-- 临时跳过特定GTID事务
STOP SLAVE;
SET GTID_NEXT = 'source_id:transaction_id';
BEGIN; COMMIT;
SET GTID_NEXT = 'AUTOMATIC';
START SLAVE;

-- 批量跳过错误（谨慎使用）
STOP SLAVE;
SET @@GLOBAL.sql_slave_skip_counter = 1;
START SLAVE;
```

### 5.3 重新同步数据

```sql
-- 1. 从库停止复制
STOP SLAVE;

-- 2. 重置GTID执行记录（危险操作，仅用于重建）
RESET MASTER;  -- 清除所有GTID记录

-- 3. 重新建立复制
CHANGE MASTER TO MASTER_AUTO_POSITION=1;
START SLAVE;
```

## 6. 故障排除

### 6.1 常见问题及解决

#### 问题1：GTID一致性错误
```
错误：Slave has more GTIDs than the master
```
**解决方案**：
```sql
-- 在从库执行
STOP SLAVE;
RESET MASTER;  -- 注意：这会清除所有GTID记录
START SLAVE;
```

#### 问题2：复制中断（缺失事务）
```
错误：Cannot replicate because the master purged required binary logs
```
**解决方案**：
```bash
# 1. 从其他从库备份数据
# 2. 重建问题从库
# 3. 使用备份恢复
```

#### 问题3：网络中断后恢复
```sql
-- 检查GTID差距
SELECT 
  master_uuid,
  master_gtid_set,
  @@GLOBAL.gtid_executed as slave_gtid_executed
FROM performance_schema.replication_connection_status;

-- 重新配置复制
STOP SLAVE;
CHANGE MASTER TO MASTER_AUTO_POSITION=1;
START SLAVE;
```

### 6.2 重要日志检查
```bash
# 错误日志
tail -f /var/log/mysql/error.log

# 慢查询日志（如果复制延迟）
grep "Slave SQL" /var/log/mysql/slow.log

# GTID相关日志
grep -i gtid /var/log/mysql/error.log
```

## 7. 最佳实践

### 7.1 配置建议
1. **统一配置**：所有节点使用相同MySQL版本和配置
2. **网络优化**：确保主从间网络延迟低且稳定
3. **监控告警**：设置GTID复制状态的监控告警
4. **定期备份**：定期备份GTID执行位置信息

### 7.2 安全建议
```sql
-- 限制复制用户权限
CREATE USER 'repl_user'@'%' IDENTIFIED BY 'strong_password';
GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'repl_user'@'%';

-- 启用SSL连接（如需要）
CHANGE MASTER TO 
  MASTER_SSL=1,
  MASTER_SSL_CA='/path/to/ca.pem',
  MASTER_SSL_CERT='/path/to/client-cert.pem',
  MASTER_SSL_KEY='/path/to/client-key.pem';
```

### 7.3 性能优化
```ini
# my.cnf优化配置
[mysqld]
# 并行复制（MySQL 5.7+）
slave_parallel_workers = 4
slave_parallel_type = LOGICAL_CLOCK

# 减少网络延迟影响
slave_net_timeout = 60

# 提高复制效率
sync_binlog = 1
innodb_flush_log_at_trx_commit = 1
```

## 8. 限制与注意事项

### 8.1 GTID复制限制
1. **不支持的操作**：
   - CREATE TABLE ... SELECT（行格式二进制日志）
   - 临时表事务
   - 某些DDL语句的原子性

2. **版本兼容性**：
   - MySQL 5.6.5+ 支持基本GTID
   - MySQL 5.7+ 支持增强功能
   - 混合版本部署需谨慎

### 8.2 升级注意事项
1. 从传统复制升级到GTID复制需要停机时间
2. 升级前必须测试所有应用程序兼容性
3. 建议先在一个从库上测试升级

## 9. 附录

### 9.1 常用命令速查
```sql
-- 启用/禁用GTID
SET @@GLOBAL.ENFORCE_GTID_CONSISTENCY = WARN;
SET @@GLOBAL.ENFORCE_GTID_CONSISTENCY = ON;
SET @@GLOBAL.GTID_MODE = OFF_PERMISSIVE;
SET @@GLOBAL.GTID_MODE = ON_PERMISSIVE;
SET @@GLOBAL.GTID_MODE = ON;

-- 查看GTID状态
SHOW VARIABLES LIKE '%gtid%';

-- 重置GTID（谨慎使用）
RESET MASTER;
```

### 9.2 相关系统表
- `mysql.gtid_executed`：持久化存储已执行GTID
- `performance_schema.replication_*`：复制监控表
- `information_schema.processlist`：查看复制线程

### 9.3 参考文档
1. [MySQL官方文档 - GTID复制](https://dev.mysql.com/doc/refman/8.0/en/replication-gtids.html)
2. [MySQL高可用解决方案](https://dev.mysql.com/doc/mysql-ha-scalability/en/)
3. [Percona GTID最佳实践](https://www.percona.com/blog/)

---

**文档版本**：1.0  
**最后更新**：2024年  
**适用版本**：MySQL 5.6.5+  
**注意事项**：生产环境变更前请充分测试，建议在维护窗口操作。

*本技术文档仅供参考，实际配置请根据具体环境和需求调整。*