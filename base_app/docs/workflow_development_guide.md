# Workflow自定义开发指南

## 1. 快速入门

### 1.1 Workflow是什么

Workflow（工作流）是BaseAgent执行复杂任务的核心机制。它将复杂的AI处理过程分解为多个步骤，每个步骤负责特定的功能，步骤间通过端口连接进行数据传递。

### 1.2 基本概念

- **Workflow**: 完整的工作流定义，包含多个步骤和执行配置
- **Step**: 工作流中的单个处理步骤，有特定的功能和类型
- **Port**: 步骤的数据接口，分为输入端口和输出端口
- **Connection**: 连接两个步骤端口的数据管道
- **Context**: 工作流执行时的上下文环境，包含变量和状态

### 1.3 第一个Hello World工作流

```python
from base_app.base_agent.core.schemas import (
    Workflow, WorkflowStep, StepType, StepPort, PortType, PortConnection
)

def create_hello_world_workflow():
    """创建一个简单的Hello World工作流"""
    steps = [
        WorkflowStep(
            id="greet",
            name="问候用户",
            step_type=StepType.CODE,
            input_ports=[
                StepPort(name="user_name", type=PortType.STRING, description="用户姓名")
            ],
            output_ports=[
                StepPort(name="greeting", type=PortType.STRING, description="问候语")
            ],
            code="""
user_name = variables.get('user_name', 'World')
greeting = f"Hello, {user_name}!"
print(f"生成问候语: {greeting}")

result = {
    'greeting': greeting
}
"""
        )
    ]
    
    return Workflow(
        name="Hello World工作流",
        description="一个简单的问候工作流",
        steps=steps,
        input_schema={
            "user_name": {"type": "string", "description": "用户姓名"}
        },
        output_schema={
            "greeting": {"type": "string", "description": "问候语"}
        }
    )
```

## 2. Workflow整体结构

### 2.1 Workflow类完整定义

```python
class Workflow(BaseModel):
    # 基础信息
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="工作流名称")
    description: str = Field(default="", description="工作流描述")
    version: str = Field(default="1.0.0", description="版本号")
    
    # 步骤定义
    steps: List[WorkflowStep] = Field(..., description="工作流步骤")
    
    # 输入输出定义
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    
    # 执行配置
    max_execution_time: int = Field(default=3600, description="最大执行时间(秒)")
    enable_parallel: bool = Field(default=False, description="是否启用并行执行")
    enable_cache: bool = Field(default=True, description="是否启用缓存")
    
    # 元数据
    tags: List[str] = Field(default_factory=list, description="标签")
    author: str = Field(default="AgentCrafter", description="作者")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
```

### 2.2 必需字段 vs 可选字段

#### 必需字段
- `name`: 工作流名称，用于标识和日志
- `steps`: 步骤列表，至少包含一个步骤

#### 常用可选字段
- `description`: 工作流描述，建议填写
- `input_schema`/`output_schema`: 输入输出定义，便于验证和文档
- `max_execution_time`: 执行超时时间，根据实际需要调整

#### 其他可选字段
- `version`, `tags`, `author`: 元数据信息
- `enable_parallel`, `enable_cache`: 性能优化选项

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

## 3. Steps详解

### 3.1 步骤类型概述

BaseAgent支持四种步骤类型：

| 类型 | 用途 | 适用场景 |
|------|------|----------|
| **CODE** | 执行Python代码 | 数据处理、逻辑判断、计算 |
| **MEMORY** | 内存操作 | 存储数据、搜索记忆、状态管理 |
| **TOOL** | 调用工具 | 浏览器操作、文件处理、API调用 |
| **AGENT** | 调用其他Agent | 复杂任务分解、专业化处理 |

### 3.2 CODE步骤

CODE步骤是最常用的步骤类型，用于执行自定义的Python代码。

#### 基本结构
```python
WorkflowStep(
    id="code_step",
    name="代码处理步骤",
    step_type=StepType.CODE,
    input_ports=[...],
    output_ports=[...],
    port_connections={...},
    code="""
# 你的Python代码
"""
)
```

#### 可用变量和函数
在CODE步骤中，你可以访问以下预定义变量：

```python
# 执行环境中可用的变量
variables      # 当前所有变量的字典
step_results   # 所有步骤结果的字典
context        # 执行上下文对象

# 内置函数
print()        # 输出到日志
len(), str(), int(), float()  # 基本函数
list(), dict() # 容器类型
```

#### 输入输出处理
```python
# 获取输入数据
user_input = variables.get('user_input', '')           # 从端口连接获取
config = variables.get('config', {})                   # 带默认值
previous_result = step_results.get('previous_step')    # 从步骤结果获取

# 处理逻辑
processed_data = process_function(user_input, config)

# 返回结果 - 必须是字典，键名对应输出端口
result = {
    'processed_text': processed_data,
    'word_count': len(processed_data.split()),
    'status': 'success'
}
```

#### 代码示例

**文本分析步骤**
```python
WorkflowStep(
    id="text_analyzer",
    name="文本分析",
    step_type=StepType.CODE,
    input_ports=[
        StepPort(name="text", type=PortType.STRING, description="待分析文本"),
        StepPort(name="language", type=PortType.STRING, description="语言类型", required=False)
    ],
    output_ports=[
        StepPort(name="analysis", type=PortType.DICT, description="分析结果"),
        StepPort(name="summary", type=PortType.STRING, description="摘要")
    ],
    code="""
import re
from collections import Counter

text = variables.get('text', '')
language = variables.get('language', 'zh-CN')

# 文本分析
word_count = len(text.split())
char_count = len(text)
sentence_count = len(re.findall(r'[.!?]+', text))

# 关键词提取（简单版本）
words = re.findall(r'\\b\\w+\\b', text.lower())
keywords = [word for word, count in Counter(words).most_common(5)]

# 生成摘要
if word_count > 50:
    summary = text[:100] + "..."
else:
    summary = text

analysis = {
    'word_count': word_count,
    'char_count': char_count,
    'sentence_count': sentence_count,
    'keywords': keywords,
    'language': language
}

print(f"分析完成: {word_count}词, {sentence_count}句")

result = {
    'analysis': analysis,
    'summary': summary
}
"""
)
```

#### 最佳实践

1. **错误处理**
```python
code="""
try:
    # 主要处理逻辑
    result_data = process_data(input_data)
    result = {'output': result_data, 'status': 'success'}
except Exception as e:
    print(f"处理失败: {e}")
    result = {'output': None, 'status': 'error', 'error': str(e)}
"""
```

2. **输入验证**
```python
code="""
# 验证必需输入
user_input = variables.get('user_input')
if not user_input:
    result = {'error': '缺少用户输入'}
    
# 验证输入类型
if not isinstance(user_input, str):
    result = {'error': '用户输入必须是字符串'}
    
# 主要逻辑...
"""
```

3. **日志记录**
```python
code="""
print(f"开始处理: {variables.get('user_input', '')[:50]}...")
# 处理逻辑
print(f"处理完成，生成结果长度: {len(result_text)}")
"""
```

### 3.3 MEMORY步骤

MEMORY步骤用于内存操作，包括存储、获取和搜索功能。

#### 基本结构
```python
WorkflowStep(
    id="memory_step",
    name="内存操作",
    step_type=StepType.MEMORY,
    memory_action="store|get|search",  # 操作类型
    memory_key="key_name",             # 存储键（store/get时使用）
    memory_value="value",              # 存储值（store时使用）
    query="search_query",              # 搜索查询（search时使用）
    params={"limit": 5}                # 额外参数
)
```

