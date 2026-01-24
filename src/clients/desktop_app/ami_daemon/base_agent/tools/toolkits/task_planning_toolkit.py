"""
TaskPlanningToolkit - Task decomposition and re-planning for agents.

Ported from CAMEL-AI/Eigent project.
Provides tools for decomposing complex tasks into subtasks and re-planning
when the original plan is insufficient.

This toolkit enables agents to dynamically manage their own task execution,
similar to Eigent's TaskPlanningToolkit.

When used with an agent that has set_task_state(), this toolkit will
emit SSE events for frontend display:
- task_decomposed: When a task is broken into subtasks
- subtask_state: When a subtask's state changes
- task_replanned: When a task is re-planned with new subtasks

References:
- CAMEL: camel/toolkits/task_planning_toolkit.py
- Eigent: third-party/eigent/backend/app/utils/workforce.py
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from .base_toolkit import BaseToolkit, FunctionTool
from ...events import listen_toolkit

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    """State of a task in the planning system.

    Aligned with CAMEL's TaskState enum.
    """
    OPEN = "OPEN"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    DELETED = "DELETED"


@dataclass
class Task:
    """Represents a task that can be decomposed and tracked.

    Simplified port of CAMEL's Task class, focused on the essentials
    needed for task planning within a single agent.

    Attributes:
        content: The task description/content.
        id: Unique identifier for the task.
        state: Current state of the task.
        parent: Parent task (if this is a subtask).
        subtasks: List of child subtasks.
        result: The result/output of the task.
        failure_count: Number of times this task has failed.
        additional_info: Extra metadata for the task.
    """
    content: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: TaskState = TaskState.OPEN
    parent: Optional["Task"] = None
    subtasks: List["Task"] = field(default_factory=list)
    result: Optional[str] = None
    failure_count: int = 0
    additional_info: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    def __repr__(self) -> str:
        """Return a string representation of the task."""
        content_preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"Task(id='{self.id}', content='{content_preview}', state='{self.state.value}')"

    def set_state(self, state: TaskState) -> None:
        """Set the state of the task.

        If setting to DONE, also propagates to subtasks.
        If setting to RUNNING, propagates up to parent.

        Args:
            state: The new state for the task.
        """
        self.state = state
        if state == TaskState.DONE:
            self.completed_at = datetime.now()
            for subtask in self.subtasks:
                if subtask.state != TaskState.DELETED:
                    subtask.set_state(state)
        elif state == TaskState.RUNNING and self.parent:
            self.parent.set_state(state)

    def update_result(self, result: str) -> None:
        """Set task result and mark as DONE.

        Args:
            result: The task result.
        """
        self.result = result
        self.set_state(TaskState.DONE)

    def add_subtask(self, task: "Task") -> None:
        """Add a subtask to this task.

        Args:
            task: The subtask to add.
        """
        task.parent = self
        self.subtasks.append(task)

    def remove_subtask(self, task_id: str) -> None:
        """Remove a subtask by ID.

        Args:
            task_id: The ID of the subtask to remove.
        """
        self.subtasks = [t for t in self.subtasks if t.id != task_id]

    def get_running_task(self) -> Optional["Task"]:
        """Get the currently running task (deepest level).

        Returns:
            The running task or None.
        """
        for sub in self.subtasks:
            if sub.state == TaskState.RUNNING:
                return sub.get_running_task()
        if self.state == TaskState.RUNNING:
            return self
        return None

    def to_string(self, indent: str = "", include_state: bool = False) -> str:
        """Convert task tree to a string representation.

        Args:
            indent: Indentation prefix for hierarchical display.
            include_state: Whether to include task state.

        Returns:
            String representation of the task tree.
        """
        if include_state:
            result = f"{indent}[{self.state.value}] Task {self.id}: {self.content}\n"
        else:
            result = f"{indent}Task {self.id}: {self.content}\n"
        for subtask in self.subtasks:
            result += subtask.to_string(indent + "  ", include_state)
        return result

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary.

        Returns:
            Dictionary representation of the task.
        """
        return {
            "id": self.id,
            "content": self.content,
            "state": self.state.value,
            "result": self.result,
            "failure_count": self.failure_count,
            "subtasks": [st.to_dict() for st in self.subtasks],
            "additional_info": self.additional_info,
        }


