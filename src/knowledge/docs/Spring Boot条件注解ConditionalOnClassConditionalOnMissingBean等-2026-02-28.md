# Spring Boot条件注解技术文档

## 1. 概述

### 1.1 什么是条件注解
条件注解是Spring Boot自动配置的核心机制之一，它允许在满足特定条件时才将Bean注册到Spring容器中。这种机制使得Spring Boot能够根据类路径、环境变量、配置文件等条件智能地决定是否启用特定的配置。

### 1.2 条件注解的作用
- **自动装配**：根据应用环境自动配置合适的Bean
- **避免冲突**：防止相同类型的Bean重复注册
- **环境适配**：根据不同的运行环境启用不同的配置
- **依赖管理**：确保必要的依赖存在时才启用相关功能

## 2. 常用条件注解分类

### 2.1 类路径相关条件

#### @ConditionalOnClass
```java
@Configuration
@ConditionalOnClass({DataSource.class, JdbcTemplate.class})
public class JdbcConfiguration {
    // 当类路径中存在DataSource和JdbcTemplate类时才启用此配置
}
```

#### @ConditionalOnMissingClass
```java
@Configuration
@ConditionalOnMissingClass("com.example.ExternalService")
public class FallbackConfiguration {
    // 当类路径中不存在指定类时才启用此配置
}
```

### 2.2 Bean相关条件

#### @ConditionalOnBean
```java
@Configuration
public class CacheConfiguration {
    
    @Bean
    @ConditionalOnBean(DataSource.class)
    public CacheManager cacheManager() {
        // 当容器中存在DataSource Bean时才创建CacheManager
        return new JCacheCacheManager();
    }
}
```

#### @ConditionalOnMissingBean
```java
@Configuration
public class JacksonConfiguration {
    
    @Bean
    @ConditionalOnMissingBean
    public ObjectMapper objectMapper() {
        // 当容器中不存在ObjectMapper Bean时才创建默认的
        ObjectMapper mapper = new ObjectMapper();
        mapper.configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
        return mapper;
    }
}
```

### 2.3 属性配置条件

#### @ConditionalOnProperty
```java
@Configuration
@ConditionalOnProperty(
    prefix = "app.cache",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true  // 配置不存在时默认启用
)
public class RedisCacheConfiguration {
    // 当app.cache.enabled=true时才启用Redis缓存配置
}
```

#### @ConditionalOnExpression
```java
@Configuration
@ConditionalOnExpression(
    "${app.feature.enabled:true} and '${app.mode}' != 'test'"
)
public class AdvancedFeatureConfiguration {
    // 使用SpEL表达式进行复杂条件判断
}
```

### 2.4 其他条件

#### @ConditionalOnWebApplication / @ConditionalOnNotWebApplication
```java
@Configuration
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
public class WebMvcConfiguration {
    // 仅当应用是Servlet Web应用时启用
}
```

#### @ConditionalOnCloudPlatform
```java
@Configuration
@ConditionalOnCloudPlatform(CloudPlatform.CLOUD_FOUNDRY)
public class CloudFoundryConfiguration {
    // 仅在Cloud Foundry平台上启用
}
```

#### @ConditionalOnResource
```java
@Configuration
@ConditionalOnResource(resources = "classpath:config/special.properties")
public class SpecialConfiguration {
    // 当指定资源存在时启用
}
```

## 3. 条件注解组合使用

### 3.1 多条件组合
```java
@Configuration
@ConditionalOnClass({RedisTemplate.class, RedisConnectionFactory.class})
@ConditionalOnProperty(prefix = "spring.redis", name = "enabled", havingValue = "true")
@ConditionalOnMissingBean(RedisTemplate.class)
public class RedisAutoConfiguration {
    
    @Bean
    @ConditionalOnMissingBean(name = "redisTemplate")
    public RedisTemplate<String, Object> redisTemplate(
            RedisConnectionFactory redisConnectionFactory) {
        RedisTemplate<String, Object> template = new RedisTemplate<>();
        template.setConnectionFactory(redisConnectionFactory);
        return template;
    }
}
```

### 3.2 自定义条件注解
```java
// 1. 实现Condition接口
public class OnProductionCondition implements Condition {
    @Override
    public boolean matches(ConditionContext context, AnnotatedTypeMetadata metadata) {
        Environment env = context.getEnvironment();
        String profile = env.getProperty("spring.profiles.active", "dev");
        return "prod".equals(profile);
    }
}

// 2. 定义元注解
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(OnProductionCondition.class)
public @interface ConditionalOnProduction {
}

// 3. 使用自定义条件注解
@Configuration
@ConditionalOnProduction
public class ProductionConfiguration {
    // 仅在生产环境启用的配置
}
```

