#!/usr/bin/env python3
"""岗位去重脚本：公司名归一化 + 岗位名模糊匹配去重"""

import json
import sys
import re
from difflib import SequenceMatcher

def normalize_company(name: str) -> str:
    """公司名归一化：去除括号内备注，统一简称"""
    name = re.sub(r'[（(][^)）]*[)）]', '', name).strip()
    name = re.sub(r'(有限公司|股份有限|有限责任|集团|科技|技术|网络|信息)$', '', name)
    return name.strip()

def job_similarity(a: str, b: str) -> float:
    """岗位名相似度"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

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
    if len(sys.argv) < 2:
        jobs = json.load(sys.stdin)
    else:
        with open(sys.argv[1]) as f:
            jobs = json.load(f)

    result = deduplicate(jobs)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
