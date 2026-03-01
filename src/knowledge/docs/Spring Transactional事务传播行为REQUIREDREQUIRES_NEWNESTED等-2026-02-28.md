好的，遵照您的指示，为您生成一份关于 Spring `@Transactional` 事务传播行为的技术文档。

---

# Spring `@Transactional` 事务传播行为详解

## 1. 概述

在基于 Spring 框架的应用程序中，声明式事务管理是核心功能之一，主要通过 `@Transactional` 注解实现。当事务方法相互调用时，**事务传播行为（Propagation Behavior）** 定义了这些事务应该如何相互作用，它是处理复杂业务逻辑中事务边界的关键。

Spring 参考了 EJB 的传播行为模型，在 `org.springframework.transaction.annotation.Propagation` 枚举中定义了 7 种传播行为。本文将深入探讨其中最常用、最核心的三种：**REQUIRED、REQUIRES_NEW 和 NESTED**，并简要对比其他类型。

## 2. 核心概念回顾

*   **事务管理器（PlatformTransactionManager）**：Spring 事务抽象的核心接口。
*   **`@Transactional`**：可以标注在类或方法上，用于声明事务属性，包括 `propagation`（传播行为）、`isolation`（隔离级别）、`rollbackFor`（回滚条件）等。
*   **逻辑事务与物理事务**：
    *   **逻辑事务**：由 `@Transactional` 注解声明的一个事务范围。
    *   **物理事务**：底层资源管理器（如数据库）实际开启和提交/回滚的事务。
    *   多个逻辑事务可以归属于同一个物理事务（如 `REQUIRED` 的加入），也可以各自独立（如 `REQUIRES_NEW`）。

## 3. 常用传播行为详解

### 3.1 REQUIRED（默认值）

*   **行为**：如果当前存在一个事务，则**加入**该事务；如果当前没有事务，则**新建**一个事务。
*   **逻辑图示**：
    ```
    方法A（REQUIRED） -> 开启事务T1
        -> 调用方法B（REQUIRED） -> 加入事务T1
    -> 方法A结束 -> 提交/回滚事务T1
    ```
*   **适用场景**：**最常用的设置**。适用于大多数业务方法，确保它们在同一事务中运行，保证数据一致性。例如，用户下单操作，需要调用创建订单、扣减库存、更新账户等多个方法，这些方法都应使用 `REQUIRED`，形成一个原子操作。
*   **代码示例**：
    ```java
    @Service
    public class OrderService {
        @Transactional(propagation = Propagation.REQUIRED) // 默认即 REQUIRED
        public void placeOrder(Order order) {
            orderDao.save(order);
            inventoryService.deductStock(order.getItems()); // 调用另一个 REQUIRED 方法
            accountService.updateBalance(order.getUserId(), order.getAmount());
        }
    }

    @Service
    public class InventoryService {
        @Transactional(propagation = Propagation.REQUIRED)
        public void deductStock(List<Item> items) {
            // ... 扣减库存逻辑
        }
    }
    ```

### 3.2 REQUIRES_NEW

*   **行为**：**无论当前是否存在事务**，都会**新建**一个独立的事务。如果当前存在事务，则将当前事务**挂起（suspend）**。
    *   新事务拥有独立的锁、隔离级别和生命周期。
    *   新事务提交或回滚后，原来的事务才恢复执行。
*   **逻辑图示**：
    ```
    方法A（REQUIRED） -> 开启事务T1
        -> 调用方法B（REQUIRES_NEW） -> 挂起T1，开启新事务T2 -> T2提交/回滚 -> 恢复T1
    -> 方法A结束 -> 提交/回滚事务T1
    ```
*   **适用场景**：
    1.  **需要独立提交的逻辑**：如日志记录、审计操作。即使主业务失败，日志仍需成功写入。
    2.  **避免大事务锁定资源**：将一个耗时且非核心的操作（如生成报告、发送通知）放入独立事务，防止其长时间占用主事务锁，影响并发。
*   **注意事项**：
    *   由于开启新连接和同步点管理，性能开销比 `REQUIRED` 大。
    *   外层事务回滚**不会影响**内层 `REQUIRES_NEW` 事务的提交。
    *   内层 `REQUIRES_NEW` 事务回滚，默认情况下，**不会导致**外层事务回滚（除非异常传播到外层）。但外层事务可以捕获内层抛出的异常，自行决定处理方式。
*   **代码示例**：
    ```java
    @Service
    public class OrderService {
        @Transactional(propagation = Propagation.REQUIRED)
        public void placeOrder(Order order) {
            orderDao.save(order);
            try {
                auditLogService.logOperation("CREATE_ORDER", order.getId()); // REQUIRES_NEW
            } catch (Exception e) {
                // 即使日志失败，订单事务仍可继续
            }
            // ... 其他业务
        }
    }

    @Service
    public class AuditLogService {
        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void logOperation(String action, Long targetId) {
            // ... 写入审计日志
        }
    }
    ```

### 3.3 NESTED

