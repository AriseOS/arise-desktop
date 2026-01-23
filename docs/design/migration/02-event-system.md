# Feature 2: Event System & Message Queue (17+ Action Types + SSE)

## Current State Analysis

### Eigent Implementation

**Location:** `third-party/eigent/backend/app/service/task.py` (lines 18-48)

Eigent defines 27+ action types via enum:

```python
class Action(str, Enum):
    # User -> Backend (Input Actions)
    improve = "improve"           # New task/question from user
    update_task = "update_task"   # Modify existing task
    start = "start"               # Start execution
    stop = "stop"                 # Stop execution
    supplement = "supplement"     # Add supplementary info
    pause = "pause"               # Pause execution
    resume = "resume"             # Resume execution
    new_agent = "new_agent"       # Create new agent
    add_task = "add_task"         # Add sub-task
    remove_task = "remove_task"   # Remove sub-task
    skip_task = "skip_task"       # Skip current task

    # Backend -> User (Output Events)
    task_state = "task_state"                 # Full task state update
    new_task_state = "new_task_state"         # New task created
    decompose_progress = "decompose_progress" # Plan decomposition progress
    decompose_text = "decompose_text"         # Plan decomposition text
    create_agent = "create_agent"             # Agent created
    activate_agent = "activate_agent"         # Agent started working
    deactivate_agent = "deactivate_agent"     # Agent finished
    assign_task = "assign_task"               # Task assigned to agent
    activate_toolkit = "activate_toolkit"     # Tool started
    deactivate_toolkit = "deactivate_toolkit" # Tool finished
    write_file = "write_file"                 # File written
    ask = "ask"                               # Asking user for input
    notice = "notice"                         # Notification message
    search_mcp = "search_mcp"                 # MCP search event
    install_mcp = "install_mcp"               # MCP install event
    terminal = "terminal"                     # Terminal output
    end = "end"                               # Task ended
    budget_not_enough = "budget_not_enough"   # Budget exceeded
```

**SSE Implementation:**

```python
# SSE JSON format
def sse_json(step: str, data):
    res_format = {"step": step, "data": data}
    return f"data: {json.dumps(res_format, ensure_ascii=False)}\n\n"

# Usage in streaming response
yield sse_json("task_state", item.data)
yield sse_json("activate_toolkit", {...})
yield sse_json("end", end_message)
```

**Queue-based Architecture:**

```python
class TaskLock:
    queue: asyncio.Queue[ActionData]
    """Queue monitoring for SSE response"""

    async def put_queue(self, data: ActionData):
        await self.queue.put(data)

    async def get_queue(self):
        return await self.queue.get()
```

### 2ami Current State

**Location:** `src/clients/desktop_app/ami_daemon/services/quick_task_service.py` (lines 229-257)

Current implementation uses asyncio.Queue but not SSE:

```python
@dataclass
class TaskState:
    _progress_queue: asyncio.Queue = field(default_factory=asyncio.Queue)

# Events pushed to queue
await state._progress_queue.put({
    "type": "task_started",
    "task_id": state.task_id,
    "message": f"Starting task: {state.task}"
})
```

**Current Event Types (Limited):**
- `task_started`
- `plan_generated`
- `step_started` / `step_completed` / `step_failed`
- `tool_call`
- `task_completed` / `task_failed` / `task_cancelled`
- `heartbeat`

**Missing:**
- No activate/deactivate_agent events
- No activate/deactivate_toolkit events
- No terminal events for command output
- No budget/notice events
- No proper SSE format (just JSON dicts)

---

## Implementation Plan

### Step 1: Define Action Enum

**File:** `src/clients/desktop_app/ami_daemon/base_agent/events/action_types.py` (NEW)

