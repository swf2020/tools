---
domain: zhipin.com
aliases: [BOSS直聘, 直聘, zhipin]
updated: 2026-05-11
---

## 平台特征

- **薪资字体加密**：页面 DOM 中薪资数字使用 PUA（Private Use Area）自定义字体（`kanzhun-Regular` / `iboss`）混淆，直接读取 `textContent` 得到的是乱码字符（U+E031-U+E038 等）。自定义字体将 PUA 码点映射到形似数字的 glyph，使渲染结果对人眼可见但爬虫无法直接读取
- **API 返回明文数据**：搜索接口 `/wapi/zpgeek/search/joblist.json` 返回完整的 JSON 数据，其中 `salaryDesc` 字段为明文薪资字符串（如 `"30-60K·14薪"`），无需解码字体
- **搜索为宽泛匹配**：搜索关键词并非精确匹配，会返回语义相关的宽泛结果。例如搜索 "AI Agent" 会返回 AI 算法、DevOps、全栈等关联岗位
- **猎头匿名发布**：大量岗位由猎头发布（`proxyJob=1`），公司名称显示为「某XX公司」格式，真实公司信息被隐藏
- **无需登录**：搜索和岗位列表浏览无需登录态即可访问

## URL 结构与路由

### 搜索页

```
https://www.zhipin.com/web/geek/jobs?city={cityCode}&jobType={jobType}&salary={salary}&experience={experience}&query={keyword}
```

### 关键 URL 参数

| 参数 | 含义 | 示例值 |
|------|------|--------|
| `city` | 城市编码 | `101280600`（深圳） |
| `jobType` | 招聘类型 | `1901`（社招） |
| `salary` | 薪资范围 | `406`（35-50K），`405`（20-35K），`404`（10-20K） |
| `experience` | 经验要求 | `105`（3-5年），`104`（1-3年），`103`（应届生） |
| `query` | 搜索关键词 | URL 编码后的关键词 |
| `page` | 页码 | 从 1 开始 |

### 关键 API 端点

```
# 搜索职位列表（GET，返回 JSON）
https://www.zhipin.com/wapi/zpgeek/search/joblist.json?scene=1&query={keyword}&city={cityCode}&experience={exp}&jobType={type}&salary={salary}&page={page}&pageSize={size}

# 职位详情页
https://www.zhipin.com/job_detail/{encryptJobId}.html
```

- API 参数与搜索页 URL 参数一一对应，额外支持 `page` 和 `pageSize`（默认 15）
- API 响应字段：`zpData.jobList[]` 数组，包含 `jobName`、`salaryDesc`、`brandName`、`brandIndustry`、`brandStageName`、`brandScaleName`、`jobLabels`、`cityName`、`areaDistrict`、`businessDistrict`、`skills`、`welfareList` 等
- `zpData.resCount` 为总结果数，`zpData.hasMore` 指示是否有更多页

## 有效模式

### 1. 通过 CDP 浏览器调用搜索 API（2026-05-11）

核心策略：不直接抓 DOM 薪资（会被加密），而是通过 CDP 浏览器在 BOSS直聘页面上下文中调用内部 API，获取明文数据。

```bash
# Step 1: 打开搜索页作为上下文（携带浏览器 Cookie）
curl -s --noproxy '*' "http://localhost:3456/new?url=https://www.zhipin.com/web/geek/jobs?city=101280600&query=AI%20agent&page=1"

# Step 2: 在页面内通过 navigate 访问搜索 API
curl -s --noproxy '*' "http://localhost:3456/navigate?target={TARGET_ID}&url=https://www.zhipin.com/wapi/zpgeek/search/joblist.json?scene=1&query=AI%20agent&city=101280600&page=1&pageSize=10"

# Step 3: 提取 API 响应（明文 JSON）
curl -s --noproxy '*' -X POST "http://localhost:3456/eval?target={TARGET_ID}" \
  -d 'document.body.innerText'
```

### 2. 提取并整理职位信息（2026-05-11）

关键字段映射：

```javascript
jobList.map(j => ({
  title: j.jobName,
  salary: j.salaryDesc,         // 明文！
  company: j.brandName,
  industry: j.brandIndustry,
  stage: j.brandStageName,
  scale: j.brandScaleName,
  experience: j.jobExperience,
  degree: j.jobDegree,
  city: j.cityName,
  district: j.areaDistrict + " " + j.businessDistrict,
  skills: j.skills,
  welfare: j.welfareList,
  isHeadhunter: j.proxyJob === 1,
  url: "https://www.zhipin.com/job_detail/" + j.encryptJobId + ".html"
}))
```

### 3. 提取招聘者活跃时间（2026-05-24）

API 返回两个关键字段，组合判定招聘者活跃度：

