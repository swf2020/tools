# Kotlin Flow：冷流与热流（SharedFlow/StateFlow）技术文档

## 1. 概述

### 1.1 Flow 简介
Kotlin Flow 是 Kotlin 协程库中的响应式流处理 API，提供了一种声明式、可组合的异步数据流处理方式。Flow 基于协程构建，天然支持结构化并发和取消操作。

### 1.2 冷流与热流的概念差异
- **冷流（Cold Flow）**：数据生产者与消费者一一对应，每个收集器启动独立的流执行
- **热流（Hot Flow）**：数据生产者独立运行，多个收集器共享同一数据源

## 2. 冷流（Cold Flow）

### 2.1 基本特性
```kotlin
// 冷流示例：每个收集器启动独立的流执行
fun getColdFlow(): Flow<Int> = flow {
    repeat(3) {
        delay(1000)
        emit(it)
        println("Emitted: $it in ${Thread.currentThread().name}")
    }
}

// 测试代码
suspend fun testColdFlow() {
    val coldFlow = getColdFlow()
    
    // 第一个收集器
    launch {
        coldFlow.collect { value ->
            println("Collector 1: $value")
        }
    }
    
    delay(1500) // 等待一段时间
    
    // 第二个收集器 - 会从头开始执行流
    launch {
        coldFlow.collect { value ->
            println("Collector 2: $value")
        }
    }
}
```

### 2.2 冷流的特点
- **延迟执行**：只有在收集器开始收集时才执行流构建器中的代码
- **独立副本**：每个收集器获取独立的数据流副本
- **自动取消**：当收集器取消时，对应的流执行也会取消
- **常见冷流创建方式**：
  - `flow { ... }` 构建器
  - `asFlow()` 扩展函数
  - `flowOf()` 函数

## 3. 热流（Hot Flow）

### 3.1 SharedFlow

#### 3.1.1 基本概念
SharedFlow 是一种可以多播（广播）数据到多个收集器的热流，数据发射与收集操作相互独立。

```kotlin
// SharedFlow 创建与使用
fun createSharedFlow(): SharedFlow<Int> {
    // 创建 MutableSharedFlow（可变的SharedFlow）
    val mutableSharedFlow = MutableSharedFlow<Int>(
        replay = 2,           // 新订阅者接收的历史数据数量
        extraBufferCapacity = 5 // 缓冲区容量
    )
    
    // 启动协程发射数据
    CoroutineScope(Dispatchers.Default).launch {
        repeat(10) {
            delay(500)
            mutableSharedFlow.emit(it)
            println("SharedFlow emitted: $it")
        }
    }
    
    return mutableSharedFlow.asSharedFlow()
}

// 测试多个收集器
suspend fun testSharedFlow() {
    val sharedFlow = createSharedFlow()
    
    delay(1000) // 等待流开始发射数据
    
    // 收集器1
    launch {
        sharedFlow.collect { value ->
            println("Collector 1 received: $value at ${System.currentTimeMillis()}")
        }
    }
    
    delay(1000)
    
    // 收集器2 - 可以接收到replay指定的历史数据
    launch {
        sharedFlow.collect { value ->
            println("Collector 2 received: $value at ${System.currentTimeMillis()}")
        }
    }
}
```

#### 3.1.2 配置参数详解
```kotlin
// MutableSharedFlow 完整配置
val customSharedFlow = MutableSharedFlow<String>(
    replay = 3,                     // 新订阅者接收的最后3个值
    extraBufferCapacity = 10,       // 除replay外的缓冲区容量
    onBufferOverflow = BufferOverflow.SUSPEND // 缓冲区满时的策略
)

// 缓冲区溢出策略
enum class BufferOverflow {
    SUSPEND,    // 默认：挂起发射器直到有空间
    DROP_OLDEST, // 丢弃最旧的数据
    DROP_LATEST  // 丢弃最新的数据
}
```

#### 3.1.3 高级操作
```kotlin
// SharedFlow 操作符示例
suspend fun advancedSharedFlowOperations() {
    val sharedFlow = MutableSharedFlow<Int>()
    
    // 1. 发射数据（可挂起）
    launch {
        sharedFlow.emit(1)
        // 或使用 tryEmit（非挂起版本）
        sharedFlow.tryEmit(2)
    }
    
    // 2. 订阅计数
    val subscriptionCount = sharedFlow.subscriptionCount
    
    // 3. 转换为 StateFlow
    val stateFlow = sharedFlow.distinctUntilChanged()
        .stateIn(
            scope = CoroutineScope(Dispatchers.Default),
            started = SharingStarted.WhileSubscribed(),
            initialValue = 0
        )
}
```

