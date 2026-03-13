import json
import os
import httpx
from datetime import datetime
from fastapi import FastAPI, Request
from starlette.responses import StreamingResponse, Response

# ──────────────────────────────────────────────
# 配置区 —— 按需修改
# ──────────────────────────────────────────────

UPSTREAM = "https://coding.dashscope.aliyuncs.com/apps/anthropic"
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "sk-sp-xxx")


# ──────────────────────────────────────────────
# Logger
# ──────────────────────────────────────────────

class AppLogger:
    def __init__(self, log_file="llm.log"):
        self.log_file = log_file
        self.round_count = 0
        with open(self.log_file, "w") as f:
            f.write("")
    
    def get_timestamp(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def increment_round(self):
        self.round_count += 1
        return self.round_count
    
    def log(self, message: str):
        timestamp = self.get_timestamp()
        formatted_message = f"[{timestamp}] {message}"
        with open(self.log_file, "a") as f:
            f.write(formatted_message + "\n")
        print(formatted_message)
    
    def log_with_round(self, message: str, round_num: int = None):
        if round_num is None:
            round_num = self.round_count
        timestamp = self.get_timestamp()
        formatted_message = f"{{{timestamp}}}-第{round_num}轮-{message}"
        with open(self.log_file, "a") as f:
            f.write(formatted_message + "\n")
        print(formatted_message)
    
    def log_json_with_round(self, data: dict | list, message: str, round_num: int = None):
        if round_num is None:
            round_num = self.round_count
        timestamp = self.get_timestamp()
        pretty = json.dumps(data, ensure_ascii=False, indent=2)
        formatted_message = f"{{{timestamp}}}-第{round_num}轮-{message}\n{pretty}"
        with open(self.log_file, "a") as f:
            f.write(formatted_message + "\n")
        print(formatted_message)


app = FastAPI(title="Claude Code ↔ DashScope Proxy")
logger = AppLogger("llm.log")


# ──────────────────────────────────────────────
# 构造上游请求头
#
# 关键差异：
#   Claude Code 发出：  x-api-key: <anthropic-key>
#   DashScope 需要：    Authorization: Bearer <dashscope-key>
# ──────────────────────────────────────────────

PASSTHROUGH_HEADERS = {"anthropic-version", "anthropic-beta", "content-type", "accept"}


def build_upstream_headers(request: Request) -> dict:
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() in PASSTHROUGH_HEADERS
    }
    # 用 DashScope 的 Key 替换 Anthropic 原生的 x-api-key
    headers["Authorization"] = f"Bearer {DASHSCOPE_API_KEY}"
    return headers


# ──────────────────────────────────────────────
# /v1/messages  —  流式 & 非流式均支持
# ──────────────────────────────────────────────

@app.post("/v1/messages")
async def proxy_messages(request: Request):
    body_bytes = await request.body()
    
    # 增加轮次计数
    round_num = logger.increment_round()

    try:
        body = json.loads(body_bytes)
        # 收集请求信息用于一次性打印
        request_info = {
            "请求轮次": f"第{round_num}轮",
            "时间戳": logger.get_timestamp(),
            "原始请求": body
        }
        if isinstance(body, dict):
            if 'model' in body:
                request_info["模型"] = body['model']
            if 'messages' in body:
                request_info["消息数量"] = len(body['messages'])
            if 'max_tokens' in body:
                request_info["最大token数"] = body['max_tokens']
            if 'temperature' in body:
                request_info["温度参数"] = body['temperature']
        logger.log_json_with_round(request_info, "模型请求完整信息", round_num)
    except Exception as e:
        error_info = {
            "请求轮次": f"第{round_num}轮",
            "时间戳": logger.get_timestamp(),
            "错误信息": str(e),
            "原始数据": body_bytes.decode()
        }
        logger.log_json_with_round(error_info, "模型请求解析失败", round_num)
        body = {}

    is_stream = body.get("stream", False)
    upstream_headers = build_upstream_headers(request)
    upstream_url = f"{UPSTREAM}/v1/messages"

    # ── 统一处理所有响应为非流式 ──────────────────────────────
    # 强制将所有请求转换为非流式处理
    modified_body = body.copy() if isinstance(body, dict) else {}
    if 'stream' in modified_body:
        modified_body['stream'] = False
    
    modified_body_bytes = json.dumps(modified_body, ensure_ascii=False).encode() if isinstance(modified_body, dict) else body_bytes

    # ── 统一的非流式响应处理 ────────────────────────────
    async with httpx.AsyncClient(timeout=None) as client:
        upstream_resp = await client.post(
            upstream_url,
            content=modified_body_bytes,
            headers=upstream_headers,
        )

    # 收集完整的响应信息用于格式化打印
    response_summary = {
        "请求轮次": f"第{round_num}轮",
        "时间戳": logger.get_timestamp(),
        "上游响应状态码": upstream_resp.status_code,
        "响应头信息": dict(upstream_resp.headers),
        "响应内容长度": f"{len(upstream_resp.content)} 字节"
    }

    if upstream_resp.status_code >= 400:
        response_summary["错误详情"] = upstream_resp.text
        logger.log_json_with_round(response_summary, "模型响应错误", round_num)
    else:
        try:
            # 解析并格式化完整的响应内容
            response_data = upstream_resp.json()
            response_summary["完整响应内容"] = response_data
            
            # 提取关键信息用于快速查看
            if isinstance(response_data, dict):
                if 'id' in response_data:
                    response_summary["响应ID"] = response_data['id']
                if 'model' in response_data:
                    response_summary["实际使用模型"] = response_data['model']
                if 'usage' in response_data:
                    response_summary["Token用量"] = response_data['usage']
                if 'content' in response_data:
                    response_summary["响应内容概要"] = f"包含{len(response_data['content'])}个内容块"
                if 'role' in response_data:
                    response_summary["角色"] = response_data['role']
                if 'stop_reason' in response_data:
                    response_summary["停止原因"] = response_data['stop_reason']
                
            logger.log_json_with_round(response_summary, "模型完整响应", round_num)

        except Exception as e:
            response_summary["解析错误"] = str(e)
            response_summary["原始响应文本"] = upstream_resp.text
            logger.log_json_with_round(response_summary, "模型响应解析失败", round_num)

    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers={"content-type": upstream_resp.headers.get("content-type", "application/json")},
    )


# ──────────────────────────────────────────────
# 透传其余 Anthropic 端点
# ──────────────────────────────────────────────

@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_other(request: Request, path: str):
    body_bytes = await request.body()
    upstream_headers = build_upstream_headers(request)

    async with httpx.AsyncClient(timeout=None) as client:
        upstream_resp = await client.request(
            method=request.method,
            url=f"{UPSTREAM}/v1/{path}",
            content=body_bytes,
            headers=upstream_headers,
            params=dict(request.query_params),
        )

    logger.log(f"[passthrough] {request.method} /v1/{path} → {upstream_resp.status_code}")
    if upstream_resp.status_code >= 400:
        logger.log(f"[upstream error body] {upstream_resp.text}")

    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers={"content-type": upstream_resp.headers.get("content-type", "application/json")},
    )


# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
