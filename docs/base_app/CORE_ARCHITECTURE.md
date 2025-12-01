# Base App Agent 架构设计文档

## 架构概述

Base App Agent 采用 Agent-as-Step 架构，系统的核心是 BaseAgent，它集成了 AgentWorkflowEngine 来执行基于Agent的工作流。每个工作流步骤都是一个独立的智能Agent，通过Provider接口与LLM交互。

## 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        BaseAgent                           │
│  ┌─────────────────────────────────────────────────────────┐│
│  │    execute(input) -> AgentResult                        ││
│  │    process_user_input(input) -> response               ││
│  │    run_workflow(workflow, input) -> WorkflowResult     ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────┬───────────────────────────────────────────┘
                  │
    ┌─────────────┼─────────────┐─────────────┐
    │             │             │             │
┌───▼───┐    ┌────▼────┐   ┌────▼──────┐ ┌───▼────┐
│Memory │    │ Tools   │   │ Providers │ │Workflow│
│       │    │         │   │           │ │        │
│store  │    │register │   │OpenAI     │ │Agent   │
│get    │    │use_tool │   │Anthropic  │ │Engine  │
│clear  │    │         │   │BaseProvider│ │        │
└───────┘    └─────────┘   └───────────┘ └────────┘
                  │                           │
            ┌─────▼─────┐              ┌──────▼──────┐
            │ Tools实现  │              │Agent Registry│
            │           │              │Agent Router │
            │AndroidUse │              │Agent Executor│
            │BrowserUse │              │             │
            │E2BSandbox │              │Text Agent   │
            └───────────┘              │Tool Agent   │
                                       │Code Agent   │
                                       └─────────────┘
```

## 核心组件设计

### 1. BaseAgent (核心类)

**职责**：作为Agent系统的统一入口，集成AgentWorkflowEngine、Memory、Tools、Provider等组件

**核心接口**：
```python
class BaseAgent:
    # 主要方法
    async def execute(self, input_data: Any) -> AgentResult
    async def process_user_input(self, user_input: str, user_id: str = None) -> str
    
    # Workflow接口
    async def run_workflow(self, workflow: Union[Workflow, List[AgentWorkflowStep]], input_data: Dict[str, Any] = None) -> WorkflowResult
    
    # Memory接口
    async def store_memory(self, key: str, value: Any)
    async def get_memory(self, key: str, default: Any = None) -> Any
    async def clear_memory(self)
    async def add_long_term_memory(self, content: str, user_id: str = None) -> Optional[str]
    async def search_long_term_memory(self, query: str, user_id: str = None, limit: int = 5) -> List[Dict[str, Any]]
    
    # Tools接口
    def register_tool(self, name: str, tool: BaseTool)
    async def use_tool(self, tool_name: str, action: str, params: Dict) -> ToolResult
    def get_registered_tools(self) -> List[str]
    
    # 状态管理
    async def initialize(self) -> bool
    async def cleanup(self) -> bool
    async def health_check(self) -> Dict[str, Any]
```

### 2. AgentWorkflowEngine (工作流引擎)

**职责**：执行基于Agent的工作流，管理AgentRegistry、AgentRouter、AgentExecutor

**核心组件**：
```python
class AgentWorkflowEngine:
    def __init__(self, agent_instance=None):
        self.agent = agent_instance
        self.agent_registry = AgentRegistry()
        self.agent_executor = AgentExecutor(self.agent_registry)
        self.agent_router = AgentRouter(self.agent_registry)
    
    async def execute_workflow(self, steps: List[AgentWorkflowStep], workflow_id: str = None, input_data: Dict[str, Any] = None) -> WorkflowResult
