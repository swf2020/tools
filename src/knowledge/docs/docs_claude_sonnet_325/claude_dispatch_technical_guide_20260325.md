# Claude Dispatch 技术学习文档

---

## 0. 定位声明

```
适用版本：Claude Code (claude CLI) ≥ 1.x，基于 2025 年 Anthropic 公开的 Agent 架构设计
前置知识：
  - 理解 Claude Code 的 Agent Loop 基本流程（工具调用 → 结果返回 → 继续推理）
  - 了解 MCP（Model Context Protocol）协议基础
  - 理解 LLM API 的 messages / tool_use / tool_result 消息结构
  - 熟悉 Prompt Caching（cache_control: ephemeral）的工作原理

不适用范围：
  - 本文不覆盖 Anthropic API 直接调用的批量推理（Batch API）
  - 不适用于通过 SDK 自行构建的 Multi-Agent 框架（如 LangGraph、AutoGen）
  - 不涉及 Anthropic 内部私有调度基础设施（Opus 路由、负载均衡层）
```

---

## 1. 一句话本质

Claude Dispatch 解决的问题是：**当一个复杂任务可以被拆分成多个独立子任务时，如何让多个 Claude 实例同时干活、互不干扰、最终把结果汇总给主 Claude？**

类比现实：就像一个包工头（主 Claude / Orchestrator）把工程拆成电工、水工、油漆工三组（子 Claude / Subagent），三组同时施工，包工头负责最终验收和协调。每组工人只知道自己那部分任务，不会看到其他组的对话。

---

## 2. 背景与根本矛盾

### 历史背景

Claude Code 作为 Agentic Coding Assistant，在处理真实工程任务时迅速暴露了单线程 Agent Loop 的天花板：

- **任务规模**：大型代码库迁移、全项目测试修复、跨模块重构——这些任务的步骤数远超单 Agent 的上下文窗口（200K tokens）
- **执行效率**：串行执行相互独立的子任务（如为 50 个文件添加 docstring）效率极低，用户等待时间线性增长
- **认知隔离**：子任务之间相互污染上下文，导致注意力涣散（attention dilution），任务越多失误率越高

Claude Dispatch 正是在这个背景下，作为 Orchestrator-Subagent 架构的工程实现而出现。

### 根本矛盾（Trade-off）

| 维度 | 张力一端 | 张力另一端 | Claude Dispatch 的取舍 |
|------|---------|-----------|----------------------|
| **并行度 vs 一致性** | 子任务并行执行，吞吐最大 | 共享状态（文件、Git）存在竞争条件 | 调度层不做状态协调，由 Orchestrator 在任务设计上保证隔离性 |
| **上下文隔离 vs 信息共享** | 每个 Subagent 独立上下文，精准聚焦 | 子任务间无法直接通信，信息需通过 Orchestrator 中转 | 优先隔离，通过结构化 prompt 注入必要上下文 |
| **任务拆分灵活性 vs 调度开销** | 粒度越细并行收益越大 | 每个 Subagent 都有独立的 LLM 调用链开销（latency + token cost） | 调度粒度由 Orchestrator（即 Claude 自身）动态决策，无固定粒度规则 |

---

## 3. 核心概念与领域模型

### 3.1 关键术语表

| 术语 | 费曼式定义 | 正式定义 |
|------|-----------|---------|
| **Orchestrator** | 总指挥，负责理解大任务、拆分任务、分配给工人、汇总结果 | 运行在主 Agent Loop 中的 Claude 实例，具有调用 `Task` 工具的权限，负责任务规划和结果聚合 |
| **Subagent** | 专注执行单一子任务的工人 Claude，只知道自己的活，不知道其他工人在干嘛 | 由 Orchestrator 通过 `Task` 工具动态创建的独立 Claude 实例，拥有独立上下文窗口，可访问工具集 |
| **Task 工具** | 一张任务委托书，Orchestrator 把子任务的描述和所需工具写进去，系统新开一个 Claude 去执行 | Claude Dispatch 的核心原语，是一个特殊 Tool，其执行会触发一个新的完整 Agent Loop |
| **Agent Loop** | Claude 的工作循环：思考 → 用工具 → 看结果 → 继续思考，直到任务完成 | LLM 调用 + 工具调用的迭代执行单元，每次循环包含至少一次 API call |
| **Context Isolation** | 每个工人只有自己的小黑板，看不到别人写了什么 | Subagent 持有独立的 conversation history，不共享 Orchestrator 的消息列表 |
| **Prompt Injection（初始化注入）** | 包工头开工前交代给工人的背景信息 | Orchestrator 在 Task 工具调用时，通过 `description` 字段向 Subagent 注入的初始上下文 |

