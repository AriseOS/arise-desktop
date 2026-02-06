# Memory-Agent Integration Design (V3)

> **Last Updated**: 2026-02-07
> **Status**: V3 - 基于 AMITaskPlanner + AMITaskExecutor 架构
> **前版**: V2 基于 eigent_style_browser_agent + task_orchestrator（已废弃）

## 1. 核心理念

**Memory 是认知地图，不是执行剧本。**

| 能力 | 说明 | 示例 |
|------|------|------|
| **地图** | 网站拓扑结构 | "首页 → 排行榜 → 详情页" |
| **菜单** | 每个页面可用操作 | "详情页可以: 看 Team、看评论、点赞" |
| **经验** | 过去类似任务的完整路径 | CognitivePhrase: 查看团队 = 进详情 → 点 Team |

Agent 参考 Memory 提供的信息，自主决策具体操作。

---

## 2. 当前架构

### 2.1 执行管线

```
User Task
  → OrchestratorAgent          # 路由: 直接回复 / 工具调用 / decompose_task
    → AMITaskPlanner            # 分解 + Memory 查询
      1. LLM 分解 → N 个 atomic subtasks (XML)
      2. 逐个 subtask 调用 memory_toolkit.query_task()
      3. 每个 subtask 标注 L1/L2/L3 + workflow_guide
    → AMITaskExecutor           # 按依赖顺序执行
      1. 取下一个可执行 subtask（依赖已完成）
      2. set_memory_context() 注入 workflow_guide
      3. _build_prompt() 构建带 Workflow Guide 的 prompt
      4. agent.astep() 执行（CAMEL 工具调用循环）
      5. 简单重试 max 2 次
    → TaskSummaryAgent          # 聚合结果
```

### 2.2 关键文件

| 文件 | 作用 |
|------|------|
| `base_agent/core/orchestrator_agent.py` | 顶层路由 |
| `base_agent/core/ami_task_planner.py` | 任务分解 + Memory 查询 |
| `base_agent/core/ami_task_executor.py` | 顺序执行 + workflow_guide 注入 |
| `base_agent/core/agent_factories.py` | 创建专业 Agent（Browser/Developer/Document/...） |
| `base_agent/tools/toolkits/memory_toolkit.py` | Memory 查询接口（V2 API） |
| `base_agent/tools/toolkits/long_term_memory_toolkit.py` | 用户语义记忆（MEMORY.md / daily log） |

### 2.3 Memory 三级查询模型

| Level | 含义 | 来源 | workflow_guide 内容 |
|-------|------|------|---------------------|
| **L1** | 精确匹配 | CognitivePhrase（用户录制的完整工作流） | 完整步骤 + URL + IntentSequence + Action |
| **L2** | 部分匹配 | 图检索组合的 states + actions 路径 | 导航路径 + 页面描述 |
| **L3** | 无匹配 | 无 | 空，Agent 自主探索 |

### 2.4 Workflow Guide 注入方式

`AMITaskExecutor._build_prompt()` 将 workflow_guide 作为**显式指令**注入：

```
## User's Original Request
{user_request}

## Your Task
{subtask.content}

## Workflow Guide (FOLLOW THESE STEPS)
The following is a proven workflow for this type of task.
You MUST follow these steps in order:

{subtask.workflow_guide}
```

---

## 3. 问题分析

### 3.1 先分解再查 Memory（时序错误）

**现状**：`decompose_and_query_memory()` 先调用 LLM 分解任务，再逐个 subtask 查 Memory。

**设计文档要求**：`memory-as-map-design.md` 明确写道 "Task decomposition MUST happen AFTER Memory query"。

**影响**：LLM 在没有 Memory 上下文的情况下分解，可能产生低效路径。

```
当前流程:
  LLM 猜测分解 → 查 Memory（但 subtask 已经分好了）

应该:
  先查 Memory → 带 Memory 上下文的 LLM 分解
```

### 3.2 执行期间无动态 Memory 查询

**现状**：`ami_task_executor.py:258-268` 中 Memory 只在 subtask 开始前通过 `set_memory_context()` 静态注入一次。

