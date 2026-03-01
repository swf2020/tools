# CountDownLatch与CyclicBarrier实现原理

## 1. 概述

### 1.1 CountDownLatch
**CountDownLatch** 是一个同步辅助类，允许一个或多个线程等待一组其他线程完成操作。它通过一个计数器实现，计数器初始化为一个正整数，表示需要等待的事件数量。当某个事件发生时，计数器递减。当计数器达到零时，所有等待的线程被释放。

**核心特性：**
- 一次性使用（不可重置）
- 基于AQS（AbstractQueuedSynchronizer）实现
- 计数器递减不可逆

### 1.2 CyclicBarrier
**CyclicBarrier** 是一个同步辅助类，允许一组线程互相等待，直到所有线程都到达某个公共屏障点。与CountDownLatch不同，CyclicBarrier可以重置并重复使用，因此称为"循环屏障"。

**核心特性：**
- 可重复使用（可重置）
- 支持可选的屏障动作
- 基于ReentrantLock和Condition实现

## 2. 实现原理深度解析

### 2.1 CountDownLatch实现原理

#### 2.1.1 内部结构
```java
public class CountDownLatch {
    // 内部同步器，继承自AQS
    private static final class Sync extends AbstractQueuedSynchronizer {
        Sync(int count) {
            setState(count);  // 使用AQS的state表示计数器
        }
        
        int getCount() {
            return getState();
        }
        
        // 尝试获取共享锁
        protected int tryAcquireShared(int acquires) {
            return (getState() == 0) ? 1 : -1;
        }
        
        // 尝试释放共享锁（递减计数器）
        protected boolean tryReleaseShared(int releases) {
            for (;;) {
                int c = getState();
                if (c == 0) return false;
                int nextc = c - 1;
                if (compareAndSetState(c, nextc))
                    return nextc == 0;
            }
        }
    }
    
    private final Sync sync;
}
```

#### 2.1.2 核心操作原理

**1. 初始化：**
```java
public CountDownLatch(int count) {
    if (count < 0) throw new IllegalArgumentException("count < 0");
    this.sync = new Sync(count);
}
```

**2. await()方法实现：**
```java
public void await() throws InterruptedException {
    sync.acquireSharedInterruptibly(1);
}

// AQS中的实现
public final void acquireSharedInterruptibly(int arg) throws InterruptedException {
    if (Thread.interrupted())
        throw new InterruptedException();
    if (tryAcquireShared(arg) < 0)  // 计数器不为0时返回-1
        doAcquireSharedInterruptibly(arg);  // 线程进入等待队列
}
```

**3. countDown()方法实现：**
```java
public void countDown() {
    sync.releaseShared(1);
}

// 核心递减逻辑
protected boolean tryReleaseShared(int releases) {
    for (;;) {  // 自旋CAS操作
        int c = getState();
        if (c == 0) return false;  // 已经是0，直接返回
        int nextc = c - 1;
        // CAS更新state，保证原子性
        if (compareAndSetState(c, nextc))
            return nextc == 0;  // 返回true表示计数器归零
    }
}
```

**4. 唤醒机制：**
当计数器归零时，会调用`doReleaseShared()`方法唤醒等待队列中的所有线程：
```java
private void doReleaseShared() {
    for (;;) {
        Node h = head;
        if (h != null && h != tail) {
            int ws = h.waitStatus;
            if (ws == Node.SIGNAL) {
                if (!compareAndSetWaitStatus(h, Node.SIGNAL, 0))
                    continue;
                unparkSuccessor(h);  // 唤醒后继节点
            }
        }
        if (h == head) break;
    }
}
```

### 2.2 CyclicBarrier实现原理

#### 2.2.1 内部结构
```java
public class CyclicBarrier {
    // 内部类，用于记录屏障的每一次使用
    private static class Generation {
        boolean broken = false;  // 屏障是否被破坏
    }
    
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition trip = lock.newCondition();  // 等待条件
    private final int parties;  // 需要等待的线程数
    private final Runnable barrierCommand;  // 屏障动作
    private Generation generation = new Generation();  // 当前代
    private int count;  // 当前等待的线程数
}
```

