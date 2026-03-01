# ThreadLocal 内存泄漏原理（弱引用 Key 与强引用 Value）

---

## 0. 定位声明

```
适用版本：JDK 8 ~ JDK 21（核心机制一致，JDK 19+ 有 Virtual Thread 相关注意事项）
前置知识：需理解 JVM 内存模型（堆/栈）、Java 引用类型（强/软/弱/虚引用）、
          线程生命周期、垃圾回收基本原理
不适用范围：本文不覆盖 InheritableThreadLocal、TransmittableThreadLocal（阿里 TTL）；
            不适用于 Kotlin 协程、Project Loom 虚拟线程的特有场景（另有补充说明）
```

---

## 1. 一句话本质

ThreadLocal 就像给每个线程发了一个"私人储物柜"——每个线程往里存东西，互相看不到对方的内容。但这个储物柜有个隐患：**柜子的锁（Key）会自动消失，但柜子里的东西（Value）不会随之清走**，时间一长，东西越堆越多，仓库（内存）就被撑爆了。

---

## 2. 背景与根本矛盾

### 2.1 历史背景

Java 1.2（1998年）引入 `ThreadLocal`，核心动机是解决多线程共享对象的状态污染问题。在 Servlet 容器（Tomcat 等）流行后，线程池模式成为标准——**同一个线程会被反复复用服务不同的请求**，这使得"用完就忘"的 ThreadLocal 变量极易发生泄漏，因为线程从未真正"死去"。

### 2.2 根本矛盾（Trade-off）

| 对立目标 | 设计选择 | 代价 |
|---------|---------|------|
| **自动回收 Key**（防止 ThreadLocal 对象本身泄漏） | Key 使用**弱引用** | Key 可被 GC 回收，但 Value 成为孤儿 |
| **防止 Value 意外丢失** | Value 使用**强引用** | Value 必须显式 remove，否则永驻内存 |

这个设计是 JDK 工程师在"ThreadLocal 对象本身不泄漏"与"Value 绝对安全"之间的妥协，**两者无法同时完美满足**。

---

## 3. 核心概念与领域模型

### 3.1 关键术语表

| 术语 | 费曼式定义 | 正式定义 |
|------|-----------|---------|
| **ThreadLocal** | 每个线程的"私人变量容器" | 提供线程局部变量的 JDK 工具类，每个线程访问同一 ThreadLocal 对象时，实际操作各自独立的副本 |
| **ThreadLocalMap** | 线程自己随身携带的"小型哈希表" | `Thread` 类的成员变量 `threadLocals`，类型为 `ThreadLocal.ThreadLocalMap`，存储该线程所有 ThreadLocal 变量 |
| **Entry** | 哈希表中的一个槽位，存放 Key-Value 对 | `ThreadLocalMap` 内部类，继承 `WeakReference<ThreadLocal<?>>`，Key 为弱引用，Value 为强引用 |
| **弱引用（WeakReference）** | "我拿着这个东西，但如果没人要了，GC 可以直接回收它" | 当对象只有弱引用指向时，下次 GC 即会被回收 |
| **强引用（StrongReference）** | "我死死抓着这个东西，GC 不敢动它" | 普通的对象引用，只要引用存在，GC 永不回收 |
| **内存泄漏** | 程序不再需要某块内存，但它一直被占着无法释放 | 已分配的堆内存因引用链未断开而无法被 GC 回收，导致可用内存持续减少 |

### 3.2 领域模型与对象关系图

```
Thread 对象
└── threadLocals: ThreadLocalMap
        └── Entry[]  (哈希表数组)
              ├── Entry[i]
              │     ├── Key:   WeakReference ──→ ThreadLocal 对象（堆中）
              │     └── Value: 强引用        ──→ 实际存储的业务对象（堆中）
              ├── Entry[j]  (Key 已被 GC = null，Value 还在！)
              │     ├── Key:   null  ← GC 已回收 ThreadLocal 对象
              │     └── Value: 强引用 ──→ 【泄漏对象】业务对象永久占用堆内存
              └── ...
```

