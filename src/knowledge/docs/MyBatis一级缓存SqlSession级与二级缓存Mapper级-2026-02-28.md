好的，遵照您的要求，我将为您生成一份关于 MyBatis 一级缓存和二级缓存的详细技术文档。

---

## **MyBatis 缓存机制详解：一级缓存与二级缓存**

### **1. 概述**

MyBatis 内置了一个强大的缓存机制，旨在减少数据库的查询次数，提高应用性能。其缓存分为两层：
- **一级缓存 (Local Cache)**：**SqlSession 级别**的缓存，默认开启且无法关闭。
- **二级缓存 (Global Cache)**：**Mapper (Namespace) 级别**的缓存，需要手动配置开启。

理解这两级缓存的区别、生命周期和交互方式，对于编写高性能、数据一致的 MyBatis 应用至关重要。

### **2. 一级缓存 (SqlSession 级缓存)**

#### **2.1 核心特性**
*   **作用域**：同一个 `SqlSession` 对象。
*   **生命周期**：与 `SqlSession` 的生命周期一致。`SqlSession` 关闭或清空时，其对应的一级缓存就会被清除。
*   **默认状态**：**默认开启**，无需任何配置。
*   **实现机制**：基于 `PerpetualCache`（一个简单的 `HashMap`）实现。

#### **2.2 工作流程**
1.  在同一个 `SqlSession` 中执行查询。
2.  首次查询时，MyBatis 会将查询结果对象**存储到该 SqlSession 的一级缓存中**，并缓存其 `SQL语句 + 参数 + 环境` 作为键。
3.  再次执行**完全相同**的 SQL 语句和参数时，MyBatis 会**优先从一级缓存中获取**，直接返回缓存对象，不再访问数据库。
4.  一旦 `SqlSession` 执行了 **INSERT、UPDATE、DELETE** 操作，或者显式调用 `sqlSession.clearCache()`，该 `SqlSession` 中的所有一级缓存会被**立即清空**，以保证数据一致性。

#### **2.3 代码示例**
```java
try (SqlSession sqlSession = sqlSessionFactory.openSession()) {
    UserMapper mapper = sqlSession.getMapper(UserMapper.class);
    // 第一次查询，访问数据库，并将结果存入一级缓存
    User user1 = mapper.selectById(1L);
    // 第二次查询，SQL和参数完全相同，直接从一级缓存返回，不访问数据库
    User user2 = mapper.selectById(1L);
    System.out.println(user1 == user2); // 输出：true，是同一个对象引用

    // 执行更新操作
    mapper.updateName(1L, "NewName");
    // 更新后，一级缓存被清空
    // 第三次查询，缓存已无，再次访问数据库
    User user3 = mapper.selectById(1L);
    System.out.println(user1 == user3); // 输出：false
}
```

#### **2.4 注意事项**
*   **对象引用相同**：一级缓存返回的是**同一个 Java 对象引用**。修改 `user1` 的属性会影响 `user2`。
*   **跨 SqlSession 无效**：不同的 `SqlSession` 有各自独立的一级缓存，互不影响。
*   **事务隔离**：一级缓存是会话级别的，不解决跨会话的脏读等问题。

### **3. 二级缓存 (Mapper 级缓存)**

#### **3.1 核心特性**
*   **作用域**：同一个 **Mapper 接口的命名空间 (Namespace)**。跨 `SqlSession` 共享。
*   **生命周期**：与应用生命周期基本一致（除非被显式清除或配置了过期策略）。
*   **默认状态**：**默认关闭**，需要在配置文件中显式开启。
*   **实现机制**：同样基于 `PerpetualCache`，但通过 `TransactionalCacheManager` 进行装饰和管理，提供了事务性的提交/回滚行为。

#### **3.2 配置与开启步骤**
1.  **全局开关 (可选)**：在 `mybatis-config.xml` 中，确保 `<setting name="cacheEnabled" value="true"/>`（默认即为 `true`）。
2.  **Mapper XML 中声明**：在需要启用二级缓存的 Mapper XML 文件中，添加 `<cache/>` 标签。
    ```xml
    <!-- UserMapper.xml -->
    <mapper namespace="com.example.mapper.UserMapper">
        <!-- 启用二级缓存 -->
        <cache/>
        <select id="selectById" resultType="User" ...>
            ...
        </select>
    </mapper>
    ```
3.  **POJO 序列化**：缓存的对象必须实现 `Serializable` 接口，因为二级缓存可能使用序列化方式存储（取决于配置的缓存装饰器）。

