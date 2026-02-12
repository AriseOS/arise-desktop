# Persistent Orchestrator with Parallel Executors — Design Document

## 1. Problem

Orchestrator Agent is ephemeral — created, used once, discarded. This causes:

1. **Message routing broken during execution**: When executor.execute() runs, user messages go to child agent's steering queue via `_user_message_queue` → child agent gets confused by unrelated messages
2. **No LLM-based message classification**: Orchestrator can't intercept messages to decide: new task / inject to running executor / cancel
3. **No context for follow-up**: After executor completes, Orchestrator is gone — `continue_task()` creates a fresh Orchestrator with only conversation history text, no execution context
4. **No parallel execution**: Only one executor runs at a time; user can't say "also check JD" while Amazon executor is running
5. **Separate summary agent**: Summary is done by `create_task_summary_provider()` with no execution context, instead of Orchestrator who planned and supervised the work

## 2. Solution Overview

Make Orchestrator a **persistent parent agent** that lives for the entire task session:

- Orchestrator runs in a loop, receiving events (user messages + executor completions)
- Spawns executors non-blocking via `asyncio.create_task()`
- All user messages go to Orchestrator first — LLM decides routing
- Multiple executors can run in parallel
- Orchestrator summarizes results (has full context from decomposition + execution)
- Frontend distinguishes parallel tasks with `executor_id` + `task_label`

## 3. Architecture

### 3.1 New Flow

```
OrchestratorSession.run(initial_message):
  │
  LOOP:
  │
  ├─ Collect completed executor results (if any)
  │  → Format as "[EXECUTION COMPLETE] exec_1: ..." system message
  │
  ├─ Orchestrator.astep(message)
  │  → LLM decides: direct reply / decompose_task / inject_message / cancel_task
  │
  ├─ If decompose_task triggered:
  │  → Plan subtasks (AMITaskPlanner + Memory)
  │  → asyncio.create_task(executor.execute())  ← NON-BLOCKING
  │  → Register in running_executors dict
  │
  ├─ Emit Orchestrator's text reply to user (via WaitConfirmData or AgentReportData)
  │
  └─ _wait_for_event():
     → asyncio.wait() on [user_message_future, *executor_tasks]
     → FIRST_COMPLETED → loop back
```

### 3.2 User Message Routing

| Phase | User sends message | Routed to |
|-------|-------------------|-----------|
| Orchestrator thinking (astep running) | `put_user_message()` → steering queue | Orchestrator's `_check_steering_queue()` picks it up |
| Executors running, Orchestrator idle | `put_user_message()` → session loop wakes | `_wait_for_event()` returns → Orchestrator.astep() decides |
| Waiting for input | `put_user_message()` → session loop wakes | Orchestrator.astep() processes directly |

**Key change**: `handle_user_message()` always queues to `_user_message_queue`. The OrchestratorSession loop consumes from this queue. No more direct routing to child agent steering.

### 3.3 Orchestrator's Tools

| Tool | Purpose | Implementation |
|------|---------|---------------|
| `decompose_task(desc)` | Spawn new parallel executor | Existing, enhanced: sets `_should_stop_after_tool`, session loop handles spawning |
| `inject_message(executor_id, message)` | Forward message to running executor's child agent | New: puts message into target executor's child agent steering queue |
| `replan_task(executor_id, new_plan)` | Replace pending subtasks of a running executor | New (async): pause → replan_subtasks → resume → emit SSE |
| `cancel_task(executor_id)` | Stop a specific executor | New: calls `executor.stop()` |

### 3.4 Executor Identification

Each executor gets a unique `executor_id` (e.g., `"exec_1"`, `"exec_2"`) and a human-readable `task_label` (e.g., `"亚马逊望远镜"`). These are:

- Passed to AMITaskExecutor constructor
- Included in all SSE events emitted during execution
- Used by frontend to group/display parallel task progress

## 4. File Changes

### 4.1 `action_types.py` — SSE Event Enrichment

**Path**: `src/clients/desktop_app/ami_daemon/base_agent/events/action_types.py`

Add `executor_id` and `task_label` fields to these event data models:

```python
# Add to these classes:
executor_id: Optional[str] = None   # e.g. "exec_1", "exec_2"
task_label: Optional[str] = None    # e.g. "亚马逊望远镜", "京东望远镜"
```

**Affected classes** (all extend BaseActionData):
- `WorkforceStartedData`, `WorkforceCompletedData`, `WorkforceStoppedData`
- `WorkerAssignedData`, `WorkerStartedData`, `WorkerCompletedData`, `WorkerFailedData`
- `TaskDecomposedData`, `SubtaskStateData`, `DynamicTasksAddedData`
- `AgentReportData`
- `ActivateAgentData`, `DeactivateAgentData`
- `WaitConfirmData`

**Why not BaseActionData**: Not all events need executor context (heartbeat, error, end). Adding to individual classes keeps the schema clean.

### 4.2 `ami_task_executor.py` — Add Executor Identity

**Path**: `src/clients/desktop_app/ami_daemon/base_agent/core/ami_task_executor.py`

Changes:
1. Add `executor_id: str` and `task_label: str` constructor params
2. Pass them to all SSE events emitted in `_emit_subtask_running()`, `_emit_subtask_state()`, `add_subtasks_async()`
3. Add `get_current_agent()` method — returns the agent currently running a subtask (for message injection)

