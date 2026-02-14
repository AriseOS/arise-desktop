# Online Learning: 从任务执行中自动生成 CognitivePhrase

## 概述

任务成功完成后，从 tool use + agent thinking 中自动生成 CognitivePhrase，记录"这类任务怎么组织"的认知。

**一句话**：Agent 做完一件事 → 收集执行数据 → LLM 提取有效路线 → 查 Memory 对接图实体 → 生成 CognitivePhrase。

## 目标

现有 online learning 只写入细粒度实体（States/Actions/IntentSequences），不生成 CognitivePhrase。CognitivePhrase 当前只能通过用户手动录制产生。

本设计让 agent 自己成功完成的任务也能自动生成 CognitivePhrase，形成闭环：
- 首次任务：无 Memory → agent 探索完成 → **自动生成 CognitivePhrase**
- 后续类似任务：PlannerAgent recall_phrases 命中 → L1 级别规划 → 更快更准

## 架构分层

```
Agent 层 (Desktop App)                    Memory 层 (Common)
┌─────────────────────────┐              ┌─────────────────────────┐
│  AMITaskExecutor        │              │  planner/               │  ← 任务前：读
│    ├─ 执行子任务        │              │    PlannerAgent         │
│    ├─ 收集执行数据 ←NEW │              │    (recall, search,     │
│    └─ 调用 Learner ←NEW │──────────────│     explore)            │
│                         │              │                         │
│  ExecutionDataCollector │              │  learner/          ←NEW │  ← 任务后：写
│    └─ 提取+压缩 messages│──────────────│    LearnerAgent         │
│                         │              │    (analyze, build,     │
│                         │              │     store phrase)        │
└─────────────────────────┘              └─────────────────────────┘
```

- **Planner**：任务开始前，从 Memory 读取知识辅助规划
- **Learner**：任务完成后，从执行数据中学习新知识写入 Memory
- **add_to_memory 不动**：Learner 是独立接口，不修改已有的 operations → Memory 流水线

## 模块 1：ExecutionDataCollector（Agent 侧）

**位置**：`src/clients/desktop_app/ami_daemon/base_agent/core/execution_data_collector.py`（新文件）

### 职责

从每个子任务的 `agent._messages` 中提取 tool use + thinking，压缩后保存。

### 数据存储

Collector 是**临时内存缓冲区**，不做持久化。生命周期跟随 `AMITaskExecutor.execute()` 一次调用：
1. 每个子任务完成后，从 `agent.get_messages()` 提取 `SubtaskExecutionData`，保存为 collector 实例属性（Python 对象）
2. 所有子任务完成后，`build_task_data()` 汇总成 `TaskExecutionData`
3. 立即通过 `cloud_client.learn_from_execution()` 发送到 Cloud Backend
4. LearnerAgent 处理完后，有用知识写入 CognitivePhrase，原始执行数据丢弃

类似 `BehaviorRecorder` 录制 operations 也是先存内存，最后一次性发给 `add_to_memory` API。

### 数据来源

`agent.get_messages()` 返回 Anthropic 原生格式的完整对话：

```python
[
  {"role": "user", "content": "prompt..."},
  {"role": "assistant", "content": [
      {"type": "text", "text": "让我访问亚马逊"},                    # thinking
      {"type": "tool_use", "name": "browser_visit_page",
       "input": {"url": "https://amazon.com/"}},                     # tool call
  ]},
  {"role": "user", "content": [
      {"type": "tool_result", "tool_use_id": "...",
       "content": "Page loaded successfully..."},                     # tool result
  ]},
  {"role": "assistant", "content": [
      {"type": "text", "text": "成功访问了首页，看到搜索框"},          # thinking（对上一步的判断）
      {"type": "tool_use", "name": "browser_type",
       "input": {"ref": "e91", "text": "ai glasses"}},
  ]},
  ...
]
```

### Hook 点

在 `AMITaskExecutor._execute_subtask()` 中，`await agent.astep(prompt)` 返回后（line 477）。此时：
- `_messages` 完整保存着当前子任务的全部对话
- `reset()` 要到下一个子任务开始时才调用
- online learning 的 `_save_recorded_operations()` 已经在这里执行

### 压缩规则

从 `_messages` 中提取，生成 `List[ToolUseRecord]`：

