# MyBatis-Plus乐观锁插件技术文档

## 1. 概述

### 1.1 什么是乐观锁
乐观锁是一种并发控制机制，它假设数据在大多数情况下不会发生冲突，因此在访问数据时不会加锁，只在数据更新时检查版本信息。如果版本信息匹配，则更新成功；否则认为数据已被其他事务修改，更新失败。

### 1.2 MyBatis-Plus乐观锁插件
MyBatis-Plus通过`@Version`注解和乐观锁插件实现乐观锁功能，能够有效防止数据更新时的并发冲突。

## 2. 实现原理

### 2.1 核心机制
1. 在数据库表中增加版本号字段（通常命名为`version`）
2. 读取数据时获取当前版本号
3. 更新数据时，将版本号作为更新条件之一
4. 更新成功后，版本号自动递增

### 2.2 执行流程
```
读取数据 → 业务处理 → 更新时检查version → 更新成功则version+1 → 更新失败则抛出异常
```

## 3. 环境要求

- MyBatis-Plus 3.0+
- Spring Boot 2.x+（推荐）
- 支持的数据表（需包含版本字段）

## 4. 配置步骤

### 4.1 添加依赖
```xml
<!-- Maven -->
<dependency>
    <groupId>com.baomidou</groupId>
    <artifactId>mybatis-plus-boot-starter</artifactId>
    <version>最新版本</version>
</dependency>
```

### 4.2 数据库表设计
```sql
CREATE TABLE user (
    id BIGINT PRIMARY KEY COMMENT '主键',
    name VARCHAR(50) COMMENT '姓名',
    age INT COMMENT '年龄',
    version INT DEFAULT 0 COMMENT '版本号',
    deleted INT DEFAULT 0 COMMENT '逻辑删除标志'
);
```

### 4.3 配置乐观锁插件

#### 方式一：Spring Boot配置类
```java
@Configuration
@MapperScan("com.example.mapper")
public class MybatisPlusConfig {

    /**
     * 乐观锁插件配置
     */
    @Bean
    public MybatisPlusInterceptor mybatisPlusInterceptor() {
        MybatisPlusInterceptor interceptor = new MybatisPlusInterceptor();
        // 添加乐观锁插件
        interceptor.addInnerInterceptor(new OptimisticLockerInnerInterceptor());
        return interceptor;
    }
}
```

#### 方式二：XML配置
```xml
<bean id="sqlSessionFactory" class="com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean">
    <property name="configuration" ref="configuration"/>
    <property name="plugins">
        <array>
            <bean class="com.baomidou.mybatisplus.extension.plugins.inner.OptimisticLockerInnerInterceptor"/>
        </array>
    </property>
</bean>
```

## 5. 实体类配置

### 5.1 基础实体类
```java
@Data
@TableName("user")
public class User {
    
    @TableId(type = IdType.ASSIGN_ID)
    private Long id;
    
    private String name;
    
    private Integer age;
    
    @Version
    private Integer version;
    
    // 其他字段...
}
```

### 5.2 @Version注解说明

| 属性 | 说明 | 必填 | 默认值 |
|------|------|------|--------|
| - | 标记字段为版本字段 | 是 | - |

**注意：**
- 字段类型必须为`Integer`、`Long`、`Date`或`Timestamp`
- 支持的数据类型取决于数据库和字段类型
- 首次插入时，版本号默认为0

## 6. 使用方法

### 6.1 插入数据
```java
@Service
public class UserServiceImpl extends ServiceImpl<UserMapper, User> implements UserService {
    
    @Override
    public boolean addUser(User user) {
        // 插入时version会自动设置为0（或数据库默认值）
        return save(user);
    }
}
```

### 6.2 更新数据
```java
@Service
public class UserServiceImpl extends ServiceImpl<UserMapper, User> implements UserService {
    
    @Transactional(rollbackFor = Exception.class)
    @Override
    public boolean updateUser(User user) {
        // 1. 查询当前数据（获取当前version）
        User dbUser = getById(user.getId());
        
        // 2. 设置更新字段
        dbUser.setName(user.getName());
        dbUser.setAge(user.getAge());
        
        // 3. 执行更新（自动处理version）
        // SQL: UPDATE user SET name=?, age=?, version=? WHERE id=? AND version=?
        boolean success = updateById(dbUser);
        
        if (!success) {
            // 更新失败，可能被其他事务修改
            throw new OptimisticLockException("数据已被修改，请刷新后重试");
        }
        return true;
    }
}
```

### 6.3 批量更新
```java
@Transactional(rollbackFor = Exception.class)
public boolean batchUpdate(List<User> userList) {
    // 批量更新也会自动处理乐观锁
    return updateBatchById(userList);
}
```

## 7. 实际应用示例

### 7.1 完整Service示例
```java
@Service
@Slf4j
public class UserService {
    
    @Autowired
    private UserMapper userMapper;
    
    /**
     * 带重试机制的乐观锁更新
     */
    public boolean updateWithRetry(User user, int maxRetry) {
        for (int i = 0; i < maxRetry; i++) {
            try {
                User dbUser = userMapper.selectById(user.getId());
                if (dbUser == null) {
                    throw new RuntimeException("用户不存在");
                }
                
                // 业务逻辑处理
                dbUser.setName(user.getName());
                dbUser.setAge(user.getAge());
                
                int rows = userMapper.updateById(dbUser);
                if (rows > 0) {
                    log.info("更新成功，版本号：{} -> {}", 
                             dbUser.getVersion() - 1, dbUser.getVersion());
                    return true;
                }
                
                log.warn("乐观锁冲突，第{}次重试", i + 1);
                Thread.sleep(100); // 短暂等待后重试
                
            } catch (Exception e) {
                log.error("更新失败", e);
                throw new RuntimeException("更新失败");
            }
        }
        throw new RuntimeException("更新失败，超过最大重试次数");
    }
}
```

