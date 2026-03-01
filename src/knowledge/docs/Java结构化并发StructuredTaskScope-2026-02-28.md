# Java结构化并发(StructuredTaskScope)技术文档

## 1. 概述

### 1.1 什么是结构化并发
结构化并发（Structured Concurrency）是一种并发编程范式，它通过明确的父子任务关系来管理并发任务的生命周期。在Java中，`StructuredTaskScope`是JDK 19引入的预览API（JEP 428），并在JDK 21中成为正式功能，旨在解决传统并发编程中任务泄漏和生命周期管理困难的问题。

### 1.2 设计目标
- **生命周期管理**：确保子任务在父任务作用域内完成
- **错误传播**：自动处理任务失败和异常传播
- **可观测性**：提供更好的线程转储和调试信息
- **资源安全**：防止任务泄漏和资源未释放

## 2. 核心概念

### 2.1 任务作用域（Task Scope）
```java
// 基本结构
try (var scope = new StructuredTaskScope<Result>()) {
    // 创建子任务
    Future<Result> future1 = scope.fork(() -> task1());
    Future<Result> future2 = scope.fork(() -> task2());
    
    // 等待所有任务完成
    scope.join();
    
    // 处理结果
    Result result1 = future1.resultNow();
    Result result2 = future2.resultNow();
}
// 作用域关闭时自动确保所有子任务完成
```

### 2.2 关键特性
- **作用域嵌套**：子作用域在父作用域内创建
- **自动清理**：try-with-resources确保资源释放
- **短路执行**：支持快速失败和提前完成

## 3. API详解

### 3.1 主要类

#### 3.1.1 `StructuredTaskScope<T>`
```java
public class StructuredTaskScope<T> implements AutoCloseable {
    // 创建子任务
    public <U extends T> Future<U> fork(Callable<? extends U> task);
    
    // 等待所有任务完成
    public StructuredTaskScope<T> join() throws InterruptedException;
    public StructuredTaskScope<T> joinUntil(Instant deadline);
    
    // 关闭作用域
    public void close();
    
    // 状态检查
    public enum State { OPEN, CLOSED }
    public State state();
}
```

#### 3.1.2 `ShutdownOnSuccess<T>`（JDK 21+）
```java
// 首个成功结果即关闭作用域
try (var scope = new StructuredTaskScope.ShutdownOnSuccess<String>()) {
    scope.fork(() -> fetchFromSourceA());
    scope.fork(() -> fetchFromSourceB());
    
    scope.join();
    String result = scope.result(); // 获取首个成功结果
}
```

#### 3.1.3 `ShutdownOnFailure`（JDK 21+）
```java
// 任一任务失败即关闭作用域
try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
    Future<String> future1 = scope.fork(() -> processItem1());
    Future<String> future2 = scope.fork(() -> processItem2());
    
    scope.join();
    scope.throwIfFailed(); // 如果有失败则抛出异常
    
    // 所有任务成功完成
    String result1 = future1.resultNow();
    String result2 = future2.resultNow();
}
```

### 3.2 使用模式

#### 模式1：并发执行与结果收集
```java
public class ConcurrentProcessor {
    public List<Result> processConcurrently(List<Task> tasks) 
            throws InterruptedException, ExecutionException {
        
        try (var scope = new StructuredTaskScope<Result>()) {
            List<Future<Result>> futures = new ArrayList<>();
            
            // 创建所有子任务
            for (Task task : tasks) {
                futures.add(scope.fork(() -> executeTask(task)));
            }
            
            // 等待所有任务完成
            scope.join();
            
            // 收集结果
            List<Result> results = new ArrayList<>();
            for (Future<Result> future : futures) {
                switch (future.state()) {
                    case SUCCESS -> results.add(future.resultNow());
                    case FAILED -> throw new ExecutionException(future.exceptionNow());
                    case CANCELLED -> // 处理取消情况
                }
            }
            return results;
        }
    }
}
```