#### 三种操作类型

**1. 存储操作 (store)**
```python
WorkflowStep(
    id="store_interaction",
    name="存储交互记录",
    step_type=StepType.MEMORY,
    input_ports=[
        StepPort(name="content", type=PortType.STRING, description="要存储的内容")
    ],
    output_ports=[
        StepPort(name="stored", type=PortType.BOOLEAN, description="是否存储成功"),
        StepPort(name="content", type=PortType.STRING, description="存储的内容")
    ],
    port_connections={
        "content": PortConnection(
            target_port="content",
            source_step="previous_step",
            source_port="result"
        )
    },
    memory_action="store",
    memory_key="user_interaction",
    error_handling=ErrorHandling.CONTINUE
)
```

**2. 获取操作 (get)**
```python
WorkflowStep(
    id="get_user_profile",
    name="获取用户档案",
    step_type=StepType.MEMORY,
    output_ports=[
        StepPort(name="profile", type=PortType.DICT, description="用户档案")
    ],
    memory_action="get",
    memory_key="user_profile",
    params={"default": {}}  # 默认值
)
```

**3. 搜索操作 (search)**
```python
WorkflowStep(
    id="search_memories",
    name="搜索相关记忆",
    step_type=StepType.MEMORY,
    input_ports=[
        StepPort(name="query", type=PortType.STRING, description="搜索查询")
    ],
    output_ports=[
        StepPort(name="memories", type=PortType.LIST, description="搜索结果")
    ],
    port_connections={
        "query": PortConnection(
            target_port="query",
            source_step="input_analyzer",
            source_port="keywords"
        )
    },
    memory_action="search",
    params={"limit": 3, "user_id": "current_user"}
)
```

#### 参数配置

| 参数 | 用途 | 适用操作 |
|------|------|----------|
| `limit` | 搜索结果数量限制 | search |
| `user_id` | 用户ID过滤 | search |
| `default` | 获取失败时的默认值 | get |
| `persistent` | 是否持久化存储 | store |

### 3.4 TOOL步骤

TOOL步骤用于调用注册的工具，如浏览器工具、文件工具等。

#### 基本结构
```python
WorkflowStep(
    id="tool_step",
    name="工具调用",
    step_type=StepType.TOOL,
    tool_name="browser",      # 工具名称
    action="navigate",        # 工具动作
    params={                  # 动作参数
        "url": "https://example.com"
    }
)
```

#### 常用工具示例

**浏览器工具**
```python
WorkflowStep(
    id="web_search",
    name="网页搜索",
    step_type=StepType.TOOL,
    input_ports=[
        StepPort(name="search_query", type=PortType.STRING, description="搜索关键词")
    ],
    output_ports=[
        StepPort(name="search_results", type=PortType.LIST, description="搜索结果"),
        StepPort(name="page_content", type=PortType.STRING, description="页面内容")
    ],
    port_connections={
        "search_query": PortConnection(
            target_port="search_query",
            source_step="query_processor",
            source_port="processed_query"
        )
    },
    tool_name="browser",
    action="search",
    params={
        "engine": "google",
        "max_results": 5
    }
)
```

**文件工具**
```python
WorkflowStep(
    id="save_report",
    name="保存报告",
    step_type=StepType.TOOL,
    input_ports=[
        StepPort(name="content", type=PortType.STRING, description="报告内容"),
        StepPort(name="filename", type=PortType.STRING, description="文件名")
    ],
    output_ports=[
        StepPort(name="file_path", type=PortType.STRING, description="保存路径"),
        StepPort(name="success", type=PortType.BOOLEAN, description="是否成功")
    ],
    tool_name="file",
    action="write",
    params={
        "encoding": "utf-8",
        "create_dirs": True
    }
)
```

### 3.5 AGENT步骤

AGENT步骤用于调用其他Agent，实现复杂任务的分解和协作。

#### 基本结构
```python
WorkflowStep(
    id="agent_step",
    name="Agent调用",
    step_type=StepType.AGENT,
    agent_name="specialized_agent",  # Agent名称
    agent_input="input_data"         # 传递给Agent的输入
)
```

#### 示例
```python
WorkflowStep(
    id="analyze_sentiment",
    name="情感分析",
    step_type=StepType.AGENT,
    input_ports=[
        StepPort(name="text", type=PortType.STRING, description="待分析文本")
    ],
    output_ports=[
        StepPort(name="sentiment", type=PortType.STRING, description="情感极性"),
        StepPort(name="confidence", type=PortType.FLOAT, description="置信度")
    ],
    port_connections={
        "text": PortConnection(
            target_port="text", 
            source_step="text_processor",
            source_port="clean_text"
        )
    },
    agent_name="sentiment_analyzer",
    agent_input="{{text}}"  # 传统变量引用方式
)
```

## 4. 步骤间通信机制

### 4.1 端口连接模式

端口连接是推荐的数据传递方式，提供清晰的数据流定义。

#### 输入端口定义
```python
input_ports = [
    StepPort(
        name="user_message",           # 端口名称
        type=PortType.STRING,          # 数据类型
        description="用户消息内容",     # 端口描述
        required=True,                 # 是否必需
        default_value=None             # 默认值
    ),
    StepPort(
        name="context",
        type=PortType.DICT,
        description="上下文信息",
        required=False,
        default_value={}
    )
]
```

#### 输出端口定义
```python
output_ports = [
    StepPort(
        name="response",
        type=PortType.STRING, 
        description="AI响应"
    ),
    StepPort(
        name="tokens_used",
        type=PortType.INTEGER,
        description="使用的token数量"
    )
]
```

#### 端口连接配置
```python
port_connections = {
    "user_message": PortConnection(
        target_port="user_message",    # 本步骤的输入端口
        source_step="input_processor", # 数据来源步骤
        source_port="processed_text"   # 来源步骤的输出端口
    ),
    "context": PortConnection(
        target_port="context",
        source_step="context_manager", 
        source_port="current_context"
    )
}
```

### 4.2 数据传递

#### 支持的数据类型
```python
class PortType(str, Enum):
    STRING = "string"      # 字符串
    INTEGER = "integer"    # 整数
    FLOAT = "float"        # 浮点数
    BOOLEAN = "boolean"    # 布尔值
    LIST = "list"          # 列表
    DICT = "dict"          # 字典
    ANY = "any"            # 任意类型
```

#### 变量访问方式
```python
# 在CODE步骤中访问数据的三种方式：

# 1. 通过端口名直接访问（推荐）
user_input = variables.get('user_input')
config = variables.get('config', {})  # 带默认值

# 2. 通过步骤ID和端口名访问
specific_data = variables.get('step_id.port_name')

# 3. 通过步骤结果访问（原始数据）
raw_result = step_results.get('previous_step_id')
```

#### 结果返回格式
```python
# CODE步骤必须返回字典，键名对应输出端口
result = {
    'output_port1': value1,
    'output_port2': value2,
    'status': 'success'
}

# MEMORY步骤自动格式化返回：
# search操作: {"memories": [...]}
# store操作: {"stored": True, "content": "..."}
# get操作: 直接返回获取的值

# TOOL步骤返回工具执行结果
# AGENT步骤返回Agent执行结果
```

### 4.3 向后兼容模式

为了兼容旧版本，系统同时支持传统的变量引用方式：

#### 传统变量引用
```python
WorkflowStep(
    name="传统模式步骤",
    step_type=StepType.CODE,
    code="""
# 使用传统变量引用
user_input = variables.get('user_input', '')
previous_result = step_results.get('previous_step')
""",
    output_key="result"  # 使用output_key而不是output_ports
)

# 其他步骤中引用
WorkflowStep(
    name="引用步骤", 
    query="{{result}}",  # 使用{{}}语法引用
    memory_value="{{previous_result}}"
)
```

