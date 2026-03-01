# AQS 独占锁与共享锁实现差异

---

## 0. 定位声明

```
适用版本：JDK 8 ~ JDK 21（核心机制一致，JDK 9+ 引入 VarHandle 替代 Unsafe，行为等价）
前置知识：需理解 Java 线程模型、CAS 操作原理、LockSupport.park/unpark 语义、Java Monitor 模型
不适用范围：
  - 不覆盖 StampedLock（非 AQS 实现）
  - 不覆盖 synchronized 关键字（JVM 内置 Monitor）
  - 不覆盖 Kotlin 协程中的并发原语
```

---

## 1. 一句话本质

> **独占锁（Exclusive）**：同一时刻只允许一个人进入房间，进去的人把门锁上，其他人在门外排队等候，锁释放后只叫醒队头的一个人。
>
> **共享锁（Shared）**：同一时刻允许多个人同时进入阅览室，只要还有空位（许可数 > 0）就可以进；当最后一个人离开时，如果门外还有等待的人，会一次性叫醒一批人。
>
> **AQS 的职责**：它是这两种规则的"门卫基础设施"——维护一个 FIFO 等待队列和一个状态变量 `state`，让独占和共享两种语义都能复用同一套排队、挂起、唤醒机制，开发者只需声明"进门条件"即可。

---

## 2. 背景与根本矛盾

### 2.1 历史背景

2004 年，Doug Lea 在论文 *The java.util.concurrent Synchronizer Framework*（JSR-166）中提出 AQS。在此之前，Java 只有 `synchronized` 一种同步原语，无法实现：

- 可超时等待（`tryLock(timeout)`）
- 可中断等待
- 公平 vs 非公平切换
- 读多写少场景的并发读

AQS 的诞生将**同步状态管理**与**线程排队机制**解耦，通过模板方法模式让上层锁只关注"许可的业务语义"。

### 2.2 根本矛盾（Trade-off）

| 矛盾维度 | 独占模式 | 共享模式 |
|---------|---------|---------|
| **并发度 vs 安全性** | 串行访问，安全性最高，并发度为 1 | 并发访问，并发度 = 许可数，需要更复杂的安全保证 |
| **唤醒代价 vs 吞吐量** | 每次只唤醒 1 个线程，代价低 | 需传播唤醒（propagation），可能唤醒 N 个线程，代价高但吞吐大 |
| **实现简洁性 vs 功能丰富** | 简单的 acquire/release | 需额外处理"传播"语义，实现更复杂 |

---

## 3. 核心概念与领域模型

### 3.1 关键术语表

| 术语 | 费曼式定义 | 正式定义 |
|------|-----------|---------|
| **state** | 一个整数计数器，代表"还剩多少资源/锁是否被占用" | `volatile int state`，AQS 中唯一的同步状态变量，语义由子类定义 |
| **CLH 队列** | 一条 FIFO 排队链表，每个等待的线程都是链表中的一个节点 | 改良版 CLH（Craig-Landin-Hagersten）双向链表，节点含前驱指针用于取消操作 |
| **Node.waitStatus** | 节点的"状态标签"，标记这个等待者是正常排队、已取消还是需要唤醒下一个 | `CANCELLED=1, SIGNAL=-1, CONDITION=-2, PROPAGATE=-3, 0=初始` |
| **PROPAGATE** | "接力棒"标志，共享模式专用，告诉后续节点"你也可以来拿锁了" | `waitStatus = -3`，仅在 `doReleaseShared` 中设置，确保共享释放信号向后传播 |
| **独占模式** | 一次只有一个线程能持有同步状态 | `tryAcquire/tryRelease`，`state=0` 表示空闲，`state=1` 表示被占用（ReentrantLock） |
| **共享模式** | 多个线程可同时持有同步状态 | `tryAcquireShared/tryReleaseShared`，返回剩余许可数；`state` 表示剩余许可（Semaphore） |

### 3.2 领域模型

