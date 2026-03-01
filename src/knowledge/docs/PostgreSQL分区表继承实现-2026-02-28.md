# PostgreSQL 分区表继承实现技术文档

## 1. 概述

PostgreSQL 通过**表继承**机制提供了灵活的分区表实现方案。虽然 PostgreSQL 10+ 引入了声明式分区，但继承式分区仍然在复杂场景中具有独特优势，特别是在需要跨分区差异化列定义或需要向后兼容旧版本时。

## 2. 核心概念

### 2.1 表继承模型
```
父表（逻辑表）
    ├── 子表1（物理分区）
    ├── 子表2（物理分区）
    └── 子表N（物理分区）
```

### 2.2 关键特性
- **数据路由**：通过约束排除（Constraint Exclusion）实现查询优化
- **数据继承**：子表继承父表所有列，并可扩展额外列
- **约束管理**：每个分区定义 CHECK 约束限定数据范围
- **触发器路由**：通过触发器或规则实现插入路由

## 3. 实现步骤

### 3.1 创建父表（逻辑表）
```sql
-- 创建父表（不存储实际数据）
CREATE TABLE measurement (
    id SERIAL,
    city_id INT NOT NULL,
    logdate DATE NOT NULL,
    peaktemp INT,
    unitsales INT
);

-- 创建索引（子表不会自动继承索引）
CREATE INDEX measurement_logdate_idx ON measurement(logdate);
```

### 3.2 创建子表（分区表）
```sql
-- 创建按月分区子表
CREATE TABLE measurement_y2023m01 (
    CHECK (logdate >= DATE '2023-01-01' AND logdate < DATE '2023-02-01')
) INHERITS (measurement);

CREATE TABLE measurement_y2023m02 (
    CHECK (logdate >= DATE '2023-02-01' AND logdate < DATE '2023-03-01')
) INHERITS (measurement);

-- 为子表创建独立索引
CREATE INDEX measurement_y2023m01_logdate_idx ON measurement_y2023m01(logdate);
CREATE INDEX measurement_y2023m01_city_id_idx ON measurement_y2023m01(city_id);
```

### 3.3 创建路由函数与触发器
```sql
-- 插入路由函数
CREATE OR REPLACE FUNCTION measurement_insert_trigger()
RETURNS TRIGGER AS $$
BEGIN
    IF (NEW.logdate >= DATE '2023-01-01' AND NEW.logdate < DATE '2023-02-01') THEN
        INSERT INTO measurement_y2023m01 VALUES (NEW.*);
    ELSIF (NEW.logdate >= DATE '2023-02-01' AND NEW.logdate < DATE '2023-03-01') THEN
        INSERT INTO measurement_y2023m02 VALUES (NEW.*);
    ELSE
        RAISE EXCEPTION 'Date out of range: %', NEW.logdate;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- 创建触发器
CREATE TRIGGER insert_measurement_trigger
    BEFORE INSERT ON measurement
    FOR EACH ROW EXECUTE FUNCTION measurement_insert_trigger();
```

### 3.4 替代方案：使用规则（Rule）
```sql
-- 创建插入规则（适用于批量插入，但效率低于触发器）
CREATE RULE measurement_insert_y2023m01 AS
ON INSERT TO measurement
WHERE (logdate >= DATE '2023-01-01' AND logdate < DATE '2023-02-01')
DO INSTEAD INSERT INTO measurement_y2023m01 VALUES (NEW.*);
```

## 4. 约束排除配置

### 4.1 启用约束排除
```sql
-- 在postgresql.conf中设置
# constraint_exclusion = partition   # 默认值，推荐
# constraint_exclusion = on          # 对所有查询生效（可能影响性能）
# constraint_exclusion = off         # 禁用约束排除

-- 会话级设置
SET constraint_exclusion = partition;
```

### 4.2 约束排除原理
```sql
-- 优化器会检查CHECK约束，排除不需要扫描的分区
EXPLAIN ANALYZE
SELECT * FROM measurement
WHERE logdate >= '2023-01-15' AND logdate < '2023-01-20';

-- 结果应显示只扫描 measurement_y2023m01 分区
```

## 5. 分区管理操作

