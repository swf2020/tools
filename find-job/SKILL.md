---
name: find-job
description: >
  从中国前十招聘网站搜集特定关键词的岗位信息，清洗去重后以结构化 Markdown 呈现。
  当用户提到「找工作」「招聘」「岗位」「求职」「投简历」「看机会」「职位」
  「搜索职位」「招聘网站」等关键词，或明确要求从招聘网站搜索岗位时触发本 skill。
  支持按岗位名、城市、薪资范围、经验要求组合条件搜索。
compatibility: needs web-access, dispatching-parallel-agents
---

# find-job — 中国招聘网站岗位聚合搜索

## 概述

从 BOSS直聘、猎聘、前程无忧、智联招聘、拉勾 等中国前十招聘网站并行搜索岗位信息，
清洗去重后生成结构化 Markdown 报告。依赖 `web-access` skill 的 CDP 浏览器能力绕过反爬，
利用 `dispatching-parallel-agents` 实现多站并行搜索。

## 执行流程

```
用户输入关键词 + 筛选条件
        │
        ▼
┌─ 1. 解析参数 ─────────────────────┐
│  从用户输入提取：关键字/岗位名、     │
│  城市、薪资范围、经验要求           │
│  城市为必填项，若用户未指定则提示：  │
│  请选择目标城市（可多选）：          │
│  1. 深圳  2. 北京  3. 上海          │
│  4. 杭州  5. 广州  6. 成都          │
│  7. 南京  8. 武汉  9. 西安          │
│  10. 苏州  11. 全国（不限）         │
└───────────────────────────────────┘
        │
        ▼
┌─ 2. 选择站点 ─────────────────────┐
│  读取 references/sites.json        │
│  按岗位类型匹配最佳站点组合：        │
│  互联网/技术 → BOSS+拉勾+猎聘       │
│  传统行业 → 51job+智联              │
│  全行业 → 全部可用站点              │
└───────────────────────────────────┘
        │
        ▼
┌─ 3. 并行搜索 ──────────────────────────────┐
│  使用 dispatching-parallel-agents 分派子 Agent │
│  每个站点一个子 Agent，必须加载 web-access skill  │
│  子 Agent 必须先读取 references/sites.json        │
│  获取对应站点的 API/URL 模式和已知陷阱              │
│  优先 CDP 浏览器模式（绕过反爬，携带登录态）        │
│  每站结果保存到 output/YYYY-MM-DD_HHmmss-{site}_results.json │
│  全部合并后写入 output/YYYY-MM-DD_HHmmss-all_raw.json │
└───────────────────────────────────────────────┘
        │
        ▼
┌─ 4. 汇总清洗 ─────────────────────┐
│  运行 scripts/deduplicate.py：     │
│  - 公司名归一化（简称→全称）        │
│  - 岗位名模糊去重（Jaccard + 编辑距离） │
│  - 按发布时间/匹配度排序            │
│  - 输出到 output/YYYY-MM-DD_HHmmss-deduped.json │
└───────────────────────────────────┘
        │
        ▼
┌─ 5. 输出报告 ─────────────────────┐
│  scripts/format_output.py 生成 MD： │
│  - 汇总表格（公司、岗位、薪资、链接） │
│  - 按来源站点分组                   │
│  - 入参：output/YYYY-MM-DD_HHmmss-deduped.json │
│  - 保存到 output/YYYY-MM-DD_HHmmss-关键词.md │
└───────────────────────────────────┘
```

## 站点选择规则

根据用户搜索的岗位类型自动选择站点组合：

| 岗位类型 | 推荐站点 |
|---------|---------|
| 互联网/技术（Golang, Java, AI, 前端...） | BOSS直聘 + 拉勾 + 猎聘 + 脉脉 |
| 传统行业（销售、财务、行政...） | 前程无忧 + 智联招聘 + BOSS直聘 |
| 蓝领/服务（司机、外卖、保洁...） | 58同城 + 赶集网 |
| 全行业（不限） | 全部 10 站 |

默认单次每站点取前 10 条结果，最多 3 页。

## 并行搜索 Agent Prompt 模板

为每个站点派子 Agent 时使用以下模板（替换 `{{}}` 占位符）：

