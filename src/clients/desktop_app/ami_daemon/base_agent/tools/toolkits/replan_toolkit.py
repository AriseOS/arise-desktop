"""
ReplanToolkit - Agent-initiated dynamic task splitting during execution.

Gives the executing agent tools to:
1. View the current subtask list and their states
2. Report progress on the current subtask
3. Add new subtasks to the executor's queue
4. Complete current subtask and hand off remaining work

This toolkit holds a live reference to AMITaskExecutor and directly
calls executor.add_subtasks() when the agent decides to split work.

All tools are async to stay on the main event loop (avoiding thread-safety
issues with SSE event emission via asyncio.to_thread).
"""

import json
import logging
from typing import List, Optional, TYPE_CHECKING

from .base_toolkit import BaseToolkit, FunctionTool
from ...events.action_types import AgentReportData

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

    The toolkit holds a live reference to AMITaskExecutor. When the agent
    calls replan_add_tasks or replan_complete_and_handoff, new subtasks are
    injected directly into the executor's queue with depends_on set to
    the current subtask.
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

    async def replan_get_subtask_list(self) -> str:
        """View all subtasks and their current status.

        Returns a formatted list showing each subtask's ID, agent type,
        execution state (PENDING/RUNNING/DONE/FAILED), and content preview.
        Use this to understand the overall task landscape before deciding
        whether to split your current work.

        Returns:
            Formatted string listing all subtasks with their status.
        """
        lines = []
        for subtask in self._executor._subtasks:
            marker = ">" if subtask.id == self._current_subtask_id else " "
            content_preview = subtask.content[:80]
            if len(subtask.content) > 80:
                content_preview += "..."
            deps = f" depends_on={subtask.depends_on}" if subtask.depends_on else ""
            lines.append(
                f"{marker} [{subtask.state.value}] {subtask.id} "
                f"({subtask.agent_type}): {content_preview}{deps}"
            )

        return f"Subtask list ({len(self._executor._subtasks)} total):\n" + "\n".join(lines)

    async def replan_report_progress(
        self,
        items_completed: int,
        items_total: int,
        details: str,
    ) -> str:
        """Report progress on the current subtask.

        Call this periodically to report how many items you have processed
        out of the total. This helps track progress and prevents premature
        task completion.

        Args:
            items_completed: Number of items processed so far.
            items_total: Total number of items to process.
            details: Brief description of what was completed.

        Returns:
            Confirmation message with progress percentage.
        """
        progress_pct = (
            round(items_completed / items_total * 100) if items_total > 0 else 0
        )

        # Emit SSE event
        if self._task_state:
            await self._task_state.put_event(AgentReportData(
                task_id=self._executor.task_id,
                message=(
                    f"Progress: {items_completed}/{items_total} "
                    f"({progress_pct}%) - {details}"
                ),
                report_type="info",
            ))

        logger.info(
            f"[ReplanToolkit] Progress on {self._current_subtask_id}: "
            f"{items_completed}/{items_total} ({progress_pct}%) - {details}"
        )

        return (
            f"Progress reported: {items_completed}/{items_total} ({progress_pct}%). "
            f"{'Keep going - you have more items to process.' if items_completed < items_total else 'All items processed.'}"
        )

    async def replan_add_tasks(self, tasks: str) -> str:
        """Add follow-up tasks to the execution queue.

        Use this when you realize the current task involves more work than
        you can complete in one go. The new tasks will execute after the
        current subtask finishes.

        Args:
            tasks: JSON string describing the tasks to add.
                Format: [{"content": "task description", "agent_type": "browser"}, ...]
                agent_type must be one of: browser, document, code, multi_modal

        Returns:
            Confirmation with the IDs of newly created subtasks.
        """
        # Parse JSON
        try:
            task_list = json.loads(tasks)
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON format. {e}"

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

        # Use call count to ensure unique IDs across multiple replan_add_tasks calls
        self._add_tasks_call_count += 1
        batch = self._add_tasks_call_count

        # Inherit parent's dependencies so dynamic subtasks see the same
        # upstream context (e.g., product URL list from an earlier subtask).
        inherited_deps = (parent.depends_on if parent else []) + [self._current_subtask_id]

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

    async def replan_complete_and_handoff(self, summary: str, remaining_tasks: str) -> str:
        """Complete the current subtask and hand off remaining work.

        Use this when you have partially completed a large task and want to
        delegate the remaining work to follow-up subtasks. This is the
        primary tool for preventing task laziness.

        Args:
            summary: Summary of work completed in this subtask.
                This becomes the subtask's result for downstream tasks.
            remaining_tasks: JSON string of tasks for remaining work.
                Same format as replan_add_tasks.

        Returns:
            Instruction to stop working on the current subtask.
        """
        # Store summary as handoff result
        self._handoff_result = summary

        # Add remaining tasks
        result = await self.replan_add_tasks(remaining_tasks)

        if result.startswith("Error:"):
            self._handoff_result = None  # Rollback
            return result

        # Signal agent to stop after this tool-call round
        self._agent._should_stop_after_tool = True

        logger.info(
            f"[ReplanToolkit] Handoff from {self._current_subtask_id}: "
            f"summary={summary[:100]}..."
        )

        return (
            f"HANDOFF COMPLETE. Your partial result has been saved. {result}\n\n"
            f"STOP working on this task now. Do NOT continue processing more items. "
            f"The remaining work will be handled by the follow-up tasks."
        )

    def get_tools(self) -> List[FunctionTool]:
        """Return tools for this toolkit."""
        return [
            FunctionTool(self.replan_get_subtask_list),
            FunctionTool(self.replan_report_progress),
            FunctionTool(self.replan_add_tasks),
            FunctionTool(self.replan_complete_and_handoff),
        ]

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "Replan Toolkit"
