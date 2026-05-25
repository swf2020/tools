#!/usr/bin/env python3
"""岗位去重脚本：公司名归一化 + 岗位名模糊匹配去重"""

import json
import sys
import re
import argparse
from difflib import SequenceMatcher

# 公司常见简称 → 归一化名称 映射表
# 用于去重时将同一公司的不同写法统一（先剥后缀再查表，如
# "腾讯科技有限公司"→剥后缀→"腾讯"→查表→"腾讯科技"，
# "腾讯"→剥后缀→"腾讯"→查表→"腾讯科技"，两者可匹配）
COMPANY_ALIASES = {
    "腾讯": "腾讯科技",
    "阿里": "阿里巴巴",
    "字节": "字节跳动",
    "美团": "美团点评",
    "滴滴": "滴滴出行",
    "京东": "京东集团",
    "华为": "华为技术",
    "小米": "小米科技",
    "网易": "网易集团",
    "快手": "快手科技",
    "小红书": "小红书科技",
    "蚂蚁": "蚂蚁集团",
    "比亚迪": "比亚迪股份",
    "蔚来": "蔚来汽车",
    "小鹏": "小鹏汽车",
    "理想": "理想汽车",
    "深信服": "深信服科技",
    "大疆": "大疆创新",
    "商汤": "商汤科技",
    "旷视": "旷视科技",
    "云从": "云从科技",
    "依图": "依图科技",
    "寒武纪": "寒武纪科技",
    "地平线": "地平线机器人",
    "智谱": "智谱华章",
    "面壁": "面壁智能",
    "深势": "深势科技",
    "SHEIN": "SHEIN",
    "SheIn": "SHEIN",
    "shein": "SHEIN",
}


def normalize_company(name: str) -> str:
    """公司名归一化：去除括号备注 → 剥后缀 → 别名统一 → 再剥后缀"""
    if not name:
        return ""
    # 1. 去除括号内备注
    name = re.sub(r'[（(][^)）]*[)）]', '', name).strip()
    # 2. 递归剥离常见公司后缀
    suffixes = r'(股份有限|有限公司|有限责任|集团公司|集团|科技|技术|网络|信息|股份)$'
    prev = None
    while prev != name:
        prev = name
        name = re.sub(suffixes, '', name).strip()
    # 3. 查别名表统一简称
    if name in COMPANY_ALIASES:
        name = COMPANY_ALIASES[name]
    return name.strip()

def job_similarity(a: str, b: str) -> float:
    """岗位名相似度"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def filter_by_active_time(jobs: list, max_days: int = 30) -> list:
    """根据招聘者活跃时间过滤：仅保留最近 max_days 天内活跃的岗位"""
    if max_days is None or max_days <= 0:
        return jobs
    filtered = []
    for j in jobs:
        text = (j.get("recruiter_active_time") or "").strip()
        if not text or "未知" in text:
            filtered.append(j)  # 无数据的保留
            continue
        days = _parse_active_days(text)
        if days is not None and days <= max_days:
            filtered.append(j)
        elif days is None:
            filtered.append(j)  # 无法解析的保留
    return filtered


def _parse_active_days(text: str) -> int | None:
    """从活跃时间文本提取天数。如 '今日活跃'→0, '3天内活跃'→3, '本周活跃'→7, '本月活跃'→30, '半年前活跃'→180"""
    import re as _re
    if "今日" in text or "刚刚" in text or "在线" in text:
        return 0
    for kw, val in [("半年", 180), ("5个月", 150), ("4个月", 120), ("3个月", 90), ("2个月", 60), ("1个月", 30), ("本月", 30), ("本周", 7)]:
        if kw in text:
            return val
    m = _re.search(r"(\d+)\s*天", text)
    if m:
        return int(m.group(1))
    m = _re.search(r"(\d+)\s*小时", text)
    if m:
        return 0
    return None


def split_headhunter(jobs: list) -> dict:
    """拆分猎头和非猎头岗位，返回 {headhunter: [...], direct: [...]}"""
    hh, direct = [], []
    for j in jobs:
        if j.get("is_headhunter") or j.get("proxyJob") == 1:
            hh.append(j)
        else:
            direct.append(j)
    return {"headhunter": hh, "direct": direct}


def deduplicate(jobs: list, company_threshold: float = 0.85, title_threshold: float = 0.80) -> list:
    """去重主逻辑"""
    if not jobs:
        return []

    deduped = []
    seen = []

    for job in sorted(jobs, key=lambda j: j.get('publish_date', ''), reverse=True):
        company = normalize_company(job.get('company', ''))
        title = job.get('job_name', '')

        is_dup = False
        for s_company, s_title in seen:
            if (SequenceMatcher(None, company, s_company).ratio() >= company_threshold
                    and job_similarity(title, s_title) >= title_threshold):
                is_dup = True
                break

        if not is_dup:
            job['company_normalized'] = company
            deduped.append(job)
            seen.append((company, title))

    return deduped

def main():
    parser = argparse.ArgumentParser(description="岗位去重：公司名归一化 + 岗位名模糊匹配 + 活跃时间过滤 + 猎头分流")
    parser.add_argument("input", nargs="?", help="输入 JSON 文件路径（缺省从 stdin 读取）")
    parser.add_argument("-o", "--output", help="输出 JSON 文件路径（去重合并结果）")
    parser.add_argument("--max-active-days", type=int, default=0, help="招聘者活跃天数上限（0=不过滤）")
    parser.add_argument("--split-headhunter", action="store_true", help="输出猎头/非猎头拆分 JSON")
    parser.add_argument("--split-output-dir", default=None, help="拆分输出目录")
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            jobs = json.load(f)
    else:
        jobs = json.load(sys.stdin)

    # 活跃时间过滤
    if args.max_active_days > 0:
        before = len(jobs)
        jobs = filter_by_active_time(jobs, args.max_active_days)
        print(f"[去重] 活跃时间过滤: {before} → {len(jobs)} (max {args.max_active_days}天)", file=sys.stderr)

    # 去重
    result = deduplicate(jobs)
    print(f"[去重] 去重: {len(jobs)} → {len(result)}", file=sys.stderr)

    output_str = json.dumps(result, ensure_ascii=False, indent=2)
    print(output_str)

    if args.output:
        from pathlib import Path
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            f.write(output_str)

    # 猎头/非猎头分流
    if args.split_headhunter:
        split = split_headhunter(result)
        out_dir = args.split_output_dir or (Path(args.output).parent if args.output else Path.cwd())
        from pathlib import Path as _Path
        out_dir = _Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        for key, items in split.items():
            spath = out_dir / f"{key}.json"
            with open(spath, "w") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
            print(f"[分流] {key}: {len(items)} 条 → {spath}", file=sys.stderr)


if __name__ == "__main__":
    main()
