# Base App Agent 架构设计文档

## 架构概述

Base App Agent 采用简单的分层架构，专注于三个核心功能：Memory、Tools、Workflow。作为Demo版本，避免过度设计，保持架构清晰易懂。

## 整体架构图

```
┌─────────────────────────────────────────────┐
│                BaseAgent                    │
│  ┌─────────────────────────────────────────┐│
│  │         execute(input) -> result        ││
│  └─────────────────────────────────────────┘│
└─────────────────┬───────────────────────────┘
                  │
    ┌─────────────┼─────────────┐
    │             │             │
┌───▼───┐    ┌────▼────┐   ┌────▼────┐
│Memory │    │ Tools   │   │Workflow │
│       │    │         │   │         │
│store  │    │register │   │run      │
│get    │    │use_tool │   │steps    │
│clear  │    │         │   │         │
└───────┘    └─────────┘   └─────────┘
                  │
            ┌─────▼─────┐
            │ Tools实现  │
            │           │
            │AndroidUse │
            │BrowserUse │
            │E2BSandbox │
            └───────────┘
```

## 核心组件设计

### 1. BaseAgent (核心类)

**职责**：作为Agent的统一入口，协调Memory、Tools、Workflow三个组件

**核心接口**：
```python
class BaseAgent:
    # 主要方法
    async def execute(self, input_data: Any) -> AgentResult
    
    # Memory接口
    async def store_memory(self, key: str, value: Any, persistent: bool = False)
    async def get_memory(self, key: str, default: Any = None) -> Any
    async def clear_memory(self, persistent: bool = False)
    
    # Tools接口
    def register_tool(self, name: str, tool: BaseTool)
    async def use_tool(self, tool_name: str, action: str, params: Dict) -> ToolResult
    def get_registered_tools(self) -> List[str]
    
    # Workflow接口
    async def run_workflow(self, steps: List[WorkflowStep]) -> WorkflowResult
```

### 2. Memory 机制

**设计**：直接在BaseAgent中维护两个字典
```python
class BaseAgent:
    def __init__(self):
        self.variables: Dict[str, Any] = {}        # 临时变量
        self.memory: Dict[str, Any] = {}           # 持久化内存
```

**接口实现**：
- `store_memory()` - 根据persistent参数存储到对应字典
- `get_memory()` - 优先查找variables，再查找memory
- `clear_memory()` - 清空对应字典

### 3. Tools 管理

**设计**：在BaseAgent中维护工具注册表
```python
class BaseAgent:
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
```

**预期工具**：
- `android_use` - Android自动化工具
- `browser_use` - 浏览器自动化工具  
- `e2b_sandbox` - 代码执行沙箱

**BaseTool抽象类**：
```python
class BaseTool:
    async def execute(self, action: str, params: Dict) -> ToolResult
    def get_available_actions(self) -> List[str]
    async def health_check(self) -> bool
```

### 4. Workflow 执行

**WorkflowStep结构**：
```python
class WorkflowStep:
    name: str                    # 步骤名称
    step_type: str              # 步骤类型: "tool" | "code" | "agent"
    
    # 工具调用步骤
    tool_name: Optional[str]     # 工具名称
    action: Optional[str]        # 工具动作
    params: Dict[str, Any]       # 参数
    
    # 代码执行步骤
    code: Optional[str]          # 要执行的代码
    
    # Agent调用步骤
    agent_name: Optional[str]    # 子Agent名称
    agent_input: Optional[Any]   # 子Agent输入
```

**执行逻辑**：
```python
async def run_workflow(self, steps: List[WorkflowStep]) -> WorkflowResult:
    results = {}
    for step in steps:
        if step.step_type == "tool":
            result = await self.use_tool(step.tool_name, step.action, step.params)
        elif step.step_type == "code":
            result = await self._execute_code(step.code)
        elif step.step_type == "agent":
            result = await self._call_agent(step.agent_name, step.agent_input)
        
        results[step.name] = result
    return WorkflowResult(results=results)
```

### 5. 服务提供商

**设计原则**：直接使用官方SDK，提供简洁统一的接口

#### 5.1 基础Provider接口
```python
class BaseProvider:
    async def _initialize_client(self) -> None:
    async def generate_response(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> str
```

#### 5.2 具体实现
- **OpenAIProvider**：使用openai官方SDK
- **AnthropicProvider**：使用anthropic官方SDK

