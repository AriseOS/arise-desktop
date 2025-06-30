# BaseApp 架构设计文档

## 架构概述

BaseApp 是 BaseAgent 的应用程序封装，旨在为用户提供简单易用的 Agent 交互体验。架构采用前后端分离的设计，提供 Web UI、CLI 工具和 API 接口三种交互方式。

### 设计原则

1. **简单优先**：专注核心功能，避免过度设计
2. **用户友好**：提供直观的交互界面和命令行工具
3. **模块化**：清晰的模块划分，便于维护和扩展
4. **标准化**：遵循 REST API 设计规范和前端最佳实践

## 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                       BaseApp 架构                          │
├─────────────────────────────────────────────────────────────┤
│  表现层 (Presentation Layer)                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  Web UI     │  │  CLI Tool   │  │  API Client │         │
│  │  (React)    │  │  (Click)    │  │  (SDK)      │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
├─────────────────────────────────────────────────────────────┤
│  应用层 (Application Layer)                                 │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              BaseApp Server                             ││
│  │              (FastAPI)                                  ││
│  └─────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│  业务层 (Business Layer)                                    │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              BaseAgent 核心                             ││
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  ││
│  │  │ Agent    │ │Workflow  │ │ Memory   │ │ Tools    │  ││
│  │  │ Manager  │ │ Engine   │ │ Manager  │ │ Manager  │  ││
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘  ││
│  └─────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│  数据层 (Data Layer)                                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ 配置文件     │  │ 对话历史     │  │ 日志文件     │         │
│  │ (YAML/JSON) │  │ (SQLite)    │  │ (Files)     │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

## 核心组件设计

### 1. BaseApp Server (应用服务层)

**技术栈**：FastAPI + Uvicorn
**职责**：提供 HTTP API 服务，处理前端请求，管理 BaseAgent 实例

#### 核心模块

```python
baseapp/
├── server/
│   ├── __init__.py
│   ├── main.py              # FastAPI 应用入口
│   ├── api/                 # API 路由
│   │   ├── __init__.py
│   │   ├── chat.py          # 对话 API
│   │   ├── agent.py         # Agent 管理 API
│   │   └── system.py        # 系统状态 API
│   ├── core/                # 核心服务
│   │   ├── __init__.py
│   │   ├── agent_service.py # Agent 服务管理
│   │   ├── chat_service.py  # 对话服务
│   │   └── config_service.py# 配置服务
│   ├── models/              # 数据模型
│   │   ├── __init__.py
│   │   ├── requests.py      # 请求模型
│   │   └── responses.py     # 响应模型
│   └── middleware/          # 中间件
│       ├── __init__.py
│       ├── cors.py          # CORS 处理
│       └── logging.py       # 日志中间件
```

#### API 设计

**对话 API**
```python
# 发送消息
POST /api/v1/chat/message
{
    "message": "用户消息",
    "session_id": "会话ID", 
    "user_id": "用户ID"
}

# 获取对话历史
GET /api/v1/chat/history?session_id=xxx&limit=50

# 创建新会话
POST /api/v1/chat/session
{
    "user_id": "用户ID",
    "title": "会话标题"
}
```

**Agent 管理 API**
```python
# 获取 Agent 状态
GET /api/v1/agent/status

# 重启 Agent
POST /api/v1/agent/restart

# 获取 Agent 配置
GET /api/v1/agent/config

# 更新 Agent 配置
PUT /api/v1/agent/config
```

**系统 API**
```python
# 系统健康检查
GET /api/v1/system/health

# 系统信息
GET /api/v1/system/info

# 获取日志
GET /api/v1/system/logs?level=info&limit=100
```

### 2. Web UI (前端界面)

**技术栈**：React + TypeScript + Ant Design/Material-UI
**职责**：提供用户友好的 Web 界面

#### 组件结构

```
frontend/
├── src/
│   ├── components/          # 通用组件
│   │   ├── ChatWindow/      # 对话窗口
│   │   ├── MessageBubble/   # 消息气泡
│   │   ├── InputBox/        # 输入框
│   │   └── Sidebar/         # 侧边栏
│   ├── pages/               # 页面组件
│   │   ├── ChatPage/        # 主对话页面
│   │   └── SettingsPage/    # 设置页面
│   ├── services/            # API 服务
│   │   ├── api.ts           # API 客户端
│   │   ├── chat.ts          # 对话服务
│   │   └── websocket.ts     # WebSocket 服务
│   ├── hooks/               # 自定义 Hooks
│   │   ├── useChat.ts       # 对话 Hook
│   │   └── useWebSocket.ts  # WebSocket Hook
│   ├── store/               # 状态管理 (Zustand/Redux)
│   │   ├── chatStore.ts     # 对话状态
│   │   └── settingsStore.ts # 设置状态
│   └── utils/               # 工具函数
│       ├── constants.ts     # 常量定义
│       └── helpers.ts       # 辅助函数
```

