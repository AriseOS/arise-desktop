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
    TaskDecomposedData,
    SubtaskStateData,
    TaskReplannedData,
    SSEEmitter,
)
from .schemas import AgentContext, AgentOutput
from .agent_registry import AgentType, AgentRegistry, get_registry
from .task_router import TaskRouter, RoutingResult
from .budget_controller import BudgetController, BudgetConfig, BudgetExceededException
from .token_usage import TokenUsage, SessionTokenUsage

logger = logging.getLogger(__name__)


class SubTaskState(str, Enum):
    """State of a subtask in the orchestration.

    Based on Eigent's TaskState model:
    - OPEN: Initial state, waiting for dependencies or turn
    - RUNNING: Currently being executed
    - DONE: Successfully completed
    - FAILED: Failed after max retries
    - DELETED: Cancelled via replan (not failed, just replaced)
    """
    OPEN = "OPEN"           # Pending, waiting to start
    RUNNING = "RUNNING"     # Currently executing
    DONE = "DONE"           # Successfully completed
    FAILED = "FAILED"       # Failed after retries exhausted
    DELETED = "DELETED"     # Cancelled via replan

    # Legacy aliases for backward compatibility
    @classmethod
    def _missing_(cls, value):
        """Handle legacy state names."""
        legacy_map = {
            "pending": cls.OPEN,
            "blocked": cls.OPEN,
            "ready": cls.OPEN,
            "running": cls.RUNNING,
            "completed": cls.DONE,
            "failed": cls.FAILED,
            "cancelled": cls.DELETED,
        }
        return legacy_map.get(value.lower())


class OrchestratorState(str, Enum):
    """State of the orchestrator."""
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ABANDONED = "abandoned"  # LLM determined task is impossible


@dataclass
class SubTask:
    """Represents a subtask in the orchestration.

    Subtasks are created by decomposing the main task and are
    assigned to specialized agents for execution.

    Based on Eigent's Task model with additional fields for
    dependency tracking and failure handling.
    """
    id: str
    content: str
    description: str = ""
    state: SubTaskState = SubTaskState.OPEN
    assigned_agent: Optional[str] = None  # AgentType value
    dependencies: List[str] = field(default_factory=list)  # List of subtask IDs
    priority: int = 0  # Higher = more important
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    failure_count: int = 0  # Eigent pattern: track failures separately
    abandon_reason: Optional[str] = None  # Reason if subtask was abandoned

    def is_ready(self, completed_tasks: Set[str], deleted_tasks: Optional[Set[str]] = None) -> bool:
        """Check if all dependencies are satisfied.

        Args:
            completed_tasks: Set of completed task IDs
            deleted_tasks: Set of deleted/cancelled task IDs (treated as satisfied)

        Returns:
            True if all dependencies are satisfied
        """
        deleted_tasks = deleted_tasks or set()
        for dep in self.dependencies:
            if dep in deleted_tasks:
                continue  # Deleted dependencies are considered satisfied
            if dep not in completed_tasks:
                return False
        return True

    @property
    def duration_seconds(self) -> Optional[float]:
        """Get execution duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "content": self.content,
            "description": self.description,
            "state": self.state.value,
            "dependencies": self.dependencies,
            "result": str(self.result)[:200] if self.result else None,
            "error": self.error,
            "failure_count": self.failure_count,
        }


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


class FailureConfig(BaseModel):
    """Configuration for failure handling (Eigent pattern)."""
    max_retries: int = 3                      # Max retry attempts per subtask
    retry_delay_seconds: float = 1.0          # Delay between retries
    auto_replan_on_failure: bool = True       # Trigger replan after max retries
    fail_fast: bool = False                   # Stop entire task on first failure


class OrchestratorConfig(BaseModel):
    """Configuration for TaskOrchestrator."""
    max_concurrent_tasks: int = 3
    max_subtasks: int = 20
    task_timeout_seconds: int = 300  # Per subtask timeout
    total_timeout_seconds: int = 1800  # Total orchestration timeout
    enable_parallel_execution: bool = False  # Default to sequential for single-agent
    auto_retry_failed: bool = True
    max_retries_per_subtask: int = 3
    budget_config: Optional[BudgetConfig] = None
    failure_config: FailureConfig = Field(default_factory=FailureConfig)
    single_agent_mode: bool = True  # New: single agent executes all subtasks


# Eigent-style task decomposition prompt
# Based on: third-party/eigent/backend/.venv/lib/python3.10/site-packages/camel/societies/workforce/prompts.py
TASK_DECOMPOSITION_PROMPT = """You are a Task Decomposition Expert. Analyze the task and break it down into executable subtasks.

## NAVIGATION MAP (from Memory)
{memory_context}

## UNDERSTANDING THE NAVIGATION MAP

The Navigation Map above shows a **verified path** to reach certain page types. Key concepts:

1. **States are page TYPES, not fixed URLs**
   - State description = type of page (e.g., "产品周排行榜页面" = weekly leaderboard page type)
   - State URL = a REFERENCE example, not the only valid URL
   - The same page type may have different URLs (e.g., weekly/2026/3 vs weekly/2026/4)

2. **Actions show HOW to navigate between page types**
   - Action description = what to click/do to reach next page type
   - Use these as navigation guidance

3. **The Map is a ROUTE, not the TASK**
   - The Map tells you HOW to reach certain pages
   - The TASK tells you WHAT to accomplish on those pages
   - You must decompose based on the TASK, using the Map as navigation reference

## CRITICAL RULES:

