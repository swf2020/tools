# OpenCode 技术学习文档

> **层级定位：软件**
> OpenCode 是一个可独立运行的 AI 编程助手软件，属于"软件"层级——它基于 AI 编程 Agent 这一技术方法论实现，是该方法论在终端/IDE 场景的具体可执行产品。

---

## 0. 定位声明

```
适用版本：OpenCode（截至 2026-02 主线版本，GitHub: anomalyco/opencode）
前置知识：熟悉终端/CLI 基本操作；了解 LLM API 的基本概念（Token、Provider、API Key）；
          理解 LSP（Language Server Protocol）有助于深入理解其代码智能功能
不适用范围：本文不覆盖 OpenCode Zen（商业托管模型服务）的私有定价细节；
            不适用于早期 fork 版本（opencode-ai/opencode）的特有 Go TUI 实现；
            不覆盖 IDE 插件（VS Code Extension）的图形界面配置细节
```

---

## 1. 一句话本质

OpenCode 是一个住在你终端里的 AI 编程搭档：你用自然语言告诉它"帮我加一个用户删除后软删除并可恢复的功能"，它会自己读代码、写代码、执行命令，把改动做完交给你审核。它不绑定任何一家 AI 公司，你可以用 Claude、GPT、Gemini，甚至本地模型，切换一行配置搞定。

---

## 2. 背景与根本矛盾

### 历史背景

2024 年底，Anthropic 发布 Claude Code（闭源、仅支持 Claude 模型、$20/月订阅），引爆了 AI 编程 Agent CLI 赛道。开发者社区立刻出现强烈诉求：**完全开源、支持任意模型、无供应商锁定**。

OpenCode 由 SST（Serverless Stack）创始团队（Anomaly Innovations）于 2025 年初发布，主打"Claude Code 的开源平替"。凭借极致的终端 UI 体验（项目团队同时是 terminal.shop 的创建者）和 100% 开源，在 GitHub 迅速积累超过 10 万 Star，月活开发者超过 250 万。

### 根本矛盾（Trade-off）

| 维度 | 矛盾两端 | OpenCode 的取舍 |
|------|---------|----------------|
| **能力 vs 安全** | Agent 自主执行越多越高效，但风险越大 | 提供 `ask/allow/deny` 三级权限；内置 `plan` 只读模式 |
| **灵活性 vs 一致性** | 支持 100+ 模型让用户自由，但各模型能力差异大 | 引入 OpenCode Zen（策划的推荐模型列表）弥补质量一致性 |
| **隐私 vs 协作** | 不存储代码保护隐私，但团队协作需要上下文共享 | 默认不共享 Session；提供手动/自动共享选项，可团队级禁用 |
| **功能丰富 vs 认知负担** | 高度可配置吸引高级用户，但对新手门槛高 | 内置 `build`/`plan` 双 Agent 一键切换（Tab 键）；提供安装脚本零配置启动 |

---

## 3. 核心概念与领域模型

### 关键术语表

| 术语 | 费曼式定义 | 正式定义 |
|------|-----------|---------|
| **Agent** | 能自主决策"下一步做什么"的 AI 工作单元 | 绑定特定系统提示、工具集、权限策略的 LLM 执行单元 |
| **Tool（工具）** | AI 可以调用的"手"：读文件、写文件、跑命令 | 基于 MCP 标准的函数调用接口，AI 通过工具感知和操作环境 |
| **Session** | 一次完整的对话+操作记录 | 持久化到 SQLite 的多轮对话上下文，包含消息历史和工具调用记录 |
| **MCP（Model Context Protocol）** | Anthropic 定义的 AI 工具调用标准接口，相当于 AI 世界的"USB 接口" | 标准化 Agent 与外部工具/数据源交互的协议，OpenCode 完整支持 |
| **ACP（Agent Client Protocol）** | 让不同编辑器都能"插上"同一个 AI 后端的标准协议 | 标准化 AI Agent 与代码编辑器/IDE 通信的协议，支持 JetBrains、Zed、Neovim 等 |
| **LSP（Language Server Protocol）** | 让 AI 看懂代码结构（不只是文本）的协议 | 标准语言服务协议，OpenCode 集成后可获得符号跳转、类型信息等代码智能能力 |
| **Provider** | AI 模型的"供应商"：OpenAI、Anthropic、Google 等 | LLM API 服务提供方，OpenCode 通过 models.dev 统一管理超过 75 个 Provider |
| **Subagent** | 被主 Agent 临时派出去执行特定子任务的 AI 助手 | 由主 Agent 动态实例化的辅助执行单元，用于并行处理或专项任务 |