#### 核心页面设计

**主对话页面 (ChatPage)**
```
┌─────────────────────────────────────────────────────────┐
│ BaseApp                                        [设置] │
├─────────────────────────────────────────────────────────┤
│ ┌─────────┐ ┌─────────────────────────────────────────┐ │
│ │ 会话列表 │ │             对话区域                   │ │
│ │         │ │                                       │ │
│ │ 新会话   │ │  ┌─────────────────────────────────┐   │ │
│ │ 会话1    │ │  │ Agent: 你好！我是你的助手        │   │ │
│ │ 会话2    │ │  └─────────────────────────────────┘   │ │
│ │ ...     │ │                                       │ │
│ │         │ │  ┌─────────────────────────────────┐   │ │
│ │         │ │  │ 用户: 帮我分析一下这个数据        │   │ │
│ │         │ │  └─────────────────────────────────┘   │ │
│ │         │ │                                       │ │
│ │         │ │  ┌─────────────────────────────────┐   │ │
│ │         │ │  │ Agent: 好的，请提供数据...       │   │ │
│ │         │ │  └─────────────────────────────────┘   │ │
│ └─────────┘ └─────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────┐ [发送] [附件]  │
│ │ 请输入您的消息...                    │              │
│ └─────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────┘
```

### 3. CLI Tool (命令行工具)

**技术栈**：Click + Rich (美化输出)
**职责**：提供命令行管理和交互功能

#### 命令结构

```
baseapp
├── start                    # 启动应用
├── stop                     # 停止应用  
├── restart                  # 重启应用
├── status                   # 查看状态
├── config                   # 配置管理
│   ├── show                 # 显示配置
│   ├── set <key> <value>    # 设置配置
│   └── reset                # 重置配置
├── chat                     # 命令行对话
│   ├── interactive          # 交互式对话
│   └── send <message>       # 发送单条消息
└── logs                     # 日志管理
    ├── show                 # 显示日志
    └── clear                # 清理日志
```

#### CLI 实现结构

```python
cli/
├── __init__.py
├── main.py                  # 主命令入口
├── commands/                # 命令实现
│   ├── __init__.py
│   ├── app.py               # 应用管理命令
│   ├── config.py            # 配置命令
│   ├── chat.py              # 对话命令
│   └── logs.py              # 日志命令
├── core/                    # CLI 核心
│   ├── __init__.py
│   ├── client.py            # API 客户端
│   ├── config.py            # 配置管理
│   └── utils.py             # 工具函数
└── ui/                      # UI 组件
    ├── __init__.py
    ├── console.py           # 控制台输出
    └── progress.py          # 进度条
```

#### 使用示例

```bash
# 启动 BaseApp
baseapp start --port 8000 --host 0.0.0.0

# 检查状态
baseapp status

# 命令行对话
baseapp chat interactive

# 发送单条消息
baseapp chat send "你好，帮我分析一下今天的天气"

# 查看配置
baseapp config show

# 设置配置
baseapp config set llm.provider openai
baseapp config set llm.model gpt-4

# 查看日志
baseapp logs show --level info --tail 50
```

### 4. Agent 服务层

**BaseAgent 封装服务**，负责管理 BaseAgent 实例的生命周期

```python
# AgentService 示例
class AgentService:
    def __init__(self, config: AgentConfig):
        self.agent = BaseAgent(config, enable_memory=True)
        self.sessions = {}  # 会话管理
        
    async def send_message(
        self, 
        message: str, 
        session_id: str, 
        user_id: str
    ) -> str:
        """发送消息到 Agent"""
        # 获取或创建会话上下文
        session = self.get_or_create_session(session_id, user_id)
        
        # 调用 BaseAgent 处理
        response = await self.agent.process_user_input(
            message, 
            user_id=user_id
        )
        
        # 保存对话历史
        await self.save_conversation(session_id, message, response)
        
        return response
    
    def get_agent_status(self) -> dict:
        """获取 Agent 状态"""
        return {
            "status": self.agent.get_status().value,
            "uptime": time.time() - self.start_time,
            "memory_enabled": self.agent.memory_manager is not None,
            "tools": self.agent.get_registered_tools()
        }
```

