# Spring Boot 外部化配置加载顺序（PropertySource 优先级）

## 1. 概述

Spring Boot 支持丰富的外部化配置机制，允许应用通过多种方式获取配置属性。这些配置源按照**特定顺序**加载，形成优先级层次结构，高优先级的配置会覆盖低优先级的配置。

## 2. 配置加载顺序（优先级从高到低）

### 2.1 最高优先级：开发者工具全局设置（Devtools global settings）
- 位置：`$HOME/.config/spring-boot/` 目录下的 `spring-boot-devtools.properties`
- 仅在 Spring Boot DevTools 启用时生效
- 主要用于开发环境的全局配置

### 2.2 测试环境配置
- 通过 `@TestPropertySource` 注解在测试类上定义
- 仅在测试环境下生效
- 示例：
```java
@TestPropertySource(properties = {"server.port=8081"})
```

### 2.3 命令行参数（Command Line Arguments）
- 启动应用时通过命令行传递
- 格式：`--propertyName=value` 或 `--propertyName value`
- 示例：
```bash
java -jar app.jar --server.port=9090 --spring.profiles.active=prod
```

### 2.4 SPRING_APPLICATION_JSON 属性
- 通过环境变量或系统属性设置 JSON 格式的配置
- 示例：
```bash
SPRING_APPLICATION_JSON='{"server":{"port":9090}}' java -jar app.jar
```

### 2.5 ServletConfig 初始化参数
- 适用于 Web 应用，在 `web.xml` 或 Servlet 初始化中配置

### 2.6 ServletContext 初始化参数
- Web 应用的上下文参数

### 2.7 JNDI 属性
- 从 Java 命名和目录接口获取
- 格式：`java:comp/env/`

### 2.8 Java 系统属性（System.getProperties()）
- 通过 `-D` 参数传递
- 示例：
```bash
java -Dserver.port=8081 -jar app.jar
```

### 2.9 操作系统环境变量
- 操作系统的环境变量
- Spring Boot 会自动将下划线转换为点，大写转换为小写
- 示例：`SERVER_PORT` 对应 `server.port`

### 2.10 RandomValuePropertySource
- 仅包含 `random.*` 属性
- 用于生成随机值

### 2.11 Profile-specific 配置文件（application-{profile}.properties/yml）
- 激活特定 profile 时加载
- 优先级：先加载 `.yml` 再加载 `.properties`
- 示例：`application-prod.properties`

### 2.12 打包在 jar 外的 Profile-specific 配置文件
- 位于 jar 文件同级目录或子目录
- 路径：`./config/application-{profile}.properties`

### 2.13 打包在 jar 内的 Profile-specific 配置文件
- 位于 classpath 下的 `application-{profile}.properties`

### 2.14 应用配置文件（application.properties/yml）
- 应用主配置文件
- 优先级：先加载 `.yml` 再加载 `.properties`

### 2.15 打包在 jar 外的应用配置文件
- 位于 jar 文件同级目录或子目录
- 加载顺序（从高到低）：
    1. 当前目录的 `/config` 子目录
    2. 当前目录
    3. classpath 下的 `/config` 包
    4. classpath 根目录

### 2.16 打包在 jar 内的应用配置文件
- 位于 classpath 下

### 2.17 @PropertySource 注解
- 通过 `@PropertySource` 注解加载自定义配置文件
- 在 `@Configuration` 类上使用
- 示例：
```java
@Configuration
@PropertySource("classpath:custom.properties")
public class AppConfig { }
```

### 2.18 默认属性（SpringApplication.setDefaultProperties）
- 通过 `SpringApplication.setDefaultProperties()` 设置的默认属性
- 最低优先级

## 3. 特殊配置源说明

### 3.1 YAML 文件
- 支持多文档块（通过 `---` 分隔）
- 支持 profile-specific 配置在同一文件中
- 示例：
```yaml
server:
  port: 8080
---
spring:
  profiles: dev
server:
  port: 8081
```

### 3.2 属性占位符
- 支持在配置文件中使用占位符
- 示例：
```properties
app.name=MyApp
app.description=${app.name} is a Spring Boot application
```

### 3.3 类型安全配置属性（@ConfigurationProperties）
- 将属性绑定到 Java Bean
- 支持嵌套属性、集合、映射等复杂类型

## 4. Profile 机制

### 4.1 激活 Profile
- 通过配置 `spring.profiles.active`
- 多种激活方式：
    - 配置文件
    - 命令行参数
    - 环境变量
    - JVM 系统属性

### 4.2 默认 Profile
- 通过 `spring.profiles.default` 设置
- 当没有激活任何 profile 时使用

### 4.3 Profile 文档（YAML）
- YAML 文件支持多 profile 配置

## 5. 配置优先级示例

### 场景分析
假设有以下配置源：
1. 命令行：`--server.port=9090`
2. 系统属性：`-Dserver.port=8081`
3. `application.properties`：`server.port=8080`
4. `application-prod.properties`：`server.port=8082`

激活 prod profile 时，最终 `server.port` 值为 **9090**（命令行参数优先级最高）

## 6. 调试与查看配置

### 6.1 查看所有属性源
```bash
# 启用调试日志
java -jar app.jar --debug

# 或在 application.properties 中
debug=true
```

### 6.2 Actuator Endpoints
- `/actuator/env`：显示所有属性源及其属性
- `/actuator/configprops`：显示 `@ConfigurationProperties` 绑定的属性

### 6.3 编程方式查看
```java
@Autowired
private Environment environment;

// 获取所有属性源
environment.getPropertySources().forEach(ps -> {
    System.out.println(ps.getName() + ": " + ps.getSource());
});
```

## 7. 最佳实践建议

1. **敏感信息管理**
   - 生产环境密码、密钥等不应放在版本控制中
   - 使用环境变量或专用配置服务器

2. **配置组织策略**
   - 通用配置放在 `application.properties`
   - 环境特定配置使用 profile-specific 文件
   - 应用特定配置使用自定义 properties 文件

3. **优先级利用**
   - 使用命令行参数进行临时覆盖
   - 使用环境变量进行容器化部署配置

4. **配置验证**
   - 使用 `@Validated` 和 `@ConfigurationProperties` 进行配置验证
   - 利用 Spring Boot 的配置元数据生成提示

## 8. 总结

Spring Boot 的配置加载顺序设计提供了极大的灵活性：
- **高优先级配置**适合临时覆盖和敏感信息
- **Profile 机制**支持多环境部署
- **多种格式支持**满足不同需求
- **可扩展性**允许自定义配置源

理解这一优先级体系对于正确管理应用配置、实现多环境部署和安全配置管理至关重要。

---

**附录：配置源优先级速查表**

| 优先级 | 配置源 | 说明 |
|--------|--------|------|
| 1 | Devtools 全局设置 | 仅开发环境 |
| 2 | @TestPropertySource | 仅测试环境 |
| 3 | 命令行参数 | 启动时动态指定 |
| 4 | SPRING_APPLICATION_JSON | JSON 格式配置 |
| 5-8 | Servlet/JNDI 相关 | Web 应用专用 |
| 9 | Java 系统属性 | -D 参数 |
| 10 | 操作系统环境变量 | 系统环境变量 |
| 11 | RandomValuePropertySource | 随机值 |
| 12-16 | Profile-specific 文件 | 按位置分层 |
| 17-20 | 主配置文件 | 按位置分层 |
| 21 | @PropertySource | 自定义配置文件 |
| 22 | 默认属性 | 最低优先级 |

*注：完整列表请参考 Spring Boot 官方文档，不同版本可能有细微差异。*