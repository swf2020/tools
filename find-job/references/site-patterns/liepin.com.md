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

### 搜索 URL 参数说明
- `city=050090` — 城市编码（050090=深圳）
- `key=AI%20Agent` — 搜索关键词
- `currentPage=0` — 页码（0-indexed）
- `pageSize=40` — 每页条数（最大40）
- `workYearCode=3$5` — 工作年限范围（$ 分隔）
- `industry=H01$H01` — 行业筛选
- `salaryCode=6` — 薪资范围编码
- `pubTime=30` — 发布时间（天）
- `dq=050090` — 地区编码

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
