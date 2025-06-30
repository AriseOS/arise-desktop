# BaseApp CLI 设计文档

## 概述

BaseApp CLI 是 BaseApp 的命令行工具，为开发者和高级用户提供快速、高效的 Agent 管理和交互功能。CLI 工具遵循 Unix 哲学，提供简洁明了的命令接口。

### 设计目标

1. **易用性**：直观的命令结构和丰富的帮助信息
2. **高效性**：快速启动、低延迟的命令响应
3. **完整性**：覆盖所有核心功能的命令行操作
4. **友好性**：良好的错误提示和用户反馈

## 命令架构

### 命令层次结构

```
baseapp                          # 主命令
├── start                        # 启动相关
│   ├── --port <port>            # 指定端口
│   ├── --host <host>            # 指定主机
│   ├── --config <file>          # 指定配置文件
│   └── --daemon                 # 后台运行
├── stop                         # 停止应用
├── restart                      # 重启应用
├── status                       # 状态查看
│   ├── --json                   # JSON 格式输出
│   └── --verbose                # 详细信息
├── config                       # 配置管理
│   ├── show [key]               # 显示配置
│   ├── set <key> <value>        # 设置配置
│   ├── unset <key>              # 删除配置
│   ├── edit                     # 编辑配置文件
│   └── validate                 # 验证配置
├── chat                         # 对话功能
│   ├── interactive              # 交互式对话
│   ├── send <message>           # 发送消息
│   ├── history [session_id]     # 查看历史
│   └── clear [session_id]       # 清理历史
├── logs                         # 日志管理
│   ├── show                     # 显示日志
│   │   ├── --level <level>      # 日志级别
│   │   ├── --tail <n>           # 显示最后n行
│   │   └── --follow             # 实时跟踪
│   └── clear                    # 清理日志
├── agent                        # Agent 管理
│   ├── info                     # Agent 信息
│   ├── tools                    # 工具列表
│   └── memory                   # 内存状态
│       ├── stats                # 内存统计
│       └── clear                # 清理内存
└── version                      # 版本信息
    ├── --check                  # 检查更新
    └── --json                   # JSON 格式输出
```

## 核心命令设计

### 1. 应用管理命令

#### `baseapp start` - 启动应用

**功能**：启动 BaseApp 服务

**语法**：
```bash
baseapp start [OPTIONS]
```

**选项**：
- `--port, -p <PORT>`：指定服务端口（默认：8000）
- `--host, -h <HOST>`：指定绑定主机（默认：0.0.0.0）
- `--config, -c <FILE>`：指定配置文件路径
- `--daemon, -d`：后台运行模式
- `--reload`：开发模式，代码变更自动重载
- `--log-level <LEVEL>`：日志级别（debug|info|warning|error）

**示例**：
```bash
# 默认启动
baseapp start

# 指定端口和主机
baseapp start --port 9000 --host localhost

# 后台运行
baseapp start --daemon

# 开发模式
baseapp start --reload --log-level debug
```

**输出**：
```
🚀 Starting BaseApp...
📁 Config file: /path/to/config/baseapp.yaml
🤖 Initializing Agent: MyAgent
🧠 Memory: Enabled (mem0 + chroma)
🔧 Tools: browser, memory
🌐 Server: http://0.0.0.0:8000
✅ BaseApp started successfully!

Press Ctrl+C to stop
```

#### `baseapp stop` - 停止应用

**功能**：优雅停止 BaseApp 服务

**语法**：
```bash
baseapp stop [OPTIONS]
```

**选项**：
- `--force, -f`：强制停止
- `--timeout <SECONDS>`：停止超时时间（默认：30秒）

**示例**：
```bash
# 优雅停止
baseapp stop

# 强制停止
baseapp stop --force
```

**输出**：
```
🛑 Stopping BaseApp...
💾 Saving application state...
🤖 Shutting down Agent gracefully...
✅ BaseApp stopped successfully!
```

#### `baseapp status` - 查看状态

**功能**：显示 BaseApp 运行状态

**语法**：
```bash
baseapp status [OPTIONS]
```

**选项**：
- `--json`：JSON 格式输出
- `--verbose, -v`：显示详细信息

**示例**：
```bash
# 简单状态
baseapp status

# 详细状态
baseapp status --verbose

# JSON 输出
baseapp status --json
```

**输出**：
```
📊 BaseApp Status

🟢 Service: Running
🌐 URL: http://localhost:8000
⏱️  Uptime: 2h 15m 32s
🤖 Agent: MyAgent (Ready)
💭 Active Sessions: 3
🧠 Memory: Enabled
🔧 Tools: 2 loaded
📈 Requests: 157 total, 12 errors
💾 Memory Usage: 245MB
🖥️  CPU Usage: 15%
```

### 2. 配置管理命令

