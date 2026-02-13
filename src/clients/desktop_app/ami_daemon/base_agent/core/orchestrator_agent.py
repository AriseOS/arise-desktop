"""
Orchestrator Agent - Persistent coordinator that manages user sessions.

The Orchestrator runs as a persistent session (OrchestratorSession) that:
- Decides how to handle each user message (direct reply / tool use / decompose_task)
- Spawns executors non-blocking for complex tasks
- Routes user messages to the right target (Orchestrator LLM decides)
- Summarizes execution results (has full context)
- Supports parallel executors with unique executor_id + task_label

New tools beyond basic search/terminal:
- decompose_task: Spawn a parallel executor for complex tasks
- inject_message: Forward a message to a running executor's child agent
- cancel_task: Cancel a specific running executor
"""

import asyncio
import datetime
import logging
import os
import platform
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .ami_agent import AMIAgent
from .ami_tool import AMITool
from .agent_factories import create_provider, _get_now_str
from ..workspace import WorkingDirectoryManager

if TYPE_CHECKING:
    from ..events import SSEEmitter

logger = logging.getLogger(__name__)

# Maximum iterations for Orchestrator's tool-use loop
MAX_ORCHESTRATOR_ITERATIONS = 20


# Orchestrator System Prompt
ORCHESTRATOR_SYSTEM_PROMPT = """\
You are AMI, a coordinator in a multi-agent system.

## Your Role
You are the first point of contact for user requests. You can:
- Answer simple questions directly or with tools
- Use terminal commands to explore user's files and help them find past work
- Delegate complex work (browsing websites, writing code, creating documents) to your team via `decompose_task`

## Your Team
- **Browser Agent**: Browse websites, click buttons, fill forms, extract content, take screenshots, multi-page navigation
- **Developer Agent**: Write Python/JS code, execute scripts, build applications, automate tasks
- **Document Agent**: Create Word documents, Excel spreadsheets, PowerPoint presentations, PDF reports
- **Social Agent**: Send emails (Gmail), manage calendar, post to social media, access Notion

## Environment
- System: {platform_system} ({platform_machine})
- Current Date: {now_str}

## User's Workspace
Task files location: `{user_workspace}`

Structure: `{{task_id}}/workspace/` - each task folder contains output files (reports, documents, data, etc.)

## Your Tools
- shell_exec: Execute terminal commands to explore user's files
- search_google: Quick web search for simple questions (weather, facts, etc.) - reply directly with search results, do NOT use decompose_task
- ask_human: Ask user for clarification
- attach_file: Attach a file to your response (user can click to open/preview it)
- decompose_task: Delegate work to your team (spawns a parallel executor)
- inject_message: Send a message to a running executor's agent (e.g., modify search criteria)
- cancel_task: Cancel a specific running executor
- replan_task: Replace pending subtasks of a running executor with a new plan

## Important Guidelines
When user asks to find files or past work:
1. Use shell_exec to locate the files
2. Use attach_file to attach found files to your response
3. Do NOT copy files to Desktop - just attach them directly

## Handling Running Tasks
When executors are running and user sends a new message, decide:
1. **New parallel task**: User wants something unrelated → call decompose_task
2. **Modify running task**: User wants to adjust a running executor → call inject_message
3. **Replan task**: User wants to change scope/direction → call replan_task
   - You can see the full subtask list with states in "Currently Running Tasks"
   - Generate new PENDING subtasks only — DONE/RUNNING are preserved automatically
   - New subtasks can depend on DONE/RUNNING subtask IDs
4. **Cancel task**: User wants to stop a running executor → call cancel_task
5. **Direct reply**: User asks a question you can answer → reply directly

## Handling Execution Results
When you receive [EXECUTION COMPLETE] messages:
1. Summarize the results for the user in their language
2. Include key findings, data, and file references
3. If files were created, use attach_file to deliver them
4. Ask if user needs anything else

{active_tasks_context}

## Language Policy
**CRITICAL**: You MUST respond in the same language as the user's input.
- If the user writes in Chinese, respond in Chinese.
- If the user writes in English, respond in English.
- This applies to ALL your responses and outputs.
"""