```

**核心特性**：
- **最终结果提取**: 新的机制返回最后一个成功步骤的输出，而不是所有上下文变量
- **变量引用**: 支持`{{variable_name}}`语法在步骤间传递数据
- **条件执行**: 支持基于上下文变量的条件判断
- **Agent自动路由**: 当agent_type为"auto"时自动选择合适的Agent

### 3. Agent类型系统

**三种核心Agent类型**：

#### 3.1 TextAgent
- **用途**: 文本生成、对话、问答
- **输入**: TextAgentInput (question, context_data, response_style, max_length)
- **输出**: TextAgentOutput (success, answer, word_count)

#### 3.2 ToolAgent  
- **用途**: 智能工具选择和调用
- **输入**: ToolAgentInput (task_description, context_data, allowed_tools, confidence_threshold)
- **输出**: ToolAgentOutput (success, result, tool_used, confidence, reasoning)

#### 3.3 CodeAgent
- **用途**: 代码生成和安全执行
- **输入**: CodeAgentInput (task_description, input_data, expected_output_format, libraries_allowed)
- **输出**: CodeAgentOutput (success, result, code_generated, execution_info)

### 4. Memory 机制

**双层存储**：
- **临时内存**: BaseAgent内置变量存储，工作流执行期间使用
- **长期记忆**: 可选的MemoryManager，支持向量存储和语义搜索

**接口实现**：
```python
# 临时内存
async def store_memory(self, key: str, value: Any)
async def get_memory(self, key: str, default: Any = None) -> Any

# 长期记忆 (可选)
async def add_long_term_memory(self, content: str, user_id: str = None) -> Optional[str]
async def search_long_term_memory(self, query: str, user_id: str = None, limit: int = 5) -> List[Dict[str, Any]]
```

### 5. Tools 管理

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

### 6. Provider系统

**LLM提供商抽象**：
```python
class BaseProvider:
    async def _initialize_client(self) -> None
    async def generate_response(self, system_prompt: str, user_prompt: str) -> str
```

**支持的Provider**：
- **OpenAIProvider**: 集成OpenAI API (gpt-4o, gpt-4o-mini等)
- **AnthropicProvider**: 集成Anthropic API (claude-3-sonnet等)

**集成到BaseAgent**：
```python
class BaseAgent:
    def _initialize_provider(self) -> None:
        # 根据配置初始化对应的Provider
        provider_type = self.provider_config.get('type', 'openai')
        if provider_type == 'openai':
            self.provider = OpenAIProvider(api_key=..., model_name=...)
        elif provider_type == 'anthropic':
            self.provider = AnthropicProvider(api_key=..., model_name=...)
```

## 数据流和执行模式

### 1. 工作流执行流程

**AgentWorkflowStep结构**：
```python
class AgentWorkflowStep:
    # 基础信息
    name: str
    agent_type: str              # "text_agent" | "tool_agent" | "code_agent" | "auto"
    task_description: str
    
    # 数据流配置
    input_ports: Dict[str, Any]  # 输入端口和变量引用
    output_ports: Dict[str, str] # 输出端口映射
    
    # 执行控制
    condition: Optional[str]     # 执行条件 "{{variable}} == 'value'"
    timeout: int = 300
    retry_count: int = 0
    
    # Agent特定配置
    allowed_tools: List[str]     # ToolAgent专用
    expected_output_format: str  # CodeAgent专用
    response_style: str          # TextAgent专用
```

### 2. 最终结果提取机制

**新的final_result逻辑**：
```python
# 在AgentWorkflowEngine中
last_step_output = None

for step in steps:
    step_result = await self._execute_agent_step(step, context)
    if step_result.success and step.output_ports:
        # 更新上下文变量
        await self._update_context_variables(step_result, step.output_ports, context)
        # 每次成功执行都更新最后一步输出
        last_step_output = await self._extract_step_outputs(step_result, step.output_ports)

return WorkflowResult(
    final_result=last_step_output if last_step_output is not None else context.variables
)
```

**行为改进**：
- **以前**: final_result包含所有上下文变量
- **现在**: final_result只返回最后一个成功步骤的实际输出

### 3. 工作流配置文件架构

**基于YAML的配置驱动工作流**：

工作流现在通过YAML配置文件定义，位于 `workflows/builtin/` 和 `workflows/user/` 目录：

```yaml
# workflows/builtin/user-qa-workflow.yaml
apiVersion: "ami.io/v1"
kind: "Workflow"

metadata:
  name: "user-qa-workflow"
  description: "智能用户问答工作流，支持意图识别和条件分支执行"

