# Claude 上下文信息提取工具集

## 概述
这是一套用于完整提取和分析 Claude 对话上下文信息的工具脚本，解决了原脚本只能显示部分信息的问题。

## 脚本功能对比

### 原始脚本问题
- ❌ 只显示前120个字符，信息被截断
- ❌ 忽略工具调用等重要信息
- ❌ 格式过于简化，丢失原始结构

### 改进后的脚本

#### 1. claude_full_context.sh - 完整上下文提取
```bash
./claude_full_context.sh [可选的JSONL文件路径]
```
**特点：**
- ✅ 完整显示所有消息内容，无截断
- ✅ 专门处理工具调用信息
- ✅ 区分不同类型的消息（用户、助手、系统）
- ✅ 清晰的时间戳标记
- ✅ 结构化的输出格式

#### 2. claude_detailed_context.sh - 详细分析
```bash
./claude_detailed_context.sh [可选的JSONL文件路径]
```
**特点：**
- ✅ 显示完整的原始 JSON 数据
- ✅ 提供消息类型统计
- ✅ 专门的工具调用详情分析
- ✅ 文件基本信息展示

## 使用示例

### 基本使用
```bash
# 在包含 Claude 会话的项目目录下执行
cd /path/to/your/project
~/Desktop/workspace/tools/claude_full_context.sh
```

### 指定特定文件
```bash
~/Desktop/workspace/tools/claude_full_context.sh ~/.claude/projects/my-project/session_20260313.jsonl
```


## 输出示例

### 完整上下文脚本输出格式：
```
=== Claude 完整对话上下文 ===
会话文件: /Users/username/.claude/projects/my-project/session.jsonl
生成时间: 2026-03-13 14:30:25
================================

[2026-03-13 14:25:10] USER:
你好，请帮我分析这段代码

[2026-03-13 14:25:12] ASSISTANT:
好的，我来帮您分析这段代码...

[工具调用] search_codebase
输入参数: {"query": "authentication logic", "key_words": "auth,login"}

---分割线---

[工具结果] ID: call_123456
结果: 找到了相关的认证逻辑代码...
==================================================
```

## 技术特性

### 支持的消息类型
- **User Messages**: 用户输入的完整内容
- **Assistant Messages**: AI助手的完整回复
- **System Messages**: 系统级消息
- **Tool Calls**: 工具调用的详细信息
- **Tool Results**: 工具执行结果

### 特殊处理
- 自动识别和格式化工具有调用
- 完整保留 JSON 参数结构
- 时间戳标准化处理
- 错误处理和边界情况检测

## 依赖要求
- `jq` - JSON 处理工具
- `zsh` - 脚本执行环境
- Claude 会话文件（JSONL 格式）

## 注意事项
1. 确保在正确的项目目录下执行脚本
2. Claude 会话文件需要是标准的 JSONL 格式
3. 部分功能可能需要较新的 jq 版本支持
4. 大型会话文件建议使用交互式模式避免输出过多

## 故障排除
如果遇到问题，请检查：
1. 是否安装了 jq 工具：`which jq`
2. Claude 会话文件是否存在：`ls ~/.claude/projects/*/*.jsonl`
3. 文件权限是否正确：`ls -la ~/.claude/projects/*/*.jsonl`