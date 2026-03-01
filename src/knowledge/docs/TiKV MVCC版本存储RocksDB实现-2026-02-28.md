# TiKV MVCC 版本存储（基于 RocksDB 的实现）

## 1. 概述
TiKV 采用 Multi-Version Concurrency Control（MVCC）机制来支持并发事务和快照隔离。MVCC 的核心思想是为每个数据项维护多个版本，使读写操作能够无锁并发执行。TiKV 利用 RocksDB 作为底层存储引擎，通过巧妙的键值编码设计实现高效的版本存储与管理。

## 2. MVCC 整体架构
TiKV 的 MVCC 实现主要包含以下核心组件：
- **Per-Key 的锁（Lock）**：记录事务对键的锁定状态
- **Per-Key 的写入（Write）**：记录键的版本提交信息
- **Per-Key 的默认数据（Default）**：存储键的实际值

这三个组件分别存储在 RocksDB 的三个不同列族（Column Family）中，以实现物理隔离和独立管理。

## 3. 键值编码设计
### 3.1 键（Key）编码结构
```
[Prefix][UserKey][Timestamp]
```
- **Prefix**：标识列族类型（`'l'` 表示锁，`'w'` 表示写入，无前缀表示数据）
- **UserKey**：用户原始键（经编码后）
- **Timestamp**：事务提交时间戳（Commit TS），对于锁列族为事务开始时间戳（Start TS）

### 3.2 各列族的具体编码
#### 3.2.1 锁列族（Lock CF）
```
Key:   'l' + encoded_user_key
Value: LockInfo (序列化格式)
```
LockInfo 包含：
- 锁类型（Put、Delete、Lock）
- 事务开始时间戳（Start TS）
- 主键（用于事务回滚时清理）
- 锁过期时间（TTL）

#### 3.2.2 写入列族（Write CF）
```
Key:   'w' + encoded_user_key + commit_ts
Value: WriteRecord (序列化格式)
```
WriteRecord 包含：
- 写入类型（Put、Delete、Rollback、Lock）
- 事务开始时间戳（Start TS）
- 指向实际数据位置的短值（Short Value，可选）

#### 3.2.3 默认列族（Default CF）
```
Key:   encoded_user_key + start_ts
Value: 用户实际数据值
```

## 4. 数据操作流程
### 4.1 写入流程（以 Put 为例）
1. **预写阶段**：
   - 在 Lock CF 写入锁记录
   - 在 Default CF 写入数据（Key: user_key + start_ts）

2. **提交阶段**：
   - 在 Write CF 写入提交记录（Key: user_key + commit_ts）
   - 从 Lock CF 删除对应的锁记录

3. **短值优化**：
   - 若数据值较小（≤ 64字节），直接存储在 Write CF 的 Value 中
   - 避免 Default CF 的额外写入，提升性能

### 4.2 读取流程（快照读）
1. 根据读取时间戳（read_ts）查找 Write CF：
   - 查找 user_key 对应的最新 commit_ts ≤ read_ts 的 WriteRecord
   - 若记录类型为 Delete 或 Rollback，返回空
   - 若记录类型为 Put，继续下一步

2. 获取实际数据：
   - 若 WriteRecord 包含短值，直接返回
   - 否则根据 WriteRecord 中的 start_ts 从 Default CF 读取数据

3. 检查锁冲突：
   - 读取 Lock CF 检查是否存在未提交的锁
   - 若存在且锁的时间戳 < read_ts，等待或报错（取决于隔离级别）

### 4.3 垃圾回收（GC）
TiKV 定期执行 GC 任务，清理不再需要的旧版本：
1. **安全点（Safe Point）**：确定最早可能被读取的时间戳
2. **扫描 Write CF**：删除 commit_ts < safe_point 的旧版本记录
3. **清理 Default CF**：删除对应的旧版本数据
4. **批量删除**：利用 RocksDB 的 DeleteRange 优化清理效率

## 5. RocksDB 优化实践
### 5.1 前缀提取与压缩
```rust
// TiKV 中的前缀提取器配置
opts.prefix_extractor = SliceTransform::FixedPrefixTransform(prefix_length);
```
- 利用键的前缀特性优化迭代和压缩
- 减少 I/O 放大，提升范围查询性能

### 5.2 列族特定配置
```toml
# TiKV 配置文件示例
[rocksdb.defaultcf]
compression-per-level = ["no", "no", "lz4", "lz4", "lz4", "zstd", "zstd"]

[rocksdb.writecf]
optimize-for-point-lookup = true
block-cache-size = "2GB"
```

### 5.3 迭代器优化
- **前缀迭代器**：高效扫描特定键的所有版本
- **合并迭代器**：同时读取多个列族的数据
- **时间戳过滤**：在迭代过程中跳过不可见版本

## 6. 性能调优建议
### 6.1 内存配置
- **Block Cache**：为 Write CF 分配足够缓存，加速版本查找
- **MemTable**：根据写入负载调整各列族的 MemTable 大小
- **Bloom Filter**：为 Write CF 和 Default CF 启用布隆过滤器

### 6.2 压缩策略
- **Write CF**：使用轻量级压缩（如 LZ4），平衡 CPU 和 I/O
- **Default CF**：上层使用快速压缩，底层使用高压缩率算法

### 6.3 并发控制
- **线程池分离**：为不同列族配置独立的压缩线程池
- **写停顿控制**：避免 GC 期间的写停顿影响在线业务

## 7. 故障恢复与一致性
### 7.1 事务恢复
- 利用 Lock CF 中的锁信息重建事务状态
- 通过 Write CF 中的提交记录判断事务结果
- 未提交事务的清理（残留锁处理）

### 7.2 一致性检查
- **定期校验**：检查 MVCC 版本链的完整性
- **跨列族一致性**：确保 Lock、Write、Default CF 间的数据一致
- **损坏修复**：利用 Raft 日志重建损坏的数据

## 8. 监控与诊断
### 8.1 关键指标
- **MVCC 版本数分布**：监控各区域的版本数量
- **GC 延迟**：监控垃圾回收的及时性
- **锁冲突率**：识别热点键和事务冲突

### 8.2 诊断工具
```sql
-- TiDB 系统表查询 MVCC 信息
SELECT * FROM information_schema.tikv_region_status
WHERE table_name = 'your_table';
```

## 9. 总结
TiKV 基于 RocksDB 的 MVCC 实现通过精心的键值编码设计和多列族存储，在保证 ACID 事务特性的同时，提供了优异的读写性能。这种设计充分利用了 RocksDB 的 LSM-tree 特性，通过版本化存储实现了高效的并发控制和历史数据管理。在实际部署中，需要根据业务负载特点合理配置 RocksDB 参数，并建立完善的监控体系，以确保系统的稳定性和性能。

---
**文档版本**：1.0  
**适用版本**：TiKV 4.0+  
**最后更新**：2024年1月  

*注：本文档描述的实现在不同 TiKV 版本中可能存在差异，具体行为请参考对应版本的源代码和官方文档。*