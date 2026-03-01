
---

# ReentrantLock 公平锁与非公平锁实现 技术文档

---

## 0. 定位声明

```
适用版本：JDK 8 ~ JDK 21
前置知识：Java 线程模型、synchronized 基本语义、CAS 原理、JVM 内存模型
不适用范围：不覆盖 StampedLock/ReadWriteLock；不涉及分布式锁；虚拟线程深度分析不在此范围
```

---

## 1. 一句话本质

想象银行只有一个窗口：
- **非公平锁**：新来的客户如果恰好窗口空了，可以直接插队上去——整体效率更高，但偶尔有人等很久
- **公平锁**：严格按排队顺序，没有插队，每人等待时间可预期，但整体吞吐量略低

`ReentrantLock` 是 Java 中一把**可重入**（同一线程可多次获取）的锁，创建时用 `new ReentrantLock(fair)` 选择模式。

---

## 2. 背景与根本矛盾

**历史背景**：JDK 1.5 前，`synchronized` 无法中断等待、无超时、无公平性控制。Doug Lea 通过 JSR-166 引入 `ReentrantLock`，基于 AQS 框架构建。

**核心 Trade-off：**

| 维度 | 公平锁 | 非公平锁 |
|------|--------|----------|
| 吞吐量 | 低（每次必须唤醒队头线程） | 高（新线程可直接 CAS） |
| 延迟公平性 | 可预测（FIFO） | 不可预测（可能饥饿） |
| CPU 上下文切换 | 频繁 | 较少 |

非公平锁之所以更快，是利用了**线程调度的时间局部性**：锁释放瞬间持有者仍在 CPU 上，新线程 CAS 成功可省去唤醒队列线程的系统调用开销（约 2,000~10,000 ns）。

---

## 3. 核心概念与领域模型

**关键术语：**

| 术语 | 费曼式定义 | 正式定义 |
|------|-----------|---------|
| AQS | "排队管理员"，记录谁在等锁、谁持有锁 | AbstractQueuedSynchronizer，基于 CLH 变体的双向队列同步器 |
| state | 锁的计数器，0=无人用，>0=重入次数 | AQS 内部 `volatile int state` |
| CLH 队列 | 锁的等待名单 | AQS 内部维护的 FIFO 双向等待队列 |
| CAS | "比较后替换"，要么成功要么失败，无中间态 | 基于 CPU `cmpxchg` 指令的原子操作 |

**领域模型：**

```
ReentrantLock
  └── Sync (extends AQS)
        ├── FairSync
        └── NonfairSync

AQS 内部：
  volatile int state          (0=无锁, >0=重入次数)
  Thread exclusiveOwnerThread (当前持有者)
  CLH 双向队列: head ←→ [T1] ←→ [T2] ←→ [T3] ←→ tail
```

---

## 4. 对比与选型决策

| 特性 | synchronized | ReentrantLock 非公平 | ReentrantLock 公平 | StampedLock |
|------|-------------|---------------------|-------------------|-------------|
| 可中断 | ❌ | ✅ | ✅ | ✅ |
| 超时 | ❌ | ✅ | ✅ | ✅ |
| 多条件变量 | 单个 | 多个 | 多个 | ❌ |
| 可重入 | ✅ | ✅ | ✅ | ❌ |
| 适用场景 | 简单互斥 | 高吞吐通用 | 公平性敏感 | 读多写少 |

**选型决策树：**
- 逻辑简单、无需高级特性 → `synchronized`
- 需要超时/中断/多条件 + 公平性要求 → `ReentrantLock(true)`（任务调度、防饥饿场景）
- 需要超时/中断/多条件 + 最大吞吐 → `ReentrantLock(false)`（缓存、连接池）
- 读多写少 → `ReadWriteLock` / `StampedLock`

---

## 5. 工作原理与实现机制

### 5.1 核心源码差异（JDK 11）