```python
"""
Event action types for real-time communication.
Based on Eigent's event system with 2ami-specific additions.
"""
from enum import Enum
from typing import Literal, Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime


class Action(str, Enum):
    """All supported action types for event system"""

    # ===== User -> Backend (Input Actions) =====
    improve = "improve"           # New task/question from user
    update_task = "update_task"   # Modify existing task
    start = "start"               # Start execution
    stop = "stop"                 # Stop execution
    pause = "pause"               # Pause execution
    resume = "resume"             # Resume execution
    supplement = "supplement"     # Add supplementary info
    human_response = "human_response"  # Human response to ask

    # ===== Backend -> User (Output Events) =====
    # Task lifecycle
    task_state = "task_state"               # Full task state update
    new_task_state = "new_task_state"       # New task created
    task_completed = "task_completed"       # Task finished successfully
    task_failed = "task_failed"             # Task failed
    task_cancelled = "task_cancelled"       # Task cancelled

    # Planning
    plan_started = "plan_started"           # Planning started
    plan_progress = "plan_progress"         # Planning progress update
    plan_generated = "plan_generated"       # Plan complete

    # Agent lifecycle
    activate_agent = "activate_agent"       # Agent started working
    deactivate_agent = "deactivate_agent"   # Agent finished
    agent_thinking = "agent_thinking"       # Agent is thinking

    # Step execution
    step_started = "step_started"           # Step execution started
    step_progress = "step_progress"         # Step progress update
    step_completed = "step_completed"       # Step completed
    step_failed = "step_failed"             # Step failed

    # Toolkit events
    activate_toolkit = "activate_toolkit"   # Tool started
    deactivate_toolkit = "deactivate_toolkit"  # Tool finished

    # Specific tool events
    terminal = "terminal"                   # Terminal command output
    browser_action = "browser_action"       # Browser action performed
    write_file = "write_file"               # File written

    # User interaction
    ask = "ask"                             # Asking user for input
    notice = "notice"                       # Notification message
    context_too_long = "context_too_long"   # Context exceeded limit

    # System events
    heartbeat = "heartbeat"                 # Keep-alive signal
    error = "error"                         # Error occurred
    end = "end"                             # Stream ended


# ===== Action Data Models =====

class BaseActionData(BaseModel):
    """Base class for all action data"""
    action: Action
    timestamp: str = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


class ActionActivateAgentData(BaseActionData):
    """Agent activation event"""
    action: Literal[Action.activate_agent] = Action.activate_agent
    data: Dict[Literal["agent_name", "process_task_id", "agent_id", "message"], str]


class ActionDeactivateAgentData(BaseActionData):
    """Agent deactivation event"""
    action: Literal[Action.deactivate_agent] = Action.deactivate_agent
    data: Dict[str, Any]  # agent_name, agent_id, process_task_id, message, tokens


class ActionActivateToolkitData(BaseActionData):
    """Toolkit activation event"""
    action: Literal[Action.activate_toolkit] = Action.activate_toolkit
    data: Dict[Literal["agent_name", "toolkit_name", "process_task_id", "method_name", "message"], str]


class ActionDeactivateToolkitData(BaseActionData):
    """Toolkit deactivation event"""
    action: Literal[Action.deactivate_toolkit] = Action.deactivate_toolkit
    data: Dict[Literal["agent_name", "toolkit_name", "process_task_id", "method_name", "message"], str]


class ActionTerminalData(BaseActionData):
    """Terminal output event"""
    action: Literal[Action.terminal] = Action.terminal
    data: Dict[Literal["command", "output", "exit_code", "working_directory"], Any]


class ActionAskData(BaseActionData):
    """Ask user event"""
    action: Literal[Action.ask] = Action.ask
    data: Dict[Literal["question", "options", "timeout"], Any]


class ActionStepData(BaseActionData):
    """Step execution event"""
    action: Action  # step_started, step_completed, step_failed
    data: Dict[str, Any]  # step_index, step_name, status, result, error


class ActionPlanData(BaseActionData):
    """Plan event"""
    action: Action  # plan_started, plan_progress, plan_generated
    data: Dict[str, Any]  # steps, progress, total


class ActionEndData(BaseActionData):
    """End event"""
    action: Literal[Action.end] = Action.end
    data: Dict[Literal["status", "message", "result"], Any]


# Type alias for all action data types
ActionData = (
    ActionActivateAgentData |
    ActionDeactivateAgentData |
    ActionActivateToolkitData |
    ActionDeactivateToolkitData |
    ActionTerminalData |
    ActionAskData |
    ActionStepData |
    ActionPlanData |
    ActionEndData |
    BaseActionData
)
```

### Step 2: Implement SSE Formatter

**File:** `src/clients/desktop_app/ami_daemon/base_agent/events/sse.py` (NEW)

