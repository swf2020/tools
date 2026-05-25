#!/usr/bin/env python3
"""格式化输出：将 JSON 岗位数据转为 Markdown 报告，猎头/非猎头分开展示"""

import json
import sys
import re
from datetime import datetime
from collections import Counter, defaultdict

TEMPLATE = """# 岗位搜索结果：{keyword}

> **搜索时间**：{search_time}
> **搜索条件**：城市={city}  |  经验={experience}  |  薪资={salary}  |  求职类型={job_type}  |  活跃时间={active_days}天内  |  数量限制={max_results}条/站
> **搜索站点**：{sites}
> **有效结果**：{total} 条（去重后，非猎头 {direct_count} 条 + 猎头 {hh_count} 条）

---

## 非猎头岗位（{direct_count} 条）

{direct_section}

---

## 猎头岗位（{hh_count} 条）

{hh_section}

---

## 按城市分类

{by_city}

---

## 按公司类型分类

{by_company_type}

---

## 按来源站点

{by_source}

---

## 薪资分布

| 薪资区间 | 岗位数 |
|---------|--------|
{salary_dist}

---

## 高频技能标签

{top_skills}
"""

# ── 已知公司分类字典 ───────────────────────────────────────────
KNOWN_COMPANIES = {
    # 互联网大厂
    "字节跳动": "互联网大厂", "京东": "互联网大厂", "京东科技集团": "互联网大厂",
    "小红书": "互联网大厂", "小红书科技": "互联网大厂", "腾讯": "互联网大厂",
    "腾讯科技": "互联网大厂", "阿里巴巴": "互联网大厂", "阿里": "互联网大厂",
    "百度": "互联网大厂", "美团": "互联网大厂", "快手": "互联网大厂",
    "快手科技": "互联网大厂", "拼多多": "互联网大厂", "网易": "互联网大厂",
    "网易集团": "互联网大厂", "滴滴": "互联网大厂", "滴滴出行": "互联网大厂",
    "蚂蚁集团": "互联网大厂", "华为": "互联网大厂", "华为技术": "互联网大厂",
    "小米": "互联网大厂", "小米科技": "互联网大厂", "三六零": "互联网大厂",
    "360": "互联网大厂", "奇虎360": "互联网大厂", "搜狐": "互联网大厂",
    "新浪": "互联网大厂", "微博": "互联网大厂", "携程": "互联网大厂",
    "哔哩哔哩": "互联网大厂", "bilibili": "互联网大厂", "B站": "互联网大厂",
    "知乎": "互联网大厂", "唯品会": "互联网大厂", "得物": "互联网大厂",
    "米哈游": "互联网大厂", "三七互娱": "互联网大厂",
    # AI 独角兽
    "智谱": "AI 独角兽", "智谱AI": "AI 独角兽", "智谱华章": "AI 独角兽",
    "月之暗面": "AI 独角兽", "Moonshot": "AI 独角兽", "Minimax": "AI 独角兽",
    "稀宇科技": "AI 独角兽", "百川智能": "AI 独角兽", "零一万物": "AI 独角兽",
    "阶跃星辰": "AI 独角兽", "面壁智能": "AI 独角兽", "昆仑万维": "AI 独角兽",
    "深势科技": "AI 独角兽", "第四范式": "AI 独角兽", "旷视科技": "AI 独角兽",
    "商汤科技": "AI 独角兽", "云从科技": "AI 独角兽", "依图科技": "AI 独角兽",
    "思必驰": "AI 独角兽", "云知声": "AI 独角兽", "DeepSeek": "AI 独角兽",
    "深度求索": "AI 独角兽", "元象": "AI 独角兽", "元象科技": "AI 独角兽",
    "澜舟科技": "AI 独角兽", "生数科技": "AI 独角兽", "爱诗科技": "AI 独角兽",
    "无问芯穹": "AI 独角兽", "硅基流动": "AI 独角兽", "趋境科技": "AI 独角兽",
    "潞晨科技": "AI 独角兽", "RWKV": "AI 独角兽", "元始智能": "AI 独角兽",
    # AI 初创
    "AfterShip": "AI 初创", "成都中科青芸智能科技有限公司": "AI 初创",
    "泰迪科技": "AI 初创", "意恒智能科技": "AI 初创",
    "广州市九重天信息科技有限公司": "AI 初创",
    # 机器人初创
    "杰能科世": "机器人初创", "大疆": "机器人初创", "大疆创新": "机器人初创",
    "优必选": "机器人初创", "宇树科技": "机器人初创", "智元机器人": "机器人初创",
    "傅利叶智能": "机器人初创", "追觅科技": "机器人初创", "云鲸": "机器人初创",
    "石头科技": "机器人初创", "科沃斯": "机器人初创",
    # 新能源汽车
    "上汽云计算中心": "新能源汽车", "上汽": "新能源汽车", "上汽集团": "新能源汽车",
    "普华基础软件": "新能源汽车", "比亚迪": "新能源汽车", "比亚迪股份": "新能源汽车",
    "蔚来": "新能源汽车", "蔚来汽车": "新能源汽车", "小鹏": "新能源汽车",
    "小鹏汽车": "新能源汽车", "理想汽车": "新能源汽车", "理想": "新能源汽车",
    "吉利": "新能源汽车", "吉利控股": "新能源汽车", "长安汽车": "新能源汽车",
    "特斯拉": "新能源汽车", "Tesla": "新能源汽车", "小米汽车": "新能源汽车",
    "赛力斯": "新能源汽车", "问界": "新能源汽车", "极氪": "新能源汽车",
    "零跑汽车": "新能源汽车",
    # ICT/云计算
    "华为云": "ICT/云计算", "深信服": "ICT/云计算", "深信服科技": "ICT/云计算",
    "新华三": "ICT/云计算", "新华三技术": "ICT/云计算", "浪潮": "ICT/云计算",
    "浪潮集团": "ICT/云计算", "中兴": "ICT/云计算", "中兴通讯": "ICT/云计算",
    "奇安信": "ICT/云计算", "启明星辰": "ICT/云计算", "天融信": "ICT/云计算",
    # 芯片/半导体
    "格科微电子（上海）有限公司": "芯片/半导体", "格科微": "芯片/半导体",
    "中芯国际": "芯片/半导体", "海思": "芯片/半导体", "寒武纪": "芯片/半导体",
    "地平线": "芯片/半导体", "地平线机器人": "芯片/半导体",
    "黑芝麻": "芯片/半导体", "黑芝麻智能": "芯片/半导体", "兆易创新": "芯片/半导体",
    "韦尔股份": "芯片/半导体", "紫光展锐": "芯片/半导体", "壁仞科技": "芯片/半导体",
    "摩尔线程": "芯片/半导体", "燧原科技": "芯片/半导体",
    # 工业制造
    "广东弗我智能制造有限公司": "工业制造", "扬子纺纱": "工业制造", "精丽": "工业制造",
    # 医药/生物
    "药明生物": "医药/生物", "药明康德": "医药/生物", "华大基因": "医药/生物",
    "百济神州": "医药/生物",
    # 金融/数据服务
    "企查查": "金融/数据服务", "企查查科技": "金融/数据服务",
    "上海邓白氏商业信息咨询有限公司": "金融/数据服务", "邓白氏": "金融/数据服务",
    "友邦资讯科技(广州)有限公司": "金融/数据服务", "友邦资讯": "金融/数据服务",
    "蚂蚁": "金融/数据服务", "微众银行": "金融/数据服务",
    "蚂蚁金服": "金融/数据服务", "众安保险": "金融/数据服务",
    "陆金所": "金融/数据服务", "万得": "金融/数据服务", "Wind": "金融/数据服务",
    # 电商/消费
    "奥尼电子": "电商/消费", "深圳押呗优品互联": "电商/消费",
    "SheIn": "电商/消费", "SHEIN": "电商/消费", "盒马": "电商/消费",
    # 游戏/娱乐
    "米哈游": "游戏/娱乐", "莉莉丝": "游戏/娱乐", "叠纸": "游戏/娱乐",
    "鹰角": "游戏/娱乐", "腾讯游戏": "游戏/娱乐", "网易游戏": "游戏/娱乐",
    "完美世界": "游戏/娱乐", "三七互娱": "游戏/娱乐",
    # 物流/供应链
    "顺丰": "物流/供应链", "京东物流": "物流/供应链", "菜鸟": "物流/供应链",
    "货拉拉": "物流/供应链", "满帮": "物流/供应链",
    # 教育/培训
    "好未来": "教育/培训", "猿辅导": "教育/培训", "作业帮": "教育/培训",
    "新东方": "教育/培训", "高途": "教育/培训", "网易有道": "教育/培训",
    # 咨询/服务
    "埃森哲": "咨询/服务", "德勤": "咨询/服务", "普华永道": "咨询/服务",
    "毕马威": "咨询/服务", "安永": "咨询/服务", "麦肯锡": "咨询/服务",
    "波士顿咨询": "咨询/服务", "贝恩": "咨询/服务",
}

