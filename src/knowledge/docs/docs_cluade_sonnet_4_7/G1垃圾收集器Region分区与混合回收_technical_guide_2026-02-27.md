# G1 垃圾收集器：Region 分区与混合回收

---

## 0. 定位声明

```
适用版本：JDK 11+ （G1 成为默认收集器），重点示例基于 JDK 17 LTS
前置知识：需了解 JVM 内存模型基础（堆/非堆）、GC 基本原理（标记-清除、复制算法）、
          以及 CMS 收集器的痛点（了解背景对比）
不适用范围：
  - 本文不覆盖 ZGC / Shenandoah 的实现（虽有对比）
  - 不适用于 JDK 8u40 以下版本（早期 G1 行为差异较大）
  - 不覆盖 Graal VM / Native Image 下的 GC 行为
```

---

## 1. 一句话本质

**G1 的 Region 分区**：把原本一整块堆内存切成几百个小格子（Region），垃圾多的格子优先被清理，而不是每次都扫整个堆。

**混合回收（Mixed GC）**：在清理"年轻代格子"的同时，顺手把"垃圾最多的老年代格子"一起清了，用一次停顿换最大回收收益。

**整体一句话**：G1 是把堆切成碎块、按垃圾密度排队清理的收集器，目标是在可预测的停顿时间内尽量多回收内存。

---

## 2. 背景与根本矛盾

### 历史背景

2000 年代中期，Java 应用堆内存从 GB 级向几十 GB 演进。传统收集器面临严重挑战：

- **Parallel GC（吞吐优先）**：Full GC 时整堆 Stop-The-World（STW），堆越大暂停越长，动辄几十秒，不可接受。
- **CMS（低延迟优先）**：并发标记减少停顿，但有三大痛点：内存碎片（无法整理）、浮动垃圾（Concurrent Mode Failure）、与 Young GC 之间的协调复杂度极高。

G1 由 David Detlefs 等人在 Sun Labs 研究，2012 年随 JDK 7u4 正式可用，2017 年 JDK 9 成为默认收集器，目标是**替代 CMS，在大堆（6GB~数百GB）上实现可预测的低停顿**。

### 根本矛盾（Core Trade-off）

| 维度 | 两端 | G1 的取舍 |
|------|------|-----------|
| **吞吐 vs 延迟** | Parallel GC 追求吞吐 | G1 倾向延迟，接受 10~15% 吞吐损耗换取可预测停顿 |
| **空间利用率 vs 碎片化** | 不整理内存则碎片多 | Region 机制允许按需整理部分区域，代价是 Region 内部碎片 |
| **回收完整性 vs 停顿时间** | 每次全量回收最彻底 | 每次只回收"性价比最高"的 Region 子集，牺牲部分回收量换停顿可控 |
| **并发复杂度 vs 安全性** | 并发越多停顿越短 | 使用 SATB（Snapshot-At-The-Beginning）写屏障保证并发标记正确性，引入额外 CPU 开销 |

---

## 3. 核心概念与领域模型

### 3.1 关键术语表

| 术语 | 费曼式定义 | 正式定义 |
|------|------------|----------|
| **Region** | 堆里的一个"小格子"，大小固定，可以临时扮演不同角色 | 堆内存的基本管理单元，大小为 1MB~32MB（2 的幂次），数量通常 ~2048 个 |
| **Humongous Region** | 放不进普通格子的"大件物品"，需要连续多个格子拼起来 | 对象大小 > Region 大小 50% 时，分配到连续 Humongous Region |
| **RSet（Remembered Set）** | 每个格子记录"谁持有我里面对象的引用"的小账本 | 每个 Region 维护的数据结构，记录来自其他 Region 的引用，用于增量扫描 |
| **CSet（Collection Set）** | 本次 GC 要清理的格子清单 | 当次 GC 选定的 Region 集合，Young GC 只含 Eden/Survivor，Mixed GC 额外含部分老年代 |
| **SATB** | 开始并发标记时，先给整个对象图拍张"快照"，之后的修改单独处理 | Snapshot-At-The-Beginning，并发标记的正确性保证算法，通过写屏障记录被覆盖的旧引用 |
| **Mixed GC** | 同时清理新生代和"垃圾最多的老年代格子"的一次 GC | 在 Young GC 基础上，额外纳入部分老年代 Region 到 CSet 的回收行为 |
| **Evacuation** | 把活着的对象从"要清理的格子"搬到空格子，原格子整体释放 | G1 的核心回收动作，复制存活对象到新 Region，原 Region 整体回收（无碎片） |

### 3.2 领域模型

