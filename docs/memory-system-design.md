# Memory System Design Reference

> 综合参考文档，基于 memory-as-map-design.md、memory-graph-redesign-v2.md、memory-agent-integration-design.md 以及当前实现整理。

## 1. 核心理念

**Memory 是认知地图，不是执行剧本。**

Memory 提供三种能力：

| 能力 | 说明 | 示例 |
|------|------|------|
| **地图 (Navigation Map)** | 网站拓扑结构 | "首页 → 分类页 → 详情页" |
| **菜单 (Operations)** | 每个页面上能做什么 | "详情页可以: 看 Team, 看评论, 点赞" |
| **经验 (Patterns)** | 过去类似任务的参考路径 | "查看团队通常: 进详情 → 点 Team" |

Agent 仍需自主决策：选择哪个产品、执行哪些操作、走哪条路径。

---

## 2. 整体架构

系统分为两层：

```
┌──────────────────────────────────────────────────────────────┐
│  Desktop Agent (BaseAgent)                                    │
│  ┌──────────────────────────────────────────────────────────┐│
│  │ MemoryManager (本地三层)                                  ││
│  │  L1: Variables (in-memory dict)                           ││
│  │  L2: SQLite KV Storage (persistent)                       ││
│  │  L3: Mem0 + ChromaDB (TODO, 未启用)                       ││
│  └──────────────────────────────────────────────────────────┘│
│  ┌──────────────────────────────────────────────────────────┐│
│  │ MemoryToolkit (远程查询)                                   ││
│  │  query_task() → Cloud Memory API                          ││
│  │  query_navigation() → Cloud Memory API                    ││
│  └──────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
              │
              ▼ HTTP API
┌──────────────────────────────────────────────────────────────┐
│  Cloud Backend (memgraph)                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐│
│  │ Reasoner     │  │ Thinker     │  │ Memory (Graph)       ││
│  │ (查询推理)    │  │ (录制解析)   │  │ Neo4j / NetworkX    ││
│  └─────────────┘  └─────────────┘  └──────────────────────┘│
│  ┌──────────────────────────────────────────────────────────┐│
│  │ EmbeddingService (OpenAI / BGE-M3)                        ││
│  └──────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 图数据模型 (V2)

### 3.1 节点类型

| 节点 | 说明 | 关键字段 |
|------|------|----------|
| **State** | 抽象页面类型（如"产品详情页"） | `description`, `embedding_vector`, `instances: List[PageInstance]` |
| **IntentSequence** | 页面内操作序列（V2: 独立节点） | `description`, `embedding_vector`, `intents`, `causes_navigation`, `navigation_target_state_id` |
| **CognitivePhrase** | 完整任务工作流 | `label`, `description`, `embedding_vector`, `execution_plan: List[ExecutionStep]` |
| **Domain** | 网站/应用域名 | `name`, `domain_type` |

### 3.2 关系类型

| 关系 | 方向 | 说明 |
|------|------|------|
| **HAS_SEQUENCE** | State → IntentSequence | 页面包含哪些操作序列 |
| **Action** | State → State | 页面间跳转（边），含 `trigger`, `trigger_sequence_id` |
| **Manage** | Domain → State | 域名管理哪些页面 |

### 3.3 关键数据结构

```python
class IntentSequence:
    id: str
    description: str
    embedding_vector: Optional[List[float]]
    intents: List[Intent]               # 具体操作列表
    causes_navigation: bool = False      # 是否导致页面跳转
    navigation_target_state_id: Optional[str]  # 跳转目标

class CognitivePhrase:
    id: str
    label: str
    description: str
    embedding_vector: Optional[List[float]]
    execution_plan: List[ExecutionStep]  # 结构化执行计划
    access_count: int = 0
    last_accessed: Optional[int]

class ExecutionStep:
    index: int                          # 步骤序号 (1-based)
    state_id: str                       # 当前页面 State ID
    in_page_sequence_ids: List[str]     # 页面内操作（不导致跳转）
    navigation_action_id: Optional[str] # 跳转 Action ID
    navigation_sequence_id: Optional[str]  # 触发跳转的 IntentSequence ID

class Action:
    source: str                         # 源 State ID
    target: str                         # 目标 State ID
    type: str
    trigger: Optional[Dict]             # {ref, text, role} 自包含执行信息
    trigger_sequence_id: Optional[str]  # 可选：关联的 IntentSequence
