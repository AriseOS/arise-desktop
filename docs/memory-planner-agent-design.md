# Memory-Powered Planner Agent Design

## 1. Memory 的目标

Memory 让 Agent 做出更好的计划。"更好"意味着：

- **A. 懂用户需要什么**：从历史工作流中理解用户的偏好和意图
- **B. 知道怎么做事**：已验证的导航路径和页面操作，不需要从零摸索

已有的工作流本身就是用户意图的表达——用户录制了"在 ProductHunt 查看周排行榜"，不只是操作序列，更是在说"我关心 ProductHunt 的周排行榜"。

## 2. Memory 提供什么

Memory 中存储了用户的历史工作流，包含两类信息：

### 偏好（What）
从历史行为中推断用户真正想要什么：
- 用户做过哪些类似的事
- 用户习惯去哪些网站
- 用户关心哪些数据字段
- 用户偏好什么输出格式

### Facts（How）
已验证的做事方法：
- 具体网站的导航路径（State → Action → State）
- 每个页面上可以做什么操作（IntentSequence）
- 哪些路径是验证过可以走通的

**偏好和 Facts 不需要分开存储**，它们自然混合在 CognitivePhrase、State、Page Operations 中。关键是 Planner 怎么用。

特别是 **Page Operations（IntentSequence）同时承载了偏好和 Facts 两层含义**：
- **Facts 层**：操作步骤本身（点击哪个按钮、输入什么、导航到哪里）
- **偏好层**：操作事件透露了用户关心什么
  - 点了 "Weekly" tab → 偏好看周排行
  - 提取了"产品名、投票数、链接" → 偏好这些数据维度
  - 点了 "Export to Excel" → 偏好 Excel 格式
  - 在搜索框输入特定分类关键词 → 偏好某个品类

Planner 看 Page Operations 时，必须同时提取这两层信息。

## 3. Memory 解决什么场景

### 场景 1：拼装
任务可以由多个已有 CognitivePhrase 组合完成。

例：用户说"去 ProductHunt 查周排行榜 top 10，然后发邮件给老板"
- Phrase A 覆盖 "查 ProductHunt 周排行榜"
- Phrase B 覆盖 "发邮件给老板"
- 两个 Phrase 拼装完成任务

也可能是 CognitivePhrase + 图路径混合。部分有 Phrase 覆盖，部分由图搜索补充。

### 场景 2：理解
任务描述模糊，需要从历史行为推断用户真实意图。

例：用户说"帮我看看最近有什么好的 AI 产品"
- Memory 中有过去的 Phrase：查 ProductHunt 周排行榜、搜 Amazon AI 产品
- 从这些历史推断：用户习惯去 ProductHunt、关注 top 10、喜欢 Excel 格式
- 将模糊任务变成具体计划

**大部分真实任务是两个场景的混合**：既需要理解用户意图，又需要拼装已有知识。

## 4. 架构：Memory 层 vs Planner Agent 层

### 分层原则

- **Memory 层**：提供数据和机制，不做决策
- **Planner Agent 层**：决定策略，在 Memory 模块内部

### Memory 层（数据 + 机制）

Memory 只提供原子操作，不包含业务策略：

| 工具 | 接口 | 说明 |
|------|------|------|
| Phrase 召回 | `recall_phrases(query, top_k)` | Embedding 搜索相关 CognitivePhrase，返回完整 Phrase（含 States + IntentSequences + Actions） |
| State 搜索 | `search_states(query, top_k)` | Embedding 搜索相关 State |
| 出边查询 | `get_connected_actions(state_id)` | 获取某个 State 的所有出边（Action） |
| 邻居查询 | `get_neighbors(state_id, direction)` | 获取某个 State 的邻居节点 |
| 页面操作 | `get_page_capabilities(state_id)` | 获取某个 State 上的 IntentSequences + 出边导航 |

### Planner Agent 层（策略）

Planner 是一个 LLM Agent，拿着上述工具，自己决定查什么、查几次、怎么组合。

所有决策逻辑都在 Planner 内部：
- Phrase 能覆盖多少？哪些相关哪些不相关？
- 未覆盖部分怎么补充？要不要搜图？搜多深？
- 最终怎么组合成计划？

