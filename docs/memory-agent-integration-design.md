# Memory-Agent Integration Design Document (V2)

> **Last Updated**: 2025-01-29
> **Status**: V2 简化方案 - 两阶段查询

## 1. Executive Summary

本文档描述如何增强 Agent 与 Memory 系统的集成，使 Agent 能够更有效地利用用户的历史工作流记忆，提升任务执行效率和成功率。

### V2 简化方案概述

**核心变更**：从三层查询简化为两层查询

| 阶段 | 查询方法 | 时机 | 输入 | 用途 |
|------|---------|------|------|------|
| Phase 1 | `query_task(task)` | 任务开始时 | 完整任务描述 | 获取整体工作流指导 |
| Phase 2 | `query_navigation(start, end)` | 每个子任务开始时 | page_title → 子任务目标 | 获取导航路径参考 |
| ~~Phase 3~~ | ~~`query_actions(state)`~~ | ~~暂不实现~~ | - | - |

**关键设计决策**：
1. **起点识别**：使用 `page_title` 做 embedding 查询（Memory 服务端处理）
2. **查询频率**：每个子任务开始时都查询 Navigation，不缓存
3. **结果定位**：Memory 结果是**参考**，不是剧本，页面可能变化
4. **暂不实现**：Action 级查询（IntentSequence）和学习闭环（Write-Back）

### V2 实施任务

| 任务 | 状态 | 说明 |
|------|------|------|
| Phase 1: Task Query | ✅ 已有 | `query_task()` 已实现 |
| Phase 2: Navigation Query | 🔲 待做 | 每个子任务开始时调用 `query_navigation(page_title, subtask_goal)` |
| 提示词简化 | 🔲 待做 | 有结果时说明是参考，无结果时不需要特殊处理 |
| 修复 embedding_service 问题 | ✅ 已修复 | `_resolve_state_id` 现在可以正常工作 |

### 核心理解：Memory 是「认知地图」而非「执行剧本」

**关键概念澄清**：

```
Memory 存储的 State 是「抽象页面类型」，不是「具体操作实例」

例如：
  State: "Product Hunt 产品详情页" (一类页面)
    └── intent_sequences: ["点击 Team 查看团队", "点击 Upvote 点赞", ...]

这意味着：
  ✅ Memory 告诉 Agent "在产品详情页，你可以做这些操作"
  ❌ Memory 不是说 "你必须依次执行这些操作"

即使有 CognitivePhrase 完整路径：
  ✅ 路径是指导: "通常走 首页 → 分类页 → 详情页"
  ❌ 不是剧本: Agent 仍需决策选择哪个产品、执行哪些操作
```

**Memory 提供三种能力**：

| 能力 | 说明 | 示例 |
|------|------|------|
| **地图 (Navigation Map)** | 网站的拓扑结构 | "首页 → 分类页 → 详情页" |
| **菜单 (Available Operations)** | 每个页面上可以做什么 | "详情页可以: 看Team, 看评论, 点赞" |
| **经验 (Past Patterns)** | 过去类似任务的参考路径 | "查看团队通常是: 进详情 → 点Team" |

**Agent 仍需自主决策**：
- 在榜单页选择**哪个**产品（基于用户任务）
- 在详情页执行**哪些**操作（基于用户意图）
- Memory 是辅助参考，不是替代决策

### 核心目标
- **形成学习闭环**: 执行 → 记忆 → 复用 → 执行
- **减少盲目探索**: 利用 Memory 的"地图"和"菜单"指导 Agent
- **提升决策质量**: 基于真实页面结构而非 LLM 猜测

---

## 2. Current State Analysis (现状分析)

### 2.1 当前架构问题

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CURRENT FLOW (存在问题)                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  User Task: "在 Product Hunt 查找 AI 产品并查看团队"                     │
│                                                                         │
│  Step 1: execute() 可能调用 Reasoner (可选，不强制)                      │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ if use_reasoner:                                                │   │
│  │     reasoner_result = await self._call_reasoner(task)           │   │
│  │                                                                 │   │
│  │ ⚠️ 问题: use_reasoner 是可选的，可能被跳过                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                          │                                              │
│                          ▼                                              │
│  Step 2: _build_workflow_hints() 转换为文本 hints                       │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ workflow_hints = [{"description": "...", "url": "...", ...}]    │   │
│  │                                                                 │   │
│  │ ⚠️ 问题: 结构化路径被扁平化为文本提示                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                          │                                              │
│                          ▼                                              │
│  Step 3: _run_agent_loop() 中 LLM 重新分解任务                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ subtasks = await self._task_orchestrator._decompose_task(task)  │   │
│  │                                                                 │   │
│  │ ❌ 问题: 完全不使用 Reasoner 返回的路径!                        │   │
│  │ ❌ LLM 重新猜测分解，忽略已有的 states/actions                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                          │                                              │
│                          ▼                                              │
│  Step 4: Agent Loop 执行                                                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ workflow_hints 只是作为"参考"写入 notes                         │   │
│  │ LLM 可能参考，也可能不参考                                      │   │
│  │                                                                 │   │
│  │ ⚠️ 问题: Memory 的价值大打折扣                                  │   │
│  │ ⚠️ 问题: 每个 Loop 不查询当前页面的 Memory                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                          │                                              │
│                          ▼                                              │
│  Step 5: 任务完成                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ ❌ 问题: 执行轨迹没有写回 Memory                                │   │
│  │ ❌ 无法形成学习闭环                                             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心问题总结

| # | 问题 | 影响 |
|---|------|------|
| 1 | Reasoner 调用是可选的 | Memory 可能完全不被使用 |
| 2 | 有路径时仍然 LLM 分解 | 浪费 CognitivePhrase 的完整路径 |
| 3 | Subtask 不单独查 Memory | 错过细粒度路径匹配机会 |
| 4 | Loop 不查当前页面 Memory | 错过页面级操作辅助 |
| 5 | 执行结果不写回 Memory | 无法学习新工作流 |

---

## 3. Memory System Capabilities (Memory 能力回顾)

### 3.1 Memory 两层存储结构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Memory Two-Layer Architecture                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Layer 1: CognitivePhrase (快速路径 - 完整工作流)                        │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ CognitivePhrase:                                                   │ │
│  │   id: "phrase_xxx"                                                 │ │
│  │   description: "在 Product Hunt 查找 AI 产品并查看团队信息"         │ │
│  │   state_path: [state_1, state_2, state_3]   ← 完整路径             │ │
│  │   action_path: [ClickLink, ClickTab]        ← 转移动作             │ │
│  │   embedding_vector: [...]                   ← 语义匹配             │ │
│  │   access_count: 5                           ← 热门度               │ │
│  │                                                                    │ │
│  │ 💡 这是"路径指导"，不是"执行剧本"                                  │ │
│  │    Agent 参考路径，但仍需决策具体选择                              │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  Layer 2: State + Action Graph (细粒度 - 页面操作)                       │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ State (抽象页面类型):                                              │ │
│  │   id: "state_xxx"                                                  │ │
│  │   description: "Product Hunt 产品详情页"                           │ │
│  │   page_url: "https://producthunt.com/posts/..."                    │ │
│  │   intent_sequences: [                        ← 操作菜单            │ │
│  │     IntentSequence(                                                │ │
│  │       description: "点击 Team 标签查看团队",                        │ │
│  │       intents: [                                                   │ │
│  │         Intent(type: "Click", css_selector: "button[data-tab=team]")│ │
│  │       ]                                                            │ │
│  │     )                                                              │ │
│  │   ]                                                                │ │
│  │                                                                    │ │
│  │ Action (状态转移):                                                 │ │
│  │   source: "state_1"                          ← 从哪来              │ │
│  │   target: "state_2"                          ← 到哪去              │ │
│  │   type: "ClickLink"                                                │ │
│  │   description: "点击产品链接进入详情页"                            │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Memory API Endpoints

