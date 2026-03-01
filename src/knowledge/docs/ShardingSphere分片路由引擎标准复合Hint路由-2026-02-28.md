好的，遵照您的要求，我为您生成一份关于 ShardingSphere 分片路由引擎的详细技术文档。

---

# ShardingSphere 分片路由引擎技术文档
**文档主题：** 标准路由、复合路由与 Hint 路由详解  
**版本：** 1.0  
**目标读者：** 中高级后端开发工程师、架构师

---

## 1. 概述

Apache ShardingSphere 是一个开源的分布式数据库生态系统，其核心功能之一是 **数据分片**。分片路由引擎是数据分片模块的大脑，它负责解析用户 SQL，并根据配置的分片规则，将逻辑 SQL 精准路由到对应的物理数据库和数据表节点上。

**核心目标**：实现“在正确的时间，将正确的数据操作，发送到正确的数据库和表”。

## 2. 路由引擎在架构中的位置

一个典型的 ShardingSphere 数据分片请求处理流程如下：

```
Client Request -> SQL Parser (解析为AST) -> Query Optimizer (优化) -> **Router Engine (路由)** -> SQL Rewriter (SQL重写) -> SQL Executor (执行) -> Result Merger (结果合并) -> Response to Client
```

**路由引擎** 在解析和优化之后介入，其输入是带有分片上下文信息的逻辑 SQL，输出是一个或多个**路由结果**，每个结果都指向一个明确的数据源和真实表名。

## 3. 核心分片路由类型详解

ShardingSphere 主要提供了三种分片路由方式，以适应不同的业务场景。

### 3.1. 标准路由 (Standard Routing)

**定义**： 最常用、最符合直觉的路由方式。路由引擎根据 SQL 语句中 `WHERE` 条件包含的 **分片键（Sharding Key）** 的值，通过配置的 **分片算法（Sharding Algorithm）** 直接计算出目标数据源和表。

**工作原理**：
1.  SQL 解析器提取 SQL 中的条件表达式。
2.  路由引擎识别出条件中包含的分片键（例如 `user_id`）。
3.  从条件中获取分片键的值（例如 `user_id = 123`）。
4.  将分片键的值输入分片算法（例如 `user_id % 4`）。
5.  根据算法结果，路由到对应的具体数据节点（例如 `ds_1.t_user_3`）。

**典型场景**：
*   **等值查询**：`SELECT * FROM t_order WHERE order_id = 1001`
*   **范围查询**：`SELECT * FROM t_order WHERE order_id BETWEEN 1001 AND 2000` （可能产生多路由结果）
*   **IN 查询**：`SELECT * FROM t_order WHERE user_id IN (1, 3, 5)` （可能产生多路由结果）

**配置文件示例 (YAML)**:
```yaml
rules:
- !SHARDING
  tables:
    t_order:
      actualDataNodes: ds_${0..1}.t_order_${0..1} # 库和表都分片
      databaseStrategy:
        standard:
          shardingColumn: user_id
          shardingAlgorithmName: database_inline
      tableStrategy:
        standard:
          shardingColumn: order_id
          shardingAlgorithmName: table_inline

  shardingAlgorithms:
    database_inline:
      type: INLINE
      props:
        algorithm-expression: ds_${user_id % 2}
    table_inline:
      type: INLINE
      props:
        algorithm-expression: t_order_${order_id % 2}
```
*执行 `SELECT * FROM t_order WHERE user_id = 25 AND order_id = 1001`，引擎将计算：*
*   *库：`ds_${25 % 2}` => `ds_1`*
*   *表：`t_order_${1001 % 2}` => `t_order_1`*
*   *最终路由至：`ds_1.t_order_1`*

### 3.2. 复合路由 (Complex Routing)

**定义**： 当 SQL 条件中同时包含 **多个分片键**，并且这些分片键通过 `AND` 或 `OR` 进行组合时，触发的路由方式。它需要处理多分片键条件下的路由逻辑。

**工作原理**：
1.  引擎解析出多个分片键及其条件和关系（`AND`/`OR`）。
2.  对每个分片键条件，独立计算其可能的路由结果集合。
3.  根据逻辑运算符（`AND`/`OR`）对这些集合进行**交集**或**并集**运算。
4.  得到最终的目标数据节点集合。