```
┌─────────────────────────────────────────────────────────────────┐
│                        JVM Heap (e.g., 32GB)                    │
│                                                                 │
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐     │
│  │ E  │ │ E  │ │ S  │ │ O  │ │ O  │ │ H  │ │ H  │ │ Free│   │
│  └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘     │
│  Eden  Eden  Surv  Old  Old Humong Humong Free                  │
│                                                                 │
│  每个 Region = 1~32MB，角色动态分配，逻辑上构成分代            │
└─────────────────────────────────────────────────────────────────┘

Region 角色：
  E (Eden)    → 新对象分配区，Young GC 后整体清空
  S (Survivor)→ Young GC 后存活对象的中转区
  O (Old)     → 经多次 GC 晋升的老对象
  H (Humongous)→ 大对象专属（连续多 Region）
  Free        → 未分配，可随时变身任意角色

RSet 关系示意：
  Old Region A ──引用→ Eden Region B
                         ↑
                   B 的 RSet 记录"A 引用了我"
  → Young GC 扫描 B 时，只需额外扫描 A，无需扫全堆
```

### 3.3 分代逻辑与 Region 动态性

G1 保留了分代概念，但**分代是逻辑上的**，物理上没有固定的新生代/老年代边界。同一个物理地址的 Region，在一次 GC 后可能从 Eden 变成 Free，再变成 Old，角色完全动态。

**关键比例参数**：
- 新生代占比默认 5%~60%（`-XX:G1NewSizePercent=5`，`-XX:G1MaxNewSizePercent=60`），G1 自适应调整
- Region 大小：`-XX:G1HeapRegionSize=N`（不设则自动计算，目标 ~2048 个 Region）

---

## 4. 对比与选型决策

### 4.1 同类收集器横向对比

| 指标 | G1 | ZGC (JDK 15+) | Shenandoah | CMS (已废弃) |
|------|----|---------------|------------|--------------|
| **目标停顿** | 可配置，通常 50~200ms | < 10ms（亚毫秒级目标） | < 10ms | 较低，但不可预测 |
| **适用堆大小** | 6GB ~ 数百GB | 8MB ~ 16TB | 任意 | < 8GB 效果好 |
| **吞吐损耗** | ~10~15% | ~15~20% | ~15~20% | ~10% |
| **内存碎片** | 无（Region 整体回收） | 无 | 无 | 有（不整理） |
| **并发整理** | 部分并发 | 全并发 | 全并发 | 无整理 |
| **CPU 额外开销** | 中（SATB 写屏障） | 高（读屏障 + 转发） | 高（Brooks 指针） | 低 |
| **Full GC 风险** | 低（有 Mixed GC） | 极低 | 极低 | 高（CMF） |
| **JDK 默认** | JDK 9~20（许多场景） | JDK 21+ 推荐 | 需显式开启 | 已删除（JDK 14） |

### 4.2 选型决策树

```
你的业务停顿要求是什么？
│
├── 需要 < 10ms 亚毫秒级 → 考虑 ZGC（JDK 21+）或 Shenandoah
│
├── 可接受 50~200ms，堆 > 6GB → ✅ 推荐 G1（主流选择）
│
├── 堆 < 4GB，吞吐优先 → Parallel GC 可能更合适
│
└── 堆极大（> 1TB） + 低延迟 → ZGC（JDK 21 引入分代 ZGC）
```

**G1 最佳场景**：
- 堆内存 8GB~64GB，停顿目标 100~200ms
- 对象生命周期两极分化（大量短命对象 + 少量长寿对象）
- 无法接受 CMS 的内存碎片风险

**不选 G1 的场景**：
- 吞吐率极度敏感（批处理场景），Parallel GC 吞吐更高
- 需要亚毫秒停顿（实时交易），选 ZGC
- 内存极小（< 2GB），G1 的 RSet 维护开销不划算

---

## 5. 工作原理与实现机制

### 5.1 静态结构

**核心数据结构**：

```
HeapRegion（每个 Region 的元数据）
├── bottom / top / end        → 地址边界
├── _type                     → Eden / Survivor / Old / Humongous / Free
├── _gc_efficiency            → 垃圾回收效率（可回收字节数 / 预计回收时间）
├── _rem_set (RSet)           → 来自其他 Region 的引用卡表
│   └── sparse/coarse/fine    → 三级精度自适应存储
└── _next_top_at_mark_start   → SATB 并发标记起始位置（NTAMS）
```

**为什么用三级 RSet 而不是单一精度？**

RSet 需要在内存占用和查询精度之间权衡。引用少时用稀疏哈希（精确），引用多时退化为粗粒度位图（省内存），这是一种自适应的空间效率优化。

