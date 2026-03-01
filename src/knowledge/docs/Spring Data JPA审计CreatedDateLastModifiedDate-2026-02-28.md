# Spring Data JPA审计功能详解：@CreatedDate与@LastModifiedDate

## 1. 概述

Spring Data JPA审计功能允许自动跟踪实体生命周期中的关键时间点，特别是创建时间和最后修改时间。这是通过`@CreatedDate`和`@LastModifiedDate`注解实现的，能够自动管理实体审计字段，无需手动设置。

### 1.1 核心价值
- **自动化管理**：自动维护创建和修改时间戳
- **代码简洁**：减少样板代码，提高开发效率
- **数据一致性**：确保审计字段的统一处理
- **业务洞察**：提供数据生命周期追踪能力

## 2. 启用审计功能

### 2.1 方式一：使用JPA注解配置

```java
@Configuration
@EnableJpaAuditing  // 启用JPA审计功能
public class JpaAuditingConfig {
    
    @Bean
    public AuditorAware<String> auditorAware() {
        return new AuditorAwareImpl(); // 用于获取当前用户
    }
}
```

### 2.2 方式二：使用Spring Boot自动配置
在Spring Boot项目中，只需添加`@EnableJpaAuditing`注解到主配置类：

```java
@SpringBootApplication
@EnableJpaAuditing
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

## 3. 核心注解详解

### 3.1 @CreatedDate
用于标记实体的创建时间字段，在实体首次持久化时自动设置当前时间。

**特性：**
- 仅在实体首次保存时设置
- 后续更新操作不会修改此字段
- 支持`Date`、`LocalDateTime`、`Instant`等时间类型

### 3.2 @LastModifiedDate
用于标记实体的最后修改时间字段，每次更新实体时自动更新为当前时间。

**特性：**
- 每次实体更新时自动更新
- 包含首次创建时的设置
- 支持与`@CreatedDate`相同的时间类型

## 4. 实体类配置示例

### 4.1 基础实体审计类（推荐）

```java
import javax.persistence.*;
import java.time.LocalDateTime;

@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)  // 启用审计监听
public abstract class BaseAuditEntity {
    
    @CreatedDate
    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;
    
    @LastModifiedDate
    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;
    
    // Getter方法
    public LocalDateTime getCreatedAt() {
        return createdAt;
    }
    
    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }
}
```

### 4.2 具体实体类实现

```java
import javax.persistence.*;

@Entity
@Table(name = "users")
public class User extends BaseAuditEntity {
    
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    
    @Column(nullable = false, unique = true)
    private String username;
    
    @Column(nullable = false)
    private String email;
    
    // 构造器、Getter和Setter
    public User() {}
    
    public User(String username, String email) {
        this.username = username;
        this.email = email;
    }
    
    // Getters and Setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    
    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
    
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
```

### 4.3 独立实体类配置（不使用继承）

```java
import javax.persistence.*;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;
import java.util.Date;

@Entity
@Table(name = "products")
@EntityListeners(AuditingEntityListener.class)
public class Product {
    
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    
    private String name;
    private BigDecimal price;
    
    @CreatedDate
    @Temporal(TemporalType.TIMESTAMP)
    @Column(name = "create_time", updatable = false)
    private Date createTime;
    
    @LastModifiedDate
    @Temporal(TemporalType.TIMESTAMP)
    @Column(name = "update_time")
    private Date updateTime;
    
    // Getter和Setter方法
    // ...
}
```

## 5. Repository配置与使用

### 5.1 Repository接口

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserRepository extends JpaRepository<User, Long> {
    // 可以添加自定义查询方法
    Optional<User> findByUsername(String username);
}
```

### 5.2 服务层使用示例

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.Optional;

@Service
public class UserService {
    
    private final UserRepository userRepository;
    
    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }
    
    @Transactional
    public User createUser(User user) {
        // 保存时自动设置createdAt和updatedAt
        return userRepository.save(user);
    }
    
    @Transactional
    public User updateUser(Long id, User updatedUser) {
        return userRepository.findById(id)
            .map(existingUser -> {
                existingUser.setUsername(updatedUser.getUsername());
                existingUser.setEmail(updatedUser.getEmail());
                // 更新时自动更新updatedAt，createdAt保持不变
                return userRepository.save(existingUser);
            })
            .orElseThrow(() -> new ResourceNotFoundException("User not found"));
    }
}
```

## 6. 高级配置与自定义

### 6.1 自定义日期格式

```java
import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.LocalDateTime;