**缺失**：Agent 执行过程中导航到新页面时，没有能力再次查询 Memory 获取当前页面的可用操作。`memory-as-map-design.md` 设计了 "During Agent Loop → Query states ONLY (current page info)" 但未实现。

**影响**：长程任务中 Agent 越到后面越「迷路」——初始注入的 workflow_guide 已不匹配当前状态。

### 3.3 无执行反馈与重规划

**现状**：`AMITaskExecutor` 按静态计划顺序执行，每个 subtask 只有简单重试（同一 prompt 重试 2 次）。

**缺失**：
- subtask 失败后没有重新规划能力
- subtask 结果与预期不符时不会调整后续计划
- 执行过程中无法新增/删除/修改后续 subtask

**影响**：长程任务（>5 步）中，前序结果改变后续逻辑但计划无法适应。

### 3.4 Memory Level 不影响执行策略

**现状**：L1/L2/L3 只决定注入什么文本，执行策略完全相同。

**缺失**：
- L1 应该「严格跟随」：按步骤执行，偏离时回退
- L2 应该「参考导航」：路径为骨架，允许适应性调整
- L3 应该「自由探索」：自主探索，同时记录路径

### 3.5 无 Memory 写回

**现状**：Agent 只读 Memory，不写 Memory。

**影响**：
- L3 探索成功后路径不会被记录
- 新发现的页面操作不会更新到 Memory
- Memory 知识不随使用增长，无法形成学习闭环

---

## 4. 改进方案

### 4.1 Memory-First 任务分解（P0）

**核心变更**：先查 Memory 再分解，Memory 结果指导分解策略。

```
当前流程（有问题）:
  LLM 盲猜分解 → 逐个 subtask 查 Memory（事后补）

新流程:
  1. query_task(整体任务) → 获取 Memory 结果（L1/L2/L3）
  2. 将 Memory 结果作为上下文注入分解 prompt
  3. LLM 根据 Memory 上下文做分解
  4. Memory 结果整体赋给 browser subtask 的 workflow_guide（不拆分）
```

**修改位置**：`ami_task_planner.py` 的 `decompose_and_query_memory()`

**当前代码**：

```python
async def decompose_and_query_memory(self, task: str) -> List[AMISubtask]:
    # Step 1: 先分解
    subtasks = await self._fine_grained_decompose(task)
    # Step 2: 再逐个查 Memory
    await self._query_memory_for_subtasks(subtasks)
    return subtasks
```

**改为**：

```python
async def decompose_and_query_memory(self, task: str) -> List[AMISubtask]:
    # Step 1: 先查 Memory（整体任务级）
    task_memory = await self._query_task_memory(task)

    # Step 2: 带 Memory 上下文的 LLM 分解
    memory_context = self._format_memory_for_decompose(task_memory)
    subtasks = await self._fine_grained_decompose(task, memory_context=memory_context)

    # Step 3: 将整体 Memory 结果分配给 browser subtask（方案 B：不拆分）
    self._assign_memory_to_subtasks(subtasks, task_memory)

    return subtasks
```

**关键设计决策：方案 B — Memory 路径整体注入，不拆成多个 subtask**

当 Memory 返回 L1/L2 的 browser 路径时（例如 3 个 states 的导航路径），**不拆成 3 个 subtask**，而是把整条路径作为 workflow_guide 注入到 browser subtask 中。

理由：
1. **动态 page operations 已覆盖细粒度**：BrowserAgent 到每个新页面时，会自动查询并注入该页面的 IntentSequence（见 4.2）。所以上层不需要帮它拆。
2. **保持上下文连续性**：一个 browser subtask 看到完整路径，比拆成 3 个各看一段好。
3. **符合分解原则**：`FINE_GRAINED_DECOMPOSE_PROMPT` 要求 "Strategic Grouping" — 同一 worker 的连续操作应合并。

