# Spring R2DBC响应式数据库访问技术文档

## 1. 概述

### 1.1 什么是R2DBC
**R2DBC**（Reactive Relational Database Connectivity）是一个响应式关系型数据库连接规范，旨在为关系型数据库提供完全非阻塞的响应式编程API。与传统的JDBC（阻塞式）不同，R2DBC支持响应式流规范，能够更好地与Spring WebFlux等响应式框架集成。

### 1.2 为什么选择Spring R2DBC
- **非阻塞I/O**：避免线程阻塞，提高系统吞吐量
- **背压支持**：内置响应式流背压机制
- **与Spring生态系统集成**：无缝集成Spring Data、Spring Boot
- **资源效率**：减少线程数量，降低内存消耗

## 2. 核心依赖配置

### 2.1 Maven依赖
```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-r2dbc</artifactId>
</dependency>

<!-- 数据库驱动（以PostgreSQL为例） -->
<dependency>
    <groupId>io.r2dbc</groupId>
    <artifactId>r2dbc-postgresql</artifactId>
    <version>${r2dbc.version}</version>
</dependency>

<!-- 响应式Web支持（可选） -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

### 2.2 配置文件
```yaml
# application.yml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/mydb
    username: user
    password: password
    pool:
      enabled: true
      initial-size: 5
      max-size: 20
      max-idle-time: 30m
```

## 3. 核心组件

### 3.1 DatabaseClient
`DatabaseClient`是R2DBC的核心接口，用于执行SQL语句并处理结果。

```java
@Component
public class UserRepository {
    
    private final DatabaseClient databaseClient;
    
    public UserRepository(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }
    
    public Flux<User> findAll() {
        return databaseClient.sql("SELECT * FROM users")
            .map((row, metadata) -> {
                User user = new User();
                user.setId(row.get("id", Long.class));
                user.setName(row.get("name", String.class));
                user.setEmail(row.get("email", String.class));
                return user;
            })
            .all();
    }
}
```

### 3.2 R2dbcEntityTemplate
Spring Data R2DBC提供的高级抽象，简化CRUD操作。

```java
@Repository
public class UserRepository {
    
    private final R2dbcEntityTemplate template;
    
    public UserRepository(R2dbcEntityTemplate template) {
        this.template = template;
    }
    
    public Mono<User> save(User user) {
        return template.insert(User.class)
            .using(user)
            .thenReturn(user);
    }
    
    public Mono<User> findById(Long id) {
        return template.select(User.class)
            .matching(Query.query(Criteria.where("id").is(id)))
            .one();
    }
}
```

## 4. 实体映射

### 4.1 基础实体定义
```java
@Table("users")
@Data
@AllArgsConstructor
@NoArgsConstructor
public class User {
    
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    
    @Column("username")
    private String name;
    
    private String email;
    
    @CreatedDate
    private LocalDateTime createdAt;
    
    @LastModifiedDate
    private LocalDateTime updatedAt;
    
    // 复杂类型转换
    @Transient
    private List<String> roles = new ArrayList<>();
    
    // 自定义类型转换器
    @ReadingConverter
    @WritingConverter
    public static class RolesConverter implements Converter<List<String>, String> {
        @Override
        public String convert(List<String> source) {
            return String.join(",", source);
        }
        
        @Override
        public List<String> convertReverse(String source) {
            return Arrays.asList(source.split(","));
        }
    }
}
```

## 5. 响应式Repository

### 5.1 基础Repository接口
```java
public interface UserRepository extends ReactiveCrudRepository<User, Long> {
    
    // 方法名查询
    Mono<User> findByEmail(String email);
    
    Flux<User> findByNameContainingIgnoreCase(String name);
    
    // 自定义查询
    @Query("SELECT * FROM users WHERE age > :age")
    Flux<User> findUsersOlderThan(@Param("age") Integer age);
    
    // 分页查询
    Flux<User> findAllBy(Pageable pageable);
    