```python
@dataclass
class ToolUseRecord:
    """一次 tool call 的压缩记录。"""
    thinking: str       # agent 在调用前的思考（为什么做这个操作）
    tool_name: str      # 工具名
    input_summary: str  # 压缩后的输入参数
    success: bool       # 是否成功
    result_summary: str # 压缩后的结果（截断 200 字符）
    judgment: str       # agent 在调用后的思考（对结果的判断）
    current_url: str    # 操作后的当前页面 URL（从 tool result 中提取）
```

**`current_url` 提取**：

每个 browser tool 的返回值由 `_build_action_result()` 构建，固定包含 `_get_page_context()` 输出的当前页面 URL + title。格式为：

```
Current Page: Amazon.com : AI glasses
URL: https://www.amazon.com/s?k=AI+glasses...
```

Collector 从 tool result 文本中用正则提取 `URL: (.+)` 即可获得操作后的当前 URL。

这个 URL 是关键数据——它让 LLM 能看到 click 等操作是否触发了页面跳转：

```
browser_visit_page(url=amazon.com)     → current_url: https://www.amazon.com/
browser_type(ref=e91, text=ai glasses) → current_url: https://www.amazon.com/       （未跳转）
browser_enter()                         → current_url: https://www.amazon.com/s?k=ai+glasses  （跳转了！）
browser_click(ref=e4389)               → current_url: https://www.amazon.com/dp/xxx  （新页面！）
browser_switch_tab(tab_id=tab-001)     → current_url: https://www.amazon.com/s?k=ai+glasses  （切回列表页）
```

不需要改 browser toolkit 代码，URL 信息已经在 tool result 中。

**`input_summary` 压缩规则**（按工具类型）：

| 工具 | 保留 | 去掉 |
|---|---|---|
| `browser_visit_page` | `url` | — |
| `browser_click` | `ref` | — |
| `browser_type` | `ref`, `text` | — |
| `browser_select` | `ref`, `value` | — |
| `browser_enter/back/scroll` | 全部（本来就小） | — |
| `browser_get_page_snapshot` | 跳过，不记录 | 整个 tool call |
| `write_to_file` / `append_to_file` | `filename` / `title` | `content` |
| `write_excel` | `filepath` | `data`, `headers` |
| `read_file` | 文件名（去绝对路径前缀） | — |
| `shell_exec` | `command`（截断 200 字符） | — |
| `search_google` | `query` | — |
| `send_message` | 跳过，不记录 | 整个 tool call |
| `replan_*` | 跳过，不记录 | 整个 tool call |

**`result_summary` 压缩规则**：
- 成功：截断到 200 字符
- 失败：保留错误信息（以 `"Tool execution failed:"` 开头的）
- `browser_get_page_snapshot` 结果：跳过（已跳过该 tool call）

**`thinking` 和 `judgment` 提取**：
- `thinking`：tool_use 块之前的 text 块（同一个 assistant message 内）
- `judgment`：tool_result 之后的下一个 assistant message 的 text 块

### 子任务执行数据

```python
@dataclass
class SubtaskExecutionData:
    """一个子任务的完整执行数据。"""
    subtask_id: str
    content: str                      # 子任务描述
    agent_type: str                   # browser / document / code / multi_modal
    depends_on: List[str]
    state: str                        # DONE / FAILED
    result_summary: str               # subtask.result 截断 500 字符
    tool_records: List[ToolUseRecord] # 压缩后的 tool use 序列
```

### 任务级执行数据

```python
@dataclass
class TaskExecutionData:
    """完整任务的执行数据，传给 Learner。"""
    task_id: str
    user_request: str                           # 用户原始请求
    subtasks: List[SubtaskExecutionData]        # 所有子任务数据
    completed_count: int
    failed_count: int
    total_count: int
```

### 重复子任务压缩

动态子任务（`4_dyn_1_1`, `4_dyn_1_2`, `4_dyn_1_3`）是同一类操作的重复执行。压缩规则：
- 识别：subtask_id 以 `{parent_id}_dyn_` 开头的为同一组
- 只保留第一个的完整 `tool_records`
- 其余只保留 `subtask_id` + `state`
- 标注 `repeat_count: N`

### 改动文件

**`ami_task_executor.py`**：
- `_execute_subtask()` 中，`astep()` 返回后，调用 `ExecutionDataCollector.collect_subtask_data(agent, subtask)`
- `execute()` 完成后，汇总所有子任务数据为 `TaskExecutionData`

## 模块 2：LearnerAgent（Memory 侧）

**位置**：`src/common/memory/learner/`（新目录）

### 目录结构