```python
class AMITaskExecutor:
    def __init__(
        self,
        task_id: str,
        task_state: Any,
        agents: Dict[str, "AMIAgent"],
        max_retries: int = 2,
        user_request: str = "",
        cloud_client: Optional[Any] = None,
        user_id: Optional[str] = None,
        executor_id: str = "",       # NEW
        task_label: str = "",        # NEW
    ):
        ...
        self.executor_id = executor_id
        self.task_label = task_label
        self._current_agent: Optional["AMIAgent"] = None  # NEW: track running agent

    def get_current_agent(self) -> Optional["AMIAgent"]:
        """Get the agent currently executing a subtask (for message injection)."""
        return self._current_agent
```

In `_execute_subtask()`, set `self._current_agent = agent` before execution, clear after.

### 4.3 `orchestrator_agent.py` — Core Changes

**Path**: `src/clients/desktop_app/ami_daemon/base_agent/core/orchestrator_agent.py`

#### 4.3.1 New: `OrchestratorSession` class

```python
@dataclass
class ExecutorHandle:
    """Tracks a running executor and its async task."""
    executor_id: str
    task_label: str
    executor: AMITaskExecutor
    async_task: asyncio.Task
    subtasks: List[AMISubtask]
    started_at: datetime


class OrchestratorSession:
    """
    Persistent Orchestrator session that lives for the entire task lifecycle.

    Runs a loop: wait for event → Orchestrator.astep() → handle result → repeat.
    Events: user messages from queue, executor completions from asyncio tasks.
    """

    def __init__(
        self,
        orchestrator: AMIAgent,
        decompose_tool: DecomposeTaskTool,
        attach_tool: AttachFileTool,
        inject_tool: "InjectMessageTool",
        cancel_tool: "CancelTaskTool",
        task_state: TaskState,
        task_id: str,
        # Dependencies for spawning executors
        create_agents_fn: Callable,     # async () -> (agents_dict, planner_provider)
        create_memory_toolkit_fn: Callable,  # async () -> MemoryToolkit
        collect_files_fn: Callable,     # async () -> List[FileAttachment]
        create_attachment_fn: Callable,  # async (Path) -> FileAttachment
        cloud_client: Optional[Any] = None,
        user_id: Optional[str] = None,
    ):
        self._orchestrator = orchestrator
        self._decompose_tool = decompose_tool
        self._attach_tool = attach_tool
        self._inject_tool = inject_tool
        self._cancel_tool = cancel_tool
        self._task_state = task_state
        self._task_id = task_id

        # Executor management
        self._running_executors: Dict[str, ExecutorHandle] = {}
        self._completed_results: List[str] = []  # formatted result messages
        self._executor_counter = 0

        # Dependencies (injected from QuickTaskService)
        self._create_agents_fn = create_agents_fn
        self._create_memory_toolkit_fn = create_memory_toolkit_fn
        self._collect_files_fn = collect_files_fn
        self._create_attachment_fn = create_attachment_fn
        self._cloud_client = cloud_client
        self._user_id = user_id

        # Lazily created agents (shared across executors)
        self._agents_dict: Optional[Dict] = None
        self._planner_provider = None
```

#### 4.3.2 `run()` — Main Session Loop

```python
async def run(self, initial_message: str) -> None:
    """Main session loop."""
    message = initial_message

    while True:
        # 1. Collect completed executor results
        completed_msgs = self._collect_completed()
        if completed_msgs:
            # Prepend execution results to the message for Orchestrator
            results_block = "\n\n".join(completed_msgs)
            if message:
                message = f"{results_block}\n\n[USER MESSAGE]\n{message}"
            else:
                message = results_block

        # 2. Inject active tasks context into system prompt
        self._update_active_tasks_context()

        # 3. Reset tools and call Orchestrator
        self._decompose_tool.reset()
        self._attach_tool.reset()
        response = await self._orchestrator.astep(message)
        orchestrator_reply = response.text

        # 4. Handle decompose_task trigger
        if self._decompose_tool.triggered:
            task_desc = self._decompose_tool.task_description
            await self._supervised_execute(task_desc)

        # 5. Emit Orchestrator's reply to user
        if orchestrator_reply:
            attachments = await self._build_attachments()
            await self._emit_reply(orchestrator_reply, attachments)

        # 6. If no executors running and no more to do, check if session should end
        # (Orchestrator's reply determines if we wait for more input)

        # 7. Wait for next event (user message or executor completion)
        message = await self._wait_for_event()
        if message is None:
            break  # Session ended (cancelled or timed out)
```

#### 4.3.3 `_supervised_execute()` — Plan + Spawn Executor

```python
async def _supervised_execute(self, task_description: str) -> None:
    """Plan subtasks and spawn a non-blocking executor."""
    # Ensure agents are created
    if self._agents_dict is None:
        self._agents_dict, self._planner_provider = await self._create_agents_fn()

    # Generate executor ID and label
    self._executor_counter += 1
    executor_id = f"exec_{self._executor_counter}"
    # LLM-generated label from decompose_task description (first 20 chars)
    task_label = task_description[:20].strip()

    # Plan subtasks
    memory_toolkit = await self._create_memory_toolkit_fn()
    planner = AMITaskPlanner(...)
    subtasks = await planner.decompose_and_query_memory(task_description)

    if not subtasks:
        # Emit warning, Orchestrator will handle in next iteration
        return

    # Emit TaskDecomposedData with executor_id
    await self._task_state.put_event(TaskDecomposedData(
        ..., executor_id=executor_id, task_label=task_label,
    ))

    # Create executor
    executor = AMITaskExecutor(
        ...,
        executor_id=executor_id,
        task_label=task_label,
    )
    executor.set_subtasks(subtasks)
    self._task_state._executor = executor  # For cancel support

    # Spawn non-blocking
    async_task = asyncio.create_task(
        executor.execute(),
        name=f"executor_{executor_id}",
    )

    # Register
    self._running_executors[executor_id] = ExecutorHandle(
        executor_id=executor_id,
        task_label=task_label,
        executor=executor,
        async_task=async_task,
        subtasks=subtasks,
        started_at=datetime.now(),
    )
```

