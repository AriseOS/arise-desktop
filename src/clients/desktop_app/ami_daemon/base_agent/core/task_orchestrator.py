"""
Task Orchestrator for Multi-Agent Coordination

Orchestrates complex tasks by:
1. Decomposing tasks into subtasks
2. Assigning subtasks to appropriate specialized agents
3. Managing dependencies between subtasks
4. Tracking progress and aggregating results

Based on Eigent's Workforce pattern from CAMEL framework.

References:
- Eigent: third-party/eigent/backend/app/utils/workforce.py
- CAMEL Workforce: https://github.com/camel-ai/camel
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union

from pydantic import BaseModel, Field

from ..events import (
    Action,
    TaskStateData,
    TaskCompletedData,
    TaskFailedData,
    StepStartedData,
    StepCompletedData,
    StepFailedData,
    ActivateAgentData,
    DeactivateAgentData,
    SSEEmitter,
)
from .schemas import AgentContext, AgentOutput
from .agent_registry import AgentType, AgentRegistry, get_registry
from .task_router import TaskRouter, RoutingResult
from .budget_controller import BudgetController, BudgetConfig, BudgetExceededException
from .token_usage import TokenUsage, SessionTokenUsage

logger = logging.getLogger(__name__)


class SubTaskState(str, Enum):
    """State of a subtask in the orchestration."""
    PENDING = "pending"
    BLOCKED = "blocked"  # Waiting for dependencies
    READY = "ready"  # Dependencies resolved, ready to run
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OrchestratorState(str, Enum):
    """State of the orchestrator."""
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubTask:
    """Represents a subtask in the orchestration.

    Subtasks are created by decomposing the main task and are
    assigned to specialized agents for execution.
    """
    id: str
    content: str
    description: str = ""
    state: SubTaskState = SubTaskState.PENDING
    assigned_agent: Optional[str] = None  # AgentType value
    dependencies: List[str] = field(default_factory=list)  # List of subtask IDs
    priority: int = 0  # Higher = more important
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 2

    def is_ready(self, completed_tasks: Set[str]) -> bool:
        """Check if all dependencies are satisfied."""
        return all(dep in completed_tasks for dep in self.dependencies)

    @property
    def duration_seconds(self) -> Optional[float]:
        """Get execution duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class OrchestratorResult(BaseModel):
    """Result of orchestrator execution."""
    success: bool
    task_id: str
    subtasks_completed: int = 0
    subtasks_failed: int = 0
    subtasks_total: int = 0
    final_result: Any = None
    error: Optional[str] = None
    duration_seconds: float = 0.0
    token_usage: Optional[Dict[str, int]] = None
    agent_usage: Dict[str, int] = Field(default_factory=dict)  # agent_type -> call count


class OrchestratorConfig(BaseModel):
    """Configuration for TaskOrchestrator."""
    max_concurrent_tasks: int = 3
    max_subtasks: int = 20
    task_timeout_seconds: int = 300  # Per subtask timeout
    total_timeout_seconds: int = 1800  # Total orchestration timeout
    enable_parallel_execution: bool = True
    auto_retry_failed: bool = True
    max_retries_per_subtask: int = 2
    budget_config: Optional[BudgetConfig] = None


# System prompt for task decomposition
TASK_DECOMPOSITION_PROMPT = """You are a Task Decomposition Agent. Your job is to break down complex tasks into smaller, actionable subtasks.

Analyze the given task and create a list of subtasks that can be assigned to specialized agents:

Available Agent Types:
- browser_agent: Web browsing, research, data collection, form filling
- developer_agent: Writing code, debugging, git operations, file editing
- document_agent: Creating documents, Google Drive, Notion operations
- social_medium_agent: Email (Gmail), calendar, social media
- question_confirm_agent: Asking user questions, confirmations

Rules:
1. Each subtask should be specific and actionable
2. Identify dependencies between subtasks (which must complete before others)
3. Assign the most appropriate agent type to each subtask
4. Keep subtasks focused - one agent type per subtask
5. Order subtasks logically based on dependencies

Output format (JSON):
{
    "subtasks": [
        {
            "id": "task_1",
            "content": "Search for information about X",
            "description": "Detailed description of what to search for",
            "agent_type": "browser_agent",
            "dependencies": [],
            "priority": 1
        },
        {
            "id": "task_2",
            "content": "Write a summary document",
            "description": "Create a document summarizing the findings",
            "agent_type": "document_agent",
            "dependencies": ["task_1"],
            "priority": 2
        }
    ]
}
"""