    // 复杂查询
    @Query("""
        SELECT u.*, COUNT(o.id) as order_count 
        FROM users u 
        LEFT JOIN orders o ON u.id = o.user_id 
        GROUP BY u.id 
        HAVING COUNT(o.id) > :minOrders
        """)
    Flux<User> findActiveUsers(@Param("minOrders") Integer minOrders);
}
```

### 5.2 自定义Repository实现
```java
public interface CustomUserRepository {
    Flux<User> findUsersWithOrders();
}

public class CustomUserRepositoryImpl implements CustomUserRepository {
    
    private final DatabaseClient databaseClient;
    
    @Override
    public Flux<User> findUsersWithOrders() {
        return databaseClient.sql("""
            SELECT u.*, 
                   json_agg(
                       json_build_object(
                           'id', o.id,
                           'amount', o.amount
                       )
                   ) as orders
            FROM users u
            JOIN orders o ON u.id = o.user_id
            GROUP BY u.id
            """)
            .fetch()
            .all()
            .map(this::mapToUserWithOrders);
    }
    
    private User mapToUserWithOrders(Map<String, Object> row) {
        // 映射逻辑
        return user;
    }
}

// 主Repository接口
public interface UserRepository extends 
    ReactiveCrudRepository<User, Long>, 
    CustomUserRepository {
    // ...
}
```

## 6. 事务管理

### 6.1 声明式事务
```java
@Service
@Transactional
public class UserService {
    
    private final UserRepository userRepository;
    private final OrderRepository orderRepository;
    
    public Mono<Void> createUserWithInitialOrder(User user, Order order) {
        return userRepository.save(user)
            .flatMap(savedUser -> {
                order.setUserId(savedUser.getId());
                return orderRepository.save(order);
            })
            .then();
    }
    
    // 只读事务
    @Transactional(readOnly = true)
    public Flux<User> findAllActiveUsers() {
        return userRepository.findByStatus("ACTIVE");
    }
}
```

### 6.2 编程式事务
```java
@Service
public class OrderService {
    
    private final TransactionalOperator transactionalOperator;
    
    public Mono<Void> processOrder(Long orderId) {
        return transactionalOperator.execute(status -> {
            return orderRepository.findById(orderId)
                .flatMap(order -> {
                    order.setStatus("PROCESSING");
                    return orderRepository.save(order)
                        .then(inventoryService.reserveItems(order))
                        .then(paymentService.processPayment(order));
                })
                .onErrorResume(e -> {
                    status.setRollbackOnly();
                    return Mono.error(e);
                });
        });
    }
}
```

## 7. 连接池配置

### 7.1 自定义连接池
```java
@Configuration
public class R2dbcConfig {
    
    @Bean
    public ConnectionFactory connectionFactory() {
        return ConnectionFactoryBuilder
            .withOptions(new PostgresqlConnectionFactoryProvider())
            .configure(builder -> builder
                .host("localhost")
                .port(5432)
                .database("mydb")
                .username("user")
                .password("password")
            )
            .build();
    }
    
    @Bean
    public ConnectionFactory connectionPool(ConnectionFactory connectionFactory) {
        return new ConnectionPool(
            ConnectionPoolConfiguration.builder(connectionFactory)
                .maxIdleTime(Duration.ofMinutes(30))
                .maxSize(20)
                .initialSize(5)
                .validationQuery("SELECT 1")
                .build()
        );
    }
}
```

## 8. 性能优化

### 8.1 批量操作
```java
@Repository
public class BatchUserRepository {
    
    private final R2dbcEntityTemplate template;
    
    public Flux<User> batchInsert(List<User> users) {
        return template.insert(User.class)
            .using(Flux.fromIterable(users))
            .all()
            .buffer(100) // 每100条批量提交
            .flatMap(batch -> template.getDatabaseClient()
                .inConnectionMany(connection -> {
                    // 手动批量操作
                    return Flux.fromIterable(batch)
                        .flatMap(user -> 
                            connection.createStatement(
                                "INSERT INTO users (name, email) VALUES ($1, $2)")
                                .bind("$1", user.getName())
                                .bind("$2", user.getEmail())
                                .execute()
                        );
                })
            );
    }
}
```

### 8.2 查询优化
```java
@Repository
public class OptimizedUserRepository {
    
    private final DatabaseClient databaseClient;
    
