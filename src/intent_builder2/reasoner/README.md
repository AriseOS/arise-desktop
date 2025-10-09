# Reasoner Module - Reasoner-based Workflow Retrieval

## 概述

本模块实现了一个智能的工作流检索系统，通过Reasoner类作为主入口，协调整个检索过程。

## 核心架构

### 主要组件

1. **Reasoner** - 主入口类，负责整体流程编排
2. **CognitivePhraseChecker** - 检查cognitive phrases是否能满足目标
3. **TaskReasoner** - 执行单个任务的检索
4. **WorkflowConverter** - 将检索结果转换为workflow JSON
5. **TaskDAG** - 任务依赖关系的有向无环图

## 工作流程

### 1. 用户提供Target（自然语言）

```python
target = "Search for flights to Paris and book a hotel"
```

### 2. Reasoner执行检索

整个流程如下：

#### Step 1: 检查Cognitive Phrases

Reasoner首先调用`CognitivePhraseChecker`，使用LLM判断memory中的cognitive_phrases是否能直接匹配或组合满足target。

- 如果**可以满足**：根据cognitive_phrase对应的states和actions转为workflow返回
- 如果**不满足**：进入Step 2

#### Step 2: 任务分解

Reasoner使用LLM将Target拆分为原子Task组成的TaskDAG：

```python
# Example TaskDAG
{
  "tasks": [
    {"task_id": "task_1", "target": "Search for flights to Paris"},
    {"task_id": "task_2", "target": "Select a suitable flight"},
    {"task_id": "task_3", "target": "Search for hotels in Paris"},
    {"task_id": "task_4", "target": "Book the hotel"}
  ],
  "edges": [
    ("task_1", "task_2"),
    ("task_2", "task_3"),
    ("task_3", "task_4")
  ]
}
```

#### Step 3: 按拓扑排序执行任务

对DAG中的每个Task，按拓扑排序依次处理。对于每个检索任务，执行以下步骤：

##### a. Embedding检索

使用Embedding Service在memory中找到最相关的states：

```python
query_embedding = embedding_service.encode(target)
candidate_states = memory.state_manager.search_states_by_embedding(
    query_embedding, top_k=10
)
```

##### b. LLM评估State

使用LLM检查找到的state是否能满足Target目标：

```python
satisfies = llm_client.evaluate(target, state)
```

- 如果**满足**：返回该state，继续下一个任务
- 如果**不满足**：进入Step c

##### c. 邻居探索

获取state的actions以及邻居states，进行深度优先搜索（最大深度可配置）：

```python
# 当前深度 < max_depth
for action in state.actions:
    neighbor_state = memory.get_state(action.target)
    # 使用LLM判断 (current_path + neighbor_state) 是否满足target
    if llm_client.evaluate(target, current_path + [neighbor_state]):
        return True, current_path, actions
```

- 如果**满足**：返回找到的path（states + actions）
- 如果到达**最大深度仍不满足**：检索失败

#### Step 4: 转换为Workflow JSON

将所有成功检索的states和actions转换为可执行的workflow JSON：

```json
{
  "workflow_id": "uuid",
  "target": "Search for flights to Paris and book a hotel",
  "steps": [
    {
      "step_id": "step_1",
      "state_id": "state-123",
      "state_label": "Search Flights",
      "state_type": "SearchState",
      "page_url": "https://example.com/flights",
      "intents": [...],
      "action": {
        "type": "CLICK",
        "source": "state-123",
        "target": "state-124",
        "attributes": {...}
      }
    }
  ],
  "metadata": {
    "method": "task_dag",
    "num_tasks": 4,
    "num_states": 8,
    "num_actions": 7
  }
}
```

## 使用示例

### 基本用法

```python
from src.reasoner import Reasoner
from src.memory import Memory
from src.services.llm import LLMClient
from src.services.embedding import EmbeddingService

# 初始化依赖
memory = Memory()
llm_client = LLMClient()
embedding_service = EmbeddingService()

# 创建Reasoner
reasoner = Reasoner(
    memory=memory,
    llm_client=llm_client,
    embedding_service=embedding_service,
    max_depth=3  # 邻居探索的最大深度
)

# 执行检索
target = "Book a flight to Paris"
result = reasoner.plan(target)

# 检查结果
if result.success:
    print(f"Workflow: {result.workflow}")
    print(f"Method: {result.metadata['method']}")
else:
    print(f"Retrieval failed: {result.metadata}")
```

### 高级配置

```python
# 自定义最大深度
reasoner = Reasoner(
    memory=memory,
    llm_client=llm_client,
    embedding_service=embedding_service,
    max_depth=5  # 允许更深的邻居探索
)

# 处理结果
result = reasoner.plan(target)

if result.success:
    if result.metadata['method'] == 'cognitive_phrase_match':
        print("Direct match from cognitive phrases!")
    elif result.metadata['method'] == 'task_dag':
        print(f"Decomposed into {result.metadata['num_tasks']} tasks")
```

## LLM Prompts

所有LLM相关的prompts都在`src/reasoner/prompts/`目录中：

1. **CognitivePhraseMatchPrompt** - 检查cognitive phrases是否匹配target
2. **TaskDecompositionPrompt** - 将target分解为TaskDAG
3. **StateSatisfactionPrompt** - 检查states是否满足target

## 配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| memory | Memory | 必需 | Memory实例 |
| llm_client | LLMClient | None | LLM客户端，若为None则使用规则匹配 |
| embedding_service | EmbeddingService | None | Embedding服务，若为None则使用列表检索 |
| max_depth | int | 3 | 邻居探索的最大深度 |

## 返回结果

### WorkflowResult

```python
class WorkflowResult:
    target: str              # 原始target
    success: bool            # 是否成功
    workflow: Dict[str, Any] # Workflow JSON（成功时）
    metadata: Dict[str, Any] # 附加元数据
```

### Metadata字段

- `method`: 使用的检索方法 ('cognitive_phrase_match' | 'task_dag')
- `num_tasks`: 任务数量（task_dag方法）
- `num_phrases`: 匹配的phrase数量（cognitive_phrase_match方法）
- `reasoning`: LLM的推理说明
- `dag_id`: TaskDAG的ID
- `failed_task_id`: 失败的任务ID（失败时）

## 注意事项

1. **LLM依赖**：核心功能依赖LLM进行语义理解和评估
2. **Embedding优先**：优先使用embedding进行向量检索，fallback到列表检索
3. **深度控制**：通过max_depth控制邻居探索的计算成本
4. **缓存机制**：考虑添加LLM结果缓存以提高性能

## 扩展点

1. 实现自定义的State评估策略
2. 添加更复杂的TaskDAG优化算法
3. 实现并行任务执行
4. 添加检索结果排序和过滤