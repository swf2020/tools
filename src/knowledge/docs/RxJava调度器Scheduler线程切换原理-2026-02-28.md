# RxJava调度器(Scheduler)线程切换原理

## 1. 概述

### 1.1 调度器(Scheduler)的作用
RxJava调度器(Scheduler)是RxJava异步编程的核心组件，它负责：
- 控制Observable操作在特定线程上执行
- 实现观察者(Observer)与被观察者(Observable)之间的线程分离
- 提供线程池管理，优化资源利用

### 1.2 主要调度器类型
```java
// 常用调度器
Schedulers.io()            // I/O密集型操作
Schedulers.computation()   // 计算密集型操作
Schedulers.newThread()     // 每次创建新线程
Schedulers.single()        // 单一线程顺序执行
Schedulers.trampoline()    // 当前线程排队执行
AndroidSchedulers.mainThread() // Android主线程
```

## 2. 核心架构设计

### 2.1 Scheduler类结构
```
Scheduler
├── createWorker()
├── scheduleDirect()
├── schedulePeriodicallyDirect()
│
└── Worker
    ├── schedule()
    ├── schedulePeriodically()
    └── dispose()
```

### 2.2 关键接口定义
```java
public abstract class Scheduler {
    // 核心方法：创建工作单元
    public abstract Worker createWorker();
    
    // 直接调度任务
    public Disposable scheduleDirect(Runnable run) {
        // 创建Worker并立即调度
        Worker w = createWorker();
        return w.schedule(runnable);
    }
}

public abstract static class Worker implements Disposable {
    // 调度一次性任务
    public abstract Disposable schedule(@NonNull Runnable run);
    
    // 调度周期性任务
    public abstract Disposable schedulePeriodically(
        @NonNull Runnable run, 
        long initialDelay, 
        long period, 
        @NonNull TimeUnit unit
    );
}
```

## 3. 线程切换原理详解

### 3.1 subscribeOn原理

#### 3.1.1 操作符实现
```java
public final Observable<T> subscribeOn(Scheduler scheduler) {
    return new ObservableSubscribeOn<T>(this, scheduler);
}

// ObservableSubscribeOn核心逻辑
static final class ObservableSubscribeOn<T> extends AbstractObservableWithUpstream<T, T> {
    final Scheduler scheduler;
    
    @Override
    public void subscribeActual(Observer<? super T> observer) {
        // 1. 创建SubscribeOnObserver包装原始观察者
        SubscribeOnObserver<T> parent = new SubscribeOnObserver<>(observer);
        
        // 2. 通知下游订阅开始
        observer.onSubscribe(parent);
        
        // 3. 在指定调度器上执行订阅操作
        parent.setDisposable(
            scheduler.scheduleDirect(new SubscribeTask(parent))
        );
    }
    
    final class SubscribeTask implements Runnable {
        private final SubscribeOnObserver<T> parent;
        
        @Override
        public void run() {
            // 4. 在新线程上执行实际订阅
            source.subscribe(parent);
        }
    }
}
```

#### 3.1.2 订阅流程图
```
Observer.subscribe()
    ↓
Observable.subscribeActual()
    ↓
scheduler.scheduleDirect(SubscribeTask)  // 切换到目标线程
    ↓
在目标线程执行: source.subscribe(parent)
    ↓
上游开始发射数据 → SubscribeOnObserver.onNext() → 下游Observer
```

### 3.2 observeOn原理

#### 3.2.1 操作符实现
```java
public final Observable<T> observeOn(Scheduler scheduler) {
    return new ObservableObserveOn<T>(this, scheduler, false, bufferSize());
}

// ObservableObserveOn核心逻辑
static final class ObservableObserveOn<T> extends AbstractObservableWithUpstream<T, T> {
    @Override
    public void subscribeActual(Observer<? super T> observer) {
        // 创建Worker处理线程切换
        Worker worker = scheduler.createWorker();
        
        // 包装原始观察者
        ObserveOnObserver<T> parent = new ObserveOnObserver<>(
            observer, worker, delayError, bufferSize
        );
        
        // 执行上游订阅
        source.subscribe(parent);
    }
}

// ObserveOnObserver关键逻辑
static final class ObserveOnObserver<T> extends BasicIntQueueDisposable<T>
    implements Observer<T>, Runnable {
    
    // 事件队列
    SimpleQueue<T> queue;
    
    @Override
    public void onNext(T t) {
        if (done) return;
        
        if (sourceMode != QueueDisposable.ASYNC) {
            // 1. 将事件放入队列
            queue.offer(t);
        }
        
        // 2. 调度队列处理
        schedule();
    }
    
    void schedule() {
        if (getAndIncrement() == 0) {
            // 3. 使用Worker调度处理任务
            worker.schedule(this);
        }
    }
    
    @Override
    public void run() {
        // 4. 在目标线程上处理队列事件
        if (outputFused) {
            drainFused();
        } else {
            drainNormal();
        }
    }
}
```

