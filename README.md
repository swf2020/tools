# tools
daliy tools

[1、半自动化发布CSDN博客的脚本](src/auto_save_and_publish_csdn_blog)

**依赖软件**

```
pyperclip==1.9.0
selenium==4.26.1
```

提前配置好要读取的markdown文件本地地址，csdn的文章配置项， 启动脚本之后，通过微信扫码｜app扫码｜第三方登录的方式登录到CSDN，
然后会代替人工自动处理整个流程

______________________________________________________________________
[2、claude code与大模型调用日志分析工具](src/anylist)

**依赖软件**

```
fastapi==0.109.2
uvicorn==0.27.1
httpx==0.26.0
```
## **执行步骤**
### 1. 配置~/.claude/setting.json 
> "ANTHROPIC_BASE_URL": "http://127.0.0.1:8000",
> "ANTHROPIC_MODEL": "qwen3-coder-next",
> "ANTHROPIC_DEFAULT_SONNET_MODEL": "qwen3-coder-plus",
> "ANTHROPIC_DEFAULT_HAIKU_MODEL": "qwen3.5-plus",

### 2. 运行src/anylist/proxy.py
> python proxy.py

### 3. 在当前项目运行 claude

### 4. 在claude对话框输入内容

### 5. 格式化claude code 当前session的context
> zsh src/anylist/claude_code_context/claude_full_context.sh > src/anylist/claude_code_context/claude_code_context.log
