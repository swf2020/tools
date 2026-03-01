好的，这是一份根据您的要求生成的关于 MyBatis Executor 类型的技术文档。

---

# **MyBatis Executor 执行器类型详解 (Simple, Reuse, Batch)**

## **1. 概述**

在 MyBatis 的核心架构中，`Executor` 是一个至关重要的组件，它是所有数据库操作的真正调度者，负责 SQL 语句的执行、缓存维护以及事务管理。`Executor` 的直接使用者是 `SqlSession`。

MyBatis 提供了三种核心的 `Executor` 实现，它们在 **语句处理（Statement）的复用方式** 和 **执行模式** 上有所不同，从而适用于不同的性能场景。在创建 `SqlSession` 时，可以通过配置指定使用哪种执行器。

## **2. 执行器类型详解**

### **2.1 SimpleExecutor（简单执行器）**

*   **工作原理**：**每次执行一个 `update` 或 `select` 操作，都会创建一个全新的 `Statement` 对象，使用完毕后立即关闭该对象（或将其归还给连接池）。**
*   **核心特点**：
    *   **无复用**：不重用任何 `Statement`。
    *   **行为简单**：逻辑清晰，是默认的执行器（除非显式配置为其他类型）。
    *   **潜在开销**：在高频次数据库调用时，频繁创建和销毁 `PreparedStatement` 会带来一定的性能开销。
*   **适用场景**：
    *   绝大多数常规场景。对于单个请求或低并发场景，其开销可以忽略不计。
    *   作为理解其他执行器工作原理的基础。
*   **代码/逻辑模拟**：
    ```java
    for (int i = 0; i < 3; i++) {
        // 1. 每次循环都创建一个新的 PreparedStatement
        PreparedStatement stmt = connection.prepareStatement(“SELECT * FROM user WHERE id = ?“);
        stmt.setInt(1, i);
        ResultSet rs = stmt.executeQuery();
        // ... 处理结果
        // 2. 立即关闭
        stmt.close();
    }
    ```

### **2.2 ReuseExecutor（重用执行器）**

*   **工作原理**：**在同一个 `SqlSession` 会话生命周期内，对相同的 SQL 语句（完全相同的字符串）会复用其创建的 `PreparedStatement` 对象。** 它内部维护了一个 `Map<String, Statement>` 来缓存 SQL 语句和对应的 `Statement`。
*   **核心特点**：
    *   **语句级复用**：避免了相同 SQL 的重复编译（JDBC 驱动级别），提升了性能。
    *   **会话范围**：缓存仅在当前 `SqlSession` 内有效，`SqlSession` 关闭后，所有缓存的 `Statement` 将被关闭。
    *   **依赖SQL一致性**：SQL 字符串必须**完全一致**（包括空格、换行）才能被复用。
*   **适用场景**：
    *   在一个会话中需要反复执行**完全相同** SQL 语句的场景。
    *   例如，循环中调用同一个查询方法。
*   **代码/逻辑模拟**：
    ```java
    Map<String， PreparedStatement> statementMap = new HashMap<>();

    String sql = “SELECT * FROM user WHERE id = ?“;
    for (int i = 0; i < 3; i++) {
        // 1. 检查缓存中是否有该SQL的Statement
        PreparedStatement stmt = statementMap.get(sql);
        if (stmt == null) {
            // 2. 没有则创建并缓存
            stmt = connection.prepareStatement(sql);
            statementMap.put(sql, stmt);
        }
        // 3. 复用已缓存的Statement
        stmt.setInt(1, i);
        ResultSet rs = stmt.executeQuery();
        // ... 处理结果
        // 注意：此处不会关闭Statement
    }
    // 4. 会话结束时，统一关闭所有缓存的Statement
    for (PreparedStatement stmt : statementMap.values()) {
        stmt.close();
    }
    ```

### **2.3 BatchExecutor（批处理执行器）**