```

### 3.4 图结构示例

```
(State: PH首页) --[Action: 点击Leaderboard]--> (State: 排行榜)
      |                                              |
      |--[HAS_SEQUENCE]--> (IntentSeq: 滚动浏览)      |--[HAS_SEQUENCE]--> (IntentSeq: 点击产品)
                                                      |
                                      --[Action: 点击产品]--> (State: 产品详情页)
                                                                   |
                                                                   |--[HAS_SEQUENCE]--> (IntentSeq: 滚动)
                                                                   |--[HAS_SEQUENCE]--> (IntentSeq: 点击Team ✨causes_navigation)

(CognitivePhrase: "在PH查看团队信息")
    execution_plan:
      Step 1: state=首页, in_page=[滚动], nav=点击Leaderboard
      Step 2: state=排行榜, in_page=[], nav=点击产品
      Step 3: state=详情页, in_page=[滚动], nav=点击Team
      Step 4: state=团队页, in_page=[], nav=null
```

---

## 4. 查询接口设计

### 4.1 统一查询入口 (V2)

```python
class Memory:
    async def query(
        self,
        target: str,
        *,
        current_state: Optional[str] = None,  # 有 → action 查询
        start_state: Optional[str] = None,     # start+end → navigation
        end_state: Optional[str] = None,
        as_type: Optional[Literal["navigation", "action", "task"]] = None,
        user_id: Optional[str] = None,
        top_k: int = 10
    ) -> QueryResult:
        """
        自动判断：
        1. as_type 指定 → 使用指定类型
        2. start_state + end_state → navigation
        3. current_state → action
        4. 否则 → task
        """
```

### 4.2 三种查询场景

| 场景 | 输入 | 输出 | 实现策略 |
|------|------|------|----------|
| **Task** | 任务描述 | CognitivePhrase 或组合路径 | 先搜 CognitivePhrase（向量），miss 则 TaskDAG 分解 |
| **Navigation** | start + end 描述 | States + Actions 路径 | 向量搜索定位端点 → 图最短路径 |
| **Action** | 目标 + current_state | IntentSequences | 向量搜索（过滤到当前 State 的 HAS_SEQUENCE） |

### 4.3 统一返回类型

```python
class QueryResult:
    query_type: Literal["navigation", "action", "task"]
    success: bool
    states: List[State] = []
    actions: List[Action] = []
    intent_sequences: List[IntentSequence] = []
    cognitive_phrase: Optional[CognitivePhrase] = None
    execution_plan: List[ExecutionStep] = []
    metadata: Dict[str, Any] = {}
```

### 4.4 API Endpoints

| Endpoint | 用途 |
|----------|------|
| `POST /api/v1/memory/add` | 添加 Recording 到图 |
| `POST /api/v1/memory/v2/query` | V2 统一查询（task/navigation/action） |
| `POST /api/v1/memory/query` | 旧版语义查询 |
| `POST /api/v1/reasoner/plan` | Reasoner 查询（含 CognitivePhrase 检查） |
| `GET /api/v1/memory/stats` | 统计信息 |
| `DELETE /api/v1/memory` | 清空 Memory |

---

## 5. Agent 集成

### 5.1 当前实现（两阶段查询）

```
Task → Phase 1: query_task(task) → 判断 memory_level
         │
         ├── L1 (CognitivePhrase 命中) → 直接转 subtasks，无需 LLM
         ├── L2 (部分信息) → LLM 分解 + Memory context 辅助
         └── L3 (无信息) → LLM 正常分解
         │
         ▼
       Phase 2: 每个子任务执行前 query_navigation(page_title, subtask_goal)
         │
         └── 结果作为参考注入 Agent 提示词
```

### 5.2 起点识别

使用当前页面的 `page_title` 做 embedding 查询，Memory 服务端通过向量相似度匹配最近的 State。

### 5.3 查询结果使用策略

| 结果类型 | 置信度 | 使用方式 |
|----------|--------|----------|
| CognitivePhrase 精确匹配 | 高 | 按路径指导执行，但仍需验证每步 |
| 组合路径匹配 | 中 | 作为导航参考 |
| 无匹配 | 无 | Agent 自主探索 |

**核心提示词原则**：有结果时注明"仅供参考，页面可能变化"。无结果时不需要特殊处理。

### 5.4 暂未实现

- **Action 级查询**：Agent Loop 中实时查询当前页面的 IntentSequence（L3），暂不实现
- **Memory Write-Back**：执行轨迹写回 Memory 形成学习闭环，暂不实现

---

## 6. 数据流

### 6.1 写入流程（Recording → Graph）

```
Recording (浏览器操作事件)
  ↓ WorkflowProcessor
