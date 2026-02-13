"""
ReplanToolkit - Agent-initiated dynamic task splitting during execution.

Gives the executing agent 2 tools following a "review then split" protocol:
1. replan_review_context() — View full execution context before deciding
2. replan_split_and_handoff() — Save progress and split remaining work

This toolkit holds a live reference to AMITaskExecutor and directly
calls executor.add_subtasks_async() when the agent decides to split work.

All tools are async to stay on the main event loop (avoiding thread-safety
issues with SSE event emission via asyncio.to_thread).
"""

import json
import logging
from typing import List, Optional, TYPE_CHECKING

from .base_toolkit import BaseToolkit, FunctionTool

if TYPE_CHECKING:
    from ...core.ami_task_executor import AMITaskExecutor
    from ...core.ami_agent import AMIAgent

logger = logging.getLogger(__name__)


class ReplanToolkit(BaseToolkit):
    """Agent-initiated dynamic task splitting during execution.

    Allows the executing agent to split large tasks into smaller follow-up
    subtasks that are added to the executor's queue. This prevents LLM
    laziness on multi-item tasks (e.g., "extract 19 products" -> agent does 5
    then summarizes).

    Two-tool protocol:
    1. replan_review_context() — see what's done, running, pending, and
       what files exist in workspace. MUST call before splitting.
    2. replan_split_and_handoff(summary, tasks) — save progress as result,
       add follow-up tasks, and stop the agent.
    """

    agent_name: str = "replan_agent"

    def __init__(
        self,
        executor: "AMITaskExecutor",
        current_subtask_id: str,
        agent: "AMIAgent",
        timeout: Optional[float] = None,
    ) -> None:
        """Initialize the ReplanToolkit.

        Args:
            executor: Live AMITaskExecutor instance.
            current_subtask_id: ID of the subtask currently being executed.
            agent: The AMIAgent executing this subtask (for early-stop signaling).
            timeout: Optional timeout for operations.
        """
        super().__init__(timeout=timeout)
        self._executor = executor
        self._current_subtask_id = current_subtask_id
        self._agent = agent
        self._handoff_result: Optional[str] = None
        self._add_tasks_call_count: int = 0  # Track calls to generate unique IDs

        logger.info(
            f"[ReplanToolkit] Initialized for subtask {current_subtask_id}"
        )

    async def replan_review_context(self) -> str:
        """Review the full execution context before deciding how to split work.

        ALWAYS call this BEFORE replan_split_and_handoff.
        Returns completed task results, current task status, pending tasks,
        and workspace files.

        Returns:
            Formatted execution context with task states and workspace files.
        """
        from ...core.ami_task_executor import SubtaskState

        sections = []

        # Group subtasks by state
        done, running, pending, failed = [], [], [], []
        for st in self._executor._subtasks:
            if st.state == SubtaskState.DONE:
                done.append(st)
            elif st.state == SubtaskState.RUNNING:
                running.append(st)
            elif st.state == SubtaskState.PENDING:
                pending.append(st)
            elif st.state == SubtaskState.FAILED:
                failed.append(st)

        # Completed: show result summary (truncated to 200 chars)
        if done:
            lines = []
            for st in done:
                result_preview = (
                    (st.result[:200] + "...")
                    if st.result and len(st.result) > 200
                    else (st.result or "(no result)")
                )
                lines.append(
                    f"  [{st.id}] ({st.agent_type}): {st.content[:80]}\n"
                    f"    Result: {result_preview}"
                )
            sections.append("Completed tasks:\n" + "\n\n".join(lines))

        # Running: current task
        if running:
            lines = [
                f"  [{st.id}] ({st.agent_type}): {st.content[:120]}"
                for st in running
            ]
            sections.append("Current task (you):\n" + "\n".join(lines))

        # Failed
        if failed:
            lines = []
            for st in failed:
                error_preview = (
                    (st.error[:200] + "...")
                    if st.error and len(st.error) > 200
                    else (st.error or "(no error info)")
                )
                lines.append(
                    f"  [{st.id}] ({st.agent_type}): {st.content[:80]}\n"
                    f"    Error: {error_preview}"
                )
            sections.append("Failed tasks:\n" + "\n\n".join(lines))

        # Pending
        if pending:
            lines = [
                f"  [{st.id}] ({st.agent_type}): {st.content[:80]}"
                for st in pending
            ]
            sections.append("Pending tasks:\n" + "\n".join(lines))

        # Workspace files
        workspace_listing = self._executor._get_workspace_listing()
        if workspace_listing:
            sections.append(f"Workspace files:\n{workspace_listing}")

        return "=== Task Execution Context ===\n\n" + "\n\n".join(sections)

    async def replan_split_and_handoff(self, summary: str, tasks: str) -> str:
        """Save current progress and split remaining work into follow-up tasks.

        You MUST save all collected data to a file BEFORE calling this.
        After this call, STOP immediately — do not continue working.

        Args:
            summary: What you accomplished. This becomes the result for downstream tasks.
            tasks: JSON array of follow-up tasks.
                Format: [{"content": "task description", "agent_type": "browser"}, ...]
                agent_type must be one of: browser, document, code, multi_modal

        Returns:
            Handoff confirmation or error message.
        """
        self._handoff_result = summary

        try:
            result = await self._create_and_add_subtasks(tasks)
        except Exception as e:
            self._handoff_result = None
            raise  # Let _execute_tool catch and return error to agent

        if result.startswith("Error:"):
            self._handoff_result = None
            return result

        # Signal agent to stop after this tool-call round
        self._agent._should_stop_after_tool = True

        logger.info(
            f"[ReplanToolkit] Handoff from {self._current_subtask_id}: "
            f"summary={summary[:100]}..."
        )

        return (
            f"HANDOFF COMPLETE. {result}\n\n"
            f"STOP now. Do NOT continue. Follow-up tasks will handle the remaining work."
        )

    async def _create_and_add_subtasks(self, tasks: str) -> str:
        """Parse, validate, and add follow-up subtasks to the executor.

        Args:
            tasks: JSON string of task array.

        Returns:
            Confirmation message or "Error: ..." on failure.
        """
        # Parse JSON (handle both string and pre-parsed list from API proxies)
        if isinstance(tasks, list):
            task_list = tasks
        elif isinstance(tasks, str):
            try:
                task_list = json.loads(tasks)
            except json.JSONDecodeError as e:
                return f"Error: Invalid JSON format. {e}"
        else:
            return f"Error: tasks must be a JSON string or array, got {type(tasks).__name__}."

        if not isinstance(task_list, list):
            return "Error: tasks must be a JSON array."

        if not task_list:
            return "Error: tasks array is empty."

        # Validate each task
        valid_agent_types = set(self._executor._agents.keys())
        for i, task in enumerate(task_list):
            if not isinstance(task, dict):
                return f"Error: task at index {i} is not an object."
            if "content" not in task:
                return f"Error: task at index {i} missing 'content' field."
            if "agent_type" not in task:
                return f"Error: task at index {i} missing 'agent_type' field."
            if task["agent_type"] not in valid_agent_types:
                return (
                    f"Error: task at index {i} has invalid agent_type "
                    f"'{task['agent_type']}'. Valid types: {sorted(valid_agent_types)}"
                )

        # Build AMISubtask objects
        from ...core.ami_task_executor import AMISubtask

        parent = self._executor._subtask_map.get(self._current_subtask_id)

        # Use call count to ensure unique IDs across multiple calls
        self._add_tasks_call_count += 1
        batch = self._add_tasks_call_count

        # Inherit parent's dependencies so dynamic subtasks see the same
        # upstream context (e.g., product URL list from an earlier subtask).
        inherited_deps = (parent.depends_on if parent else []) + [self._current_subtask_id]
        logger.info(
            f"[ReplanToolkit] Creating dynamic subtasks from '{self._current_subtask_id}': "
            f"parent.depends_on={parent.depends_on if parent else None}, "
            f"inherited_deps={inherited_deps}"
        )

        new_subtasks = []
        for i, task in enumerate(task_list):
            subtask = AMISubtask(
                id=f"{self._current_subtask_id}_dyn_{batch}_{i + 1}",
                content=task["content"],
                agent_type=task["agent_type"],
                depends_on=list(inherited_deps),
                workflow_guide=parent.workflow_guide if parent else None,
                memory_level=parent.memory_level if parent else "L3",
            )
            new_subtasks.append(subtask)

        # Add to executor (emits SSE events internally)
        new_ids = await self._executor.add_subtasks_async(
            new_subtasks, after_subtask_id=self._current_subtask_id
        )

        return (
            f"Added {len(new_ids)} follow-up tasks: {new_ids}. "
            f"They will execute after the current subtask completes."
        )

    def get_tools(self) -> List[FunctionTool]:
        """Return tools for this toolkit."""
        return [
            FunctionTool(self.replan_review_context),
            FunctionTool(self.replan_split_and_handoff),
        ]

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "Replan Toolkit"