```
learner/
├── __init__.py
├── models.py           # LearnResult, LearningPlan
├── tools.py            # LearnerTools（查询 Memory 实体）
├── prompts.py          # LEARNER_SYSTEM_PROMPT
└── learner_agent.py    # LearnerAgent 主类
```

### 与 Planner 的对称关系

| | Planner | Learner |
|---|---|---|
| 时机 | 任务开始前 | 任务完成后 |
| 输入 | 用户请求文本 | TaskExecutionData |
| 输出 | MemoryPlan（读取建议） | LearnResult（写入结果） |
| LLM 工具 | recall_phrases, search_states, explore_graph | recall_phrases, find_states_by_urls, get_state_sequences, verify_action |
| 核心策略 | Coverage 判断 + workflow_guide 注入 | Recall-First + Coverage 判断 + Phrase 创建 |
| 最终动作 | 返回 workflow_guide | 创建 CognitivePhrase + auto-share |

### LearnerAgent 接口

```python
class LearnerAgent:
    def __init__(
        self,
        memory: WorkflowMemory,          # 私有 Memory
        llm_provider: AnthropicProvider,  # LLM 调用
        embedding_service,                # Embedding 生成
    ):
        ...

    async def learn(self, execution_data: TaskExecutionData) -> LearnResult:
        """从任务执行数据中学习，生成 CognitivePhrase。"""
        ...
```

### LearnerTools

```python
class LearnerTools:
    """LLM 在分析过程中可调用的 Memory 查询工具。"""

    async def recall_phrases(self, query: str, top_k: int = 5) -> str:
        """搜索已有的 CognitivePhrases（embedding 相似度）。

        Recall-First：LLM 第一步就调用此工具，判断已有 phrases 是否已覆盖当前任务。
        返回每个 phrase 的完整信息（state_path, execution_plan, actions, similarity_score）。
        """

    async def find_states_by_urls(self, urls: List[str]) -> str:
        """给定 URL 列表，查找 Memory 中对应的 States。

        使用 URL index O(1) 查找。
        返回每个 URL 对应的 State（id, description, page_url, domain）或 "not found"。
        """

    async def get_state_sequences(self, state_id: str) -> str:
        """查询某个 State 上的所有 IntentSequences。

        返回该 State 上所有 IntentSequence 的摘要（id, description, intent 数量）。
        """

    async def verify_action(self, source_state_id: str, target_state_id: str) -> str:
        """验证两个 States 之间是否存在 Action。

        返回 Action 信息或 "no action found"。
        """
```

> **注意**：原设计中的 `check_similar_phrases` 已重命名为 `recall_phrases`，与 PlannerAgent 对称。功能从"去重检查"升级为"Recall-First 工作流"的核心入口。

### LLM 的工作流程（Recall-First）

LLM 收到 `TaskExecutionData` 的压缩表示，遵循 **Recall-First** 工作流：

**Step 1：Recall 已有 Phrases**

LLM **首先**调用 `recall_phrases(user_request + subtask summaries)` 搜索已有的 CognitivePhrases。

**Step 2：Coverage 判断**

LLM 阅读每个 recalled phrase 的完整信息（state_path, execution_plan），判断每个 browser 子任务是否已被覆盖。判断标准是 **workflow pattern** 而非具体搜索词（如 "Search products on Amazon" 覆盖 "Search for headphones on Amazon"）。

- **如果所有 browser 子任务都已覆盖** → 输出空 learning_plan（0 个 phrase_candidate），**提前退出**（节省 tokens）
- **如果有未覆盖的子任务** → 继续分析

**Step 2.5：按 Method 分组**

对于未覆盖的 browser 子任务，识别不同的工作流模式。同一类操作（如重复提取不同产品页面信息）→ 一个 phrase。

**Step 3：分析未覆盖部分**

对每个未覆盖的子任务：
1. 提取有效 URL（排除弯路/探索/试错）
2. 调用 `find_states_by_urls` 查找 Memory 中的 States
3. 调用 `verify_action` 确认 States 间有 Action 连接
4. 可选调用 `get_state_sequences` 查看已有的页面操作

**Step 4：输出学习计划**

LLM 输出 `<learning_plan>` XML，支持 **0 到 N 个 phrase_candidate**：

```xml
<learning_plan>
  <coverage_judgment>
    Recalled "Amazon Product Search" (0.87): covers sub_1 and sub_2 (same search+sort pattern).
    sub_3 (Google Shopping comparison) is new — no existing phrase.
  </coverage_judgment>

  <phrase_candidate>
    <should_create>true</should_create>
    <description>在 Google Shopping 上搜索并比较商品价格</description>
    <label>Google Shopping Price Compare</label>
    <effective_path>
      <state state_id="state_abc" />
      <state state_id="state_def" />
    </effective_path>
    <reason>New workflow for Google Shopping, not covered by existing phrases.</reason>
  </phrase_candidate>
</learning_plan>
```