class TaskPlanningToolkit(BaseToolkit):
    """A toolkit for task decomposition and re-planning.

    Enables agents to break down complex tasks into subtasks and
    re-plan when the original decomposition is insufficient.

    This is a direct port of CAMEL's TaskPlanningToolkit, adapted
    for AMI's architecture.

    Features:
    - decompose_task: Break a task into subtasks
    - replan_tasks: Re-decompose when original plan fails
    - get_current_plan: View current task tree
    - update_task_state: Update task progress

    Uses @listen_toolkit for automatic event emission.
    """

    # Agent name for event tracking
    agent_name: str = "task_planner"

    def __init__(
        self,
        task_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        """Initialize the TaskPlanningToolkit.

        Args:
            task_id: Optional root task ID for the session.
            timeout: Optional timeout for toolkit operations.
        """
        super().__init__(timeout=timeout)
        self.task_id = task_id or str(uuid.uuid4())
        self._tasks: Dict[str, Task] = {}
        self._root_task: Optional[Task] = None
        logger.info(f"TaskPlanningToolkit initialized with task_id={self.task_id}")

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an SSE event if task_state is available.

        Args:
            event_type: The event type (e.g., 'task_decomposed')
            data: Event data dictionary
        """
        if self._task_state and hasattr(self._task_state, 'put_event'):
            try:
                # Build the event dict with event type and data
                # TaskState.put_event expects a single dict with 'event' key
                event_dict = {"event": event_type, **data}

                # put_event may be sync or async
                result = self._task_state.put_event(event_dict)
                if asyncio.iscoroutine(result):
                    # Schedule async call if we're in an event loop
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(result)
                    except RuntimeError:
                        # No running loop, run synchronously
                        asyncio.run(result)
                logger.info(f"Emitted event: {event_type} with data keys: {list(data.keys())}")
            except Exception as e:
                logger.warning(f"Failed to emit {event_type} event: {e}")

    def _register_task(self, task: Task) -> None:
        """Register a task in the internal registry.

        Args:
            task: The task to register.
        """
        self._tasks[task.id] = task

    def _get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID.

        Args:
            task_id: The task ID.

        Returns:
            The task or None if not found.
        """
        return self._tasks.get(task_id)

    @listen_toolkit(
        inputs=lambda self, original_task_content, sub_task_contents, **kw:
            f"Decomposing task into {len(sub_task_contents)} subtasks",
        return_msg=lambda r: f"Created {len(r)} subtasks"
    )
    def decompose_task(
        self,
        original_task_content: str,
        sub_task_contents: List[str],
        original_task_id: Optional[str] = None,
    ) -> List[Task]:
        """Decompose an original task into several sub-tasks.

        Use this tool when a task is complex and needs to be broken down
        into smaller, manageable pieces. Each subtask should be specific
        and actionable.

        Args:
            original_task_content: The content of the task to be decomposed.
            sub_task_contents: A list of strings, where each string is the
                content for a new sub-task.
            original_task_id: The ID of the task to be decomposed. If not
                provided, a new ID will be generated.

        Returns:
            List of newly created sub-task objects.

        Example:
            decompose_task(
                original_task_content="Research and summarize AI trends",
                sub_task_contents=[
                    "Search for recent AI news articles",
                    "Extract key trends from articles",
                    "Write a summary document"
                ]
            )
        """
        # Create or get the original task
        task_id = original_task_id or f"{self.task_id}.main"

        if task_id in self._tasks:
            original_task = self._tasks[task_id]
            # Clear existing subtasks for re-decomposition
            original_task.subtasks = []
        else:
            original_task = Task(
                content=original_task_content,
                id=task_id,
            )
            self._register_task(original_task)
            if self._root_task is None:
                self._root_task = original_task

        # Create subtasks
        new_tasks: List[Task] = []
        for i, content in enumerate(sub_task_contents):
            new_task = Task(
                content=content,
                id=f"{original_task.id}.{i + 1}",
                parent=original_task,
            )
            new_tasks.append(new_task)
            original_task.subtasks.append(new_task)
            self._register_task(new_task)

        logger.info(
            f"Decomposed task '{original_task.content[:50]}...' (id={original_task.id}) "
            f"into {len(new_tasks)} sub-tasks: {[t.id for t in new_tasks]}"
        )

        # Emit task_decomposed event for frontend
        self._emit_event("task_decomposed", {
            "subtasks": [t.to_dict() for t in new_tasks],
            "summary_task": original_task_content,
            "original_task_id": original_task.id,
            "total_subtasks": len(new_tasks),
        })

        return new_tasks

    @listen_toolkit(
        inputs=lambda self, original_task_content, sub_task_contents, **kw:
            f"Re-planning task into {len(sub_task_contents)} new subtasks",
        return_msg=lambda r: f"Re-planned into {len(r)} subtasks"
    )
    def replan_tasks(
        self,
        original_task_content: str,
        sub_task_contents: List[str],
        original_task_id: Optional[str] = None,
    ) -> List[Task]:
        """Re-decompose a task into new sub-tasks.

        Use this tool when the original task decomposition is not working
        well and a new plan is needed. This will replace the existing
        subtasks with the new ones.

        Args:
            original_task_content: The content of the task to be re-planned.
            sub_task_contents: A list of strings for the new sub-tasks.
            original_task_id: The ID of the task to be re-planned.

        Returns:
            List of newly created sub-task objects.

        Example:
            replan_tasks(
                original_task_content="Research AI trends",
                sub_task_contents=[
                    "Focus on generative AI specifically",
                    "Look at industry applications",
                    "Summarize findings"
                ],
                original_task_id="task.main"
            )
        """
        task_id = original_task_id or f"{self.task_id}.main"

        # Get existing task or create new one
        if task_id in self._tasks:
            original_task = self._tasks[task_id]
            # Mark old subtasks as deleted
            for subtask in original_task.subtasks:
                subtask.set_state(TaskState.DELETED)
            original_task.subtasks = []
            # Update content if different
            if original_task.content != original_task_content:
                original_task.content = original_task_content
        else:
            original_task = Task(
                content=original_task_content,
                id=task_id,
            )
            self._register_task(original_task)

        # Create new subtasks
        new_tasks: List[Task] = []
        for i, content in enumerate(sub_task_contents):
            new_task = Task(
                content=content,
                id=f"{original_task.id}.r{i + 1}",  # 'r' prefix indicates replan
                parent=original_task,
            )
            new_tasks.append(new_task)
            original_task.subtasks.append(new_task)
            self._register_task(new_task)

        logger.info(
            f"Re-planned task '{original_task.content[:50]}...' (id={original_task.id}) "
            f"into {len(new_tasks)} new sub-tasks: {[t.id for t in new_tasks]}"
        )

        # Emit task_replanned event for frontend
        self._emit_event("task_replanned", {
            "subtasks": [t.to_dict() for t in new_tasks],
            "original_task_id": original_task.id,
            "reason": "Re-planned by agent",
        })

        return new_tasks

    @listen_toolkit(
        inputs=lambda self, **kw: "Getting current task plan",
        return_msg=lambda r: f"Plan retrieved ({len(r)} chars)"
    )
    def get_current_plan(self, include_state: bool = True) -> str:
        """Get the current task plan as a formatted string.

        Use this tool to review the current task decomposition and
        progress. Helpful for tracking what has been done and what
        remains.

        Args:
            include_state: Whether to include task states in output.

        Returns:
            Formatted string showing the task tree with states.

        Example output:
            [RUNNING] Task main: Research AI trends
              [DONE] Task main.1: Search for articles
              [RUNNING] Task main.2: Extract key points
              [OPEN] Task main.3: Write summary
        """
        if not self._root_task:
            return "No task plan created yet. Use decompose_task to create one."

        return self._root_task.to_string(include_state=include_state)

    @listen_toolkit(
        inputs=lambda self, task_id, state, **kw: f"Updating task {task_id} to {state}",
        return_msg=lambda r: r
    )
    def update_task_state(
        self,
        task_id: str,
        state: str,
        result: Optional[str] = None,
    ) -> str:
        """Update the state of a task.

        Use this tool to mark tasks as in-progress, completed, or failed.
        This helps track overall progress through the task plan.

        Args:
            task_id: The ID of the task to update.
            state: The new state. One of: OPEN, RUNNING, DONE, FAILED, DELETED.
            result: Optional result message (typically for DONE state).

        Returns:
            Confirmation message.

        Example:
            update_task_state(
                task_id="task.main.1",
                state="DONE",
                result="Found 5 relevant articles"
            )
        """
        task = self._get_task(task_id)
        if not task:
            return f"Error: Task '{task_id}' not found."

        try:
            new_state = TaskState(state.upper())
        except ValueError:
            valid_states = [s.value for s in TaskState]
            return f"Error: Invalid state '{state}'. Valid states: {valid_states}"

        task.set_state(new_state)

        if result and new_state == TaskState.DONE:
            task.result = result

        logger.info(f"Updated task {task_id} to state {new_state.value}")

        # Emit subtask_state event for frontend
        self._emit_event("subtask_state", {
            "subtask_id": task_id,
            "state": new_state.value,
            "result": result,
            "failure_count": task.failure_count,
        })

        return f"Task '{task_id}' updated to {new_state.value}"

    @listen_toolkit(
        inputs=lambda self, **kw: "Getting task progress summary",
        return_msg=lambda r: r[:100] + "..." if len(r) > 100 else r
    )
    def get_progress_summary(self) -> str:
        """Get a summary of task progress.

        Use this tool to get a quick overview of how many tasks are
        complete, in progress, and remaining.

        Returns:
            Summary string with task counts by state.

        Example output:
            Task Progress Summary:
            - Total tasks: 4
            - Completed (DONE): 2
            - In Progress (RUNNING): 1
            - Pending (OPEN): 1
            - Failed: 0
        """
        if not self._tasks:
            return "No tasks created yet."

        counts = {state: 0 for state in TaskState}
        for task in self._tasks.values():
            counts[task.state] += 1

        total = len(self._tasks)
        summary = f"""Task Progress Summary:
- Total tasks: {total}
- Completed (DONE): {counts[TaskState.DONE]}
- In Progress (RUNNING): {counts[TaskState.RUNNING]}
- Pending (OPEN): {counts[TaskState.OPEN]}
- Failed: {counts[TaskState.FAILED]}
- Deleted: {counts[TaskState.DELETED]}"""

        return summary

    def get_tools(self) -> List[FunctionTool]:
        """Return a list of FunctionTool objects for this toolkit.

        Returns:
            List of FunctionTool objects.
        """
        return [
            FunctionTool(self.decompose_task),
            FunctionTool(self.replan_tasks),
            FunctionTool(self.get_current_plan),
            FunctionTool(self.update_task_state),
            FunctionTool(self.get_progress_summary),
        ]

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "Task Planning Toolkit"