#### 混合使用策略
```python
# 可以在同一工作流中混合使用两种模式
steps = [
    # 新步骤使用端口连接
    WorkflowStep(
        id="modern_step",
        input_ports=[...],
        output_ports=[...],
        port_connections={...}
    ),
    
    # 旧步骤使用传统模式
    WorkflowStep(
        name="legacy_step",
        code="result = process({{modern_step_result}})",
        output_key="legacy_result"
    )
]
```

## 5. 高级特性

### 5.1 执行控制

#### 条件执行
```python
WorkflowStep(
    id="conditional_step",
    name="条件执行步骤",
    step_type=StepType.CODE,
    condition="{{confidence}} > 0.8",  # 执行条件
    code="""
# 只有当置信度大于0.8时才执行
result = {'action': 'high_confidence_processing'}
"""
)
```

#### 依赖关系
```python
WorkflowStep(
    id="dependent_step",
    name="依赖步骤",
    step_type=StepType.CODE,
    depends_on=["step1", "step2"],  # 依赖的步骤ID列表
    code="""
# 等待step1和step2都完成后才执行
result1 = step_results.get('step1')
result2 = step_results.get('step2')
combined_result = combine(result1, result2)
"""
)
```

#### 并行执行
```python
# 在Workflow级别启用并行执行
workflow = Workflow(
    name="并行工作流",
    enable_parallel=True,  # 启用并行执行
    steps=[
        # 这些步骤如果没有依赖关系，将并行执行
        WorkflowStep(id="parallel_step1", ...),
        WorkflowStep(id="parallel_step2", ...),
        WorkflowStep(id="parallel_step3", ...)
    ]
)
```

### 5.2 错误处理

#### 错误处理策略
```python
from base_app.base_agent.core.schemas import ErrorHandling

WorkflowStep(
    id="error_prone_step",
    name="可能出错的步骤",
    step_type=StepType.TOOL,
    error_handling=ErrorHandling.RETRY,  # 错误处理策略
    retry_count=3,                       # 重试次数
    timeout=60,                          # 超时时间(秒)
    tool_name="external_api",
    action="call"
)
```

错误处理策略选项：
- `ErrorHandling.STOP`: 停止整个工作流
- `ErrorHandling.CONTINUE`: 继续执行下一步
- `ErrorHandling.RETRY`: 重试当前步骤
- `ErrorHandling.SKIP`: 跳过当前步骤

#### 重试机制
```python
WorkflowStep(
    id="retry_step",
    name="重试步骤",
    step_type=StepType.CODE,
    retry_count=3,           # 最多重试3次
    error_handling=ErrorHandling.RETRY,
    code="""
import random
if random.random() < 0.3:  # 30%概率失败
    raise Exception("随机失败")
result = {'status': 'success'}
"""
)
```

#### 失败恢复
```python
WorkflowStep(
    id="robust_step",
    name="健壮步骤",
    step_type=StepType.CODE,
    error_handling=ErrorHandling.CONTINUE,
    code="""
try:
    # 主要处理逻辑
    main_result = risky_operation()
    result = {'data': main_result, 'status': 'success'}
except Exception as e:
    # 失败时的备用逻辑
    print(f"主要操作失败: {e}")
    fallback_result = safe_fallback()
    result = {'data': fallback_result, 'status': 'fallback'}
"""
)
```

### 5.3 性能优化

#### 缓存机制
```python
# 在Workflow级别启用缓存
workflow = Workflow(
    name="缓存工作流",
    enable_cache=True,  # 启用结果缓存
    steps=[...]
)

# 对于计算密集型步骤，缓存特别有效
WorkflowStep(
    id="expensive_computation",
    name="昂贵计算",
    step_type=StepType.CODE,
    code="""
# 这个计算结果会被缓存
import time
time.sleep(2)  # 模拟耗时操作
result = {'computed_value': complex_calculation()}
"""
)
```

#### 超时设置
```python
# 全局超时设置
workflow = Workflow(
    name="超时控制工作流",
    max_execution_time=1800,  # 30分钟超时
    steps=[...]
)

# 步骤级超时设置
WorkflowStep(
    id="long_running_step",
    name="长时间运行步骤",
    timeout=300,  # 5分钟超时
    step_type=StepType.TOOL,
    tool_name="slow_api",
    action="process"
)
```

#### 资源管理
```python
WorkflowStep(
    id="resource_aware_step",
    name="资源感知步骤",
    step_type=StepType.CODE,
    code="""
import gc
import psutil

# 检查内存使用
memory_usage = psutil.virtual_memory().percent
if memory_usage > 80:
    print(f"内存使用率高: {memory_usage}%")
    gc.collect()  # 强制垃圾回收

# 处理逻辑...
result = {'processed': True, 'memory_usage': memory_usage}
"""
)
```

## 6. 完整示例

### 6.1 简单示例

#### 文本处理工作流
```python
def create_text_processing_workflow():
    """创建文本处理工作流"""
    steps = [
        # 步骤1: 文本清理
        WorkflowStep(
            id="clean_text",
            name="文本清理",
            step_type=StepType.CODE,
            input_ports=[
                StepPort(name="raw_text", type=PortType.STRING, description="原始文本")
            ],
            output_ports=[
                StepPort(name="clean_text", type=PortType.STRING, description="清理后文本"),
                StepPort(name="removed_chars", type=PortType.INTEGER, description="移除字符数")
            ],
            code="""
import re

raw_text = variables.get('raw_text', '')
print(f"开始清理文本，长度: {len(raw_text)}")

# 移除特殊字符和多余空格
clean_text = re.sub(r'[^\w\s\u4e00-\u9fff]', '', raw_text)
clean_text = re.sub(r'\s+', ' ', clean_text).strip()

removed_chars = len(raw_text) - len(clean_text)
print(f"清理完成，移除 {removed_chars} 个字符")

result = {
    'clean_text': clean_text,
    'removed_chars': removed_chars
}
"""
        ),
        
        # 步骤2: 文本分析
        WorkflowStep(
            id="analyze_text",
            name="文本分析",
            step_type=StepType.CODE,
            input_ports=[
                StepPort(name="text", type=PortType.STRING, description="待分析文本")
            ],
            output_ports=[
                StepPort(name="analysis", type=PortType.DICT, description="分析结果")
            ],
            port_connections={
                "text": PortConnection(
                    target_port="text",
                    source_step="clean_text",
                    source_port="clean_text"
                )
            },
            code="""
text = variables.get('text', '')

# 基本统计
word_count = len(text.split())
char_count = len(text)
sentence_count = text.count('。') + text.count('.') + text.count('!') + text.count('?')

# 简单关键词提取
words = text.split()
word_freq = {}
for word in words:
    if len(word) > 1:  # 过滤单字符
        word_freq[word] = word_freq.get(word, 0) + 1

top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]

analysis = {
    'word_count': word_count,
    'char_count': char_count,
    'sentence_count': sentence_count,
    'top_words': top_words,
    'avg_word_length': char_count / word_count if word_count > 0 else 0
}

print(f"分析完成: {word_count}词, {sentence_count}句")

result = {
    'analysis': analysis
}
"""
        ),
        
        # 步骤3: 生成报告
        WorkflowStep(
            id="generate_report",
            name="生成报告",
            step_type=StepType.CODE,
            input_ports=[
                StepPort(name="original_text", type=PortType.STRING, description="原始文本"),
                StepPort(name="clean_text", type=PortType.STRING, description="清理后文本"),
                StepPort(name="analysis", type=PortType.DICT, description="分析结果"),
                StepPort(name="removed_chars", type=PortType.INTEGER, description="移除字符数")
            ],
            output_ports=[
                StepPort(name="report", type=PortType.STRING, description="文本处理报告")
            ],
            port_connections={
                "clean_text": PortConnection(
                    target_port="clean_text",
                    source_step="clean_text",
                    source_port="clean_text"
                ),
                "analysis": PortConnection(
                    target_port="analysis", 
                    source_step="analyze_text",
                    source_port="analysis"
                ),
                "removed_chars": PortConnection(
                    target_port="removed_chars",
                    source_step="clean_text", 
                    source_port="removed_chars"
                )
            },
            code="""
clean_text = variables.get('clean_text', '')
analysis = variables.get('analysis', {})
removed_chars = variables.get('removed_chars', 0)

# 生成报告
report = f'''文本处理报告
==================

原始文本长度: {len(variables.get('user_input', ''))} 字符
清理后长度: {len(clean_text)} 字符
移除字符数: {removed_chars}

分析结果:
- 词数: {analysis.get('word_count', 0)}
- 句数: {analysis.get('sentence_count', 0)}
- 平均词长: {analysis.get('avg_word_length', 0):.2f}

高频词汇:
'''

for word, freq in analysis.get('top_words', []):
    report += f"- {word}: {freq}次\\n"

print("报告生成完成")

result = {
    'report': report
}
"""
        )
    ]
    
    return Workflow(
        name="文本处理工作流",
        description="清理、分析文本并生成处理报告",
        steps=steps,
        input_schema={
            "user_input": {"type": "string", "description": "待处理的原始文本"}
        },
        output_schema={
            "report": {"type": "string", "description": "文本处理报告"}
        }
    )
```

