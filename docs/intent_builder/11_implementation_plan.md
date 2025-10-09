# Intent Builder 实现计划

**版本**: v2.0
**日期**: 2025-10-09
**状态**: MVP 开发计划

---

## 1. 概述

### 1.1 目标

实现完整的 Intent Builder 系统，支持：
- **Learning Phase**: User Operations → Intent Memory Graph
- **Generation Phase**: User Query → Workflow

### 1.2 MVP 范围

**包含**:
1. Intent 提取（URL 切分 + LLM 生成）
2. IntentMemoryGraph（存储 + 语义检索）
3. MetaFlow 生成（LLM 推理：循环、隐式节点、数据流）
4. Workflow 生成（已有实现）
5. 端到端 Demo

**不包含**:
1. Intent 去重/合并
2. 使用频率统计
3. 复杂控制流（条件分支、嵌套循环）
4. 交互式修改 MetaFlow
5. Intent 版本管理

---

## 2. 实现阶段

### Phase 1: 核心数据结构（1-2天）

#### 1.1 Intent 数据模型

**文件**: `src/intent_builder/core/intent.py`

**任务**:
- [ ] 定义 `Intent` dataclass
- [ ] 定义 `Operation` dataclass
- [ ] 实现 `generate_intent_id()` (MD5 hash)
- [ ] JSON 序列化/反序列化
- [ ] 单元测试

**代码结构**:
```python
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Any
import hashlib
import json

@dataclass
class Operation:
    type: str
    timestamp: int
    url: str
    page_title: str
    element: Dict[str, Any]
    data: Dict[str, Any]

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Operation":
        return Operation(**data)

@dataclass
class Intent:
    id: str
    description: str
    operations: List[Operation]
    created_at: datetime
    source_session_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "operations": [asdict(op) for op in self.operations],
            "created_at": self.created_at.isoformat(),
            "source_session_id": self.source_session_id
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Intent":
        return Intent(
            id=data["id"],
            description=data["description"],
            operations=[Operation.from_dict(op) for op in data["operations"]],
            created_at=datetime.fromisoformat(data["created_at"]),
            source_session_id=data["source_session_id"]
        )

def generate_intent_id(description: str) -> str:
    hash_value = hashlib.md5(description.encode('utf-8')).hexdigest()[:8]
    return f"intent_{hash_value}"
```

**测试**:
```python
def test_intent_creation():
    intent = Intent(
        id="intent_test123",
        description="导航到首页",
        operations=[...],
        created_at=datetime.now(),
        source_session_id="session_001"
    )
    assert intent.id == "intent_test123"

def test_intent_id_generation():
    id1 = generate_intent_id("导航到首页")
    id2 = generate_intent_id("导航到首页")
    assert id1 == id2  # 相同描述生成相同 ID
```

#### 1.2 IntentMemoryGraph

**文件**: `src/intent_builder/core/intent_memory_graph.py`

**任务**:
- [ ] 定义 `IntentMemoryGraph` 类
- [ ] 实现 `add_intent()`, `add_edge()`
- [ ] 实现 `save()`, `load()` (JSON)
- [ ] 实现 `retrieve_similar()` (语义检索)
- [ ] 单元测试

