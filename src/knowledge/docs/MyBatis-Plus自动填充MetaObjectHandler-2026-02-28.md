# MyBatis-Plus 自动填充(MetaObjectHandler) 技术文档

## 1. 概述

### 1.1 什么是自动填充
MyBatis-Plus的自动填充功能用于在数据库记录插入或更新时，自动填充某些字段的值，例如创建时间、更新时间、创建人、更新人等通用字段。这种机制减少了重复代码编写，提高了开发效率。

### 1.2 核心组件
- **@TableField 注解**：标记需要自动填充的字段
- **MetaObjectHandler 接口**：定义填充逻辑的实现类
- **MetaObject**：MyBatis提供的元对象，用于操作实体类的属性

## 2. 使用场景

### 2.1 典型应用场景
1. **时间字段自动填充**
   - 创建时间（create_time）
   - 更新时间（update_time）
   
2. **操作人信息自动填充**
   - 创建人（create_user）
   - 更新人（update_user）
   
3. **逻辑删除字段填充**
   - 删除标志（deleted）
   - 删除时间（delete_time）
   
4. **版本控制字段**
   - 数据版本（version）

## 3. 快速开始

### 3.1 添加依赖
```xml
<dependency>
    <groupId>com.baomidou</groupId>
    <artifactId>mybatis-plus-boot-starter</artifactId>
    <version>最新版本</version>
</dependency>
```

### 3.2 实体类配置
```java
import com.baomidou.mybatisplus.annotation.*;
import java.time.LocalDateTime;

@Data
@TableName("user")
public class User {
    
    @TableId(type = IdType.AUTO)
    private Long id;
    
    private String name;
    
    private Integer age;
    
    private String email;
    
    // 插入时自动填充
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createTime;
    
    // 插入和更新时自动填充
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updateTime;
    
    // 插入时自动填充
    @TableField(fill = FieldFill.INSERT)
    private Long createUser;
    
    // 插入和更新时自动填充
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private Long updateUser;
    
    // 逻辑删除字段
    @TableLogic
    @TableField(fill = FieldFill.INSERT)
    private Integer deleted;
}
```

### 3.3 实现MetaObjectHandler
```java
import com.baomidou.mybatisplus.core.handlers.MetaObjectHandler;
import lombok.extern.slf4j.Slf4j;
import org.apache.ibatis.reflection.MetaObject;
import org.springframework.stereotype.Component;
import java.time.LocalDateTime;

@Slf4j
@Component
public class MyMetaObjectHandler implements MetaObjectHandler {
    
    /**
     * 插入时自动填充
     */
    @Override
    public void insertFill(MetaObject metaObject) {
        log.info("开始插入填充...");
        
        // 填充创建时间
        this.strictInsertFill(metaObject, "createTime", LocalDateTime.class, LocalDateTime.now());
        
        // 填充更新时间
        this.strictInsertFill(metaObject, "updateTime", LocalDateTime.class, LocalDateTime.now());
        
        // 填充创建人ID（从ThreadLocal或SecurityContext获取）
        Long currentUserId = getCurrentUserId();
        this.strictInsertFill(metaObject, "createUser", Long.class, currentUserId);
        
        // 填充更新人ID
        this.strictInsertFill(metaObject, "updateUser", Long.class, currentUserId);
        
        // 填充逻辑删除字段默认值
        this.strictInsertFill(metaObject, "deleted", Integer.class, 0);
    }
    
    /**
     * 更新时自动填充
     */
    @Override
    public void updateFill(MetaObject metaObject) {
        log.info("开始更新填充...");
        
        // 填充更新时间
        this.strictUpdateFill(metaObject, "updateTime", LocalDateTime.class, LocalDateTime.now());
        
        // 填充更新人ID
        Long currentUserId = getCurrentUserId();
        this.strictUpdateFill(metaObject, "updateUser", Long.class, currentUserId);
    }
    
    /**
     * 获取当前用户ID（示例方法）
     */
    private Long getCurrentUserId() {
        // 实际项目中可以从SecurityContext、ThreadLocal或JWT令牌中获取
        // 这里返回模拟值
        return 1001L;
    }
}
```

## 4. 高级配置

### 4.1 填充策略详解

#### 4.1.1 FieldFill 枚举
```java
public enum FieldFill {
    DEFAULT,          // 默认不处理
    INSERT,           // 插入时填充
    UPDATE,           // 更新时填充
    INSERT_UPDATE     // 插入和更新时填充
}
```

#### 4.2 多种填充方法

##### 4.2.1 strictInsertFill / strictUpdateFill
```java
// 严格模式填充（推荐）
// 属性值为null时才填充，属性值不为null不处理
this.strictInsertFill(metaObject, "createTime", LocalDateTime.class, LocalDateTime.now());

// 注意：strictUpdateFill在更新时，即使字段有值也会被填充覆盖
this.strictUpdateFill(metaObject, "updateTime", LocalDateTime.class, LocalDateTime.now());
```

