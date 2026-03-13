import json
import os
import httpx
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from starlette.responses import Response

# ──────────────────────────────────────────────
# 配置区 —— 按需修改
# ──────────────────────────────────────────────

UPSTREAM = "https://coding.dashscope.aliyuncs.com/apps/anthropic"
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "sk-sp-7b3a3e020bd1454fae26f689651daf16")


# ──────────────────────────────────────────────
# Logger（并发安全版本）
#
# 修复点：
#   1. threading.Lock → asyncio.Lock，不阻塞事件循环
#   2. 文件 I/O 通过 asyncio.to_thread 移出事件循环线程
#   3. round_count 读写统一在同一个 asyncio.Lock 保护内完成
#   4. 去除冗余的二次加锁
# ──────────────────────────────────────────────

class AppLogger:
    def __init__(self, log_file: str = "llm.log"):
        self.log_file = log_file
        self.round_count = 0
        # asyncio.Lock：协程安全，不阻塞事件循环
        self._lock = asyncio.Lock()
        # 启动时清空日志文件（同步，仅执行一次）
        with open(self.log_file, "w") as f:
            f.write("")

    @staticmethod
    def get_timestamp() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async def increment_round(self) -> int:
        """原子递增并返回当前轮次。"""
        async with self._lock:
            self.round_count += 1
            return self.round_count

    def _format_plain(self, message: str) -> str:
        return f"[{self.get_timestamp()}] {message}\n"

    def _format_round(self, message: str, round_num: int) -> str:
        return f"{{{self.get_timestamp()}}}-第{round_num}轮-{message}\n"

    def _format_json_round(self, data: dict | list, message: str, round_num: int) -> str:
        pretty = json.dumps(data, ensure_ascii=False, indent=2)
        return f"{{{self.get_timestamp()}}}-第{round_num}轮-{message}\n{pretty}\n"

    async def _write(self, text: str) -> None:
        """
        将日志写入文件。
        asyncio.Lock 保证多协程不会交错写入；
        asyncio.to_thread 将阻塞的文件 I/O 移到线程池，不卡事件循环。
        """
        async with self._lock:
            await asyncio.to_thread(self._sync_append, text)
        print(text, end="")

    def _sync_append(self, text: str) -> None:
        """纯同步文件追加，只在 to_thread 的线程中执行。"""
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(text)

    async def log(self, message: str) -> None:
        await self._write(self._format_plain(message))

    async def log_with_round(self, message: str, round_num: int) -> None:
        await self._write(self._format_round(message, round_num))

    async def log_json_with_round(
            self, data: dict | list, message: str, round_num: int
    ) -> None:
        await self._write(self._format_json_round(data, message, round_num))


# ──────────────────────────────────────────────
# 全局共享 httpx.AsyncClient（连接池复用）
#
# 修复点：原代码每次请求都 async with httpx.AsyncClient()，
# 会频繁创建/销毁连接池，高并发下开销大。
# 用 lifespan 在应用启动/关闭时统一管理。
# ──────────────────────────────────────────────

http_client: httpx.AsyncClient | None = None

def is_title_generation(body: dict) -> bool:
    """
    识别两种标题生成请求：
    1. 会话结束时的 "Please write a 5-10 word title..." (user message)
    2. 每轮对话后的话题检测 "Analyze if this message indicates a new conversation topic" (system)
    """
    try:
        # ── 模式一：检查 user message 内容 ──────────
        messages = body.get("messages", [])
        if len(messages) == 1:
            content = messages[0].get("content", "")
            text = content if isinstance(content, str) else (
                next((b.get("text", "") for b in content
                      if isinstance(b, dict) and b.get("type") == "text"), "")
            )
            if "Please write a 5-10 word title" in text:
                return True

        # ── 模式二：检查 system prompt 内容 ─────────
        system = body.get("system", [])
        for block in system:
            if isinstance(block, dict) and block.get("type") == "text":
                if "Analyze if this message indicates a new conversation topic" in block.get("text", ""):
                    return True

        return False
    except Exception:
        return False

def make_title_mock(body: dict) -> dict:
    """根据请求类型返回对应的 mock 响应"""
    system = body.get("system", [])
    is_topic_detection = any(
        "Analyze if this message indicates a new conversation topic" in b.get("text", "")
        for b in system if isinstance(b, dict)
    )

    if is_topic_detection:
        # 模式二：返回"不是新话题"，不触发标题更新
        reply_text = '{"isNewTopic": false, "title": null}'
    else:
        # 模式一：返回一个固定标题
        reply_text = "New Conversation"

    return {
        "id": f"mock_title_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": reply_text}],
        "model": body.get("model", "mock"),
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(timeout=None)
    yield
    await http_client.aclose()


app = FastAPI(title="Claude Code ↔ DashScope Proxy", lifespan=lifespan)
logger = AppLogger("llm.log")