```java
// 非公平锁
static final class NonfairSync extends Sync {
    final void lock() {
        if (compareAndSetState(0, 1))       // ① 直接 CAS，不看队列
            setExclusiveOwnerThread(Thread.currentThread());
        else
            acquire(1);
    }
    protected final boolean tryAcquire(int acquires) {
        return nonfairTryAcquire(acquires); // ② CAS 时不检查队列
    }
}

// 公平锁
static final class FairSync extends Sync {
    final void lock() {
        acquire(1);                         // ① 直接走 AQS，无初始 CAS
    }
    protected final boolean tryAcquire(int acquires) {
        if (c == 0) {
            if (!hasQueuedPredecessors()    // ② 必须检查：队列是否有前驱
                && compareAndSetState(0, acquires)) {
                setExclusiveOwnerThread(current);
                return true;
            }
        }
        // ...
    }
}
```

**唯一差异：** 非公平锁在两个地方省略了对队列的检查，其他逻辑完全相同。

### 5.2 关键流程

**非公平锁 lock()：**
```
① 直接 CAS(0→1)  →成功→ 获锁 ✅
              ↓失败
② tryAcquire() 再次 CAS（仍可插队）
              ↓失败
③ addWaiter() → 入队
④ acquireQueued() → 前驱是 head? tryAcquire() : park()
```

**公平锁 lock()：**
```
① acquire(1) → tryAcquire()
② hasQueuedPredecessors()==false && CAS(0→1) → 获锁 ✅
   有前驱 → addWaiter() → 入队 → park()
```

**解锁（公平/非公平相同）：**
```
unlock() → state-- → state==0? 清除owner + unpark(队头下一个线程)
```

### 5.3 关键设计决策

**为什么非公平锁在 acquire() 前先 CAS 一次？**
> 利用时间局部性：释放锁的线程还在 CPU 上，新线程此时 CAS 成功可省去上下文切换（1~5 μs）。吞吐量提升的根本原因在此。

**为什么公平锁用 `hasQueuedPredecessors()` 而非直接入队？**
> 无竞争时避免无谓入队/出队操作，在保证公平语义的同时降低开销。

**为什么 state 用 `volatile` + CAS 而非 synchronized？**
> 用锁来实现锁会产生递归依赖。`volatile` 保可见性，CAS 保原子性，是 Lock-Free 编程的经典模式。

---

## 6. 高可靠性保障

**标准使用模板（必须遵守）：**
```java
lock.lock();
try {
    // 临界区
} finally {
    lock.unlock();  // finally 确保释放
}
```

**可观测性指标：**

| 指标 | 正常阈值 | 告警阈值 |
|------|---------|---------|
| `lock.getQueueLength()` | < 10 | > 100 |
| 锁持有时间 | < 1ms | > 10ms |
| BLOCKED/WAITING 线程比例 | < 5% | > 20% |

---

## 7. 使用实践与故障手册

**生产级示例（JDK 11+）：**

```java
// 非公平锁（默认）
private final ReentrantLock lock = new ReentrantLock();

// 公平锁
private final ReentrantLock fairLock = new ReentrantLock(true);

// 可中断等待
lock.lockInterruptibly();

// 带超时防死锁
if (lock.tryLock(100, TimeUnit.MILLISECONDS)) {
    try { /* 业务 */ } finally { lock.unlock(); }
} else { /* 降级 */ }

// 多条件变量（生产者-消费者）
Condition notFull  = lock.newCondition();
Condition notEmpty = lock.newCondition();
```

**故障手册：**

```
【锁泄漏】
现象：线程大量 WAITING，系统逐渐卡死
原因：临界区异常，unlock() 未在 finally 执行
处理：重启；强制所有代码使用 try-finally 模板

【死锁】
现象：多线程互相等待，系统完全停响
原因：多锁获取顺序不一致
预防：全局锁排序 + tryLock(timeout)
处理：jstack 定位，kill 一个线程，重启

【非公平锁饥饿】
现象：某线程等待 > 10s 无法获锁
原因：高并发下活跃线程持续插队
处理：切换公平锁或引入信号量限并发

【临界区过重】
现象：吞吐量骤降 50%+，大量 BLOCKED 线程
原因：锁内做 RPC/DB 操作，持锁时间 μs→s
处理：缩短临界区，IO 操作移出锁外
```