#### 数据转换工作流
```python
def create_data_transformation_workflow():
    """创建数据转换工作流"""
    steps = [
        # 步骤1: 数据验证
        WorkflowStep(
            id="validate_data",
            name="数据验证",
            step_type=StepType.CODE,
            input_ports=[
                StepPort(name="raw_data", type=PortType.ANY, description="原始数据")
            ],
            output_ports=[
                StepPort(name="validated_data", type=PortType.DICT, description="验证后数据"),
                StepPort(name="validation_errors", type=PortType.LIST, description="验证错误")
            ],
            code="""
import json

raw_data = variables.get('raw_data')
errors = []
validated_data = {}

try:
    # 如果是字符串，尝试解析为JSON
    if isinstance(raw_data, str):
        validated_data = json.loads(raw_data)
    elif isinstance(raw_data, dict):
        validated_data = raw_data
    else:
        errors.append(f"不支持的数据类型: {type(raw_data)}")
        
    # 验证必需字段
    required_fields = ['id', 'name', 'value']
    for field in required_fields:
        if field not in validated_data:
            errors.append(f"缺少必需字段: {field}")
            
    # 验证数据类型
    if 'value' in validated_data and not isinstance(validated_data['value'], (int, float)):
        errors.append("value字段必须是数字")
        
except json.JSONDecodeError as e:
    errors.append(f"JSON解析错误: {e}")
except Exception as e:
    errors.append(f"验证错误: {e}")

print(f"数据验证完成，发现 {len(errors)} 个错误")

result = {
    'validated_data': validated_data,
    'validation_errors': errors
}
"""
        ),
        
        # 步骤2: 数据转换
        WorkflowStep(
            id="transform_data",
            name="数据转换",
            step_type=StepType.CODE,
            input_ports=[
                StepPort(name="data", type=PortType.DICT, description="待转换数据"),
                StepPort(name="errors", type=PortType.LIST, description="验证错误")
            ],
            output_ports=[
                StepPort(name="transformed_data", type=PortType.DICT, description="转换后数据"),
                StepPort(name="success", type=PortType.BOOLEAN, description="转换是否成功")
            ],
            port_connections={
                "data": PortConnection(
                    target_port="data",
                    source_step="validate_data",
                    source_port="validated_data"
                ),
                "errors": PortConnection(
                    target_port="errors",
                    source_step="validate_data",
                    source_port="validation_errors"
                )
            },
            condition="{{errors}} == []",  # 只有没有验证错误时才执行
            code="""
data = variables.get('data', {})
errors = variables.get('errors', [])

if errors:
    print(f"由于验证错误，跳过数据转换: {errors}")
    result = {
        'transformed_data': {},
        'success': False
    }
else:
    # 数据转换逻辑
    transformed_data = {
        'id': str(data.get('id', '')),
        'name': data.get('name', '').upper(),
        'value': float(data.get('value', 0)),
        'processed_at': datetime.now().isoformat(),
        'category': 'processed'
    }
    
    # 添加计算字段
    if transformed_data['value'] > 100:
        transformed_data['level'] = 'high'
    elif transformed_data['value'] > 50:
        transformed_data['level'] = 'medium'
    else:
        transformed_data['level'] = 'low'
    
    print(f"数据转换完成: {transformed_data['name']} -> {transformed_data['level']}")
    
    result = {
        'transformed_data': transformed_data,
        'success': True
    }
"""
        ),
        
        # 步骤3: 数据存储
        WorkflowStep(
            id="store_data",
            name="数据存储", 
            step_type=StepType.MEMORY,
            input_ports=[
                StepPort(name="data", type=PortType.DICT, description="要存储的数据"),
                StepPort(name="success", type=PortType.BOOLEAN, description="是否成功")
            ],
            output_ports=[
                StepPort(name="stored", type=PortType.BOOLEAN, description="存储结果")
            ],
            port_connections={
                "data": PortConnection(
                    target_port="data",
                    source_step="transform_data", 
                    source_port="transformed_data"
                ),
                "success": PortConnection(
                    target_port="success",
                    source_step="transform_data",
                    source_port="success"
                )
            },
            condition="{{success}} == True",  # 只有转换成功时才存储
            memory_action="store",
            memory_key="transformed_record",
            error_handling=ErrorHandling.CONTINUE
        )
    ]
    
    return Workflow(
        name="数据转换工作流",
        description="验证、转换和存储数据",
        steps=steps,
        input_schema={
            "raw_data": {"type": "any", "description": "原始数据，支持JSON字符串或字典"}
        },
        output_schema={
            "transformed_data": {"type": "object", "description": "转换后的数据"},
            "success": {"type": "boolean", "description": "处理是否成功"}
        }
    )
```

### 6.2 复杂示例

