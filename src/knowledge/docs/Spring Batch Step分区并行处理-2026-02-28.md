# Spring Batch Step分区并行处理技术文档

## 1. 概述

### 1.1 什么是分区并行处理
Spring Batch分区并行处理是一种将单个Step分解为多个独立子Step并行执行的技术。它允许将大规模数据处理任务分割为可管理的块（partitions），在多线程、多进程或多节点环境中同时处理，显著提高批处理作业的执行效率。

### 1.2 适用场景
- 大数据量处理（百万级以上记录）
- I/O密集型操作（文件处理、数据库读写）
- 可独立处理的记录集合
- 需要横向扩展的批处理任务

## 2. 核心架构

### 2.1 分区处理组件
```
┌─────────────────────────────────────────────────────┐
│                    Master Step                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │ Partitioner │  │   Handler   │  │  Aggregator │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────┘
         │                     │               │
         ▼                     ▼               ▼
┌─────────────────────────────────────────────────────┐
│                 Slave Steps (并行执行)                │
│  ┌───────────┐  ┌───────────┐       ┌───────────┐  │
│  │ Worker 1  │  │ Worker 2  │ ...   │ Worker N  │  │
│  └───────────┘  └───────────┘       └───────────┘  │
└─────────────────────────────────────────────────────┘
```

### 2.2 关键接口

```java
// 分区器：决定如何分割数据
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}

// 分区处理器：管理分区执行策略
public interface PartitionHandler {
    Collection<StepExecution> handle(StepExecutionSplitter stepSplitter, 
                                     StepExecution stepExecution) throws Exception;
}

// 结果聚合器：收集分区结果
public interface StepExecutionAggregator {
    void aggregate(StepExecution result, 
                   Collection<StepExecution> completedStepExecutions);
}
```

## 3. 实现方式

### 3.1 基于线程池的本地分区（常用）

```java
@Configuration
@EnableBatchProcessing
public class PartitionJobConfiguration {
    
    @Autowired
    private JobBuilderFactory jobBuilderFactory;
    
    @Autowired
    private StepBuilderFactory stepBuilderFactory;
    
    @Bean
    public Job partitionJob() {
        return jobBuilderFactory.get("partitionJob")
                .start(masterStep())
                .build();
    }
    
    @Bean
    public Step masterStep() {
        return stepBuilderFactory.get("masterStep")
                .partitioner("slaveStep", partitioner())
                .partitionHandler(partitionHandler())
                .build();
    }
    
    @Bean
    public Partitioner partitioner() {
        // 示例：基于数据范围的分区
        return new Partitioner() {
            @Override
            public Map<String, ExecutionContext> partition(int gridSize) {
                Map<String, ExecutionContext> partitions = new HashMap<>();
                
                // 模拟从数据库获取总记录数
                int totalRecords = 1000000;
                int range = totalRecords / gridSize;
                
                for (int i = 0; i < gridSize; i++) {
                    ExecutionContext context = new ExecutionContext();
                    int start = i * range;
                    int end = (i == gridSize - 1) ? totalRecords : (i + 1) * range - 1;
                    
                    context.put("startIndex", start);
                    context.put("endIndex", end);
                    context.put("partitionId", "partition" + i);
                    
                    partitions.put("partition" + i, context);
                }
                
                return partitions;
            }
        };
    }
    
    @Bean
    public PartitionHandler partitionHandler() {
        TaskExecutorPartitionHandler handler = new TaskExecutorPartitionHandler();
        handler.setTaskExecutor(taskExecutor());
        handler.setStep(slaveStep());
        handler.setGridSize(10); // 分区数量
        
        return handler;
    }
    
    @Bean
    public Step slaveStep() {
        return stepBuilderFactory.get("slaveStep")
                .<InputData, OutputData>chunk(1000)
                .reader(partitionAwareItemReader())
                .processor(itemProcessor())
                .writer(itemWriter())
                .build();
    }
    
    @Bean
    public TaskExecutor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(10);
        executor.setMaxPoolSize(20);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("partition-thread-");
        executor.initialize();
        
        return executor;
    }
}
```

### 3.2 分区感知的ItemReader

