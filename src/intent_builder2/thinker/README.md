# Thinker Module

Thinker 模块是一个完整的工作流处理管道，用于将用户在 web/app 中的操作工作流转换为语义化的认知结构。

## 功能概述

Thinker 模块通过以下流程处理用户工作流：

```
Workflow (JSON/Text)
    ↓
Intent 列表 (使用 LogicalForm 分析)
    ↓
Intent DAG (有向无环图)
    ↓
State + Action (语义状态和转换)
    ↓
CognitivePhrase (认知短语)
    ↓
Memory Storage (存储到记忆系统)
```

## 核心组件

### 0. JsonProcessor

JSON输入处理器，负责解析和验证JSON格式的浏览器操作输入，将其转换为标准化的数据结构。

**功能：**
- 解析JSON格式的浏览器事件序列
- 验证输入数据的完整性和正确性
- 将事件批次转换为结构化对象
- 导出为LLM友好的文本格式
- 提供批次统计和摘要信息

**使用示例：**
```python
from src.thinker.json_processor import JsonProcessor

processor = JsonProcessor()

# 处理JSON输入
json_data = {
    "events": [
        {
            "event_type": "click",
            "timestamp": 1000,
            "page_url": "https://example.com",
            "element_id": "button-1"
        }
    ],
    "context": {
        "user_id": "user123",
        "session_id": "session456"
    }
}

batch = processor.process_json_input(json_data)

# 验证输入
is_valid, errors = processor.validate_input(batch)

# 导出为LLM格式
llm_format = processor.export_to_llm_format(batch)
```

### 1. IntentDAGBuilder

将 Intent 列表构建成有向无环图（DAG），使用语言学的 LogicalForm 方法分析意图之间的依赖关系。

**功能：**
- 分析意图之间的时序、因果、条件等关系
- 构建 DAG 结构表示意图依赖
- 支持 LLM 分析和基于规则的回退

**使用示例：**
```python
from src.thinker.intent_dag_builder import IntentDAGBuilder

builder = IntentDAGBuilder(llm_client=llm_client)
dag = builder.build_dag(intents, use_llm=True)

# 获取根节点和叶子节点
root_intents = dag.get_root_intents()
leaf_intents = dag.get_leaf_intents()

# 获取后继节点
successors = dag.get_successors(intent_id)
```

### 2. StateGenerator

语义状态生成器，将原子意图聚合为高层语义状态，并构建状态之间的转换关系。

**功能：**
- 使用LLM分析将原子意图聚合为语义状态
- 识别状态类型（浏览、搜索、比较、选择等）
- 构建状态之间的转换边（Transition Edges）
- 支持规则驱动的fallback方法
- 提供缓存和统计功能

**使用示例：**
```python
from src.thinker.state_generator import StateGenerator

state_gen = StateGenerator(llm_client=llm_client, model_name="gpt-4")

# 生成语义状态和转换边
result = state_gen.generate_semantic_states(
    atomic_intents=intents,
    context={"dag": intent_dag.to_dict()}
)

# 访问结果
states = result.semantic_states
edges = result.transition_edges
metadata = result.generation_metadata

print(f"Generated {len(states)} states and {len(edges)} edges")
for state in states:
    print(f"State: {state.label} (type: {state.type})")
```

### 3. CognitivePhraseGenerator

将 State 和 Action 转换为高层次的认知短语（CognitivePhrase）。

**功能：**
- 从语义状态和动作中提炼认知任务
- 识别完整的用户目标和意图
- 生成语义完整的任务描述

**使用示例：**
```python
from src.thinker.cognitive_phrase_generator import CognitivePhraseGenerator

generator = CognitivePhraseGenerator(llm_client=llm_client)
result = generator.generate_phrases(states, actions, use_llm=True)

for phrase in result.phrases:
    print(f"Task: {phrase.label}")
    print(f"Description: {phrase.description}")
    print(f"Duration: {phrase.duration}ms")
```

### 4. WorkflowProcessor

主流程编排器，协调整个处理管道。

**功能：**
- 解析 JSON/Text 格式的工作流输入
- 调用各个处理组件
- 将结果存储到 Memory
- 生成完整的处理报告