```python
def _assign_memory_to_subtasks(self, subtasks, task_memory):
    """将整体 Memory 结果赋给 browser subtask。"""
    if not task_memory or not task_memory.success:
        return

    # 确定 memory level
    if task_memory.cognitive_phrase:
        level = "L1"
        guide = MemoryToolkit.format_cognitive_phrase(task_memory.cognitive_phrase)
    elif task_memory.states:
        level = "L2"
        guide = MemoryToolkit.format_navigation_path(task_memory.states, task_memory.actions)
    else:
        return  # L3, nothing to assign

    # 整体赋给 browser 类型的 subtask
    for subtask in subtasks:
        if subtask.agent_type == "browser":
            subtask.memory_level = level
            subtask.workflow_guide = guide
        # 非 browser subtask 保持 L3（Memory 没有 document/code 的路径信息）
```

**注意**：`query_task` 当前底层是单 domain 的（基于图最短路径），跨 domain 场景由 Memory 层面（Reasoner）处理，不是 Agent 层面的问题。

**分解 prompt 增加 Memory 上下文**：

在 `FINE_GRAINED_DECOMPOSE_PROMPT` 末尾追加：

```
## MEMORY CONTEXT
{memory_context}

If Memory context is provided above:
- Browser tasks should align with the known navigation path
- The path shows proven page transitions — keep browser steps consistent with it
- Non-browser tasks (document, code) are not affected by Memory
If no Memory context: decompose from scratch as usual.
```

**删除方法**：`_query_memory_for_subtasks()`（不再逐个 subtask 查 Memory）

### 4.2 执行期间动态 Memory 查询（P0 — 已实现）

**状态**：已完整实现，不需要代码改动。仅需在 BrowserAgent system prompt 中补充说明。

**已实现的自动化流水线**：

```
ListenBrowserAgent.set_current_url(url)        # URL 变化触发
  → _start_page_operations_query(url)           # 后台异步发起 Memory 查询（去重）
    → MemoryToolkit.query_page_operations(url)  # 调用 Memory API
      → agent.cache_page_operations(url, ops)   # 缓存结果

ListenChatAgent.step() / astep()               # 每次 LLM 调用前
  → _check_and_inject_page_operations_cache()   # 检查缓存，有就注入 message
    → "## Available Page Operations (from Memory)\n{ops}"
```

**关键特性**：
- **全自动**：URL 变化即触发，不依赖 Agent 主动调用
- **去重**：已查过的 URL 不重复查询（`_page_ops_checked_urls`）
- **异步**：后台查询，不阻塞 Agent 执行
- **缓存失效**：URL 变化时自动清除旧缓存

**注入到 LLM 的内容示例**（来自 `debug_memory_llm_context.py` 测试）：

```
## Page Operations (2 recorded)

1. "用户在亚马逊网站上进行商品搜索操作。"
   - click searchbox "Search Amazon"
   - click textbox

**Navigation options:**
- 系统自动导航，从亚马逊首页跳转到AI戒指产品搜索结果页面。
```

**补充改动**：在 BrowserAgent 的 `<capabilities>` 段增加一行：
```
- Use the memory toolkit to query known page operations when exploring unfamiliar pages.
```

**两层配合关系**：
```
4.1 Memory-First 分解 → workflow_guide（整体路径）: "首页 → 搜索结果 → 详情页"
4.2 动态 page operations（自动注入）: "当前页面可以: 点搜索框、选分类..."
```
- 4.1 给 Agent 全局视野（整条路径去哪里）
- 4.2 给 Agent 局部信息（当前页面能做什么）

### 4.3 执行监控与动态重规划（P1）

**核心变更**：AMITaskExecutor 增加结果校验和动态调整能力。

#### 4.3.1 结果校验

subtask 完成后，检查结果是否满足预期：

```python
async def _verify_subtask_result(self, subtask: AMISubtask) -> bool:
    """检查 subtask 结果是否满足要求。"""
    if not subtask.result:
        return False

    # 简单方案：检查关键信息是否存在
    # 例如 subtask 要求 "提取产品名称"，检查结果中是否有产品名称
    # 未来可用 LLM 做更智能的校验
    return len(subtask.result.strip()) > 0
```

#### 4.3.2 动态重规划

当 subtask 失败或结果偏离时，重新规划剩余任务：