#### 模式2：竞速模式
```java
public class FastestSourceFinder {
    public String findFastest(List<DataSource> sources) 
            throws InterruptedException {
        
        try (var scope = new StructuredTaskScope.ShutdownOnSuccess<String>()) {
            // 并发查询所有数据源
            for (DataSource source : sources) {
                scope.fork(() -> source.fetchData());
            }
            
            scope.join();
            return scope.result(); // 返回最快的结果
        } catch (ExecutionException e) {
            throw new RuntimeException("所有数据源查询失败", e);
        }
    }
}
```

#### 模式3：容错处理
```java
public class ResilientProcessor {
    public Result processWithFallback() throws InterruptedException {
        try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
            Future<Result> primary = scope.fork(() -> primaryOperation());
            Future<Result> fallback = scope.fork(() -> fallbackOperation());
            
            scope.join();
            
            if (primary.state() == Future.State.SUCCESS) {
                return primary.resultNow();
            } else {
                return fallback.resultNow();
            }
        }
    }
}
```

## 4. 最佳实践

### 4.1 错误处理策略
```java
try (var scope = new StructuredTaskScope<Result>()) {
    // 创建任务
    Future<Result> future = scope.fork(() -> riskyOperation());
    
    scope.join();
    
    // 统一错误处理
    try {
        Result result = future.get(); // 阻塞获取结果
        return result;
    } catch (ExecutionException e) {
        Throwable cause = e.getCause();
        if (cause instanceof TimeoutException) {
            // 处理超时
        } else if (cause instanceof IOException) {
            // 处理IO异常
        }
        throw new ProcessingException("处理失败", cause);
    }
}
```

### 4.2 资源管理
```java
public class ResourceAwareProcessor {
    public void processWithResources() {
        // 外层资源作用域
        try (var resourceScope = new ResourceScope()) {
            Resource resource = resourceScope.acquire();
            
            // 内层并发作用域
            try (var taskScope = new StructuredTaskScope<Void>()) {
                taskScope.fork(() -> useResource(resource, "Task1"));
                taskScope.fork(() -> useResource(resource, "Task2"));
                
                taskScope.join();
            }
            // 所有任务完成后自动清理
        }
    }
}
```

### 4.3 超时控制
```java
public class TimeoutProcessor {
    public Result processWithTimeout(Duration timeout) 
            throws InterruptedException, TimeoutException {
        
        try (var scope = new StructuredTaskScope<Result>()) {
            Future<Result> future = scope.fork(() -> longRunningOperation());
            
            // 带超时的等待
            Instant deadline = Instant.now().plus(timeout);
            scope.joinUntil(deadline);
            
            if (future.isDone()) {
                return future.resultNow();
            } else {
                scope.shutdown(); // 中断所有任务
                throw new TimeoutException("操作超时");
            }
        }
    }
}
```

## 5. 与传统并发对比

### 5.1 ExecutorService方式
```java
// 传统方式 - 需要手动管理
ExecutorService executor = Executors.newCachedThreadPool();
List<Future<Result>> futures = new ArrayList<>();

try {
    for (Task task : tasks) {
        futures.add(executor.submit(() -> process(task)));
    }
    
    for (Future<Result> future : futures) {
        try {
            Result result = future.get();
            // 处理结果
        } catch (ExecutionException e) {
            // 错误处理复杂
        }
    }
} finally {
    executor.shutdown(); // 容易忘记调用
    executor.awaitTermination(1, TimeUnit.MINUTES);
}
```

### 5.2 StructuredTaskScope优势
1. **自动生命周期管理**：作用域结束时确保所有任务完成
2. **结构化错误传播**：异常自动传播到父作用域
3. **更好的可观测性**：线程转储显示任务层次结构
4. **防止任务泄漏**：编译器确保作用域正确关闭

## 6. 性能考量