```
AQS 内部结构
─────────────────────────────────────────────────────────
  volatile int state          ← 同步状态（核心资源）
  Node head                   ← 队列哨兵头节点（dummy）
  Node tail                   ← 队列尾节点

CLH 队列（双向链表）
  [head/dummy] ←→ [Node-T1] ←→ [Node-T2] ←→ [Node-T3] ← tail
                    thread      thread          thread
                    SIGNAL      SIGNAL          0

Node 结构
  ┌─────────────────────────────┐
  │ Thread thread               │ ← 被挂起的线程引用
  │ int waitStatus              │ ← 节点状态
  │ Node prev / next            │ ← 双向链接
  │ Node nextWaiter             │ ← 共享模式: SHARED常量; 独占: null/Condition队列链
  └─────────────────────────────┘

独占节点：nextWaiter = null（或 Condition 队列）
共享节点：nextWaiter = Node.SHARED（静态常量节点，作标记用）
```

---

## 4. 对比与选型决策

### 4.1 独占锁 vs 共享锁横向对比

| 维度 | 独占锁 | 共享锁 |
|------|-------|-------|
| **典型实现** | ReentrantLock, ReentrantWriteLock.WriteLock | Semaphore, CountDownLatch, ReentrantReadLock |
| **同时持有线程数** | 1 | N（由 state 初始值决定） |
| **acquire 核心方法** | `tryAcquire(int arg)` | `tryAcquireShared(int arg)` 返回 int |
| **release 核心方法** | `tryRelease(int arg)` | `tryReleaseShared(int arg)` 返回 boolean |
| **成功条件返回值** | boolean：true=成功 | int：≥0=成功，负数=失败 |
| **唤醒策略** | 唤醒队头下一个节点（单个） | 唤醒队头下一个 + 传播给后续共享节点 |
| **节点标记** | `nextWaiter = null` | `nextWaiter = Node.SHARED` |
| **释放传播** | 无传播，唤醒单个 | `doReleaseShared` 循环传播 |
| **可重入支持** | 子类可实现（如 ReentrantLock） | 一般不可重入（语义不同） |
| **吞吐量（读多写少）** | 低（串行） | 高（并发读） |
| **实现复杂度** | 低 | 高（传播逻辑复杂，有历史 Bug） |

### 4.2 选型决策树

```
需要并发控制？
├── 只有一个线程能执行临界区 → 独占锁（ReentrantLock）
│     ├── 需要读写分离？ → ReentrantReadWriteLock（读=共享，写=独占）
│     └── 需要乐观读？ → StampedLock（非 AQS）
└── 多个线程可并发执行？
      ├── 控制并发数量（如连接池限流）→ Semaphore（共享）
      ├── 等待多个操作完成 → CountDownLatch（共享，一次性）
      └── 多个线程相互等待到同一起跑线 → CyclicBarrier（独占+Condition）
```

---

## 5. 工作原理与实现机制

### 5.1 静态结构

**为什么用 CLH 变体而不是普通队列？**

普通队列的出队操作需要修改头节点，在高并发下 CAS 竞争激烈。CLH 变体让每个节点只自旋/监听自己的前驱节点状态，天然分散了竞争点。AQS 将自旋改为 `LockSupport.park`（避免 CPU 空转），并增加后驱指针以支持取消节点的跳过。

**为什么 tryAcquireShared 返回 int 而 tryAcquire 返回 boolean？**

独占模式只需知道"成功/失败"；共享模式需要知道"成功后剩余资源数"，以便判断是否还需要继续唤醒后续的共享节点（`remaining > 0` 则传播）。这是两种模式在接口层面的根本差异。

### 5.2 动态行为：独占锁 acquire 流程

```
Thread 调用 lock() → acquire(1)
  │
  ├─ [1] tryAcquire(1)  ← 子类实现，CAS(state, 0, 1)
  │     ├─ 成功 → 直接返回，线程持有锁 ✅
  │     └─ 失败 → 继续
  │
  ├─ [2] addWaiter(Node.EXCLUSIVE)
  │       CAS 将新节点追加到队列尾部
  │       nextWaiter = null（独占标记）
  │
  └─ [3] acquireQueued(node, 1)  ← 自旋等待
          loop:
            ├─ 前驱是 head？ → tryAcquire(1)
            │     成功 → setHead(node), 返回 ✅
            │     失败 → 继续自旋
            ├─ shouldParkAfterFailedAcquire？
            │     将前驱 waitStatus 设为 SIGNAL(-1)
            └─ parkAndCheckInterrupt()
                  LockSupport.park(this)  ← 挂起，等待唤醒
```

### 5.3 动态行为：独占锁 release 流程

