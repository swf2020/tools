# 面向切面编程（AOP）技术学习文档

---

## 0. 定位声明

```
适用版本：
  - Java/Spring AOP：Spring Framework 6.x，JDK 17+
  - AspectJ：1.9.x
  - 代码示例以 Spring AOP + AspectJ 注解风格为主

前置知识：
  - 理解面向对象编程（OOP）基本概念（类、继承、多态）
  - 了解设计模式中的代理模式（Proxy Pattern）
  - 基础 Java 语法

不适用范围：
  - 本文不覆盖编译时织入（compile-time weaving）的深度 JVM 字节码原理
  - 不适用于 AspectJ 独立使用（非 Spring 环境）的完整工程配置
  - 不覆盖 .NET 平台（PostSharp 等）的 AOP 实现
```

---

## 1. 一句话本质

**无术语版**：你写了很多函数，每个函数开始和结束时都要打日志、检查权限、记录时间——这些重复的"琐事"和业务逻辑混在一起，既难看又难改。AOP 就是一种方法，让你把这些"琐事"单独写在一个地方，然后自动"插入"到每个函数里，你的业务代码就只负责业务，干净清爽。

**正式版**：面向切面编程（Aspect-Oriented Programming，AOP）是一种编程范式，通过将**横切关注点**（Cross-Cutting Concerns，如日志、安全、事务）从业务逻辑中分离，以声明式的方式动态织入目标对象的执行流程，实现关注点的模块化。

---

## 2. 背景与根本矛盾

### 历史背景

1997 年，Xerox PARC 的 Gregor Kiczales 团队在研究 OOP 局限性时，发现了一类 OOP 难以优雅解决的问题：**横切关注点**（Cross-Cutting Concerns）。

OOP 擅长纵向的业务逻辑分解（用户模块、订单模块），但对于"每个模块都需要的日志记录、权限校验、事务管理"，OOP 只能选择继承（层次太深，僵化）或工具类（每个地方手动调用，代码散落各处，改一个点要改几十个文件）。

1995 年 Java 兴起，企业级开发中这一问题被急剧放大。Kiczales 团队于 2001 年发布 **AspectJ**，这是第一个成熟的 AOP 语言扩展。2003 年 Spring 1.0 将 AOP 引入主流 Java 开发生态。

### 根本矛盾（Trade-off）

| 维度 | 矛盾 |
|------|------|
| **内聚性 vs 侵入性** | 业务代码高内聚（只写业务）**vs** 横切逻辑必须在某处执行（无法凭空消失） |
| **透明性 vs 可追踪性** | 开发者感知不到切面的存在（透明插入）**vs** 调试时行为难以溯源（"我明明没写日志，日志从哪来的？"） |
| **编译时安全 vs 运行时灵活** | 编译时织入（AspectJ compile-time weaving）：性能好，但灵活性低 **vs** 运行时动态代理（Spring AOP）：灵活，但有运行时开销 |
| **功能强大 vs 理解成本** | 切点表达式（Pointcut）可以精确匹配任意方法 **vs** 过于复杂的切点导致误切，难以维护 |

**核心 Trade-off 一句话**：AOP 用"代码执行流程的可预测性"换取了"横切关注点的集中管理"。

---

## 3. 核心概念与领域模型

### 3.1 关键术语表

| 概念 | 费曼式定义 | 正式定义 |
|------|------------|----------|
| **Aspect（切面）** | 把"日志记录"这件事单独封装成一个模块 | 横切关注点的模块化封装，包含 Pointcut 和 Advice |
| **Join Point（连接点）** | 程序运行中所有"可以插入代码的地方"，比如每个方法的调用前、调用后 | 程序执行过程中的特定点，AOP 框架可在此处插入 Advice |
| **Pointcut（切点）** | 从所有可插入的地方中，用规则筛选出"我要在哪些地方插入" | 定义 Advice 应用于哪些 Join Point 的表达式谓词 |
| **Advice（通知/增强）** | 真正要插入的那段代码（比如打印日志的代码） | 在特定 Join Point 执行的动作，定义了"做什么"和"何时做" |
| **Weaving（织入）** | 把你写的"插入代码"实际放进目标程序的过程 | 将 Aspect 应用到目标对象，创建代理对象的过程 |
| **Target Object（目标对象）** | 被"插入代码"的那个原始对象 | 被一个或多个 Aspect 增强的对象，也称 Advised Object |
| **Proxy（代理对象）** | 替代目标对象出现的"中间人"，外界看不出区别，但它会先执行切面逻辑 | 由 AOP 框架创建的对象，用于实现 Aspect 合约 |
| **Introduction（引入）** | 给一个已有的类"偷偷加上"它原本没有的接口和方法 | 在不修改类代码的情况下，为类添加新方法或属性 |