### 3.3 引用链分析

**正常情况（ThreadLocal 被强引用持有）：**

```
栈帧（局部变量）──强引用──→ ThreadLocal 对象（堆）
                                    ↑
                               弱引用（Entry.key）
Thread ──→ ThreadLocalMap ──→ Entry[i].key（弱引用指向同一 ThreadLocal）
                           └→ Entry[i].value（强引用 → 业务对象）
```

**泄漏情况（ThreadLocal 仅剩弱引用）：**

```
栈帧出栈，局部变量消失 → ThreadLocal 对象仅剩 Entry.key 的弱引用
↓ GC 触发
Entry.key = null（ThreadLocal 被回收）
Entry.value = 强引用 → 业务对象（永远无法被 GC 到达！）
Thread（线程池线程永不死） → ThreadLocalMap → Entry（key=null，value=泄漏对象）
```

---

## 4. 对比与选型决策

### 4.1 线程隔离方案横向对比

| 方案 | 隔离粒度 | 使用复杂度 | 内存风险 | 适用场景 |
|------|---------|-----------|---------|---------|
| **ThreadLocal** | 线程级 | 低 | ⚠️ 高（需手动 remove） | 单线程内跨方法传递上下文 |
| **方法参数透传** | 调用栈级 | 高（参数爆炸） | 无 | 简单、短链路场景 |
| **ConcurrentHashMap<Thread, V>** | 线程级 | 中 | ⚠️ 高（线程死后 Key 不会自动清理） | 不推荐直接使用 |
| **ScopedValue（JDK 21 预览）** | 调用域级 | 中 | 低（自动绑定生命周期） | 虚拟线程、结构化并发 |
| **TransmittableThreadLocal（TTL）** | 线程+子线程级 | 低 | 中（需配合 Agent） | 线程池上下文传递 |

### 4.2 选型决策

**选 ThreadLocal 的场景：**
- 数据库连接/Session 的线程隔离（MyBatis、Hibernate 广泛使用）
- 请求上下文传递（用户信息、TraceId、语言偏好）
- 非线程安全对象的线程本地副本（如 `SimpleDateFormat`）

**不选 ThreadLocal 的场景：**
- 异步任务/线程池任务需要继承父线程上下文 → 用 TTL
- JDK 21+ 虚拟线程环境 → 优先考虑 `ScopedValue`
- 需要跨线程共享且需要并发控制 → 用 `synchronized` 或 `Lock`

---

## 5. 工作原理与实现机制

### 5.1 静态结构：核心数据结构

**ThreadLocalMap 的哈希表设计：**

```java
// 源码路径：java.lang.ThreadLocal.ThreadLocalMap
// JDK 8 ~ JDK 21 核心结构一致

static class ThreadLocalMap {
    // Entry 继承 WeakReference，Key 天然是弱引用
    static class Entry extends WeakReference<ThreadLocal<?>> {
        Object value;  // Value 是强引用！

        Entry(ThreadLocal<?> k, Object v) {
            super(k);      // 调用 WeakReference 构造，Key 成为弱引用
            value = v;     // Value 直接强引用持有
        }
    }

    private Entry[] table;          // 哈希桶数组
    private int size;               // 元素个数
    private int threshold;          // 扩容阈值（约为 table.length * 2/3）
    
    // 初始容量 16，负载因子 2/3，扩容时翻倍
    private static final int INITIAL_CAPACITY = 16;
}
```

**为什么 Key 用弱引用？**

设计意图是：当外部代码不再持有 `ThreadLocal` 对象时（栈帧出栈），允许 GC 回收该对象，防止 `ThreadLocal` 实例本身泄漏。**但这只解决了 Key 的泄漏，没有解决 Value 的泄漏。**

**为什么 Value 不能用弱引用？**

如果 Value 也用弱引用，那么在用户调用 `get()` 之前，Value 可能随时被 GC 回收（因为 ThreadLocalMap 是唯一持有它的地方），导致用户拿到 `null`，产生不可预期的业务错误。这是不可接受的。