steps:
  # 步骤1: 意图分析
  - id: "intent-analysis"
    name: "用户意图分析"
    agent_type: "text_agent"
    task_description: "分析用户输入，判断需要的处理方式"
    condition:
      expression: "true"  # 始终执行
    outputs:
      answer: "intent_type"
  
  # 步骤2a: 工具执行（条件执行）
  - id: "tool-execution"
    name: "工具执行"
    agent_type: "tool_agent"
    condition:
      expression: "{{intent_type}} == 'tool'"
    outputs:
      result: "tool_result"
  
  # 步骤2b: 代码分析（条件执行）
  - id: "code-analysis"
    name: "代码分析"
    agent_type: "code_agent"
    condition:
      expression: "{{intent_type}} == 'code'"
    outputs:
      result: "code_result"
  
  # 步骤3: 最终响应生成
  - id: "final-response"
    name: "生成最终响应"
    agent_type: "text_agent"
    outputs:
      answer: "final_response"
```

**工作流加载**：
```python
def _load_default_workflows(self) -> None:
    from ..workflows.workflow_loader import load_workflow
    # 从YAML配置文件加载用户问答工作流
    self._default_workflows["user_qa"] = load_workflow("user-qa-workflow")
```

**关键特性**：
- **配置驱动**: 工作流完全由YAML配置文件定义
- **条件执行**: 支持复杂的条件表达式和分支逻辑
- **配置验证**: 加载时进行完整性和正确性检查
- **可扩展性**: 支持内置和用户自定义工作流
- **版本控制**: 配置文件可以进行版本管理和协作

## 目录结构

基于最新的Agent-as-Step架构：

```
base_app/
├── __init__.py
├── base_agent/
│   ├── __init__.py
│   ├── ARCHITECTURE.md              # 架构文档(已更新)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── base_agent.py           # BaseAgent核心类(集成AgentWorkflowEngine)
│   │   ├── agent_workflow_engine.py # Agent工作流执行引擎(新)
│   │   ├── schemas.py              # 核心数据结构(AgentWorkflowStep等)
│   │   └── memory_manager.py       # 内存管理器
│   ├── agents/                     # Agent类型系统(新)
│   │   ├── __init__.py
│   │   ├── agent_registry.py       # Agent注册表
│   │   ├── agent_router.py         # Agent路由器
│   │   ├── agent_executor.py       # Agent执行器
│   │   ├── text_agent.py           # 文本处理Agent
│   │   ├── tool_agent.py           # 工具调用Agent
│   │   └── code_agent.py           # 代码执行Agent
│   ├── providers/                  # LLM提供商(新)
│   │   ├── __init__.py
│   │   ├── base_provider.py        # 基础Provider接口
│   │   ├── openai_provider.py      # OpenAI集成
│   │   └── anthropic_provider.py   # Anthropic集成
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base_tool.py            # BaseTool抽象类
│   │   ├── android_use/
│   │   │   ├── __init__.py
│   │   │   └── android_tool.py     # Android自动化工具
│   │   ├── browser_use/
│   │   │   ├── __init__.py
│   │   │   └── browser_tool.py     # 浏览器自动化工具
│   │   └── e2b_sandbox/            # 代码执行沙箱
│   │       ├── __init__.py
│   │       └── sandbox_tool.py
│   ├── memory/
│   │   ├── __init__.py
│   │   └── memory_manager.py       # 长期记忆管理(mem0集成)
│   ├── examples/                   # Agent示例
│   │   ├── __init__.py
│   │   ├── agent_workflow_demo.py  # 工作流演示
│   │   └── simple_agent.py         # 简单Agent示例
│   └── docs/                       # 文档(已更新)
│       ├── workflow_development_guide.md
│       └── agent_as_step_design_v2.md
├── examples/                       # 全局示例
│   └── browser_examples.py
└── web/                           # Web相关(现有)
    ├── __init__.py
    ├── api/
    │   └── __init__.py
    ├── backend/
    └── frontend/
```


## 核心数据结构

### Agent输入输出类型

```python
# TextAgent
class TextAgentInput(BaseModel):
    question: str
    context_data: Dict[str, Any] = {}
    response_style: str = "professional"
    max_length: int = 500

class TextAgentOutput(BaseModel):
    success: bool
    answer: str
    word_count: int
    error_message: Optional[str] = None

# ToolAgent
class ToolAgentInput(BaseModel):
    task_description: str
    context_data: Dict[str, Any] = {}
    allowed_tools: List[str] = []
    confidence_threshold: float = 0.8

class ToolAgentOutput(BaseModel):
    success: bool
    result: Any
    tool_used: str
    confidence: float
    reasoning: str

# CodeAgent
class CodeAgentInput(BaseModel):
    task_description: str
    input_data: Any
    expected_output_format: str
    libraries_allowed: List[str] = []

