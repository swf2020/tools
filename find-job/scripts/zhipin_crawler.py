#!/usr/bin/env python3
"""BOSS直聘数据采集脚本 - 通过 CDP Proxy 搜索岗位并采集详情"""

import json
import time
import subprocess
import sys
import os
import re
from datetime import datetime

CDP_BASE = "http://localhost:3456"
CURL_OPTS = ["curl", "-s", "--noproxy", "*", "--max-time", "30"]

# 输出文件
OUTPUT_FILE = "/Users/sunwenfei/Desktop/workspace/tools/find-job/output/2026-05-25_155258-zhipin_results.json"

# 搜索参数
KEYWORDS = ["AI Agent", "AI Agent开发", "AI开发", "大模型开发", "后端开发", "软件开发"]
EXPERIENCES = {"105": "3-5年", "106": "5-10年"}
CITY = "101280600"
SALARY = "407"  # 50K+
JOB_TYPE = "1901"  # 社招

def curl_cdp(method, path, data=None):
    """通过 curl 调用 CDP Proxy API"""
    if method == "GET":
        cmd = CURL_OPTS + [f"{CDP_BASE}{path}"]
    elif method == "POST":
        cmd = CURL_OPTS + ["-X", "POST", f"{CDP_BASE}{path}"]
        if data:
            cmd += ["-d", data]
    elif method == "POST_FILE":
        cmd = CURL_OPTS + ["-X", "POST", "--data-binary", "@-", f"{CDP_BASE}{path}"]
        # Special handling below
        proc = subprocess.run(
            ["curl", "-s", "--noproxy", "*", "--max-time", "30", "-X", "POST", "--data-binary", data, f"{CDP_BASE}{path}"],
            capture_output=True, text=True, timeout=35
        )
        return proc.stdout.strip()
    else:
        return None

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        return proc.stdout.strip()
    except subprocess.TimeoutExpired:
        print("  curl timeout")
        return None
    except Exception as e:
        print(f"  curl error: {e}")
        return None

def cdp_eval(target, js_code, max_retries=3):
    """通过 CDP Proxy 执行 eval"""
    result = None
    for attempt in range(max_retries):
        resp = curl_cdp("POST_FILE", f"/eval?target={target}", js_code)
        if resp:
            try:
                parsed = json.loads(resp)
                if 'value' in parsed:
                    return json.loads(parsed['value'])
                return parsed
            except json.JSONDecodeError:
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    print(f"  JSON parse error: {resp[:200]}")
        else:
            if attempt < max_retries - 1:
                time.sleep(2)
    return None

def cdp_navigate(target, url_str):
    """通过 CDP Proxy 导航到 URL"""
    from urllib.parse import quote
    encoded_url = quote(url_str, safe='/:?=&%')
    resp = curl_cdp("GET", f"/navigate?target={target}&url={encoded_url}")
    return resp is not None and len(resp) > 0

def cdp_new_tab(url_str):
    """创建新的 CDP tab"""
    from urllib.parse import quote
    encoded_url = quote(url_str, safe='/:?=&%')
    resp = curl_cdp("GET", f"/new?url={encoded_url}")
    if resp:
        try:
            return json.loads(resp).get('targetId')
        except:
            pass
    return None

def cdp_close(target):
    """关闭 CDP tab"""
    curl_cdp("GET", f"/close?target={target}")

def parse_salary(salary_desc):
    """解析薪资描述，返回 (min, max)"""
    if not salary_desc:
        return None, None
    match = re.match(r'(\d+)-(\d+)K', salary_desc)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.match(r'(\d+)K以上', salary_desc)
    if match:
        return int(match.group(1)), None
    match = re.match(r'(\d+)K', salary_desc)
    if match:
        return int(match.group(1)), int(match.group(1))
    return None, None

def fetch_job_page(target, keyword, experience, page):
    """通过 CDP eval 获取单页搜索结果"""
    js = (
        "fetch('/wapi/zpgeek/search/joblist.json?scene=1&query=' + encodeURIComponent('" +
        keyword + "') + '&city=" + CITY + "&experience=" + experience +
        "&jobType=" + JOB_TYPE + "&salary=" + SALARY + "&page=" + str(page) +
        "&pageSize=10').then(r => r.json()).then(d => JSON.stringify(d.zpData || d))"
    )
    return cdp_eval(target, js)

def fetch_detail_page(target, encrypt_job_id):
    """访问详情页提取职位描述"""
    detail_url = f"https://www.zhipin.com/job_detail/{encrypt_job_id}.html"
    if not cdp_navigate(target, detail_url):
        return "", ""

    time.sleep(2.5)  # 等待页面加载

    js = """(() => {
        const text = document.body.innerText;
        const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
        const descIdx = lines.findIndex(l => l === '职位描述');
        let description = '', jobRequirements = '';
        if (descIdx !== -1) {
            const stopKws = ['公司信息', '工商信息', '工作地址', '公司介绍', '职位发布者', '微信扫码', 'Boss', '相似职位', '竞争力分析'];
            let inRequirements = false;
            for (let i = descIdx + 1; i < lines.length; i++) {
                if (stopKws.some(kw => lines[i].includes(kw))) break;
                if (lines[i] === '任职要求：' || lines[i].startsWith('任职要求')) { inRequirements = true; continue; }
                if (!inRequirements) description += lines[i] + '\\n';
                else jobRequirements += lines[i] + '\\n';
            }
        }
        return JSON.stringify({description: description.trim().substring(0, 1000), jobRequirements: jobRequirements.trim().substring(0, 500)});
    })()"""
    result = cdp_eval(target, js)
    if result:
        return result.get('description', ''), result.get('jobRequirements', '')
    return "", ""