#### **3.3 工作流程**
1.  一个 `SqlSession` 查询数据，数据被存入其自身的一级缓存。
2.  当该 `SqlSession` **关闭 (`close()`)** 或 **提交 (`commit()`)** 时，其一级缓存中的数据才会被**转存**到对应的二级缓存区域（以 Mapper Namespace 划分）。
3.  另一个 `SqlSession` 执行相同的查询时：
    *   首先检查自己的一级缓存。
    *   一级缓存未命中，则查询**二级缓存**。
    *   二级缓存命中，则返回数据（注意：返回的是**反序列化后的新对象副本**，非同一引用）。
    *   二级缓存也未命中，则访问数据库，并将结果存入自己的一级缓存，在会话关闭/提交时再转存到二级缓存。
4.  任何一个 `SqlSession` 执行了 **INSERT、UPDATE、DELETE** 操作并成功提交后，MyBatis 会**清空该 Mapper Namespace 下的整个二级缓存**，以确保数据一致性。

#### **3.4 缓存配置详解**
`<cache/>` 标签支持多种属性进行精细控制：
```xml
<cache
  eviction="LRU"               <!-- 清除策略：LRU(默认)/FIFO/SOFT/WEAK -->
  flushInterval="60000"        <!-- 刷新间隔（毫秒），不设置则不清空 -->
  size="1024"                  <!-- 最多缓存对象个数 -->
  readOnly="true"              <!-- 是否只读。true:返回共享实例(不安全但快)；false:返回拷贝(安全) -->
/>
```

#### **3.5 注意事项**
*   **事务性**：二级缓存的生效与 `SqlSession` 的提交 (`commit`) 或关闭紧密相关。未提交的事务，其数据不会进入二级缓存。
*   **跨 Mapper 共享**：通过 `<cache-ref namespace="..."/>` 可以让多个 Mapper 共享同一个二级缓存，但会增加维护复杂度，一般不推荐。
*   **数据一致性风险**：在分布式或多线程环境下，二级缓存可能带来脏读问题，需要谨慎使用。
*   **查询结果映射**：如果查询使用了 `resultMap` 进行复杂的嵌套映射，确保所有嵌套的 Java 对象也都是可序列化的。

### **4. 一级缓存与二级缓存对比总结**

| 特性 | 一级缓存 | 二级缓存 |
| :--- | :--- | :--- |
| **作用域** | `SqlSession` 内部 | `Mapper (Namespace)` 级别，跨 `SqlSession` |
| **生命周期** | 随 `SqlSession` 创建而创建，关闭而销毁 | 随整个应用生命周期，除非被显式清除或配置过期 |
| **默认状态** | **开启**，且无法关闭 | **关闭**，需要手动配置开启 |
| **数据共享** | 不能在多个 `SqlSession` 间共享 | 可以被多个 `SqlSession` 共享 |
| **清空时机** | `SqlSession` 执行更新操作或调用 `clearCache()` | 执行同 Namespace 的更新操作并提交后，或配置的 `flushInterval` 到期 |
| **对象返回** | 同一个对象的**相同引用** | 默认返回反序列化的**新对象副本**（除非 `readOnly=true`） |
| **使用场景** | 单个会话内重复查询 | 跨会话的、读多写少的共享数据查询 |

### **5. 最佳实践与建议**

1.  **一级缓存**：无需特别管理，理解其存在即可。在需要获取最新数据的场景，可以通过 `sqlSession.clearCache()` 或在查询语句上设置 `flushCache="true"` 来跳过缓存。
2.  **二级缓存**：
    *   **谨慎开启**：对于**更新频繁、对数据实时性要求高**的数据，不宜开启二级缓存。
    *   **适合场景**：**静态数据、配置表、极少被修改的历史数据**等读多写少的场景。
    *   **明确配置**：根据数据特性配置合理的 `eviction`、`flushInterval` 和 `size` 策略。
    *   **考虑序列化**：确认缓存对象及其关联对象均已实现 `Serializable`。
    *   **分布式环境**：在微服务或分布式部署中，内置的二级缓存（单机）通常会导致数据不一致，**建议使用集中式缓存（如 Redis、Ehcache）替代 MyBatis 内置的二级缓存**，并通过 MyBatis 提供的 `Cache` 接口进行集成。

通过合理利用和配置 MyBatis 的这两级缓存，可以在保证数据一致性的前提下，显著提升数据库访问性能。