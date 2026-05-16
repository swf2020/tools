# 岗位信息标准字段

每个采集到的岗位须包含以下字段：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `job_name` | string | 是 | 岗位名称（原始） |
| `company` | string | 是 | 公司名称（归一化后） |
| `company_full` | string | 否 | 工商全称 |
| `salary` | string | 是 | 薪资范围，如 "20-35K·15薪" |
| `salary_min` | int | 否 | 最低月薪（K），从 salary 解析 |
| `salary_max` | int | 否 | 最高月薪（K），从 salary 解析 |
| `city` | string | 是 | 工作城市 |
| `district` | string | 否 | 区域/商圈 |
| `experience` | string | 是 | 经验要求，如 "3-5年" |
| `degree` | string | 否 | 学历要求 |
| `skills` | list[string] | 否 | 技能标签 |
| `description` | string | 否 | 职位描述前 200 字摘要 |
| `welfare` | list[string] | 否 | 福利列表 |
| `industry` | string | 否 | 公司行业 |
| `stage` | string | 否 | 融资阶段 |
| `scale` | string | 否 | 公司规模 |
| `publish_date` | string | 是 | 发布日期，格式 YYYY-MM-DD |
| `source` | string | 是 | 来源站点：zhipin/liepin/51job/... |
| `url` | string | 是 | 岗位详情页原始链接 |
| `is_headhunter` | bool | 是 | 是否为猎头/外包发布 |
