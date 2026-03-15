"""
format_log.py
=============
把 claude_code_to_llm_proxy.log 中 JSON 字符串值里的 \\n 转义序列展开为真实换行符，
展开后的续行与原行保持相同缩进，方便人工阅读。

用法
----
python3 format_log.py                        # 原地覆盖 claude_code_to_llm_proxy.log
python3 format_log.py claude_code_to_llm_proxy.log               # 同上，显式指定
python3 format_log.py claude_code_to_llm_proxy.log out.log       # 写入新文件，原文件不变
"""

import sys
from pathlib import Path


def expand_line(line: str) -> str:
    """
    把一行文本中所有的 \\n（两个字符：反斜杠 + n）
    替换为真实换行符 + 与本行相同的前导空白。

    规则：
    - 只替换出现在行内容（非行首）的 \\n
    - 续行缩进 = 原行的前导空白数量
    - \\t 同理展开（可选，默认关闭）
    """
    if "\\n" not in line:
        return line

    # 计算原行前导空白
    stripped = line.lstrip()
    indent_len = len(line) - len(stripped)
    indent = " " * indent_len

    # 替换：\n → 真实换行 + 缩进
    return line.replace("\\n", "\n" + indent)


def format_log(src: Path, dst: Path) -> None:
    text = src.read_text(encoding="utf-8")

    lines = text.split("\n")
    out_lines = [expand_line(line) for line in lines]
    result = "\n".join(out_lines)

    dst.write_text(result, encoding="utf-8")
    print(f"✓ 完成：{src} → {dst}  ({len(lines)} 行处理)")


def main() -> None:
    args = sys.argv[1:]

    if len(args) == 0:
        src = dst = Path("claude_code_to_llm_proxy.log")
    elif len(args) == 1:
        src = dst = Path(args[0])
    elif len(args) == 2:
        src, dst = Path(args[0]), Path(args[1])
    else:
        print("用法: python3 format_log.py [输入文件] [输出文件]")
        sys.exit(1)

    if not src.exists():
        print(f"✗ 文件不存在: {src}")
        sys.exit(1)

    format_log(src, dst)


if __name__ == "__main__":
    main()
