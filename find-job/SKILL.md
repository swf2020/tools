---
name: find-job
description: >
  从 BOSS直聘 和 猎聘 搜索 AI Agent / 软件开发相关岗位信息，
  支持按地域、薪资区间、搜索关键字、数量限制、求职类型、工作经验、招聘者活跃时间精确过滤，
  分离猎头和非猎头内容后以结构化 Markdown 呈现。
  当用户提到「找工作」「招聘」「岗位」「求职」「投简历」「看机会」「职位」
  「搜索职位」「招聘网站」等关键词，或明确要求从招聘网站搜索岗位时触发本 skill。
compatibility: needs web-access, dispatching-parallel-agents
---

# find-job — BOSS直聘 + 猎聘 岗位精准搜索

## 概述

从 **BOSS直聘** 和 **猎聘** 两个平台并行搜索岗位信息，严格按用户指定的条件筛选，
去重后**分离猎头和非猎头内容**，生成结构化 Markdown 报告。
依赖 `web-access` skill（CDP 浏览器）和 `dispatching-parallel-agents`（并行搜索）。

## 用户输入参数

执行搜索前，必须从用户输入中提取以下参数。
若参数缺失，主动提示用户补充。

| 参数 | 必填 | 说明 | 可选值 |
|------|------|------|--------|
| `keyword` | 是 | 搜索关键字 | 如 "AI Agent"、"Golang 开发"、"大模型" |
| `city` | 是 | 工作城市（可多选） | 北京/上海/广州/深圳/杭州/成都/南京/武汉/西安/苏州/全国 |
| `salary_range` | 否(默认不限) | 薪资区间 | 不限 / 10-20K / 20-35K / 30-60K / 35-50K / 40-60K / 30K以上 / 40K以上 / 50K+ |
| `job_type` | 否(默认社招) | 求职类型 | 社招 / 校招 / 实习 |
| `experience` | 否(默认不限) | 工作经验 | 应届生 / 1-3年 / 3-5年 / 5-10年 / 10年以上 / 不限 |
| `recruiter_active_days` | 否(默认30) | 招聘者活跃时间 | 7天 / 14天 / 30天 / 60天 |
| `max_results` | 否(默认15) | 每站最大结果数 | 整数，建议 10-30 |

### 参数解析规则

1. 若用户未指定 `city`，提示用户选择城市（展示选项列表）
2. 若用户只给出模糊描述（如 "深圳 AI 岗位 20-35K"），按规则自动拆解：
   - 城市名 → `city`
   - 薪资范围 → `salary_range`
   - 剩余文本 → `keyword`
3. `recruiter_active_days` 和 `max_results` 若未指定，使用默认值

## 执行流程

```
用户输入参数
        │
        ▼
┌─ 1. 解析参数 ─────────────────────────┐
│  从用户输入提取 7 个参数               │
│  缺失必填项（keyword/city）→ 提示补充   │
│  缺失可选项 → 使用默认值                │
└───────────────────────────────────────┘
        │
        ▼
┌─ 2. 并行搜索 ─────────────────────────────────┐
│  使用 dispatching-parallel-agents 分派 2 个子 Agent │
│  - Agent A: BOSS直聘 (zhipin)                    │
│  - Agent B: 猎聘 (liepin)                        │
│  每个子 Agent 先读取 references/sites.json        │
│  获取对应站点的 API/URL 模式和编码映射              │
│  并读取 references/site-patterns/{site}.md        │
│  获取已知陷阱和有效模式                            │
│  优先 CDP 浏览器模式（绕过反爬，携带登录态）        │
│  每个岗位需额外访问详情页提取描述（列表 API 无描述）  │
│  每站结果保存到 output/YYYY-MM-DD_HHmmss-{site}_results.json │
│  全部合并后写入 output/YYYY-MM-DD_HHmmss-all_raw.json │
└──────────────────────────────────────────────────┘
        │
        ▼
┌─ 3. 汇总清洗 ────────────────────────────────┐
│  运行 scripts/deduplicate.py：                 │
│  - 活跃时间过滤（recruiter_active_time ≤ N 天）  │
│  - 公司名归一化（简称→全称）                     │
│  - 岗位名模糊去重（Jaccard + 编辑距离）          │
│  - 猎头/非猎头分流                               │
│  - 输出：                                        │
│    output/YYYY-MM-DD_HHmmss-deduped.json         │
│    output/YYYY-MM-DD_HHmmss-direct.json          │
│    output/YYYY-MM-DD_HHmmss-headhunter.json      │
└────────────────────────────────────────────────┘
        │
        ▼
┌─ 4. 输出报告 ───────────────────────────┐
│  运行 scripts/format_output.py 生成 MD：  │
│  - 非猎头岗位 section（汇总表格+详情卡片） │
│  - 猎头岗位 section（汇总表格+详情卡片）   │
│  - 按城市分类 / 公司类型分类               │
│  - 薪资分布 / 高频技能标签                 │
│  - 每个岗位卡片包含：                      │
│    岗位名称、岗位要求、岗位描述、            │
│    工作地点、招聘者最近活跃时间、            │
│    薪资、经验、学历、公司规模、行业          │
│  - 保存到 output/YYYY-MM-DD_HHmmss-{关键词}.md │
└──────────────────────────────────────────┘
```