class TaskOrchestrator:
    """Orchestrates multi-agent task execution.

    The TaskOrchestrator manages the execution of complex tasks by:
    1. Decomposing the main task into subtasks using LLM
    2. Assigning subtasks to appropriate specialized agents
    3. Managing execution order based on dependencies
    4. Handling failures and retries
    5. Aggregating results

    This is similar to Eigent's Workforce but simplified for 2ami.

    Usage:
        orchestrator = TaskOrchestrator(
            task_id="task_123",
            emitter=sse_emitter,
            config=OrchestratorConfig()
        )

        result = await orchestrator.execute(
            "Research AI trends and write a summary document"
        )
    """

    def __init__(
        self,
        task_id: str,
        emitter: Optional[SSEEmitter] = None,
        config: Optional[OrchestratorConfig] = None,
        llm_client: Optional[Any] = None,
        context: Optional[AgentContext] = None,
    ):
        """Initialize TaskOrchestrator.

        Args:
            task_id: Unique identifier for this orchestration
            emitter: SSE emitter for real-time events
            config: Orchestrator configuration
            llm_client: LLM client for task decomposition
            context: Agent context with shared resources
        """
        self.task_id = task_id
        self.emitter = emitter
        self.config = config or OrchestratorConfig()
        self.llm_client = llm_client
        self.context = context

        self.state = OrchestratorState.IDLE
        self.subtasks: Dict[str, SubTask] = {}
        self.completed_tasks: Set[str] = set()
        self.failed_tasks: Set[str] = set()
        self.running_tasks: Set[str] = set()

        # Agent management
        self._registry = get_registry()
        self._router = TaskRouter()
        self._agents: Dict[str, Any] = {}  # agent_type -> agent instance

        # Budget tracking
        self._budget_controller: Optional[BudgetController] = None
        if self.config.budget_config:
            self._budget_controller = BudgetController(self.config.budget_config)

        self._session_usage = SessionTokenUsage(task_id=task_id)

        # Execution control
        self._cancel_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused by default

        # Timing
        self._started_at: Optional[datetime] = None
        self._completed_at: Optional[datetime] = None

    async def execute(
        self,
        task: str,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> OrchestratorResult:
        """Execute a complex task with multi-agent orchestration.

        Args:
            task: The main task to execute
            initial_context: Optional context/variables to pass to subtasks

        Returns:
            OrchestratorResult with execution details
        """
        self._started_at = datetime.now()
        self.state = OrchestratorState.PLANNING

        try:
            # Emit task started
            await self._emit_task_state("started", task)

            # Step 1: Decompose task into subtasks
            logger.info(f"Orchestrator {self.task_id}: Decomposing task")
            await self._decompose_task(task)

            if not self.subtasks:
                raise ValueError("Task decomposition produced no subtasks")

            logger.info(
                f"Orchestrator {self.task_id}: Created {len(self.subtasks)} subtasks"
            )

            # Step 2: Execute subtasks
            self.state = OrchestratorState.EXECUTING
            await self._execute_subtasks(initial_context or {})

            # Step 3: Aggregate results
            self._completed_at = datetime.now()

            if self.failed_tasks and not self.completed_tasks:
                self.state = OrchestratorState.FAILED
                error_msgs = [
                    self.subtasks[tid].error
                    for tid in self.failed_tasks
                    if self.subtasks[tid].error
                ]
                raise RuntimeError(f"All subtasks failed: {'; '.join(error_msgs)}")

            self.state = OrchestratorState.COMPLETED

            result = self._build_result(success=True)
            await self._emit_task_completed(result)

            return result

        except BudgetExceededException as e:
            logger.warning(f"Orchestrator {self.task_id}: Budget exceeded: {e}")
            self.state = OrchestratorState.FAILED
            self._completed_at = datetime.now()

            result = self._build_result(success=False, error=str(e))
            await self._emit_task_failed(str(e))

            return result

        except asyncio.CancelledError:
            logger.info(f"Orchestrator {self.task_id}: Cancelled")
            self.state = OrchestratorState.CANCELLED
            self._completed_at = datetime.now()

            result = self._build_result(success=False, error="Cancelled by user")
            await self._emit_task_failed("Cancelled")

            return result

        except Exception as e:
            logger.exception(f"Orchestrator {self.task_id}: Failed: {e}")
            self.state = OrchestratorState.FAILED
            self._completed_at = datetime.now()

            result = self._build_result(success=False, error=str(e))
            await self._emit_task_failed(str(e))

            return result

    async def _decompose_task(self, task: str) -> None:
        """Decompose the main task into subtasks using LLM.

        Args:
            task: The main task to decompose
        """
        # If no LLM client, use rule-based decomposition
        if not self.llm_client:
            await self._rule_based_decomposition(task)
            return

        # Use LLM for smart decomposition
        try:
            messages = [
                {"role": "system", "content": TASK_DECOMPOSITION_PROMPT},
                {"role": "user", "content": f"Task to decompose:\n{task}"},
            ]

            response = await self.llm_client.chat(
                messages=messages,
                temperature=0.3,
                max_tokens=2000,
            )

            # Parse response
            import json
            content = response.get("content", "")

            # Extract JSON from response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            data = json.loads(content)
            subtasks_data = data.get("subtasks", [])

            for st_data in subtasks_data:
                subtask = SubTask(
                    id=st_data.get("id", f"subtask_{uuid.uuid4().hex[:8]}"),
                    content=st_data.get("content", ""),
                    description=st_data.get("description", ""),
                    assigned_agent=st_data.get("agent_type"),
                    dependencies=st_data.get("dependencies", []),
                    priority=st_data.get("priority", 0),
                    max_retries=self.config.max_retries_per_subtask,
                )
                self.subtasks[subtask.id] = subtask

            # Track token usage
            if "usage" in response:
                usage = TokenUsage(
                    input_tokens=response["usage"].get("input_tokens", 0),
                    output_tokens=response["usage"].get("output_tokens", 0),
                )
                self._session_usage.add_usage(usage)
                if self._budget_controller:
                    self._budget_controller.record_usage(usage)

        except Exception as e:
            logger.warning(
                f"LLM decomposition failed: {e}, falling back to rule-based"
            )
            await self._rule_based_decomposition(task)

    async def _rule_based_decomposition(self, task: str) -> None:
        """Simple rule-based task decomposition fallback.

        Args:
            task: The main task to decompose
        """
        # Use router to determine primary agent
        routing_result = self._router.route(task, self.context)

        # Create a single subtask for simple cases
        subtask = SubTask(
            id=f"subtask_{uuid.uuid4().hex[:8]}",
            content=task,
            description=f"Execute task using {routing_result.agent_type}",
            assigned_agent=routing_result.agent_type,
            priority=1,
            max_retries=self.config.max_retries_per_subtask,
        )
        self.subtasks[subtask.id] = subtask

    async def _execute_subtasks(
        self,
        context: Dict[str, Any],
    ) -> None:
        """Execute all subtasks respecting dependencies.

        Args:
            context: Shared context for subtask execution
        """
        shared_context = dict(context)
        total_timeout = self.config.total_timeout_seconds
        start_time = time.time()

        while not self._all_tasks_finished():
            # Check cancellation
            if self._cancel_event.is_set():
                logger.info(f"Orchestrator {self.task_id}: Cancellation requested")
                break

            # Check pause
            await self._pause_event.wait()

            # Check total timeout
            if time.time() - start_time > total_timeout:
                logger.warning(f"Orchestrator {self.task_id}: Total timeout exceeded")
                break

            # Get ready tasks
            ready_tasks = self._get_ready_tasks()

            if not ready_tasks:
                # No tasks ready, check if we're stuck
                if self.running_tasks:
                    # Wait for running tasks
                    await asyncio.sleep(0.1)
                    continue
                else:
                    # No running tasks and no ready tasks - deadlock or done
                    logger.warning(
                        f"Orchestrator {self.task_id}: No ready or running tasks"
                    )
                    break

            # Execute ready tasks (possibly in parallel)
            if self.config.enable_parallel_execution:
                await self._execute_parallel(ready_tasks, shared_context)
            else:
                await self._execute_sequential(ready_tasks, shared_context)

    def _get_ready_tasks(self) -> List[SubTask]:
        """Get subtasks that are ready to execute."""
        ready = []
        for subtask in self.subtasks.values():
            if subtask.state in (SubTaskState.PENDING, SubTaskState.BLOCKED):
                if subtask.is_ready(self.completed_tasks):
                    subtask.state = SubTaskState.READY
                    ready.append(subtask)

        # Sort by priority (higher first)
        ready.sort(key=lambda t: t.priority, reverse=True)

        # Limit concurrency
        max_new = self.config.max_concurrent_tasks - len(self.running_tasks)
        return ready[:max_new]

    async def _execute_parallel(
        self,
        tasks: List[SubTask],
        context: Dict[str, Any],
    ) -> None:
        """Execute tasks in parallel."""
        if not tasks:
            return

        async def run_task(subtask: SubTask):
            await self._execute_single_subtask(subtask, context)

        await asyncio.gather(
            *[run_task(t) for t in tasks],
            return_exceptions=True,
        )

    async def _execute_sequential(
        self,
        tasks: List[SubTask],
        context: Dict[str, Any],
    ) -> None:
        """Execute tasks sequentially."""
        for subtask in tasks:
            if self._cancel_event.is_set():
                break
            await self._execute_single_subtask(subtask, context)

    async def _execute_single_subtask(
        self,
        subtask: SubTask,
        context: Dict[str, Any],
    ) -> None:
        """Execute a single subtask.

        Args:
            subtask: The subtask to execute
            context: Shared context
        """
        subtask.state = SubTaskState.RUNNING
        subtask.started_at = datetime.now()
        self.running_tasks.add(subtask.id)

        await self._emit_step_started(subtask)

        try:
            # Get or create agent
            agent = await self._get_agent(subtask.assigned_agent)

            if not agent:
                raise ValueError(f"No agent available for type: {subtask.assigned_agent}")

            # Create agent context
            agent_context = self._create_agent_context(subtask, context)

            # Execute with timeout
            timeout = self.config.task_timeout_seconds

            async with asyncio.timeout(timeout):
                result = await agent.execute(
                    {"task": subtask.content, **context},
                    agent_context,
                )

            # Handle result
            if isinstance(result, AgentOutput):
                if result.success:
                    subtask.state = SubTaskState.COMPLETED
                    subtask.result = result.data
                    self.completed_tasks.add(subtask.id)
                    await self._emit_step_completed(subtask, result)
                else:
                    raise RuntimeError(result.message or "Agent execution failed")
            else:
                # Assume success if we got here
                subtask.state = SubTaskState.COMPLETED
                subtask.result = result
                self.completed_tasks.add(subtask.id)
                await self._emit_step_completed(subtask, result)

            # Update shared context with result
            context[f"result_{subtask.id}"] = subtask.result

        except asyncio.TimeoutError:
            error = f"Subtask timed out after {self.config.task_timeout_seconds}s"
            await self._handle_subtask_failure(subtask, error, context)

        except BudgetExceededException:
            raise  # Propagate budget exceptions

        except Exception as e:
            await self._handle_subtask_failure(subtask, str(e), context)

        finally:
            subtask.completed_at = datetime.now()
            self.running_tasks.discard(subtask.id)

    async def _handle_subtask_failure(
        self,
        subtask: SubTask,
        error: str,
        context: Dict[str, Any],
    ) -> None:
        """Handle subtask failure with optional retry.

        Args:
            subtask: The failed subtask
            error: Error message
            context: Shared context
        """
        logger.warning(
            f"Subtask {subtask.id} failed (attempt {subtask.retry_count + 1}): {error}"
        )

        subtask.retry_count += 1

        if (
            self.config.auto_retry_failed
            and subtask.retry_count <= subtask.max_retries
        ):
            # Retry the subtask
            logger.info(f"Retrying subtask {subtask.id}")
            subtask.state = SubTaskState.READY
            subtask.error = None
            await self._execute_single_subtask(subtask, context)
        else:
            # Mark as failed
            subtask.state = SubTaskState.FAILED
            subtask.error = error
            self.failed_tasks.add(subtask.id)
            await self._emit_step_failed(subtask, error)

    async def _get_agent(self, agent_type: Optional[str]) -> Any:
        """Get or create an agent instance.

        Args:
            agent_type: The type of agent to get

        Returns:
            Agent instance
        """
        if not agent_type:
            agent_type = AgentType.BROWSER.value

        if agent_type not in self._agents:
            # Create agent from registry
            agent = self._registry.create(agent_type)
            self._agents[agent_type] = agent

        return self._agents.get(agent_type)

    def _create_agent_context(
        self,
        subtask: SubTask,
        shared_context: Dict[str, Any],
    ) -> AgentContext:
        """Create context for subtask execution.

        Args:
            subtask: The subtask being executed
            shared_context: Shared context variables

        Returns:
            AgentContext for the subtask
        """
        return AgentContext(
            workflow_id=self.task_id,
            step_id=subtask.id,
            user_id=shared_context.get("user_id", "default_user"),
            variables=shared_context,
            step_results={
                tid: self.subtasks[tid].result
                for tid in self.completed_tasks
            },
        )

    def _all_tasks_finished(self) -> bool:
        """Check if all subtasks have finished (completed or failed)."""
        for subtask in self.subtasks.values():
            if subtask.state not in (
                SubTaskState.COMPLETED,
                SubTaskState.FAILED,
                SubTaskState.CANCELLED,
            ):
                return False
        return True

    def _build_result(
        self,
        success: bool,
        error: Optional[str] = None,
    ) -> OrchestratorResult:
        """Build the orchestration result.

        Args:
            success: Whether orchestration succeeded
            error: Error message if failed

        Returns:
            OrchestratorResult
        """
        # Aggregate final result from completed subtasks
        final_result = {}
        for tid in self.completed_tasks:
            subtask = self.subtasks[tid]
            if subtask.result:
                final_result[tid] = subtask.result

        # Count agent usage
        agent_usage: Dict[str, int] = {}
        for subtask in self.subtasks.values():
            if subtask.assigned_agent:
                agent_usage[subtask.assigned_agent] = (
                    agent_usage.get(subtask.assigned_agent, 0) + 1
                )

        duration = 0.0
        if self._started_at and self._completed_at:
            duration = (self._completed_at - self._started_at).total_seconds()

        return OrchestratorResult(
            success=success,
            task_id=self.task_id,
            subtasks_completed=len(self.completed_tasks),
            subtasks_failed=len(self.failed_tasks),
            subtasks_total=len(self.subtasks),
            final_result=final_result,
            error=error,
            duration_seconds=duration,
            token_usage=self._session_usage.to_dict() if self._session_usage else None,
            agent_usage=agent_usage,
        )

    # ==================== Event Emission ====================

    async def _emit_task_state(self, status: str, task: str) -> None:
        """Emit task state event."""
        if not self.emitter:
            return

        await self.emitter.emit(TaskStateData(
            task_id=self.task_id,
            status=status,
            task=task,
            progress=self._calculate_progress(),
        ))

    async def _emit_task_completed(self, result: OrchestratorResult) -> None:
        """Emit task completed event."""
        if not self.emitter:
            return

        await self.emitter.emit(TaskCompletedData(
            task_id=self.task_id,
            output=result.final_result,
            duration_seconds=result.duration_seconds,
        ))

    async def _emit_task_failed(self, error: str) -> None:
        """Emit task failed event."""
        if not self.emitter:
            return

        await self.emitter.emit(TaskFailedData(
            task_id=self.task_id,
            error=error,
        ))

    async def _emit_step_started(self, subtask: SubTask) -> None:
        """Emit step started event."""
        if not self.emitter:
            return

        # Find step index
        step_index = list(self.subtasks.keys()).index(subtask.id)

        await self.emitter.emit(StepStartedData(
            task_id=self.task_id,
            step_index=step_index,
            step_name=subtask.content[:50],
            step_description=subtask.description,
        ))

        # Also emit agent activation
        if subtask.assigned_agent:
            await self.emitter.emit(ActivateAgentData(
                task_id=self.task_id,
                agent_name=subtask.assigned_agent,
                agent_id=subtask.id,
                message=f"Starting: {subtask.content[:100]}",
            ))

    async def _emit_step_completed(
        self,
        subtask: SubTask,
        result: Any,
    ) -> None:
        """Emit step completed event."""
        if not self.emitter:
            return

        step_index = list(self.subtasks.keys()).index(subtask.id)
        result_preview = str(result)[:200] if result else None

        await self.emitter.emit(StepCompletedData(
            task_id=self.task_id,
            step_index=step_index,
            step_name=subtask.content[:50],
            result=result_preview,
            duration_seconds=subtask.duration_seconds,
        ))

        # Emit agent deactivation
        if subtask.assigned_agent:
            await self.emitter.emit(DeactivateAgentData(
                task_id=self.task_id,
                agent_name=subtask.assigned_agent,
                agent_id=subtask.id,
                message="Completed",
                duration_seconds=subtask.duration_seconds,
            ))

    async def _emit_step_failed(self, subtask: SubTask, error: str) -> None:
        """Emit step failed event."""
        if not self.emitter:
            return

        step_index = list(self.subtasks.keys()).index(subtask.id)

        await self.emitter.emit(StepFailedData(
            task_id=self.task_id,
            step_index=step_index,
            step_name=subtask.content[:50],
            error=error,
            recoverable=subtask.retry_count < subtask.max_retries,
        ))

    def _calculate_progress(self) -> float:
        """Calculate overall progress (0.0 to 1.0)."""
        if not self.subtasks:
            return 0.0

        completed = len(self.completed_tasks) + len(self.failed_tasks)
        return completed / len(self.subtasks)

    # ==================== Control Methods ====================

    def cancel(self) -> None:
        """Request cancellation of the orchestration."""
        logger.info(f"Orchestrator {self.task_id}: Cancel requested")
        self._cancel_event.set()

        # Cancel running subtasks
        for tid in self.running_tasks:
            if tid in self.subtasks:
                self.subtasks[tid].state = SubTaskState.CANCELLED

    def pause(self) -> None:
        """Pause the orchestration."""
        logger.info(f"Orchestrator {self.task_id}: Paused")
        self._pause_event.clear()
        self.state = OrchestratorState.PAUSED

    def resume(self) -> None:
        """Resume the orchestration."""
        logger.info(f"Orchestrator {self.task_id}: Resumed")
        self._pause_event.set()
        if self.state == OrchestratorState.PAUSED:
            self.state = OrchestratorState.EXECUTING

    def get_status(self) -> Dict[str, Any]:
        """Get current orchestration status.

        Returns:
            Status dictionary with state and progress
        """
        return {
            "task_id": self.task_id,
            "state": self.state.value,
            "progress": self._calculate_progress(),
            "subtasks_total": len(self.subtasks),
            "subtasks_completed": len(self.completed_tasks),
            "subtasks_failed": len(self.failed_tasks),
            "subtasks_running": len(self.running_tasks),
            "subtasks": [
                {
                    "id": st.id,
                    "content": st.content[:100],
                    "state": st.state.value,
                    "agent": st.assigned_agent,
                }
                for st in self.subtasks.values()
            ],
        }

    async def cleanup(self) -> None:
        """Cleanup resources."""
        # Close any agent instances
        for agent in self._agents.values():
            if hasattr(agent, "close") and asyncio.iscoroutinefunction(agent.close):
                await agent.close()
            elif hasattr(agent, "close"):
                agent.close()

        self._agents.clear()
        logger.debug(f"Orchestrator {self.task_id}: Cleaned up")
