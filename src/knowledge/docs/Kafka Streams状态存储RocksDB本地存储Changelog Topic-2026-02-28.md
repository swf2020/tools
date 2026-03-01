# Kafka Streams状态存储技术文档  
## 本地RocksDB存储 + Changelog Topic协同架构  

---

## 1. 概述  
Kafka Streams的状态存储是其实现有状态流处理的核心机制，通过**本地RocksDB实例**与**Kafka Changelog Topic**的协同设计，在保证低延迟本地访问的同时，提供了容错性与状态恢复能力。本文档详细描述该架构的工作原理、配置方式及最佳实践。

---

## 2. 架构设计  
### 2.1 整体视图  
```
┌─────────────────────────────────────────────────────────────┐
│                    Kafka Streams 实例                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                State Store (逻辑层)                   │  │
│  │  ┌──────────────┐  ┌────────────────────────────┐  │  │
│  │  │   RocksDB    │◄─┤     Store Changelog        │  │  │
│  │  │  (本地存储)   │  │     (异步持久化)           │  │  │
│  │  └──────┬───────┘  └──────────────┬─────────────┘  │  │
│  └─────────┼──────────────────────────┼────────────────┘  │
│            │                          │                   │
│     本地磁盘访问               Kafka Cluster                │
└────────────┼──────────────────────────┼────────────────────┘
             │                          │
        ┌────┴─────┐             ┌──────┴──────┐
        │ 本地磁盘  │             │Changelog Topic│
        │ (状态快照)│             │(持久化状态变更)│
        └──────────┘             └──────────────┘
```

### 2.2 核心组件  
- **RocksDB本地存储**：嵌入式键值数据库，提供低延迟状态访问  
- **Changelog Topic**：Kafka内部Topic，按分区记录所有状态变更  
- **Standby Replica**：通过Changelog实现的状态副本，用于故障转移  

---

## 3. RocksDB本地存储  
### 3.1 特性  
1. **嵌入式设计**  
   - 每个流分区对应独立的RocksDB实例  
   - 数据存储在`{application.id}-{task.id}/`目录下  

2. **存储结构**  
   ```bash
   state.dir/
   ├── kafka-streams/
   │   ├── my-app/
   │   │   ├── 0_0/          # 任务目录 (分区_副本)
   │   │   │   ├── rocksdb/  # 数据文件
   │   │   │   │   ├── 000001.sst
   │   │   │   │   ├── MANIFEST-000001
   │   │   │   │   └── OPTIONS-000001
   │   │   │   └── checkpoint # 恢复点
   ```

3. **访问模式**  
   - 通过`ReadOnlyKeyValueStore`或`ReadWriteKeyValueStore`接口访问  
   - 支持范围查询、前缀扫描等操作  

### 3.2 配置参数  
```properties
# RocksDB基础配置
streamsConfig.put(StreamsConfig.ROCKSDB_CONFIG_SETTER_CLASS_CONFIG, 
                  CustomRocksDBConfig.class);

# 状态目录配置
streamsConfig.put(StreamsConfig.STATE_DIR_CONFIG, "/var/lib/kafka-streams");

# 缓存配置
streamsConfig.put(StreamsConfig.CACHE_MAX_BYTES_BUFFERING_CONFIG, 10 * 1024 * 1024L);
```

---

## 4. Changelog Topic机制  
### 4.1 变更日志记录  
- **记录内容**：键值状态的`PUT`、`DELETE`操作  
- **压缩策略**：基于键的日志压缩，仅保留最新值  
- **分区映射**：与源流分区一一对应  

### 4.2 数据格式示例  
```json
{
  "key": "user:1001",
  "value": {"lastLogin": "2024-01-15T10:30:00Z", "count": 42},
  "operation": "PUT",
  "timestamp": 1705314600000
}
```

