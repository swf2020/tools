#!/bin/zsh

# Claude 详细上下文信息分析脚本
# 功能：显示完整的 JSON 结构和所有字段信息

PROJECT=$(pwd | sed 's/\//-/g')
LATEST="${1:-$(ls -t ~/.claude/projects/$PROJECT/*.jsonl 2>/dev/null | head -1)}"

if [[ -z "$LATEST" ]]; then
    echo "错误: 未找到会话文件"
    exit 1
fi

echo "=== Claude 详细对话分析 ==="
echo "会话文件: $LATEST"
echo "文件大小: $(ls -lh "$LATEST" | awk '{print $5}')"
echo "记录条数: $(wc -l < "$LATEST")"
echo "最后修改: $(stat -f "%Sm" "$LATEST")"
echo "================================"
echo

echo "=== 完整 JSON 记录 ==="
cat "$LATEST" | jq -C '.' | less -R

echo
echo "=== 消息类型统计 ==="
cat "$LATEST" | jq -r 'select(.type != null) | .type' | sort | uniq -c | sort -nr

echo
echo "=== 工具调用详情 ==="
cat "$LATEST" | jq -r '
select(.message.content and (.message.content | type == "array")) |
.message.content[] |
select(.type == "tool_use") |
"工具名称: " + (.name // "unknown") + "\n工具ID: " + (.id // "unknown") + "\n输入参数: " + (.input | tojson) + "\n" + "-"*30
' 2>/dev/null || echo "未发现工具调用记录"