HEADHUNTER_HINTS = [
    (r"互联网", "互联网大厂"),
    (r"AI|人工智能|智能(?!座舱|驾驶)", "AI 初创"),
    (r"机器人|具身智能", "机器人初创"),
    (r"新能源|智能驾驶|智能座舱|车联网|汽车", "新能源汽车"),
    (r"芯片|半导体|IC|集成电路", "芯片/半导体"),
    (r"云计算|云服务|ICT|通信", "ICT/云计算"),
    (r"制造|工业|自动化", "工业制造"),
    (r"医药|生物|制药|CRO|医疗", "医药/生物"),
    (r"金融|银行|保险|证券|投顾", "金融/数据服务"),
    (r"电商|消费|零售|品牌", "电商/消费"),
    (r"网络安全|安全", "ICT/云计算"),
    (r"消费品", "电商/消费"),
]


def parse_salary(salary_str: str) -> tuple:
    """解析薪资字符串为 (min_k, max_k) 元组"""
    if not salary_str:
        return (0, 0)
    s = salary_str.lower().replace(" ", "")
    m = re.search(r'(\d+)\s*k?\s*(?:-|~)\s*(\d+)\s*k', s)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m = re.search(r'(\d+)k\s*以下', s)
    if m:
        return (0, int(m.group(1)))
    m = re.search(r'(\d+)k\s*以上', s)
    if m:
        return (int(m.group(1)), int(m.group(1)) * 2)
    return (0, 0)