#### 3.2.2 事件传递流程
```
上游Observable.onNext(data)
    ↓
ObserveOnObserver.onNext()  // 接收数据
    ↓
queue.offer(data)           // 放入队列
    ↓
worker.schedule(this)       // 调度处理任务
    ↓
在目标线程执行run()方法
    ↓
queue.poll()                // 从队列取出数据
    ↓
下游Observer.onNext(data)   // 发送给下游
```

## 4. 调度器实现机制

### 4.1 IoScheduler原理
```java
public final class IoScheduler extends Scheduler {
    // 使用线程池缓存
    final AtomicReference<CachedWorkerPool> pool;
    
    @Override
    public Worker createWorker() {
        return new EventLoopWorker(pool.get());
    }
    
    static final class EventLoopWorker extends Scheduler.Worker {
        private final ThreadWorker threadWorker;
        
        @Override
        public Disposable schedule(Runnable action, long delayTime, TimeUnit unit) {
            // 使用线程池执行任务
            return threadWorker.scheduleActual(
                action, delayTime, unit, null
            );
        }
    }
    
    // 线程缓存池
    static final class CachedWorkerPool {
        private final ConcurrentLinkedQueue<ThreadWorker> expiringWorkerQueue;
        private final CompositeDisposable allWorkers;
        
        ThreadWorker get() {
            // 尝试从缓存获取空闲Worker
            while (!expiringWorkerQueue.isEmpty()) {
                ThreadWorker threadWorker = expiringWorkerQueue.poll();
                if (threadWorker != null) {
                    return threadWorker;
                }
            }
            
            // 创建新的Worker
            ThreadWorker w = new ThreadWorker();
            allWorkers.add(w);
            return w;
        }
    }
}
```

### 4.2 ComputationScheduler原理
```java
public final class ComputationScheduler extends Scheduler {
    // 固定大小的线程池
    final AtomicReference<FixedSchedulerPool> pool;
    
    static final class FixedSchedulerPool {
        final int cores;
        final PoolWorker[] eventLoops;
        
        FixedSchedulerPool(int maxThreads) {
            this.cores = maxThreads;
            this.eventLoops = new PoolWorker[maxThreads];
            
            for (int i = 0; i < maxThreads; i++) {
                this.eventLoops[i] = new PoolWorker(
                    new RxThreadFactory("RxComputationThreadPool")
                );
            }
        }
        
        // 轮询分配线程
        public PoolWorker getEventLoop() {
            int c = cores;
            if (c == 0) return null;
            
            // 使用简单轮询策略
            int index = n.getAndIncrement() % c;
            return eventLoops[index];
        }
    }
    
    static final class PoolWorker extends NewThreadWorker {
        // 继承自NewThreadWorker，提供任务调度能力
    }
}
```

## 5. 关键组件分析

### 5.1 线程调度核心类

#### 5.1.1 ScheduledRunnable
```java
final class ScheduledRunnable 
    extends AtomicReferenceArray<Object>
    implements Runnable, Disposable, Callable<Void> {
    
    static final int PARENT_INDEX = 0;
    static final int FUTURE_INDEX = 1;
    static final int THREAD_INDEX = 2;
    
    @Override
    public void run() {
        // 1. 设置当前执行线程
        lazySet(THREAD_INDEX, Thread.currentThread());
        
        try {
            // 2. 执行实际任务
            runnable.run();
        } finally {
            // 3. 清理线程引用
            lazySet(THREAD_INDEX, null);
        }
    }
}
```

#### 5.1.2 NewThreadWorker
```java
public class NewThreadWorker extends Scheduler.Worker {
    private final ScheduledExecutorService executor;
    
    public ScheduledRunnable scheduleActual(
        final Runnable run, 
        long delayTime,
        TimeUnit unit
    ) {
        Runnable decoratedRun = RxJavaPlugins.onSchedule(run);
        
        // 创建可调度的任务
        ScheduledRunnable sr = new ScheduledRunnable(decoratedRun, parent);
        
        if (delayTime <= 0) {
            // 立即执行
            future = executor.submit((Callable<?>)sr);
        } else {
            // 延迟执行
            future = executor.schedule(
                (Callable<?>)sr, 
                delayTime, 
                unit
            );
        }
        
        sr.setFuture(future);
        return sr;
    }
}
```

