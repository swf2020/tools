# Claude Cowork

---

## 0. 定位声明

```
适用版本：Claude Cowork Research Preview（2026 年 1 月 12 日发布，持续迭代中）
运行环境：macOS（Apple Silicon / Intel）、Windows（2026 年 2 月 12 日起支持）
前置知识：了解 AI Agent 基本概念、对 MCP（Model Context Protocol）有初步认知、
         熟悉基本的文件系统操作
不适用范围：本文不覆盖 Claude Code（命令行版本）的深度使用、Anthropic API 编程接口、
           Microsoft Copilot Cowork（微软基于 Claude 构建的 M365 云端版本）
```

---

## 1. 一句话本质

**Cowork 是什么？**

你告诉电脑上的一个 AI 助手"帮我把下载文件夹整理一下"或"把这堆收据截图做成报销表格"，它就会自己规划步骤、读取你的文件、执行操作、最后交付成果——你甚至可以走开去喝杯咖啡，回来时工作已经完成了。

更精确地说：Cowork 是 Anthropic 将其开发者工具 Claude Code 的 Agent 能力"降门槛化"后的桌面产品。它运行在 Claude Desktop 桌面应用中，让非技术用户无需接触终端，就能让 Claude 以"数字同事"的方式自主完成文件处理、文档生成、数据分析等多步骤知识工作任务。

---

## 2. 背景与根本矛盾

### 2.1 历史背景

Cowork 的诞生源于一个"意外发现"：

1. **2024 年 11 月**：Anthropic 发布 Claude Code，一个面向开发者的命令行 AI 编程工具
2. **用户行为偏移**：大量用户将 Claude Code 用于非编程任务——整理文件、做幻灯片、清理邮箱、甚至恢复婚礼照片、监控植物生长、控制烤箱
3. **产品洞察**：Anthropic 工程师 Boris Cherny 指出："这些用例如此多样和令人惊讶，原因是底层的 Claude Agent 是最好的 Agent"
4. **2026 年 1 月 12 日**：Cowork 作为 Research Preview 发布，将 Claude Code 的 Agent 架构包装为面向普通知识工作者的桌面产品
5. **2026 年 1 月 16 日**：从 Max 独占扩展到 Pro 订阅用户
6. **2026 年 2 月 12 日**：Windows 版发布，实现与 macOS 功能完全对等
7. **2026 年 2 月 24 日**：发布企业级更新——Connectors（Google Drive、Gmail、DocuSign、FactSet）、Plugins 生态、私有插件市场

**市场影响**：Cowork 发布后，企业软件股票合计下跌约 2850 亿美元，投资者重新评估了 AI Agent 对传统 SaaS 软件的替代潜力。

### 2.2 根本矛盾（Trade-off）

Cowork 的核心设计在以下对立约束之间取舍：

| 矛盾维度 | 一端 | 另一端 | Cowork 的取舍 |
|----------|------|--------|---------------|
| **自主性 vs 安全性** | Agent 完全自主执行效率最高 | 每步都要人类确认最安全 | VM 隔离 + 文件夹级权限 + 关键操作前确认（HITL），在沙箱边界内自主执行 |
| **能力广度 vs 攻击面** | 连接越多外部工具越有用 | 每多一个连接器都增加攻击面 | 默认禁止网络访问 + 白名单机制 + 每个 Connector 需显式授权 |
| **易用性 vs 可控性** | 面向非技术用户要极简 | 企业需要审计日志和精细管控 | 当前优先易用性（Research Preview），企业功能逐步补齐中 |
| **本地执行 vs 云端协同** | 本地执行保护隐私 | 云端才能跨设备同步 | 选择本地 VM 执行，对话历史仅存本地，⚠️ 跨设备同步尚未实现 |

---

## 3. 核心概念与领域模型

### 3.1 关键术语表

