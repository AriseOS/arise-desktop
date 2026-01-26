"""
Quick Task Service

Manages autonomous task execution, status tracking, and result storage.
Uses EigentStyleBrowserAgent for Tool-calling based browser automation.

Features:
- Tool-calling architecture with Anthropic tool_use API
- Complete Toolkit system (NoteTaking, Search, Terminal, Human, Browser, Memory)
- Memory-guided planning with semantic search
- Real-time progress streaming via SSE/WebSocket
- Typed event system with 30+ action types
"""

from typing import Optional, Dict, Any, AsyncGenerator, List, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio
import uuid
import logging

from ..base_agent.workspace import (
    WorkingDirectoryManager,
    set_current_manager,
    get_current_manager,
)
from ..base_agent.events import (
    Action,
    ActionData,
    BaseActionData,
    SSEEmitter,
    # Task lifecycle
    TaskStateData,
    TaskCompletedData,
    TaskFailedData,
    TaskCancelledData,
    # Planning
    PlanGeneratedData,
    # Agent lifecycle
    ActivateAgentData,
    DeactivateAgentData,
    AgentThinkingData,
    # Step/toolkit events
    StepStartedData,
    StepCompletedData,
    ActivateToolkitData,
    DeactivateToolkitData,
    # Tool-specific
    TerminalData,
    BrowserActionData,
    # User interaction
    AskData,
    NoticeData,
    # Memory events
    MemoryResultData,
    # System events
    HeartbeatData,
    EndData,
    ErrorData,
)
from ..base_agent.core.task_router import TaskRouter, RoutingResult, get_router
from ..base_agent.core.agent_registry import (
    get_registry,
    register_default_agents,
    AgentType,
)

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ConversationEntry:
    """Single conversation entry in task history.

    Tracks multi-turn conversation context for LLM prompt injection.
    Based on Eigent's TaskLock.conversation_history pattern.
    """
    role: str  # 'user', 'assistant', 'task_result', 'tool_call', 'system'
    content: Union[str, Dict[str, Any]]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp,
        }

    def content_length(self) -> int:
        """Get character length of content."""
        if isinstance(self.content, str):
            return len(self.content)
        return len(str(self.content))


