#!/usr/bin/env python3
"""BOSS直聘数据采集 V3 - 每个搜索组合使用独立 tab 避免限流"""

import json
import time
import subprocess
import sys
import os
import re
import urllib.parse

CDP = "http://localhost:3456"
CURL = ["curl", "-s", "--noproxy", "*", "--max-time", "45"]
OUTPUT = "/Users/sunwenfei/Desktop/workspace/tools/find-job/output/2026-05-25_155258-zhipin_results.json"

KEYWORDS = ["AI Agent", "AI Agent开发", "AI开发", "大模型开发", "后端开发", "软件开发"]
EXP_LIST = [("105", "3-5年"), ("106", "5-10年")]
CITY = "101280600"
SALARY = "407"
JOB_TYPE = "1901"

def curl(path, data=None, timeout=45):
    opts = ["curl", "-s", "--noproxy", "*", "--max-time", str(timeout)]
    if data is not None:
        proc = subprocess.run(opts + ["-X", "POST", "--data-binary", data, f"{CDP}{path}"],
            capture_output=True, text=True, timeout=timeout+10)
    else:
        proc = subprocess.run(opts + [f"{CDP}{path}"],
            capture_output=True, text=True, timeout=timeout+10)
    return proc.stdout.strip()

def cdp_new(url_str):
    resp = curl(f"/new?url={urllib.parse.quote(url_str, safe='/:?=&%')}", timeout=30)
    if resp:
        try:
            return json.loads(resp).get('targetId')
        except:
            pass
    return None

def cdp_close(target):
    try:
        curl(f"/close?target={target}", timeout=10)
    except:
        pass

def cdp_eval(target, js, retries=2):
    for attempt in range(retries):
        try:
            resp = curl(f"/eval?target={target}", js)
            if resp:
                parsed = json.loads(resp)
                if 'value' in parsed:
                    return json.loads(parsed['value'])
                elif 'error' in parsed:
                    if attempt < retries - 1:
                        time.sleep(2)
                else:
                    return parsed
        except:
            if attempt < retries - 1:
                time.sleep(2)
    return None

def cdp_navigate(target, url_str):
    path = f"/navigate?target={target}&url={urllib.parse.quote(url_str, safe='/:?=&%')}"
    resp = curl(path)
    return resp is not None and len(resp.strip()) > 0

def fetch_search_page(target, keyword, exp_code, page):
    q = urllib.parse.quote(keyword, safe='')
    api_url = f"/wapi/zpgeek/search/joblist.json?scene=1&query={q}&city={CITY}&experience={exp_code}&jobType={JOB_TYPE}&salary={SALARY}&page={page}&pageSize=10"
    js = f"fetch('{api_url}').then(r => r.json()).then(d => JSON.stringify(d.zpData || d)).catch(e => JSON.stringify({{_error: e.message}}))"
    data = cdp_eval(target, js)
    if not data:
        return [], False, 0
    if '_error' in data:
        return [], False, 0
    jobs = data.get('jobList', [])
    return jobs, data.get('hasMore', False), data.get('totalCount', len(jobs))

def parse_salary(desc):
    if not desc:
        return None, None
    m = re.match(r'(\d+)-(\d+)K', desc)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r'(\d+)K以上', desc)
    if m:
        return int(m.group(1)), None
    m = re.match(r'(\d+)K', desc)
    if m:
        return int(m.group(1)), int(m.group(1))
    return None, None

def extract_job(job):
    sd = job.get('salaryDesc', '')
    smin, smax = parse_salary(sd)
    if smin is None or smin < 30:
        return None
    eid = job.get('encryptJobId', '')
    return {
        'job_name': job.get('jobName', ''),
        'company': job.get('brandName', ''),
        'salary': sd,
        'salary_min': smin,
        'salary_max': smax,
        'city': job.get('cityName', ''),
        'district': f"{job.get('areaDistrict', '')} {job.get('businessDistrict', '')}".strip(),
        'experience': job.get('jobExperience', ''),
        'degree': job.get('jobDegree', ''),
        'skills': job.get('skills', []),
        'description': '',
        'welfare': job.get('welfareList', []),
        'industry': job.get('brandIndustry', ''),
        'stage': job.get('brandStageName', ''),
        'scale': job.get('brandScaleName', ''),
        'publish_date': '',
        'source': 'zhipin',
        'url': f"https://www.zhipin.com/job_detail/{eid}.html",
        'is_headhunter': job.get('proxyJob', 0) == 1,
        'recruiter_active_time': job.get('lastLogin', ''),
        'job_requirements': '',
        'job_type': '社招',
        'encryptJobId': eid,
    }