### 3.2 StateFlow

#### 3.2.1 基本概念
StateFlow 是 SharedFlow 的特殊变体，专门用于表示状态，具有以下特点：
- 总是有当前值（初始值必须提供）
- 只保留最新的值（replay=1）
- 使用 `distinctUntilChanged()` 进行值去重

```kotlin
// StateFlow 示例
class ViewModel {
    private val _uiState = MutableStateFlow<UiState>(UiState.Loading)
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()
    
    suspend fun loadData() {
        _uiState.value = UiState.Loading
        try {
            val data = fetchData()
            _uiState.value = UiState.Success(data)
        } catch (e: Exception) {
            _uiState.value = UiState.Error(e.message)
        }
    }
    
    // 收集状态更新
    fun observeUiState() {
        viewModelScope.launch {
            uiState.collect { state ->
                when (state) {
                    is UiState.Loading -> showLoading()
                    is UiState.Success -> showData(state.data)
                    is UiState.Error -> showError(state.message)
                }
            }
        }
    }
}
```

#### 3.2.2 StateFlow 与 LiveData 对比
```kotlin
// StateFlow 优势
class StateFlowAdvantages {
    // 1. 结构化并发支持
    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    
    // 2. 丰富的操作符
    val processedState = uiState
        .map { it.data }
        .filter { it.isNotEmpty() }
        .distinctUntilChanged()
        .stateIn(
            scope = scope,
            started = SharingStarted.WhileSubscribed(5000),
            initialValue = emptyList()
        )
    
    // 3. 更好的测试支持
    fun testStateFlow() = runTest {
        val testFlow = MutableStateFlow(0)
        assertEquals(0, testFlow.value)
        
        testFlow.value = 1
        assertEquals(1, testFlow.value)
    }
}
```

## 4. 冷流与热流的比较

### 4.1 特性对比表

| 特性 | 冷流（Cold Flow） | SharedFlow | StateFlow |
|------|------------------|------------|-----------|
| **数据发射时机** | 按需发射 | 独立发射 | 独立发射 |
| **订阅者关系** | 一对一 | 一对多 | 一对多 |
| **历史数据** | 无 | 可配置replay | 最后1个值 |
| **初始值** | 不需要 | 不需要 | 必须提供 |
| **去重机制** | 无 | 无 | 自动去重 |
| **典型应用** | 网络请求、数据库查询 | 事件总线、实时消息 | UI状态管理 |

### 4.2 性能考虑
```kotlin
// 性能对比示例
class FlowPerformance {
    
    // 冷流：适用于一次性操作
    fun fetchUserData(): Flow<User> = flow {
        // 数据库查询或网络请求
        val user = apiService.getUser()
        emit(user)
    }
    
    // SharedFlow：适用于事件分发
    private val _events = MutableSharedFlow<Event>(
        replay = 0,
        extraBufferCapacity = 10
    )
    val events = _events.asSharedFlow()
    
    // StateFlow：适用于状态管理
    private val _state = MutableStateFlow(AppState.IDLE)
    val state = _state.asStateFlow()
    
    // 选择建议：
    // 1. 需要多个收集器共享数据 -> 热流
    // 2. 需要记住最新状态 -> StateFlow
    // 3. 需要处理一次性异步操作 -> 冷流
    // 4. 需要事件广播 -> SharedFlow
}
```

## 5. 转换与互操作

### 5.1 冷流转热流
```kotlin
// 使用 shareIn 将冷流转换为热流
class FlowConverter {
    
    // 原始冷流
    private val dataStream: Flow<Data> = flow {
        // 模拟数据流
        while (true) {
            emit(fetchData())
            delay(1000)
        }
    }
    
    // 转换为热流
    val hotDataStream = dataStream
        .shareIn(
            scope = CoroutineScope(Dispatchers.IO),
            started = SharingStarted.WhileSubscribed(),
            replay = 1
        )
    
    // started 参数选项：
    // - Lazily: 第一个订阅者出现时开始
    // - Eagerly: 立即开始，与订阅者无关
    // - WhileSubscribed: 有活跃订阅者时开始
    //   (stopTimeoutMillis = 0, replayExpirationMillis = Long.MAX_VALUE)
}

// 使用 stateIn 转换为 StateFlow
val stateFlow = dataStream
    .stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5000),
        initialValue = null
    )
```

### 5.2 热流转冷流
```kotlin
// 热流转冷流的场景较少，但可通过 callbackFlow 实现
fun hotToColdConversion(sharedFlow: SharedFlow<Int>): Flow<String> = flow {
    // 为每个收集器创建独立的订阅
    sharedFlow
        .map { "Processed: $it" }
        .collect { value ->
            emit(value)
        }
}
```