### 5.1 添加新分区
```sql
-- 创建新月份分区
CREATE TABLE measurement_y2023m03 (
    CHECK (logdate >= DATE '2023-03-01' AND logdate < DATE '2023-04-01')
) INHERITS (measurement);

-- 更新路由函数
CREATE OR REPLACE FUNCTION measurement_insert_trigger()
RETURNS TRIGGER AS $$
BEGIN
    -- 原有逻辑...
    ELSIF (NEW.logdate >= DATE '2023-03-01' AND NEW.logdate < DATE '2023-04-01') THEN
        INSERT INTO measurement_y2023m03 VALUES (NEW.*);
    -- 原有逻辑...
END;
$$ LANGUAGE plpgsql;
```

### 5.2 删除分区
```sql
-- 分离分区（保留数据）
ALTER TABLE measurement_y2023m01 NO INHERIT measurement;

-- 删除分区（同时删除数据）
DROP TABLE measurement_y2023m01;
```

### 5.3 数据迁移
```sql
-- 将数据移动到另一个分区
WITH moved_rows AS (
    DELETE FROM measurement_y2023m01
    WHERE logdate >= '2023-01-25'
    RETURNING *
)
INSERT INTO measurement_y2023m02
SELECT * FROM moved_rows;
```

## 6. 查询优化技巧

### 6.1 分区键条件优化
```sql
-- 有效：条件与CHECK约束匹配
SELECT * FROM measurement
WHERE logdate >= '2023-01-01' AND logdate < '2023-02-01';

-- 有效：包含分区键的条件
SELECT * FROM measurement
WHERE city_id = 1
  AND logdate >= '2023-01-01' AND logdate < '2023-02-01';

-- 低效：缺少分区键条件，需要扫描所有分区
SELECT * FROM measurement WHERE city_id = 1;
```

### 6.2 聚合查询优化
```sql
-- 使用分区键进行聚合
SELECT date_trunc('month', logdate) as month,
       COUNT(*) as total_records,
       AVG(peaktemp) as avg_temp
FROM measurement
WHERE logdate >= '2023-01-01' AND logdate < '2023-04-01'
GROUP BY date_trunc('month', logdate);

-- 并行查询各分区
SET max_parallel_workers_per_gather = 4;
```

## 7. 高级特性实现

### 7.1 多级分区（子分区）
```sql
-- 创建按年分区的父表
CREATE TABLE measurement_y2023 (
    CHECK (logdate >= DATE '2023-01-01' AND logdate < DATE '2024-01-01')
) INHERITS (measurement);

-- 创建月份子分区
CREATE TABLE measurement_y2023m01 (
    CHECK (logdate >= DATE '2023-01-01' AND logdate < DATE '2023-02-01')
) INHERITS (measurement_y2023);
```

### 7.2 自定义分区策略
```sql
-- 基于城市ID的哈希分区
CREATE TABLE measurement_city_1 (
    CHECK (city_id % 4 = 0)
) INHERITS (measurement);

-- 复杂的组合分区
CREATE TABLE measurement_special (
    CHECK (
        (logdate >= '2023-01-01' AND logdate < '2023-04-01')
        AND (city_id BETWEEN 1 AND 10)
    )
) INHERITS (measurement);
```

## 8. 监控与维护

### 8.1 分区状态检查
```sql
-- 查看分区继承关系
SELECT inhparent::regclass AS parent,
       inhrelid::regclass AS child
FROM pg_inherits
WHERE inhparent = 'measurement'::regclass;

-- 检查分区约束
SELECT conname, consrc
FROM pg_constraint
WHERE conrelid = 'measurement_y2023m01'::regclass
  AND contype = 'c';

-- 分析分区数据分布
SELECT tableoid::regclass AS partition_name,
       COUNT(*) as row_count,
       MIN(logdate) as min_date,
       MAX(logdate) as max_date
FROM measurement
GROUP BY tableoid
ORDER BY min_date;
```

### 8.2 性能监控
```sql
-- 检查约束排除效果
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM measurement
WHERE logdate >= '2023-01-15';

-- 监控分区扫描统计
SELECT schemaname, relname, seq_scan, seq_tup_read,
       idx_scan, idx_tup_fetch
FROM pg_stat_user_tables
WHERE relname LIKE 'measurement_%';
```

