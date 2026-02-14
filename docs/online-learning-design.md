# Online Learning：Agent 边做边学

## 概述

Agent 在执行多个 browser 子任务时，利用 BehaviorRecorder 在浏览器层记录所有操作事件。每个子任务完成后，将录制的 operations 写入 Memory。后续子任务访问相同页面时，Layer 2 自动查到刚写入的 page operations，agent 即可参考。

**一句话**：录制 → 写入 Memory → 下一个子任务自动受益。

## 为什么用 BehaviorRecorder 而不是 Tool Call 层

我们评估了三个候选层：

| 层 | 数据完整性 | 主要缺陷 |
|---|---|---|
| **Tool Call 层** | 差 | 只有 `ref`，没有 URL、role、text，拼不出 State→Action→State 图 |
| **ActionExecutor 层** | 中 | click 有 element_diag，但 type/select/scroll 缺 URL 和 metadata；需改每个 Toolkit 方法 |
| **BehaviorRecorder 层** | 好 | 每个事件都有 URL、role、text、timestamp；输出格式直接兼容 Memory API |

**BehaviorRecorder 的优势**：

1. **数据完整** — 通过 CDP + JS injection，每个操作都有完整的 URL、element role、text、timestamp
2. **导航自动检测** — CDP `Page.frameNavigated` 自动捕获所有页面跳转（包括新 tab）
3. **格式零转换** — `recorder.operations` 的输出格式就是 Memory API 的 `operations` 输入格式
4. **已验证** — BehaviorRecorder 已在用户录制场景下生产使用
5. **Playwright 操作可被捕获** — Playwright 触发的是真实 DOM 事件，JS event listener 正常触发
6. **无侵入性** — 纯观察者模式，不改 ActionExecutor、不改 BrowserToolkit、不改 agent

## 改动点

### 1. AMITaskExecutor：在 browser 子任务执行前后管理 recorder

**文件**：`src/clients/desktop_app/ami_daemon/base_agent/core/ami_task_executor.py`

#### 1.1 新增构造函数参数

```python
def __init__(
    self,
    task_id: str,
    task_state: Any,
    agents: Dict[str, "AMIAgent"],
    max_retries: int = 2,
    user_request: str = "",
    # --- 新增 ---
    cloud_client: Optional[Any] = None,
    user_id: Optional[str] = None,
):
    # ...existing code...
    self._cloud_client = cloud_client
    self._user_id = user_id
```

#### 1.2 改动 `_execute_subtask()` 流程

Recorder 在 **retry loop 内部**创建，每次重试都使用新 recorder，避免失败尝试的 operations 污染：

```python
async def _execute_subtask(self, subtask: AMISubtask) -> bool:
    agent = self._agents.get(subtask.agent_type)
    # ...existing validation...

    agent.reset()
    recorder = None

    try:
        while subtask.retry_count <= self._max_retries:
            try:
                # --- 每次重试都创建新 recorder ---
                if subtask.agent_type == "browser":
                    recorder = await self._start_behavior_recorder(agent=agent)

                response = await agent.astep(prompt)
                subtask.state = SubtaskState.DONE

                # --- 子任务成功，保存录制的操作到 Memory ---
                if recorder:
                    await self._save_recorded_operations(recorder, subtask)

                return True

            except Exception as e:
                # --- 失败时停止 recorder，丢弃 operations ---
                if recorder:
                    await self._stop_behavior_recorder(recorder)
                    recorder = None
                subtask.retry_count += 1
                ...
    finally:
        # --- 最后兜底：停止 recorder 释放 CDP session ---
        if recorder:
            await self._stop_behavior_recorder(recorder)
```

#### 1.3 新增三个私有方法