### 5.2 动态行为：四种 GC 模式

#### 模式一：Young GC（最常见）

```
触发条件：Eden Region 全满

执行步骤（全程 STW）：
1. 确定 CSet = 全部 Eden + 全部 Survivor Region
2. 并行扫描 GC Root（栈变量、静态变量、JNI 引用）
3. 通过 RSet 找到跨 Region 引用（无需扫全堆）
4. Evacuation（疏散）：
   - 存活对象复制到新 Survivor Region
   - 达到晋升阈值的对象复制到 Old Region
5. 原 CSet 中所有 Region 整体释放 → 立即可用作 Free Region
6. 更新 RSet（并发完成）

典型停顿：10~150ms（取决于存活对象数量，非堆大小）
```

#### 模式二：并发标记周期（Concurrent Marking Cycle）

```
触发条件：老年代占用 >= InitiatingHeapOccupancyPercent（默认 45%）

阶段：
1. 初始标记（STW，~5ms）      → 标记 GC Root 直接引用的对象，借助 Young GC 完成
2. 根扫描（并发）             → 扫描 Survivor Region，找跨代引用根
3. 并发标记（并发，分钟级别）  → 遍历整个对象图，使用 SATB 写屏障处理并发修改
4. 最终标记（STW，~10ms）     → 处理 SATB 缓冲区中的剩余变更（Remark）
5. 清理（STW + 并发）        → 统计每个 Region 存活率，生成回收优先级列表
   - STW 部分：更新 RSet、释放完全空的 Region（~10ms）
   - 并发部分：重置位图，准备下次标记
```

**SATB 的正确性保证（关键设计决策）**：

并发标记期间，应用线程在修改引用时，写屏障会把"被覆盖的旧引用值"写入 SATB 缓冲区。这确保了在标记开始时存活的所有对象都不会被漏标，代价是可能保留一些"浮动垃圾"（并发期间死亡的对象）到下次回收。

**为什么用 SATB 而不是增量更新（CMS 的方式）？**

增量更新（跟踪新增引用）需要在每次"引用变新值"时记录，而 SATB 记录"旧值"，逻辑上只需保证标记开始时的快照完整性。在并发标记结束的 Remark 阶段，SATB 的需要处理的队列通常远小于增量更新的集合，STW 更短。

#### 模式三：混合回收（Mixed GC）—— 核心机制

```
触发条件：并发标记周期完成后，G1 认为有足够多的高效老年代 Region 值得回收

选择逻辑（Garbage-First 的名字来源）：
  按 _gc_efficiency（可回收字节 / 预计暂停时间）降序排列老年代 Region
  在停顿时间预算内，尽量多纳入高效率 Region

CSet 构成：
  = 全部 Eden + Survivor（必选）
  + 高价值老年代 Region（按效率排名 Top-K，受 G1MixedGCCountTarget 控制）

执行过程：与 Young GC 相同的 Evacuation 机制
  存活对象从 Old Region 复制到 Free Region，原 Old Region 整体释放

混合回收轮数：
  通常执行 4~8 次（G1MixedGCCountTarget 默认 8），每次纳入不同的老年代 Region
  直到老年代占用降到 G1HeapWastePercent（默认 5%）以下，停止混合回收
```

**混合回收的核心 Trade-off**：

每次只清理"性价比最高"的老年代 Region，而不是全部老年代，停顿时间可控（符合 MaxGCPauseMillis 预算），但代价是**回收不彻底**——垃圾密度低的老年代 Region 可能长期得不到清理。极端情况下，若老年代增长速度超过混合回收速度，会触发 Full GC。

#### 模式四：Full GC（兜底，尽量避免）

```
触发条件：
  - Evacuation 失败（To Space Exhausted）：复制对象时找不到空闲 Region
  - 混合回收跟不上老年代增长速度
  - Humongous 对象分配导致内存耗尽

行为：退化为单线程（JDK 10+ 支持并行 Full GC）串行 Mark-Compact，全堆整理
停顿：秒级到分钟级，必须尽力避免
```

### 5.3 关键设计决策分析

**决策一：Region 大小为何是 1~32MB 的 2 次幂？**

Region 必须足够大以容纳对象并摊销元数据开销（RSet、位图等），又必须足够小使数量足够多（~2048 个）以支撑精细的回收选择。1~32MB 的 2 次幂约束是为了简化地址计算（位运算定位 Region），权衡了内存利用率和管理精度。

**决策二：RSet 为何存储"谁引用了我"而非"我引用了谁"？**