```
Thread 调用 unlock() → release(1)
  │
  ├─ [1] tryRelease(1)  ← 子类实现，state=0
  │     失败 → 抛异常（未持有锁）
  │     成功 → 继续
  │
  └─ [2] unparkSuccessor(head)
          找到 head.next 中第一个 waitStatus ≤ 0 的节点
          LockSupport.unpark(node.thread)  ← 唤醒队头线程
          被唤醒线程回到 acquireQueued 的 loop 重试 tryAcquire
```

### 5.4 动态行为：共享锁 acquireShared 流程

```
Thread 调用 acquire() → acquireShared(1)
  │
  ├─ [1] tryAcquireShared(1)  ← 子类实现
  │     返回 r:
  │       r < 0  → 失败，进入队列
  │       r >= 0 → 成功，进入 setHeadAndPropagate ← ⚠️ 关键差异点
  │
  ├─ [成功路径] setHeadAndPropagate(node, r)
  │     setHead(node)           ← 将当前节点设为新 head
  │     if (r > 0 || ...) {
  │       doReleaseShared()     ← 传播：唤醒后续共享节点！
  │     }
  │
  └─ [失败路径] doAcquireShared(1)
          addWaiter(Node.SHARED)  ← nextWaiter = Node.SHARED（共享标记）
          loop:
            前驱是 head？ → tryAcquireShared(1)
              r >= 0 → setHeadAndPropagate(node, r)  ← 同样触发传播
            → parkAndCheckInterrupt()
```

### 5.5 动态行为：共享锁 releaseShared 流程

```
Thread 调用 release() → releaseShared(1)
  │
  ├─ [1] tryReleaseShared(1)  ← 子类实现，CAS 增加 state
  │
  └─ [2] doReleaseShared()  ← ⚠️ 独占模式没有对应方法，这是最大差异
          loop:
            h = head
            if h.waitStatus == SIGNAL:
              CAS(h.waitStatus, SIGNAL, 0)
              unparkSuccessor(h)   ← 唤醒队头
            elif h.waitStatus == 0:
              CAS(h.waitStatus, 0, PROPAGATE)  ← 设置传播标志
            if head == h: break    ← head 未变化则退出（变化说明有新线程入队）
```

### 5.6 关键设计决策

**决策 1：为什么共享模式需要 `PROPAGATE` 状态？**

历史上（JDK 6 早期版本）没有 PROPAGATE 状态，存在并发 Bug：当多个线程同时 `releaseShared` 时，可能出现后续等待的共享节点永远得不到唤醒的竞态条件（lost wakeup）。JDK 6u11 引入 `PROPAGATE(-3)` 状态，确保即使 `setHeadAndPropagate` 看到的 `propagate=0`，也能通过检测 `waitStatus < 0` 触发传播，彻底消除该 Bug。

> Trade-off：增加了一个状态位的复杂度，换取了正确性。

**决策 2：为什么独占 release 只唤醒一个，而共享 release 要循环传播？**

独占锁 release 后只有一个线程能成功获得锁，唤醒多个线程只会造成"惊群效应"（thundering herd），徒增上下文切换开销。共享锁 release 后可能多个等待线程都能成功获取，必须传播唤醒，否则会降低并发度。

> Trade-off：共享模式下 `doReleaseShared` 是个循环，在高并发 `releaseShared` 时可能有多个线程同时执行此循环，存在短暂的 CAS 竞争，但这是为了高吞吐必须付出的代价。

**决策 3：为什么 `addWaiter` 使用 CAS + 自旋而不是加锁？**

在入队操作上加锁会引入递归的同步问题。使用 CAS 自旋（`compareAndSetTail`）在低竞争时极快（纳秒级），高竞争时也只在尾节点上竞争，不影响队列中已有节点的操作。

---

## 6. 高可靠性保障

### 6.1 中断处理

独占模式：`acquireInterruptibly` 在 `park` 期间检测中断，立即抛出 `InterruptedException`，而非像 `acquire` 那样只在退出后补中断。

共享模式：同理有 `acquireSharedInterruptibly`。

### 6.2 超时机制

`tryAcquireNanos` / `tryAcquireSharedNanos`：计算 deadline，若剩余等待时间 > 1000ns 则 park 指定时长，否则自旋（避免短时超时带来 park/unpark 系统调用开销）。

