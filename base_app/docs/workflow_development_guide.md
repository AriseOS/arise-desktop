# Agent-as-Step工作流开发指南

## 1. 快速入门

### 1.1 Agent-as-Step架构

Agent-as-Step是新一代工作流架构，将每个处理步骤抽象为独立的Agent。每个Agent都具备特定的能力（如文本处理、工具调用、代码执行），并通过统一的Provider接口与LLM交互。

### 1.2 核心概念

- **AgentWorkflow**: 基于Agent的工作流定义，包含多个Agent步骤
- **AgentWorkflowStep**: 工作流中的单个Agent步骤，指定Agent类型和配置
- **BaseStepAgent**: 所有Agent的基类，定义统一接口
- **Provider**: 统一的LLM提供者接口，支持多种LLM后端
- **AgentContext**: Agent执行时的上下文环境，包含变量和状态

### 1.3 三种核心Agent类型

1. **TextAgent**: 文本处理Agent，处理对话、问答、文本生成等
2. **ToolAgent**: 工具调用Agent，智能选择和执行各种工具
3. **CodeAgent**: 代码执行Agent，生成和安全执行代码

### 1.4 第一个Agent工作流

```python
from base_app.base_agent.core.schemas import AgentWorkflow, AgentWorkflowStep

def create_simple_qa_workflow():
    """创建一个简单的问答工作流"""
    steps = [
        AgentWorkflowStep(
            id="analyze_intent",
            name="分析用户意图",
            agent_type="text_agent",
            input_mapping={"question": "{{user_input}}"},
            output_mapping={"intent": "intent", "confidence": "confidence"},
            agent_config={
                "response_style": "analytical",
                "max_length": 200
            }
        ),
        AgentWorkflowStep(
            id="generate_answer",
            name="生成回答",
            agent_type="text_agent", 
            condition="{{confidence}} > 0.7",
            input_mapping={
                "question": "{{user_input}}",
                "context_data": {"intent": "{{intent}}"}
            },
            output_mapping={"final_answer": "answer"},
            agent_config={
                "response_style": "friendly",
                "max_length": 500
            }
        )
    ]
    
    return AgentWorkflow(
        name="简单问答工作流",
        description="基于Agent的问答处理流程",
        steps=steps,
        input_schema={
            "user_input": {"type": "string", "description": "用户输入"}
        },
        output_schema={
            "final_answer": {"type": "string", "description": "最终回答"}
        }
    )
```

## 2. AgentWorkflow架构

### 2.1 AgentWorkflow类定义

```python
class AgentWorkflow(BaseModel):
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
    
    # 元数据
    tags: List[str] = Field(default_factory=list, description="标签")
    author: str = Field(default="AgentCrafter", description="作者")
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
    id: str = Field(..., description="步骤唯一标识")
    name: str = Field(..., description="步骤名称")
    agent_type: str = Field(..., description="Agent类型")
    
    # 数据映射
    input_mapping: Dict[str, Any] = Field(default_factory=dict)
    output_mapping: Dict[str, str] = Field(default_factory=dict)
    
    # 执行控制
    condition: Optional[str] = Field(None, description="执行条件")
    retry_count: int = Field(default=0, description="重试次数")
    timeout: int = Field(default=300, description="超时时间(秒)")
    
    # Agent配置
    agent_config: Dict[str, Any] = Field(default_factory=dict)
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
    input_mapping={
        "question": "{{user_input}}",
        "context_data": {"previous_answer": "{{prev_result}}"}
    },
    output_mapping={
        "response": "answer",
        "confidence": "confidence"
    },
    agent_config={
        "response_style": "friendly",
        "max_length": 500,
        "temperature": 0.7
    }
)
```

#### 输入输出处理
```python
# TextAgent输入格式
TextAgentInput(
    question="用户问题",
    context_data={"key": "value"},
    response_style="friendly",
    max_length=500
)

# TextAgent输出格式
TextAgentOutput(
    success=True,
    answer="AI回答内容",
    confidence=0.85,
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
    input_mapping={
        "task_description": "{{task}}",
        "allowed_tools": ["browser_use", "llm_extract"],
        "confidence_threshold": 0.7
    },
    output_mapping={
        "result": "tool_result",
        "tool_used": "used_tool"
    },
    agent_config={
        "fallback_tools": ["llm_extract"],
        "max_retries": 2
    }
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
    input_mapping={
        "task_description": "{{task}}",
        "input_data": "{{data}}",
        "expected_output_format": "json"
    },
    output_mapping={
        "result": "processed_data",
        "code": "generated_code"
    },
    agent_config={
        "libraries_allowed": ["json", "re", "math"],
        "timeout": 30
    }
)
```

#### 安全执行环境
```python
# CodeAgent输入格式
CodeAgentInput(
    task_description="处理JSON数据并计算统计信息",
    input_data={"numbers": [1, 2, 3, 4, 5]},
    expected_output_format="{sum: int, avg: float}",
    libraries_allowed=["json", "math"]
)

# 安全检查包括：
# - AST语法检查
# - 危险函数检测（exec, eval, open等）
# - 未授权库导入检测
# - 限制执行环境
```

## 4. 数据映射和变量引用

### 4.1 输入映射（input_mapping）

输入映射定义如何从工作流变量构造Agent的输入：