#### 4.3.4 `_wait_for_event()` — Wait for User Message or Executor Completion

```python
async def _wait_for_event(self) -> Optional[str]:
    """Wait for the next event: user message or executor completion.

    Returns:
        User message string, or "" if executor completed (results collected next loop),
        or None if session should end.
    """
    # Build wait set
    waitables = set()

    # User message: wrap queue.get() in a task
    user_msg_task = asyncio.create_task(
        self._task_state.get_user_message(),
        name="user_message_wait",
    )
    waitables.add(user_msg_task)

    # Executor tasks
    for handle in self._running_executors.values():
        if not handle.async_task.done():
            waitables.add(handle.async_task)

    if not waitables:
        return None

    # Wait for FIRST_COMPLETED
    done, pending = await asyncio.wait(waitables, return_when=asyncio.FIRST_COMPLETED)

    # Cancel the user message wait if an executor completed instead
    if user_msg_task in pending:
        user_msg_task.cancel()
        try:
            await user_msg_task
        except asyncio.CancelledError:
            pass

    # Check what completed
    for task in done:
        if task is user_msg_task:
            # User sent a message
            return task.result()
        # Else: an executor completed — results will be collected in next loop iteration

    return ""  # Executor completed, loop back to collect results
```

#### 4.3.5 `_collect_completed()` — Harvest Finished Executor Results

```python
def _collect_completed(self) -> List[str]:
    """Check for completed executors and format their results."""
    messages = []
    completed_ids = []

    for eid, handle in self._running_executors.items():
        if handle.async_task.done():
            completed_ids.append(eid)
            try:
                result = handle.async_task.result()
                msg = self._format_execution_result(handle, result)
                messages.append(msg)
            except Exception as e:
                messages.append(
                    f"[EXECUTION FAILED] {eid} ({handle.task_label}): {e}"
                )

    for eid in completed_ids:
        del self._running_executors[eid]

    return messages
```

#### 4.3.6 `_format_execution_result()` — Format for Orchestrator

```python
def _format_execution_result(self, handle: ExecutorHandle, result: dict) -> str:
    """Format executor result as a system message for Orchestrator."""
    duration = (datetime.now() - handle.started_at).total_seconds()

    # Collect subtask results
    subtask_summaries = []
    for st in handle.subtasks:
        status = st.state.value
        result_preview = (st.result[:500] + "...") if st.result and len(st.result) > 500 else (st.result or "No result")
        subtask_summaries.append(f"  - [{status}] {st.content[:80]}: {result_preview}")

    # Collect workspace files
    candidate_files = ...  # from _collect_files_fn

    return (
        f"[EXECUTION COMPLETE] {handle.executor_id} ({handle.task_label})\n"
        f"Duration: {duration:.0f}s | "
        f"Completed: {result['completed']}/{result['total']} | "
        f"Failed: {result['failed']}\n"
        f"Subtask Results:\n" + "\n".join(subtask_summaries) + "\n"
        f"Files in workspace: {', '.join(f.file_name for f in candidate_files)}"
    )
```

#### 4.3.7 `_update_active_tasks_context()` — Dynamic Prompt Injection

```python
def _update_active_tasks_context(self) -> None:
    """Inject active executor status into Orchestrator's system prompt."""
    if not self._running_executors:
        # Remove active tasks section if no executors running
        return

    lines = ["## Currently Running Tasks"]
    for eid, handle in self._running_executors.items():
        progress = handle.executor.get_progress()
        lines.append(
            f"- {eid} ({handle.task_label}): "
            f"{progress['done']}/{progress['total']} subtasks done, "
            f"{progress['running']} running"
        )

    context_section = "\n".join(lines)
    # Append to orchestrator's system prompt (or inject as system message)
    # Implementation: prepend to next user message as context block
```

#### 4.3.8 New Tools: InjectMessageTool, CancelTaskTool

```python
class InjectMessageTool:
    """Forward a message to a running executor's child agent."""

    def __init__(self, session: "OrchestratorSession"):
        self._session = session

    def inject_message(self, executor_id: str, message: str) -> str:
        """
        Send a message to a running executor's child agent.
        The agent will receive this as a steering message during its next tool call.

        Args:
            executor_id: ID of the target executor (e.g., "exec_1")
            message: Message to inject (user's instruction or modification)
        """
        handle = self._session._running_executors.get(executor_id)
        if not handle:
            return f"Error: No running executor with ID '{executor_id}'"

        agent = handle.executor.get_current_agent()
        if not agent:
            return f"Executor {executor_id} exists but no agent is currently active"

        # Put message into the agent's steering queue via task_state
        # AMIAgent._check_steering_queue() reads from task_state._user_message_queue
        # But we need per-executor routing, so use agent-level queue
        asyncio.create_task(
            self._session._task_state.put_user_message(message)
        )
        return f"Message injected to executor {executor_id}"


class CancelTaskTool:
    """Cancel a running executor."""

    def __init__(self, session: "OrchestratorSession"):
        self._session = session

    def cancel_task(self, executor_id: str) -> str:
        """
        Cancel a running executor, stopping its current work.

        Args:
            executor_id: ID of the executor to cancel (e.g., "exec_1")
        """
        handle = self._session._running_executors.get(executor_id)
        if not handle:
            return f"Error: No running executor with ID '{executor_id}'"

        handle.executor.stop()
        return f"Executor {executor_id} ({handle.task_label}) is being cancelled"
```