### 6.3 取消（Cancellation）

节点 `waitStatus` 设为 `CANCELLED(1)` 后，`shouldParkAfterFailedAcquire` 会跳过所有已取消节点，重新链接 prev 指针，确保队列不因取消节点而卡死。

### 6.4 可观测性

| 监控维度 | 方法/指标 | 正常阈值参考 |
|---------|---------|------------|
| 等待队列长度 | `lock.getQueueLength()` | < 100（业务相关，超过需排查） |
| 是否有线程等待 | `lock.hasQueuedThreads()` | false 为理想状态 |
| 锁持有线程 | `lock.getOwner()`（ReentrantLock） | 不应长时间为同一线程 |
| 锁竞争率 | 自定义：`tryLock` 失败次数 / 总次数 | < 5% 为低竞争 |
| 平均等待时间 | 自定义埋点 | < 1ms 为低延迟锁 |

---

## 7. 使用实践与故障手册

### 7.1 典型使用方式

#### 自定义独占锁（基于 AQS）

```java
// 运行环境：JDK 8+
import java.util.concurrent.locks.AbstractQueuedSynchronizer;

public class SimpleMutex {
    private final Sync sync = new Sync();

    // AQS 子类：独占模式
    private static class Sync extends AbstractQueuedSynchronizer {
        // tryAcquire: state=0 空闲，CAS 置为 1
        @Override
        protected boolean tryAcquire(int arg) {
            // compareAndSetState 是 AQS 提供的 CAS 工具方法
            if (compareAndSetState(0, 1)) {
                setExclusiveOwnerThread(Thread.currentThread());
                return true;
            }
            return false;
        }

        // tryRelease: 清空 state
        @Override
        protected boolean tryRelease(int arg) {
            if (getState() == 0) throw new IllegalMonitorStateException();
            setExclusiveOwnerThread(null);
            setState(0); // state 写在 setExclusiveOwnerThread 之后（happens-before 保证）
            return true;
        }

        @Override
        protected boolean isHeldExclusively() {
            return getState() == 1;
        }
    }

    public void lock()   { sync.acquire(1); }
    public void unlock() { sync.release(1); }
}
```

#### 自定义共享锁（固定许可数）

```java
// 运行环境：JDK 8+（等价于 Semaphore 的简化实现）
public class SimpleSharedLock {
    private final Sync sync;

    public SimpleSharedLock(int permits) {
        sync = new Sync(permits);
    }

    private static class Sync extends AbstractQueuedSynchronizer {
        Sync(int permits) {
            setState(permits); // state 初始值 = 许可总数
        }

        // tryAcquireShared: 返回 ≥0 成功，<0 失败
        @Override
        protected int tryAcquireShared(int arg) {
            for (;;) {
                int current = getState();
                int remaining = current - arg;
                // remaining < 0: 无资源，直接返回负数（AQS 据此判定失败）
                if (remaining < 0 || compareAndSetState(current, remaining)) {
                    return remaining;
                }
                // CAS 失败：被其他线程抢先，自旋重试
            }
        }

        // tryReleaseShared: 返回 true 表示需要唤醒等待者
        @Override
        protected boolean tryReleaseShared(int arg) {
            for (;;) {
                int current = getState();
                int next = current + arg;
                if (next < current) throw new Error("Maximum permit count exceeded");
                if (compareAndSetState(current, next)) {
                    return true; // 返回 true 触发 doReleaseShared
                }
            }
        }
    }

    public void acquire() throws InterruptedException { sync.acquireSharedInterruptibly(1); }
    public void release() { sync.releaseShared(1); }
}
```

**关键配置项风险说明**

| 要点 | 独占模式 | 共享模式 |
|------|---------|---------|
| `setState` vs `compareAndSetState` | `tryRelease` 中可直接 `setState(0)`，因为只有持有者才能 release | `tryReleaseShared` 必须用 CAS，多个线程可能并发 release |
| 返回值语义 | boolean，true=释放成功 | int（acquire）/boolean（release），int 的正负决定是否传播 |
| 忘记 `setExclusiveOwnerThread` | 导致 `isHeldExclusively` 错误，Condition 使用异常 | 共享模式一般不需要此字段 |

### 7.2 故障模式手册