| 概念 | 费曼式定义 | 正式定义 |
|------|-----------|---------|
| **Cowork** | "一个住在你电脑里的数字同事，你给它分配任务和文件夹权限，它就自己干活" | Anthropic Claude Desktop 应用中的 Agent 模式，基于 Claude Code 的 Agent 架构，在本地 VM 中自主执行多步骤知识工作任务 |
| **Agent Loop** | "AI 不只是回答问题，而是像人一样：想计划→做一步→看结果→调整→再做下一步，循环往复直到完成" | Claude 在接收任务后进入的自主规划-执行-反馈-修正循环，是 Cowork 区别于普通聊天的核心机制 |
| **VM 隔离** | "给 AI 一个独立的'小房间'干活，就算它搞砸了也不会影响你的整个电脑" | Cowork 在本地启动一个轻量级 Linux 虚拟机（macOS 使用 Apple Virtualization Framework），所有任务在 VM 内执行，与宿主机隔离 |
| **文件夹权限** | "你选哪个文件夹让 AI 看，它就只能看那个文件夹，别的地方碰不到" | 用户显式授权特定目录挂载到 VM 内，Agent 只能访问被授权的文件路径 |
| **Connectors** | "把 AI 连上你的其他工具（比如 Google Drive、Slack），让它能从那些地方拿信息" | 通过 MCP 协议连接外部服务的标准接口，每个 Connector 提供特定数据源和操作能力 |
| **Skills** | "教 AI 一些特定的'手艺'，比如怎么做 Excel、怎么做 PPT、怎么做 PDF" | Markdown 编写的领域知识文件，Claude 在相关任务中自动激活，指导其遵循特定格式和最佳实践 |
| **Plugins** | "把多种能力打包成一个'工具包'，一键安装就能让 AI 变成某个岗位的专家" | 将 Skills、Commands、Connectors、Sub-agent 定义打包为一个文件级安装包的可组合扩展单元 |
| **HITL** | "在做危险操作前先问你一声'确定要这么做吗？'" | Human-in-the-Loop，Agent 在执行不可逆操作（如删除文件）前强制请求用户确认 |

### 3.2 领域模型

