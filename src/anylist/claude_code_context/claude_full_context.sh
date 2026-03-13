#!/bin/zsh

# Claude 完整上下文信息提取脚本
# 功能：完整记录 Claude 对话的全部上下文信息，包括工具调用、完整消息内容等

PROJECT=$(pwd | sed 's/\//-/g')
LATEST="${1:-$(ls -t ~/.claude/projects/$PROJECT/*.jsonl 2>/dev/null | head -1)}"

# 检查文件是否存在
if [[ -z "$LATEST" ]]; then
    echo "错误: 未找到会话文件"
    echo "请确保在正确的项目目录下执行此脚本"
    exit 1
fi

echo "=== Claude 完整对话上下文 ==="
echo "会话文件: $LATEST"
echo "生成时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================"
echo

# 使用 jq 完整解析并显示所有信息
cat "$LATEST" | jq -r '
def format_timestamp:
  if .timestamp then
    "[" + (.timestamp[0:19] | gsub("T";" ")) + "]"
  else
    "[未知时间]"
  end;

def format_message_type:
  (.type // "unknown" | ascii_upcase);

def format_content_array:
  if type == "array" then
    map(
      if .type == "text" then
        .text
      elif .type == "tool_use" then
        "[工具调用] " + (.name // "unknown") + ": " + (.input | tostring)
      elif .type == "tool_result" then
        "[工具结果] ID: " + (.tool_use_id // "unknown") + "\n结果: " +
        (
          if .content | type == "array" then
            .content | map(if .text then .text else . end) | join("\n")
          else
            .content // "" | tostring
          end
        )
      else
        "[类型: " + (.type // "unknown") + "] " +
        (
          if .text then .text
          elif .content then
            if .content | type == "array" then
              .content | map(if .text then .text else . end) | join("\n")
            else
              .content | tostring
            end
          else ""
          end
        )
      end
    ) | join("\n---\n")
  else
    tostring
  end;

def format_user_content:
  if .message.content then
    if .message.content | type == "string" then
      .message.content
    elif .message.content | type == "array" then
      .message.content | format_content_array
    else
      .message.content | tostring
    end
  else
    "[空内容]"
  end;

def format_assistant_content:
  if .message.content then
    if .message.content | type == "string" then
      .message.content
    elif .message.content | type == "array" then
      .message.content | format_content_array
    else
      .message.content | tostring
    end
  else
    "[无回复内容]"
  end;

def format_system_content:
  if .message.content then
    .message.content | tostring
  else
    "[系统消息]"
  end;

# 主处理逻辑
select(.type != null) |
format_timestamp + " " + format_message_type + ":\n" +
(
  if .type == "user" then
    format_user_content
  elif .type == "assistant" then
    format_assistant_content
  elif .type == "system" then
    format_system_content
  else
    "[未知类型: " + (.type // "null") + "] 内容: " + (.message.content // "" | tostring)
  end
) + "\n" + ("=" * 50) + "\n"
'