@dataclass
class TaskState:
    """Task state for EigentStyleBrowserAgent execution.

    Each task has an isolated working directory:
    ~/.ami/users/{user_id}/projects/{project_id}/tasks/{task_id}/
    """
    task_id: str
    task: str
    start_url: Optional[str]
    status: TaskStatus

    # User and project isolation
    user_id: str = "default"
    project_id: str = "default"

    # Execution state
    plan: list = field(default_factory=list)
    current_step: Optional[Dict] = None
    progress: float = 0.0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Tool-calling specific state
    tools_called: List[Dict] = field(default_factory=list)  # History of tool calls (legacy, simple format)
    toolkit_events: List[Dict] = field(default_factory=list)  # Detailed toolkit events for restoration
    thinking_logs: List[Dict] = field(default_factory=list)  # Agent thinking/reasoning logs
    notes_content: Optional[str] = None  # Notes created during execution
    loop_iteration: int = 0  # Current iteration in the agent loop

    # Conversation history for multi-turn context (Eigent TaskLock pattern)
    conversation_history: List[ConversationEntry] = field(default_factory=list)
    last_task_result: Optional[str] = None
    max_history_length: int = 100000  # 100KB max for context

    # Agent routing state (Eigent Migration)
    routed_agent: Optional[str] = None  # Selected agent type
    routing_confidence: float = 0.0  # Router confidence (0.0-1.0)
    routing_reasoning: Optional[str] = None  # Why this agent was selected

    # Internal state - created lazily to avoid dataclass issues
    _cancel_event: Optional[asyncio.Event] = field(default=None, repr=False)
    _progress_queue: Optional[asyncio.Queue] = field(default=None, repr=False)

    # Event queue for typed events (SSE streaming)
    _event_queue: Optional[asyncio.Queue] = field(default=None, repr=False)
    _sse_emitter: Optional[SSEEmitter] = field(default=None, repr=False)

    # Human interaction state
    _human_response_queue: Optional[asyncio.Queue] = field(default=None, repr=False)
    _pending_human_question: Optional[str] = field(default=None, repr=False)

    # Subtask confirmation state
    _subtask_confirmation_event: Optional[asyncio.Event] = field(default=None, repr=False)
    _confirmed_subtasks: Optional[List[Dict]] = field(default=None, repr=False)
    _subtasks_cancelled: bool = field(default=False, repr=False)

    # Working directory manager
    _dir_manager: Optional[WorkingDirectoryManager] = field(default=None, repr=False)

    def __post_init__(self):
        if self._cancel_event is None:
            self._cancel_event = asyncio.Event()
        if self._progress_queue is None:
            self._progress_queue = asyncio.Queue()
        if self._human_response_queue is None:
            self._human_response_queue = asyncio.Queue()
        if self._subtask_confirmation_event is None:
            self._subtask_confirmation_event = asyncio.Event()

        # Initialize event queue and SSE emitter
        if self._event_queue is None:
            self._event_queue = asyncio.Queue()
        if self._sse_emitter is None:
            self._sse_emitter = SSEEmitter(self._event_queue)
            self._sse_emitter.configure(task_id=self.task_id)

        # Initialize working directory manager
        if self._dir_manager is None:
            self._dir_manager = WorkingDirectoryManager(
                user_id=self.user_id,
                project_id=self.project_id,
                task_id=self.task_id,
            )

    @property
    def dir_manager(self) -> WorkingDirectoryManager:
        """Get the working directory manager."""
        return self._dir_manager

    @property
    def working_directory(self) -> str:
        """Get the main working directory path."""
        return str(self._dir_manager.workspace)

    @property
    def notes_directory(self) -> str:
        """Get the notes directory path."""
        return str(self._dir_manager.notes_dir)

    @property
    def browser_data_directory(self) -> str:
        """Get the browser data directory path."""
        return str(self._dir_manager.browser_data_dir)

    def get_output_path(self, filename: str) -> str:
        """Get path for output file."""
        return str(self._dir_manager.output_dir / filename)

    def write_output(self, filename: str, content: str) -> str:
        """Write file to output directory."""
        return str(self._dir_manager.write_file(f"output/{filename}", content))

    # ===== Event System Properties =====

    @property
    def emitter(self) -> SSEEmitter:
        """Get SSE emitter for this task."""
        return self._sse_emitter

    @property
    def event_queue(self) -> asyncio.Queue:
        """Get the event queue for SSE streaming."""
        return self._event_queue

    async def put_event(self, event: Union[ActionData, Dict]) -> None:
        """
        Put event into queue for SSE streaming.

        Also puts into legacy progress queue for backward compatibility.

        Args:
            event: ActionData instance or dict (for backward compatibility)
        """
        # Handle typed ActionData
        if isinstance(event, BaseActionData):
            await self._event_queue.put(event)
            # Also convert to dict for legacy queue
            legacy_dict = {"event": event.action.value if hasattr(event.action, 'value') else event.action}
            legacy_dict.update(event.model_dump(exclude={"action", "timestamp"}))
            await self._progress_queue.put(legacy_dict)
        else:
            # Handle legacy dict format
            await self._progress_queue.put(event)
            # Try to convert to typed event
            event_type = event.get("event", "notice")
            try:
                action = Action(event_type)
                typed_event = BaseActionData(action=action, task_id=self.task_id)
                await self._event_queue.put(typed_event)
            except (ValueError, Exception):
                pass

    async def get_event(self) -> ActionData:
        """Get next event from typed event queue."""
        return await self._event_queue.get()

    # ===== Subtask Confirmation Methods =====

    async def wait_for_subtask_confirmation(self, timeout: float = 30.0) -> bool:
        """
        Wait for subtask confirmation from frontend.

        Args:
            timeout: Maximum time to wait in seconds (default 30s)

        Returns:
            True if confirmed and should proceed, False if cancelled by user
        """
        try:
            # Clear the event and cancelled flag before waiting
            self._subtask_confirmation_event.clear()
            self._subtasks_cancelled = False
            logger.info(f"[Task {self.task_id}] Waiting for subtask confirmation (timeout={timeout}s)...")

            # Wait with timeout
            await asyncio.wait_for(
                self._subtask_confirmation_event.wait(),
                timeout=timeout
            )

            # Check if user cancelled (cancel_subtasks sets this flag before triggering event)
            if self._subtasks_cancelled:
                logger.info(f"[Task {self.task_id}] Subtask confirmation cancelled by user")
                return False

            logger.info(f"[Task {self.task_id}] Subtask confirmation received")
            return True
        except asyncio.TimeoutError:
            logger.info(f"[Task {self.task_id}] Subtask confirmation timeout, auto-confirming")
            return True  # Auto-confirm on timeout
        except asyncio.CancelledError:
            logger.info(f"[Task {self.task_id}] Subtask confirmation cancelled")
            return False

    def confirm_subtasks(self, subtasks: List[Dict]) -> None:
        """
        Confirm subtasks from frontend.

        Called by confirm-subtasks endpoint to unblock the agent.

        Args:
            subtasks: List of confirmed (possibly edited) subtasks
        """
        self._confirmed_subtasks = subtasks
        self._subtask_confirmation_event.set()
        logger.info(f"[Task {self.task_id}] Subtasks confirmed: {len(subtasks)} subtasks")

    def get_confirmed_subtasks(self) -> Optional[List[Dict]]:
        """Get the confirmed subtasks (may be edited by user)."""
        return self._confirmed_subtasks

    # ===== Conversation History Methods (Eigent TaskLock pattern) =====

    def add_conversation(
        self,
        role: str,
        content: Union[str, Dict[str, Any]],
    ) -> None:
        """
        Add a conversation entry to history.

        Based on Eigent's TaskLock.add_conversation pattern.
        Automatically trims history if it exceeds max_history_length.

        Args:
            role: One of 'user', 'assistant', 'task_result', 'tool_call', 'system'
            content: Message content (str or dict for structured data)
        """
        entry = ConversationEntry(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
        )
        self.conversation_history.append(entry)
        self._trim_history_if_needed()

        # Update last_task_result if this is a task result
        if role == 'task_result':
            if isinstance(content, dict):
                self.last_task_result = content.get('summary', str(content))
            else:
                self.last_task_result = str(content)

        logger.debug(f"Added conversation entry: {role} ({entry.content_length()} chars)")

    def _trim_history_if_needed(self) -> None:
        """
        Trim history if exceeds max length.

        Removes oldest entries (keeping at least 1) until under limit.
        Based on Eigent's check_conversation_history_length pattern.
        """
        total_length = self.get_history_length()

        while total_length > self.max_history_length and len(self.conversation_history) > 1:
            removed = self.conversation_history.pop(0)
            removed_length = removed.content_length()
            total_length -= removed_length
            logger.debug(f"Trimmed conversation entry: {removed.role} ({removed_length} chars)")

    def get_history_length(self) -> int:
        """
        Get total character length of conversation history.

        Returns:
            Total characters in all conversation content.
        """
        return sum(entry.content_length() for entry in self.conversation_history)

    def get_recent_context(
        self,
        max_entries: Optional[int] = None,
        include_tool_calls: bool = False,
    ) -> str:
        """
        Get recent conversation context as formatted string.

        Based on Eigent's TaskLock.get_recent_context pattern.
        Formats history for LLM prompt injection.

        Args:
            max_entries: Maximum number of entries to include (None = all)
            include_tool_calls: Whether to include tool_call entries

        Returns:
            Formatted context string for LLM prompt
        """
        if not self.conversation_history:
            return ""

        context_parts = ["=== Recent Conversation ==="]

        history = self.conversation_history
        if max_entries is not None:
            history = history[-max_entries:]

        for entry in history:
            # Skip tool calls unless requested
            if entry.role == 'tool_call' and not include_tool_calls:
                continue

            if entry.role == 'task_result' and isinstance(entry.content, dict):
                # Format structured task result
                content = entry.content
                parts = [f"Task Result:"]
                if content.get('task'):
                    parts.append(f"  Task: {content['task']}")
                if content.get('summary'):
                    parts.append(f"  Summary: {content['summary']}")
                if content.get('status'):
                    parts.append(f"  Status: {content['status']}")
                if content.get('files_created'):
                    files = content['files_created']
                    if isinstance(files, list):
                        files = ', '.join(files)
                    parts.append(f"  Files Created: {files}")
                context_parts.append('\n'.join(parts))
            elif entry.role == 'tool_call' and isinstance(entry.content, dict):
                # Format tool call
                tool_name = entry.content.get('name', 'unknown')
                tool_result = entry.content.get('result', '')
                if len(str(tool_result)) > 200:
                    tool_result = str(tool_result)[:200] + '...'
                context_parts.append(f"Tool [{tool_name}]: {tool_result}")
            else:
                # Format regular conversation
                role_display = entry.role.title()
                content = entry.content
                if isinstance(content, dict):
                    content = str(content)
                # Truncate very long content
                if len(content) > 1000:
                    content = content[:1000] + '...'
                context_parts.append(f"{role_display}: {content}")

        return "\n\n".join(context_parts)

    def clear_conversation_history(self) -> None:
        """Clear all conversation history."""
        self.conversation_history.clear()
        self.last_task_result = None
        logger.debug("Cleared conversation history")

    def get_conversation_summary(self) -> Dict[str, Any]:
        """
        Get summary of conversation history.

        Returns:
            Dict with history stats and summary.
        """
        return {
            'entry_count': len(self.conversation_history),
            'total_length': self.get_history_length(),
            'max_length': self.max_history_length,
            'usage_percent': (self.get_history_length() / self.max_history_length) * 100,
            'roles': {role: sum(1 for e in self.conversation_history if e.role == role)
                     for role in set(e.role for e in self.conversation_history)},
            'last_task_result': self.last_task_result,
        }