## 6. 生命周期管理

### 6.1 收集器的生命周期
```kotlin
class LifecycleAwareFlowCollection {
    
    // 使用 LifecycleOwner 收集
    fun collectWithLifecycle(lifecycle: Lifecycle, flow: Flow<Int>) {
        flow
            .flowWithLifecycle(lifecycle, Lifecycle.State.STARTED)
            .onEach { value ->
                // 只在 STARTED 状态下处理数据
                updateUI(value)
            }
            .launchIn(viewModelScope)
    }
    
    // 手动控制收集
    private var collectionJob: Job? = null
    
    fun startCollection(flow: Flow<Int>) {
        stopCollection()
        collectionJob = viewModelScope.launch {
            flow.collect { value ->
                processValue(value)
            }
        }
    }
    
    fun stopCollection() {
        collectionJob?.cancel()
        collectionJob = null
    }
}
```

### 6.2 避免内存泄漏
```kotlin
class SafeFlowUsage {
    
    // 在 ViewModel 中使用
    class MyViewModel : ViewModel() {
        private val _data = MutableStateFlow<List<Item>>(emptyList())
        val data: StateFlow<List<Item>> = _data.asStateFlow()
        
        // 自动取消：viewModelScope 在 ViewModel 清除时取消
        fun loadData() {
            viewModelScope.launch {
                repository.getItems()
                    .catch { e -> 
                        // 异常处理
                    }
                    .collect { items ->
                        _data.value = items
                    }
            }
        }
    }
    
    // 在 Activity/Fragment 中使用
    class MyFragment : Fragment() {
        private var flowJob: Job? = null
        
        override fun onStart() {
            super.onStart()
            flowJob = lifecycleScope.launch {
                viewModel.data.collect { data ->
                    // 更新 UI
                }
            }
        }
        
        override fun onStop() {
            super.onStop()
            flowJob?.cancel()
        }
    }
}
```

## 7. 最佳实践与常见模式

### 7.1 事件处理模式
```kotlin
// 单一事件模式（防止事件重放）
class SingleEventViewModel {
    
    private val _events = MutableSharedFlow<Event>(
        replay = 0,  // 重要：不重放历史事件
        extraBufferCapacity = 10
    )
    val events: SharedFlow<Event> = _events.asSharedFlow()
    
    fun triggerEvent(event: Event) {
        viewModelScope.launch {
            _events.emit(event)
        }
    }
    
    // 在 UI 层收集
    fun observeEvents() {
        viewModelScope.launch {
            events.collect { event ->
                when (event) {
                    is Event.ShowMessage -> showToast(event.message)
                    is Event.Navigate -> navigateTo(event.destination)
                }
            }
        }
    }
}
```

### 7.2 状态管理最佳实践
```kotlin
// 使用 sealed class 表示状态
sealed class UiState {
    object Loading : UiState()
    data class Success(val data: List<String>) : UiState()
    data class Error(val message: String?) : UiState()
}

// 状态容器模式
class StateContainer {
    
    private val _state = MutableStateFlow<UiState>(UiState.Loading)
    val state: StateFlow<UiState> = _state.asStateFlow()
    
    // 状态更新方法
    fun updateState(update: (UiState) -> UiState) {
        _state.update(update)
    }
    
    // 状态转换
    suspend fun loadData() {
        _state.value = UiState.Loading
        try {
            val result = repository.fetchData()
            _state.value = UiState.Success(result)
        } catch (e: Exception) {
            _state.value = UiState.Error(e.message)
        }
    }
}
```

### 7.3 错误处理
```kotlin
// 完整的错误处理模式
class ErrorHandlingExample {
    
    val dataFlow: Flow<Result<Data>> = flow {
        emit(Result.loading())
        try {
            val data = apiService.getData()
            emit(Result.success(data))
        } catch (e: Exception) {
            emit(Result.error(e))
        }
    }
    
    // 使用 catch 操作符
    val safeFlow = flow {
        emit(apiService.getData())
    }.catch { e ->
        // 处理异常，可以发射替代值
        emit(Data.empty())
        // 或重新抛出
        if (e is NetworkException) throw e
    }
    
    // SharedFlow 异常处理
    private val _errorEvents = MutableSharedFlow<Throwable>()
    val errorEvents = _errorEvents.asSharedFlow()
    
    fun executeWithErrorHandling() {
        viewModelScope.launch {
            try {
                dataFlow.collect { result ->
                    result.onSuccess { data ->
                        // 处理成功数据
                    }.onFailure { error ->
                        // 发送错误事件
                        _errorEvents.emit(error)
                    }
                }
            } catch (e: CancellationException) {
                // 协程取消，正常退出
                throw e
            } catch (e: Exception) {
                // 未捕获的异常
                _errorEvents.emit(e)
            }
        }
    }
}
```