## 6. 线程切换性能优化

### 6.1 队列机制
```java
// ObserveOn中的队列实现
static final class ObserveOnObserver<T> {
    // 使用SpscArrayQueue提高性能
    SimpleQueue<T> queue;
    
    // 批处理减少线程切换开销
    void drainNormal() {
        int missed = 1;
        final SimpleQueue<T> q = queue;
        final Observer<? super T> a = downstream;
        
        for (;;) {
            // 批量处理队列中的多个元素
            for (;;) {
                T v = q.poll();
                if (v == null) break;
                
                a.onNext(v);
            }
            
            missed = addAndGet(-missed);
            if (missed == 0) break;
        }
    }
}
```

### 6.2 背压处理
```java
// 支持背压的ObserveOn
static final class ObserveOnObserver<T> extends BasicIntQueueDisposable<T> {
    
    @Override
    public void onNext(T t) {
        if (done) return;
        
        // 检查队列容量
        if (sourceMode != QueueDisposable.ASYNC) {
            if (!queue.offer(t)) {
                // 队列满，触发背压
                upstream.dispose();
                onError(new MissingBackpressureException());
                return;
            }
        }
        
        schedule();
    }
}
```

## 7. 典型使用场景分析

### 7.1 Android中的线程切换
```java
Observable.create((ObservableOnSubscribe<String>) emitter -> {
    // 在IO线程执行耗时操作
    String data = loadFromDatabase();
    emitter.onNext(data);
    emitter.onComplete();
})
.subscribeOn(Schedulers.io())        // 指定上游执行线程
.observeOn(AndroidSchedulers.mainThread())  // 指定下游执行线程
.subscribe(data -> {
    // 在主线程更新UI
    updateUI(data);
}, throwable -> {
    // 错误处理也在主线程
    showError(throwable);
});
```

### 7.2 多层线程切换
```java
apiService.getUserData()
    .subscribeOn(Schedulers.io())          // 网络请求在IO线程
    .map(user -> processUserData(user))    // 仍在IO线程
    .observeOn(Schedulers.computation())   // 切换到计算线程
    .map(data -> heavyComputation(data))   // 在计算线程执行
    .observeOn(AndroidSchedulers.mainThread()) // 切换到主线程
    .subscribe(result -> {
        // 在主线程显示结果
        showResult(result);
    });
```

## 8. 常见问题与优化建议

### 8.1 内存泄漏预防
```java
// 正确的Disposable管理
CompositeDisposable compositeDisposable = new CompositeDisposable();

Disposable disposable = observable
    .subscribeOn(Schedulers.io())
    .observeOn(AndroidSchedulers.mainThread())
    .subscribe(...);

compositeDisposable.add(disposable);

// 在适当时机清理
@Override
protected void onDestroy() {
    compositeDisposable.clear();
    super.onDestroy();
}
```

### 8.2 调度器选择建议
| 场景 | 推荐调度器 | 说明 |
|------|-----------|------|
| 网络请求 | Schedulers.io() | 适合I/O等待操作 |
| 数据计算 | Schedulers.computation() | CPU密集型计算 |
| 频繁小任务 | Schedulers.single() | 避免线程创建开销 |
| 即时响应 | Schedulers.trampoline() | 当前线程顺序执行 |

### 8.3 性能优化技巧
1. **减少不必要的线程切换**
2. **合理设置缓冲区大小**
3. **使用CompositeDisposable统一管理**
4. **避免在主线程执行耗时操作**

## 9. 总结

RxJava调度器的线程切换原理基于以下几个核心机制：

1. **订阅时切换(subscribeOn)**: 通过将订阅操作包装成Runnable，在目标调度器上执行

2. **观察时切换(observeOn)**: 使用队列缓存事件，通过Worker在目标线程消费

3. **调度器实现**: 基于ExecutorService和线程池，提供不同类型的线程管理策略

4. **性能优化**: 通过批处理、背压控制、队列优化等技术提升效率

理解这些原理有助于开发者：
- 编写更高效的异步代码
- 避免常见的线程相关问题
- 根据场景选择合适的调度策略
- 更好地调试和优化RxJava应用