| Endpoint | Method | 用途 | 返回内容 |
|----------|--------|------|----------|
| `/api/v1/reasoner/plan` | POST | 查询工作流路径 | states, actions, method |
| `/api/v1/memory/query` | POST | 语义查询 State | paths (含 State + IntentSequence) |
| `/api/v1/memory/add` | POST | 写入记忆 | states_added, sequences_added |
| `/api/v1/memory/stats` | GET | 统计信息 | domains, total_states |

> **Note**: L3 级别查询当前页面信息时，使用 `/api/v1/memory/query` 进行 embedding 语义查询，而不是简单的 URL 匹配。因为 State 是抽象页面类型，需要通过语义相似度找到当前页面对应的 State。

### 3.3 Reasoner 检索流程

```python
async def plan(target: str) -> WorkflowResult:
    # 1. 快速路径: 检查 CognitivePhrase
    can_satisfy, phrases, reasoning = await phrase_checker.check(target)

    if can_satisfy:
        # CognitivePhrase 命中! 返回完整路径作为指导
        return WorkflowResult(
            states=[memory.get_state(id) for id in phrase.state_path],
            actions=[memory.get_action(s, t) for s, t in pairs],
            metadata={"method": "cognitive_phrase_match"}
        )

    # 2. 慢速路径: TaskDAG + 图检索
    dag = await decompose_target(target)
    for task in dag:
        result = await retrieval_tool.execute(task.target)
        # embedding 搜索 + LLM 评估 + 邻居遍历

    return WorkflowResult(
        states=all_states,
        actions=all_actions,
        metadata={"method": "task_dag"}
    )
```

---

## 4. V2 Proposed Design (简化设计方案)

### 4.1 设计原则

**核心原则**：Memory 是「认知地图」，不是「执行剧本」

**V2 简化策略**：两阶段查询，专注于导航指导

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    V2 Memory 辅助策略 - 两阶段查询                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Phase 1: 任务开始 - Task Query                                         │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │ 时机: execute() 入口，任务开始前                                   ││
│  │ 方法: MemoryToolkit.query_task(task_description)                   ││
│  │                                                                    ││
│  │ 输入: 完整任务描述                                                 ││
│  │       "在 Product Hunt 查找 AI 产品并查看团队信息"                 ││
│  │                                                                    ││
│  │ 输出: QueryResult                                                  ││
│  │       - cognitive_phrase: 完整工作流 (如果有精确匹配)              ││
│  │       - states + actions: 组合路径 (如果有部分匹配)                ││
│  │       - None: 无匹配                                               ││
│  │                                                                    ││
│  │ 用途: 存入 workflow_guide Note，供任务分解和执行参考               ││
│  └────────────────────────────────────────────────────────────────────┘│
│                          │                                              │
│                          ▼                                              │
│  Phase 2: 子任务开始 - Navigation Query                                 │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │ 时机: 每个子任务执行前                                             ││
│  │ 方法: MemoryToolkit.query_navigation(start, end)                   ││
│  │                                                                    ││
│  │ 输入:                                                              ││
│  │   start: 当前页面的 page_title (会做 embedding 查询)               ││
│  │   end: 子任务目标描述                                              ││
│  │                                                                    ││
│  │ 输出: QueryResult                                                  ││
│  │       - states: 路径上的所有 State                                 ││
│  │       - actions: 状态间的转移 Action                               ││
│  │                                                                    ││
│  │ 用途: 告诉 Agent 从当前位置到目标大概怎么走                        ││
│  │                                                                    ││
│  │ ⚠️ 重要: 结果是参考！页面可能变化，前面步骤可能出错                ││
│  └────────────────────────────────────────────────────────────────────┘│
│                                                                         │
│  ❌ Phase 3: 暂不实现 - Action Query                                    │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │ 原计划: 在页面上查询 IntentSequence                                ││
│  │ 状态: 暂不实现，后续迭代再考虑                                     ││
│  │ 原因: 简化复杂度，先验证 Phase 1 + 2 的效果                        ││
│  └────────────────────────────────────────────────────────────────────┘│
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 起点识别设计

**问题**：Agent 在某个页面，需要告诉 Memory 当前在哪里

**方案**：使用 `page_title` 做 embedding 查询

```python
# Agent 获取当前页面标题
page_title = await browser.get_page_title()  # e.g., "Product Hunt – The best new products in tech."

# 传给 Navigation Query 作为起点
result = await memory_toolkit.query_navigation(
    start_state=page_title,  # Memory 服务端会用 embedding 匹配最近的 State
    end_state="查看团队信息"
)
```

**Memory 服务端处理**：
```python
async def _resolve_state_id(self, state_ref: str) -> Optional[str]:
    """解析 state 引用为实际的 state_id"""

    # 1. 尝试直接 ID 匹配
    if state := self.memory.get_state(state_ref):
        return state.id

    # 2. 使用 embedding 搜索（page_title 会走这条路径）
    embedding = self.embedding_service.encode(state_ref)
    results = self.memory.search_states_by_embedding(embedding, limit=1)
    if results:
        return results[0].id

    return None
```

### 4.3 查询结果使用策略

**核心思想**：Memory 结果是**参考**，Agent 需要适应实际情况

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    查询结果使用策略                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  结果类型 1: CognitivePhrase 精确匹配                                    │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │ 置信度: 高                                                         ││
│  │ 用法: 按路径指导执行，但仍需验证每一步                             ││
│  │ 提示词: "这是用户验证过的工作流，优先按此执行"                      ││
│  └────────────────────────────────────────────────────────────────────┘│
│                                                                         │
│  结果类型 2: 组合路径匹配                                                │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │ 置信度: 中                                                         ││
│  │ 用法: 作为导航参考，验证每个状态                                   ││
│  │ 提示词: "这是推断的路径，参考使用，实际情况可能不同"               ││
│  └────────────────────────────────────────────────────────────────────┘│
│                                                                         │
│  结果类型 3: 无匹配                                                      │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │ 置信度: 无                                                         ││
│  │ 用法: Agent 自主探索                                               ││
│  │ 提示词: "Memory 没有相关记录，请根据页面内容自行判断"              ││
│  └────────────────────────────────────────────────────────────────────┘│
│                                                                         │
│  ⚠️ 通用提示词强调:                                                     │
│  "Memory 结果是参考，页面可能已变化，前面步骤可能出错，                 │
│   导致你当前的 state 和参考的不一致。请结合实际页面判断。"              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.4 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 起点识别 | page_title embedding | 简单可靠，Memory 服务端已支持 |
| 查询频率 | 每个子任务都查询 | 不同子任务起点不同 |
| 缓存策略 | 不缓存 | 每次查询的输入都不同 |
| Action Query | 暂不实现 | 简化复杂度，先验证基础功能 |
| Write-Back | 暂不实现 | 学习闭环后续迭代再做 |

---

## 4.5 Original Design (V1 参考)

> 以下是 V1 的三层设计，保留作为参考。V2 简化后只实现 Phase 1 (Task Query) 和 Phase 2 (Navigation Query)。