## 8. 测试策略

### 8.1 测试 StateFlow
```kotlin
class StateFlowTest {
    
    @Test
    fun testStateFlowUpdates() = runTest {
        val viewModel = MyViewModel()
        
        // 收集状态变化
        val values = mutableListOf<UiState>()
        backgroundScope.launch {
            viewModel.uiState.collect { values.add(it) }
        }
        
        // 触发状态更新
        viewModel.loadData()
        
        // 验证状态序列
        advanceUntilIdle()
        assertEquals(3, values.size) // Loading, Success, etc.
        assertTrue(values[0] is UiState.Loading)
    }
    
    @Test
    fun testStateFlowValue() = runTest {
        val flow = MutableStateFlow(0)
        
        // 直接测试值
        assertEquals(0, flow.value)
        
        flow.value = 1
        assertEquals(1, flow.value)
        
        // 测试更新函数
        flow.update { it + 1 }
        assertEquals(2, flow.value)
    }
}
```

### 8.2 测试 SharedFlow
```kotlin
class SharedFlowTest {
    
    @Test
    fun testSharedFlowEmission() = runTest {
        val sharedFlow = MutableSharedFlow<Int>()
        
        // 启动收集器
        val collected = mutableListOf<Int>()
        val job = launch {
            sharedFlow.collect { collected.add(it) }
        }
        
        // 发射数据
        sharedFlow.emit(1)
        sharedFlow.emit(2)
        
        // 验证收集的数据
        advanceUntilIdle()
        assertEquals(listOf(1, 2), collected)
        
        job.cancel()
    }
    
    @Test
    fun testSharedFlowReplay() = runTest {
        val sharedFlow = MutableSharedFlow<Int>(
            replay = 2
        )
        
        // 先发射数据
        sharedFlow.emit(1)
        sharedFlow.emit(2)
        sharedFlow.emit(3)
        
        // 后启动收集器
        val collected = mutableListOf<Int>()
        val job = launch {
            sharedFlow.collect { collected.add(it) }
        }
        
        // 验证收到重放数据
        advanceUntilIdle()
        assertEquals(listOf(2, 3), collected) // 收到最后两个值
        
        job.cancel()
    }
}
```

## 9. 总结与选择指南

### 9.1 何时使用冷流
- 执行一次性异步操作（网络请求、数据库查询）
- 需要独立数据流副本的场景
- 资源密集型操作，需要按需执行
- 示例：`retrofit` 接口调用、`Room` 数据库查询

### 9.2 何时使用 SharedFlow
- 事件广播（用户操作、系统事件）
- 多订阅者共享实时数据
- 需要控制历史数据重放
- 示例：事件总线、实时消息推送

### 9.3 何时使用 StateFlow
- UI 状态管理
- 需要始终有当前值
- 状态去重优化性能
- 示例：ViewModel 状态、设置管理

### 9.4 性能优化建议
1. **合理选择缓冲区大小**：避免过大导致内存浪费
2. **使用 distinctUntilChanged()**：减少不必要的更新
3. **适时取消收集**：避免内存泄漏
4. **考虑使用 flowOn**：指定适当的调度器
5. **避免在热流中进行耗时操作**：使用冷流处理耗时任务

## 附录：常用操作符速查表

| 操作符 | 冷流 | SharedFlow | StateFlow | 描述 |
|--------|------|------------|-----------|------|
| `map` | ✓ | ✓ | ✓ | 转换每个值 |
| `filter` | ✓ | ✓ | ✓ | 过滤值 |
| `catch` | ✓ | ✓ | ✓ | 异常处理 |
| `flowOn` | ✓ | ✓ | ✓ | 切换调度器 |
| `shareIn` | ✗ | 创建 | 创建 | 冷流转热流 |
| `stateIn` | ✗ | ✗ | 创建 | 转换为StateFlow |
| `distinctUntilChanged` | ✓ | ✓ | 内置 | 值去重 |
| `replay` | ✗ | 配置 | 固定1 | 重放历史数据 |
| `emit` | 在flow中 | ✓ | ✓ | 发射值 |
| `tryEmit` | ✗ | ✓ | ✓ | 非挂起发射 |

---

**文档版本**：1.0  
**最后更新**：2024年  
**适用版本**：Kotlin 1.8+，Coroutines 1.7+