#### `baseapp config` - 配置管理

**功能**：管理 BaseApp 配置

**子命令**：

**`baseapp config show`** - 显示配置
```bash
# 显示所有配置
baseapp config show

# 显示特定配置
baseapp config show agent.llm.provider
baseapp config show app
```

**`baseapp config set`** - 设置配置
```bash
# 设置配置值
baseapp config set agent.llm.provider openai
baseapp config set agent.llm.model gpt-4
baseapp config set app.port 9000
```

**`baseapp config edit`** - 编辑配置文件
```bash
# 使用默认编辑器编辑配置
baseapp config edit

# 使用指定编辑器
EDITOR=vim baseapp config edit
```

**输出示例**：
```bash
$ baseapp config show
📋 BaseApp Configuration

🔧 App Settings:
  name: BaseApp
  port: 8000
  host: 0.0.0.0
  debug: false

🤖 Agent Settings:
  name: MyAgent
  memory.enabled: true
  memory.provider: mem0
  
🧠 LLM Settings:
  provider: openai
  model: gpt-4o
  api_key: sk-****...****

📚 Tools Settings:
  enabled: browser, memory
  browser.headless: true
```

### 3. 对话交互命令

#### `baseapp chat` - 对话功能

**功能**：命令行方式与 Agent 对话

**子命令**：

**`baseapp chat interactive`** - 交互式对话
```bash
baseapp chat interactive [OPTIONS]
```

**选项**：
- `--session-id <ID>`：指定会话ID
- `--user-id <ID>`：指定用户ID

**交互界面**：
```
🤖 BaseApp Interactive Chat
Type 'exit' to quit, 'help' for commands

Session: chat_20231201_143022
Agent: MyAgent

You: 你好，请帮我分析一下今天的天气情况

Agent: 你好！我很乐意帮您分析天气情况。不过我需要知道您所在的城市才能为您提供准确的天气信息。请告诉我您想了解哪个城市的天气？

You: 北京

Agent: 好的，让我为您查询北京的天气情况...

[Agent thinking...] ⠋

Agent: 根据最新的天气数据，北京今天的天气情况如下：

📅 日期：2023年12月1日
🌤️  天气：多云转晴
🌡️  温度：2°C ~ 15°C
💨 风力：西北风3-4级
💧 湿度：45%
🔮 空气质量：良好 (AQI: 85)

建议您今天外出时添加一件外套，早晚温差较大。

You: exit

👋 再见！感谢使用 BaseApp！
```

**`baseapp chat send`** - 发送单条消息
```bash
baseapp chat send "请帮我总结一下今天的新闻" [OPTIONS]
```

**选项**：
- `--session-id <ID>`：指定会话ID
- `--user-id <ID>`：指定用户ID
- `--timeout <SECONDS>`：响应超时时间

**示例**：
```bash
# 发送消息
baseapp chat send "现在几点了？"

# 指定会话
baseapp chat send "继续上次的话题" --session-id session_123
```

**`baseapp chat history`** - 查看对话历史
```bash
baseapp chat history [SESSION_ID] [OPTIONS]
```

**选项**：
- `--limit <N>`：显示最近N条消息
- `--format <FORMAT>`：输出格式（text|json|csv）
- `--export <FILE>`：导出到文件

### 4. 日志管理命令

#### `baseapp logs` - 日志管理

**`baseapp logs show`** - 显示日志
```bash
baseapp logs show [OPTIONS]
```

**选项**：
- `--level <LEVEL>`：日志级别过滤（debug|info|warning|error）
- `--tail <N>`：显示最后N行
- `--follow, -f`：实时跟踪日志
- `--grep <PATTERN>`：搜索模式
- `--since <TIME>`：显示指定时间之后的日志

**示例**：
```bash
# 显示最后50行日志
baseapp logs show --tail 50

# 实时跟踪错误日志
baseapp logs show --level error --follow

# 搜索特定内容
baseapp logs show --grep "Agent"

# 显示最近1小时的日志
baseapp logs show --since "1h"
```

### 5. Agent 管理命令

#### `baseapp agent` - Agent 管理

**`baseapp agent info`** - Agent 信息
```bash
baseapp agent info [OPTIONS]
```

**输出**：
```
🤖 Agent Information

📝 Basic Info:
  Name: MyAgent
  Status: Ready
  Version: 1.0.0
  Uptime: 2h 15m 32s

🧠 Memory:
  Status: Enabled
  Provider: mem0
  Vector Store: chroma
  Total Memories: 1,247

🔧 Tools:
  browser: Browser automation tool
  memory: Memory management tool

📊 Statistics:
  Total Conversations: 89
  Total Messages: 456
  Success Rate: 98.7%
  Average Response Time: 2.3s
```

**`baseapp agent tools`** - 工具列表
```bash
baseapp agent tools [OPTIONS]
```