def extract_job_fields(job, keyword, experience):
    """从 API 响应提取完整字段"""
    salary_desc = job.get('salaryDesc', '')
    salary_min, salary_max = parse_salary(salary_desc)

    # 薪资后过滤：只保留 salary_min >= 30
    if salary_min is None:
        print(f"    SKIP: 无法解析薪资 '{salary_desc}'")
        return None
    if salary_min < 30:
        return None

    encrypt_job_id = job.get('encryptJobId', '')

    return {
        'job_name': job.get('jobName', ''),
        'company': job.get('brandName', ''),
        'salary': salary_desc,
        'salary_min': salary_min,
        'salary_max': salary_max,
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
        'url': f"https://www.zhipin.com/job_detail/{encrypt_job_id}.html",
        'is_headhunter': job.get('proxyJob', 0) == 1,
        'recruiter_active_time': job.get('lastLogin', ''),
        'job_requirements': '',
        'job_type': '社招',
        'encryptJobId': encrypt_job_id,
        'search_keyword': keyword,
        'search_experience': EXPERIENCES.get(experience, experience),
    }

def deduplicate(jobs):
    """去重：同一公司+同一岗位名只保留一条"""
    seen = set()
    result = []
    for job in jobs:
        key = (job.get('company', '').strip(), job.get('job_name', '').strip())
        if key not in seen:
            seen.add(key)
            result.append(job)
    return result

def main():
    print("=== 开始 BOSS直聘数据采集 ===")
    target = cdp_new_tab("https://www.zhipin.com/web/geek/jobs?city=101280600&query=AI%20Agent&page=1")
    if not target:
        print("ERROR: 无法创建 CDP tab")
        sys.exit(1)
    print(f"主 tab: {target}")

    all_jobs = []

    # 创建详情页 tab
    time.sleep(1)
    detail_tab = cdp_new_tab("about:blank")
    if not detail_tab:
        print("使用主 tab 作为详情页 tab")
        detail_tab = target

    try:
        for keyword in KEYWORDS:
            for exp_code in ["105", "106"]:
                exp_label = EXPERIENCES[exp_code]
                print(f"\n--- 搜索: {keyword} ({exp_label}) ---")
                combo_jobs = []

                for page in range(1, 5):  # 最多4页
                    print(f"  页码 {page}...")
                    data = fetch_job_page(target, keyword, exp_code, page)
                    if not data:
                        print(f"    API 无数据")
                        break

                    job_list = data.get('jobList', [])
                    if not job_list:
                        print(f"    无岗位")
                        break

                    new_count = 0
                    skip_count = 0
                    for job in job_list:
                        job_fields = extract_job_fields(job, keyword, exp_code)
                        if job_fields:
                            combo_jobs.append(job_fields)
                            new_count += 1
                        else:
                            skip_count += 1

                    print(f"    API返回 {len(job_list)}, 薪资>=30K: {new_count}, 跳过: {skip_count}")

                    has_more = data.get('hasMore', False)
                    if not has_more:
                        print(f"    无更多页")
                        break

                    if len(combo_jobs) >= 30:
                        print(f"    已采集>=30条, 停止翻页")
                        break

                    time.sleep(1.2)  # 翻页间隔

                # 去重
                combo_jobs = deduplicate(combo_jobs)
                # 限制最多30条
                combo_jobs = combo_jobs[:30]
                print(f"  => 组合结果: {len(combo_jobs)} 条 (去重+限制后)")

                all_jobs.extend(combo_jobs)

        # 全局去重
        all_jobs = deduplicate(all_jobs)
        print(f"\n=== 去重后共 {len(all_jobs)} 个岗位 ===")

        # Step 5: 访问详情页提取描述
        print(f"\n=== 提取职位描述 (每个 >=2.5秒) ===")
        for i, job in enumerate(all_jobs):
            encrypt_id = job.get('encryptJobId', '')
            if not encrypt_id:
                continue
            print(f"  [{i+1}/{len(all_jobs)}] {job['job_name'][:40]} @ {job['company'][:25]}")
            description, requirements = fetch_detail_page(detail_tab, encrypt_id)
            job['description'] = description
            job['job_requirements'] = requirements
            print(f"    描述: {len(description)}字, 要求: {len(requirements)}字")
            if i < len(all_jobs) - 1:
                time.sleep(0.3)

        # 清理临时字段
        for job in all_jobs:
            job.pop('encryptJobId', None)
            job.pop('search_keyword', None)
            job.pop('search_experience', None)

        # Step 7: 保存结果
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(all_jobs, f, ensure_ascii=False, indent=2)
        print(f"\n=== 结果已保存: {OUTPUT_FILE} ===")
        print(f"共 {len(all_jobs)} 条")

        # 统计猎头/非猎头
        headhunter = sum(1 for j in all_jobs if j.get('is_headhunter'))
        non_headhunter = len(all_jobs) - headhunter
        print(f"猎头: {headhunter} 条, 非猎头: {non_headhunter} 条")

    finally:
        # 关闭 tab
        if detail_tab != target:
            print(f"关闭详情 tab: {detail_tab}")
            cdp_close(detail_tab)
        print(f"关闭主 tab: {target}")
        cdp_close(target)
        print("所有 tab 已关闭")

if __name__ == '__main__':
    main()