```
你是一个招聘信息采集专家。请在 {{SITE_NAME}} 上搜索岗位。
必须加载 web-access skill 并遵循指引。

**搜索条件：**
- 关键词：{{KEYWORD}}
- 城市：{{CITY}}
- 经验要求：{{EXPERIENCE}}
- 薪资范围：{{SALARY}}

**前置步骤（必须）：**
先用 Read 工具读取 references/sites.json，找到 id="{{SITE_ID}}" 的站点配置，
了解搜索 URL 模式、API 端点、参数映射和已知陷阱。
如有 site-patterns/{{SITE_ID}}.md 也一并读取。

**采集要求：**
- 每个岗位提取完整字段（见 references/job_schema.md）
- 记录来源网站和原始链接
- 仅提取近 90 天内发布的岗位& 30 天招聘方活跃的岗位
- 标注是否为猎头/外包发布
- 提取公司规模（scale）和行业（industry）字段（API 有返回则必须采集）
- 完成后将 JSON 数组写入 `output/YYYY-MM-DD_HHmmss-{{SITE_ID}}_results.json`（时间戳取当前时刻）

**输出格式：**
返回严格 JSON 数组，每元素包含：
{
  "job_name": "岗位名",
  "company": "公司名",
  "salary": "薪资范围",
  "city": "城市",
  "district": "区域",
  "experience": "经验要求",
  "degree": "学历要求",
  "skills": ["标签1","标签2"],
  "description": "职位描述前1000字",
  "publish_date": "YYYY-MM-DD",
  "source": "{{SITE_ID}}",
  "url": "原始链接",
  "is_headhunter": false,
  "scale": "公司规模",
  "industry": "行业"
}
```

## 输出报告格式

### 文件路径

所有输出文件统一使用秒级时间戳命名，防止覆盖：

- 单站原始结果：`output/YYYY-MM-DD_HHmmss-{site}_results.json`
- 合并原始结果：`output/YYYY-MM-DD_HHmmss-all_raw.json`
- 去重后结果：`output/YYYY-MM-DD_HHmmss-deduped.json`
- 最终报告：`output/YYYY-MM-DD_HHmmss-{关键词}.md`

时间戳格式：`YYYY-MM-DD_HHmmss`（如 `2026-05-16_094730`）

### 报告模板

```markdown
# 岗位搜索结果：{关键词}

> 搜索时间：YYYY-MM-DD HH:MM
> 搜索条件：城市={} 经验={} 薪资={}
> 搜索站点：{站点列表}
> 有效结果：N 条（去重后）

---

## 汇总概览

| # | 岗位名称 | 公司 | 薪资 | 城市 | 经验 | 来源 |
|---|---------|------|------|------|------|------|
| 1 | xxx | xxx | xxx | xxx | xxx | xxx |

---

## 按城市分类

### 深圳（N 条）

| # | 岗位名称 | 公司 | 薪资 | 经验 | 来源 |
|---|---------|------|------|------|------|
| 1 | xxx | xxx | xxx | xxx | xxx |

### 上海（N 条）
...

---

## 按公司类型分类

### 互联网大厂（N 条）
...

### AI 独角兽（N 条）
...

### AI 初创（N 条）
...

---

## 按来源站点

### BOSS直聘（N 条）
...

---

## 薪资分布

| 薪资区间 | 岗位数 |
|---------|--------|
| 10-20K | N |
| 20-35K | N |
| 35-50K | N |

---

## 高频技能标签

#技能1 #技能2 #技能3 ...
```

## 注意事项

- 每个子 Agent 在自己的 CDP tab 中独立操作，不干扰其他 Agent
- 搜索失败站点标记为「采集失败」，不阻断其他站点
- CDP curl 命令必须加 `--noproxy '*'` 避免 localhost 请求走代理
- BOSS直聘薪资为 PUA 字体加密，必须通过 API 获取 salaryDesc 明文
- 不采集付费内容
- 单个子 Agent 超时 120 秒，超时标记为「采集超时」
- 单站搜索失败自动重试最多 2 次（每次间隔 5 秒），2 次均失败再标记「采集失败」