### 3.2 领域模型

```
┌─────────────────────────────────────────────────────────────────┐
│                     User / Shell Session                        │
└─────────────────────────┬───────────────────────────────────────┘
                          │ 用户指令（自然语言）
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Orchestrator Claude                          │
│                                                                 │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │ Plan Phase  │───▶│ Dispatch     │───▶│ Aggregate Phase  │  │
│  │（任务拆分）  │    │（Task 工具） │    │（结果汇总验证）  │  │
│  └─────────────┘    └──────┬───────┘    └──────────────────┘  │
│                            │                                    │
│              ┌─────────────┼──────────────┐                   │
│              ▼             ▼              ▼                    │
│       ┌────────────┐ ┌────────────┐ ┌────────────┐           │
│       │ Subagent A │ │ Subagent B │ │ Subagent C │           │
│       │ (独立Loop) │ │ (独立Loop) │ │ (独立Loop) │           │
│       │            │ │            │ │            │           │
│       │ Bash Tool  │ │ Bash Tool  │ │ Edit Tool  │           │
│       │ Read Tool  │ │ Write Tool │ │ Search Tool│           │
│       └─────┬──────┘ └─────┬──────┘ └─────┬──────┘          │
│             │               │               │                  │
│             └───────────────┼───────────────┘                 │
│                             │ tool_result（串行返回）          │
└─────────────────────────────────────────────────────────────────┘
```

**实体关系：**
- 1 个 Orchestrator 可同时 dispatch N 个 Subagent（并行）
- 每个 Subagent 拥有独立的：消息历史、工具执行权限、token 预算
- Subagent 的执行结果通过 `tool_result` 消息块返回给 Orchestrator
- Subagent 之间**无直接通信通道**，只能通过文件系统或 Orchestrator 间接通信

---

## 4. 对比与选型决策

### 4.1 同类架构横向对比

| 维度 | Claude Dispatch (Task 工具) | LangGraph Multi-Agent | AutoGen GroupChat | CrewAI |
|------|----------------------------|-----------------------|-------------------|--------|
| **调度模型** | Orchestrator 动态决策 | 静态 DAG 图 | 基于角色的轮询 | 基于角色的任务链 |
| **隔离粒度** | 完全上下文隔离 | 节点间可共享 State | 共享 GroupChat 历史 | 部分隔离 |
| **并行能力** | ✅ 原生并行（同时 dispatch 多个 Task）| ✅ 条件并行 | ❌ 基本串行 | ⚠️ 有限并行 |
| **工具传递** | Orchestrator 显式指定子任务工具集 | 节点级工具绑定 | Agent 级工具绑定 | Agent 级工具绑定 |
| **人工干预点** | Orchestrator 决策层可介入 | DAG 节点边界 | 每轮对话 | 任务交接点 |
| **上下文膨胀风险** | 低（子任务隔离） | 中 | 高（全局历史增长） | 中 |
| **适用场景** | 大规模代码工程任务 | 结构化 pipeline | 对话型协作 | 角色扮演型任务 |

### 4.2 选型决策树

```
任务是否可并行拆分？
├── 否 → 使用单 Agent Loop，无需 Dispatch
└── 是 → 子任务间是否存在共享可变状态竞争？
          ├── 是（如写同一文件）→ 先串行 Dispatch，或由 Orchestrator 设计隔离边界
          └── 否 → 使用并行 Dispatch（同时触发多个 Task）
                    子任务是否需要跨任务实时通信？
                    ├── 是 → 考虑 LangGraph 等支持 State 共享的框架
                    └── 否 → Claude Dispatch 是最优选
```