@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class BaseEntity {
    
    @CreatedDate
    @Column(name = "created_at", updatable = false)
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime createdAt;
    
    @LastModifiedDate
    @Column(name = "updated_at")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime updatedAt;
    
    // ...
}
```

### 6.2 添加创建者和修改者审计

```java
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.LastModifiedBy;

@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class FullAuditEntity extends BaseAuditEntity {
    
    @CreatedBy
    @Column(name = "created_by", updatable = false)
    private String createdBy;
    
    @LastModifiedBy
    @Column(name = "updated_by")
    private String updatedBy;
    
    // Getter和Setter
    // ...
}
```

### 6.3 实现AuditorAware获取当前用户

```java
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import java.util.Optional;

public class AuditorAwareImpl implements AuditorAware<String> {
    
    @Override
    public Optional<String> getCurrentAuditor() {
        Authentication authentication = SecurityContextHolder.getContext()
            .getAuthentication();
        
        if (authentication == null || !authentication.isAuthenticated()) {
            return Optional.of("SYSTEM");
        }
        
        return Optional.of(authentication.getName());
    }
}
```

## 7. 数据库表设计建议

### 7.1 MySQL示例

```sql
CREATE TABLE users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_username (username),
    INDEX idx_created_at (created_at)
);

-- 如果需要纳秒级精度
CREATE TABLE audit_logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    action VARCHAR(50) NOT NULL,
    entity_id BIGINT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);
```

### 7.2 PostgreSQL示例

```sql
CREATE TABLE products (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    updated_by VARCHAR(100)
);

-- 创建更新触发器（可选）
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_products_updated_at 
    BEFORE UPDATE ON products 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

## 8. 常见问题与解决方案

### 8.1 时区处理

```java
import javax.persistence.PrePersist;
import javax.persistence.PreUpdate;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class TimezoneAwareEntity {
    
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
    
    @PrePersist
    protected void onCreate() {
        // 使用系统默认时区
        createdAt = LocalDateTime.now(ZoneId.systemDefault());
        updatedAt = createdAt;
    }
    
    @PreUpdate
    protected void onUpdate() {
        // 使用UTC时区
        updatedAt = LocalDateTime.now(ZoneId.of("UTC"));
    }
    
    // 或者在配置类中设置全局时区
    @Bean
    public Jackson2ObjectMapperBuilderCustomizer jacksonCustomizer() {
        return builder -> {
            builder.timeZone(TimeZone.getTimeZone("Asia/Shanghai"));
            builder.simpleDateFormat("yyyy-MM-dd HH:mm:ss");
        };
    }
}
```

### 8.2 批量操作处理

```java
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

public interface ProductRepository extends JpaRepository<Product, Long> {
    
    @Modifying
    @Query("UPDATE Product p SET p.price = p.price * ?1 WHERE p.category = ?2")
    int updatePriceByCategory(BigDecimal multiplier, String category);
    // 注意：批量更新不会触发@LastModifiedDate自动更新
}
```

### 8.3 测试中的审计

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

@SpringBootTest
@TestPropertySource(properties = {
    "spring.jpa.properties.hibernate.jdbc.time_zone=UTC"
})
public class UserAuditTest {
    
    @Test
    public void testAuditFields() {
        User user = new User("testuser", "test@example.com");
        user = userRepository.save(user);
        
        assertNotNull(user.getCreatedAt());
        assertNotNull(user.getUpdatedAt());
        assertEquals(user.getCreatedAt(), user.getUpdatedAt());
        
        // 模拟更新
        user.setEmail("updated@example.com");
        User updatedUser = userRepository.save(user);
        
        assertTrue(updatedUser.getUpdatedAt()
            .isAfter(updatedUser.getCreatedAt()));
    }
}
```

## 9. 最佳实践建议

1. **使用基类继承**：创建`BaseAuditEntity`基类提高代码复用性
2. **数据库触发器备份**：对于关键业务表，可同时使用数据库触发器作为备份
3. **时区统一**：所有时间字段使用UTC存储，展示时转换为本地时间
4. **索引优化**：为审计字段添加适当索引以提高查询性能
5. **日志记录**：结合审计字段实现操作日志追踪
6. **版本控制**：重要实体添加`@Version`注解实现乐观锁

## 10. 总结

Spring Data JPA的审计功能通过`@CreatedDate`和`@LastModifiedDate`注解，为实体提供了自动化的时间戳管理。这种声明式的审计方式：

- **减少样板代码**：无需手动设置时间字段
- **提高数据质量**：确保审计字段的一致性
- **增强可维护性**：集中管理审计逻辑
- **支持扩展**：可轻松添加创建者、修改者等审计信息

通过合理配置和使用，这些审计功能能够显著提升应用程序的数据追踪能力和维护效率，是构建企业级应用的推荐实践。