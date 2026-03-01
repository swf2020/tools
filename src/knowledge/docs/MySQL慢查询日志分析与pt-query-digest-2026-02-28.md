# MySQL慢查询日志分析与pt-query-digest工具指南

## 1. 概述

### 1.1 什么是慢查询日志
MySQL慢查询日志是MySQL数据库记录执行时间超过指定阈值的SQL语句的日志文件，用于识别和优化性能瓶颈。

### 1.2 慢查询日志的重要性
- 识别性能瓶颈
- 优化查询性能
- 提高数据库整体性能
- 发现索引使用问题

## 2. 配置MySQL慢查询日志

### 2.1 启用慢查询日志

```sql
-- 临时启用（重启失效）
SET GLOBAL slow_query_log = 'ON';
SET GLOBAL long_query_time = 2; -- 单位：秒
SET GLOBAL slow_query_log_file = '/var/log/mysql/mysql-slow.log';

-- 永久配置（修改my.cnf或my.ini）
[mysqld]
slow_query_log = 1
slow_query_log_file = /var/log/mysql/mysql-slow.log
long_query_time = 2
log_queries_not_using_indexes = 1
min_examined_row_limit = 100
```

### 2.2 配置参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `slow_query_log` | OFF | 是否开启慢查询日志 |
| `slow_query_log_file` | host_name-slow.log | 日志文件路径 |
| `long_query_time` | 10 | 慢查询阈值（秒） |
| `log_queries_not_using_indexes` | OFF | 记录未使用索引的查询 |
| `log_throttle_queries_not_using_indexes` | 0 | 限制每分钟记录的未使用索引查询数 |
| `min_examined_row_limit` | 0 | 最小检查行数阈值 |
| `log_slow_admin_statements` | OFF | 记录管理语句（如OPTIMIZE TABLE） |
| `log_output` | FILE | 输出格式（FILE/TABLE） |

## 3. 慢查询日志格式解析

### 3.1 标准日志格式示例
```
# Time: 2023-10-25T08:30:15.123456Z
# User@Host: root[root] @ localhost []  Id: 12345
# Query_time: 5.123456  Lock_time: 0.001234  Rows_sent: 10  Rows_examined: 1000000
SET timestamp=1698215415;
SELECT * FROM orders WHERE customer_id = 123 AND order_date > '2023-01-01';
```

### 3.2 关键字段说明
- **Query_time**: 查询执行总时间
- **Lock_time**: 等待表锁的时间
- **Rows_sent**: 返回给客户端的行数
- **Rows_examined**: 扫描的行数

## 4. pt-query-digest工具详解

### 4.1 工具安装

```bash
# Ubuntu/Debian
sudo apt-get install percona-toolkit

# CentOS/RHEL
sudo yum install percona-toolkit

# 或使用Perl CPAN安装
cpan install DBD::mysql
wget https://www.percona.com/downloads/percona-toolkit/3.5.0/binary/tarball/percona-toolkit-3.5.0_x86_64.tar.gz
tar -zxvf percona-toolkit-*.tar.gz
```

### 4.2 基本用法

```bash
# 分析慢查询日志
pt-query-digest /var/log/mysql/mysql-slow.log

# 输出到文件
pt-query-digest /var/log/mysql/mysql-slow.log > slow_report.txt

# 分析最近24小时的慢查询
pt-query-digest --since=24h /var/log/mysql/mysql-slow.log

# 分析特定时间范围的查询
pt-query-digest --since='2023-10-25 00:00:00' --until='2023-10-25 23:59:59' mysql-slow.log
```

### 4.3 高级选项