### 3.2 Advice 类型详解

```
Advice 按执行时机分为 5 种：

Before Advice     ──→ 方法执行前
                       │
After Returning   ──→ 方法正常返回后
After Throwing    ──→ 方法抛出异常后
After (Finally)   ──→ 方法结束后（无论正常还是异常）
Around Advice     ──→ 包裹整个方法执行（最强大，也最危险）
```

### 3.3 领域模型

```
┌─────────────────────────────────────────────────────┐
│                     AOP 领域模型                      │
│                                                       │
│  ┌──────────┐       定义        ┌──────────────────┐  │
│  │  Aspect  │ ──────────────→  │    Pointcut      │  │
│  │  (切面)  │                  │  (切点表达式)     │  │
│  │          │ ──────────────→  │    Advice        │  │
│  └──────────┘       包含        │  (增强逻辑)      │  │
│                                └────────┬─────────┘  │
│                                         │ 匹配        │
│                                         ▼             │
│  ┌──────────┐  Weaving   ┌─────────────────────────┐ │
│  │  Target  │ ─────────→ │      Join Points        │ │
│  │  Object  │            │  (方法调用、字段访问等)  │ │
│  └──────────┘            └─────────────────────────┘ │
│        │                           │                  │
│        └──────── 生成 ─────────────▼                  │
│                            ┌───────────┐              │
│                            │   Proxy   │              │
│                            │  Object   │ ← 客户端调用  │
│                            └───────────┘              │
└─────────────────────────────────────────────────────┘
```

---

## 4. 对比与选型决策

### 4.1 AOP 实现方式横向对比

| 实现方式 | 代表技术 | 织入时机 | 支持 Join Point | 性能开销 | 适用场景 |
|----------|----------|----------|-----------------|----------|----------|
| **编译时织入** | AspectJ (ajc) | 编译期 | 方法、字段、构造器、静态初始化 | 几乎为零 | 性能敏感，需要全功能 AOP |
| **类加载时织入** | AspectJ LTW | 类加载期 | 同上 | 极小 | 无法修改源码的第三方库 |
| **JDK 动态代理** | Spring AOP（接口代理） | 运行时 | 仅接口方法 | 低（⚠️约 10-30ns/次，存疑） | Spring Bean，目标类实现了接口 |
| **CGLIB 代理** | Spring AOP（类代理） | 运行时 | 非 final 方法 | 低-中（⚠️约 20-50ns/次，存疑） | Spring Bean，目标类无接口 |
| **字节码增强** | ByteBuddy、Javassist | 运行时/加载时 | 灵活 | 中（有字节码生成开销） | APM Agent（如 SkyWalking） |

### 4.2 选型决策树

```
你的场景是什么？
│
├─ 在 Spring 应用中拦截 Bean 方法调用
│   ├─ 目标类实现了接口 → JDK 动态代理（Spring AOP 默认）
│   └─ 目标类没有接口 → CGLIB 代理（Spring AOP 自动切换）
│
├─ 需要拦截字段访问、构造器、静态方法
│   └─ 必须用 AspectJ（Spring AOP 不支持）
│
├─ 需要对第三方库（无源码）进行增强
│   └─ AspectJ LTW 或字节码增强（ByteBuddy）
│
├─ 开发 APM/链路追踪 Agent（Java Agent）
│   └─ ByteBuddy + Java Instrumentation API
│
└─ 不要使用 AOP 的场景：
    - 切面逻辑比业务逻辑更复杂时（引入的复杂度 > 解决的复杂度）
    - 需要非常清晰的调用栈追踪（AOP 会使调试变困难）
    - 团队对 AOP 不熟悉的小项目（直接调用工具方法更直白）
```

### 4.3 与上下游技术的配合关系

