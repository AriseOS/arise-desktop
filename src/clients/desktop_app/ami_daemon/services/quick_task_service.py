"""
Quick Task Service

Manages autonomous task execution, status tracking, and result storage.
Uses EigentBrowserAgent for LLM-guided browser automation.
"""

from typing import Optional, Dict, Any, AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio
import uuid
import logging

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskState:
    """Task state"""
    task_id: str
    task: str
    start_url: Optional[str]
    status: TaskStatus
    plan: list = field(default_factory=list)
    current_step: Optional[Dict] = None
    progress: float = 0.0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Internal state - created lazily to avoid dataclass issues
    _cancel_event: Optional[asyncio.Event] = field(default=None, repr=False)
    _progress_queue: Optional[asyncio.Queue] = field(default=None, repr=False)

    def __post_init__(self):
        if self._cancel_event is None:
            self._cancel_event = asyncio.Event()
        if self._progress_queue is None:
            self._progress_queue = asyncio.Queue()


class QuickTaskService:
    """
    Quick Task Service

    Responsible for:
    - Task submission and execution
    - Status tracking
    - Result storage
    - Progress streaming
    """

    def __init__(self):
        self._tasks: Dict[str, TaskState] = {}
        self._llm_api_key: Optional[str] = None
        self._llm_model: Optional[str] = None
        self._llm_base_url: Optional[str] = None

    def configure_llm(
        self,
        api_key: str,
        model: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        """Configure LLM credentials for the service.

        Args:
            api_key: User's Ami API key (ami_xxxxx format)
            model: LLM model name (optional)
            base_url: CRS proxy URL (e.g., https://api.ariseos.com/api)
        """
        self._llm_api_key = api_key
        if model:
            self._llm_model = model
        if base_url:
            self._llm_base_url = base_url

    async def submit_task(
        self,
        task: str,
        start_url: Optional[str] = None,
        max_steps: int = 15,
        headless: bool = False,
    ) -> str:
        """
        Submit a task for execution.

        Args:
            task: Task description in natural language
            start_url: Starting URL for the browser
            max_steps: Maximum number of steps the agent can take
            headless: Whether to run browser in headless mode

        Returns:
            task_id
        """
        task_id = str(uuid.uuid4())[:8]

        state = TaskState(
            task_id=task_id,
            task=task,
            start_url=start_url,
            status=TaskStatus.PENDING
        )
        self._tasks[task_id] = state

        # Execute task asynchronously
        asyncio.create_task(
            self._execute_task(task_id, max_steps=max_steps, headless=headless)
        )

        logger.info(f"Task submitted: {task_id}")
        return task_id

    async def get_status(self, task_id: str) -> Optional[Dict]:
        """Get task status."""
        state = self._tasks.get(task_id)
        if not state:
            return None

        return {
            "task_id": state.task_id,
            "status": state.status.value,
            "plan": state.plan,
            "current_step": state.current_step,
            "progress": state.progress,
            "error": state.error
        }

    async def get_result(self, task_id: str) -> Optional[Dict]:
        """Get task result."""
        state = self._tasks.get(task_id)
        if not state:
            return None

        # Calculate duration
        duration = 0.0
        if state.started_at:
            end_time = state.completed_at or datetime.now()
            duration = (end_time - state.started_at).total_seconds()

        if state.result:
            return {
                "task_id": task_id,
                "success": state.result.get("success", False),
                "output": state.result.get("data", {}).get("result"),
                "plan": state.plan,
                "steps_executed": state.result.get("data", {}).get("steps_taken", 0),
                "total_steps": len(state.plan) if state.plan else 0,
                "duration_seconds": duration,
                "error": state.error,
                "action_history": state.result.get("data", {}).get("action_history", []),
            }
        else:
            return {
                "task_id": task_id,
                "success": False,
                "output": None,
                "plan": state.plan,
                "steps_executed": 0,
                "total_steps": len(state.plan) if state.plan else 0,
                "duration_seconds": duration,
                "error": state.error or "Task not completed"
            }

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a task."""
        state = self._tasks.get(task_id)
        if not state:
            return False

        if state.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            return False

        state._cancel_event.set()
        state.status = TaskStatus.CANCELLED
        state.updated_at = datetime.now()

        await state._progress_queue.put({
            "event": "task_cancelled"
        })

        logger.info(f"Task cancelled: {task_id}")
        return True

    async def subscribe_progress(self, task_id: str) -> AsyncGenerator[Dict, None]:
        """Subscribe to task progress."""
        state = self._tasks.get(task_id)
        if not state:
            yield {"event": "error", "message": "Task not found"}
            return

        while True:
            try:
                # Wait for progress update, timeout 30 seconds
                event = await asyncio.wait_for(
                    state._progress_queue.get(),
                    timeout=30.0
                )
                yield event

                # If terminal event, exit
                if event.get("event") in ["task_completed", "task_failed", "task_cancelled"]:
                    break

            except asyncio.TimeoutError:
                # Send heartbeat
                yield {"event": "heartbeat"}

    async def _execute_task(
        self,
        task_id: str,
        max_steps: int = 15,
        headless: bool = False,
    ):
        """Execute a task using EigentBrowserAgent."""
        state = self._tasks[task_id]
        state.status = TaskStatus.RUNNING
        state.started_at = datetime.now()
        state.updated_at = state.started_at

        # Send task started event
        await state._progress_queue.put({
            "event": "task_started",
            "task_id": task_id,
            "task": state.task,
        })

        try:
            # Import EigentBrowserAgent
            from ..base_agent.agents.eigent_browser_agent import EigentBrowserAgent
            from ..base_agent.core.schemas import AgentContext, AgentInput

            # Create agent
            agent = EigentBrowserAgent()

            # Set up progress callback to forward events to WebSocket
            async def on_agent_progress(event: str, data: dict):
                """Forward agent progress events to the WebSocket queue."""
                if event == "plan_generated":
                    state.plan = data.get("plan", [])
                    state.updated_at = datetime.now()
                    await state._progress_queue.put({
                        "event": "plan_generated",
                        "plan": data.get("plan", []),
                        "first_action": data.get("first_action"),
                    })
                elif event == "step_started":
                    state.current_step = data.get("action")
                    state.progress = data.get("step", 0) / max(data.get("max_steps", 1), 1)
                    state.updated_at = datetime.now()
                    await state._progress_queue.put({
                        "event": "step_started",
                        "step": data.get("step"),
                        "max_steps": data.get("max_steps"),
                        "action": data.get("action"),
                        "action_type": data.get("action_type"),
                    })
                elif event == "step_completed":
                    state.progress = data.get("step", 0) / max(data.get("max_steps", 1), 1)
                    state.updated_at = datetime.now()
                    await state._progress_queue.put({
                        "event": "step_completed",
                        "step": data.get("step"),
                        "max_steps": data.get("max_steps"),
                        "action": data.get("action"),
                        "result": data.get("result"),
                        "action_history": data.get("action_history", []),
                    })
                elif event == "step_failed":
                    state.updated_at = datetime.now()
                    await state._progress_queue.put({
                        "event": "step_failed",
                        "step": data.get("step"),
                        "max_steps": data.get("max_steps"),
                        "action": data.get("action"),
                        "error": data.get("error"),
                        "action_history": data.get("action_history", []),
                    })

            agent.set_progress_callback(on_agent_progress)

            # Create context with LLM config (including CRS proxy URL)
            class MockProvider:
                def __init__(self, api_key, model, base_url):
                    self.api_key = api_key
                    self.model_name = model
                    self.base_url = base_url

            class MockAgentInstance:
                def __init__(self, provider):
                    self.provider = provider

            provider = MockProvider(
                self._llm_api_key,
                self._llm_model,
                self._llm_base_url
            )
            agent_instance = MockAgentInstance(provider)

            context = AgentContext(
                workflow_id="quick_task",
                step_id=task_id,
                agent_instance=agent_instance,
            )

            # Initialize agent
            init_success = await agent.initialize(context)
            if not init_success:
                raise Exception("Failed to initialize EigentBrowserAgent")

            # Prepare input
            input_data = AgentInput(
                data={
                    "task": state.task,
                    "start_url": state.start_url or "https://www.google.com",
                    "max_steps": max_steps,
                    "headless": headless,
                }
            )

            # Execute
            result = await agent.execute(input_data, context)

            # Cleanup
            await agent.cleanup(context)

            # Save result
            state.result = {
                "success": result.success,
                "message": result.message,
                "data": result.data,
            }
            state.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
            state.error = result.message if not result.success else None
            state.completed_at = datetime.now()
            state.updated_at = state.completed_at

            # Push completion event
            if result.success:
                await state._progress_queue.put({
                    "event": "task_completed",
                    "output": result.data.get("result") if result.data else None,
                    "action_history": result.data.get("action_history", []) if result.data else [],
                })
            else:
                await state._progress_queue.put({
                    "event": "task_failed",
                    "error": result.message
                })

        except Exception as e:
            logger.exception(f"Task {task_id} failed: {e}")
            state.status = TaskStatus.FAILED
            state.error = str(e)
            state.completed_at = datetime.now()
            state.updated_at = state.completed_at

            await state._progress_queue.put({
                "event": "task_failed",
                "error": str(e)
            })

    def cleanup_old_tasks(self, max_age_seconds: int = 3600):
        """Clean up old completed/failed tasks."""
        now = datetime.now()
        to_remove = []

        for task_id, state in self._tasks.items():
            if state.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                age = (now - state.updated_at).total_seconds()
                if age > max_age_seconds:
                    to_remove.append(task_id)

        for task_id in to_remove:
            del self._tasks[task_id]
            logger.debug(f"Cleaned up old task: {task_id}")

        return len(to_remove)