class DecomposeTaskTool:
    """
    Special tool that triggers Workforce execution for complex tasks.

    When the Orchestrator calls this tool, it signals that the current task
    should be handed off to the full Workforce pipeline (decomposition,
    user confirmation, multi-agent execution).
    """

    def __init__(self, callback: Callable[[str], Any]):
        """
        Initialize DecomposeTaskTool.

        Args:
            callback: Async function to call when decompose_task is invoked.
                     Takes the task description and returns the execution result.
        """
        self._callback = callback
        self._triggered = False
        self._task_description: Optional[str] = None
        self._agent: Optional["AMIAgent"] = None

    def set_agent(self, agent: "AMIAgent") -> None:
        """Set agent reference so decompose_task can stop the agent loop."""
        self._agent = agent

    @property
    def triggered(self) -> bool:
        """Check if decompose_task was called."""
        return self._triggered

    @property
    def task_description(self) -> Optional[str]:
        """Get the task description passed to decompose_task."""
        return self._task_description

    def reset(self) -> None:
        """Reset the trigger state for reuse across multiple decompose calls."""
        self._triggered = False
        self._task_description = None
        if self._agent:
            self._agent._should_stop_after_tool = False

    def decompose_task(self, task_description: str) -> str:
        """
        Delegate a task to specialized agents (Browser, Developer, Document, etc.)

        Call this when the task requires browsing websites, writing code, or
        creating documents - things you cannot do yourself.

        Args:
            task_description: The user's request in their own words.
                - Copy the user's original wording as closely as possible
                - Do NOT rephrase, translate, or substitute any keywords
                - Do NOT add requirements the user didn't mention
                - Do NOT specify output formats unless user asked
                - Do NOT add "suggested steps" or implementation details

        Returns:
            Confirmation that the task has been queued for execution.
        """
        if self._triggered:
            return (
                "Task already delegated and is being executed. "
                "Do NOT call decompose_task again. "
                "Summarize your plan to the user and stop."
            )

        self._triggered = True
        self._task_description = task_description
        logger.info(f"[DecomposeTaskTool] Triggered with: {task_description[:100]}...")

        # Stop the Orchestrator agent loop immediately after this tool call.
        # Without this, the LLM keeps calling search_google/ask_human/etc.
        # and never reaches the AMITaskPlanner → Memory → Executor path.
        if self._agent:
            self._agent._should_stop_after_tool = True

        return (
            "Task delegated successfully. The team will now execute this task. "
            "Summarize what you plan to do for the user."
        )


class AttachFileTool:
    """
    Tool for attaching files to Orchestrator's response.

    When the Orchestrator finds files that the user requested, it can use this
    tool to attach them to the response. The frontend will display these as
    clickable file cards with previews.
    """

    def __init__(self):
        """Initialize AttachFileTool."""
        self._attached_files: List[str] = []

    @property
    def attached_files(self) -> List[str]:
        """Get list of attached file paths."""
        return self._attached_files

    def reset(self) -> None:
        """Reset attached files list."""
        self._attached_files = []

    def attach_file(self, file_path: str) -> str:
        """
        Attach a file to your response so user can view/open it directly.

        Use this when you find a file the user asked for. The file will appear
        as a clickable card in the chat - user can preview or open it.

        Args:
            file_path: Absolute path to the file to attach.
                      Must be an existing file or directory.

        Returns:
            Confirmation message.
        """
        # Expand user home directory
        expanded_path = os.path.expanduser(file_path)

        # Validate file exists
        if not os.path.exists(expanded_path):
            return f"Error: File not found: {file_path}"

        # Store absolute path
        abs_path = os.path.abspath(expanded_path)

        # Avoid duplicates
        if abs_path not in self._attached_files:
            self._attached_files.append(abs_path)
            logger.info(f"[AttachFileTool] Attached: {abs_path}")

        file_type = "folder" if os.path.isdir(abs_path) else "file"
        return f"Successfully attached {file_type}: {os.path.basename(abs_path)}"


class InjectMessageTool:
    """Forward a message to a running executor's child agent."""

    def __init__(self):
        self._session: Optional["OrchestratorSession"] = None

    def set_session(self, session: "OrchestratorSession") -> None:
        self._session = session

    def inject_message(self, executor_id: str, message: str) -> str:
        """
        Send a message to a running executor's child agent.
        The agent will receive this as a steering message during its next tool call.

        Args:
            executor_id: ID of the target executor (e.g., "exec_1")
            message: Message to inject (user's instruction or modification)

        Returns:
            Confirmation or error string.
        """
        if not self._session:
            return "Error: Session not initialized"

        handle = self._session._running_executors.get(executor_id)
        if not handle:
            available = list(self._session._running_executors.keys())
            return f"Error: No running executor with ID '{executor_id}'. Available: {available}"

        agent = handle.executor.get_current_agent()
        if not agent:
            return f"Executor {executor_id} exists but no agent is currently active"

        # Inject directly into the agent's per-agent steering queue
        # (bypasses the shared TaskState queue used by OrchestratorSession)
        agent.inject_steering_message(message)
        return f"Message injected to executor {executor_id} ({handle.task_label})"


class CancelTaskTool:
    """Cancel a running executor."""

    def __init__(self):
        self._session: Optional["OrchestratorSession"] = None

    def set_session(self, session: "OrchestratorSession") -> None:
        self._session = session

    def cancel_task(self, executor_id: str) -> str:
        """
        Cancel a running executor, stopping its current work.

        Args:
            executor_id: ID of the executor to cancel (e.g., "exec_1")

        Returns:
            Confirmation or error string.
        """
        if not self._session:
            return "Error: Session not initialized"

        handle = self._session._running_executors.get(executor_id)
        if not handle:
            available = list(self._session._running_executors.keys())
            return f"Error: No running executor with ID '{executor_id}'. Available: {available}"

        handle.executor.stop()
        handle.async_task.cancel()
        return f"Executor {executor_id} ({handle.task_label}) is being cancelled"


