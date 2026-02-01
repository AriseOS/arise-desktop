"""
AMI Workforce - Task Coordinator based on CAMEL Workforce.

This class manages task decomposition, worker assignment, and execution
coordination. It extends CAMEL's Workforce with AMI-specific features:
- SSE event emission for real-time UI updates
- Task decomposition with user confirmation flow
- Integration with existing TaskState and event system
- Uses configured LLM (not environment variables)
- Coarse-grained task decomposition by agent type
- Memory integration for workflow guidance
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..tools.toolkits import MemoryToolkit, QueryResult

from camel.agents import ChatAgent
from camel.societies.workforce.workforce import (
    Workforce as BaseWorkforce,
    WorkforceState,
)
from camel.societies.workforce.utils import FailureHandlingConfig
from camel.societies.workforce.task_channel import TaskChannel
from camel.societies.workforce.base import BaseNode
from camel.tasks.task import Task, TaskState as CAMELTaskState, validate_task_content

from src.common.llm import parse_json_with_repair
from .agent_factories import create_model_backend
from ..events import (
    TaskDecomposedData,
    SubtaskStateData,
    StreamingDecomposeData,
    DecomposeProgressData,
    NoticeData,
    WorkerAssignedData,
    AssignTaskData,
    MemoryLevelData,
)
from ..events.toolkit_listen import _run_async_safely

logger = logging.getLogger(__name__)


# =============================================================================
# Data Structures for Coarse-Grained Decomposition
# =============================================================================

@dataclass
class CoarseSubtask:
    """
    Coarse-grained subtask - Workforce level task decomposition result.

    This represents a high-level subtask that is categorized by the type of
    agent needed to execute it (browser, document, code, etc.).

    The Memory query result is attached after coarse decomposition, allowing
    each subtask to have its own workflow guidance.
    """
    id: str
    content: str  # Task description
    agent_type: str  # "browser" | "document" | "code"
    depends_on: List[str] = field(default_factory=list)  # Dependent subtask IDs

    # Memory query result (populated by query_memory_for_coarse_subtasks)
    memory_result: Optional["QueryResult"] = None
    memory_level: str = "L3"  # L1/L2/L3
    workflow_guide: Optional[str] = None  # Formatted guidance content


# =============================================================================
# Prompts for Task Decomposition
# =============================================================================


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

# Coarse-grained decomposition prompt - splits by agent type
COARSE_DECOMPOSE_PROMPT = """Split the task by work type. Keep related operations of the same type together.

Types:
- browser: Web browsing, research, online operations
- document: Writing reports, creating files
- code: Programming, terminal commands

Output JSON:
{{
    "subtasks": [
        {{"id": "1", "type": "browser", "content": "...", "depends_on": []}},
        {{"id": "2", "type": "document", "content": "...", "depends_on": ["1"]}}
    ]
}}