**典型场景**：
*   **多分片键 AND 条件**：
    ```sql
    SELECT * FROM t_order 
    WHERE user_id = 123 AND order_id = 1001 AND status = 'ACTIVE';
    ```
    *如果 `user_id` 和 `order_id` 都是分片键，则需同时满足两者的算法，结果通常是单个节点（交集）。*
*   **多分片键 OR 条件**：
    ```sql
    SELECT * FROM t_order 
    WHERE user_id = 123 OR order_id = 1001;
    ```
    *这会分别计算两个条件可能路由的所有节点，然后取并集，可能导致全库表路由，性能最差。*

**配置说明**： 配置方式与标准路由类似，但在定义分片策略时，可以指定多个 `shardingColumn`。
```yaml
tableStrategy:
  complex:
    shardingColumns: user_id, order_type # 复合分片键
    shardingAlgorithmName: complex_algo

shardingAlgorithms:
  complex_algo:
    type: CLASS_BASED
    props:
      strategy: complex
      algorithmClassName: com.example.UserOrderComplexAlgorithm
```

### 3.3. Hint 路由 (Hint Routing)

**定义**： 一种 **强制路由** 机制。它允许开发者通过编程方式（**Hint**），直接指定 SQL 应该被执行到哪个数据源或表，**完全绕过 SQL 解析和分片算法计算**。

**核心价值**： 解决标准路由无法覆盖的特殊场景，例如：
1.  数据分片键不在 SQL 条件中。
2.  执行一些数据库管理操作（如 `CREATE TABLE`， `SELECT MAX(id)`）。
3.  实现基于业务逻辑的定制化路由（如根据租户上下文路由）。
4.  作为故障排查和手动数据处理的工具。

**实现方式**：
ShardingSphere 提供了 `HintManager` API 来添加 Hint 信息。

**Java 代码示例**:
```java
// 在执行 SQL 前，通过 HintManager 设置分片值
try (HintManager hintManager = HintManager.getInstance()) {
    // 1. 设置数据源分片值（库级别路由）
    // hintManager.setDataSourceName("ds_0");
    
    // 2. 为特定表添加分片值（表级别路由，更常用）
    hintManager.addTableShardingValue("t_order", 123L); // 分片值为123

    // 3. 执行SQL（此SQL本身可以不含分片键条件）
    String sql = "SELECT * FROM t_order WHERE status = 'PENDING'";
    // 该 SQL 将被强制路由到 t_order 分片键值为 123 对应的物理表
    executeSql(sql);
} // HintManager 会自动关闭并清理线程上下文中的Hint
```

**配置说明**： Hint 路由需要在配置中启用对应的 Hint 分片策略。
```yaml
tableStrategy:
  hint:
    shardingAlgorithmName: hint_algo

shardingAlgorithms:
  hint_algo:
    type: HINT_INLINE # 使用Hint内联算法，实际上算法会直接读取 HintManager 设置的值
```

## 4. 三种路由对比与选择指南

| 特性 | 标准路由 | 复合路由 | Hint 路由 |
| :--- | :--- | :--- | :--- |
| **驱动力** | SQL 中的分片键条件 | SQL 中的多分片键条件 | 外部编程 Hint |
| **性能** | 高（直接计算） | 中（需集合运算） | 最高（无计算，直接指定） |
| **灵活性** | 低（依赖SQL结构） | 中 | **极高**（完全由代码控制） |
| **业务侵入性** | 无 | 无 | **有**（需修改代码） |
| **适用场景** | 日常CRUD，分片键明确 | 多维度分片查询 | 特殊操作、运维、复杂业务路由 |
| **SQL要求** | 必须包含分片键条件 | 必须包含复合分片键条件 | **无要求** |

**选择建议**：
1.  **优先使用标准路由**：满足绝大多数基于分片键查询的场景。
2.  **谨慎设计复合路由**：避免使用 `OR` 连接不同分片键，可能导致全库表扫描。
3.  **保守使用 Hint 路由**：将其作为“逃生通道”或“特殊工具”，而非常规方案，因为它破坏了分片逻辑对应用的透明性。

## 5. 总结

ShardingSphere 的分片路由引擎通过 **标准路由、复合路由、Hint 路由** 三种策略，构建了一个从自动到手动、从通用到特殊的完整路由解决方案。理解它们的工作原理和适用场景，是设计高效、稳定分片数据库系统的关键。在实际应用中，应坚持以**标准路由**为主，**复合路由**为辅，**Hint 路由**为补充的原则进行架构设计。