```
业务代码（Service）
      │
      ▼
Spring AOP（运行时代理层）
      │
      ├──→ 事务管理（@Transactional）───→ 数据库连接池
      ├──→ 安全校验（Spring Security）──→ 认证中心
      ├──→ 缓存控制（@Cacheable）──────→ Redis
      ├──→ 日志/监控（Micrometer）─────→ Prometheus/Grafana
      └──→ 链路追踪（SkyWalking Agent）→ ES/Zipkin
```

---

## 5. 工作原理与实现机制

### 5.1 静态结构

**Spring AOP 核心组件**：

```
org.springframework.aop
├── Advisor              # 切面的最小单元：一个 Pointcut + 一个 Advice
├── Pointcut             # 切点接口（ClassFilter + MethodMatcher）
├── Advice               # 增强接口（Before/After/Around 等）
├── AopProxy             # 代理对象接口（JdkDynamicAopProxy / CglibAopProxy）
├── ProxyFactory         # 编程式创建代理的工厂
└── DefaultAdvisorChainFactory  # 负责将多个 Advisor 排序成拦截器链
```

**关键数据结构 — 拦截器链（Interceptor Chain）**：

Spring AOP 将匹配到某个方法的所有 Advisor 转换为 `MethodInterceptor` 列表，形成**责任链**。选择责任链而非 if-else 嵌套的原因：支持动态添加/删除切面；每个拦截器只关心自己的逻辑；Around Advice 通过 `proceed()` 控制链的继续执行，天然支持"短路"。

### 5.2 动态行为：代理调用时序

**以 JDK 动态代理为例**：

```
客户端                JdkDynamicAopProxy        目标对象
   │                        │                      │
   │  proxy.doService()     │                      │
   │───────────────────────→│                      │
   │                        │                      │
   │                  invoke() 被触发              │
   │                        │                      │
   │               获取拦截器链                    │
   │              (AdvisorChainFactory)             │
   │                        │                      │
   │            ┌───────────────────────┐          │
   │            │  ReflectiveMethodInvocation       │
   │            │  执行拦截器链：                   │
   │            │  1. Before Advice 执行            │
   │            │  2. Around Advice 前半段          │
   │            │  3. proceed() ──────────────────→│
   │            │                     目标方法执行  │
   │            │  4. Around Advice 后半段 ←───────│
   │            │  5. After Returning Advice        │
   │            └───────────────────────┘          │
   │                        │                      │
   │←───────────────────────│                      │
   │   返回结果              │                      │
```

### 5.3 CGLIB 代理原理

CGLIB（Code Generation Library）通过在运行时**生成目标类的子类**，重写非 final 方法，在子类方法中插入拦截逻辑。这就是为什么 `final` 类和 `final` 方法无法被 CGLIB 代理。

### 5.4 关键设计决策

**决策 1：为什么 Spring AOP 只支持方法级别 Join Point？**

AspectJ 支持字段、构造器等更细粒度的 Join Point。Spring 选择"只支持方法调用"的原因：简化实现（动态代理天然以方法为粒度）、满足 80% 的生产需求、避免过度复杂的切点表达式带来的维护噩梦。Trade-off：功能受限，但学习成本低、行为可预测。

**决策 2：为什么 Around Advice 要用 `proceed()` 而不是直接调用目标方法？**

`proceed()` 调用的是"拦截器链的下一个节点"，不一定是目标方法本身。这保证了多个 Around Advice 可以正确嵌套，每个 Around 都能控制"是否继续执行下一层"。如果直接调用目标方法，则多个 Around Advice 无法形成正确的嵌套层次。

**决策 3：自调用（Self-Invocation）为何无法被 AOP 拦截？**

```java
// 在同一个 Bean 内部：
public void methodA() {
    this.methodB(); // ❌ 直接调用 this，绕过了代理对象，AOP 不生效
}
```

因为 AOP 是通过代理对象实现的，`this` 指向的是目标对象本身而非代理。解决方案：注入自身 Bean 或使用 `AopContext.currentProxy()`。

---

## 6. 高可靠性保障

> 说明：AOP 本身是编程范式而非分布式系统，"高可靠性"维度重点关注**切面代码对系统稳定性的影响**。

### 6.1 切面失效对系统的影响隔离

| 场景 | 风险 | 防护手段 |
|------|------|----------|
| Advice 内抛出未捕获异常 | 可能中断业务请求 | Around Advice 必须 try-catch，明确异常处理策略 |
| 切点表达式过于宽泛 | 意外拦截第三方库方法导致性能问题 | 切点要精确到包路径，必须排除框架内部类 |
| 切面顺序混乱 | 事务切面在安全校验之前执行，导致未授权操作被提交 | 使用 `@Order` 显式定义切面优先级 |
| 循环依赖 + AOP | 导致 Bean 创建失败 | 避免切面 Bean 与目标 Bean 相互依赖 |