### 5.2 动态行为：关键流程时序

**`set()` 流程：**

```
用户调用 threadLocal.set(value)
    ↓
获取当前线程 Thread t = Thread.currentThread()
    ↓
获取 t.threadLocals (ThreadLocalMap)
    ↓
若 map 不为 null → map.set(this, value)
    ├── 计算哈希槽位：i = threadLocalHashCode & (table.length - 1)
    ├── 线性探测处理冲突（开放地址法）
    ├── 途中若遇到 key==null 的 stale Entry → 触发 replaceStaleEntry() 顺带清理
    └── 最终插入 Entry，检查是否需要 rehash/扩容
若 map 为 null → createMap(t, value)（首次创建 ThreadLocalMap）
```

**`get()` 流程：**

```
用户调用 threadLocal.get()
    ↓
Thread t = Thread.currentThread()
    ↓
ThreadLocalMap map = t.threadLocals
    ↓
若 map != null → map.getEntry(this)
    ├── 计算槽位，直接命中 → 返回 entry.value
    └── 未命中 → 线性探测，途中清理 stale Entry（key==null 的槽位）
若 map == null 或未找到 → setInitialValue()（返回 initialValue()，默认 null）
```

**`remove()` 流程（必须调用！）：**

```
用户调用 threadLocal.remove()
    ↓
ThreadLocalMap m = Thread.currentThread().threadLocals
    ↓
m.remove(this)
    ├── 找到对应 Entry
    ├── entry.clear()  → 主动将 WeakReference 的 referent 置 null
    └── expungeStaleEntry()  → 清理该槽位及后续 stale Entry，Value 置 null
                                （Value 的强引用断开，GC 可回收）
```

### 5.3 关键设计决策

**决策1：哈希冲突使用线性探测（开放地址法）而非链表**

理由：ThreadLocalMap 的 Entry 数量通常很少（< 10 个），线性探测的 CPU 缓存友好性远优于链表跳转，且实现更简单。代价是删除时需要重新整理哈希表（`expungeStaleEntry` 的复杂逻辑）。

**决策2：被动清理（探测时顺带清理 stale Entry）**

ThreadLocalMap 在 `set()`、`get()`、`remove()` 时会顺带扫描并清理 key==null 的 stale Entry，但**不保证全量清理**。这是一种懒清理策略，避免每次操作都全表扫描的性能开销，但也意味着如果线程长期不调用这些方法，stale Entry 会一直占用内存。

**决策3：每个 Thread 持有自己的 ThreadLocalMap（而非 ThreadLocal 持有 Map）**

如果反过来，让 ThreadLocal 对象持有一个 `Map<Thread, Value>`，则线程死亡后其 Value 无法被自动清理（Thread 对象作为 Key，死亡线程的 Thread 对象仍被 Map 强引用）。现在的设计让 ThreadLocalMap 随线程的生命周期存亡，更符合直觉。

---

## 6. 内存泄漏场景与高可靠保障

### 6.1 泄漏的完整触发条件

内存泄漏必须同时满足以下三个条件：

```
条件1：线程生命周期极长（线程池中的核心线程永不销毁）
   AND
条件2：ThreadLocal 变量没有被任何强引用持有（方法返回后，局部变量的强引用消失）
   AND
条件3：用户没有显式调用 threadLocal.remove()
```

**任意一个条件不满足，就不会发生泄漏。**

线程池（Tomcat、Spring 的线程池）使线程永久存活，是泄漏的根本放大器。

### 6.2 可观测性：监控指标

| 监控指标 | 正常范围 | 泄漏信号 | 获取方式 |
|---------|---------|---------|---------|
| JVM 堆内存使用率 | < 70% | 持续缓慢增长，Full GC 后不降 | JVM Metrics / Prometheus JMX Exporter |
| Full GC 频率 | < 1次/小时（业务低峰） | 频率升高但内存不释放 | GC 日志 `-Xlog:gc*` |
| Old Gen 增长速率 | 趋于平稳 | 单调递增 | VisualVM / Arthas `memory` 命令 |
| Thread 数量 | 与线程池配置一致 | 异常增长（非 ThreadLocal 问题） | `jstack` / Arthas `thread` |

