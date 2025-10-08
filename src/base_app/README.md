# BaseApp - AI Agent Assistant Application

BaseApp 是一个基于 BaseAgent 框架构建的完整 AI Agent 应用程序，提供 Web UI、CLI 和 REST API 三种交互方式，让您轻松部署和使用智能助手。

## ✨ 特性

- **🔄 多端交互**: 支持 Web UI、命令行 CLI 和 REST API 三种交互方式
- **🤖 强大的 Agent**: 基于 BaseAgent 框架，支持工作流、内存管理和工具调用
- **⚡ 开箱即用**: 一键安装和启动，快速获得完整的 Agent 环境
- **⚙️ 灵活配置**: 支持 YAML 配置文件和环境变量覆盖
- **🏢 企业级**: 内置会话管理、日志系统和状态监控
- **🔧 可扩展**: 支持自定义工具和LLM提供商

## 📋 系统要求

- Python 3.8+
- OpenAI API Key 或其他 LLM 提供商密钥

## 📦 安装

### 从源码安装

```bash
git clone <repository>
cd baseapp
pip install -e .
```

### 验证安装

```bash
baseapp --help
```

## 🚀 快速开始

### 1. 设置 API 密钥

```bash
export OPENAI_API_KEY="your-openai-api-key"
```

### 2. 启动服务

```bash
# 使用默认配置启动
baseapp start

# 指定端口和配置文件
baseapp start --port 9000 --config ./my-config.yaml
```

### 3. 开始使用

#### 📱 CLI 对话

```bash
# 交互式对话
baseapp chat interactive

# 发送单条消息
baseapp chat send "你好，请介绍一下你自己"

# 查看对话历史
baseapp chat history
```

#### 🌐 Web UI

启动服务后，打开浏览器访问：
```
http://localhost:8000
```

#### 📡 API 调用

```python
import requests

# 发送消息
response = requests.post("http://localhost:8000/api/v1/chat/message", json={
    "message": "你好，世界！",
    "user_id": "user123"
})

print(response.json())
```

## 🛠️ CLI 命令参考

### 应用管理

```bash
baseapp start [OPTIONS]     # 启动服务
  --port, -p INTEGER        # 指定端口 (默认: 8000)
  --host, -h TEXT          # 指定主机 (默认: 0.0.0.0)
  --config, -c PATH        # 指定配置文件
  --daemon, -d             # 后台运行
  --reload                 # 开发模式（自动重载）

baseapp stop [OPTIONS]      # 停止服务
  --pid-file PATH          # 指定PID文件路径

baseapp restart             # 重启服务
baseapp status [OPTIONS]    # 查看运行状态
  --detail                 # 显示详细信息
```

### 配置管理

```bash
baseapp config show [key]          # 显示配置
baseapp config edit                # 编辑配置文件
baseapp config validate            # 验证配置文件
baseapp config create              # 创建默认配置文件
```

### 对话交互

```bash
baseapp chat interactive                # 启动交互式对话
  --session-id TEXT                     # 指定会话ID
  --user-id TEXT                        # 指定用户ID (默认: cli_user)

baseapp chat send "message"             # 发送单条消息
  --session-id TEXT                     # 指定会话ID
  --user-id TEXT                        # 指定用户ID

baseapp chat history [session_id]       # 查看对话历史
baseapp chat sessions                   # 列出所有会话
baseapp chat clear <session_id>         # 清理指定会话
```

## ⚙️ 配置

BaseApp 使用 YAML 配置文件，支持环境变量覆盖。配置文件查找顺序：

1. `--config` 参数指定的文件
2. `./baseapp.yaml`
3. `./config/baseapp.yaml` 
4. `~/.baseapp/config.yaml`
5. `/etc/baseapp/config.yaml`

### 配置文件示例

```yaml
app:
  name: "BaseApp"
  version: "1.0.0"
  host: "0.0.0.0"
  port: 8000
  debug: false

agent:
  name: "BaseApp Agent"
  memory:
    enabled: false
    provider: mem0
    config:
      llm:
        provider: openai
        model: gpt-4o-mini
      vector_store:
        provider: chroma
        path: ./data/chroma_db
  llm:
    provider: openai
    model: gpt-4o-mini
    api_key: ${OPENAI_API_KEY}
  tools:
    enabled: []
    browser:
      headless: true
      timeout: 30

database:
  type: sqlite
  url: ./data/baseapp.db

logging:
  level: INFO
  file: ./logs/baseapp.log
  max_size: 10MB
  backup_count: 5
```

