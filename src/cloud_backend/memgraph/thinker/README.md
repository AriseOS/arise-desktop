# Thinker Module

Thinker 模块是生产级的工作流处理管道，使用LLM驱动的方式将用户在 web/app 中的操作工作流转换为图结构化的语义表示。

## 核心概念

Thinker 模块通过以下LLM驱动的流程处理用户工作流：

```
Workflow Events (JSON)
    ↓
[1] Domain Extraction (LLM)
    ↓
Domains (app/website nodes)
    ↓
[2] State + Intent Extraction (LLM)
    ↓
States (pages) + Intents (operations within pages)
    ↓
[3] Action Extraction (LLM)
    ↓
Actions (state transitions/navigation)
    ↓
[4] Manage Generation (Rule-based)
    ↓
Manages (domain-state connections with visit metadata)
    ↓
[5] Memory Storage
    ↓
Graph-based Memory
```

## 核心组件

### 0. JsonProcessor

JSON输入处理器，负责解析和验证JSON格式的浏览器操作输入。

**功能：**
- 解析JSON格式的浏览器事件序列
- 验证输入数据的完整性和正确性
- 将事件批次转换为结构化对象
- 导出为LLM友好的文本格式

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
```

### 1. DomainExtractor (LLM-driven)

Domain提取器，使用LLM从URL中识别和提取Domain节点（app/website主页）。

**功能：**
- 使用LLM分析URL模式，识别unique domains
- 区分不同的app和website
- 建立URL到Domain的映射关系
- 自动生成domain_name和domain_type

**使用示例：**
```python
from src.thinker.domain_extractor import DomainExtractor

extractor = DomainExtractor(llm_client=llm_client)

# 从workflow events中提取domains
result = extractor.extract_domains(
    workflow_data=events,
    user_id="user123"
)

# 访问结果
domains = result.domains
domain_mapping = result.domain_mapping  # URL -> Domain
metadata = result.extraction_metadata
```

### 2. StateIntentExtractor (LLM-driven)

State和Intent提取器，使用LLM分析事件序列，识别State（页面状态）和Intent（页面内操作）。

**核心概念：**
- **State**: 用户所在的页面/屏幕（由page_url标识）
- **Intent**: 在State内进行的操作，**不会导致页面跳转**
- State包含多个Intent，Intent属于某个State

**功能：**
- 使用LLM识别unique states（页面/屏幕）
- 提取每个state内的intents（点击、输入、滚动等）
- 确保Intent不导致状态转换
- 建立State和Intent的关联关系

**使用示例：**
```python
from src.thinker.state_intent_extractor import StateIntentExtractor

extractor = StateIntentExtractor(llm_client=llm_client)

# 提取states和intents
result = extractor.extract_states_and_intents(
    workflow_data=events,
    domain_mapping=domain_mapping,
    user_id="user123",
    session_id="session456"
)

# 访问结果
states = result.states
intents = result.intents
state_intent_mapping = result.state_intent_mapping  # state_id -> [Intent]
```

### 3. ActionExtractor (LLM-driven)

Action提取器，使用LLM从State序列中识别导致页面跳转的Action（状态转换）。

**核心概念：**
- **Action**: 连接两个不同State的导航操作
- Action代表页面跳转（点击链接、提交表单、浏览器导航等）
- Action必须连接不同的States（source ≠ target）

**功能：**
- 使用LLM分析State序列，识别状态转换
- 识别Action类型（ClickLink, SubmitForm, NavigateBack等）
- 关联触发Action的Intent（trigger_intent_id）
- 验证Action的有效性（source ≠ target）

**使用示例：**
```python
from src.thinker.action_extractor import ActionExtractor

extractor = ActionExtractor(llm_client=llm_client)

# 提取actions
result = extractor.extract_actions(
    states=states,
    workflow_data=events,
    user_id="user123",
    session_id="session456"
)

# 访问结果
actions = result.actions
metadata = result.extraction_metadata
```

### 4. ManageGenerator (Rule-based)

Manage连接生成器，基于规则将Domain与其关联的State通过Manage边连接起来。

**核心概念：**
- **Manage**: Domain到State的边，记录访问元数据
- 每个State属于一个Domain（通过URL匹配）
- Manage边记录visit时间、次数、时长等信息

**功能：**
- 基于URL匹配将State关联到Domain
- 生成Manage边，记录访问信息
- 聚合visit timestamps, counts, duration
- 自动处理多次访问同一State的情况

**使用示例：**
```python
from src.thinker.manage_generator import ManageGenerator

generator = ManageGenerator()

# 生成manages
result = generator.generate_manages(
    domains=domains,
    states=states,
    user_id="user123"
)