## 数据流设计

### 1. Web 用户对话流程

```
用户输入消息 → Web UI → API Request → BaseApp Server 
    → AgentService → BaseAgent → 工作流执行 → 响应生成 
    → AgentService → API Response → Web UI → 用户界面
```

### 2. CLI 对话流程

```
用户CLI命令 → CLI Tool → HTTP Client → BaseApp Server 
    → AgentService → BaseAgent → 响应生成 
    → AgentService → HTTP Response → CLI Tool → 终端输出
```

### 3. 配置管理流程

```
配置文件 → ConfigService → AgentService → BaseAgent 配置更新
```

## 配置设计

### 应用配置 (baseapp.yaml)

```yaml
# BaseApp 应用配置
app:
  name: "BaseApp"
  version: "1.0.0"
  host: "0.0.0.0"
  port: 8000
  debug: false

# Agent 配置
agent:
  name: "MyAgent"
  memory:
    enabled: true
    provider: "mem0"
    config:
      llm:
        provider: "openai"
        model: "gpt-4o-mini"
      vector_store:
        provider: "chroma"
        path: "./data/chroma_db"
  
  # LLM 提供商配置
  llm:
    provider: "openai"  # openai, anthropic
    model: "gpt-4o"
    api_key: "${OPENAI_API_KEY}"
    
  # 工具配置
  tools:
    enabled:
      - "browser"
      - "memory"
    
    browser:
      headless: true
      timeout: 30

# 数据库配置
database:
  type: "sqlite"
  url: "./data/baseapp.db"

# 日志配置
logging:
  level: "INFO"
  file: "./logs/baseapp.log"
  max_size: "10MB"
  backup_count: 5

# Web UI 配置
web:
  title: "BaseApp - AI Agent Assistant"
  theme: "light"
  language: "zh-CN"
```

## 部署架构

### 1. 开发环境部署

```bash
# 目录结构
baseapp/
├── backend/                 # 后端代码
├── frontend/                # 前端代码
├── cli/                     # CLI 工具
├── config/                  # 配置文件
├── data/                    # 数据文件
├── logs/                    # 日志文件
└── scripts/                 # 部署脚本
    ├── dev.sh               # 开发环境启动
    ├── build.sh             # 构建脚本
    └── install.sh           # 安装脚本

# 启动命令
python -m baseapp.server     # 启动后端
npm run dev                  # 启动前端开发服务器
baseapp start               # 或使用 CLI 启动
```

### 2. 生产环境部署

```dockerfile
# Dockerfile
FROM python:3.9-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install -r requirements.txt

# 复制代码
COPY . .

# 构建前端
RUN npm install && npm run build

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python", "-m", "baseapp.server", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  baseapp:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./config:/app/config
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
```

## 安全设计

### 1. API 安全
- **输入验证**：所有 API 输入进行严格验证
- **CORS 配置**：适当的跨域资源共享设置
- **请求限制**：防止 API 滥用的频率限制

### 2. 数据安全
- **敏感信息**：API 密钥等敏感信息使用环境变量
- **数据加密**：对话历史等数据进行加密存储
- **访问控制**：基于会话的访问控制

## 监控和日志

### 1. 日志系统
- **结构化日志**：使用 JSON 格式记录日志
- **日志级别**：支持 DEBUG、INFO、WARN、ERROR 级别
- **日志轮转**：自动日志文件轮转和清理

### 2. 监控指标
- **系统指标**：CPU、内存、磁盘使用率
- **应用指标**：API 响应时间、请求数量、错误率
- **Agent 指标**：对话数量、处理时间、成功率

## 扩展设计

### 1. 插件化架构
- **工具插件**：支持自定义工具扩展
- **UI 插件**：支持前端组件扩展
- **协议插件**：支持不同通信协议

### 2. 多 Agent 支持
- **Agent 池**：支持运行多个 Agent 实例
- **负载均衡**：请求在多个 Agent 间分发
- **隔离机制**：不同 Agent 间的资源隔离

这个架构设计提供了一个完整、简洁的 BaseApp 实现方案，专注于将 BaseAgent 封装成用户友好的应用程序。