### 环境变量

主要环境变量：

```bash
OPENAI_API_KEY          # OpenAI API 密钥
ANTHROPIC_API_KEY       # Anthropic API 密钥
BASEAPP_CONFIG_PATH     # 配置文件路径
BASEAPP_LOG_LEVEL       # 日志级别
BASEAPP_HOST            # 服务主机
BASEAPP_PORT            # 服务端口
```

## 🔌 API 接口

### 对话 API

```http
POST /api/v1/chat/message
Content-Type: application/json

{
  "message": "用户消息",
  "session_id": "可选的会话ID",
  "user_id": "用户ID"
}
```

```http
POST /api/v1/chat/sessions
Content-Type: application/json

{
  "user_id": "用户ID",
  "title": "会话标题"
}
```

```http
GET /api/v1/chat/sessions/{session_id}/history
```

### Agent 管理 API

```http
GET /api/v1/agent/status      # 获取 Agent 状态
GET /api/v1/agent/config      # 获取 Agent 配置
POST /api/v1/agent/restart    # 重启 Agent
```

### 系统 API

```http
GET /api/v1/system/health     # 健康检查
GET /api/v1/system/info       # 系统信息
GET /api/v1/system/logs       # 系统日志
```

## 🏗️ 架构设计

```
BaseApp
├── 🌐 Web UI (React)           # 前端界面
├── 💻 CLI Tool (Click)         # 命令行工具
├── 🔗 API Server (FastAPI)     # REST API服务
└── 🤖 BaseAgent Core           # Agent核心框架
    ├── 🔄 Workflow Engine      # 工作流引擎
    ├── 🧠 Memory Manager       # 内存管理系统
    ├── 🛠️  Tool System          # 工具调用系统
    └── 🔮 LLM Providers        # 多LLM提供商支持
```

### 核心组件

- **ConfigService**: 配置管理服务，支持 YAML 和环境变量
- **AgentService**: Agent 服务封装，管理 BaseAgent 实例
- **SessionManager**: 会话管理，支持多用户多会话
- **APIClient**: CLI 客户端，与 API 服务通信

## 🧪 开发

### 开发环境设置

```bash
# 克隆项目
git clone <repository>
cd baseapp

# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 代码格式化
black base_app/
isort base_app/

# 类型检查
mypy base_app/
```

### 开发模式启动

```bash
# 开启自动重载和调试模式
baseapp start --reload --debug --log-level debug
```

### 项目结构

```
base_app/
├── cli/                    # CLI 命令行工具
│   ├── commands/          # 子命令实现
│   ├── core/              # CLI 核心功能
│   └── main.py           # CLI 入口点
├── server/                # API 服务器
│   ├── api/              # API 路由
│   ├── core/             # 服务器核心
│   ├── models/           # 数据模型
│   └── main.py          # 服务器入口点
├── base_agent/            # BaseAgent 框架
│   ├── core/             # 核心组件
│   ├── providers/        # LLM 提供商
│   ├── tools/            # 工具系统
│   └── memory/           # 内存管理
└── config/               # 配置文件
```

## 🔧 扩展开发

### 添加自定义工具

```python
from base_app.base_agent.tools.base_tool import BaseTool

class MyCustomTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="my_tool",
            description="我的自定义工具"
        )
    
    async def execute(self, **kwargs):
        # 工具逻辑实现
        return "工具执行结果"
```

### 添加新的 LLM 提供商

```python
from base_app.base_agent.providers.base_provider import BaseLLMProvider

class MyLLMProvider(BaseLLMProvider):
    def __init__(self, api_key: str):
        super().__init__()
        self.api_key = api_key
    
    async def generate(self, messages, **kwargs):
        # LLM 调用逻辑
        return "LLM 响应"
```

## 📚 相关文档

项目包含以下文档：
- 配置说明和最佳实践
- API 接口详细文档
- BaseAgent 框架使用指南
- 部署和运维指南

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

### 贡献指南

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开 Pull Request

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 🆘 支持与反馈

- 📧 邮箱支持：baseapp@example.com
- 🐛 问题报告：[GitHub Issues](https://github.com/example/baseapp/issues)
- 💬 讨论交流：[GitHub Discussions](https://github.com/example/baseapp/discussions)

---

**享受使用 BaseApp！** 🚀