```javascript
const activeMap = {
  // bossOnlineState: 1=当前在线, 2=近期活跃, 3=最近来过, 0=未知
  // lastLogin: 最后登录时间字符串，如 "今日活跃"、"3天内活跃"、"本月活跃"
}

jobList.map(j => ({
  isOnline: j.bossOnlineState === 1,       // 当前在线
  lastLogin: j.lastLogin,                   // "今日活跃" / "3天内活跃" / "本月活跃" / "半年前活跃"
  activeTime: j.lastLogin || (j.bossOnlineState === 1 ? "今日活跃" : "未知"),
}))
```

**判定规则：**
- `bossOnlineState=1` → 当天在线 → `recruiter_active_time` = "今日活跃"
- `bossOnlineState=2` + `lastLogin` 含 "3天" → "3天内活跃"
- `bossOnlineState=3` + `lastLogin` 含 "本月" → "本月活跃"
- 其余情况直接取 `lastLogin` 原始值

### 4. 详情页职位描述提取（2026-05-25 实测验证）

**重要：搜索列表 API 不返回 `jobDescription` / `jobRequirement` 字段。**
职位描述和任职要求仅存在于详情页 `https://www.zhipin.com/job_detail/{encryptJobId}.html` 的 DOM 中。

采集流程：搜索 API 获取列表 → 逐个 navigate 到详情页 → eval 提取 `document.body.innerText` → 解析职位描述和任职要求。

```javascript
// 在详情页 eval 执行，从 body.innerText 提取描述和任职要求
const text = document.body.innerText;
const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
const descIdx = lines.findIndex(l => l === '职位描述');

let description = '';
let jobRequirements = '';

if (descIdx !== -1) {
  const stopKws = [
    '公司信息', '工商信息', '工作地址', '公司介绍',
    '职位发布者', '微信扫码', 'Boss', '相似职位',
    '竞争力分析', '认证资质', '人力资源服务'
  ];
  let inRequirements = false;
  for (let i = descIdx + 1; i < lines.length; i++) {
    if (stopKws.some(kw => lines[i].includes(kw))) break;
    if (lines[i] === '任职要求：' || lines[i].startsWith('任职要求')) {
      inRequirements = true;
      continue;
    }
    if (!inRequirements) {
      description += lines[i] + '\n';
    } else {
      jobRequirements += lines[i] + '\n';
    }
  }
}

// 若详情页无数据，用列表字段合成 job_requirements 兜底
if (!jobRequirements.trim()) {
  jobRequirements = `经验${j.jobExperience || '不限'}，学历${j.jobDegree || '不限'}，技能：${(j.skills || []).join('、')}`;
}
```

**详情页访问注意事项：**
- 每次 navigate 到详情页后等待 `ready: complete`，建议间隔 2-3 秒避免风控
- 部分详情页（猎头岗位）可能重定向或无法访问，此时仅使用列表字段
- 描述文本建议截取前 1000 字，避免数据过大

### 5. jobType 编码（2026-05-24）

搜索 API 参数 `jobType` 的取值：

| 编码 | 含义 |
|------|------|
| `1901` | 社招 |
| `1902` | 校招 |
| `1903` | 实习 |

### 6. 获取多页结果（2026-05-11）

通过 `page` 参数翻页，注意控制频率避免触发风控：

```bash
for page in 1 2 3; do
  curl -s --noproxy '*' "http://localhost:3456/navigate?target={TARGET_ID}&url=https://www.zhipin.com/wapi/zpgeek/search/joblist.json?scene=1&query=keyword&city=101280600&page=${page}&pageSize=10"
done
```

## 已知陷阱

- **DOM 薪资不可直接读取**（2026-05-11）：页面渲染层使用 PUA 自定义字体混淆薪资数字，`textContent` 返回的是 `U+E031-U+E038` 区间的乱码字符，无法直接解析为阿拉伯数字。解码需要下载字体文件并解析 cmap 表做 glyph→digit 映射，且每个字体文件的映射可能不同。**正确做法是调用 API 获取 `salaryDesc` 明文**。
- **代理环境变量干扰 CDP 通信**（2026-05-11）：`http_proxy` 环境变量会导致 `localhost:3456` 的 curl 请求经过代理返回 502。所有 CDP curl 命令需加 `--noproxy '*'`
- **API URL 参数在 `new` 中可能被截断**（2026-05-11）：当 API URL 包含多个查询参数时，`/new` 可能只保留第一个参数。可考虑先打开搜索页获取上下文，再通过 `navigate` 到完整 API URL，或使用 `eval` 发起 `fetch` 请求
- **搜索结果宽泛匹配**（2026-05-11）：搜索 "AI Agent" 返回的结果中包含几何算法、DevOps、运动控制等非直接相关的岗位。如需精确筛选，需要额外对结果做关键词过滤
- **猎头岗位公司信息模糊**（2026-05-11）：`proxyJob=1` 的岗位公司名显示为「某XXX公司」，无法获取真实公司名。`brandLogo` 为默认占位图而非真实 logo。这类岗位通常占据搜索结果的相当比例