### 旧架构 vs 新架构

**旧架构（L1/L2/L3 分层）**：
```
L1 CognitivePhrase 精确匹配
  ↓ 没命中
L2 子图路径规划（固定子图，LLM 在内部规划）
  ↓ 没命中
L3 无 Memory，直接分解
```
降级是机械的，每一级互相不知道对方的结果。

**新架构（Planner Agent）**：
```
Planner Agent 一个入口
  ├── 召回 Phrases → 判断覆盖情况
  ├── 未覆盖部分 → rewrite → 图探索补充
  └── 综合所有信息 → 制定计划
```
降级逻辑收拢到 Planner Agent 内部，由 LLM 智能决策。降级本质不变（Phrase 覆盖不了就用图搜索补充），但 Planner 有完整上下文，知道为什么要降级、降级去找什么。

## 5. Planner Agent 工作流程（职责解耦版）

### 职责边界

PlannerAgent 只负责 **Memory 层** 职责：
- 召回 Phrase、判断覆盖、提取偏好、图探索
- 输出 `<memory_plan>` — 覆盖判断 + 偏好总结 + 未覆盖部分
- **不做** 子任务拆分、agent_type 分配、depends_on 依赖

**Agent 层** 职责由 AMITaskPlanner 完成：
- 接收 memory_plan 文本作为 memory_context
- 结合 worker 能力做最终的原子拆分
- 分配 agent_type 和 depends_on
- 将 coverage 中的 workflow_guide 分配给匹配的 browser 子任务

### 输入
- 用户的任务描述

### 输出
`<memory_plan>` XML，包含：
- **coverage**：哪些部分被 Memory 覆盖（含 evidence：phrase_id/state_ids、覆盖哪几步）
- **uncovered**：哪些部分 Memory 中无记录
- **preferences**：从历史行为推断的用户偏好列表

### 输出格式

```xml
<memory_plan>
  <coverage>
    <covered source="phrase" phrase_id="xxx" steps="1-3">
      去 ProductHunt 查看周排行榜，用户偏好 top 10、Excel 格式
    </covered>
    <covered source="graph" state_ids="s1,s2">
      发邮件给老板
    </covered>
  </coverage>
  <uncovered>整理成报告（Memory 中无相关记录）</uncovered>
  <preferences>
    - 用户习惯去 ProductHunt 看排行榜
    - 偏好周排行（不是日/月）
    - 关注的数据字段：产品名、投票数、链接
  </preferences>
</memory_plan>
```

### 流程

```
用户任务："帮我看看最近好的 AI 产品，整理成报告发给老板"
  │
  ▼
Step 1: Phrase 召回
  recall_phrases(query) → 召回完整 Phrase
  → Phrase A: ProductHunt 查周排行榜（Step 1-4，含每个 State 的 IntentSequences）
  → Phrase B: 发邮件给老板（Step 1-3）
  → Phrase C: Amazon 搜索商品（Step 1-5）
  │
  ▼
Step 2: 覆盖判断 + 偏好提取
  看完整 Phrase 内容（包括 IntentSequence），理解偏好 + facts
  → Phrase A 覆盖 "看最近好的 AI 产品" ✓ → 偏好: top 10、Excel
  → Phrase B 覆盖 "发给老板" ✓
  → Phrase C 不相关 ✗
  → "整理成报告" 未覆盖 → rewrite query
  │
  ▼
Step 3: 图探索（未覆盖部分）
  rewrite query → search_states("整理数据生成报告")
  → 找到候选 States
  → Planner 选择起点，调用 get_connected_actions() 查出边
  → 判断够不够，不够则调用 get_neighbors() 探索下一度
  → 逐步扩展，直到找到满意的路径（或确认无路径）
  │
  ▼
Step 4: 输出 <memory_plan>
  → coverage: Phrase A 覆盖 step 1-4, Phrase B 覆盖 step 1-3
  → uncovered: "整理成报告"
  → preferences: top 10, Excel, ProductHunt, 周排行
  │
  ▼
代码层：解析 <memory_plan> + 从 tool result 提取 workflow_guide
  → 返回 MemoryPlan(coverage_items, uncovered, preferences)
```

