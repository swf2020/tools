"""
技术文档批量生成脚本
环境：Python 3.11+，anthropic 0.40+
用法：python generate_docs.py
      python generate_docs.py --type 技术        # 只生成"技术"类
      python generate_docs.py --type 技术点      # 只生成"技术点"类
      python generate_docs.py --topic "Redis"    # 只生成指定主题
      python generate_docs.py --concurrency 3   # 并发数（默认 3）
      python generate_docs.py --dry-run          # 只打印任务列表，不实际调用
"""

import anthropic
import json
import os
import re
import time
import argparse
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────
# 配置区
# ─────────────────────────────────────────
JSON_FILE   = "../技术.json"
SKILL_FILE  = "../.claude/skills/tech-doc-generator/SKILL.md"
OUTPUT_DIR  = "./docs"
MODEL       = "claude-sonnet-4-6"
MAX_TOKENS  = 15000
CONCURRENCY = 3   # 并发协程数，避免触发速率限制
RETRY_TIMES = 3   # 失败重试次数
RETRY_DELAY = 10  # 重试间隔（秒）
os.environ["ANTHROPIC_BASE_URL"] = "https://crsacc.itssx.com/api"
os.environ["ANTHROPIC_API_KEY"] = "cr_610fa65f8077fd03d189e3bc22205d5296d6bbc8477991007e4c45f40d798229"


# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("generate_docs.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────
# 文件工具
# ─────────────────────────────────────────
def load_topics(json_file: str, doc_type: Optional[str] = None) -> list[tuple[str, str]]:
    """
    读取 JSON，返回 [(主题, 类型), ...] 列表
    doc_type: "技术" | "软件" | "技术点" | None(全部)
    """
    with open(json_file, encoding="utf-8") as f:
        data = json.load(f)

    result = []
    target_keys = [doc_type] if doc_type else list(data.keys())

    for key in target_keys:
        if key not in data:
            log.warning(f"JSON 中不存在 key: {key}，已跳过")
            continue
        for topic in data[key]:
            result.append((topic.strip(), key))

    log.info(f"共加载 {len(result)} 个主题（来源类型：{target_keys}）")
    return result


def load_skill(skill_file: str) -> str:
    """读取 SKILL.md 内容"""
    with open(skill_file, encoding="utf-8") as f:
        content = f.read()
    log.info(f"SKILL.md 加载完成，长度 {len(content)} 字符")
    return content


def sanitize_filename(name: str) -> str:
    """将主题名转为合法文件名（去除特殊字符）"""
    return re.sub(r'[\\/*?:"<>|()\[\]{} ]', "_", name)


def build_output_path(topic: str, output_dir: str) -> Path:
    """构造输出文件路径：./docs/${主题}_${日期}.md"""
    date_str  = datetime.now().strftime("%Y%m%d")
    safe_name = sanitize_filename(topic)
    return Path(output_dir) / f"{safe_name}_{date_str}.md"


def is_already_done(topic: str, output_dir: str) -> bool:
    """检查今天是否已生成过该文档（支持断点续跑）"""
    return build_output_path(topic, output_dir).exists()


# ─────────────────────────────────────────
# Prompt 构造
# ─────────────────────────────────────────
def build_system_prompt(skill_content: str) -> str:
    """
    将 SKILL.md 作为系统提示词。

    修复说明：
    SKILL.md 含 "把生成最终内容保存为markdown文件" 指令，
    模型在纯 API 环境中无法执行文件操作，会回复操作说明而非文档内容。
    在末尾追加覆盖指令，明确告知模型只需输出文档正文。
    """
    override = (
        "\n\n---\n"
        "## 重要覆盖指令（优先级最高）\n\n"
        "你当前运行在 API 批处理环境中，没有文件系统访问能力。\n"
        "请忽略所有关于保存文件、写入文件的指令。\n"
        "你只需要将完整的技术文档内容以纯 Markdown 文本的形式直接输出，"
        "不要输出任何操作说明、确认信息或额外解释。\n"
        "直接从文档的一级标题开始输出，直到文档结束。\n"
    )
    return skill_content + override


def build_user_prompt(topic: str, doc_type: str) -> str:
    """
    构造用户消息。

    修复说明：
    SKILL.md 任务章节含 "[主题：{技术 | 软件 | 技术点}]" 占位符，
    通过 user_content 明确指定主题和类型，确保模型知道具体写什么。
    明确要求直接输出 Markdown，防止模型误以为需要询问或保存。
    """
    return (
        f"请为以下主题撰写完整的技术文档：\n\n"
        f"- 主题：{topic}\n"
        f"- 类型：{doc_type}\n\n"
        f"要求：\n"
        f"1. 直接输出完整 Markdown 文档，从 # {topic} 一级标题开始\n"
        f"2. 严格按照系统提示词中的文档结构模板输出所有适用章节\n"
        f"3. 不需要任何前言、操作说明或确认信息，只输出文档本身"
    )