**原三层策略**：

| Level | 触发条件 | Memory 提供 | Agent 行为 |
|-------|----------|-------------|------------|
| **L1** | `cognitive_phrase_match` | 完整路径 + 各步操作菜单 | 按路径指导执行 |
| **L2** | `task_dag` 中有 Memory 支撑的 task | 该 task 相关的 State 信息 | 用 State 信息指导执行该 task |
| **L3** | Task 无 Memory 支撑 | 实时查询当前页面的 State | 每个 Loop 语义查询辅助信息 |

**判断是否有 Memory 支撑**：
- `cognitive_phrase_match` → 整体有 Memory 支撑
- `task_dag` → Reasoner 已分解，检查每个 task 的 retrieval 结果是否找到了 State

### 4.2 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        PROPOSED FLOW (优化后)                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  User Task: "在 Product Hunt 找一个 AI 写作工具，看看团队背景"           │
│                                                                         │
│  ══════════════════════════════════════════════════════════════════════│
│  Phase 1: 任务级 Memory Query                                           │
│  ══════════════════════════════════════════════════════════════════════│
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 强制调用 Reasoner:                                              │   │
│  │   POST /api/v1/reasoner/plan                                    │   │
│  │   {"target": "在 Product Hunt 找 AI 写作工具看团队背景"}         │   │
│  │                                                                 │   │
│  │ 判断返回结果:                                                   │   │
│  │   if method == "cognitive_phrase_match":                        │   │
│  │       → L1 命中! 有完整路径指导                                 │   │
│  │       → 进入 Phase 2A                                           │   │
│  │   else:                                                         │   │
│  │       → L1 未命中，需要 LLM 分解                                │   │
│  │       → 进入 Phase 2B                                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                          │                                              │
│          ┌───────────────┴───────────────┐                              │
│          ▼                               ▼                              │
│  ════════════════════          ════════════════════                     │
│  Phase 2A: L1 命中             Phase 2B: L1 未命中                       │
│  有完整路径指导                 LLM 分解 + Subtask 查询                  │
│  ════════════════════          ════════════════════                     │
│  ┌─────────────────────┐       ┌─────────────────────┐                  │
│  │ 路径指导:           │       │ LLM 分解为 Subtasks │                  │
│  │ State1 → State2 →   │       │                     │                  │
│  │ State3              │       │ 每个 Subtask 调用   │                  │
│  │                     │       │ Reasoner 找路径:    │                  │
│  │ 每个 State 包含:    │       │                     │                  │
│  │ - description       │       │ Subtask 1: 导航分类 │                  │
│  │ - intent_sequences  │       │   → Reasoner.plan() │                  │
│  │ - 到下一步的 Action │       │   → 可能有/没有路径 │                  │
│  │                     │       │                     │                  │
│  │ Agent 按指导执行:   │       │ Subtask 2: 选产品   │                  │
│  │ 但仍需决策选择      │       │   → Reasoner.plan() │                  │
│  └─────────────────────┘       │   → ...             │                  │
│          │                     │                     │                  │
│          │                     │ Subtask 3: 看Team   │                  │
│          │                     │   → Reasoner.plan() │                  │
│          │                     │   → 可能命中!       │                  │
│          │                     └─────────────────────┘                  │
│          │                               │                              │
│          └───────────────┬───────────────┘                              │
│                          ▼                                              │
│  ══════════════════════════════════════════════════════════════════════│
│  Phase 3: Subtask/Loop 执行                                             │
│  ══════════════════════════════════════════════════════════════════════│
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 执行每个 Subtask/Step:                                          │   │
│  │                                                                 │   │
│  │ Case A: 有路径指导 (L1 或 L2 命中)                              │   │
│  │   → 使用 State 的 intent_sequences 作为操作参考                 │   │
│  │   → 使用 Action 知道如何跳转                                    │   │
│  │   → Agent 参考执行，但仍做具体决策                              │   │
│  │                                                                 │   │
│  │ Case B: 无路径指导 (L3 兜底)                                    │   │
│  │   → 每个 Loop 查询当前 URL 对应的 State                         │   │
│  │   → GET /api/v1/memory/state-by-url?url={current_url}           │   │
│  │   → 获取: intent_sequences (能做什么) + actions (能去哪)        │   │
│  │   → 注入 LLM Context 辅助决策                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                          │                                              │
│                          ▼                                              │
│  ══════════════════════════════════════════════════════════════════════│
│  Phase 4: Memory Write-Back                                             │
│  ══════════════════════════════════════════════════════════════════════│
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 任务成功完成后:                                                 │   │
│  │                                                                 │   │
│  │ 1. 收集执行轨迹 (operations)                                    │   │
│  │ 2. POST /api/v1/memory/add                                      │   │
│  │ 3. Memory 会:                                                   │   │
│  │    - 更新已有 State 的 intent_sequences (发现新操作)            │   │
│  │    - 创建新 State (访问了新页面类型)                            │   │
│  │    - 创建/更新 CognitivePhrase (记录完整路径)                   │   │
│  │                                                                 │   │
│  │ → 形成学习闭环: 下次类似任务可能 L1 命中                        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Detailed Design

#### 4.3.1 Phase 1: 任务级 Memory Query (强制)

**目标**: 确保 Memory 被强制查询，判断是否有完整路径

**修改位置**: `eigent_style_browser_agent.py:execute()`

```python
async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
    # ... 参数解析 ...

    # === PHASE 1: 强制查询 Memory ===
    reasoner_result = None
    memory_level = "L3"  # 默认最低级别

    if self._memory_api_base_url:
        reasoner_result = await self._call_reasoner(task)

        if reasoner_result:
            method = reasoner_result.get("metadata", {}).get("method", "")
            states = reasoner_result.get("states", [])

            if method == "cognitive_phrase_match" and states:
                memory_level = "L1"  # 完整路径命中
                logger.info(f"[Memory L1] CognitivePhrase 命中, {len(states)} states")
            elif states:
                memory_level = "L2"  # 有部分信息
                logger.info(f"[Memory L2] TaskDAG 返回 {len(states)} states")
            else:
                memory_level = "L3"  # 无路径
                logger.info("[Memory L3] 无路径命中，将使用 Loop 级查询")

    # 根据 memory_level 决定后续流程
    if memory_level == "L1":
        # 完整路径指导，直接按 States 执行
        result = await self._execute_with_workflow_guidance(task, reasoner_result)
    else:
        # 需要分解，进入 Subtask 流程
        result = await self._execute_with_subtask_queries(task, reasoner_result, memory_level)
```

#### 4.3.2 Phase 2A: L1 命中 - 按路径指导执行

**场景**: CognitivePhrase 命中，有完整路径

```python
async def _execute_with_workflow_guidance(
    self,
    task: str,
    reasoner_result: Dict,
) -> str:
    """L1: 有完整路径指导时的执行流程.

    路径是指导而非剧本 - Agent 参考路径，但仍需做具体决策。
    """
    states = reasoner_result.get("states", [])
    actions = reasoner_result.get("actions", [])

    # 将路径转换为执行步骤
    for i, state in enumerate(states):
        step_context = self._build_step_context(
            state=state,
            action=actions[i] if i < len(actions) else None,
            step_number=i + 1,
            total_steps=len(states),
        )

        # 执行这一步 (可能需要多个 Loop)
        # Agent 参考 intent_sequences，但自己决策具体操作
        await self._execute_step_with_guidance(
            task=task,
            step_context=step_context,
        )

def _build_step_context(self, state: Dict, action: Dict, ...) -> str:
    """构建步骤上下文，供 LLM 参考."""
    context = f"""
## Step {step_number}/{total_steps}: {state.get('description', 'Unknown')}

**目标页面**: {state.get('page_title', 'Unknown')}
**URL Pattern**: {state.get('page_url', '')}

**该页面可用操作** (参考，非必须全部执行):
"""
    for seq in state.get("intent_sequences", []):
        context += f"- {seq.get('description', '')}\n"
        for intent in seq.get("intents", []):
            selector = intent.get("css_selector") or intent.get("xpath") or ""
            context += f"  - {intent.get('type')}: {selector}\n"

    if action:
        context += f"\n**到下一步的方式**: {action.get('description', action.get('type', ''))}\n"

    return context
```