```
┌─────────────────────────────────────────────────────────────────┐
│                    Claude Desktop App                            │
│                                                                  │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐                   │
│   │   Chat   │   │  Cowork  │   │   Code   │  ← 三种模式切换    │
│   └──────────┘   └────┬─────┘   └──────────┘                   │
│                       │                                          │
│              ┌────────▼────────┐                                │
│              │   Task Prompt   │  ← 用户描述任务 + 授权文件夹     │
│              └────────┬────────┘                                │
│                       │                                          │
│   ┌───────────────────▼───────────────────┐                     │
│   │         Master Agent Loop              │                    │
│   │  Plan → Act → Observe → Adjust → ...  │                    │
│   │                                        │                    │
│   │  ┌─────────┐ ┌─────────┐ ┌─────────┐ │                    │
│   │  │Sub-Agent│ │Sub-Agent│ │Sub-Agent│ │ ← 并行子任务        │
│   │  └─────────┘ └─────────┘ └─────────┘ │                    │
│   └───────────────────┬───────────────────┘                     │
│                       │                                          │
│   ╔═══════════════════▼═══════════════════╗                     │
│   ║        VM Isolation Boundary           ║                    │
│   ║  ┌──────────────────────────────────┐ ║                    │
│   ║  │    Guest Linux (Ubuntu 22.04)    │ ║                    │
│   ║  │  ┌────────────────────────────┐  │ ║                    │
│   ║  │  │  bubblewrap + seccomp      │  │ ║  ← 进程级沙箱      │
│   ║  │  │  ┌──────────────────────┐  │  │ ║                    │
│   ║  │  │  │   Claude Code CLI    │  │  │ ║  ← 实际执行引擎    │
│   ║  │  │  └──────────────────────┘  │  │ ║                    │
│   ║  │  └────────────────────────────┘  │ ║                    │
│   ║  └──────────────────────────────────┘ ║                    │
│   ╚═══════════════════════════════════════╝                     │
│                       │                                          │
│   ┌───────────────────┼───────────────────┐                     │
│   │  VirtioFS Mount   │  Network Proxy    │                     │
│   │  (授权文件夹)      │  (白名单域名)      │                     │
│   └───────────────────┴───────────────────┘                     │
│                                                                  │
│   External Integrations:                                         │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐         │
│   │Connectors│ │  Skills  │ │ Plugins  │ │Chrome Ext│         │
│   │(MCP)     │ │(Markdown)│ │(Bundles) │ │(Browser) │         │
│   └──────────┘ └──────────┘ └──────────┘ └──────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

**关键关系说明**：

- **单 VM 多会话**：一个 VM 实例服务于多个 Cowork 会话，每个会话获得独立的隔离 Session（命名风格类似 Docker：`adjective-adjective-scientist`）
- **MCP 透传**：Claude Desktop 上配置的 MCP 服务器通过 SDK 协议动态注入 VM，Agent 在 VM 内可调用外部工具
- **路径翻译**：VM 内路径自动翻译为宿主机路径显示给用户，保持 UX 一致性

---

## 4. 对比与选型决策

### 4.1 Anthropic 产品矩阵内部对比

| 维度 | Claude Chat | Claude Cowork | Claude Code |
|------|-------------|---------------|-------------|
| **目标用户** | 所有人 | 知识工作者（非技术） | 软件开发者 |
| **交互方式** | 对话式问答 | 任务式委派，可离开等待 | 终端命令行 |
| **文件访问** | 仅上传附件 | 本地文件夹直接读写 | 完整文件系统 |
| **执行环境** | 服务端沙箱 | 本地 VM 隔离 | 本地终端（可配沙箱） |
| **自主程度** | 被动响应 | 主动规划+执行+汇报 | 主动规划+执行+汇报 |
| **底层引擎** | Claude API | Claude Code Agent 架构 | Claude Code Agent 架构 |
| **最低订阅** | Free | Pro ($20/月) | Pro ($20/月) |

### 4.2 外部竞品对比

| 维度 | Claude Cowork | OpenAI Operator / GPT Agent | Microsoft Copilot Cowork | Google Gemini Agent |
|------|---------------|----------------------------|--------------------------|---------------------|
| **部署方式** | 本地 VM | 云端 | M365 云端 | 云端 |
| **数据位置** | 本地存储 | OpenAI 服务器 | Microsoft Graph | Google Cloud |
| **文件访问** | 本地文件夹 | 有限 | M365 全数据图谱 | Google Workspace |
| **安全模型** | VM + 文件夹沙箱 | API 级别 | 企业级治理 | Google IAM |
| **插件生态** | MCP + Plugins（开源） | GPT Store | M365 生态 | ⚠️ 存疑 |
| **离线能力** | 部分（需网络调用模型） | 无 | 无 | 无 |
| **定价起点** | $20/月（Pro） | $20/月 | $30/用户/月 | ⚠️ 存疑 |

### 4.3 选型决策

**选 Cowork 的场景**：
- 需要 AI 直接操作本地文件（整理文件夹、批量处理文档、从截图生成表格）
- 重视数据隐私，不希望文件上传到云端
- 团队使用异构工具栈，不被 M365 或 Google Workspace 绑定
- 需要高度可定制的 Agent 行为（通过 Plugins/Skills）

**不选 Cowork 的场景**：
- 已深度绑定 M365 生态 → 考虑 Microsoft Copilot Cowork
- 仅需简单对话式 AI 辅助 → Claude Chat 足够
- 需要企业级审计日志和合规 API → ⚠️ Cowork 当前审计能力有限
- 纯 API 集成需求 → 直接使用 Anthropic API

---

## 5. 工作原理与实现机制

### 5.1 静态结构：安全隔离架构

Cowork 采用**四层纵深防御**架构：

```
第 1 层：VM 硬隔离
├── macOS: Apple Virtualization Framework (VZVirtualMachine)
├── 启动自定义 Linux 根文件系统（Ubuntu 22.04 ARM64）
├── 非 Docker 容器，是真正的虚拟机
└── 意义：即使 Agent 执行出错，爆炸半径限制在 VM 内

第 2 层：进程级沙箱
├── bubblewrap：限制进程可访问的命名空间
├── seccomp BPF：过滤系统调用（阻止 AF_UNIX socket 创建等）
└── 意义：VM 内部的二次约束，防止权限提升