class CodeAgentOutput(BaseModel):
    success: bool
    result: Any
    code_generated: str
    execution_info: Dict[str, Any]
```

### 工作流核心类型

```python
# 工作流结果
class WorkflowResult(BaseModel):
    success: bool
    workflow_id: str
    steps: List[StepResult]
    final_result: Any              # 新：只返回最后一步输出
    total_execution_time: float
    error_message: Optional[str] = None

# 步骤结果
class StepResult(BaseModel):
    step_id: str
    success: bool
    data: Any
    message: str
    execution_time: float

# Agent上下文
class AgentContext(BaseModel):
    workflow_id: str
    step_id: str
    variables: Dict[str, Any]      # 工作流变量
    agent_instance: Optional[Any]  # BaseAgent实例
    tools_registry: Optional[Any]
    memory_manager: Optional[Any]
```

## 扩展机制

### 1. Agent扩展
```python
# 创建自定义Agent
class CustomAgent(BaseAgent):
    async def execute(self, input_data: Any) -> AgentResult:
        # 实现自定义逻辑
        result = await self.use_tool('custom_tool', 'action', params)
        return AgentResult(success=True, data=result.data)

# 注册到AgentRegistry
agent_registry.register_agent(CustomAgent())
```

### 2. 工具扩展
```python
# 继承BaseTool
class CustomTool(BaseTool):
    async def execute(self, action: str, params: Dict) -> ToolResult:
        # 实现具体逻辑
        pass

# 注册到BaseAgent
agent.register_tool("custom", CustomTool())
```

### 3. Agent工作流扩展
```python
# 自定义AgentWorkflowStep
steps = [
    AgentWorkflowStep(
        name="分析数据",
        agent_type="code_agent",
        task_description="分析用户数据并生成报告",
        input_ports={"input_data": "{{user_data}}"},
        output_ports={"result": "analysis_result"}
    ),
    AgentWorkflowStep(
        name="生成回复",
        agent_type="text_agent", 
        task_description="基于分析结果生成用户回复",
        input_ports={"context_data": {"analysis": "{{analysis_result}}"}},
        output_ports={"answer": "final_response"}
    )
]

# 执行工作流
result = await agent.run_workflow(steps, {"user_data": data})
```

### 4. Provider扩展
```python
# 自定义LLM Provider
class CustomProvider(BaseProvider):
    async def generate_response(self, system_prompt: str, user_prompt: str) -> str:
        # 调用自定义LLM API
        pass

# 集成到BaseAgent
agent = BaseAgent(provider_config={
    'type': 'custom',
    'custom_provider': CustomProvider()
})
```

## 架构优势与特点

### 1. 设计优势

1. **Agent-as-Step架构**: 每个工作流步骤都是智能Agent，提供最大的灵活性
2. **统一的Provider接口**: 支持多种LLM后端，便于切换和扩展
3. **智能路由**: 自动选择最合适的Agent类型处理任务
4. **数据流清晰**: 新的最终结果提取机制让输出更直观
5. **条件执行**: 支持基于上下文的智能分支执行

### 2. 技术特点

1. **模块化设计**: 核心组件独立，易于测试和维护
2. **异步优先**: 全面支持异步操作，提高性能
3. **类型安全**: 基于Pydantic的强类型定义
4. **扩展友好**: 提供多个扩展点，支持自定义Agent、Tool、Provider
5. **内存管理**: 支持临时变量和长期记忆的双层存储

### 3. 核心改进

1. **最终结果优化**: `final_result`现在只返回最后一步的实际输出
2. **字段名称统一**: 使用`input_ports`和`output_ports`替代旧的映射字段名
3. **Agent类型简化**: 三种核心Agent类型覆盖所有业务场景
4. **执行引擎优化**: 移除了复杂的端口连接机制，采用更直观的变量引用方式

### 4. 实际应用场景

1. **智能客服**: 意图识别 → 工具调用/知识查询 → 回复生成
2. **数据分析**: 数据获取 → 代码分析 → 结果展示
3. **文档处理**: 内容提取 → 信息整理 → 格式转换
4. **自动化任务**: 任务分解 → 工具执行 → 结果汇总

这个架构在保持简洁性的同时，提供了强大的功能和良好的扩展性，适合作为AI Agent系统的核心基础。