**代码结构**:
```python
from typing import Dict, List, Tuple
import json
from openai import OpenAI

class IntentMemoryGraph:
    def __init__(self):
        self.intents: Dict[str, Intent] = {}
        self.edges: List[Tuple[str, str]] = []
        self._embedding_cache: Dict[str, List[float]] = {}
        self._openai_client = OpenAI()

    def add_intent(self, intent: Intent) -> None:
        self.intents[intent.id] = intent

    def add_edge(self, from_id: str, to_id: str) -> None:
        self.edges.append((from_id, to_id))

    def get_all_intents(self) -> List[Intent]:
        return list(self.intents.values())

    async def retrieve_similar(
        self,
        query: str,
        limit: int = 5
    ) -> List[Intent]:
        # 1. Get query embedding
        query_emb = await self._get_embedding(query)

        # 2. Calculate similarity scores
        scores = []
        for intent in self.intents.values():
            desc_emb = await self._get_embedding(intent.description)
            similarity = self._cosine_similarity(query_emb, desc_emb)
            scores.append((intent, similarity))

        # 3. Sort and return top-k
        scores.sort(key=lambda x: x[1], reverse=True)
        return [intent for intent, _ in scores[:limit]]

    async def _get_embedding(self, text: str) -> List[float]:
        if text in self._embedding_cache:
            return self._embedding_cache[text]

        response = self._openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        embedding = response.data[0].embedding
        self._embedding_cache[text] = embedding
        return embedding

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        import math
        dot_product = sum(x * y for x, y in zip(a, b))
        magnitude_a = math.sqrt(sum(x * x for x in a))
        magnitude_b = math.sqrt(sum(y * y for y in b))
        return dot_product / (magnitude_a * magnitude_b)

    def save(self, filepath: str) -> None:
        data = {
            "intents": {
                id: intent.to_dict()
                for id, intent in self.intents.items()
            },
            "edges": self.edges
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def load(filepath: str) -> "IntentMemoryGraph":
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        graph = IntentMemoryGraph()
        graph.intents = {
            id: Intent.from_dict(intent_data)
            for id, intent_data in data["intents"].items()
        }
        graph.edges = [tuple(edge) for edge in data["edges"]]
        return graph
```

**测试**:
```python
async def test_intent_memory_graph():
    graph = IntentMemoryGraph()

    # Add intents
    intent1 = Intent(...)
    intent2 = Intent(...)
    graph.add_intent(intent1)
    graph.add_intent(intent2)
    graph.add_edge(intent1.id, intent2.id)

    # Save and load
    graph.save("test_graph.json")
    loaded_graph = IntentMemoryGraph.load("test_graph.json")
    assert len(loaded_graph.intents) == 2

    # Semantic retrieval
    results = await graph.retrieve_similar("采集价格", limit=3)
    assert len(results) <= 3
```

---

### Phase 2: Intent 提取（2-3天）

#### 2.1 IntentExtractor

**文件**: `src/intent_builder/extractors/intent_extractor.py`

**任务**:
- [ ] 实现 URL 切分逻辑 `_split_by_url()`
- [ ] 实现 LLM 提取 `_extract_from_segment()`
- [ ] 实现主方法 `extract_intents()`
- [ ] Prompt 设计和优化
- [ ] 集成测试

**代码结构**:
```python
from typing import List, Dict, Any
from src.common.llm import AnthropicProvider

class IntentExtractor:
    def __init__(self, llm_provider: AnthropicProvider):
        self.llm = llm_provider

    async def extract_intents(
        self,
        operations: List[Dict[str, Any]],
        task_description: str
    ) -> List[Intent]:
        # Step 1: URL-based segmentation
        segments = self._split_by_url(operations)

        # Step 2: LLM extraction
        all_intents = []
        for segment in segments:
            intents = await self._extract_from_segment(
                segment,
                task_description
            )
            all_intents.extend(intents)

        return all_intents

    def _split_by_url(
        self,
        operations: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        """Split operations by URL changes."""
        if not operations:
            return []

        segments = []
        current_segment = [operations[0]]
        last_url = operations[0].get("url")

        for op in operations[1:]:
            url = op.get("url")
            if op["type"] == "navigate" and last_url and url != last_url:
                # URL changed, start new segment
                segments.append(current_segment)
                current_segment = [op]
                last_url = url
            else:
                current_segment.append(op)
                if url:
                    last_url = url

        if current_segment:
            segments.append(current_segment)

        return segments

    async def _extract_from_segment(
        self,
        segment: List[Dict[str, Any]],
        task_description: str
    ) -> List[Intent]:
        """Extract 1-N intents from a segment using LLM."""
        prompt = self._build_extraction_prompt(segment, task_description)
        response = await self.llm.generate_response("", prompt)

        # Parse LLM response
        intents_data = self._parse_llm_response(response)

        # Create Intent objects
        intents = []
        for data in intents_data:
            description = data["description"]
            operation_indices = data["operation_indices"]

            intent = Intent(
                id=generate_intent_id(description),
                description=description,
                operations=[
                    Operation.from_dict(segment[i])
                    for i in operation_indices
                ],
                created_at=datetime.now(),
                source_session_id=data.get("session_id", "unknown")
            )
            intents.append(intent)

        return intents

    def _build_extraction_prompt(
        self,
        segment: List[Dict[str, Any]],
        task_description: str
    ) -> str:
        # Build detailed prompt (see intent_extractor_design.md)
        return f"""
You are an expert at analyzing user browser operations and extracting semantic intents.

Task Description: {task_description}

Operations Segment:
{json.dumps(segment, indent=2, ensure_ascii=False)}

Your job:
1. Analyze the operations and understand what the user is trying to accomplish
2. Extract 1 or more intents from this segment (each intent represents a complete sub-task)
3. For each intent, provide:
   - description: A concise semantic description (1 sentence)
   - operation_indices: The indices of operations that belong to this intent

Output format (JSON):
[
  {{
    "description": "...",
    "operation_indices": [0, 1, 2]
  }}
]
"""

    def _parse_llm_response(self, response: str) -> List[Dict[str, Any]]:
        # Extract JSON from response
        # Handle markdown code blocks
        import re
        import json

        # Try to find JSON in code blocks
        match = re.search(r'```json\n(.*?)\n```', response, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            json_str = response

        return json.loads(json_str)
```

