# 讨论记录 04 - Intent 架构核心决策

**日期**: 2025-10-09
**参与者**: User, Claude
**状态**: 已确定

---

## 讨论背景

在完成 MetaFlow → Workflow 转换后，需要确定上游的 User Operations → Intent → MetaFlow 的架构设计。

**核心问题**：
1. Intent 的数据结构应该如何设计？
2. Intent Memory Graph 如何组织和检索？
3. 如何从 User Operations JSON 提取 Intent？
4. 如何从 Intent 生成 MetaFlow（包括隐式节点和数据流推断）？

---

## 核心架构确认

### 完整数据流

```
User Operations JSON + Task Description
  ↓
[1] IntentExtractor (URL切分 + LLM语义提取)
  ↓
Intent List
  ↓
[2] IntentMemoryGraph (存储、无去重)
  ↓
[3] Intent Retrieval (基于描述相似度)
  ↓
Retrieved Intent List
  ↓
[4] MetaFlowGenerator (LLM组装 + 推断)
  ↓
MetaFlow YAML
  ↓
[5] WorkflowGenerator (已完成)
  ↓
Workflow YAML
```

---

## 决策记录

### 决策 1: Intent 数据结构极简化

**问题**: Intent 需要哪些字段？是否需要 tags, category, inputs/outputs？

**决策**: **极简设计，只保留核心字段**

```python
@dataclass
class Intent:
    id: str                          # 唯一标识
    description: str                 # LLM 生成的意图描述
    operations: List[Operation]      # 来自 JSON 的原始操作

    # 元数据
    created_at: datetime
    source_session_id: str
```

**理由**：
1. ❌ **去掉 tags/category**：检索用语义相似度，不需要标签
2. ❌ **去掉 inputs/outputs**：由 MetaFlow 层的 LLM 推断，Intent 层不处理
3. ✅ **只保留描述和操作**：Intent 的本质就是"做什么"（description）和"怎么做"（operations）

**优势**：
- 简单：数据结构清晰，易于理解
- 灵活：LLM 负责语义理解，无需预定义分类体系
- 可扩展：未来需要时可以添加字段

---

### 决策 2: Intent ID 生成策略

**问题**: Intent ID 如何生成？UUID vs 序号 vs 描述哈希？

**决策**: **使用描述的 MD5 哈希（前8位）**

```python
import hashlib

def generate_intent_id(description: str) -> str:
    hash_value = hashlib.md5(description.encode()).hexdigest()[:8]
    return f"intent_{hash_value}"
```

**理由**：
- 语义相关：相同描述生成相同 ID（有助于未来去重）
- 唯一性：MD5 哈希冲突概率极低
- 可读性：ID 包含语义哈希，便于调试

---

### 决策 3: MVP 无去重策略

**问题**: 相似的 Intent 是否需要去重/合并？

**决策**: **MVP 阶段不实现去重**

**理由**：
- MVP 场景简单：通常只有单个或少量 JSON 输入
- 去重需要语义相似度计算：增加复杂度
- 先验证核心流程：去重是优化，不是必需

**未来迭代**：
- 使用 embedding 计算相似度
- 阈值：0.90（相对严格）
- 策略：合并并增加 frequency

---

### 决策 4: IntentMemoryGraph 存储结构

**问题**: Graph 如何存储节点和边？

**决策**: **极简图结构，边表示时间顺序**

```python
class IntentMemoryGraph:
    intents: Dict[str, Intent]              # id -> Intent
    edges: List[Tuple[str, str]]            # [(from_id, to_id), ...]

    def add_intent(self, intent: Intent) -> None
    def add_edge(self, from_id: str, to_id: str) -> None
    def get_all_intents(self) -> List[Intent]
    def save(self, filepath: str) -> None
    @staticmethod
    def load(filepath: str) -> "IntentMemoryGraph"
```

**边的语义**:
- 表示时间顺序（"然后"）
- from_intent 执行后，执行 to_intent
- MVP 不记录频率权重（未来可扩展）

**持久化**: MVP 使用 JSON 文件

---

### 决策 5: Intent 提取策略

**问题**: 如何从 User Operations 提取 Intent？

