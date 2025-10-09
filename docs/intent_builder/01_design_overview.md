# Intent-Based AgentBuilder - 系统设计

**更新日期**: 2025-10-09
**状态**: 架构已确定

---

## 1. 目标

将用户的浏览器操作记录转换为可执行的 Workflow，通过意图抽象和记忆复用实现智能化工作流生成。

```
学习阶段: 用户操作 JSON + 任务描述 → Intent Memory Graph
生成阶段: 用户查询 + Intent Memory Graph → YAML Workflow
```

---

## 2. 核心设计思想

### 2.1 极简意图 + LLM推理 架构

**核心理念**：Intent 只负责语义抽象，复杂的推理交给 LLM

1. **提取意图**：把操作序列抽象成语义描述（description）+ 原始操作（operations）
2. **记住意图**：构建意图图（IntentMemoryGraph），记录时间顺序
3. **LLM 推理**：从意图生成 MetaFlow 时，LLM 负责：
   - 推断隐式节点（如循环需要的 ExtractList）
   - 推断数据流（变量的传递关系）
   - 推断控制流（循环、分支）
4. **重用意图**：新任务时从记忆检索相关意图，组合成新 workflow

```
学习阶段:
用户操作 JSON → IntentExtractor → Intent Graph → 持久化

生成阶段:
用户查询 → 语义检索 → Intents → MetaFlowGenerator → MetaFlow → WorkflowGenerator → YAML
```

### 2.2 设计原则

1. **极简设计**：Intent 只有 `id`, `description`, `operations`, `metadata`
2. **语义优先**：使用语义相似度检索，不依赖标签/分类
3. **LLM 为主**：复杂逻辑交给 LLM，规则只用于结构化切分
4. **操作完整**：保留原始操作序列，提供完整上下文

---

## 3. 核心概念

### 3.1 意图（Intent）

**定义**：用户操作的语义抽象，表示一个完整的子任务单元

**数据结构**：
```python
@dataclass
class Intent:
    id: str                          # MD5 hash of description
    description: str                 # 语义描述（LLM 生成）
    operations: List[Operation]      # 原始操作序列
    created_at: datetime             # 创建时间
    source_session_id: str           # 来源会话
```

**示例**：
```python
Intent(
    id="intent_b7e4c8d2",
    description="通过菜单导航进入咖啡产品分类页面",
    operations=[
        Operation(type="click", element={"textContent": "菜单"}),
        Operation(type="click", element={"textContent": "Kawy", "href": "..."}),
        Operation(type="navigate", url="https://allegro.pl/kategoria/...")
    ],
    created_at=datetime(2025, 10, 9, 12, 30, 5),
    source_session_id="session_demo_001"
)
```

**特点**：
- **极简设计**：不包含 tags、category、inputs/outputs
- **语义完整**：description 提供人类可读的意图描述
- **上下文完整**：operations 保留完整的用户操作（包括 copy_action）
- **语义 ID**：基于 description 的 MD5 hash，支持未来去重

### 3.2 IntentMemoryGraph

**定义**：存储 Intent 节点和时间顺序边的图结构

**核心接口**：
```python
class IntentMemoryGraph:
    intents: Dict[str, Intent]              # id -> Intent
    edges: List[Tuple[str, str]]            # [(from_id, to_id), ...]

    def add_intent(self, intent: Intent) -> None
    def add_edge(self, from_id: str, to_id: str) -> None
    async def retrieve_similar(self, query: str, limit: int = 5) -> List[Intent]
    def save(self, filepath: str) -> None
    @staticmethod
    def load(filepath: str) -> "IntentMemoryGraph"
```

**特点**：
- **有向图**：边表示时间先后顺序
- **语义检索**：使用 embedding 相似度检索（OpenAI text-embedding-3-small）
- **持久化**：JSON 格式存储（MVP）
- **不记录频率**：MVP 不需要频率统计