GC 回收 Region X 时，需要找到所有来自外部的引用（以更新它们）。如果存储"我引用了谁"，定位引用者需要全堆扫描。反向存储（RSet 记录入引用），可以精确定位需要扫描的外部 Region，将扫描范围从整堆压缩到少数几个 Region。

**决策三：InitiatingHeapOccupancyPercent（IHOP）为何默认 45% 而不是更高？**

留出足够缓冲空间给并发标记期间新分配的对象。45% 意味着并发标记开始时，至少还有 55% 的空间可供应用继续运行。若设置过高（如 80%），并发标记期间空间耗尽，会触发 Evacuation 失败进而 Full GC。JDK 9+ 引入了 Adaptive IHOP，G1 会根据历史数据自动调整此值。

---

## 6. 高可靠性保障

### 6.1 高可用机制

**Evacuation 失败处理**：复制对象时空间不足，G1 会把对象原地标记（不复制），继续完成本次 GC，然后触发 Full GC 整理。这比直接 OOM 更安全，但停顿会显著延长（秒级）。

**To Space Overflow 预防**：`-XX:G1ReservePercent=10`（默认10%），预留 10% 堆空间专供 Evacuation，降低失败概率。

**并发标记失败降级**：若并发标记来不及完成（堆占用激增），G1 会强制触发 Full GC，保证内存安全。

### 6.2 可观测性——关键监控指标

| 指标 | 含义 | 健康阈值 | 异常信号 |
|------|------|----------|----------|
| **GC 停顿时间** | 每次 STW 时长 | < MaxGCPauseMillis（200ms） | 持续超出目标 30%+ |
| **Full GC 频率** | Full GC 次数/小时 | 0（理想情况） | > 1次/天 需关注 |
| **老年代占用率** | Old Region / 总 Region | < 70% | 持续上升趋近 100% |
| **Mixed GC 触发频率** | 并发标记周期次数/小时 | 与业务对象晋升速度匹配 | 0（不触发说明混合回收不足） |
| **Evacuation 失败次数** | To Space Exhausted 事件 | 0 | 任何出现需立即处理 |
| **RSet 扫描时间** | Young GC 中扫描 RSet 的耗时 | < 30ms | > 50ms 考虑调整 RSet 参数 |
| **Humongous 分配次数** | 每秒大对象分配量 | 越少越好 | 高频出现需优化代码 |

**获取指标方法**：
```bash
# JDK 17，开启 GC 详细日志（生产推荐配置）
-Xlog:gc*,gc+phases=debug,gc+humongous=debug:file=/var/log/gc.log:time,uptime,pid:filecount=5,filesize=20m

# 通过 JMX / JFR（Java Flight Recorder）实时监控
jcmd <pid> JFR.start duration=60s filename=gc_recording.jfr
```

### 6.3 SLA 保障核心手段

1. **设置合理停顿目标**：`-XX:MaxGCPauseMillis=200`（G1 会自适应调整 CSet 大小以符合目标，但无法保证 100% 达标）
2. **堆大小设置**：`-Xms` 与 `-Xmx` 设为相同值，避免堆动态扩缩容触发额外 GC
3. **避免大对象**：超过 Region 50% 的对象直接进 Humongous，不参与常规分代晋升，影响回收效率

---

## 7. 使用实践与故障手册

### 7.1 生产级配置示例

```bash
# 适用于：JDK 17 LTS，8~32GB 堆，响应时间敏感的 Web 服务
# 场景：Spring Boot 应用，堆 16GB，停顿目标 200ms

JAVA_OPTS="\
  -Xms16g \
  -Xmx16g \
  -XX:+UseG1GC \
  -XX:MaxGCPauseMillis=200 \
  -XX:G1HeapRegionSize=16m \         # 16GB 堆 / 2048 = 8MB，手动设 16MB 减少 Region 数
  -XX:G1NewSizePercent=20 \          # 新生代最小 20%（避免过小导致频繁 Young GC）
  -XX:G1MaxNewSizePercent=40 \       # 新生代最大 40%（留空间给老年代）
  -XX:G1ReservePercent=15 \          # 预留 15% 防 Evacuation 失败（默认 10% 偏小）
  -XX:InitiatingHeapOccupancyPercent=35 \  # 提前触发并发标记（默认 45% 对高吞吐场景偏晚）
  -XX:G1MixedGCCountTarget=8 \       # 混合回收最多 8 轮（默认值，一般够用）
  -XX:G1HeapWastePercent=5 \         # 老年代可回收量 < 5% 时停止混合回收
  -XX:ConcGCThreads=4 \              # 并发标记线程数（建议 CPU 核数 / 4）
  -XX:ParallelGCThreads=8 \          # STW 并行 GC 线程数（建议 CPU 核数 / 2 或与核数相同）
  -Xlog:gc*:file=/var/log/app-gc.log:time,uptime:filecount=5,filesize=20m"
```