#### 4.3.3 Phase 2B: L2/L3 - Subtask 级查询

**场景**: L1 未命中，需要 LLM 分解，每个 Subtask 单独查询

```python
async def _execute_with_subtask_queries(
    self,
    task: str,
    reasoner_result: Optional[Dict],
    memory_level: str,
) -> str:
    """L2/L3: 需要分解任务，每个 Subtask 单独查询 Memory."""

    # LLM 分解任务 (可以用 reasoner_result 中的部分信息辅助)
    workflow_hints = None
    if reasoner_result and reasoner_result.get("states"):
        workflow_hints = self._build_workflow_hints(reasoner_result)

    subtasks = await self._task_orchestrator._decompose_task(
        task,
        workflow_hints=workflow_hints
    )

    # 为每个 Subtask 查询 Memory
    for subtask in subtasks:
        subtask_result = await self._call_reasoner(subtask.content)

        if subtask_result and subtask_result.get("states"):
            # L2: Subtask 找到了路径
            subtask.memory_guidance = subtask_result
            logger.info(f"[Memory L2] Subtask '{subtask.id}' 找到路径")
        else:
            # L3: Subtask 也没路径，将在 Loop 中查询
            subtask.memory_guidance = None
            logger.info(f"[Memory L3] Subtask '{subtask.id}' 无路径，使用 Loop 级查询")

    # 执行 Subtasks
    return await self._run_agent_loop_with_memory(task, subtasks)
```

#### 4.3.4 Phase 3: Loop 级查询 (L3 兜底)

**场景**: L1 和 L2 都没有路径，在每个 Loop 查询当前页面

```python
async def _query_current_page_memory(self, current_url: str) -> Optional[Dict]:
    """L3: 查询当前 URL 对应的 State，获取操作菜单."""

    if not self._memory_api_base_url or not current_url:
        return None

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._memory_api_base_url}/api/v1/memory/state-by-url",
                params={"url": current_url, "user_id": self._user_id},
                headers={"X-Ami-API-Key": self._ami_api_key},
                timeout=5.0,  # 快速超时，不阻塞主流程
            )

            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.debug(f"[Memory L3] 查询失败: {e}")

    return None


def _format_page_memory_context(self, page_memory: Dict) -> str:
    """格式化页面 Memory 为 LLM Context."""

    state = page_memory.get("state", {})

    context = f"""
## Memory: 当前页面信息

**页面类型**: {state.get('description', 'Unknown')}

**可用操作**:
"""
    for seq in state.get("intent_sequences", []):
        context += f"- {seq.get('description', '')}\n"
        for intent in seq.get("intents", []):
            selector = intent.get("css_selector") or intent.get("xpath") or ""
            text = intent.get("text", "")
            context += f"  - {intent.get('type')}: {selector} {text}\n"

    # 添加可用跳转
    actions = page_memory.get("outgoing_actions", [])
    if actions:
        context += "\n**可以跳转到**:\n"
        for action in actions:
            target_desc = action.get("target_description", action.get("target", ""))
            context += f"- {action.get('description', action.get('type', ''))}: → {target_desc}\n"

    return context
```

#### 4.3.5 Phase 4: Memory Write-Back

**目标**: 任务完成后将执行轨迹写回 Memory

```python
async def _write_back_to_memory(
    self,
    task: str,
    success: bool,
) -> None:
    """将执行轨迹写回 Memory，形成学习闭环."""

    if not success:
        logger.info("[Memory] 任务失败，跳过写回")
        return

    if not self._memory_api_base_url:
        return

    try:
        # 从消息历史中提取操作轨迹
        operations = self._extract_operations_from_messages(self._messages)

        if not operations:
            logger.info("[Memory] 无操作轨迹，跳过写回")
            return

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._memory_api_base_url}/api/v1/memory/add",
                json={
                    "user_id": self._user_id,
                    "operations": operations,
                    "session_id": f"agent_{int(time.time())}",
                    "generate_embeddings": True,
                },
                headers={"X-Ami-API-Key": self._ami_api_key},
                timeout=60.0,
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    f"[Memory] 写回成功: "
                    f"{result.get('states_added', 0)} states, "
                    f"{result.get('intent_sequences_added', 0)} sequences, "
                    f"cognitive_phrase: {result.get('phrase_created', False)}"
                )
    except Exception as e:
        logger.warning(f"[Memory] 写回失败: {e}")
```

---

## 5. V2 Prompt Design (V2 提示词设计)

### 5.0 V2 提示词设计原则

**核心原则**：告诉 Agent 情况，让它自己判断。不需要详细指导。

#### 5.0.1 提示词模板

**有 Memory 结果时**：

```markdown
## Memory Reference (参考信息)

以下是 Memory 中记录的相关路径，仅供参考。
页面可能已变化，前面步骤可能出错导致当前状态与预期不符。
请结合实际页面内容判断。

{formatted_path}
```

**无 Memory 结果时**：

不需要特殊提示。Agent 本身就有能力完成任务。

#### 5.0.2 关键点

1. **简洁**：只说明这是参考，可能不准
2. **信任 Agent**：不需要详细指导如何处理各种情况
3. **无 Memory 时不废话**：Agent 本来就能干活

---

## 5.1 Original Prompt Modifications (V1 参考)

> 以下是 V1 的提示词设计，保留作为参考。

### 5.1 Agent System Prompt 修改

**文件**: `eigent_style_browser_agent.py` 中的 `EIGENT_STYLE_SYSTEM_PROMPT`

**新增内容**: 添加 Memory/Workflow Hints 解读说明

```python
<memory_guidance>
## Understanding Memory Information

When executing tasks, you may receive **Memory Guidance** from the system's workflow memory.
This guidance comes from previously recorded successful workflows and provides valuable context.

### What Memory Provides

Memory provides THREE types of information:

1. **Navigation Map (地图)**: Website topology structure
   - Shows the typical path: "Homepage → Category → Detail Page"
   - Helps you understand how pages connect

2. **Available Operations (菜单)**: What you can do on each page type
   - Each State describes a "page type" (not a specific URL)
   - Contains `intent_sequences`: operations that can be performed
   - Example: "On product detail page, you can: click Team tab, click Upvote, etc."

3. **Past Patterns (经验)**: Reference paths from similar tasks
   - Shows how similar tasks were completed before
   - Provides action descriptions and target states

### How to Interpret Memory Data

When you see **Workflow Hints** or **States**:

```
State: "Product Hunt Product Detail Page"
  └── intent_sequences:
        - "Click Team tab to view team info"
          └── Intent: Click, selector: [data-tab=team]
        - "Click Upvote button"
          └── Intent: Click, selector: .upvote-btn
  └── outgoing_actions:
        - "Click logo to return home" → Homepage