```python
"""
Server-Sent Events (SSE) formatting utilities.
"""
import json
from typing import Any, Dict, Optional
from .action_types import Action, ActionData


def sse_json(step: str, data: Any) -> str:
    """
    Format data as SSE JSON message.

    Args:
        step: Event type/step name
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
        SSE-formatted string
    """
    return sse_json(action_data.action.value, action_data.model_dump())


def sse_comment(comment: str) -> str:
    """
    Format SSE comment (for keep-alive).

    Args:
        comment: Comment text

    Returns:
        SSE comment string: ": comment\n\n"
    """
    return f": {comment}\n\n"


def sse_heartbeat() -> str:
    """Generate SSE heartbeat message"""
    return sse_json("heartbeat", {"message": "keep-alive"})


class SSEEmitter:
    """
    Helper class for emitting SSE events.
    Can be used as async generator for StreamingResponse.
    """

    def __init__(self, queue: 'asyncio.Queue[ActionData]'):
        self.queue = queue
        self._closed = False

    async def emit(self, action_data: ActionData) -> None:
        """Emit an action to the queue"""
        if not self._closed:
            await self.queue.put(action_data)

    async def emit_toolkit_activate(
        self,
        agent_name: str,
        toolkit_name: str,
        method_name: str,
        message: str,
        process_task_id: str = ""
    ) -> None:
        """Convenience method for toolkit activation"""
        from .action_types import ActionActivateToolkitData
        await self.emit(ActionActivateToolkitData(
            data={
                "agent_name": agent_name,
                "toolkit_name": toolkit_name,
                "method_name": method_name,
                "message": message,
                "process_task_id": process_task_id
            }
        ))

    async def emit_toolkit_deactivate(
        self,
        agent_name: str,
        toolkit_name: str,
        method_name: str,
        message: str,
        process_task_id: str = ""
    ) -> None:
        """Convenience method for toolkit deactivation"""
        from .action_types import ActionDeactivateToolkitData
        await self.emit(ActionDeactivateToolkitData(
            data={
                "agent_name": agent_name,
                "toolkit_name": toolkit_name,
                "method_name": method_name,
                "message": message,
                "process_task_id": process_task_id
            }
        ))

    async def emit_terminal(
        self,
        command: str,
        output: str,
        exit_code: int,
        working_directory: str
    ) -> None:
        """Convenience method for terminal output"""
        from .action_types import ActionTerminalData
        await self.emit(ActionTerminalData(
            data={
                "command": command,
                "output": output,
                "exit_code": exit_code,
                "working_directory": working_directory
            }
        ))

    def close(self) -> None:
        """Mark emitter as closed"""
        self._closed = True
```

### Step 3: Update TaskState with Event Queue

**File:** `src/clients/desktop_app/ami_daemon/services/quick_task_service.py`

```python
from ..base_agent.events.action_types import Action, ActionData, BaseActionData
from ..base_agent.events.sse import SSEEmitter

@dataclass
class TaskState:
    # ... existing fields ...

    # Event queue for SSE streaming
    _event_queue: asyncio.Queue[ActionData] = field(default_factory=asyncio.Queue)
    _sse_emitter: Optional[SSEEmitter] = None

    def __post_init__(self):
        self._sse_emitter = SSEEmitter(self._event_queue)

    @property
    def emitter(self) -> SSEEmitter:
        """Get SSE emitter for this task"""
        return self._sse_emitter

    async def put_event(self, event: ActionData) -> None:
        """Put event into queue for SSE streaming"""
        await self._event_queue.put(event)

    async def get_event(self) -> ActionData:
        """Get next event from queue"""
        return await self._event_queue.get()
```

### Step 4: Implement SSE Streaming Endpoint

**File:** `src/clients/desktop_app/ami_daemon/routers/quick_task.py`

```python
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from ..base_agent.events.sse import sse_action, sse_heartbeat
from ..base_agent.events.action_types import Action
import asyncio
import time

SSE_TIMEOUT_SECONDS = 300  # 5 minutes

router = APIRouter()


async def sse_stream_wrapper(
    state: TaskState,
    request: Request,
    timeout_seconds: int = SSE_TIMEOUT_SECONDS
):
    """
    Wrap event queue as SSE stream with timeout handling.

    Closes the SSE connection if:
    - No data is received within timeout period
    - Client disconnects
    - End event is received
    """
    last_data_time = time.time()

    try:
        while True:
            # Check client disconnection
            if await request.is_disconnected():
                break

            elapsed = time.time() - last_data_time
            remaining_timeout = timeout_seconds - elapsed

            if remaining_timeout <= 0:
                # Timeout - send heartbeat and reset
                yield sse_heartbeat()
                last_data_time = time.time()
                continue

            try:
                event = await asyncio.wait_for(
                    state.get_event(),
                    timeout=min(remaining_timeout, 30.0)  # Check every 30s
                )
                last_data_time = time.time()

                # Yield SSE-formatted event
                yield sse_action(event)

                # Check for terminal events
                if event.action in (Action.end, Action.task_completed,
                                    Action.task_failed, Action.task_cancelled):
                    break

            except asyncio.TimeoutError:
                # No event within check interval, send heartbeat
                yield sse_heartbeat()
                last_data_time = time.time()

    except asyncio.CancelledError:
        pass
    finally:
        state.emitter.close()


@router.post("/task/{task_id}/stream")
async def stream_task_events(task_id: str, request: Request):
    """
    SSE endpoint for streaming task events.

    Returns Server-Sent Events stream with real-time updates.
    """
    state = quick_task_service.get_task_state(task_id)
    if not state:
        return {"error": "Task not found"}

    return StreamingResponse(
        sse_stream_wrapper(state, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.post("/chat")
async def chat(data: ChatRequest, request: Request):
    """
    Main chat endpoint with SSE streaming.
    Creates or continues a task and returns SSE stream.
    """
    # Get or create task
    state = await quick_task_service.get_or_create_task(
        project_id=data.project_id,
        task_id=data.task_id,
        question=data.question
    )

    # Start task processing in background
    asyncio.create_task(
        quick_task_service.process_task(state)
    )

    # Return SSE stream
    return StreamingResponse(
        sse_stream_wrapper(state, request),
        media_type="text/event-stream"
    )
```