class ReplanTaskTool:
    """Replace pending subtasks of a running executor with a new plan."""

    def __init__(self):
        self._session: Optional["OrchestratorSession"] = None

    def set_session(self, session: "OrchestratorSession") -> None:
        self._session = session

    async def replan_task(self, executor_id: str, new_plan: str) -> str:
        """
        Replace pending subtasks of a running executor with a new plan.

        Use this when the user wants to change scope, add requirements,
        or redirect a running task. DONE and RUNNING subtasks are preserved.

        Args:
            executor_id: ID of the target executor (e.g., "exec_1")
            new_plan: JSON array of subtask objects. Each object must have:
                - id (str): Unique subtask ID (must not collide with existing non-PENDING IDs)
                - content (str): Task description
                - agent_type (str): "browser", "document", "code", or "multi_modal"
                - depends_on (list[str], optional): IDs of subtasks this depends on

        Returns:
            Confirmation or error string.
        """
        import json
        from .ami_task_executor import AMISubtask, SubtaskState

        if not self._session:
            return "Error: Session not initialized"

        handle = self._session._running_executors.get(executor_id)
        if not handle:
            available = list(self._session._running_executors.keys())
            return f"Error: No running executor with ID '{executor_id}'. Available: {available}"

        # Check if executor already completed
        if handle.async_task.done():
            return f"Error: Executor {executor_id} has already completed"

        # Parse new_plan JSON
        try:
            plan_list = json.loads(new_plan)
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON in new_plan: {e}"

        if not isinstance(plan_list, list):
            return "Error: new_plan must be a JSON array of subtask objects"

        # Validate structure and build AMISubtask list
        valid_agent_types = set(handle.executor._agents.keys())
        new_subtasks = []
        for i, item in enumerate(plan_list):
            if not isinstance(item, dict):
                return f"Error: Item {i} is not an object"
            for required in ("id", "content", "agent_type"):
                if required not in item:
                    return f"Error: Item {i} missing required field '{required}'"
            if item["agent_type"] not in valid_agent_types:
                return (
                    f"Error: Item {i} has invalid agent_type '{item['agent_type']}'. "
                    f"Valid types: {sorted(valid_agent_types)}"
                )
            new_subtasks.append(AMISubtask(
                id=item["id"],
                content=item["content"],
                agent_type=item["agent_type"],
                depends_on=item.get("depends_on", []),
                state=SubtaskState.PENDING,
            ))

        # Apply replan: pause → modify → resume
        # Since this is async and runs on the event loop thread, the executor's
        # coroutines are suspended at await points during this synchronous section.
        # No thread-safety issue — all mutations happen on the event loop thread.
        executor = handle.executor
        executor.pause()
        try:
            result = executor.replan_subtasks(new_subtasks)
        except ValueError as e:
            executor.resume()
            return f"Error: Dependency validation failed: {e}"

        executor.resume()

        # Update handle.subtasks reference
        handle.subtasks = executor._subtasks

        # Update _task_state.subtasks — replace this executor's entries, keep others
        if self._session._task_state:
            existing_state_subtasks = getattr(self._session._task_state, 'subtasks', None) or []
            other_subtasks = [
                s for s in existing_state_subtasks
                if s.get("executor_id") != executor_id
            ]
            new_state_subtasks = [
                {
                    "id": st.id,
                    "content": st.content,
                    "state": st.state.value,
                    "status": st.state.value,
                    "agent_type": st.agent_type,
                    "executor_id": executor_id,
                }
                for st in executor._subtasks
            ]
            self._session._task_state.subtasks = other_subtasks + new_state_subtasks

        # Emit TaskReplannedData
        from ..events import TaskReplannedData
        all_subtask_dicts = [
            {
                "id": st.id,
                "content": st.content,
                "state": st.state.value,
                "status": st.state.value,
                "agent_type": st.agent_type,
                "depends_on": st.depends_on,
                "executor_id": executor_id,
            }
            for st in executor._subtasks
        ]
        await self._session._task_state.put_event(TaskReplannedData(
            task_id=self._session._task_id,
            subtasks=all_subtask_dicts,
            reason="User-requested replan",
            executor_id=executor_id,
            task_label=handle.task_label,
        ))

        return (
            f"Replan successful for {executor_id} ({handle.task_label}): "
            f"removed {result['removed_count']} pending, added {result['added_count']} new. "
            f"Kept subtasks: {result['kept_ids']}"
        )


@dataclass
class ExecutorHandle:
    """Tracks a running executor and its async task."""

    executor_id: str
    task_label: str
    executor: Any  # AMITaskExecutor
    async_task: asyncio.Task
    subtasks: List[Any]  # List[AMISubtask]
    started_at: datetime.datetime = dc_field(default_factory=datetime.datetime.now)


# Idle timeout: how long to wait for user input when no executors are running.
# After this, the session exits gracefully to avoid leaking resources.
SESSION_IDLE_TIMEOUT_SECONDS = 30 * 60  # 30 minutes