```java
@Component
@StepScope
public class PartitionAwareItemReader implements ItemReader<InputData> {
    
    @Value("#{stepExecutionContext['startIndex']}")
    private Long startIndex;
    
    @Value("#{stepExecutionContext['endIndex']}")
    private Long endIndex;
    
    @Value("#{stepExecutionContext['partitionId']}")
    private String partitionId;
    
    private Long currentIndex;
    private JdbcTemplate jdbcTemplate;
    
    public PartitionAwareItemReader(DataSource dataSource) {
        this.jdbcTemplate = new JdbcTemplate(dataSource);
        this.currentIndex = startIndex;
    }
    
    @Override
    public InputData read() throws Exception {
        if (currentIndex > endIndex) {
            return null;
        }
        
        // 分页读取数据
        String sql = "SELECT * FROM input_table WHERE id BETWEEN ? AND ? LIMIT 1";
        List<InputData> results = jdbcTemplate.query(
            sql, 
            new Object[]{currentIndex, currentIndex},
            new RowMapper<InputData>() {
                @Override
                public InputData mapRow(ResultSet rs, int rowNum) throws SQLException {
                    // 映射逻辑
                    return new InputData();
                }
            }
        );
        
        currentIndex++;
        return results.isEmpty() ? null : results.get(0);
    }
}
```

## 4. 高级配置

### 4.1 动态分区大小

```java
@Bean
public Partitioner dynamicPartitioner(
        @Value("${batch.partition.size:10000}") int partitionSize,
        DataSource dataSource) {
    
    return gridSize -> {
        Map<String, ExecutionContext> partitions = new HashMap<>();
        
        // 动态计算分区
        Long totalCount = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM input_table", Long.class);
        
        int partitionCount = (int) Math.ceil((double) totalCount / partitionSize);
        
        for (int i = 0; i < partitionCount; i++) {
            ExecutionContext context = new ExecutionContext();
            int start = i * partitionSize;
            int end = Math.min(start + partitionSize - 1, totalCount.intValue() - 1);
            
            context.put("minValue", start);
            context.put("maxValue", end);
            context.put("partitionNumber", i);
            
            partitions.put("partition" + i, context);
        }
        
        return partitions;
    };
}
```

### 4.2 分区结果聚合

```java
public class CustomStepExecutionAggregator implements StepExecutionAggregator {
    
    @Override
    public void aggregate(StepExecution result, 
                         Collection<StepExecution> completedStepExecutions) {
        
        int totalRead = 0;
        int totalWrite = 0;
        int totalSkip = 0;
        
        for (StepExecution stepExecution : completedStepExecutions) {
            totalRead += stepExecution.getReadCount();
            totalWrite += stepExecution.getWriteCount();
            totalSkip += stepExecution.getSkipCount();
            
            // 收集自定义指标
            String partitionId = stepExecution.getExecutionContext()
                .getString("partitionId", "unknown");
            
            Long processingTime = stepExecution.getExecutionContext()
                .getLong("processingTime", 0L);
            
            result.getExecutionContext()
                .put(partitionId + "_processingTime", processingTime);
        }
        
        result.setReadCount(totalRead);
        result.setWriteCount(totalWrite);
        result.setSkipCount(totalSkip);
        
        // 设置作业级上下文
        result.getJobExecution().getExecutionContext()
            .put("aggregatedMetrics", calculateAggregatedMetrics(completedStepExecutions));
    }
    
    private Map<String, Object> calculateAggregatedMetrics(
            Collection<StepExecution> stepExecutions) {
        // 实现聚合逻辑
        return new HashMap<>();
    }
}
```

## 5. 最佳实践

### 5.1 性能优化建议

```yaml
# application.yml 配置示例
spring:
  batch:
    job:
      enabled: true
    jdbc:
      initialize-schema: always
      
# 分区配置
batch:
  partition:
    grid-size: ${GRID_SIZE:10}  # 根据CPU核心数调整
    chunk-size: 1000            # 根据内存和事务需求调整
    throttle-limit: 10          # 控制并发线程数
    
# 线程池配置
task:
  executor:
    core-pool-size: 10
    max-pool-size: 20
    queue-capacity: 50
    keep-alive-seconds: 60
```

### 5.2 错误处理策略