---

## 8. 性能调优指南

**诊断工具：**
- `jstack` 连续 3 次快照，对比 WAITING 线程持有的锁地址
- Arthas `trace` 方法耗时
- JFR `Java.MonitorWait` 事件
- async-profiler `-e lock` 火焰图

**调优优先级：**
1. **缩短临界区** → 目标持锁 < 100μs
2. **锁分段** → 将 1 把锁拆为 N 把，竞争概率降低约 1/N
3. **非公平锁** → 公平场景无需求时，吞吐量预期提升 10%~30%（⚠️ 存疑）
4. **无锁替代** → 计数器用 `LongAdder`（比 `AtomicLong` 高并发快 3~10 倍）

---

## 9. 演进方向

**JDK 21 虚拟线程**：`synchronized` 在 JDK 21 之前会 pin 住平台线程，`ReentrantLock` 则支持虚拟线程在 `lock()` 阻塞时 unmount，这是当前虚拟线程场景优先选 `ReentrantLock` 的核心原因。JDK 23+ 正在改善 `synchronized` 的虚拟线程支持。

**Project Valhalla**：值类型无对象头，无法用于 `synchronized` monitor，进一步强化显式锁的重要性。

---

## 10. 面试高频题

**【基础理解层】公平锁和非公平锁区别？**

核心差异仅两行代码：非公平锁 `lock()` 先直接 CAS，`tryAcquire()` 中不检查队列；公平锁 `lock()` 直接走 AQS，`tryAcquire()` 必须先调 `hasQueuedPredecessors()`。解锁逻辑完全相同。

*考察意图：是否读过源码，而非死背结论。*

---

**【原理深挖层】CLH 队列为何是双向的？**

支持 O(1) 取消等待：取消节点时需找前驱更新其 next 指针，单向队列须 O(n) 遍历，双向队列通过 prev 直接 O(1) 定位。

*考察意图：数据结构选型的 trade-off 理解。*

---

**【原理深挖层】非公平锁会导致线程永远饿死吗？**

理论上有风险，实际极少。每次释放锁都会 unpark 队头线程参与竞争，且 JVM 抢占调度会让持续插队的线程耗尽时间片。极端高并发（QPS > 10万/核）+ 持锁时间长（>1ms）时风险上升，应改用公平锁。

*考察意图：避免绝对化，考察辩证理解。*

---

**【生产实战层】如何诊断锁竞争性能问题？**

① jstack 连续 dump 3 次，对比 WAITING 线程持有的锁地址；② Arthas `trace` 定位 lock() 耗时；③ JFR `MonitorWait` 事件；④ async-profiler `-e lock` 火焰图。

*考察意图：真实工具使用经验，区分背书与实战。*

---

## 11. 文档元信息

```
验证说明：
✅ 源码分析基于 OpenJDK 11（openjdk/jdk11u）逐行核对
✅ 官方文档：https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html
⚠️ 未经本地 JMH 验证：吞吐量差距数值（10%~30%）、JVM 参数对 ReentrantLock 的影响

适用范围：JDK 8~21，Linux x86_64/ARM64
不适用：Kotlin 协程 Mutex、Android 平台、GraalVM Native Image

参考资料：
- Doug Lea《The java.util.concurrent Synchronizer Framework》(2004)
  https://dl.acm.org/doi/10.1145/1011767.1011802
- 《Java Concurrency in Practice》- Brian Goetz
- JEP 444 Virtual Threads：https://openjdk.org/jeps/444
- OpenJDK 源码：https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/util/concurrent/locks/ReentrantLock.java
```

---