def salary_to_range(salary: str) -> str:
    """薪资归一化为区间"""
    lo, hi = parse_salary(salary)
    if hi == 0:
        return "未知"
    if hi <= 20:
        return "10-20K"
    if hi <= 35:
        return "20-35K"
    if hi <= 50:
        return "35-50K"
    return "50K+"


def classify_company_type(job: dict) -> str:
    """按行业领域 + 公司特征分类"""
    company = job.get("company", "")
    industry = job.get("industry", "")
    is_hh = job.get("is_headhunter", False)

    if company in KNOWN_COMPANIES:
        return KNOWN_COMPANIES[company]
    for known, label in KNOWN_COMPANIES.items():
        if known in company:
            return label

    if industry:
        industry_lower = industry.lower()
        if any(kw in industry_lower for kw in ["互联网", "电商", "社交", "游戏", "广告"]):
            return "互联网大厂"
        if any(kw in industry_lower for kw in ["人工智能", "AI", "大模型", "智能"]):
            return "AI 初创"
        if any(kw in industry_lower for kw in ["机器人", "具身智能", "无人机"]):
            return "机器人初创"
        if any(kw in industry_lower for kw in ["新能源", "汽车", "车联网", "智能驾驶"]):
            return "新能源汽车"
        if any(kw in industry_lower for kw in ["芯片", "半导体", "集成电路"]):
            return "芯片/半导体"
        if any(kw in industry_lower for kw in ["云计算", "通信", "ICT"]):
            return "ICT/云计算"
        if any(kw in industry_lower for kw in ["制造", "工业"]):
            return "工业制造"
        if any(kw in industry_lower for kw in ["医药", "生物", "医疗"]):
            return "医药/生物"
        if any(kw in industry_lower for kw in ["金融", "银行", "保险", "证券"]):
            return "金融/数据服务"

    if is_hh or "某" in company:
        for pattern, label in HEADHUNTER_HINTS:
            if re.search(pattern, company):
                return label

    if not is_hh:
        for pattern, label in HEADHUNTER_HINTS:
            if re.search(pattern, company):
                return label

    return "未分类"


def split_headhunter(jobs: list) -> tuple:
    """拆分为 (direct_jobs, headhunter_jobs)"""
    direct, hh = [], []
    for j in jobs:
        if j.get("is_headhunter"):
            hh.append(j)
        else:
            direct.append(j)
    return direct, hh


def group_by_city(jobs: list) -> dict:
    """按城市分组"""
    groups = defaultdict(list)
    for j in jobs:
        city = j.get("city", "未知")
        groups[city].append(j)
    tier1 = ["上海", "北京", "深圳", "杭州", "广州", "成都"]
    def sort_key(item):
        city, js = item
        tier_idx = tier1.index(city) if city in tier1 else len(tier1)
        return (tier_idx, -len(js))
    return dict(sorted(groups.items(), key=sort_key))