> **与原设计的关键差异**：原设计将去重检查放在 Phase 3（分析之后），实际实现将 recall 放在 Step 1（分析之前），实现了 early exit 优化。

### 代码构建 CognitivePhrase

LLM 输出 `<learning_plan>` 后，**代码**（不是 LLM）负责：

1. 从 `<effective_path>` 提取 State IDs → `state_path`
2. 相邻 States 查 Action → `action_path`
3. 每个 State 查 IntentSequences → `execution_plan`（调用 `_build_execution_plan` 或等效逻辑）
4. 用 LLM 输出的 `description` / `label` 填充字段
5. 生成 embedding
6. 创建 CognitivePhrase 写入 Memory

这一步可以复用 `WorkflowProcessor._create_cognitive_phrase()` 的逻辑，或者直接在 Learner 中构建。

### 数据模型

```python
@dataclass
class PhraseCandidate:
    """单个 phrase 候选。"""
    should_create: bool
    description: str
    label: str
    effective_state_ids: List[str]    # 有效路径上的 State IDs
    reason: str

@dataclass
class LearningPlan:
    """LLM 输出的学习计划（支持多个候选）。"""
    coverage_judgment: str             # 覆盖判断推理
    candidates: List[PhraseCandidate]  # 0..N 个 phrase 候选

@dataclass
class LearnResult:
    """Learner 的最终输出。"""
    success: bool
    phrase_created: bool
    phrase_ids: List[str] = field(default_factory=list)        # 新创建的 CognitivePhrase IDs
    shared_phrase_ids: List[str] = field(default_factory=list) # 分享到公共 Memory 的 IDs
    reason: str = ""
```

## 触发条件

不是每次任务完成都需要学习。分两层判断：

### Executor 侧（`_should_trigger_learning()`）

1. 未被停止/取消
2. 有 `cloud_client` 和 `user_id`
3. 至少有 1 个 browser 子任务
4. 子任务总数 ≥ 2（单步任务不值得生成 CognitivePhrase）
5. **所有** browser 子任务成功（`SubtaskState.DONE`）

### LearnerAgent 侧（Recall-First 工作流）

6. `recall_phrases` 未找到完全覆盖的已有 phrase（LLM 判断 coverage）

条件 1-5 是廉价的前置检查（不调 LLM），条件 6 在 LearnerAgent 内部通过 Recall-First 工作流判断。

## 调用链路

```
AMITaskExecutor.execute()
  ├─ collector = ExecutionDataCollector()
  ├─ 执行所有子任务（支持并行）
  │   ├─ 每次 retry：fresh BehaviorRecorder（录制 → 写入 State/Action/IntentSequence）
  │   └─ 成功后：collector.collect_subtask_data(agent, subtask)  ← 提取 messages
  │
  └─ 全部完成后：
        if _should_trigger_learning():
            task_data = collector.build_task_data(task_id, user_request, subtasks)
            # Fire-and-forget：不阻塞任务完成
            asyncio.create_task(_learn_from_execution(task_data))
```

`_learn_from_execution()` 内部：
1. Dump `task_data` 到 `~/.ami/logs/learner_input_{task_id}_{timestamp}.json`（调试用）
2. 调用 `cloud_client.learn_from_execution(user_id, execution_data)`

Cloud Backend API：

```
POST /api/v1/memory/learn
Body: { user_id, execution_data: TaskExecutionData }
Response: { success, phrase_created, phrase_ids, shared_phrase_ids, reason }
```

该 API 内部：
1. 获取用户的 private Memory
2. 创建 LearnerAgent（使用 cached provider 和 embedding service）
3. 调用 `learner.learn(execution_data)`
4. Auto-share 创建的 phrases 到 public memory
5. 返回 LearnResult

## 不需要改动的部分

| 模块 | 原因 |
|---|---|
| **BehaviorRecorder** | 继续录 operations，不受影响 |
| **WorkflowProcessor** | 继续处理 operations → 图实体，不受影响 |
| **`add_to_memory` API** | 向后兼容，Learner 是独立 API |
| **PlannerAgent** | 不变，依然从 Memory 读取 |
| **CognitivePhrase 模型** | 不需要新增字段，现有结构足够 |
| **Memory 图模型** | State/Action/IntentSequence 不变 |

