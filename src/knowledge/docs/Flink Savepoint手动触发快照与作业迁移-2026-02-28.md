# Flink Savepoint：手动触发快照与作业迁移技术文档

## 1. 概述

### 1.1 Savepoint 基本概念
**Savepoint** 是 Apache Flink 提供的一种**有状态的、一致性的作业快照机制**，它允许用户在指定时间点捕获整个流处理作业的完整状态。与 Checkpoint 不同，Savepoint 的主要特点是：
- **手动触发与控制**：由用户显式触发和管理
- **持久化存储**：独立于作业生命周期，长期保存
- **作业迁移支持**：用于版本升级、集群迁移、作业调优等场景

### 1.2 与 Checkpoint 的关键区别
| 特性 | Savepoint | Checkpoint |
|------|-----------|------------|
| 触发方式 | 手动 | 自动（周期性） |
| 主要用途 | 作业迁移、版本升级 | 故障恢复 |
| 存储格式 | 标准化格式，版本兼容 | 内部优化格式 |
| 存储位置 | 用户指定（HDFS、S3等） | 配置的State Backend |
| 生命周期 | 手动管理 | 自动清理（可配置） |

## 2. 手动触发 Savepoint

### 2.1 触发前提条件
在触发 Savepoint 前，确保：
1. **作业正常运行**：作业已提交且处于 RUNNING 状态
2. **State Backend 配置正确**：已配置支持 Savepoint 的 State Backend
3. **存储路径可访问**：目标存储系统（HDFS、S3等）权限正常
4. **足够磁盘空间**：保存完整状态数据

### 2.2 触发方式

#### 2.2.1 通过 REST API 触发
```bash
# 触发同步 Savepoint（等待完成）
curl -X POST http://<jobmanager-host>:8081/jobs/<job-id>/savepoints

# 触发异步 Savepoint
curl -X POST http://<jobmanager-host>:8081/jobs/<job-id>/savepoints \
  -H "Content-Type: application/json" \
  -d '{
    "cancel-job": false,
    "target-directory": "hdfs:///flink/savepoints/"
  }'
```

#### 2.2.2 通过 Flink CLI 触发
```bash
# 触发 Savepoint
./bin/flink savepoint <job-id> [target-directory]

# 触发 Savepoint 并停止作业
./bin/flink stop --savepointPath [target-directory] <job-id>
```

#### 2.2.3 通过 Web UI 触发
1. 访问 Flink Web UI（默认端口 8081）
2. 选择目标作业
3. 点击 "Savepoints" 选项卡
4. 点击 "Trigger Savepoint" 按钮
5. 指定存储路径（可选）

### 2.3 带触发参数的高级用法
```bash
# 触发 Savepoint 时指定最大等待时间
./bin/flink savepoint <job-id> \
  --targetDirectory hdfs:///flink/savepoints \
  --timeout 300000

# 使用 YARN 时的特殊处理
./bin/flink savepoint <job-id> \
  -yid <yarn-app-id> \
  <target-directory>
```

## 3. Savepoint 作业迁移

### 3.1 迁移工作流程

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   源作业运行     │───▶│ 触发Savepoint   │───▶│   停止源作业    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                     │
┌─────────────────┐    ┌─────────────────┐    ┌─────▼─────┐
│   检查兼容性    │◀───│ 准备目标环境    │◀───│  选择Savepoint │
└─────────────────┘    └─────────────────┘    └────────────┘
        │
┌───────▼───────┐    ┌─────────────────┐    ┌─────────────────┐
│ 调整作业配置  │───▶│ 从Savepoint恢复  │───▶│  验证目标作业   │
└───────────────┘    └─────────────────┘    └─────────────────┘
```

### 3.2 从 Savepoint 恢复作业

#### 3.2.1 命令行恢复
```bash
# 基本恢复命令
./bin/flink run \
  -s hdfs:///flink/savepoints/savepoint-<id> \
  -c com.example.StreamingJob \
  /path/to/your-job.jar \
  --input <input-path> \
  --output <output-path>

# 允许非恢复状态启动（谨慎使用）
./bin/flink run \
  -s hdfs:///flink/savepoints/savepoint-<id> \
  --allowNonRestoredState \
  ...
```

#### 3.2.2 程序化恢复（在代码中指定）
```java
StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();

// 从指定 Savepoint 恢复
env.setStateBackend(new FsStateBackend("hdfs://namenode:40010/flink/checkpoints"));

// 当从 Savepoint 恢复时，以下配置会在提交作业时指定
// 无需在代码中显式设置
```

### 3.3 跨版本迁移注意事项

#### 3.3.1 状态兼容性检查
```bash
# 检查 Savepoint 的元数据
./bin/flink info <savepoint-path>