### 数据流（端到端）

```
AMITaskPlanner.decompose_and_query_memory(task)
  → MemoryToolkit.plan_task(task)
    → POST /api/v1/memory/plan
      → PlannerAgent.plan(task)
        → Agent Loop: recall → coverage → explore → output <memory_plan>
        → 代码解析 + workflow_guide 提取
        → 返回 MemoryPlan
  → 格式化 memory_plan 为 memory_context 文本
  → _fine_grained_decompose(task, memory_context) → List[AMISubtask]
  → 将 coverage 的 workflow_guide 分配给匹配的 browser 子任务
  → 返回 List[AMISubtask]
```

### 图探索 vs 旧 L2

| | 旧 L2 | 新设计（Planner 图探索） |
|---|-------|----------------------|
| 子图构建 | 一次性固定大小（max_states=20） | 按需逐步扩展 |
| 探索深度 | 写死的一度邻居 | Planner 自己决定探几度 |
| 决策者 | 嵌套的 LLM 调用（独立于 Planner） | Planner 自己，有完整上下文 |
| 失败处理 | 固定重试（给反馈 → 重规划） | Planner 可以换起点、换策略 |

## 6. Memory 在两个阶段的使用

| 阶段 | Memory 提供的 | 目的 |
|------|-------------|------|
| Planner 阶段 | CognitivePhrase（完整）+ Page Operations | 理解偏好 + 制定可落地的计划 |
| Runtime 阶段 | Page Operations（按 URL 查询） | 计划外页面的操作提示 + 偏好补充 |

Page Operations 两个阶段都给：
- **Planner 阶段**：了解用户在这个页面上关心什么、习惯怎么操作
- **Runtime 阶段**：执行时可能走到计划外的页面，提供操作方法提示

## 7. 和现有设计的关键区别

| | 现有设计 | 新设计 |
|---|---------|-------|
| 整体架构 | Reasoner 编排 L1→L2→L3 | Planner Agent 统一决策 |
| Planner 形式 | 固定函数调用流程 | LLM Agent，工具驱动 |
| 降级逻辑 | 机械的逐级降级 | 智能降级，Planner 自己决定 |
| Phrase 匹配 | 精确回放语义（几乎命中不了） | Embedding 召回相关 Phrase 作为参考 |
| Phrase 使用方式 | 整个 Phrase 塞给每个子任务 | Phrase 的具体 Steps 对应到子任务 |
| 多 Phrase 组合 | 不支持 | 多个 Phrase 拼装覆盖任务 |
| 未覆盖部分 | 直接降级到固定子图 L2 | Rewrite query + 按需图探索 |
| 图探索 | 一次性固定子图 | 动态按需探索，Planner 决定深度 |
| Page Operations | 只在 Runtime 给 | Planner + Runtime 都给 |
| Memory 层职责 | 混合数据+策略（Reasoner） | 纯数据+机制，不做决策 |

## 8. 实现方案（已实现）

> **Status**: Phase 1-4 已全部实现。旧 Reasoner 路径保留为 fallback。

### 8.1 Memory 层接口

5 个工具全部基于现有 Memory 接口实现，唯一新增的是 `recall_phrases` 的 enrichment 逻辑（查到 Phrase 后自动展开 States + IntentSequences + Actions）。

| Planner 工具 | 底层 Memory 接口 |
|---|---|
| `recall_phrases(query, top_k)` | `phrase_manager.search_phrases_by_embedding()` + enrichment |
| `search_states(query, top_k)` | `state_manager.search_states_by_embedding()` |
| `get_connected_actions(state_id)` | `action_manager.list_outgoing_actions()` |
| `get_neighbors(state_id, direction)` | `state_manager.get_k_hop_neighbors()` |
| `get_page_capabilities(state_id)` | `memory.get_page_capabilities()` |

所有工具同时搜索 private 和 public memory（如可用），结果去重合并。

### 8.2 Planner Agent 架构

```
src/common/memory/planner/
  ├── __init__.py               # 延迟导入 PlannerAgent 避免循环依赖
  ├── planner_agent.py          # PlannerAgent 主类（基于 AMIAgent Agent Loop）
  ├── tools.py                  # PlannerTools 类，5 个工具作为 bound methods
  ├── prompts.py                # PLANNER_SYSTEM_PROMPT
  └── models.py                 # EnrichedPhrase, CoverageItem, MemoryPlan, PlanResult
```