#### 2.2.2 核心操作原理

**1. await()方法实现：**
```java
public int await() throws InterruptedException, BrokenBarrierException {
    try {
        return dowait(false, 0L);
    } catch (TimeoutException toe) {
        throw new Error(toe);
    }
}

private int dowait(boolean timed, long nanos)
    throws InterruptedException, BrokenBarrierException, TimeoutException {
    
    final ReentrantLock lock = this.lock;
    lock.lock();
    try {
        final Generation g = generation;
        
        if (g.broken)  // 屏障已被破坏
            throw new BrokenBarrierException();
        
        if (Thread.interrupted()) {
            breakBarrier();  // 中断时破坏屏障
            throw new InterruptedException();
        }
        
        int index = --count;  // 递减计数器
        if (index == 0) {  // 最后一个线程到达
            boolean ranAction = false;
            try {
                final Runnable command = barrierCommand;
                if (command != null)
                    command.run();  // 执行屏障动作
                ranAction = true;
                nextGeneration();  // 重置屏障，进入下一代
                return 0;
            } finally {
                if (!ranAction)
                    breakBarrier();
            }
        }
        
        // 不是最后一个线程，进入等待
        for (;;) {
            try {
                if (!timed)
                    trip.await();  // 无限期等待
                else if (nanos > 0L)
                    nanos = trip.awaitNanos(nanos);  // 超时等待
            } catch (InterruptedException ie) {
                // 处理中断
            }
            
            if (g.broken)
                throw new BrokenBarrierException();
            
            if (g != generation)  // 已经进入下一代
                return index;
            
            if (timed && nanos <= 0L) {
                breakBarrier();
                throw new TimeoutException();
            }
        }
    } finally {
        lock.unlock();
    }
}
```

**2. 屏障重置机制：**
```java
private void nextGeneration() {
    // 唤醒所有等待线程
    trip.signalAll();
    // 重置计数器
    count = parties;
    // 创建新的Generation
    generation = new Generation();
}

private void breakBarrier() {
    generation.broken = true;
    count = parties;
    trip.signalAll();  // 唤醒所有线程，但屏障已破坏
}
```

## 3. 核心对比分析

### 3.1 相同点
| 特性 | 两者共同点 |
|------|-----------|
| 同步机制 | 都是线程同步辅助类 |
| 等待机制 | 都支持线程等待 |
| JUC包 | 都属于java.util.concurrent包 |

### 3.2 差异对比
| 特性 | CountDownLatch | CyclicBarrier |
|------|---------------|---------------|
| **使用次数** | 一次性使用 | 可重复使用 |
| **计数器方向** | 递减（countDown） | 递增（await） |
| **初始化参数** | 需要等待的事件数 | 需要等待的线程数 |
| **核心操作** | countDown() + await() | await() |
| **内部实现** | 基于AQS | 基于ReentrantLock+Condition |
| **重置能力** | 不可重置 | 自动重置 |
| **屏障动作** | 不支持 | 支持Runnable屏障动作 |
| **异常处理** | 相对简单 | 需要处理BrokenBarrierException |
| **适用场景** | 一个线程等待多个线程 | 多个线程互相等待 |

## 4. 底层实现机制对比

### 4.1 同步机制
**CountDownLatch：**
- 基于共享锁模式
- 使用AQS的state作为计数器
- 使用CLH队列管理等待线程

**CyclicBarrier：**
- 基于条件等待/通知机制
- 使用ReentrantLock保证互斥
- 使用Condition管理等待线程

### 4.2 状态管理
```java
// CountDownLatch的状态流转
初始状态: state = N (N>0)
countDown(): state = state - 1 (CAS操作)
终止状态: state = 0 → 唤醒所有等待线程

// CyclicBarrier的状态流转
初始状态: count = parties, generation = new Generation()
await(): count = count - 1
等待状态: count > 0 → 线程进入Condition队列
完成状态: count = 0 → 执行屏障动作 → nextGeneration()
重置状态: count = parties, generation更新
```