```python
async def _start_behavior_recorder(self, agent: Optional["AMIAgent"] = None) -> Optional["BehaviorRecorder"]:
    """为 browser 子任务启动 BehaviorRecorder。"""
    try:
        from ...tools.eigent_browser.behavior_recorder import BehaviorRecorder

        # 优先从 agent 的 BrowserToolkit 获取 session（支持并行执行，每个 agent 独立 session）
        session = None
        if agent:
            tool = agent.get_tool("browser_get_page_snapshot")
            if tool:
                toolkit = tool.func.__self__
                session = await toolkit._get_session()

        # 兜底：通过 task_id 查找共享 session
        if session is None:
            from ...tools.eigent_browser.browser_session import HybridBrowserSession
            session = await HybridBrowserSession.get_session(session_id=self.task_id)

        recorder = BehaviorRecorder(enable_snapshot_capture=False)  # 不需要 DOM snapshot
        await recorder.start_recording(session)
        return recorder
    except Exception as e:
        logger.warning(f"[OnlineLearning] Failed to start recorder: {e}")
        return None


async def _stop_behavior_recorder(self, recorder: "BehaviorRecorder") -> None:
    """停止 recorder。"""
    try:
        await recorder.stop_recording()
    except Exception as e:
        logger.warning(f"[OnlineLearning] Failed to stop recorder: {e}")


async def _save_recorded_operations(
    self,
    recorder: "BehaviorRecorder",
    subtask: "AMISubtask",
) -> None:
    """将 recorder 录制的 operations 写入 Memory。"""
    if not self._cloud_client or not self._user_id:
        logger.debug("[OnlineLearning] No cloud_client or user_id, skipping memory save")
        return

    operations = recorder.operations
    if not operations:
        logger.debug("[OnlineLearning] No operations recorded, skipping")
        return

    try:
        logger.info(
            f"[OnlineLearning] Saving {len(operations)} operations to memory "
            f"(subtask={subtask.id})"
        )
        result = await self._cloud_client.add_to_memory(
            user_id=self._user_id,
            operations=operations,
            session_id=f"{self.task_id}_{subtask.id}",
            generate_embeddings=True,
            skip_cognitive_phrase=True,  # 防止 Runtime 阶段创建 CognitivePhrase，由 Post-Execution 阶段统一创建
        )
        logger.info(f"[OnlineLearning] Memory save result: {result}")
    except Exception as e:
        logger.warning(f"[OnlineLearning] Failed to save to memory: {e}")
```

**关键设计决策**：

- **`enable_snapshot_capture=False`**：不需要 DOM snapshot，agent 已经有 page snapshot 系统
- **`session_id=f"{task_id}_{subtask_id}"`**：每个子任务一个独立的 session_id，使图实体按子任务分开
- **`skip_cognitive_phrase=True`**：Runtime Learning 只写入 State/Action/IntentSequence，CognitivePhrase 由 Post-Execution Learning 统一创建
- **只在 `subtask.state == DONE` 时保存**：失败子任务的操作不写入 Memory
- **每次 retry 创建新 recorder**：recorder 在 retry loop 内部创建，失败尝试的 operations 被丢弃
- **从 agent 的 BrowserToolkit 获取 session**：支持并行执行，每个 agent 有独立的 browser session
- **try-except 包裹所有 recorder 操作**：recorder 失败不影响主任务执行
- **`finally` 中 stop_recording**：确保 recorder 资源释放，防止 CDP session 泄漏

### 2. AMIBrowserAgent：清除 page operations 缓存

**文件**：`src/clients/desktop_app/ami_daemon/base_agent/core/ami_browser_agent.py`

**当前问题**：

`_page_ops_checked_urls` 记录了已查询过的 URL。`agent.reset()` 只清 `_messages` 和 `_step_count`，**不清 `_page_ops_checked_urls`**。

子任务 1 写入了新 Memory → 子任务 2 的 agent 访问同一 URL → URL 在 `_page_ops_checked_urls` 中 → 跳过查询 → **看不到新 Memory**。

**改动**：override `reset()` 清除缓存。

```python
def reset(self) -> None:
    """Reset conversation history and page operations cache."""
    super().reset()
    self._page_ops_checked_urls.clear()
    self._page_ops_inflight.clear()
    self._cached_page_operations = None
    self._cached_page_operations_url = None
    self._cached_page_operations_ids = None
```

### 3. quick_task_service.py：传入 cloud_client 和 user_id

**文件**：`src/clients/desktop_app/ami_daemon/services/quick_task_service.py`

在创建 executor 时传入新参数（line ~1856）：

```python
executor = AMITaskExecutor(
    task_id=task_id,
    task_state=state,
    agents=agents_dict,
    user_request=current_question,
    cloud_client=self._cloud_client,   # 新增
    user_id=self._user_id,             # 新增
)
```

### 4. 不需要改动的部分

| 模块 | 为什么不用改 |
|---|---|
| **BehaviorRecorder** | 已有完整的事件捕获能力，支持 Playwright 操作 |
| **Memory API** (`/api/v1/memory/add`) | 已接受 operations 格式，有完整处理流水线 |
| **WorkflowProcessor** | 已有 State / IntentSequence / Action 去重机制 |
| **Layer 2 查询** | `query_page_operations()` 已按 URL 查询所有 IntentSequence |
| **`_enrich_message()`** | 已自动注入 cached page operations |
| **ActionExecutor** | 不需要改返回结构 |
| **BrowserToolkit** | 不需要改任何方法 |
| **Ontology** | 不需要新实体或新字段 |