### 领域模型

```
┌─────────────────────────────────────────────────────────┐
│                        OpenCode                         │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐                  │
│  │  TUI / Web   │    │  IDE Plugin  │  ← 前端客户端     │
│  │  (前端)      │    │  (ACP)       │                  │
│  └──────┬───────┘    └──────┬───────┘                  │
│         │ HTTP/ACP          │                           │
│  ┌──────▼───────────────────▼──────────────────────┐   │
│  │              OpenCode Server（后端）              │   │
│  │                                                  │   │
│  │  ┌────────────┐    ┌────────────────────────┐   │   │
│  │  │  Session   │    │   Agent Orchestrator   │   │   │
│  │  │  Manager  │    │  (build / plan / general│   │   │
│  │  │  (SQLite) │    │   / explorer)           │   │   │
│  │  └────────────┘    └────────────┬───────────┘   │   │
│  │                                  │               │   │
│  │  ┌───────────────────────────────▼────────────┐ │   │
│  │  │              Tool Layer                     │ │   │
│  │  │  edit │ bash │ read │ webfetch │ MCP Server │ │   │
│  │  └───────────────────────────────┬────────────┘ │   │
│  └──────────────────────────────────│───────────────┘   │
│                                     │                    │
│  ┌──────────────────────────────────▼────────────────┐  │
│  │              Provider Layer（LLM 调用）             │  │
│  │  Anthropic │ OpenAI │ Gemini │ Bedrock │ 本地模型   │  │
│  └────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**核心实体关系：**
- 一个 **Session** 包含多轮 **Message**，每轮 Message 可触发多次 **Tool Call**
- 一个 **Agent** = 系统提示 + 工具白名单 + 权限策略 + 模型配置
- **Subagent** 由主 Agent 在执行中动态创建，完成后销毁，结果回传主 Agent
- 所有 Agent 共享同一个 **Provider Layer**，模型切换不影响 Agent 逻辑

---

## 4. 对比与选型决策

### 同类工具横向对比

| 维度 | OpenCode | Claude Code | Cursor | GitHub Copilot CLI |
|------|---------|------------|--------|-------------------|
| **开源** | ✅ 完全开源 | ❌ 闭源 | ❌ 闭源 | ❌ 闭源 |
| **模型支持** | 75+ providers | 仅 Claude | 多模型（闭源集成） | 仅 GPT/Copilot |
| **运行环境** | 终端 TUI + 桌面 + IDE | 终端 CLI | IDE（VS Code fork） | 终端 CLI |
| **隐私** | 不存储代码 | ⚠️ 存疑 | 代码上传服务器 | 微软服务器处理 |
| **Agent 自定义** | 深度可配置（Markdown 定义） | 有限 | 有限 | 无 |
| **MCP 支持** | ✅ 完整 | ✅ 完整 | 部分 | ❌ |
| **离线/本地模型** | ✅（LM Studio / Ollama） | ❌ | 部分 | ❌ |
| **月费用参考** | 按 Token 自付（可$0） | $20/月（订阅） | $20-40/月 | $10/月起 |
| **Windows 支持** | WSL 推荐（原生有限） | ✅ | ✅ | ✅ |

### 选型决策树

```
你的核心诉求是什么？
│
├── 开箱即用、不想折腾配置 → Claude Code 或 Cursor
│
├── 隐私敏感、代码不能上外部服务器
│   └── → OpenCode（本地模型 + 不存储代码架构）
│
├── 需要灵活切换多家模型（成本控制/模型对比）
│   └── → OpenCode
│
├── 深度定制 Agent 工作流、团队级共享
│   └── → OpenCode（Markdown Agent 定义 + Session 共享）
│
├── 重度 IDE 用户（不喜欢终端）
│   └── → Cursor（IDE 优先体验）
│
└── 已有 GitHub Copilot 订阅、只需轻量 CLI
    └── → GitHub Copilot CLI 或 OpenCode（可复用 Copilot Token）