**关键参数说明**：

| 参数 | 默认值 | 作用 | 调整风险 |
|------|--------|------|----------|
| `MaxGCPauseMillis` | 200ms | 停顿时间目标（软目标，非硬保证） | 设太小 → G1 频繁 GC，吞吐下降 |
| `G1HeapRegionSize` | 自动计算 | Region 大小 | 设太小 → Humongous 对象增多；设太大 → 分代粒度粗 |
| `InitiatingHeapOccupancyPercent` | 45% | 并发标记触发阈值 | 设太高 → 并发标记来不及完成，引发 Full GC |
| `G1ReservePercent` | 10% | 预留空间比例 | 设太低 → Evacuation 失败风险上升 |
| `ConcGCThreads` | ~1/4 核数 | 并发标记线程数 | 设太高 → 抢占应用 CPU；太低 → 标记跟不上分配 |

### 7.2 故障模式手册

```
【故障1：频繁 Full GC（Evacuation Failure）】
- 现象：日志出现 "to-space exhausted" 或 "Evacuation Failure"，停顿突然从 200ms 飙到 5s+
- 根本原因：
    Old Region 占用太快 → 混合回收赶不上晋升速度
    或 G1ReservePercent 太低，Evacuation 无空闲 Region 可用
- 预防措施：
    增大 G1ReservePercent（10% → 20%）
    降低 InitiatingHeapOccupancyPercent（45% → 30~35%）提前启动并发标记
    检查是否存在对象过早晋升（降低 MaxTenuringThreshold）
- 应急处理：
    短期：重启实例，触发 Full GC 后内存恢复
    中期：增加堆内存或增大 G1ReservePercent
    根本：分析对象分配模式，减少大对象或内存泄漏
```

```
【故障2：GC 停顿持续超出 MaxGCPauseMillis 目标】
- 现象：-XX:MaxGCPauseMillis=200 但实测停顿 500ms~1s
- 根本原因：
    存活对象太多，Evacuation 耗时超预算
    RSet 过大（大量跨 Region 引用），扫描耗时高
    G1 无法将 CSet 缩小到停顿目标以内（活对象下限）
- 预防措施：
    检查 Young GC 日志中 "[Scan RS]" 耗时，若 > 30ms 考虑优化对象引用结构
    减少 G1MaxNewSizePercent，降低每次 Young GC 的 Evacuation 量
    检查是否有大量 Humongous 对象（会绕过 RSet 机制，处理代价高）
- 应急处理：
    调低 G1MaxNewSizePercent（如 40% → 25%），降低单次回收量换取达标
    开启 -Xlog:gc+phases=debug 分析各阶段耗时，定位瓶颈
```

```
【故障3：大对象（Humongous）导致内存泄漏式增长】
- 现象：Old 区持续增长，Mixed GC 效果弱，GC 日志大量 "Humongous allocation"
- 根本原因：
    大对象（> Region 50%）直接进 Humongous Region，占据连续内存
    Humongous Region 在并发标记后才能回收，回收频率低于普通 Region
    JDK 8u60 以前，Humongous 对象甚至不会在 Young GC 中被回收（⚠️ 版本差异）
- 预防措施：
    增大 G1HeapRegionSize，提高 Humongous 阈值（如 Region 16MB，则 > 8MB 才算大对象）
    代码层面：避免大数组、大 String 频繁分配；考虑对象池
    开启 -Xlog:gc+humongous=debug 统计大对象分配热点
- 应急处理：
    JDK 9+ Humongous 对象已可在 Young GC 阶段回收（-XX:+G1EagerReclaimHumongousObjects 默认开启）
    短期可适当增加堆大小缓解压力
```

```
【故障4：并发标记长时间不触发（老年代缓慢增长不达 IHOP）】
- 现象：老年代占用 40%+ 但 GC 日志没有并发标记，只有 Young GC，内存持续上涨
- 根本原因：
    InitiatingHeapOccupancyPercent 设置过高（如 70%）
    或 Adaptive IHOP 计算异常，低估了所需标记时机
- 预防措施：
    监控老年代占用趋势，IHOP 应在趋势到达危险水位前 20%+ 时触发
    JDK 9+ 可观察 GC 日志中 "Adaptive IHOP" 相关行确认自适应状态
- 应急处理：
    临时降低 InitiatingHeapOccupancyPercent 至 30~40%
    重启应用前确认无内存泄漏
```