第 3 层：文件系统隔离
├── VirtioFS 挂载：仅用户授权的文件夹被挂载进 VM
├── 默认拒绝：未授权目录不可见
└── 意义：最小权限原则，Agent 只能碰你让它碰的东西

第 4 层：网络隔离
├── 默认禁止所有出站网络
├── 白名单机制：仅允许依赖安装等必要域名
├── 所有流量经宿主机代理路由，可审计
└── 意义：即使 Agent 被 Prompt Injection 攻击，也无法随意外传数据
```

**为什么选 VM 而不是容器？** 这是一个关键设计决策。容器（Docker）与宿主机共享内核，内核漏洞可导致逃逸；VM 提供硬件级隔离边界，安全保证更强。对于一个面向非技术用户、需要在用户个人电脑上运行的 Agent 产品，VM 隔离是更负责任的选择——代价是资源开销略高。

### 5.2 动态行为：Agent Loop 执行流程

```
用户输入任务
    │
    ▼
[1] 任务理解与规划
    ├── 解析用户意图
    ├── 识别所需文件/工具/Connector
    └── 生成执行计划（可能拆分为并行子任务）
    │
    ▼
[2] 向用户展示计划
    ├── 高层次步骤概述
    └── 等待用户确认（或直接执行，取决于操作风险等级）
    │
    ▼
[3] 进入执行循环 ─────────────────────┐
    │                                   │
    ├── 执行一个步骤                     │
    │   ├── 文件读写                     │
    │   ├── 运行脚本（Python/Bash）      │
    │   ├── 调用 Connector（MCP）        │
    │   ├── 使用 Chrome 浏览器           │
    │   └── 调用 Skills（自动激活）       │
    │                                   │
    ├── 观察执行结果                     │
    │                                   │
    ├── 判断：是否需要人类确认？          │
    │   ├── 是（删除文件等不可逆操作）    │
    │   │   └── 暂停，等待用户确认       │
    │   └── 否                           │
    │       └── 继续下一步               │
    │                                   │
    ├── 判断：是否需要调整计划？          │
    │   ├── 是 → 修正计划                │
    │   └── 否 → 继续                    │
    │                                   │
    └── 循环直到任务完成 ────────────────┘
    │
    ▼
[4] 交付结果
    ├── 汇报完成情况
    ├── 展示生成/修改的文件
    └── 保持会话上下文（可追加指令）