##### 4.2.2 fillStrategy
```java
// 策略模式填充（3.3.0+）
// 无论属性是否有值都填充
this.fillStrategy(metaObject, "updateTime", LocalDateTime.now());
```

##### 4.2.3 setFieldValByName
```java
// 直接设置值（不推荐，容易覆盖已有值）
this.setFieldValByName("createTime", LocalDateTime.now(), metaObject);
```

### 4.3 自定义填充值

```java
@Component
public class CustomMetaObjectHandler implements MetaObjectHandler {
    
    @Override
    public void insertFill(MetaObject metaObject) {
        // 根据实体类类型进行不同的填充逻辑
        String className = metaObject.getOriginalObject().getClass().getName();
        
        if (className.contains("User")) {
            this.strictInsertFill(metaObject, "tenantId", String.class, getCurrentTenantId());
        }
        
        if (className.contains("Order")) {
            this.strictInsertFill(metaObject, "orderNo", String.class, generateOrderNo());
        }
    }
    
    @Override
    public void updateFill(MetaObject metaObject) {
        // 可以根据字段是否已存在决定是否填充
        Object updateTime = getFieldValByName("updateTime", metaObject);
        if (updateTime == null) {
            this.strictUpdateFill(metaObject, "updateTime", LocalDateTime.class, LocalDateTime.now());
        }
    }
    
    private String getCurrentTenantId() {
        // 获取当前租户ID
        return "tenant_001";
    }
    
    private String generateOrderNo() {
        // 生成订单号
        return "ORD" + System.currentTimeMillis();
    }
}
```

## 5. 实际应用示例

### 5.1 完整业务示例

#### 5.1.1 实体类
```java
@Data
@TableName("sys_log")
public class SystemLog {
    
    @TableId(type = IdType.ASSIGN_ID)
    private String id;
    
    private String module;
    
    private String operation;
    
    private String params;
    
    private String ip;
    
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createTime;
    
    @TableField(fill = FieldFill.INSERT)
    private String createBy;
    
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updateTime;
    
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private String updateBy;
    
    @TableField(fill = FieldFill.INSERT)
    private Integer status;
}
```

#### 5.1.2 增强的MetaObjectHandler
```java
@Component
public class SystemMetaObjectHandler implements MetaObjectHandler {
    
    private final ThreadLocal<UserContext> userContext = new ThreadLocal<>();
    
    @Override
    public void insertFill(MetaObject metaObject) {
        UserContext currentUser = getUserContext();
        
        // 填充公共字段
        fillCommonFields(metaObject, currentUser, true);
        
        // 特定实体类特殊处理
        if (metaObject.getOriginalObject() instanceof SystemLog) {
            this.strictInsertFill(metaObject, "status", Integer.class, 1);
        }
        
        if (metaObject.getOriginalObject() instanceof BusinessEntity) {
            this.strictInsertFill(metaObject, "orgCode", String.class, currentUser.getOrgCode());
        }
    }
    
    @Override
    public void updateFill(MetaObject metaObject) {
        UserContext currentUser = getUserContext();
        fillCommonFields(metaObject, currentUser, false);
    }
    
    /**
     * 填充公共字段
     */
    private void fillCommonFields(MetaObject metaObject, UserContext user, boolean isInsert) {
        LocalDateTime now = LocalDateTime.now();
        
        if (isInsert) {
            // 插入操作
            this.strictInsertFill(metaObject, "createTime", LocalDateTime.class, now);
            this.strictInsertFill(metaObject, "createBy", String.class, user.getUserId());
            
            // 如果实体有租户字段
            if (metaObject.hasSetter("tenantId")) {
                this.strictInsertFill(metaObject, "tenantId", String.class, user.getTenantId());
            }
        }
        
        // 更新操作（包括插入时的更新字段）
        this.strictUpdateFill(metaObject, "updateTime", LocalDateTime.class, now);
        this.strictUpdateFill(metaObject, "updateBy", String.class, user.getUserId());
    }
    
    /**
     * 获取用户上下文（可以从ThreadLocal或SecurityContext获取）
     */
    private UserContext getUserContext() {
        UserContext context = userContext.get();
        if (context == null) {
            // 模拟获取用户信息
            context = new UserContext("user123", "tenant_001", "ORG001");
            userContext.set(context);
        }
        return context;
    }
    
    /**
     * 清理ThreadLocal
     */
    public void clearContext() {
        userContext.remove();
    }
    
    @Data
    @AllArgsConstructor
    private static class UserContext {
        private String userId;
        private String tenantId;
        private String orgCode;
    }
}
```