## 4. 最佳实践与使用示例

### 4.1 典型应用场景

#### 场景1：多数据源配置
```java
@Configuration
public class DataSourceConfiguration {
    
    @Primary
    @Bean(name = "primaryDataSource")
    @ConfigurationProperties(prefix = "spring.datasource.primary")
    @ConditionalOnProperty(prefix = "spring.datasource.primary", name = "enabled")
    public DataSource primaryDataSource() {
        return DataSourceBuilder.create().build();
    }
    
    @Bean(name = "secondaryDataSource")
    @ConfigurationProperties(prefix = "spring.datasource.secondary")
    @ConditionalOnProperty(prefix = "spring.datasource.secondary", name = "enabled")
    @ConditionalOnBean(name = "primaryDataSource")
    public DataSource secondaryDataSource() {
        return DataSourceBuilder.create().build();
    }
}
```

#### 场景2：功能开关配置
```java
@Configuration
public class FeatureToggleConfiguration {
    
    @Bean
    @ConditionalOnProperty(
        name = "features.analytics.enabled",
        havingValue = "true"
    )
    public AnalyticsService analyticsService() {
        return new GoogleAnalyticsService();
    }
    
    @Bean
    @ConditionalOnMissingBean(AnalyticsService.class)
    public AnalyticsService noopAnalyticsService() {
        return new NoopAnalyticsService();
    }
}
```

### 4.2 调试与排查

#### 启用条件注解调试
```yaml
# application.yml
logging:
  level:
    org.springframework.boot.autoconfigure: DEBUG
    org.springframework.boot.autoconfigure.condition: TRACE
```

#### 查看条件评估报告
```java
@Component
public class ConditionReport implements ApplicationRunner {
    
    private final AutoConfigurationReport report;
    
    public ConditionReport(AutoConfigurationMetadata autoConfigurationMetadata) {
        this.report = AutoConfigurationReport.load(
            autoConfigurationMetadata, 
            getClass().getClassLoader()
        );
    }
    
    @Override
    public void run(ApplicationArguments args) {
        report.getConditionAndOutcomesBySource()
            .forEach((source, outcomes) -> {
                System.out.println("Source: " + source);
                outcomes.forEach(outcome -> 
                    System.out.println("  Outcome: " + outcome)
                );
            });
    }
}
```

## 5. 注意事项与常见问题

### 5.1 加载顺序问题
- 条件注解的评估发生在Bean定义阶段，而非Bean实例化阶段
- 使用`@AutoConfigureOrder`或`@Order`控制配置类加载顺序

### 5.2 循环依赖风险
```java
// 错误示例：可能产生循环依赖
@Configuration
public class ProblematicConfiguration {
    
    @Bean
    @ConditionalOnBean(ServiceB.class)  // 依赖ServiceB
    public ServiceA serviceA() {
        return new ServiceA();
    }
    
    @Bean
    @ConditionalOnBean(ServiceA.class)  // 依赖ServiceA
    public ServiceB serviceB() {
        return new ServiceB();
    }
}
```

### 5.3 条件注解的继承性
- 条件注解在父类上声明时，子类不会自动继承
- 每个配置类需要显式声明自己的条件

## 6. 性能优化建议

1. **减少条件评估开销**：避免在条件判断中执行复杂操作
2. **合理使用缓存**：Spring会缓存条件评估结果
3. **避免过度使用**：只在必要时使用条件注解
4. **注意条件顺序**：将最可能失败的条件放在前面

## 7. 版本兼容性说明

| Spring Boot版本 | 重要特性 |
|----------------|----------|
| 1.x | 基础条件注解支持 |
| 2.0+ | 新增`@ConditionalOnWebApplication(type)` |
| 2.1+ | 改进条件评估性能 |
| 2.4+ | 新增`@ConditionalOnWarDeployment` |

## 8. 总结

Spring Boot条件注解是自动配置的核心机制，合理使用可以：
- 实现灵活的配置管理
- 支持多环境部署
- 避免Bean冲突
- 提高应用可维护性

建议在实际项目中根据具体需求选择合适的条件注解，并遵循最佳实践以确保配置的清晰性和可维护性。

---
**文档版本**: 1.0  
**最后更新**: 2024年1月  
**适用版本**: Spring Boot 2.0+