1. **DECOMPOSE THE USER'S ACTUAL TASK**
   - Focus on WHAT the user wants to accomplish
   - Navigation is a MEANS, not the GOAL
   - BAD: "Navigate to weekly leaderboard page" (this is just navigation)
   - GOOD: "Collect product information from weekly leaderboard and identify Chinese team members"

2. **USE MAP AS NAVIGATION REFERENCE**
   - Include Map guidance in subtask descriptions
   - "Use Navigation Map Step 2-3 to reach the weekly leaderboard"
   - Don't create separate subtasks just for navigation

3. **SELF-CONTAINED**: Each subtask must be independently executable with all necessary context.
   - BAD: "Continue from previous step"
   - GOOD: "On the weekly leaderboard page, click each product to view team details"

4. **CLEAR DELIVERABLE**: Define exactly what each subtask produces.
   - BAD: "Research the topic"
   - GOOD: "For each product in top 10, record: name, description, team members, team nationality"

5. **INCLUDE ITERATION WHEN NEEDED**
   - If task requires processing multiple items, make that explicit
   - "For EACH of the top 10 products: visit detail page, check Team tab, record member info"

## OUTPUT FORMAT:
Return valid JSON only, no markdown code blocks:
{{
    "analysis": "Brief analysis: what the user wants to achieve, how the Navigation Map helps",
    "navigation_map_summary": "Brief summary of the navigation path from the Map",
    "subtasks": [
        {{
            "id": "1.1",
            "content": "Clear description of what to ACCOMPLISH (not just navigate)",
            "navigation_hint": "Which Map steps to use for this subtask",
            "dependencies": []
        }},
        {{
            "id": "1.2",
            "content": "Next step with clear deliverable",
            "navigation_hint": "Map step reference or 'Continue on current page'",
            "dependencies": ["1.1"]
        }}
    ]
}}

## TASK TO DECOMPOSE:
{task}
"""

# Prompt for automatic replan after failure
TASK_REPLAN_PROMPT = """A subtask has failed and needs replanning.

## FAILED SUBTASK:
- ID: {subtask_id}
- Content: {subtask_content}
- Error: {error}
- Attempts: {failure_count}/{max_retries}

## CURRENT PLAN STATUS:
{plan_summary}

## YOUR OPTIONS:
1. **replan**: Suggest alternative approach with new subtasks
2. **skip**: Mark this subtask as skipped (if not critical)
3. **fail**: Stop the entire task (if this subtask is blocking)