**Arthas 快速定位泄漏：**

```bash
# 运行环境：Arthas 3.6+，JDK 8+
# 查看堆中占用最大的对象类型
java -jar arthas-boot.jar
> memory
> heapdump /tmp/dump.hprof
```

---

## 7. 使用实践与故障手册

### 7.1 生产级正确使用模板

**环境：JDK 8+，Spring Boot 2.x / 3.x，线程池场景**

```java
/**
 * 推荐模式：将 ThreadLocal 定义为 static final，配合 try-finally 保证 remove
 * 运行环境：JDK 8+
 */
public class UserContextHolder {

    // ✅ static final：ThreadLocal 对象本身常驻，不会因方法返回而失去强引用
    // ✅ 使用 static 使其成为类级别共享，节省对象创建开销
    private static final ThreadLocal<UserContext> CONTEXT =
            ThreadLocal.withInitial(UserContext::new);

    public static void set(UserContext ctx) {
        CONTEXT.set(ctx);
    }

    public static UserContext get() {
        return CONTEXT.get();
    }

    /**
     * ✅ 必须在请求结束时调用 remove，推荐在 Filter 或 Interceptor 的 finally 块中执行
     */
    public static void clear() {
        CONTEXT.remove();
    }
}

// Spring MVC 拦截器中正确清理
// 运行环境：Spring MVC 5.x / 6.x，JDK 8+
@Component
public class UserContextInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(HttpServletRequest request,
                             HttpServletResponse response, Object handler) {
        UserContext ctx = resolveUserFromRequest(request);
        UserContextHolder.set(ctx);
        return true;
    }

    @Override
    public void afterCompletion(HttpServletRequest request,
                                HttpServletResponse response,
                                Object handler, Exception ex) {
        // ✅ afterCompletion 保证无论是否异常都会执行，等价于 finally
        UserContextHolder.clear();
    }
}
```

**⚠️ 反模式警告：**

```java
// ❌ 错误示范 1：ThreadLocal 定义为实例变量，随对象创建/销毁
public class BadService {
    // 每次 BadService 实例化都创建新 ThreadLocal，旧的被 GC，Value 泄漏
    private ThreadLocal<String> localVar = new ThreadLocal<>();
}

// ❌ 错误示范 2：在方法内定义 ThreadLocal 局部变量
public void doSomething() {
    ThreadLocal<String> local = new ThreadLocal<>();  // 方法返回后强引用消失！
    local.set("data");
    // 忘记 remove，此后 Entry.key 被 GC，Value 永久泄漏
}

// ❌ 错误示范 3：线程池任务中忘记清理
executor.submit(() -> {
    threadLocal.set(heavyObject);
    // 任务结束，线程归还线程池，但 heavyObject 永久留在线程的 ThreadLocalMap 中
    // 没有 threadLocal.remove()！
});
```

### 7.2 故障模式手册

```
【故障1：堆内存持续增长，Full GC 后不降】
- 现象：应用运行数小时后 Old Gen 内存缓慢线性增长，
        每次 Full GC 只能释放少量内存，最终 OOM
- 根本原因：线程池中的 ThreadLocal Value 泄漏，大量强引用对象堆积在 Old Gen
- 预防措施：
    1. 所有 ThreadLocal 使用 static final 声明
    2. 在 Filter/Interceptor 的 finally 或 afterCompletion 中强制调用 remove()
    3. 代码 Review 检查 ThreadLocal 的每个 set() 是否有对应 remove()
- 应急处理：
    1. Arthas heapdump 后用 MAT 分析 GC Root 链路，找到泄漏业务对象
    2. 重启应用（临时缓解），同时修复代码并灰度验证
```