**使用示例：**
```python
from src.thinker import WorkflowProcessor

processor = WorkflowProcessor(
    llm_client=llm_client,
    memory=memory
)

# 处理工作流
result = processor.process_workflow(
    workflow_input=workflow_events,
    input_type="json",
    user_id="user123",
    session_id="session456",
    store_to_memory=True
)

# 查看结果
print(f"Intents: {len(result.intents)}")
print(f"States: {len(result.states)}")
print(f"Phrases: {len(result.phrases)}")
```

## 数据流

### 输入格式

#### JSON 格式（推荐）

```json
[
  {
    "event_type": "input",
    "timestamp": 1234567890000,
    "page_url": "https://example.com",
    "element_id": "search-input",
    "value": "premium coffee"
  },
  {
    "event_type": "click",
    "timestamp": 1234567891000,
    "page_url": "https://example.com",
    "element_id": "search-button",
    "text": "Search"
  }
]
```

#### Text 格式

```python
processor.process_workflow(
    workflow_input="User navigated to shopping page",
    input_type="text",
    user_id="user123"
)
```

### 输出结构

```python
class WorkflowProcessingResult:
    intents: List[Intent]          # 提取的原子意图
    intent_dag: IntentDAG           # Intent 有向无环图
    states: List[State]             # 语义状态
    actions: List[Action]           # 状态转换动作
    phrases: List[CognitivePhrase]  # 认知短语
    metadata: Dict[str, Any]        # 处理元数据
```

## 完整示例

### 基础使用

```python
from src.services.llm import create_llm_client, LLMProvider
from src.graphstore.memory_graph import MemoryGraph
from src.memory.workflow_memory import WorkflowMemory
from src.thinker import WorkflowProcessor

# 1. 初始化 LLM 客户端
llm_client = create_llm_client(
    provider=LLMProvider.OPENAI,
    api_client=openai_client,
    model_name="gpt-4"
)

# 2. 初始化 Memory
graph_store = MemoryGraph()
memory = WorkflowMemory(graph_store=graph_store)

# 3. 初始化处理器
processor = WorkflowProcessor(
    llm_client=llm_client,
    memory=memory
)

# 4. 处理工作流
workflow_events = [
    {
        "event_type": "click",
        "timestamp": 1000,
        "page_url": "https://shop.com/products",
        "element_id": "product-123",
        "text": "Premium Coffee"
    }
]

result = processor.process_workflow(
    workflow_input=workflow_events,
    input_type="json",
    user_id="user_123",
    session_id="session_456",
    store_to_memory=True
)

# 5. 使用结果
print(f"Generated {len(result.phrases)} cognitive phrases:")
for phrase in result.phrases:
    print(f"  - {phrase.label}: {phrase.description}")
```

### 从文件处理

```python
# 处理 JSON 文件
result = processor.process_workflow_file(
    file_path="/path/to/workflow.json",
    user_id="user_123",
    session_id="session_456",
    store_to_memory=True
)
```

### 自定义处理管道

```python
from src.thinker.intent_dag_builder import IntentDAGBuilder
from src.thinker.cognitive_phrase_generator import CognitivePhraseGenerator
from src.thinker.state_generator import StateGenerator

# 1. 构建 Intent DAG
dag_builder = IntentDAGBuilder(llm_client=llm_client)
dag = dag_builder.build_dag(intents, use_llm=True)

# 2. 生成 States 和 Actions
state_gen = StateGenerator(llm_client=llm_client)
state_result = state_gen.generate_semantic_states(intents)

# 3. 生成 Cognitive Phrases
phrase_gen = CognitivePhraseGenerator(llm_client=llm_client)
phrase_result = phrase_gen.generate_phrases(
    state_result.semantic_states,
    state_result.transition_edges,
    use_llm=True
)

# 4. 手动存储到 Memory
for state in state_result.semantic_states:
    memory.create_state(state)

for action in state_result.transition_edges:
    memory.create_action(action)

for phrase in phrase_result.phrases:
    memory.create_phrase(phrase)
```

## LogicalForm 分析方法