**数据模型（`models.py`）：**

```python
@dataclass
class EnrichedPhrase:
    """CognitivePhrase with fully resolved States, Actions, IntentSequences."""
    phrase: CognitivePhrase
    states: List[State]
    actions: List[Action]
    state_sequences: Dict[str, List[IntentSequence]]  # state_id → sequences

@dataclass
class CoverageItem:
    """A task part covered by Memory."""
    source: str          # "phrase" | "graph"
    summary: str         # Description of what this covers
    phrase_id: Optional[str] = None
    state_ids: List[str] = field(default_factory=list)
    steps: str = ""      # Step range, e.g. "1-3"
    workflow_guide: str = ""  # Extracted from tool results by code, NOT LLM-generated

@dataclass
class MemoryPlan:
    """Parsed <memory_plan> output from PlannerAgent."""
    coverage_items: List[CoverageItem]
    uncovered: str = ""
    preferences: List[str] = field(default_factory=list)

@dataclass
class PlanResult:
    """Complete output of PlannerAgent. Serializable for HTTP transport."""
    memory_plan: MemoryPlan = field(default_factory=MemoryPlan)
```

**关键设计决策**：`workflow_guide` 不由 LLM 生成，而是由代码从 Agent Loop 的 tool result 历史中提取。LLM 只负责判断覆盖关系（输出 `<covered phrase_id="xxx" steps="1-3">`），代码根据 phrase_id + steps 去 tool result 中找到对应的 EnrichedPhrase 数据并格式化为 guide 文本。这避免了 LLM hallucination。

**PlannerAgent（`planner_agent.py`）核心流程：**

```python
class PlannerAgent:
    def __init__(self, memory, llm_provider, embedding_service, task_state=None, public_memory=None):
        self._tools_impl = PlannerTools(memory, embedding_service, public_memory)
        tools = [
            AMITool(self._tools_impl.recall_phrases),
            AMITool(self._tools_impl.search_states),
            AMITool(self._tools_impl.get_connected_actions),
            AMITool(self._tools_impl.get_neighbors),
            AMITool(self._tools_impl.get_page_capabilities),
        ]
        self._agent = AMIAgent(
            task_state=task_state,
            agent_name="PlannerAgent",
            provider=llm_provider,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            tools=tools,
            max_iterations=15,
        )

    async def plan(self, task: str) -> PlanResult:
        self._agent.reset()
        response = await self._agent.astep(task)
        return self._parse_plan_output(response.text)
```

**解析流程**（`_parse_plan_output`）：
1. 用正则提取 `<memory_plan>` XML
2. 解析 `<coverage>` → `List[CoverageItem]`（含 source、phrase_id、steps 等属性）
3. 解析 `<uncovered>` → 字符串
4. 解析 `<preferences>` → `List[str]`
5. 调用 `_fill_workflow_guides()` — 遍历 Agent 对话历史中的 tool_result，按 phrase_id 找到 EnrichedPhrase JSON，按 steps 范围提取并格式化为 workflow_guide 文本
6. 返回 `PlanResult(memory_plan=...)`

**workflow_guide 构建策略**：
- **source="phrase"**：从 `recall_phrases` tool result 中找到对应 phrase_id 的 EnrichedPhrase，按 steps 范围提取每个 Step 的 URL、页面操作（IntentSequence）、导航动作
- **source="graph"**：从 `search_states`/`get_connected_actions`/`get_page_capabilities` tool result 中按 state_ids 查找，格式化为导航路径

### 8.3 System Prompt 设计

Prompt 的核心理念是 **"选择最佳参考，而非列举所有匹配"**：

```
You are a Memory Planner. Your goal is to find the best execution reference
from the user's workflow memory for their current task.

## Your Role
- SELECT the best matching memory for each part of the task — not list every match
- Extract user preferences from historical operations
- Do NOT decompose tasks into subtasks
```

**关键设计原则**：