#### 多步骤AI对话流程
```python
def create_ai_conversation_workflow():
    """创建AI对话工作流"""
    steps = [
        # 步骤1: 输入预处理
        WorkflowStep(
            id="preprocess_input",
            name="输入预处理",
            step_type=StepType.CODE,
            input_ports=[
                StepPort(name="user_message", type=PortType.STRING, description="用户消息"),
                StepPort(name="user_id", type=PortType.STRING, description="用户ID")
            ],
            output_ports=[
                StepPort(name="clean_message", type=PortType.STRING, description="清理后消息"),
                StepPort(name="message_type", type=PortType.STRING, description="消息类型"),
                StepPort(name="user_id", type=PortType.STRING, description="用户ID")
            ],
            code="""
import re

user_message = variables.get('user_message', '').strip()
user_id = variables.get('user_id', 'anonymous')

# 清理消息
clean_message = re.sub(r'\\s+', ' ', user_message)
clean_message = clean_message.replace('\\n', ' ')

# 检测消息类型
if '?' in clean_message or clean_message.startswith(('什么', '怎么', '为什么', '如何')):
    message_type = 'question'
elif any(word in clean_message for word in ['谢谢', '感谢', '再见', '拜拜']):
    message_type = 'social'
elif any(word in clean_message for word in ['帮助', '求助', '问题')):
    message_type = 'help_request'
else:
    message_type = 'general'

print(f"预处理完成: {len(clean_message)}字符, 类型: {message_type}")

result = {
    'clean_message': clean_message,
    'message_type': message_type,
    'user_id': user_id
}
"""
        ),
        
        # 步骤2: 上下文检索
        WorkflowStep(
            id="retrieve_context",
            name="上下文检索",
            step_type=StepType.MEMORY,
            input_ports=[
                StepPort(name="message", type=PortType.STRING, description="用户消息"),
                StepPort(name="user_id", type=PortType.STRING, description="用户ID")
            ],
            output_ports=[
                StepPort(name="memories", type=PortType.LIST, description="相关记忆")
            ],
            port_connections={
                "message": PortConnection(
                    target_port="message",
                    source_step="preprocess_input",
                    source_port="clean_message"
                ),
                "user_id": PortConnection(
                    target_port="user_id",
                    source_step="preprocess_input", 
                    source_port="user_id"
                )
            },
            memory_action="search",
            params={"limit": 5}
        ),
        
        # 步骤3: 意图识别
        WorkflowStep(
            id="detect_intent",
            name="意图识别",
            step_type=StepType.CODE,
            input_ports=[
                StepPort(name="message", type=PortType.STRING, description="清理后消息"),
                StepPort(name="message_type", type=PortType.STRING, description="消息类型"),
                StepPort(name="context", type=PortType.LIST, description="上下文记忆")
            ],
            output_ports=[
                StepPort(name="intent", type=PortType.STRING, description="用户意图"),
                StepPort(name="confidence", type=PortType.FLOAT, description="置信度"),
                StepPort(name="entities", type=PortType.LIST, description="实体列表")
            ],
            port_connections={
                "message": PortConnection(
                    target_port="message",
                    source_step="preprocess_input",
                    source_port="clean_message"
                ),
                "message_type": PortConnection(
                    target_port="message_type",
                    source_step="preprocess_input",
                    source_port="message_type"
                ),
                "context": PortConnection(
                    target_port="context",
                    source_step="retrieve_context",
                    source_port="memories"
                )
            },
            code="""
import re

message = variables.get('message', '')
message_type = variables.get('message_type', 'general')
context = variables.get('context', [])

# 简单的意图识别逻辑
intent_keywords = {
    'weather': ['天气', '气温', '下雨', '晴天', '阴天'],
    'time': ['时间', '几点', '日期', '今天', '明天'],
    'booking': ['预订', '预约', '订餐', '订票', '预定'],
    'complaint': ['投诉', '问题', '故障', '不满', '错误'],
    'information': ['信息', '介绍', '说明', '详情', '资料']
}

detected_intent = 'general'
confidence = 0.5
entities = []

# 检测意图
for intent, keywords in intent_keywords.items():
    if any(keyword in message for keyword in keywords):
        detected_intent = intent
        confidence = 0.8
        break

# 提取实体（简单的命名实体识别）
# 提取时间实体
time_patterns = [r'\\d{1,2}[点时]', r'\\d{4}年\\d{1,2}月\\d{1,2}日']
for pattern in time_patterns:
    matches = re.findall(pattern, message)
    for match in matches:
        entities.append({'type': 'time', 'value': match})

# 考虑上下文调整置信度
if context and len(context) > 0:
    confidence += 0.1

print(f"意图识别: {detected_intent} (置信度: {confidence:.2f})")

result = {
    'intent': detected_intent,
    'confidence': confidence,
    'entities': entities
}
"""
        ),
        
        # 步骤4: 响应生成
        WorkflowStep(
            id="generate_response",
            name="响应生成",
            step_type=StepType.CODE,
            input_ports=[
                StepPort(name="message", type=PortType.STRING, description="用户消息"),
                StepPort(name="intent", type=PortType.STRING, description="用户意图"),
                StepPort(name="confidence", type=PortType.FLOAT, description="置信度"),
                StepPort(name="entities", type=PortType.LIST, description="实体列表"),
                StepPort(name="context", type=PortType.LIST, description="上下文")
            ],
            output_ports=[
                StepPort(name="response", type=PortType.STRING, description="AI响应"),
                StepPort(name="response_type", type=PortType.STRING, description="响应类型")
            ],
            port_connections={
                "message": PortConnection(
                    target_port="message",
                    source_step="preprocess_input",
                    source_port="clean_message"
                ),
                "intent": PortConnection(
                    target_port="intent",
                    source_step="detect_intent",
                    source_port="intent"
                ),
                "confidence": PortConnection(
                    target_port="confidence", 
                    source_step="detect_intent",
                    source_port="confidence"
                ),
                "entities": PortConnection(
                    target_port="entities",
                    source_step="detect_intent",
                    source_port="entities"
                ),
                "context": PortConnection(
                    target_port="context",
                    source_step="retrieve_context",
                    source_port="memories"
                )
            },
            code="""
import datetime

message = variables.get('message', '')
intent = variables.get('intent', 'general')
confidence = variables.get('confidence', 0.5)
entities = variables.get('entities', [])
context = variables.get('context', [])

# 根据意图生成响应
if intent == 'weather':
    response = "我无法实时获取天气信息，建议您查看天气应用或网站获取最新天气预报。"
    response_type = "information"
    
elif intent == 'time':
    current_time = datetime.datetime.now()
    response = f"当前时间是 {current_time.strftime('%Y年%m月%d日 %H:%M:%S')}"
    response_type = "direct_answer"
    
elif intent == 'booking':
    response = "请问您需要预订什么服务？我可以帮您转接到相关部门。"
    response_type = "clarification"
    
elif intent == 'complaint':
    response = "很抱歉给您带来不便。请详细描述遇到的问题，我会尽力帮助您解决。"
    response_type = "empathy"
    
elif intent == 'information':
    if context:
        # 基于上下文提供信息
        response = f"根据我的了解，{message}相关的信息如下：[基于历史对话的信息]"
    else:
        response = "请问您需要了解哪方面的具体信息？我会为您详细说明。"
    response_type = "information"
    
else:
    # 通用响应
    if confidence < 0.6:
        response = "我没有完全理解您的意思，您能再详细说明一下吗？"
        response_type = "clarification"
    else:
        response = f"关于您提到的"{message}"，我理解您的意思。让我为您提供帮助。"
        response_type = "acknowledgment"

# 如果提取到实体，在响应中体现
if entities:
    time_entities = [e['value'] for e in entities if e['type'] == 'time']
    if time_entities:
        response += f" 我注意到您提到了时间：{', '.join(time_entities)}。"

print(f"响应生成完成: {len(response)}字符, 类型: {response_type}")

result = {
    'response': response,
    'response_type': response_type
}
"""
        ),
        
        # 步骤5: 对话记录存储
        WorkflowStep(
            id="store_conversation",
            name="存储对话记录",
            step_type=StepType.MEMORY,
            input_ports=[
                StepPort(name="user_message", type=PortType.STRING, description="用户消息"),
                StepPort(name="ai_response", type=PortType.STRING, description="AI响应"),
                StepPort(name="user_id", type=PortType.STRING, description="用户ID"),
                StepPort(name="intent", type=PortType.STRING, description="识别意图")
            ],
            output_ports=[
                StepPort(name="stored", type=PortType.BOOLEAN, description="是否存储成功")
            ],
            port_connections={
                "user_message": PortConnection(
                    target_port="user_message",
                    source_step="preprocess_input",
                    source_port="clean_message"
                ),
                "ai_response": PortConnection(
                    target_port="ai_response",
                    source_step="generate_response",
                    source_port="response"
                ),
                "user_id": PortConnection(
                    target_port="user_id",
                    source_step="preprocess_input",
                    source_port="user_id"
                ),
                "intent": PortConnection(
                    target_port="intent",
                    source_step="detect_intent",
                    source_port="intent"
                )
            },
            memory_action="store",
            memory_key="conversation_history",
            error_handling=ErrorHandling.CONTINUE
        )
    ]
    
    return Workflow(
        name="AI对话工作流",
        description="完整的AI对话处理流程，包括预处理、意图识别、响应生成和记录存储",
        steps=steps,
        input_schema={
            "user_message": {"type": "string", "description": "用户输入消息"},
            "user_id": {"type": "string", "description": "用户唯一标识", "optional": True}
        },
        output_schema={
            "response": {"type": "string", "description": "AI生成的响应"},
            "response_type": {"type": "string", "description": "响应类型"},
            "intent": {"type": "string", "description": "识别的用户意图"},
            "confidence": {"type": "number", "description": "意图识别置信度"}
        },
        max_execution_time=300,  # 5分钟超时
        enable_cache=True
    )
```