    // 使用投影减少数据传输
    public Flux<UserProjection> findUserProjections() {
        return databaseClient.sql("""
            SELECT id, name, 
                   (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) as order_count
            FROM users u
            """)
            .map((row, metadata) -> new UserProjection(
                row.get("id", Long.class),
                row.get("name", String.class),
                row.get("order_count", Integer.class)
            ))
            .all();
    }
    
    // 流式查询处理大数据集
    public Flux<User> streamLargeDataset() {
        return databaseClient.sql("SELECT * FROM large_table")
            .fetch()
            .rowsUpdated()
            .flatMapMany(rows -> 
                databaseClient.sql("SELECT * FROM large_table")
                    .map(this::mapRowToUser)
                    .all()
            )
            .onBackpressureBuffer(1000); // 背压缓冲
    }
}
```

## 9. 监控与日志

### 9.1 配置日志
```yaml
logging:
  level:
    org.springframework.r2dbc: DEBUG
    io.r2dbc.postgresql.QUERY: TRACE
    io.r2dbc.postgresql.PARAM: TRACE
```

### 9.2 监控指标
```java
@Configuration
public class MetricsConfig {
    
    @Bean
    public ConnectionFactoryDecorator metricsConnectionFactoryDecorator(
            MeterRegistry meterRegistry) {
        return connectionFactory -> 
            new ObservableConnectionFactory(connectionFactory, meterRegistry);
    }
}
```

## 10. 最佳实践

### 10.1 错误处理
```java
@Component
public class UserService {
    
    public Mono<User> findUserSafe(Long id) {
        return userRepository.findById(id)
            .switchIfEmpty(Mono.error(
                new UserNotFoundException("User not found with id: " + id)
            ))
            .onErrorResume(R2dbcException.class, e -> {
                log.error("Database error: ", e);
                return Mono.error(new ServiceException("Database error occurred"));
            })
            .retryWhen(Retry.backoff(3, Duration.ofSeconds(1))
                .filter(e -> e instanceof TransientDataAccessException));
    }
}
```

### 10.2 测试
```java
@SpringBootTest
@DataR2dbcTest
@Import(TestDatabaseConfiguration.class)
public class UserRepositoryTest {
    
    @Autowired
    private UserRepository userRepository;
    
    @Test
    public void testFindByEmail() {
        User user = new User(null, "test", "test@example.com");
        
        userRepository.save(user)
            .as(StepVerifier::create)
            .expectNextCount(1)
            .verifyComplete();
            
        userRepository.findByEmail("test@example.com")
            .as(StepVerifier::create)
            .expectNextMatches(u -> u.getName().equals("test"))
            .verifyComplete();
    }
}
```

## 11. 常见问题解决

### 11.1 连接泄露检测
```java
@Component
public class ConnectionLeakDetector {
    
    @EventListener(ApplicationReadyEvent.class)
    public void detectConnectionLeaks() {
        ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(1);
        scheduler.scheduleAtFixedRate(() -> {
            // 监控连接池状态
            log.info("Active connections: {}", connectionPool.getMetrics().getAcquiredSize());
        }, 0, 1, TimeUnit.MINUTES);
    }
}
```

### 11.2 序列化问题
```java
@Configuration
public class R2dbcCustomConverters {
    
    @Bean
    public R2dbcCustomConversions r2dbcCustomConversions() {
        List<Converter<?, ?>> converters = new ArrayList<>();
        converters.add(new User.RolesConverter());
        converters.add(new InstantToTimestampConverter());
        converters.add(new TimestampToInstantConverter());
        
        return new R2dbcCustomConversions(
            CustomConversions.StoreConversions.NONE,
            converters
        );
    }
}
```

## 12. 总结

Spring R2DBC为关系型数据库的响应式访问提供了完整的解决方案。通过本指南，您可以：

1. **快速集成**：使用Spring Boot Starter快速集成R2DBC
2. **高效开发**：利用Spring Data的Repository模式简化开发
3. **性能优化**：实现非阻塞、响应式的数据库访问
4. **生产就绪**：配置连接池、监控、事务管理等生产级特性

在实际应用中，请根据具体业务需求选择合适的配置和优化策略，确保系统的高性能和可靠性。