```

### 在技术栈中的角色

OpenCode 定位为**开发侧工具链**的 AI 层，通常与以下技术配合：

- **上游**：Git 仓库、Issue Tracker（GitHub Issues）→ OpenCode 可读取 Issue 自动实现
- **下游**：CI/CD 流水线 → OpenCode 生成的代码进入正常 PR 审核流程
- **平级**：MCP Server（数据库 MCP、Slack MCP 等）→ 扩展 Agent 的环境感知能力
- **替代**：在 GitHub Actions 中以无头模式（`opencode -p "..."`)运行，实现自动化编程任务

---

## 5. 工作原理与实现机制

### 静态结构

OpenCode 采用**客户端/服务端分离架构**（C/S），这是其区别于传统 CLI 工具的关键设计。

**核心组件：**

| 组件 | 技术实现 | 职责 |
|------|---------|------|
| TUI 前端 | TypeScript（Ink/React TUI 框架） | 渲染终端界面、处理键盘输入 |
| HTTP Server | Node.js HTTP | 前后端通信、Web UI 接入 |
| Agent Orchestrator | TypeScript | Agent 生命周期管理、工具调用编排 |
| Tool Executor | TypeScript | 执行 bash/edit/read/webfetch 等工具 |
| Session Store | SQLite（本地） | 持久化对话历史和 Token 统计 |
| Auth Manager | JSON 文件（~/.local/share/opencode/auth.json） | 存储各 Provider 的 API Key |
| MCP Client | MCP 协议实现 | 与外部 MCP Server 通信 |

**关键数据结构选择：**
- **SQLite 存储 Session**：轻量、无需单独部署、支持 SQL 查询历史；代价是不支持跨机器实时同步（需手动共享）
- **JSON 文件存储凭证**：简单透明、用户可直接编辑；代价是安全性依赖文件系统权限（chmod 600）

### 动态行为：一次典型的编程 Agent 执行流程

```
用户输入 "给 /settings 路由添加身份认证"
         │
         ▼
① TUI 将消息发送到 OpenCode Server（HTTP POST）
         │
         ▼
② Agent Orchestrator 将消息 + 对话历史 + 系统提示组装为 LLM 请求
         │
         ▼
③ 发送到 Provider（如 Anthropic API），获取 LLM 响应
         │
         ├── 响应包含 tool_use（如 read_file）
         │         │
         │         ▼
         │    ④ Tool Executor 执行工具调用
         │         │ 权限策略检查（ask/allow/deny）
         │         │ 若需确认 → 暂停，通知 TUI 请求用户审批
         │         │ 审批通过 → 执行工具，结果作为 tool_result 追加到上下文
         │         │
         │         └── 回到步骤③（多轮迭代，直到达到 max_turns 上限）
         │
         └── 响应为纯文本（任务完成）
                   │
                   ▼
         ⑤ TUI 渲染最终回复，Session 写入 SQLite
```

**关键设计决策：**

**决策1：C/S 分离架构（而不是单进程 CLI）**

> 传统 CLI 工具（如早期 Claude Code）是单进程：你关掉终端，一切结束。OpenCode 将后端作为独立 Server 运行（`opencode serve`），TUI 只是其中一个客户端。
>
> 这带来的能力：手机 App 远程控制本机运行的 Agent、VS Code 插件和终端共享同一个 Session、CI/CD 附着到已运行的 Server 避免 MCP 冷启动延迟。
>
> **代价**：架构更复杂；Server 进程需要常驻；本地开发时进程管理增加认知负担。

**决策2：Agent 以 Markdown 文件定义（而不是代码或 YAML）**

> Agent 的系统提示直接写在 `.md` 文件里，文件名即 Agent ID。这让非工程师也能通过编辑文本文件定制 Agent 行为，降低门槛，同时可纳入 Git 版本控制。
>
> **代价**：复杂的条件逻辑（如"当检测到 TypeScript 时使用 strict 模式"）无法在 Markdown 中表达，需要借助 MCP Server 或自定义工具实现。

**决策3：权限系统采用 ask/allow/deny 三级（而不是简单的 Y/N）**

> `ask`：每次执行前询问；`allow`：本 Session 内自动允许；`deny`：禁止执行。这三级让用户可以在"完全受控"和"全自动"之间灵活调整，适应不同场景的风险容忍度。
>
> **代价**：默认配置对新用户来说，可能因频繁弹出确认框影响体验；部分社区用户反映 Agent 默认不询问直接执行命令存在风险（权限配置不当时）。

---

## 6. 高可靠性保障

### 高可用机制

OpenCode 是**单机本地工具**，不存在分布式节点故障问题。其可靠性设计集中在：

- **操作可撤销**：`/undo` 命令可回滚 Agent 做的文件改动，恢复到操作前状态
- **Plan 模式隔离**：`plan` Agent 为只读，无法执行文件写入或 bash 命令，用于高风险变更前的预览
- **Session 持久化**：对话历史写入 SQLite，进程意外崩溃后可恢复上下文
- **`-d` 调试模式**：`opencode -d` 开启详细日志，便于定位 Agent 执行异常

### 可观测性

OpenCode 内置 Token 用量统计，可用以下命令查看：

```bash
# 查看 Session 列表及 Token 消耗
opencode sessions