**测试**:
```python
async def test_intent_extractor():
    # Load test data
    with open("tests/sample_data/browser-user-operation-tracker-example.json") as f:
        data = json.load(f)

    extractor = IntentExtractor(llm_provider)
    intents = await extractor.extract_intents(
        data["operations"],
        data["taskDescription"]
    )

    # Verify
    assert len(intents) >= 3
    assert all(intent.description for intent in intents)
    assert all(intent.operations for intent in intents)
```

---

### Phase 3: MetaFlow 生成（2-3天）

#### 3.1 MetaFlowGenerator

**文件**: `src/intent_builder/generators/metaflow_generator.py`

**任务**:
- [ ] 实现主方法 `generate()`
- [ ] 实现 Prompt 构建 `_build_prompt()`
- [ ] YAML 解析和验证
- [ ] 集成测试

**代码结构**:
```python
class MetaFlowGenerator:
    def __init__(self, llm_provider: AnthropicProvider):
        self.llm = llm_provider

    async def generate(
        self,
        intents: List[Intent],
        task_description: str,
        user_query: str
    ) -> MetaFlow:
        """
        Generate MetaFlow from intents using LLM.

        LLM responsibilities:
        1. Loop detection (keywords: "所有", "每个")
        2. Hidden node generation (e.g., ExtractList)
        3. Data flow inference (source_node, loop_variable)
        4. Node ordering
        """
        # Build comprehensive prompt
        prompt = self._build_prompt(intents, task_description, user_query)

        # LLM generates complete MetaFlow YAML
        response = await self.llm.generate_response("", prompt)

        # Parse and validate
        metaflow_yaml = self._extract_yaml(response)
        metaflow = MetaFlow.from_yaml(metaflow_yaml)

        return metaflow

    def _build_prompt(
        self,
        intents: List[Intent],
        task_description: str,
        user_query: str
    ) -> str:
        # Build detailed prompt (see metaflow_generator_design.md)
        intents_info = self._format_intents(intents)

        return f"""
You are an expert at generating MetaFlow from user intents.

Task Description: {task_description}
User Query: {user_query}

Retrieved Intents:
{intents_info}

Your job:
1. **Loop Detection**: Analyze user_query for keywords like "所有", "每个" to detect loops
2. **Hidden Node Generation**: If loop is detected but no ExtractList intent exists, generate one
3. **Data Flow Inference**: Determine source_node and loop_variable for loops
4. **Node Ordering**: Arrange nodes in execution order

Output a complete MetaFlow YAML with:
- version: "2.0"
- task_description: "{user_query}"
- nodes: [list of nodes, may include hidden nodes]
- control_flow: {{loops: [...]}} (if loops detected)

Example structure:
```yaml
version: "2.0"
task_description: "..."
nodes:
  - id: node_1
    intent_id: intent_xxx
    intent_name: "..."
    intent_description: "..."
    operations: [...]

  - id: node_2
    # Hidden node (no intent_id)
    intent_name: "ExtractList"
    intent_description: "..."
    operations: [...]