#### 4.3.9 Modify ORCHESTRATOR_SYSTEM_PROMPT

Add sections for the new capabilities:

```python
ORCHESTRATOR_SYSTEM_PROMPT = """\
You are AMI, a coordinator in a multi-agent system.

## Your Role
...existing content...

## Your Tools
- shell_exec: Execute terminal commands to explore user's files
- search_google: Quick web search for simple questions
- ask_human: Ask user for clarification
- attach_file: Attach a file to your response
- decompose_task: Delegate work to your team (spawns a parallel executor)
- inject_message: Send a message to a running executor's agent (e.g., modify search criteria)
- cancel_task: Cancel a specific running executor

## Handling Running Tasks
When executors are running and user sends a new message, decide:
1. **New parallel task**: User wants something unrelated → call decompose_task
2. **Modify running task**: User wants to adjust a running executor → call inject_message
3. **Cancel task**: User wants to stop a running executor → call cancel_task
4. **Direct reply**: User asks a question you can answer → reply directly

## Handling Execution Results
When you receive [EXECUTION COMPLETE] messages:
1. Summarize the results for the user in their language
2. Include key findings, data, and file references
3. If files were created, use attach_file to deliver them
4. Ask if user needs anything else

{active_tasks_context}

## Language Policy
**CRITICAL**: Respond in the same language as the user's input.
"""
```

#### 4.3.10 Modify `DecomposeTaskTool.reset()`

```python
def reset(self) -> None:
    """Reset the trigger state for reuse across multiple decompose calls."""
    self._triggered = False
    self._task_description = None
    # Reset _should_stop_after_tool so Orchestrator can decompose again
    if self._agent:
        self._agent._should_stop_after_tool = False
```

#### 4.3.11 Modify `create_orchestrator_agent()`

Add new tools to the agent:

```python
async def create_orchestrator_agent(...) -> tuple[AMIAgent, DecomposeTaskTool, AttachFileTool, "InjectMessageTool", "CancelTaskTool"]:
    ...
    # (inject_tool and cancel_tool need session reference, set later)
    inject_tool = InjectMessageTool(session=None)  # session set after creation
    cancel_tool = CancelTaskTool(session=None)

    inject_ami_tool = AMITool(inject_tool.inject_message)
    cancel_ami_tool = AMITool(cancel_tool.cancel_task)
    tools.extend([inject_ami_tool, cancel_ami_tool])

    ...
    return agent, decompose_tool, attach_tool, inject_tool, cancel_tool
```

### 4.4 `quick_task_service.py` — Refactor `_execute_task_ami()`

**Path**: `src/clients/desktop_app/ami_daemon/services/quick_task_service.py`

#### 4.4.1 Refactored `_execute_task_ami()`

Replace the inline Orchestrator→Executor pipeline (~lines 1653-2067) with:

```python
async def _execute_task_ami(self, task_id: str, headless: bool = False):
    state = self._tasks[task_id]
    state.status = TaskStatus.RUNNING
    state.started_at = datetime.now()

    if not state.conversation_history:
        state.add_conversation("user", state.task)

    set_current_manager(state.dir_manager)

    await state.put_event(TaskStateData(...))

    # Create Orchestrator Agent (with new tools)
    orchestrator, decompose_tool, attach_tool, inject_tool, cancel_tool = \
        await create_orchestrator_agent(...)

    # Build context-aware user message
    current_question = state.task
    if len(state.conversation_history) > 1:
        context = state.get_recent_context(max_entries=10)
        current_question = f"{context}\n\n=== Current Request ===\n{state.task}"

    try:
        # Create OrchestratorSession
        session = OrchestratorSession(
            orchestrator=orchestrator,
            decompose_tool=decompose_tool,
            attach_tool=attach_tool,
            inject_tool=inject_tool,
            cancel_tool=cancel_tool,
            task_state=state,
            task_id=task_id,
            create_agents_fn=lambda: self._create_agents_for_ami_executor(task_id, state, headless),
            create_memory_toolkit_fn=lambda: self._create_memory_toolkit(task_id, state),
            collect_files_fn=lambda: self._collect_candidate_files(task_id, state),
            create_attachment_fn=self._create_file_attachment,
            cloud_client=self._cloud_client,
            user_id=self._user_id,
        )

        # Wire up session reference in tools
        inject_tool._session = session
        cancel_tool._session = session

        # Run the persistent session loop
        await session.run(current_question)

    except asyncio.CancelledError:
        logger.info(f"[Task {task_id}] Task cancelled during execution")
    except Exception as e:
        logger.exception(f"[Task {task_id}] Session failed: {e}")
        state.error = str(e)
        await state.put_event(WaitConfirmData(
            task_id=task_id,
            content=f"An error occurred: {e}",
            question=current_question,
            context="initial",
        ))

    # Cleanup (same as current)
    state._executor = None
    if state.status != TaskStatus.CANCELLED:
        ...  # same completion logic
    # Browser cleanup (same as current)
```

