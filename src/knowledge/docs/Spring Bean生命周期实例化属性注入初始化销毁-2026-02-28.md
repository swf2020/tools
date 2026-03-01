# Spring Bean生命周期详解

## 概述
Spring Bean生命周期指的是Bean从创建到销毁的整个过程，由Spring IoC容器管理。理解Bean生命周期对于掌握Spring框架的运行机制和进行高级定制开发至关重要。

## 生命周期整体流程图

```mermaid
graph TD
    A[容器启动] --> B[Bean定义加载]
    B --> C[实例化Bean]
    C --> D[属性注入/依赖注入]
    D --> E[BeanNameAware.setBeanName]
    E --> F[BeanFactoryAware.setBeanFactory]
    F --> G[ApplicationContextAware.setApplicationContext]
    G --> H[BeanPostProcessor.postProcessBeforeInitialization]
    H --> I[@PostConstruct注解方法]
    I --> J[InitializingBean.afterPropertiesSet]
    J --> K[自定义init-method]
    K --> L[BeanPostProcessor.postProcessAfterInitialization]
    L --> M[Bean准备就绪/使用中]
    M --> N[容器关闭]
    N --> O[@PreDestroy注解方法]
    O --> P[DisposableBean.destroy]
    P --> Q[自定义destroy-method]
    Q --> R[Bean销毁完成]
```

## 详细阶段解析

### 第一阶段：实例化（Instantiation）

#### 1.1 Bean定义加载
```java
// Spring容器读取配置文件或注解，解析为BeanDefinition
BeanDefinition beanDefinition = new RootBeanDefinition(UserService.class);
beanDefinition.setScope(BeanDefinition.SCOPE_SINGLETON);
```

#### 1.2 实例化策略
- **构造函数实例化**：默认方式
- **静态工厂方法**：`factory-method`
- **实例工厂方法**：`factory-bean` + `factory-method`

```java
// 1. 构造函数实例化（最常见）
public class UserService {
    public UserService() {
        System.out.println("1. Bean实例化 - 构造函数执行");
    }
}

// 2. 静态工厂方法
public class StaticFactory {
    public static UserService createInstance() {
        return new UserService();
    }
}

// 配置示例
// <bean id="userService" class="com.example.StaticFactory" factory-method="createInstance"/>
```

### 第二阶段：属性注入（Population）

#### 2.1 依赖注入方式

```java
@Component
public class UserService {
    
    // 1. 字段注入（不推荐，Spring 4.3+）
    @Autowired
    private UserDao userDao;
    
    // 2. 构造函数注入（推荐）
    private final UserDao userDao;
    
    @Autowired
    public UserService(UserDao userDao) {
        this.userDao = userDao;
        System.out.println("2. 属性注入 - 构造函数注入完成");
    }
    
    // 3. Setter注入
    private UserRepository userRepository;
    
    @Autowired
    public void setUserRepository(UserRepository userRepository) {
        this.userRepository = userRepository;
        System.out.println("2. 属性注入 - Setter注入完成");
    }
}
```

#### 2.2 Aware接口注入
Spring提供了一系列Aware接口，用于让Bean获取容器中的资源：

```java
@Component
public class MyBean implements 
        BeanNameAware, 
        BeanFactoryAware, 
        ApplicationContextAware {
    
    private String beanName;
    private BeanFactory beanFactory;
    private ApplicationContext applicationContext;
    
    @Override
    public void setBeanName(String name) {
        this.beanName = name;
        System.out.println("3. BeanNameAware - Bean名称: " + name);
    }
    
    @Override
    public void setBeanFactory(BeanFactory beanFactory) {
        this.beanFactory = beanFactory;
        System.out.println("4. BeanFactoryAware - BeanFactory注入");
    }
    
    @Override
    public void setApplicationContext(ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
        System.out.println("5. ApplicationContextAware - ApplicationContext注入");
    }
}
```

### 第三阶段：初始化（Initialization）

#### 3.1 初始化扩展点执行顺序