### 6.2 可观测性

| 监控指标 | 采集方式 | 正常阈值 |
|----------|----------|----------|
| 方法调用耗时 P99 | Around Advice + Micrometer Timer | 依业务而定，通常 < 200ms |
| 切面初始化时间 | Spring Actuator startup endpoint | ⚠️ 存疑：< 500ms（切面数量 < 50，未验证） |
| 代理对象创建数量 | JVM 内存分析 | 不应无限增长 |

### 6.3 事务切面的 SLA 保障重点

`@Transactional` 是最重要的内置 AOP 切面，生产保障要点：事务超时必须设置（`timeout` 参数，建议 ≤ 30s）；只读事务显式声明 `readOnly=true`，减少锁竞争；长事务告警阈值建议设为 5s。

---

## 7. 使用实践与故障手册

### 7.1 典型使用方式

**环境**：Spring Boot 3.2+，JDK 17，AspectJ 1.9.x

#### 基础示例：统一日志切面

```java
// 运行环境：Spring Boot 3.2+，JDK 17+
@Aspect
@Component
@Slf4j
public class LoggingAspect {

    // 切点：拦截 com.example.service 包下所有 public 方法
    // 注意：不要用 com..* 这种过于宽泛的表达式！
    @Pointcut("execution(public * com.example.service..*(..))")
    public void serviceLayer() {}

    // Around Advice：记录入参、出参、耗时、异常
    @Around("serviceLayer()")
    public Object logAround(ProceedingJoinPoint joinPoint) throws Throwable {
        String methodName = joinPoint.getSignature().toShortString();
        Object[] args = joinPoint.getArgs();
        
        long start = System.currentTimeMillis();
        try {
            log.info("[AOP] 调用方法: {}, 入参: {}", methodName, Arrays.toString(args));
            Object result = joinPoint.proceed(); // 继续执行目标方法
            long cost = System.currentTimeMillis() - start;
            log.info("[AOP] 方法: {}, 耗时: {}ms, 返回: {}", methodName, cost, result);
            return result;
        } catch (Throwable e) {
            long cost = System.currentTimeMillis() - start;
            log.error("[AOP] 方法: {}, 耗时: {}ms, 异常: {}", methodName, cost, e.getMessage());
            throw e; // 必须重新抛出，不要吞掉异常！
        }
    }
}
```

#### 生产级示例：自定义注解 + 幂等校验切面

```java
// 运行环境：Spring Boot 3.2+，JDK 17+，Spring Data Redis

// 1. 定义注解
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface Idempotent {
    int expireSeconds() default 60;
}

// 2. 实现切面
@Aspect
@Component
@RequiredArgsConstructor
public class IdempotentAspect {

    private final RedisTemplate<String, String> redisTemplate;

    @Around("@annotation(idempotent)")
    public Object checkIdempotent(ProceedingJoinPoint joinPoint,
                                   Idempotent idempotent) throws Throwable {
        String idempotentKey = RequestContextHolder.getIdempotentKey();
        String redisKey = "idempotent:" + idempotentKey;
        
        // 使用 Redis SETNX 保证原子性
        Boolean isFirstCall = redisTemplate.opsForValue()
            .setIfAbsent(redisKey, "1", idempotent.expireSeconds(), TimeUnit.SECONDS);
        
        if (Boolean.FALSE.equals(isFirstCall)) {
            throw new IdempotentException("重复请求，请勿重试");
        }
        
        try {
            return joinPoint.proceed();
        } catch (Throwable e) {
            // 业务异常时删除 key，允许重试
            redisTemplate.delete(redisKey);
            throw e;
        }
    }
}

// 3. 使用方式（业务代码无任何幂等逻辑，干净清爽）
@Service
public class OrderService {
    @Idempotent(expireSeconds = 120)
    public OrderResult createOrder(CreateOrderRequest request) {
        // 纯业务逻辑
    }
}
```

#### 关键配置项