### 5.2 多租户场景下的自动填充
```java
@Component
public class MultiTenantMetaObjectHandler implements MetaObjectHandler {
    
    @Override
    public void insertFill(MetaObject metaObject) {
        // 获取当前租户ID
        String tenantId = TenantContext.getCurrentTenant();
        
        // 检查实体是否有tenantId字段
        if (hasField(metaObject, "tenantId")) {
            this.strictInsertFill(metaObject, "tenantId", String.class, tenantId);
        }
        
        // 检查实体是否有orgId字段
        if (hasField(metaObject, "orgId")) {
            String orgId = getCurrentOrgId();
            this.strictInsertFill(metaObject, "orgId", String.class, orgId);
        }
    }
    
    private boolean hasField(MetaObject metaObject, String fieldName) {
        return metaObject.hasGetter(fieldName) && metaObject.hasSetter(fieldName);
    }
    
    private String getCurrentOrgId() {
        // 从用户信息中获取组织ID
        return "ORG_001";
    }
}
```

## 6. 注意事项与最佳实践

### 6.1 注意事项
1. **字段名匹配**：确保@TableField中的字段名与数据库字段名一致
2. **类型匹配**：填充值的类型必须与实体字段类型一致
3. **null值处理**：strict方法只在字段为null时填充，fillStrategy会覆盖已有值
4. **线程安全**：MetaObjectHandler通常是单例，注意线程安全问题

### 6.2 最佳实践
1. **统一字段命名规范**
```java
// 建议使用以下字段名规范
create_time    // 创建时间
create_by      // 创建人
update_time    // 更新时间  
update_by      // 更新人
tenant_id      // 租户ID
org_id         // 组织ID
```

2. **使用严格模式填充**
```java
// 推荐使用strict方法，避免意外覆盖数据
this.strictInsertFill(metaObject, "createTime", LocalDateTime.class, LocalDateTime.now());
```

3. **用户上下文管理**
```java
// 使用Filter或Interceptor设置ThreadLocal
@Component
public class UserContextFilter implements Filter {
    
    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain) {
        try {
            // 从请求中获取用户信息
            String userId = extractUserId(request);
            UserContextHolder.set(userId);
            chain.doFilter(request, response);
        } finally {
            UserContextHolder.clear();
        }
    }
}
```

4. **测试策略**
```java
@SpringBootTest
class MetaObjectHandlerTest {
    
    @Autowired
    private UserMapper userMapper;
    
    @Test
    void testAutoFill() {
        User user = new User();
        user.setName("测试用户");
        user.setAge(25);
        
        userMapper.insert(user);
        
        assertNotNull(user.getCreateTime());
        assertNotNull(user.getCreateUser());
        assertNotNull(user.getUpdateTime());
        assertEquals(0, user.getDeleted());
    }
}
```

## 7. 常见问题排查

### 7.1 自动填充不生效
1. **检查注解配置**
   ```java
   // 确保添加了正确的fill属性
   @TableField(fill = FieldFill.INSERT)
   private LocalDateTime createTime;
   ```

2. **检查处理器注册**
   ```java
   // 确保MetaObjectHandler被Spring管理
   @Component
   public class MyMetaObjectHandler implements MetaObjectHandler
   ```

3. **检查字段类型**
   ```java
   // 确保填充值类型与字段类型匹配
   this.strictInsertFill(metaObject, "createTime", LocalDateTime.class, LocalDateTime.now());
   ```

### 7.2 填充值被覆盖
- 使用`strictInsertFill`替代`fillStrategy`避免覆盖已有值
- 检查是否在业务代码中手动设置了字段值

### 7.3 多数据源配置
```java
@Configuration
public class DataSourceConfig {
    
    @Bean
    public MetaObjectHandler metaObjectHandler() {
        return new MyMetaObjectHandler();
    }
    
    // 如果使用多数据源，需要为每个数据源配置SqlSessionFactory
    @Bean
    public SqlSessionFactory sqlSessionFactory(DataSource dataSource, 
                                               MetaObjectHandler metaObjectHandler) throws Exception {
        MybatisPlusSqlSessionFactoryBean factory = new MybatisPlusSqlSessionFactoryBean();
        factory.setDataSource(dataSource);
        
        // 配置自动填充
        MybatisPlusConfiguration configuration = new MybatisPlusConfiguration();
        configuration.setMetaObjectHandler(metaObjectHandler);
        factory.setConfiguration(configuration);
        
        return factory.getObject();
    }
}
```

## 8. 总结

MyBatis-Plus的自动填充功能通过MetaObjectHandler提供了强大的字段自动填充能力，能够显著减少重复代码，提高开发效率。合理使用该功能可以：

1. **统一字段管理**：规范创建时间、更新时间等通用字段的处理
2. **减少重复代码**：避免在每个业务方法中手动设置这些字段
3. **提高数据一致性**：确保关键字段的正确填充
4. **支持复杂场景**：通过自定义处理器支持多租户、操作日志等复杂需求

在实际项目中，建议结合ThreadLocal或SecurityContext获取用户信息，实现完整的自动填充解决方案，同时注意线程安全和性能考量。