def group_by_company_type(jobs: list) -> dict:
    """按公司类型分组"""
    type_order = [
        "互联网大厂", "AI 独角兽", "AI 初创", "机器人初创",
        "新能源汽车", "ICT/云计算", "芯片/半导体", "工业制造",
        "医药/生物", "金融/数据服务", "电商/消费", "外包/猎头匿", "未分类",
    ]
    groups = defaultdict(list)
    for j in jobs:
        ct = classify_company_type(j)
        groups[ct].append(j)
    return dict(sorted(groups.items(), key=lambda x: (
        type_order.index(x[0]) if x[0] in type_order else len(type_order),
        -len(x[1])
    )))


def format_job_row(i: int, job: dict) -> str:
    return (f"| {i} | {job.get('job_name','')} | {job.get('company','')} "
            f"| {job.get('salary','')} | {job.get('city','')} "
            f"| {job.get('experience','')} | {job.get('recruiter_active_time','') or '未知'} "
            f"| {job.get('source','')} |")


def format_job_detail(i: int, job: dict) -> str:
    """生成单个岗位的详情卡片"""
    skills = ", ".join(job.get("skills", [])) or "无"
    degree = job.get("degree", "") or "不限"
    description = job.get("description", "") or "暂无描述"
    job_requirements = job.get("job_requirements", "") or "暂无"
    url = job.get("url", "")
    source = job.get("source", "")
    url_link = f"[{source}]({url})" if url else source
    active_time = job.get("recruiter_active_time", "") or "未知"
    job_type = job.get("job_type", "") or "社招"
    scale = job.get("scale", "") or "未知"
    industry = job.get("industry", "") or "未知"

    lines = [
        f'<a id="job-{i}"></a>',
        f"",
        f"### {i}. {job.get('job_name', '')} @ {job.get('company', '')}",
        f"",
        f"| 字段 | 内容 |",
        f"|------|------|",
        f"| 薪资 | {job.get('salary', '')} |",
        f"| 城市 | {job.get('city', '')} |",
        f"| 区域 | {job.get('district', '') or '不限'} |",
        f"| 经验 | {job.get('experience', '')} |",
        f"| 学历 | {degree} |",
        f"| 求职类型 | {job_type} |",
        f"| 公司规模 | {scale} |",
        f"| 行业 | {industry} |",
        f"| 技能 | {skills} |",
        f"| 招聘者活跃 | {active_time} |",
        f"| 来源 | {url_link} |",
        f"| 猎头 | {'是' if job.get('is_headhunter') else '否'} |",
        f"",
        f"**岗位要求：**",
        f"",
        f"> {job_requirements}",
        f"",
        f"**职位描述：**",
        f"",
        f"> {description}",
        f"",
    ]
    return "\n".join(lines)


def build_section_table(jobs: list, start_idx: int = 1) -> str:
    """生成岗位汇总表格"""
    header = "| # | 岗位名称 | 公司 | 薪资 | 城市 | 经验 | 活跃 | 来源 |\n"
    header += "|---|---------|------|------|------|------|------|------|"
    rows = "\n".join(format_job_row(start_idx + i, j) for i, j in enumerate(jobs))
    return header + "\n" + rows


def build_section_details(jobs: list, start_idx: int = 1) -> str:
    """生成所有岗位详情"""
    return "\n".join(format_job_detail(start_idx + i, j) for i, j in enumerate(jobs))