## OUTPUT FORMAT:
Return valid JSON only:
{
    "action": "replan" | "skip" | "fail",
    "reason": "Explanation of your decision",
    "new_subtasks": [
        {"id": "1.2.1", "content": "Alternative approach", "dependencies": [...]}
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

            # Step 3: Check for abandonment or aggregate results
            self._completed_at = datetime.now()

            # Check if task was abandoned by LLM
            if self.is_abandoned():
                self.state = OrchestratorState.ABANDONED
                reason = self.get_abandon_reason()
                logger.info(f"Orchestrator {self.task_id}: Task abandoned - {reason}")

                result = self._build_result(success=False, error=f"Task abandoned: {reason}")
                await self._emit_task_failed(f"Abandoned: {reason}")

                return result

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

    async def _decompose_task(
        self,
        task: str,
        cognitive_phrase: Optional[Any] = None,
        path: Optional[Any] = None,
    ) -> List[SubTask]:
        """Decompose the main task into subtasks.

        Memory-first strategy:
        1. If cognitive_phrase exists: Use user-recorded workflow as guide
        2. Elif path exists: Use retrieved path as guide
        3. Else: LLM decomposes from scratch

        Args:
            task: The main task to decompose
            cognitive_phrase: Optional CognitivePhrase from memory
            path: Optional Path from memory

        Returns:
            List of created subtasks
        """
        # Import here to avoid circular dependency
        from ..tools.toolkits.memory_toolkit import (
            CognitivePhrase, Path, MemoryToolkit
        )

        # === Case 1: CognitivePhrase exists - use as primary guide ===
        if cognitive_phrase:
            subtasks = self._cognitive_phrase_to_subtasks(task, cognitive_phrase)
            if subtasks:
                logger.info(
                    f"[Memory] Used CognitivePhrase to create {len(subtasks)} subtasks"
                )
                await self._emit_task_decomposed(task)
                return subtasks
            logger.warning("[Memory] CognitivePhrase conversion failed, trying path")

        # === Case 2: Path exists - use as navigation guide ===
        # Path from /api/v1/memory/query is a Navigation Map showing how to reach certain page types.
        # It should be passed to LLM as context, NOT directly converted to subtasks.
        # The LLM will decompose based on the user's ACTUAL TASK, using the Path as navigation guidance.

        # === Case 3: LLM decomposition with Path as Navigation Map ===
        if not self.llm_client:
            await self._rule_based_decomposition(task)
            return list(self.subtasks.values())

        try:
            # Build memory context for LLM
            memory_context = self._format_memory_context_for_decomposition(
                cognitive_phrase, path
            )

            user_prompt = TASK_DECOMPOSITION_PROMPT.format(
                task=task,
                memory_context=memory_context,
            )
            system_prompt = "You are a Task Decomposition Expert. Return valid JSON only."

            content = await self.llm_client.generate_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

            # Parse response
            import json
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            content = content.strip()
            data = json.loads(content)
            subtasks_data = data.get("subtasks", [])

            logger.info(f"[LLM] Decomposition: {len(subtasks_data)} subtasks")

            for st_data in subtasks_data:
                subtask = SubTask(
                    id=st_data.get("id", f"subtask_{uuid.uuid4().hex[:8]}"),
                    content=st_data.get("content", ""),
                    description=st_data.get("description", ""),
                    dependencies=st_data.get("dependencies", []),
                    max_retries=self.config.max_retries_per_subtask,
                )
                self.subtasks[subtask.id] = subtask

            await self._emit_task_decomposed(task)
            return list(self.subtasks.values())

        except Exception as e:
            logger.warning(f"LLM decomposition failed: {e}, falling back to rule-based")
            await self._rule_based_decomposition(task)
            return list(self.subtasks.values())

    def _cognitive_phrase_to_subtasks(
        self,
        task: str,
        phrase: Any,
    ) -> List[SubTask]:
        """Convert CognitivePhrase to subtasks.

        Each state in the phrase becomes a subtask.

        Args:
            task: Original task description
            phrase: CognitivePhrase from memory

        Returns:
            List of SubTask objects, or empty list if conversion fails
        """
        if not phrase or not phrase.states:
            return []

        subtasks = []
        prev_id = None

        for i, state in enumerate(phrase.states):
            # Build subtask content
            subtask_id = f"1.{i + 1}"
            content = f"Navigate to: {state.description}"

            if state.page_url:
                content += f" (URL: {state.page_url})"

            # Add action to next state if exists
            if i < len(phrase.actions):
                action = phrase.actions[i]
                if action.description:
                    content += f". Then: {action.description}"

            # Add intent_sequences hints
            if state.intent_sequences:
                ops = [seq.description for seq in state.intent_sequences[:3] if seq.description]
                if ops:
                    content += f". Available operations: {', '.join(ops)}"

            subtask = SubTask(
                id=subtask_id,
                content=content,
                description=state.description,
                dependencies=[prev_id] if prev_id else [],
                max_retries=self.config.max_retries_per_subtask,
            )
            self.subtasks[subtask_id] = subtask
            subtasks.append(subtask)
            prev_id = subtask_id

        return subtasks

    def _path_to_subtasks(
        self,
        task: str,
        path: Any,
    ) -> List[SubTask]:
        """Convert retrieved Path to subtasks.

        Each state in the path becomes a subtask.

        Args:
            task: Original task description
            path: Path from memory (states + actions)

        Returns:
            List of SubTask objects, or empty list if conversion fails
        """
        if not path or not path.states:
            return []

        subtasks = []
        prev_id = None

        for i, state in enumerate(path.states):
            subtask_id = f"1.{i + 1}"
            content = f"Navigate to: {state.description}"

            if state.page_url:
                content += f" (URL: {state.page_url})"

            # Add action to next state if exists
            if i < len(path.actions):
                action = path.actions[i]
                if action.description:
                    content += f". Then: {action.description}"

            # Add intent_sequences hints
            if state.intent_sequences:
                ops = [seq.description for seq in state.intent_sequences[:3] if seq.description]
                if ops:
                    content += f". Available operations: {', '.join(ops)}"

            subtask = SubTask(
                id=subtask_id,
                content=content,
                description=state.description,
                dependencies=[prev_id] if prev_id else [],
                max_retries=self.config.max_retries_per_subtask,
            )
            self.subtasks[subtask_id] = subtask
            subtasks.append(subtask)
            prev_id = subtask_id

        return subtasks

    def _format_memory_context_for_decomposition(
        self,
        cognitive_phrase: Optional[Any],
        path: Optional[Any],
    ) -> str:
        """Format Memory info for task decomposition prompt.

        Args:
            cognitive_phrase: CognitivePhrase from memory (if any)
            path: Path from memory (if any)

        Returns:
            Formatted string for the decomposition prompt.
        """
        # Import formatters
        from ..tools.toolkits.memory_toolkit import MemoryToolkit

        if cognitive_phrase:
            return MemoryToolkit.format_cognitive_phrase(cognitive_phrase)
        elif path:
            return MemoryToolkit.format_path(path)
        else:
            return "No workflow guidance available from memory. Decompose based on logical steps."

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
        deleted_tasks = self._get_deleted_tasks()
        for subtask in self.subtasks.values():
            if subtask.state == SubTaskState.OPEN:
                if subtask.is_ready(self.completed_tasks, deleted_tasks):
                    subtask.state = SubTaskState.RUNNING
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
                    subtask.state = SubTaskState.DONE
                    subtask.result = result.data
                    self.completed_tasks.add(subtask.id)
                    await self._emit_step_completed(subtask, result)
                else:
                    raise RuntimeError(result.message or "Agent execution failed")
            else:
                # Assume success if we got here
                subtask.state = SubTaskState.DONE
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
        """Handle subtask failure with retry, fail_fast, and dependency handling.

        Based on docs/task-planning-system.md lines 540-608.

        Args:
            subtask: The failed subtask
            error: Error message
            context: Shared context
        """
        subtask.failure_count += 1
        subtask.retry_count += 1

        logger.warning(
            f"Subtask {subtask.id} failed (attempt {subtask.retry_count}/{subtask.max_retries}): {error}"
        )

        # Step 1: Check fail_fast mode - stop entire task on first failure
        if self.config.failure_config.fail_fast:
            logger.error(f"fail_fast enabled: stopping entire task due to {subtask.id} failure")
            subtask.state = SubTaskState.FAILED
            subtask.error = error
            self.failed_tasks.add(subtask.id)
            await self._emit_step_failed(subtask, error)
            raise TaskFailedException(f"Subtask {subtask.id} failed: {error}")

        # Step 2: Check if retry is possible
        if (
            self.config.auto_retry_failed
            and subtask.retry_count <= subtask.max_retries
        ):
            # Apply retry delay before retrying
            retry_delay = self.config.failure_config.retry_delay_seconds
            if retry_delay > 0:
                logger.info(
                    f"Waiting {retry_delay}s before retrying subtask {subtask.id}"
                )
                await asyncio.sleep(retry_delay)

            # Emit RETRY event
            self._emit_subtask_state_sync(subtask.id, "RETRY", error)

            # Reset subtask to OPEN for retry - the main loop will pick it up
            # Note: We don't recursively call _execute_single_subtask here to avoid
            # stack overflow with multiple retries. The main loop handles retry.
            logger.info(f"Resetting subtask {subtask.id} to OPEN for retry")
            subtask.state = SubTaskState.OPEN
            subtask.error = None
            # Don't add to running_tasks - let _get_ready_tasks handle it
            return

        # Step 3: Max retries exhausted
        logger.warning(
            f"Subtask {subtask.id} failed after {subtask.max_retries} attempts"
        )

        # Mark as failed
        subtask.state = SubTaskState.FAILED
        subtask.error = error
        self.failed_tasks.add(subtask.id)
        await self._emit_step_failed(subtask, error)

        # Step 4: Handle dependency failure - notify blocked tasks
        blocked_tasks = self.handle_dependency_failure(subtask.id)
        if blocked_tasks:
            logger.warning(
                f"Subtask {subtask.id} failure blocks {len(blocked_tasks)} dependent tasks: {blocked_tasks}"
            )

        # Step 5: Trigger automatic replan if configured
        if self.config.failure_config.auto_replan_on_failure:
            logger.info(f"Triggering auto-replan for failed subtask {subtask.id}")
            await self.auto_replan_failed_subtask(subtask, error)

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
                SubTaskState.DONE,
                SubTaskState.FAILED,
                SubTaskState.DELETED,
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
                self.subtasks[tid].state = SubTaskState.DELETED

    def abandon(self, reason: str) -> None:
        """Abandon the task when LLM determines it's impossible to complete.

        Unlike cancel (user-initiated), abandon is called by the LLM when it
        determines the task cannot be completed due to:
        - Fundamental impossibility (e.g., website doesn't exist)
        - Repeated failures with no viable alternatives
        - Missing prerequisites that cannot be obtained
        - Task requirements that conflict with constraints

        Args:
            reason: Explanation of why the task cannot be completed.
        """
        logger.warning(f"Orchestrator {self.task_id}: Task abandoned - {reason}")
        self._abandon_reason = reason
        self._cancel_event.set()  # Reuse cancel mechanism to stop execution

        # Mark all remaining tasks as deleted
        for tid, subtask in self.subtasks.items():
            if subtask.state in (SubTaskState.OPEN, SubTaskState.RUNNING):
                subtask.state = SubTaskState.DELETED

    def is_abandoned(self) -> bool:
        """Check if task was abandoned by LLM."""
        return hasattr(self, '_abandon_reason') and self._abandon_reason is not None

    def get_abandon_reason(self) -> Optional[str]:
        """Get the reason for task abandonment."""
        return getattr(self, '_abandon_reason', None)

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

    # ==================== Single-Agent Mode Methods ====================
    # These methods support the design where a single LLM agent executes
    # subtasks one by one, controlled by the agent loop.

    def get_plan_summary(self) -> str:
        """Get compact plan summary for LLM context injection.

        This summary is injected into the LLM context each loop iteration
        so the agent knows what's completed, what's current, and what's next.

        Returns:
            Formatted plan summary string
        """
        if not self.subtasks:
            return "No plan created yet."

        lines = ["## Current Task Plan"]

        # Find current subtask (first RUNNING or first OPEN that's ready)
        current_id = None
        for subtask in self.subtasks.values():
            if subtask.state == SubTaskState.RUNNING:
                current_id = subtask.id
                break

        if not current_id:
            # Find next ready task
            for subtask in self.subtasks.values():
                if subtask.state == SubTaskState.OPEN and subtask.is_ready(
                    self.completed_tasks, self._get_deleted_tasks()
                ):
                    current_id = subtask.id
                    break

        for subtask in self.subtasks.values():
            if subtask.state == SubTaskState.DONE:
                status = "[x]"
                suffix = "✓"
            elif subtask.state == SubTaskState.FAILED:
                status = "[!]"
                # Show failure count and error
                error_msg = subtask.error[:30] if subtask.error else 'unknown'
                suffix = f"FAILED (tried {subtask.failure_count}x): {error_msg}"
            elif subtask.state == SubTaskState.DELETED:
                status = "[-]"
                # Distinguish between cancelled and abandoned
                if subtask.abandon_reason:
                    reason_preview = subtask.abandon_reason[:30]
                    suffix = f"ABANDONED: {reason_preview}"
                else:
                    suffix = "cancelled"
            elif subtask.id == current_id:
                status = "[→]"
                # Show retry count if there were previous failures
                if subtask.failure_count > 0:
                    suffix = f"← CURRENT (retry #{subtask.failure_count + 1})"
                else:
                    suffix = "← CURRENT"
            else:
                status = "[ ]"
                # Show if this task has had failures before
                if subtask.failure_count > 0:
                    suffix = f"(failed {subtask.failure_count}x, will retry)"
                else:
                    suffix = ""

            # Truncate content for summary
            content = subtask.content[:60]
            if len(subtask.content) > 60:
                content += "..."

            line = f"- {status} {subtask.id}: {content}"
            if suffix:
                line += f" {suffix}"
            lines.append(line)

        # Add instruction for current task
        if current_id:
            current = self.subtasks[current_id]
            lines.append("")
            lines.append(f"**Current task ({current_id})**: {current.content}")
            lines.append("Complete this task, then call `complete_subtask()` to proceed.")

        return "\n".join(lines)

    def all_done(self) -> bool:
        """Check if all subtasks are completed (or deleted/failed).

        Used by agent loop to determine when to exit.

        Returns:
            True if no more subtasks need execution
        """
        for subtask in self.subtasks.values():
            if subtask.state in (SubTaskState.OPEN, SubTaskState.RUNNING):
                return False
        return True

    def get_final_result(self) -> Any:
        """Get the final result from the last completed subtask.

        Returns the result of the last DONE subtask, which typically
        contains the extracted data or final output.

        Returns:
            The result from the last completed subtask, or None if no subtask completed
        """
        last_result = None
        last_completed_at = None

        for subtask in self.subtasks.values():
            if subtask.state == SubTaskState.DONE and subtask.result is not None:
                # Track the most recently completed subtask
                if last_completed_at is None or (
                    subtask.completed_at and subtask.completed_at > last_completed_at
                ):
                    last_completed_at = subtask.completed_at
                    last_result = subtask.result

        return last_result

    def get_next_subtask(self) -> Optional[SubTask]:
        """Get the next subtask that is ready to execute.

        Returns:
            Next ready subtask, or None if no subtask is ready
        """
        deleted_tasks = self._get_deleted_tasks()

        for subtask in self.subtasks.values():
            if subtask.state == SubTaskState.OPEN:
                if subtask.is_ready(self.completed_tasks, deleted_tasks):
                    return subtask

        return None

    def get_current_subtask(self) -> Optional[SubTask]:
        """Get the currently running subtask.

        Returns:
            Currently running subtask, or None
        """
        for subtask in self.subtasks.values():
            if subtask.state == SubTaskState.RUNNING:
                return subtask
        return None

    def _get_deleted_tasks(self) -> Set[str]:
        """Get set of deleted task IDs."""
        return {
            st.id for st in self.subtasks.values()
            if st.state == SubTaskState.DELETED
        }

    def mark_running(self, subtask_id: str) -> None:
        """Mark a subtask as running and emit SSE event.

        Args:
            subtask_id: ID of the subtask to mark
        """
        if subtask_id not in self.subtasks:
            logger.warning(f"Subtask {subtask_id} not found")
            return

        subtask = self.subtasks[subtask_id]
        subtask.state = SubTaskState.RUNNING
        subtask.started_at = datetime.now()
        self.running_tasks.add(subtask_id)

        logger.info(f"Subtask {subtask_id} marked as RUNNING")

        # Emit SSE event
        self._emit_subtask_state_sync(subtask_id, "RUNNING")

    def mark_completed(self, subtask_id: str, result: Any = None) -> None:
        """Mark a subtask as completed and emit SSE event.

        Args:
            subtask_id: ID of the subtask to mark
            result: Result of the subtask execution
        """
        if subtask_id not in self.subtasks:
            logger.warning(f"Subtask {subtask_id} not found")
            return

        subtask = self.subtasks[subtask_id]
        subtask.state = SubTaskState.DONE
        subtask.result = result
        subtask.completed_at = datetime.now()
        subtask.error = None

        self.running_tasks.discard(subtask_id)
        self.completed_tasks.add(subtask_id)

        logger.info(f"Subtask {subtask_id} marked as DONE")

        # Emit SSE event
        result_str = str(result)[:200] if result else None
        self._emit_subtask_state_sync(subtask_id, "DONE", result_str)

    def mark_failed(self, subtask_id: str, error: str) -> None:
        """Mark a subtask as failed and emit SSE event.

        Args:
            subtask_id: ID of the subtask to mark
            error: Error message
        """
        if subtask_id not in self.subtasks:
            logger.warning(f"Subtask {subtask_id} not found")
            return

        subtask = self.subtasks[subtask_id]
        subtask.state = SubTaskState.FAILED
        subtask.error = error
        subtask.completed_at = datetime.now()
        subtask.failure_count += 1

        self.running_tasks.discard(subtask_id)
        self.failed_tasks.add(subtask_id)

        logger.info(f"Subtask {subtask_id} marked as FAILED: {error}")

        # Emit SSE event
        self._emit_subtask_state_sync(subtask_id, "FAILED", error)

    def mark_abandoned(self, subtask_id: str, reason: str) -> None:
        """Mark a subtask as abandoned (impossible to complete).

        Unlike mark_failed (which may trigger retries), abandoned subtasks
        are permanently marked as DELETED and won't be retried.

        Args:
            subtask_id: ID of the subtask to abandon
            reason: Explanation of why the subtask cannot be completed
        """
        if subtask_id not in self.subtasks:
            logger.warning(f"Subtask {subtask_id} not found")
            return

        subtask = self.subtasks[subtask_id]
        subtask.state = SubTaskState.DELETED
        subtask.abandon_reason = reason
        subtask.error = f"Abandoned: {reason}"
        subtask.completed_at = datetime.now()

        self.running_tasks.discard(subtask_id)
        # Don't add to failed_tasks - abandoned is different from failed

        logger.info(f"Subtask {subtask_id} abandoned: {reason}")

        # Emit SSE event with abandon reason
        self._emit_subtask_state_sync(subtask_id, "ABANDONED", reason)

    def update_subtasks_from_confirmation(self, confirmed_subtasks: List[Dict]) -> None:
        """Update subtasks based on user confirmation (may be edited).

        This allows users to:
        - Edit subtask content
        - Remove subtasks
        - Reorder subtasks (by updating IDs)

        Args:
            confirmed_subtasks: List of confirmed subtask dicts from frontend
        """
        if not confirmed_subtasks:
            return

        # Create a map of confirmed subtasks by ID
        confirmed_map = {st.get("id"): st for st in confirmed_subtasks}
        confirmed_ids = set(confirmed_map.keys())
        current_ids = set(self.subtasks.keys())

        # Remove subtasks that were deleted by user
        for subtask_id in current_ids - confirmed_ids:
            if subtask_id in self.subtasks:
                self.subtasks[subtask_id].state = SubTaskState.DELETED
                logger.info(f"Subtask {subtask_id} marked as DELETED by user")

        # Update content of existing subtasks
        for subtask_id, confirmed in confirmed_map.items():
            if subtask_id in self.subtasks:
                old_content = self.subtasks[subtask_id].content
                new_content = confirmed.get("content", old_content)
                if new_content != old_content:
                    self.subtasks[subtask_id].content = new_content
                    logger.info(f"Subtask {subtask_id} content updated by user")
            else:
                # New subtask added by user
                new_subtask = SubTask(
                    id=subtask_id,
                    content=confirmed.get("content", ""),
                )
                self.subtasks[subtask_id] = new_subtask
                logger.info(f"Subtask {subtask_id} added by user")

        logger.info(f"Subtasks updated from confirmation: {len(confirmed_subtasks)} subtasks")

    def _emit_subtask_state_sync(
        self,
        subtask_id: str,
        state: str,
        result: Optional[str] = None,
    ) -> None:
        """Emit subtask state change SSE event (sync wrapper).

        Args:
            subtask_id: The subtask ID
            state: New state value
            result: Optional result or error message
        """
        if not self.emitter:
            return

        subtask = self.subtasks.get(subtask_id)
        failure_count = subtask.failure_count if subtask else 0

        event = SubtaskStateData(
            task_id=self.task_id,
            subtask_id=subtask_id,
            state=state,
            result=result,
            failure_count=failure_count,
        )

        # Use asyncio.create_task if in async context
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.emitter.emit(event))
        except RuntimeError:
            # No running loop - skip SSE for now
            logger.debug(f"No event loop, skipping SSE for subtask {subtask_id}")

    def _emit_replan_event_sync(
        self,
        reason: str,
        added_count: int,
        cancelled_count: int,
    ) -> None:
        """Emit task replanned SSE event (sync wrapper).

        Args:
            reason: Why replan was needed.
            added_count: Number of subtasks added.
            cancelled_count: Number of subtasks cancelled.
        """
        if not self.emitter:
            return

        event = TaskReplannedData(
            task_id=self.task_id,
            subtasks=[st.to_dict() for st in self.subtasks.values()],
            original_task_id=self.task_id,
            reason=reason,
        )

        # Use asyncio.create_task if in async context
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.emitter.emit(event))
        except RuntimeError:
            # No running loop - skip SSE for now
            logger.debug(f"No event loop, skipping SSE for replan event")

    # ==================== Replan Methods ====================

    def replan(
        self,
        reason: str,
        new_subtasks: List[Dict[str, Any]],
        cancelled_task_ids: Optional[List[str]] = None,
    ) -> str:
        """Replan the current task by cancelling some subtasks and adding new ones.

        This is called when:
        - LLM discovers new information that changes the plan
        - A subtask fails and needs an alternative approach
        - The original plan is no longer valid

        Args:
            reason: Why replan is needed (for logging)
            new_subtasks: List of new subtasks to add
                [{"id": "1.3", "content": "...", "dependencies": [...]}]
            cancelled_task_ids: List of subtask IDs to cancel

        Returns:
            Updated plan summary
        """
        logger.info(f"Replan triggered: {reason}")

        # Cancel specified tasks
        cancelled_task_ids = cancelled_task_ids or []
        for task_id in cancelled_task_ids:
            if task_id in self.subtasks:
                subtask = self.subtasks[task_id]
                subtask.state = SubTaskState.DELETED
                self.running_tasks.discard(task_id)
                logger.info(f"Subtask {task_id} cancelled via replan")

        # Add new subtasks
        for st_data in new_subtasks:
            subtask_id = st_data.get("id", f"subtask_{uuid.uuid4().hex[:8]}")

            # Filter out dependencies on DELETED tasks
            deps = st_data.get("dependencies", [])
            valid_deps = [
                d for d in deps
                if d not in cancelled_task_ids and
                   (d not in self.subtasks or
                    self.subtasks[d].state != SubTaskState.DELETED)
            ]

            subtask = SubTask(
                id=subtask_id,
                content=st_data.get("content", ""),
                description=st_data.get("description", ""),
                dependencies=valid_deps,
                max_retries=self.config.max_retries_per_subtask,
            )
            self.subtasks[subtask_id] = subtask
            logger.info(f"Added new subtask {subtask_id} via replan")

        # Emit replan event
        self._emit_replan_event_sync(reason, len(new_subtasks), len(cancelled_task_ids))

        return self.get_plan_summary()

    async def _emit_replan_event(
        self,
        reason: str,
        added_count: int,
        cancelled_count: int,
    ) -> None:
        """Emit task replanned SSE event."""
        if not self.emitter:
            return

        # Emit proper TaskReplannedData event
        await self.emitter.emit(TaskReplannedData(
            task_id=self.task_id,
            subtasks=[st.to_dict() for st in self.subtasks.values()],
            original_task_id=self.task_id,
            reason=reason,
        ))

    async def _emit_task_decomposed(self, task: str) -> None:
        """Emit task decomposed SSE event.

        Args:
            task: The original task content
        """
        if not self.emitter:
            return

        await self.emitter.emit(TaskDecomposedData(
            task_id=self.task_id,
            subtasks=[st.to_dict() for st in self.subtasks.values()],
            summary_task=task[:100],
            original_task_id=self.task_id,
            total_subtasks=len(self.subtasks),
        ))

    async def auto_replan_failed_subtask(self, subtask: SubTask, error: str) -> bool:
        """Automatically replan a failed subtask using LLM.

        Called when a subtask fails after max retries and auto_replan is enabled.

        Args:
            subtask: The failed subtask
            error: Error message

        Returns:
            True if replan succeeded, False otherwise
        """
        if not self.llm_client:
            logger.warning("No LLM client for auto-replan, marking as failed")
            return False

        try:
            user_prompt = TASK_REPLAN_PROMPT.format(
                subtask_id=subtask.id,
                subtask_content=subtask.content,
                error=error,
                failure_count=subtask.failure_count,
                max_retries=subtask.max_retries,
                plan_summary=self.get_plan_summary(),
            )

            system_prompt = "You are a Task Replan Expert. Analyze the failed subtask and decide the best course of action. Return valid JSON only."

            content = await self.llm_client.generate_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

            import json

            # Parse JSON response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            data = json.loads(content)
            action = data.get("action", "fail")
            reason = data.get("reason", "Unknown reason")

            if action == "replan":
                new_subtasks = data.get("new_subtasks", [])
                self.replan(reason, new_subtasks, [subtask.id])
                return True

            elif action == "skip":
                subtask.state = SubTaskState.DELETED
                logger.info(f"Subtask {subtask.id} skipped: {reason}")
                return True

            else:  # fail
                subtask.state = SubTaskState.FAILED
                self.failed_tasks.add(subtask.id)
                logger.warning(f"Subtask {subtask.id} failed permanently: {reason}")
                return False

        except Exception as e:
            logger.exception(f"Auto-replan failed: {e}")
            subtask.state = SubTaskState.FAILED
            self.failed_tasks.add(subtask.id)
            return False

    def handle_dependency_failure(self, failed_task_id: str) -> List[str]:
        """Handle downstream effects of a failed subtask.

        When a subtask fails, all subtasks that depend on it (directly or
        transitively) may become unexecutable. This method identifies such
        tasks and optionally triggers a replan.

        Args:
            failed_task_id: The ID of the failed subtask.

        Returns:
            List of subtask IDs that are blocked by this failure.
        """
        blocked_tasks = []

        for subtask in self.subtasks.values():
            if subtask.state in (SubTaskState.DONE, SubTaskState.FAILED, SubTaskState.DELETED):
                continue

            if failed_task_id in subtask.dependencies:
                blocked_tasks.append(subtask.id)
                logger.warning(
                    f"Subtask {subtask.id} is blocked by failed dependency {failed_task_id}"
                )

        if blocked_tasks and self.config.failure_config.auto_replan_on_failure:
            logger.info(
                f"Dependency failure affects {len(blocked_tasks)} tasks, "
                f"auto-replan may be triggered"
            )

        return blocked_tasks