Thinker 模块使用语言学中的 LogicalForm 方法分析意图依赖关系：

### 关系类型

1. **时序关系（Temporal）**: A 在 B 之前发生
2. **因果关系（Causal）**: A 导致 B 发生
3. **条件关系（Conditional）**: A 是 B 的前提条件
4. **并行关系（Parallel）**: A 和 B 可以同时进行
5. **从属关系（Subordinate）**: A 从属于 B

### DAG 构建规则

- **节点**: 每个 Intent 作为一个节点
- **边**: 意图之间存在依赖关系时建立边
- **无环性**: 确保图中不存在环路
- **传递性**: 考虑间接依赖关系

## 认知短语类型

### 典型任务类型

- **信息查找**: 搜索并浏览相关信息
- **商品选购**: 浏览、比较、选择商品
- **决策制定**: 评估选项、比较价格、做出决定
- **任务执行**: 完成购买、提交表单、操作执行

### 识别原则

1. **任务边界识别**
   - 开始标志：新搜索、导航到新页面、开始新交互
   - 结束标志：完成购买、退出页面、任务目标达成

2. **语义聚合规则**
   - 将目标一致的状态聚合为一个短语
   - 考虑用户的潜在意图和动机
   - 识别任务的层次结构

## 配置选项

### LLM 配置

```python
# 使用 OpenAI
llm_client = create_llm_client(
    provider=LLMProvider.OPENAI,
    api_client=openai_client,
    model_name="gpt-4"
)

# 使用 Claude
llm_client = create_llm_client(
    provider=LLMProvider.ANTHROPIC,
    api_client=anthropic_client,
    model_name="claude-3-opus-20240229"
)

# 使用 Mock（测试）
llm_client = create_llm_client(
    provider=LLMProvider.MOCK,
    model_name="mock-gpt-4"
)
```

### 处理选项

```python
result = processor.process_workflow(
    workflow_input=events,
    input_type="json",           # "json" 或 "text"
    user_id="user_123",          # 用户 ID
    session_id="session_456",    # 会话 ID
    store_to_memory=True         # 是否存储到 Memory
)
```

## 错误处理

所有组件都支持 LLM 失败时的规则回退：

```python
try:
    # 尝试使用 LLM
    result = processor.process_workflow(
        workflow_input=events,
        use_llm=True
    )
except Exception as e:
    # 自动回退到基于规则的方法
    print(f"LLM processing failed: {e}")
    # 组件会自动使用规则方法
```

## API 参考

### WorkflowProcessor

```python
class WorkflowProcessor:
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        memory: Optional[Memory] = None
    )

    def process_workflow(
        self,
        workflow_input: Union[str, Dict, List[Dict]],
        input_type: str = "json",
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        store_to_memory: bool = True
    ) -> WorkflowProcessingResult

    def process_workflow_file(
        self,
        file_path: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        store_to_memory: bool = True
    ) -> WorkflowProcessingResult
```

### IntentDAGBuilder

```python
class IntentDAGBuilder:
    def __init__(self, llm_client: Optional[LLMClient] = None)

    def build_dag(
        self,
        intents: List[Intent],
        use_llm: bool = True
    ) -> IntentDAG
```

### CognitivePhraseGenerator

```python
class CognitivePhraseGenerator:
    def __init__(self, llm_client: Optional[LLMClient] = None)

    def generate_phrases(
        self,
        states: List[State],
        actions: List[Action],
        use_llm: bool = True
    ) -> CognitivePhraseGenerationResult
```

## 测试

运行示例代码：

```bash
python examples/thinker_example.py
```

## 依赖关系

- `src.ontology`: Intent, State, Action, CognitivePhrase 定义
- `src.services.llm`: LLM 客户端接口
- `src.thinker.intent_dag_builder`: Intent DAG 构建器（包含 LogicalForm 分析）
- `src.thinker.state_generator`: 语义状态生成器
- `src.thinker.cognitive_phrase_generator`: 认知短语生成器
- `src.memory`: Memory 存储接口
- `src.graphstore`: 图存储后端

## 许可

版权所有 © 2024 Memory Project Team