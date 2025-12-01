# Agent-as-Step工作流开发指南

## 1. 快速入门

### 1.1 Agent-as-Step架构

Agent-as-Step是新一代工作流架构，将每个处理步骤抽象为独立的Agent。每个Agent都具备特定的能力（如文本处理、工具调用、代码执行），并通过统一的Provider接口与LLM交互。

### 1.2 核心概念

- **Workflow**: 基于Agent的工作流定义，包含多个Agent步骤
- **AgentWorkflowStep**: 工作流中的单个Agent步骤，指定Agent类型和配置
- **AgentWorkflowEngine**: Agent工作流执行引擎
- **Provider**: 统一的LLM提供者接口，支持多种LLM后端
- **AgentContext**: Agent执行时的上下文环境，包含变量和状态

### 1.3 三种核心Agent类型

1. **TextAgent**: 文本处理Agent，处理对话、问答、文本生成等
2. **ToolAgent**: 工具调用Agent，智能选择和执行各种工具
3. **CodeAgent**: 代码执行Agent，生成和安全执行代码

### 1.4 第一个Agent工作流

```python
from base_app.base_agent.core.schemas import Workflow, AgentWorkflowStep

def create_simple_qa_workflow():
    """创建一个简单的问答工作流"""
    steps = [
        AgentWorkflowStep(
            id="analyze_intent",
            name="分析用户意图",
            agent_type="text_agent",
            task_description="分析用户意图，判断是否需要工具调用",
            input_ports={"context_data": {"user_input": "{{user_input}}"}},
            output_ports={"answer": "intent_type"},
            response_style="analytical",
            max_length=200
        ),
        AgentWorkflowStep(
            id="generate_answer",
            name="生成回答",
            agent_type="text_agent", 
            task_description="根据用户问题生成友好回答",
            condition="{{intent_type}} == 'chat'",
            input_ports={
                "context_data": {
                    "user_input": "{{user_input}}",
                    "intent": "{{intent_type}}"
                }
            },
            output_ports={"answer": "final_response"},
            response_style="friendly",
            max_length=500
        )
    ]
    
    return Workflow(
        name="简单问答工作流",
        description="基于Agent的问答处理流程",
        steps=steps,
        input_schema={
            "user_input": {"type": "string", "description": "用户输入"}
        },
        output_schema={
            "final_response": {"type": "string", "description": "最终回答"}
        }
    )
```

## 2. Workflow架构

### 2.1 Workflow类定义

```python
class Workflow(BaseModel):
    # 基础信息
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="工作流名称")
    description: str = Field(default="", description="工作流描述")
    version: str = Field(default="1.0.0", description="版本号")
    
    # Agent步骤定义
    steps: List[AgentWorkflowStep] = Field(..., description="Agent工作流步骤")
    
    # 输入输出定义
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    
    # 执行配置
    max_execution_time: int = Field(default=3600, description="最大执行时间(秒)")
    enable_parallel: bool = Field(default=False, description="是否启用并行执行")
    enable_cache: bool = Field(default=True, description="是否启用缓存")
    
    # 元数据
    tags: List[str] = Field(default_factory=list, description="标签")
    author: str = Field(default="Ami", description="作者")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
```

### 2.2 必需字段 vs 可选字段

#### 必需字段
- `name`: 工作流名称，用于标识和日志
- `steps`: Agent步骤列表，至少包含一个步骤

#### 常用可选字段
- `description`: 工作流描述，建议填写
- `input_schema`/`output_schema`: 输入输出定义，便于验证和文档
- `max_execution_time`: 执行超时时间，根据实际需要调整

#### 其他可选字段
- `version`, `tags`, `author`: 元数据信息
- `enable_parallel`: 性能优化选项
- `enable_cache`: 缓存控制

### 2.3 输入输出Schema定义

```python
# 输入Schema示例
input_schema = {
    "user_input": {
        "type": "string",
        "description": "用户输入文本",
        "required": True
    },
    "language": {
        "type": "string", 
        "description": "语言代码",
        "default": "zh-CN",
        "enum": ["zh-CN", "en-US", "ja-JP"]
    },
    "options": {
        "type": "object",
        "description": "处理选项",
        "properties": {
            "max_length": {"type": "integer", "default": 1000},
            "temperature": {"type": "number", "default": 0.7}
        }
    }
}

# 输出Schema示例
output_schema = {
    "response": {
        "type": "string",
        "description": "AI响应内容"
    },
    "confidence": {
        "type": "number",
        "description": "置信度分数"
    },
    "metadata": {
        "type": "object",
        "description": "响应元数据"
    }
}
```

## 3. AgentWorkflowStep详解