```python
input_mapping = {
    # 直接变量引用
    "question": "{{user_input}}",
    
    # 嵌套对象构造
    "context_data": {
        "intent": "{{previous_intent}}",
        "confidence": "{{previous_confidence}}"
    },
    
    # 数组构造
    "allowed_tools": ["{{preferred_tool}}", "llm_extract"],
    
    # 常量值
    "max_length": 500,
    
    # 条件表达式
    "temperature": "{{confidence}} > 0.8 ? 0.3 : 0.7"
}
```

### 4.2 输出映射（output_mapping）

输出映射定义如何将Agent的输出存储到工作流变量：

```python
output_mapping = {
    # 将Agent输出的'answer'字段存储到'final_response'变量
    "final_response": "answer",
    
    # 将Agent输出的'confidence'字段存储到'response_confidence'变量
    "response_confidence": "confidence",
    
    # 将Agent输出的'metadata'字段存储到'processing_info'变量
    "processing_info": "metadata"
}
```

### 4.3 变量引用语法

```python
# 基本变量引用
"{{variable_name}}"

# 嵌套对象访问
"{{user.name}}"
"{{result.data.items[0]}}"

# 条件表达式
"{{confidence > 0.8 ? 'high' : 'low'}}"

# 数学运算
"{{score * 100}}"

# 字符串拼接
"Hello {{user_name}}, your score is {{score}}"
```

## 5. 条件执行

### 5.1 条件语法

```python
# 简单比较
condition = "{{confidence}} > 0.7"

# 逻辑运算
condition = "{{confidence}} > 0.7 && {{intent}} == 'question'"

# 存在性检查
condition = "{{user_input}} != null"

# 字符串匹配
condition = "{{category}} in ['urgent', 'important']"
```

### 5.2 条件执行示例

```python
AgentWorkflowStep(
    id="urgent_handler",
    name="紧急处理",
    agent_type="tool_agent",
    condition="{{priority}} == 'urgent'",
    input_mapping={...},
    output_mapping={...}
),
AgentWorkflowStep(
    id="normal_handler", 
    name="常规处理",
    agent_type="text_agent",
    condition="{{priority}} != 'urgent'",
    input_mapping={...},
    output_mapping={...}
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
            input_mapping={
                "question": "{{user_input}}",
                "context_data": {}
            },
            output_mapping={
                "intent": "intent",
                "confidence": "confidence",
                "analysis": "analysis"
            },
            agent_config={
                "response_style": "analytical",
                "max_length": 200
            }
        ),
        
        # 步骤2A：工具调用（条件执行）
        AgentWorkflowStep(
            id="tool_execution",
            name="工具执行",
            agent_type="tool_agent",
            condition="{{intent}} == 'tool_usage' && {{confidence}} > 0.7",
            input_mapping={
                "task_description": "{{analysis}}",
                "allowed_tools": ["browser_use", "llm_extract"],
                "confidence_threshold": 0.8
            },
            output_mapping={
                "tool_result": "result",
                "tool_used": "tool_used"
            },
            agent_config={
                "fallback_tools": ["llm_extract"]
            }
        ),
        
        # 步骤2B：文本对话（条件执行）
        AgentWorkflowStep(
            id="text_conversation",
            name="文本对话",
            agent_type="text_agent",
            condition="{{intent}} != 'tool_usage' || {{confidence}} <= 0.7",
            input_mapping={
                "question": "{{user_input}}",
                "context_data": {
                    "intent": "{{intent}}",
                    "analysis": "{{analysis}}"
                }
            },
            output_mapping={
                "text_response": "answer",
                "response_confidence": "confidence"
            },
            agent_config={
                "response_style": "friendly",
                "max_length": 500
            }
        ),
        
        # 步骤3：统一响应
        AgentWorkflowStep(
            id="unified_response",
            name="统一响应格式",
            agent_type="text_agent",
            input_mapping={
                "question": "{{user_input}}",
                "context_data": {
                    "tool_result": "{{tool_result}}",
                    "text_response": "{{text_response}}",
                    "tool_used": "{{tool_used}}"
                }
            },
            output_mapping={
                "final_answer": "answer",
                "response_type": "response_type"
            },
            agent_config={
                "response_style": "professional",
                "max_length": 600
            }
        )
    ]
    
    return AgentWorkflow(
        name="智能问答系统",
        description="基于意图分析的智能问答工作流",
        steps=steps,
        input_schema={
            "user_input": {"type": "string", "description": "用户输入"}
        },
        output_schema={
            "final_answer": {"type": "string", "description": "最终回答"},
            "response_type": {"type": "string", "description": "响应类型"}
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
result = await agent.execute_workflow(
    workflow_name="user_qa",
    input_data={"user_input": "请帮我搜索今天的天气"}
)

print(f"回答: {result.get('final_answer')}")
print(f"类型: {result.get('response_type')}")
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
    input_mapping={...},
    output_mapping={...},
    agent_config={
        "fallback_response": "抱歉，处理出现问题，请稍后重试"
    }
)
```

### 8.4 调试技巧

1. **详细日志**: 启用详细的执行日志
2. **步骤验证**: 单独测试每个Agent步骤
3. **数据检查**: 验证输入输出映射的正确性
4. **条件测试**: 测试各种条件分支

这个指南涵盖了Agent-as-Step架构的核心概念和实际应用，帮助开发者快速上手并构建强大的AI工作流系统。