class TaskFailedException(Exception):
    """Exception raised when a task fails permanently."""
    pass


class MessageHistoryManager:
    """Manages message history for long-running tasks.

    Long-running tasks accumulate many messages and can exceed token limits.
    This class implements a compression strategy to manage context size.

    Based on docs/task-planning-system.md lines 648-723.
    """

    class MessageCategory(Enum):
        """Categories for message classification."""
        SYSTEM = "system"           # System prompt - always keep
        PLAN_SUMMARY = "plan"       # Current plan - always keep (updated each loop)
        CURRENT_SUBTASK = "current" # Current subtask messages - keep full detail
        COMPLETED = "completed"     # Completed subtask messages - compress
        TOOL_RESULT = "tool"        # Tool call results - compress after use

    def __init__(self, max_tokens: int = 100000):
        """Initialize MessageHistoryManager.

        Args:
            max_tokens: Maximum estimated tokens before compression is triggered.
        """
        self.max_tokens = max_tokens
        self.compression_threshold = 0.8  # Compress when 80% full
        self._chars_per_token = 4  # Rough estimate

    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Estimate token count from messages.

        Args:
            messages: List of message dicts.

        Returns:
            Estimated token count.
        """
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        total_chars += len(str(item.get("content", "")))
                        total_chars += len(str(item.get("text", "")))
        return total_chars // self._chars_per_token

    def manage_history(
        self,
        messages: List[Dict[str, Any]],
        current_subtask_id: Optional[str],
        completed_subtask_ids: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Compress history if approaching token limit.

        Args:
            messages: Full message history.
            current_subtask_id: ID of the currently executing subtask.
            completed_subtask_ids: Set of completed subtask IDs.

        Returns:
            Potentially compressed message list.
        """
        estimated_tokens = self._estimate_tokens(messages)

        if estimated_tokens < self.max_tokens * self.compression_threshold:
            return messages  # No compression needed

        logger.info(
            f"[MessageHistoryManager] Token estimate {estimated_tokens} exceeds "
            f"threshold ({self.max_tokens * self.compression_threshold:.0f}), compressing"
        )

        return self._compress_messages(
            messages, current_subtask_id, completed_subtask_ids or set()
        )

    def _compress_messages(
        self,
        messages: List[Dict[str, Any]],
        current_subtask_id: Optional[str],
        completed_subtask_ids: Set[str],
    ) -> List[Dict[str, Any]]:
        """Compress old messages while preserving important context.

        Args:
            messages: Full message history.
            current_subtask_id: ID of currently executing subtask.
            completed_subtask_ids: Set of completed subtask IDs.

        Returns:
            Compressed message list.
        """
        import copy

        compressed = []
        completed_summaries = []

        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")

            # Always keep system messages
            if role == "system":
                compressed.append(copy.deepcopy(msg))
                continue

            # Check if this is a plan summary message
            if isinstance(content, str) and "## Current Task Plan" in content:
                # Only keep the most recent plan summary
                if i == len(messages) - 1 or not any(
                    "## Current Task Plan" in str(m.get("content", ""))
                    for m in messages[i+1:]
                ):
                    compressed.append(copy.deepcopy(msg))
                continue

            # Check if this is tool result from current subtask
            if role == "user" and isinstance(content, list):
                # This is likely tool results - check if recent
                is_recent = i >= len(messages) - 4  # Keep last few exchanges
                if is_recent:
                    compressed.append(copy.deepcopy(msg))
                else:
                    # Compress older tool results
                    compressed_msg = copy.deepcopy(msg)
                    for item in compressed_msg.get("content", []):
                        if isinstance(item, dict) and item.get("type") == "tool_result":
                            original = item.get("content", "")
                            if isinstance(original, str) and len(original) > 500:
                                item["content"] = self._truncate_tool_result(original)
                    compressed.append(compressed_msg)
                continue

            # Keep assistant messages (they're usually smaller)
            compressed.append(copy.deepcopy(msg))

        # Add completed summaries if any
        if completed_summaries:
            summary_msg = {
                "role": "system",
                "content": "## Completed Subtasks Summary\n" + "\n".join(completed_summaries)
            }
            # Insert after first system message
            insert_idx = 1 if compressed and compressed[0].get("role") == "system" else 0
            compressed.insert(insert_idx, summary_msg)

        before_tokens = self._estimate_tokens(messages)
        after_tokens = self._estimate_tokens(compressed)
        logger.info(
            f"[MessageHistoryManager] Compressed {before_tokens} -> {after_tokens} tokens "
            f"({(1 - after_tokens/before_tokens)*100:.1f}% reduction)"
        )

        return compressed

    def _truncate_tool_result(self, content: str, max_length: int = 500) -> str:
        """Truncate long tool results.

        Args:
            content: Original tool result content.
            max_length: Maximum length to keep.

        Returns:
            Truncated content.
        """
        if len(content) <= max_length:
            return content
        return content[:max_length] + f"\n...[truncated from {len(content)} chars]"

    def _summarize_subtask_messages(
        self,
        subtask_id: str,
        result: Optional[str],
    ) -> str:
        """Create brief summary of completed subtask.

        Args:
            subtask_id: The subtask ID.
            result: The result string.

        Returns:
            Summary line.
        """
        result_preview = result[:100] if result else "completed"
        return f"- Subtask {subtask_id}: {result_preview}"


