"""
AMI Task Executor - Lightweight task execution system.

This module replaces CAMEL Workforce with a simpler, more controllable system:
- Direct control over prompt format (workflow_guide as explicit instruction)
- Sequential execution with dependency resolution
- SSE event emission for real-time UI updates
- Pause/resume support for multi-turn conversations

No CAMEL dependencies - uses AMIAgent for execution.
"""

import asyncio
import html as html_mod
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .ami_agent import AMIAgent

from ..events import (
    SubtaskStateData,
    AssignTaskData,
    WorkerAssignedData,
    NoticeData,
    AgentReportData,
)

logger = logging.getLogger(__name__)


class SubtaskState(Enum):
    """State of a subtask during execution."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


@dataclass
class AMISubtask:
    """
    Subtask representation for AMI task execution.

    Contains all information needed for execution including workflow guidance.
    This is a simpler alternative to CAMEL's Task object.
    """
    id: str
    content: str
    agent_type: str  # "browser" | "document" | "code" | "multi_modal"
    depends_on: List[str] = field(default_factory=list)

    # Memory/workflow guidance - injected directly into prompt
    workflow_guide: Optional[str] = None
    memory_level: str = "L3"  # L1=exact match, L2=partial, L3=no match

    # Execution state
    state: SubtaskState = SubtaskState.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0


class AMITaskExecutor:
    """
    Task executor that replaces CAMEL Workforce.

    Key features:
    - workflow_guide is injected as an explicit instruction in the prompt
    - Sequential execution with dependency resolution
    - SSE events for real-time UI updates
    - Pause/resume for multi-turn conversations
    - Simple retry logic

    Unlike CAMEL Workforce:
    - No agent pooling or cloning
    - No complex coordinator agent
    - Direct control over prompt format
    - ~250 lines vs ~6000 lines
    """

    def __init__(
        self,
        task_id: str,
        task_state: Any,  # TaskState for SSE events
        agents: Dict[str, "AMIAgent"],  # {"browser": agent, "document": agent, ...}
        max_retries: int = 2,
        user_request: str = "",  # User's original request for context
    ):
        """
        Initialize the executor.

        Args:
            task_id: Unique task identifier for events.
            task_state: TaskState instance for SSE event emission.
            agents: Dictionary mapping agent_type to ChatAgent instances.
            max_retries: Maximum retry attempts for failed subtasks.
            user_request: The user's original request (for agent context).
        """
        self.task_id = task_id
        self._task_state = task_state
        self._agents = agents
        self._max_retries = max_retries
        self._user_request = user_request

        # Subtask management
        self._subtasks: List[AMISubtask] = []
        self._subtask_map: Dict[str, AMISubtask] = {}

        # Pause/resume control
        self._paused = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially

        # Stop control
        self._stopped = False

        logger.info(
            f"[AMITaskExecutor] Initialized for task {task_id} "
            f"with agents: {list(agents.keys())}"
        )

    def set_subtasks(self, subtasks: List[AMISubtask]) -> None:
        """Set subtasks to execute."""
        self._subtasks = subtasks
        self._subtask_map = {s.id: s for s in subtasks}
        logger.info(f"[AMITaskExecutor] Set {len(subtasks)} subtasks")
        for st in subtasks:
            deps = f" depends_on={st.depends_on}" if st.depends_on else ""
            guide = f" guide={st.memory_level}" if st.memory_level else ""
            logger.info(
                f"[AMITaskExecutor] Subtask {st.id} ({st.agent_type}): "
                f"{st.content[:120]}{deps}{guide}"
            )

    async def execute(self) -> Dict[str, Any]:
        """
        Execute all subtasks respecting dependencies.

        Returns:
            Dictionary with execution results:
            - completed: number of completed subtasks
            - failed: number of failed subtasks
            - stopped: whether execution was stopped
        """
        logger.info(
            f"[AMITaskExecutor] Starting execution of {len(self._subtasks)} subtasks"
        )

        completed = 0
        failed = 0

        while not self._stopped:
            # Wait if paused
            await self._wait_if_paused()

            if self._stopped:
                break

            # Find next executable subtask (dependencies satisfied)
            subtask = self._get_next_subtask()
            if subtask is None:
                # No more subtasks to execute
                break

            # Execute the subtask
            success = await self._execute_subtask(subtask)

            if success:
                completed += 1
            else:
                failed += 1
                # Continue with other subtasks even if one fails
                # (unless they depend on the failed one)

        result = {
            "completed": completed,
            "failed": failed,
            "stopped": self._stopped,
            "total": len(self._subtasks),
        }

        logger.info(f"[AMITaskExecutor] Execution finished: {result}")
        return result

    def _get_next_subtask(self) -> Optional[AMISubtask]:
        """
        Get the next subtask that can be executed.

        A subtask can execute if:
        - Its state is PENDING
        - All its dependencies are DONE

        Returns None if no executable subtask found.
        """
        for subtask in self._subtasks:
            if subtask.state != SubtaskState.PENDING:
                continue

            # Check if all dependencies are satisfied
            deps_satisfied = True
            for dep_id in subtask.depends_on:
                dep = self._subtask_map.get(dep_id)
                if dep is None:
                    # Dependency reference is invalid - log and treat as unsatisfied
                    logger.warning(
                        f"[AMITaskExecutor] Subtask {subtask.id} depends on "
                        f"non-existent task '{dep_id}'. Marking as blocked."
                    )
                    deps_satisfied = False
                    break
                if dep.state != SubtaskState.DONE:
                    deps_satisfied = False
                    break

            if deps_satisfied:
                return subtask

        return None

    async def _execute_subtask(self, subtask: AMISubtask) -> bool:
        """
        Execute a single subtask using astep().

        Each subtask starts with a fresh conversation history (agent.reset()).
        Cross-subtask context is passed explicitly via _build_prompt()
        (dependency results injected into prompt, not via conversation history).

        Returns:
            True if successful, False otherwise.
        """
        # Get the appropriate agent
        agent = self._agents.get(subtask.agent_type)
        if agent is None:
            logger.error(
                f"[AMITaskExecutor] No agent for type: {subtask.agent_type}"
            )
            subtask.state = SubtaskState.FAILED
            subtask.error = f"No agent available for type: {subtask.agent_type}"
            await self._emit_subtask_state(subtask)
            return False

        # Reset agent conversation history — each subtask starts fresh.
        # Cross-subtask context is passed via prompt (dependency results + browser state).
        agent.reset()

        # Capture browser page state BEFORE reset clears agent's knowledge of it.
        # This gives the new subtask awareness of where the browser currently is.
        browser_context = await self._get_browser_context(agent)

        # Wire up retry notification: emit SSE when provider retries API calls
        self._setup_retry_notification(agent, subtask)

        # Mark as running and emit event
        subtask.state = SubtaskState.RUNNING
        await self._emit_subtask_running(subtask)

        # Execute with retries
        while subtask.retry_count <= self._max_retries:
            try:
                if self._stopped:
                    return False

                await self._wait_if_paused()

                logger.info(
                    f"[AMITaskExecutor] Executing subtask {subtask.id} "
                    f"(attempt {subtask.retry_count + 1}/{self._max_retries + 1})"
                )

                # Set memory context if agent supports it
                if hasattr(agent, 'set_memory_context') and subtask.workflow_guide:
                    agent.set_memory_context(
                        memory_result=None,
                        memory_level=subtask.memory_level,
                        workflow_guide=subtask.workflow_guide,
                    )
                    logger.info(
                        f"[AMITaskExecutor] Set memory context for {type(agent).__name__}: "
                        f"level={subtask.memory_level}, workflow_guide_len={len(subtask.workflow_guide)}"
                    )

                # Unified execution: build prompt and call astep()
                prompt = self._build_prompt(subtask, browser_context=browser_context)
                logger.info(
                    f"[AMITaskExecutor] Executing {type(agent).__name__}.astep() "
                    f"for subtask {subtask.id}"
                )
                response = await agent.astep(prompt)

                # Extract result
                subtask.result = response.text

                subtask.state = SubtaskState.DONE
                await self._emit_subtask_state(subtask)

                result_preview = str(subtask.result)[:200] if subtask.result else "(empty)"
                logger.info(
                    f"[AMITaskExecutor] Subtask {subtask.id} completed: "
                    f"{result_preview}"
                )
                return True

            except Exception as e:
                subtask.retry_count += 1
                subtask.error = str(e)

                logger.warning(
                    f"[AMITaskExecutor] Subtask {subtask.id} failed "
                    f"(attempt {subtask.retry_count}): {e}"
                )

                if subtask.retry_count > self._max_retries:
                    subtask.state = SubtaskState.FAILED
                    await self._emit_subtask_state(subtask)
                    return False

        return False

    async def _get_browser_context(self, agent: "AMIAgent") -> Optional[str]:
        """Get current browser page URL and title if agent has browser tools.

        Returns a lightweight context string (URL + title only, no full snapshot)
        so the agent knows where the browser is without wasting tokens.
        """
        snapshot_tool = agent.get_tool("browser_get_page_snapshot")
        if snapshot_tool is None:
            return None

        try:
            # Call the underlying toolkit method to get just page context.
            # The tool's func is a bound method on BrowserToolkit.
            toolkit = snapshot_tool.func.__self__
            context = await toolkit._get_page_context()
            if context:
                logger.info(f"[AMITaskExecutor] Browser context captured: {context[:120]}")
            return context or None
        except Exception as e:
            logger.debug(f"[AMITaskExecutor] Failed to get browser context: {e}")
            return None

    def _build_prompt(self, subtask: AMISubtask, browser_context: Optional[str] = None) -> str:
        """
        Build the execution prompt for a subtask.

        The workflow_guide is injected as an explicit instruction,
        not just as metadata. This ensures the LLM follows the steps.
        """
        parts = []

        # Browser state — tell agent where the browser currently is
        if browser_context:
            parts.append(f"## Current Browser State\n{browser_context}\n\nThe browser is already open on this page. You do NOT need to navigate here again — start working directly.")

        # Task content - this is the ONLY thing the agent should focus on
        parts.append(f"## Your Task\n{subtask.content}")

        # Workflow guide - as reference context
        if subtask.workflow_guide:
            parts.append(f"""