control_flow:
  loops:
    - loop_variable: product_url
      source_node: node_2
      loop_body: [node_3]
```

Generate the MetaFlow YAML now:
"""

    def _format_intents(self, intents: List[Intent]) -> str:
        lines = []
        for i, intent in enumerate(intents, 1):
            lines.append(f"Intent {i}:")
            lines.append(f"  ID: {intent.id}")
            lines.append(f"  Description: {intent.description}")
            lines.append(f"  Operations ({len(intent.operations)} total):")
            for j, op in enumerate(intent.operations[:3]):  # Show first 3
                lines.append(f"    - {op.type}: {op.url}")
            if len(intent.operations) > 3:
                lines.append(f"    ... and {len(intent.operations) - 3} more")
            lines.append("")
        return "\n".join(lines)

    def _extract_yaml(self, response: str) -> str:
        # Extract YAML from markdown code blocks
        import re
        match = re.search(r'```yaml\n(.*?)\n```', response, re.DOTALL)
        if match:
            return match.group(1)
        return response
```

---

### Phase 4: 端到端集成（1-2天）

#### 4.1 Demo 1: Learning Flow

**文件**: `tests/integration/test_learning_flow.py`

**任务**:
- [ ] 完整的 User Operations → Intent Graph 流程
- [ ] 使用真实数据测试
- [ ] 验证结果正确性

**代码**:
```python
async def test_demo1_learning_flow():
    """Demo 1: User Operations → Intent Graph"""
    # 1. Load user operations
    with open("tests/sample_data/browser-user-operation-tracker-example.json") as f:
        data = json.load(f)

    # 2. Extract intents
    extractor = IntentExtractor(llm_provider)
    intents = await extractor.extract_intents(
        data["operations"],
        data["taskDescription"]
    )
    print(f"Extracted {len(intents)} intents")

    # 3. Build graph
    graph = IntentMemoryGraph()
    for i, intent in enumerate(intents):
        graph.add_intent(intent)
        if i > 0:
            graph.add_edge(intents[i-1].id, intent.id)

    # 4. Save graph
    graph.save("output/intent_graph.json")
    print("Intent graph saved")

    # Verify
    assert len(graph.intents) == len(intents)
    assert len(graph.edges) == len(intents) - 1
```

#### 4.2 Demo 2: Generation Flow

**文件**: `tests/integration/test_generation_flow.py`

**任务**:
- [ ] 完整的 User Query → Workflow 流程
- [ ] 使用 Demo 1 生成的 Intent Graph
- [ ] 验证生成的 Workflow 可执行

**代码**:
```python
async def test_demo2_generation_flow():
    """Demo 2: User Query → Workflow"""
    # 1. Load intent graph
    graph = IntentMemoryGraph.load("output/intent_graph.json")
    print(f"Loaded {len(graph.intents)} intents")

    # 2. Semantic retrieval
    user_query = "采集 Allegro 上所有咖啡的价格和销量"
    retrieved_intents = await graph.retrieve_similar(user_query, limit=5)
    print(f"Retrieved {len(retrieved_intents)} intents")

    # 3. Generate MetaFlow
    metaflow_gen = MetaFlowGenerator(llm_provider)
    metaflow = await metaflow_gen.generate(
        retrieved_intents,
        "从 Allegro 采集咖啡产品价格",
        user_query
    )
    print("MetaFlow generated")

    # 4. Generate Workflow
    workflow_gen = WorkflowGenerator()
    workflow_yaml = await workflow_gen.generate(metaflow)
    print("Workflow generated")

    # 5. Save outputs
    with open("output/metaflow.yaml", "w") as f:
        f.write(metaflow.to_yaml())
    with open("output/workflow.yaml", "w") as f:
        f.write(workflow_yaml)

    # Verify
    assert "version" in workflow_yaml
    assert "steps" in workflow_yaml
```

---

## 3. 开发计划时间表