```python
async def _replan_remaining(
    self,
    failed_subtask: AMISubtask,
    remaining_subtasks: List[AMISubtask],
) -> List[AMISubtask]:
    """基于当前状态重新规划剩余任务。"""

    # 收集已完成的上下文
    completed_context = self._summarize_completed_subtasks()

    # 重新查询 Memory（当前状态可能已变化）
    new_memory = await self._planner._query_task_memory(
        f"Continue: {self._user_request}\n\nCompleted so far:\n{completed_context}"
    )

    # 重新分解剩余工作
    remaining_task = self._describe_remaining_work(failed_subtask, remaining_subtasks)
    new_subtasks = await self._planner.decompose_and_query_memory(remaining_task)

    return new_subtasks
```

#### 4.3.3 触发条件

```python
# 在 AMITaskExecutor.execute() 的主循环中：
success = await self._execute_subtask(subtask, agent)

if not success and subtask.retry_count > self._max_retries:
    # 重试用尽 → 尝试重规划
    remaining = [s for s in self._subtasks if s.state == SubtaskState.PENDING]
    if remaining and self._allow_replan:
        new_subtasks = await self._replan_remaining(subtask, remaining)
        # 替换剩余 subtasks
        self._replace_remaining_subtasks(new_subtasks)
        continue
```

### 4.4 分级执行策略（P2）

根据 Memory Level 调整 Agent 的执行行为。

**实现方式**：通过 system prompt 动态调整 + 执行参数配置。

#### L1：Replay 模式

```python
# L1 subtask 的额外 prompt 指令
L1_EXECUTION_HINT = """
## Execution Mode: REPLAY (Memory L1)
You have a complete, user-verified workflow. Follow it precisely:
- Execute each step in the exact order given
- If a step fails, report the failure rather than improvising
- Use the provided URLs, selectors, and actions as primary guidance
- Only deviate if the page has clearly changed from the recorded state
"""
```

- 最大步数限制 = workflow 步数 × 1.5
- 每步检查实际 URL/状态是否与 Memory 中的 state 匹配
- 偏离时优先回退到预期路径

#### L2：Guided Exploration 模式

```python
L2_EXECUTION_HINT = """
## Execution Mode: GUIDED (Memory L2)
You have a partial navigation path as reference. Use it as a guide:
- The path shows known pages and transitions between them
- Treat each state as a checkpoint - verify you reach it
- You have freedom in HOW you reach each checkpoint
- If a checkpoint doesn't match reality, skip it and continue
"""
```

- State 节点作为检查点，Agent 可在节点间自由操作
- 到达目标 state 即视为成功

#### L3：Free Exploration 模式

```python
L3_EXECUTION_HINT = """
## Execution Mode: EXPLORE (Memory L3)
No prior workflow exists for this task. Explore freely:
- Use query_page_operations(url) tool to check what's known about pages you visit
- Take a systematic approach: navigate methodically rather than randomly
- If you find a successful path, note it clearly in your response
"""
```

- 增加探索预算（更多允许步数）
- 鼓励使用 `query_page_operations` 工具
- 结果需清晰记录路径（为写回做准备）

**注入位置**：`AMITaskExecutor._build_prompt()` 中根据 `subtask.memory_level` 选择对应 hint。

### 4.5 Memory 写回 / 学习闭环（P1）

**核心变更**：Agent 成功完成任务后，将执行轨迹写回 Memory。

#### 触发条件

| 场景 | 写回内容 | 原因 |
|------|----------|------|
| L3 任务成功 | 完整执行轨迹 | 新路径发现，下次可能 L1 命中 |
| L2 任务发现更优路径 | 差异部分 | 丰富 Memory 图 |
| Agent 发现新页面操作 | 新 IntentSequence | 扩展页面操作菜单 |

#### 执行轨迹收集

```python
# 在 AMITaskExecutor 完成后：
async def _collect_execution_trace(self) -> Optional[List[Dict]]:
    """从已完成的 subtasks 中收集执行轨迹。"""
    trace = []
    for subtask in self._subtasks:
        if subtask.state != SubtaskState.DONE:
            continue
        trace.append({
            "subtask_id": subtask.id,
            "agent_type": subtask.agent_type,
            "content": subtask.content,
            "result": subtask.result,
            "memory_level": subtask.memory_level,
        })
    return trace if trace else None
```