## 9. 限制与注意事项

### 9.1 已知限制
- 外键约束不能跨分区引用
- 唯一约束必须包含分区键或使用独立索引
- 自动增长序列在分区中不共享
- VACUUM 操作需要对每个分区单独执行

### 9.2 最佳实践
1. **分区数量控制**：建议不超过100-200个分区
2. **分区粒度选择**：根据数据量和查询模式决定
3. **约束优化**：确保CHECK约束能被优化器识别
4. **定期维护**：对热点分区单独进行维护操作

### 9.3 与声明式分区对比

| 特性 | 继承分区 | 声明式分区（PG10+） |
|------|----------|-------------------|
| 多列分区键 | 支持 | 支持 |
| 默认分区 | 不支持 | 支持 |
| 分区索引 | 手动创建 | 自动创建 |
| 分区卸载 | 需要触发器 | 内置支持 |
| 复杂约束 | 完全支持 | 有限支持 |
| 跨分区修改 | 灵活 | 限制较多 |

## 10. 故障排除

### 10.1 常见问题
```sql
-- 问题1：约束排除未生效
-- 解决方案：确保CHECK约束使用不可变表达式
-- 错误示例：CHECK (logdate >= CURRENT_DATE - INTERVAL '1 month')

-- 问题2：插入数据失败
-- 解决方案：检查触发器/规则是否正确路由
INSERT INTO measurement (city_id, logdate, peaktemp, unitsales)
VALUES (1, '2023-01-15', 25, 100)
RETURNING *;

-- 问题3：查询性能差
-- 解决方案：为常用查询条件创建索引，确保约束排除生效
ANALYZE measurement_y2023m01;  -- 更新统计信息
```

### 10.2 性能诊断
```sql
-- 检查约束排除状态
EXPLAIN (VERBOSE, COSTS OFF)
SELECT * FROM measurement WHERE logdate = '2023-01-15';

-- 强制禁用约束排除以对比性能
SET constraint_exclusion = off;
-- 执行查询...
SET constraint_exclusion = partition;
```

## 11. 总结

PostgreSQL 的继承式分区提供了高度灵活的数据分区方案，特别适用于：
- 需要复杂分区逻辑的场景
- 需要向后兼容旧版本 PostgreSQL
- 需要跨分区不同表结构的场景
- 需要精细控制分区维护操作的场景

虽然声明式分区在 PostgreSQL 10+ 中提供了更简洁的语法，但继承分区在复杂场景中仍然具有不可替代的优势。正确的实现需要仔细设计分区策略、优化约束定义和维护适当的触发器/规则机制。

## 附录：完整示例脚本

```sql
-- 完整的分区表实现示例
-- 创建父表
CREATE TABLE sales_data (
    id BIGSERIAL,
    sale_date DATE NOT NULL,
    region VARCHAR(50) NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建分区
CREATE TABLE sales_data_2023_q1 (
    CHECK (sale_date >= DATE '2023-01-01' AND sale_date < DATE '2023-04-01')
) INHERITS (sales_data);

-- 创建索引
CREATE INDEX sales_data_2023_q1_date_idx ON sales_data_2023_q1(sale_date);
CREATE INDEX sales_data_2023_q1_region_idx ON sales_data_2023_q1(region);

-- 创建路由触发器
CREATE OR REPLACE FUNCTION sales_data_insert_trigger()
RETURNS TRIGGER AS $$
BEGIN
    IF (NEW.sale_date >= DATE '2023-01-01' AND NEW.sale_date < DATE '2023-04-01') THEN
        INSERT INTO sales_data_2023_q1 VALUES (NEW.*);
    ELSE
        RAISE EXCEPTION 'Sale date % out of range', NEW.sale_date;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER insert_sales_data_trigger
    BEFORE INSERT ON sales_data
    FOR EACH ROW EXECUTE FUNCTION sales_data_insert_trigger();

-- 启用约束排除
SET constraint_exclusion = partition;
```

---

*文档版本：1.1 | 最后更新：2024年1月 | 适用版本：PostgreSQL 9.0+*