```
【故障1：死锁——线程永久阻塞在 park】
- 现象：应用无响应，线程 dump 显示大量线程 WAITING at LockSupport.park
- 根本原因：
    ① 独占锁未在 finally 中释放（异常路径漏 unlock）
    ② 共享锁 tryReleaseShared 返回 false 导致 doReleaseShared 不执行
- 预防措施：lock/unlock 必须 try-finally 包裹；单测覆盖异常路径
- 应急处理：jstack <pid> 分析锁链，找到锁持有者线程，确认业务逻辑是否卡死

【故障2：活锁——CPU 100% 但无进展】
- 现象：某线程 CPU 占用率极高，但业务无产出
- 根本原因：tryAcquire/tryAcquireShared 实现中有无限自旋而不挂起
    （例如在 tryAcquire 中自己实现了 for 循环而不是返回 false 让 AQS 处理）
- 预防措施：tryAcquire 应只做一次 CAS 尝试并返回结果，排队逻辑交给 AQS
- 应急处理：jstack 找到自旋线程，分析 tryAcquire 实现

【故障3：共享锁唤醒丢失（JDK 6 早期版本）】
- 现象：CountDownLatch.await() 的线程在 countDown 到 0 后仍未被唤醒
- 根本原因：缺少 PROPAGATE 状态导致的竞态，已在 JDK 6u11 修复
- 预防措施：使用 JDK 8+
- 应急处理：升级 JDK 版本

【故障4：公平锁下吞吐量骤降】
- 现象：高并发场景下 ReentrantLock(true) 的 TPS 比 ReentrantLock(false) 低 5~10 倍
- 根本原因：公平模式下每次 tryAcquire 都要检查队列是否有前驱（hasQueuedPredecessors），
    即使锁空闲也不能直接 CAS 抢占，增加了线程上下文切换
- 预防措施：除非业务强依赖 FIFO 顺序，默认使用非公平锁
- 应急处理：切换为非公平模式，重新压测验证

【故障5：Semaphore 许可泄漏】
- 现象：可用许可数随时间单调递减，最终所有线程永久阻塞
- 根本原因：acquire 成功后未在 finally 中 release（异常路径遗漏）
- 预防措施：try { acquire(); doWork(); } finally { release(); }
- 应急处理：重启服务或通过 Semaphore.release(n) 手动补充许可（临时方案）
```

### 7.3 边界条件与局限性

- `ReentrantLock` 重入深度受 `state` 上限（`Integer.MAX_VALUE`）限制，超出后 `tryAcquire` 抛 `Error`，正常业务不会触发（重入 21 亿次）。
- `Semaphore` 初始许可数为 0 时，所有 `acquire` 立即阻塞，直到 `release` 补充许可，这是合法用法（实现 CountDownLatch 语义）。
- AQS 的 CLH 队列在极高并发下（>10,000 线程竞争同一锁）入队的 CAS 尾节点会出现明显竞争，此时应考虑分片锁（Striped64 思路）或无锁数据结构。
- `LockSupport.park` 对虚拟线程（JDK 21 Project Loom）行为不同：虚拟线程 park 不会阻塞载体线程，AQS 在虚拟线程下的吞吐特性与平台线程有较大差异。⚠️ 存疑：VirtualThread 与 AQS 结合的最佳实践尚在演进中。

---

## 8. 性能调优指南

### 8.1 性能瓶颈识别

| 瓶颈层 | 识别方法 | 工具 |
|-------|---------|------|
| 锁竞争过高 | jstack 发现大量 BLOCKED/WAITING 线程；`ReentrantLock.getQueueLength() > 50` | jstack、Arthas `thread -b` |
| CAS 失败率高 | 独占模式入队自旋次数多（JVM 内部计数）；CPU 用量高但 TPS 低 | async-profiler CPU 火焰图 |
| 上下文切换过多 | `vmstat` 中 `cs` 列持续 > 100,000/s | vmstat、perf |
| park/unpark 系统调用开销 | 锁持有时间 < 1μs 但频繁切换 | perf stat -e context-switches |

### 8.2 调优步骤（按优先级）