### 6.3 实际应用案例

#### 客服机器人工作流
```python
def create_customer_service_workflow():
    """创建客服机器人工作流"""
    steps = [
        # 步骤1: 客户身份验证
        WorkflowStep(
            id="verify_customer",
            name="客户身份验证",
            step_type=StepType.CODE,
            input_ports=[
                StepPort(name="customer_id", type=PortType.STRING, description="客户ID"),
                StepPort(name="phone", type=PortType.STRING, description="电话号码", required=False)
            ],
            output_ports=[
                StepPort(name="customer_info", type=PortType.DICT, description="客户信息"),
                StepPort(name="verified", type=PortType.BOOLEAN, description="是否验证通过"),
                StepPort(name="customer_level", type=PortType.STRING, description="客户等级")
            ],
            code="""
customer_id = variables.get('customer_id', '')
phone = variables.get('phone', '')

# 模拟客户数据库查询
customer_database = {
    'C001': {'name': '张三', 'phone': '138****1234', 'level': 'VIP', 'account_status': 'active'},
    'C002': {'name': '李四', 'phone': '139****5678', 'level': 'Gold', 'account_status': 'active'},
    'C003': {'name': '王五', 'phone': '137****9012', 'level': 'Silver', 'account_status': 'suspended'}
}

verified = False
customer_info = {}
customer_level = 'Unknown'

if customer_id in customer_database:
    customer_info = customer_database[customer_id]
    customer_level = customer_info['level']
    
    # 如果提供了电话号码，进行二次验证
    if phone:
        if phone in customer_info['phone']:
            verified = True
        else:
            verified = False
            print(f"电话号码不匹配: {phone}")
    else:
        verified = True  # 只有客户ID时也认为验证通过
        
    if customer_info['account_status'] != 'active':
        verified = False
        print(f"客户账户状态异常: {customer_info['account_status']}")
else:
    print(f"未找到客户: {customer_id}")

print(f"客户验证: {'通过' if verified else '失败'}, 等级: {customer_level}")

result = {
    'customer_info': customer_info,
    'verified': verified,
    'customer_level': customer_level
}
"""
        ),
        
        # 步骤2: 问题分类
        WorkflowStep(
            id="classify_issue",
            name="问题分类",
            step_type=StepType.CODE,
            input_ports=[
                StepPort(name="issue_description", type=PortType.STRING, description="问题描述"),
                StepPort(name="customer_level", type=PortType.STRING, description="客户等级")
            ],
            output_ports=[
                StepPort(name="category", type=PortType.STRING, description="问题类别"),
                StepPort(name="priority", type=PortType.STRING, description="优先级"),
                StepPort(name="department", type=PortType.STRING, description="负责部门")
            ],
            port_connections={
                "customer_level": PortConnection(
                    target_port="customer_level",
                    source_step="verify_customer",
                    source_port="customer_level"
                )
            },
            code="""
issue_description = variables.get('issue_description', '').lower()
customer_level = variables.get('customer_level', 'Unknown')

# 问题分类规则
categories = {
    'billing': ['账单', '费用', '扣费', '付款', '发票'],
    'technical': ['故障', '无法', '错误', '问题', '连接'],
    'account': ['密码', '登录', '注册', '账户', '权限'],
    'product': ['功能', '使用', '操作', '设置', '配置'],
    'complaint': ['投诉', '不满', '服务', '态度', '质量']
}

category = 'general'
for cat, keywords in categories.items():
    if any(keyword in issue_description for keyword in keywords):
        category = cat
        break

# 根据客户等级和问题类别确定优先级
if customer_level == 'VIP':
    priority = 'high'
elif customer_level == 'Gold':
    priority = 'medium' if category in ['billing', 'complaint'] else 'normal'
elif customer_level == 'Silver':
    priority = 'medium' if category == 'complaint' else 'normal'
else:
    priority = 'low'

# 确定负责部门
department_mapping = {
    'billing': 'finance',
    'technical': 'tech_support', 
    'account': 'account_service',
    'product': 'product_support',
    'complaint': 'customer_relations',
    'general': 'general_service'
}

department = department_mapping.get(category, 'general_service')

print(f"问题分类: {category}, 优先级: {priority}, 部门: {department}")

result = {
    'category': category,
    'priority': priority,
    'department': department
}
"""
        ),
        
        # 步骤3: 生成解决方案
        WorkflowStep(
            id="generate_solution",
            name="生成解决方案",
            step_type=StepType.CODE,
            input_ports=[
                StepPort(name="category", type=PortType.STRING, description="问题类别"),
                StepPort(name="priority", type=PortType.STRING, description="优先级"),
                StepPort(name="customer_info", type=PortType.DICT, description="客户信息"),
                StepPort(name="issue_description", type=PortType.STRING, description="问题描述")
            ],
            output_ports=[
                StepPort(name="solution", type=PortType.STRING, description="解决方案"),
                StepPort(name="next_steps", type=PortType.LIST, description="后续步骤"),
                StepPort(name="escalate", type=PortType.BOOLEAN, description="是否需要升级")
            ],
            port_connections={
                "category": PortConnection(
                    target_port="category",
                    source_step="classify_issue",
                    source_port="category"
                ),
                "priority": PortConnection(
                    target_port="priority",
                    source_step="classify_issue", 
                    source_port="priority"
                ),
                "customer_info": PortConnection(
                    target_port="customer_info",
                    source_step="verify_customer",
                    source_port="customer_info"
                )
            },
            code="""
category = variables.get('category', 'general')
priority = variables.get('priority', 'normal')
customer_info = variables.get('customer_info', {})
issue_description = variables.get('issue_description', '')

customer_name = customer_info.get('name', '客户')

# 根据问题类别生成解决方案
solutions = {
    'billing': f"尊敬的{customer_name}，关于您的账单问题，我为您查询到以下信息：\\n1. 请核对您的消费记录\\n2. 如有疑问可申请详细账单\\n3. 支持在线支付和分期付款",
    
    'technical': f"{customer_name}您好，针对您遇到的技术问题，请尝试以下解决步骤：\\n1. 重启设备并检查网络连接\\n2. 清除缓存并更新到最新版本\\n3. 如问题持续，我们将安排技术人员联系您",
    
    'account': f"{customer_name}您好，关于账户相关问题：\\n1. 您可以通过短信验证重置密码\\n2. 建议启用双重验证保护账户安全\\n3. 如需修改绑定信息，请提供身份验证",
    
    'product': f"{customer_name}您好，关于产品使用问题：\\n1. 建议查看用户手册和在线教程\\n2. 可参加我们的产品培训课程\\n3. 如需个性化配置，可预约专家指导",
    
    'complaint': f"非常抱歉给{customer_name}您带来不便，我们高度重视您的反馈：\\n1. 我会将您的意见转达给相关部门\\n2. 48小时内会有专人跟进处理\\n3. 我们将采取措施避免类似问题再次发生"
}

solution = solutions.get(category, f"{customer_name}您好，感谢您的咨询，我们会认真处理您的问题。")

# 确定后续步骤
next_steps = []
escalate = False

if priority == 'high':
    next_steps = [
        "立即转接人工客服",
        "15分钟内电话回访", 
        "创建VIP优先工单"
    ]
    escalate = True
elif priority == 'medium':
    next_steps = [
        "创建工单跟进",
        "24小时内回访",
        "发送邮件确认"
    ]
    escalate = category in ['complaint', 'technical']
else:
    next_steps = [
        "发送解决方案邮件",
        "3个工作日内跟进",
        "满意度调查"
    ]

print(f"解决方案生成完成，是否升级: {escalate}")

result = {
    'solution': solution,
    'next_steps': next_steps,
    'escalate': escalate
}
"""
        ),
        
        # 步骤4: 创建工单
        WorkflowStep(
            id="create_ticket",
            name="创建工单",
            step_type=StepType.MEMORY,
            input_ports=[
                StepPort(name="customer_info", type=PortType.DICT, description="客户信息"),
                StepPort(name="category", type=PortType.STRING, description="问题类别"),
                StepPort(name="priority", type=PortType.STRING, description="优先级"),
                StepPort(name="department", type=PortType.STRING, description="负责部门"),
                StepPort(name="issue_description", type=PortType.STRING, description="问题描述"),
                StepPort(name="solution", type=PortType.STRING, description="解决方案")
            ],
            output_ports=[
                StepPort(name="ticket_id", type=PortType.STRING, description="工单ID")
            ],
            port_connections={
                "customer_info": PortConnection(
                    target_port="customer_info",
                    source_step="verify_customer",
                    source_port="customer_info"
                ),
                "category": PortConnection(
                    target_port="category",
                    source_step="classify_issue",
                    source_port="category"
                ),
                "priority": PortConnection(
                    target_port="priority",
                    source_step="classify_issue",
                    source_port="priority"
                ),
                "department": PortConnection(
                    target_port="department", 
                    source_step="classify_issue",
                    source_port="department"
                ),
                "solution": PortConnection(
                    target_port="solution",
                    source_step="generate_solution",
                    source_port="solution"
                )
            },
            memory_action="store",
            memory_key="customer_ticket",
            error_handling=ErrorHandling.CONTINUE
        )
    ]
    
    return Workflow(
        name="客服机器人工作流",
        description="完整的客服处理流程：身份验证、问题分类、解决方案生成和工单创建",
        steps=steps,
        input_schema={
            "customer_id": {"type": "string", "description": "客户ID"},
            "issue_description": {"type": "string", "description": "问题描述"},
            "phone": {"type": "string", "description": "电话号码", "optional": True}
        },
        output_schema={
            "solution": {"type": "string", "description": "解决方案"},
            "next_steps": {"type": "array", "description": "后续步骤"},
            "escalate": {"type": "boolean", "description": "是否需要升级"},
            "ticket_id": {"type": "string", "description": "工单ID"}
        },
        max_execution_time=180,
        enable_cache=True,
        tags=["customer_service", "automated_response"]
    )
```