#### 写回 API 调用

```python
async def _write_back_to_memory(self, trace: List[Dict]) -> None:
    """将成功的执行轨迹写回 Memory。"""
    # 从 BrowserAgent 的执行历史中提取 operations
    # （navigate、click、type 等浏览器操作）
    operations = self._extract_browser_operations(trace)

    if not operations:
        return

    await self._memory_toolkit.add_operations(
        operations=operations,
        task_description=self._user_request,
        generate_embeddings=True,
    )
```

#### 写回时机

```python
# AMITaskExecutor.execute() 末尾：
results = await self._execute_all_subtasks()

if results["completed"] > 0 and results["failed"] == 0:
    # 全部成功 → 写回
    trace = await self._collect_execution_trace()
    if trace and self._should_write_back(trace):
        await self._write_back_to_memory(trace)

def _should_write_back(self, trace: List[Dict]) -> bool:
    """判断是否需要写回。"""
    # L3 任务成功 → 一定写回
    if any(t["memory_level"] == "L3" for t in trace):
        return True
    # L2 且路径与 Memory 不同 → 写回
    # L1 按原路径执行 → 不写回（已有）
    return False
```

---

## 5. 实施优先级

| 优先级 | 改进 | 难度 | 影响 | 依赖 |
|--------|------|------|------|------|
| **P0** | 4.1 Memory-First 分解 | 低 | 分解质量大幅提升 | - |
| **P0** | 4.2 执行期间动态 Memory 查询 | 低 | Agent 执行中不再"迷路" | - |
| **P1** | 4.3 执行监控与动态重规划 | 高 | 长程任务核心保障 | P0 |
| **P1** | 4.5 Memory 写回 | 中 | 知识积累闭环 | P0 |
| **P2** | 4.4 分级执行策略 | 中 | 精细化控制 | P0 |

**对长程任务最关键的组合**：P0（准确起点 + 持续导航）+ P1-重规划（偏差修正）。

---

## 6. Memory API 参考

Agent 侧通过 `MemoryToolkit` 调用，底层对应 Cloud Backend API：

| MemoryToolkit 方法 | 后端 API | 用途 |
|-------------------|----------|------|
| `query_task(task)` | `POST /api/v1/memory/query` | 任务级查询（L1/L2/L3） |
| `query_navigation(start, end)` | `POST /api/v1/memory/query` | 导航路径查询 |
| `query_actions(state)` | `POST /api/v1/memory/query` | 页面操作查询 |
| `query_page_operations(url)` | `POST /api/v1/memory/state` | 按 URL 查页面操作 |
| `add_operations(...)` | `POST /api/v1/memory/add` | 写回执行轨迹 |

### 查询结果数据结构

```python
@dataclass
class QueryResult:
    cognitive_phrase: Optional[CognitivePhrase]  # L1: 完整工作流
    states: Optional[List[State]]                # L2: 页面列表
    actions: Optional[List[Action]]              # L2: 导航动作
    intent_sequences: Optional[List[IntentSequence]]  # 页面操作序列
    execution_plan: Optional[List[ExecutionStep]]     # 结构化执行计划

@dataclass
class CognitivePhrase:
    id: str
    description: str
    states: List[State]
    actions: List[Action]
    execution_plan: List[ExecutionStep]

@dataclass
class State:
    id: str
    description: str
    page_url: str
    page_title: str
    intent_sequences: List[IntentSequence]

@dataclass
class IntentSequence:
    id: str
    description: Optional[str]
    intents: List[Intent]
    causes_navigation: bool
    navigation_target_state_id: Optional[str]
```

---

## 7. 设计总结

```
改进前:
  分解(LLM 盲猜) → 查 Memory(事后补) → 静态注入 → 执行(无反馈) → 结束(不学习)

改进后:
  查 Memory(先看地图) → 分解(有据可依) → 动态查询(持续导航) → 重规划(偏差修正) → 写回(学习闭环)
```

核心原则不变：**Memory 提供信息，Agent 做决策**。改进的是信息提供的时机、频率和闭环。
