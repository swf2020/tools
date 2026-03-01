# MySQL执行计划（EXPLAIN）各字段含义详解

## 一、EXPLAIN命令概述

EXPLAIN是MySQL中用于分析SQL查询性能的关键工具，它可以显示MySQL如何执行一条SELECT语句，包括表的读取顺序、使用的索引、连接类型等重要信息。

### 基本使用方法：
```sql
EXPLAIN SELECT * FROM users WHERE age > 25;
-- 或
EXPLAIN FORMAT=JSON SELECT * FROM users WHERE age > 25;
```

## 二、EXPLAIN各字段详解

### 1. **id** - 查询标识符
- **含义**：SELECT查询的序列号，表示查询中执行SELECT子句或操作表的顺序
- **取值规则**：
  - id相同：执行顺序从上到下
  - id不同：id值越大，优先级越高，越先执行
  - id为NULL：表示是结果集，如UNION查询
- **示例分析**：
```sql
EXPLAIN 
SELECT t1.* FROM table1 t1 
UNION 
SELECT t2.* FROM table2 t2;
-- 第一个SELECT的id为1，第二个为2，UNION结果为NULL
```

### 2. **select_type** - 查询类型
- **SIMPLE**：简单SELECT查询，不包含子查询或UNION
- **PRIMARY**：查询中最外层的SELECT
- **SUBQUERY**：子查询中的第一个SELECT
- **DERIVED**：派生表（FROM子句中的子查询）
- **UNION**：UNION中的第二个及之后的SELECT
- **UNION RESULT**：UNION的结果
- **DEPENDENT SUBQUERY**：依赖外部查询的子查询
- **UNCACHEABLE SUBQUERY**：结果无法缓存的子查询

### 3. **table** - 访问的表
- **含义**：显示这一行的数据是关于哪张表的
- **特殊值**：
  - `<derivedN>`：派生表，N是id值
  - `<unionM,N>`：UNION结果，M,N是参与UNION的id值

### 4. **partitions** - 匹配的分区
- **含义**：查询匹配的分区（仅在使用分区表时显示）
- **示例**：`p0,p1` 表示查询使用了p0和p1分区

### 5. **type** - 连接类型（**关键性能指标**）
按性能从最优到最差排序：

#### **system**
- 表中只有一行数据，是const类型的特例

#### **const**
- 通过索引一次就找到，用于primary key或unique索引的等值比较
```sql
EXPLAIN SELECT * FROM users WHERE id = 1;
```

#### **eq_ref**
- 唯一性索引扫描，对于每个索引键，表中只有一条记录匹配
- 常见于主键或唯一索引的关联查询
```sql
EXPLAIN SELECT * FROM t1, t2 WHERE t1.id = t2.id;
```

#### **ref**
- 非唯一性索引扫描，返回匹配某个单独值的所有行
```sql
-- 假设age字段有普通索引
EXPLAIN SELECT * FROM users WHERE age = 25;
```

#### **ref_or_null**
- 类似ref，但包含对NULL值的搜索
```sql
EXPLAIN SELECT * FROM users WHERE age = 25 OR age IS NULL;
```

#### **range**
- 只检索给定范围的行，使用索引选择行
```sql
EXPLAIN SELECT * FROM users WHERE age BETWEEN 20 AND 30;
```

#### **index**
- Full Index Scan，遍历整个索引树
- 比ALL快，因为索引文件通常比数据文件小

#### **ALL**
- Full Table Scan，全表扫描
- **性能最差**，应尽量避免

### 6. **possible_keys** - 可能使用的索引
- **含义**：查询可能使用哪些索引来查找
- **注意**：列出的索引并不一定实际使用

### 7. **key** - 实际使用的索引
- **含义**：查询实际使用的索引
- **为NULL时**：表示没有使用索引

### 8. **key_len** - 使用的索引长度
- **含义**：索引字段的最大可能长度
- **计算规则**：所有索引字段的长度之和
- **用途**：
  - 判断复合索引是否被完全使用
  - 估算索引使用效率
- **示例**：
```sql
-- 假设索引为 (name VARCHAR(20), age INT)
-- utf8mb4字符集：20*4 + 1(变长字段) = 81
-- age为INT：4字节
-- 总长度：81 + 4 = 85
```

