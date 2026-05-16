#!/bin/bash

# Claude Code MCP + LLM Proxy 启动脚本
# 功能：同时启动 MCP Server代理和 LLM Proxy

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROXY_SCRIPT="$SCRIPT_DIR/claude_code_to_mcp_server_proxy.py"
LLM_PROXY_SCRIPT="$SCRIPT_DIR/claude_code_to_llm_proxy.py"

echo "======================================"
echo "Claude Code MCP + LLM Proxy 启动脚本"
echo "======================================"
echo

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误：未找到 python3，请先安装 Python 3.11+"
    exit 1
fi

echo "✅ Python 版本：$(python3 --version)"
echo

# 启动方式选择
echo "请选择启动模式："
echo "1) 仅启动 LLM Proxy (HTTP 服务器，端口 8000)"
echo "2) 仅启动 MCP Server代理 (stdio 模式)"
echo "3) 同时启动两个服务（后台运行）"
echo "4) 查看当前运行的服务"
echo "5) 停止所有相关服务"
echo

read -p "请输入选项 (1-5): " choice

case $choice in
    1)
        echo "🚀 启动 LLM Proxy..."
        echo "访问地址：http://localhost:8000"
        echo "日志文件：claude_code_to_llm_proxy.log"
        echo
        cd "$SCRIPT_DIR" && python3 "$LLM_PROXY_SCRIPT"
        ;;
    2)
        echo "🚀 启动 MCP Server代理..."
        echo "模式：stdio (通过 Claude Code MCP 配置调用)"
        echo "日志文件：claude_code_to_mcp_server_proxy.log"
        echo
        echo "⚠️  注意：此服务应该由 Claude Code 自动调用，不要手动运行！"
        echo "请确保已更新 ~/.claude.json 或 claude_desktop_config.json 配置"
        echo
        cd "$SCRIPT_DIR" && python3 "$PROXY_SCRIPT"
        ;;
    3)
        echo "🚀 同时启动两个服务..."
        echo
        
        # 启动 LLM Proxy 到后台
        echo "[1/2] 启动 LLM Proxy (后台)..."
        cd "$SCRIPT_DIR" && nohup python3 "$LLM_PROXY_SCRIPT" > /tmp/llm_proxy.log 2>&1 &
        LLM_PID=$!
        echo "✅ LLM Proxy 已启动 (PID: $LLM_PID)"
        
        # 等待 1 秒
        sleep 1
        
        # 启动 MCP Server代理到后台
        echo "[2/2] 启动 MCP Server代理 (后台)..."
        cd "$SCRIPT_DIR" && nohup python3 "$PROXY_SCRIPT" > /tmp/mcp_proxy.log 2>&1 &
        MCP_PID=$!
        echo "✅ MCP Server代理已启动 (PID: $MCP_PID)"
        
        echo
        echo "======================================"
        echo "服务状态:"
        echo "  LLM Proxy:     http://localhost:8000 (PID: $LLM_PID)"
        echo "  MCP Server:    stdio 模式 (PID: $MCP_PID)"
        echo "日志位置:"
        echo "  LLM Proxy:     claude_code_to_llm_proxy.log"
        echo "  MCP Server:    claude_code_to_mcp_server_proxy.log"
        echo
        echo "停止命令:"
        echo "  kill $LLM_PID $MCP_PID"
        echo "======================================"
        ;;
    4)
        echo "🔍 查找运行中的服务..."
        echo
        echo "LLM Proxy 进程:"
        ps aux | grep "claude_code_to_llm_proxy.py" | grep -v grep || echo "  未运行"
        echo
        echo "MCP Server 进程:"
        ps aux | grep "claude_code_to_mcp_server_proxy.py" | grep -v grep || echo "  未运行"
        ;;
    5)
        echo "🛑 停止所有服务..."
        pkill -f "claude_code_to_llm_proxy.py"
        pkill -f "claude_code_to_mcp_server_proxy.py"
        echo "✅ 所有服务已停止"
        ;;
    *)
        echo "❌ 无效选项"
        exit 1
        ;;
esac