---

## 5. 工作原理与实现机制

### 5.1 静态结构：Task 工具定义

在 Claude Code 的内部工具定义中，`Task` 工具的 schema 大致如下：

```json
{
  "name": "Task",
  "description": "Launch a new agent to handle a subtask. Use for parallelizable work or tasks requiring focused context.",
  "input_schema": {
    "type": "object",
    "properties": {
      "description": {
        "type": "string",
        "description": "Short label for this subtask (used for display)"
      },
      "prompt": {
        "type": "string",
        "description": "Full instruction for the subagent, including all necessary context"
      }
    },
    "required": ["description", "prompt"]
  }
}
```

> ⚠️ 存疑：以上 schema 基于代理日志逆向分析推断，非 Anthropic 官方公开文档，实际字段名可能存在差异。

**关键设计决策 1：为什么 prompt 字段要求"包含所有必要上下文"？**

因为 Subagent 的上下文窗口从零开始，它看不到 Orchestrator 的任何对话历史。这意味着 Orchestrator 必须在 `prompt` 中"重新交代"所有背景——这是 Context Isolation 的直接代价，也是为什么 Dispatch 要求 Orchestrator 具有良好的信息提炼能力。

### 5.2 动态行为：完整执行时序

```
时间轴 ──────────────────────────────────────────────────────────▶

Orchestrator:  [API Call #1: Plan]
               → LLM 输出 tool_use: Task(A), Task(B), Task(C)
               ↓
               [同时触发 3 个 Subagent]
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
    Subagent A   Subagent B   Subagent C
    [API Call]   [API Call]   [API Call]
    [Bash exec]  [File read]  [Code edit]
    [API Call]   [API Call]   [API Call]
    [完成]        [完成]       [完成]
         │            │            │
         └────────────┼────────────┘
                      ▼
Orchestrator:  [收到 3 个 tool_result]
               [API Call #2: Aggregate]
               → 分析结果、验证、输出最终答案
```

**步骤详解：**

1. **Plan Phase**：Orchestrator 接收用户指令，通过 LLM 推理决定是否需要 Dispatch，以及拆分为几个子任务
2. **Dispatch Phase**：Orchestrator 在单次 LLM 响应中输出多个 `tool_use` 块，每个 `tool_use` 对应一个 Task 调用——这实现了并行触发
3. **Subagent Execution**：每个 Subagent 运行独立的完整 Agent Loop，可能包含多轮 LLM 调用和工具执行
4. **Result Collection**：Subagent 完成后，其最终输出作为 `tool_result` 返回给 Orchestrator
5. **Aggregate Phase**：Orchestrator 基于所有 `tool_result` 进行综合分析，生成用户可见的最终输出

### 5.3 并行机制的 API 层实现

Dispatch 的并行性来源于 Claude API 的 `tool_use` 并行返回特性：

```python
# Orchestrator 的 LLM 响应结构（简化）
response.content = [
    {"type": "text", "text": "I'll handle these three parts in parallel..."},
    {"type": "tool_use", "id": "tu_001", "name": "Task", "input": {"description": "Fix auth module", "prompt": "..."}},
    {"type": "tool_use", "id": "tu_002", "name": "Task", "input": {"description": "Fix payment module", "prompt": "..."}},
    {"type": "tool_use", "id": "tu_003", "name": "Task", "input": {"description": "Fix logging module", "prompt": "..."}},
]
# Claude Code runtime 检测到多个 tool_use，并行调度执行
```

**关键设计决策 2：为什么选择"单次响应多个 tool_use"而不是"多次串行 tool_use"？**

如果串行（每次只 dispatch 一个），总耗时 = T_A + T_B + T_C。
如果并行（单次输出多个），总耗时 = max(T_A, T_B, T_C)。

对于均衡任务（各子任务耗时相近），并行可带来接近 N 倍的加速。代价是 Orchestrator 必须在没有任何子任务结果的情况下完成任务规划——这要求 Orchestrator 的拆分设计足够健壮。

### 5.4 Prompt Caching 与 Dispatch 的协同

