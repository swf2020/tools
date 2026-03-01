## **Sentinel 集群限流技术文档（Token Server 模式）**

### **1. 概述**

在高并发、分布式的微服务架构中，单机限流无法解决集群流量总和超过系统总体承载能力的问题。例如，某个API的集群QPS阈值为1000，若均匀分布在10个节点，单机限流100 QPS是合理的。但如果流量分配不均，可能出现部分节点空闲而部分节点超载的情况，导致总体服务不可用。

Sentinel 的**集群限流**功能旨在通过统一的规则和协调机制，对跨多个服务实例的流量总和进行精准控制。**Token Server 模式**是 Sentinel 实现集群限流的核心模式之一，它通过一个中心化的 Server 节点来统一管理令牌（Token），实现全局流量的精确调控。

### **2. 核心概念**

*   **Token Server（令牌服务器）**： 一个独立的 Sentinel 服务端组件，负责管理全局的令牌桶。它接收来自各个客户端的令牌请求，根据配置的集群规则决定是否发放令牌。
*   **Token Client（令牌客户端）**： 集成了 Sentinel 客户端并启用了集群限流功能的微服务实例。在需要执行限流检查时，它会向 Token Server 发起远程调用申请令牌。
*   **集群规则（ClusterRule）**： 定义在 Token Server 上的限流规则，指定了受保护的资源、全局的QPS阈值、流控模式等。
*   **令牌（Token）**： 代表一个允许通过的请求许可。Token Server 根据规则以固定的速率生成令牌，客户端获取到令牌则请求被放行，否则被限流。

### **3. 架构与工作原理**

#### **3.1 架构图**
```
+-------------------+      Request Token       +-------------------+
|  微服务实例 A       | ----------------------> |                   |
|  (Token Client 1)  |                          |   Token Server    |
+-------------------+                          |  (Sentinel Server)|
                                                |                   |
+-------------------+      Request Token       |  • 集群规则管理    |
|  微服务实例 B       | ----------------------> |  • 令牌桶维护     |
|  (Token Client 2)  |                          |  • 请求仲裁       |
+-------------------+                          +-------------------+
          |                                              ^
          |                                              | 规则推送/心跳
          |                                      +-------------------+
          +------------------------------------> |  配置中心/注册中心 |
                注册/发现                          |  (如 Nacos)      |
                                                 +-------------------+
```

#### **3.2 工作流程**
1.  **初始化与发现**：
    *   Token Server 启动，将自己注册到配置中心（如Nacos），并加载配置的集群限流规则。
    *   Token Client 启动，从配置中心获取或通过静态配置知晓 Token Server 的地址。

2.  **请求处理流程**：
    1.  用户请求到达 **Token Client** 的受保护资源（如一个API接口）。
    2.  Client 端的 Sentinel 根据资源名查找对应的**集群限流规则**。
    3.  Client 通过预先配置的 **ClusterTransport** 向 **Token Server** 发送一个请求令牌的 RPC 调用。
    4.  **Token Server** 接收到请求后：
        *   根据资源名查找对应的全局令牌桶。
        *   检查当前令牌桶中是否有可用令牌。
        *   如果有，则扣除一个令牌，并向 Client 返回 `PASS` 的信号。
        *   如果无令牌（即全局QPS已耗尽），则向 Client 返回 `BLOCKED` 的信号。
        *   如果与 Server 通信失败，Client 会执行预设的**失败降级策略**（如快速失败或本地降级）。
    5.  **Token Client** 根据 Server 的响应决定请求的命运：
        *   `PASS` -> 放行请求，执行后续业务逻辑。
        *   `BLOCKED` -> 立即触发流控异常，返回给调用方。

### **4. 配置与使用**

#### **4.1 依赖引入**
确保所有 Token Client 和 Token Server 项目中引入集群限流模块依赖（以 Maven 为例）。
```xml
<!-- Sentinel 核心依赖 -->
<dependency>
    <groupId>com.alibaba.csp</groupId>
    <artifactId>sentinel-core</artifactId>
    <version>1.8.6</version>
</dependency>
<!-- 集群限流客户端依赖 -->
<dependency>
    <groupId>com.alibaba.csp</groupId>
    <artifactId>sentinel-cluster-client-default</artifactId>
    <version>1.8.6</version>
</dependency>
<!-- 集群限流服务端依赖 (仅 Token Server 需要) -->
<dependency>
    <groupId>com.alibaba.csp</groupId>
    <artifactId>sentinel-cluster-server-default</artifactId>
    <version>1.8.6</version>
</dependency>
<!-- 可选：使用 Nacos 作为规则数据源和 Server 发现 -->
<dependency>
    <groupId>com.alibaba.csp</groupId>
    <artifactId>sentinel-datasource-nacos</artifactId>
    <version>1.8.6</version>
</dependency>
```

#### **4.2 Token Server 配置**
**启动类配置：**
```java
@SpringBootApplication
public class TokenServerApplication {
    public static void main(String[] args) {
        // 1. 初始化 Server 功能
        ClusterTokenServer tokenServer = new SentinelDefaultTokenServer();
        // 2. 配置 Server 属性 (例如端口)
        ClusterServerConfigManager.loadServerNamespaceSet(Collections.singleton("my-app-group")); // 命名空间，用于隔离
        // 3. 启动 Server
        tokenServer.start();
    }
}
```
**通过配置文件 (`application.yml`)：**
```yaml
spring:
  application:
    name: sentinel-token-server
server:
  port: 18730 # Sentinel 默认的 Token Server 端口

sentinel:
  transport:
    dashboard: localhost:8080 # Sentinel Dashboard 地址，用于监控
  # 集群服务器配置
  cluster-server:
    # 配置server的命名空间集合，client只有匹配才能连接
    server-namespace-set:
      - my-app-group
    # 端口
    port: 18730
    # 闲置超时时间（毫秒），超时后关闭空闲连接
    idle-seconds: 600
```