**示例**：
```python
graph = IntentMemoryGraph()
graph.add_intent(intent1)  # NavigateToAllegro
graph.add_intent(intent2)  # EnterCoffeeCategory
graph.add_intent(intent3)  # ExtractProductInfo
graph.add_edge(intent1.id, intent2.id)  # 时间顺序
graph.add_edge(intent2.id, intent3.id)

# 语义检索
intents = await graph.retrieve_similar("采集咖啡价格", limit=5)
```

### 3.3 MetaFlow

**定义**：Intent 和控制流的中间表示，人类可读的 YAML 格式

**数据结构**：
```python
@dataclass
class MetaFlow:
    task_description: str                # 任务描述
    nodes: List[MetaFlowNode]            # 节点列表
    control_flow: Dict[str, Any]         # 控制流信息
```

**示例**（来自 `coffee_collection_metaflow.yaml`）：
```yaml
task_description: "从 Allegro 采集所有咖啡产品的价格"
nodes:
  - id: node_1
    intent_name: NavigateToAllegro
    intent_description: "导航到 Allegro 首页"

  - id: node_2
    intent_name: EnterCoffeeCategory
    intent_description: "进入咖啡分类页面"

  - id: node_3
    intent_name: ExtractProductList
    intent_description: "提取产品列表"
    type: hidden  # LLM 推断的隐式节点

  - id: node_4
    intent_name: ExtractProductInfo
    intent_description: "提取单个产品信息"
    is_loop_body: true

control_flow:
  loops:
    - loop_variable: product_url
      source_node: node_3  # 数据来源
      loop_body: [node_4]
```

**特点**：
- **包含隐式节点**：LLM 推断的节点（如 ExtractList）
- **包含数据流**：变量引用关系
- **包含控制流**：循环、分支信息
- **人类可读**：YAML 格式，便于理解和调试

### 3.4 Workflow

**定义**：BaseAgent 可执行的 YAML 文件

**生成方式**：由 WorkflowGenerator 将 MetaFlow 转换为 Workflow

**参考**：`docs/baseagent/workflow_specification.md`

---

## 4. 系统架构

### 4.1 完整数据流

```
                    ┌─────────────────────────────────┐
                    │      Learning Phase             │
                    │  (用户演示 → 意图提取)            │
                    └─────────────────────────────────┘
                              ↓
    User Operations JSON + Task Description
                              ↓
                    ┌─────────────────────┐
                    │  IntentExtractor     │
                    │  - URL切分 (规则)     │
                    │  - Intent生成 (LLM)  │
                    └─────────────────────┘
                              ↓
                      List[Intent]
                              ↓
                    ┌─────────────────────┐
                    │ IntentMemoryGraph    │
                    │ - 存储Intent节点      │
                    │ - 添加时间顺序边      │
                    │ - 持久化到JSON       │
                    └─────────────────────┘


                    ┌─────────────────────────────────┐
                    │     Generation Phase            │
                    │  (用户查询 → Workflow生成)        │
                    └─────────────────────────────────┘
                              ↓
              User Query + IntentMemoryGraph
                              ↓
                    ┌─────────────────────┐
                    │ Semantic Retrieval   │
                    │ - Embedding相似度     │
                    │ - 检索相关Intents     │
                    └─────────────────────┘
                              ↓
                    Retrieved Intents
                              ↓
                    ┌─────────────────────┐
                    │ MetaFlowGenerator    │
                    │ (LLM完成所有推理)     │
                    │ - 循环检测           │
                    │ - 隐式节点生成        │
                    │ - 数据流推断         │
                    │ - 节点排序           │
                    └─────────────────────┘
                              ↓
                         MetaFlow
                              ↓
                    ┌─────────────────────┐
                    │ WorkflowGenerator    │
                    │ (LLM生成YAML)        │
                    │ - 转换为BaseAgent    │
                    │   Workflow格式       │
                    └─────────────────────┘
                              ↓
                       workflow.yaml
                              ↓
                    ┌─────────────────────┐
                    │     BaseAgent        │
                    └─────────────────────┘
                              ↓
                          Result
```