class OrchestratorSession:
    """
    Persistent Orchestrator session that lives for the entire task lifecycle.

    Runs a loop: wait for event -> Orchestrator.astep() -> handle result -> repeat.
    Events: user messages from queue, executor completions from asyncio tasks.
    """

    def __init__(
        self,
        orchestrator: AMIAgent,
        decompose_tool: DecomposeTaskTool,
        attach_tool: AttachFileTool,
        inject_tool: InjectMessageTool,
        cancel_tool: CancelTaskTool,
        task_state: Any,
        task_id: str,
        create_agents_fn: Callable,
        create_memory_toolkit_fn: Callable,
        collect_files_fn: Callable,
        create_attachment_fn: Callable,
        cloud_client: Optional[Any] = None,
        user_id: Optional[str] = None,
        replan_tool: Optional[ReplanTaskTool] = None,
    ):
        self._orchestrator = orchestrator
        self._decompose_tool = decompose_tool
        self._attach_tool = attach_tool
        self._inject_tool = inject_tool
        self._cancel_tool = cancel_tool
        self._replan_tool = replan_tool
        self._task_state = task_state
        self._task_id = task_id

        # Executor management
        self._running_executors: Dict[str, ExecutorHandle] = {}
        self._executor_counter = 0
        # Sequential execution lock: only one executor runs at a time.
        # Additional decompose_task calls queue up and wait.
        # This prevents browser tab state conflicts from parallel executors.
        self._executor_lock = asyncio.Lock()

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

    def stop_all_executors(self) -> None:
        """Stop all running executors. Used by external cancellation."""
        for eid, handle in self._running_executors.items():
            if not handle.async_task.done():
                handle.executor.stop()
                logger.info(f"[OrchestratorSession] Stopped executor {eid} via external cancel")

    async def run(self, initial_message: str) -> None:
        """Main session loop."""
        from ..events import WaitConfirmData, ConfirmedData

        message = initial_message

        while True:
            # 1. Collect completed executor results
            completed_msgs = await self._collect_completed()
            if completed_msgs:
                results_block = "\n\n".join(completed_msgs)
                if message:
                    message = f"{results_block}\n\n[USER MESSAGE]\n{message}"
                else:
                    message = results_block

            # 2. Build active tasks context for system prompt
            active_ctx = self._build_active_tasks_context()

            # 3. Update orchestrator's system prompt with active tasks context
            self._update_system_prompt(active_ctx)

            # 4. Reset tools and call Orchestrator
            self._decompose_tool.reset()
            self._attach_tool.reset()

            logger.info(f"[OrchestratorSession] Calling astep with: {message[:200]}...")
            response = await self._orchestrator.astep(message)
            orchestrator_reply = response.text

            # 5. Handle decompose_task trigger
            if self._decompose_tool.triggered:
                task_desc = self._decompose_tool.task_description
                logger.info(f"[OrchestratorSession] decompose_task triggered: {task_desc[:100]}...")

                # Emit confirmed event
                await self._task_state.put_event(ConfirmedData(
                    task_id=self._task_id,
                    question=task_desc,
                ))

                await self._supervised_execute(task_desc)

            # 6. Emit Orchestrator's reply to user
            if orchestrator_reply:
                attachments = await self._build_attachments()
                await self._emit_reply(orchestrator_reply, attachments)

            # 7. Wait for next event (user message or executor completion)
            message = await self._wait_for_event()
            if message is None:
                logger.info("[OrchestratorSession] Session ending (no more waitables)")
                break

    async def _supervised_execute(self, task_description: str) -> None:
        """Plan subtasks and spawn a non-blocking executor."""
        from .ami_task_planner import AMITaskPlanner
        from .ami_task_executor import AMITaskExecutor
        from ..events import (
            TaskDecomposedData,
            AgentReportData,
            WorkforceStartedData,
            NoticeData,
        )
        from ..i18n import t as _t
        import html as html_mod

        # Ensure agents are created (lazy init)
        if self._agents_dict is None:
            self._agents_dict, self._planner_provider = await self._create_agents_fn()
            # Disable shared queue fallback — Orchestrator owns the shared queue,
            # child agents must only receive messages via inject_steering_message().
            for agent in self._agents_dict.values():
                agent._disable_shared_queue = True
            logger.info(f"[OrchestratorSession] Agents created: {list(self._agents_dict.keys())}")

        # Generate executor ID and label
        self._executor_counter += 1
        executor_id = f"exec_{self._executor_counter}"
        task_label = task_description[:20].strip()

        # Plan subtasks
        memory_toolkit = await self._create_memory_toolkit_fn()
        planner = AMITaskPlanner(
            task_id=self._task_id,
            task_state=self._task_state,
            provider=self._planner_provider,
            memory_toolkit=memory_toolkit,
        )

        logger.info(f"[OrchestratorSession] Decomposing for {executor_id}...")
        subtasks = await planner.decompose_and_query_memory(task_description)

        if not subtasks:
            logger.warning(f"[OrchestratorSession] Decomposition returned no subtasks for {executor_id}")
            await self._task_state.put_event(NoticeData(
                task_id=self._task_id,
                level="warning",
                title="Decomposition Failed",
                message="Could not decompose task into subtasks.",
            ))
            return

        # Store subtask info on task state for frontend
        # Append to existing subtasks to support parallel executors
        new_subtask_dicts = [
            {
                "id": st.id,
                "content": st.content,
                "state": st.state.value,
                "status": st.state.value,
                "agent_type": st.agent_type,
                "memory_level": st.memory_level,
                "executor_id": executor_id,
            }
            for st in subtasks
        ]
        existing = getattr(self._task_state, 'subtasks', None) or []
        self._task_state.subtasks = existing + new_subtask_dicts
        self._task_state.summary_task = task_description

        # Emit TaskDecomposedData (only new subtasks, not accumulated)
        await self._task_state.put_event(TaskDecomposedData(
            task_id=self._task_id,
            subtasks=new_subtask_dicts,
            summary_task=task_description,
            total_subtasks=len(subtasks),
            executor_id=executor_id,
            task_label=task_label,
        ))

        # Emit human-readable subtask list
        lang = getattr(self._task_state, 'user_language', 'en')
        type_labels = {
            k: _t(f"service.type.{k}", lang)
            for k in ("browser", "document", "code", "multi_modal")
        }
        li_items = []
        for st in subtasks:
            label = type_labels.get(st.agent_type, st.agent_type)
            preview = st.content[:60] + ("..." if len(st.content) > 60 else "")
            li_items.append(f"<li>[{html_mod.escape(label)}] {html_mod.escape(preview)}</li>")
        await self._task_state.put_event(AgentReportData(
            task_id=self._task_id,
            message=(
                f"{_t('service.task_decomposed', lang, count=len(subtasks))}\n\n"
                f"<details><summary>{_t('service.view_subtasks', lang)}</summary>"
                f"<ol>{''.join(li_items)}</ol></details>"
            ),
            report_type="info",
            executor_id=executor_id,
            task_label=task_label,
        ))

        # Clone agents for this executor — each executor needs its own agent
        # instances to avoid conversation history and state corruption when
        # parallel executors use the same agent type simultaneously.
        # Clones share provider and tools (lightweight) but have fresh state.
        executor_agents = {
            name: agent.clone() for name, agent in self._agents_dict.items()
        }

        # Create executor
        executor = AMITaskExecutor(
            task_id=self._task_id,
            task_state=self._task_state,
            agents=executor_agents,
            user_request=task_description,
            cloud_client=self._cloud_client,
            user_id=self._user_id,
            executor_id=executor_id,
            task_label=task_label,
        )
        executor.set_subtasks(subtasks)

        # Note: we don't set _task_state._executor per-executor (would only track last one).
        # External cancellation uses _task_state._orchestrator_session.stop_all_executors().

        # Emit WorkforceStartedData
        await self._task_state.put_event(WorkforceStartedData(
            task_id=self._task_id,
            total_tasks=len(subtasks),
            workers_count=len(self._agents_dict),
            description=f"Starting execution: {task_label}",
            executor_id=executor_id,
            task_label=task_label,
        ))

        # Spawn non-blocking, but sequential: acquire _executor_lock before
        # running execute(). Planning + SSE events fire immediately so the user
        # sees the subtask list, but actual execution waits for prior executors.
        async def _run_with_lock(ex: AMITaskExecutor, eid: str) -> Dict:
            async with self._executor_lock:
                logger.info(f"[OrchestratorSession] Executor {eid} acquired lock, starting")
                return await ex.execute()

        async_task = asyncio.create_task(
            _run_with_lock(executor, executor_id),
            name=f"executor_{executor_id}",
        )

        # Register
        self._running_executors[executor_id] = ExecutorHandle(
            executor_id=executor_id,
            task_label=task_label,
            executor=executor,
            async_task=async_task,
            subtasks=subtasks,
        )

        logger.info(f"[OrchestratorSession] Spawned {executor_id} with {len(subtasks)} subtasks")

    async def _wait_for_event(self) -> Optional[str]:
        """Wait for user message or executor completion.

        Returns:
            User message string, "" if executor completed, None if session should end.
        """
        waitables = set()

        # When no executors are running, apply idle timeout to avoid
        # leaking resources on abandoned sessions.
        has_active_executors = any(
            not h.async_task.done() for h in self._running_executors.values()
        )
        timeout = None if has_active_executors else SESSION_IDLE_TIMEOUT_SECONDS

        user_msg_task = asyncio.create_task(
            self._task_state.get_user_message(),
            name="user_message_wait",
        )
        waitables.add(user_msg_task)

        for handle in self._running_executors.values():
            if not handle.async_task.done():
                waitables.add(handle.async_task)

        try:
            done, pending = await asyncio.wait(
                waitables, return_when=asyncio.FIRST_COMPLETED, timeout=timeout,
            )
        except Exception:
            user_msg_task.cancel()
            raise

        # Timeout: no event within idle timeout — end session
        if not done:
            logger.info(
                f"[OrchestratorSession] Idle timeout ({SESSION_IDLE_TIMEOUT_SECONDS}s) "
                f"with no executors running, ending session"
            )
            user_msg_task.cancel()
            try:
                await user_msg_task
            except asyncio.CancelledError:
                pass
            return None

        # Cancel the user message wait if an executor completed instead.
        # Guard against message loss: if the task already completed with a
        # result (message dequeued but task not yet in 'done'), put it back.
        if user_msg_task in pending:
            user_msg_task.cancel()
            try:
                await user_msg_task
            except asyncio.CancelledError:
                pass
            # Check if a message was retrieved before cancel took effect
            if user_msg_task.done() and not user_msg_task.cancelled():
                try:
                    lost_msg = user_msg_task.result()
                    if lost_msg is not None:
                        logger.info(
                            f"[OrchestratorSession] Recovering message from cancelled wait: "
                            f"{lost_msg[:100]}..."
                        )
                        await self._task_state.put_user_message(lost_msg)
                except asyncio.CancelledError:
                    pass  # Task was properly cancelled, no message to recover
                except Exception as e:
                    logger.warning(
                        f"[OrchestratorSession] Failed to recover message from "
                        f"cancelled wait: {e}"
                    )

        for task in done:
            if task is user_msg_task:
                result = task.result()
                if result is None:
                    return None  # Cancelled or timeout
                logger.info(f"[OrchestratorSession] User message received: {result[:100]}...")
                return result

        # Executor(s) completed — return empty string to trigger result collection
        return ""

    async def _collect_completed(self) -> List[str]:
        """Check for completed executors and format their results."""
        from ..events import WorkforceCompletedData, AgentReportData
        from ..i18n import t as _t

        messages = []
        completed_ids = []

        for eid, handle in self._running_executors.items():
            if handle.async_task.done():
                completed_ids.append(eid)
                try:
                    result = handle.async_task.result()
                    msg = self._format_execution_result(handle, result)
                    messages.append(msg)

                    duration = (datetime.datetime.now() - handle.started_at).total_seconds()

                    # Record task_result in conversation history
                    if hasattr(self._task_state, 'add_conversation'):
                        self._task_state.add_conversation("task_result", {
                            "task_content": handle.task_label,
                            "task_result": msg,
                            "executor_id": eid,
                            "working_directory": getattr(self._task_state, 'working_directory', ''),
                        })

                    # Update state.result for status tracking
                    self._task_state.result = {
                        "success": result.get("failed", 0) == 0,
                        "message": msg,
                        "data": {
                            "completed": result.get("completed", 0),
                            "failed": result.get("failed", 0),
                            "duration": duration,
                        },
                    }

                    # Emit WorkforceCompletedData
                    await self._task_state.put_event(WorkforceCompletedData(
                        task_id=self._task_id,
                        completed_count=result.get("completed", 0),
                        failed_count=result.get("failed", 0),
                        total_count=result.get("total", 0),
                        duration_seconds=duration,
                        executor_id=eid,
                        task_label=handle.task_label,
                    ))

                    # Emit completion report
                    lang = getattr(self._task_state, 'user_language', 'en')
                    if result.get("failed", 0) == 0:
                        await self._task_state.put_event(AgentReportData(
                            task_id=self._task_id,
                            message=_t("service.all_completed", lang,
                                       count=result.get("completed", 0)),
                            report_type="success",
                            executor_id=eid,
                            task_label=handle.task_label,
                        ))
                    else:
                        await self._task_state.put_event(AgentReportData(
                            task_id=self._task_id,
                            message=_t("service.execution_summary", lang,
                                       completed=result.get("completed", 0),
                                       failed=result.get("failed", 0)),
                            report_type="warning",
                            executor_id=eid,
                            task_label=handle.task_label,
                        ))

                except asyncio.CancelledError:
                    # Executor was cancelled (via cancel_task tool)
                    logger.info(f"[OrchestratorSession] Executor {eid} was cancelled")
                    messages.append(
                        f"[EXECUTION CANCELLED] {eid} ({handle.task_label}): Task was cancelled by user"
                    )

                    from ..events import WorkforceStoppedData as _WfStopped
                    await self._task_state.put_event(_WfStopped(
                        task_id=self._task_id,
                        reason="Cancelled by user",
                        executor_id=eid,
                        task_label=handle.task_label,
                    ))

                except Exception as e:
                    logger.exception(f"[OrchestratorSession] Executor {eid} failed: {e}")
                    messages.append(
                        f"[EXECUTION FAILED] {eid} ({handle.task_label}): {e}"
                    )

                    from ..events import WorkforceStoppedData as _WfStopped
                    await self._task_state.put_event(_WfStopped(
                        task_id=self._task_id,
                        reason=str(e),
                        executor_id=eid,
                        task_label=handle.task_label,
                    ))

        for eid in completed_ids:
            del self._running_executors[eid]

        return messages

    def _format_execution_result(self, handle: ExecutorHandle, result: dict) -> str:
        """Format executor result as a message for Orchestrator."""
        duration = (datetime.datetime.now() - handle.started_at).total_seconds()

        subtask_summaries = []
        for st in handle.subtasks:
            status = st.state.value
            result_text = st.result or "No result"
            if len(result_text) > 500:
                result_text = result_text[:500] + "..."
            preview = st.content[:80]
            subtask_summaries.append(f"  - [{status}] {preview}: {result_text}")

        # Collect workspace files
        file_listing = ""
        try:
            from ..workspace import get_current_manager
            manager = get_current_manager()
            if manager and manager.workspace.exists():
                files = [f.name for f in sorted(manager.workspace.iterdir()) if f.is_file()]
                if files:
                    file_listing = f"\nFiles in workspace: {', '.join(files)}"
        except Exception:
            pass

        return (
            f"[EXECUTION COMPLETE] {handle.executor_id} ({handle.task_label})\n"
            f"Duration: {duration:.0f}s | "
            f"Completed: {result.get('completed', 0)}/{result.get('total', 0)} | "
            f"Failed: {result.get('failed', 0)}\n"
            f"Subtask Results:\n" + "\n".join(subtask_summaries) +
            file_listing
        )

    def _build_active_tasks_context(self) -> str:
        """Build active executor status with subtask-level detail for system prompt."""
        if not self._running_executors:
            return ""

        lines = ["## Currently Running Tasks"]
        for eid, handle in self._running_executors.items():
            progress = handle.executor.get_progress()
            lines.append(
                f"\n### {eid} ({handle.task_label})"
            )
            lines.append(
                f"Progress: {progress['done']}/{progress['total']} done, "
                f"{progress['running']} running, {progress['pending']} pending"
            )

            # Show subtask-level detail
            state_icons = {
                "DONE": "[OK]",
                "RUNNING": "[>>]",
                "PENDING": "[..]",
                "FAILED": "[XX]",
            }
            for detail in handle.executor.get_subtasks_detail():
                icon = state_icons.get(detail["state"], "[??]")
                deps = f"  depends_on={detail['depends_on']}" if detail["depends_on"] else ""
                result_info = ""
                if detail["result_preview"]:
                    result_info = f'  result="{detail["result_preview"]}"'
                content = detail["content"][:80]
                if len(detail["content"]) > 80:
                    content += "..."
                lines.append(
                    f"  {icon} {detail['id']} ({detail['agent_type']}): "
                    f"{content}{deps}{result_info}"
                )

        return "\n".join(lines)

    def _update_system_prompt(self, active_ctx: str) -> None:
        """Update orchestrator's system prompt with active tasks context."""
        # The base system prompt has {active_tasks_context} placeholder
        # We rebuild the full prompt each time
        base_prompt = ORCHESTRATOR_SYSTEM_PROMPT.format(
            platform_system=platform.system(),
            platform_machine=platform.machine(),
            user_workspace=self._get_user_workspace(),
            now_str=_get_now_str(),
            active_tasks_context=active_ctx,
        )
        self._orchestrator._system_prompt = base_prompt

    def _get_user_workspace(self) -> str:
        """Get user workspace path for system prompt."""
        user_id = self._user_id or "default"
        return str(WorkingDirectoryManager.USERS_DIR / user_id / "projects" / "default" / "tasks")

    async def _build_attachments(self) -> List[Any]:
        """Convert attach_tool files to FileAttachment objects."""
        attachments = []
        for file_path_str in self._attach_tool.attached_files:
            try:
                attachment = await self._create_attachment_fn(Path(file_path_str))
                if attachment:
                    attachments.append(attachment)
            except Exception as e:
                logger.warning(f"[OrchestratorSession] Failed to create attachment for {file_path_str}: {e}")
        return attachments

    async def _emit_reply(self, text: str, attachments: List[Any]) -> None:
        """Emit orchestrator's reply as WaitConfirmData."""
        from ..events import WaitConfirmData

        # Record in conversation history
        if hasattr(self._task_state, 'add_conversation'):
            self._task_state.add_conversation("assistant", text)

        await self._task_state.put_event(WaitConfirmData(
            task_id=self._task_id,
            content=text,
            question="",
            context="initial",
            attachments=attachments if attachments else None,
        ))

        # Set status: WAITING only if no executors running, else keep RUNNING.
        # This ensures frontend shows correct task state (spinner vs input prompt).
        if hasattr(self._task_state, 'status'):
            has_running = any(
                not h.async_task.done() for h in self._running_executors.values()
            )
            target_status = "running" if has_running else "waiting"
            status_cls = type(self._task_state.status)
            try:
                self._task_state.status = status_cls(target_status)
            except (ValueError, KeyError):
                self._task_state.status = target_status

        logger.info(f"[OrchestratorSession] Emitted reply ({len(text)} chars, {len(attachments)} attachments)")


