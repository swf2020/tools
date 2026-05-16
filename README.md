# tools

日常工具集

---

## 1. anylist — Claude Code 通信调试/可观测性代理

拦截 Claude Code 与外部服务的全部通信并记录日志，用于调试和分析。

**三个组件：**

| 文件 | 作用 |
|------|------|
| `claude_code_to_llm_proxy.py` | HTTP 代理：Claude Code ↔ 阿里云 DashScope API，记录每轮请求/响应 |
| `claude_code_to_mcp_server_proxy.py` | stdio 代理：Claude Code ↔ GitNexus MCP，记录 JSON-RPC 报文 |
| `format_log.py` | 日志格式化：把日志中 `\n` 转义序列展开为真实换行 |

**依赖**

```
fastapi==0.109.2
uvicorn==0.27.1
httpx==0.26.0
python-dotenv
```

**使用步骤**

1. 配置 `~/.claude/settings.json`：
   ```json
   "ANTHROPIC_BASE_URL": "http://127.0.0.1:8000",
   "ANTHROPIC_MODEL": "qwen3-coder-next",
   "ANTHROPIC_DEFAULT_SONNET_MODEL": "qwen3-coder-plus",
   "ANTHROPIC_DEFAULT_HAIKU_MODEL": "qwen3.5-plus"
   ```

2. 启动 LLM 代理：
   ```bash
   python claude_code_to_llm_proxy.py
   ```

3. 在项目目录运行 `claude`

4. 所有请求/响应自动记录到 `claude_code_to_llm_proxy.log`

5. 格式化日志（展开转义换行符）：
   ```bash
   python format_log.py claude_code_to_llm_proxy.log
   ```

---

## 2. auto_save_and_publish_csdn_blog — CSDN 博客半自动化发布

基于 Selenium 的自动化脚本，将本地 Markdown 文件批量保存/发布到 CSDN 博客。

**模块结构：**

| 文件 | 职责 |
|------|------|
| `main.py` | 入口，编排整体流程 |
| `browser.py` | Chrome 浏览器管理 |
| `login.py` | CSDN 登录（微信扫码/APP扫码/第三方） |
| `editor.py` | CSDN 编辑器操作（填写标题、内容、标签等） |
| `processor.py` | Markdown 文件扫描与去重 |
| `models.py` | 数据模型定义 |
| `config.py` | 从 `.env` 读取配置 |

**依赖**

```
selenium==4.26.1
python-dotenv
```

**使用方式**

```bash
# 保存为草稿
python -m auto_save_and_publish_csdn_blog.main

# 直接发布
python -m auto_save_and_publish_csdn_blog.main --action publish

# 无头模式
python -m auto_save_and_publish_csdn_blog.main --headless

# 指定 Markdown 文件夹
python -m auto_save_and_publish_csdn_blog.main --folder /path/to/md/files
```

**配置（.env）**

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CSDN_LOGIN_METHOD` | 登录方式 | `WeChatScanCode` |
| `MD_FOLDER` | Markdown 文件目录 | 必填 |
| `DEFAULT_TAGS` | 默认标签（逗号分隔） | 空 |
| `DEFAULT_CATEGORIES` | 默认分类（逗号分隔） | 空 |
| `DEFAULT_COVER_IMG` | 默认封面图路径 | 空 |
| `MAX_FILES_PER_RUN` | 单次最大处理数量 | `5` |
| `HEADLESS` | 是否无头模式 | `false` |

**流程：** 启动浏览器 → 扫码登录 CSDN → 扫描本地 `.md` 文件 → 逐个填入编辑器 → 保存草稿/发布 → 记录已处理文件防止重复

---

## 3. find-job — 中国招聘网站岗位聚合搜索

从 BOSS直聘、猎聘、前程无忧、智联招聘、拉勾等前十招聘网站并行采集岗位信息，清洗去重后输出结构化 Markdown 报告。

**覆盖站点（按岗位类型自动选择）：**

| 岗位类型 | 推荐站点 |
|---------|---------|
| 互联网/技术 | BOSS直聘 + 拉勾 + 猎聘 + 脉脉 |
| 传统行业 | 前程无忧 + 智联招聘 + BOSS直聘 |
| 蓝领/服务 | 58同城 + 赶集网 |
| 全行业 | 全部站点 |

**输出：** `output/YYYY-MM-DD-关键词.md`，包含汇总表格、按来源站点分组、薪资分布、高频技能标签。

**依赖：** 作为 Claude Code Skill 运行，依赖 `web-access` 和 `dispatching-parallel-agents` skill，无需额外 Python 依赖。

**使用方式：** 在 Claude Code 对话中直接描述搜索条件即可触发，例如：
> 帮我找北京 Golang 开发的岗位，薪资 20K 以上

Skill 文件：`find-job/SKILL.md`
