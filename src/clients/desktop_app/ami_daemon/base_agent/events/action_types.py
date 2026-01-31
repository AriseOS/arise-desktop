"""
Event Action Types for Real-time Communication.

Defines all supported action types and their data models for
agent-frontend communication via SSE/WebSocket.

Based on Eigent's event system with 2ami-specific additions.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class Action(str, Enum):
    """All supported action types for the event system."""

    # ===== User -> Backend (Input Actions) =====
    improve = "improve"              # New task/question from user
    update_task = "update_task"      # Modify existing task
    start = "start"                  # Start execution
    stop = "stop"                    # Stop execution
    pause = "pause"                  # Pause execution
    resume = "resume"                # Resume execution
    supplement = "supplement"        # Add supplementary info
    human_response = "human_response"  # Human response to ask

    # ===== Backend -> User (Output Events) =====

    # Task lifecycle
    task_state = "task_state"               # Full task state update
    new_task_state = "new_task_state"       # New task created
    task_started = "task_started"           # Task execution started
    task_completed = "task_completed"       # Task finished successfully
    task_failed = "task_failed"             # Task failed
    task_cancelled = "task_cancelled"       # Task cancelled

    # Planning
    plan_started = "plan_started"           # Planning started
    plan_progress = "plan_progress"         # Planning progress update
    plan_generated = "plan_generated"       # Plan complete

    # Task decomposition (from TaskPlanningToolkit / Workforce)
    task_decomposed = "task_decomposed"       # Task broken into subtasks
    subtask_state = "subtask_state"           # Subtask state changed
    task_replanned = "task_replanned"         # Task re-planned with new subtasks
    streaming_decompose = "streaming_decompose"  # Streaming decomposition text

    # Workforce events (CAMEL-based multi-agent coordination)
    workforce_started = "workforce_started"           # Workforce started processing
    workforce_completed = "workforce_completed"       # Workforce finished all tasks
    workforce_stopped = "workforce_stopped"           # Workforce stopped/cancelled
    worker_assigned = "worker_assigned"               # Task assigned to a worker
    worker_started = "worker_started"                 # Worker started processing
    worker_completed = "worker_completed"             # Worker finished task
    worker_failed = "worker_failed"                   # Worker failed task
    dynamic_tasks_added = "dynamic_tasks_added"       # New tasks discovered during execution

    # Agent lifecycle
    activate_agent = "activate_agent"       # Agent started working
    deactivate_agent = "deactivate_agent"   # Agent finished
    agent_thinking = "agent_thinking"       # Agent is reasoning/thinking
    agent_started = "agent_started"         # Agent loop started

    # Step/iteration execution
    step_started = "step_started"           # Step execution started
    step_progress = "step_progress"         # Step progress update
    step_completed = "step_completed"       # Step completed
    step_failed = "step_failed"             # Step failed
    loop_iteration = "loop_iteration"       # Agent loop iteration

    # Toolkit events
    activate_toolkit = "activate_toolkit"       # Tool started
    deactivate_toolkit = "deactivate_toolkit"   # Tool finished
    tool_started = "tool_started"               # Tool call initiated
    tool_completed = "tool_completed"           # Tool call completed
    tool_failed = "tool_failed"                 # Tool call failed
    tool_executed = "tool_executed"             # Legacy: tool execution event

    # Specific tool events
    terminal = "terminal"                   # Terminal command output
    browser_action = "browser_action"       # Browser action performed
    write_file = "write_file"               # File written
    screenshot = "screenshot"               # Screenshot captured

    # User interaction
    ask = "ask"                             # Asking user for input
    notice = "notice"                       # Notification message
    human_question = "human_question"       # Question for human
    human_message = "human_message"         # Message to human

    # Memory events
    memory_query = "memory_query"           # Memory query started
    memory_result = "memory_result"         # Memory query result
    memory_loaded = "memory_loaded"         # Memory paths loaded
    memory_level = "memory_level"           # Memory level determination (L1/L2/L3)

    # Reasoner events
    reasoner_query_started = "reasoner_query_started"
    reasoner_workflow_started = "reasoner_workflow_started"
    reasoner_navigate = "reasoner_navigate"
    reasoner_intent_executed = "reasoner_intent_executed"
    reasoner_intent_failed = "reasoner_intent_failed"
    reasoner_workflow_completed = "reasoner_workflow_completed"
    reasoner_fallback = "reasoner_fallback"

    # LLM events
    llm_request = "llm_request"             # LLM request sent
    llm_response = "llm_response"           # LLM response received
    llm_reasoning = "llm_reasoning"         # LLM reasoning/thinking
    llm_error = "llm_error"                 # LLM error occurred
    context_too_long = "context_too_long"   # Context exceeded limit
    context_warning = "context_warning"     # Context nearing limit (80%)

    # System events
    heartbeat = "heartbeat"                 # Keep-alive signal
    error = "error"                         # Error occurred
    end = "end"                             # Stream ended
    connected = "connected"                 # WebSocket connected


# ===== Base Action Data Model =====

class BaseActionData(BaseModel):
    """Base class for all action data."""

    action: Action
    timestamp: Optional[str] = None
    task_id: Optional[str] = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', datetime.now().isoformat())

    class Config:
        use_enum_values = True


# ===== Task Lifecycle Events =====

class TaskStateData(BaseActionData):
    """Full task state update."""

    action: Literal[Action.task_state] = Action.task_state
    status: str
    task: str
    progress: float = 0.0
    plan: Optional[List[Dict]] = None
    current_step: Optional[Dict] = None
    working_directory: Optional[str] = None
    user_id: Optional[str] = None
    project_id: Optional[str] = None


class TaskCompletedData(BaseActionData):
    """Task completed event."""

    action: Literal[Action.task_completed] = Action.task_completed
    output: Optional[Any] = None
    notes: Optional[str] = None
    tools_called: List[Dict] = Field(default_factory=list)
    loop_iterations: int = 0
    duration_seconds: Optional[float] = None


class TaskFailedData(BaseActionData):
    """Task failed event."""

    action: Literal[Action.task_failed] = Action.task_failed
    error: str
    notes: Optional[str] = None
    tools_called: List[Dict] = Field(default_factory=list)
    step: Optional[int] = None


class TaskCancelledData(BaseActionData):
    """Task cancelled event."""

    action: Literal[Action.task_cancelled] = Action.task_cancelled
    reason: Optional[str] = None


# ===== Planning Events =====

class PlanStartedData(BaseActionData):
    """Planning started event."""

    action: Literal[Action.plan_started] = Action.plan_started
    task: str


class PlanProgressData(BaseActionData):
    """Planning progress event."""

    action: Literal[Action.plan_progress] = Action.plan_progress
    progress: float  # 0.0 to 1.0
    message: Optional[str] = None


class PlanGeneratedData(BaseActionData):
    """Plan generated event."""

    action: Literal[Action.plan_generated] = Action.plan_generated
    steps: List[Dict]
    total_steps: int
    method: Optional[str] = None  # "memory", "llm", etc.


# ===== Task Decomposition Events =====

class TaskDecomposedData(BaseActionData):
    """Task decomposed into subtasks event (from TaskPlanningToolkit)."""

    action: Literal[Action.task_decomposed] = Action.task_decomposed
    subtasks: List[Dict]  # List of subtask dicts with id, content, state
    summary_task: Optional[str] = None  # Main task summary
    original_task_id: Optional[str] = None
    total_subtasks: int = 0


class SubtaskStateData(BaseActionData):
    """Subtask state changed event."""

    action: Literal[Action.subtask_state] = Action.subtask_state
    subtask_id: str
    state: str  # OPEN, RUNNING, DONE, FAILED, DELETED, ABANDONED
    result: Optional[str] = None
    failure_count: int = 0


class TaskReplannedData(BaseActionData):
    """Task re-planned with new subtasks event."""

    action: Literal[Action.task_replanned] = Action.task_replanned
    subtasks: List[Dict]  # New subtask list
    original_task_id: Optional[str] = None
    reason: Optional[str] = None  # Why re-planned


class StreamingDecomposeData(BaseActionData):
    """Streaming decomposition text event."""

    action: Literal[Action.streaming_decompose] = Action.streaming_decompose
    text: str  # Accumulated decomposition text


# ===== Agent Lifecycle Events =====

class ActivateAgentData(BaseActionData):
    """Agent activation event."""

    action: Literal[Action.activate_agent] = Action.activate_agent
    agent_name: str
    agent_id: Optional[str] = None
    process_task_id: Optional[str] = None
    message: Optional[str] = None


class DeactivateAgentData(BaseActionData):
    """Agent deactivation event."""

    action: Literal[Action.deactivate_agent] = Action.deactivate_agent
    agent_name: str
    agent_id: Optional[str] = None
    process_task_id: Optional[str] = None
    message: Optional[str] = None
    tokens_used: Optional[int] = None
    duration_seconds: Optional[float] = None


class AgentThinkingData(BaseActionData):
    """Agent thinking/reasoning event."""

    action: Literal[Action.agent_thinking] = Action.agent_thinking
    agent_name: str
    thinking: str  # The agent's reasoning text
    step: Optional[int] = None


# ===== Step Execution Events =====

class StepStartedData(BaseActionData):
    """Step started event."""

    action: Literal[Action.step_started] = Action.step_started
    step_index: int
    step_name: str
    step_description: Optional[str] = None


class StepProgressData(BaseActionData):
    """Step progress event."""

    action: Literal[Action.step_progress] = Action.step_progress
    step_index: int
    progress: float  # 0.0 to 1.0
    message: Optional[str] = None


class StepCompletedData(BaseActionData):
    """Step completed event."""

    action: Literal[Action.step_completed] = Action.step_completed
    step_index: int
    step_name: str
    result: Optional[str] = None  # Truncated result preview
    duration_seconds: Optional[float] = None


class StepFailedData(BaseActionData):
    """Step failed event."""

    action: Literal[Action.step_failed] = Action.step_failed
    step_index: int
    step_name: str
    error: str
    recoverable: bool = True


# ===== Toolkit Events =====

class ActivateToolkitData(BaseActionData):
    """Toolkit activation event."""

    action: Literal[Action.activate_toolkit] = Action.activate_toolkit
    toolkit_name: str
    method_name: str
    agent_name: Optional[str] = None
    process_task_id: Optional[str] = None
    input_preview: Optional[str] = None  # Truncated input
    message: Optional[str] = None


class DeactivateToolkitData(BaseActionData):
    """Toolkit deactivation event."""

    action: Literal[Action.deactivate_toolkit] = Action.deactivate_toolkit
    toolkit_name: str
    method_name: str
    agent_name: Optional[str] = None
    process_task_id: Optional[str] = None
    output_preview: Optional[str] = None  # Truncated output
    success: bool = True
    duration_ms: Optional[int] = None
    message: Optional[str] = None


# ===== Tool-Specific Events =====

class TerminalData(BaseActionData):
    """Terminal command event."""

    action: Literal[Action.terminal] = Action.terminal
    command: str
    output: Optional[str] = None  # Truncated output
    exit_code: Optional[int] = None
    working_directory: Optional[str] = None
    duration_ms: Optional[int] = None


class BrowserActionData(BaseActionData):
    """Browser action event."""

    action: Literal[Action.browser_action] = Action.browser_action
    action_type: str  # click, type, navigate, scroll, etc.
    target: Optional[str] = None  # Element description or URL
    value: Optional[str] = None  # Input value for type action
    success: bool = True
    screenshot_url: Optional[str] = None  # Base64 or URL to screenshot
    page_url: Optional[str] = None
    page_title: Optional[str] = None


class WriteFileData(BaseActionData):
    """File write event."""

    action: Literal[Action.write_file] = Action.write_file
    file_path: str
    file_name: str
    file_size: Optional[int] = None
    content_preview: Optional[str] = None  # First N characters
    mime_type: Optional[str] = None


class ScreenshotData(BaseActionData):
    """Browser screenshot event.

    Sent when a browser screenshot is captured, allowing the frontend
    to display the current browser state in the BrowserTab.
    """

    action: Literal[Action.screenshot] = Action.screenshot
    screenshot: str  # Base64-encoded image data (with data URI prefix)
    url: Optional[str] = None  # Current page URL
    page_title: Optional[str] = None  # Current page title
    tab_id: Optional[str] = None  # Tab ID if multiple tabs


# ===== User Interaction Events =====

class AskData(BaseActionData):
    """Ask user event."""

    action: Literal[Action.ask] = Action.ask
    question: str
    context: Optional[str] = None
    options: Optional[List[str]] = None  # Multiple choice options
    timeout_seconds: Optional[int] = None
    default: Optional[str] = None


class NoticeData(BaseActionData):
    """Notice/notification event."""

    action: Literal[Action.notice] = Action.notice
    level: str = "info"  # info, warning, error, success
    title: str
    message: str
    duration_ms: Optional[int] = None  # Auto-dismiss duration


class HumanResponseData(BaseActionData):
    """Human response event (input from user)."""

    action: Literal[Action.human_response] = Action.human_response
    response: str
    question_id: Optional[str] = None


# ===== Memory Events =====

class MemoryQueryData(BaseActionData):
    """Memory query started event."""

    action: Literal[Action.memory_query] = Action.memory_query
    query: str
    top_k: int = 3


class MemoryResultData(BaseActionData):
    """Memory query result event."""

    action: Literal[Action.memory_result] = Action.memory_result
    paths_count: int
    paths: List[Dict]  # Summary of matched paths
    has_workflow: bool = False
    method: Optional[str] = None


class MemoryLevelData(BaseActionData):
    """Memory level determination event.

    Indicates which level of memory guidance is available for the current task:
    - L1: Complete path from CognitivePhrase (full workflow match)
    - L2: Partial match from TaskDAG (some subtasks have memory support)
    - L3: No path match, will use real-time per-loop queries
    """

    action: Literal[Action.memory_level] = Action.memory_level
    level: str  # "L1" | "L2" | "L3"
    reason: str  # Human-readable explanation of the level determination
    states_count: int = 0  # Number of states found in memory
    method: str = ""  # "cognitive_phrase_match" | "task_dag" | "none"
    paths: Optional[List[Dict]] = None  # Optional workflow path info (for L1)


# ===== System Events =====

class HeartbeatData(BaseActionData):
    """Heartbeat keep-alive event."""

    action: Literal[Action.heartbeat] = Action.heartbeat
    message: str = "keep-alive"


class ErrorData(BaseActionData):
    """Error event."""

    action: Literal[Action.error] = Action.error
    error: str
    error_type: Optional[str] = None  # Exception class name
    recoverable: bool = True
    details: Optional[Dict] = None


class EndData(BaseActionData):
    """End stream event."""

    action: Literal[Action.end] = Action.end
    status: str  # "completed", "failed", "cancelled"
    message: Optional[str] = None
    result: Optional[Any] = None


class ContextWarningData(BaseActionData):
    """Context usage warning event (emitted at 80% threshold)."""

    action: Literal[Action.context_warning] = Action.context_warning
    current_length: int  # Current context length in characters
    max_length: int  # Maximum allowed length
    usage_percent: float  # Percentage of max (e.g., 80.5)
    message: str
    entries_count: int = 0  # Number of conversation entries


# ===== Workforce Events (CAMEL-based multi-agent) =====

class WorkforceStartedData(BaseActionData):
    """Workforce started processing event."""

    action: Literal[Action.workforce_started] = Action.workforce_started
    total_tasks: int
    workers_count: int
    description: Optional[str] = None


class WorkforceCompletedData(BaseActionData):
    """Workforce completed all tasks event."""

    action: Literal[Action.workforce_completed] = Action.workforce_completed
    completed_count: int
    failed_count: int
    total_count: int
    duration_seconds: Optional[float] = None


class WorkforceStoppedData(BaseActionData):
    """Workforce stopped/cancelled event."""

    action: Literal[Action.workforce_stopped] = Action.workforce_stopped
    reason: Optional[str] = None
    completed_count: int = 0
    pending_count: int = 0


class WorkerAssignedData(BaseActionData):
    """Task assigned to a worker event."""

    action: Literal[Action.worker_assigned] = Action.worker_assigned
    worker_name: str
    worker_id: Optional[str] = None
    subtask_id: str
    subtask_content: str


class WorkerStartedData(BaseActionData):
    """Worker started processing event."""

    action: Literal[Action.worker_started] = Action.worker_started
    worker_name: str
    worker_id: Optional[str] = None
    subtask_id: str


class WorkerCompletedData(BaseActionData):
    """Worker completed task event."""

    action: Literal[Action.worker_completed] = Action.worker_completed
    worker_name: str
    worker_id: Optional[str] = None
    subtask_id: str
    result_preview: Optional[str] = None  # Truncated result
    duration_seconds: Optional[float] = None


class WorkerFailedData(BaseActionData):
    """Worker failed task event."""

    action: Literal[Action.worker_failed] = Action.worker_failed
    worker_name: str
    worker_id: Optional[str] = None
    subtask_id: str
    error: str
    retry_count: int = 0
    will_retry: bool = False


class DynamicTasksAddedData(BaseActionData):
    """New tasks discovered and added during execution."""

    action: Literal[Action.dynamic_tasks_added] = Action.dynamic_tasks_added
    new_tasks: List[Dict]  # List of {id, content, status}
    added_by_worker: Optional[str] = None
    reason: Optional[str] = None
    total_tasks_now: int = 0


# ===== Type Alias for All Action Data Types =====

ActionData = Union[
    # Task lifecycle
    TaskStateData,
    TaskCompletedData,
    TaskFailedData,
    TaskCancelledData,
    # Planning
    PlanStartedData,
    PlanProgressData,
    PlanGeneratedData,
    # Task decomposition
    TaskDecomposedData,
    SubtaskStateData,
    TaskReplannedData,
    # Agent lifecycle
    ActivateAgentData,
    DeactivateAgentData,
    AgentThinkingData,
    # Step execution
    StepStartedData,
    StepProgressData,
    StepCompletedData,
    StepFailedData,
    # Toolkit events
    ActivateToolkitData,
    DeactivateToolkitData,
    # Tool-specific events
    TerminalData,
    BrowserActionData,
    WriteFileData,
    ScreenshotData,
    # User interaction
    AskData,
    NoticeData,
    HumanResponseData,
    # Memory events
    MemoryQueryData,
    MemoryResultData,
    MemoryLevelData,
    # System events
    HeartbeatData,
    ErrorData,
    EndData,
    ContextWarningData,
    # Workforce events
    WorkforceStartedData,
    WorkforceCompletedData,
    WorkforceStoppedData,
    WorkerAssignedData,
    WorkerStartedData,
    WorkerCompletedData,
    WorkerFailedData,
    DynamicTasksAddedData,
    # Fallback
    BaseActionData,
]