```yaml
# application.yml
spring:
  aop:
    # 强制使用 CGLIB 代理，Spring Boot 3.x 已默认为 true
    # 优点：避免接口/类代理混用问题；缺点：启动时额外字节码生成开销
    proxy-target-class: true
    auto: true  # 默认 true，勿关闭
```

### 7.2 故障模式手册

```
【故障 1：AOP 切面对同类内部方法调用不生效】
- 现象：A 方法调用同类的 B 方法，B 上的 @Transactional 或自定义注解不起作用
- 根本原因：Spring AOP 基于代理实现，this.B() 绕过代理直接调用目标对象
- 预防措施：代码规范中明确禁止同类内部方法间的注解依赖；单元测试验证切面行为
- 应急处理：
  方案1（推荐）：将 B 方法移到独立的 Bean 中
  方案2：注入自身：@Autowired private OrderService self; self.methodB()
  方案3：AopContext.currentProxy()（需开启 exposeProxy=true，不推荐）
```

```
【故障 2：@Transactional 注解在 private 方法上不生效】
- 现象：标注了 @Transactional 的 private 方法，事务不开启
- 根本原因：代理只能重写 public/protected 方法（CGLIB 限制），private 不被拦截
- 预防措施：IDE 插件警告（IntelliJ IDEA 会提示）；代码审查
- 应急处理：将方法改为 public；或使用 AspectJ 编译时织入
```

```
【故障 3：切面顺序导致事务与日志行为异常】
- 现象：日志切面打印的返回值是事务回滚前的数据
- 根本原因：多个切面的执行顺序未定义，默认顺序不确定
- 预防措施：所有切面都显式声明 @Order 值
            规范：安全(@Order(1)) > 日志(@Order(10)) > 事务(@Order(100))
- 应急处理：添加 @Order 注解并重启应用
```

```
【故障 4：CGLIB 代理导致 Bean 类型强转失败】
- 现象：ClassCastException，无法将 CGLIB 生成的代理类转为目标类型
- 根本原因：某处代码硬转 (TargetClass) applicationContext.getBean()
- 预防措施：始终通过接口类型获取 Bean；避免强制类型转换
- 应急处理：使用 AopUtils.getTargetClass(bean) 获取真实类型
```

```
【故障 5：切面意外拦截框架内部方法导致栈溢出】
- 现象：StackOverflowError，或应用启动极慢
- 根本原因：切点表达式过于宽泛（如 execution(* *(..))），拦截了框架自身方法，递归调用
- 预防措施：切点必须精确到业务包路径，如 execution(* com.example..*(..))
- 应急处理：立即回滚切面代码；检查切点表达式
```

### 7.3 边界条件与局限性

- **`final` 类/方法**：CGLIB 无法代理，Spring AOP 不支持（AspectJ 编译时织入可以）
- **静态方法**：AOP 无法拦截（代理基于实例），需用 AspectJ
- **构造方法**：Spring AOP 不支持，AspectJ 支持
- **原始类型参数**：`@Around` 中 `proceed()` 返回值为 `Object`，原始类型会自动装箱，需注意性能
- **多线程环境**：切面 Bean 是单例，避免在切面中持有可变状态（线程安全问题）
- **启动时性能**：⚠️ 存疑：Bean 数量 > 5000 时可能影响启动时间（约增加 10-30%，依系统配置而定，未验证）

---

## 8. 性能调优指南

### 8.1 性能瓶颈识别

AOP 的性能问题通常不来自代理调用本身（通常 < 1μs），而来自切面逻辑本身耗时（如日志序列化、同步写 I/O）、切点匹配开销（启动时），以及切面过多导致拦截器链过长（运行时）。

**定位方法**：

```bash
# 开启 Spring AOP 调试日志（仅用于开发环境！生产禁用）
logging.level.org.springframework.aop=DEBUG

# 使用 Arthas 在生产环境非侵入式分析（不需要重启）
# 追踪 createOrder 方法的调用链耗时，采集 5 次
trace com.example.service.OrderService createOrder -n 5
```

### 8.2 调优步骤（按优先级）

**优先级 1：精确切点，减少不必要的匹配**

```java
// ❌ 差：匹配所有类的所有方法（包括框架内部）
@Pointcut("execution(* *.*(..))")

// ✅ 好：精确到业务包
@Pointcut("execution(public * com.example.service..*Service.*(..))")
```

**优先级 2：避免在 Advice 中做同步 I/O**