Orchestrator 在初始化每个 Subagent 时，通常需要注入大量共享上下文（如代码库结构、项目规范）。Claude Code 利用 `cache_control: ephemeral` 对这部分内容做 Prompt Cache：

```python
# 每个 Subagent 的初始消息结构
messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": "<shared_context>项目背景、代码规范、文件树...</shared_context>",
                "cache_control": {"type": "ephemeral"}  # ← 缓存共享上下文
            },
            {
                "type": "text",
                "text": "<task_specific>具体子任务描述...</task_specific>"
            }
        ]
    }
]
```

**效果**：多个并行 Subagent 共享同一份被缓存的 prefix，Token 处理成本从 O(N × context_size) 降为 O(1 × context_size + N × task_size)。

> ⚠️ 存疑：Prompt Cache 在并行 Subagent 间的 cache hit 率取决于 Anthropic 后端缓存策略，并行请求在不同服务器实例上执行时 cache 可能无法共享。

---

## 6. 高可靠性保障

### 6.1 任务失败处理

Claude Dispatch 本身不内置重试机制，但有以下隐性保障：

- **Subagent 自愈**：单个 Subagent 内部可以在其 Agent Loop 中自主处理错误（如命令失败后重试）
- **Orchestrator 感知**：Subagent 执行失败（或返回错误信息）时，Orchestrator 可在 Aggregate Phase 选择重新 Dispatch 或降级处理
- **Human-in-the-loop**：Claude Code 默认在关键操作（如删除文件、执行破坏性命令）前请求用户确认，这在 Subagent 层面也有效

### 6.2 资源竞争与文件冲突

**最大风险**：多个并行 Subagent 同时写入同一文件，导致覆盖。

**缓解策略**（需 Orchestrator 在设计任务时保证）：
1. 按文件/模块边界拆分任务（最常见也最有效）
2. 对共享资源的任务串行 Dispatch
3. 利用临时文件 + 最终合并（Map-Reduce 模式）

### 6.3 可观测性指标

| 指标 | 含义 | 正常范围 | 异常信号 |
|------|------|---------|---------|
| **Subagent 数量** | 单次 Dispatch 创建的子 Agent 数 | 2-10 个 | > 20 时 token 成本显著上升 |
| **Subagent P99 耗时** | 最慢子任务的执行时间 | < 120s | > 300s 考虑任务拆分是否合理 |
| **Tool 调用轮次（per Subagent）** | 子 Agent 内部循环次数 | 1-15 轮 | > 30 轮可能陷入循环 |
| **总 Token 消耗** | 所有 LLM 调用的 token 之和 | 任务相关 | 超过预算阈值时触发告警 |
| **Cache Hit Rate** | Prompt Cache 命中率 | > 70%（有大量共享上下文时）| < 30% 说明上下文设计有问题 |

---

## 7. 使用实践与故障手册

### 7.1 触发 Dispatch 的典型 Prompt 模式

Claude Code 并不要求用户显式触发 Dispatch，Orchestrator 会自主判断。但用户可以通过 prompt 设计引导：

```bash
# 明确指示并行
claude "请并行地为以下 5 个模块编写单元测试：auth, payment, logging, notification, user"

# 大规模批量任务（隐式触发）
claude "扫描整个 src/ 目录，为所有缺少类型注解的 Python 函数添加类型注解"

# 多阶段复杂任务
claude "先并行分析所有微服务的依赖关系，再汇总生成架构图"
```

### 7.2 故障模式手册

