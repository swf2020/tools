# async-profiler 火焰图：CPU 与内存热点分析技术文档

## 1. 概述

async-profiler 是一款低开销的 Java 性能分析工具，能够同时采集 CPU 和内存分配信息，生成直观的火焰图（Flame Graph）来可视化热点代码路径。

## 2. 核心特性

### 2.1 优势特点
- **低开销**：采用采样机制而非侵入式插桩
- **安全**：无需 Java 代理或修改字节码
- **异步采集**：通过信号机制触发，不干扰应用线程
- **多维度分析**：支持 CPU 时间、内存分配、锁竞争等
- **容器友好**：完全支持容器化环境

### 2.2 支持的分析类型
- CPU 热点分析（执行时间）
- 分配分析（堆内存分配）
- 锁分析（锁竞争情况）
- 文件 I/O 分析
- 套接字 I/O 分析

## 3. 安装与配置

### 3.1 下载与安装
```bash
# 下载最新版本
wget https://github.com/jvm-profiling-tools/async-profiler/releases/download/v2.9/async-profiler-2.9-linux-x64.tar.gz
tar -xzf async-profiler-2.9-linux-x64.tar.gz
cd async-profiler-2.9-linux-x64
```

### 3.2 权限配置
```bash
# 设置权限（允许采集 perf_events）
sudo sysctl -w kernel.perf_event_paranoid=1
sudo sysctl -w kernel.kptr_restrict=0

# 或者使用 capabilities（推荐）
sudo setcap cap_sys_admin+ep /path/to/libasyncProfiler.so
```

## 4. CPU 热点分析

### 4.1 基本使用
```bash
# 启动 CPU 分析（持续 60 秒）
./profiler.sh -d 60 -f cpu-flamegraph.html <pid>

# 实时分析模式
./profiler.sh -e cpu -d 30 -t <pid>
```

### 4.2 常用参数说明
| 参数 | 说明 |
|------|------|
| `-e cpu` | 分析 CPU 使用率（默认） |
| `-d N` | 采集时长（秒） |
| `-i N` | 采样间隔（毫秒，默认10ms） |
| `-t` | 采集每个线程的单独样本 |
| `-o html/text/flamegraph` | 输出格式 |
| `--all-user` | 包含所有用户模式事件 |

### 4.3 生成火焰图
```bash
# 生成 HTML 格式火焰图
./profiler.sh -d 60 -f cpu-profile.html <pid>

# 生成 SVG 格式
./profiler.sh -d 60 -f cpu-profile.svg <pid>

# 生成折叠格式（可用于自定义可视化）
./profiler.sh -d 60 -f cpu-profile.collapsed <pid>
```

## 5. 内存分配分析

### 5.1 堆内存分配热点
```bash
# 分析内存分配（TLAB 内部分配）
./profiler.sh -e alloc -d 60 -f alloc-flamegraph.html <pid>

# 分析对象存活（需要 JDK 11+）
./profiler.sh -e live -d 60 -f live-flamegraph.html <pid>
```

### 5.2 内存分析参数
| 参数 | 说明 |
|------|------|
| `-e alloc` | 分析堆内存分配 |
| `-e live` | 分析存活对象（GC 后仍存在） |
| `--alloc N` | 每 N 字节分配采样一次（默认 16KB） |
| `--live` | 仅跟踪存活对象 |

### 5.3 内存火焰图解读
- **宽度**：表示分配频率或分配大小
- **栈深度**：显示分配调用链
- **颜色编码**：通常按包名或方法名着色

## 6. 火焰图解读指南

### 6.1 视觉元素解析
```
示例火焰图结构：
     ____________
    |   main()   |  ← 顶层函数，最宽表示耗时最多
    |____________|
    ____|____    ____|____
   |  funcA()|  |  funcB()| ← 并列表示并发执行
   |_________|  |_________|
   ____|____       |
  |  libC() |      |      ← 栈深度显示调用关系
  |_________|      |
      |        ____|____
      |       |  libD() |
      |       |_________|
```

### 6.2 热点识别方法
1. **寻找最宽的"山峰"**：表示最耗时的代码路径
2. **检查平顶区域**：可能表示循环或密集计算
3. **分析调用链深度**：深层调用可能产生栈开销
4. **比较不同颜色块**：识别特定包或类的贡献