## 站点选择

本 skill 专为 AI Agent / 软件开发岗位优化，固定使用 **BOSS直聘 + 猎聘** 组合：

| 站点 | 平台特征 | 优势 |
|------|---------|------|
| BOSS直聘 | 互联网/技术岗位最多，API 明文数据 | 直接 JSON 响应，薪资明文，字段齐全 |
| 猎聘 | 中高端岗位为主，猎头资源丰富 | 薪资范围更广，中大厂岗位多，适合猎头分离 |

不搜索其他站点（前程无忧、拉勾等），除非用户明确要求。

## 并行搜索 Agent Prompt 模板

为每个站点派子 Agent 时使用以下模板（替换 `{{}}` 占位符）：

```
你是一个招聘信息采集专家。请在 {{SITE_NAME}} 上搜索岗位。
必须加载 web-access skill 并遵循指引。

**搜索条件：**
- 关键词：{{KEYWORD}}
- 城市：{{CITY}}（编码：{{CITY_CODE}}）
- 薪资范围：{{SALARY_RANGE}}（编码：{{SALARY_CODE}}）
- 求职类型：{{JOB_TYPE}}（编码：{{JOB_TYPE_CODE}}）
- 经验要求：{{EXPERIENCE}}（编码：{{EXP_CODE}}）
- 招聘者活跃时间：{{ACTIVE_DAYS}}天内
- 每站结果数：{{MAX_RESULTS}}条

**前置步骤（必须）：**
先用 Read 工具读取 references/sites.json，找到 id="{{SITE_ID}}" 的站点配置，
了解搜索 URL 模式、API 端点、参数编码映射和已知陷阱。
再读取 references/site-patterns/{{SITE_ID}}.md 获取有效模式和 CSS 选择器。

**采集要求：**
- 严格按搜索条件过滤，不采集不相关的岗位
- 每个岗位提取完整字段（见 references/job_schema.md），必须包含：
  - `job_name`: 岗位名称
  - `company`: 公司名
  - `salary`: 薪资范围
  - `city`: 城市
  - `district`: 区域
  - `experience`: 经验要求
  - `degree`: 学历要求
  - `skills`: 技能标签列表
  - `description`: 职位描述（前 1000 字）
  - `job_requirements`: 岗位要求（区别于职位描述）
  - `publish_date`: 发布日期
  - `recruiter_active_time`: 招聘者最近活跃时间（如 "今日活跃"、"3天内活跃"）
  - `job_type`: 求职类型（社招/校招/实习）
  - `is_headhunter`: 是否猎头/外包发布
  - `url`: 原始链接
  - `source`: 来源站点 ({{SITE_ID}})
  - `scale`: 公司规模（API 有则必采）
  - `industry`: 行业（API 有则必采）
- 仅提取招聘者 {{ACTIVE_DAYS}} 天内活跃的岗位
- 完成后将 JSON 数组写入 `output/YYYY-MM-DD_HHmmss-{{SITE_ID}}_results.json`（时间戳取当前时刻）

**详情页描述提取（必须）：**
搜索列表 API 不返回职位描述和任职要求。每获取一个岗位后，必须访问其详情页提取描述。
提取方法见 references/site-patterns/{{SITE_ID}}.md 的"详情页职位描述提取" section。
- CDP navigate 到详情页 URL → 等待 ready: complete → eval 提取 document.body.innerText → 解析描述/要求
- 详情页访问间隔 >= 2 秒，避免风控
- 若详情页无法访问，用列表字段（experience + skills + degree）合成 job_requirements 兜底
- description 截取前 1000 字，job_requirements 截取前 500 字

**输出格式：**
返回严格 JSON 数组，每元素包含以上所有字段。
```

## 去重与清洗脚本使用

```bash
# 基本去重（从合并的 all_raw.json）
python3 scripts/deduplicate.py output/YYYY-MM-DD_HHmmss-all_raw.json \
  -o output/YYYY-MM-DD_HHmmss-deduped.json

# 带活跃时间过滤 + 猎头分流
python3 scripts/deduplicate.py output/YYYY-MM-DD_HHmmss-all_raw.json \
  -o output/YYYY-MM-DD_HHmmss-deduped.json \
  --max-active-days 30 \
  --split-headhunter \
  --split-output-dir output/
```

