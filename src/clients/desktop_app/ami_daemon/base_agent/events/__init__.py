"""
Event System for Agent-Frontend Communication.

Provides typed events, SSE formatting, and event emission utilities
for real-time task progress streaming.
"""

from .action_types import (
    Action,
    ActionData,
    BaseActionData,
    # Task lifecycle
    TaskStateData,
    TaskCompletedData,
    TaskFailedData,
    TaskCancelledData,
    # Planning
    PlanStartedData,
    PlanProgressData,
    PlanGeneratedData,
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
    # User interaction
    AskData,
    NoticeData,
    HumanResponseData,
    # Memory events
    MemoryQueryData,
    MemoryResultData,
    # System events
    HeartbeatData,
    ErrorData,
    EndData,
    ContextWarningData,
)

from .sse import (
    sse_json,
    sse_action,
    sse_comment,
    sse_heartbeat,
    SSEEmitter,
)

from .toolkit_listen import (
    listen_toolkit,
    auto_listen_toolkit,
    set_process_task,
    process_task,
    EXCLUDED_METHODS,
)

__all__ = [
    # Action enum
    "Action",
    "ActionData",
    "BaseActionData",
    # Task lifecycle
    "TaskStateData",
    "TaskCompletedData",
    "TaskFailedData",
    "TaskCancelledData",
    # Planning
    "PlanStartedData",
    "PlanProgressData",
    "PlanGeneratedData",
    # Agent lifecycle
    "ActivateAgentData",
    "DeactivateAgentData",
    "AgentThinkingData",
    # Step execution
    "StepStartedData",
    "StepProgressData",
    "StepCompletedData",
    "StepFailedData",
    # Toolkit events
    "ActivateToolkitData",
    "DeactivateToolkitData",
    # Tool-specific events
    "TerminalData",
    "BrowserActionData",
    "WriteFileData",
    # User interaction
    "AskData",
    "NoticeData",
    "HumanResponseData",
    # Memory events
    "MemoryQueryData",
    "MemoryResultData",
    # System events
    "HeartbeatData",
    "ErrorData",
    "EndData",
    "ContextWarningData",
    # SSE utilities
    "sse_json",
    "sse_action",
    "sse_comment",
    "sse_heartbeat",
    "SSEEmitter",
    # Toolkit decorators
    "listen_toolkit",
    "auto_listen_toolkit",
    "set_process_task",
    "process_task",
    "EXCLUDED_METHODS",
]