#### 5.3 集成到BaseAgent
```python
class BaseAgent:
    def __init__(self, llm_provider: BaseProvider = None):
        self.llm_provider = llm_provider
    
    async def generate_response(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> str:
        return await self.llm_provider.generate_response(system_prompt, user_prompt)
```

**特点**：
- 上层调用者只需要提供system_prompt和user_prompt
- 内部处理所有SDK细节（认证、模型选择、参数配置等）
- 支持通过环境变量或构造参数配置API密钥和模型

## 目录结构

基于实际的项目结构：

```
base_app/
├── __init__.py
├── base_agent/
│   ├── __init__.py
│   ├── ARCHITECTURE.md              # 架构文档
│   ├── REQUIREMENTS_ANALYSIS.md     # 需求分析文档
│   ├── core/
│   │   ├── __init__.py
│   │   ├── base_agent.py           # BaseAgent核心类
│   │   ├── memory_manager.py       # 内存管理器
│   │   ├── state_manager.py        # 状态管理器
│   │   ├── workflow_engine.py      # 工作流引擎
│   │   └── schemas.py              # 数据结构定义(新增)
│   ├── memory/
│   │   └── __init__.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base_tool.py            # BaseTool抽象类
│   │   ├── android_use/
│   │   │   ├── __init__.py
│   │   │   └── android_tool.py     # Android工具实现(新增)
│   │   ├── browser_use/
│   │   │   ├── __init__.py
│   │   │   └── browser_tool.py     # 浏览器工具实现
│   │   ├── llm_extract/
│   │   │   ├── __init__.py
│   │   │   └── llm_tool.py         # LLM提取工具(新增)
│   │   └── e2b_sandbox/            # 代码执行沙箱(新增)
│   │       ├── __init__.py
│   │       └── sandbox_tool.py
│   ├── providers/                  # LLM服务提供商(新增)
│   │   ├── __init__.py
│   │   ├── base_provider.py        # 基础Provider接口
│   │   ├── openai_provider.py      # OpenAI实现
│   │   └── anthropic_provider.py     # 使用示例(新增)
│       ├── __init__.py
│       ├── simple_agent.py         # 简单Agent示例
│       └── workflow_example.py     # 工作流示例
├── examples/                       # 全局示例
│   └── browser_examples.py
└── web/                           # Web相关(现有)
    ├── __init__.py
    ├── api/
    │   └── __init__.py
    ├── backend/
    └── frontend/
```


## 数据结构

### 核心数据类型

```python
# AgentResult
class AgentResult:
    success: bool
    data: Any
    message: str
    execution_time: float

# ToolResult  
class ToolResult:
    success: bool
    data: Any
    message: str

# WorkflowResult
class WorkflowResult:
    success: bool
    results: Dict[str, Any]
    total_time: float
```

## 扩展机制

### 1. 工具扩展
```python
# 1. 继承BaseTool
class CustomTool(BaseTool):
    async def execute(self, action: str, params: Dict) -> ToolResult:
        # 实现具体逻辑
        pass

# 2. 注册工具
agent.register_tool("custom", CustomTool())
```

### 2. 工作流扩展
```python
# 自定义工作流步骤
steps = [
    WorkflowStep(name="step1", step_type="tool", tool_name="browser", action="navigate", params={"url": "https://example.com"}),
    WorkflowStep(name="step2", step_type="code", code="result = data['title'].upper()"),
    WorkflowStep(name="step3", step_type="agent", agent_name="analyzer", agent_input="{{step1_result}}")
]
```

### 3. LLM提供商扩展
```python
# 自定义LLM提供商
class CustomProvider(BaseProvider):
    async def call_llm(self, messages: List[Dict]) -> str:
        # 调用自定义LLM API
        pass

agent = BaseAgent(llm_provider=CustomProvider())
```

## 简化的错误处理

- 所有方法返回统一的Result结构
- 基本的异常捕获和转换
- 简单的日志记录
- 不实现复杂的重试和恢复机制

## Demo实现重点

1. **最小可用**：实现核心功能即可，不追求完美
2. **清晰接口**：重点在于接口设计的清晰性
3. **易于扩展**：为未来扩展预留空间
4. **示例丰富**：提供足够的使用示例

这个架构保持了最大的简洁性，同时提供了必要的扩展能力，适合作为Demo和后续开发的基础。