1. **减少锁粒度**：将单一大锁拆分为多个细粒度锁（锁分段），目标：单个锁的平均等待队列长度 < 5。
2. **非公平优先**：默认使用 `ReentrantLock(false)`，仅在有明确公平性需求时开启公平模式，非公平模式吞吐量通常高 3~10 倍。
3. **读写分离**：读多写少（读占比 > 70%）场景使用 `ReentrantReadWriteLock`，理论上读并发度可提升至 CPU 核数倍。
4. **缩短锁持有时间**：将锁内的 IO、远程调用、复杂计算移到锁外，目标：单次锁持有时间 < 100μs。
5. **尝试无锁**：对计数器类场景使用 `AtomicLong` / `LongAdder`（高并发下 LongAdder 比 AtomicLong 吞吐量高 10~50 倍）。

### 8.3 调优参数速查（JVM 层）

| 参数 | 默认值 | 推荐场景 | 调整风险 |
|------|-------|---------|---------|
| `-XX:+UseBiasedLocking` | JDK 8-14 开启，JDK 15 弃用 | 单线程高频加锁场景 | JDK 15+ 已移除，无需配置 |
| `-XX:BiasedLockingStartupDelay` | 4000ms | 希望启动即生效：设为 0 | 启动期轻微性能影响 |
| 无（AQS 自身无 JVM 参数） | — | AQS 无可配置参数 | 通过代码层选型调优 |

---

## 9. 演进方向与未来趋势

### 9.1 虚拟线程（JDK 21 Loom）对 AQS 的冲击

JDK 21 正式引入虚拟线程。`synchronized` 在 JDK 21 中持续优化（JDK 23 解决了 `synchronized` 导致的 carrier thread pin 问题），而 `ReentrantLock`（基于 AQS）天然与虚拟线程兼容——`LockSupport.park` 在虚拟线程上会 yield 载体线程而非阻塞。

**对使用者的影响**：在虚拟线程密集型应用（百万级并发）中，优先使用 `ReentrantLock` 而非 `synchronized`，避免虚拟线程被 pin 住载体线程，直到 `synchronized` 的 pin 问题在目标 JDK 版本完全修复。

### 9.2 结构化并发（JDK 21 JEP 453）

结构化并发 API（`StructuredTaskScope`）提供了更高层的并发抽象，减少手动使用 Lock/Semaphore 的场景。长期来看，直接操作 AQS 的频率将下降，但 AQS 作为底层基础设施仍不可替代。

### 9.3 社区动向