# 查看 Token 用量和费用统计
opencode sessions stats
```

**关键关注指标：**

| 指标 | 查看方式 | 参考阈值 |
|------|---------|---------|
| 单 Session Token 消耗 | `opencode sessions stats` | 超过 100K Token/Session 时注意上下文窗口接近上限 |
| Agent 迭代轮次 | TUI 底部状态栏 | 超过 `max_turns`（默认值⚠️ 存疑：约 10-20 轮）时 Agent 强制输出文本 |
| 工具调用耗时 | `-d` 模式日志 | MCP Server 冷启动 > 3s 时考虑使用 `opencode serve` 常驻 |

### SLA 保障手段

OpenCode 作为开发侧工具，SLA 主要指"不造成代码损失"：

1. **变更前使用 `plan` 模式**：先用只读 Agent 分析，确认计划后再切 `build` 模式执行
2. **Git 集成**：执行前确保工作区已 `git commit`，利用 Git 作为终极回滚保障
3. **权限策略收紧**：生产代码仓库中将 `bash` 工具设为 `ask`，避免意外执行破坏性命令
4. **自定义 Agent 限制工具范围**：通过 `tools` 配置禁用不需要的工具，最小化攻击面

---

## 7. 使用实践与故障手册

### 7.1 典型使用方式

**安装（推荐方式，macOS/Linux）：**

```bash
# 推荐：Homebrew（始终最新版本）
brew install anomalyco/tap/opencode

# 或：官方安装脚本
curl -fsSL https://opencode.ai/install | bash

# 或：npm（需 Node.js 18+）
npm i -g opencode-ai@latest
```

**初始配置（~/.config/opencode/opencode.json）：**

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "anthropic/claude-sonnet-4-5",
  "autoshare": false,
  "instructions": "你是一个严格遵循项目代码规范的助手，修改前先阅读 CONTRIBUTING.md",
  "permission": {
    "bash": "ask",
    "edit": "ask",
    "webfetch": "allow"
  },
  "mcp": {
    "filesystem": {
      "type": "local",
      "command": "mcp-server-filesystem",
      "args": ["/home/user/projects"]
    }
  }
}
```

**配置项说明：**

| 配置项 | 默认值 | 风险说明 |
|--------|--------|---------|
| `model` | ⚠️ 无默认（需手动配置） | 未配置时无法启动，需先运行 `opencode auth login` |
| `permission.bash` | `ask` | 设为 `allow` 时 Agent 可无确认执行任意 Shell 命令，**高风险** |
| `permission.edit` | `ask` | 设为 `allow` 时 Agent 可无确认修改任意文件 |
| `autoshare` | `false` | 设为 `true` 时 Session 自动上传到 opencode.ai 服务器供分享 |
| `max_tokens` | 模型上限 | 不限制时单次请求可消耗大量 Token，影响成本 |

**非交互模式（脚本/CI 集成）：**

```bash
# 单次提问，输出到 stdout
opencode -p "解释 Go 中 context 的使用方式"

# JSON 格式输出（便于脚本解析）
opencode -p "列出该项目的所有 API 端点" -f json

# 静默模式（无进度动画，适合 CI）
opencode -p "检查代码中的安全漏洞" -q

# 附着到已运行的 Server（避免 MCP 冷启动）
opencode -p "修复 test 失败" --attach
```

### 7.2 故障模式手册