# ──────────────────────────────────────────────
# 构造上游请求头
# ──────────────────────────────────────────────

PASSTHROUGH_HEADERS = {"anthropic-version", "anthropic-beta", "content-type", "accept"}


def build_upstream_headers(request: Request) -> dict:
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() in PASSTHROUGH_HEADERS
    }
    headers["Authorization"] = f"Bearer {DASHSCOPE_API_KEY}"
    return headers


# ──────────────────────────────────────────────
# /v1/messages
# ──────────────────────────────────────────────

@app.post("/v1/messages")
async def proxy_messages(request: Request):
    body_bytes = await request.body()
    try:
        body = json.loads(body_bytes)
    except Exception:
        body = {}

    # ── 拦截标题生成请求，直接 mock 返回 ──────────
    if is_title_generation(body):
        # await logger.log("⚡ 拦截标题生成请求，mock 返回")
        return Response(
            content=json.dumps(make_title_mock(body)).encode(),
            status_code=200,
            headers={"content-type": "application/json"},
        )

    round_num = await logger.increment_round()

    # ── 解析并记录请求 ──────────────────────────
    try:
        body = json.loads(body_bytes)
        request_info: dict = {
            "请求轮次": f"第{round_num}轮",
            "时间戳": logger.get_timestamp(),
            "原始请求": body,
        }
        if isinstance(body, dict):
            for key, label in [
                ("model", "模型"),
                ("max_tokens", "最大token数"),
                ("temperature", "温度参数"),
            ]:
                if key in body:
                    request_info[label] = body[key]
            if "messages" in body:
                request_info["消息数量"] = len(body["messages"])
        await logger.log_json_with_round(request_info, "模型请求完整信息", round_num)
    except Exception as e:
        error_info = {
            "请求轮次": f"第{round_num}轮",
            "时间戳": logger.get_timestamp(),
            "错误信息": str(e),
            "原始数据": body_bytes.decode(errors="replace"),
        }
        await logger.log_json_with_round(error_info, "模型请求解析失败", round_num)
        body = {}

    # ── 强制非流式，转发上游 ────────────────────
    modified_body = {**body, "stream": False} if isinstance(body, dict) else {}
    modified_body_bytes = (
        json.dumps(modified_body, ensure_ascii=False).encode()
        if modified_body
        else body_bytes
    )

    upstream_headers = build_upstream_headers(request)
    upstream_resp = await http_client.post(
        f"{UPSTREAM}/v1/messages",
        content=modified_body_bytes,
        headers=upstream_headers,
    )

    # ── 记录响应 ────────────────────────────────
    response_summary: dict = {
        "请求轮次": f"第{round_num}轮",
        "时间戳": logger.get_timestamp(),
        "上游响应状态码": upstream_resp.status_code,
        "响应内容长度": f"{len(upstream_resp.content)} 字节",
    }

    if upstream_resp.status_code >= 400:
        response_summary["错误详情"] = upstream_resp.text
        await logger.log_json_with_round(response_summary, "模型响应错误", round_num)
    else:
        try:
            response_data = upstream_resp.json()
            response_summary["完整响应内容"] = response_data
            if isinstance(response_data, dict):
                for key, label in [
                    ("id", "响应ID"),
                    ("model", "实际使用模型"),
                    ("usage", "Token用量"),
                    ("role", "角色"),
                    ("stop_reason", "停止原因"),
                ]:
                    if key in response_data:
                        response_summary[label] = response_data[key]
                if "content" in response_data:
                    response_summary["响应内容概要"] = (
                        f"包含{len(response_data['content'])}个内容块"
                    )
            await logger.log_json_with_round(response_summary, "模型完整响应", round_num)
        except Exception as e:
            response_summary["解析错误"] = str(e)
            response_summary["原始响应文本"] = upstream_resp.text
            await logger.log_json_with_round(response_summary, "模型响应解析失败", round_num)

    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers={
            "content-type": upstream_resp.headers.get(
                "content-type", "application/json"
            )
        },
    )


# ──────────────────────────────────────────────
# 透传其余 Anthropic 端点
# ──────────────────────────────────────────────

@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_other(request: Request, path: str):
    body_bytes = await request.body()
    upstream_headers = build_upstream_headers(request)

    upstream_resp = await http_client.request(
        method=request.method,
        url=f"{UPSTREAM}/v1/{path}",
        content=body_bytes,
        headers=upstream_headers,
        params=dict(request.query_params),
    )

    await logger.log(f"[passthrough] {request.method} /v1/{path} → {upstream_resp.status_code}")
    if upstream_resp.status_code >= 400:
        await logger.log(f"[upstream error body] {upstream_resp.text}")

    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers={
            "content-type": upstream_resp.headers.get(
                "content-type", "application/json"
            )
        },
    )


# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)