| 阶段 | 任务 | 预计时间 | 产出 |
|------|------|---------|------|
| Phase 1 | Intent 数据模型 | 1天 | `core/intent.py` + 测试 |
| Phase 1 | IntentMemoryGraph | 1天 | `core/intent_memory_graph.py` + 测试 |
| Phase 2 | IntentExtractor | 2天 | `extractors/intent_extractor.py` + 测试 |
| Phase 3 | MetaFlowGenerator | 2天 | `generators/metaflow_generator.py` + 测试 |
| Phase 4 | Demo 1 | 0.5天 | 学习流程端到端测试 |
| Phase 4 | Demo 2 | 0.5天 | 生成流程端到端测试 |
| Phase 4 | 文档和优化 | 1天 | README, 示例, 性能优化 |
| **总计** | | **8天** | 完整 MVP 系统 |

---

## 4. 测试策略

### 4.1 单元测试

每个组件独立测试：
- Intent: 创建、序列化、ID 生成
- IntentMemoryGraph: 添加、检索、持久化
- IntentExtractor: URL 切分、LLM 提取
- MetaFlowGenerator: Prompt 构建、YAML 生成

### 4.2 集成测试

端到端流程测试：
- Demo 1: User Operations → Intent Graph
- Demo 2: User Query → Workflow
- 完整 Pipeline: User Operations → Workflow

### 4.3 性能测试

- Intent 提取：16个操作 → 4个 Intent（~10-15s）
- 语义检索：100个 Intent 检索 top-5（<1s）
- MetaFlow 生成：5个 Intent → MetaFlow（~15-20s）
- 总耗时：~40-60s（端到端）

---

## 5. 依赖项

### Python 包
```
anthropic>=0.18.0
openai>=1.12.0
pydantic>=2.0.0
pyyaml>=6.0
```

### 环境变量
```bash
ANTHROPIC_API_KEY=your_key
OPENAI_API_KEY=your_key  # For embeddings
```

---

## 6. 验收标准

### MVP 完成标准

1. ✅ 所有核心组件实现并通过单元测试
2. ✅ Demo 1 成功运行（User Operations → Intent Graph）
3. ✅ Demo 2 成功运行（User Query → Workflow）
4. ✅ 生成的 Workflow 可在 BaseAgent 上执行
5. ✅ 代码文档完整
6. ✅ 示例数据和输出可复现

### 质量标准

1. 代码覆盖率 > 80%
2. 所有 LLM 调用有超时和重试机制
3. 所有文件操作有错误处理
4. 日志记录完整（INFO级别）
5. 符合项目代码规范

---

## 7. 风险和缓解

### 7.1 LLM 输出质量

**风险**: LLM 生成的 Intent/MetaFlow 不符合预期

**缓解**:
1. 详细的 Prompt 设计和示例
2. 输出验证和重试机制
3. 逐步优化 Prompt

### 7.2 语义检索准确性

**风险**: 检索到的 Intent 不相关

**缓解**:
1. 使用高质量 embedding 模型（text-embedding-3-small）
2. 支持调整检索数量 limit
3. 后续可添加重排序（reranking）

### 7.3 性能问题

**风险**: LLM 调用耗时长

**缓解**:
1. 异步调用
2. Embedding 缓存
3. 后续优化：批量处理、并行调用

---

## 8. 下一步（MVP 后）

### 迭代 1（Post-MVP）
1. Intent 去重和合并
2. 使用频率统计
3. 支持条件分支
4. 改进 Prompt

### 迭代 2
1. 交互式修改 MetaFlow
2. 多语言支持
3. 可视化 Intent Graph
4. 性能优化

### 迭代 3
1. Fine-tuned 模型
2. 增量学习
3. 用户反馈闭环
4. 企业级部署

---

## 9. 参考文档

- [设计概览](design_overview.md)
- [Intent 规范](intent_specification.md)
- [IntentMemoryGraph 规范](intent_memory_graph_specification.md)
- [IntentExtractor 设计](intent_extractor_design.md)
- [MetaFlowGenerator 设计](metaflow_generator_design.md)
- [完整 Pipeline 流程](complete_pipeline_flow.md)
- [实现指南](implementation_guide.md)