## 数据流示例

以"给 10 个人发邮件"为例：

### 子任务 1 执行（首次，无 Memory）

```
1. executor._start_behavior_recorder(agent)
   → BehaviorRecorder.start_recording(shared_session)
   → CDP session 建立，JS tracker 注入到所有 tab

2. agent.astep(prompt) 开始执行：
   - browser_visit_page("https://mail.google.com")
     → Playwright 导航 → CDP Page.frameNavigated 触发
     → recorder 记录: {"type": "navigate", "url": "https://mail.google.com", ...}

   - browser_click(ref="e5")  // "Compose" 按钮
     → Playwright click → DOM click event 触发
     → JS tracker 捕获: {"type": "click", "ref": "e5", "role": "button", "text": "Compose", "url": "https://mail.google.com/inbox"}
     → 新 tab 打开 → CDP Page.frameNavigated
     → recorder 记录: {"type": "navigate", "url": "https://mail.google.com/compose", ...}

   - browser_type(ref="e10", text="alice@example.com")  // 收件人
     → Playwright type → DOM input event 触发
     → JS tracker 捕获: {"type": "input", "ref": "e10", "role": "textbox", "text": "To", "value": "alice@example.com", "url": "https://mail.google.com/compose"}

   - browser_type(ref="e12", text="Meeting tomorrow")  // 主题
     → recorder 记录: {"type": "input", "ref": "e12", ...}

   - browser_click(ref="e20")  // Send 按钮
     → recorder 记录: {"type": "click", "ref": "e20", "role": "button", "text": "Send", ...}
     → 导航回 inbox
     → recorder 记录: {"type": "navigate", "url": "https://mail.google.com/inbox", ...}

3. subtask.state = DONE

4. executor._save_recorded_operations(recorder, subtask)
   → recorder.operations = [navigate, click, navigate, input, input, click, navigate]  (7 条)
   → cloud_client.add_to_memory(operations=..., session_id="task1_sub1")
   → WorkflowProcessor 处理:
     - 创建 State: "Gmail Inbox" (mail.google.com/inbox)
     - 创建 State: "Gmail Compose" (mail.google.com/compose)
     - 创建 Action: Inbox → Compose (click "Compose" button)
     - 创建 Action: Compose → Inbox (click "Send" button)
     - 创建 IntentSequence: 在 Compose 页面的操作 [type "To", type "Subject", click "Send"]
     - 创建 CognitivePhrase: "Send an email via Gmail Compose"

5. executor._stop_behavior_recorder(recorder)
```

### 子任务 2 执行（有 Memory）

```
1. agent.reset()
   → 清除 _page_ops_checked_urls（新改动）
   → 下一次访问 mail.google.com 时会重新查询 Memory

2. executor._start_behavior_recorder(agent) → 新 recorder

3. agent.astep(prompt)：
   - browser_visit_page("https://mail.google.com")
     → URL 变化 → AMIBrowserAgent.set_current_url() → 触发 _start_page_operations_query()
     → Memory 查询命中子任务 1 写入的 IntentSequence
     → 注入 page operations:
       "## Page Operations (1 recorded)
        1. 'Fill in recipient, subject, and send email'
           - type in textbox 'To'
           - type in textbox 'Subject'
           - click button 'Send'"

   - agent 参考 page operations，直接知道该怎么操作
   - 执行更高效（步骤更少、不走弯路）

4. subtask.state = DONE → 保存到 Memory
   → IntentSequence 去重：如果操作和子任务 1 相同 → content hash 匹配 → 跳过
   → 如果路径不同（如先填主题再填收件人）→ 新增一条 IntentSequence
```

## 后果分析

### 会有哪些 Memory 新增？

#### 每个 browser 子任务产生的实体

| 实体 | 首次（无 Memory） | 后续（有 Memory） | 去重机制 |
|---|---|---|---|
| **State** | 新增 2-3 个 | 0（URL 命中已有） | URL index 精确匹配 |
| **PageInstance** | 新增 2-3 个 | 0（同 URL upsert 覆盖） | `id = MD5(url)`，同 URL 只保留一条 |
| **IntentSequence** | 新增 2-4 条 | 0-2 条 | content hash + embedding 相似度 ≥ 0.95 |
| **Action** | 新增 1-2 条 | 0（upsert 覆盖） | source+target State 对 |
| **CognitivePhrase** | 新增 1 条 | 新增 1 条 | 只检查 ID 是否存在 |
| **Domain** | 新增 1 个 | 0（已存在） | domain URL 精确匹配 |

