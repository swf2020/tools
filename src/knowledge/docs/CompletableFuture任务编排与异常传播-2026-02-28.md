好的，遵照您的指示，我将为您生成一份关于 **CompletableFuture任务编排与异常传播** 的技术文档。

---

# CompletableFuture任务编排与异常传播技术文档

## 1. 概述

`CompletableFuture` 是 Java 8 引入的 `Future` 接口的增强实现，是 `java.util.concurrent` 包的一部分。它不仅代表了异步计算的结果，更重要的是提供了强大的函数式编程能力，用于构建复杂的**异步任务流水线**和**工作流**，实现任务之间的**编排**。

其核心价值在于：
*   **非阻塞式组合**： 可以通过链式调用组合多个异步任务，无需手工进行线程阻塞和等待。
*   **函数式回调**： 支持 `thenApply`, `thenAccept`, `thenRun`, `thenCompose` 等方法，在任务完成后触发相应操作。
*   **多任务聚合**： 支持 `allOf`, `anyOf`, `thenCombine` 等方法，协调多个并发任务的结果。
*   **显式异常处理**： 提供了标准化的方式来处理异步计算链中的异常，实现异常的传播和控制。

## 2. 核心任务编排模式

### 2.1 串行编排
当一个任务依赖于前一个任务的结果时，使用串行编排。

*   `thenApply(Function<T, U>)`： 接收上一个任务的结果 `T`，返回新的结果 `U`（转换）。
*   `thenAccept(Consumer<T>)`： 消费结果，无返回值。
*   `thenRun(Runnable)`： 不关心结果，只在前置任务完成后执行一个动作。
*   `thenCompose(Function<T, CompletionStage<U>>)`： 用于“展平”嵌套的 `CompletableFuture`，是异步的 `flatMap`。

```java
CompletableFuture<String> future = CompletableFuture.supplyAsync(() -> "Hello")
        .thenApply(s -> s + " World") // 转换: "Hello" -> "Hello World"
        .thenApply(String::toUpperCase) // 转换: "Hello World" -> "HELLO WORLD"
        .thenApply(s -> s + "!"); // 转换: "HELLO WORLD" -> "HELLO WORLD!"
```

### 2.2 聚合编排（AND关系）
当需要等待多个**独立**的任务全部完成，并聚合它们的结果时使用。

*   `thenCombine(CompletionStage<U>, BiFunction<T, U, V>)`： 合并两个独立任务的结果。
*   `thenAcceptBoth(CompletionStage<U>, BiConsumer<T, U>)`： 消费两个独立任务的结果。
*   `allOf(CompletableFuture<?>...)`： 等待所有给定的 Future 完成。返回的 `CompletableFuture<Void>` 本身不携带结果，需要手动收集。

```java
CompletableFuture<Integer> future1 = CompletableFuture.supplyAsync(() -> 10);
CompletableFuture<Integer> future2 = CompletableFuture.supplyAsync(() -> 20);

CompletableFuture<Integer> combinedFuture = future1.thenCombine(future2, (a, b) -> a + b);
// combinedFuture 的结果为 30
```

### 2.3 竞争编排（OR关系）
当只需要多个任务中**任意一个**完成时使用。

*   `anyOf(CompletableFuture<?>...)`： 返回一个新的 `CompletableFuture<Object>`，它会在任意一个输入的 Future 完成时完成，并以该 Future 的结果作为结果。

```java
CompletableFuture<String> future1 = CompletableFuture.supplyAsync(() -> {
    try { Thread.sleep(100); } catch (InterruptedException e) {}
    return "Result from Future 1";
});
CompletableFuture<String> future2 = CompletableFuture.supplyAsync(() -> "Result from Future 2");

CompletableFuture<Object> firstCompleted = CompletableFuture.anyOf(future1, future2);
// firstCompleted 的结果很可能是 "Result from Future 2"
```

## 3. 异常传播与处理机制

`CompletableFuture` 的异常处理是其编排能力的核心部分。当一个阶段的计算抛出异常时，该阶段的 `CompletableFuture` 会以 **`CompletionException`**（或其子类）异常完成。此异常会沿着任务链向下游传播，直到遇到一个**显式的异常处理方法**。

### 3.1 关键异常处理方法

1.  **`exceptionally(Function<Throwable, T>)`**
    *   **作用**： 类似于 `catch` 块。仅当上游阶段**异常完成**时被调用。
    *   **参数**： 接收异常 `Throwable`，并返回一个**替代值** `T` 用于恢复链的正常执行。
    *   **下游感知**： 下游阶段将接收到 `exceptionally` 返回的替代值，**感知不到异常**。