**Removed from `_execute_task_ami()`**:
- Inline `run_orchestrator()` call
- Inline executor creation + `executor.execute()` (moved to `OrchestratorSession._supervised_execute()`)
- `_aggregate_ami_results()` call (Orchestrator now summarizes)
- `_collect_candidate_files()` call in-place (moved to session)
- Per-executor WaitConfirmData emission (moved to session)

**Kept in `_execute_task_ami()`**:
- Outer try/except + cleanup
- Browser session close
- Tab group close
- Status transitions

#### 4.4.2 `handle_user_message()` — No Changes Needed

Current implementation already queues all messages to `_user_message_queue` for RUNNING and WAITING states. The OrchestratorSession loop consumes from this queue via `_wait_for_event()`. No changes needed.

The only subtle change: when task is COMPLETED, `continue_task()` creates a new `_execute_task_ami()` which creates a new OrchestratorSession. The old session is already gone.

### 4.5 Frontend Files

#### 4.5.1 `sseClient.js`

**Path**: `src/clients/desktop_app/src/utils/sseClient.js`

No changes needed — `sseClient.js` already parses SSE events as JSON and passes the full event object to `agentStore.handleSSEEvent()`. New fields (`executor_id`, `task_label`) are automatically available.

#### 4.5.2 `agentStore.js`

**Path**: `src/clients/desktop_app/src/store/agentStore.js`

**Add to task state**:

```javascript
// In createInitialTaskState():
executors: {},  // { "exec_1": { id, label, status, subtasks, startedAt } }
```

**Modify event handlers** to track executor state:

```javascript
case 'workforce_started': {
    const executorId = event.executor_id;
    const taskLabel = event.task_label;
    if (executorId) {
        const currentTask = store.tasks[taskId];
        const executors = { ...currentTask?.executors };
        executors[executorId] = {
            id: executorId,
            label: taskLabel,
            status: 'running',
            subtasks: [],
            startedAt: new Date().toISOString(),
        };
        updateTask({ executors });
    }
    // ...existing logic unchanged
    break;
}

case 'workforce_completed': {
    const executorId = event.executor_id;
    if (executorId) {
        const currentTask = store.tasks[taskId];
        const executors = { ...currentTask?.executors };
        if (executors[executorId]) {
            executors[executorId] = { ...executors[executorId], status: 'completed' };
        }
        updateTask({ executors });
    }
    // ...existing logic unchanged
    break;
}

case 'task_decomposed': {
    const executorId = event.executor_id;
    // Store subtasks under executor if executor_id present
    if (executorId) {
        const currentTask = store.tasks[taskId];
        const executors = { ...currentTask?.executors };
        if (executors[executorId]) {
            executors[executorId] = {
                ...executors[executorId],
                subtasks: event.subtasks,
            };
        }
        updateTask({ executors });
    }
    // ...existing logic unchanged
    break;
}

case 'agent_report': {
    const { message, report_type, executor_id, task_label } = event;
    if (message) {
        addMessage('agent', message, {
            reportType: report_type || 'info',
            executorId: executor_id,
            taskLabel: task_label,
        });
    }
    break;
}
```

#### 4.5.3 `MessageList.jsx` / `AgentMessage.jsx`

**Path**: `src/clients/desktop_app/src/components/ChatBox/`

**AgentMessage**: Show executor label badge when `executorId` is present:

```jsx
// In AgentMessage component:
const { reportType, executorId, taskLabel } = message.metadata || {};

// Render executor badge if present
{taskLabel && (
    <span className="executor-badge">
        {taskLabel}
    </span>
)}
```

**MessageList**: Group subtask progress by executor (enhancement, not critical for v1).

## 5. Key Design Decisions

### 5.1 Executor remains blocking internally
`executor.execute()` is still a blocking sequential loop for its own subtasks. Parallelism is at the **executor level** (multiple executors via `asyncio.create_task()`), not subtask level.

### 5.2 Message classification by LLM, not heuristics
Orchestrator LLM sees active task context and decides routing. No keyword matching — the LLM naturally understands "顺便也看看京东" (new task) vs "只看天文望远镜" (inject to current) vs "取消" (cancel).

### 5.3 Orchestrator summarizes, no separate summary agent
Orchestrator has full context: what user asked, what it decomposed, execution results. Eliminates `_aggregate_ami_results()` and `create_task_summary_provider()`. The execution results are injected as formatted text, and Orchestrator produces the final summary reply.

### 5.4 Per-executor steering queue (NOT shared)
Current problem: `_user_message_queue` is shared — messages during execution go to child agent steering and confuse it.

Solution: OrchestratorSession loop owns `_user_message_queue`. To inject messages to child agents, Orchestrator calls `inject_message(executor_id, msg)` which puts the message into that specific executor's currently-active agent steering queue. Each executor/agent has its own message path.

### 5.5 Browser cleanup is per-executor
Each executor uses the shared browser session but tracks its own tabs. On executor completion, only that executor's tabs are closed via `_cleanup_subtask_tabs()`. Full browser session cleanup only on OrchestratorSession exit.

### 5.6 Lazy agent creation
Agents (`_agents_dict`) are only created when the first `decompose_task` is triggered. Simple direct replies never create browser/developer/document agents. This is the same as current behavior.