```
【故障 1：子任务结果不完整或截断】
- 现象：Orchestrator 汇总时发现某个 Subagent 的结果只完成了一半
- 根本原因：Subagent 达到 max_tokens 限制，或超出 Subagent 的最大循环轮次
- 预防措施：在 Task prompt 中明确指定任务范围，避免范围过宽；拆分为更细粒度的子任务
- 应急处理：Orchestrator 可检测到不完整结果，重新 Dispatch 处理剩余部分

【故障 2：文件竞争写入导致内容丢失】
- 现象：最终文件内容只有某一个 Subagent 的修改，其余丢失
- 根本原因：多个 Subagent 并行对同一文件执行写操作，后写者覆盖先写者
- 预防措施：任务拆分时按文件/目录边界隔离，确保每个文件只由一个 Subagent 负责
- 应急处理：通过 git diff 恢复丢失内容，重新 Dispatch 丢失部分

【故障 3：Subagent 陷入工具调用死循环】
- 现象：某个 Subagent 持续循环调用同一工具，耗时远超预期，token 消耗异常高
- 根本原因：Subagent 遇到错误但无法自主跳出（如命令持续返回非零退出码），或误判任务完成条件
- 预防措施：Task prompt 中明确设置退出条件，如"如果尝试 3 次仍失败，报告错误并停止"
- 应急处理：Claude Code 支持 Ctrl+C 中断，在 Orchestrator 等待 Subagent 时可强制终止

【故障 4：Orchestrator 任务拆分过细导致成本爆炸】
- 现象：简单任务触发了数十个 Subagent，token 消耗超出预期 10 倍以上
- 根本原因：Orchestrator 对任务的并行化判断过于激进，将本应串行的步骤全部并行化
- 预防措施：在 /CLAUDE.md 中设置约束，如"对于少于 5 个文件的任务，不使用并行 Dispatch"
- 应急处理：通过 ccusage 监控 token 消耗，设置每日预算告警

【故障 5：Context Injection 信息不足导致子任务决策错误】
- 现象：Subagent 执行结果与预期不符，分析发现子任务缺少关键上下文（如项目编码规范）
- 根本原因：Orchestrator 在生成 Task prompt 时，未将必要背景信息注入 Subagent
- 预防措施：在 /CLAUDE.md 中维护项目级共享上下文，Claude Code 会自动将其注入所有 Agent
- 应急处理：重新设计 Task prompt，显式包含关键约束和背景信息
```

### 7.3 边界条件与局限性

1. **Subagent 间无实时通信**：如果子任务 B 依赖子任务 A 的中间结果，必须串行而非并行 Dispatch
2. **上下文大小限制**：每个 Subagent 拥有独立的 200K token 上下文窗口，Orchestrator 通过 prompt 注入的上下文越大，Subagent 可用于推理的"工作空间"越小
3. **文件系统是唯一共享状态**：Subagent 之间唯一的通信机制是文件系统（和网络），无法通过内存共享状态
4. **Orchestrator 的 token 成本叠加**：N 个 Subagent 的执行结果都会返回到 Orchestrator 的上下文，随着 N 增加，Orchestrator 的 API 调用成本线性增长
5. **不支持 Subagent 嵌套 Dispatch（⚠️ 存疑）**：理论上 Subagent 也可以调用 Task 工具（嵌套 Dispatch），但深层嵌套的行为和成本控制复杂，实际使用中罕见

---

## 8. 性能调优指南

### 8.1 性能瓶颈识别

```
瓶颈诊断流程：

总耗时过长
├── ccusage 查看 token 消耗分布
│   ├── 某个 Subagent token 消耗异常高 → 检查是否陷入循环或任务范围过宽
│   └── Orchestrator 消耗高 → 检查 Aggregate Phase 是否处理了过多子任务结果
└── 观察并行度
    ├── Subagent 实际是否并行执行 → 检查 Task 是否在同一 LLM 响应中触发
    └── 并行但仍慢 → 最慢子任务决定总耗时（木桶效应），拆分该子任务
```

### 8.2 调优策略（按优先级排序）

| 优先级 | 策略 | 调优目标 | 验证方法 |
|--------|------|---------|---------|
| P0 | **任务边界隔离**：确保子任务间无共享可变状态 | 消除串行等待，避免合并冲突 | 观察 Subagent 执行是否有等待阻塞 |
| P1 | **Prompt Cache 最大化**：将共享上下文（项目背景、规范）放在 cache-able prefix | 将重复上下文的 token 成本降低 60%-80% | ccusage 中 cache_read_input_tokens 占比 |
| P2 | **子任务粒度均衡**：避免任务规模差异过大（如 1 个超大任务 + 9 个小任务） | Subagent 完成时间标准差 < 20% | 观察各 Subagent 的完成时间分布 |
| P3 | **/CLAUDE.md 约束注入**：在项目级配置中限制 Dispatch 的使用场景 | 避免 Orchestrator 过度并行化 | 对比有无配置时的 token 消耗 |
| P4 | **结果压缩**：在 Task prompt 中要求 Subagent 返回结构化摘要而非原始输出 | 降低 Orchestrator Aggregate Phase 的上下文大小 | 对比 Aggregate 阶段的 input tokens |

