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
    # Task decomposition
    TaskDecomposedData,
    SubtaskStateData,
    TaskReplannedData,
    StreamingDecomposeData,
    DecomposeProgressData,
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
    WaitConfirmData,
    ConfirmedData,
    AgentReportData,
    # Memory events
    MemoryQueryData,
    MemoryResultData,
    MemoryLevelData,
    MemoryEventData,
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
    AssignTaskData,
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
    # Task decomposition
    "TaskDecomposedData",
    "SubtaskStateData",
    "TaskReplannedData",
    "StreamingDecomposeData",
    "DecomposeProgressData",
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
    "WaitConfirmData",
    "ConfirmedData",
    "AgentReportData",
    # Memory events
    "MemoryQueryData",
    "MemoryResultData",
    "MemoryLevelData",
    "MemoryEventData",
    # System events
    "HeartbeatData",
    "ErrorData",
    "EndData",
    "ContextWarningData",
    # Workforce events
    "WorkforceStartedData",
    "WorkforceCompletedData",
    "WorkforceStoppedData",
    "WorkerAssignedData",
    "WorkerStartedData",
    "WorkerCompletedData",
    "WorkerFailedData",
    "DynamicTasksAddedData",
    "AssignTaskData",
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
