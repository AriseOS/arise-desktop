"""
Quick Task Service

Manages autonomous task execution, status tracking, and result storage.
Uses EigentStyleBrowserAgent for Tool-calling based browser automation.

Features:
- Tool-calling architecture with Anthropic tool_use API
- Complete Toolkit system (NoteTaking, Search, Terminal, Human, Browser, Memory)
- Memory-guided planning with semantic search
- Real-time progress streaming via SSE
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
    TaskFailedData,
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
    WaitConfirmData,
    ConfirmedData,
    AgentReportData,
    # Memory events
    MemoryResultData,
    # Task decomposition
    TaskDecomposedData,
    SubtaskStateData,
    TaskReplannedData,
    StreamingDecomposeData,
    # System events
    HeartbeatData,
    EndData,
    ErrorData,
    # Workforce events
    WorkforceStartedData,
    WorkforceCompletedData,
    WorkforceStoppedData,
    WorkerAssignedData,
    WorkerStartedData,
    WorkerCompletedData,
    WorkerFailedData,
    DynamicTasksAddedData,
)
from ..base_agent.core.task_router import TaskRouter, RoutingResult, get_router
from ..base_agent.core.agent_registry import (
    get_registry,
    register_default_agents,
    AgentType,
)
from ..base_agent.core.cost_calculator import DEFAULT_MODEL
from ..base_agent.core.orchestrator_agent import (
    create_orchestrator_agent,
    run_orchestrator,
    DecomposeTaskTool,
)

logger = logging.getLogger(__name__)


# Tool name prefix to Toolkit name mapping
# Used to format toolkit_name consistently with @listen_toolkit decorator
TOOL_PREFIX_TO_TOOLKIT = {
    "browser": "Browser Toolkit",
    "shell": "Terminal Toolkit",
    "terminal": "Terminal Toolkit",
    "search": "Search Toolkit",
    "note": "Note Taking Toolkit",
    "human": "Human Toolkit",
    "memory": "Memory Toolkit",
    "task": "Task Planning Toolkit",
    "calendar": "Calendar Toolkit",
    # Internal task management tools (ListenBrowserAgent)
    "get": "Task Planning Toolkit",      # get_current_plan
    "complete": "Task Planning Toolkit", # complete_subtask
    "report": "Task Planning Toolkit",   # report_subtask_failure
    "replan": "Task Planning Toolkit",   # replan_task
}


def get_toolkit_name(tool_name: str) -> str:
    """Get formatted toolkit name from tool name.

    Matches the format used by @listen_toolkit decorator.

    Args:
        tool_name: Raw tool name (e.g., "browser_click", "shell_exec")

    Returns:
        Formatted toolkit name (e.g., "Browser Toolkit", "Terminal Toolkit")
    """
    # Extract prefix (first word before underscore)
    prefix = tool_name.split("_")[0].lower() if "_" in tool_name else tool_name.lower()

    # Look up in mapping
    if prefix in TOOL_PREFIX_TO_TOOLKIT:
        return TOOL_PREFIX_TO_TOOLKIT[prefix]

    # Fallback: Title case the prefix
    return prefix.title() + " Toolkit"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"  # Eigent pattern: waiting for user input after simple answer
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

    # Event queue for typed events (SSE streaming)
    _event_queue: Optional[asyncio.Queue] = field(default=None, repr=False)
    _sse_emitter: Optional[SSEEmitter] = field(default=None, repr=False)

    # Human interaction state
    _human_response_queue: Optional[asyncio.Queue] = field(default=None, repr=False)
    _pending_human_question: Optional[str] = field(default=None, repr=False)

    # User message queue for multi-turn conversation (Eigent pattern)
    _user_message_queue: Optional[asyncio.Queue] = field(default=None, repr=False)

    # Working directory manager
    _dir_manager: Optional[WorkingDirectoryManager] = field(default=None, repr=False)

    # Task decomposition state
    subtasks: List[Dict] = field(default_factory=list)  # Decomposed subtasks
    summary_task: Optional[str] = None  # Summary of the main task

    def __post_init__(self):
        if self._cancel_event is None:
            self._cancel_event = asyncio.Event()
        if self._human_response_queue is None:
            self._human_response_queue = asyncio.Queue()
        if self._user_message_queue is None:
            self._user_message_queue = asyncio.Queue()

        # Initialize event queue and SSE emitter
        # BUG-8 fix: Use bounded queue to prevent memory leak
        if self._event_queue is None:
            self._event_queue = asyncio.Queue(maxsize=1000)
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

        Args:
            event: ActionData instance or dict (for backward compatibility)
        """
        # BUG-8 fix: Handle full queue gracefully
        async def safe_put(evt):
            try:
                # Use put_nowait to avoid blocking if queue is full
                self._event_queue.put_nowait(evt)
            except asyncio.QueueFull:
                # Log and drop old events if queue is full
                logger.warning(f"[Task {self.task_id}] Event queue full, dropping oldest event")
                try:
                    self._event_queue.get_nowait()  # Remove oldest
                    self._event_queue.put_nowait(evt)  # Add new
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass  # Best effort

        # Handle typed ActionData
        if isinstance(event, BaseActionData):
            await safe_put(event)
        else:
            # Handle legacy dict format - convert to typed event
            event_type = event.get("event", "notice")
            typed_event = None

            try:
                # Map event types to their corresponding ActionData classes
                if event_type == "task_decomposed":
                    typed_event = TaskDecomposedData(
                        task_id=self.task_id,
                        subtasks=event.get("subtasks", []),
                        summary_task=event.get("summary_task"),
                        original_task_id=event.get("original_task_id"),
                        total_subtasks=event.get("total_subtasks", len(event.get("subtasks", []))),
                    )
                elif event_type == "subtask_state":
                    typed_event = SubtaskStateData(
                        task_id=self.task_id,
                        subtask_id=event.get("subtask_id", ""),
                        state=event.get("state", "OPEN"),
                        result=event.get("result"),
                        failure_count=event.get("failure_count", 0),
                    )
                elif event_type == "task_replanned":
                    typed_event = TaskReplannedData(
                        task_id=self.task_id,
                        subtasks=event.get("subtasks", []),
                        original_task_id=event.get("original_task_id"),
                        reason=event.get("reason"),
                    )
                elif event_type == "streaming_decompose":
                    # DS-8: Only use 'text' field, 'content' doesn't exist in StreamingDecomposeData
                    typed_event = StreamingDecomposeData(
                        task_id=self.task_id,
                        text=event.get("text") or event.get("content", ""),
                    )
                else:
                    # Generic fallback - try basic ActionData
                    action = Action(event_type)
                    typed_event = BaseActionData(action=action, task_id=self.task_id)

                if typed_event:
                    await safe_put(typed_event)

            except (ValueError, Exception) as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to convert event '{event_type}' to typed: {e}")

    async def get_event(self) -> ActionData:
        """Get next event from typed event queue."""
        return await self._event_queue.get()

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

    async def put_user_message(self, message: str) -> None:
        """
        Put a user message into the queue for multi-turn conversation.

        Called when frontend sends a new message via the message API.
        The multi-turn loop will receive this message.
        """
        if self._user_message_queue is not None:
            await self._user_message_queue.put(message)
            logger.debug(f"User message queued: {message[:50]}...")

    async def get_user_message(self, timeout: Optional[float] = None) -> Optional[str]:
        """
        Wait for and get the next user message from the queue.

        Args:
            timeout: Optional timeout in seconds (None = wait indefinitely)

        Returns:
            The user message, or None if cancelled/timeout
        """
        if self._user_message_queue is None:
            return None

        try:
            if timeout is not None:
                message = await asyncio.wait_for(
                    self._user_message_queue.get(),
                    timeout=timeout
                )
            else:
                message = await self._user_message_queue.get()
            return message
        except asyncio.TimeoutError:
            return None
        except asyncio.CancelledError:
            return None

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
        model: str,
        base_url: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        """Configure LLM credentials for the service.

        Args:
            api_key: User's Ami API key (ami_xxxxx format)
            model: LLM model name (required)
            base_url: CRS proxy URL (e.g., https://api.ariseos.com/api)
            user_id: User ID for memory queries (optional)
        """
        if not api_key:
            raise ValueError("api_key is required for LLM configuration")
        if not model:
            raise ValueError("model is required for LLM configuration")

        self._llm_api_key = api_key
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

        # Execute task asynchronously using AMI Executor
        asyncio.create_task(
            self._execute_task_ami(task_id, headless=headless)
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

            # Execute new task using AMI Executor
            asyncio.create_task(
                self._execute_task_ami(new_task_id, headless=headless)
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

            # Reset events and queues for new execution
            old_state._cancel_event = asyncio.Event()
            # Clear any stale messages from previous session
            old_state._user_message_queue = asyncio.Queue()

            # Set as current manager
            set_current_manager(old_state.dir_manager)

            # Execute continued task using AMI Executor
            asyncio.create_task(
                self._execute_task_ami(task_id, headless=headless)
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
            "subtasks": state.subtasks,
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
                "subtasks": state.subtasks,
                "steps_executed": state.result.get("data", {}).get("steps_taken", 0),
                "total_steps": len(state.subtasks) if state.subtasks else 0,
                "duration_seconds": duration,
                "error": state.error,
                "action_history": state.result.get("data", {}).get("action_history", []),
            }
        else:
            return {
                "task_id": task_id,
                "success": False,
                "output": None,
                "subtasks": state.subtasks,
                "steps_executed": 0,
                "total_steps": len(state.subtasks) if state.subtasks else 0,
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

        # Send end event with cancelled status
        await state.put_event(EndData(
            task_id=task_id,
            status="cancelled",
            message="Task cancelled by user",
        ))

        logger.info(f"Task cancelled: {task_id}")
        return True

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

    async def _decompose_task(self, state: TaskState) -> List[Dict]:
        """
        Decompose a task into subtasks using LLM with streaming (Eigent-style).

        This is called BEFORE agent execution to let user review/edit the plan.
        Streams the decomposition text to frontend via streaming_decompose events.

        Args:
            state: TaskState containing the task to decompose

        Returns:
            List of subtask dicts with id, content, status fields
        """
        task = state.task
        task_id = state.task_id
        logger.info(f"[Task {task_id}] Decomposing task with streaming: {task[:100]}...")

        if not self._llm_api_key:
            logger.warning(f"[Task {task_id}] No LLM API key, skipping decomposition")
            return []

        try:
            from anthropic import Anthropic

            # Initialize Anthropic client
            client_kwargs = {"api_key": self._llm_api_key}
            if self._llm_base_url:
                client_kwargs["base_url"] = self._llm_base_url

            client = Anthropic(**client_kwargs)

            # Task decomposition prompt (based on Eigent's TASK_DECOMPOSE_PROMPT)
            decompose_prompt = f"""You are a task planning assistant. Break down the following task into 2-5 concrete, actionable subtasks.

Task: {task}

Requirements:
1. Each subtask should be specific and completable
2. Subtasks should be in logical order
3. Each subtask should be achievable with web browsing, searching, or data extraction
4. Keep subtasks focused - avoid overly broad steps

Respond with a JSON array of subtasks. Each subtask should have:
- "id": A unique identifier like "task.1", "task.2", etc.
- "content": A clear description of what needs to be done
- "status": Always "OPEN" for new tasks

Example response:
[
  {{"id": "task.1", "content": "Search for relevant information about X", "status": "OPEN"}},
  {{"id": "task.2", "content": "Navigate to the website and extract data", "status": "OPEN"}},
  {{"id": "task.3", "content": "Compile findings into a summary", "status": "OPEN"}}
]

Respond ONLY with the JSON array, no other text."""

            # Call LLM for decomposition with streaming
            model = self._llm_model or DEFAULT_MODEL

            # Use streaming to show decomposition progress
            response_text = ""
            with client.messages.stream(
                model=model,
                max_tokens=1024,
                messages=[{"role": "user", "content": decompose_prompt}],
            ) as stream:
                for text in stream.text_stream:
                    response_text += text
                    # Send streaming_decompose event to frontend (Eigent-style)
                    await state.put_event(StreamingDecomposeData(
                        task_id=task_id,
                        text=response_text,
                    ))

            response_text = response_text.strip()

            # Try to extract JSON from response
            import json
            import re

            # Handle markdown code blocks
            if "```json" in response_text:
                match = re.search(r"```json\s*([\s\S]*?)\s*```", response_text)
                if match:
                    response_text = match.group(1)
            elif "```" in response_text:
                match = re.search(r"```\s*([\s\S]*?)\s*```", response_text)
                if match:
                    response_text = match.group(1)

            subtasks = json.loads(response_text)

            # Validate and normalize subtasks
            normalized_subtasks = []
            for i, subtask in enumerate(subtasks):
                normalized_subtasks.append({
                    "id": subtask.get("id", f"task.{i+1}"),
                    "content": subtask.get("content", ""),
                    "status": "OPEN",
                })

            logger.info(f"[Task {task_id}] Decomposed into {len(normalized_subtasks)} subtasks")
            for st in normalized_subtasks:
                logger.info(f"  - {st['id']}: {st['content'][:60]}...")

            return normalized_subtasks

        except Exception as e:
            logger.warning(f"[Task {task_id}] Task decomposition failed: {e}")
            # Return a single fallback subtask
            return [{
                "id": "task.1",
                "content": task,
                "status": "OPEN",
            }]

    # ===== Task Classification (Eigent question_confirm pattern) =====

    async def _classify_task(self, task: str, state: "TaskState") -> bool:
        """
        Determine if user query is a complex task or simple question.

        This implements Eigent's question_confirm pattern:
        - Complex task: Requires tools, code execution, file operations, multi-step planning
        - Simple question: Can be answered directly with knowledge, no action needed

        Args:
            task: User's input query/task
            state: TaskState for conversation context

        Returns:
            True: Complex task, needs decomposition and execution
            False: Simple question, answer directly
        """
        logger.info(f"[Task {state.task_id}] Classifying task: {task[:100]}...")

        # Build conversation context (Eigent pattern)
        context_prompt = ""
        if state.conversation_history:
            context_prompt = "=== Previous Conversation ===\n"
            for entry in state.conversation_history[-10:]:  # Last 10 entries
                role = entry.role.upper()
                content = entry.content
                if isinstance(content, dict):
                    content = str(content)
                context_prompt += f"{role}: {content[:500]}\n"
            context_prompt += "=== End Conversation ===\n\n"

        # Classification prompt (based on Eigent's question_confirm)
        classify_prompt = f"""{context_prompt}User Query: {task}

Determine if this user query is a complex task or a simple question.

**Complex task** (answer "yes"): Requires tools, code execution, file operations, multi-step planning, or creating/modifying content
- Examples: "create a file", "search for X", "implement feature Y", "write code", "analyze data", "build something", "download X", "scrape website"

**Simple question** (answer "no"): Can be answered directly with knowledge or conversation history, no action needed
- Examples: greetings ("hello", "hi", "你好"), fact queries ("what is X?"), clarifications ("what did you mean?"), status checks ("how are you?"), explanations ("explain X"), opinions ("which is better?")

Answer only "yes" or "no". Do not provide any explanation.

Is this a complex task? (yes/no):"""

        try:
            # Use lightweight LLM call for classification
            from ..base_agent.core.agent_factories import create_model_backend

            model = create_model_backend(
                llm_api_key=self._llm_api_key,
                llm_model=self._llm_model,
                llm_base_url=self._llm_base_url,
            )

            # Make LLM call with OpenAI message format (dict)
            response = model.run(
                messages=[{"role": "user", "content": classify_prompt}]
            )

            content = response.choices[0].message.content.strip().lower()
            is_complex = "yes" in content

            logger.info(f"[Task {state.task_id}] Classification result: {'complex' if is_complex else 'simple'} (response: {content})")
            return is_complex

        except Exception as e:
            logger.error(f"[Task {state.task_id}] Classification error: {e}")
            # BUG-9 fix: Notify user about classification failure
            await state.put_event(NoticeData(
                task_id=state.task_id,
                level="warning",
                title="Classification Failed",
                message="Could not classify task, treating as complex task",
            ))
            # Default to complex task on error (safer)
            return True

    async def _answer_simple_question(self, question: str, state: "TaskState") -> str:
        """
        Directly answer a simple question without task decomposition.

        Used when _classify_task returns False. Generates a conversational
        response using conversation history for context.

        Args:
            question: User's simple question
            state: TaskState for conversation context

        Returns:
            LLM-generated answer string
        """
        logger.info(f"[Task {state.task_id}] Answering simple question: {question[:100]}...")

        # Build conversation context
        context_prompt = ""
        if state.conversation_history:
            context_prompt = "=== Previous Conversation ===\n"
            for entry in state.conversation_history[-10:]:
                role = entry.role.upper()
                content = entry.content
                if isinstance(content, dict):
                    content = str(content)
                context_prompt += f"{role}: {content[:500]}\n"
            context_prompt += "=== End Conversation ===\n\n"

        answer_prompt = f"""{context_prompt}User Query: {question}

You are AMI, a helpful AI assistant. Provide a direct, helpful, and conversational response to the user's question.

Guidelines:
- Be friendly and natural
- Keep the response concise but complete
- If the question is a greeting, respond warmly
- If you need to clarify something, ask
- Use the conversation history for context when relevant

Response:"""

        try:
            from ..base_agent.core.agent_factories import create_model_backend

            model = create_model_backend(
                llm_api_key=self._llm_api_key,
                llm_model=self._llm_model,
                llm_base_url=self._llm_base_url,
            )

            # Make LLM call with OpenAI message format (dict)
            response = model.run(
                messages=[{"role": "user", "content": answer_prompt}]
            )

            answer = response.choices[0].message.content.strip()
            logger.info(f"[Task {state.task_id}] Simple answer generated: {answer[:100]}...")
            return answer

        except Exception as e:
            logger.error(f"[Task {state.task_id}] Failed to answer simple question: {e}")
            return f"I apologize, but I encountered an error: {str(e)}"

    async def _wait_for_user_message(
        self,
        task_id: str,
        state: "TaskState",
        timeout: Optional[float] = None,
    ) -> Optional[str]:
        """
        Wait for the next user message in multi-turn conversation.

        Called after wait_confirm event is sent. Waits for user to send
        a new message via the message API.

        Args:
            task_id: Task identifier
            state: TaskState containing the message queue
            timeout: Optional timeout in seconds (None = wait indefinitely)

        Returns:
            User message string, or None if cancelled/timeout
        """
        logger.info(f"[Task {task_id}] Waiting for next user message...")

        try:
            # Wait for message with cancellation support
            message = await state.get_user_message(timeout=timeout)

            if message is None:
                logger.info(f"[Task {task_id}] No user message received (timeout or cancelled)")
                return None

            logger.info(f"[Task {task_id}] Received user message: {message[:100]}...")
            return message

        except asyncio.CancelledError:
            logger.info(f"[Task {task_id}] Wait for user message cancelled")
            return None
        except Exception as e:
            logger.error(f"[Task {task_id}] Error waiting for user message: {e}")
            return None

    async def _execute_task_ami(
        self,
        task_id: str,
        headless: bool = False,
    ):
        """
        Execute a task using AMITaskPlanner + AMITaskExecutor.

        This method replaces _execute_task_workforce with a simpler implementation:
        - Uses AMITaskPlanner for coarse-grained decomposition + Memory query
        - Uses AMITaskExecutor for sequential execution with workflow_guide injection
        - No CAMEL Workforce dependency

        Key differences from _execute_task_workforce:
        - workflow_guide is injected as explicit instruction, not metadata
        - ~650 lines vs ~2000 lines of code
        - Direct prompt control

        Args:
            task_id: Task identifier
            headless: Whether to run browser in headless mode
        """
        logger.info(f"[Task {task_id}] Starting AMI Executor-based session")

        state = self._tasks[task_id]
        state.status = TaskStatus.RUNNING
        state.started_at = datetime.now()
        state.updated_at = state.started_at

        # Record user's task as first conversation entry
        state.add_conversation("user", state.task)

        # Set current working directory manager
        set_current_manager(state.dir_manager)
        logger.info(f"[Task {task_id}] Working directory: {state.working_directory}")

        # Send task started event
        await state.put_event(TaskStateData(
            task_id=task_id,
            status="running",
            task=state.task,
            working_directory=state.working_directory,
            user_id=state.user_id,
            project_id=state.project_id,
        ))

        # ===== Create Orchestrator Agent =====
        orchestrator, decompose_tool = await create_orchestrator_agent(
            task_state=state,
            task_id=task_id,
            working_directory=state.working_directory,
            notes_directory=state.notes_directory,
            browser_data_directory=state.browser_data_directory,
            headless=headless,
            memory_api_base_url=self._cloud_client.api_url if self._cloud_client else None,
            ami_api_key=self._llm_api_key,
            user_id=self._user_id,
            llm_api_key=self._llm_api_key,
            llm_model=self._llm_model,
            llm_base_url=self._llm_base_url,
        )
        logger.info(f"[Task {task_id}] Orchestrator Agent created")

        # AMI components (created lazily)
        executor = None
        agents_dict = None
        current_question = state.task
        loop_iteration = 0

        # ===== Main Multi-turn Loop =====
        while True:
            loop_iteration += 1
            logger.info(f"[Task {task_id}] Multi-turn loop iteration #{loop_iteration}")

            try:
                # ===== Run Orchestrator Agent =====
                logger.info(f"[Task {task_id}] Running Orchestrator for: {current_question[:100]}...")

                orchestrator_reply = await run_orchestrator(
                    orchestrator=orchestrator,
                    decompose_tool=decompose_tool,
                    user_message=current_question,
                )

                logger.info(f"[Task {task_id}] Orchestrator response: {orchestrator_reply[:200]}...")

                # Check if decompose_task was called
                if decompose_tool.triggered:
                    # ===== AMI Executor Path =====
                    task_to_decompose = decompose_tool.task_description or current_question
                    logger.info(f"[Task {task_id}] decompose_task triggered, starting AMI Executor")

                    # Emit confirmed event
                    await state.put_event(ConfirmedData(
                        task_id=task_id,
                        question=task_to_decompose,
                    ))

                    # Report: Starting task decomposition
                    await state.put_event(AgentReportData(
                        task_id=task_id,
                        message="这是一个复杂任务，正在拆解为子任务...",
                        report_type="thinking",
                    ))

                    try:
                        # Create agents and executor if not yet created
                        if agents_dict is None:
                            agents_dict, task_agent = await self._create_agents_for_ami_executor(
                                task_id, state, headless
                            )
                            logger.info(f"[Task {task_id}] Created agents for AMI Executor")

                        # Create Memory Toolkit
                        memory_toolkit = await self._create_memory_toolkit(task_id, state)

                        # Create Task Planner
                        from ..base_agent.core import AMITaskPlanner, AMITaskExecutor
                        planner = AMITaskPlanner(
                            task_id=task_id,
                            task_state=state,
                            task_agent=task_agent,
                            memory_toolkit=memory_toolkit,
                        )

                        # Phase 1 & 2: Decompose and query Memory
                        logger.info(f"[Task {task_id}] AMI: Decomposing and querying Memory...")
                        subtasks = await planner.decompose_and_query_memory(task_to_decompose)

                        if not subtasks:
                            logger.warning(f"[Task {task_id}] Decomposition returned no subtasks")
                            await state.put_event(NoticeData(
                                task_id=task_id,
                                level="warning",
                                title="Decomposition Failed",
                                message="Could not decompose task into subtasks.",
                            ))
                            state.add_conversation("assistant", orchestrator_reply)
                            await state.put_event(WaitConfirmData(
                                task_id=task_id,
                                content=orchestrator_reply,
                                question=current_question,
                                context="initial",
                            ))
                        else:
                            # Update state with subtasks
                            state.subtasks = [
                                {
                                    "id": st.id,
                                    "content": st.content,
                                    "state": st.state.value,
                                    "status": st.state.value,
                                    "agent_type": st.agent_type,
                                    "memory_level": st.memory_level,
                                }
                                for st in subtasks
                            ]
                            state.summary_task = task_to_decompose

                            # Emit TaskDecomposedData event (for frontend display only, no confirmation needed)
                            await state.put_event(TaskDecomposedData(
                                task_id=task_id,
                                subtasks=state.subtasks,
                                summary_task=task_to_decompose,
                                total_subtasks=len(subtasks),
                            ))

                            # Execute subtasks directly (no confirmation wait)
                            logger.info(f"[Task {task_id}] Starting AMI Executor with {len(subtasks)} subtasks...")
                            start_time = datetime.now()

                            # Report: Starting execution
                            await state.put_event(AgentReportData(
                                task_id=task_id,
                                message=f"开始执行 {len(subtasks)} 个子任务...",
                                report_type="info",
                            ))

                            await state.put_event(WorkforceStartedData(
                                task_id=task_id,
                                total_tasks=len(subtasks),
                                workers_count=len(agents_dict),
                                description=f"Starting execution with {len(subtasks)} subtasks",
                            ))

                            # Create executor
                            executor = AMITaskExecutor(
                                task_id=task_id,
                                task_state=state,
                                agents=agents_dict,
                            )
                            executor.set_subtasks(subtasks)

                            # Execute
                            result = await executor.execute()

                            duration = (datetime.now() - start_time).total_seconds()

                            await state.put_event(WorkforceCompletedData(
                                task_id=task_id,
                                completed_count=result["completed"],
                                failed_count=result["failed"],
                                total_count=result["total"],
                                duration_seconds=duration,
                            ))

                            # Report: Execution completed
                            if result["failed"] == 0:
                                await state.put_event(AgentReportData(
                                    task_id=task_id,
                                    message=f"全部 {result['completed']} 个子任务执行完成！",
                                    report_type="success",
                                ))
                            else:
                                await state.put_event(AgentReportData(
                                    task_id=task_id,
                                    message=f"执行完成：{result['completed']} 成功，{result['failed']} 失败",
                                    report_type="warning",
                                ))

                            # Aggregate results
                            final_output = await self._aggregate_ami_results(
                                task_id, state, subtasks, result, duration
                            )

                            # Record in conversation history
                            state.add_conversation("task_result", {
                                "task_content": task_to_decompose,
                                "task_result": final_output,
                                "working_directory": state.working_directory,
                            })

                            # Update state
                            state.result = {
                                "success": result["failed"] == 0,
                                "message": final_output,
                                "data": {
                                    "completed": result["completed"],
                                    "failed": result["failed"],
                                    "duration": duration,
                                },
                            }

                            context = "mid_execution" if loop_iteration > 1 else "initial"
                            await state.put_event(WaitConfirmData(
                                task_id=task_id,
                                content=final_output,
                                question=task_to_decompose,
                                context=context,
                            ))

                            logger.info(f"[Task {task_id}] AMI Executor completed, ready for multi-turn")

                    except Exception as e:
                        logger.exception(f"[Task {task_id}] AMI Executor failed: {e}")
                        state.error = str(e)

                        await state.put_event(WorkforceStoppedData(
                            task_id=task_id,
                            reason=str(e),
                        ))
                        await state.put_event(TaskFailedData(
                            task_id=task_id,
                            error=str(e),
                        ))
                        context = "mid_execution" if loop_iteration > 1 else "initial"
                        await state.put_event(WaitConfirmData(
                            task_id=task_id,
                            content=f"Task execution failed: {e}\n\nYou can try again or ask me something else.",
                            question=task_to_decompose,
                            context=context,
                        ))
                        state.status = TaskStatus.WAITING
                        state.updated_at = datetime.now()

                else:
                    # ===== Direct Response Path (No Execution) =====
                    logger.info(f"[Task {task_id}] Orchestrator handled directly (no decompose_task)")

                    state.add_conversation("assistant", orchestrator_reply)

                    context = "initial" if loop_iteration == 1 else "mid_execution"
                    await state.put_event(WaitConfirmData(
                        task_id=task_id,
                        content=orchestrator_reply,
                        question=current_question,
                        context=context,
                    ))

                # Set status to WAITING for multi-turn
                state.status = TaskStatus.WAITING
                state.updated_at = datetime.now()

            except asyncio.CancelledError:
                logger.info(f"[Task {task_id}] Task cancelled during execution")
                break
            except Exception as e:
                logger.exception(f"[Task {task_id}] Orchestrator execution failed: {e}")
                state.error = str(e)

                await state.put_event(NoticeData(
                    task_id=task_id,
                    level="error",
                    title="Execution Error",
                    message=str(e),
                ))
                context = "mid_execution" if loop_iteration > 1 else "initial"
                await state.put_event(WaitConfirmData(
                    task_id=task_id,
                    content=f"An error occurred: {e}\n\nYou can try again or ask me something else.",
                    question=current_question,
                    context=context,
                ))
                state.status = TaskStatus.WAITING

            # ===== Wait for Next User Message =====
            logger.info(f"[Task {task_id}] Waiting for next user message...")

            try:
                next_message = await self._wait_for_user_message(task_id, state)
                if next_message is None:
                    logger.info(f"[Task {task_id}] No more user messages, ending session")
                    break

                state.add_conversation("user", next_message)
                current_question = next_message
                logger.info(f"[Task {task_id}] Received next user message: {next_message[:100]}...")

            except asyncio.CancelledError:
                logger.info(f"[Task {task_id}] Task cancelled while waiting")
                break
            except Exception as e:
                logger.error(f"[Task {task_id}] Error waiting for user message: {e}")
                break

        # ===== Session End Cleanup =====
        logger.info(f"[Task {task_id}] AMI session ended after {loop_iteration} iterations")
        state.status = TaskStatus.COMPLETED
        state.completed_at = datetime.now()

        await state.put_event(EndData(
            task_id=task_id,
            status="completed",
            message="Session ended",
            result=state.result,
        ))

        # Close browser session
        try:
            from ..base_agent.tools.eigent_browser.browser_session import HybridBrowserSession
            closed = await HybridBrowserSession.close_session_by_id(task_id)
            if closed:
                logger.info(f"[Task {task_id}] Browser session closed successfully")
        except Exception as cleanup_error:
            logger.warning(f"[Task {task_id}] Error closing browser session: {cleanup_error}")

    async def _create_agents_for_ami_executor(
        self,
        task_id: str,
        state: "TaskState",
        headless: bool = False,
    ):
        """
        Create agents for AMI Executor.

        Returns a dictionary of agents keyed by agent_type for AMITaskExecutor,
        plus the task_agent for AMITaskPlanner.

        Args:
            task_id: Task identifier
            state: TaskState containing working directories
            headless: Whether to run browser in headless mode

        Returns:
            Tuple of (agents_dict, task_agent)
        """
        from ..base_agent.core.agent_factories import (
            create_listen_browser_agent,
            create_developer_agent,
            create_document_agent,
            create_multi_modal_agent,
            create_model_backend,
        )
        from camel.agents import ChatAgent

        logger.info(f"[Task {task_id}] Creating agents for AMI Executor...")

        # Create all agents in parallel
        agent_results = await asyncio.gather(
            create_listen_browser_agent(
                task_state=state,
                task_id=task_id,
                working_directory=state.working_directory,
                notes_directory=state.notes_directory,
                browser_data_directory=state.browser_data_directory,
                headless=headless,
                memory_api_base_url=self._cloud_client.api_url if self._cloud_client else None,
                ami_api_key=self._llm_api_key,
                user_id=self._user_id,
                llm_api_key=self._llm_api_key,
                llm_model=self._llm_model,
                llm_base_url=self._llm_base_url,
            ),
            asyncio.to_thread(
                create_developer_agent,
                task_state=state,
                task_id=task_id,
                working_directory=state.working_directory,
                notes_directory=state.notes_directory,
                llm_api_key=self._llm_api_key,
                llm_model=self._llm_model,
                llm_base_url=self._llm_base_url,
            ),
            create_document_agent(
                task_state=state,
                task_id=task_id,
                working_directory=state.working_directory,
                notes_directory=state.notes_directory,
                llm_api_key=self._llm_api_key,
                llm_model=self._llm_model,
                llm_base_url=self._llm_base_url,
            ),
            asyncio.to_thread(
                create_multi_modal_agent,
                task_state=state,
                task_id=task_id,
                working_directory=state.working_directory,
                notes_directory=state.notes_directory,
                llm_api_key=self._llm_api_key,
                llm_model=self._llm_model,
                llm_base_url=self._llm_base_url,
            ),
            return_exceptions=True,
        )

        # Process results
        agent_names = ["browser", "code", "document", "multi_modal"]
        agents_dict = {}
        failed_agents = []

        for i, result in enumerate(agent_results):
            if isinstance(result, Exception):
                logger.warning(f"[Task {task_id}] {agent_names[i]} Agent creation failed: {result}")
                failed_agents.append(agent_names[i])
            else:
                agents_dict[agent_names[i]] = result

        if not agents_dict:
            raise RuntimeError(f"All agents failed to create: {failed_agents}")

        if failed_agents:
            await state.put_event(NoticeData(
                task_id=task_id,
                level="warning",
                title="Partial Agent Availability",
                message=f"Some agents failed to initialize: {', '.join(failed_agents)}. Continuing with available agents.",
            ))

        logger.info(f"[Task {task_id}] Agents created: {len(agents_dict)}/4 available")

        # Create task_agent for AMITaskPlanner
        model_backend = create_model_backend(
            llm_api_key=self._llm_api_key,
            llm_model=self._llm_model,
            llm_base_url=self._llm_base_url,
        )

        task_agent = ChatAgent(
            system_message="You are a task decomposition expert. Split tasks by work type (browser, document, code).",
            model=model_backend,
        )

        return agents_dict, task_agent

    async def _create_memory_toolkit(
        self,
        task_id: str,
        state: "TaskState",
    ):
        """
        Create Memory Toolkit for AMI components.

        Args:
            task_id: Task identifier
            state: TaskState

        Returns:
            MemoryToolkit instance or None
        """
        if not self._cloud_client or not self._llm_api_key:
            return None

        try:
            from ..base_agent.tools.toolkits import MemoryToolkit
            memory_api_base_url = getattr(self._cloud_client, 'api_url', None)
            if memory_api_base_url:
                effective_user_id = state.user_id or self._user_id or "default"
                memory_toolkit = MemoryToolkit(
                    memory_api_base_url=memory_api_base_url,
                    ami_api_key=self._llm_api_key,
                    user_id=effective_user_id,
                )
                logger.info(f"[Task {task_id}] MemoryToolkit created for AMI Executor")
                return memory_toolkit
        except Exception as e:
            logger.warning(f"[Task {task_id}] Failed to create MemoryToolkit: {e}")

        return None

    async def _aggregate_ami_results(
        self,
        task_id: str,
        state: "TaskState",
        subtasks,
        result: dict,
        duration: float,
    ) -> str:
        """
        Aggregate results from AMI subtasks into a summary.

        Args:
            task_id: Task identifier
            state: TaskState
            subtasks: List of AMISubtask objects
            result: Execution result dict
            duration: Execution duration in seconds

        Returns:
            Summary string
        """
        summary_output = None

        if len(subtasks) > 1:
            try:
                from ..base_agent.core.agent_factories import (
                    create_task_summary_agent,
                    summarize_subtasks_results,
                )

                logger.info(f"[Task {task_id}] Generating summary for {len(subtasks)} subtasks...")

                subtasks_with_results = [
                    {
                        "id": st.id,
                        "content": st.content,
                        "result": str(st.result)[:2000] if st.result else "No result",
                    }
                    for st in subtasks
                ]

                summary_agent = create_task_summary_agent(
                    llm_api_key=self._llm_api_key,
                    llm_model=self._llm_model,
                    llm_base_url=self._llm_base_url,
                )
                summary_output = await summarize_subtasks_results(
                    agent=summary_agent,
                    main_task=state.task,
                    subtasks=subtasks_with_results,
                )
                logger.info(f"[Task {task_id}] Summary generated successfully")
            except Exception as e:
                logger.error(f"[Task {task_id}] Failed to generate summary: {e}")

        elif len(subtasks) == 1:
            single_result = subtasks[0].result
            if single_result:
                summary_output = str(single_result)
                logger.info(f"[Task {task_id}] Using single subtask result directly")

        if summary_output:
            return summary_output
        else:
            return f"Completed {result['completed']}/{result['total']} subtasks"

    # ===== Multi-turn Conversation Handling (Eigent pattern) =====

    async def handle_user_message(self, task_id: str, message: str) -> Dict[str, Any]:
        """
        Handle user message during task execution (Eigent pattern).

        This method implements multi-turn conversation support:
        1. If task is WAITING → put message in queue for the multi-turn loop
        2. If task is completed → delegate to continue_task
        3. If task is running → classify message, handle accordingly

        Args:
            task_id: Task identifier
            message: User's new message

        Returns:
            Dict with handling result:
            - {"type": "queued", "success": True} for WAITING state
            - {"type": "simple_answer", "answer": str} for simple questions
            - {"type": "continued", "new_task_id": str} for completed tasks
        """
        state = self._tasks.get(task_id)
        if not state:
            raise ValueError(f"Task {task_id} not found")

        logger.info(f"[Task {task_id}] Handling user message (status={state.status.value}): {message[:100]}...")

        # Case 0: Task is WAITING for user input (Eigent multi-turn pattern)
        # Put message in queue for the multi-turn loop to receive
        if state.status == TaskStatus.WAITING:
            logger.info(f"[Task {task_id}] Task is WAITING, queuing message for multi-turn loop")
            await state.put_user_message(message)
            return {"type": "queued", "success": True}

        # Case 0.5: Task is RUNNING - queue the message, it will be processed after current operation
        # This allows users to type while agent is working (queue instead of block pattern)
        if state.status == TaskStatus.RUNNING:
            logger.info(f"[Task {task_id}] Task is RUNNING, queuing message for later processing")
            # Don't add to conversation here - the main loop will do it when it processes the message
            # Queue for processing after current operation completes
            await state.put_user_message(message)
            return {"type": "queued", "success": True}

        # Case 1: Task already completed → continue with new task
        if state.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            logger.info(f"[Task {task_id}] Task already finished, delegating to continue_task")
            # Record in conversation history before continuing
            state.add_conversation("user", message)
            new_task_id = await self.continue_task(task_id, message)
            return {"type": "continued", "new_task_id": new_task_id}

        # Case 2: Task is PENDING - this shouldn't normally happen
        # Queue it anyway for safety (don't add to conversation - loop will do it)
        logger.warning(f"[Task {task_id}] Task is in PENDING state, queuing message")
        await state.put_user_message(message)
        return {"type": "queued", "success": True, "message": "Message queued - task is starting"}

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