### 4.3 性能考虑
1. **CountDownLatch**：
   - 更轻量级，直接使用AQS
   - 无锁竞争时性能更好
   - 适合简单的一次性等待场景

2. **CyclicBarrier**：
   - 更复杂的功能带来额外开销
   - 锁竞争可能成为瓶颈
   - 适合复杂的可重用场景

## 5. 源码级关键点

### 5.1 CountDownLatch关键代码片段
```java
// 核心：CAS递减计数器
protected boolean tryReleaseShared(int releases) {
    for (;;) {  // 自旋保证成功
        int c = getState();
        if (c == 0)
            return false;
        int nextc = c - 1;
        // 关键：使用CAS保证线程安全
        if (compareAndSetState(c, nextc))
            return nextc == 0;  // 返回是否归零
    }
}
```

### 5.2 CyclicBarrier关键代码片段
```java
// 关键：屏障重置逻辑
private void nextGeneration() {
    trip.signalAll();      // 1. 唤醒所有等待线程
    count = parties;       // 2. 重置计数器
    generation = new Generation();  // 3. 创建新代
}

// 关键：屏障破坏处理
private void breakBarrier() {
    generation.broken = true;  // 标记屏障为破坏状态
    count = parties;           // 重置计数器
    trip.signalAll();          // 唤醒所有等待线程
}
```

## 6. 使用场景分析

### 6.1 CountDownLatch适用场景
1. **启动等待**：主线程等待所有服务初始化完成
2. **结束等待**：多个线程完成后触发某个操作
3. **并行任务同步**：多个并行任务完成后汇总结果

```java
// 典型使用模式
CountDownLatch startSignal = new CountDownLatch(1);
CountDownLatch doneSignal = new CountDownLatch(N);

// 工作线程
new Thread(() -> {
    startSignal.await();      // 等待开始信号
    doWork();
    doneSignal.countDown();   // 完成计数
}).start();

// 主线程
startSignal.countDown();      // 发出开始信号
doneSignal.await();           // 等待所有完成
```

### 6.2 CyclicBarrier适用场景
1. **多阶段任务**：多阶段计算，每阶段需要同步
2. **数据分片处理**：多个线程处理数据分片，最后合并结果
3. **模拟测试**：模拟并发场景，所有线程同时开始

```java
// 典型使用模式
CyclicBarrier barrier = new CyclicBarrier(N, () -> {
    // 所有线程到达后执行
    System.out.println("所有线程到达屏障");
});

for (int i = 0; i < N; i++) {
    new Thread(() -> {
        doWorkPart1();
        barrier.await();      // 等待其他线程
        doWorkPart2();
        barrier.await();      // 可重复使用
    }).start();
}
```

## 7. 注意事项

### 7.1 CountDownLatch注意事项
1. **一次性**：计数器归零后无法再次使用
2. **countDown调用**：确保countDown()被调用足够次数
3. **内存一致性**：countDown()之前的操作happen-before await()返回后的操作

### 7.2 CyclicBarrier注意事项
1. **屏障破坏**：线程中断、超时或异常会导致屏障破坏
2. **重置成本**：每次使用都会创建新的Generation对象
3. **死锁风险**：如果等待线程数超过parties，会导致死锁
4. **屏障动作异常**：屏障动作抛出异常会导致屏障破坏

## 8. 总结

**CountDownLatch**和**CyclicBarrier**都是Java并发包中重要的同步工具，但设计理念和使用场景不同：

- **CountDownLatch**更像是一个"倒计时门闩"，强调一个或多个线程等待一组事件发生，具有**单向、一次性**的特点。

- **CyclicBarrier**更像是一个"循环栅栏"，强调一组线程互相等待到达共同点，具有**多向、可重用**的特点。

**选择建议：**
- 如果只需要一次性的等待机制，使用CountDownLatch
- 如果需要多阶段的、可重用的同步，使用CyclicBarrier
- 如果需要在等待点执行特定动作，只能使用CyclicBarrier
- 如果等待线程数固定且需要互相等待，使用CyclicBarrier

两者都体现了Java并发包"分工与协作"的设计思想，合理选择和使用可以大大提高并发程序的可靠性和性能。