### Step 5: Emit Events in Agent Execution

**File:** `src/clients/desktop_app/ami_daemon/base_agent/agents/eigent_style_browser_agent.py`

```python
from ..events.action_types import (
    Action, ActionActivateAgentData, ActionDeactivateAgentData,
    ActionActivateToolkitData, ActionDeactivateToolkitData,
    ActionStepData, ActionEndData
)

class EigentStyleBrowserAgent:

    async def _emit_agent_activate(self, message: str = "") -> None:
        """Emit agent activation event"""
        if self._state and self._state.emitter:
            await self._state.emitter.emit(ActionActivateAgentData(
                data={
                    "agent_name": self.agent_name,
                    "agent_id": self.agent_id,
                    "process_task_id": self._current_task_id,
                    "message": message
                }
            ))

    async def _emit_agent_deactivate(self, message: str = "", tokens: int = 0) -> None:
        """Emit agent deactivation event"""
        if self._state and self._state.emitter:
            await self._state.emitter.emit(ActionDeactivateAgentData(
                data={
                    "agent_name": self.agent_name,
                    "agent_id": self.agent_id,
                    "process_task_id": self._current_task_id,
                    "message": message,
                    "tokens": tokens
                }
            ))

    async def _emit_step_started(self, step_index: int, step_name: str) -> None:
        """Emit step started event"""
        if self._state and self._state.emitter:
            await self._state.emitter.emit(ActionStepData(
                action=Action.step_started,
                data={
                    "step_index": step_index,
                    "step_name": step_name,
                    "status": "started"
                }
            ))

    async def _emit_step_completed(self, step_index: int, step_name: str, result: Any) -> None:
        """Emit step completed event"""
        if self._state and self._state.emitter:
            await self._state.emitter.emit(ActionStepData(
                action=Action.step_completed,
                data={
                    "step_index": step_index,
                    "step_name": step_name,
                    "status": "completed",
                    "result": str(result)[:500]  # Truncate result
                }
            ))
```

---

## Migration Checklist

- [ ] Create `events/` package directory
- [ ] Create `action_types.py` with Action enum (27+ types)
- [ ] Create all ActionData pydantic models
- [ ] Create `sse.py` with SSE formatting utilities
- [ ] Create `SSEEmitter` helper class
- [ ] Update `TaskState` with event queue
- [ ] Add SSE streaming endpoint `/task/{id}/stream`
- [ ] Add main chat endpoint with SSE `/chat`
- [ ] Integrate event emission in agent execution
- [ ] Integrate event emission in toolkit execution
- [ ] Add terminal event emission in TerminalToolkit
- [ ] Add browser action event emission
- [ ] Add heartbeat handling
- [ ] Add client disconnection handling
- [ ] Add unit tests for SSE formatting
- [ ] Add integration tests for event streaming

---

## Event Flow Diagram

```
User Request
     │
     ▼
┌─────────────────┐
│  /chat endpoint │
│  (FastAPI)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│  TaskState      │────▶│  asyncio.Queue  │
│  (state holder) │     │  (event buffer) │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│  Agent/Toolkit  │     │  SSE Stream     │
│  (emit events)  │────▶│  (to client)    │
└─────────────────┘     └─────────────────┘

Events emitted:
1. task_state (initial)
2. activate_agent
3. step_started
4. activate_toolkit (tool call)
5. terminal (command output)
6. deactivate_toolkit
7. step_completed
8. deactivate_agent
9. task_completed / end
```

---

## Testing Strategy

1. **Unit Tests:**
   - Test SSE JSON formatting
   - Test Action enum completeness
   - Test ActionData serialization

2. **Integration Tests:**
   - Test SSE streaming endpoint
   - Test event queue flow
   - Test timeout and heartbeat
   - Test client disconnection handling

3. **Manual Testing:**
   - Use curl to test SSE endpoint
   - Verify all event types are emitted
   - Verify event ordering is correct