def build_section(jobs: list, start_idx: int) -> tuple:
    """构建完整 section: 表格 + 详情，返回 (markdown_text, next_idx)"""
    if not jobs:
        return ("_暂无数据_", start_idx)
    table = build_section_table(jobs, start_idx)
    details = build_section_details(jobs, start_idx)
    return table + "\n\n" + details, start_idx + len(jobs)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="格式化岗位 JSON → Markdown 报告")
    parser.add_argument("input", nargs="?", help="输入 JSON 文件路径（缺省从 stdin 读取）")
    parser.add_argument("-o", "--output", help="输出 MD 文件路径（自动生成时间戳文件名）")
    parser.add_argument("--keyword", default="岗位", help="搜索关键词")
    parser.add_argument("--city", default="不限", help="城市")
    parser.add_argument("--experience", default="不限", help="经验要求")
    parser.add_argument("--salary", default="不限", help="薪资范围")
    parser.add_argument("--job-type", default="社招", help="求职类型")
    parser.add_argument("--active-days", default="30", help="招聘者活跃天数")
    parser.add_argument("--max-results", default="15", help="每站最大结果数")
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            jobs = json.load(f)
    else:
        jobs = json.load(sys.stdin)

    keyword = args.keyword
    sites = sorted(set(j.get("source", "") for j in jobs))

    # ── 猎头/非猎头拆分 ──
    direct_jobs, hh_jobs = split_headhunter(jobs)

    # ── 所有技能标签 ──
    all_skills = []
    for j in jobs:
        all_skills.extend(j.get("skills", []))

    # ── 构建非猎头 section ──
    direct_section, next_idx = build_section(direct_jobs, 1)

    # ── 构建猎头 section ──
    hh_section, _ = build_section(hh_jobs, next_idx)

    # ── 按城市分类 ──
    city_groups = group_by_city(jobs)
    city_parts = []
    idx = 1
    for c, cjobs in city_groups.items():
        city_parts.append(f"### {c}（{len(cjobs)} 条）\n")
        city_parts.append("| # | 岗位名称 | 公司 | 薪资 | 城市 | 经验 | 活跃 | 来源 |")
        city_parts.append("|---|---------|------|------|------|------|------|------|")
        city_parts.append(build_section_table(cjobs, idx).split("\n", 1)[1] if "\n" in build_section_table(cjobs, idx) else build_section_table(cjobs, idx))
        city_parts.append("")
        idx += len(cjobs)

    # ── 按公司类型分类 ──
    type_groups = group_by_company_type(jobs)
    type_parts = []
    tidx = 1
    for ct, tjobs in type_groups.items():
        type_parts.append(f"### {ct}（{len(tjobs)} 条）\n")
        type_parts.append("| # | 岗位名称 | 公司 | 薪资 | 城市 | 经验 | 活跃 | 来源 |")
        type_parts.append("|---|---------|------|------|------|------|------|------|")
        type_parts.append("\n".join(format_job_row(tidx + i, j) for i, j in enumerate(tjobs)))
        type_parts.append("")
        tidx += len(tjobs)

    # ── 按来源站点 ──
    by_source_parts = []
    for site in sites:
        site_jobs = [j for j in jobs if j.get("source") == site]
        by_source_parts.append(f"### {site}（{len(site_jobs)} 条）\n")
        for j in site_jobs:
            by_source_parts.append(
                f"- **{j.get('job_name','')}** @ {j.get('company','')}  "
                f"{j.get('salary','')} | {j.get('city','')} | "
                f"活跃: {j.get('recruiter_active_time','') or '未知'} | "
                f"[链接]({j.get('url','')})"
            )
        by_source_parts.append("")

    # ── 薪资分布 ──
    salary_counter = Counter(salary_to_range(j.get("salary", "")) for j in jobs)
    salary_dist = "\n".join(
        f"| {k} | {v} |" for k, v in salary_counter.most_common()
    )

    # ── 技能标签 ──
    skill_counter = Counter(all_skills)
    top_skills = " ".join(f"#{s}" for s, _ in skill_counter.most_common(20))

    # ── 渲染模板 ──
    output = TEMPLATE.format(
        keyword=keyword,
        search_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
        city=args.city, experience=args.experience, salary=args.salary,
        job_type=args.job_type, active_days=args.active_days, max_results=args.max_results,
        sites=", ".join(sites),
        total=len(jobs),
        direct_count=len(direct_jobs),
        hh_count=len(hh_jobs),
        direct_section=direct_section,
        hh_section=hh_section,
        by_city="\n".join(city_parts) if city_parts else "无数据",
        by_company_type="\n".join(type_parts) if type_parts else "无数据",
        by_source="\n".join(by_source_parts),
        salary_dist=salary_dist,
        top_skills=top_skills,
    )

    from pathlib import Path
    outdir = Path(__file__).resolve().parent.parent / "output"
    outdir.mkdir(parents=True, exist_ok=True)
    if args.output:
        outfile = Path(args.output)
    else:
        outfile = outdir / f"{datetime.now().strftime('%Y-%m-%d_%H%M%S')}-{keyword}.md"
    with open(outfile, "w") as f:
        f.write(output)

    print(f"报告已生成: {outfile}")
    print(output)


if __name__ == "__main__":
    main()
