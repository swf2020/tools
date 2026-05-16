#!/usr/bin/env python3
"""格式化输出：将 JSON 岗位数据转为 Markdown 报告"""

import json
import sys
from datetime import datetime
from collections import Counter

TEMPLATE = """# 岗位搜索结果：{keyword}

> 搜索时间：{search_time}
> 搜索条件：城市={city}  经验={experience}  薪资={salary}
> 搜索站点：{sites}
> 有效结果：{total} 条（去重后）

---

## 汇总概览

| # | 岗位名称 | 公司 | 薪资 | 城市 | 经验 | 来源 |
|---|---------|------|------|------|------|------|
{overview}

---

## 按来源站点

{by_source}

---

## 薪资分布

{salary_dist}

---

## 高频技能标签

{top_skills}
"""

def format_job_row(i: int, job: dict) -> str:
    return (f"| {i} | {job.get('job_name','')} | {job.get('company','')} "
            f"| {job.get('salary','')} | {job.get('city','')} "
            f"| {job.get('experience','')} | {job.get('source','')} |")

def salary_to_range(salary: str) -> str:
    """将薪资字符串归一化为区间"""
    import re
    m = re.search(r'(\d+)-(\d+)K', salary)
    if m:
        low = int(m.group(1))
        high = int(m.group(2))
        if high <= 20: return "10-20K"
        if high <= 35: return "20-35K"
        if high <= 50: return "35-50K"
        return "50K+"
    return "未知"

def main():
    if len(sys.argv) < 2:
        print("用法: python format_output.py input.json [keyword] [city] [experience] [salary]", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1]) as f:
        jobs = json.load(f)

    keyword = sys.argv[2] if len(sys.argv) > 2 else "岗位"
    city = sys.argv[3] if len(sys.argv) > 3 else "不限"
    experience = sys.argv[4] if len(sys.argv) > 4 else "不限"
    salary = sys.argv[5] if len(sys.argv) > 5 else "不限"

    sites = sorted(set(j.get('source', '') for j in jobs))
    all_skills = []
    for j in jobs:
        all_skills.extend(j.get('skills', []))

    overview = "\n".join(format_job_row(i+1, j) for i, j in enumerate(jobs))

    by_source_parts = []
    for site in sites:
        site_jobs = [j for j in jobs if j.get('source') == site]
        by_source_parts.append(f"### {site}（{len(site_jobs)} 条）\n")
        for j in site_jobs:
            by_source_parts.append(
                f"- **{j.get('job_name','')}** @ {j.get('company','')}  "
                f"{j.get('salary','')} | {j.get('city','')} | "
                f"[链接]({j.get('url','')})"
            )
        by_source_parts.append("")

    salary_counter = Counter(salary_to_range(j.get('salary', '')) for j in jobs)
    salary_dist = "\n".join(f"| {k} | {v} |" for k, v in salary_counter.most_common())

    skill_counter = Counter(all_skills)
    top_skills = " ".join(f"#{s}" for s, _ in skill_counter.most_common(20))

    output = TEMPLATE.format(
        keyword=keyword,
        search_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
        city=city, experience=experience, salary=salary,
        sites=", ".join(sites),
        total=len(jobs),
        overview=overview,
        by_source="\n".join(by_source_parts),
        salary_dist=salary_dist,
        top_skills=top_skills,
    )

    outfile = f"output/{datetime.now().strftime('%Y-%m-%d')}-{keyword}.md"
    with open(outfile, "w") as f:
        f.write(output)

    print(f"报告已生成: {outfile}")
    print(output)

if __name__ == "__main__":
    main()