# 访问结果
manages = result.manages
domain_state_mapping = result.domain_state_mapping  # domain_id -> [state_id]
```

### 5. WorkflowProcessor (Main Orchestrator)

主流程编排器，协调整个LLM驱动的处理管道。

**功能：**
- 解析JSON格式的工作流输入
- 依次调用各个提取器/生成器
- 将结果存储到Memory
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
    workflow_data=events,
    user_id="user123",
    session_id="session456",
    store_to_memory=True
)

# 查看结果
print(f"Domains: {len(result.domains)}")
print(f"States: {len(result.states)}")
print(f"Intents: {len(result.intents)}")
print(f"Actions: {len(result.actions)}")
print(f"Manages: {len(result.manages)}")
```

## 数据流

### 输入格式 (JSON)

```json
[
  {
    "event_type": "input",
    "timestamp": 1234567890000,
    "page_url": "https://shop.com/search",
    "element_id": "search-input",
    "value": "premium coffee"
  },
  {
    "event_type": "click",
    "timestamp": 1234567891000,
    "page_url": "https://shop.com/search",
    "element_id": "search-button",
    "text": "Search"
  },
  {
    "event_type": "navigation",
    "timestamp": 1234567892000,
    "page_url": "https://shop.com/products?q=coffee",
    "page_title": "Search Results"
  }
]
```

### 输出结构

```python
class WorkflowProcessingResult:
    domains: List[Domain]           # 提取的Domain节点
    states: List[State]             # 提取的State节点（页面）
    intents: List[Intent]           # 提取的Intent（页面内操作）
    actions: List[Action]           # 提取的Action边（状态转换）
    manages: List[Manage]           # 生成的Manage边（domain-state连接）

    domain_mapping: Dict[str, Domain]              # URL -> Domain
    state_intent_mapping: Dict[str, List[Intent]]  # state_id -> Intents
    domain_state_mapping: Dict[str, List[str]]     # domain_id -> state_ids

    processing_metadata: Dict[str, Any]  # 处理元数据
    timestamp: datetime                  # 处理时间
```

## 完整示例

### 基础使用

```python
from src.services.llm import create_llm_client, LLMProvider
from src.graphstore.networkx_storage import NetworkXGraphStorage
from src.memory.workflow_memory import WorkflowMemory
from src.thinker import WorkflowProcessor

# 1. 初始化 LLM 客户端
llm_client = create_llm_client(
    provider=LLMProvider.OPENAI,
    api_client=openai_client,
    model_name="gpt-4"
)

# 2. 初始化 Memory
graph_storage = NetworkXGraphStorage()
memory = WorkflowMemory(graph_storage=graph_storage)

# 3. 初始化处理器
processor = WorkflowProcessor(
    llm_client=llm_client,
    memory=memory
)

# 4. 处理工作流
workflow_events = [
    {
        "event_type": "navigation",
        "timestamp": 1000,
        "page_url": "https://shop.com",
        "page_title": "Home"
    },
    {
        "event_type": "click",
        "timestamp": 2000,
        "page_url": "https://shop.com",
        "element_id": "products-link",
        "text": "Products"
    },
    {
        "event_type": "navigation",
        "timestamp": 3000,
        "page_url": "https://shop.com/products",
        "page_title": "All Products"
    }
]

result = processor.process_workflow(
    workflow_data=workflow_events,
    user_id="user_123",
    session_id="session_456",
    store_to_memory=True
)

# 5. 使用结果
print(f"Extracted {len(result.domains)} domains:")
for domain in result.domains:
    print(f"  - {domain.domain_name}: {domain.domain_url}")

print(f"\nExtracted {len(result.states)} states:")
for state in result.states:
    print(f"  - {state.page_url}: {len(state.intents)} intents")

print(f"\nExtracted {len(result.actions)} actions:")
for action in result.actions:
    print(f"  - {action.type}: {action.source} -> {action.target}")
```

### 自定义处理管道

```python
from src.thinker.domain_extractor import DomainExtractor
from src.thinker.state_intent_extractor import StateIntentExtractor
from src.thinker.action_extractor import ActionExtractor
from src.thinker.manage_generator import ManageGenerator

# 1. Extract Domains
domain_extractor = DomainExtractor(llm_client=llm_client)
domain_result = domain_extractor.extract_domains(events, user_id="user123")

# 2. Extract States and Intents
state_intent_extractor = StateIntentExtractor(llm_client=llm_client)
state_intent_result = state_intent_extractor.extract_states_and_intents(
    events,
    domain_mapping=domain_result.domain_mapping,
    user_id="user123",
    session_id="session456"
)

# 3. Extract Actions
action_extractor = ActionExtractor(llm_client=llm_client)
action_result = action_extractor.extract_actions(
    state_intent_result.states,
    workflow_data=events,
    user_id="user123",
    session_id="session456"
)

# 4. Generate Manages
manage_generator = ManageGenerator()
manage_result = manage_generator.generate_manages(
    domain_result.domains,
    state_intent_result.states,
    user_id="user123"
)

# 5. 手动存储到 Memory
for domain in domain_result.domains:
    memory.create_domain(domain)

# Store states (with embedded intents)
# Intents are already in state.intents, no need to store separately
for state in state_intent_result.states:
    memory.create_state(state)

for action in action_result.actions:
    memory.create_action(action)

for manage in manage_result.manages:
    memory.create_manage(manage)

# NOTE: Intents are NOT stored separately!
# They are embedded in State nodes via state.intents field
```