```

**并行子代理（Sub-Agent）**：对于复杂任务，Master Agent 会拆分为多个并行工作流。例如"分析 10 份财报并生成对比报告"，可能派出 10 个子代理并行读取，再由 Master Agent 汇总。每个子代理的执行进度对用户可见。

### 5.3 关键设计决策

**决策 1：本地 VM vs 云端执行**

Cowork 选择本地 VM 执行而非云端。这意味着用户文件不离开本机，隐私保护更强。Trade-off 是：对话历史仅存本地，无法跨设备同步；VM 启动和执行受限于本地硬件性能；企业审计日志和合规 API 暂时无法覆盖 Cowork 活动。

**决策 2：沙箱内自主 vs 逐步审批**

传统安全模型对每个操作弹窗确认，但这会导致"审批疲劳"（用户几分钟后就会无脑点"同意"）。Cowork 选择"预先划定边界，边界内自主执行"——通过 VM + 文件夹权限 + 网络白名单定义安全边界，边界内 Agent 无需逐步请求权限。Anthropic 在 Claude Code 文档中明确指出这种"upfront boundary"模式优于"per-action approval"。

**决策 3：Plugin 架构选择文件级（Markdown + JSON）而非代码级**

Plugin 的 Skills 用 Markdown 编写，Commands 用结构化文件定义，不需要编译或构建。这个决策牺牲了执行效率（需要 LLM 理解 Markdown 而非直接运行代码），但换来了：可审计性（任何人都能阅读和审查 Plugin 内容）、可组合性（fork 任何 Plugin 即可定制）、低门槛（会写 README 就会写 Plugin）。

---

## 6. 高可靠性保障

### 6.1 高可用机制

| 机制 | 说明 |
|------|------|
| **VM 持久化** | 单个 VM 实例服务多会话，会话间隔离但 VM 不重复启动 |
| **会话恢复** | Session 目录持久化在 VM 内的 `/sessions/` 路径下 |
| **优雅降级** | 当安全状态不确定时，优先限制能力（禁用网络、限制 Connector）而非崩溃 |

### 6.2 安全风险与缓解

| 风险 | 严重程度 | 缓解措施 |
|------|---------|---------|
| **Prompt Injection** | 高 | Anthropic 明确承认尚未完全解决；依靠模型层抗注入训练 + 使用侧纪律 + 纵深防御 |
| **文件泄露** | 中 | VM 隔离 + 仅授权目录可见 + 网络白名单阻止外传 |
| **Confused Deputy** | 中 | 当 Agent 链式调用多工具时，信任上下文可能转移；目前无系统性建模 |
| **敏感文件误授权** | 中 | 用户教育 + 建议使用专用工作目录而非共享宽目录 |

### 6.3 可观测性

⚠️ **当前限制**：Cowork 的可观测性处于早期阶段。

- **对话历史**：仅存储在本地设备，Anthropic 服务器不保存
- **审计日志**：企业级 audit log、合规 API、数据导出**当前不覆盖** Cowork 活动
- **管理员控制**：可开关 Cowork 功能，但无细粒度操作级审计
- **企业更新（2026.02）**：引入 OpenTelemetry 监控，提供插件使用可见性

### 6.4 SLA 保障

Cowork 当前为 **Research Preview** 状态，Anthropic 未提供正式 SLA 承诺。使用限制通过 5 小时滚动窗口的 token 配额管理：

| 订阅计划 | 每 5 小时约可用消息数 | 备注 |
|---------|---------------------|------|
| Pro ($20/月) | 基础配额 | Cowork 任务消耗速度远高于普通聊天 |
| Max 5x ($100/月) | ~225+ 条 | 5 倍 Pro 配额 |
| Max 20x ($200/月) | ~900+ 条 | 20 倍 Pro 配额 |

---

## 7. 使用实践与故障手册

### 7.1 典型使用方式

#### 场景 1：文件整理

```
Prompt 示例（直接在 Cowork 界面输入）：

Help me organize my Downloads folder.
Scan the contents and propose a plan:
- Categories/folders to create
- How files should be sorted
- Any naming conventions to apply
- Files to flag for review or deletion
Show me the plan before making changes. Only proceed after I approve.
```

**操作**：选择 Cowork 模式 → 授权 Downloads 文件夹 → 输入任务 → 审核计划 → 确认执行

#### 场景 2：收据截图生成报销表

```
授权包含收据照片的文件夹，输入：

This folder contains receipt photos from my business trip.
Please extract the date, vendor, amount, and category from each receipt,
then create an Excel spreadsheet with these columns.
Flag any receipts that are unclear or partially visible.
```

**关键配置建议**：
- 使用**专用工作文件夹**，不要授权包含敏感文件的宽目录
- 对于长时间任务，确保 Desktop 应用保持打开（⚠️ 定时任务仅在应用运行时触发）
- 复杂任务建议使用 Max 计划以避免配额耗尽中断

#### 场景 3：Plugin 安装与使用

```bash
# 在 Cowork 中安装知识工作 Plugin
# 方法 1：通过 claude.com/plugins 浏览并一键安装
# 方法 2：通过命令行（Claude Code 中）
claude plugin marketplace add anthropics/knowledge-work-plugins
claude plugin install sales@knowledge-work-plugins

# 安装后，slash 命令自动可用
# 例如：/sales:call-prep、/data:write-query
```

**Plugin 目录结构**：
```
plugin-name/
├── .claude-plugin/plugin.json   # 清单文件（名称、版本、描述）
├── .mcp.json                    # MCP 工具连接配置
├── commands/                    # Slash 命令（显式调用）
└── skills/                      # 领域知识（自动激活）
```

### 7.2 故障模式手册

```
【任务因配额耗尽中断】
- 现象：长时间运行的 Cowork 任务突然停止，提示 usage limit
- 根本原因：Cowork 任务消耗 token 远高于普通聊天，5 小时滚动窗口配额耗尽
- 预防措施：将大任务拆分为多个小批次；使用 Max 计划获取更高配额
- 应急处理：等待 5 小时窗口重置后继续；或升级到更高配额计划
```

```
【定时任务未执行】
- 现象：设置的定时 Cowork 任务（如每日 7AM 执行）未触发
- 根本原因：定时任务仅在 Claude Desktop 应用打开时运行；
           笔记本休眠/应用关闭时不会触发