### 7.3 边界条件与局限性

- **G1 停顿目标是"软目标"**：`MaxGCPauseMillis` 是指导性参数，当存活对象太多时，G1 无法进一步缩减停顿，只能超出目标。承诺"绝对不超 200ms"是错误的产品设计。
- **RSet 内存开销不可忽视**：在引用关系复杂的应用中（如图数据库、大规模缓存），RSet 内存可能占到总堆的 5%~20%，需要纳入堆大小规划。
- **并发标记 CPU 开销**：`ConcGCThreads` 个并发线程持续运行会抢占 CPU（通常 10~25%），CPU 敏感的实时计算场景需评估影响。
- **小堆不适合 G1**：堆 < 4GB 时，Region 数量少，G1 的选择性回收优势无法发挥，Parallel GC 通常有更好的吞吐表现。
- **Humongous 对象无法被 Young GC 完整处理**（JDK 8u60 以前）：老版本大对象只在并发标记后回收，是已知限制，升级 JDK 可改善。

---

## 8. 性能调优指南

### 8.1 性能瓶颈识别

```bash
# Step 1：启用详细 GC 日志（JDK 11+）
-Xlog:gc*,gc+phases=debug:file=gc.log:time,uptime

# Step 2：分析停顿时间分布
# 关注 GC 日志中各阶段耗时（单位 ms）：
# [Eden: 2.0G->0.0B(2.0G) Survivors: 128.0M->192.0M Heap: 8.0G->6.0G(16.0G)]
# [Ext Root Scanning: 12.3ms]    → GC Root 扫描，高则检查 JNI 引用、ClassLoader 数量
# [Scan RS: 45.2ms]              → RSet 扫描，高则跨 Region 引用过多
# [Object Copy: 120.5ms]         → 对象复制，高则存活对象过多
# [Choose CSet: 0.5ms]           → CSet 选择，通常可忽略

# Step 3：使用 GCViewer 或 GCEasy 可视化分析
# https://gceasy.io（在线分析 GC 日志）
```

**瓶颈定位优先级**：
1. Evacuation Failure / Full GC → 内存配置或 IHOP 问题（最高优先级）
2. `Object Copy` 耗时过高（> 150ms）→ 存活对象过多，检查内存泄漏或调大堆
3. `Scan RS` 耗时过高（> 30ms）→ 跨 Region 引用过多，优化数据结构或调大 Region 大小
4. `Ext Root Scanning` 耗时过高（> 20ms）→ 检查 JNI 引用、ClassLoader 数量（OSGi 场景常见）

### 8.2 调优步骤（按优先级）

| 优先级 | 调优方向 | 操作 | 预期效果 | 验证方法 |
|--------|----------|------|----------|----------|
| P0 | 消除 Full GC | 降低 IHOP，增加 Reserve | Full GC 次数归零 | GC 日志无 Full GC |
| P1 | 达到停顿目标 | 调整 MaxGCPauseMillis 与新生代比例 | P99 停顿 ≤ 目标 | GC 日志停顿分布 |
| P2 | 减少 GC 频率 | 调大堆或 Eden 比例 | Young GC 间隔 > 5s | GC 频率统计 |
| P3 | 降低 GC CPU 开销 | 减少 ConcGCThreads，优化对象存活率 | CPU 使用率下降 5~15% | 系统监控 |
| P4 | 内存利用率优化 | 消除 Humongous，调整 Region 大小 | 堆利用率提升 | GC 日志 Humongous 事件 |

### 8.3 调优参数速查表

| 参数 | 默认值 | 推荐值（16GB Web 服务） | 调整风险 |
|------|--------|------------------------|----------|
| `MaxGCPauseMillis` | 200ms | 100~200ms（按业务 SLA） | 过低 → GC 频率高，吞吐下降 |
| `G1HeapRegionSize` | 自动 | 8~16MB（>= 8GB 堆） | 过大 → Humongous 阈值高；过小 → RSet 多 |
| `InitiatingHeapOccupancyPercent` | 45% | 35~40% | 过低 → 并发标记频繁，CPU 开销增加 |
| `G1ReservePercent` | 10% | 15~20% | 过高 → 浪费堆空间 |
| `G1NewSizePercent` | 5% | 20~25% | 过大 → 老年代空间受压 |
| `G1MaxNewSizePercent` | 60% | 30~40% | 过大 → 单次 Young GC 停顿长 |
| `G1MixedGCCountTarget` | 8 | 4~8 | 过小 → 每轮混合回收量大，停顿长 |
| `G1HeapWastePercent` | 5% | 5~10% | 过高 → 混合回收提前停止，老年代残留垃圾多 |
| `ParallelGCThreads` | ~CPU核数 | CPU核数（容器注意限额） | 过多 → 容器环境 CPU 超额 |
| `ConcGCThreads` | ~1/4核数 | CPU核数 / 4 | 过多 → 抢占应用线程 CPU |