```
【故障1：Agent 无限循环执行工具调用，无法完成任务】
- 现象：TUI 显示 Agent 持续调用工具，消耗大量 Token，无输出文本
- 根本原因：任务描述模糊导致 Agent 无法判断完成条件；或 max_turns 配置过高
- 预防措施：提供清晰的完成标准（"直到所有 Jest 测试通过为止"）；配置合理的 max_turns
- 应急处理：Ctrl+C 中断当前 Agent；使用 /undo 回滚变更；在 opencode.json 中设置 max_turns

【故障2：MCP Server 连接失败，工具调用报错】
- 现象：调用 MCP 工具时报 "connection refused" 或 "spawn error"
- 根本原因：MCP Server 进程未启动；command 路径配置错误；依赖未安装
- 预防措施：MCP Server 命令配置前在终端手动验证可执行；使用绝对路径
- 应急处理：opencode -d 查看详细日志定位具体错误；检查 MCP server 进程是否存活

【故障3：上下文窗口超限（Context Length Exceeded）】
- 现象：长 Session 中 LLM 返回 "context_length_exceeded" 错误
- 根本原因：对话历史 + 文件内容 + 工具输出累积超过模型 Token 上限（如 Claude Sonnet 200K Token）
- 预防措施：定期开启新 Session；使用 @文件 精确引用而非让 Agent 自行搜索
- 应急处理：/new 开启新 Session；在新 Session 开头用 "续上下文：..." 提供关键状态摘要

【故障4：文件被意外修改或删除】
- 现象：Agent 执行后代码不符合预期，甚至删除了错误文件
- 根本原因：权限配置为 allow，Agent 自动执行了破坏性操作
- 预防措施：高价值仓库将 bash/edit 设为 ask；操作前确保 git commit 干净
- 应急处理：opencode /undo 回滚；若已超出 /undo 范围，使用 git checkout 恢复

【故障5：Windows 下 TUI 显示异常或功能缺失】
- 现象：字符乱码、快捷键不响应、部分功能报错
- 根本原因：OpenCode TUI 对 Windows 原生终端（cmd/PowerShell）支持有限
- 预防措施：使用 WSL2 + Windows Terminal 运行 OpenCode
- 应急处理：切换到 WSL 环境；或使用 opencode web 命令通过浏览器访问 Web UI
```

### 7.3 边界条件与局限性

- **大型 Monorepo**：代码库超过 50 万行时，Agent 自主搜索文件效率显著下降，建议使用 `@文件路径` 手动指定上下文，而非依赖 Agent 自行探索
- **二进制文件处理**：OpenCode 的 `read` 工具不能处理图片、PDF、编译产物等二进制文件，需通过 MCP 扩展实现
- **并发 Session**：多个 Session 同时修改同一文件集时，OpenCode 不提供冲突检测，依赖用户通过 Git 管理
- **Token 成本无上限保护**：⚠️ 存疑 OpenCode 本身不提供单 Session Token 用量硬性上限，需通过 Provider 侧（如 AWS Bedrock 预算告警）控制成本
- **Windows 原生支持**：Bun on Windows 的安装支持仍在进行中（截至 2026-02），原生 Windows 体验不如 WSL

---

## 8. 性能调优指南

### 性能瓶颈识别

OpenCode 的性能瓶颈通常来自三层：

1. **LLM API 延迟**（最常见）：网络往返 + 模型推理时间，单次调用 2-30 秒
2. **MCP Server 冷启动**：每次 `-p` 非交互调用都重新启动 MCP Server，可增加 1-5 秒延迟
3. **大文件 Tool 调用**：读取超过 1MB 的单文件时，Token 消耗激增，影响响应速度

### 调优步骤（按优先级）

**优先级1：使用 `opencode serve` 保持 Server 常驻**

```bash
# 后台启动 Server
opencode serve &

# 之后的 -p 调用附着到已运行 Server，跳过 MCP 冷启动
opencode -p "修复 lint 错误" --attach
```
预期收益：MCP 冷启动开销从 1-5s 降为 ~0s。

**优先级2：为不同任务选择合适的模型**

```json
{
  "agents": {
    "plan": { "model": "google/gemini-2.0-flash" },
    "build": { "model": "anthropic/claude-sonnet-4-5" }
  }
}
```
预期收益：`plan` 阶段使用快速模型可节省 60-80% 的计划阶段时间和费用。

**优先级3：精确提供上下文，减少 Agent 搜索轮次**

```
# 低效（Agent 需要多轮搜索）：
"给用户认证加上 JWT 刷新令牌功能"

# 高效（直接指定相关文件）：
"给 @src/auth/jwt.ts 和 @src/routes/auth.ts 加上 JWT 刷新令牌功能，
 参考 @docs/auth-design.md 中的设计规范"
```
预期收益：减少 3-8 轮工具调用，节省 10-40K Token。

