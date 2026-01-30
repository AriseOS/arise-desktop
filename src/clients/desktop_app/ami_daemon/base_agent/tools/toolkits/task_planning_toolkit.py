"""
TaskPlanningToolkit - LLM Tool Interface for TaskOrchestrator.

This toolkit provides LLM-callable tools for managing task execution:
- complete_subtask: Mark a subtask as done and proceed to next
- replan_task: Adjust the plan based on new information
- get_current_plan: Get the current plan summary

The toolkit delegates all state management to TaskOrchestrator,
which handles:
- Subtask state tracking
- Dependency management
- SSE event emission
- Failure handling and auto-replan

Based on Eigent's task planning patterns and CAMEL's TaskPlanningToolkit.

References:
- TaskOrchestrator: base_agent/core/task_orchestrator.py
- Design Doc: docs/task-planning-system.md
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .base_toolkit import BaseToolkit, FunctionTool
from ...events import listen_toolkit

if TYPE_CHECKING:
    from ...core.task_orchestrator import TaskOrchestrator

logger = logging.getLogger(__name__)


class TaskPlanningToolkit(BaseToolkit):
    """LLM tool interface for TaskOrchestrator.

    This toolkit exposes task planning capabilities as LLM-callable tools.
    It acts as a thin wrapper around TaskOrchestrator, which manages
    all the actual state and event emission.

    Tools:
    - complete_subtask: Mark current subtask as done
    - replan_task: Adjust plan based on new information
    - get_current_plan: View current plan and progress

    Usage:
        orchestrator = TaskOrchestrator(task_id="123", emitter=sse_emitter)
        toolkit = TaskPlanningToolkit(orchestrator=orchestrator)
        agent.add_toolkit(toolkit)
    """

    # Agent name for event tracking
    agent_name: str = "task_planner"

    def __init__(
        self,
        orchestrator: Optional["TaskOrchestrator"] = None,
        task_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        """Initialize the TaskPlanningToolkit.

        Args:
            orchestrator: The TaskOrchestrator to delegate to.
                If not provided, toolkit operates in standalone mode (legacy).
            task_id: Optional task ID (used if no orchestrator provided).
            timeout: Optional timeout for toolkit operations.
        """
        super().__init__(timeout=timeout)
        self._orchestrator = orchestrator
        self._task_id = task_id or (orchestrator.task_id if orchestrator else None)
        logger.info(f"TaskPlanningToolkit initialized with task_id={self._task_id}")

    def set_orchestrator(self, orchestrator: "TaskOrchestrator") -> None:
        """Set the TaskOrchestrator to delegate to.

        Args:
            orchestrator: The TaskOrchestrator instance.
        """
        self._orchestrator = orchestrator
        self._task_id = orchestrator.task_id
        logger.info(f"TaskPlanningToolkit linked to orchestrator {self._task_id}")

    @listen_toolkit(
        inputs=lambda self, subtask_id, result, **kw: f"Completing subtask {subtask_id}",
        return_msg=lambda r: r[:200] if r else "Subtask completed"
    )
    def complete_subtask(
        self,
        subtask_id: str,
        result: str,
    ) -> str:
        """Mark a subtask as completed and get the updated plan.

        Call this tool when you have finished executing the current subtask.
        The system will automatically determine the next subtask to execute.

        Args:
            subtask_id: The ID of the subtask to mark as completed (e.g., "1.1", "1.2").
            result: A summary of what was accomplished in this subtask.

        Returns:
            The updated plan summary showing progress and next task.

        Example:
            complete_subtask(
                subtask_id="1.1",
                result="Successfully visited website and found 25 products listed"
            )
        """
        if not self._orchestrator:
            return "Error: No TaskOrchestrator configured. Cannot track subtask state."

        # Mark the subtask as completed (validates state)
        error = self._orchestrator.mark_completed(subtask_id, result)
        if error:
            return error

        # Return updated plan summary
        return self._orchestrator.get_plan_summary()

    @listen_toolkit(
        inputs=lambda self, reason, **kw: f"Replanning: {reason[:50]}...",
        return_msg=lambda r: r[:200] if r else "Plan updated"
    )
    def replan_task(
        self,
        reason: str,
        new_subtasks: List[Dict[str, Any]],
        cancelled_subtask_ids: Optional[List[str]] = None,
    ) -> str:
        """Replan the current task based on new information.

        Call this tool when you discover that the current plan needs adjustment:
        - The website structure is different than expected
        - There are more/fewer items to process than anticipated
        - A better approach becomes apparent
        - The current subtask is no longer valid or needed

        Args:
            reason: Why the replan is needed (for logging and context).
            new_subtasks: List of new subtasks to add. Each subtask is a dict:
                {
                    "id": "1.3",  # Optional, will be auto-generated if not provided
                    "content": "Description of what to do",
                    "dependencies": ["1.1", "1.2"]  # Optional, list of subtask IDs
                }
            cancelled_subtask_ids: Optional list of subtask IDs to cancel.
                Cancelled subtasks are marked as DELETED, not FAILED.

        Returns:
            The updated plan summary showing the new plan.

        Example:
            replan_task(
                reason="Website has pagination, need to iterate through 10 pages",
                new_subtasks=[
                    {"id": "1.2.1", "content": "Extract products from page 1-5"},
                    {"id": "1.2.2", "content": "Extract products from page 6-10", "dependencies": ["1.2.1"]}
                ],
                cancelled_subtask_ids=["1.2"]
            )
        """
        if not self._orchestrator:
            return "Error: No TaskOrchestrator configured. Cannot replan."

        # Delegate replan to orchestrator
        return self._orchestrator.replan(
            reason=reason,
            new_subtasks=new_subtasks,
            cancelled_task_ids=cancelled_subtask_ids,
        )

    @listen_toolkit(
        inputs=lambda self, **kw: "Getting current task plan",
        return_msg=lambda r: f"Plan retrieved ({len(r)} chars)"
    )
    def get_current_plan(self) -> str:
        """Get the current task plan with progress status.

        Use this tool to review the current task plan and see:
        - Which subtasks are completed
        - Which subtask is currently being worked on
        - Which subtasks are remaining

        Returns:
            Formatted plan summary showing progress.

        Example output:
            ## Current Task Plan
            - [x] 1.1: Visit website and get product list ✓
            - [→] 1.2: Extract product details ← CURRENT
            - [ ] 1.3: Generate summary report

            **Current task (1.2)**: Extract product details
            Complete this task, then call `complete_subtask()` to proceed.
        """
        if not self._orchestrator:
            return "No task plan created yet."

        return self._orchestrator.get_plan_summary()

    @listen_toolkit(
        inputs=lambda self, subtask_id, error, **kw: f"Reporting failure for {subtask_id}",
        return_msg=lambda r: r[:100] if r else "Failure reported"
    )
    async def report_subtask_failure(
        self,
        subtask_id: str,
        error: str,
    ) -> str:
        """Report that a subtask has failed.

        Call this tool when you encounter an unrecoverable error while
        executing a subtask. The system will:
        - Mark the subtask as failed
        - Handle dependency failures (block dependent tasks)
        - Trigger automatic replan if configured

        Note: Unlike internal failures, agent-reported failures do NOT trigger
        automatic retry, since the agent has already determined the task cannot
        be completed.

        Args:
            subtask_id: The ID of the failed subtask.
            error: Description of what went wrong.

        Returns:
            Status message indicating next steps.
        """
        if not self._orchestrator:
            return "Error: No TaskOrchestrator configured."

        # Mark the subtask as failed
        self._orchestrator.mark_failed(subtask_id, error)

        # Get the subtask for further processing
        subtask = self._orchestrator.subtasks.get(subtask_id)
        if not subtask:
            return f"Error: Subtask {subtask_id} not found."

        # Handle dependency failures - notify blocked tasks
        blocked_tasks = self._orchestrator.handle_dependency_failure(subtask_id)
        blocked_msg = ""
        if blocked_tasks:
            blocked_msg = f" Blocked dependent tasks: {blocked_tasks}."
            logger.warning(f"Subtask {subtask_id} failure blocks {len(blocked_tasks)} tasks: {blocked_tasks}")

        # Trigger automatic replan if configured
        replan_msg = ""
        if self._orchestrator.config.failure_config.auto_replan_on_failure:
            logger.info(f"Triggering auto-replan for agent-reported failure: {subtask_id}")
            replan_success = await self._orchestrator.auto_replan_failed_subtask(subtask, error)
            if replan_success:
                replan_msg = " Plan has been automatically adjusted."
            else:
                replan_msg = " Auto-replan was attempted but did not succeed."

        # Build response message
        if self._orchestrator.all_done():
            return f"Subtask {subtask_id} failed.{blocked_msg}{replan_msg} No more subtasks to execute."
        else:
            return f"Subtask {subtask_id} failed.{blocked_msg}{replan_msg} Continuing with remaining subtasks.\n\n{self._orchestrator.get_plan_summary()}"

    @listen_toolkit(
        inputs=lambda self, subtask_id, reason, **kw: f"Abandoning subtask {subtask_id}",
        return_msg=lambda r: r[:100] if r else "Subtask abandoned"
    )
    def abandon_subtask(
        self,
        subtask_id: str,
        reason: str,
    ) -> str:
        """Abandon a subtask that cannot be completed.

        Call this tool when you determine that a specific subtask CANNOT be
        completed after trying multiple approaches. Unlike report_subtask_failure
        (which may trigger retries), abandon_subtask permanently marks the subtask
        as impossible and moves on.

        Use this when:
        - The subtask's goal is fundamentally impossible (e.g., "find X" but X doesn't exist)
        - You've tried multiple approaches and all failed
        - The required resource/element doesn't exist
        - Continuing to retry would be pointless

        The task will continue with other subtasks. Dependent subtasks will be
        skipped unless you replan them.

        Args:
            subtask_id: The ID of the subtask to abandon.
            reason: Clear explanation of why the subtask cannot be completed.

        Returns:
            Updated plan summary.

        Example:
            abandon_subtask(
                subtask_id="1.2",
                reason="Product page has no team tab - this information is not available"
            )
        """
        if not self._orchestrator:
            return "Error: No TaskOrchestrator configured."

        # Mark the subtask as failed with abandon reason
        self._orchestrator.mark_abandoned(subtask_id, reason)

        return f"Subtask {subtask_id} abandoned: {reason}\n\n{self._orchestrator.get_plan_summary()}"

    @listen_toolkit(
        inputs=lambda self, reason, **kw: f"Abandoning entire task: {reason[:50]}...",
        return_msg=lambda r: r[:100] if r else "Task abandoned"
    )
    def abandon_task(
        self,
        reason: str,
    ) -> str:
        """Abandon the entire task when it's impossible to complete.

        Call this tool ONLY when the entire task cannot be completed, not just
        a single subtask. For individual subtask issues, use abandon_subtask instead.

        Use this for situations like:
        - The target website/resource fundamentally doesn't exist
        - ALL critical subtasks have failed with no alternatives
        - The main task goal conflicts with reality
        - Required permissions cannot be obtained for the entire workflow

        IMPORTANT: Before abandoning the entire task, consider:
        1. Can you complete partial results with remaining subtasks?
        2. Is only one subtask impossible? Use abandon_subtask instead.
        3. Have you tried alternative approaches via replan_task?

        Args:
            reason: Clear explanation of why the entire task cannot be completed.
                   This will be shown to the user.

        Returns:
            Confirmation message.

        Example:
            abandon_task(
                reason="The target website (example.com) is completely down and "
                       "has been unreachable for the past 5 attempts. Cannot "
                       "complete any part of the task."
            )
        """
        if not self._orchestrator:
            return "Error: No TaskOrchestrator configured."

        # Call orchestrator's abandon method
        self._orchestrator.abandon(reason)

        return f"Task abandoned: {reason}\n\nAll remaining subtasks have been cancelled."

    def get_tools(self) -> List[FunctionTool]:
        """Return a list of FunctionTool objects for this toolkit.

        Returns:
            List of FunctionTool objects.
        """
        return [
            FunctionTool(self.complete_subtask),
            FunctionTool(self.replan_task),
            FunctionTool(self.get_current_plan),
            FunctionTool(self.report_subtask_failure),
            FunctionTool(self.abandon_subtask),
            FunctionTool(self.abandon_task),
        ]

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "Task Planning Toolkit"