- 预防措施：确保执行时段内应用保持运行
- 应急处理：手动触发任务；考虑将关键定时任务安排在工作时间内
```

```
【Prompt Injection 导致意外行为】
- 现象：处理来自外部的文件/邮件/网页内容时，Agent 执行了非预期操作
- 根本原因：不可信内容中嵌入了恶意指令，Agent 无法 100% 区分
- 预防措施：处理不可信内容时限制 Connector 权限；避免同时授予文件写入和网络访问
- 应急处理：立即停止任务；检查被修改的文件；从备份恢复
```

```
【文件被意外删除或覆盖】
- 现象：Cowork 在执行任务时删除或覆盖了重要文件
- 根本原因：指令不够明确，Agent 按自己的理解执行了清理操作
- 预防措施：使用专用工作目录而非包含重要文件的目录；
           在 Prompt 中明确要求"先展示计划再执行"；保持文件备份
- 应急处理：Cowork 默认在永久删除前请求确认，但修改操作可能不会
```

### 7.3 边界条件与局限性

- **5 小时配额窗口**：超过 5 小时的长任务可能在配额重置时被中断
- **仅本地存储**：对话历史不同步到云端，更换设备后无法继续之前的会话
- **企业审计缺失**：audit log、合规 API、数据导出暂不覆盖 Cowork 活动
- **认证方式**：每个用户通过 OAuth 独立连接 MCP 服务器，权限由用户个人控制，企业无法统一管理 scope
- **Prompt Injection 未解决**：Anthropic 明确声明 Agent 安全仍为活跃研究领域
- **硬件依赖**：VM 执行依赖本地 CPU/内存，低配机器可能体验较差

---

## 8. 性能调优指南

### 8.1 配额优化策略

由于 Cowork 没有传统意义的"性能调优参数"（它是一个封闭产品），优化重点在于**配额效率**：

| 策略 | 预期效果 | 说明 |
|------|---------|------|
| **批量处理** | 减少 30-50% 配额消耗 | 将相关任务合并为一个 Cowork 会话，避免重复建立上下文 |
| **分流到 Chat** | 节省配额 | 简单文本处理、问答用普通 Chat，只在需要文件操作时用 Cowork |
| **明确 Prompt** | 减少反复修正 | 指令越清晰，Agent 一次做对的概率越高，消耗的 token 越少 |
| **限制扫描范围** | 减少不必要的文件读取 | 授权尽可能小的文件夹范围 |
| **使用 Skills/Plugins** | 提升输出质量 | 内置 Skills（docx、xlsx、pptx、pdf）已针对格式输出优化 |

### 8.2 Prompt 工程最佳实践

```
✅ 好的 Prompt：
"这个文件夹包含 20 张收据照片。请提取日期、商户名、金额，
 生成一个 Excel 表格。对于无法识别的收据标注'待人工审核'。
 先给我看处理计划，确认后再执行。"

