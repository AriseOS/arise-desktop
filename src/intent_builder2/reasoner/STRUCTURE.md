# Reasoner Module Structure

## 文件结构

经过重构，reasoner模块已经将reasoner.py拆分为多个独立的文件，每个文件负责单一职责：

```
src/reasoner/
├── __init__.py                      # 模块导出
├── reasoner.py                       # Reasoner主类（入口）
├── task_dag.py                      # TaskDAG类
├── retrieval_result.py              # RetrievalResult和WorkflowResult类
├── cognitive_phrase_checker.py      # CognitivePhraseChecker类
├── task_reasoner.py                # TaskReasoner类
├── workflow_converter.py            # WorkflowConverter类
├── prompts/                         # Prompt模板文件夹
│   ├── __init__.py
│   ├── cognitive_phrase_match_prompt.py
│   ├── task_decomposition_prompt.py
│   └── state_satisfaction_prompt.py
└── README.md                        # 使用文档
```

## 各文件说明

### 1. reasoner.py (reasoner.py:31)
**职责**: 主入口类，协调整个检索流程

**主要类**:
- `Reasoner` - 主要入口类

**依赖**:
- CognitivePhraseChecker
- TaskReasoner
- WorkflowConverter
- TaskDAG

**关键方法**:
- `plan(target: str) -> WorkflowResult` - 主入口方法

---

### 2. task_dag.py (task_dag.py:8)
**职责**: 任务依赖关系的有向无环图

**主要类**:
- `TaskDAG` - 表示任务DAG结构

**关键方法**:
- `topological_order() -> List[str]` - 获取拓扑排序

**使用场景**:
当需要将复杂target分解为多个原子任务时使用

---

### 3. retrieval_result.py (retrieval_result.py:11)
**职责**: 定义检索结果数据结构

**主要类**:
- `RetrievalResult` - 单个任务的检索结果
- `WorkflowResult` - 最终的workflow结果

**关键属性**:
- RetrievalResult: `success`, `states`, `actions`, `reasoning`
- WorkflowResult: `target`, `success`, `workflow`, `metadata`

---

### 4. cognitive_phrase_checker.py (cognitive_phrase_checker.py:17)
**职责**: 检查cognitive phrases是否能满足target

**主要类**:
- `CognitivePhraseChecker`

**关键方法**:
- `check(target: str) -> Tuple[bool, List[CognitivePhrase], str]` - 检查phrases
- `_text_match()` - 文本匹配（fallback）
- `_llm_check()` - LLM评估

**使用场景**:
在检索流程的第一步，尝试直接从cognitive phrases中匹配target

---

### 5. task_reasoner.py (task_reasoner.py:18)
**职责**: 执行单个任务的检索（Embedding + LLM + 邻居探索）

**主要类**:
- `TaskReasoner`

**关键方法**:
- `retrieve(target: str) -> RetrievalResult` - 执行检索
- `_find_states_by_embedding()` - Embedding检索
- `_check_satisfaction()` - LLM满足度检查
- `_explore_neighbors()` - 邻居探索（深度优先）

**配置参数**:
- `max_depth`: 邻居探索的最大深度（默认3）

---

### 6. workflow_converter.py (workflow_converter.py:11)
**职责**: 将states和actions转换为workflow JSON

**主要类**:
- `WorkflowConverter`

**关键方法**:
- `convert() -> Dict[str, Any]` - 转换为workflow JSON

**输出格式**:
```json
{
  "workflow_id": "uuid",
  "target": "string",
  "steps": [...],
  "metadata": {...}
}
```

---

## 导入关系

```
reasoner.py
  ├── imports CognitivePhraseChecker  (cognitive_phrase_checker.py)
  ├── imports TaskReasoner           (task_reasoner.py)
  ├── imports WorkflowConverter       (workflow_converter.py)
  ├── imports TaskDAG                 (task_dag.py)
  └── imports WorkflowResult          (retrieval_result.py)

cognitive_phrase_checker.py
  └── imports CognitivePhraseMatchPrompt (prompts/)

task_reasoner.py
  ├── imports RetrievalResult         (retrieval_result.py)
  └── imports StateSatisfactionPrompt (prompts/)

workflow_converter.py
  └── (no internal dependencies)

task_dag.py
  └── (no internal dependencies)

retrieval_result.py
  └── (no internal dependencies)
```

## 使用示例

### 基本用法

```python
from src.reasoner import Reasoner
from src.memory import Memory
from src.services.llm import LLMClient

# 初始化
memory = Memory()
llm_client = LLMClient()
embedding_service = EmbeddingService()

reasoner = Reasoner(
    memory=memory,
    llm_client=llm_client,
    embedding_service=embedding_service,
    max_depth=3
)

# 执行检索
result = reasoner.plan("Book a flight to Paris")

if result.success:
    print(result.workflow)
```

### 使用单个组件

```python
# 单独使用CognitivePhraseChecker
from src.reasoner import CognitivePhraseChecker

checker = CognitivePhraseChecker(memory, llm_client)
can_satisfy, phrases, reasoning = checker.check(target)

# 单独使用TaskReasoner
from src.reasoner import TaskReasoner

reasoner = TaskReasoner(memory, llm_client, embedding_service, max_depth=5)
result = reasoner.retrieve(target)

# 单独使用WorkflowConverter
from src.reasoner import WorkflowConverter

converter = WorkflowConverter()
workflow = converter.convert(target, states, actions)
```

## 优势

1. **模块化**: 每个类独立文件，职责清晰
2. **可测试**: 每个组件可以独立测试
3. **可复用**: 各组件可以在其他场景复用
4. **可维护**: 代码结构清晰，易于理解和修改
5. **可扩展**: 易于添加新功能或替换实现

## 扩展点

如果需要扩展功能：

1. **添加新的Checker**: 创建新的checker类，在Reasoner中使用
2. **自定义Reasoner**: 实现新的retrieval策略，替换TaskReasoner
3. **自定义Converter**: 实现新的workflow格式，替换WorkflowConverter
4. **添加新的Prompt**: 在prompts/目录下添加新的prompt模板