**决策**: **规则切分 + LLM 语义提取（方案 A）**

#### 步骤 1: URL 切分（规则）

```python
def split_by_url_change(operations: List[Dict]) -> List[List[Dict]]:
    """按 URL 变化切分操作序列"""
    segments = []
    current_segment = []
    last_url = None

    for op in operations:
        url = op.get('url', '')

        # navigate 操作 + URL 变化 → 新 segment
        if op['type'] == 'navigate' and last_url and url != last_url:
            if current_segment:
                segments.append(current_segment)
            current_segment = [op]
        else:
            current_segment.append(op)

        last_url = url

    if current_segment:
        segments.append(current_segment)

    return segments
```

#### 步骤 2: LLM 提取 Intent（每个 segment → 1-N Intent）

**Prompt 设计**：
- 输入：操作序列 + 任务描述
- 输出：1个或多个 Intent（JSON 数组）
- 切分粒度：一个明确的子目标 = 一个 Intent

**输出格式**：
```json
[
  {
    "description": "导航到 Allegro 首页",
    "operation_indices": [0]
  },
  {
    "description": "通过菜单进入咖啡分类页面",
    "operation_indices": [1, 2, 3]
  }
]
```

**理由**：
- 规则处理结构化问题（URL 切分）
- LLM 处理语义问题（Intent 识别和描述）
- 可控性强，便于调试

---

### 决策 6: MetaFlow 生成策略

**问题**: 如何从 Intent 列表生成 MetaFlow？是否需要推断隐式节点和数据流？

**决策**: **完全交给 LLM**

```python
class MetaFlowGenerator:
    async def generate(
        self,
        intents: List[Intent],
        task_description: str,
        user_query: str
    ) -> MetaFlow:
        """从 Intent 列表生成 MetaFlow"""

        # 构建 Prompt（包含 Intent 列表）
        prompt = self._build_prompt(intents, task_description, user_query)

        # LLM 生成完整的 MetaFlow YAML
        metaflow_yaml = await self.llm.generate_response("", prompt)

        # 解析并返回
        metaflow = MetaFlow.from_yaml(metaflow_yaml)
        return metaflow
```

**LLM 负责**：
1. ✅ 循环检测（从 user_query 关键词："所有"、"每个"）
2. ✅ 隐式节点生成（如需要循环但缺少列表提取节点）
3. ✅ 数据流连接（推断变量引用）
4. ✅ 节点顺序调整

**不使用规则推断的理由**：
- 隐式节点生成逻辑复杂（何时插入？如何推断 xpath？）
- 数据流连接需要语义理解（哪个 output 对应哪个 input？）
- LLM 更灵活，可以处理各种复杂情况
- 简化代码，减少维护成本

**Prompt 设计要点**：
- 提供完整的 Intent 信息（description + operations）
- 说明 MetaFlow 规范
- 给出转换规则和示例
- 明确要求：推断隐式节点、连接数据流

---

### 决策 7: copy_action 处理

**问题**: JSON 中的 copy_action 操作如何处理？

**决策**: **保留原样，作为 Intent.operations 的一部分**

**理由**：
- copy_action 是用户操作的真实记录
- LLM 能理解其语义（"用户想要提取这个数据"）
- 在 MetaFlow → Workflow 时，LLM 会将其转换为 scraper_agent 配置

**示例**：
```python
# Intent.operations 中保留
Operation(
    type="copy_action",
    data={"copiedText": "69,50 zł"}
)

# LLM 在生成 Workflow 时理解为：
# - 这是数据提取操作
# - 用户想要的数据是 "69,50 zł"
# - 生成 scraper_agent 的 sample_data
```

---

### 决策 8: Intent 检索策略

**问题**: 如何从 Graph 检索相关 Intent？

**决策**: **基于语义相似度检索（Embedding + Cosine Similarity）**