### 3.1 AgentWorkflowStep结构

```python
class AgentWorkflowStep(BaseModel):
    # 基础信息
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="步骤名称")
    description: str = Field(default="", description="步骤描述")
    
    # Agent配置
    agent_type: str = Field(..., description="Agent类型: text_agent | tool_agent | code_agent | auto")
    task_description: str = Field(..., description="任务描述")
    
    # 输入配置
    input_ports: Dict[str, Any] = Field(default_factory=dict, description="输入映射")
    constraints: List[str] = Field(default_factory=list, description="约束条件")
    
    # Tool Agent 特有配置
    allowed_tools: List[str] = Field(default_factory=list, description="允许使用的工具列表")
    fallback_tools: List[str] = Field(default_factory=list, description="备选工具列表") 
    confidence_threshold: float = Field(default=0.8, description="工具选择置信度阈值")
    
    # Code Agent 特有配置
    allowed_libraries: List[str] = Field(default_factory=list, description="允许使用的代码库")
    expected_output_format: str = Field(default="", description="期望的输出格式")
    
    # Text Agent 特有配置
    response_style: str = Field(default="professional", description="回答风格")
    max_length: int = Field(default=500, description="最大回答长度")
    
    # 输出配置  
    output_ports: Dict[str, str] = Field(default_factory=dict, description="输出映射")
    
    # 执行控制
    condition: Optional[str] = Field(default=None, description="执行条件")
    timeout: int = Field(default=300, description="超时时间")
    retry_count: int = Field(default=0, description="重试次数")
```

### 3.2 三种核心Agent类型

| Agent类型 | 用途 | 适用场景 |
|-----------|------|----------|
| **text_agent** | 文本处理 | 对话、问答、文本生成、情感分析 |
| **tool_agent** | 工具调用 | 浏览器操作、文件处理、API调用 |
| **code_agent** | 代码执行 | 数据处理、计算、代码生成 |

### 3.3 TextAgent步骤

TextAgent处理各种文本相关任务，通过Provider接口与LLM交互。

#### 基本结构
```python
AgentWorkflowStep(
    id="text_step",
    name="文本处理步骤",
    agent_type="text_agent",
    task_description="根据用户输入生成友好回答",
    input_ports={
        "context_data": {
            "user_input": "{{user_input}}",
            "previous_answer": "{{prev_result}}"
        }
    },
    output_ports={
        "answer": "final_response"
    },
    response_style="friendly",
    max_length=500
)
```

#### 输入输出处理
```python
# TextAgent输入格式
TextAgentInput(
    question="用户问题",
    context_data={"key": "value"},
    response_style="friendly",
    max_length=500,
    language="zh"
)

# TextAgent输出格式
TextAgentOutput(
    success=True,
    answer="AI回答内容",
    word_count=120,
    error_message=None
)
```

### 3.4 ToolAgent步骤

ToolAgent智能选择和执行工具，支持工具预筛选和置信度机制。

#### 基本结构
```python
AgentWorkflowStep(
    id="tool_step",
    name="工具调用步骤",
    agent_type="tool_agent",
    task_description="填写企业微信中的表单",
    input_ports={
        "context_data": {
            "form_data": "{{extracted_info}}",
            "url": "{{form_url}}"
        }
    },
    output_ports={
        "result": "form_result"
    },
    allowed_tools=["browser_use"],
    fallback_tools=["android_use"],
    confidence_threshold=0.8
)
```

#### 工具预筛选机制
```python
# 在Workflow设计时预筛选工具
allowed_tools = [
    "browser_use",    # 浏览器操作
    "android_use",    # 安卓操作
    "llm_extract"     # 文本提取
]

# Agent执行时只从预筛选工具中选择
ToolAgentInput(
    task_description="打开网页并提取标题",
    context_data={"url": "https://example.com"},
    allowed_tools=allowed_tools,
    confidence_threshold=0.8
)
```

### 3.5 CodeAgent步骤

CodeAgent生成和安全执行代码，适用于数据处理和计算任务。

#### 基本结构
```python
AgentWorkflowStep(
    id="code_step",
    name="代码执行步骤",
    agent_type="code_agent",
    task_description="分析聊天记录提取关键信息",
    input_ports={
        "input_data": "{{chat_content}}"
    },
    output_ports={
        "result": "extracted_info"
    },
    expected_output_format="JSON格式包含客户姓名、时间、地点",
    allowed_libraries=["json", "re", "datetime"]
)
```