```java
// ❌ 同步 JSON 序列化可能耗时 1-10ms，阻塞业务线程
log.info("请求参数: " + JsonUtils.toJson(args));

// ✅ 仅记录关键字段，使用 Logback AsyncAppender 异步写盘
log.info("方法: {}, 用户ID: {}", methodName, userId);
```

**优先级 3：使用 `@Pointcut` 复用，避免重复解析**

```java
@Pointcut("execution(public * com.example.service..*(..))")
public void serviceLayer() {}

@Before("serviceLayer()")
public void logBefore() { ... }

@AfterReturning("serviceLayer()")
public void logAfter() { ... }
```

### 8.3 调优参数速查表

| 参数/配置 | 默认值 | 推荐值 | 调整风险 |
|-----------|--------|--------|----------|
| `spring.aop.proxy-target-class` | false（Spring Boot 3.x 已改为 true） | true（统一 CGLIB） | 低 |
| Logback AsyncAppender `queueSize` | 256 | 1024-4096（高并发） | 中：增大内存占用约 4-16MB |
| `@Transactional timeout` | -1（无超时） | 30（秒） | 低：防止长事务 |
| `@Transactional readOnly` | false | true（只读操作显式声明） | 低：减少锁竞争 |

---

## 9. 演进方向与未来趋势

### 9.1 GraalVM Native Image 对 AOP 的冲击

GraalVM AOT 编译后**运行时无法生成字节码**，CGLIB 动态子类生成受限。Spring Boot 3.x 通过引入 **AOT 处理阶段**（`spring-aot-maven-plugin`），在构建时预生成代理类代码来应对。

对使用者的影响：迁移到 GraalVM Native Image（容器启动时间从秒级降至毫秒级）时，需升级到 Spring Boot 3.x，避免运行时动态注册切面，切面中避免大量反射操作。

### 9.2 服务网格（Service Mesh）对 AOP 的部分替代

| 功能 | AOP 方案 | Service Mesh 方案 |
|------|----------|-------------------|
| 链路追踪 | SkyWalking Java Agent | Envoy + Jaeger |
| 限流 | Sentinel AOP 拦截器 | Envoy Rate Limit |
| 熔断 | Resilience4j @CircuitBreaker | Istio Circuit Breaker |

**趋势**：AOP 更专注于**进程内**的横切关注点（权限、事务、业务日志），跨服务的关注点逐步下沉到基础设施层。

---

## 10. 面试高频题

```
【基础理解层】（考察概念掌握）

Q：AOP 和 OOP 的区别是什么？AOP 是为了替代 OOP 吗？
A：OOP 通过封装、继承、多态解决纵向的业务逻辑分解问题；AOP 通过切面解决横切关注点
   （日志、事务等跨越多个模块的共性逻辑）的模块化问题。AOP 是 OOP 的补充而非替代，
   现实中 AOP 依赖 OOP 的类模型来定位切点。
   类比：OOP 是把代码分成不同部门（纵向分工），AOP 是给所有部门统一配备安保和行政（横向统管）。
考察意图：考察候选人是否理解 AOP 的定位，避免"AOP 能解决一切"的过度设计倾向。

Q：Spring AOP 和 AspectJ 有什么区别？
A：Spring AOP 基于运行时动态代理，只支持方法级别的 Join Point，且只对 Spring 管理的
   Bean 生效。AspectJ 是完整的 AOP 框架，支持编译时/加载时织入，支持字段、构造器、
   静态方法等更细粒度的 Join Point，功能更强但配置更复杂。Spring AOP 可以使用 
   AspectJ 的注解（@Aspect）但实现机制不同。
考察意图：考察候选人是否了解 Spring AOP 的局限性，避免误用（如期望拦截静态方法）。
```

```
【原理深挖层】（考察内部机制理解）

Q：Spring AOP 中 JDK 动态代理和 CGLIB 有何区别？Spring 如何选择？
A：JDK 动态代理要求目标类实现接口，通过 java.lang.reflect.Proxy 运行时创建接口实现类；
   CGLIB 通过 ASM 字节码库运行时生成目标类的子类，不要求接口但不能代理 final 类/方法。
   Spring 的选择规则：proxy-target-class=false 时有接口用 JDK 代理否则用 CGLIB；
   proxy-target-class=true（Spring Boot 3.x 默认）强制使用 CGLIB。
考察意图：考察候选人对动态代理原理的理解，以及 Spring 配置对行为的影响。

Q：为什么 AOP 对同类内部方法调用不生效？如何解决？
A：Spring AOP 通过代理对象实现拦截，外部调用 proxy.method() 时经过代理，但同类内部
   this.method() 直接调用目标对象绕过代理，切面不生效。
   解决方案：
   1. 将被调用方法移到另一个 Bean 中（最推荐）
   2. 注入自身 Bean：@Autowired SelfService self; self.method()
   3. AopContext.currentProxy()（需 exposeProxy=true，有耦合性问题）
考察意图：考察候选人对 AOP 代理机制的深度理解，以及解决实际问题的能力。
```