## 报告生成

```bash
python3 scripts/format_output.py output/YYYY-MM-DD_HHmmss-deduped.json \
  --keyword "AI Agent" \
  --city "深圳" \
  --experience "3-5年" \
  --salary "20-35K" \
  --job-type "社招" \
  --active-days "30" \
  --max-results "15"
```

## 输出报告格式

### 文件路径

- 单站原始结果：`output/YYYY-MM-DD_HHmmss-{site}_results.json`
- 合并原始结果：`output/YYYY-MM-DD_HHmmss-all_raw.json`
- 去重后结果：`output/YYYY-MM-DD_HHmmss-deduped.json`
- 非猎头岗位：`output/YYYY-MM-DD_HHmmss-direct.json`
- 猎头岗位：`output/YYYY-MM-DD_HHmmss-headhunter.json`
- 最终报告：`output/YYYY-MM-DD_HHmmss-{关键词}.md`

时间戳格式：`YYYY-MM-DD_HHmmss`（如 `2026-05-24_143000`）

### 报告结构

```markdown
# 岗位搜索结果：{关键词}

> 搜索时间 / 搜索条件 / 站点 / 有效结果

## 非猎头岗位（N 条）
汇总表格 + 每条岗位详情卡片（含活跃时间、岗位要求、求职类型）

## 猎头岗位（M 条）
汇总表格 + 每条岗位详情卡片

## 按城市分类 / 按公司类型分类 / 按来源站点
## 薪资分布 / 高频技能标签
```

### 岗位详情卡片字段

| 字段 | 说明 |
|------|------|
| 薪资 | 明文薪资，如 "20-35K·14薪" |
| 城市 | 工作城市 |
| 区域 | 区域/商圈 |
| 经验 | 经验要求 |
| 学历 | 学历要求 |
| 求职类型 | 社招/校招/实习 |
| 公司规模 | 公司人数规模 |
| 行业 | 所属行业 |
| 技能 | 技能标签列表 |
| 招聘者活跃 | 最近活跃时间 |
| 来源 | 原始链接 |
| 猎头 | 是/否 |
| 岗位要求 | 硬性条件（技能/经验/学历等） |
| 职位描述 | 工作内容摘要 |
```

## 注意事项

- 仅搜索 BOSS直聘 + 猎聘，其他站点除非用户明确要求否则不搜索
- 每个子 Agent 在独立 CDP tab 中操作，互不干扰
- 搜索失败站点标记为「采集失败」，不阻断另一站点
- CDP curl 命令必须加 `--noproxy '*'` 避免 localhost 请求走代理
- BOSS直聘薪资为 PUA 字体加密，必须通过 API 获取 `salaryDesc` 明文
- BOSS直聘 API 返回 `bossOnlineState` + `lastLogin` 共同判定招聘者活跃度
- 猎聘 CSS 类名用动态前缀，务必使用 `[class*="suffix"]` 属性选择器
- 猎聘招聘者活跃时间从卡片 DOM 中 `.recruiter-active-time` 提取
- **搜索列表 API 不返回职位描述**：子 Agent 必须额外访问每个岗位的详情页，从 DOM 提取 description 和 job_requirements
- 不采集付费内容
- 单个子 Agent 超时 120 秒，超时标记为「采集超时」
- 单站搜索失败自动重试最多 2 次（每次间隔 5 秒）
- 去重阈值：公司名相似度 ≥ 0.85 且岗位名相似度 ≥ 0.80 视为重复
- 所有输出文件统一放在 `output/` 目录下，秒级时间戳防止覆盖

### 薪资范围映射策略

BOSS直聘和猎聘的标准薪资筛选器不支持所有自定义区间。处理策略：

| 用户选择 | zhipin API code | liepin approx | 后过滤 |
|---------|----------------|---------------|--------|
| 不限 | 0 | 0 | 否 |
| 10-20K | 404 | ??? | 否 |
| 20-35K | 405 | ??? | 否 |
| 30-60K | **不传（不限）** | **不传** | **是** |
| 35-50K | 406 | ??? | 否 |
| 40-60K | **不传（不限）** | **不传** | **是** |
| 30K以上 | **407（50K+）** | **max available** | **是** |
| 40K以上 | **407（50K+）** | **max available** | **是** |
| 50K+ | 407 | ??? | 否 |

**后过滤逻辑**：API 返回后，在子 Agent 中解析 `salaryDesc` 的数值（取中位数或最小值），
过滤掉不在目标薪资区间内的岗位。例如用户选 30-60K，API 不限薪资拉回全部结果，
子 Agent 只保留 `salary_min >= 30 AND salary_max <= 60` 的岗位。
