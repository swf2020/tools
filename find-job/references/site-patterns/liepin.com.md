---
domain: liepin.com
aliases: [猎聘, Liepin]
updated: 2026-05-16
---

## 平台特征

- SPA 架构，搜索结果为 JS 动态渲染，静态 curl/WebFetch 无法获取职位数据
- CSS 类名使用动态前缀（如 `_40108`）+ 固定后缀（如 `Nrnc3`, `E8PWS`, `hJbMl`），前缀可能随版本迭代变化
- 搜索结果列表页底部有登录/注册弹窗，但不影响列表中已加载的职位卡片数据提取
- 部分猎头发布的职位会隐藏真实公司名，显示为"某深圳互联网上市公司"等模糊描述
- 搜索结果页 URL 采用完整的 query string 参数体系（city, dq, pubTime, currentPage, pageSize, key, workYearCode, industry, salaryCode 等），构造搜索 URL 较为便利
- 需要登录态才能访问完整职位详情页，但列表页在未登录情况下也可能展示基础信息（取决于反爬策略）

## 有效模式

### CDP 浏览器方式（推荐）
- 通过 CDP 直连用户 Chrome，天然携带登录态，是获取数据的首选方式
- 创建新 tab 打开搜索 URL，等待 `ready: complete` 后通过 `/eval` 提取 DOM 数据

### 关键 CSS 选择器（2026-05-16 验证）
| 目标 | 选择器 | 备注 |
|------|--------|------|
| 职位卡片容器 | `.job-card-pc-container` | 稳定，无动态前缀 |
| 职位详情链接 | `a[data-nick="job-detail-job-info"]` | 稳定 |
| 职位标题 | 卡片内第一个 `.ellipsis-1` 的 `title` 属性 | |
| 薪资 | `[class*="E8PWS"]` | 后缀匹配，前缀可能变 |
| 经验/学历 | `[class*="hJbMl"]` | 第1个=经验，第2个=学历 |
| 公司名 | `[class*="K6Y1c"]` | |
| 公司标签 | `[class*="hFeAm"]` 内的 span | 行业/融资/规模 |
| 工作地点 | 标题区域 text 中正则 `/【(.+?)】/` | 更可靠 |
| 招聘者信息 | `[class*="JTQby"]` | |

### 薪资编码映射（2026-05-24）

`salaryCode` 参数对应薪资区间，编码值需 CDP 实测验证：

| salaryCode | 薪资区间 |
|------------|---------|
| `0` | 不限 |
| `?` | 10-20K |
| `?` | 20-35K |
| `?` | 30-60K |
| `?` | 35-50K |
| `?` | 40-60K |
| `?` | 30K以上 |
| `?` | 40K以上 |
| `?` | 50K+ |

> 验证方法：在猎聘搜索页选择不同薪资区间，观察 URL 中 `salaryCode` 参数变化。

### 经验编码映射（2026-05-24）

`workYearCode` 参数格式为 `min$max`（年份范围）：

| workYearCode | 含义 |
|-------------|------|
| `0$1` | 应届生（0-1年） |
| `2$3` | 1-3年 |
| `4$5` | 3-5年 |
| `6$7` | 5-10年 |
| `8$9` | 10年以上 |

### 招聘者活跃时间提取（2026-05-24）

猎聘搜索结果卡片包含招聘者活跃状态，通过 DOM 提取：

```javascript
// 招聘者信息容器 [class*="JTQby"] 内提取
// 活跃标签通常包含文字如 "今日活跃"、"3日内活跃"、"本周活跃"、"本月活跃"
const recruiterInfo = card.querySelector('[class*="JTQby"]');
const activeTime = recruiterInfo?.textContent?.match(/今日活跃|\\d+日内活跃|本周活跃|本月活跃|\\d+天前活跃/)?.[0] || "未知";
```

### 详情页职位描述提取（2026-05-25 实测验证）

**重要：列表页仅含概要信息（薪资/经验/学历/公司等），不包含完整职位描述和任职要求。**
必须进入详情页提取。

详情页 URL 从卡片 `a[data-nick="job-detail-job-info"]` 的 `href` 获取。
详情页结构为"职位介绍" → "岗位职责" section → "任职要求" section。
`document.body.innerText` 可直接提取全文，无需担心 CSS 类名动态前缀问题。