```
【生产实战层】（考察工程经验）

Q：生产环境中如何设计切面的执行顺序？有哪些坑？
A：使用 @Order 注解显式定义优先级，数字越小优先级越高（越外层）。
   常见顺序规范：认证授权(1) > 幂等校验(10) > 日志(20) > 事务(100)。
   坑1：未设置 @Order 时顺序不确定（依赖 Bean 加载顺序，不同环境可能不同）。
   坑2：事务切面在日志切面外层时，日志在事务提交前执行，无法记录最终状态。
   坑3：多个 Around Advice 的 @Order 相同时行为未定义。
考察意图：考察候选人是否有多切面协作的生产经验，以及对 @Order 的正确理解。

Q：如何排查一个 @Transactional 不生效的问题？
A：按以下步骤排查：
   1. 是否在 Spring 管理的 Bean 上？（非 Spring Bean 无代理）
   2. 方法是否为 public？（protected/private 不被代理拦截）
   3. 是否是自调用？（同类内部调用绕过代理）
   4. 异常类型是否正确？（默认只回滚 RuntimeException，checked exception 不回滚）
   5. 数据库/存储引擎是否支持事务？（MyISAM 不支持事务）
   6. 是否被 try-catch 吞掉了异常？
   开启 DEBUG 日志：logging.level.org.springframework.transaction=DEBUG
   可看到事务的创建/提交/回滚完整日志。
考察意图：考察候选人系统化排查问题的能力，以及对事务代理机制的实际掌握程度。
```

---

## 11. 文档元信息

### 验证声明

```
本文档内容经过以下验证：
✅ 与官方文档一致性核查：
   - Spring Framework 官方文档 AOP 章节
     https://docs.spring.io/spring-framework/reference/core/aop.html
   - AspectJ 官方文档
     https://www.eclipse.org/aspectj/doc/released/progguide/index.html

⚠️ 以下内容未经本地环境验证，仅基于文档推断：
   - 第 6.2 节：切面初始化时间 "< 500ms（切面数量 < 50）" 的具体数值
   - 第 7.3 节：Bean 数量 > 5000 时启动时间增加 10-30% 的估算
   - 第 4.1 节：JDK 动态代理 10-30ns、CGLIB 20-50ns 的性能数据（量级参考）
```

### 知识边界声明

```
本文档适用范围：
  - Spring Framework 6.x，Spring Boot 3.x
  - AspectJ 1.9.x
  - JDK 17+，Linux x86_64 环境

不适用场景：
  - Spring Boot 2.x 以下（部分 AOT 相关内容不适用）
  - Android 平台的 AOP
  - Python/Go 等语言的 AOP 实现（仅提及，未深入）
  - .NET 平台（PostSharp、Castle DynamicProxy）
```

### 参考资料

```
官方文档：
- Spring Framework AOP 官方文档：
  https://docs.spring.io/spring-framework/reference/core/aop.html
- Spring Boot AOT（GraalVM Native）：
  https://docs.spring.io/spring-boot/reference/native-image/introducing-graalvm-native-images.html
- AspectJ 编程指南：
  https://www.eclipse.org/aspectj/doc/released/progguide/index.html

核心源码：
- Spring AOP 核心包源码：
  https://github.com/spring-projects/spring-framework/tree/main/spring-aop/src
- CGLIB 源码：
  https://github.com/cglib/cglib

延伸阅读：
- Gregor Kiczales 的原始 AOP 论文（1997）：
  "Aspect-Oriented Programming" - ECOOP 1997 Proceedings
- ByteBuddy 官方教程（APM Agent 开发参考）：
  https://bytebuddy.net/#/tutorial
- Arthas 官方文档（生产环境诊断工具）：
  https://arthas.aliyun.com/doc/
```

---