## 数据流示例

以"帮我看看亚马逊上卖的最好的 5 款 AI 眼镜"为例：

### 执行阶段（已有）

```
子任务 1 [browser]: 搜索 ai glasses → DONE
  operations → Memory: State(amazon首页), State(搜索结果页), Action(首页→搜索结果页)

子任务 2 [browser]: 按 Best Sellers 排序 → DONE
  operations → Memory: State(排序后结果页), Action(搜索结果页→排序后结果页)

子任务 3 [browser]: 提取数据 → write_to_file → DONE
  operations → Memory: IntentSequences(排序后结果页上的数据提取操作)

子任务 4 [document]: 生成 Excel → DONE
  无 operations（非浏览器）
```

### 学习阶段（新增）

**Step 1：ExecutionDataCollector 收集数据**

```python
TaskExecutionData(
    task_id="91e4e28e",
    user_request="帮我看看亚马逊上卖的最好的 5 款 AI 眼镜",
    subtasks=[
        SubtaskExecutionData(
            subtask_id="1",
            content="访问 amazon.com，搜索 ai glasses",
            agent_type="browser",
            state="DONE",
            tool_records=[
                ToolUseRecord(
                    thinking="我会访问亚马逊网站搜索 ai glasses",
                    tool_name="browser_visit_page",
                    input_summary="url=https://www.amazon.com/",
                    success=True,
                    result_summary="Page loaded: Amazon.com",
                    judgment="成功访问了亚马逊首页，看到搜索框",
                ),
                ToolUseRecord(
                    thinking="在搜索框输入关键词",
                    tool_name="browser_type",
                    input_summary="ref=e91, text=ai glasses",
                    success=True,
                    result_summary="Text typed successfully",
                    judgment="输入成功，按 Enter 搜索",
                ),
                ToolUseRecord(
                    thinking="按 Enter 执行搜索",
                    tool_name="browser_enter",
                    input_summary="",
                    success=True,
                    result_summary="Navigation complete",
                    judgment="搜索完成，页面显示了 AI 眼镜产品列表",
                ),
            ],
        ),
        SubtaskExecutionData(
            subtask_id="2",
            content="按 Best Sellers 排序",
            agent_type="browser",
            state="DONE",
            tool_records=[
                ToolUseRecord(
                    thinking="找到排序下拉菜单，选择 Best Sellers",
                    tool_name="browser_select",
                    input_summary="ref=e247, value=Best Sellers",
                    success=True,
                    result_summary="Selected: Best Sellers",
                    judgment="成功按销量排序",
                ),
            ],
        ),
        SubtaskExecutionData(
            subtask_id="3",
            content="提取前5款产品信息，保存到 md 文件",
            agent_type="browser",
            state="DONE",
            tool_records=[
                ToolUseRecord(
                    thinking="从当前页面提取产品信息",
                    tool_name="write_to_file",
                    input_summary="filename=ai_glasses_data.md",
                    success=True,
                    result_summary="File written successfully",
                    judgment="数据已保存到文件",
                ),
            ],
        ),
        SubtaskExecutionData(
            subtask_id="4",
            content="读取 md 生成 Excel 报告",
            agent_type="document",
            state="DONE",
            tool_records=[
                ToolUseRecord(thinking="读取数据文件", tool_name="read_file",
                    input_summary="filename=ai_glasses_data.md", success=True, ...),
                ToolUseRecord(thinking="尝试 write_excel", tool_name="write_excel",
                    input_summary="filepath=ai_glasses_report.xlsx", success=False,
                    result_summary="Tool execution failed: ...", ...),
                ToolUseRecord(thinking="改用 python 脚本", tool_name="shell_exec",
                    input_summary="command=cat > create_excel.py << 'EOF'...",
                    success=True, ...),
                ToolUseRecord(thinking="执行脚本", tool_name="shell_exec",
                    input_summary="command=python3 create_excel.py",
                    success=True, result_summary="Excel created successfully", ...),
            ],
        ),
    ],
    completed_count=4,
    failed_count=0,
    total_count=4,
)
```

**Step 2：LearnerAgent 分析**

LLM 阅读 TaskExecutionData，调用工具：

