# AgentCrafter 系统架构设计

## 整体架构概览

AgentCrafter 是一个自然语言驱动的智能 Agent 构建与运行平台，采用分层架构设计：

```
┌─────────────────────────────────────────┐
│           用户交互层 (UI Layer)            │
│     Web界面 | API接口 | CLI工具           │
├─────────────────────────────────────────┤
│        Agent 构建层 (Builder Layer)       │
│  ┌─────────────┐  ┌─────────────────────┐ │
│  │产品经理Agent │  │    项目经理Agent     │ │
│  │(需求分析)   │  │   (代码生成)        │ │
│  └─────────────┘  └─────────────────────┘ │
├─────────────────────────────────────────┤
│       Agent 执行层 (Runtime Layer)        │
│  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Agent Core  │  │   工具调度器(Tool   │ │
│  │ (引擎)      │  │   Dispatcher)       │ │
│  └─────────────┘  └─────────────────────┘ │
├─────────────────────────────────────────┤
│        工具层 (Tool Layer)                │
│  android_use | browser_use | memory | ... │
├─────────────────────────────────────────┤
│        基础设施层 (Infrastructure)         │
│  Docker | 数据库 | 日志 | 监控 | API网关   │
└─────────────────────────────────────────┘
```

## 核心组件设计

### 1. Agent Builder Service（Agent 构建服务）

负责将自然语言需求转换为可执行的 Agent 代码。

```python
class AgentBuilder:
    - RequirementAnalyzer()  # 产品经理Agent - 需求分析与澄清
    - CodeGenerator()        # 项目经理Agent - 代码生成
    - TestGenerator()        # 测试代码生成器
    - AgentValidator()       # Agent 功能验证器
    - DSLCompiler()         # DSL 编译器
```

**核心流程：**
1. 用户输入自然语言描述
2. RequirementAnalyzer 引导用户明确需求细节
3. CodeGenerator 生成 Agent DSL 定义
4. TestGenerator 创建测试用例
5. AgentValidator 验证 Agent 功能正确性

### 2. Agent Runtime Engine（Agent 运行时引擎）

负责执行已构建的 Agent，管理其生命周期。

```python
class AgentRuntime:
    - WorkflowExecutor()     # 工作流执行器
    - ToolManager()          # 工具管理器
    - MemoryManager()        # 内存/状态管理器
    - StateManager()         # 执行状态管理器
    - EventDispatcher()      # 事件分发器
```

**核心特性：**
- 支持异步执行长时间任务
- 状态持久化，支持断点续传
- 事件驱动架构，响应式设计
- 沙箱执行环境，保证安全性

### 3. Tool System（工具系统）

提供标准化的工具接口，支持第三方工具扩展。

```python
class ToolSystem:
    - ToolRegistry()         # 工具注册表
    - ToolProxy()           # 工具代理(安全沙箱)
    - ToolValidator()       # 工具参数验证
    - ToolMetrics()         # 工具使用统计
```

**内置工具：**
- `android_use`: Android 设备控制（微信、企业微信）
- `browser_use`: 浏览器自动化操作
- `memory`: 持久化内存管理
- `http_tool`: HTTP 请求工具
- `llm_extract`: 文本信息提取

### 4. DSL Definition（领域特定语言）

定义 Agent 的标准化描述格式，支持 JSON/YAML/Python 语法。

```json
{
  "name": "Agent名称",
  "version": "1.0.0",
  "description": "Agent功能描述",
  "trigger": "触发方式",
  "inputs": ["输入参数列表"],
  "workflow": [
    {
      "step": "步骤名称",
      "tool": "工具名称", 
      "action": "动作",
      "params": {"参数": "值"},
      "conditions": "执行条件",
      "retry": "重试策略"
    }
  ],
  "memory": true,
  "timeout": 300,
  "error_handling": "错误处理策略"
}
```

## 技术架构决策

### 后端技术栈
- **框架**: FastAPI（高性能 Python Web 框架）
- **数据库**: PostgreSQL（主数据库）+ Redis（缓存/会话）
- **消息队列**: Redis/RabbitMQ（异步任务处理）
- **容器化**: Docker + Docker Compose
- **监控**: Prometheus + Grafana

### 前端技术栈
- **框架**: React + TypeScript
- **样式**: Tailwind CSS
- **状态管理**: Redux Toolkit
- **构建工具**: Vite

### 部署架构
- **容器编排**: Docker Compose（开发）/ Kubernetes（生产）
- **API 网关**: Nginx/Traefik
- **服务发现**: Consul（可选）
- **日志收集**: ELK Stack

## 设计原则

### 1. 安全性优先
- Agent 在隔离沙箱中执行
- 工具调用权限控制
- 敏感数据加密存储
- API 访问认证授权

### 2. 可扩展性
- 插件化工具系统
- 微服务架构设计
- 水平扩展支持
- 多语言工具接入

### 3. 易用性
- 自然语言交互
- 可视化 Agent 构建
- 一键部署运行
- 丰富的模板库

### 4. 可观测性
- 完整的执行日志
- 性能监控指标
- 错误追踪报告
- 用户行为分析

## 数据流设计

```
用户输入 → 需求分析 → DSL生成 → 代码编译 → 测试验证 → Agent部署 → 执行监控
    ↓         ↓         ↓         ↓         ↓         ↓         ↓
  自然语言   结构化需求  Agent DSL  Python代码  测试报告   运行实例   执行日志
```

## 扩展规划

### Stage 1: 核心功能（当前）
- Agent 构建流程
- 基础工具集成
- 本地执行环境

### Stage 2: 平台化
- Web 管理界面
- 多用户支持
- Agent 市场

### Stage 3: 企业级
- 权限管理
- 审计日志
- 高可用部署
- API 网关

## 安全考虑

1. **执行隔离**: Agent 在独立容器中运行
2. **权限控制**: 基于角色的访问控制（RBAC）
3. **数据保护**: 敏感信息加密存储
4. **审计追踪**: 完整的操作日志记录
5. **输入验证**: 严格的参数校验和过滤