### 5.7 Backward compatibility
- Frontend gracefully handles events with or without `executor_id` (Optional fields)
- If `executor_id` is None, frontend behaves exactly as today (single executor mode)
- `handle_user_message()` API unchanged
- `cancel_task()` API unchanged (cancels all executors via session)

## 6. Execution Example

```
User: "帮我看看亚马逊最畅销的望远镜"

OrchestratorSession.run("帮我看看亚马逊最畅销的望远镜")
  → Orchestrator.astep() → decompose_task("亚马逊最畅销望远镜")
  → _supervised_execute() → spawn Executor exec_1 (label="亚马逊望远镜")
  → reply: "好的，正在帮你浏览亚马逊..."
  → _wait_for_event()

  [Executor exec_1 running: subtask 1/4 browsing amazon.com]

User: "顺便也帮我看看京东上的"
  → handle_user_message() → put_user_message()
  → _wait_for_event() returns "顺便也帮我看看京东上的"

  → Orchestrator.astep("顺便也帮我看看京东上的")
     (system prompt shows: exec_1 running "亚马逊望远镜" 1/4 done)
  → LLM decides: new parallel task
  → decompose_task("京东最畅销望远镜")
  → _supervised_execute() → spawn Executor exec_2 (label="京东望远镜")
  → reply: "好的，同时在京东上查找..."
  → _wait_for_event()

  [exec_1 completes → async_task.done()]
  → _wait_for_event() returns ""
  → _collect_completed() returns formatted exec_1 results

  → Orchestrator.astep("[EXECUTION COMPLETE] exec_1 亚马逊望远镜: 4/4 done...")
  → reply: "亚马逊的结果出来了：Top 5 望远镜如下..."（+ attach_file）
  → _wait_for_event()

  [exec_2 completes]
  → Similar flow → Orchestrator summarizes JD results

User: "帮我做个对比表格"
  → Orchestrator has full context of both results (in conversation history)
  → decompose_task("对比亚马逊和京东望远镜") → exec_3
  → ...
```

## 7. ReplanTaskTool — Mid-Flight Plan Modification

### 7.1 Problem

The Orchestrator's "Handling Running Tasks" was missing a **replan** scenario. Users may want to modify a running executor's plan mid-flight:

- "不用收集那么多" → reduce scope (remove PENDING subtasks)
- "报告格式换一下" → change document subtask content
- "加上价格对比" → add a new subtask

Previously the Orchestrator could only: `decompose_task` (new executor), `inject_message` (steering child agent), `cancel_task` (stop entirely). There was no way to **replace the PENDING portion of the plan** while preserving completed work.

### 7.2 Design

**Whole-plan replacement, not individual edits**: Orchestrator LLM sees the full subtask state and produces a complete new PENDING set. Simpler and less error-prone than add/remove/modify individual ops.

**Pause-modify-resume pattern**: `executor.pause()` takes effect at the next `_wait_if_paused()` call (between subtasks). The RUNNING subtask completes normally. Since `replan_task` is async and runs on the event loop thread, the executor's coroutines are suspended at await points during mutation — no thread-safety issues.

### 7.3 Implementation

#### 7.3.1 `AMITaskExecutor` — New Methods

**`get_subtasks_detail() -> List[Dict]`**: Returns serialized subtask list with id, content, agent_type, state, depends_on, result_preview. Used by `_build_active_tasks_context()` to give the Orchestrator LLM enough context to produce a valid new plan.

**`replan_subtasks(new_pending: List[AMISubtask]) -> Dict`**: Replaces all PENDING subtasks with new ones. Preserves DONE/RUNNING/FAILED. Validates:
- No new ID collides with kept (non-PENDING) IDs
- All `depends_on` in new subtasks reference either kept IDs or other new IDs
- Raises `ValueError` on violation

#### 7.3.2 `ReplanTaskTool` (in `orchestrator_agent.py`)

```python
class ReplanTaskTool:
    async def replan_task(self, executor_id: str, new_plan: str) -> str:
        """
        Replace pending subtasks of a running executor with a new plan.

        Args:
            executor_id: e.g. "exec_1"
            new_plan: JSON array of subtask objects with id, content, agent_type, depends_on
        """
```