Task: {task}"""


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
        memory_toolkit: Optional["MemoryToolkit"] = None,  # Memory toolkit for workflow queries
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
            memory_toolkit: MemoryToolkit for querying historical workflows
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

        # Memory integration for workflow guidance
        self._memory_toolkit = memory_toolkit
        self._workflow_guide_content: Optional[str] = None
        self._memory_level: str = "L3"  # L1=strong, L2=medium, L3=weak guidance

        # Subtask Memory mapping (from L3 subtasks query result)
        self._global_path_states: List[Any] = []  # L2 global path states
        self._global_path_actions: List[Any] = []  # L2 global path actions
        self._subtask_target_states: Dict[str, Any] = {}  # subtask_id -> target State
        self._subtask_memory_hints: Dict[str, str] = {}  # subtask_id -> workflow_guide

        # Coarse-grained decomposition (by agent type)
        self._coarse_subtasks: List[CoarseSubtask] = []  # Coarse subtasks with Memory results

        # Track subtasks and their states
        self._subtasks: List[Task] = []
        self._subtask_states: Dict[str, str] = {}  # subtask_id -> state

        # Progress tracking
        self._completed_count = 0
        self._failed_count = 0

        # Pause/resume mechanism (Eigent pattern for multi-turn conversation)
        # BUG-6 fix: Use Lock to make pause/resume atomic
        self._paused = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Initially not paused (event is set)
        self._pause_lock = asyncio.Lock()  # BUG-6 fix: Protect state changes

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
        3. Emits progress events during decomposition
        4. Returns list of CAMEL Task objects

        Args:
            task: Task description to decompose
            on_stream_text: Optional callback for streaming text chunks

        Returns:
            List of decomposed Task objects
        """
        logger.info(f"[AMIWorkforce] Decomposing task: {task[:100]}...")

        # Emit initial progress event
        await self._emit_event(DecomposeProgressData(
            task_id=self.task_id,
            progress=0.0,
            message="Starting task decomposition...",
            is_final=False,
        ))

        # Create the main task
        # Use "task" as prefix instead of task_id for cleaner subtask IDs
        # This generates subtask IDs like "task.1", "task.2" instead of "abc123.main.1"
        main_task = Task(content=task, id="task")

        if not validate_task_content(main_task.content, main_task.id):
            logger.warning(f"[AMIWorkforce] Invalid task content")
            raise ValueError("Invalid or empty task content")

        # Reset workforce state for new decomposition
        self.reset()
        self._task = main_task
        self.set_channel(TaskChannel())
        self._state = WorkforceState.RUNNING
        main_task.state = CAMELTaskState.OPEN

        # Emit progress: analyzing task
        await self._emit_event(DecomposeProgressData(
            task_id=self.task_id,
            progress=0.2,
            message="Analyzing task complexity...",
            is_final=False,
        ))

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

            # Emit progress: generating subtasks (50-80% based on text length)
            progress = min(0.8, 0.5 + len(accumulated_text) / 2000 * 0.3)
            await self._emit_event(DecomposeProgressData(
                task_id=self.task_id,
                progress=progress,
                message="Generating subtasks...",
                is_final=False,
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
        # DS-5: Use 'state' field for consistency with SubtaskStateData
        subtasks_data = [
            {
                "id": st.id,
                "content": st.content,
                "state": "OPEN",
                "status": "OPEN",  # Keep for backward compatibility
            }
            for st in subtasks
        ]
        await self._emit_event(TaskDecomposedData(
            task_id=self.task_id,
            subtasks=subtasks_data,
            summary_task=task,
            total_subtasks=len(subtasks),
        ))

        # Emit final progress event
        await self._emit_event(DecomposeProgressData(
            task_id=self.task_id,
            progress=1.0,
            message="Decomposition complete",
            sub_tasks=subtasks_data,
            is_final=True,
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

        # Create a sync wrapper for the async stream callback
        # The lambda creates a task that is tracked via _run_async_safely
        def sync_stream_callback(text):
            _run_async_safely(stream_callback(text))

        # Call decompose with streaming callback
        result = task.decompose(
            self.task_agent,
            decompose_prompt,
            stream_callback=sync_stream_callback,
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
        Override to emit assign_task events when tasks are assigned.

        Emits two types of events:
        1. assign_task with state="waiting" - Task assigned, in queue
        2. worker_assigned - Legacy event for backwards compatibility

        Args:
            tasks: List of tasks to assign

        Returns:
            TaskAssignResult from parent class
        """
        from camel.societies.workforce.utils import TaskAssignResult

        assigned = await super()._find_assignee(tasks)

        # Log assignment summary for debugging
        logger.info(f"[AMIWorkforce] Coordinator assigned {len(assigned.assignments)} tasks:")
        for item in assigned.assignments:
            task_obj = self._find_task_by_id(item.task_id, tasks)
            content_preview = (task_obj.content[:50] + "...") if task_obj and len(task_obj.content) > 50 else (task_obj.content if task_obj else "N/A")
            worker_name = self._get_worker_name(item.assignee_id)
            logger.info(f"  - {item.task_id} -> {worker_name}: {content_preview}")

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

            # Get agent_type for frontend display
            agent_type = self._get_agent_type_for_task(task_obj) if task_obj else None

            # Emit assign_task event with "waiting" state (Phase 1)
            await self._emit_event(AssignTaskData(
                task_id=self.task_id,
                assignee_id=item.assignee_id,
                subtask_id=item.task_id,
                content=content,
                state="waiting",
                failure_count=0,
                worker_name=worker_name,
                agent_type=agent_type,
                # DS-2: Backward compatible fields
                agent_id=item.assignee_id,
            ))

            # DS-3: WorkerAssignedData is legacy, keeping for backward compatibility
            # TODO: Remove once frontend fully migrates to assign_task
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
        Override to emit assign_task event with RUNNING state when task starts.

        This is Phase 2 of the two-phase assignment:
        - Phase 1 (in _find_assignee): state="waiting"
        - Phase 2 (here): state="running"

        Note: Memory/workflow_guide is passed via task.additional_info,
        which CAMEL's PROCESS_TASK_PROMPT automatically includes in the prompt.

        Args:
            task: Task being posted
            assignee_id: ID of assigned worker
        """
        # BUG-7 fix: Check if paused before executing task
        # This is the primary checkpoint for pause/resume during multi-turn conversation
        await self._wait_if_paused()

        # Check if stopped (using getattr for safety since _stopped may come from parent class)
        if getattr(self, '_stopped', False):
            logger.info(f"[AMIWorkforce] Skipping task {task.id}: workforce stopped")
            return

        # Skip the main task itself
        if not (self._task and task.id == self._task.id):
            worker_name = self._get_worker_name(assignee_id)
            agent_type = self._get_agent_type_for_task(task)

            # Emit assign_task event with "running" state (Phase 2)
            await self._emit_event(AssignTaskData(
                task_id=self.task_id,
                assignee_id=assignee_id,
                subtask_id=task.id,
                content=task.content,
                state="running",
                failure_count=task.failure_count,
                worker_name=worker_name,
                agent_type=agent_type,
                # DS-2: Backward compatible fields
                agent_id=assignee_id,
            ))

            # DS-3: WorkerAssignedData is legacy, keeping for backward compatibility
            # TODO: Remove once frontend fully migrates to assign_task
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

        # BUG-7 fix: Check again before calling parent (in case pause happened during event emission)
        await self._wait_if_paused()

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

    def _get_agent_type_for_task(self, task: Task) -> Optional[str]:
        """
        Get the agent type for a task.

        Looks up agent_type from:
        1. CoarseSubtask (if task ID matches coarse.X pattern)
        2. Task's additional_info field

        Args:
            task: The task to look up.

        Returns:
            Agent type string ("browser", "document", "code") or None.
        """
        # Try to find from CoarseSubtask by task ID
        if task.id.startswith("coarse."):
            coarse_id = task.id.replace("coarse.", "")
            coarse_subtask = self.get_coarse_subtask(coarse_id)
            if coarse_subtask:
                return coarse_subtask.agent_type

        # Try to find from CoarseSubtask by content match
        for cs in self._coarse_subtasks:
            if cs.content == task.content:
                return cs.agent_type

        # Try to get from task's additional_info
        if hasattr(task, 'additional_info') and task.additional_info:
            return task.additional_info.get('agent_type')

        return None

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
        # DS-5: Use 'state' field for consistency with SubtaskStateData
        subtasks_data = [
            {
                "id": st.id,
                "content": st.content,
                "state": self._subtask_states.get(st.id, "OPEN"),
                "status": self._subtask_states.get(st.id, "OPEN"),  # Backward compatibility
            }
            for st in self._subtasks
        ]
        await self._emit_event(TaskDecomposedData(
            task_id=self.task_id,
            subtasks=subtasks_data,
            summary_task=self._task.content if self._task else "",
            total_subtasks=len(self._subtasks),
        ))

    def _sync_subtask_to_parent(self, task: Task) -> None:
        """
        Sync completed subtask's result and state back to its parent.subtasks list.

        CAMEL stores results in _completed_tasks but doesn't update parent.subtasks,
        causing parent.subtasks[i].result to remain None. This ensures consistency.

        Based on Eigent's _sync_subtask_to_parent pattern.

        Args:
            task: The completed subtask whose result/state should be synced
        """
        parent = task.parent
        if not parent or not parent.subtasks:
            return

        for sub in parent.subtasks:
            if sub.id == task.id:
                sub.result = task.result
                sub.state = task.state
                logger.debug(f"[AMIWorkforce] Synced subtask {task.id} result to parent.subtasks")
                return

        logger.warning(f"[AMIWorkforce] Subtask {task.id} not found in parent.subtasks")

    async def _handle_completed_task(self, task: Task) -> None:
        """
        Override to emit subtask_state events on completion.

        Args:
            task: Completed task
        """
        logger.info(f"[AMIWorkforce] Task completed: {task.id}")

        # BUG-7 fix: Check if paused before handling completion
        await self._wait_if_paused()

        # Sync result to parent's subtasks list first (Eigent pattern)
        self._sync_subtask_to_parent(task)

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

        Enhanced failure handling:
        - Only notify user on final failure (after all retries exhausted)
        - Retry silently to avoid UI noise
        - Include error message in final failure notification

        Args:
            task: Failed task

        Returns:
            True if task was handled (retry/replan), False otherwise
        """
        # BUG-7 fix: Check if paused before handling failure
        await self._wait_if_paused()

        # Call parent implementation first for retry/replan logic
        # Note: parent increments task.failure_count before returning
        result = await super()._handle_failed_task(task)

        # Get max retries from config
        max_retries = self.failure_handling_config.max_retries

        logger.info(f"[AMIWorkforce] Task failed: {task.id}, attempt {task.failure_count}/{max_retries}")

        # Only send failure notification when all retries are exhausted
        if task.failure_count < max_retries:
            # Silent retry - just log it
            logger.info(f"[AMIWorkforce] Retrying task {task.id} silently")
            return result

        # Final failure - update state and notify user
        logger.warning(f"[AMIWorkforce] Task {task.id} failed after {task.failure_count} attempts, max retries exhausted")

        # Update state tracking
        self._subtask_states[task.id] = "FAILED"
        self._failed_count += 1

        # Extract error message from task result
        error_message = self._extract_error_message(task)

        # Emit subtask_state event with failure details
        await self._emit_event(SubtaskStateData(
            task_id=self.task_id,
            subtask_id=task.id,
            state="FAILED",
            result=error_message[:500] if error_message else None,
            failure_count=task.failure_count,
        ))

        return result

    def _extract_error_message(self, task: Task) -> str:
        """
        Extract error message from a failed task.

        Args:
            task: Failed task

        Returns:
            Error message string
        """
        if task.result:
            return str(task.result)

        # Try to get from task's additional_info or other attributes
        if hasattr(task, 'additional_info') and task.additional_info:
            return str(task.additional_info)

        return "Task failed after maximum retries"

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
        """Override stop to emit notice event and cleanup workers."""
        logger.info(f"[AMIWorkforce] Stopping workforce")

        # BUG-14 fix: Cleanup worker resources before stopping
        self._cleanup_workers()

        super().stop()

        # Emit notice safely (handles both sync and async contexts)
        _run_async_safely(self._emit_event(NoticeData(
            task_id=self.task_id,
            level="info",
            title="Workforce Stopped",
            message="Task execution has been stopped",
        )))

    def _cleanup_workers(self) -> None:
        """
        BUG-14 fix: Cleanup worker resources.

        Called when workforce is stopped to release resources held by workers.
        """
        try:
            # Get all worker nodes
            if hasattr(self, '_children') and self._children:
                for worker_node in self._children:
                    if hasattr(worker_node, 'worker'):
                        worker = worker_node.worker
                        # Reset agent state if possible
                        if hasattr(worker, 'reset'):
                            try:
                                worker.reset()
                                logger.debug(f"[AMIWorkforce] Reset worker: {getattr(worker, 'agent_name', 'unknown')}")
                            except Exception as e:
                                logger.warning(f"[AMIWorkforce] Failed to reset worker: {e}")

            logger.info(f"[AMIWorkforce] Worker cleanup completed")
        except Exception as e:
            logger.warning(f"[AMIWorkforce] Error during worker cleanup: {e}")

    # ===== Pause/Resume Mechanism (Eigent pattern for multi-turn conversation) =====

    def pause(self) -> None:
        """
        Pause Workforce execution.

        Used when user sends a new message during task execution.
        The Workforce will pause at the next safe checkpoint.

        BUG-6 fix: Made thread-safe with simple flag setting.
        The asyncio.Event provides the actual synchronization.
        """
        # Simple atomic flag check - Event provides synchronization
        if not self._paused:
            self._paused = True
            self._pause_event.clear()  # Block _wait_if_paused
            logger.info(f"[AMIWorkforce] Pausing workforce for task {self.task_id}")

            # Emit notice event safely (handles both sync and async contexts)
            _run_async_safely(self._emit_event(NoticeData(
                task_id=self.task_id,
                level="info",
                title="Workforce Paused",
                message="Task execution paused for user input",
            )))

    def resume(self) -> None:
        """
        Resume Workforce execution.

        Called after handling user's message during execution.

        BUG-6 fix: Made thread-safe with simple flag setting.
        """
        if self._paused:
            self._paused = False
            self._pause_event.set()  # Unblock _wait_if_paused
            logger.info(f"[AMIWorkforce] Resuming workforce for task {self.task_id}")

            # Emit notice event safely (handles both sync and async contexts)
            _run_async_safely(self._emit_event(NoticeData(
                task_id=self.task_id,
                level="info",
                title="Workforce Resumed",
                message="Task execution resumed",
            )))

    @property
    def is_paused(self) -> bool:
        """Check if Workforce is paused."""
        return self._paused

    async def _wait_if_paused(self) -> None:
        """
        Wait if Workforce is paused.

        Called at safe checkpoints during execution to allow pause/resume.
        """
        if self._paused:
            logger.info(f"[AMIWorkforce] Waiting for resume signal...")
            await self._pause_event.wait()
            logger.info(f"[AMIWorkforce] Resume signal received, continuing...")

    async def add_dynamic_subtasks(self, new_tasks: List[Task]) -> None:
        """
        Add new subtasks during execution (Eigent pattern).

        Used when user adds additional requirements during execution.
        The new tasks will be added to the pending queue.

        Args:
            new_tasks: List of new tasks to add
        """
        logger.info(f"[AMIWorkforce] Adding {len(new_tasks)} dynamic subtasks")

        # Add to pending queue
        self._pending_tasks.extend(new_tasks)

        # Track states
        for task in new_tasks:
            self._subtask_states[task.id] = "OPEN"
            self._subtasks.append(task)

        # Emit event for UI update
        from ..events import DynamicTasksAddedData

        await self._emit_event(DynamicTasksAddedData(
            task_id=self.task_id,
            # DS-5: Use 'state' field for consistency
            new_tasks=[
                {"id": t.id, "content": t.content, "state": "OPEN", "status": "OPEN"}
                for t in new_tasks
            ],
            reason="User added additional requirements",
            total_tasks_now=len(self._subtasks),
            total_tasks=len(self._subtasks),  # DS-6: Both fields for compatibility
        ))

    # ===== Memory Integration Methods =====

    async def query_memory_for_task(self, task: str) -> None:
        """
        Query memory for similar past workflows before task decomposition.

        This method queries the Memory system (L1/L2/L3 hierarchy) for historical
        workflows that match the given task. The result is stored in:
        - self._workflow_guide_content: Formatted guidance text
        - self._memory_level: L1 (cognitive_phrase), L2 (path), or L3 (none)

        Memory Levels:
        - L1: Complete cognitive_phrase match (strict guidance)
        - L2: Partial path match (reference guidance)
        - L3: No match (use judgment)

        Args:
            task: Task description to search for in memory.
        """
        if not self._memory_toolkit:
            logger.info("[AMIWorkforce] Memory toolkit not configured, skipping query")
            return

        # Check if memory toolkit is available
        if hasattr(self._memory_toolkit, 'is_available') and not self._memory_toolkit.is_available():
            logger.info("[AMIWorkforce] Memory service not available, skipping query")
            return

        logger.info(f"[AMIWorkforce] Querying memory for task: {task[:100]}...")

        # Emit memory query start event
        await self._emit_event(NoticeData(
            task_id=self.task_id,
            level="info",
            title="Memory Query",
            message="Searching for similar past workflows...",
        ))

        try:
            memory_result = await self._memory_toolkit.query_task(task)

            if memory_result.cognitive_phrase:
                # L1: Complete workflow match - strong guidance
                from ..tools.toolkits import MemoryToolkit
                self._workflow_guide_content = MemoryToolkit.format_cognitive_phrase(
                    memory_result.cognitive_phrase
                )
                self._memory_level = "L1"
                states_count = len(memory_result.cognitive_phrase.states) if hasattr(memory_result.cognitive_phrase, 'states') else 0
                logger.info(
                    f"[AMIWorkforce] Found cognitive_phrase (L1) with {states_count} states"
                )
                await self._emit_event(NoticeData(
                    task_id=self.task_id,
                    level="success",
                    title="Memory Match Found",
                    message=f"Found complete workflow with {states_count} steps (L1 - High confidence)",
                ))

            elif memory_result.subtasks:
                # L3a: Subtasks with global path - build subtask memory mapping
                from ..tools.toolkits import MemoryToolkit

                # Store global path for navigation reference
                self._global_path_states = memory_result.states or []
                self._global_path_actions = memory_result.actions or []

                # Build subtask to target state mapping
                for st in memory_result.subtasks:
                    subtask_id = getattr(st, 'task_id', None) or str(id(st))
                    path_indices = getattr(st, 'path_state_indices', [])

                    if path_indices and self._global_path_states:
                        # Map subtask to its target state (last state in path_indices)
                        last_idx = path_indices[-1]
                        if last_idx < len(self._global_path_states):
                            self._subtask_target_states[subtask_id] = self._global_path_states[last_idx]

                # Format global path as workflow guide
                if self._global_path_states:
                    self._workflow_guide_content = MemoryToolkit.format_navigation_path(
                        self._global_path_states, self._global_path_actions
                    )
                    self._memory_level = "L2"
                    logger.info(
                        f"[AMIWorkforce] Found subtasks with global path (L2) - "
                        f"{len(memory_result.subtasks)} subtasks, {len(self._global_path_states)} states"
                    )
                    await self._emit_event(NoticeData(
                        task_id=self.task_id,
                        level="info",
                        title="Subtask Plan Found",
                        message=f"Found {len(memory_result.subtasks)} subtasks with navigation path (L2)",
                    ))
                else:
                    # Subtasks without path (L3b)
                    self._memory_level = "L3"
                    logger.info(
                        f"[AMIWorkforce] Found subtasks without path (L3) - "
                        f"{len(memory_result.subtasks)} subtasks"
                    )

            elif memory_result.states:
                # L2: Partial path match - reference guidance
                from ..tools.toolkits import MemoryToolkit

                # Store global path
                self._global_path_states = memory_result.states
                self._global_path_actions = memory_result.actions or []

                self._workflow_guide_content = MemoryToolkit.format_navigation_path(
                    memory_result.states, memory_result.actions
                )
                self._memory_level = "L2"
                logger.info(
                    f"[AMIWorkforce] Found navigation path (L2) with {len(memory_result.states)} states"
                )
                await self._emit_event(NoticeData(
                    task_id=self.task_id,
                    level="info",
                    title="Partial Match Found",
                    message=f"Found navigation path with {len(memory_result.states)} pages (L2 - Medium confidence)",
                ))

            else:
                # L3: No match - use judgment
                self._memory_level = "L3"
                logger.info("[AMIWorkforce] No workflow found in memory (L3)")
                await self._emit_event(NoticeData(
                    task_id=self.task_id,
                    level="info",
                    title="No Memory Match",
                    message="No similar workflow found. Agent will explore freely (L3)",
                ))

        except Exception as e:
            logger.warning(f"[AMIWorkforce] Memory query failed: {e}")
            self._memory_level = "L3"
            await self._emit_event(NoticeData(
                task_id=self.task_id,
                level="warning",
                title="Memory Query Failed",
                message=f"Could not query memory: {str(e)[:100]}",
            ))

    def propagate_workflow_guide_to_workers(self) -> None:
        """
        Propagate workflow guide content to all workers' agents.

        This method iterates over all child workers and sets the workflow_guide
        on their underlying ListenChatAgent instances. The guide will be
        injected into every LLM call made by the agent.

        The memory_level is also propagated to adjust guidance strength:
        - L1: Strict following instructions
        - L2: Reference suggestions
        - L3: No specific guidance
        """
        if not self._workflow_guide_content:
            logger.debug("[AMIWorkforce] No workflow guide to propagate")
            return

        propagated_count = 0
        for child in self._children:
            # AMISingleAgentWorker.worker is ListenChatAgent
            if hasattr(child, 'worker') and hasattr(child.worker, 'set_workflow_guide'):
                child.worker.set_workflow_guide(
                    self._workflow_guide_content,
                    memory_level=self._memory_level
                )
                propagated_count += 1
                worker_desc = getattr(child, 'description', 'Unknown')[:50]
                logger.info(
                    f"[AMIWorkforce] Propagated workflow guide (level={self._memory_level}) "
                    f"to {worker_desc}"
                )

                # CRITICAL: Reinitialize agent pool so cloned agents get the workflow guide
                # AgentPool clones agents at init time, before workflow guide is set.
                # We need to reset the pool so new clones will have the guide.
                has_pool = hasattr(child, 'agent_pool')
                pool_value = getattr(child, 'agent_pool', None) if has_pool else None
                logger.debug(f"[AMIWorkforce] Child {worker_desc}: has_pool={has_pool}, pool={pool_value}")
                if has_pool and pool_value is not None:
                    from camel.societies.workforce.single_agent_worker import AgentPool
                    child.agent_pool = AgentPool(base_agent=child.worker)
                    logger.info(f"[AMIWorkforce] Reinitialized agent pool for {worker_desc}")

        if propagated_count > 0:
            logger.info(
                f"[AMIWorkforce] Workflow guide propagated to {propagated_count} workers"
            )
        else:
            logger.warning("[AMIWorkforce] No workers found to propagate workflow guide")

    @property
    def memory_level(self) -> str:
        """Get the current memory level (L1/L2/L3)."""
        return self._memory_level

    @property
    def has_workflow_guide(self) -> bool:
        """Check if a workflow guide is available."""
        return self._workflow_guide_content is not None

    @property
    def global_path_states(self) -> List[Any]:
        """Get the global path states from L2 query."""
        return self._global_path_states

    @property
    def global_path_actions(self) -> List[Any]:
        """Get the global path actions from L2 query."""
        return self._global_path_actions

    def get_subtask_target_state(self, subtask_id: str) -> Optional[Any]:
        """Get the target state for a specific subtask.

        Args:
            subtask_id: The subtask ID to look up.

        Returns:
            The target State object if mapped, None otherwise.
        """
        return self._subtask_target_states.get(subtask_id)

    async def query_memory_for_subtask(
        self,
        subtask_id: str,
        subtask_content: str,
    ) -> Optional[str]:
        """Query Memory for a specific subtask and cache the result.

        This method queries Memory for a single subtask, useful for getting
        more specific guidance when the global path doesn't cover this subtask.

        Args:
            subtask_id: The subtask identifier.
            subtask_content: The subtask description/content.

        Returns:
            Formatted workflow guide for this subtask, or None if not found.
        """
        if not self._memory_toolkit:
            return None

        # Check if already cached
        if subtask_id in self._subtask_memory_hints:
            return self._subtask_memory_hints[subtask_id]

        try:
            result = await self._memory_toolkit.query_task(subtask_content)

            if result.states:
                from ..tools.toolkits import MemoryToolkit
                guide = MemoryToolkit.format_navigation_path(
                    result.states, result.actions or []
                )
                self._subtask_memory_hints[subtask_id] = guide
                logger.info(
                    f"[AMIWorkforce] Found memory for subtask {subtask_id[:20]}: "
                    f"{len(result.states)} states"
                )
                return guide

        except Exception as e:
            logger.warning(
                f"[AMIWorkforce] Memory query for subtask {subtask_id[:20]} failed: {e}"
            )

        return None

    def get_subtask_memory_hint(self, subtask_id: str) -> Optional[str]:
        """Get cached memory hint for a subtask.

        Args:
            subtask_id: The subtask identifier.

        Returns:
            Cached workflow guide for this subtask, or None if not cached.
        """
        return self._subtask_memory_hints.get(subtask_id)

    # =========================================================================
    # Coarse-Grained Decomposition Methods
    # =========================================================================

    async def coarse_decompose_task(self, task: str) -> List[CoarseSubtask]:
        """
        Coarse-grained task decomposition - split task by agent type.

        This method analyzes the task and splits it into coarse-grained subtasks
        based on the TYPE of work required (browser, document, code).

        This is Phase 1 of the two-phase decomposition:
        - Phase 1 (here): Split by agent type, get Memory for each
        - Phase 2 (in Worker): Fine-grained decomposition within each agent

        The key insight is that Memory queries work better on semantically
        complete subtasks rather than fragmented steps. By keeping all browser
        operations together, we can match complete workflows from Memory.

        Args:
            task: The original task description from user.

        Returns:
            List of CoarseSubtask objects, each tagged with agent_type.

        Raises:
            ValueError: If LLM response cannot be parsed.
        """
        logger.info(f"[AMIWorkforce] Coarse decomposing task: {task[:100]}...")

        # Emit progress event
        await self._emit_event(DecomposeProgressData(
            task_id=self.task_id,
            progress=0.1,
            message="Analyzing task types...",
            is_final=False,
        ))

        # Build the prompt
        prompt = COARSE_DECOMPOSE_PROMPT.format(task=task)

        # Call LLM for coarse decomposition
        self.task_agent.reset()
        response = self.task_agent.step(prompt)

        if not response or not response.msg:
            raise ValueError("Coarse decomposition returned empty response")

        response_text = response.msg.content
        logger.debug(f"[AMIWorkforce] Coarse decompose raw response: {response_text[:500]}...")

        # Parse the JSON response
        coarse_subtasks = self._parse_coarse_subtasks(response_text)

        # Store in instance
        self._coarse_subtasks = coarse_subtasks

        # Log summary
        type_counts = {}
        for st in coarse_subtasks:
            type_counts[st.agent_type] = type_counts.get(st.agent_type, 0) + 1
        logger.info(
            f"[AMIWorkforce] Coarse decomposition complete: {len(coarse_subtasks)} subtasks "
            f"(types: {type_counts})"
        )

        # Emit progress event
        await self._emit_event(DecomposeProgressData(
            task_id=self.task_id,
            progress=0.3,
            message=f"Identified {len(coarse_subtasks)} coarse subtasks",
            is_final=False,
        ))

        return coarse_subtasks

    def _parse_coarse_subtasks(self, response_text: str) -> List[CoarseSubtask]:
        """
        Parse LLM response into CoarseSubtask objects.

        Uses common/llm parse_json_with_repair for robust JSON parsing.

        Args:
            response_text: Raw LLM response text.

        Returns:
            List of parsed CoarseSubtask objects.

        Raises:
            ValueError: If response cannot be parsed or is missing required fields.
        """
        # Use common JSON parsing with repair
        data = parse_json_with_repair(response_text)

        # Check for fallback (parsing failed completely)
        if "answer" in data and "subtasks" not in data:
            logger.error(f"[AMIWorkforce] JSON parsing failed, got fallback: {response_text[:500]}")
            raise ValueError("Invalid JSON in coarse decomposition response")

        # Validate structure
        if "subtasks" not in data:
            raise ValueError("Coarse decomposition response missing 'subtasks' field")

        subtasks = []
        for item in data["subtasks"]:
            # Validate required fields
            if "id" not in item or "type" not in item or "content" not in item:
                logger.warning(f"[AMIWorkforce] Skipping invalid subtask: {item}")
                continue

            # Validate agent type
            agent_type = item["type"].lower()
            if agent_type not in ("browser", "document", "code"):
                logger.warning(
                    f"[AMIWorkforce] Unknown agent type '{agent_type}', defaulting to 'browser'"
                )
                agent_type = "browser"

            subtask = CoarseSubtask(
                id=str(item["id"]),
                content=item["content"],
                agent_type=agent_type,
                depends_on=item.get("depends_on", []),
            )
            subtasks.append(subtask)

        if not subtasks:
            raise ValueError("Coarse decomposition produced no valid subtasks")

        return subtasks

    async def query_memory_for_coarse_subtasks(self) -> None:
        """
        Query Memory for each coarse-grained subtask.

        This method iterates over all coarse subtasks and queries Memory
        for each one. The results are stored in the CoarseSubtask objects:
        - memory_result: The raw QueryResult from Memory API
        - memory_level: L1/L2/L3 based on match quality
        - workflow_guide: Formatted guidance text for injection

        This is the key integration point between coarse decomposition and
        Memory. Each subtask gets its own Memory context, which will be
        passed to the Worker when the task is assigned.
        """
        if not self._memory_toolkit:
            logger.info("[AMIWorkforce] Memory toolkit not configured, skipping coarse subtask queries")
            return

        if not self._memory_toolkit.is_available():
            logger.info("[AMIWorkforce] Memory service not available, skipping coarse subtask queries")
            return

        if not self._coarse_subtasks:
            logger.warning("[AMIWorkforce] No coarse subtasks to query Memory for")
            return

        logger.info(
            f"[AMIWorkforce] Querying Memory for {len(self._coarse_subtasks)} coarse subtasks..."
        )

        # Emit progress event
        await self._emit_event(DecomposeProgressData(
            task_id=self.task_id,
            progress=0.4,
            message="Querying Memory for each subtask...",
            is_final=False,
        ))

        for i, subtask in enumerate(self._coarse_subtasks):
            try:
                logger.info(
                    f"[AMIWorkforce] Querying Memory for subtask {subtask.id}: "
                    f"{subtask.content[:50]}..."
                )

                result = await self._memory_toolkit.query_task(subtask.content)
                subtask.memory_result = result

                # Determine memory level and format guide
                if result.cognitive_phrase:
                    # L1: Complete workflow match
                    subtask.memory_level = "L1"
                    from ..tools.toolkits import MemoryToolkit
                    subtask.workflow_guide = MemoryToolkit.format_cognitive_phrase(
                        result.cognitive_phrase
                    )
                    states_count = len(result.cognitive_phrase.states) if hasattr(result.cognitive_phrase, 'states') else 0
                    logger.info(
                        f"[AMIWorkforce] Subtask {subtask.id}: L1 match with "
                        f"{states_count} states"
                    )

                elif result.states:
                    # L2: Partial path match
                    subtask.memory_level = "L2"
                    from ..tools.toolkits import MemoryToolkit
                    subtask.workflow_guide = MemoryToolkit.format_navigation_path(
                        result.states, result.actions or []
                    )
                    logger.info(
                        f"[AMIWorkforce] Subtask {subtask.id}: L2 match with "
                        f"{len(result.states)} states"
                    )

                else:
                    # L3: No match
                    subtask.memory_level = "L3"
                    logger.info(f"[AMIWorkforce] Subtask {subtask.id}: L3 (no match)")

                # Emit memory level event for this subtask
                await self._emit_event(MemoryLevelData(
                    task_id=self.task_id,
                    level=subtask.memory_level,
                    reason=f"Memory query for subtask {subtask.id}",
                    states_count=len(result.states) if result.states else 0,
                    method="coarse_subtask_query",
                ))

            except Exception as e:
                logger.warning(
                    f"[AMIWorkforce] Memory query failed for subtask {subtask.id}: {e}"
                )
                subtask.memory_level = "L3"

            # Update progress
            progress = 0.4 + (0.3 * (i + 1) / len(self._coarse_subtasks))
            await self._emit_event(DecomposeProgressData(
                task_id=self.task_id,
                progress=progress,
                message=f"Memory query {i + 1}/{len(self._coarse_subtasks)} complete",
                is_final=False,
            ))

        # Log summary
        level_counts = {"L1": 0, "L2": 0, "L3": 0}
        for st in self._coarse_subtasks:
            level_counts[st.memory_level] = level_counts.get(st.memory_level, 0) + 1
        logger.info(
            f"[AMIWorkforce] Memory queries complete: L1={level_counts['L1']}, "
            f"L2={level_counts['L2']}, L3={level_counts['L3']}"
        )

    def get_coarse_subtask(self, subtask_id: str) -> Optional[CoarseSubtask]:
        """
        Get a coarse subtask by ID.

        Args:
            subtask_id: The subtask ID to look up.

        Returns:
            The CoarseSubtask if found, None otherwise.
        """
        for st in self._coarse_subtasks:
            if st.id == subtask_id:
                return st
        return None

    def get_coarse_subtasks_by_type(self, agent_type: str) -> List[CoarseSubtask]:
        """
        Get all coarse subtasks of a specific agent type.

        Args:
            agent_type: The agent type to filter by ("browser", "document", "code").

        Returns:
            List of matching CoarseSubtask objects.
        """
        return [st for st in self._coarse_subtasks if st.agent_type == agent_type]

    @property
    def coarse_subtasks(self) -> List[CoarseSubtask]:
        """Get all coarse subtasks."""
        return self._coarse_subtasks

    def coarse_subtasks_to_tasks(self) -> List[Task]:
        """
        Convert coarse subtasks to CAMEL Task objects for execution.

        This method converts the CoarseSubtask objects (with their Memory
        context) into CAMEL Task objects that can be assigned to Workers.

        The Memory context (workflow_guide, memory_level) is stored in the
        Task's additional_info field. CAMEL's PROCESS_TASK_PROMPT will
        automatically include this in the prompt sent to the Worker agent.

        Returns:
            List of CAMEL Task objects ready for execution.
        """
        tasks = []
        for coarse_st in self._coarse_subtasks:
            # Build additional_info with workflow guide
            additional_info = {
                "agent_type": coarse_st.agent_type,
                "memory_level": coarse_st.memory_level,
                "depends_on": coarse_st.depends_on,
            }

            # Include workflow guide directly in additional_info
            # CAMEL's PROCESS_TASK_PROMPT will include this in the prompt
            if coarse_st.workflow_guide:
                additional_info["workflow_guide"] = coarse_st.workflow_guide

            # Create CAMEL Task
            task = Task(
                content=coarse_st.content,
                id=f"coarse.{coarse_st.id}",
                additional_info=additional_info,
            )
            tasks.append(task)

            # Track state
            self._subtask_states[task.id] = "OPEN"

        # Update subtasks list
        self._subtasks.extend(tasks)

        return tasks