def deduplicate(jobs):
    seen = set()
    result = []
    for j in jobs:
        k = (j.get('company', '').strip(), j.get('job_name', '').strip())
        if k not in seen:
            seen.add(k)
            result.append(j)
    return result

def search_keyword(keyword, exp_code, exp_label):
    """对单个关键词+经验组合进行搜索，使用独立 tab"""
    print(f"  [{keyword}] ({exp_label})...", end=" ", flush=True)

    # 创建独立 tab
    tab = cdp_new("https://www.zhipin.com/web/geek/jobs?city=101280600")
    if not tab:
        print("ERROR: 无法创建 tab")
        return []

    try:
        combo = []
        for page in range(1, 4):  # 最多3页
            jobs, has_more, total = fetch_search_page(tab, keyword, exp_code, page)
            if not jobs:
                break

            for job in jobs:
                jf = extract_job(job)
                if jf:
                    combo.append(jf)

            if not has_more:
                break
            if len(combo) >= 30:
                break
            time.sleep(1.0)

        combo = deduplicate(combo)[:30]
        print(f"{len(combo)} jobs")
        return combo
    finally:
        cdp_close(tab)

def fetch_description(target, encrypt_id):
    url = f"https://www.zhipin.com/job_detail/{encrypt_id}.html"
    if not cdp_navigate(target, url):
        return "", ""
    time.sleep(2.5)
    js = """(() => {
        const text = document.body.innerText;
        const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
        const descIdx = lines.findIndex(l => l === '职位描述');
        let desc = '', reqs = '';
        if (descIdx !== -1) {
            const stopKws = ['公司信息', '工商信息', '工作地址', '公司介绍', '职位发布者', '微信扫码', 'Boss', '相似职位', '竞争力分析'];
            let inReqs = false;
            for (let i = descIdx + 1; i < lines.length; i++) {
                if (stopKws.some(kw => lines[i].includes(kw))) break;
                if (lines[i] === '任职要求：' || lines[i].startsWith('任职要求')) { inReqs = true; continue; }
                if (!inReqs) desc += lines[i] + '\\n';
                else reqs += lines[i] + '\\n';
            }
        }
        return JSON.stringify({desc: desc.trim().substring(0, 1000), reqs: reqs.trim().substring(0, 500)});
    })()"""
    r = cdp_eval(target, js)
    if r:
        return r.get('desc', ''), r.get('reqs', '')
    return "", ""

def main():
    print("=== BOSS直聘数据采集 V3 ===")
    all_jobs = []

    for keyword in KEYWORDS:
        for exp_code, exp_label in EXP_LIST:
            jobs = search_keyword(keyword, exp_code, exp_label)
            all_jobs.extend(jobs)
            time.sleep(1.0)  # 搜索间隔

    all_jobs = deduplicate(all_jobs)
    print(f"\n=== 去重后共 {len(all_jobs)} 岗位 ===")

    if not all_jobs:
        print("无岗位数据")
        return

    # 详情提取 - 使用独立 tab
    print(f"\n=== 提取职位描述 ===")
    detail_tab = cdp_new("about:blank")
    try:
        for i, job in enumerate(all_jobs):
            eid = job.get('encryptJobId', '')
            if not eid:
                continue
            print(f"  [{i+1}/{len(all_jobs)}] {job['job_name'][:45]} @ {job['company'][:25]}")
            d, r = fetch_description(detail_tab, eid)
            job['description'] = d
            job['job_requirements'] = r
            print(f"    desc={len(d)}chars, reqs={len(r)}chars")
            if i < len(all_jobs) - 1:
                time.sleep(0.3)
    finally:
        cdp_close(detail_tab)

    # 清理
    for j in all_jobs:
        j.pop('encryptJobId', None)

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(all_jobs, f, ensure_ascii=False, indent=2)

    print(f"\n=== 保存: {OUTPUT} ===")
    print(f"总数: {len(all_jobs)}")
    hh = sum(1 for j in all_jobs if j.get('is_headhunter'))
    print(f"猎头: {hh}, 非猎头: {len(all_jobs) - hh}")

if __name__ == '__main__':
    main()