```bash
# 限制输出结果数量
pt-query-digest --limit 10 /var/log/mysql/mysql-slow.log

# 按特定维度排序
pt-query-digest --order-by Query_time:sum /var/log/mysql/mysql-slow.log

# 过滤特定数据库
pt-query-digest --filter '($event->{db} || "") =~ /^mydatabase$/' mysql-slow.log

# 分析并保存到数据库
pt-query-digest --review h=localhost,D=slow_query_log,t=global_query_review \
                --history h=localhost,D=slow_query_log,t=global_query_review_history \
                --no-report mysql-slow.log

# 生成JSON输出
pt-query-digest --output json /var/log/mysql/mysql-slow.log
```

### 4.4 实时监控分析

```bash
# 从tcpdump实时分析
tcpdump -s 65535 -x -nn -q -tttt -i any -c 1000 port 3306 > mysql.tcp.txt
pt-query-digest --type tcpdump mysql.tcp.txt

# 从PROCESSLIST分析
pt-query-digest --processlist h=localhost --interval 0.01 --print
```

## 5. 分析报告解读

### 5.1 报告结构

```
# 概览部分
# 360ms user time, 20ms system time, 26.45M rss, 215.82M vsz
# Current date: Wed Oct 25 10:30:00 2023
# Hostname: db-server
# Files: mysql-slow.log
# Overall: 1.23k total, 21 unique, 0.00 QPS, 0.01x concurrency _______
# Time range: 2023-10-24 00:00:00 to 2023-10-25 10:30:00
# Attribute          total     min     max     avg     95%  stddev  median
# ============     ======= ======= ======= ======= ======= ======= =======
# Exec time         2847s    100ms     35s      2s      5s      3s      1s
# Lock time           12s       0    500ms     9ms    50ms    25ms     1ms
# Rows sent          8.25M       0  100.00k   6.85k  49.21k  10.12k   1.02k
# Rows examine      25.43M       0   1.50M   21.08k 100.23k  45.67k   5.23k
# Query size         5.65M       6  10.23k   4.80k   8.19k   1.23k   2.56k
```

### 5.2 查询分组分析

```
# Profile
# Rank Query ID           Response time Calls R/Call V/M   Item
# ==== ================== ============= ===== ====== ===== ==============
#    1 0xABCDEF1234567890 1124.3618 39%   234  4.8057 0.15 SELECT orders
#    2 0xFEDCBA9876543210  892.1432 31%   189  4.7203 0.22 SELECT users
#    3 0x1234567890ABCDEF  456.8921 16%   567  0.8056 0.08 UPDATE products
```

### 5.3 详细查询分析

```
# Query 1: 0.00 QPS, 0.00x concurrency, ID 0xABCDEF1234567890 at byte 123456
# Scores: V/M = 0.15
# Time range: 2023-10-24 00:00:00 to 2023-10-25 10:30:00
# Attribute    pct   total     min     max     avg     95%  stddev  median
# ============ === ======= ======= ======= ======= ======= ======= =======
# Count          8     234
# Exec time     39   1124s      1s     35s      5s     12s      3s      4s
# Lock time     15      2s       0   100ms     9ms    50ms    10ms     5ms
# Rows sent     12   1.23M       0  10.00k   5.38k   9.23k   1.23k   4.56k
# Rows examine  45  11.45M   1.23k   1.50M  50.05k 100.23k  25.67k  45.23k
# Query size    18   1.02M   1.23k   8.19k   4.47k   6.54k   1.23k   4.12k
# String:
# Databases    production
# Hosts        app-server-1 (50%), app-server-2 (30%), app-server-3 (20%)
# Users        app_user
# Query_time distribution
#   1us
#  10us
# 100us
#   1ms
#  10ms  ################
# 100ms  ####################################################
#    1s  ##########
#  10s+  ###
# Tables:
#    SHOW TABLE STATUS FROM `production` LIKE 'orders'\G
#    SHOW CREATE TABLE `production`.`orders`\G
# EXPLAIN /*!50100 PARTITIONS*/
SELECT * FROM orders WHERE customer_id = ? AND order_date > ? AND status = 'pending'\G
```

## 6. 性能问题识别与优化建议