### 8.3 调优参数速查

| 配置项 | 位置 | 默认值 | 推荐值 | 调整风险 |
|--------|------|--------|--------|---------|
| `max_tokens`（Subagent 输出） | API 调用参数 | 8192 | 4096-16384（按任务复杂度） | 过小导致截断，过大增加成本 |
| Prompt Cache prefix 大小 | Task prompt 设计 | 无限制 | 1024-4096 tokens | 超过 cache 阈值（约 1024 tokens）才生效 |
| 并行 Subagent 数量 | Orchestrator 决策 | 无限制 | ≤ 10 | 超过 10 时 Orchestrator 汇总成本显著上升 |

---

## 9. 演进方向与未来趋势

### 9.1 结构化通信协议

当前 Subagent 之间只能通过文件系统交换信息，存在明显局限。社区和 Anthropic 内部探索中的方向包括：通过 MCP 协议为 Subagent 提供"消息总线"能力，使 Subagent 间可以通过 MCP Server 发布和订阅结构化消息，而非依赖文件 IO。

**对使用者的影响**：一旦实现，可以支持更复杂的依赖型并行任务（如流水线架构），而不必将所有依赖关系都通过 Orchestrator 中转。

### 9.2 Agent 级资源配额与成本控制

随着 Dispatch 使用规模增大，缺乏细粒度资源控制成为痛点。预期的演进方向：每个 Subagent 可以被分配独立的 token 预算、最大循环轮次、允许使用的工具集合——类似 Kubernetes 的 Resource Quota 机制。

**对使用者的影响**：可以为不同优先级的子任务分配不同的资源等级，在成本和质量之间做精细化权衡。

---

## 10. 面试高频题