### 4.2 组件职责

**IntentExtractor** - Intent 提取器
- 输入：User Operations JSON + Task Description
- 输出：List[Intent]
- 策略：规则切分（URL变化）+ LLM提取（语义理解）

**IntentMemoryGraph** - Intent 存储和检索
- 存储：Intent 节点 + 时间顺序边
- 检索：基于语义相似度（embedding）
- 持久化：JSON 格式

**MetaFlowGenerator** - MetaFlow 生成器
- 输入：List[Intent] + User Query + Task Description
- 输出：MetaFlow (YAML)
- LLM 职责：
  - 循环检测（关键词："所有"、"每个"）
  - 隐式节点生成（如循环前的 ExtractList）
  - 数据流推断（变量传递）
  - 节点排序

**WorkflowGenerator** - Workflow 生成器（已实现）
- 输入：MetaFlow
- 输出：BaseAgent Workflow YAML
- 已有实现：`src/intent_builder/generators/workflow_generator.py`

---

## 5. 核心组件详细设计

### 5.1 IntentExtractor

**核心方法**：
```python
async def extract_intents(
    self,
    operations: List[Dict],
    task_description: str
) -> List[Intent]:
    # Step 1: URL-based segmentation (规则)
    segments = self._split_by_url(operations)

    # Step 2: LLM extraction (1-N intents per segment)
    all_intents = []
    for segment in segments:
        intents = await self._extract_from_segment(segment, task_description)
        all_intents.extend(intents)

    return all_intents
```

**切分规则**：
- `navigate` 操作 + URL 变化 → 新 segment
- 每个 segment 交给 LLM 生成 1-N 个 Intent

**LLM 提示词**：包含 operations + task_description，要求生成 description 和 operation_indices

详见：`docs/intent_builder/intent_extractor_design.md`

### 5.2 IntentMemoryGraph

**存储结构**：
```python
{
    "intents": {
        "intent_id": {
            "id": "intent_xxx",
            "description": "...",
            "operations": [...],
            "created_at": "2025-10-09T12:30:00",
            "source_session_id": "session_001"
        }
    },
    "edges": [
        ["intent_id_1", "intent_id_2"],
        ["intent_id_2", "intent_id_3"]
    ]
}
```

**检索实现**：
```python
async def retrieve_similar(self, query: str, limit: int = 5) -> List[Intent]:
    # 1. 生成 query embedding
    query_emb = await self._get_embedding(query)

    # 2. 计算相似度
    scores = []
    for intent in self.intents.values():
        desc_emb = await self._get_embedding(intent.description)
        similarity = cosine_similarity(query_emb, desc_emb)
        scores.append((intent, similarity))

    # 3. 排序返回
    scores.sort(key=lambda x: x[1], reverse=True)
    return [intent for intent, _ in scores[:limit]]
```

详见：`docs/intent_builder/intent_memory_graph_specification.md`

### 5.3 MetaFlowGenerator

**核心方法**：
```python
async def generate(
    self,
    intents: List[Intent],
    task_description: str,
    user_query: str
) -> MetaFlow:
    # Build comprehensive prompt
    prompt = self._build_prompt(intents, task_description, user_query)

    # LLM generates complete MetaFlow YAML
    response = await self.llm.generate_response("", prompt)

    # Parse and validate
    metaflow_yaml = self._extract_yaml(response)
    return MetaFlow.from_yaml(metaflow_yaml)
```

**LLM 职责**：
1. 循环检测：从 user_query 识别关键词（"所有"、"每个"）
2. 隐式节点生成：如果有循环但缺少 ExtractList 节点，生成之
3. 数据流连接：推断变量传递关系
4. 节点排序：确定执行顺序