### 6.1 线程管理
- `StructuredTaskScope`默认使用`ForkJoinPool`的虚拟线程（Project Loom）
- 适合I/O密集型任务
- 对于CPU密集型任务，考虑使用固定线程池

### 6.2 内存使用
```java
// 控制并发度防止内存溢出
public class BoundedConcurrency {
    private static final int MAX_CONCURRENCY = 100;
    
    public void processBatched(List<Item> items) 
            throws InterruptedException {
        
        try (var scope = new StructuredTaskScope<Void>()) {
            Semaphore semaphore = new Semaphore(MAX_CONCURRENCY);
            List<Future<Void>> futures = new ArrayList<>();
            
            for (Item item : items) {
                semaphore.acquire();
                futures.add(scope.fork(() -> {
                    try {
                        return processItem(item);
                    } finally {
                        semaphore.release();
                    }
                }));
            }
            
            scope.join();
        }
    }
}
```

## 7. 调试与监控

### 7.1 线程转储分析
```
"main" #1
  java.lang.Thread.State: RUNNABLE
  at com.example.Main.main(Main.java:10)
  - scope: StructuredTaskScope@1a2b3c4d
    "forked-1" #1001 (virtual)
      java.lang.Thread.State: RUNNABLE
      at com.example.Main.lambda$main$0(Main.java:12)
    "forked-2" #1002 (virtual)
      java.lang.Thread.State: RUNNABLE  
      at com.example.Main.lambda$main$1(Main.java:13)
```

### 7.2 自定义钩子
```java
public class MonitoringScope<T> extends StructuredTaskScope<T> {
    private final MetricsCollector metrics;
    
    @Override
    protected void handleComplete(Future<T> future) {
        super.handleComplete(future);
        metrics.recordCompletion(future.state());
    }
    
    @Override
    protected void afterJoin() {
        super.afterJoin();
        metrics.recordScopeCompletion();
    }
}
```

## 8. 限制与注意事项

### 8.1 当前限制
1. **预览功能**：在JDK 19-20中为预览功能
2. **虚拟线程要求**：最佳效果需要虚拟线程支持
3. **框架集成**：部分框架可能需要适配

### 8.2 迁移建议
1. 逐步替换`ExecutorService`调用
2. 保持向后兼容性
3. 添加适当的异常处理
4. 监控资源使用情况

## 9. 示例：完整应用场景

```java
public class WebPageCrawler {
    public PageData fetchPageWithResources(String url, Duration timeout) 
            throws InterruptedException, PageFetchException {
        
        try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
            // 并发获取页面和资源
            Future<String> htmlFuture = scope.fork(() -> fetchHtml(url));
            Future<List<Image>> imagesFuture = scope.fork(() -> discoverImages(url));
            Future<Metadata> metadataFuture = scope.fork(() -> fetchMetadata(url));
            
            // 带超时等待
            scope.joinUntil(Instant.now().plus(timeout));
            
            // 检查失败
            scope.throwIfFailed(PageFetchException::new);
            
            // 组装结果
            return new PageData(
                htmlFuture.resultNow(),
                imagesFuture.resultNow(),
                metadataFuture.resultNow()
            );
        }
    }
    
    private static class PageFetchException extends Exception {
        public PageFetchException(Throwable cause) {
            super("页面获取失败", cause);
        }
    }
}
```

## 10. 总结

`StructuredTaskScope`代表了Java并发编程的重大进步，它通过结构化方法解决了传统并发编程中的常见问题：
- ✅ 明确的任务生命周期管理
- ✅ 自动的错误传播机制  
- ✅ 防止任务和资源泄漏
- ✅ 改进的可调试性和可观测性

对于新项目，建议直接采用结构化并发模式。对于现有项目，可以逐步迁移关键路径，特别是在处理复杂并发逻辑和需要可靠错误处理的场景中。

---

*文档版本：1.0*
*对应JDK版本：21+*
*最后更新：2024年*