1. **Embedding 搜索的局限性说明**：Prompt 明确告诉 LLM "tools always return results, even when nothing relevant exists"，避免 LLM 对不相关结果做过度解读
2. **"同域名同流程"泛化**：同一网站 + 相同操作模式 = 有效参考（如 "AI rings" phrase 可用于 "glasses" 搜索——同站、同流程、不同关键词）
3. **偏好提取**：从 IntentSequence 操作中推断用户偏好（点了 "Weekly" tab → 偏好周排行）
4. **快速收敛**：大多数情况下 1 次 recall_phrases 即可输出 `<memory_plan>`，只有部分匹配时才进一步探索图

### 8.4 与现有系统的集成

**调用链（已实现）：**

```
OrchestratorAgent → AMITaskPlanner.decompose_and_query_memory()
  ├── Try PlannerAgent path (if MemoryToolkit available):
  │     → MemoryToolkit.plan_task() → HTTP POST /api/v1/memory/plan
  │       → Cloud Backend → MemoryService.plan() → PlannerAgent.plan()
  │         → Agent Loop: recall → coverage → explore → output <memory_plan>
  │         → Code: parse XML + extract workflow_guide from tool results
  │       → Return PlanResult(memory_plan)
  │     → Format memory_plan as memory_context text
  │     → _fine_grained_decompose(task, memory_context) → List[AMISubtask]
  │     → Assign workflow_guide from coverage to browser subtasks
  │
  └── Fallback to old Reasoner path (if PlannerAgent fails or unavailable):
        → _query_task_memory() → MemoryToolkit.query_task() → Reasoner
        → _format_memory_for_decompose() → LLM decompose
        → _assign_memory_to_subtasks() → whole injection
```

**AMITaskPlanner 的 4 步 PlannerAgent 流程**（`_plan_with_planner_agent`）：

1. **Get MemoryPlan**：调用 `MemoryToolkit.plan_task()` 获取 `PlanResult`
2. **Format as context**：`_format_memory_plan_for_decompose()` — 将 coverage（含 workflow_guide 全文）+ preferences + uncovered 格式化为 LLM 可读的 memory_context
3. **Decompose**：`_fine_grained_decompose(task, memory_context)` — 复用现有 LLM 分解，memory_context 作为参考
4. **Assign guides**：`_assign_coverage_guides()` — 将所有 coverage 的 workflow_guide 合并，整体注入到所有 browser 类型子任务（whole injection 策略，与旧路径一致）

**workflow_guide 分配策略**：

当前采用 **whole injection**：所有 coverage items 的 workflow_guide 合并后注入到所有 browser 子任务。原因是动态的 page operations 层（Runtime Layer 2）会在执行时提供更精细的 per-page guidance。Planner 阶段的 guide 主要提供整体导航路径参考。

**Executor 无需改动**：AMISubtask 结构不变，workflow_guide 仍通过 `AMITaskExecutor._build_prompt()` 注入。

### 8.5 Client-Side 镜像模型

**文件**：`memory_toolkit.py` 底部

MemoryToolkit 中定义了 client-side 的镜像数据模型（`CoverageItemData`, `MemoryPlanData`, `MemoryPlanResult`），用于反序列化 HTTP 响应。这些模型是 `src/common/memory/planner/models.py` 中服务端模型的简化版本，通过 `from_dict()` 从 JSON 构造。

### 8.6 实现状态

| Phase | 内容 | 状态 |
|-------|------|------|
| Phase 1 | Memory 模块新增 `planner/` | ✅ 已完成 |
| Phase 2 | `MemoryService.plan()` | ✅ 已完成 |
| Phase 3 | Cloud Backend `/api/v1/memory/plan` | ✅ 已完成 |
| Phase 4 | Client 侧 `MemoryToolkit.plan_task()` + `AMITaskPlanner` 改造 | ✅ 已完成 |
| Phase 5 | 清理旧 Reasoner 路径 | ⏳ 待定（旧路径保留为 fallback） |

## 9. 详细架构改造方案（已实现）

### 9.1 改造概览

改造涉及两大部分：

1. **Memory 模块内部改造**：新增 `planner/` 子模块
2. **Agent 侧改造**：AMITaskPlanner 优先使用 PlannerAgent、Cloud Backend 新增 API、MemoryToolkit 新增方法