```java
@Component
public class UserService implements InitializingBean {
    
    // 1. BeanPostProcessor前置处理
    // BeanPostProcessor.postProcessBeforeInitialization()
    
    // 2. @PostConstruct注解方法（JSR-250标准）
    @PostConstruct
    public void init() {
        System.out.println("6. @PostConstruct - 初始化方法执行");
    }
    
    // 3. InitializingBean接口的afterPropertiesSet()
    @Override
    public void afterPropertiesSet() throws Exception {
        System.out.println("7. InitializingBean.afterPropertiesSet()执行");
    }
    
    // 4. 自定义init-method
    public void customInit() {
        System.out.println("8. 自定义init-method执行");
    }
    
    // 5. BeanPostProcessor后置处理
    // BeanPostProcessor.postProcessAfterInitialization()
}
```

#### 3.2 BeanPostProcessor示例
```java
@Component
public class MyBeanPostProcessor implements BeanPostProcessor {
    
    @Override
    public Object postProcessBeforeInitialization(Object bean, String beanName) {
        System.out.println("BeanPostProcessor前置处理: " + beanName);
        // 可以对bean进行包装或修改
        return bean;
    }
    
    @Override
    public Object postProcessAfterInitialization(Object bean, String beanName) {
        System.out.println("BeanPostProcessor后置处理: " + beanName);
        // 如返回代理对象
        return bean;
    }
}
```

### 第四阶段：使用期

Bean初始化完成后，进入就绪状态，可以被应用程序使用：

```java
// 获取并使用Bean
ApplicationContext context = new AnnotationConfigApplicationContext(AppConfig.class);
UserService userService = context.getBean(UserService.class);
userService.process();
```

### 第五阶段：销毁（Destruction）

#### 5.1 销毁触发时机
- 容器关闭时（`context.close()`）
- Web应用停止时
- 对于原型Bean，Spring不管理其销毁，由调用者负责

#### 5.2 销毁执行顺序

```java
@Component
public class UserService implements DisposableBean {
    
    // 1. @PreDestroy注解方法（JSR-250标准）
    @PreDestroy
    public void preDestroy() {
        System.out.println("9. @PreDestroy - 销毁前方法执行");
    }
    
    // 2. DisposableBean接口的destroy()
    @Override
    public void destroy() throws Exception {
        System.out.println("10. DisposableBean.destroy()执行");
    }
    
    // 3. 自定义destroy-method
    public void customDestroy() {
        System.out.println("11. 自定义destroy-method执行");
    }
}
```

#### 5.3 容器关闭示例
```java
public class Application {
    public static void main(String[] args) {
        // 对于AnnotationConfigApplicationContext
        AnnotationConfigApplicationContext context = 
            new AnnotationConfigApplicationContext(AppConfig.class);
        
        // 使用Bean...
        
        // 关闭容器，触发销毁
        context.close(); // 或 context.registerShutdownHook()
    }
}
```

## 完整示例代码

### 配置类
```java
@Configuration
@ComponentScan("com.example")
public class AppConfig {
    
    @Bean(initMethod = "customInit", destroyMethod = "customDestroy")
    public MyBean myBean() {
        return new MyBean();
    }
}
```

### Bean类
```java
@Component
public class MyBean implements 
        BeanNameAware, 
        InitializingBean, 
        DisposableBean {
    
    private String name;
    
    public MyBean() {
        System.out.println("1. 构造函数执行 - Bean实例化");
    }
    
    @Autowired
    public void setDependency(AnotherBean anotherBean) {
        System.out.println("2. 依赖注入完成");
    }
    
    @Override
    public void setBeanName(String name) {
        this.name = name;
        System.out.println("3. BeanNameAware: " + name);
    }
    
    @PostConstruct
    public void postConstruct() {
        System.out.println("4. @PostConstruct方法执行");
    }
    
    @Override
    public void afterPropertiesSet() {
        System.out.println("5. InitializingBean.afterPropertiesSet()");
    }
    
    public void customInit() {
        System.out.println("6. 自定义init-method");
    }
    
    public void doWork() {
        System.out.println("7. Bean使用中...");
    }
    
    @PreDestroy
    public void preDestroy() {
        System.out.println("8. @PreDestroy方法执行");
    }
    
    @Override
    public void destroy() {
        System.out.println("9. DisposableBean.destroy()");
    }
    
    public void customDestroy() {
        System.out.println("10. 自定义destroy-method");
    }
}
```