*   **行为**：如果当前存在事务，则在当前事务的一个**嵌套事务（保存点，Savepoint）** 中执行。如果当前没有事务，则行为同 `REQUIRED`（新建一个事务）。
    *   嵌套事务是外部事务的一部分，**只有外部事务可以提交**。
    *   嵌套事务可以独立地回滚到其保存点，而不会影响外部事务。但外部事务回滚会连带导致所有嵌套事务回滚。
*   **逻辑图示**：
    ```
    方法A（REQUIRED） -> 开启事务T1
        -> 调用方法B（NESTED） -> 在T1中设置保存点Sp1
            -> B成功 -> 释放Sp1
            -> B失败 -> 回滚到Sp1，T1继续
    -> 方法A结束 -> 提交/回滚事务T1
    ```
*   **适用场景**：
    1.  **可部分回滚的业务流程**：如一个订单处理流程中，可以先保存订单主信息（成功），再处理每个子项（某个子项失败时，仅回滚该子项操作，而不回滚已保存的订单主信息）。
    2.  它是 `REQUIRED` 和 `REQUIRES_NEW` 的折中方案，允许细粒度的回滚控制，同时大部分工作仍在同一物理事务中，避免了 `REQUIRES_NEW` 的额外连接开销。
*   **实现限制**：
    *   **需要 JDBC 3.0+ 驱动** 和**支持保存点的数据库**（如 MySQL with InnoDB, PostgreSQL, Oracle 等）。
    *   **不支持 JTA（全局事务）**。通常与 `DataSourceTransactionManager` 一起使用。
    *   某些 JPA 提供商的实现可能不完全支持。
*   **代码示例**：
    ```java
    @Service
    public class OrderService {
        @Transactional(propagation = Propagation.REQUIRED)
        public void processComplexOrder(ComplexOrder order) {
            // 步骤1：保存主订单（一旦保存，即使后面失败，也已持久化）
            orderDao.saveMaster(order);

            // 步骤2：处理每个订单项，每个都是嵌套事务
            for (OrderItem item : order.getItems()) {
                try {
                    itemService.processItem(item); // NESTED 传播
                } catch (BusinessException e) {
                    // 某个子项处理失败，仅该项回滚，记录日志，继续处理其他项
                    log.error("Process item failed: {}", item.getId(), e);
                }
            }
            // 所有项处理完毕，外部事务最终提交
        }
    }

    @Service
    public class ItemService {
        @Transactional(propagation = Propagation.NESTED)
        public void processItem(OrderItem item) {
            // ... 复杂的子项处理逻辑，可能抛出 BusinessException
        }
    }
    ```

## 4. 其他传播行为简介

*   **SUPPORTS**：支持当前事务，如果不存在，则以非事务方式执行。
*   **MANDATORY**：强制要求当前存在事务，否则抛出异常。
*   **NOT_SUPPORTED**：以非事务方式执行，如果当前存在事务，则将其挂起。
*   **NEVER**：以非事务方式执行，如果当前存在事务，则抛出异常。

## 5. 对比总结

| 传播行为 | 当前无事务 | 当前有事务 | 回滚影响 | 性能/资源 | 典型场景 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **REQUIRED** | 新建事务 | **加入**现有事务 | 一荣俱荣，一损俱损 | 最优 | 通用业务方法，数据一致性要求高的操作链 |
| **REQUIRES_NEW** | 新建事务 | **挂起**现有，**新建**独立事务 | **完全独立**，互不影响提交 | 开销较大（新连接） | 独立日志、审计；避免大事务锁资源 |
| **NESTED** | 新建事务 | 在现有事务中创建**嵌套事务（保存点）** | 内层可单独回滚；外层回滚导致全部回滚 | 开销小（使用保存点） | 可部分回滚的复杂流程（需数据库支持） |

## 6. 注意事项与最佳实践

1.  **代理机制**：`@Transactional` 基于 AOP 代理，**自调用（同一个类中一个非事务方法调用事务方法）会导致事务失效**。可通过注入自身代理或使用 `AspectJ` 模式解决。
2.  **异常回滚**：默认只在抛出 `RuntimeException` 和 `Error` 时回滚。检查异常（Checked Exception）不会导致回滚，需通过 `@Transactional(rollbackFor = Exception.class)` 指定。
3.  **方法可见性**：Spring AOP 代理下，`protected`, `package-visible`, `private` 方法上的 `@Transactional` 注解**会被忽略**。建议只用于 `public` 方法。
4.  **隔离级别交互**：传播行为与隔离级别共同作用。注意在 `REQUIRES_NEW` 中，新事务的隔离级别是独立的。
5.  **测试**：务必为复杂的事务交互编写集成测试，验证在各种成功和失败场景下，数据状态是否符合预期。

---

**结论**：正确理解并应用 `REQUIRED`, `REQUIRES_NEW`, `NESTED` 等事务传播行为，是设计健壮、高效且数据一致的 Spring 应用程序的基石。开发者应根据具体的业务需求、数据一致性要求和性能考量，审慎选择最合适的传播策略。