#### **4.3 Token Client 配置**
**启动类配置：**
```java
@SpringBootApplication
public class MyServiceApplication {
    @PostConstruct
    public void initClusterClient() {
        // 1. 注册集群组 (必须与 Server 的 namespace 匹配)
        ClusterClientConfig clientConfig = new ClusterClientConfig();
        clientConfig.setServerHost("localhost");
        clientConfig.setServerPort(18730);
        clientConfig.setRequestTimeout(100); // 请求超时时间
        ClusterClientConfigManager.applyNewConfig(clientConfig);
        ClusterClientConfigManager.registerServerAssignProperty((source) -> "my-app-group");

        // 2. 配置动态规则源（例如从Nacos读取集群规则）
        ReadableDataSource<String, List<FlowRule>> ruleSource = new NacosDataSource<>(...);
        FlowRuleManager.register2Property(ruleSource.getProperty());
    }
    public static void main(String[] args) {
        SpringApplication.run(MyServiceApplication.class, args);
    }
}
```
**通过配置文件 (`application.yml`)：**
```yaml
sentinel:
  transport:
    dashboard: localhost:8080
    port: 8719
  # 集群客户端配置
  cluster-client:
    # 指定要连接的 Token Server 地址
    server-addr:
      - localhost:18730
    # 与 Server 端一致的命名空间
    namespace: my-app-group
    # 请求超时时间
    request-timeout: 100
```

#### **4.4 定义集群限流规则**
规则可以通过代码、Dashboard 或配置中心（推荐）动态下发。规则的关键是设置 `clusterMode` 为 `true` 并指定 `clusterConfig`。
```java
// 示例：代码定义一条集群限流规则
FlowRule rule = new FlowRule();
rule.setResource("GET:/api/v1/test");
rule.setGrade(RuleConstant.FLOW_GRADE_QPS);
rule.setCount(100); // **全局** QPS 阈值为 100
rule.setClusterMode(true); // ！！！开启集群模式！！！

// 集群特定配置
ClusterFlowConfig clusterConfig = new ClusterFlowConfig();
clusterConfig.setFlowId(123456L); // 全局唯一的规则ID，非常重要
clusterConfig.setThresholdType(ClusterRuleConstant.FLOW_THRESHOLD_GLOBAL);
clusterConfig.setFallbackToLocalWhenFail(true); // 与Server通信失败时是否降级到本地限流
rule.setClusterConfig(clusterConfig);

FlowRuleManager.loadRules(Collections.singletonList(rule));
```

### **5. 容错与降级**

*   **网络故障/Server宕机**： 通过 `fallbackToLocalWhenFail` 配置。若为 `true`，Client 在无法联系 Server 时，会临时退化为使用本地单机限流规则（需额外配置）或直接放行（取决于配置），保证服务可用性。
*   **Client 启动时 Server 不可用**： Client 会持续重试连接，直至成功。
*   **Server 扩容/重启**： 新的 Server 启动后，Client 需要重新建立连接。Server 重启后令牌桶状态会重置，可能引起瞬间的流量波动，生产环境建议配合 warm-up 规则使用。

### **6. 监控与管理**

*   **Sentinel Dashboard**： 可以实时查看集群限流规则、各个 Client 和 Server 的运行状态、通过的QPS、阻塞的请求数等关键指标。
*   **日志**： Sentinel 会输出详细的集群限流相关日志，包括令牌申请、规则更新、连接状态等，便于问题排查。
*   **Metrics**： 所有集群限流的指标都会通过 Sentinel 的指标系统暴露，可以集成到 Prometheus 等监控系统中。

### **7. 最佳实践与注意事项**

1.  **性能考量**： Token Server 可能成为性能和单点故障的瓶颈。务必确保 Token Server 本身高可用（可部署多个，但需注意规则同步和状态共享问题，通常一主多备或使用有状态中间件）。网络延迟也会增加限流判断的耗时。
2.  **规则ID唯一性**： `flowId` 必须在全局唯一，通常由规则管理系统统一分配。
3.  **生产环境部署**：
    *   Token Server 建议独立部署，与业务应用隔离。
    *   为 Token Server 配置足够的资源（CPU、内存、网络）。
    *   使用 VIP 或服务发现（如Nacos）对 Token Server 进行负载均衡和故障转移。
4.  **测试**： 上线前必须充分测试集群限流功能，包括模拟 Server 宕机、网络分区、突发流量等场景。
5.  **配合使用**： 集群限流通常与**单机限流**、**熔断降级**、**系统自适应保护**等 Sentinel 其他功能结合使用，构建多层次、立体化的防护体系。

### **8. 总结**

Sentinel 的 Token Server 集群限流模式提供了一种中心化、强一致的全局流量控制方案，非常适合需要对全集群流量进行精确配额管理的场景。它通过清晰的职责分离（Client/Server）和灵活的配置，在保证防护能力的同时，也提供了必要的容错机制。成功实施的关键在于合理的架构设计、正确的配置以及对可能故障场景的充分预案。