**Tool flow**:
1. Validate executor exists and hasn't completed (`handle.async_task.done()`)
2. Parse + validate JSON (id, content, agent_type required; agent_type in executor's agents)
3. Build `List[AMISubtask]` from JSON
4. `executor.pause()` → `executor.replan_subtasks(new_subtasks)` → `executor.resume()`
5. Update `handle.subtasks` reference
6. Update `self._task_state.subtasks` — replace this executor's entries, keep other executors'
7. `await` emit `TaskReplannedData` SSE event
8. Return confirmation string with removed/added counts

On validation/dependency error: `executor.resume()` then return error string.

**Critical: `replan_task` is `async`**. Since `AMIAgent._execute_tool()` dispatches sync tools via `asyncio.to_thread()` (worker thread), a sync `replan_task` would crash when calling `asyncio.create_task()` or manipulating `asyncio.Event` from a non-event-loop thread. Making it async ensures it runs on the event loop thread via `await tool.func()`.

#### 7.3.3 Enhanced `_build_active_tasks_context()`

Shows subtask-level detail so the LLM can produce valid replan requests:

```
### exec_1 (看亚马逊望远镜)
Progress: 2/5 done, 1 running, 2 pending
  [OK] sub_1 (browser): 打开亚马逊搜索望远镜  result="Found 15 products..."
  [OK] sub_2 (browser): 收集前5个产品信息  result="Collected data for..."
  [>>] sub_3 (browser): 收集后5个产品信息  depends_on=[sub_2]
  [..] sub_4 (document): 生成对比报告  depends_on=[sub_2, sub_3]
  [..] sub_5 (browser): 截图价格页面  depends_on=[sub_3]
```

#### 7.3.4 Updated System Prompt

```
## Your Tools
...
- replan_task: Replace pending subtasks of a running executor with a new plan

## Handling Running Tasks
...
3. **Replan task**: User wants to change scope/direction → call replan_task
   - You can see the full subtask list with states in "Currently Running Tasks"
   - Generate new PENDING subtasks only — DONE/RUNNING are preserved automatically
   - New subtasks can depend on DONE/RUNNING subtask IDs
```

#### 7.3.5 `TaskReplannedData` — Added Fields

```python
class TaskReplannedData(BaseActionData):
    executor_id: Optional[str] = None   # NEW
    task_label: Optional[str] = None    # NEW
```

#### 7.3.6 Frontend `agentStore.js` — Executor-Aware Replan Handler

The `task_replanned` handler now:
- Maps subtask states to UI statuses
- When `executor_id` is present: replaces only that executor's subtasks, keeps others
- Updates executor-specific tracking (`executors[executorId].subtasks`)
- Falls back to legacy full-replace when no `executor_id`

#### 7.3.7 Wiring

- `create_orchestrator_agent()` returns 6-tuple (added `ReplanTaskTool`)
- `OrchestratorSession.__init__` accepts `replan_tool` parameter
- `quick_task_service.py` destructures 6-tuple, passes `replan_tool` to session, calls `replan_tool.set_session(session)`
- `core/__init__.py` exports `ReplanTaskTool`

### 7.4 Scenario Analysis

| # | Scenario | Behavior | Status |
|---|----------|----------|--------|
| 1 | **Reduce scope**: 5 subtasks (2 DONE, 1 RUNNING, 2 PENDING). User: "只看前3个" | `replan_task(exec_1, [])` removes 2 PENDING. After RUNNING completes, `_get_next_subtask()` returns None → executor exits cleanly. | OK |
| 2 | **Add requirement**: 3 subtasks (1 DONE, 2 PENDING). User: "加上价格对比" | `replan_task(exec_1, [original_pending + new_comparison_task])` | OK |
| 3 | **Change direction**: Collecting Amazon data. User: "改成看京东的" | `replan_task(exec_1, [new_jd_subtasks])` replaces PENDING amazon tasks. DONE data preserved as dependency context. | OK |
| 4 | **New subtask depends on RUNNING**: New subtask with `depends_on=["s3"]` where s3 is RUNNING | Dependency validation passes (s3 is in kept_ids). After s3→DONE, `_get_next_subtask()` picks up new subtask. | OK |
| 5 | **Dependency violation**: New subtask depends on removed PENDING ID | `replan_subtasks()` raises `ValueError`, tool returns error, LLM retries. | OK |
| 6 | **Executor already completed**: All subtasks done, `async_task.done()` | `replan_task` returns "Error: Executor has already completed". | OK |
| 7 | **Dynamic subtasks from ReplanToolkit**: RUNNING subtask added dynamic PENDING subtasks, then user replans | Dynamic PENDING subtasks are removed along with original PENDING. LLM sees all subtasks in context and can re-include them. **Design trade-off**: no distinction between original and dynamic PENDING. | Acceptable |
| 8 | **Race: replan during subtask execution** | `replan_task` is async, runs on event loop thread. `_execute_subtask` is suspended at `await agent.astep()`. List mutation is atomic from event loop perspective. No race. | OK |
| 9 | **Empty new_plan** | All PENDING removed. Executor finishes after current RUNNING completes. | OK |
| 10 | **ID collision** | New subtask ID matches DONE/RUNNING ID → `ValueError` → error returned to LLM. | OK |

### 7.5 Key Design Decisions

1. **Async tool function**: `replan_task` must be `async` because sync tools are dispatched via `asyncio.to_thread()` to a worker thread, which cannot safely call `asyncio.create_task()`, manipulate `asyncio.Event`, or mutate shared state read by event-loop coroutines.

2. **Whole-plan replacement over individual edits**: LLM produces the complete new PENDING set. This avoids the complexity of add/remove/modify individual operations and ensures the LLM has full control over the new dependency graph.

3. **`_build_active_tasks_context` with subtask detail**: The LLM MUST see subtask IDs, states, content, and results to produce a valid replacement plan. Without this, it can't know which DONE subtask IDs to reference as dependencies.

4. **`_task_state.subtasks` coherence**: The replan tool updates both the executor's internal subtask list AND the shared `_task_state.subtasks` (replacing only this executor's entries). This keeps the frontend's global subtask view consistent with per-executor views.

5. **Dynamic subtasks treated as regular PENDING**: When a RUNNING subtask dynamically adds PENDING subtasks (via ReplanToolkit), those are indistinguishable from original PENDING subtasks. A replan removes all PENDING. The LLM can see them in context and re-include if needed. A more granular approach (preserving dynamic subtasks) would add complexity without clear benefit.

## 8. Verification Plan