```
【故障2：请求间数据串扰（脏数据）】
- 现象：A 用户的请求偶发性读取到 B 用户的数据（如 UserContext 错乱）
- 根本原因：前一个请求 set() 了 ThreadLocal，但没有 remove()；
            线程归还线程池后，被下一个请求复用，读取到残留数据
- 预防措施：同故障1，在请求结束时强制 remove()
- 应急处理：
    1. 在 preHandle 中同时执行 clear() 再 set()，双重保险
    2. 添加监控：请求开始时检查 ThreadLocal 是否有残留值并告警
```

```
【故障3：JDK 21 虚拟线程下 ThreadLocal 内存开销过大】
- 现象：大量虚拟线程创建后，内存占用异常高
- 根本原因：虚拟线程数量可达百万级，每个线程独立的 ThreadLocalMap 存储开销被放大
- 预防措施：JDK 21+ 环境中，虚拟线程场景改用 ScopedValue
- 应急处理：评估是否可将 ThreadLocal 替换为 ScopedValue，或限制虚拟线程并发数
```

### 7.3 边界条件与局限性

- **线程池场景必须手动 remove**，否则必然泄漏，JDK 的被动清理无法保证
- **Value 对象越大，泄漏越严重**：存储 byte[]（如图片数据）、大型 DTO 时，单次泄漏可达 MB 级
- **JDK 的 replaceStaleEntry() 只做局部清理**，不进行全表扫描，不能依赖其自动回收
- **InheritableThreadLocal 子线程会 copy 父线程的 Value**，子线程同样需要 remove
- **ThreadLocalMap 初始容量 16，负载因子 2/3**：超过 10 个 ThreadLocal 时开始扩容，但业务中通常不会达到此上限

---

## 8. 性能调优指南

### 8.1 ThreadLocalMap 的性能特性

| 操作 | 时间复杂度 | 说明 |
|------|-----------|------|
| `set()` | O(1) 均摊 | 冲突时线性探测，通常 < 3 次探测 |
| `get()` | O(1) 均摊 | 直接命中时 O(1)；哈希冲突多时退化 |
| `remove()` | O(n) | 需要 expungeStaleEntry，向后扫描整理哈希表 |
| 扩容 | O(n) | 全量 rehash，阈值为容量的 2/3 |

### 8.2 调优建议

**避免 ThreadLocal 数量过多造成性能退化：**

单个线程的 ThreadLocalMap 中 Entry 超过 16 个时会触发第一次扩容，建议将相关上下文合并为单个对象：

```java
// 优化：单次 set 存储整个上下文对象，而非多个 ThreadLocal 分别 set
// 运行环境：JDK 8+
private static final ThreadLocal<RequestContext> CONTEXT = new ThreadLocal<>();

// RequestContext 封装所有上下文字段
public class RequestContext {
    private String userId;
    private String traceId;
    private Locale locale;
    // ...
}

// 而非：
// private static final ThreadLocal<String> USER_ID = new ThreadLocal<>();
// private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();
// private static final ThreadLocal<Locale> LOCALE = new ThreadLocal<>();
```

**调优参数速查（JVM 层面）：**

| 参数 | 默认值 | 推荐值（高并发 Web） | 调整风险 |
|------|--------|---------------------|---------|
| `-Xmx` | JVM 自适应 | 物理内存的 50%~70% | 过大导致 GC 停顿时间增加 |
| `-XX:+HeapDumpOnOutOfMemoryError` | 关闭 | 开启 | 生成大文件，需确保磁盘空间 ≥ 堆大小 |
| `-XX:HeapDumpPath` | JVM 启动目录 | `/data/dumps/` | 需确保目录有写权限 |
| GC 算法 | G1（JDK 9+） | G1 或 ZGC（低延迟场景） | ZGC 吞吐量比 G1 低约 5%~15% |

---

## 9. 演进方向与未来趋势

### 9.1 ScopedValue（JDK 21 正式预览，JDK 23 持续迭代）