```

**CRITICAL**: This is a GUIDE, not a SCRIPT!

✅ DO:
- Use the path as navigation guidance
- Reference intent_sequences to find correct selectors
- Understand what operations are available on each page type
- Adapt the guidance to your specific task goal

❌ DON'T:
- Blindly execute every listed operation
- Assume you must visit every state in order
- Ignore your actual task requirements
- Treat Memory as exact replay instructions

### Decision Making with Memory

Memory tells you "what's possible" - YOU decide "what to do":

- **Selecting items**: Memory shows "榜单页可点击产品链接",
  but YOU choose WHICH product based on user's task
- **Executing operations**: Memory shows "详情页可点击Team",
  but YOU decide IF this is needed for the current task
- **Navigation choices**: Memory shows available paths,
  but YOU pick the path that serves the user's goal

### Memory Level Indicator

The system will indicate which Memory level is active:

- **[L1] Complete Path**: Full workflow path available - use as strong guidance
- **[L2] Partial Match**: Some subtasks have Memory support - use when available
- **[L3] Real-time Query**: Per-loop page queries - opportunistic assistance

Always check the Memory level to understand how much guidance is available.
</memory_guidance>
```

### 5.2 Task Decomposition Prompt 修改

**文件**: `task_orchestrator.py` 中的 `TASK_DECOMPOSITION_PROMPT`

**修改目的**: 让 TaskDecomposition 知道可能有 Memory 信息，并合理利用

```python
TASK_DECOMPOSITION_PROMPT = """You are a Task Decomposition Expert. Analyze the task and break it down into executable subtasks.

## MEMORY CONTEXT (if available)
{memory_context}

## CRITICAL RULES:

1. **USE MEMORY GUIDANCE**: If Memory provides workflow hints or states:
   - Align subtasks with the suggested navigation path
   - Don't create subtasks that contradict Memory's path
   - But feel free to add/modify subtasks based on actual task requirements

2. **SELF-CONTAINED**: Each subtask must be independently executable with all necessary context.
   - BAD: "Continue from previous step"
   - GOOD: "Extract product names from the search results page at example.com/products"

3. **CLEAR DELIVERABLE**: Define exactly what each subtask produces.
   - BAD: "Research the topic"
   - GOOD: "Find and list 5 competitor websites with their URLs and main features"

4. **SEQUENTIAL BY DEFAULT**: Order subtasks by dependency.

5. **MINIMAL DECOMPOSITION**: Don't over-decompose simple tasks.
   - If Memory provides a complete path, consider using fewer subtasks
   - If no Memory available, use standard decomposition

6. **SMART GROUPING**: Combine related sequential actions.

## OUTPUT FORMAT:
Return valid JSON only, no markdown code blocks:
{
    "analysis": "Brief analysis of task complexity and Memory usage",
    "memory_utilized": true/false,
    "subtasks": [
        {
            "id": "1.1",
            "content": "Clear description of what to do with expected deliverable",
            "dependencies": [],
            "has_memory_support": true/false
        }
    ]
}

## TASK TO DECOMPOSE:
{task}
"""
```

### 5.3 Memory Context Format

当调用 TaskDecomposition 时，需要传入格式化的 Memory 上下文：

```python
def _format_memory_context_for_decomposition(self, reasoner_result: Optional[Dict]) -> str:
    """Format Memory info for task decomposition prompt."""

    if not reasoner_result:
        return "No Memory guidance available. Decompose based on task requirements."

    method = reasoner_result.get("metadata", {}).get("method", "")
    states = reasoner_result.get("states", [])
    actions = reasoner_result.get("actions", [])

    if method == "cognitive_phrase_match" and states:
        # L1: Complete path available
        context = """**Memory Level: L1 - Complete Path Available**

The system found a previously recorded workflow that matches this task.

**Suggested Navigation Path:**
"""
        for i, state in enumerate(states):
            desc = state.get("description", "") if isinstance(state, dict) else getattr(state, "description", "")
            context += f"  {i+1}. {desc}\n"

            # Add action to next state if exists
            if i < len(actions):
                action = actions[i]
                action_desc = action.get("description", "") if isinstance(action, dict) else getattr(action, "description", "")
                context += f"     → {action_desc}\n"

        context += """
**Recommendation**: Align your subtasks with this path. The path is guidance, not requirement.
"""
        return context

    elif method == "task_dag" and states:
        # L2: TaskDAG with some matches
        context = """**Memory Level: L2 - Partial Memory Support**

The system found some relevant page information but not a complete path.

**Available State Information:**
"""
        for state in states[:5]:  # Limit to 5 states
            desc = state.get("description", "") if isinstance(state, dict) else getattr(state, "description", "")
            context += f"  - {desc}\n"

        context += """
**Recommendation**: Consider these known pages when creating subtasks.
"""
        return context

    else:
        return "No Memory guidance available. Decompose based on task requirements."
```

### 5.4 Prompt Injection Points

**在 Agent Loop 中注入 Memory 上下文的位置**：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Context Injection Flow                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. Initial Task Message                                                 │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ ## Your Task                                                       │ │
│  │ {task}                                                             │ │
│  │                                                                    │ │
│  │ ## Memory Guidance [L1/L2/L3]                                      │ │
│  │ {formatted_workflow_hints}     ← 初始注入 Memory 路径信息          │ │
│  │                                                                    │ │
│  │ ## Current Task Plan                                               │ │
│  │ {plan_summary}                                                     │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  2. Per-Loop Context Update (L3 模式)                                    │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ [Tool Results...]                                                  │ │
│  │                                                                    │ │
│  │ ## Current Page Memory (L3 Query)                                  │ │
│  │ {page_memory_context}          ← 每个 Loop 注入当前页面信息        │ │
│  │                                                                    │ │
│  │ ## Current Task Plan                                               │ │
│  │ {updated_plan_summary}                                             │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.5 Implementation Checklist

**Phase P0-3: Prompt Modifications**

**文件**: `eigent_style_browser_agent.py`
- [ ] 更新 `EIGENT_STYLE_SYSTEM_PROMPT` 添加 `<memory_guidance>` 章节
- [ ] 新增 `_format_workflow_hints_for_prompt()` 方法
- [ ] 修改 `_build_task_message_with_plan()` 注入 Memory 上下文

**文件**: `task_orchestrator.py`
- [ ] 更新 `TASK_DECOMPOSITION_PROMPT` 添加 Memory 上下文占位符
- [ ] 新增 `_format_memory_context_for_decomposition()` 方法
- [ ] 修改 `_decompose_task()` 接受 `workflow_hints` 参数

**文件**: `prompts/browser_agent.py`
- [ ] 更新 `BROWSER_AGENT_SYSTEM_PROMPT` 添加 Memory 解读说明
- [ ] 更新 `BROWSER_TOOL_CALLING_PROMPT` 同步修改

---

## 6. New API Endpoint Required

### 6.1 GET /api/v1/memory/state-by-url

**用途**: L3 级查询，根据 URL 获取对应的 State 及其操作菜单

**请求**:
```
GET /api/v1/memory/state-by-url?url=https://producthunt.com/posts/xxx&user_id=user123
Headers:
  X-Ami-API-Key: xxx
```