```
改造后的调用链（PlannerAgent path）：
  QuickTaskService
    → 创建 MemoryToolkit(HTTP)
    → 创建 AMITaskPlanner(memory_toolkit)
    → AMITaskPlanner.decompose_and_query_memory()
        → _plan_with_planner_agent(task)
            → MemoryToolkit.plan_task() → HTTP POST /api/v1/memory/plan
                → Cloud Backend → MemoryService.plan() → PlannerAgent.plan()
                    → Agent Loop: recall_phrases → 覆盖判断 → 图探索 → <memory_plan>
                    → Code: parse XML + fill workflow_guide from tool results
                → 返回 PlanResult(memory_plan)
            → _format_memory_plan_for_decompose(memory_plan) → memory_context text
            → _fine_grained_decompose(task, memory_context) → List[AMISubtask]
            → _assign_coverage_guides(subtasks, memory_plan) → workflow_guide 注入

Fallback 调用链（旧 Reasoner path，PlannerAgent 失败时自动触发）：
  → _decompose_with_old_path(task)
      → _query_task_memory() → MemoryToolkit.query_task() → Reasoner
      → _format_memory_for_decompose() → LLM 分解
      → _assign_memory_to_subtasks() → 整体注入 workflow_guide
```

**关键决策：PlannerAgent 运行在 Cloud Backend 侧。**

原因：
- PlannerAgent 需要直接访问 Memory（Graph Store），不走 HTTP 逐个查询
- 5 个工具的每次调用都是对 Memory 的直接读取，如果走 HTTP 会产生 N 次网络往返
- Cloud Backend 已有 MemoryService + Graph Store 实例，PlannerAgent 直接复用
- Client 只需一次 HTTP 调用（plan_task），等待 PlanResult 返回

### 9.2 Memory 模块内部改造

#### 9.2.1 `src/common/memory/planner/` 模块

在 `src/common/memory/` 下新增 `planner/` 目录，与 `reasoner/` 平级：

```
src/common/memory/
  ├── memory/          # 数据层（不变）
  ├── ontology/        # 数据模型（不变）
  ├── services/        # AI/ML 服务（不变）
  ├── graphstore/      # 图存储（不变）
  ├── thinker/         # 工作流处理（不变）
  ├── reasoner/        # Reasoner（保留为 fallback）
  └── planner/         # PlannerAgent
      ├── __init__.py          # 延迟导入 PlannerAgent（避免循环依赖）
      ├── models.py            # EnrichedPhrase, CoverageItem, MemoryPlan, PlanResult
      ├── tools.py             # PlannerTools 类（5 个 Memory 工具）
      ├── prompts.py           # PLANNER_SYSTEM_PROMPT
      └── planner_agent.py     # PlannerAgent 主类
```

**planner 模块依赖关系：**
- `planner/` 依赖 `memory/`（Memory 接口）、`ontology/`（数据模型）、`services/`（EmbeddingService）
- `planner/` 不依赖 `reasoner/`（完全独立）
- `planner/` 依赖 AMIAgent（来自 `ami_daemon/base_agent/core/`）用于 Agent Loop

**AMIAgent 依赖：**

PlannerAgent 位于 `src/common/memory/`（共享模块），AMIAgent 位于 `src/clients/desktop_app/ami_daemon/base_agent/core/`（客户端模块）。虽然是跨层依赖，但 **PlannerAgent 直接复用 AMIAgent**，不自己实现 Agent Loop。PlannerAgent 运行在 Cloud Backend 侧，Cloud Backend 本身就依赖了 ami_daemon 的 Agent 代码。

#### 9.2.2 Reasoner 保留为 Fallback

Reasoner 保持现状，不删除也不修改任何代码。PlannerAgent 是一条独立的新路径，与 Reasoner 并行存在。

- `/api/v1/memory/query`（走 Reasoner）继续可用
- `/api/v1/memory/plan`（走 PlannerAgent）新增
- AMITaskPlanner 优先走 PlannerAgent，失败时自动 fallback 到旧 Reasoner 路径

#### 9.2.3 MemoryService 新增 `plan()` 方法

`query()` 方法保留不变。新增 `plan()` 方法，创建 PlannerAgent 并调用：