### 7.2 Controller层示例
```java
@RestController
@RequestMapping("/user")
public class UserController {
    
    @Autowired
    private UserService userService;
    
    @PutMapping("/update")
    public Result<?> updateUser(@RequestBody User user) {
        try {
            boolean success = userService.updateWithRetry(user, 3);
            return success ? Result.success("更新成功") : 
                           Result.fail("更新失败");
        } catch (OptimisticLockException e) {
            return Result.fail(ErrorCode.OPTIMISTIC_LOCK_ERROR, "数据冲突，请刷新后重试");
        }
    }
}
```

## 8. 注意事项

### 8.1 版本字段管理
- **不要手动修改version值**：让插件自动管理
- **初始值设置**：新插入数据时version默认为0
- **字段类型**：建议使用Integer或Long类型

### 8.2 事务管理
```java
// 建议在Service方法上添加事务注解
@Transactional(rollbackFor = Exception.class)
public void businessMethod() {
    // 业务逻辑
}
```

### 8.3 与其他插件兼容性
- 乐观锁插件与分页插件、动态表名插件等可以同时使用
- 插件执行顺序可能影响结果，需注意配置顺序

### 8.4 异常处理
```java
@ControllerAdvice
public class GlobalExceptionHandler {
    
    @ExceptionHandler(OptimisticLockException.class)
    @ResponseBody
    public Result<?> handleOptimisticLockException(OptimisticLockException e) {
        log.error("乐观锁异常", e);
        return Result.fail("数据版本冲突，操作失败");
    }
}
```

## 9. 性能优化建议

### 9.1 索引优化
```sql
-- 为版本字段和主键创建复合索引（如果经常作为查询条件）
CREATE INDEX idx_version ON user(id, version);
```

### 9.2 重试策略
```java
// 实现指数退避重试
public <T> T executeWithRetry(Supplier<T> supplier, int maxRetries) {
    int retries = 0;
    while (retries < maxRetries) {
        try {
            return supplier.get();
        } catch (OptimisticLockException e) {
            retries++;
            if (retries >= maxRetries) {
                throw e;
            }
            try {
                Thread.sleep((long) Math.pow(2, retries) * 100);
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
                throw new RuntimeException("重试被中断", ie);
            }
        }
    }
    throw new OptimisticLockException("超出最大重试次数");
}
```

## 10. 常见问题排查

### 10.1 更新无效问题
**问题**：更新时没有触发版本检查
**解决**：
1. 检查是否配置了乐观锁插件
2. 检查实体类字段是否有`@Version`注解
3. 检查字段类型是否支持

### 10.2 版本号不更新
**问题**：更新成功后版本号没有递增
**解决**：
1. 检查数据库字段默认值
2. 检查是否有其他拦截器修改了version值
3. 检查SQL日志确认更新语句

### 10.3 并发冲突频繁
**问题**：高并发下乐观锁冲突过多
**解决**：
1. 优化业务逻辑，减少更新竞争
2. 实现重试机制
3. 考虑使用悲观锁或分布式锁

## 11. 最佳实践

### 11.1 代码规范
```java
// 推荐：明确处理乐观锁异常
try {
    userService.update(user);
} catch (OptimisticLockException e) {
    // 1. 记录日志
    log.warn("乐观锁冲突，用户ID：{}", user.getId());
    
    // 2. 通知用户
    throw new BusinessException("数据已被修改，请刷新页面");
    
    // 或3. 自动重试
    // retryUpdate(user);
}
```

### 11.2 监控指标
```java
// 添加乐观锁冲突监控
@Aspect
@Component
@Slf4j
public class OptimisticLockMonitorAspect {
    
    @Around("@annotation(org.springframework.transaction.annotation.Transactional)")
    public Object monitor(ProceedingJoinPoint joinPoint) throws Throwable {
        long start = System.currentTimeMillis();
        try {
            return joinPoint.proceed();
        } catch (OptimisticLockException e) {
            // 记录冲突指标
            Metrics.counter("optimistic.lock.conflict").increment();
            log.warn("乐观锁冲突，方法：{}", joinPoint.getSignature().getName());
            throw e;
        } finally {
            long duration = System.currentTimeMillis() - start;
            Metrics.timer("optimistic.lock.duration").record(duration, TimeUnit.MILLISECONDS);
        }
    }
}
```

## 12. 总结

MyBatis-Plus的乐观锁插件通过`@Version`注解提供了一种简单有效的并发控制方案：

**优点**：
1. 配置简单，使用方便
2. 无锁机制，性能较好
3. 与MyBatis-Plus完美集成
4. 支持多种数据库

**适用场景**：
- 读多写少的应用
- 并发冲突概率较低的场景
- 需要保证数据一致性的业务

**不适用场景**：
- 写操作非常频繁的场景
- 对实时性要求极高的场景
- 无法接受重试的业务

通过合理配置和使用，乐观锁插件能够有效提升系统的并发处理能力和数据一致性。