class SnapshotManager:
    """Manages periodic snapshots for very long tasks.

    For tasks with many subtasks, this manager creates periodic snapshots
    of progress and allows cleaning old message history while preserving
    a summary of what was accomplished.

    Based on docs/task-planning-system.md lines 730-766.
    """

    def __init__(self, snapshot_interval: int = 10):
        """Initialize SnapshotManager.

        Args:
            snapshot_interval: Create snapshot every N completed subtasks.
        """
        self.snapshot_interval = snapshot_interval
        self.snapshots: List[Dict[str, Any]] = []
        self._last_snapshot_count = 0

    def maybe_create_snapshot(
        self,
        orchestrator: "TaskOrchestrator",
    ) -> bool:
        """Create snapshot if enough subtasks completed.

        Args:
            orchestrator: The TaskOrchestrator instance.

        Returns:
            True if a snapshot was created.
        """
        completed_count = len(orchestrator.completed_tasks)

        # Check if we've passed another interval
        if completed_count > 0 and completed_count >= self._last_snapshot_count + self.snapshot_interval:
            snapshot = {
                "timestamp": datetime.now().isoformat(),
                "completed_subtasks": list(orchestrator.completed_tasks),
                "results": {
                    tid: str(orchestrator.subtasks[tid].result)[:200]
                    for tid in orchestrator.completed_tasks
                    if orchestrator.subtasks.get(tid)
                },
                "failed_subtasks": list(orchestrator.failed_tasks),
            }
            self.snapshots.append(snapshot)
            self._last_snapshot_count = completed_count

            logger.info(
                f"[SnapshotManager] Created snapshot #{len(self.snapshots)} "
                f"with {completed_count} completed tasks"
            )
            return True

        return False

    def get_context_from_snapshots(self) -> str:
        """Get compressed context from all snapshots.

        Returns:
            Summary string of all snapshots, or empty if none.
        """
        if not self.snapshots:
            return ""

        lines = ["## Previous Progress (from snapshots)"]
        for i, snapshot in enumerate(self.snapshots, 1):
            completed = len(snapshot.get("completed_subtasks", []))
            failed = len(snapshot.get("failed_subtasks", []))
            lines.append(f"- Snapshot {i}: {completed} completed, {failed} failed")

            # Add key results if any
            results = snapshot.get("results", {})
            if results:
                for tid, result in list(results.items())[:3]:  # Show up to 3 results
                    lines.append(f"  - {tid}: {result[:50]}...")

        return "\n".join(lines)

    def should_reset_history(self) -> bool:
        """Check if message history should be reset after snapshot.

        Returns:
            True if a new snapshot was just created.
        """
        return len(self.snapshots) > 0 and self._last_snapshot_count > 0