```
【基础理解层】（考察概念掌握）

Q：Claude Dispatch 中 Orchestrator 和 Subagent 的主要区别是什么？
A：Orchestrator 是主 Claude 实例，负责任务规划、拆分和结果聚合，它有权调用 Task 工具来创建 Subagent。Subagent 是被 Task 工具触发的独立 Claude 实例，拥有独立的上下文窗口和工具执行权限，专注于执行单一子任务，无法看到 Orchestrator 的对话历史，执行结果以 tool_result 形式返回给 Orchestrator。
考察意图：验证候选人是否理解 Orchestrator-Subagent 的职责分离和上下文隔离机制。

Q：为什么 Subagent 之间不能直接通信？
A：Claude Dispatch 的设计是每个 Subagent 持有独立的上下文窗口，彼此之间没有共享内存。唯一的共享状态是底层文件系统（或通过 MCP 提供的外部服务）。这是一个有意为之的设计权衡：完全隔离可以避免注意力稀释、简化调试和错误追踪，但代价是无法支持需要实时协调的任务模式。
考察意图：验证候选人是否理解隔离设计的 Trade-off，而不只是记住"不能通信"这个结论。

【原理深挖层】（考察内部机制理解）

Q：并行 Dispatch 的实现机制是什么？为什么多个 Task 可以同时执行而不是串行？
A：并行性来源于 Claude API 支持在单次 LLM 响应中返回多个 tool_use 块。当 Orchestrator 的 LLM 推理输出了多个 Task tool_use，Claude Code runtime 检测到这些并行意图后，会同时为每个 Task 启动独立的 Agent Loop，而不是等待前一个完成后再启动下一个。这本质上是 API 层的批量工具调用（parallel tool use）触发了 runtime 层的并发执行。
考察意图：验证候选人能否从 API 消息结构层面解释并行机制，而不仅停留在"并行"这个表面概念。

Q：Prompt Cache 在多 Subagent 场景下如何工作？有什么限制？
A：每个 Subagent 初始化时，如果其 prompt 中的共享 prefix（如项目背景）被标记为 cache_control: ephemeral，Anthropic 后端会尝试复用已缓存的 KV 激活值。在理想情况下，N 个共享同一 prefix 的并行 Subagent，只需对该 prefix 做一次 full prefill，后续 N-1 个请求直接 cache hit，可将重复 token 处理成本降低 60%-80%，延迟也随之下降（cache read 约为 full prefill 的 10% 成本）。限制在于：并行请求可能路由到不同的服务器实例，导致 cache miss；cache 有效期有限（约 5 分钟），长时间任务可能失效。
考察意图：考察候选人对 Prompt Caching 机制和成本优化的深度理解，以及对实际限制的诚实认知。

【生产实战层】（考察工程经验）

Q：在生产中，如何防止并行 Subagent 意外覆盖同一文件？
A：核心是在任务设计阶段建立文件级隔离边界，而不是依赖运行时锁机制（Claude Dispatch 没有提供文件锁）。具体做法：(1) 按模块/目录边界拆分任务，确保每个文件只属于一个 Subagent 的责任范围；(2) 在 Task prompt 中明确列出该 Subagent 可以修改的文件列表；(3) 对于无法避免的共享文件（如配置文件），将其相关修改合并到一个专用 Subagent 中串行处理；(4) 全程在 Git 仓库中操作，便于事后通过 git diff 审计和回滚。
考察意图：验证候选人在真实工程场景中的系统设计能力，以及对并发副作用的工程防御意识。

Q：如何监控和控制 Claude Dispatch 的 token 消耗，防止成本失控？
A：(1) 使用 ccusage 工具实时查看当前会话和历史会话的 token 消耗分布，可按 Subagent 维度分析；(2) 在 /CLAUDE.md 中定义约束规则，如"对少于 3 个文件的任务不使用 Dispatch"，引导 Orchestrator 做更保守的决策；(3) 在 Task prompt 中要求 Subagent 返回压缩后的结构化摘要，减少 Orchestrator Aggregate Phase 的 input tokens；(4) 设置 Claude Code 的每日 API 使用预算告警；(5) 对高频重复任务（如标准化批量处理）进行 Prompt 模板化，最大化 cache hit 率。
考察意图：验证候选人是否有生产环境的成本意识，以及是否理解 Prompt Cache、token 计费、工具链配合的综合优化方法。
```

---

## 11. 文档元信息

### 验证声明

```
本文档内容经过以下验证：
✅ 与 Anthropic Claude Code 官方文档一致性核查：https://docs.anthropic.com/en/docs/claude-code/overview
✅ 与 Anthropic Multi-Agent 架构文档核查：https://docs.anthropic.com/en/docs/build-with-claude/agents
⚠️ 以下内容未经本地环境验证，仅基于文档推断和代理日志分析：
   - 第 5.1 节 Task 工具的 JSON Schema 字段名
   - 第 6.3 节 Prompt Cache 跨实例命中率的具体数值
   - 第 7.3 节关于"不支持 Subagent 嵌套 Dispatch"的说法
```

### 知识边界声明

```
本文档适用范围：Claude Code 1.x，基于 2025 年 Q1 Anthropic 公开架构文档
不适用场景：
  - Anthropic API 直接调用的自定义 Multi-Agent 框架
  - Claude.ai 网页端（不支持 Claude Dispatch 机制）
  - Anthropic 企业版的私有化部署（行为可能不同）
```

### 参考资料

```
官方文档：
  - Claude Code Overview: https://docs.anthropic.com/en/docs/claude-code/overview
  - Building Multi-Agent Systems: https://docs.anthropic.com/en/docs/build-with-claude/agents
  - Prompt Caching: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
  - Tool Use: https://docs.anthropic.com/en/docs/build-with-claude/tool-use

延伸阅读：
  - Anthropic Blog: Introducing Claude Code (2025)
  - ccusage: https://github.com/ryoppippi/ccusage（Claude Code token 消耗分析工具）
  - MCP Protocol Spec: https://modelcontextprotocol.io/specification
```

---
