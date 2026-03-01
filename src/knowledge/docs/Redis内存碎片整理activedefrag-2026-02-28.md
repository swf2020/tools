# Redis 内存碎片整理（Active Defrag）技术文档

## 1. 概述

### 1.1 内存碎片问题
Redis作为内存数据库，在执行内存分配和回收过程中会产生内存碎片。内存碎片会降低内存利用率，可能导致即使有足够空闲内存也无法满足新内存分配请求的情况，从而影响系统性能。

### 1.2 Active Defrag 简介
Active Defragmentation（主动碎片整理）是Redis 4.0引入的特性，用于自动识别并整理内存碎片，将分散的小块空闲内存合并为连续的大块内存，提高内存使用效率。

## 2. 内存碎片产生原因

### 2.1 主要产生场景
- **键值对频繁修改**：值大小变化导致内存重新分配
- **键过期或删除**：产生不连续的空闲内存块
- **不同大小对象混合存储**：导致内存分配器无法有效复用空间
- **使用大量小对象**：增加内存分配频率

### 2.2 碎片率计算
```plaintext
内存碎片率 = used_memory_rss / used_memory
```
- `used_memory_rss`：Redis进程实际占用的物理内存
- `used_memory`：Redis分配器分配的内存总量
- 碎片率 > 1.0 表示存在碎片，1.5以上为显著碎片

## 3. Active Defrag 工作原理

### 3.1 自适应算法
Active Defrag采用自适应算法，在系统空闲时执行碎片整理，避免影响正常服务：
- 监控系统CPU和内存使用情况
- 仅在系统负载较低时执行整理操作
- 可配置的CPU占用上限

### 3.2 碎片整理过程
1. **扫描阶段**：遍历数据库中的键，识别可以移动的键值对
2. **移动阶段**：将键值对移动到连续内存区域
3. **内存回收**：释放原内存空间，形成连续空闲块

## 4. 配置参数详解

### 4.1 启用配置
```bash
# redis.conf 配置文件
activedefrag yes
```

### 4.2 核心配置参数

#### 4.2.1 触发阈值
```bash
# 内存碎片率阈值，达到此值开始整理
active-defrag-ignore-bytes 100mb
active-defrag-threshold-lower 10
active-defrag-threshold-upper 100
```

#### 4.2.2 资源限制
```bash
# CPU占用限制（百分比）
active-defrag-cycle-min 5
active-defrag-cycle-max 75

# 最小碎片量触发整理
active-defrag-min-scan-freq 1000
```

## 5. 监控与管理

### 5.1 监控指标
```bash
# 查看碎片状态
redis-cli info memory | grep -E "mem_fragmentation_ratio|active_defrag"

# 关键指标说明
# mem_fragmentation_ratio: 当前内存碎片率
# active_defrag_running: 是否正在执行碎片整理（0/1）
# defrag_misses: 因各种原因跳过的整理次数
```

### 5.2 手动触发整理
```bash
# 通过命令手动触发
redis-cli memory purge
```

## 6. 最佳实践

### 6.1 生产环境配置建议
```bash
# 推荐配置示例
activedefrag yes
active-defrag-ignore-bytes 200mb
active-defrag-threshold-lower 20
active-defrag-threshold-upper 100
active-defrag-cycle-min 10
active-defrag-cycle-max 50
```

### 6.2 注意事项
1. **性能影响**：碎片整理会消耗CPU资源，建议在业务低峰期执行
2. **大键处理**：对于大键（如list、hash）的移动可能较慢
3. **内存预留**：确保有足够空闲内存供整理过程使用
4. **版本兼容**：确保Redis版本≥4.0

## 7. 故障排查

### 7.1 常见问题
```bash
# 问题1：碎片整理未触发
检查项：
1. 配置是否启用 activedefrag
2. 碎片率是否达到阈值
3. 系统负载是否过高

# 问题2：整理效果不明显
可能原因：
1. 存在大量不可移动的大对象
2. 内存分配器限制
3. 配置阈值设置过高
```

### 7.2 性能调优
1. 根据实际负载调整CPU占用限制
2. 对于大内存实例，适当增加扫描频率
3. 监控整理进度，避免影响业务性能

## 8. 性能测试建议

### 8.1 测试方案
```bash
# 模拟碎片产生
redis-benchmark -n 1000000 -r 1000000 -d 1000

# 监控整理过程
while true; do
    redis-cli info memory | grep fragmentation
    sleep 1
done
```

## 9. 结论

Redis Active Defrag功能提供了有效的内存碎片管理方案，通过合理配置可以在不影响业务性能的前提下自动优化内存使用。建议在生产环境中根据实际业务特点和硬件配置进行参数调优，并建立相应的监控告警机制。

---
**文档版本**：v1.0  
**适用版本**：Redis 4.0+  
**最后更新**：2024年