## 7. 开发和调试

### 7.1 开发环境设置

```python
# 开发时的基本设置
import logging
from base_app.base_agent.core import BaseAgent, AgentConfig

# 设置详细日志
logging.basicConfig(level=logging.DEBUG)

# 创建开发用Agent
config = AgentConfig(
    name="开发测试Agent",
    enable_logging=True,
    log_level="DEBUG"
)

agent = BaseAgent(config=config, enable_memory=True)
```

### 7.2 测试工作流

```python
async def test_workflow():
    """测试工作流函数"""
    # 创建工作流
    workflow = create_text_processing_workflow()
    
    # 准备测试数据
    test_input = {
        "user_input": "这是一个测试文本，包含一些特殊字符！@#$%^&*()和多余的    空格。"
    }
    
    # 执行工作流
    result = await agent.run_workflow(workflow, test_input)
    
    # 检查结果
    assert result.success, f"工作流执行失败: {result.error_message}"
    assert "report" in result.output_variables, "缺少报告输出"
    
    print("测试通过！")
    print(f"报告内容: {result.output_variables['report']}")

# 运行测试
import asyncio
asyncio.run(test_workflow())
```

### 7.3 调试技巧

1. **使用print语句调试**
```python
code="""
print(f"调试: 输入变量 = {variables}")
print(f"调试: 步骤结果 = {step_results}")

# 主要逻辑
result = process_data()

print(f"调试: 输出结果 = {result}")
"""
```

2. **分步测试**
```python
# 只测试前几个步骤
test_workflow = Workflow(
    name="调试工作流",
    steps=original_workflow.steps[:2]  # 只执行前2个步骤
)
```

3. **添加调试步骤**
```python
debug_step = WorkflowStep(
    id="debug_checkpoint",
    name="调试检查点",
    step_type=StepType.CODE,
    code="""
print("=== 调试检查点 ===")
print(f"当前变量: {variables}")
print(f"步骤结果: {step_results}")
print("==================")
result = {'debug': 'ok'}
"""
)
```

### 7.4 日志和监控

```python
# 在步骤中添加详细日志
code="""
import logging
logger = logging.getLogger(__name__)

logger.info(f"开始处理: {variables.get('user_input', '')[:50]}...")

try:
    # 处理逻辑
    result_data = complex_processing()
    logger.info(f"处理成功，结果长度: {len(result_data)}")
    
except Exception as e:
    logger.error(f"处理失败: {e}", exc_info=True)
    raise

result = {'output': result_data}
"""
```

## 8. 最佳实践

### 8.1 工作流设计原则

1. **单一职责**: 每个步骤只负责一个明确的功能
2. **最小化依赖**: 减少步骤间的复杂依赖关系
3. **错误处理**: 为每个步骤考虑错误情况
4. **可测试性**: 确保每个步骤可以独立测试
5. **可重用性**: 设计可以在多个工作流中重用的步骤

### 8.2 命名规范

```python
# 步骤ID命名：动词_名词的形式
"validate_input"      # 验证输入
"process_text"        # 处理文本
"generate_response"   # 生成响应
"store_result"        # 存储结果

# 端口命名：名词形式，描述清晰
"user_message"        # 用户消息
"processed_data"      # 处理后数据
"analysis_result"     # 分析结果
"error_info"          # 错误信息

# 工作流命名：功能描述_workflow
"text_processing_workflow"
"customer_service_workflow"
"data_analysis_workflow"
```

### 8.3 模块化和复用