#### 安全执行环境
```python
# CodeAgent输入格式
CodeAgentInput(
    task_description="处理JSON数据并计算统计信息",
    input_data={"numbers": [1, 2, 3, 4, 5]},
    expected_output_format="{sum: int, avg: float}",
    constraints=["输出必须是JSON格式"],
    libraries_allowed=["json", "math"]
)

# 安全检查包括：
# - AST语法检查
# - 危险函数检测（exec, eval, open等）
# - 未授权库导入检测
# - 限制执行环境
```

## 4. 数据流和变量引用

### 4.1 输入端口（input_ports）

输入端口定义如何从工作流变量构造Agent的输入：

```python
input_ports = {
    # 直接变量引用
    "context_data": {
        "user_input": "{{user_input}}",
        "intent": "{{previous_intent}}"
    },
    
    # 嵌套数据结构
    "task_context": {
        "customer": {
            "name": "{{customer_name}}",
            "contact": "{{contact_info}}"
        }
    }
}
```

### 4.2 输出端口（output_ports）

输出端口定义如何将Agent的输出存储到工作流变量：

```python
output_ports = {
    # 将Agent输出的'answer'字段存储到'final_response'变量
    "answer": "final_response",
    
    # 将Agent输出的'result'字段存储到'processing_result'变量
    "result": "processing_result"
}
```

### 4.3 变量引用语法

```python
# 基本变量引用
"{{variable_name}}"

# 嵌套对象访问
"{{user.name}}"
"{{result.data.items[0]}}"

# 字符串模板（在上下文数据中）
"Hello {{user_name}}, your score is {{score}}"
```

### 4.4 最终结果提取

**重要更新**: 工作流的 `final_result` 现在返回**最后一个成功执行步骤的输出**，而不是所有上下文变量：

```python
# 以前的行为（返回所有变量）
final_result = {
    'user_input': 'hello',
    'user_id': 'cli_user', 
    'intent_type': 'chat',
    'final_response': '你好！有什么我可以帮忙的吗？'
}

# 现在的行为（只返回最后一步输出）
final_result = "你好！有什么我可以帮忙的吗？"  # 来自最后一步的output_ports
```

## 5. 条件执行

### 5.1 条件语法

```python
# 简单比较
condition = "{{confidence}} > 0.7"

# 逻辑运算
condition = "{{confidence}} > 0.7 and {{intent}} == 'question'"

# 存在性检查
condition = "{{user_input}} != None"

# 字符串匹配
condition = "{{intent_type}} == 'tool'"
```

### 5.2 条件执行示例

```python
AgentWorkflowStep(
    id="tool_handler",
    name="工具处理",
    agent_type="tool_agent",
    condition="{{intent_type}} == 'tool'",
    input_ports={"context_data": {"task": "{{user_input}}"}},
    output_ports={"result": "tool_result"}
),
AgentWorkflowStep(
    id="chat_handler", 
    name="聊天处理",
    agent_type="text_agent",
    condition="{{intent_type}} == 'chat'",
    input_ports={"context_data": {"question": "{{user_input}}"}},
    output_ports={"answer": "chat_response"}
)
```

## 6. Provider集成

### 6.1 Provider架构

所有Agent通过BaseAgent统一的Provider接口访问LLM：

```python
class BaseAgent:
    def __init__(self, provider_config: Dict[str, Any]):
        self.provider = None
        self.provider_config = provider_config
    
    async def initialize(self) -> bool:
        # 初始化Provider
        if self.provider_config.get('type') == 'openai':
            self.provider = OpenAIProvider(self.provider_config)
            return await self.provider.initialize()
        return False
```

### 6.2 Provider调用

```python
# 在Agent中调用Provider
response = await self.provider.generate_response(
    system_prompt="你是一个专业的AI助手",
    user_prompt="请回答用户的问题"
)
```

### 6.3 多Provider支持

```python
provider_configs = {
    "openai": {
        "type": "openai",
        "model_name": "gpt-4o-mini",
        "api_key": "your-api-key"
    },
    "anthropic": {
        "type": "anthropic", 
        "model_name": "claude-3-sonnet",
        "api_key": "your-api-key"
    }
}
```

## 7. 完整示例：智能问答系统

### 7.1 三步式工作流

