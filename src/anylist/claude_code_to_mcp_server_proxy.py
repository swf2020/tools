"""
Claude Code ↔ GitNexus MCP stdio 代理
======================================
作用：拦截 Claude Code 与 gitnexus mcp 之间的全部 JSON-RPC 2.0 报文，
      记录到 claude_code_to_mcp_server_proxy.log，同时完全透传，不破坏任何功能。

使用方式
---------
1. 确认 gitnexus 已安装并已执行过 `gitnexus analyze`
2. 在 Claude Code MCP 配置中，把原 gitnexus mcp 命令改为本代理：

   原始配置（~/.claude.json 或 claude_desktop_config.json）：
     {
       "mcpServers": {
         "gitnexus": {
           "command": "npx",
           "args": ["gitnexus", "mcp"]
         }
       }
     }

   改为：
     {
       "mcpServers": {
         "gitnexus": {
           "command": "python3",
           "args": ["/path/to/claude_code_to_mcp_server_proxy.py"]
         }
       }
     }

3. 运行：代理自动 spawn gitnexus mcp，日志写入同目录 claude_code_to_mcp_server_proxy.log

环境变量
---------
GITNEXUS_CMD   上游命令，默认 "npx"
GITNEXUS_ARGS  传给命令的参数，默认 "gitnexus mcp"
MCP_LOG_FILE   日志文件路径，默认 "claude_code_to_mcp_server_proxy.log"（脚本同目录）
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path


# ──────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).parent

GITNEXUS_CMD  = os.environ.get("GITNEXUS_CMD", "npx").split()
GITNEXUS_ARGS = os.environ.get("GITNEXUS_ARGS", "gitnexus mcp").split()
LOG_FILE      = os.environ.get("MCP_LOG_FILE", str(_SCRIPT_DIR / "claude_code_to_mcp_server_proxy.log"))


# ──────────────────────────────────────────────
# JSON-RPC 报文分析器
# ──────────────────────────────────────────────

# MCP 核心方法中文说明
_METHOD_LABELS: dict[str, str] = {
    "initialize":                "握手初始化",
    "notifications/initialized": "初始化完成通知",
    "ping":                      "心跳",
    "tools/list":                "获取工具列表",
    "tools/call":                "调用工具",
    "resources/list":            "获取资源列表",
    "resources/read":            "读取资源",
    "resources/templates/list":  "获取资源模板",
    "prompts/list":              "获取提示词列表",
    "prompts/get":               "获取提示词",
    "logging/setLevel":          "设置日志级别",
    "notifications/progress":    "进度通知",
    "notifications/message":     "服务端消息通知",
    "notifications/cancelled":   "取消通知",
}

def _analyze(msg: dict) -> str:
    """把 JSON-RPC 消息提炼成一行人类可读摘要。"""
    if not isinstance(msg, dict):
        return "[非对象报文]"

    method = msg.get("method", "")
    msg_id = msg.get("id")
    has_result = "result" in msg
    has_error  = "error" in msg

    # ── 请求 / 通知 ──────────────────────────────
    if method:
        label = _METHOD_LABELS.get(method, method)
        params = msg.get("params", {})
        detail = ""

        if method == "tools/call":
            name = params.get("name", "?")
            args = params.get("arguments", {})
            # 摘取 arguments 里最具代表性的字段
            arg_str = ", ".join(f"{k}={repr(v)[:40]}" for k, v in list(args.items())[:3])
            detail = f"  →  工具={name}({arg_str})"

        elif method == "resources/read":
            uri = params.get("uri", "?")
            detail = f"  →  uri={uri}"

        elif method == "initialize":
            ci = params.get("clientInfo", {})
            detail = f"  →  client={ci.get('name','?')} v{ci.get('version','?')}"

        id_str = f" [id={msg_id}]" if msg_id is not None else ""
        return f"{label}{id_str}{detail}"

    # ── 响应 ─────────────────────────────────────
    if has_result:
        result = msg["result"]
        detail = ""
        if isinstance(result, dict):
            # tools/list 响应
            if "tools" in result:
                names = [t.get("name", "?") for t in result["tools"]]
                detail = f"  →  {len(names)} 个工具: {', '.join(names)}"
            # initialize 响应
            elif "serverInfo" in result:
                si = result["serverInfo"]
                detail = f"  →  server={si.get('name','?')} v{si.get('version','?')}"
            # tools/call 响应
            elif "content" in result:
                contents = result["content"]
                total_chars = sum(len(c.get("text", "")) for c in contents if isinstance(c, dict))
                detail = f"  →  {len(contents)} 个内容块, {total_chars} 字符"
        return f"响应 [id={msg_id}]{detail}"

    if has_error:
        err = msg["error"]
        code = err.get("code", "?")
        msg_text = err.get("message", "?")
        return f"错误响应 [id={msg_id}] code={code} msg={msg_text}"

    return "[未知报文结构]"


# ──────────────────────────────────────────────
# 并发安全日志器
# ──────────────────────────────────────────────

class MCPLogger:
    """
    asyncio.Lock + asyncio.to_thread 实现的协程安全日志器。
    所有写操作都不阻塞事件循环。
    注意：stdout 被 MCP stdio 协议占用，日志只写文件 + stderr。
    """

    def __init__(self, log_file: str):
        self.log_file = log_file
        self._lock = asyncio.Lock()
        # 初始化日志文件
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"{'='*60}\n")
            f.write(f"  MCP Proxy 启动  {datetime.now():%Y-%m-%d %H:%M:%S}\n")
            f.write(f"  上游命令: {' '.join(GITNEXUS_CMD + GITNEXUS_ARGS)}\n")
            f.write(f"{'='*60}\n\n")

    @staticmethod
    def _ts() -> str:
        return datetime.now().strftime("%H:%M:%S.%f")[:-3]

    def _build_entry(self, direction: str, raw: bytes, msg, summary: str) -> str:
        ts = self._ts()
        arrow = "→" if "Claude" in direction else "←"
        lines = [
            f"[{ts}] {arrow} {direction}",
            f"  摘要：{summary}",
        ]
        # 完整 JSON（格式化，不截断）
        if isinstance(msg, (dict, list)):
            pretty = json.dumps(msg, ensure_ascii=False, indent=2)
            lines.append("  原文:")
            for line in pretty.splitlines():
                lines.append("    " + line)
        else:
            # 非 JSON 数据也完整打印
            full_text = raw.decode(errors='replace')
            lines.append(f"  原文(非 JSON): {full_text}")
        lines.append("─" * 60)
        return "\n".join(lines) + "\n"

    def _sync_append(self, text: str) -> None:
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(text)
        # 同时打到 stderr（不干扰 stdout MCP 协议）
        print(text, file=sys.stderr, end="", flush=True)

    async def log_message(self, direction: str, raw: bytes, msg) -> None:
        summary = _analyze(msg) if isinstance(msg, dict) else "[非 JSON 数据]"
        entry = self._build_entry(direction, raw, msg, summary)
        async with self._lock:
            await asyncio.to_thread(self._sync_append, entry)

    async def log_event(self, text: str) -> None:
        ts = self._ts()
        entry = f"[{ts}] *** {text} ***\n"
        async with self._lock:
            await asyncio.to_thread(self._sync_append, entry)


# ──────────────────────────────────────────────
# 双向透传协程
# ──────────────────────────────────────────────

async def pipe(
    reader: asyncio.StreamReader,
    write_fn,           # 同步写函数，接收 bytes
    drain_fn,           # 可 await 的 drain
    direction: str,
    logger: MCPLogger,
    stop_event: asyncio.Event,
) -> None:
    """
    从 reader 逐行读取 newline-delimited JSON，
    记录日志后转发给 write_fn / drain_fn。
    """
    while not stop_event.is_set():
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout=5.0)
        except asyncio.TimeoutError:
            continue  # 超时重试，让 stop_event 有机会被检查
        except Exception as e:
            await logger.log_event(f"{direction} 读取异常: {e}")
            break

        if not raw:  # EOF
            await logger.log_event(f"{direction} 连接关闭 (EOF)")
            stop_event.set()
            break

        # 解析 JSON
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            msg = raw.decode(errors="replace").strip()

        # 异步记录（不阻塞转发）
        asyncio.ensure_future(logger.log_message(direction, raw, msg))

        # 转发
        try:
            write_fn(raw)
            await drain_fn()
        except Exception as e:
            await logger.log_event(f"{direction} 转发失败: {e}")
            stop_event.set()
            break


async def pipe_stderr(
    reader: asyncio.StreamReader,
    logger: MCPLogger,
    stop_event: asyncio.Event,
) -> None:
    """把 gitnexus mcp 的 stderr 转发到我们的 stderr，并记录日志。"""
    while not stop_event.is_set():
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout=5.0)
        except asyncio.TimeoutError:
            continue
        except Exception:
            break
        if not raw:
            break
        text = raw.decode(errors="replace").rstrip()
        await logger.log_event(f"[GitNexus stderr] {text}")


# ──────────────────────────────────────────────
# stdout 包装（让 asyncio 能 drain）
# ──────────────────────────────────────────────

class StdoutWriter:
    """把 sys.stdout.buffer 包成带 drain() 的对象，供 pipe() 统一调用。"""

    def write(self, data: bytes) -> None:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()

    async def drain(self) -> None:
        pass  # 同步 flush 已在 write 中完成


# ──────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────

async def main() -> None:
    logger = MCPLogger(LOG_FILE)
    await logger.log_event(f"代理启动，spawn: {' '.join(GITNEXUS_CMD + GITNEXUS_ARGS)}")

    # ── 启动 gitnexus mcp 子进程 ────────────────
    try:
        proc = await asyncio.create_subprocess_exec(
            *GITNEXUS_CMD,
            *GITNEXUS_ARGS,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        await logger.log_event(f"启动失败: {e}  —  请确认 GITNEXUS_CMD 正确")
        sys.exit(1)

    await logger.log_event(f"gitnexus mcp 已启动，PID={proc.pid}")

    # ── 将自身 stdin 接入 asyncio ───────────────
    loop = asyncio.get_event_loop()
    stdin_reader = asyncio.StreamReader(limit=2**20)   # 1 MB 缓冲
    proto = asyncio.StreamReaderProtocol(stdin_reader)
    await loop.connect_read_pipe(lambda: proto, sys.stdin.buffer)

    stdout_writer = StdoutWriter()
    stop_event    = asyncio.Event()

    # ── 并发运行三条管道 ────────────────────────
    #   Claude Code  →  gitnexus mcp   （stdin → subprocess stdin）
    #   gitnexus mcp →  Claude Code    （subprocess stdout → stdout）
    #   gitnexus mcp stderr → 本代理 stderr
    await asyncio.gather(
        pipe(
            reader     = stdin_reader,
            write_fn   = proc.stdin.write,
            drain_fn   = proc.stdin.drain,
            direction  = "Claude Code → GitNexus",
            logger     = logger,
            stop_event = stop_event,
        ),
        pipe(
            reader     = proc.stdout,
            write_fn   = stdout_writer.write,
            drain_fn   = stdout_writer.drain,
            direction  = "GitNexus → Claude Code",
            logger     = logger,
            stop_event = stop_event,
        ),
        pipe_stderr(proc.stderr, logger, stop_event),
        return_exceptions=True,
    )

    # ── 清理子进程 ──────────────────────────────
    try:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=5.0)
    except Exception:
        proc.kill()

    await logger.log_event(f"代理退出，gitnexus mcp 返回码={proc.returncode}")


if __name__ == "__main__":
    # Python 3.12+ Windows 需要显式设置 ProactorEventLoop，Linux/macOS 默认可用
    # 只启动 MCP Server 代理，LLM Proxy 应该单独运行
    asyncio.run(main())