| # | Scenario | Expected Behavior |
|---|----------|-------------------|
| 1 | Simple task: "你好" | Orchestrator replies directly, no executor spawned |
| 2 | Complex task: "帮我看亚马逊望远镜" | decompose → executor spawns → subtasks execute → Orchestrator summarizes |
| 3 | Parallel tasks: While exec running, send "也看看京东" | Second executor spawns, both run simultaneously, results arrive separately |
| 4 | Inject message: While browsing, send "只看天文望远镜" | Orchestrator calls inject_message → child agent adjusts |
| 5 | Cancel: While executing, send "取消" | Orchestrator calls cancel_task → executor stops → confirms |
| 6 | Follow-up after completion: After all done, send "做个对比" | Orchestrator uses context → new executor |
| 7 | Browser isolation: Two browser executors simultaneous | Each has own tab scope, closing one doesn't affect other |
| 8 | Frontend: Parallel executors | Different executors show different labels in chat, subtask progress grouped |
| 9 | Replan - reduce scope: "不用收集那么多" | Orchestrator calls replan_task with fewer PENDING subtasks, executor finishes sooner |
| 10 | Replan - add requirement: "加上价格对比" | Orchestrator calls replan_task with original PENDING + new subtask, executor continues with expanded plan |
| 11 | Replan - change direction: "改成看京东的" | Orchestrator calls replan_task replacing PENDING browse-Amazon with browse-JD subtasks |
| 12 | Replan - dependency error | LLM produces invalid deps → tool returns error → LLM retries with correct deps |
| 13 | Replan - completed executor | Executor already done → tool returns "already completed" → LLM suggests decompose_task instead |
| 14 | Replan - frontend update | task_replanned SSE event → frontend updates only target executor's subtasks in UI |

## 9. Implementation Status

All 4 phases are fully implemented.

### Phase 1: OrchestratorSession + Refactor ✅

- `OrchestratorSession` with `run()`, `_wait_for_event()`, `_supervised_execute()`, `_collect_completed()`, `_format_execution_result()`, `_build_active_tasks_context()`
- `_execute_task_ami()` refactored: creates `OrchestratorSession`, calls `session.run()`
- Session idle timeout (30 min) with graceful exit
- External cancellation via `session.stop_all_executors()`

### Phase 2: SSE Event Enrichment + Frontend ✅

- `executor_id`/`task_label` fields on all relevant event data classes
- `AMITaskExecutor` passes executor identity to all SSE emissions
- `agentStore.js` tracks per-executor state (`executors: {}`)
- `AgentMessage.jsx` shows executor label badges

### Phase 3: Sequential Execution with Queuing ✅

**Current behavior**: Executors run sequentially via `_executor_lock`. Multiple `decompose_task` calls are accepted immediately (planning + SSE events fire right away so user sees subtask lists), but actual execution waits for prior executors to complete.

**Infrastructure (ready for future parallel)**:
- `_supervised_execute()` spawns via `asyncio.create_task()` + `_executor_lock`
- `_running_executors` dict tracks all executors (queued + running)
- `_wait_for_event()` uses `FIRST_COMPLETED` across all executor tasks + user message
- `AMIAgent.clone()` / `AMIBrowserAgent.clone()`: each executor gets fresh agent instances
- `_disable_shared_queue` flag: Orchestrator exclusively owns the shared queue

**Why sequential**: `BrowserToolkit` has a single `session._page` pointer. Parallel browser executors would fight over Playwright page state. Enabling true parallel requires per-executor browser tab isolation (separate `_page` per executor).

**To enable parallel in the future**: Remove `_executor_lock`, implement per-executor page tracking in `HybridBrowserSession`.

### Phase 4: Tool Suite ✅

- `InjectMessageTool`: routes message to specific executor's active agent via `inject_steering_message()`
- `CancelTaskTool`: stops specific executor via `executor.stop()` + `async_task.cancel()`
- `ReplanTaskTool` (async): pause → `replan_subtasks()` → resume → emit `TaskReplannedData`
- `_build_active_tasks_context()` shows subtask-level detail (`[OK]`/`[>>]`/`[..]`/`[XX]`)
- System prompt updated with all 5 tools + handling instructions

### Bug Fixes Applied

| Bug | Fix | Severity |
|-----|-----|----------|
| Child agent stealing shared queue messages | `_disable_shared_queue` flag on AMIAgent | High |
| Parallel executors sharing agent instances | `clone()` per executor in `_supervised_execute` | High |
| `_emit_reply` always sets WAITING status | Only set WAITING when no executors running | Medium |
| Message lost on cancel in `_wait_for_event` | Check `user_msg_task.result()` after cancel, re-queue if needed | Medium |
| `_collect_completed` fire-and-forget SSE | Converted to `async def`, `await` all events | Medium |
| `_task_state._executor` only tracks last executor | `stop_all_executors()` on session, external cancel uses session | Medium |
| Session no idle timeout | 30-min timeout via `asyncio.wait(timeout=)` | Medium |
| Orphan executors on session exception | `stop_all_executors()` in cleanup section | Low |

### Known Limitations (Future Work)

- **Shared toolkit instances across clones**: `clone()` shares the same `BrowserToolkit` instance. If two parallel executors both run browser subtasks simultaneously, the underlying Playwright page state may conflict. This is acceptable for Phase 1-3 (executors rarely run same agent type simultaneously) but needs per-executor browser tab isolation for true parallel browser tasks.
- **Dynamic PENDING subtasks removed by replan**: `replan_subtasks()` treats all PENDING subtasks equally. Dynamically added subtasks (via ReplanToolkit) are removed along with original PENDING. The LLM sees them in `_build_active_tasks_context()` and can re-include, but there's no mechanism to selectively preserve them.