```java
@Bean
public Step slaveStep() {
    return stepBuilderFactory.get("slaveStep")
            .<InputData, OutputData>chunk(1000)
            .reader(reader())
            .processor(processor())
            .writer(writer())
            .faultTolerant()
            .skipLimit(100)                     // 跳过错位记录限制
            .skip(Exception.class)              // 可跳过的异常类型
            .noSkip(FileNotFoundException.class) // 不可跳过的异常
            .retryLimit(3)                      // 重试次数
            .retry(DeadlockLoserDataAccessException.class)
            .listener(new PartitionErrorListener()) // 自定义错误监听器
            .build();
}

public class PartitionErrorListener {
    
    @OnReadError
    public void onReadError(Exception ex) {
        // 记录读取错误，考虑跳过该分区
        log.error("Read error in partition", ex);
    }
    
    @OnWriteError
    public void onWriteError(Exception ex, List<? extends OutputData> items) {
        // 记录写入错误，可考虑重试或告警
        log.error("Write error for {} items", items.size(), ex);
    }
}
```

### 5.3 监控与诊断

```java
@Slf4j
@Component
public class PartitionPerformanceMonitor {
    
    private Map<String, PartitionMetrics> metricsMap = new ConcurrentHashMap<>();
    
    @BeforeStep
    public void beforeStep(StepExecution stepExecution) {
        String partitionId = stepExecution.getExecutionContext()
            .getString("partitionId");
        
        metricsMap.put(partitionId, new PartitionMetrics()
            .setStartTime(System.currentTimeMillis())
            .setPartitionId(partitionId));
    }
    
    @AfterStep
    public ExitStatus afterStep(StepExecution stepExecution) {
        String partitionId = stepExecution.getExecutionContext()
            .getString("partitionId");
        
        PartitionMetrics metrics = metricsMap.get(partitionId);
        if (metrics != null) {
            metrics.setEndTime(System.currentTimeMillis())
                  .setRecordCount(stepExecution.getWriteCount())
                  .setStatus(stepExecution.getStatus().toString());
            
            logPartitionMetrics(metrics);
            
            // 存储到执行上下文供聚合器使用
            stepExecution.getExecutionContext()
                .put("processingTime", 
                     metrics.getEndTime() - metrics.getStartTime());
        }
        
        return stepExecution.getExitStatus();
    }
    
    private void logPartitionMetrics(PartitionMetrics metrics) {
        log.info("Partition {} completed: {} records in {} ms, Status: {}",
                metrics.getPartitionId(),
                metrics.getRecordCount(),
                metrics.getProcessingTime(),
                metrics.getStatus());
    }
}
```

## 6. 部署考量

### 6.1 分布式部署（远程分区）

```java
@Bean
public PartitionHandler remotePartitionHandler(
        JobExplorer jobExplorer,
        StepExecutionRequestHandler stepExecutionRequestHandler) {
    
    MessageChannelPartitionHandler handler = new MessageChannelPartitionHandler();
    handler.setJobExplorer(jobExplorer);
    handler.setStepName("slaveStep");
    handler.setGridSize(10);
    
    // 消息中间件配置
    handler.setMessagingOperations(messagingTemplate());
    handler.setOutputChannel(outgoingRequestsChannel());
    handler.setInputChannel(incomingRepliesChannel());
    
    return handler;
}

@Bean
public Step remoteSlaveStep() {
    return stepBuilderFactory.get("remoteSlaveStep")
            .inputChannel(incomingRequestsChannel())
            .outputChannel(outgoingRepliesChannel())
            .handler(stepExecutionRequestHandler())
            .build();
}
```

### 6.2 资源管理

```java
@Configuration
public class ResourceAwarePartitionConfig {
    
    @Bean
    @StepScope
    public Partitioner resourceAwarePartitioner(
            Environment env,
            DataSource dataSource) {
        
        return gridSize -> {
            // 根据可用资源动态调整分区
            int availableCores = Runtime.getRuntime().availableProcessors();
            int memoryMB = getAvailableMemoryMB();
            
            // 动态计算最优分区大小
            int actualGridSize = calculateOptimalGridSize(
                availableCores, memoryMB, gridSize);
            
            // 创建分区...
            return createPartitions(actualGridSize, dataSource);
        };
    }
    
    private int getAvailableMemoryMB() {
        long maxMemory = Runtime.getRuntime().maxMemory();
        return (int) (maxMemory / (1024 * 1024));
    }
}
```

## 7. 总结

Spring Batch的分区并行处理提供了强大的横向扩展能力，能够有效处理大规模数据。关键成功因素包括：
- 合理划分数据分区，避免数据倾斜
- 根据系统资源调整并发度
- 完善的错误处理和监控机制
- 根据业务特点选择合适的ItemReader/Writer

通过合理配置和优化，分区并行处理可以将批处理作业性能提升数倍甚至数十倍，是企业级批处理系统的核心功能之一。