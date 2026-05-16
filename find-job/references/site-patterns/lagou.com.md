---
domain: lagou.com
aliases: [拉勾, 拉勾网, 拉勾招聘]
updated: 2026-05-16
---
## 平台特征
- Next.js SSR 架构，所有列表数据在 `<script id="__NEXT_DATA__">` JSON 中
- 阿里云 WAF 保护，静态 fetch/curl 返回验证页面，无法绕过
- CDP 浏览器模式（用户 Chrome 携带登录态）可正常访问
- 职位列表使用事件委托（React），卡片无 href，点击触发侧边栏详情弹窗
- 职位详情页 URL 模式：`https://www.lagou.com/wn/jobs/{positionId}.html`

## 有效模式
- **直接提取 SSR 数据**：`document.getElementById("__NEXT_DATA__").textContent` → JSON.parse → `props.pageProps.initData.content.positionResult.result[]` 获取完整结构化职位列表
- **职位详情页**：直接 navigate 到 `/wn/jobs/{positionId}.html` 获取完整 JD
- **分页**：URL 参数 `pn=N`，每页 15 条
- **搜索 URL**：`/wn/jobs?kd={keyword}&city={city}&pn={page}&fromSearch=true`
- 数据字段丰富：positionId, positionName, companyFullName, salary, workYear, education, industryField, financeStage, companySize, skillLables, positionLables, positionAdvantage, encryptId 等
- totalCount 在 `positionResult.totalCount` 中（本次查询 450 条）

## 已知陷阱
- WebFetch/curl 静态层被 WAF 拦截（2026-05-16）
- 页面内 a#openWinPostion 点击打开侧边栏弹窗，不是导航到详情页
- 导航时 URL 参数过多可能被截断，建议直接用 `/wn/jobs?kd=...&pn=N` 简洁参数
- 职位卡片无 `<a href>` 链接，无法直接提取详情页 URL