`ScopedValue` 是 Project Loom 为虚拟线程引入的 ThreadLocal 替代品（JEP 446/481）。其核心改进：

- **不可变性**：ScopedValue 在绑定作用域内只读，天然线程安全，无需手动 remove
- **生命周期自动管理**：随调用作用域（`ScopedValue.where(...).run(...)`）自动销毁
- **虚拟线程友好**：不为每个虚拟线程分配独立的全量存储，内存开销大幅降低

```java
// JDK 21+ ScopedValue 示例（preview 特性）
// 运行环境：JDK 21，需添加 --enable-preview --source 21 编译参数
static final ScopedValue<UserContext> USER = ScopedValue.newInstance();

ScopedValue.where(USER, userCtx).run(() -> {
    // 在此作用域内，USER.get() 返回 userCtx
    // 作用域结束自动清理，无需 remove()
    processRequest();
});
// 作用域外调用 USER.get() 会抛出 NoSuchElementException
```

**对现有用户的影响：** JDK 21+ 新项目建议在虚拟线程场景优先评估 `ScopedValue`；存量项目无需立即迁移，`ThreadLocal` 在传统线程场景仍完全支持。

### 9.2 结构化并发与上下文传播标准化

JEP 428/453 推进的结构化并发（Structured Concurrency）将进一步规范线程上下文的传播方式，未来框架层（如 Spring 7.x）可能内置更安全的上下文传播机制，减少开发者手动管理 ThreadLocal 的需求。

---

## 10. 面试高频题

```
【基础理解层】（考察概念掌握）

Q：ThreadLocal 是如何实现线程隔离的？
A：每个 Thread 对象内部维护一个 ThreadLocalMap（哈希表），以 ThreadLocal 实例为 Key，
   以线程本地值为 Value。不同线程操作同一个 ThreadLocal 对象时，实际上操作的是
   各自线程内部 ThreadLocalMap 中不同的 Entry，因此天然隔离。
考察意图：区分"ThreadLocal 持有 Map"与"Thread 持有 Map"两种设计理解的正确性。

Q：ThreadLocal 的内存泄漏是如何发生的？
A：ThreadLocalMap 的 Entry 中，Key（ThreadLocal 对象引用）是弱引用，Value 是强引用。
   当 ThreadLocal 变量没有外部强引用时，GC 会回收 ThreadLocal 对象，Key 变为 null。
   但 Value 仍被 Entry 强引用持有，而 Entry 又被 Thread→ThreadLocalMap 强引用持有。
   在线程池中线程永不销毁，这条引用链永不断开，Value 对象无法被 GC 回收，造成泄漏。
考察意图：检验对弱引用机制和引用链的理解深度。
```

```
【原理深挖层】（考察内部机制理解）

Q：Key 为什么用弱引用？为什么 Value 不也用弱引用？
A：Key 用弱引用是为了防止 ThreadLocal 实例本身泄漏——当业务代码不再需要某个
   ThreadLocal 时，弱引用允许 GC 回收它，避免 ThreadLocal 对象永久驻留内存。
   Value 不能用弱引用，因为 ThreadLocalMap 是 Value 的唯一持有者，
   若 Value 只剩弱引用，GC 随时可能回收，导致 get() 返回 null，产生不可预期错误。
   这是一个两害相权取其轻的设计决策：选择保护 Value 的可靠性，要求开发者手动 remove。
考察意图：考察是否理解设计背后的 Trade-off，而非只记结论。

Q：JDK 有没有自动清理机制？为什么不足以防止泄漏？
A：有。ThreadLocalMap 在 set()、get()、remove() 时，会通过 expungeStaleEntry() 
   和 replaceStaleEntry() 清理 key==null 的 stale Entry。但这是被动触发的局部清理：
   1. 只扫描冲突探测路径上的 stale Entry，不是全表扫描
   2. 如果线程长期不调用这三个方法（如线程池线程处于等待状态），stale Entry 永不被清理
   3. 线程池中线程可能长期等待任务，被动清理完全失效
   因此不能依赖 JDK 的自动清理，必须显式调用 remove()。
考察意图：检验是否真正读过源码，而非仅凭概念作答。
```