❌ 差的 Prompt：
"帮我处理这些文件"
（缺少预期输出格式、确认流程、异常处理策略）
```

---

## 9. 演进方向与未来趋势

### 9.1 已确认的近期演进

| 方向 | 状态 | 对用户的影响 |
|------|------|-------------|
| **跨设备同步** | Anthropic 已公布计划 | 不同设备间的 Cowork 会话可延续 |
| **更多 Connector** | Google Drive、Gmail 已上线（2026.02）| 工作流覆盖面扩大 |
| **私有插件市场** | 企业版已支持（2026.02）| 企业可分发和管理内部定制 Plugin |
| **审计与合规** | 路线图中 | 企业级部署的关键前提 |

### 9.2 值得关注的趋势

**趋势 1：Agent 平台化 → Plugin 生态竞争**

Cowork 的 Plugin 架构（基于文件的 Markdown + JSON + MCP）正在形成一个开放生态。Anthropic 已开源 15 个起步 Plugin，社区和合作伙伴正在扩展。这类似于早期的 App Store 或 Chrome Extension 生态——未来谁的 Plugin 生态更丰富，谁的 Agent 就更有用。对使用者的影响：现在投入学习 Plugin 定制能力，可以在团队内形成竞争优势。

**趋势 2：Copilot Cowork（微软）的竞合关系**

微软基于 Claude 构建的 Copilot Cowork 在 M365 云端运行，与 Anthropic 的本地 Cowork 形成互补。企业可能出现"本地 Cowork 处理敏感文件 + 云端 Copilot Cowork 处理 M365 协作"的双栈模式。Anthropic 和微软的 $300 亿 Azure 计算协议为这种共存提供了基础。

---

## 10. 面试高频题

```
【基础理解层】（考察概念掌握）

Q：Claude Cowork 和 Claude Chat 的核心区别是什么？
A：Chat 是被动对话模式——你问一句它答一句，无法直接访问你的文件。
   Cowork 是主动 Agent 模式——你描述一个任务目标，它会自主规划步骤、
   读写你授权的本地文件、调用外部工具，循环执行直到任务完成。
   底层引擎不同：Chat 直接调用 Claude API，Cowork 运行的是 Claude Code
   的完整 Agent 架构（在本地 VM 中）。
考察意图：是否理解 Agent 模式与对话模式的本质差异，是否了解 Cowork 的技术基础

Q：Cowork 的 Plugin 系统由哪些组件构成？
A：Plugin 是一个文件级的安装包，包含四个核心组件：
   - Skills（Markdown 文件）：领域知识，Claude 自动激活
   - Commands（Slash 命令）：用户显式触发的结构化工作流
   - Connectors（.mcp.json）：通过 MCP 协议连接外部工具
   - Sub-agents：针对特定任务的专用子代理定义
   所有组件都是 Markdown 和 JSON 文件，无需编译。
考察意图：是否了解 Cowork 的可扩展架构设计
```

```
【原理深挖层】（考察内部机制理解）

Q：为什么 Cowork 选择 VM 隔离而不是 Docker 容器隔离？
A：Docker 容器与宿主机共享内核，内核漏洞可导致容器逃逸。
   VM 提供硬件级隔离边界（macOS 上使用 Apple Virtualization Framework），
   即使 Guest OS 内核被攻破也无法影响宿主机。
   对于一个面向非技术用户、在个人电脑上运行的 Agent 产品，
   VM 提供的安全保证更适合这个信任模型。
   Trade-off 是资源开销更高、启动略慢——但 Cowork 通过单 VM 服务多会话来摊销成本。
考察意图：是否理解容器 vs VM 的安全边界差异，是否能分析产品场景下的安全决策

Q：Cowork 如何处理 Agent 安全中的"审批疲劳"问题？
A：传统方式是逐操作弹窗确认，但用户几分钟后就会无脑点"同意"，
   反而比不弹窗更危险。Cowork 采用"upfront boundary"模式：
   通过 VM 隔离 + 文件夹级权限 + 网络白名单预先划定安全边界，
   边界内 Agent 自主执行无需逐步审批。
   仅在不可逆操作（如永久删除文件）时触发 HITL 确认。
   本质上是把安全从"每步确认"转变为"一次性信任边界设定"。
考察意图：是否理解 Agent 安全 UX 设计的核心权衡
```

```
【生产实战层】（考察工程经验）

Q：如果你负责在团队中推广 Cowork，你会如何设计安全策略？
A：我会按以下步骤设计：
   1. 定义信任边界：为不同部门创建专用工作目录，禁止授权包含凭证/密钥的目录
   2. 网络管控：通过白名单严格控制 Connector 可访问的外部服务
   3. Plugin 管控：使用私有插件市场，所有 Plugin 上线前经安全审查
   4. HITL 流程：对写操作（尤其是连接 CRM/邮件等外部系统的操作）设置强制确认
   5. 监控：利用 OpenTelemetry 集成追踪 Plugin 使用和异常
   6. 渐进推广：先在低风险场景（文件整理、文档生成）试点，
      验证安全后再扩展到涉及外部系统的工作流
   7. 明确风险：向团队坦诚 Prompt Injection 是未解决问题，
      处理不可信内容时限制 Agent 权限