### 调优参数速查表

| 参数 | 位置 | 默认值 | 推荐值 | 调整风险 |
|------|------|--------|--------|---------|
| `max_turns` | agent 配置 | ⚠️ 存疑（约 20） | 10-15（复杂任务） | 过低导致任务提前终止 |
| `temperature` | agent 配置 | 模型默认（通常 0） | 0（编程任务）/ 0.3（文档任务） | 过高导致代码不稳定 |
| `permission.bash` | opencode.json | `ask` | `ask`（生产）/ `allow`（实验） | `allow` 存在安全风险 |
| MCP `timeout` | mcp server 配置 | ⚠️ 存疑 | 10000ms | 过低导致 MCP 工具频繁超时 |

---

## 9. 演进方向与未来趋势

### 趋势1：ACP（Agent Client Protocol）标准化

OpenCode 正积极推进 ACP 作为 AI Agent 与编辑器通信的开放标准，已支持 JetBrains、Zed、Neovim、Emacs，Eclipse 支持开发中。

**对使用者的影响**：一套 OpenCode 配置（Agent 定义、MCP Server、权限策略）将可跨所有支持 ACP 的编辑器复用，彻底消除工具链碎片化问题。

### 趋势2：移动端 / 远程驱动架构成熟

C/S 分离架构已为移动端控制铺好基础，官方提到"手机 App 远程驱动本机 Agent"的路线图方向。这将使开发者可以在手机上审批 Agent 的高风险操作，真正实现"随时随地编程"。

**对使用者的影响**：未来可能出现 OpenCode 官方移动 App，或第三方基于 HTTP API 的控制端；企业场景下可部署 OpenCode Server 作为共享编程基础设施。

---

## 10. 面试高频题