## 7. 实战分析案例

### 7.1 CPU 瓶颈分析示例
```bash
# 发现高 CPU 使用率后启动分析
./profiler.sh -e cpu -d 30 --chunksize 50m \
  -f /tmp/high-cpu-profile.html <pid>

# 分析结果典型发现：
# 1. JSON 序列化占用 40% CPU
# 2. 正则表达式匹配占用 25% CPU
# 3. 数据库查询结果处理占用 20% CPU
```

### 7.2 内存泄漏分析示例
```bash
# 监控内存增长趋势
./profiler.sh -e alloc -d 120 --interval 5ms \
  -f /tmp/memory-growth.html <pid>

# 配合 GC 日志分析
./profiler.sh -e live -d 300 \
  -f /tmp/live-objects.html <pid>
```

## 8. 高级功能

### 8.1 增量分析
```bash
# 生成差分火焰图（比较两个时间点）
./profiler.sh start <pid>
# ... 执行某些操作 ...
./profiler.sh stop -f diff-start.html <pid>
```

### 8.2 容器环境分析
```bash
# Docker 容器分析
docker exec <container> /profiler/profiler.sh \
  -d 30 -f /tmp/profile.html <pid_in_container>

# Kubernetes 环境
kubectl exec <pod> -- /profiler/profiler.sh \
  -d 60 -f /tmp/profile.html <pid>
```

### 8.3 Java 代理模式
```java
// 启动时加载代理
java -agentpath:/path/to/libasyncProfiler.so=start,event=cpu,file=profile.html \
  -jar application.jar
```

## 9. 最佳实践

### 9.1 分析策略
1. **基线采集**：在正常负载下建立性能基线
2. **负载测试**：在模拟压力下采集数据
3. **对比分析**：优化前后进行对比
4. **持续监控**：关键服务定期采集

### 9.2 避免常见陷阱
- 采样间隔过短导致开销过大
- 分析时间不足遗漏偶发问题
- 忽略容器环境特殊配置
- 未考虑 JIT 编译影响

### 9.3 性能调优循环
```
采集数据 → 识别热点 → 假设优化 → 验证效果 → 重复循环
    ↓           ↓          ↓          ↓
火焰图分析  根因分析   代码修改   性能测试
```

## 10. 工具集成

### 10.1 与 APM 工具结合
- **集成到监控系统**：定期采集并存储火焰图
- **告警联动**：性能异常时自动触发分析
- **历史对比**：建立性能变化时间线

### 10.2 CI/CD 流水线集成
```yaml
# 示例 GitHub Actions 配置
- name: Performance Profiling
  run: |
    ./profiler.sh -d 30 -f perf-${GITHUB_SHA}.html $JAVA_PID
    # 上传分析结果
    # 设置性能基准检查
```

## 11. 故障排除

### 11.1 常见问题
| 问题 | 解决方案 |
|------|----------|
| 权限错误 | 配置 perf_event_paranoid 或使用 capabilities |
| 无符号信息 | 确保使用 -g 编译或保留调试符号 |
| 容器内失败 | 挂载 /proc 和 /sys 文件系统 |
| 采样数据少 | 增加采样时长或调整间隔 |

### 11.2 调试命令
```bash
# 检查 profiler 状态
./profiler.sh status <pid>

# 验证环境配置
./profiler.sh check <pid>

# 查看可用事件
./profiler.sh list <pid>
```

## 12. 结论

async-profiler 结合火焰图提供了强大的 Java 应用性能分析能力。通过系统性的 CPU 和内存热点分析，开发团队可以：
- 快速定位性能瓶颈
- 优化资源使用效率
- 预防内存泄漏问题
- 建立数据驱动的性能优化文化

## 附录
- 官方仓库：https://github.com/jvm-profiling-tools/async-profiler
- 火焰图可视化工具：https://github.com/brendangregg/FlameGraph
- 推荐阅读：《性能之巅》、《深入理解 Java 虚拟机》

---

*文档版本：1.0 | 更新日期：2024-01 | 适用版本：async-profiler 2.0+*