```
【生产实战层】（考察工程经验）

Q：在 Spring MVC 项目中，如何系统性地防止 ThreadLocal 内存泄漏？
A：三层防御：
   1. 规范声明：所有 ThreadLocal 定义为 static final，避免实例变量或局部变量声明
   2. 生命周期管理：在 HandlerInterceptor.afterCompletion() 或 Filter 的 finally 块
      中统一调用 clear()，afterCompletion 保证无论是否异常都执行
   3. 监控告警：配置 JVM OldGen 增长速率告警（如 Prometheus + Grafana），
      Full GC 后内存不降时触发告警，结合 Arthas heap dump 快速定位
   可选：引入自定义 ThreadLocal 包装类，在 set() 时记录调用栈，便于排查谁没有 remove
考察意图：检验是否有系统性工程思维，而非只知道"调用 remove()"。

Q：如果接手一个存在 ThreadLocal 泄漏的线上系统，如何定位并修复？
A：定位步骤：
   1. 确认现象：GC 日志确认 Full GC 后 Old Gen 不下降
   2. 获取 Heap Dump：jmap -dump:live,format=b,file=heap.hprof <pid>，
      或配置 -XX:+HeapDumpOnOutOfMemoryError
   3. 分析 Heap Dump：用 MAT 或 VisualVM，查找数量最多/占用最大的对象类型，
      通过 GC Root 分析找到持有链：Thread → ThreadLocalMap → Entry → 业务对象
   4. 定位源码：找到对应业务对象的 ThreadLocal set 位置，检查是否有 remove
   修复步骤：
   1. 加 remove()（短期修复）
   2. 重构为统一的上下文管理类，避免散落的 ThreadLocal 难以追踪
   3. 验证：压测后观察 Old Gen 内存曲线是否趋于平稳
考察意图：检验实际故障排查能力和生产经验。
```

---

## 11. 文档元信息

### 验证声明

```
本文档内容经过以下验证：
✅ 与官方文档一致性核查：
   - JDK 源码：java.lang.ThreadLocal（OpenJDK 8/11/17/21）
   - https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html
   - JEP 446（ScopedValue）：https://openjdk.org/jeps/446
⚠️ 以下内容未经本地环境验证，仅基于文档推断：
   - 第9章 ScopedValue 代码示例（preview 特性，行为可能随 JDK 版本变化）
   - 第8章性能数据为业界普遍经验值，未在特定硬件环境下基准测试验证
```

### 知识边界声明

```
本文档适用范围：JDK 8 ~ JDK 21，标准 Java 线程（非虚拟线程为主场景），
               部署于 Linux x86_64 / ARM64 环境
不适用场景：
   - Kotlin 协程（协程有自己的 CoroutineContext 机制）
   - JDK 21+ 虚拟线程为主的新应用（建议评估 ScopedValue）
   - Android 平台（ART 虚拟机实现与 HotSpot 有差异）
```

### 参考资料

```
【官方文档】
- OpenJDK ThreadLocal 源码：
  https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/lang/ThreadLocal.java
- JEP 446 - Scoped Values（JDK 21 Preview）：
  https://openjdk.org/jeps/446
- Java SE 21 API 文档 - ThreadLocal：
  https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html

【核心源码】
- OpenJDK GitHub（ThreadLocal.ThreadLocalMap 内部类）：
  https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/lang/ThreadLocal.java#L220

【延伸阅读】
- 《Java 并发编程实战》（Brian Goetz 等）第 3 章：线程封闭
- 《深入理解 Java 虚拟机》（周志明）第 3 章：垃圾收集器与内存分配策略
- Arthas 官方文档（heapdump 分析）：https://arthas.aliyun.com/doc/heapdump.html
- Eclipse MAT 内存分析工具：https://eclipse.dev/mat/
```

---