---

## 9. 演进方向与未来趋势

### 9.1 分代 ZGC（JDK 21，重要趋势）

JDK 21 引入了**分代 ZGC**（`-XX:+UseZGC -XX:+ZGenerational`），将 ZGC 的亚毫秒停顿与分代假设结合，在吞吐率和停顿之间取得新的平衡。这对 G1 构成实质性竞争：

- **对 G1 用户的影响**：在 JDK 21+ 的新项目中，高延迟敏感场景（停顿目标 < 50ms）建议优先评估分代 ZGC。G1 仍然是中等延迟（100~200ms）场景的稳健选择，生态成熟度和可调参数更丰富。
- **G1 自身演进**：JDK 20+ 持续优化 G1 的并发标记效率和 Evacuation 并行度，每个 LTS 版本停顿时间有 5~15% 的改善。

### 9.2 G1 的 Adaptive IHOP 成熟化

JDK 9 引入的 Adaptive IHOP 在 JDK 17~21 持续优化，通过机器学习预测最佳标记触发时机，减少手动调参需求。

**实践影响**：JDK 17+ 在大多数场景下，可以不设置 `InitiatingHeapOccupancyPercent`，让 Adaptive IHOP 自动管理。但对停顿有严格 SLA 的场景，仍建议手动设置并监控。

### 9.3 值得关注的 JEP

- **JEP 404（G1 的 Card Set Memory）**：改进 RSet 存储结构，减少内存占用 20~30%，JDK 18+ 可用
- **JEP 423（Region Pinning for G1）**：JDK 22 引入，支持固定特定 Region 不被移动，解决 JNI Critical Section 导致的 GC 停顿扩大问题

---

## 10. 面试高频题

```
【基础理解层】（考察概念掌握）

Q：G1 的 Region 和传统分代有什么本质区别？
A：传统分代（如 Parallel GC）的新生代/老年代是物理连续的固定内存块；G1 的分代是逻辑上的，
   物理上是等大小的 Region 碎片，同一 Region 可在不同 GC 后扮演不同角色。这使 G1 能够灵活
   调整各代大小，并选择性地回收任意位置的高垃圾密度 Region，而不需要整体搬移。
考察意图：区分概念理解深度，是否仅停留于"G1有Region"这一表象，还是理解其动态性和设计初衷。

Q：什么是 Mixed GC，它和 Full GC 有什么区别？
A：Mixed GC 在 Young GC 基础上，额外将部分垃圾率高的老年代 Region 纳入 CSet 一并回收，
   通过 Evacuation（复制存活对象）实现无碎片整理，停顿时间可控（符合 MaxGCPauseMillis 预算）。
   Full GC 是整堆的 Mark-Compact，单线程（JDK 10 前）或并行，停顿时间数秒到分钟级，是兜底机制。
   Mixed GC 是 G1 的"正常老年代回收手段"，Full GC 是失控时的最后手段。
考察意图：验证候选人是否真正理解 G1 的设计目标——通过 Mixed GC 避免 Full GC。
```

```
【原理深挖层】（考察内部机制理解）

Q：G1 如何在不扫描全堆的情况下确保 Young GC 的正确性？
A：通过 RSet（记忆集）。每个 Region 维护一个 RSet，记录来自其他 Region 的引用。
   Young GC 时，CSet 是全部 Eden+Survivor，只需额外扫描这些 Region 的 RSet 所指向的
   外部 Region（通常是老年代的少数几个 Region），即可找到所有跨代引用，无需全堆扫描。
   RSet 由写屏障（Write Barrier）在每次引用赋值时维护，代价是每次写操作的额外 CPU 开销。
考察意图：考察对 RSet 机制和写屏障代价的理解，判断候选人是否能权衡"正确性保障的成本"。

Q：G1 并发标记期间，应用线程修改了引用，如何保证不漏标？
A：G1 使用 SATB（Snapshot-At-The-Beginning）算法。并发标记开始时逻辑上对对象图"快照"，
   之后应用线程若覆盖一个引用（将旧值改为新值），写屏障会把旧引用值记录到 SATB 缓冲区。
   最终标记（Remark，STW）阶段处理缓冲区，确保旧值指向的对象也被标记。
   代价是可能保留部分"已死"对象到下次 GC（浮动垃圾），但绝不会漏标存活对象。
考察意图：验证对并发 GC 正确性挑战的理解（三色标记法的并发修改问题），以及 SATB vs 增量更新的权衡。
```