**返回**:
```json
{
    "success": true,
    "state": {
        "id": "state_xxx",
        "description": "Product Hunt 产品详情页",
        "page_url": "https://producthunt.com/posts/...",
        "page_title": "Product - Product Hunt",
        "intent_sequences": [
            {
                "description": "点击 Team 标签查看团队",
                "intents": [
                    {"type": "Click", "css_selector": "[data-tab=team]", "text": "Team"}
                ]
            },
            {
                "description": "点击 Upvote 按钮",
                "intents": [
                    {"type": "Click", "css_selector": ".upvote-btn"}
                ]
            }
        ]
    },
    "outgoing_actions": [
        {
            "target": "state_yyy",
            "target_description": "Product Hunt 首页",
            "type": "ClickLink",
            "description": "点击 Logo 返回首页"
        }
    ]
}
```

---

## 7. Implementation Plan (实施计划)

### 7.1 优先级和阶段

| Phase | 任务 | 难度 | 工作量 | 依赖 | 状态 |
|-------|------|------|--------|------|------|
| **P0-1** | 强制调用 Reasoner + 判断 memory_level | 低 | 0.5d | - | ✅ DONE |
| **P0-2** | Memory Write-Back 实现 | 中 | 1d | - | **暂不做** |
| **P0-3** | Agent/TaskPlan 提示词修改 | 低 | 0.5d | - | ✅ DONE |
| **P1-1** | L1 执行流程 (完整路径 → subtasks) | 中 | 1d | P0-1, P0-3 | ✅ DONE |
| **P1-2** | L2 执行流程 (Memory辅助LLM分解) | 中 | 1d | P0-1, P0-3 | ✅ DONE |
| **P1-3** | L3 执行流程 (Loop 级 embedding 查询) | 中 | 1d | P0-1, P0-3 | 暂不做 |
| **前端** | memory_level 事件处理 + UI 显示 | 低 | 0.5d | P0-1 | ✅ DONE |

> **Note**:
> - P0-2 (Memory Write-Back) 暂不实现，后续再考虑学习闭环
> - P1-3 (L3 Loop级查询) 暂不实现，当前先聚焦 L1/L2
> - 前端已完成 memory_level 事件处理和 Status Bar 显示

### 7.1.1 简化后的实现架构

实现采用了更简洁的架构，核心逻辑集中在 `_decompose_task()` 方法：

```
Task → Reasoner 查询 → 判断 memory_level
                          ↓
        L1 (完整 workflow) → _workflow_to_subtasks() → 直接转 subtasks (无需 LLM)
        L2 (部分信息)      → LLM + Memory context → 拆解
        L3 (无信息)        → LLM 正常拆解
```

**关键改动**:

1. **`_decompose_task()` 统一入口**:
   - L1: 调用 `_workflow_to_subtasks()` 直接转换，不调 LLM
   - L2/L3: 调用 LLM，L2 时传入 Memory context 作为参考

2. **`_workflow_to_subtasks()` 新方法**:
   - 将 workflow 的 states/actions 直接转成 subtasks
   - 每个 state 对应一个 subtask
   - subtask 内容包含 state 描述、URL、intent_sequences

3. **`memory_level` SSE 事件**:
   - 在 execute() 中判断并发送
   - 前端接收后显示在 Status Bar

### 7.2 详细任务

#### Phase P0-1: 强制调用 Reasoner (0.5d) ✅ DONE

**文件**: `eigent_style_browser_agent.py`

- [x] 修改 `execute()` 方法
  - [x] 移除 `use_reasoner` 的可选逻辑，改为强制调用（如果配置了 Memory API）
  - [x] 新增 `memory_level` 变量 ("L1", "L2", "L3")
  - [x] 根据 `reasoner_result.metadata.method` 和 `states` 判断级别
- [x] 新增 SSE 事件
  - [x] `memory_level` 事件 (携带 level, reason, states_count, method)

**文件**: `events/action_types.py`
- [x] 新增 `Action.memory_level` 枚举
- [x] 新增 `MemoryLevelData` 事件类

#### Phase P0-2: Memory Write-Back (1d) - 暂不做

**文件**: `eigent_style_browser_agent.py`

- [ ] 新增方法 `_write_back_to_memory()`
- [ ] 新增方法 `_extract_operations_from_messages()`
- [ ] 在 `execute()` 末尾添加 write-back 调用
- [ ] 新增 SSE 事件 `memory_write_back_completed`

#### Phase P0-3: Agent/TaskPlan 提示词修改 (0.5d) ✅ DONE

**目标**: 让 LLM 正确理解 Memory 信息并合理使用

**文件**: `eigent_style_browser_agent.py`
- [x] 更新 `EIGENT_STYLE_SYSTEM_PROMPT` 添加 `<memory_guidance>` 章节
  - [x] 解释 Memory 提供的三种能力 (地图/菜单/经验)
  - [x] 解释 State、Intent、Action 的含义
  - [x] 强调 "指导而非剧本" 的核心理念
  - [x] 说明 L1/L2/L3 三个级别的含义
- [x] 新增 `_format_workflow_hints_for_prompt()` 方法
- [x] 修改 `_build_task_message_with_plan()` 注入 Memory 上下文

**文件**: `task_orchestrator.py`
- [x] 更新 `TASK_DECOMPOSITION_PROMPT`
  - [x] 添加 `{memory_context}` 占位符
  - [x] 添加 "USE MEMORY GUIDANCE" 规则
  - [x] 输出格式添加 `memory_utilized` 和 `has_memory_support` 字段
- [x] 新增 `_format_memory_context_for_decomposition()` 方法
- [x] 修改 `_decompose_task()` 接受 `reasoner_result` 和 `memory_level` 参数
- [x] 新增 `_workflow_to_subtasks()` 方法 (L1 直接转换)

**文件**: `prompts/browser_agent.py`
- [ ] 更新 `BROWSER_AGENT_SYSTEM_PROMPT` 添加 Memory 解读说明 (可选，system prompt 已包含)
- [ ] 更新 `BROWSER_TOOL_CALLING_PROMPT` 同步修改 (可选)

#### Phase P1-1: L1 执行流程 (1d) ✅ DONE (简化实现)

**实现方式**: 不再需要独立的执行方法，直接在 `_decompose_task()` 中转换

**文件**: `task_orchestrator.py`

- [x] 新增方法 `_workflow_to_subtasks()` - 将 workflow 直接转为 subtasks
- [x] L1 时跳过 LLM 调用，直接使用 workflow 生成的 subtasks

#### Phase P1-2: L2 执行流程 (1d) ✅ DONE (简化实现)

**实现方式**: 在 `_decompose_task()` 中传入 Memory context 辅助 LLM 分解

**文件**: `task_orchestrator.py`

- [x] L2 时调用 LLM 但传入 `_format_memory_context_for_decomposition()` 的结果
- [x] LLM 可以参考 Memory 信息进行更准确的分解

#### Phase P1-3: L3 执行流程 (1d) - 暂不做

**文件**: `eigent_style_browser_agent.py`, `task_orchestrator.py`

- [ ] 新增方法 `_execute_with_subtask_queries()`
- [ ] 修改 `SubTask` 数据类，添加 `memory_guidance` 字段
- [ ] 修改 `_decompose_task()` 支持 `workflow_hints` 参数

#### Phase P1-3: L3 执行流程 (1d)

**文件**: `eigent_style_browser_agent.py`

- [ ] 新增方法 `_query_current_page_memory()`
- [ ] 新增方法 `_format_page_memory_context()`
- [ ] 修改 `_run_agent_loop()` 在每次迭代时查询

#### Phase P2-1: 新增 API (0.5d) - 可选

**文件**: `cloud_backend/main.py`