```python
class IntentRetriever:
    def __init__(self, graph: IntentMemoryGraph, embedding_service):
        self.graph = graph
        self.embedding = embedding_service

    async def retrieve(
        self,
        user_query: str,
        limit: int = 5
    ) -> List[Intent]:
        """根据用户查询检索相关意图"""

        # 计算查询的 embedding
        query_embedding = await self.embedding.embed(user_query)

        # 计算所有 Intent 的相似度
        scored = []
        for intent in self.graph.get_all_intents():
            intent_embedding = await self.embedding.embed(intent.description)
            similarity = cosine_similarity(query_embedding, intent_embedding)

            if similarity > 0.6:  # 过滤低相似度
                scored.append((similarity, intent))

        # 排序并返回 top-K
        scored.sort(key=lambda x: x[0], reverse=True)
        return [intent for _, intent in scored[:limit]]
```

**Embedding 模型**: OpenAI text-embedding-3-small（MVP）

**相似度阈值**: 0.6（过滤明显不相关的）

---

## 设计原则总结

### 1. 极简原则
- Intent 只保留核心字段（description + operations）
- Graph 只存储必要信息（intents + edges）
- MVP 不实现非必需功能（去重、频率权重）

### 2. LLM 优先原则
- Intent 提取：LLM 生成描述
- MetaFlow 生成：LLM 推断隐式节点和数据流
- 不用规则处理复杂语义问题

### 3. 语义理解原则
- Intent 检索：语义相似度（非标签匹配）
- Intent ID：描述哈希（语义相关）
- 数据流：LLM 推断（非规则匹配）

### 4. 渐进式演进原则
- MVP：验证核心流程（单 JSON → MetaFlow）
- 迭代 1：引入去重、频率权重
- 迭代 2：支持多 JSON、路径推荐

---

## MVP 范围确认

### 包含功能

1. ✅ **Intent 提取**：URL 切分 + LLM 生成描述
2. ✅ **Intent 存储**：IntentMemoryGraph（内存 + JSON 持久化）
3. ✅ **Intent 检索**：语义相似度检索
4. ✅ **MetaFlow 生成**：LLM 推断（含隐式节点和数据流）
5. ✅ **完整流程**：User JSON → Intent → MetaFlow → Workflow

### 不包含功能

1. ❌ **Intent 去重**：MVP 不实现
2. ❌ **频率权重**：MVP 不记录使用频率
3. ❌ **路径推荐**：MVP 不推荐高频路径
4. ❌ **交互式修改**：MVP 不支持用户修改 MetaFlow
5. ❌ **多版本管理**：MVP 不支持 Intent 版本优化

---

## 未解决问题（后续讨论）

### P1: LLM Prompt 细节设计

需要详细设计两个关键 Prompt：

1. **IntentExtractor Prompt**
   - 如何描述切分粒度？
   - Few-shot 示例？
   - 输出格式限制？

2. **MetaFlowGenerator Prompt**
   - 如何指导 LLM 推断隐式节点？
   - 如何指导 LLM 连接数据流？
   - 如何确保输出格式正确？

### P2: 边界情况处理

1. **同页面多操作如何切分？**
   - 例如：多个 click 但 URL 不变
   - LLM 是否会切分成多个 Intent？

2. **复杂数据流如何推断？**
   - 例如：多个 extract 操作的数据如何组合？
   - LLM 是否能正确推断？

3. **隐式节点的 xpath 如何生成？**
   - LLM 使用占位符？
   - 还是尝试推断具体的 xpath？

---

## 后续行动

1. **编写详细的组件设计文档**
   - IntentExtractor
   - IntentMemoryGraph
   - MetaFlowGenerator

2. **设计 LLM Prompt 模板**
   - Intent 提取 Prompt
   - MetaFlow 生成 Prompt

3. **更新整体设计文档**
   - design_overview.md
   - metaflow_design.md

4. **编写实施计划**
   - 开发顺序
   - 测试策略
   - 验收标准

---

## 参考资料

- User Operations 示例: `tests/sample_data/browser-user-operation-tracker-example.json`
- MetaFlow 示例: `docs/intent_builder/examples/coffee_collection_metaflow.yaml`
- Workflow 示例: `src/base_app/base_app/base_agent/workflows/user/paginated-scraper-workflow.yaml`
- MetaFlow 规范: `metaflow_specification.md`
- 系统设计: `design_overview.md`