#### 10 个子任务后的总量预估

| 实体 | 总量 | 增长模式 |
|---|---|---|
| **State** | 2-3 | 第 2 次即收敛 |
| **PageInstance** | 2-3 | 第 2 次即收敛（同 URL upsert） |
| **IntentSequence** | 2-8 | 亚线性增长，去重后趋于稳定 |
| **Action** | 1-2 | 第 2 次即收敛 |
| **CognitivePhrase** | 10 | 线性增长（每条 ~2-5KB） |

**CognitivePhrase 是唯一持续增长的实体**（每子任务一条），但 10 条 ~50KB，可接受。其他所有实体（State、PageInstance、Action）在第 2 个子任务后就收敛，IntentSequence 也因去重而趋于稳定。

### Agent 能分辨哪个 Memory 更好吗？

**目前不能显式分辨。**

Layer 2 的 `format_page_operations()` 返回所有 IntentSequence 的 flat list，没有排序、评分或推荐标记。Agent 靠 LLM 自身判断力选择。

**但这在 v1 中是可接受的**：

1. **有参考总比没有** — 从零探索 vs 有操作列表参考，差距巨大
2. **LLM 倾向简洁** — 给它一条 15 步路径和一条 8 步路径，它大概率选短的
3. **去重过滤重复** — content hash + embedding 相似度 ≥ 0.95 过滤完全相同的操作
4. **BehaviorRecorder 的数据比 tool_call 丰富得多** — 有 role、text、URL，IntentSequence 的描述更精确，LLM 更容易理解和选择

**未来可改进（不在本次范围内）**：
- 给 IntentSequence 加 `usage_count` / `success_rate`
- `format_page_operations()` 按分数排序
- 失败子任务的 IntentSequence 标记低置信度

### 性能影响

| 环节 | 耗时预估 | 阻塞性 |
|---|---|---|
| `start_recording()` | ~100ms | 子任务开始前，可忽略 |
| 运行时 recorder 开销 | ~0（纯监听） | 不影响 agent 执行 |
| `stop_recording()` | ~50ms | 子任务结束后，可忽略 |
| `add_to_memory()` API 调用 | 2-5 秒 | **阻塞下一个子任务** |
| 其中：WorkflowProcessor | ~1 秒 | State 去重 + IntentSequence 创建 |
| 其中：generate_descriptions | ~1-2 秒 | LLM 调用 |
| 其中：generate_embeddings | ~0.5-1 秒 | Embedding API |
| Layer 2 re-query（下一子任务） | ~0.5 秒 | 异步，不阻塞 |

**总额外开销**：每个子任务之间增加 ~3-5 秒。子任务本身通常需要 30-120 秒，可接受。

**为什么要阻塞**：必须等 Memory 写入完成，下一个子任务才能查到新数据。如果异步写入，可能出现子任务 2 已经开始但 Memory 还没写完，Layer 2 查不到。

### 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| CDP session 与 Playwright 冲突 | recorder 干扰 agent | BehaviorRecorder 是纯观察者，已在生产使用，无冲突 |
| recorder 失败导致子任务失败 | 阻塞任务执行 | 所有 recorder 操作都 try-except 包裹 |
| 失败子任务的操作被存入 | 不正确路径污染 Memory | 只在 `DONE` 时保存 |
| CognitivePhrase 快速增长 | 存储增加 | 短期可接受；未来可加清理策略 |
| JS tracker debounce 合并事件 | 丢失部分 input 事件 | debounce 1.5 秒，符合正常操作节奏；type 类操作合并后更准确 |
| 导航去重窗口 2 秒 | 丢失快速连续导航 | 正常场景下 2 秒足够区分不同导航 |

## 实现清单

| # | 文件 | 改动 |
|---|---|---|
| 1 | `ami_task_executor.py` | 新增 `__init__` 参数 `cloud_client`, `user_id` |
| 2 | `ami_task_executor.py` | 新增 `_start_behavior_recorder()` 方法 |
| 3 | `ami_task_executor.py` | 新增 `_stop_behavior_recorder()` 方法 |
| 4 | `ami_task_executor.py` | 新增 `_save_recorded_operations()` 方法 |
| 5 | `ami_task_executor.py` | 改动 `_execute_subtask()` — 在执行前后管理 recorder |
| 6 | `ami_browser_agent.py` | 新增 `reset()` override — 清除 `_page_ops_checked_urls` 和缓存 |
| 7 | `quick_task_service.py` | 创建 executor 时传入 `cloud_client` 和 `user_id` |

**预估代码量**：~80 行新增代码，改动 3 个文件。
