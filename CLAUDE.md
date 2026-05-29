# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This repo contains three independent tools for daily workflows. Each tool is self-contained in its own directory. No shared code between them.

## Project Structure

```
tools/
├── anylist/                          # Claude Code observability proxy
│   ├── claude_code_to_llm_proxy.py   #   FastAPI HTTP proxy: CC ↔ DashScope API
│   ├── claude_code_to_mcp_server_proxy.py  # stdio proxy: CC ↔ GitNexus MCP
│   └── format_log.py                 #   Log formatter (unescape \n)
├── auto_save_and_publish_csdn_blog/  # CSDN blog batch publisher (Selenium)
│   ├── main.py                       #   Entry point, CLI arg parsing
│   ├── browser.py                    #   Chrome driver lifecycle (context manager)
│   ├── login.py                      #   CSDN login (WeChat scan code)
│   ├── editor.py                     #   CSDN editor interactions + publish flow
│   ├── processor.py                  #   Markdown file scanner + dedup tracker
│   ├── config.py                     #   .env loader
│   └── models.py                     #   Blog dataclass
├── find-job/                         # Claude Code Skill for job search
│   ├── SKILL.md                      #   Skill definition (trigger, flow, params)
│   ├── scripts/
│   │   ├── deduplicate.py            #   Company normalization + fuzzy dedup + headhunter split
│   │   └── format_output.py          #   JSON → Markdown report generator
│   ├── references/
│   │   ├── sites.json                #   10 recruitment site configs (URLs, API params, pitfalls)
│   │   ├── job_schema.md             #   Job data field schema
│   │   └── site-patterns/            #   Per-site scraping patterns (CSS selectors, known traps)
│   └── output/                       #   Search result JSON + Markdown reports (gitignored)
├── venv/                             # Python virtualenv (gitignored)
└── .env                              # API keys: DASHSCOPE_API_KEY (gitignored)
```

## Commands

```bash
# Virtualenv
source venv/bin/activate

# --- anylist ---
# Start LLM proxy (intercept Claude Code ↔ DashScope)
python anylist/claude_code_to_llm_proxy.py
# Format proxy logs (expand \n escapes to real newlines)
python anylist/format_log.py [input.log] [output.log]

# --- CSDN blog publisher ---
# Save as draft (default)
python -m auto_save_and_publish_csdn_blog.main
# Publish directly
python -m auto_save_and_publish_csdn_blog.main --action publish
# Headless mode + custom folder
python -m auto_save_and_publish_csdn_blog.main --headless --folder /path/to/md

# --- find-job ---
# Deduplicate job results
python find-job/scripts/deduplicate.py output/all_raw.json -o output/deduped.json \
  --max-active-days 30 --split-headhunter --split-output-dir output/
# Generate Markdown report
python find-job/scripts/format_output.py output/deduped.json \
  --keyword "AI Agent" --city "深圳" --salary "20-35K"
```

## Key Architecture Details

### anylist proxy pair
- **LLM proxy** runs on `http://0.0.0.0:8000`. Claude Code points `ANTHROPIC_BASE_URL` at it. It intercepts title-generation requests (mock-returns them locally) and forwards everything else to DashScope. Forces `stream: false`. Uses `asyncio.Lock` + `asyncio.to_thread` for concurrency-safe file I/O.
- **MCP proxy** is a stdio intermediary. Claude Code MCP config points `command: python3` at this script instead of `npx gitnexus mcp`. It spawns the real gitnexus as a subprocess and pipes JSON-RPC bidirectionally, logging every message with human-readable method summaries.

### CSDN publisher flow
Browser → login (WeChat scan, retries 3x) → scan `.md` files (sorted by numeric prefix) → for each: open editor tab → fill title/content → save draft → open config modal → set tags/categories/cover/original/visibility → final save/publish. Tracks processed files in a log file to avoid re-processing.

### find-job skill
Not a standalone app — invoked as a Claude Code Skill. Dispatches parallel sub-agents (one per site: BOSS直聘 + 猎聘) via `dispatching-parallel-agents`, each using `web-access` CDP browser to scrape. Raw JSON → `deduplicate.py` (company alias normalization + SequenceMatcher fuzzy dedup + active-time filter + headhunter/direct split) → `format_output.py` (Markdown with summary tables, detail cards, city/company-type/salary/skill breakdowns).

BOSS直聘 uses its internal JSON API (`wapi/zpgeek/search/joblist.json`); salary is PUA font-encoded in DOM so must use API's `salaryDesc`. 猎聘 is SPA, requires CDP browser with `[class*="suffix"]` attribute selectors (dynamic CSS prefix). Both sites may need post-filtering on salary when the site's filter doesn't support custom ranges (e.g., 30-60K → fetch all, filter client-side).

## Dependencies

```
fastapi==0.109.2 uvicorn==0.27.1 httpx==0.26.0 python-dotenv selenium==4.26.1 pyperclip
```

All installed in `venv/`. `find-job` has no Python deps beyond stdlib — scraping relies on Claude Code skills.