### 4.3 配置参数  
```properties
# Changelog Topic配置
streamsConfig.put(StreamsConfig.topicPrefix(TopicConfig.RETENTION_MS_CONFIG), 
                  7 * 24 * 60 * 60 * 1000L);  // 保留7天
streamsConfig.put(StreamsConfig.topicPrefix(TopicConfig.CLEANUP_POLICY_CONFIG), 
                  "compact,delete");
```

---

## 5. 状态恢复流程  
### 5.1 正常启动恢复  
```
1. 定位最新检查点 → 2. 从Changelog加载变更 → 3. 重建RocksDB
```

### 5.2 故障恢复场景  
```java
// 自动恢复配置
streamsConfig.put(StreamsConfig.PROCESSING_GUARANTEE_CONFIG, 
                  StreamsConfig.EXACTLY_ONCE_V2);

// 恢复监听器
streams.setGlobalStateRestoreListener(new StateRestoreListener() {
    @Override
    public void onRestoreStart(TopicPartition tp, String storeName, long start, long end) {
        log.info("开始恢复状态存储: {}", storeName);
    }
});
```

---

## 6. 容错与高可用  
### 6.1 Standby副本机制  
- 每个状态存储维护`num.standby.replicas`个热备副本  
- 备用实例持续消费Changelog Topic保持同步  

### 6.2 故障转移流程  
```
主实例失败 → 控制器重分配任务 → Standby实例提升为主实例
    ↓
无数据丢失（Changelog保证） → 继续处理
```

---

## 7. 性能调优指南  
### 7.1 RocksDB优化  
```java
public class CustomRocksDBConfig implements RocksDBConfigSetter {
    @Override
    public void setConfig(String storeName, Options options, 
                         Map<String, Object> configs) {
        // 调整内存表大小
        options.setMaxWriteBufferNumber(4);
        options.setWriteBufferSize(64 * 1024 * 1024L);
        
        // 压缩优化
        options.setCompressionType(CompressionType.LZ4_COMPRESSION);
        options.setBottommostCompressionType(CompressionType.ZSTD_COMPRESSION);
    }
}
```

### 7.2 状态存储配置  
| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `cache.max.bytes.buffering` | 10-50MB | 缓存大小 |
| `commit.interval.ms` | 100ms | 提交间隔 |
| `num.standby.replicas` | 1-2 | 备用副本数 |

---

## 8. 监控与运维  
### 8.1 关键指标  
- **状态存储大小**：`stream-state-size-bytes`  
- **恢复进度**：`restore-rate`、`remaining-records`  
- **缓存命中率**：`hit-ratio`  

### 8.2 运维命令  
```bash
# 查看状态目录
ls -lah /var/lib/kafka-streams/my-app/

# 检查Changelog Topic
kafka-console-consumer --topic my-app-store-changelog --partition 0 --from-beginning

# 重置应用程序状态（危险！）
kafka-streams-application-reset --application-id my-app --input-topics source-topic
```

---

## 9. 限制与注意事项  
1. **磁盘空间**：RocksDB可能产生大量SST文件  
2. **恢复时间**：状态越大恢复时间越长  
3. **内存使用**：Block缓存与Memtable占用堆外内存  
4. **多实例部署**：确保每个实例有独立的状态目录  

---

## 10. 最佳实践  
1. **定期清理**：设置Changelog保留策略  
2. **监控告警**：监控状态存储增长情况  
3. **测试恢复**：定期模拟故障测试恢复流程  
4. **版本兼容**：升级时注意RocksDB文件格式兼容性  

---

## 附录  
- [RocksDB官方调优指南](https://github.com/facebook/rocksdb/wiki/RocksDB-Tuning-Guide)  
- [Kafka Streams状态存储文档](https://kafka.apache.org/documentation/streams/)  
- [性能基准测试模板](./benchmark/state-store-benchmark.java)  

---

**文档版本**: 1.1  
**最后更新**: 2024年1月  
**适用版本**: Kafka Streams 3.0+