"""
Server-Sent Events (SSE) Formatting Utilities.

Provides SSE message formatting and an SSEEmitter helper class
for real-time event streaming to clients.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, AsyncGenerator, Callable, Optional

from .action_types import (
    Action,
    ActionData,
    BaseActionData,
    ActivateAgentData,
    DeactivateAgentData,
    ActivateToolkitData,
    DeactivateToolkitData,
    TerminalData,
    BrowserActionData,
    StepStartedData,
    StepCompletedData,
    StepFailedData,
    HeartbeatData,
    EndData,
    ErrorData,
    NoticeData,
    AgentReportData,
    # Task decomposition
    TaskDecomposedData,
    SubtaskStateData,
    TaskReplannedData,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def sse_json(step: str, data: Any) -> str:
    """
    Format data as SSE JSON message.

    Args:
        step: Event type/step name (the action type)
        data: Event data (will be JSON serialized)

    Returns:
        SSE-formatted string: "data: {...}\n\n"
    """
    res_format = {"step": step, "data": data}
    return f"data: {json.dumps(res_format, ensure_ascii=False)}\n\n"


def sse_action(action_data: ActionData) -> str:
    """
    Format ActionData as SSE message.

    Args:
        action_data: Action data model instance

    Returns:
        SSE-formatted string with step and data
    """
    try:
        # Get action value (handle both enum and string)
        action_value = action_data.action
        if hasattr(action_value, 'value'):
            action_value = action_value.value

        # Serialize to dict
        data_dict = action_data.model_dump()

        return sse_json(action_value, data_dict)
    except Exception as e:
        logger.error(f"Error formatting SSE action: {e}")
        return sse_json("error", {"error": str(e)})


def sse_comment(comment: str) -> str:
    """
    Format SSE comment (for keep-alive).

    Comments are ignored by SSE parsers but keep the connection alive.

    Args:
        comment: Comment text

    Returns:
        SSE comment string: ": comment\n\n"
    """
    return f": {comment}\n\n"


def sse_heartbeat() -> str:
    """
    Generate SSE heartbeat message.

    Returns:
        SSE-formatted heartbeat event
    """
    return sse_json("heartbeat", {
        "message": "keep-alive",
        "timestamp": datetime.now().isoformat()
    })


class SSEEmitter:
    """
    Helper class for emitting SSE events.

    Can be used with asyncio.Queue for buffered event emission,
    or directly for immediate event formatting.

    Usage:
        # With queue (for streaming endpoint)
        queue = asyncio.Queue()
        emitter = SSEEmitter(queue)
        await emitter.emit_toolkit_activate("BrowserAgent", "BrowserToolkit", "click", "Clicking button")

        # Then consume from queue in streaming response
        while True:
            event = await queue.get()
            yield sse_action(event)
    """

    def __init__(self, queue: Optional['asyncio.Queue[ActionData]'] = None):
        """
        Initialize SSEEmitter.

        Args:
            queue: Optional asyncio.Queue for buffered emission.
                   If not provided, emit() will log a warning.
        """
        self.queue = queue
        self._closed = False
        self._task_id: Optional[str] = None
        self._agent_name: Optional[str] = None
        self._start_time: Optional[float] = None

    def configure(
        self,
        task_id: Optional[str] = None,
        agent_name: Optional[str] = None
    ) -> 'SSEEmitter':
        """
        Configure emitter with context.

        Args:
            task_id: Task ID for all emitted events
            agent_name: Default agent name for events

        Returns:
            Self for chaining
        """
        self._task_id = task_id
        self._agent_name = agent_name
        self._start_time = time.time()
        return self

    async def emit(self, action_data: ActionData) -> None:
        """
        Emit an action to the queue.

        Args:
            action_data: The action data to emit
        """
        if self._closed:
            logger.warning("Attempted to emit on closed SSEEmitter")
            return

        if self.queue is None:
            logger.warning("SSEEmitter has no queue configured")
            return

        # Add task_id if configured and not already set
        if self._task_id and not action_data.task_id:
            action_data.task_id = self._task_id

        await self.queue.put(action_data)

    async def emit_raw(self, event_dict: dict) -> None:
        """
        Emit a raw dictionary event (for backward compatibility).

        Converts dict to BaseActionData and emits.

        Args:
            event_dict: Dictionary with event data
        """
        if self._closed or self.queue is None:
            return

        # Try to determine action from event type
        event_type = event_dict.get("event", event_dict.get("action", "notice"))

        try:
            action = Action(event_type)
        except ValueError:
            action = Action.notice

        data = BaseActionData(
            action=action,
            task_id=self._task_id,
            **{k: v for k, v in event_dict.items() if k not in ["event", "action"]}
        )
        await self.queue.put(data)

    # ===== Convenience Methods for Common Events =====

    async def emit_agent_activate(
        self,
        agent_name: Optional[str] = None,
        agent_id: Optional[str] = None,
        message: str = ""
    ) -> None:
        """Emit agent activation event."""
        await self.emit(ActivateAgentData(
            agent_name=agent_name or self._agent_name or "Agent",
            agent_id=agent_id,
            process_task_id=self._task_id,
            message=message,
            task_id=self._task_id,
        ))

    async def emit_agent_deactivate(
        self,
        agent_name: Optional[str] = None,
        agent_id: Optional[str] = None,
        message: str = "",
        tokens_used: Optional[int] = None
    ) -> None:
        """Emit agent deactivation event."""
        duration = None
        if self._start_time:
            duration = time.time() - self._start_time

        await self.emit(DeactivateAgentData(
            agent_name=agent_name or self._agent_name or "Agent",
            agent_id=agent_id,
            process_task_id=self._task_id,
            message=message,
            tokens_used=tokens_used,
            duration_seconds=duration,
            task_id=self._task_id,
        ))

    async def emit_toolkit_activate(
        self,
        toolkit_name: str,
        method_name: str,
        input_preview: Optional[str] = None,
        message: str = "",
        agent_name: Optional[str] = None,
    ) -> None:
        """Emit toolkit activation event."""
        await self.emit(ActivateToolkitData(
            toolkit_name=toolkit_name,
            method_name=method_name,
            agent_name=agent_name or self._agent_name,
            process_task_id=self._task_id,
            input_preview=input_preview[:200] if input_preview else None,
            message=message,
            task_id=self._task_id,
        ))

    async def emit_toolkit_deactivate(
        self,
        toolkit_name: str,
        method_name: str,
        output_preview: Optional[str] = None,
        success: bool = True,
        duration_ms: Optional[int] = None,
        message: str = "",
        agent_name: Optional[str] = None,
    ) -> None:
        """Emit toolkit deactivation event."""
        await self.emit(DeactivateToolkitData(
            toolkit_name=toolkit_name,
            method_name=method_name,
            agent_name=agent_name or self._agent_name,
            process_task_id=self._task_id,
            output_preview=output_preview[:200] if output_preview else None,
            success=success,
            duration_ms=duration_ms,
            message=message,
            task_id=self._task_id,
        ))

    async def emit_terminal(
        self,
        command: str,
        output: Optional[str] = None,
        exit_code: Optional[int] = None,
        working_directory: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        """Emit terminal command event."""
        await self.emit(TerminalData(
            command=command,
            output=output[:2000] if output else None,  # Truncate long output
            exit_code=exit_code,
            working_directory=working_directory,
            duration_ms=duration_ms,
            task_id=self._task_id,
        ))

    async def emit_browser_action(
        self,
        action_type: str,
        target: Optional[str] = None,
        value: Optional[str] = None,
        success: bool = True,
        page_url: Optional[str] = None,
        page_title: Optional[str] = None,
        screenshot_url: Optional[str] = None,
        webview_id: Optional[str] = None,
    ) -> None:
        """Emit browser action event."""
        await self.emit(BrowserActionData(
            action_type=action_type,
            target=target,
            value=value,
            success=success,
            page_url=page_url,
            page_title=page_title,
            screenshot_url=screenshot_url,
            webview_id=webview_id,
            task_id=self._task_id,
        ))

    async def emit_step_started(
        self,
        step_index: int,
        step_name: str,
        step_description: Optional[str] = None,
    ) -> None:
        """Emit step started event."""
        await self.emit(StepStartedData(
            step_index=step_index,
            step_name=step_name,
            step_description=step_description,
            task_id=self._task_id,
        ))

    async def emit_step_completed(
        self,
        step_index: int,
        step_name: str,
        result: Optional[str] = None,
        duration_seconds: Optional[float] = None,
    ) -> None:
        """Emit step completed event."""
        await self.emit(StepCompletedData(
            step_index=step_index,
            step_name=step_name,
            result=result[:500] if result else None,
            duration_seconds=duration_seconds,
            task_id=self._task_id,
        ))

    async def emit_step_failed(
        self,
        step_index: int,
        step_name: str,
        error: str,
        recoverable: bool = True,
    ) -> None:
        """Emit step failed event."""
        await self.emit(StepFailedData(
            step_index=step_index,
            step_name=step_name,
            error=error,
            recoverable=recoverable,
            task_id=self._task_id,
        ))

    async def emit_notice(
        self,
        title: str,
        message: str,
        level: str = "info",
        duration_ms: Optional[int] = None,
    ) -> None:
        """Emit notice event."""
        await self.emit(NoticeData(
            level=level,
            title=title,
            message=message,
            duration_ms=duration_ms,
            task_id=self._task_id,
        ))

    async def emit_error(
        self,
        error: str,
        error_type: Optional[str] = None,
        recoverable: bool = True,
        details: Optional[dict] = None,
    ) -> None:
        """Emit error event."""
        await self.emit(ErrorData(
            error=error,
            error_type=error_type,
            recoverable=recoverable,
            details=details,
            task_id=self._task_id,
        ))

    async def emit_heartbeat(self) -> None:
        """Emit heartbeat event."""
        await self.emit(HeartbeatData(task_id=self._task_id))

    async def emit_agent_report(
        self,
        message: str,
        report_type: str = "info",
    ) -> None:
        """Emit agent report event for HomePage chat-style display.

        Args:
            message: Human-readable report message
            report_type: Type of report (info, success, warning, error, thinking)
        """
        await self.emit(AgentReportData(
            message=message,
            report_type=report_type,
            task_id=self._task_id,
        ))

    async def emit_end(
        self,
        status: str,
        message: Optional[str] = None,
        result: Optional[Any] = None,
    ) -> None:
        """Emit end event."""
        await self.emit(EndData(
            status=status,
            message=message,
            result=result,
            task_id=self._task_id,
        ))

    # ===== Task Decomposition Events =====

    async def emit_task_decomposed(
        self,
        subtasks: list,
        summary_task: Optional[str] = None,
        original_task_id: Optional[str] = None,
    ) -> None:
        """Emit task decomposed event (from TaskPlanningToolkit).

        Args:
            subtasks: List of subtask dicts with id, content, state
            summary_task: Main task summary
            original_task_id: ID of the parent task
        """
        await self.emit(TaskDecomposedData(
            subtasks=subtasks,
            summary_task=summary_task,
            original_task_id=original_task_id,
            total_subtasks=len(subtasks),
            task_id=self._task_id,
        ))

    async def emit_subtask_state(
        self,
        subtask_id: str,
        state: str,
        result: Optional[str] = None,
        failure_count: int = 0,
    ) -> None:
        """Emit subtask state change event.

        Args:
            subtask_id: ID of the subtask
            state: New state (OPEN, RUNNING, DONE, FAILED, DELETED)
            result: Optional result message
            failure_count: Number of failures
        """
        await self.emit(SubtaskStateData(
            subtask_id=subtask_id,
            state=state,
            result=result,
            failure_count=failure_count,
            task_id=self._task_id,
        ))

    async def emit_task_replanned(
        self,
        subtasks: list,
        original_task_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        """Emit task re-planned event.

        Args:
            subtasks: New list of subtasks
            original_task_id: ID of the parent task
            reason: Why the task was re-planned
        """
        await self.emit(TaskReplannedData(
            subtasks=subtasks,
            original_task_id=original_task_id,
            reason=reason,
            task_id=self._task_id,
        ))

    def close(self) -> None:
        """Mark emitter as closed."""
        self._closed = True

    @property
    def is_closed(self) -> bool:
        """Check if emitter is closed."""
        return self._closed


async def sse_stream_generator(
    queue: 'asyncio.Queue[ActionData]',
    timeout_seconds: int = 300,
    heartbeat_interval: int = 30,
    is_disconnected: Optional[Callable[[], bool]] = None,
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields SSE-formatted events from a queue.

    Args:
        queue: Queue to consume events from
        timeout_seconds: Total timeout for the stream (default 5 minutes)
        heartbeat_interval: Seconds between heartbeat checks (default 30)
        is_disconnected: Optional callback to check client disconnection

    Yields:
        SSE-formatted strings
    """
    start_time = time.time()

    try:
        while True:
            # Check total timeout
            elapsed = time.time() - start_time
            if elapsed >= timeout_seconds:
                logger.info("SSE stream timeout reached")
                yield sse_action(EndData(status="timeout", message="Stream timeout"))
                break

            # Check client disconnection
            if is_disconnected and is_disconnected():
                logger.info("SSE client disconnected")
                break

            try:
                # Wait for event with heartbeat interval timeout
                event = await asyncio.wait_for(
                    queue.get(),
                    timeout=heartbeat_interval
                )

                # Yield SSE-formatted event
                yield sse_action(event)

                # Check for terminal events
                if hasattr(event, 'action'):
                    action = event.action
                    if hasattr(action, 'value'):
                        action = action.value
                    if action in (
                        "end", "task_completed", "task_failed", "task_cancelled"
                    ):
                        break

            except asyncio.TimeoutError:
                # No event within interval, send heartbeat
                yield sse_heartbeat()

    except asyncio.CancelledError:
        logger.info("SSE stream cancelled")
    except Exception as e:
        logger.error(f"SSE stream error: {e}")
        yield sse_action(ErrorData(error=str(e), recoverable=False))