OpenJDK 正在探讨将 `AbstractQueuedSynchronizer` 与虚拟线程调度器深度集成，使 park/unpark 在混合线程模型下更高效。关注 [JDK-8284065](https://bugs.openjdk.org/browse/JDK-8284065) 等相关 Issue。

---

## 10. 面试高频题

```
【基础理解层】

Q：AQS 中独占模式和共享模式最直观的区别是什么？
A：独占模式同一时刻只有一个线程能持有同步状态（state 被单个线程占用），
   共享模式允许多个线程同时持有（state 代表剩余许可数，> 0 即可获取）。
   接口层面：独占实现 tryAcquire（返回 boolean），共享实现 tryAcquireShared（返回 int）。
考察意图：确认候选人对 AQS 两种模式有基本区分，了解接口差异。

Q：为什么 tryAcquireShared 返回 int 而不是 boolean？
A：返回值不仅表示成功/失败，还携带"剩余资源数"信息。AQS 据此判断是否继续唤醒后续的
   共享等待节点（remaining > 0 则传播）。若只返回 boolean，AQS 无法得知是否需要传播。
考察意图：考察对共享模式传播机制的理解深度。

【原理深挖层】

Q：AQS 中 Node.PROPAGATE 状态的作用是什么？为什么需要它？
A：PROPAGATE（waitStatus = -3）是共享模式专用状态，用于解决并发 releaseShared 时
   可能出现的唤醒丢失（lost wakeup）竞态条件。
   场景：线程 A 执行 setHeadAndPropagate 时看到 propagate=0（许可刚被 B 拿走），
   但 B 随即 release 了，此时若无 PROPAGATE 记录"有释放发生"，A 不会触发传播，
   后续等待的共享线程永远得不到唤醒。PROPAGATE 让这种"已发生的释放"被持久化记录，
   setHeadAndPropagate 通过 h.waitStatus < 0 检测到它，从而正确触发传播。
   此 Bug 在 JDK 6u11 修复，可参考 Doug Lea 的修复说明。
考察意图：考察候选人是否深入研读过 AQS 源码及其历史演进，能否分析并发场景下的竞态。

Q：独占锁 release 和共享锁 releaseShared 的唤醒逻辑有何本质区别？
A：独占：unparkSuccessor(head) 只唤醒队头下一个节点，唤醒单个线程。
   共享：doReleaseShared() 是一个循环，唤醒队头后若 head 发生变化（新线程成为 head）
   则继续循环；同时设置 PROPAGATE 确保信号向后传播，可能连续唤醒多个共享等待节点。
   本质：共享模式需要"接力唤醒"，独占模式是"点对点唤醒"。
考察意图：考察对两种释放流程时序的掌握程度，以及是否理解为何共享模式需要循环传播。

【生产实战层】

Q：生产中何时选公平锁，何时选非公平锁？有何数据依据？
A：非公平锁（默认）在高并发下吞吐量通常比公平锁高 3~10 倍，原因是：
   公平模式每次 tryAcquire 都调用 hasQueuedPredecessors()，即便锁空闲也不能直接 CAS，
   强制线程入队，增加了上下文切换。
   选公平锁的场景：①业务对请求处理顺序有强依赖；②需避免线程饥饿（某线程可能长期拿不到锁）。
   大多数业务场景选非公平锁，并通过监控 getQueueLength() 判断竞争是否过热。
考察意图：考察候选人是否有锁调优的生产经验，能否给出量化依据而非凭感觉选型。

Q：如果发现线上服务 CPU 正常但 TPS 骤降，如何排查是否为 AQS 锁竞争导致？
A：①jstack 抓取线程快照，统计 WAITING/BLOCKED 状态线程占比，定位锁对象（waiting on / locked by）
   ②使用 Arthas `thread -b` 找到阻塞最多线程的持锁线程
   ③使用 async-profiler 生成 lock 火焰图，定位热点锁
   ④在代码层通过 ReentrantLock.getQueueLength() 埋点监控，若持续 > 50 则锁竞争严重
   ⑤验证修复：拆分锁粒度或改为读写锁后，重新压测对比 TPS 是否恢复。
考察意图：考察候选人是否具备系统性排查并发问题的工程能力，而非只会背理论。
```

---

## 11. 文档元信息

### 验证声明

```
本文档内容经过以下验证：
✅ 与官方 OpenJDK 源码一致性核查（JDK 17 AbstractQueuedSynchronizer.java）
✅ AQS 工作原理与 Doug Lea 原论文（The java.util.concurrent Synchronizer Framework, 2004）核对
✅ PROPAGATE Bug 修复描述参考 JDK 官方 Bug 记录与社区分析

⚠️ 以下内容未经本地环境验证，仅基于文档推断：
  - 第9节：虚拟线程与 AQS 结合的性能数据（Loom 仍在演进）
  - 第8.3节：JVM BiasedLocking 参数在 JDK 21+ 的确切行为
  - 性能数字（如公平/非公平锁吞吐差异 3~10 倍）来自社区压测报告，具体数值因业务负载而异
```

### 知识边界声明

```
本文档适用范围：JDK 8 ~ JDK 21，x86_64 平台，标准 OpenJDK/OracleJDK
不适用场景：
  - Kotlin 协程并发原语（Mutex/Semaphore 使用挂起函数，非 AQS）
  - GraalVM Native Image（部分 Unsafe 操作行为不同）
  - Android 平台（使用 ART，底层实现有差异）
  - Confluent Platform / Azul JDK 私有优化版本
```

### 参考资料

```
官方文档与源码：
  - OpenJDK AQS 源码（JDK 17）：
    https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/util/concurrent/locks/AbstractQueuedSynchronizer.java
  - Doug Lea 原论文：
    http://gee.cs.oswego.edu/dl/papers/aqs.pdf

核心分析：
  - PROPAGATE 状态修复说明（JDK Bug 数据库）：
    https://bugs.openjdk.org/browse/JDK-6801020
  - AQS 独占/共享流程深度分析（infoq.cn）：
    https://www.infoq.cn/article/jdk1.8-abstractqueuedsynchronizer

延伸阅读：
  - 《Java 并发编程的艺术》第 5 章，方腾飞等著
  - Virtual Threads 与 AQS 兼容性讨论：
    https://openjdk.org/jeps/444
  - async-profiler（锁竞争分析工具）：
    https://github.com/async-profiler/async-profiler
```

---