*   **工作原理**：**专门针对 `UPDATE`， `INSERT`， `DELETE` 操作进行优化。它将所有修改操作（`addBatch`）积攒起来，然后在合适的时机一次性发送到数据库执行（`executeBatch`），从而大幅减少网络交互次数。**
*   **核心特点**：
    *   **批量执行**：核心优势，对大量写操作性能提升显著。
    *   **仅针对更新**：`select` 操作不会被批量处理，遇到 `select` 时会先触发执行之前积攒的所有批处理语句。
    *   **手动提交**：默认情况下，批处理需要手动调用 `SqlSession#flushStatements()` 来触发执行。事务提交、回滚或执行查询时也会自动触发刷新。
    *   **潜在内存消耗**：如果批处理队列过大，可能会占用较多内存。
*   **适用场景**：
    *   需要进行大量数据插入、更新或删除的作业（ETL、数据迁移、批量初始化等）。
*   **注意事项与代码模拟**：
    ```java
    // 模拟 BatchExecutor 对同一SQL的批量处理
    String sql = “INSERT INTO user (name) VALUES (?)“;
    PreparedStatement stmt = connection.prepareStatement(sql);

    for (int i = 0; i < 1000; i++) {
        stmt.setString(1， “User“ + i);
        stmt.addBatch(); // 1. 添加到批处理，而非立即执行

        if (i % 500 == 0) { // 2. 达到一定批次后，手动刷新执行
            int[] counts = stmt.executeBatch();
            stmt.clearBatch();
        }
    }
    // 3. 执行最后一批
    int[] counts = stmt.executeBatch();
    stmt.clearBatch();
    stmt.close();
    ```

## **3. 对比总结**

| 特性 | **SimpleExecutor** | **ReuseExecutor** | **BatchExecutor** |
| :--- | :--- | :--- | :--- |
| **Statement 处理** | 每次创建，用完即关 | 相同SQL在会话内复用 | 对更新操作进行批量添加，统一执行 |
| **优点** | 实现简单，无状态 | 避免相同SQL重复编译 | 大幅提升批量写操作的性能 |
| **缺点** | 频繁创建/销毁开销 | 需SQL完全一致，缓存占用 | 逻辑稍复杂，需手动控制刷新，可能占用内存 |
| **默认选择** | **是** | 否 | 否 |
| **适用操作** | 所有操作 | 所有操作 | **主要针对 Update/Insert/Delete** |
| **性能关键** | SQL编译开销 | SQL复用率 | 批量大小 |

## **4. 配置与使用**

### **4.1 全局配置**
在 MyBatis 核心配置文件 `mybatis-config.xml` 的 `settings` 中设置默认执行器。
```xml
<configuration>
    <settings>
        <!-- 可选值: SIMPLE, REUSE, BATCH -->
        <setting name=“defaultExecutorType“ value=“BATCH“/>
    </settings>
</configuration>
```

### **4.2 局部配置（覆盖全局）**
在创建 `SqlSession` 时，通过 `SqlSessionFactory.openSession(ExecutorType execType)` 方法指定本次会话使用的执行器。
```java
try (SqlSession session = sqlSessionFactory.openSession(ExecutorType.BATCH)) {
    UserMapper mapper = session.getMapper(UserMapper.class);
    for (User user : userList) {
        mapper.insert(user);
    }
    // 在BatchExecutor中，必须手动刷新或提交事务来执行批处理
    session.flushStatements();
    session.commit();
}
```

### **4.3 与 Spring 集成时的注意事项**
当 MyBatis 与 Spring 集成时（如使用 `mybatis-spring`），`SqlSession` 的生命周期由 Spring 管理。通常每个事务或方法调用会使用一个 `SqlSession`。此时：
*   在 Spring 管理的服务方法中，默认会为每个方法创建一个新的 `SqlSession`，这会使 `ReuseExecutor` 的会话级缓存意义不大。
*   `BatchExecutor` 需要确保一批操作在同一个事务和同一个 `SqlSession` 中完成。可以通过将批量操作放入一个 `@Transactional` 注解的方法中来实现，但需注意事务的边界和刷新时机。

---

**总结**：选择合适的 `Executor` 是 MyBatis 性能调优的一个有效手段。理解其原理后，可以根据具体的业务场景（是频繁的相同查询，还是大量的数据写入）来做出最佳选择。大多数情况下，默认的 `SimpleExecutor` 已足够高效。