# 输出示例：
# -------------------------------------------
# Savepoint Metadata
# -------------------------------------------
# Version: 2.2
# Operator States:
#   - SourceOperator (uid: "source", size: 1.2KB)
#   - WindowOperator (uid: "window", size: 45.7MB)
#   - SinkOperator (uid: "sink", size: 0.5KB)
```

#### 3.3.2 Flink 版本兼容性矩阵
| 保存版本 | 可恢复版本 | 注意事项 |
|----------|------------|----------|
| 1.4.x | 1.5.x-1.8.x | 可能需要状态迁移工具 |
| 1.9.x-1.11.x | 1.12.x-1.13.x | 通常兼容 |
| 1.14.x | 1.15.x+ | 检查 API 变更 |

### 3.4 状态迁移工具（当需要时）
```bash
# 使用状态迁移工具（Flink 1.13+）
./bin/flink savepoint -m migrate <savepoint-path> \
  --from-version <old-version> \
  --to-version <new-version> \
  --target-directory <new-savepoint-path>
```

## 4. 最佳实践与故障排除

### 4.1 最佳实践

#### 4.1.1 定期创建 Savepoint
```bash
#!/bin/bash
# 自动化 Savepoint 脚本示例
JOB_ID="your-job-id"
SAVEPOINT_DIR="hdfs:///flink/savepoints/$(date +%Y%m%d)"

# 触发 Savepoint
RESPONSE=$(curl -s -X POST "http://jobmanager:8081/jobs/${JOB_ID}/savepoints" \
  -H "Content-Type: application/json" \
  -d "{\"target-directory\": \"${SAVEPOINT_DIR}\"}")

REQUEST_ID=$(echo $RESPONSE | jq -r '.request-id')

# 轮询状态
while true; do
  STATUS=$(curl -s "http://jobmanager:8081/jobs/${JOB_ID}/savepoints/${REQUEST_ID}")
  STATE=$(echo $STATUS | jq -r '.status.id')
  
  if [ "$STATE" = "COMPLETED" ]; then
    LOCATION=$(echo $STATUS | jq -r '.operation.location')
    echo "Savepoint created: $LOCATION"
    break
  elif [ "$STATE" = "FAILED" ]; then
    echo "Savepoint failed"
    exit 1
  fi
  
  sleep 5
done
```

#### 4.1.2 Savepoint 目录管理
```bash
# 清理旧 Savepoint（保留最近7天）
find /flink/savepoints -type d -name "savepoint-*" -mtime +7 | xargs rm -rf

# 或使用 Flink 的保留策略配置
state.savepoints.dir: hdfs:///flink/savepoints
execution.checkpointing.cleanup: RETAIN_ON_CANCELLATION
```

### 4.2 常见问题与解决方案

#### 4.2.1 Savepoint 触发失败
**问题**：`java.util.concurrent.TimeoutException`
```bash
# 解决方案：增加超时时间
./bin/flink savepoint <job-id> <target-directory> --timeout 600000
```

#### 4.2.2 恢复时状态不匹配
**问题**：`java.lang.IllegalStateException: Failed to rollback to checkpoint/savepoint`
```bash
# 解决方案：检查算子UID是否一致
# 1. 确认恢复作业的算子UID与Savepoint中一致
# 2. 或在恢复时添加参数：
./bin/flink run -s <savepoint-path> --allowNonRestoredState ...
```

#### 4.2.3 状态过大导致超时
**问题**：大状态作业Savepoint耗时过长
```yaml
# 解决方案：调整配置
execution.checkpointing.timeout: 30min
taskmanager.memory.managed.size: 4g  # 增加托管内存
state.backend.fs.memory-threshold: 1024kb  # 减小文件阈值
```

### 4.3 监控与验证

#### 4.3.1 Savepoint 完整性检查
```bash
# 检查Savepoint是否完整
./bin/flink check-archive <savepoint-path>

# 验证状态大小
hadoop fs -du -h /flink/savepoints/savepoint-<id>
```

#### 4.3.2 监控指标
通过 Flink Metrics 监控 Savepoint：
- `lastCheckpointSize`: 上次Savepoint大小
- `lastCheckpointDuration`: 上次Savepoint耗时
- `numberOfCompletedCheckpoints`: 已完成检查点计数

## 5. 高级主题

### 5.1 增量 Savepoint
```yaml
# 配置增量Savepoint（RocksDBStateBackend）
state.backend: rocksdb
state.backend.rocksdb.checkpoint.transfer.thread.num: 4
execution.checkpointing.incremental: true
```

### 5.2 并行度调整恢复
```bash
# 从Savepoint恢复时改变并行度
./bin/flink run \
  -s <savepoint-path> \
  -p 16 \  # 新并行度
  ...
```

### 5.3 Savepoint 状态裁剪
```bash
# 使用State Processor API处理Savepoint
# 可以：1) 过滤特定状态 2) 修改状态结构 3) 状态压缩
```

## 6. 结论

Flink Savepoint 提供了强大的手动快照和作业迁移能力，是生产环境中不可或缺的功能。关键要点包括：

1. **明确使用场景**：Savepoint 主要用于有计划的操作，Checkpoint 用于故障恢复
2. **保持兼容性**：跨版本迁移时仔细测试状态兼容性
3. **监控与验证**：始终验证 Savepoint 的完整性和可恢复性
4. **制定策略**：建立定期的 Savepoint 策略和清理机制

通过合理使用 Savepoint，可以实现 Flink 作业的零停机迁移、蓝绿部署和安全升级，大大提高流处理系统的可维护性和可靠性。