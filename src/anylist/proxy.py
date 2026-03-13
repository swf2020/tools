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