### 6.1 常见问题模式识别

| 问题类型 | 特征 | 优化建议 |
|----------|------|----------|
| 全表扫描 | Rows_examined远大于Rows_sent | 添加合适的索引 |
| 大量小查询 | 查询次数多，单次执行快 | 考虑批量操作或缓存 |
| 锁等待 | Lock_time占比高 | 优化事务隔离级别，拆分事务 |
| 临时表 | Using temporary出现频繁 | 优化查询语句，添加适当索引 |
| 文件排序 | Using filesort | 添加ORDER BY相关索引 |

### 6.2 优化示例

```sql
-- 优化前（慢查询）
SELECT * FROM orders 
WHERE customer_id = 123 
  AND DATE(order_date) = '2023-10-25'
  AND status = 'pending';

-- 优化后
SELECT * FROM orders 
WHERE customer_id = 123 
  AND order_date >= '2023-10-25 00:00:00' 
  AND order_date < '2023-10-26 00:00:00'
  AND status = 'pending';

-- 添加复合索引
ALTER TABLE orders ADD INDEX idx_customer_status_date (customer_id, status, order_date);
```

## 7. 自动化监控方案

### 7.1 定时分析脚本

```bash
#!/bin/bash
# slow_query_analyzer.sh

LOG_FILE="/var/log/mysql/mysql-slow.log"
REPORT_DIR="/var/log/mysql/reports"
DATE=$(date +%Y%m%d_%H%M%S)

# 分析慢查询日志
pt-query-digest $LOG_FILE > $REPORT_DIR/slow_report_$DATE.txt

# 发送报告（可选）
# mail -s "MySQL Slow Query Report $DATE" admin@example.com < $REPORT_DIR/slow_report_$DATE.txt

# 归档原日志文件
mv $LOG_FILE $LOG_FILE.$DATE
mysqladmin flush-logs
```

### 7.2 Crontab配置

```bash
# 每天凌晨分析前一天的慢查询
0 1 * * * /path/to/slow_query_analyzer.sh

# 每小时分析一次（高负载环境）
0 * * * * pt-query-digest --since=1h /var/log/mysql/mysql-slow.log > /tmp/hourly_report.txt
```

## 8. 最佳实践

1. **阈值设置合理**
   - 生产环境：1-2秒
   - 测试环境：0.1-0.5秒

2. **定期分析**
   - 每日分析生产环境慢查询
   - 每周生成性能趋势报告

3. **索引优化策略**
   - 使用EXPLAIN分析执行计划
   - 优先优化最频繁的慢查询
   - 定期审查和重建索引

4. **日志管理**
   - 设置日志轮转，避免磁盘空间不足
   - 保留历史日志（至少30天）
   - 定期清理过期的慢查询日志

5. **监控告警**
   - 设置慢查询数量阈值告警
   - 监控慢查询执行时间趋势
   - 关键业务SQL性能监控

## 9. 总结

MySQL慢查询日志结合pt-query-digest工具是数据库性能优化的利器。通过系统性地收集、分析和优化慢查询，可以显著提升数据库性能和应用响应速度。建议将慢查询分析纳入日常运维工作，建立完整的性能监控和优化体系。

## 附录：常用命令速查

```bash
# 查看慢查询配置
SHOW VARIABLES LIKE '%slow%';

# 查看当前慢查询数量
SHOW GLOBAL STATUS LIKE 'Slow_queries';

# 临时启用慢查询日志
SET GLOBAL slow_query_log = ON;

# 使用pt-query-digest分析
pt-query-digest /path/to/slow.log
pt-query-digest --limit 10 --order-by Query_time:sum slow.log
pt-query-digest --filter '($event->{db}) =~ /prod/' slow.log

# 分析并保存到数据库
pt-query-digest --review h=localhost,D=slow_log,t=review_table \
                --history h=localhost,D=slow_log,t=history_table \
                slow.log
```