```javascript
// CDP navigate 到详情页 → eval 执行
const text = document.body.innerText;
const lines = text.split('\n').map(l => l.trim()).filter(Boolean);

let description = '';
let jobRequirements = '';

// 找到"职位介绍"或"岗位职责"段落
const jdIdx = lines.findIndex(l => l === '岗位职责' || l === '职位描述');
const reqIdx = lines.findIndex(l => l === '任职要求' || l === '岗位要求');

if (jdIdx !== -1) {
  const stopKws = ['其他信息', '语言要求', '行业要求', '猎聘温馨提示', '工作地址'];
  const endIdx = reqIdx !== -1 ? reqIdx : lines.findIndex((l, i) => i > jdIdx && stopKws.some(kw => l.includes(kw)));
  const limit = endIdx !== -1 ? endIdx : Math.min(lines.length, jdIdx + 30);
  for (let i = jdIdx + 1; i < limit; i++) {
    description += lines[i] + '\n';
  }
}

if (reqIdx !== -1) {
  const stopKws = ['其他信息', '语言要求', '行业要求', '猎聘温馨提示', '工作地址', '职位福利'];
  const endIdx = lines.findIndex((l, i) => i > reqIdx && stopKws.some(kw => l.includes(kw)));
  const limit = endIdx !== -1 ? endIdx : Math.min(lines.length, reqIdx + 20);
  for (let i = reqIdx + 1; i < limit; i++) {
    jobRequirements += lines[i] + '\n';
  }
}

// 兜底：若无详情页数据，从列表卡片字段合成
if (!jobRequirements.trim()) {
  jobRequirements = `经验${jobExperience || '不限'}，学历${jobDegree || '不限'}，技能：${(skills || []).join('、')}`;
}
```

**详情页访问注意事项：**
- 详情页 URL 可能为 `/a/xxxxx.shtml` 或 `/job/xxxxx.shtml` 两种格式
- 部分猎头岗位详情页可能隐藏真实公司名（显示"某深圳互联网上市公司"），属正常现象
- 每次访问间隔 >= 2 秒，避免风控
- 描述文本截取前 1000 字，任职要求截取前 500 字

### 搜索 URL 参数说明
- `city=050090` — 城市编码（050090=深圳）
- `key=AI%20Agent` — 搜索关键词
- `currentPage=0` — 页码（0-indexed）
- `pageSize=40` — 每页条数（最大40）
- `workYearCode=3$5` — 工作年限范围（$ 分隔）
- `industry=H01$H01` — 行业筛选
- `salaryCode=6` — 薪资范围编码（映射见上方表格）
- `pubTime=30` — 发布时间/活跃天数（天）
- `dq=050090` — 地区编码

### pubTime 参数与活跃时间过滤（2026-05-24）

`pubTime` 控制只显示最近 N 天内发布/活跃的职位：

| pubTime | 含义 |
|---------|------|
| `7` | 近7天 |
| `14` | 近14天 |
| `30` | 近30天 |
| `60` | 近60天 |
| 不传 | 不限时间 |

> 注意：`pubTime` 过滤的是职位发布时间，不是招聘者活跃时间。招聘者活跃状态需要从卡片 DOM 中单独提取（见上方提取方法）。

### 翻页
- 修改 URL 中 `currentPage` 参数即可翻页，无需点击翻页按钮
- 分页器显示最大页码（本次搜索约 10 页），可通过分页 DOM 获取总页数

## 已知陷阱

- **动态类名前缀**（2026-05-16）：CSS 类名前缀 `_40108` 随版本变化，务必使用 `[class*="suffix"]` 属性选择器匹配固定后缀，不要硬编码完整类名
- **Shell 转义问题**：通过 curl POST 发送 JS 到 CDP `/eval` 时，单引号/方括号等容易被 shell 解析，推荐将 JS 写入临时文件后 `--data-binary @file` 方式发送
- **反爬风险**：短时间内密集打开大量详情页（如批量 `/new`）可能触发风控，建议适度控制频率
- **公司匿名化**：猎头发布的职位可能隐藏真实公司名，如需确认公司信息需要进入职位详情页查看（需登录）
- **职位详情页格式差异**：不同来源的职位详情页（`/a/xxxxx.shtml` vs `/job/xxxxx.shtml`）HTML 结构可能不同，需注意适配
- **登录墙位置**：搜索结果页底部的登录弹窗在未登录时出现，但滚动触发即可见——数据已在 DOM 中，直接提取即可无需交互