## Reference: Historical Workflow

The following is a workflow from a SIMILAR past task. Use it as background reference, NOT as a step-by-step instruction.

{subtask.workflow_guide}

**Important**:
- Your current task is ONLY what's described in "Your Task" above
- This workflow covers the ENTIRE original task, but you are only responsible for YOUR subtask
- Use this workflow to understand context (e.g. which site to visit, what elements look like)
- Do NOT execute steps that go beyond your assigned task
- When your specific task is complete, STOP immediately
""")
        else:
            parts.append("""
## Note
No historical workflow guide available. Please explore and complete the task using your best judgment.
""")

        # Previous results from dependencies
        dep_results = []
        for dep_id in subtask.depends_on:
            dep = self._subtask_map.get(dep_id)
            if dep and dep.result:
                if len(dep.result) > 2000:
                    # Large result: write to workspace file, inject file reference
                    file_ref = self._save_result_to_file(dep_id, dep.result)
                    dep_results.append(
                        f"### Result from task '{dep_id}':\n"
                        f"Result saved to file: {file_ref}\n"
                        f"Use `read_note` tool with note_name=\"{dep_id}_result\" to read the full data."
                    )
                else:
                    dep_results.append(f"### Result from task '{dep_id}':\n{dep.result}")

        if dep_results:
            parts.append("## Results from Previous Tasks\n" + "\n\n".join(dep_results))

        return "\n\n".join(parts)

    def _save_result_to_file(self, subtask_id: str, result: str) -> str:
        """Save large subtask result to a note file in workspace.

        Returns:
            The note name (without .md extension) for read_note access.
        """
        from ..workspace import get_current_manager

        note_name = f"{subtask_id}_result"
        manager = get_current_manager()
        if manager:
            file_path = manager.notes_dir / f"{note_name}.md"
            file_path.write_text(result, encoding="utf-8")
            logger.info(
                f"[AMITaskExecutor] Saved large result for {subtask_id} "
                f"to {file_path} ({len(result)} chars)"
            )
            return str(file_path)

        # Fallback: no workspace manager, just truncate
        logger.warning(
            f"[AMITaskExecutor] No WorkingDirectoryManager, "
            f"cannot save result file for {subtask_id}"
        )
        return f"(file save failed, result truncated): {result[:2000]}..."

    # =========================================================================
    # Provider Retry Notification
    # =========================================================================

    def _setup_retry_notification(self, agent: "AMIAgent", subtask: AMISubtask) -> None:
        """Wire up provider retry callback to emit SSE events."""
        provider = getattr(agent, '_provider', None)
        if provider is None or not hasattr(provider, 'set_on_retry_callback'):
            return

        progress = self._get_subtask_progress(subtask)

        async def on_retry(attempt: int, max_retries: int, delay: float, error_msg: str) -> None:
            if not self._task_state:
                return
            await self._task_state.put_event(AgentReportData(
                task_id=self.task_id,
                message=f"{progress} API error, retrying ({attempt}/{max_retries}) in {delay:.0f}s...",
                report_type="warning",
            ))

        provider.set_on_retry_callback(on_retry)

    @staticmethod
    def _classify_error(error_msg: str) -> str:
        """Classify error into user-friendly category."""
        if not error_msg:
            return ""
        lower = error_msg.lower()
        if any(kw in lower for kw in ("connection", "timeout", "timed out", "network", "unreachable", "dns")):
            return "Network connection error, please check your network"
        if any(kw in lower for kw in ("429", "rate limit", "too many requests")):
            return "API rate limited, please try again later"
        if any(kw in lower for kw in ("500", "502", "503", "504", "internal server error")):
            return "API server unstable, please try again later"
        if any(kw in lower for kw in ("400", "bad request")):
            return "API request error"
        if any(kw in lower for kw in ("401", "unauthorized", "authentication")):
            return "API key invalid or expired"
        return "Unexpected error"

    # =========================================================================
    # SSE Event Emission
    # =========================================================================

    def _get_subtask_progress(self, subtask: AMISubtask) -> str:
        """Get [index/total] progress string for a subtask."""
        total = len(self._subtasks)
        try:
            index = next(i for i, s in enumerate(self._subtasks, 1) if s.id == subtask.id)
        except StopIteration:
            index = 0
        return f"[{index}/{total}]"

    async def _emit_subtask_running(self, subtask: AMISubtask) -> None:
        """Emit events when subtask starts running."""
        if not self._task_state:
            return

        # Get agent name for display
        agent = self._agents.get(subtask.agent_type)
        agent_name = getattr(agent, 'agent_name', subtask.agent_type)

        # Report: Subtask starting with progress counter
        progress = self._get_subtask_progress(subtask)
        content_preview = subtask.content[:80]
        if len(subtask.content) > 80:
            content_preview += "..."
        await self._task_state.put_event(AgentReportData(
            task_id=self.task_id,
            message=f"{progress} 正在执行: {html_mod.escape(content_preview)}",
            report_type="info",
        ))

        # Emit assign_task event (for compatibility)
        await self._task_state.put_event(AssignTaskData(
            task_id=self.task_id,
            assignee_id=subtask.agent_type,
            subtask_id=subtask.id,
            content=subtask.content,
            state="running",
            failure_count=subtask.retry_count,
            worker_name=agent_name,
            agent_type=subtask.agent_type,
            agent_id=subtask.agent_type,
        ))

        # Emit subtask state
        await self._task_state.put_event(SubtaskStateData(
            task_id=self.task_id,
            subtask_id=subtask.id,
            state="RUNNING",
        ))

    async def _emit_subtask_state(self, subtask: AMISubtask) -> None:
        """Emit SSE event for subtask state change."""
        if not self._task_state:
            return

        # Report: Subtask state change with progress counter
        progress = self._get_subtask_progress(subtask)
        content_preview = subtask.content[:50]
        if len(subtask.content) > 50:
            content_preview += "..."
        safe_preview = html_mod.escape(content_preview)

        if subtask.state == SubtaskState.DONE:
            await self._task_state.put_event(AgentReportData(
                task_id=self.task_id,
                message=f"✓ {progress} 完成: {safe_preview}",
                report_type="success",
            ))
        elif subtask.state == SubtaskState.FAILED:
            # Classify error for user-friendly message
            error_hint = self._classify_error(subtask.error) if subtask.error else ""
            error_suffix = f" ({error_hint})" if error_hint else ""
            await self._task_state.put_event(AgentReportData(
                task_id=self.task_id,
                message=f"✗ {progress} 失败: {safe_preview}{error_suffix}",
                report_type="error",
            ))

        await self._task_state.put_event(SubtaskStateData(
            task_id=self.task_id,
            subtask_id=subtask.id,
            state=subtask.state.value,
        ))

    # =========================================================================
    # Pause/Resume/Stop Control
    # =========================================================================

    async def _wait_if_paused(self) -> None:
        """Wait if execution is paused."""
        if self._paused:
            logger.info(f"[AMITaskExecutor] Waiting (paused)")
            await self._pause_event.wait()

    def pause(self) -> None:
        """Pause execution."""
        self._paused = True
        self._pause_event.clear()
        logger.info(f"[AMITaskExecutor] Paused")

    def resume(self) -> None:
        """Resume execution."""
        self._paused = False
        self._pause_event.set()
        logger.info(f"[AMITaskExecutor] Resumed")

    def stop(self) -> None:
        """Stop execution."""
        self._stopped = True
        self._pause_event.set()  # Unblock if paused
        logger.info(f"[AMITaskExecutor] Stopped")

    @property
    def is_paused(self) -> bool:
        """Check if executor is paused."""
        return self._paused

    @property
    def is_stopped(self) -> bool:
        """Check if executor is stopped."""
        return self._stopped

    # =========================================================================
    # Progress Tracking
    # =========================================================================

    def get_progress(self) -> Dict[str, int]:
        """Get execution progress."""
        counts = {
            "total": len(self._subtasks),
            "pending": 0,
            "running": 0,
            "done": 0,
            "failed": 0,
        }

        for subtask in self._subtasks:
            if subtask.state == SubtaskState.PENDING:
                counts["pending"] += 1
            elif subtask.state == SubtaskState.RUNNING:
                counts["running"] += 1
            elif subtask.state == SubtaskState.DONE:
                counts["done"] += 1
            elif subtask.state == SubtaskState.FAILED:
                counts["failed"] += 1

        return counts

    def get_subtask(self, subtask_id: str) -> Optional[AMISubtask]:
        """Get a subtask by ID."""
        return self._subtask_map.get(subtask_id)

    def get_results(self) -> Dict[str, Optional[str]]:
        """Get all subtask results."""
        return {s.id: s.result for s in self._subtasks}