```python
class MemoryService:
    async def plan(
        self,
        task: str,
        llm_provider,
        embedding_service,
        task_state=None,
        public_memory_service: Optional["MemoryService"] = None,
    ) -> PlanResult:
        from src.common.memory.planner.planner_agent import PlannerAgent

        public_wm = None
        if public_memory_service:
            try:
                public_wm = public_memory_service.workflow_memory
            except RuntimeError:
                pass

        agent = PlannerAgent(
            memory=self._workflow_memory,
            llm_provider=llm_provider,
            embedding_service=embedding_service,
            task_state=task_state,
            public_memory=public_wm,
        )
        return await agent.plan(task)
```

### 9.3 Agent 侧改造

#### 9.3.1 Cloud Backend `/api/v1/memory/plan` 端点

**文件**：`src/cloud_backend/main.py`

```python
@app.post("/api/v1/memory/plan")
async def plan_with_memory(data: dict, x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")):
    """Memory-Powered Task Analysis via PlannerAgent.

    Request: {"user_id": "...", "task": "..."}
    Headers: X-Ami-API-Key (required)

    Returns:
    {
        "success": true,
        "memory_plan": {
            "coverage_items": [
                {"source": "phrase", "summary": "...", "phrase_id": "xxx",
                 "steps": "1-3", "workflow_guide": "..."}
            ],
            "uncovered": "...",
            "preferences": ["pref1", "pref2"]
        }
    }
    """
```

使用 cached provider（`get_cached_anthropic_provider` + `get_cached_embedding_service`），timeout 设为 300 秒以支持多轮 Agent Loop。

**与现有端点的关系：**
- `/api/v1/memory/query`：保留，仍处理 action/navigation/task 查询
- `/api/v1/memory/plan`：新增，task 级别的 Memory 分析
- 两个端点并行存在

#### 9.3.2 MemoryToolkit 新增 `plan_task()` 方法

**文件**：`memory_toolkit.py`

```python
async def plan_task(self, task: str) -> MemoryPlanResult:
    """Call PlannerAgent via Cloud Backend."""
    url = f"{self._memory_api_base_url}/api/v1/memory/plan"
    payload = {"user_id": self._user_id, "task": task}
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(url, json=payload, headers={"X-Ami-API-Key": self._ami_api_key})
    # ... error handling ...
    return MemoryPlanResult.from_dict(response.json())
```

**现有方法的保留情况：**

| MemoryToolkit 方法 | 状态 |
|---|---|
| `plan_task()` | **新增**，调用 `/api/v1/memory/plan` |
| `query_task()` | **保留**（旧路径 fallback 使用） |
| `query_navigation()` | **保留**（Runtime 阶段用） |
| `query_actions()` | **保留**（Runtime 阶段用） |
| `query_page_operations()` | **保留**（Runtime 阶段 LLM 工具） |
| `format_*()` 系列 | **保留**（旧路径 fallback 使用） |
| `get_tools()` | **保留**（返回 `query_page_operations` 工具给 Runtime Agent） |

#### 9.3.3 AMITaskPlanner 改造

**文件**：`ami_task_planner.py`

**核心改变**：`decompose_and_query_memory()` 优先走 PlannerAgent path，失败时 fallback 到旧 Reasoner path。

```python
async def decompose_and_query_memory(self, task: str) -> List[AMISubtask]:
    # Try PlannerAgent path first
    if self._memory_toolkit and self._memory_toolkit.is_available():
        try:
            subtasks = await self._plan_with_planner_agent(task)
            return subtasks
        except Exception as e:
            logger.warning(f"PlannerAgent failed, falling back to old path: {e}")

    # Fallback: old Reasoner-based path
    return await self._decompose_with_old_path(task)
```

**新增方法：**
- `_plan_with_planner_agent(task)` — PlannerAgent 4 步流程
- `_format_memory_plan_for_decompose(memory_plan)` — 将 MemoryPlan 格式化为 LLM 可读的 context
- `_assign_coverage_guides(subtasks, memory_plan)` — workflow_guide 分配（whole injection）
- `_build_planner_agent_report(memory_plan)` — 构建人类可读的 Memory 报告（用于 SSE 展示）
- `_decompose_with_old_path(task)` — 旧 Reasoner 路径（原 `decompose_and_query_memory` 的逻辑重构）
- `_emit_decompose_result(subtasks)` — 提取公共的 SSE 事件发送逻辑