## LLM Prompts设计

所有LLM prompts都嵌入在对应的extractor类中，便于维护和理解上下文。

### Domain Extraction Prompt (中文)
- 任务：识别unique domains（app/website主页）
- 输入：URL列表
- 输出：JSON格式的domain列表

### State + Intent Extraction Prompt (中文)
- 任务：识别State（页面）和Intent（页面内操作）
- **关键约束**：Intent不会导致State转换
- 输入：事件序列
- 输出：JSON格式的states和intents列表

### Action Extraction Prompt (中文)
- 任务：识别Action（状态转换/导航）
- **关键约束**：source和target必须不同
- 输入：State序列
- 输出：JSON格式的actions列表

## 图结构设计

### Nodes
- **Domain**: App/Website主页节点（图节点）
- **State**: 页面/屏幕节点（图节点）
- **Intent**: 原子操作（**不是图节点**，嵌入在State中作为属性）

### Edges
- **Action**: State -> State（状态转换边）
- **Manage**: Domain -> State（域-状态连接边，带访问元数据）

### Graph Schema
```
Domain (node)
  |
  | (Manage edge: visit_count, timestamps, duration)
  |
  v
State (node) {
    page_url: str
    page_title: str
    timestamp: int
    intents: List[Intent]  ← Intents embedded here, not separate nodes
    intent_ids: List[str]
}
  |
  | (Action edge: type, timestamp, trigger_intent_id)
  |
  v
State (node)
```

### 存储说明
- **Domain** 和 **State** 作为图节点存储
- **Action** 和 **Manage** 作为图边存储
- **Intent** **不单独存储**，作为State节点的属性嵌入（`state.intents`字段）

## 配置选项

### LLM 配置

```python
# 使用 OpenAI
from src.services.llm import create_llm_client, LLMProvider

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
```

### 处理选项

```python
result = processor.process_workflow(
    workflow_data=events,      # 事件列表
    user_id="user_123",        # 用户 ID
    session_id="session_456",  # 会话 ID
    store_to_memory=True       # 是否存储到 Memory
)
```

## API 参考

### WorkflowProcessor

```python
class WorkflowProcessor:
    def __init__(
        self,
        llm_client: LLMClient,
        memory: Optional[Memory] = None
    )

    def process_workflow(
        self,
        workflow_data: List[Dict[str, Any]],
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        store_to_memory: bool = True
    ) -> WorkflowProcessingResult
```

### DomainExtractor

```python
class DomainExtractor:
    def __init__(
        self,
        llm_client: LLMClient,
        model_name: str = "gpt-4"
    )

    def extract_domains(
        self,
        workflow_data: List[Dict[str, Any]],
        user_id: Optional[str] = None
    ) -> DomainExtractionResult
```

### StateIntentExtractor

```python
class StateIntentExtractor:
    def __init__(
        self,
        llm_client: LLMClient,
        model_name: str = "gpt-4"
    )

    def extract_states_and_intents(
        self,
        workflow_data: List[Dict[str, Any]],
        domain_mapping: Optional[Dict[str, Domain]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> StateIntentExtractionResult
```

### ActionExtractor

```python
class ActionExtractor:
    def __init__(
        self,
        llm_client: LLMClient,
        model_name: str = "gpt-4"
    )

    def extract_actions(
        self,
        states: List[State],
        workflow_data: Optional[List[Dict[str, Any]]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> ActionExtractionResult
```

### ManageGenerator

```python
class ManageGenerator:
    def __init__(self)

    def generate_manages(
        self,
        domains: List[Domain],
        states: List[State],
        user_id: Optional[str] = None
    ) -> ManageGenerationResult
```

## 测试

运行测试：

```bash
# 运行所有thinker测试
python -m pytest tests/thinker/ -v

# 运行ontology测试
python -m pytest tests/ontology/ -v
```

## 依赖关系

- `src.ontology`: Domain, State, Intent, Action, Manage 定义
- `src.services.llm`: LLM 客户端接口
- `src.memory`: Memory 存储接口
- `src.graphstore`: 图存储后端

## 架构优势

### LLM-Driven Approach
- **准确性**: 使用LLM理解语义，提取更准确的结构
- **灵活性**: 适应各种domain和workflow类型
- **可扩展性**: 易于添加新的extraction类型

### Modular Design
- **关注点分离**: 每个extractor专注于特定任务
- **易于测试**: 每个组件可独立测试
- **易于维护**: 代码结构清晰，便于修改和扩展

### Production-Grade
- **错误处理**: 完善的异常处理和验证
- **元数据跟踪**: 详细的extraction metadata
- **可观测性**: 完整的日志和调试信息

## 许可

版权所有 © 2024 Memory Project Team