async def create_orchestrator_agent(
    task_state: Any,
    task_id: str,
    working_directory: str,
    browser_data_directory: Optional[str] = None,
    headless: bool = False,
    memory_api_base_url: Optional[str] = None,
    ami_api_key: Optional[str] = None,
    user_id: Optional[str] = None,
    llm_api_key: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    decompose_callback: Optional[Callable[[str], Any]] = None,
) -> tuple[AMIAgent, DecomposeTaskTool, AttachFileTool, InjectMessageTool, CancelTaskTool, ReplanTaskTool]:
    """
    Create the Orchestrator Agent with all toolkits.

    Returns:
        Tuple of (AMIAgent, DecomposeTaskTool, AttachFileTool, InjectMessageTool, CancelTaskTool, ReplanTaskTool)
    """
    logger.info(f"[OrchestratorAgent] Creating for task {task_id}")
    logger.info(f"[OrchestratorAgent] Working directory: {working_directory}")

    agent_name = "orchestrator_agent"

    # Determine user workspace root (for Orchestrator to explore all user files)
    user_workspace = str(WorkingDirectoryManager.USERS_DIR / (user_id or "default") / "projects" / "default" / "tasks")
    logger.info(f"[OrchestratorAgent] User workspace: {user_workspace}")

    # Lazy import to avoid circular dependency (toolkits -> base_toolkit -> ami_tool -> core/__init__ -> orchestrator_agent)
    from ..tools.toolkits import (
        SearchToolkit,
        HumanToolkit,
        MemoryToolkit,
        TerminalToolkit,
    )

    # Initialize toolkits
    search_toolkit = SearchToolkit()
    search_toolkit.set_task_state(task_state)

    human_toolkit = HumanToolkit()
    human_toolkit.set_task_state(task_state)

    # Terminal toolkit for Orchestrator - uses user workspace root (not task workspace)
    terminal_toolkit = TerminalToolkit(working_directory=user_workspace)
    terminal_toolkit.set_task_state(task_state)
    logger.info("[OrchestratorAgent] TerminalToolkit added (user workspace root)")

    tools = [
        *search_toolkit.get_tools(),
        *human_toolkit.get_tools(),
        *terminal_toolkit.get_tools(),
    ]

    # Add memory toolkit if configured
    if memory_api_base_url and ami_api_key and user_id:
        memory_toolkit = MemoryToolkit(
            memory_api_base_url=memory_api_base_url,
            ami_api_key=ami_api_key,
            user_id=user_id,
        )
        memory_toolkit.set_task_state(task_state)
        tools.extend(memory_toolkit.get_tools())
        logger.info("[OrchestratorAgent] MemoryToolkit added")

    # Create and add decompose_task tool (wrap bound method in AMITool)
    decompose_tool = DecomposeTaskTool(
        callback=decompose_callback or (lambda x: x)
    )
    decompose_ami_tool = AMITool(decompose_tool.decompose_task)
    decompose_ami_tool._toolkit_name = "Orchestrator"
    tools.append(decompose_ami_tool)
    logger.info("[OrchestratorAgent] DecomposeTaskTool added")

    # Create and add attach_file tool
    attach_tool = AttachFileTool()
    attach_ami_tool = AMITool(attach_tool.attach_file)
    attach_ami_tool._toolkit_name = "Orchestrator"
    tools.append(attach_ami_tool)
    logger.info("[OrchestratorAgent] AttachFileTool added")

    # Create and add inject_message tool (session wired later)
    inject_tool = InjectMessageTool()
    inject_ami_tool = AMITool(inject_tool.inject_message)
    inject_ami_tool._toolkit_name = "Orchestrator"
    tools.append(inject_ami_tool)
    logger.info("[OrchestratorAgent] InjectMessageTool added")

    # Create and add cancel_task tool (session wired later)
    cancel_tool = CancelTaskTool()
    cancel_ami_tool = AMITool(cancel_tool.cancel_task)
    cancel_ami_tool._toolkit_name = "Orchestrator"
    tools.append(cancel_ami_tool)
    logger.info("[OrchestratorAgent] CancelTaskTool added")

    # Create and add replan_task tool (session wired later)
    replan_tool = ReplanTaskTool()
    replan_ami_tool = AMITool(replan_tool.replan_task)
    replan_ami_tool._toolkit_name = "Orchestrator"
    tools.append(replan_ami_tool)
    logger.info("[OrchestratorAgent] ReplanTaskTool added")

    # Build system prompt
    system_message = ORCHESTRATOR_SYSTEM_PROMPT.format(
        platform_system=platform.system(),
        platform_machine=platform.machine(),
        user_workspace=user_workspace,
        now_str=_get_now_str(),
        active_tasks_context="",
    )

    # Create provider
    provider = create_provider(
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
    )

    # Create the agent
    agent = AMIAgent(
        task_state=task_state,
        agent_name=agent_name,
        provider=provider,
        system_prompt=system_message,
        tools=tools,
    )

    # Set agent reference in toolkits (for memory caching)
    if memory_api_base_url and ami_api_key and user_id:
        memory_toolkit.set_agent(agent)

    # Set agent reference in decompose_tool so it can stop the agent loop
    decompose_tool.set_agent(agent)

    logger.info(f"[OrchestratorAgent] Created with {len(tools)} tools")
    return agent, decompose_tool, attach_tool, inject_tool, cancel_tool, replan_tool