### 9. **ref** - 索引的引用
- **含义**：显示索引的哪一列被使用
- **常见值**：
  - `const`：常量值
  - `库名.表名.字段名`：关联查询的字段
  - `func`：函数

### 10. **rows** - 预估扫描行数
- **含义**：MySQL认为必须检查的行数
- **重要性**：**重要的性能指标**，rows越小越好

### 11. **filtered** - 过滤百分比
- **含义**：存储引擎返回的数据在server层过滤后，剩余多少百分比
- **范围**：0.00-100.00
- **理想值**：100.00，表示没有额外过滤

### 12. **Extra** - 额外信息（**重要提示**）

#### **Using index**
- 使用覆盖索引，无需回表查询
- **性能最佳情况之一**

#### **Using where**
- 在存储引擎检索行后，server层进行过滤

#### **Using temporary**
- 使用临时表保存中间结果
- **需要优化**，常见于GROUP BY、ORDER BY

#### **Using filesort**
- 使用外部排序，无法利用索引排序
- **需要优化**，考虑添加合适的索引

#### **Using join buffer**
- 使用连接缓冲区
- 常见于关联字段没有索引的情况

#### **Impossible WHERE**
- WHERE条件永远为false
```sql
EXPLAIN SELECT * FROM users WHERE 1=0;
```

#### **Select tables optimized away**
- 使用聚合函数访问索引
```sql
EXPLAIN SELECT MIN(id) FROM users;
```

## 三、EXPLAIN实际使用示例

### 示例1：简单查询分析
```sql
EXPLAIN SELECT * FROM orders 
WHERE user_id = 100 
AND status = 'completed'
ORDER BY created_at DESC;
```

### 示例2：关联查询分析
```sql
EXPLAIN SELECT u.name, o.order_no 
FROM users u
JOIN orders o ON u.id = o.user_id
WHERE u.city = 'Beijing'
ORDER BY o.created_at;
```

### 示例3：子查询分析
```sql
EXPLAIN SELECT * FROM products
WHERE category_id IN (
    SELECT id FROM categories WHERE parent_id = 1
);
```

## 四、EXPLAIN最佳实践

### 1. **分析步骤**
```
1. 查看type字段，确保不是ALL
2. 检查key字段，确保使用了合适的索引
3. 查看rows字段，预估扫描行数是否过大
4. 分析Extra字段，避免Using temporary和Using filesort
5. 检查key_len，确认索引使用效率
```

### 2. **常见优化场景**

#### 场景1：全表扫描优化
```sql
-- 优化前：type=ALL
EXPLAIN SELECT * FROM users WHERE phone = '13800138000';

-- 优化后：添加索引
ALTER TABLE users ADD INDEX idx_phone(phone);
```

#### 场景2：排序优化
```sql
-- 优化前：Extra中出现Using filesort
EXPLAIN SELECT * FROM orders ORDER BY user_id, created_at;

-- 优化后：添加复合索引
ALTER TABLE orders ADD INDEX idx_user_created(user_id, created_at);
```

#### 场景3：覆盖索引优化
```sql
-- 优化前：需要回表查询
EXPLAIN SELECT id, name FROM users WHERE age > 25;

-- 优化后：使用覆盖索引
ALTER TABLE users ADD INDEX idx_age_name(age, name);
```

### 3. **EXPLAIN格式扩展**

#### JSON格式（更详细的信息）
```sql
EXPLAIN FORMAT=JSON SELECT * FROM users WHERE age > 25;
-- 输出包含成本估算、优化器决策等详细信息
```

#### 传统格式对比
```sql
EXPLAIN SELECT * FROM users WHERE age > 25\G
-- 使用\G垂直显示结果，便于阅读
```

## 五、总结

### 关键指标优先级：
1. **type**：确保不是ALL，至少达到range级别
2. **key**：确认使用了合适的索引
3. **rows**：扫描行数尽量少
4. **Extra**：避免出现Using temporary和Using filesort

### 性能优化建议：
1. 为WHERE、ORDER BY、GROUP BY、JOIN条件创建合适索引
2. 使用覆盖索引减少回表查询
3. 避免在WHERE条件中对字段进行函数操作
4. 合理设计复合索引，注意字段顺序
5. 定期使用EXPLAIN分析慢查询

通过深入理解EXPLAIN各字段含义，可以准确诊断SQL性能问题，制定有效的优化策略，提升数据库查询效率。