# ─────────────────────────────────────────
# Markdown 后处理
# ─────────────────────────────────────────
def to_standard_markdown(raw: str, topic: str, doc_type: str) -> str:
    """
    对模型输出做轻量标准化：
    - 确保文档以一级标题开头
    - 去除首尾多余空行
    - 统一换行符
    - 追加生成元信息
    """
    content = raw.strip().replace("\r\n", "\n")

    if not content.startswith("# "):
        content = f"# {topic}\n\n> 类型：{doc_type}\n\n" + content

    footer = (
        f"\n\n---\n\n"
        f"> 生成日期：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n"
        f"> 模型：{MODEL}  \n"
        f"> 类型：{doc_type}\n"
    )
    return content + footer


# ─────────────────────────────────────────
# API 调用（支持 Prompt Caching + 重试）
# ─────────────────────────────────────────
async def generate_doc(
    client: anthropic.AsyncAnthropic,
    topic: str,
    doc_type: str,
    system_prompt: str,
    semaphore: asyncio.Semaphore,
    dry_run: bool = False,
) -> Optional[str]:
    """异步生成单份技术文档，返回 Markdown 字符串"""

    if dry_run:
        log.info(f"[DRY-RUN] 跳过：{topic}")
        return f"# {topic}\n\n（dry-run 模式）\n"

    user_prompt = build_user_prompt(topic, doc_type)

    for attempt in range(1, RETRY_TIMES + 1):
        async with semaphore:
            try:
                log.info(f"[{attempt}/{RETRY_TIMES}] 生成中：{topic}")
                start = time.monotonic()

                response = await client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=[
                        {
                            "type": "text",
                            "text": system_prompt,
                            # Prompt Caching：system_prompt 对所有主题固定不变，
                            # 首次请求写入缓存，后续 N 个主题直接命中，节省约 90% 输入费用
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[
                        {"role": "user", "content": user_prompt}
                    ],
                    # 修复：显式禁止工具调用，强制模型只输出文本
                    # SKILL.md 含文件操作语义，会被模型误解为需要调用工具
                    tool_choice={"type": "none"},
                )

                elapsed     = time.monotonic() - start
                out_tokens  = response.usage.output_tokens
                in_tokens   = response.usage.input_tokens
                cache_read  = getattr(response.usage, "cache_read_input_tokens", 0)
                cache_write = getattr(response.usage, "cache_creation_input_tokens", 0)

                log.info(
                    f"完成：{topic} | 耗时 {elapsed:.1f}s | "
                    f"输入 {in_tokens} tokens"
                    f"（缓存命中 {cache_read} / 缓存写入 {cache_write}）| "
                    f"输出 {out_tokens} tokens"
                )

                # ── 内容提取（两层策略）──────────────────────────────
                # 层1：正常情况，直接从 TextBlock 提取
                text_blocks = [
                    block.text
                    for block in response.content
                    if hasattr(block, "text")
                ]

                # 层2：代理注入工具导致模型返回 ToolUseBlock（Write/TodoWrite/Task 等）
                # 此时 input 为空（{}），内容被代理拦截未传回。
                # 解法：多轮对话——伪造"工具执行失败"结果，
                # 迫使模型放弃工具调用，改为直接输出文本。
                if not text_blocks and response.stop_reason == "tool_use":
                    tool_names = [
                        getattr(b, "name", "unknown")
                        for b in response.content
                        if type(b).__name__ == "ToolUseBlock"
                    ]
                    log.warning(
                        f"检测到代理注入工具调用（{tool_names}），"
                        f"启动多轮对话兜底：{topic}"
                    )

                    # 构造多轮消息：
                    # 1. 把模型的工具调用响应原样放回 assistant 轮
                    # 2. 为每个 tool_use 伪造一个 tool_result（报错）
                    # 3. 明确要求模型以纯文本重新输出文档
                    tool_results = []
                    for block in response.content:
                        if type(block).__name__ == "ToolUseBlock":
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "is_error": True,
                                "content": (
                                    "Error: file system is not available in this environment. "
                                    "Please output the complete document content directly "
                                    "as plain text in your next response instead."
                                ),
                            })

                    fallback_response = await client.messages.create(
                        model=MODEL,
                        max_tokens=MAX_TOKENS,
                        system=[
                            {
                                "type": "text",
                                "text": system_prompt,
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                        messages=[
                            # 轮1：原始用户请求
                            {"role": "user", "content": user_prompt},
                            # 轮2：模型的工具调用（原样回传）
                            {"role": "assistant", "content": response.content},
                            # 轮3：工具执行失败 + 要求改为文本输出
                            {"role": "user",      "content": tool_results},
                        ],
                    )

                    # 从兜底响应中提取文本
                    text_blocks = [
                        block.text
                        for block in fallback_response.content
                        if hasattr(block, "text")
                    ]

                    if text_blocks:
                        fb_tokens = fallback_response.usage.output_tokens
                        log.info(f"多轮兜底成功，输出 {fb_tokens} tokens：{topic}")
                    else:
                        log.error(
                            f"多轮兜底仍无文本，放弃：{topic}，"
                            f"块类型：{[type(b).__name__ for b in fallback_response.content]}"
                        )
                        return None
                # ─────────────────────────────────────────────────────

                raw_text = "\n".join(text_blocks)

                # 防御：内容过短视为无效（小于 200 字符说明模型没有真正输出文档）
                if len(raw_text.strip()) < 200:
                    log.warning(
                        f"响应内容过短（{len(raw_text)} 字符），可能未正确生成文档：{topic}\n"
                        f"原始响应：{raw_text[:300]!r}"
                    )
                    if attempt < RETRY_TIMES:
                        log.info(f"将在 {RETRY_DELAY}s 后重试...")
                        await asyncio.sleep(RETRY_DELAY)
                        continue
                    return None

                return to_standard_markdown(raw_text, topic, doc_type)

            except anthropic.RateLimitError:
                wait = RETRY_DELAY * attempt
                log.warning(f"速率限制，{wait}s 后重试：{topic}")
                await asyncio.sleep(wait)

            except anthropic.APIStatusError as e:
                log.error(f"API 错误（{e.status_code}）：{topic} -> {e.message}")
                if attempt < RETRY_TIMES:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    log.error(f"放弃：{topic}")
                    return None

            except Exception as e:
                log.error(f"未知错误：{topic} -> {e}")
                if attempt < RETRY_TIMES:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    return None

    return None


# ─────────────────────────────────────────
# 任务调度
# ─────────────────────────────────────────
async def run_all(
    topics: list[tuple[str, str]],
    skill_content: str,
    output_dir: str,
    concurrency: int,
    dry_run: bool,
):
    """并发调度所有文档生成任务"""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # 构造系统提示词（所有任务共享，用于 Prompt Caching）
    system_prompt = build_system_prompt(skill_content)
    log.info(f"系统提示词构造完成，长度 {len(system_prompt)} 字符")

    # 过滤已完成任务（断点续跑）
    pending = [
        (topic, dtype)
        for topic, dtype in topics
        if not is_already_done(topic, output_dir)
    ]
    skipped = len(topics) - len(pending)
    if skipped:
        log.info(f"跳过已完成 {skipped} 个主题（断点续跑）")

    if not pending:
        log.info("所有主题已生成完毕。")
        return

    log.info(f"待生成 {len(pending)} 个主题，并发数 {concurrency}")

    client    = anthropic.AsyncAnthropic()
    semaphore = asyncio.Semaphore(concurrency)

    success_count = 0
    fail_list: list[str] = []

    async def process(topic: str, dtype: str):
        nonlocal success_count
        content = await generate_doc(
            client, topic, dtype, system_prompt, semaphore, dry_run
        )
        if content:
            out_path = build_output_path(topic, output_dir)
            out_path.write_text(content, encoding="utf-8")
            log.info(f"已保存：{out_path}")
            success_count += 1
        else:
            fail_list.append(topic)

    await asyncio.gather(*[process(t, d) for t, d in pending])

    log.info("=" * 50)
    log.info(f"生成完成：成功 {success_count} 个，失败 {len(fail_list)} 个")
    if fail_list:
        log.warning(f"失败主题：{fail_list}")
        fail_file = Path(output_dir) / "failed_topics.txt"
        fail_file.write_text("\n".join(fail_list), encoding="utf-8")
        log.info(f"失败列表已保存至：{fail_file}，可用 --topic 逐个重跑")


# ─────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(description="批量生成技术文档")
    parser.add_argument("--json",        default=JSON_FILE,   help="JSON 数据文件路径")
    parser.add_argument("--skill",       default=SKILL_FILE,  help="SKILL.md 路径")
    parser.add_argument("--output",      default=OUTPUT_DIR,  help="输出目录")
    parser.add_argument("--type",        default=None,        help="指定类型：技术 / 软件 / 技术点")
    parser.add_argument("--topic",       default=None,        help="只生成指定主题")
    parser.add_argument("--concurrency", default=CONCURRENCY, type=int, help="并发数")
    parser.add_argument("--dry-run",     action="store_true", help="只打印任务列表")
    return parser.parse_args()


def main():
    args = parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        log.error("请设置环境变量 ANTHROPIC_API_KEY")
        raise SystemExit(1)

    for f in [args.json, args.skill]:
        if not Path(f).exists():
            log.error(f"文件不存在：{f}")
            raise SystemExit(1)

    skill_content = load_skill(args.skill)

    if args.topic:
        with open(args.json, encoding="utf-8") as f:
            data = json.load(f)
        dtype  = next((k for k, v in data.items() if args.topic in v), "未知")
        topics = [(args.topic, dtype)]
    else:
        topics = load_topics(args.json, args.type)

    if args.dry_run:
        log.info("=== DRY-RUN 任务列表 ===")
        for topic, dtype in topics:
            log.info(f"  [{dtype}] {topic}")
        log.info(f"共 {len(topics)} 个任务")
        return

    asyncio.run(run_all(
        topics=topics,
        skill_content=skill_content,
        output_dir=args.output,
        concurrency=args.concurrency,
        dry_run=False,
    ))


if __name__ == "__main__":
    main()