class QuickTaskService:
    """
    Quick Task Service

    Responsible for:
    - Task submission and execution
    - Status tracking
    - Result storage
    - Progress streaming
    - Memory-guided planning (query memory for similar workflow paths)
    """

    def __init__(self, cloud_client=None):
        """Initialize QuickTaskService.

        Args:
            cloud_client: CloudClient instance for memory API calls.
                         If None, memory query will be skipped.
        """
        self._tasks: Dict[str, TaskState] = {}
        self._llm_api_key: Optional[str] = None
        self._llm_model: Optional[str] = None
        self._llm_base_url: Optional[str] = None
        self._cloud_client = cloud_client
        self._user_id: Optional[str] = None

        # Initialize TaskRouter for agent selection (Eigent Migration)
        self._task_router = get_router()

        # Register default agents on first service initialization
        register_default_agents()

    def set_cloud_client(self, cloud_client):
        """Set CloudClient for memory API calls."""
        self._cloud_client = cloud_client

    def configure_llm(
        self,
        api_key: str,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        """Configure LLM credentials for the service.

        Args:
            api_key: User's Ami API key (ami_xxxxx format)
            model: LLM model name (optional)
            base_url: CRS proxy URL (e.g., https://api.ariseos.com/api)
            user_id: User ID for memory queries (optional)
        """
        self._llm_api_key = api_key
        if model:
            self._llm_model = model
        if base_url:
            self._llm_base_url = base_url
        if user_id:
            self._user_id = user_id

    async def submit_task(
        self,
        task: str,
        headless: bool = False,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> str:
        """
        Submit a task for execution.

        Each task gets an isolated working directory:
        ~/.ami/users/{user_id}/projects/{project_id}/tasks/{task_id}/

        Args:
            task: Task description in natural language
            headless: Whether to run browser in headless mode
            user_id: User identifier for directory isolation (default: service user_id or "default")
            project_id: Project identifier for grouping tasks (default: "default")

        Returns:
            task_id
        """
        task_id = str(uuid.uuid4())[:8]

        # Use service-level user_id if not provided
        effective_user_id = user_id or self._user_id or "default"
        effective_project_id = project_id or "default"

        state = TaskState(
            task_id=task_id,
            task=task,
            start_url=None,
            status=TaskStatus.PENDING,
            user_id=effective_user_id,
            project_id=effective_project_id,
        )
        self._tasks[task_id] = state

        # Set as current manager for toolkits
        set_current_manager(state.dir_manager)

        # Execute task asynchronously
        asyncio.create_task(
            self._execute_task(task_id, headless=headless)
        )

        logger.info(f"Task submitted: {task_id} (workspace: {state.working_directory})")
        return task_id

    async def continue_task(
        self,
        task_id: str,
        new_task: str,
        create_new_workspace: bool = False,
        headless: bool = False,
    ) -> str:
        """
        Continue a task with a new instruction, preserving conversation history.

        This enables multi-turn conversation patterns where context from
        previous task execution is carried forward.

        Args:
            task_id: ID of the existing task to continue from
            new_task: New task instruction
            create_new_workspace: If True, creates a new task with fresh workspace
                                  but preserves conversation history.
                                  If False, continues in the same workspace.
            headless: Whether to run browser in headless mode

        Returns:
            Task ID (same as input if continuing, new ID if create_new_workspace=True)

        Raises:
            ValueError: If task_id not found
        """
        old_state = self._tasks.get(task_id)
        if not old_state:
            raise ValueError(f"Task {task_id} not found")

        # Record the user's new task as a conversation entry
        old_state.add_conversation("user", new_task)

        if create_new_workspace:
            # Create new task with fresh workspace but preserve conversation history
            new_task_id = str(uuid.uuid4())[:8]

            new_state = TaskState(
                task_id=new_task_id,
                task=new_task,
                start_url=None,
                status=TaskStatus.PENDING,
                user_id=old_state.user_id,
                project_id=old_state.project_id,
                # Copy conversation history from old task
                conversation_history=list(old_state.conversation_history),
                last_task_result=old_state.last_task_result,
            )
            self._tasks[new_task_id] = new_state

            # Set as current manager
            set_current_manager(new_state.dir_manager)

            # Execute new task
            asyncio.create_task(
                self._execute_task(new_task_id, headless=headless)
            )

            logger.info(
                f"Task continued with new workspace: {task_id} -> {new_task_id} "
                f"(preserved {len(old_state.conversation_history)} conversation entries)"
            )
            return new_task_id

        else:
            # Continue in the same workspace
            old_state.task = new_task
            old_state.status = TaskStatus.PENDING
            old_state.error = None
            old_state.result = None
            old_state.loop_iteration = 0
            old_state.tools_called = []
            old_state.updated_at = datetime.now()

            # Reset events for new execution
            old_state._cancel_event = asyncio.Event()

            # Set as current manager
            set_current_manager(old_state.dir_manager)

            # Execute continued task
            asyncio.create_task(
                self._execute_task(task_id, headless=headless)
            )

            logger.info(
                f"Task {task_id} continued with new instruction "
                f"(preserved {len(old_state.conversation_history)} conversation entries)"
            )
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
            "error": state.error,
            "working_directory": state.working_directory,
            "user_id": state.user_id,
            "project_id": state.project_id,
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

        # Send typed cancel events
        await state.put_event(TaskCancelledData(
            task_id=task_id,
            reason="User cancelled",
        ))
        await state.put_event(EndData(
            task_id=task_id,
            status="cancelled",
            message="Task cancelled by user",
        ))

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

    async def provide_human_response(self, task_id: str, response: str) -> bool:
        """Provide a human response to a pending question.

        Args:
            task_id: The task ID
            response: The human's response text

        Returns:
            True if the response was delivered, False otherwise
        """
        state = self._tasks.get(task_id)
        if not state:
            logger.warning(f"Task {task_id} not found for human response")
            return False

        if not state._pending_human_question:
            logger.warning(f"No pending human question for task {task_id}")
            return False

        # Put the response in the queue
        await state._human_response_queue.put(response)
        state._pending_human_question = None
        logger.info(f"Human response delivered for task {task_id}: {response[:50]}...")
        return True

    async def _call_reasoner(self, task: str) -> Optional[Dict[str, Any]]:
        """Call Reasoner API to get workflow plan.

        This is the single source of truth for memory-based planning.
        Returns the full Reasoner result which can be used for:
        1. Frontend display (states/workflow summary)
        2. Agent execution (full workflow with intent_sequences)

        Args:
            task: Task description

        Returns:
            Reasoner result dict if successful, None otherwise
        """
        logger.info(f"_call_reasoner called: cloud_client={self._cloud_client is not None}, user_id={self._user_id}")
        if not self._cloud_client or not self._user_id or not self._llm_api_key:
            logger.info(f"Reasoner call skipped: cloud_client={self._cloud_client is not None}, user_id={self._user_id}")
            return None

        try:
            import aiohttp

            # Build API URL
            base_url = self._cloud_client.api_url.rstrip("/")
            if base_url.endswith("/api"):
                api_url = f"{base_url}/v1/reasoner/plan"
            else:
                api_url = f"{base_url}/api/v1/reasoner/plan"

            headers = {
                "Content-Type": "application/json",
                "X-Ami-Api-Key": self._llm_api_key,
            }

            payload = {
                "target": task,
                "user_id": self._user_id,
            }

            logger.info(f"Calling Reasoner API: {api_url}")

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("success"):
                            states = result.get("states", [])
                            actions = result.get("actions", [])
                            logger.info(f"Reasoner returned workflow: {len(states)} states, {len(actions)} actions")

                            # === DEBUG: Log raw Reasoner response ===
                            for i, state in enumerate(states):
                                state_id = state.get("id", "?") if isinstance(state, dict) else getattr(state, "id", "?")
                                state_desc = (state.get("description", "") if isinstance(state, dict) else getattr(state, "description", "")) or ""
                                logger.info(f"[Reasoner] State {i}: id={state_id}, desc={state_desc[:60]}")

                            for i, action in enumerate(actions):
                                action_desc = (action.get("description", "") if isinstance(action, dict) else getattr(action, "description", "")) or ""
                                action_source = (action.get("source", "") if isinstance(action, dict) else getattr(action, "source", "")) or ""
                                action_target = (action.get("target", "") if isinstance(action, dict) else getattr(action, "target", "")) or ""
                                logger.info(f"[Reasoner] Action {i}: source={action_source}, target={action_target}, desc={action_desc[:60]}")
                            # === END DEBUG ===

                            return result
                        else:
                            logger.info(f"Reasoner returned no workflow: {result.get('message', 'no match')}")
                            return None
                    else:
                        error_text = await resp.text()
                        logger.warning(f"Reasoner API returned {resp.status}: {error_text[:200]}")
                        return None

        except Exception as e:
            logger.warning(f"Reasoner API call failed: {e}")
            return None

    async def _query_memory(self, task: str) -> List[Dict[str, Any]]:
        """Query memory for similar workflow paths.

        DEPRECATED: Use _call_reasoner instead for full workflow retrieval.
        This method is kept for backward compatibility.

        Args:
            task: Task description to query

        Returns:
            List of memory paths, empty if no results or error
        """
        logger.info(f"_query_memory called: cloud_client={self._cloud_client is not None}, user_id={self._user_id}")
        if not self._cloud_client or not self._user_id:
            logger.info(f"Memory query skipped: cloud_client={self._cloud_client is not None}, user_id={self._user_id}")
            return []

        try:
            logger.info(f"Querying memory for task: {task[:50]}...")
            result = await self._cloud_client.query_memory(
                user_id=self._user_id,
                query=task,
                top_k=3,
                min_score=0.3  # Lower threshold to get more potential matches
            )

            if result.get("success") and result.get("paths"):
                paths = result["paths"]
                logger.info(f"Memory query returned {len(paths)} paths")
                for i, path in enumerate(paths):
                    logger.info(f"  Path {i+1}: score={path.get('score', 0):.3f}, "
                              f"steps={path.get('path_length', 0)}, "
                              f"desc={path.get('description', '')[:50]}")
                return paths
            else:
                logger.info("Memory query returned no paths")
                return []

        except Exception as e:
            logger.warning(f"Memory query failed: {e}")
            return []

    async def _execute_task(
        self,
        task_id: str,
        headless: bool = False,
    ):
        """Execute a task using EigentStyleBrowserAgent (Tool-calling architecture)."""
        logger.info(f"[Task {task_id}] _execute_task started with EigentStyleBrowserAgent")
        logger.info(f"[Task {task_id}] cloud_client={self._cloud_client is not None}, user_id={self._user_id}")

        state = self._tasks[task_id]
        state.status = TaskStatus.RUNNING
        state.started_at = datetime.now()
        state.updated_at = state.started_at

        # Record user's task as first conversation entry (for restoration)
        state.add_conversation("user", state.task)

        # Set current working directory manager for this task
        set_current_manager(state.dir_manager)
        logger.info(f"[Task {task_id}] Working directory: {state.working_directory}")

        # Send task started event (typed + legacy)
        await state.put_event(TaskStateData(
            task_id=task_id,
            status="running",
            task=state.task,
            working_directory=state.working_directory,
            user_id=state.user_id,
            project_id=state.project_id,
        ))

        try:
            # Memory query is now handled inside Agent.execute() via MemoryToolkit
            # No longer call _call_reasoner() here - Agent will query Memory itself
            logger.info(f"[Task {task_id}] Memory query will be handled by Agent internally")

            # ==================== Task Routing (Eigent Migration) ====================
            # Use TaskRouter to determine the best agent for this task
            routing_result = self._task_router.route(state.task, context={
                "user_id": state.user_id,
            })
            logger.info(
                f"[Task {task_id}] TaskRouter: agent={routing_result.agent_type}, "
                f"confidence={routing_result.confidence:.2f}, reasoning={routing_result.reasoning}"
            )

            # Store routing info in state for frontend display
            state.routed_agent = routing_result.agent_type
            state.routing_confidence = routing_result.confidence
            state.routing_reasoning = routing_result.reasoning

            # Emit routing event for frontend
            await state.put_event(ActivateAgentData(
                task_id=task_id,
                agent_name=routing_result.agent_type,
                message=f"Selected {routing_result.agent_type} (confidence: {routing_result.confidence:.0%}): {routing_result.reasoning}",
            ))

            # ==================== Agent Selection ====================
            from ..base_agent.core.schemas import AgentContext, AgentInput

            # Get agent class from registry based on routing result
            registry = get_registry()
            agent_class = registry.get_class(routing_result.agent_type)

            if agent_class is None:
                # Fallback to EigentStyleBrowserAgent if agent not found
                logger.warning(
                    f"[Task {task_id}] Agent '{routing_result.agent_type}' not found in registry, "
                    f"falling back to browser_agent"
                )
                from ..base_agent.agents.eigent_style_browser_agent import EigentStyleBrowserAgent
                agent_class = EigentStyleBrowserAgent

            # Create agent instance from routed agent class
            agent = agent_class()
            agent_name = routing_result.agent_type

            # Set up progress callback to forward events to WebSocket
            async def on_agent_progress(event: str, data: dict):
                """Forward agent progress events using typed event system."""
                state.updated_at = datetime.now()

                if event == "agent_started":
                    await state.put_event(ActivateAgentData(
                        task_id=task_id,
                        agent_name=agent_name,
                        message=f"Starting task: {data.get('task', '')[:50]}",
                    ))

                elif event == "loop_iteration":
                    state.loop_iteration = data.get("step", 0)
                    tools_called = data.get("tools_called", [])
                    state.tools_called.extend([
                        {"name": t, "iteration": state.loop_iteration}
                        for t in tools_called
                    ])
                    await state.put_event(StepStartedData(
                        task_id=task_id,
                        step_index=state.loop_iteration,
                        step_name=f"Iteration {state.loop_iteration}",
                        step_description=f"Tools: {', '.join(tools_called)}" if tools_called else None,
                    ))

                elif event == "tool_started":
                    tool_name = data.get("tool", "unknown")
                    tool_input = data.get("input", {})
                    input_preview = str(tool_input)[:200] if tool_input else None
                    toolkit_name = tool_name.split(".")[0] if "." in tool_name else tool_name
                    method_name = tool_name.split(".")[-1] if "." in tool_name else tool_name
                    timestamp = datetime.now().isoformat()

                    # Save to state for persistence
                    state.toolkit_events.append({
                        "toolkit_name": toolkit_name,
                        "method_name": method_name,
                        "status": "running",
                        "input_preview": input_preview,
                        "output_preview": None,
                        "timestamp": timestamp,
                        "agent_name": agent_name,
                    })

                    await state.put_event(ActivateToolkitData(
                        task_id=task_id,
                        toolkit_name=toolkit_name,
                        method_name=method_name,
                        input_preview=input_preview,
                        agent_name=agent_name,
                    ))

                elif event == "tool_completed":
                    tool_name = data.get("tool", "unknown")
                    result = str(data.get("result", ""))
                    result_preview = result[:200]
                    toolkit_name = tool_name.split(".")[0] if "." in tool_name else tool_name
                    method_name = tool_name.split(".")[-1] if "." in tool_name else tool_name

                    # Update the last running event with same toolkit/method
                    for evt in reversed(state.toolkit_events):
                        if evt["toolkit_name"] == toolkit_name and evt["method_name"] == method_name and evt["status"] == "running":
                            evt["status"] = "completed"
                            evt["output_preview"] = result_preview
                            break

                    await state.put_event(DeactivateToolkitData(
                        task_id=task_id,
                        toolkit_name=toolkit_name,
                        method_name=method_name,
                        output_preview=result_preview,
                        success=True,
                        agent_name=agent_name,
                    ))

                    # For terminal tools, also emit a specific terminal event
                    if tool_name in ("shell_exec", "shell_exec_async", "terminal"):
                        tool_input = data.get("input", {})
                        command = tool_input.get("command", "")
                        # Try to extract exit code from output
                        exit_code = None
                        if "[Exit code:" in result:
                            try:
                                exit_code = int(result.split("[Exit code:")[1].split("]")[0].strip())
                            except (ValueError, IndexError):
                                pass
                        # Truncate output with indicator if too long
                        output_display = result
                        if len(result) > 2000:
                            output_display = result[:2000] + "\n... [output truncated]"
                        await state.put_event(TerminalData(
                            task_id=task_id,
                            command=command,
                            output=output_display,
                            exit_code=exit_code,
                            working_directory=state.working_directory,
                        ))

                elif event == "tool_failed":
                    tool_name = data.get("tool", "unknown")
                    error = data.get("error", "unknown")
                    toolkit_name = tool_name.split(".")[0] if "." in tool_name else tool_name
                    method_name = tool_name.split(".")[-1] if "." in tool_name else tool_name

                    # Update the last running event with same toolkit/method
                    for evt in reversed(state.toolkit_events):
                        if evt["toolkit_name"] == toolkit_name and evt["method_name"] == method_name and evt["status"] == "running":
                            evt["status"] = "failed"
                            evt["output_preview"] = f"Error: {error}"
                            break

                    await state.put_event(DeactivateToolkitData(
                        task_id=task_id,
                        toolkit_name=toolkit_name,
                        method_name=method_name,
                        output_preview=f"Error: {error}",
                        success=False,
                        agent_name=agent_name,
                    ))

                elif event == "tool_executed":
                    # Legacy event - convert to deactivate_toolkit
                    tool_name = data.get("tool_name", "unknown")
                    await state.put_event(DeactivateToolkitData(
                        task_id=task_id,
                        toolkit_name=tool_name,
                        method_name=tool_name,
                        output_preview=data.get("result_preview", "")[:200],
                        success=not data.get("error", False),
                    ))

                elif event == "browser_action":
                    await state.put_event(BrowserActionData(
                        task_id=task_id,
                        action_type=data.get("action_type", "unknown"),
                        target=data.get("target"),
                        success=data.get("success", True),
                        page_url=data.get("page_url"),
                        page_title=data.get("page_title"),
                    ))

                elif event == "terminal":
                    output = data.get("output", "")
                    if len(output) > 2000:
                        output = output[:2000] + "\n... [output truncated]"
                    await state.put_event(TerminalData(
                        task_id=task_id,
                        command=data.get("command", ""),
                        output=output,
                        exit_code=data.get("exit_code"),
                        working_directory=data.get("working_directory"),
                    ))

                elif event == "llm_reasoning":
                    reasoning_text = data.get("reasoning", "")
                    step = data.get("step", state.loop_iteration)
                    timestamp = datetime.now().isoformat()
                    logger.info(f"[Task {task_id}] on_agent_progress received llm_reasoning event")
                    logger.info(f"[Task {task_id}] Emitting agent_thinking event: {reasoning_text[:100]}...")

                    # Save to state for persistence
                    state.thinking_logs.append({
                        "content": reasoning_text[:500],  # Truncate for storage
                        "step": step,
                        "agent_name": agent_name,
                        "timestamp": timestamp,
                    })

                    thinking_event = AgentThinkingData(
                        task_id=task_id,
                        agent_name=agent_name,
                        thinking=reasoning_text,
                        step=step,
                    )
                    logger.info(f"[Task {task_id}] AgentThinkingData created: action={thinking_event.action}")
                    await state.put_event(thinking_event)
                    logger.info(f"[Task {task_id}] agent_thinking event put to queue")

                elif event == "agent_completed":
                    state.progress = 1.0
                    await state.put_event(DeactivateAgentData(
                        task_id=task_id,
                        agent_name=agent_name,
                        message=data.get("response", "")[:200],
                    ))

                elif event == "agent_error":
                    await state.put_event(ErrorData(
                        task_id=task_id,
                        error=data.get("error", "Unknown error"),
                        recoverable=True,
                        details={"step": data.get("step")},
                    ))

                # Reasoner-specific events - forward to legacy queue for now
                elif event in ("reasoner_query_started", "reasoner_workflow_started",
                               "reasoner_navigate", "reasoner_intent_executed",
                               "reasoner_intent_failed", "reasoner_workflow_completed",
                               "reasoner_fallback"):
                    # Forward to legacy queue
                    await state._progress_queue.put({"event": event, **data})

            agent.set_progress_callback(on_agent_progress)

            # Set up human interaction callbacks
            async def on_human_ask(question: str, context: Optional[str] = None) -> str:
                """Handle ask_human tool calls from the agent."""
                logger.info(f"[Task {task_id}] Agent asking human: {question[:100]}...")

                # Store the pending question
                state._pending_human_question = question

                # Send typed ask event
                await state.put_event(AskData(
                    task_id=task_id,
                    question=question,
                    context=context,
                    timeout_seconds=300,
                ))

                # Wait for human response (timeout after 5 minutes)
                try:
                    response = await asyncio.wait_for(
                        state._human_response_queue.get(),
                        timeout=300.0
                    )
                    logger.info(f"[Task {task_id}] Human responded: {response[:50]}...")
                    return response
                except asyncio.TimeoutError:
                    logger.warning(f"[Task {task_id}] Human response timeout")
                    state._pending_human_question = None
                    return "[No response from human - timeout after 5 minutes]"

            async def on_human_message(title: str, description: str) -> None:
                """Handle send_message tool calls from the agent."""
                logger.info(f"[Task {task_id}] Agent sending message: {title}")

                # Send typed notice event
                await state.put_event(NoticeData(
                    task_id=task_id,
                    level="info",
                    title=title,
                    message=description,
                ))

            agent.set_human_callbacks(
                ask_callback=on_human_ask,
                message_callback=on_human_message
            )

            # Set task state for toolkit event emission via @listen_toolkit decorators
            agent.set_task_state(state)

            # Configure memory toolkit (for MemoryToolkit to work within Agent loop)
            if self._cloud_client and self._llm_api_key:
                agent.set_memory_config(
                    memory_api_base_url=self._cloud_client.api_url,
                    ami_api_key=self._llm_api_key,
                    user_id=self._user_id,
                )

            # Create agent context with LLM configuration
            context = AgentContext(
                workflow_id="quick_task",
                step_id=task_id,
                user_id=state.user_id,
                variables={
                    "llm_api_key": self._llm_api_key,
                    "llm_model": self._llm_model,
                    "llm_base_url": self._llm_base_url,
                },
            )

            # Initialize agent
            init_success = await agent.initialize(context)
            if not init_success:
                raise Exception(f"Failed to initialize {agent_name}")

            # Build conversation context for multi-turn task continuation
            conversation_context = ""
            if state.conversation_history:
                from .context_builder import build_conversation_context
                conversation_context = build_conversation_context(
                    state,
                    max_entries=15,  # Limit context to last 15 entries
                    skip_files=True,  # Don't include file listings in context
                )
                logger.info(f"[Task {task_id}] Including conversation context ({len(conversation_context)} chars)")

            # Prepare input - Memory query is handled inside Agent via MemoryToolkit
            input_data = AgentInput(
                data={
                    "task": state.task,
                    "task_id": task_id,  # For notes directory isolation
                    "headless": headless,
                    # Working directory info for toolkits
                    "working_directory": state.working_directory,
                    "notes_directory": state.notes_directory,
                    "browser_data_directory": state.browser_data_directory,
                    "user_id": state.user_id,
                    "project_id": state.project_id,
                    # Conversation context for multi-turn tasks
                    "conversation_context": conversation_context,
                }
            )

            # Execute
            result = await agent.execute(input_data, context)

            # Extract notes content from result
            notes_content = None
            if result.data and result.data.get("notes"):
                notes_content = result.data.get("notes")
                state.notes_content = notes_content

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

            # Record task result in conversation history for multi-turn context
            task_result_content = {
                "task": state.task,
                "summary": result.message or "",
                "status": "completed" if result.success else "failed",
                "working_directory": state.working_directory,
            }
            if notes_content:
                task_result_content["notes_preview"] = notes_content[:500] if len(notes_content) > 500 else notes_content
            if state.tools_called:
                task_result_content["tools_used"] = list(set(t.get("name", "") for t in state.tools_called[:20]))
            state.add_conversation("task_result", task_result_content)
            logger.info(f"[Task {task_id}] Recorded task result to conversation history")

            # Push completion event with notes (typed events)
            duration = (state.completed_at - state.started_at).total_seconds() if state.started_at else 0
            if result.success:
                await state.put_event(TaskCompletedData(
                    task_id=task_id,
                    output=result.data.get("result") if result.data else None,
                    notes=notes_content,
                    tools_called=state.tools_called,
                    loop_iterations=state.loop_iteration,
                    duration_seconds=duration,
                ))
                # Also send end event
                await state.put_event(EndData(
                    task_id=task_id,
                    status="completed",
                    message="Task completed successfully",
                    result=result.data,
                ))
            else:
                await state.put_event(TaskFailedData(
                    task_id=task_id,
                    error=result.message,
                    notes=notes_content,
                    tools_called=state.tools_called,
                ))
                await state.put_event(EndData(
                    task_id=task_id,
                    status="failed",
                    message=result.message,
                ))

        except Exception as e:
            logger.exception(f"Task {task_id} failed: {e}")
            state.status = TaskStatus.FAILED
            state.error = str(e)
            state.completed_at = datetime.now()
            state.updated_at = state.completed_at

            await state.put_event(TaskFailedData(
                task_id=task_id,
                error=str(e),
                tools_called=state.tools_called,
            ))
            await state.put_event(EndData(
                task_id=task_id,
                status="failed",
                message=str(e),
            ))

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
