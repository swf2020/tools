# Flink CDC实时同步技术文档  
**主题：基于Debezium嵌入引擎的Flink CDC实时数据同步方案**  
**版本：** 1.0  
**最后更新日期：** 2023年10月  

---

## 1. 概述  
### 1.1 背景  
随着企业对实时数据处理需求的增长，传统批处理数据同步方案已无法满足业务对低延迟、高一致性的要求。基于**Change Data Capture (CDC)** 技术的实时同步方案应运而生，能够捕获数据库的增量变更并实时同步到下游系统。  

### 1.2 方案选型  
**Flink CDC** 结合 **Debezium嵌入式引擎** 提供以下优势：  
- **全量+增量一体化同步**：无需依赖外部工具，支持历史数据全量拉取与增量变更捕获。  
- **Exactly-Once语义**：基于Flink Checkpoint机制保障端到端数据一致性。  
- **低侵入性**：通过数据库日志（如MySQL Binlog、PostgreSQL WAL）解析变更，不影响源库性能。  
- **多源支持**：兼容MySQL、PostgreSQL、Oracle等主流数据库。  

---

## 2. 核心架构  
### 2.1 组件架构图  
```  
┌─────────────────┐    ┌──────────────────────┐    ┌─────────────────┐  
│   Source DB     │────│  Flink CDC Job       │────│   Sink System   │  
│  (MySQL/PostgreSQL) │  │  (Debezium Embedded)│  │ (Kafka/ES/DB)  │  
└─────────────────┘    └──────────────────────┘    └─────────────────┘  
         │                          │                          │  
    Change Logs (Binlog/WAL)   └─── CDC Events ───┘     实时写入  
```  

### 2.2 数据流程  
1. **变更捕获**：Debezium引擎连接源数据库，读取事务日志并解析为变更事件（插入/更新/删除）。  
2. **事件转换**：Flink CDC将Debezium事件转换为Flink内部的`RowData`结构，包含`before/after`数据及元信息（库名、表名、操作类型）。  
3. **流处理**：通过Flink DataStream API或Table API进行数据清洗、转换、聚合。  
4. **结果输出**：将处理后的数据写入Kafka、数据湖或目标数据库。  

---

## 3. 环境与依赖  
### 3.1 系统要求  
- **Flink版本**：≥ 1.13（推荐1.14+，完整支持CDC Connector）。  
- **Debezium版本**：≥ 1.5（与Flink CDC捆绑，无需独立部署）。  
- **源数据库要求**：  
  - MySQL：启用Binlog（`ROW`格式）及`GTID`（推荐）。  
  - PostgreSQL：配置`wal_level=logical`并创建复制槽。  

### 3.2 Maven依赖（示例）  
```xml  
<dependency>  
    <groupId>com.ververica</groupId>  
    <artifactId>flink-connector-mysql-cdc</artifactId>  
    <version>2.3.0</version>  
</dependency>  
<!-- 如需同步PostgreSQL -->  
<dependency>  
    <groupId>com.ververica</groupId>  
    <artifactId>flink-connector-postgres-cdc</artifactId>  
    <version>2.3.0</version>  
</dependency>  
```  

---

## 4. 配置与实现  
### 4.1 源表定义（Flink SQL示例）  
```sql  
CREATE TABLE mysql_source (  
    id INT PRIMARY KEY,  
    name STRING,  
    update_time TIMESTAMP(3)  
) WITH (  
    'connector' = 'mysql-cdc',  
    'hostname' = 'localhost',  
    'port' = '3306',  
    'username' = 'user',  
    'password' = 'password',  
    'database-name' = 'test_db',  
    'table-name' = 'user_table',  
    'server-time-zone' = 'Asia/Shanghai',  
    -- 全量阶段读取选项  
    'scan.startup.mode' = 'initial', -- 可选: initial（全量+增量）, latest-offset（仅增量）  
    'debezium.snapshot.mode' = 'initial'  
);  
```  

### 4.2 数据管道逻辑  
```java  
// DataStream API示例（Java）  
StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();  
env.enableCheckpointing(60000); // 启用Checkpoint（精确一次保障）  

SourceFunction<RowData> sourceFunction = MySQLSource.<RowData>builder()  
    .hostname("localhost")  
    .port(3306)  
    .databaseList("test_db")  
    .tableList("test_db.user_table")  
    .username("user")  
    .password("password")  
    .deserializer(new JsonDebeziumDeserializationSchema())  
    .startupOptions(StartupOptions.initial())  
    .build();  

DataStreamSource<RowData> sourceStream = env.addSource(sourceFunction);  
sourceStream  
    .map(new TransformationLogic()) // 自定义转换逻辑  
    .addSink(new KafkaSink(...)); // 输出到Kafka  
```  