**`baseapp agent memory`** - 内存管理
```bash
# 内存统计
baseapp agent memory stats

# 清理内存
baseapp agent memory clear [--confirm]
```

## 用户体验设计

### 1. 交互设计原则

#### 渐进式信息披露
- 基础命令提供简洁输出
- 使用 `--verbose` 显示详细信息
- 使用 `--json` 提供机器可读格式

#### 一致的命令模式
```bash
# 模式：baseapp <resource> <action> [options]
baseapp config show
baseapp config set key value
baseapp logs show
baseapp agent info
```

#### 智能默认值
- 配置文件自动发现：`./baseapp.yaml` → `~/.baseapp/config.yaml`
- 合理的端口默认值：8000
- 适当的日志级别：info

### 2. 错误处理和用户反馈

#### 错误消息设计
```bash
# 好的错误消息
❌ Error: Configuration file not found
   Looked for: ./baseapp.yaml, ~/.baseapp/config.yaml
   💡 Tip: Run 'baseapp config create' to create a default config

# 避免的错误消息
Error: FileNotFoundError: [Errno 2] No such file or directory: 'baseapp.yaml'
```

#### 进度指示
```bash
# 启动过程
🚀 Starting BaseApp...
⚙️  Loading configuration... ✅
🤖 Initializing Agent... ✅
🧠 Setting up memory... ✅
🔧 Loading tools... ✅
🌐 Starting server... ✅
✅ BaseApp started successfully!
```

#### 确认操作
```bash
# 危险操作需要确认
$ baseapp agent memory clear
⚠️  This will permanently delete all agent memories.
   Type 'yes' to confirm: yes
🗑️  Clearing agent memory...
✅ Agent memory cleared successfully!
```

### 3. 帮助系统

#### 内置帮助
```bash
# 主帮助
$ baseapp --help
BaseApp - AI Agent Assistant

USAGE:
    baseapp [OPTIONS] COMMAND [ARGS]...

COMMANDS:
    start       Start the BaseApp server
    stop        Stop the BaseApp server
    status      Show application status
    config      Manage configuration
    chat        Chat with the agent
    logs        View and manage logs
    agent       Agent management
    version     Show version information

OPTIONS:
    --help      Show this message and exit
    --version   Show version and exit

EXAMPLES:
    baseapp start --port 9000    Start server on port 9000
    baseapp chat interactive     Start interactive chat
    baseapp status --verbose     Show detailed status

For more help on a specific command, run:
    baseapp COMMAND --help
```

#### 命令特定帮助
```bash
$ baseapp chat --help
Chat with the BaseApp agent

USAGE:
    baseapp chat COMMAND [OPTIONS]

COMMANDS:
    interactive    Start interactive chat session
    send          Send a single message
    history       View chat history
    clear         Clear chat history

EXAMPLES:
    baseapp chat interactive
    baseapp chat send "Hello, how are you?"
    baseapp chat history --limit 10
```

## 配置和环境

### 1. 配置文件位置
按优先级顺序查找：
1. `--config` 参数指定的文件
2. `./baseapp.yaml`
3. `~/.baseapp/config.yaml`
4. `/etc/baseapp/config.yaml`

### 2. 环境变量支持
```bash
# 覆盖配置文件设置
BASEAPP_PORT=9000 baseapp start
BASEAPP_LOG_LEVEL=debug baseapp start
OPENAI_API_KEY=sk-... baseapp start
```

### 3. 配置文件模板
```bash
# 创建默认配置
$ baseapp config create
📝 Creating default configuration...
✅ Configuration created at: ~/.baseapp/config.yaml

💡 Edit the configuration file to customize your settings:
   baseapp config edit
```

## 安装和分发

### 1. 安装方式

#### pip 安装
```bash
pip install baseapp
```

#### 开发安装
```bash
git clone https://github.com/example/baseapp.git
cd baseapp
pip install -e .
```

### 2. 命令行入口
通过 `pyproject.toml` 配置：
```toml
[project.scripts]
baseapp = "baseapp.cli.main:main"
```

### 3. 自动补全
支持 bash/zsh 自动补全：
```bash
# 生成补全脚本
baseapp --install-completion bash
baseapp --install-completion zsh

# 或手动添加
eval "$(_BASEAPP_COMPLETE=bash_source baseapp)"
```

## 测试策略

### 1. 单元测试
- 所有命令的参数解析
- 配置管理功能
- API 客户端功能

### 2. 集成测试
- 完整的命令行流程
- 与 BaseApp Server 的交互
- 配置文件处理

### 3. 用户体验测试
- 新手用户引导
- 常见使用场景
- 错误恢复流程

这个 CLI 设计提供了完整、友好的命令行体验，让用户能够高效地管理和使用 BaseApp。