- [ ] 新增 endpoint `GET /api/v1/memory/state-by-url` (如果 L3 需要)
- [ ] 或直接使用现有 `/api/v1/memory/query` 进行语义查询
- [ ] 返回 State + outgoing_actions

---

## 8. Related Components (相关组件)

本节列出与 Memory-Agent 集成相关的所有组件，确保设计完整性。

### 8.1 组件清单

| 组件 | 位置 | 作用 | 修改需求 |
|------|------|------|----------|
| **Agent System Prompt** | `eigent_style_browser_agent.py` | LLM 主提示词 | ✅ 需修改 (P0-3) |
| **Task Decomposition Prompt** | `task_orchestrator.py` | 任务分解提示词 | ✅ 需修改 (P0-3) |
| **Browser Agent Prompt** | `prompts/browser_agent.py` | Browser 特定提示词 | ⚠️ 可能需要同步 |
| **Note Taking Toolkit** | `note_taking_toolkit.py` | workflow_hints.md 生成 | ✅ 需修改格式 (P0-3) |
| **SSE Event Types** | `events/action_types.py` | 前端事件定义 | ⚠️ 可能需新增 L1/L2/L3 事件 |
| **Agent Store (Frontend)** | `agentStore.js` | 前端状态管理 | ⚠️ 可能需处理新事件 |
| **Memory Toolkit** | `memory_toolkit.py` | Memory 查询工具 | ✅ 需增强 L3 查询 |

### 8.2 组件交互流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Component Interaction Flow                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. Task Start                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │ eigent_style_browser_agent.execute()                                ││
│  │   │                                                                 ││
│  │   ├─→ _call_reasoner() → Memory API                                 ││
│  │   │     └─→ Emit: memory_query SSE Event                            ││
│  │   │     └─→ Emit: memory_level_determined (L1/L2/L3) SSE Event      ││
│  │   │                                                                 ││
│  │   ├─→ _format_workflow_hints_for_prompt()                           ││
│  │   │     └─→ Inject into Agent System Prompt                         ││
│  │   │                                                                 ││
│  │   └─→ note_taking_toolkit._create_workflow_hints_note()             ││
│  │         └─→ Create workflow_hints.md with Memory data               ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  2. Task Decomposition (if L1 not available)                             │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │ task_orchestrator._decompose_task()                                 ││
│  │   │                                                                 ││
│  │   ├─→ _format_memory_context_for_decomposition()                    ││
│  │   │     └─→ Build memory_context for prompt                         ││
│  │   │                                                                 ││
│  │   └─→ LLM Call with TASK_DECOMPOSITION_PROMPT                       ││
│  │         └─→ Returns subtasks with has_memory_support flags          ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  3. Agent Loop (per iteration)                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │ _run_agent_loop() iteration                                         ││
│  │   │                                                                 ││
│  │   ├─→ (L3 only) _query_current_page_memory()                        ││
│  │   │     └─→ memory_toolkit / Memory API                             ││
│  │   │     └─→ _format_page_memory_context()                           ││
│  │   │                                                                 ││
│  │   ├─→ _build_task_message_with_plan()                               ││
│  │   │     └─→ Inject Memory context + plan summary                    ││
│  │   │                                                                 ││
│  │   └─→ LLM Call with System Prompt (contains <memory_guidance>)      ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  4. Frontend Display                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │ agentStore.js                                                       ││
│  │   │                                                                 ││
│  │   ├─→ Handle memory_level_determined event                          ││
│  │   │     └─→ Display L1/L2/L3 indicator in UI                        ││
│  │   │                                                                 ││
│  │   └─→ Handle memory_result event                                    ││
│  │         └─→ Update memoryPaths display                              ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 8.3 额外修改任务 (P0-3 补充)

**文件**: `note_taking_toolkit.py`
- [ ] 更新 `_create_workflow_hints_note()` 方法
  - [ ] 添加 Memory Level 标识 (L1/L2/L3)
  - [ ] 改进 States/Actions 格式化
  - [ ] 添加 intent_sequences 详细信息

**文件**: `events/action_types.py`
- [ ] 新增 `MemoryLevelData` 事件类型
  ```python
  class MemoryLevelData(BaseActionData):
      action: str = "memory_level"
      level: str  # "L1" | "L2" | "L3"
      reason: str  # 为什么是这个级别
      states_count: int = 0
      method: str = ""  # "cognitive_phrase_match" | "task_dag" | "none"
  ```

**文件**: `agentStore.js`
- [ ] 处理 `memory_level` 事件
  - [ ] 更新 UI 显示 Memory 级别
  - [ ] 在任务信息中展示 L1/L2/L3 状态

**文件**: `memory_toolkit.py`
- [ ] 增强 L3 查询能力
  - [ ] 新增 `query_current_page()` 方法 (使用 embedding 语义查询)
  - [ ] 返回 State 的 intent_sequences 和 outgoing actions

### 8.4 前端适配任务

本节详细描述前端需要的适配工作，确保 Memory 级别信息能够正确显示在 UI 中。

#### 8.4.1 新增 SSE 事件类型

**文件**: `events/action_types.py`

需要新增以下事件类型：

```python
# Memory Level 事件 (P0-1 新增)
class MemoryLevelData(BaseActionData):
    """Memory level determination event."""

    action: Literal[Action.memory_level] = Action.memory_level
    level: str  # "L1" | "L2" | "L3"
    reason: str  # 为什么是这个级别 (中文说明)
    states_count: int = 0  # 找到的 State 数量
    method: str = ""  # "cognitive_phrase_match" | "task_dag" | "none"
    paths: Optional[List[Dict]] = None  # 可选：完整路径信息 (L1 时有值)
```

同时在 `Action` 枚举中添加：
```python
# Memory events
memory_level = "memory_level"  # Memory 级别确定事件
```

#### 8.4.2 前端 Store 适配

**文件**: `agentStore.js`

1. **Task State 新增字段**:

在 `createInitialTaskState()` 中添加：
```javascript
// Memory integration state
memoryLevel: null,        // "L1" | "L2" | "L3" | null
memoryLevelReason: '',    // 级别判定原因
memoryMethod: '',         // "cognitive_phrase_match" | "task_dag" | "none"
memoryStatesCount: 0,     // 找到的 State 数量
memoryWorkflowPath: [],   // L1 时的完整路径 (用于 UI 显示)
```

2. **新增 SSE 事件处理**:

在 `handleSSEEvent()` 中添加 case：
```javascript
case 'memory_level':
  {
    const { level, reason, states_count, method, paths } = event;

    updateTask({
      memoryLevel: level,
      memoryLevelReason: reason,
      memoryMethod: method || '',
      memoryStatesCount: states_count || 0,
      memoryWorkflowPath: paths || [],
      executionPhase: level === 'L1' ? 'memory_guided' : 'executing',
    });

    // 根据级别显示不同提示
    const levelMessages = {
      'L1': `Memory L1: 找到完整路径 (${states_count} states)`,
      'L2': `Memory L2: 找到部分信息 (${states_count} states)`,
      'L3': 'Memory L3: 将使用实时查询',
    };

    addNotice('memory', 'Memory Level', levelMessages[level] || `Memory: ${level}`);
  }
  break;
```

3. **更新 memory_loaded/memory_result 处理**:

增强现有事件处理，携带更多信息：
```javascript
case 'memory_loaded':
case 'memory_result':
  {
    const paths = event.paths || [];
    const level = event.level || (paths.length > 0 ? 'L2' : 'L3');

    updateTask({
      memoryPaths: paths,
      memoryLevel: level,
      executionPhase: 'memory_loaded',
    });

    if (paths.length > 0) {
      addNotice('memory', 'Memory Loaded', `找到 ${paths.length} 条相关路径 [${level}]`);
    }
  }
  break;
```

#### 8.4.3 UI 组件适配

**文件**: `AgentPage.jsx`

1. **从 Store 获取 Memory 状态**:
```javascript
const memoryLevel = activeTask?.memoryLevel || null;
const memoryLevelReason = activeTask?.memoryLevelReason || '';
const memoryMethod = activeTask?.memoryMethod || '';
const memoryStatesCount = activeTask?.memoryStatesCount || 0;
const memoryWorkflowPath = activeTask?.memoryWorkflowPath || [];
```

2. **传递给 WorkspaceTabs**:
```jsx
<WorkspaceTabs
  // ... existing props ...
  // Memory integration props
  memoryLevel={memoryLevel}
  memoryLevelReason={memoryLevelReason}
  memoryMethod={memoryMethod}
  memoryStatesCount={memoryStatesCount}
  memoryWorkflowPath={memoryWorkflowPath}
/>
```

**文件**: `components/Workspace/AgentTab.jsx` (或相关组件)

1. **显示 Memory Level Badge**:
```jsx
const MemoryLevelBadge = ({ level, statesCount }) => {
  if (!level) return null;

  const levelConfig = {
    L1: { color: 'green', icon: '🎯', label: 'Complete Path' },
    L2: { color: 'yellow', icon: '📍', label: 'Partial Match' },
    L3: { color: 'gray', icon: '🔍', label: 'Real-time Query' },
  };

  const config = levelConfig[level] || levelConfig.L3;

  return (
    <div className={`memory-level-badge ${config.color}`}>
      <span className="icon">{config.icon}</span>
      <span className="level">{level}</span>
      <span className="label">{config.label}</span>
      {statesCount > 0 && <span className="count">({statesCount} states)</span>}
    </div>
  );
};
```

2. **在 AgentTab 头部显示**:
```jsx
<div className="agent-tab-header">
  <MemoryLevelBadge level={memoryLevel} statesCount={memoryStatesCount} />
  {/* ... other header content ... */}
</div>
```

#### 8.4.4 Status Bar 适配

**文件**: `AgentPage.jsx` - Status Bar 部分

在 `getPhaseText()` 中添加新的 phase：
```javascript
const getPhaseText = () => {
  switch (executionPhase) {
    // ... existing cases ...
    case 'memory_guided': return `🧠 Memory L1: 路径指导执行`;
    case 'memory_l2': return `📍 Memory L2: 部分信息指导`;
    case 'memory_l3': return `🔍 Memory L3: 实时查询中`;
    // ...
  }
};
```

在 Status Bar 中显示 Memory 级别：
```jsx
{status !== 'idle' && (
  <div className="task-status-bar bottom">
    <div className="task-status-left">
      {/* ... existing status badges ... */}

      {/* Memory Level Indicator */}
      {memoryLevel && (
        <div className={`memory-indicator memory-${memoryLevel.toLowerCase()}`}>
          <span className="memory-level">{memoryLevel}</span>
        </div>
      )}

      {/* ... task description ... */}
    </div>
    {/* ... */}
  </div>
)}
```

#### 8.4.5 CSS 样式

**文件**: `styles/AgentPage.css` (或相关样式文件)

```css
/* Memory Level Badge */
.memory-level-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.memory-level-badge.green {
  background: rgba(34, 197, 94, 0.1);
  color: #22c55e;
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.memory-level-badge.yellow {
  background: rgba(234, 179, 8, 0.1);
  color: #eab308;
  border: 1px solid rgba(234, 179, 8, 0.3);
}

.memory-level-badge.gray {
  background: rgba(107, 114, 128, 0.1);
  color: #6b7280;
  border: 1px solid rgba(107, 114, 128, 0.3);
}

/* Memory Indicator in Status Bar */
.memory-indicator {
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
  margin-left: 8px;
}

.memory-indicator.memory-l1 {
  background: #22c55e;
  color: white;
}

.memory-indicator.memory-l2 {
  background: #eab308;
  color: white;
}

.memory-indicator.memory-l3 {
  background: #6b7280;
  color: white;
}
```

#### 8.4.6 实现检查清单

**前端适配任务清单**:

- [ ] `events/action_types.py`: 新增 `memory_level` Action 枚举值
- [ ] `events/action_types.py`: 新增 `MemoryLevelData` 事件类型
- [ ] `agentStore.js`: 在 `createInitialTaskState()` 添加 Memory 相关字段
- [ ] `agentStore.js`: 在 `handleSSEEvent()` 添加 `memory_level` case
- [ ] `agentStore.js`: 增强 `memory_loaded/memory_result` 事件处理
- [ ] `AgentPage.jsx`: 从 Store 获取并传递 Memory 状态
- [ ] `AgentPage.jsx`: 更新 `getPhaseText()` 添加 Memory phases
- [ ] `AgentPage.jsx`: Status Bar 添加 Memory Level 显示
- [ ] `components/Workspace/AgentTab.jsx`: 添加 MemoryLevelBadge 组件
- [ ] `styles/AgentPage.css`: 添加 Memory 相关样式

---

## 9. Success Metrics (成功指标)

### 9.1 功能指标

| 指标 | 当前 | 目标 |
|------|------|------|
| Memory 查询率 | ~50% (可选) | 100% (强制) |
| L1 命中率 (重复任务) | N/A | >30% |
| Memory Write-Back 率 | 0% | >80% (成功任务) |

### 9.2 效率指标

| 指标 | 当前 | 目标 |
|------|------|------|
| 重复任务执行步数 | N (探索) | N*0.7 (有指导) |
| 页面操作成功率 | Baseline | +15% (有 selector) |

---

## 10. Summary

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            设计总结                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  核心理念:                                                               │
│    Memory 是「认知地图 + 操作菜单」，不是「执行剧本」                     │
│    CognitivePhrase 是「路径指导」，Agent 仍需自主决策                    │
│                                                                         │
│  逐级降级策略:                                                           │
│    L1: 任务级 - CognitivePhrase 完整路径 → 按指导执行                   │
│    L2: Subtask 级 - 每个子任务查询路径 → 有就用，没有降级               │
│    L3: Loop 级 - 每次迭代 embedding 查询 → 获取操作菜单                 │
│                                                                         │
│  关键改进:                                                               │
│    1. Memory 查询从可选变强制 (P0-1)                                    │
│    2. Agent/TaskPlan 提示词支持 Memory (P0-3)                           │
│    3. 有完整路径时不再重复 LLM 分解 (P1-1)                              │
│    4. 每个 Subtask 单独查询 Memory (P1-2)                               │
│    5. Loop 级 embedding 兜底查询 (P1-3)                                 │
│    6. 执行结果写回形成闭环 (暂不做)                                      │
│                                                                         │
│  涉及组件:                                                               │
│    - Agent System Prompt (EIGENT_STYLE_SYSTEM_PROMPT)                   │
│    - Task Decomposition Prompt (TASK_DECOMPOSITION_PROMPT)              │
│    - Note Taking Toolkit (workflow_hints.md 格式)                       │
│    - SSE Events (memory_level 事件)                                     │
│    - Memory Toolkit (L3 查询增强)                                       │
│    - Frontend Store (memory_level 显示)                                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```