```python
# 创建可重用的步骤模板
def create_text_cleaner_step(step_id: str, input_port: str = "raw_text"):
    """创建文本清理步骤模板"""
    return WorkflowStep(
        id=step_id,
        name="文本清理",
        step_type=StepType.CODE,
        input_ports=[
            StepPort(name=input_port, type=PortType.STRING, description="原始文本")
        ],
        output_ports=[
            StepPort(name="clean_text", type=PortType.STRING, description="清理后文本")
        ],
        code="""
import re
raw_text = variables.get('{}', '')
clean_text = re.sub(r'\\s+', ' ', raw_text).strip()
result = {{'clean_text': clean_text}}
""".format(input_port)
    )

# 组合成复杂工作流
def create_text_analysis_workflow():
    steps = [
        create_text_cleaner_step("clean_input", "user_input"),
        create_sentiment_analyzer_step("analyze_sentiment"),
        create_report_generator_step("generate_report")
    ]
    return Workflow(name="文本分析工作流", steps=steps)
```

### 8.4 性能考虑

1. **避免在循环中执行复杂操作**
```python
# 不好的做法
code="""
results = []
for item in large_list:
    complex_result = expensive_operation(item)  # 每次都执行昂贵操作
    results.append(complex_result)
"""

# 好的做法
code="""
# 批量处理
results = batch_process(large_list)  # 一次性处理
"""
```

2. **使用缓存减少重复计算**
```python
# 启用工作流级缓存
workflow = Workflow(
    name="缓存工作流",
    enable_cache=True,
    steps=[...]
)
```

3. **合理设置超时时间**
```python
# 为耗时步骤设置合适的超时
WorkflowStep(
    id="long_process",
    timeout=600,  # 10分钟超时
    step_type=StepType.TOOL,
    ...
)
```

## 9. 参考资料

### 9.1 API参考

#### Workflow类
```python
class Workflow(BaseModel):
    id: str                           # 工作流ID
    name: str                         # 工作流名称
    description: str                  # 描述
    version: str                      # 版本号
    steps: List[WorkflowStep]         # 步骤列表
    input_schema: Dict[str, Any]      # 输入Schema
    output_schema: Dict[str, Any]     # 输出Schema
    max_execution_time: int           # 最大执行时间
    enable_parallel: bool             # 是否并行执行
    enable_cache: bool                # 是否启用缓存
    tags: List[str]                   # 标签
    author: str                       # 作者
    created_at: datetime              # 创建时间
    updated_at: datetime              # 更新时间
```

#### WorkflowStep类
```python
class WorkflowStep(BaseModel):
    id: str                           # 步骤ID
    name: str                         # 步骤名称
    description: str                  # 描述
    step_type: StepType               # 步骤类型
    
    # 端口定义
    input_ports: List[StepPort]       # 输入端口
    output_ports: List[StepPort]      # 输出端口
    port_connections: Dict[str, PortConnection]  # 端口连接
    
    # 执行控制
    condition: Optional[str]          # 执行条件
    depends_on: List[str]             # 依赖步骤
    timeout: int                      # 超时时间
    error_handling: ErrorHandling     # 错误处理策略
    retry_count: int                  # 重试次数
    
    # 类型特定字段
    code: Optional[str]               # CODE步骤的代码
    tool_name: Optional[str]          # TOOL步骤的工具名
    action: Optional[str]             # TOOL步骤的动作
    memory_action: Optional[str]      # MEMORY步骤的操作
    agent_name: Optional[str]         # AGENT步骤的Agent名
    
    # 通用字段
    params: Dict[str, Any]            # 参数字典
    output_key: Optional[str]         # 输出键(向后兼容)
```

#### StepPort类
```python
class StepPort(BaseModel):
    name: str                         # 端口名称
    type: PortType                    # 端口类型
    description: str                  # 端口描述
    required: bool                    # 是否必需
    default_value: Any                # 默认值
```

#### PortConnection类
```python
class PortConnection(BaseModel):
    target_port: str                  # 目标端口名
    source_step: str                  # 源步骤ID
    source_port: str                  # 源端口名
```

### 9.2 配置参考

#### StepType枚举
- `StepType.CODE`: 执行Python代码
- `StepType.MEMORY`: 内存操作
- `StepType.TOOL`: 工具调用
- `StepType.AGENT`: Agent调用

#### PortType枚举
- `PortType.STRING`: 字符串
- `PortType.INTEGER`: 整数
- `PortType.FLOAT`: 浮点数
- `PortType.BOOLEAN`: 布尔值
- `PortType.LIST`: 列表
- `PortType.DICT`: 字典
- `PortType.ANY`: 任意类型

#### ErrorHandling枚举
- `ErrorHandling.STOP`: 停止工作流
- `ErrorHandling.CONTINUE`: 继续执行
- `ErrorHandling.RETRY`: 重试步骤
- `ErrorHandling.SKIP`: 跳过步骤

### 9.3 错误代码

| 错误类型 | 原因 | 解决方案 |
|----------|------|----------|
| `PortConnectionError` | 端口连接配置错误 | 检查源步骤ID和端口名 |
| `TypeMismatchError` | 端口类型不匹配 | 确保连接端口的类型兼容 |
| `MissingRequiredPortError` | 缺少必需端口连接 | 为所有必需端口配置连接 |
| `CircularDependencyError` | 循环依赖 | 重新设计步骤依赖关系 |
| `TimeoutError` | 步骤执行超时 | 增加超时时间或优化代码 |
| `CodeExecutionError` | 代码执行失败 | 检查CODE步骤中的Python代码 |

## 10. 附录

### 10.1 工作流模板库

可以创建常用的工作流模板供复用：

```python
# 文本处理模板
TEXT_PROCESSING_TEMPLATE = create_text_processing_workflow()

# AI对话模板  
AI_CONVERSATION_TEMPLATE = create_ai_conversation_workflow()

# 客服处理模板
CUSTOMER_SERVICE_TEMPLATE = create_customer_service_workflow()

# 数据分析模板
DATA_ANALYSIS_TEMPLATE = create_data_analysis_workflow()
```

### 10.2 常用代码片段

```python
# 输入验证片段
INPUT_VALIDATION_CODE = """
# 验证必需输入
required_fields = ['field1', 'field2']
for field in required_fields:
    if not variables.get(field):
        result = {'error': f'缺少必需字段: {field}'}
        break
"""

# 错误处理片段
ERROR_HANDLING_CODE = """
try:
    # 主要处理逻辑
    main_result = process_data()
    result = {'data': main_result, 'status': 'success'}
except Exception as e:
    print(f"处理失败: {e}")
    result = {'data': None, 'status': 'error', 'error': str(e)}
"""

# 日志记录片段
LOGGING_CODE = """
import logging
logger = logging.getLogger(__name__)

logger.info(f"开始处理: {variables.get('input_data', '')[:100]}")
# 处理逻辑...
logger.info(f"处理完成: {len(result_data)} 条记录")
"""
```

### 10.3 迁移指南

如果你有使用传统变量引用方式的旧工作流，可以按以下步骤迁移到端口连接模式：

1. **分析现有工作流**
   - 识别步骤间的数据依赖关系
   - 列出所有使用的变量

2. **定义端口**
   - 为每个步骤定义输入输出端口
   - 确定端口的数据类型

3. **配置连接**
   - 将变量引用转换为端口连接
   - 验证连接的正确性

4. **测试验证**
   - 使用相同输入测试新旧工作流
   - 确保输出结果一致

5. **逐步替换**
   - 先在开发环境测试
   - 确认无误后替换生产环境

---

这个开发指南提供了创建自定义工作流的完整指导，从基本概念到复杂的实际应用案例。使用端口连接模式，您可以创建清晰、可维护、可视化友好的AI工作流。