**保留的方法（旧路径 fallback 使用）：**
- `_query_task_memory()` — 调用 Reasoner
- `_format_memory_for_decompose()` — 格式化 Reasoner 结果
- `_fine_grained_decompose()` — LLM 分解（两条路径共用）
- `_assign_memory_to_subtasks()` — 旧路径的 guide 注入

#### 9.3.4 QuickTaskService / OrchestratorAgent

**无需改造**。QuickTaskService 只负责创建 MemoryToolkit 并传给 AMITaskPlanner，接口不变。AMITaskPlanner 内部的路径选择对调用方透明。

### 9.4 不需要改动的部分

| 组件 | 为什么不变 |
|------|-----------|
| **AMITaskExecutor** | 仍然接收 `List[AMISubtask]`，通过 `workflow_guide` 注入 prompt，接口不变 |
| **AMIBrowserAgent Runtime** | 仍然通过 `_enrich_message()` 按 URL 查询 Page Operations（Runtime Layer 2） |
| **Reasoner action/navigation 查询** | Runtime 阶段仍需要，通过 `/api/v1/memory/query` 保持可用 |
| **MemoryToolkit 的 Runtime 工具** | `query_page_operations()` 作为 LLM 工具在 Runtime 阶段使用，不变 |
| **WorkflowMemory** | 数据层不变，被 PlannerAgent 通过 PlannerTools 访问 |
| **ontology 数据模型** | State, Action, IntentSequence 等不变 |
| **thinker 工作流处理** | 录制处理流程不变 |
| **graphstore** | 图存储不变 |

### 9.5 数据流对比

**旧数据流（Reasoner path，现为 fallback）：**
```
AMITaskPlanner
  → MemoryToolkit.query_task(task)           # 1 次 HTTP
    → POST /api/v1/memory/query
      → Reasoner._query_task()
        → L1: CognitivePhrase 精确匹配
        → L2: Embedding search → 固定子图 → LLM 路径规划
        → L3: 无 Memory 降级
      → 返回 QueryResult(states, actions, cognitive_phrase, metadata)
  → _format_memory_for_decompose(result)     # 客户端格式化
  → _fine_grained_decompose(task, context)   # 客户端 LLM 分解
  → _assign_memory_to_subtasks(subtasks)     # 整体注入 workflow_guide
  → List[AMISubtask]
```

**新数据流（PlannerAgent path，优先使用）：**
```
AMITaskPlanner._plan_with_planner_agent(task)
  → MemoryToolkit.plan_task(task)                      # 1 次 HTTP
    → POST /api/v1/memory/plan
      → MemoryService.plan() → PlannerAgent.plan(task)
        → Agent Loop (max 15 iterations):
          → recall_phrases(query)                      # 直接访问 Memory
          → LLM 判断覆盖 + 提取偏好                    # LLM 思考
          → search_states / get_neighbors（按需）       # 图探索
          → 输出 <memory_plan> XML                     # LLM 最终输出
        → Code: parse XML + fill workflow_guide        # 从 tool results 提取
      → 返回 PlanResult(memory_plan)
  → _format_memory_plan_for_decompose(memory_plan)     # 格式化为 context
  → _fine_grained_decompose(task, memory_context)      # 客户端 LLM 分解（复用）
  → _assign_coverage_guides(subtasks, memory_plan)     # whole injection
  → List[AMISubtask]
```

**关键差异：**
- 旧流程：Memory 查询是固定 L1→L2→L3 降级，客户端 2 次 LLM 调用
- 新流程：Memory 查询是 LLM Agent 动态决策，服务端 N 次 LLM + 客户端 1 次 LLM 分解
- 旧流程：workflow_guide 从 Reasoner 结果整体格式化
- 新流程：workflow_guide 由代码从 PlannerAgent tool results 中精确提取（避免 LLM hallucination）
- 新流程保留 fallback：PlannerAgent 异常时自动降级到旧 Reasoner 路径