```python
def create_intelligent_qa_workflow():
    """创建智能问答工作流"""
    steps = [
        # 步骤1：意图分析
        AgentWorkflowStep(
            id="analyze_intent",
            name="分析用户意图",
            agent_type="text_agent",
            task_description="分析用户输入，判断意图类型。请只返回以下三个选项之一：'tool'(需要工具调用)、'code'(需要复杂分析/计算)、'chat'(普通聊天)",
            input_ports={
                "context_data": {
                    "user_input": "{{user_input}}",
                    "instruction": "请仔细分析用户输入的意图。如果用户需要搜索信息、获取实时数据、访问网页等，请返回'tool'；如果用户需要复杂计算、数据分析、代码生成等，请返回'code'；如果是普通问答、聊天，请返回'chat'。请只返回一个单词。"
                }
            },
            output_ports={
                "answer": "intent_type"
            },
            response_style="concise",
            max_length=10
        ),
        
        # 步骤2A：工具调用（条件执行）
        AgentWorkflowStep(
            id="tool_execution",
            name="工具执行",
            agent_type="tool_agent",
            condition="{{intent_type}} == 'tool'",
            task_description="根据用户输入执行工具调用",
            input_ports={
                "context_data": {
                    "user_input": "{{user_input}}",
                    "task": "执行工具调用"
                }
            },
            output_ports={
                "result": "tool_result"
            },
            allowed_tools=[],  # 根据需要配置
            fallback_tools=[]
        ),
        
        # 步骤2B：代码分析（条件执行）
        AgentWorkflowStep(
            id="code_analysis",
            name="复杂分析",
            agent_type="code_agent",
            condition="{{intent_type}} == 'code'",
            task_description="根据用户需求执行复杂分析",
            input_ports={
                "input_data": "{{user_input}}"
            },
            output_ports={
                "result": "code_result"
            },
            expected_output_format="分析结果",
            allowed_libraries=[]
        ),
        
        # 步骤3：统一响应
        AgentWorkflowStep(
            id="unified_response",
            name="生成最终回复",
            agent_type="text_agent",
            task_description="根据用户问题和所有可用信息，生成友好、有用的回复",
            input_ports={
                "context_data": {
                    "user_input": "{{user_input}}",
                    "intent_type": "{{intent_type}}",
                    "tool_result": "{{tool_result}}",
                    "code_result": "{{code_result}}",
                    "instructions": "请根据用户的原始问题和可用的结果信息，生成一个友好、准确的回复。如果有工具调用结果，请基于结果回答；如果有代码分析结果，请解释结果；如果是普通聊天，请直接友好回复。"
                }
            },
            output_ports={
                "answer": "final_response"
            },
            response_style="helpful",
            max_length=500
        )
    ]
    
    return Workflow(
        name="智能问答系统",
        description="基于意图分析的智能问答工作流",
        steps=steps,
        input_schema={
            "user_input": {"type": "string", "description": "用户输入"}
        },
        output_schema={
            "final_response": {"type": "string", "description": "最终回答"}
        }
    )
```

### 7.2 执行示例

```python
# 创建BaseAgent实例
agent = BaseAgent(
    provider_config={
        'type': 'openai',
        'model_name': 'gpt-4o-mini'
    }
)

# 初始化Agent
success = await agent.initialize()
if not success:
    raise Exception("Provider初始化失败")

# 执行工作流
workflow = create_intelligent_qa_workflow()
result = await agent.run_workflow(
    workflow, 
    input_data={"user_input": "请帮我搜索今天的天气"}
)

print(f"回答: {result.final_result}")  # 现在直接是最终回答字符串
```

## 8. 最佳实践

### 8.1 Agent选择指南

- **TextAgent**: 用于纯文本处理，如对话、翻译、摘要
- **ToolAgent**: 用于需要外部工具的任务，如网页抓取、文件操作
- **CodeAgent**: 用于需要计算或数据处理的任务

### 8.2 性能优化

1. **工具预筛选**: 在Workflow设计时限制可用工具范围
2. **条件执行**: 使用条件避免不必要的Agent调用
3. **超时设置**: 为每个步骤设置合理的超时时间
4. **缓存机制**: 对相同输入启用结果缓存

### 8.3 错误处理

```python
AgentWorkflowStep(
    id="safe_step",
    name="安全执行步骤",
    agent_type="text_agent",
    retry_count=2,
    timeout=60,
    input_ports={
        "context_data": {"question": "{{user_input}}"}
    },
    output_ports={
        "answer": "response"
    }
)
```

### 8.4 调试技巧

1. **详细日志**: 启用详细的执行日志
2. **步骤验证**: 单独测试每个Agent步骤
3. **数据检查**: 验证输入输出端口的正确性
4. **条件测试**: 测试各种条件分支

### 8.5 数据流设计

1. **变量命名**: 使用清晰的变量名，如 `user_input`, `intent_type`, `final_response`
2. **数据传递**: 确保上下文变量在步骤间正确传递
3. **最终输出**: 工作流现在自动返回最后一步的输出，确保最后一步产生有意义的结果

这个指南涵盖了基于最新代码的Agent-as-Step架构的核心概念和实际应用，特别是新的最终结果提取机制和更新的数据结构。