**Prompt 设计**：
- 提供所有 Intent 的 description + operations
- 提供 user_query 和 task_description
- 要求生成完整的 MetaFlow YAML（包括隐式节点和数据流）

详见：`docs/intent_builder/metaflow_generator_design.md`

### 5.4 WorkflowGenerator（已实现）

**功能**：将 MetaFlow 转换为 BaseAgent Workflow YAML

**实现**：`src/intent_builder/generators/workflow_generator.py`

**策略**：LLM 生成 + 模板填充

---

## 6. MVP 范围

### ✅ 包含

1. **Intent 提取**
   - URL-based 切分（规则）
   - LLM 生成 description（语义理解）
   - 1-N Intent per segment

2. **IntentMemoryGraph**
   - 存储 Intent 节点
   - 时间顺序边
   - 语义相似度检索（embedding）
   - JSON 持久化

3. **MetaFlow 生成**
   - LLM 完成所有推理
   - 循环检测（关键词）
   - 隐式节点生成（ExtractList）
   - 数据流推断

4. **Workflow 生成**
   - MetaFlow → Workflow YAML
   - 已有实现

5. **完整 Pipeline**
   - Demo 1: User Operations → Intent Graph
   - Demo 2: User Query → Workflow

### ❌ 不包含

1. **Intent 去重/合并**
   - MVP 假设没有重复 Intent
   - 未来可用 ID (description hash) 实现

2. **使用频率统计**
   - 不记录 Intent 使用次数
   - 不基于频率排序

3. **复杂控制流**
   - 只支持简单循环（foreach）
   - 不支持条件分支（if/else）
   - 不支持嵌套循环

4. **交互式修改**
   - 生成后不可修改
   - 未来可添加 UI

5. **Intent 版本管理**
   - 只保留一个版本
   - 不支持版本对比/回滚

---

## 7. 核心设计决策

详细决策过程见：`docs/intent_builder/discussions/04_intent_architecture_decisions.md`

| 问题 | 决策 | 理由 |
|-----|------|------|
| **Intent 结构** | 极简化：只有 `id`, `description`, `operations`, `metadata` | 复杂推理交给 LLM，Intent 只负责语义抽象 |
| **Intent ID** | MD5 hash of description（前8位） | 语义相关，支持未来去重 |
| **去重策略** | MVP 不实现 | MVP 假设无重复 Intent |
| **Graph 边含义** | 时间顺序 | 不表示因果关系或数据流 |
| **Intent 切分** | 规则（URL变化）+ LLM（语义理解） | 混合策略：结构化切分 + 语义理解 |
| **MetaFlow 生成** | 完全交给 LLM | LLM 负责循环检测、隐式节点、数据流 |
| **copy_action** | 保留在 operations 中 | 不转换为 extract，由 LLM 理解其语义 |
| **检索方式** | 语义相似度（embedding） | 不使用 tags/category，灵活且准确 |
| **存储方式** | JSON 文件 | MVP 使用文件，未来可升级数据库 |

---

## 8. 实现优先级

### Phase 1: 核心组件实现

1. **Intent 数据结构** - `src/intent_builder/core/intent.py`
   - Intent, Operation 类定义
   - ID 生成逻辑

2. **IntentMemoryGraph** - `src/intent_builder/core/intent_memory_graph.py`
   - 图存储
   - 语义检索
   - JSON 序列化

3. **IntentExtractor** - `src/intent_builder/extractors/intent_extractor.py`
   - URL 切分
   - LLM 提取

### Phase 2: MetaFlow 生成

4. **MetaFlowGenerator** - `src/intent_builder/generators/metaflow_generator.py`
   - Prompt 构建
   - LLM 调用
   - YAML 解析

### Phase 3: 端到端测试

5. **Demo 1**: User Operations → Intent Graph
6. **Demo 2**: User Query → Workflow
7. 性能优化和错误处理

详见：待创建的 `implementation_plan.md`

---

## 9. 完整示例

