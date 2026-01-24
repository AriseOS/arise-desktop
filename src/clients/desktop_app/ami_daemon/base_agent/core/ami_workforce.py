"""
AMI Workforce - Task Coordinator based on CAMEL Workforce.

This class manages task decomposition, worker assignment, and execution
coordination. It extends CAMEL's Workforce with AMI-specific features:
- SSE event emission for real-time UI updates
- Task decomposition with user confirmation flow
- Integration with existing TaskState and event system
- Uses configured LLM (not environment variables)
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from camel.agents import ChatAgent
from camel.societies.workforce.workforce import (
    Workforce as BaseWorkforce,
    WorkforceState,
)
from camel.societies.workforce.utils import FailureHandlingConfig
from camel.societies.workforce.task_channel import TaskChannel
from camel.societies.workforce.base import BaseNode
from camel.tasks.task import Task, TaskState as CAMELTaskState, validate_task_content

from .agent_factories import create_model_backend
from ..events import (
    TaskDecomposedData,
    SubtaskStateData,
    StreamingDecomposeData,
    NoticeData,
    WorkerAssignedData,
)

logger = logging.getLogger(__name__)


# System prompts for coordinator and task agents
COORDINATOR_SYSTEM_PROMPT = """You are a task coordinator responsible for:
1. Assigning tasks to appropriate workers based on their capabilities
2. Monitoring task progress and handling failures
3. Coordinating between multiple workers when needed

Available workers will be provided to you. Match tasks to workers based on their descriptions.
Be concise and efficient in your responses."""

TASK_DECOMPOSITION_SYSTEM_PROMPT = """You are a task decomposition expert responsible for:
1. Breaking down complex tasks into smaller, actionable subtasks
2. Identifying dependencies between subtasks
3. Ensuring each subtask is clear and achievable