### 4.3 关键配置项说明  
| 参数 | 说明 | 示例值 |  
|------|------|--------|  
| `scan.startup.mode` | 启动模式，定义从何处开始读取 | `initial`（全量+增量） |  
| `debezium.*` | Debezium引擎底层配置，如心跳、缓冲区大小 | `debezium.snapshot.locking.mode=none` |  
| `server-id` | MySQL副本ID，需保证集群内唯一 | `5001-5005` |  
| `chunk-key-column` | 全量阶段数据分片列（提升并行度） | `id` |  

---

## 5. 高级特性与优化  
### 5.1 并行度与性能调优  
- **全量阶段并行读取**：通过`chunk-key-column`将大表拆分为多个Split，并行拉取。  
- **增量阶段负载均衡**：对多个表或分片库配置不同`server-id`，避免单点压力。  
- **内存管理**：调整`debezium.buffer.size`（默认32MB）以应对高流量场景。  

### 5.2 异常处理与监控  
- **断点续传**：依赖Flink Checkpoint保存offset，任务重启后自动恢复。  
- **监控指标**：  
  - Flink Metrics：`numRecordsIn`（输入记录数）、`currentFetchEventTimeLag`（消费延迟）。  
  - Debezium Metrics：通过JMX暴露`snapshot.completed`、`last.event.time`。  

### 5.3 多表同步与Schema变更  
- **整库同步**：通过`database-name`和`table-name`支持正则匹配（如`test_db.user_.*`）。  
- **Schema自动演化**：当源表结构变更（如新增列）时，可通过`debezium.schema.history.internal`记录变更历史。  

---

## 6. 生产部署建议  
### 6.1 高可用配置  
- **Flink JobManager HA**：基于ZooKeeper或Kubernetes实现JobManager故障转移。  
- **数据库连接冗余**：为Debezium配置重试策略（`debezium.retriable.error.codes`）。  

### 6.2 数据一致性保障  
- **Exactly-Once写入Kafka**：启用Flink Kafka Producer的**事务写入**（需Kafka 0.11+）。  
- **幂等写入数据库**：通过Upsert操作（如`INSERT ... ON DUPLICATE KEY UPDATE`）避免重复数据。  

### 6.3 资源规划参考  
| 场景 | 建议并行度 | 内存配置 |  
|------|-----------|----------|  
| 单表同步（QPS < 1k） | 2~4 | TaskManager 2GB |  
| 多表同步（QPS > 10k） | 8~16 | TaskManager 8GB+ |  

---

## 7. 常见问题与解决  
### 7.1 延迟增高  
- **原因**：源库事务日志堆积或网络瓶颈。  
- **解决**：  
  1. 检查数据库日志清理策略（如MySQL `expire_logs_days`）。  
  2. 增加Flink任务并行度或调整`debezium.poll.interval.ms`。  

### 7.2 全量阶段内存溢出  
- **原因**：大表全量拉取时数据缓冲过大。  
- **解决**：  
  1. 启用分片读取（配置`chunk-key-column`）。  
  2. 调低`scan.incremental.snapshot.chunk.size`（默认8096行）。  

### 7.3 DDL变更导致同步中断  
- **原因**：Debezium无法解析不兼容的DDL（如修改列类型）。  
- **解决**：  
  1. 手动跳过该DDL事件（`debezium.skipped.operations=truncate`）。  
  2. 重启任务并从最新offset继续（需业务容忍数据丢失）。  

---

## 8. 附录  
### 8.1 参考文档  
- [Flink CDC官方文档](https://ververica.github.io/flink-cdc-connectors/)  
- [Debezium嵌入式配置指南](https://debezium.io/documentation/reference/stable/development/engine.html)  

### 8.2 版本更新记录  
| 版本 | 日期 | 修改说明 |  
|------|------|----------|  
| 1.0  | 2023-10 | 初始版本，基于Flink 1.16 + Debezium 1.9 |  

---

**文档维护团队：** 数据平台组  
**联系方式：** data-platform@company.com