基于 `tests/sample_data/browser-user-operation-tracker-example.json`

### Demo 1: 学习阶段（User Operations → Intent Graph）

**输入**：
```json
{
  "taskDescription": "从 Allegro 采集咖啡产品价格",
  "operations": [...]  // 16个操作
}
```

**输出 (IntentMemoryGraph)**：
```python
intents = [
    Intent(
        id="intent_a3f5b2c1",
        description="导航到 Allegro 电商网站首页"
    ),
    Intent(
        id="intent_b7e4c8d2",
        description="通过菜单导航进入咖啡产品分类页面"
    ),
    Intent(
        id="intent_d8e3f1a5",
        description="从分类页面提取所有产品的链接"
    ),
    Intent(
        id="intent_c9f2d5e3",
        description="访问产品详情页，提取并存储产品的标题、价格、销量信息"
    )
]

# 时间顺序边
edges = [
    (intent_a3f5b2c1, intent_b7e4c8d2),
    (intent_b7e4c8d2, intent_d8e3f1a5),
    (intent_d8e3f1a5, intent_c9f2d5e3)
]
```

### Demo 2: 生成阶段（User Query → Workflow）

**输入**：
```python
user_query = "采集 Allegro 上所有咖啡的价格和销量"
```

**检索结果**：
```python
retrieved_intents = [intent_a3f5b2c1, intent_b7e4c8d2, intent_c9f2d5e3]
```

**MetaFlow 生成**（LLM 推断）：
```yaml
task_description: "采集 Allegro 上所有咖啡的价格和销量"
nodes:
  - id: node_1
    intent_id: intent_a3f5b2c1
    intent_name: NavigateToAllegro

  - id: node_2
    intent_id: intent_b7e4c8d2
    intent_name: EnterCoffeeCategory

  - id: node_3
    intent_name: ExtractProductList  # 隐式节点（LLM生成）
    type: hidden

  - id: node_4
    intent_id: intent_c9f2d5e3
    intent_name: ExtractProductInfo
    is_loop_body: true

control_flow:
  loops:
    - loop_variable: product_url
      source_node: node_3
      loop_body: [node_4]
```

**Workflow 生成**：
```yaml
workflow:
  steps:
    - name: navigate_to_allegro
      agent_type: scraper_agent
      parameters: {...}

    - name: enter_category
      agent_type: scraper_agent
      parameters: {...}

    - name: extract_list
      agent_type: scraper_agent
      parameters:
        action: extract_links

    - name: foreach_product
      type: foreach
      variable: product_url
      items: ${extract_list.output}
      steps:
        - name: extract_info
          agent_type: scraper_agent
```

详见：`docs/intent_builder/complete_pipeline_flow.md`

---

## 10. 参考文档

### 核心规范
- **Intent 数据结构**: `intent_specification.md`
- **IntentMemoryGraph**: `intent_memory_graph_specification.md`
- **IntentExtractor 设计**: `intent_extractor_design.md`
- **MetaFlowGenerator 设计**: `metaflow_generator_design.md`
- **完整 Pipeline**: `complete_pipeline_flow.md`

### 设计决策
- **架构决策记录**: `discussions/04_intent_architecture_decisions.md`

### 示例数据
- **用户操作示例**: `tests/sample_data/browser-user-operation-tracker-example.json`
- **MetaFlow 示例**: `examples/coffee_collection_metaflow.yaml`
- **Workflow 示例**: `src/base_app/base_app/base_agent/workflows/user/paginated-scraper-workflow.yaml`

### BaseAgent 文档
- **BaseAgent 架构**: `docs/baseagent/ARCHITECTURE.md`
- **Workflow 规范**: `docs/baseagent/workflow_specification.md`

### 下一步
1. 完成 `metaflow_design.md` 更新
2. 更新 `implementation_guide.md`
3. 创建 `implementation_plan.md`（详细开发计划）
4. 开始 Phase 1 实现