Guidelines:
- Create 2-5 subtasks for most tasks
- Each subtask should be specific and actionable
- Consider the logical order of execution
- Keep subtasks focused on a single objective"""


class AMIWorkforce(BaseWorkforce):
    """
    AMI's Workforce implementation based on CAMEL.

    Manages task decomposition, worker assignment, and execution coordination.
    Extends CAMEL's Workforce with:
    - SSE event emission via TaskState
    - Streaming task decomposition
    - User confirmation flow (30s auto-confirm)
    - Dynamic subtask addition

    Architecture:
    ```
    AMIWorkforce
    ├── task_agent: LLM for task decomposition
    ├── pending_tasks: CAMEL TaskChannel
    ├── workers:
    │   └── BrowserWorker → AMISingleAgentWorker → BrowserAgentAdapter
    └── failure_handling: retry + replan (CAMEL built-in)
    ```
    """

    def __init__(
        self,
        task_id: str,
        task_state: Any,  # TaskState from quick_task_service
        llm_api_key: str,  # Required: API key for LLM calls
        llm_model: str,  # Required: Model name for LLM
        llm_base_url: Optional[str] = None,
        description: str = "AMI Task Coordinator",
        children: Optional[List[BaseNode]] = None,
        coordinator_agent: Optional[ChatAgent] = None,
        task_agent: Optional[ChatAgent] = None,
        graceful_shutdown_timeout: float = 3,
    ) -> None:
        """
        Initialize AMIWorkforce.

        Args:
            task_id: Unique task identifier for SSE events
            task_state: TaskState instance with put_event() method
            llm_api_key: API key for LLM calls (required)
            llm_model: Model name for LLM (required)
            llm_base_url: Base URL for LLM API (optional, for proxy)
            description: Workforce description
            children: Initial worker nodes
            coordinator_agent: Custom coordinator agent (created if None)
            task_agent: Custom task decomposition agent (created if None)
            graceful_shutdown_timeout: Timeout for graceful shutdown
        """
        logger.info(f"[AMIWorkforce] Initializing for task_id={task_id}")

        # Validate required parameters
        if not llm_api_key:
            raise ValueError("llm_api_key is required for AMIWorkforce")
        if not llm_model:
            raise ValueError("llm_model is required for AMIWorkforce")

        # Store LLM config
        self._llm_api_key = llm_api_key
        self._llm_model = llm_model
        self._llm_base_url = llm_base_url

        # Create model backend using shared factory (not environment variables)
        model_backend = create_model_backend(
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
        )

        # Create coordinator agent if not provided
        if coordinator_agent is None:
            logger.info(f"[AMIWorkforce] Creating coordinator_agent with model={llm_model}")
            coordinator_agent = ChatAgent(
                system_message=COORDINATOR_SYSTEM_PROMPT,
                model=model_backend,
            )

        # Create task decomposition agent if not provided
        if task_agent is None:
            logger.info(f"[AMIWorkforce] Creating task_agent with model={llm_model}")
            task_agent = ChatAgent(
                system_message=TASK_DECOMPOSITION_SYSTEM_PROMPT,
                model=model_backend,
            )

        super().__init__(
            description=description,
            children=children,
            coordinator_agent=coordinator_agent,
            task_agent=task_agent,
            graceful_shutdown_timeout=graceful_shutdown_timeout,
            failure_handling_config=FailureHandlingConfig(
                enabled_strategies=["retry", "replan"],
                max_retries=3,
            ),
        )

        self.task_id = task_id
        self._task_state = task_state

        # Track subtasks and their states
        self._subtasks: List[Task] = []
        self._subtask_states: Dict[str, str] = {}  # subtask_id -> state

        # Progress tracking
        self._completed_count = 0
        self._failed_count = 0

        logger.info(f"[AMIWorkforce] Initialization complete")

    async def _emit_event(self, event: Any) -> None:
        """
        Emit an event to the task's event queue.

        Args:
            event: ActionData instance to emit
        """
        if self._task_state and hasattr(self._task_state, 'put_event'):
            await self._task_state.put_event(event)

    async def decompose_task(
        self,
        task: str,
        on_stream_text: Optional[Callable[[str], None]] = None,
    ) -> List[Task]:
        """
        Decompose a task into subtasks with streaming output.

        This method:
        1. Calls the task_agent to decompose the task
        2. Streams decomposition text to frontend via SSE
        3. Returns list of CAMEL Task objects

        Args:
            task: Task description to decompose
            on_stream_text: Optional callback for streaming text chunks

        Returns:
            List of decomposed Task objects
        """
        logger.info(f"[AMIWorkforce] Decomposing task: {task[:100]}...")

        # Create the main task
        main_task = Task(content=task, id=f"{self.task_id}.main")

        if not validate_task_content(main_task.content, main_task.id):
            logger.warning(f"[AMIWorkforce] Invalid task content")
            raise ValueError("Invalid or empty task content")

        # Reset workforce state for new decomposition
        self.reset()
        self._task = main_task
        self.set_channel(TaskChannel())
        self._state = WorkforceState.RUNNING
        main_task.state = CAMELTaskState.OPEN

        # Perform decomposition with streaming
        accumulated_text = ""

        async def stream_callback(text: str):
            nonlocal accumulated_text
            accumulated_text = text

            # Emit streaming_decompose event
            await self._emit_event(StreamingDecomposeData(
                task_id=self.task_id,
                text=accumulated_text,
            ))

            # Call external callback if provided
            if on_stream_text:
                on_stream_text(text)

        # Use parent class decomposition with our callback
        subtasks = await self._decompose_with_streaming(main_task, stream_callback)

        # Store subtasks
        self._subtasks = subtasks
        for subtask in subtasks:
            self._subtask_states[subtask.id] = "OPEN"

        logger.info(f"[AMIWorkforce] Decomposed into {len(subtasks)} subtasks")

        # Emit task_decomposed event
        subtasks_data = [
            {
                "id": st.id,
                "content": st.content,
                "status": "OPEN",
            }
            for st in subtasks
        ]
        await self._emit_event(TaskDecomposedData(
            task_id=self.task_id,
            subtasks=subtasks_data,
            summary_task=task,
            total_subtasks=len(subtasks),
        ))

        return subtasks

    async def _decompose_with_streaming(
        self,
        task: Task,
        stream_callback: Callable[[str], Any],
    ) -> List[Task]:
        """
        Internal method to decompose task with streaming.

        Uses CAMEL's task decomposition with streaming support.

        Args:
            task: Task to decompose
            stream_callback: Callback for streaming text

        Returns:
            List of subtasks

        Raises:
            RuntimeError: If task_agent is not available
        """
        if not hasattr(self, 'task_agent') or not self.task_agent:
            raise RuntimeError("task_agent is required for task decomposition")

        self.task_agent.stream_accumulate = True

        # Get child nodes info for decomposition prompt
        child_nodes_info = self._get_child_nodes_info() if hasattr(self, '_get_child_nodes_info') else ""

        # Build decomposition prompt
        from camel.societies.workforce.prompts import TASK_DECOMPOSE_PROMPT
        decompose_prompt = str(
            TASK_DECOMPOSE_PROMPT.format(
                content=task.content,
                child_nodes_info=child_nodes_info,
                additional_info=task.additional_info or "",
            )
        )

        self.task_agent.reset()

        # Call decompose with streaming callback
        result = task.decompose(
            self.task_agent,
            decompose_prompt,
            stream_callback=lambda text: asyncio.create_task(stream_callback(text)),
        )

        # Handle generator or direct result
        if hasattr(result, '__iter__') and not isinstance(result, list):
            subtasks = []
            for new_tasks in result:
                subtasks.extend(new_tasks)
            return subtasks
        else:
            if not result:
                raise RuntimeError("Task decomposition returned empty result")
            return result

    async def start_with_subtasks(self, subtasks: List[Task]) -> None:
        """
        Start executing with confirmed subtasks.

        This is called after user confirms the task plan.
        Forces execution of all subtasks until completion.

        Args:
            subtasks: Confirmed list of subtasks to execute
        """
        logger.info(f"[AMIWorkforce] Starting execution with {len(subtasks)} subtasks")

        self._subtasks = subtasks
        self._pending_tasks.extendleft(reversed(subtasks))

        # Save initial snapshot
        self.save_snapshot("Initial task decomposition")

        try:
            # Start the workforce execution
            await self.start()
            logger.info(f"[AMIWorkforce] Execution completed")
        except Exception as e:
            logger.error(f"[AMIWorkforce] Execution error: {e}", exc_info=True)
            self._state = WorkforceState.STOPPED
            raise
        finally:
            if self._state != WorkforceState.STOPPED:
                self._state = WorkforceState.IDLE

    async def _find_assignee(self, tasks: List[Task]):
        """
        Override to emit worker_assigned events when tasks are assigned.

        Args:
            tasks: List of tasks to assign

        Returns:
            TaskAssignResult from parent class
        """
        from camel.societies.workforce.utils import TaskAssignResult

        assigned = await super()._find_assignee(tasks)

        for item in assigned.assignments:
            # Skip the main task itself
            if self._task and item.task_id == self._task.id:
                continue

            # Find task content
            task_obj = self._find_task_by_id(item.task_id, tasks)
            content = task_obj.content if task_obj else ""

            # Skip if already assigned (retry scenario)
            if task_obj and getattr(task_obj, 'assigned_worker_id', None):
                logger.debug(f"[AMIWorkforce] Skip notification for task {item.task_id}: already assigned")
                continue

            # Get worker name from node_id
            worker_name = self._get_worker_name(item.assignee_id)

            # Emit worker_assigned event
            await self._emit_event(WorkerAssignedData(
                task_id=self.task_id,
                worker_name=worker_name,
                worker_id=item.assignee_id,
                subtask_id=item.task_id,
                subtask_content=content,
            ))

            # Update subtask state
            self._subtask_states[item.task_id] = "ASSIGNED"

        return assigned

    async def _post_task(self, task: Task, assignee_id: str) -> None:
        """
        Override to emit worker_assigned event with RUNNING state when task starts.

        Args:
            task: Task being posted
            assignee_id: ID of assigned worker
        """
        # Skip the main task itself
        if not (self._task and task.id == self._task.id):
            worker_name = self._get_worker_name(assignee_id)

            # Emit worker_assigned with running state
            await self._emit_event(WorkerAssignedData(
                task_id=self.task_id,
                worker_name=worker_name,
                worker_id=assignee_id,
                subtask_id=task.id,
                subtask_content=task.content,
            ))

            # Update subtask state to RUNNING
            self._subtask_states[task.id] = "RUNNING"
            await self._emit_event(SubtaskStateData(
                task_id=self.task_id,
                subtask_id=task.id,
                state="RUNNING",
            ))

        # Call parent implementation
        await super()._post_task(task, assignee_id)

    def _find_task_by_id(self, task_id: str, tasks: List[Task]) -> Optional[Task]:
        """Find a task by ID in the task tree."""
        for task in tasks:
            if task.id == task_id:
                return task
            if hasattr(task, 'subtasks') and task.subtasks:
                found = self._find_task_by_id(task_id, task.subtasks)
                if found:
                    return found
        return None

    def _get_worker_name(self, node_id: str) -> str:
        """Get worker name from node ID."""
        for child in self._children:
            if hasattr(child, 'node_id') and child.node_id == node_id:
                if hasattr(child, 'worker') and hasattr(child.worker, 'agent_name'):
                    return child.worker.agent_name
                return getattr(child, 'description', node_id)
        return node_id

    async def add_subtasks(self, new_tasks: List[Task]) -> None:
        """
        Dynamically add new subtasks during execution.

        Used when a worker discovers additional work (e.g., found 50 products
        that need individual processing).

        Args:
            new_tasks: New tasks to add to the pending queue
        """
        logger.info(f"[AMIWorkforce] Adding {len(new_tasks)} new subtasks dynamically")

        # Add to pending queue
        self._pending_tasks.extend(new_tasks)

        # Track states
        for task in new_tasks:
            self._subtask_states[task.id] = "OPEN"
            self._subtasks.append(task)

        # Emit event for UI update
        subtasks_data = [
            {
                "id": st.id,
                "content": st.content,
                "status": self._subtask_states.get(st.id, "OPEN"),
            }
            for st in self._subtasks
        ]
        await self._emit_event(TaskDecomposedData(
            task_id=self.task_id,
            subtasks=subtasks_data,
            summary_task=self._task.content if self._task else "",
            total_subtasks=len(self._subtasks),
        ))

    async def _handle_completed_task(self, task: Task) -> None:
        """
        Override to emit subtask_state events on completion.

        Args:
            task: Completed task
        """
        logger.info(f"[AMIWorkforce] Task completed: {task.id}")

        # Update state tracking
        self._subtask_states[task.id] = "DONE"
        self._completed_count += 1

        # Emit subtask_state event
        await self._emit_event(SubtaskStateData(
            task_id=self.task_id,
            subtask_id=task.id,
            state="DONE",
            result=str(task.result)[:500] if task.result else None,
            failure_count=task.failure_count,
        ))

        # Call parent implementation
        await super()._handle_completed_task(task)

    async def _handle_failed_task(self, task: Task) -> bool:
        """
        Override to emit subtask_state events on failure.

        Args:
            task: Failed task

        Returns:
            True if task was handled (retry/replan), False otherwise
        """
        logger.info(f"[AMIWorkforce] Task failed: {task.id}, retry={task.failure_count}")

        # Update state tracking
        self._subtask_states[task.id] = "FAILED"
        self._failed_count += 1

        # Emit subtask_state event
        await self._emit_event(SubtaskStateData(
            task_id=self.task_id,
            subtask_id=task.id,
            state="FAILED",
            result=str(task.result)[:500] if task.result else None,
            failure_count=task.failure_count,
        ))

        # Call parent implementation for retry/replan logic
        return await super()._handle_failed_task(task)

    def get_progress(self) -> Dict[str, Any]:
        """
        Get current execution progress.

        Returns:
            Dict with progress information
        """
        total = len(self._subtasks)
        pending = len(self._pending_tasks)
        running = total - pending - self._completed_count - self._failed_count

        return {
            "total": total,
            "pending": pending,
            "running": max(0, running),
            "completed": self._completed_count,
            "failed": self._failed_count,
            "progress_percent": (self._completed_count / total * 100) if total > 0 else 0,
        }

    def stop(self) -> None:
        """Override stop to emit notice event."""
        logger.info(f"[AMIWorkforce] Stopping workforce")
        super().stop()

        # Emit notice asynchronously
        asyncio.create_task(self._emit_event(NoticeData(
            task_id=self.task_id,
            level="info",
            title="Workforce Stopped",
            message="Task execution has been stopped",
        )))