按 URL 分段 → 每段创建 State + IntentSequences
  ↓
相邻 State 间创建 Action
  ↓
标记 causes_navigation（IntentSequence 是否导致跳转）
  ↓
生成 CognitivePhrase（包含 execution_plan）
  ↓
批量生成 embeddings
  ↓
存入 Graph (Neo4j / NetworkX)
```

### 6.2 查询流程（Task → Workflow）

```
用户任务描述
  ↓ Reasoner
1. CognitivePhrase 向量搜索 → 命中则返回 execution_plan
  ↓ (miss)
2. TaskDAG 分解 → 每个子任务用 RetrievalTool 搜索
  ↓
3. 组装成 WorkflowResult (states + actions)
  ↓
返回给 Agent → 注入 LLM 提示词
```

---

## 7. 存储与检索

### 7.1 向量索引

| 索引 | 节点类型 | 维度 | 用途 |
|------|----------|------|------|
| `state_embeddings` | State | 1024 | 页面语义搜索 |
| `intent_sequence_embeddings` | IntentSequence | 1024 | 操作语义搜索 |
| `cognitive_phrase_embeddings` | CognitivePhrase | 1024 | 任务工作流匹配 |

### 7.2 Embedding Service

单例服务，支持两种 provider：
- **OpenAI** (默认): 支持自定义 endpoint（如 SiliconFlow）
- **Local BGE**: BAAI/bge-m3，无需 API key

### 7.3 Graph Store

| 后端 | 持久化 | 向量索引 | 适用场景 |
|------|--------|----------|----------|
| **Neo4j** | 是 | 原生支持 | 生产环境 |
| **NetworkX** | 否 | 手动余弦相似度 | 开发测试 |

---

## 8. Desktop Agent 本地 Memory

MemoryManager 三层架构（与 Cloud Memory 独立）：

| 层 | 存储 | 持久化 | 用途 |
|----|------|--------|------|
| L1: Variables | Python dict | 否 | 工作流步骤间数据传递 |
| L2: KV Storage | SQLite | 是 | 脚本缓存、配置、会话状态 |
| L3: Long-term | mem0 + ChromaDB | 是 | 语义搜索（TODO，未启用） |

**关键原则**：Memory 属于用户，不属于 Agent 实例。同一 `user_id` 的多个 Agent 共享 Memory。

---

## 9. 实现状态

### 已完成

- [x] 图数据模型 V2（State, Action, IntentSequence, CognitivePhrase, ExecutionStep）
- [x] GraphStore 抽象 + Neo4j/NetworkX 实现
- [x] WorkflowProcessor（Recording 解析）
- [x] EmbeddingService（OpenAI + BGE）
- [x] Reasoner（CognitivePhrase 检查 + TaskDAG）
- [x] Agent Phase 1: query_task() + memory_level 判断
- [x] Agent Phase 2: query_navigation()（基于 page_title embedding）
- [x] L1 直接转 subtasks / L2 Memory context 辅助 LLM 分解
- [x] 前端 memory_level SSE 事件 + Status Bar 显示

### 待完成

- [ ] V2 数据模型 breaking changes（IntentSequence 独立节点、删除 State.intent_sequences 字段等）
- [ ] Memory.query() 统一智能查询入口（替代多个独立方法）
- [ ] L3 Loop 级实时页面查询
- [ ] Memory Write-Back（执行轨迹写回，学习闭环）
- [ ] 清理旧代码（_call_reasoner, _build_workflow_hints 等）

---

## 10. 关键文件索引

| 文件 | 说明 |
|------|------|
| `src/cloud_backend/memgraph/memory/workflow_memory.py` | 核心 Memory 实现 |
| `src/cloud_backend/memgraph/ontology/` | 数据模型（state, action, intent_sequence, cognitive_phrase, query_result） |
| `src/cloud_backend/memgraph/graphstore/neo4j_graph.py` | Neo4j 存储后端 |
| `src/cloud_backend/memgraph/thinker/workflow_processor.py` | Recording 解析 |
| `src/cloud_backend/memgraph/reasoner/reasoner.py` | 查询推理 |
| `src/cloud_backend/memgraph/services/embedding_service.py` | Embedding 服务 |
| `src/clients/desktop_app/ami_daemon/base_agent/memory/memory_manager.py` | Agent 本地 Memory |
| `src/clients/desktop_app/ami_daemon/base_agent/tools/toolkits/memory_toolkit.py` | Agent Memory 查询工具 |