## Bean作用域对生命周期的影响

| 作用域 | 生命周期特点 |
|--------|-------------|
| **singleton** | 容器启动时创建，容器关闭时销毁，完整生命周期 |
| **prototype** | 每次获取时创建，Spring不管理销毁，只执行到初始化阶段 |
| **request** | 每次HTTP请求创建，请求结束时销毁 |
| **session** | 每个HTTP会话创建，会话结束时销毁 |
| **application** | ServletContext生命周期内有效 |

## 实际应用场景

### 1. 数据库连接池管理
```java
@Component
public class DatabasePool implements InitializingBean, DisposableBean {
    
    private DataSource dataSource;
    
    @Override
    public void afterPropertiesSet() throws Exception {
        // 初始化连接池
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl("jdbc:mysql://localhost:3306/test");
        config.setUsername("root");
        config.setPassword("password");
        this.dataSource = new HikariDataSource(config);
        System.out.println("数据库连接池初始化完成");
    }
    
    @Override
    public void destroy() throws Exception {
        // 关闭连接池
        if (dataSource instanceof HikariDataSource) {
            ((HikariDataSource) dataSource).close();
        }
        System.out.println("数据库连接池已关闭");
    }
    
    public Connection getConnection() throws SQLException {
        return dataSource.getConnection();
    }
}
```

### 2. 缓存预热
```java
@Component
public class CacheManager {
    
    private Map<String, Object> cache = new ConcurrentHashMap<>();
    
    @PostConstruct
    public void warmUpCache() {
        // 应用启动时预热缓存
        cache.put("config", loadConfigFromDB());
        cache.put("constants", loadConstants());
        System.out.println("缓存预热完成");
    }
    
    @PreDestroy
    public void clearCache() {
        cache.clear();
        System.out.println("缓存已清理");
    }
}
```

## 常见问题与调试技巧

### 1. 生命周期方法执行顺序验证
```java
@Component
public class LifecycleDebugBean implements 
        BeanNameAware, 
        BeanFactoryAware,
        ApplicationContextAware,
        InitializingBean,
        DisposableBean {
    
    private static final Logger logger = LoggerFactory.getLogger(LifecycleDebugBean.class);
    
    public LifecycleDebugBean() {
        logger.debug("构造函数执行");
    }
    
    @Autowired
    public void setDependency(Object dependency) {
        logger.debug("依赖注入: {}", dependency.getClass().getSimpleName());
    }
    
    // ... 实现各个接口方法，添加日志
    
    @PostConstruct
    public void annotatedInit() {
        logger.debug("@PostConstruct执行");
    }
    
    @PreDestroy
    public void annotatedDestroy() {
        logger.debug("@PreDestroy执行");
    }
}
```

### 2. 使用BeanPostProcessor进行监控
```java
@Component
public class MonitoringBeanPostProcessor implements BeanPostProcessor {
    
    @Override
    public Object postProcessBeforeInitialization(Object bean, String beanName) {
        System.out.println("准备初始化Bean: " + beanName + ", 类型: " + bean.getClass().getName());
        return bean;
    }
    
    @Override
    public Object postProcessAfterInitialization(Object bean, String beanName) {
        System.out.println("Bean初始化完成: " + beanName);
        return bean;
    }
}
```

## 最佳实践

1. **依赖注入优先使用构造函数注入**，保证Bean在构造后即处于完整状态
2. **初始化逻辑放在@PostConstruct中**，而非构造函数，避免依赖未注入的问题
3. **资源清理放在@PreDestroy中**，确保及时释放
4. **避免在BeanPostProcessor中执行耗时操作**，影响启动速度
5. **原型Bean需手动管理资源释放**，Spring不负责其销毁

## 总结

Spring Bean生命周期是Spring框架的核心机制之一，理解其各个阶段的执行顺序和扩展点对于：
- 正确管理Bean的初始化和清理
- 实现自定义的初始化逻辑
- 诊断和解决Bean相关的问题
- 进行框架的深度定制和扩展

掌握Bean生命周期，能够帮助开发者编写更健壮、更易维护的Spring应用程序。