考察意图：是否能将安全架构知识转化为可落地的企业实践方案

Q：Cowork 任务执行被配额限制中断了怎么办？如何优化配额使用？
A：短期应急：等 5 小时窗口重置后继续，或升级到 Max 计划。
   长期优化：
   - 批量合并相关任务到同一会话，避免重复上下文建立
   - 简单任务分流到 Chat 模式
   - Prompt 尽量明确，减少 Agent 反复试错消耗
   - 限制授权文件夹范围，避免 Agent 扫描大量无关文件
   - 将超长任务拆分为多个可恢复的阶段
考察意图：是否有实际使用 Agent 产品的经验和资源管理意识
```

---

## 11. 文档元信息

### 验证声明

```
本文档内容经过以下验证：
✅ 与 Anthropic 官方博客一致性核查：https://claude.com/blog/cowork-research-preview
✅ 与 Anthropic 官方产品页一致性核查：https://claude.com/product/cowork
✅ 架构信息参考独立逆向工程分析（Simon Willison、pvieito.com）
⚠️ 以下内容未经本地环境验证，仅基于文档和社区分析推断：
   - 第 5 章中 VM 内部的 bubblewrap + seccomp 具体配置细节
   - 第 6 章中具体配额数值（Anthropic 未公开精确值，社区测试数据仅供参考）
   - 第 9 章中未来演进方向基于公开声明，具体时间线未确认
```

### 知识边界声明

```
本文档适用范围：
  - Claude Cowork Research Preview（截至 2026 年 3 月）
  - macOS（Apple Silicon / Intel）和 Windows 桌面环境
  - Pro / Max / Team / Enterprise 付费订阅计划

不适用场景：
  - Claude Code 命令行工具的深度使用（虽然底层共享架构）
  - Microsoft Copilot Cowork（微软基于 Claude 的 M365 云端版本）
  - Anthropic API 编程接口
  - Free 计划用户（无 Cowork 访问权限）
```

### 参考资料

```
官方文档：
  - Anthropic 博客 - Introducing Cowork：https://claude.com/blog/cowork-research-preview
  - Cowork 产品页：https://claude.com/product/cowork
  - Plugin 目录：https://claude.com/plugins
  - Anthropic Labs 公告：https://www.anthropic.com/news/introducing-anthropic-labs

核心分析：
  - Simon Willison - First impressions of Claude Cowork：https://simonw.substack.com/p/first-impressions-of-claude-cowork
  - pvieito - Inside Claude Cowork（逆向工程）：https://pvieito.com/2026/01/inside-claude-cowork
  - Micheal Lanham - Claude Cowork Architecture Deep Dive：
    https://medium.com/@Micheal-Lanham/claude-cowork-architecture-how-anthropic-built-a-desktop-agent-that-actually-respects-your-files-cf601325df86

开源资源：
  - Knowledge Work Plugins（GitHub）：https://github.com/anthropics/knowledge-work-plugins
  - Sandbox Runtime（GitHub）：https://github.com/anthropic-experimental/sandbox-runtime

延伸阅读：
  - VentureBeat - Cowork Launch Coverage：https://venturebeat.com/technology/anthropic-launches-cowork-a-claude-desktop-agent-that-works-in-your-files-no
  - TechCrunch - Anthropic's new Cowork tool：https://techcrunch.com/2026/01/12/anthropics-new-cowork-tool-offers-claude-code-without-the-code/
  - CNBC - Anthropic Claude Cowork Enterprise Update：https://www.cnbc.com/2026/02/24/anthropic-claude-cowork-office-worker.html
  - Cowork Security Architecture Analysis：https://claudecn.com/en/blog/claude-cowork-security-architecture/
```

---
> 如有纰漏或者错误，欢迎指正。