```
【基础理解层】（考察概念掌握）

Q：OpenCode 和 Claude Code 的核心区别是什么？
A：OpenCode 是完全开源、支持 75+ 模型 Provider、采用 C/S 架构的 AI 编程 Agent；
   Claude Code 是 Anthropic 的闭源产品，仅支持 Claude 模型。OpenCode 的核心价值主张是
   无供应商锁定、隐私优先（不存储代码）、高度可定制（Markdown 定义 Agent）。
考察意图：判断候选人是否了解 AI 编程工具市场格局，以及开源 vs 闭源在实际工程中的取舍考量。

【基础理解层】

Q：OpenCode 的 build 和 plan 两种 Agent 模式有什么区别？何时应该用 plan？
A：build 是默认的全权限 Agent，可读写文件、执行 bash 命令；plan 是只读 Agent，只能分析代码
   和生成计划，无法修改文件。在处理核心业务逻辑变更、重构、或任何高风险改动前，应先用 plan
   模式确认 Agent 的执行思路，降低因 AI 误解需求导致大范围错误修改的风险。
考察意图：考察候选人对 AI Agent 安全边界的意识，以及在生产环境中使用 AI 工具的风险意识。

【原理深挖层】（考察内部机制理解）

Q：OpenCode 为什么采用 C/S 分离架构？这个设计带来了哪些能力？
A：传统单进程 CLI 工具与 TUI 生命周期绑定，关闭终端即结束。C/S 分离后，后端 Server 独立
   运行，TUI 只是其中一个客户端。这带来：(1) IDE 插件和终端可共享同一 Session；(2) CI/CD
   可附着到已运行 Server 复用 MCP 连接，避免冷启动开销；(3) 未来支持移动端远程控制。
   代价是本地开发需要管理额外的 Server 进程，架构复杂度上升。
考察意图：考察候选人能否从架构层面分析工具设计的取舍，而不只是停留在功能使用层面。

【原理深挖层】

Q：OpenCode 的权限系统（ask/allow/deny）是如何工作的？为什么不直接用 Y/N？
A：OpenCode 在每次 Tool 调用前检查权限策略：ask 暂停执行并通过 TUI 请求用户审批；allow 
   在 Session 范围内自动批准；deny 永远拒绝。三级设计的意义在于：编程任务需要多次调用同类
   工具（如反复读写文件），每次都弹 Y/N 会严重打断工作流；但对高风险操作（bash 执行任意命令）
   需要保留人工介入点。三级允许用户对不同工具类型设置不同粒度的信任级别。
考察意图：考察候选人对人机协作中安全与效率平衡的理解。

【生产实战层】（考察工程经验）

Q：在 CI/CD 流水线中集成 OpenCode 有哪些注意事项？
A：(1) 使用非交互模式 `opencode -p "..." -q -f json`，配合 `--attach` 复用已运行 Server
   减少冷启动；(2) 权限配置：CI 环境中 bash/edit 建议设为 allow（无人值守），但必须通过
   Git 保护分支规则作为安全兜底；(3) Token 成本控制：在 Provider 侧（如 Anthropic Console）
   设置用量告警，OpenCode 自身不提供硬性 Token 预算限制；(4) 敏感信息：确保 API Key 通过
   CI Secret 注入，而非写入 opencode.json 明文配置文件。
考察意图：考察候选人是否有将 AI 工具融入工程化工作流的实战经验，以及安全意识。

【生产实战层】

Q：团队共同使用 OpenCode 时，如何管理 Agent 配置的一致性？
A：(1) 将项目级 Agent 定义（`.opencode/agents/*.md`）和 `opencode.json` 纳入 Git 版本控制；
   (2) 在 `.opencode/opencode.json` 中定义团队共享的 MCP Server 配置和权限策略基线；
   (3) 个人偏好（模型选择、个人 API Key）放在全局配置 `~/.config/opencode/opencode.json`，
   不进入代码仓库；(4) 通过 CI 验证 Agent 配置文件语法正确性（`opencode agent list --validate`
   ⚠️ 存疑：该命令是否存在需核实）。
考察意图：考察候选人在团队协作场景下对 AI 工具工程化管理的实践经验。
```

---

## 11. 文档元信息

### 验证声明

```
本文档内容经过以下验证：
✅ 与官方文档一致性核查：https://opencode.ai/docs/
✅ GitHub 仓库信息核查：https://github.com/sst/opencode（anomalyco/opencode）
✅ 社区报道参考：InfoQ 2026-02 报道

⚠️ 以下内容未经本地环境验证，仅基于文档推断：
- 第8节 max_turns 的默认值（标注了 ⚠️ 存疑）
- 第8节 MCP timeout 的默认值
- 第7.3节 Token 用量硬限制的缺失（需实际测试确认）
- 第10节面试题中 `opencode agent list --validate` 命令是否存在
```

### 知识边界声明

```
本文档适用范围：OpenCode 主线版本（anomalyco/opencode），截至 2026-02-28
不适用场景：
- opencode-ai/opencode（独立的 Go 语言实现，架构不同）
- OpenCode Zen 商业托管服务的私有定价和 SLA
- OpenCode 桌面 App 和 VS Code Extension 的 GUI 特有功能
- 通过 OpenRouter 或 LM Studio 接入本地模型的具体配置细节
```

### 参考资料

```
官方文档：
- OpenCode 官方文档：https://opencode.ai/docs/
- GitHub 仓库：https://github.com/sst/opencode
- CLI 命令参考：https://opencode.ai/docs/cli/
- Agent 配置文档：https://opencode.ai/docs/agents/

社区资源：
- Awesome OpenCode（插件/主题/Agent 生态）：https://github.com/awesome-opencode/awesome-opencode
- InfoQ 技术报道（2026-02）：https://www.infoq.com/news/2026/02/opencode-coding-agent/
- KDnuggets 工具对比：https://www.kdnuggets.com/top-5-agentic-coding-cli-tools

延伸阅读：
- MCP 协议规范：https://modelcontextprotocol.io/
- ACP 协议（Agent Client Protocol）：关注 OpenCode 官方博客更新
```

---

## 输出质量自检清单

- [x] 每个核心概念是否提供了费曼式无术语解释？→ 已在术语表中每条提供费曼式定义
- [x] 每个设计决策是否说明了 Trade-off 而不只是结论？→ 第2节根本矛盾表格、第5节三个关键设计决策均含 Trade-off 分析
- [x] 代码示例是否注明了可运行的版本环境？→ 安装命令注明 Node.js 18+；配置示例附有运行方式说明
- [x] 性能数据是否给出了具体数值而非模糊描述？→ MCP 冷启动 1-5s、大文件 Token 超过 1MB 等均给出量化范围
- [x] 不确定内容是否标注了 `⚠️ 存疑`？→ max_turns 默认值、Token 硬限制等均已标注
- [x] 文档元信息（验证声明、边界、参考资料）是否完整？→ 第11节已完整覆盖