```
【生产实战层】（考察工程经验）

Q：线上 Java 服务突然出现 GC 停顿从 200ms 飙升至 5 秒，如何排查？
A：
  1. 立即查看 GC 日志，确认是 Full GC（"Pause Full"）还是 Young/Mixed GC 超时
  2. 若是 Full GC：查找触发原因：
     - "to-space exhausted" → Evacuation 失败，G1ReservePercent 不足或老年代增长过快
     - "Metadata GC Threshold" → Metaspace 不足，调大 MaxMetaspaceSize
     - "System.gc()" → 应用主动调用，排查代码或关闭 ExplicitGCInvokesConcurrent
  3. 若是 Young/Mixed GC 超时：分析各阶段耗时（phases=debug 日志）：
     - Object Copy 高 → 存活对象多，查内存泄漏（heapdump 分析）
     - Scan RS 高 → 跨 Region 引用多，考虑增大 G1HeapRegionSize
  4. 同时检查：CPU 使用率是否异常（GC 并发标记线程是否抢占）、是否有 OOM 风险
考察意图：验证实际生产 GC 问题排查能力，包括工具使用、日志解读、问题定位的系统性思维。

Q：如何评估一个 Java 服务是否适合从 G1 切换到 ZGC？
A：
  评估维度：
  1. 停顿目标：若业务 SLA 要求 P99 < 50ms，G1 难以持续达成，ZGC 更适合
  2. 堆大小：堆 > 32GB 且停顿敏感，ZGC 优势更明显
  3. JDK 版本：ZGC 在 JDK 21（分代 ZGC）后才有与 G1 可比的吞吐率，建议 JDK 21+
  4. CPU 资源：ZGC 读屏障比 G1 写屏障 CPU 开销更高，CPU 受限环境需评估
  5. 应用特征：若对象存活率高（Full GC 频繁），ZGC 的全并发优势更大
  
  迁移建议：在预发布环境压测，对比 P50/P95/P99 停顿、吞吐率、CPU 使用率，数据驱动决策。
考察意图：验证候选人能否基于业务约束做有依据的技术选型，而非盲目追新。
```

---

## 11. 文档元信息

### 验证声明

```
本文档内容经过以下验证：
✅ 核心机制描述（Region 模型、RSet、SATB、Mixed GC 触发逻辑）
   与官方文档一致性核查：https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html
✅ 参数默认值参考 JDK 17 官方调优指南
✅ 故障模式与调优建议来自 JVM 领域公开生产案例

⚠️ 以下内容未经本地环境实测验证，仅基于官方文档推断：
   - 第8节调优参数"推荐值"（基于常见生产经验，需根据实际工作负载验证）
   - RSet 内存占比数据（5%~20%，来源于社区博客，未在特定业务场景实测）
   - JEP 423（Region Pinning）的具体效果（JDK 22 新特性，实战案例有限）
```

### 知识边界声明

```
本文档适用范围：
  JDK 11~21，部署于 Linux x86_64 环境，使用 HotSpot JVM
  堆大小 4GB~128GB 的典型 Web/微服务场景

不适用场景：
  - GraalVM Native Image（无 JIT，GC 行为完全不同）
  - OpenJ9（IBM J9 JVM 的 G1 实现有差异）
  - JDK 8u40 以下（早期 G1 缺少 Adaptive IHOP 等关键功能）
  - Azul Zing/Zulu 商业 JVM（C4 收集器替代了 G1）
```

### 参考资料

```
官方文档：
  - JDK 17 G1 调优指南：https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html
  - G1 GC 性能调优白皮书（Oracle）：https://www.oracle.com/technical-resources/articles/java/g1gc.html

核心论文：
  - Garbage-First Garbage Collection（Detlefs et al., 2004）：
    https://dl.acm.org/doi/10.1145/1029873.1029879

社区资源：
  - OpenJDK GC 相关 JEP 列表：https://openjdk.org/jeps/
  - GCEasy 在线 GC 日志分析：https://gceasy.io
  - Aleksey Shipilёv 的 GC 系列博客（深度机制分析）：https://shipilev.net

延伸阅读：
  - 《深入理解 Java 虚拟机》第三版，周志明（第3章 GC 算法与收集器）
  - RedHat G1GC 生产调优指南：https://access.redhat.com/solutions/2162391
```

---