2.  **`handle(BiFunction<T, Throwable, U>)`**
    *   **作用**： 无论上游阶段是**正常完成**还是**异常完成**，都会被调用。
    *   **参数**： 接收两个参数：结果 `T`（正常时为值，异常时为 `null`）和异常 `Throwable`（正常时为 `null`，异常时为异常对象）。必须返回一个新的结果 `U`。
    *   **下游感知**： 下游阶段将接收到 `handle` 返回的新结果。

3.  **`whenComplete(BiConsumer<T, Throwable>)`**
    *   **作用**： 类似于 `finally` 块。无论成功失败都会被调用，用于执行副作用（如日志记录、资源清理）。
    *   **参数**： 接收结果和异常，但**不返回新值**。
    *   **下游感知**： **不改变完成状态**。如果上游异常，`whenComplete` 执行后，下游收到的仍然是同一个异常，异常会继续传播。

### 3.2 异常传播示例

```java
CompletableFuture.supplyAsync(() -> {
            if (true) {
                throw new RuntimeException("Calculation failed!");
            }
            return 100;
        })
        .thenApply(i -> i * 2) // 这一步不会执行，因为上游已异常
        .exceptionally(ex -> {
            System.err.println("Caught exception: " + ex.getMessage());
            return -1; // 提供恢复值
        })
        .thenApply(i -> {
            System.out.println("Recovered value: " + i); // 输出: Recovered value: -1
            return i + 10;
        })
        .thenAccept(System.out::println); // 输出: 9
```

**解释**：
1.  初始任务抛出 `RuntimeException`。
2.  `.thenApply(i -> i * 2)` 被跳过。
3.  `.exceptionally` 捕获异常，打印日志，并返回恢复值 `-1`。
4.  任务链从异常中恢复，后续的 `.thenApply` 和 `.thenAccept` 接收到的是 `-1`，并正常执行。

### 3.3 对比 `handle` 与 `whenComplete`

```java
// 使用 handle
CompletableFuture.supplyAsync(() -> "Success")
        .handle((result, ex) -> {
            if (ex != null) {
                return "Recovered from error";
            }
            return result.toUpperCase();
        })
        .thenAccept(System.out::println); // 输出: SUCCESS

// 使用 whenComplete (上游异常的情况)
CompletableFuture.supplyAsync(() -> {
            throw new RuntimeException("Oops");
        })
        .whenComplete((result, ex) -> {
            if (ex != null) {
                System.out.println("Logging error in whenComplete: " + ex.getMessage());
            }
            // 无法改变 result，异常继续传播
        })
        .exceptionally(ex -> {
            System.out.println("Exception caught in exceptionally after whenComplete.");
            return "Default";
        });
// 输出:
// Logging error in whenComplete: Oops
// Exception caught in exceptionally after whenComplete.
```

## 4. 最佳实践与注意事项

1.  **明确指定线程池**： 避免在所有步骤中都使用默认的 `ForkJoinPool.commonPool()`。对于I/O密集型或希望隔离的任务，应传入自定义的 `Executor`。
    ```java
    ExecutorService customPool = Executors.newFixedThreadPool(10);
    CompletableFuture.supplyAsync(() -> queryDatabase(), customPool);
    ```

2.  **异常处理前置**： 尽量在链的早期处理或记录异常，避免异常在链中无提示地传播导致难以调试。

3.  **避免阻塞主线程**： 使用 `join()`（在非ForkJoinPool管理的线程中慎用，会抛未检查异常）或 `get()`（抛受检异常）来获取最终结果，但应将其限制在异步流程的边界。

4.  **小心回调地狱**： 虽然链式调用优雅，但过长的链可能降低可读性。可考虑将逻辑拆分为多个方法，或使用 `thenCompose` 进行模块化。

5.  **理解“异步”边界**： `thenApply` 等方法是**同步**执行的（在前一个任务的同一线程或完成线程中），除非使用它们的 `Async` 变体（如 `thenApplyAsync`），后者会将函数提交到线程池。

6.  **资源管理**： 对于持有资源的任务，确保在 `whenComplete` 或单独的阶段中正确关闭资源。

## 5. 总结

`CompletableFuture` 通过其丰富的API，将异步编程从简单的“提交-获取”模式提升到了声明式的**工作流编排**层面。其核心在于：
*   **任务编排**： 通过 `then*`、`combine`、`allOf`/`anyOf` 等方法灵活组合任务。
*   **异常传播**： 异常作为一等公民在链中传播，通过 `exceptionally`、`handle`、`whenComplete` 等方法可以精确地控制恢复、转换或记录行为，构建出健壮的异步应用程序。

熟练掌握其任务编排与异常处理机制，是编写高效、可靠并发Java程序的关键。