```
→ find_states_by_urls(["https://www.amazon.com/",
                        "https://www.amazon.com/s?k=ai+glasses...",
                        "https://www.amazon.com/s?k=ai+glasses&s=exact-aware-popularity-rank..."])
← state_abc (Amazon 首页), state_def (搜索结果页), state_ghi (排序后结果页)

→ verify_action("state_abc", "state_def")
← Action found: type=navigate, trigger=search

→ verify_action("state_def", "state_ghi")
← Action found: type=navigate, trigger=sort

→ get_state_sequences("state_abc")
← IntentSequence: "搜索商品" (click search box, type keyword, press enter)

→ get_state_sequences("state_ghi")
← IntentSequence: "提取产品数据" (scroll, extract text, write to file)

→ check_similar_phrases("在亚马逊搜索商品按销量排序提取数据生成报告")
← No similar phrases found
```

LLM 输出：

```xml
<learning_plan>
  <should_create_phrase>true</should_create_phrase>
  <description>在亚马逊上搜索某品类商品，按销量排序，提取前N款产品信息并生成Excel报告</description>
  <label>Amazon Best Sellers Search and Report</label>
  <effective_path>
    <state url="https://www.amazon.com/" state_id="state_abc" />
    <state url="https://www.amazon.com/s?k=ai+glasses..." state_id="state_def" />
    <state url="https://www.amazon.com/s?k=ai+glasses&s=exact-aware-popularity-rank..." state_id="state_ghi" />
  </effective_path>
  <reason>首次完成"亚马逊商品排行搜索"类任务，Memory 中无类似认知</reason>
</learning_plan>
```

**Step 3：代码构建 CognitivePhrase**

```python
state_path = ["state_abc", "state_def", "state_ghi"]
action_path = ["navigate", "navigate"]  # 从 verify_action 结果
execution_plan = [
    ExecutionStep(index=1, state_id="state_abc",
                  in_page_sequence_ids=["seq_search"],
                  navigation_action_id="action_abc_def"),
    ExecutionStep(index=2, state_id="state_def",
                  in_page_sequence_ids=["seq_sort"],
                  navigation_action_id="action_def_ghi"),
    ExecutionStep(index=3, state_id="state_ghi",
                  in_page_sequence_ids=["seq_extract"],
                  navigation_action_id=None),
]
# → CognitivePhrase 写入 Memory
```

### 下次类似任务

用户："帮我看看亚马逊上卖的最好的 10 款望远镜"

```
PlannerAgent.recall_phrases("亚马逊上卖的最好的望远镜")
  → 命中 CognitivePhrase "Amazon Best Sellers Search and Report"
  → L1 级别匹配
  → workflow_guide 注入到 browser 子任务
  → 更快完成
```

## 实现清单

### Phase 1：数据收集（Agent 侧）

| # | 文件 | 改动 |
|---|---|---|
| 1 | `execution_data_collector.py`（新） | 数据模型 + 压缩逻辑 |
| 2 | `ami_task_executor.py` | hook：astep() 后收集数据，execute() 后触发学习 |

### Phase 2：学习写入（Memory 侧）

| # | 文件 | 改动 |
|---|---|---|
| 3 | `learner/__init__.py`（新） | 模块入口 |
| 4 | `learner/models.py`（新） | LearningPlan, LearnResult |
| 5 | `learner/tools.py`（新） | LearnerTools（4 个 Memory 查询工具） |
| 6 | `learner/prompts.py`（新） | LEARNER_SYSTEM_PROMPT |
| 7 | `learner/learner_agent.py`（新） | LearnerAgent 主类 |

### Phase 3：API 连接

| # | 文件 | 改动 |
|---|---|---|
| 8 | `cloud_backend/main.py` | 新增 `/api/v1/memory/learn` endpoint |
| 9 | `cloud_client.py` | 新增 `learn_from_execution()` 方法 |

## 开放问题

1. **非浏览器子任务在 CognitivePhrase 中怎么表达？** 当前 CognitivePhrase 的 execution_plan 完全绑定 State（页面）。document 子任务没有 State。本次设计先只覆盖浏览器部分，非浏览器子任务的认知记录留待后续。

2. ~~**异步还是同步？**~~ **已解决**：采用 fire-and-forget（`asyncio.create_task`），不阻塞任务完成。学习结果可能在下一次 PlannerAgent 查询前尚未写入，但这是可接受的权衡。

3. **失败任务要不要学？** 当前实现要求所有 browser 子任务成功才触发学习。部分成功（3/4 子任务成功）可能有值得学的路径。留待后续。

4. **CognitivePhrase 质量评估？** 自动生成的 phrase 质量可能不如人工录制的。可以通过 `success_count` 追踪后续使用效果，低效的 phrase 自动降权。
