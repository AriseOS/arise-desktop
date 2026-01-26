"""
Quick Task API

Independent task execution interface, separate from Workflow.
Users input natural language tasks, and the Agent completes them autonomously.

Memory-Guided Planning:
- Queries memory for similar workflow paths before execution
- Uses retrieved paths to guide plan generation

Streaming:
- SSE endpoint for typed event streaming
- WebSocket for bidirectional communication (human interaction)
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import asyncio
import logging
import os

from ..services.quick_task_service import QuickTaskService, TaskStatus
from ..core.config_service import get_config
from ..base_agent.events import sse_action, sse_heartbeat, Action, EndData

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/quick-task", tags=["Quick Task"])

# Load config for LLM settings
config = get_config()

# Service instance
_service: Optional[QuickTaskService] = None
# CloudClient reference (set by daemon.py)
_cloud_client = None


def get_service() -> QuickTaskService:
    global _service, _cloud_client
    if _service is None:
        _service = QuickTaskService(cloud_client=_cloud_client)
    return _service


def set_cloud_client(cloud_client):
    """Set CloudClient for memory API calls.

    Called by daemon.py during startup to inject the CloudClient instance.
    """
    global _cloud_client, _service
    _cloud_client = cloud_client
    if _service is not None:
        _service.set_cloud_client(cloud_client)
    logger.info("QuickTask router: CloudClient configured for memory queries")


# ============== Request/Response Models ==============

class TaskRequest(BaseModel):
    """Task execution request"""
    task: str = Field(..., description="Task description", min_length=1, max_length=2000)
    headless: bool = Field(False, description="Run browser in headless mode")


class TaskResponse(BaseModel):
    """Task submission response"""
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    """Task status response"""
    task_id: str
    status: str
    plan: Optional[List] = None
    current_step: Optional[Dict] = None
    progress: float = 0.0
    error: Optional[str] = None


class TaskResultResponse(BaseModel):
    """Task result response"""
    task_id: str
    success: bool
    output: Any = None
    plan: List = []
    steps_executed: int = 0
    total_steps: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    action_history: List = []


class WorkspaceFilesResponse(BaseModel):
    """Workspace files listing response"""
    task_id: str
    workspace: str
    files: List[str]
    total_size_bytes: int


class WorkspaceCleanupResponse(BaseModel):
    """Workspace cleanup response"""
    task_id: str
    cleaned: bool
    message: str
    freed_bytes: Optional[int] = None


class TaskListItem(BaseModel):
    """Single task in the task list"""
    task_id: str
    task: str
    status: str
    progress: float = 0.0
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    # New fields for history display
    loop_iterations: int = 0
    tools_called_count: int = 0
    has_result: bool = False
    has_error: bool = False


class TaskListResponse(BaseModel):
    """Task list response"""
    tasks: List[TaskListItem]
    total: int
    running: int
    completed: int
    failed: int


# ============== REST Endpoints ==============

@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    status: Optional[str] = None,
    limit: int = 50,
):
    """
    List all tasks with optional status filter.

    Query params:
    - status: Filter by status (pending, running, completed, failed, cancelled)
    - limit: Maximum number of tasks to return (default 50)

    Returns list of tasks sorted by creation time (newest first).
    """
    service = get_service()
    tasks_dict = service._tasks

    task_list = []
    running_count = 0
    completed_count = 0
    failed_count = 0

    for task_id, state in tasks_dict.items():
        # Count by status
        if state.status == TaskStatus.RUNNING:
            running_count += 1
        elif state.status == TaskStatus.COMPLETED:
            completed_count += 1
        elif state.status == TaskStatus.FAILED:
            failed_count += 1

        # Filter by status if provided
        if status and state.status.value != status:
            continue

        task_list.append(TaskListItem(
            task_id=state.task_id,
            task=state.task[:200] if state.task else "",  # Truncate long task descriptions
            status=state.status.value,
            progress=state.progress,
            created_at=state.created_at.isoformat() if state.created_at else "",
            started_at=state.started_at.isoformat() if state.started_at else None,
            completed_at=state.completed_at.isoformat() if state.completed_at else None,
            user_id=state.user_id,
            project_id=state.project_id,
            # New fields
            loop_iterations=state.loop_iteration,
            tools_called_count=len(state.tools_called) if state.tools_called else 0,
            has_result=state.result is not None,
            has_error=state.error is not None,
        ))

    # Sort by created_at (newest first)
    task_list.sort(key=lambda x: x.created_at, reverse=True)

    # Apply limit
    task_list = task_list[:limit]

    return TaskListResponse(
        tasks=task_list,
        total=len(tasks_dict),
        running=running_count,
        completed=completed_count,
        failed=failed_count,
    )


@router.post("/execute", response_model=TaskResponse)
async def execute_task(
    request: TaskRequest,
    x_ami_api_key: Optional[str] = Header(default=None, alias="X-Ami-API-Key"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """
    Submit task for execution.

    Headers:
    - X-Ami-API-Key: User's Ami API key (ami_xxxxx format). Required for LLM calls via CRS.
    - X-User-Id: User ID for memory queries (optional but recommended).

    Returns task_id, which can be used for:
    - GET /status/{task_id} to check status
    - GET /result/{task_id} to get result
    - WebSocket /ws/{task_id} for real-time progress
    """
    service = get_service()

    # Get LLM config from app config
    use_proxy = config.get('llm.use_proxy', True)
    proxy_url = config.get('llm.proxy_url', 'https://api.ariseos.com/api')
    llm_model = config.get('llm.model', 'claude-sonnet-4-5-20250929')

    # TODO: Temporarily hardcode user_id for memory queries
    # Will add proper user_id from frontend later
    user_id = x_user_id or "shenyouren"

    # Configure LLM - use X-Ami-API-Key with CRS proxy
    if x_ami_api_key:
        # Set API key on cloud_client for memory queries (same as daemon.py pattern)
        if _cloud_client:
            _cloud_client.set_user_api_key(x_ami_api_key)

        if use_proxy:
            # Use CRS (Claude Relay Service) proxy
            service.configure_llm(
                api_key=x_ami_api_key,
                model=llm_model,
                base_url=proxy_url,
                user_id=user_id
            )
            logger.info(f"Quick Task using CRS proxy: {proxy_url}, user_id: {user_id}")
        else:
            # Direct API call (not recommended for production)
            service.configure_llm(api_key=x_ami_api_key, model=llm_model, user_id=user_id)
            logger.info(f"Quick Task using direct Anthropic API, user_id: {user_id}")
    else:
        # Fallback to environment variable (for local development)
        env_api_key = os.environ.get("ANTHROPIC_API_KEY")
        if env_api_key:
            service.configure_llm(api_key=env_api_key, model=llm_model, user_id=user_id)
            logger.warning(f"Using ANTHROPIC_API_KEY env var (no X-Ami-API-Key header), user_id: {user_id}")
        else:
            logger.warning("No API key provided - LLM calls will fail")

    try:
        task_id = await service.submit_task(
            task=request.task,
            headless=request.headless,
        )

        return TaskResponse(
            task_id=task_id,
            status="started",
            message="Task submitted successfully"
        )

    except Exception as e:
        logger.exception(f"Failed to submit task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """Query task status."""
    service = get_service()
    status = await service.get_status(task_id)

    if status is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return status


@router.get("/result/{task_id}", response_model=TaskResultResponse)
async def get_task_result(task_id: str):
    """Get task result."""
    service = get_service()
    result = await service.get_result(task_id)

    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return result


@router.post("/cancel/{task_id}")
async def cancel_task(task_id: str):
    """Cancel a task."""
    service = get_service()
    success = await service.cancel_task(task_id)

    if not success:
        raise HTTPException(status_code=404, detail="Task not found or already completed")

    return {"message": "Task cancelled"}


# ============== Task Detail Endpoint (Eigent Migration) ==============

class ConversationEntryResponse(BaseModel):
    """Single conversation entry"""
    role: str
    content: Any
    timestamp: str


class ToolkitEventResponse(BaseModel):
    """Toolkit event for history display"""
    toolkit_name: str
    method_name: str
    status: str  # running, completed, failed
    input_preview: Optional[str] = None
    output_preview: Optional[str] = None
    timestamp: str
    duration_ms: Optional[int] = None


class ThinkingLogResponse(BaseModel):
    """Agent thinking/reasoning log"""
    content: str
    step: int
    agent_name: str
    timestamp: str


class TaskDetailResponse(BaseModel):
    """
    Complete task detail for restoration/replay.

    Contains all data needed to restore a task in the frontend:
    - Basic task info
    - Conversation history (messages)
    - Toolkit events (tool calls)
    - Thinking logs (agent reasoning)
    - Execution results
    """
    task_id: str
    task: str
    status: str
    progress: float

    # Timestamps
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    # Execution state
    loop_iterations: int
    current_step: Optional[Dict] = None

    # Conversation history
    messages: List[ConversationEntryResponse]

    # Toolkit events (for AgentTab timeline)
    toolkit_events: List[ToolkitEventResponse]

    # Thinking logs (for AgentTab timeline)
    thinking_logs: List[ThinkingLogResponse]

    # Results
    result: Optional[Any] = None
    error: Optional[str] = None
    notes_content: Optional[str] = None

    # User/Project info
    user_id: str
    project_id: str


@router.get("/{task_id}/detail", response_model=TaskDetailResponse)
async def get_task_detail(task_id: str):
    """
    Get complete task detail for restoration/replay.

    This endpoint returns all data needed to restore a task in the frontend,
    similar to Eigent's replay functionality.

    Used when:
    - User clicks on a history task that's not in memory
    - Page refresh and need to restore task state
    - Viewing completed task details
    """
    service = get_service()
    state = service._tasks.get(task_id)

    if not state:
        raise HTTPException(status_code=404, detail="Task not found")

    # Convert conversation history to response format
    messages = []
    for entry in state.conversation_history:
        messages.append(ConversationEntryResponse(
            role=entry.role,
            content=entry.content,
            timestamp=entry.timestamp,
        ))

    # Use persisted toolkit_events from state (detailed format)
    toolkit_events = []
    for event in state.toolkit_events:
        toolkit_events.append(ToolkitEventResponse(
            toolkit_name=event.get("toolkit_name", "Unknown"),
            method_name=event.get("method_name", "unknown"),
            status=event.get("status", "completed"),
            input_preview=event.get("input_preview"),
            output_preview=event.get("output_preview"),
            timestamp=event.get("timestamp", state.created_at.isoformat()),
            duration_ms=event.get("duration_ms"),
        ))

    # Use persisted thinking_logs from state
    thinking_logs = []
    for log in state.thinking_logs:
        thinking_logs.append(ThinkingLogResponse(
            content=log.get("content", ""),
            step=log.get("step", 0),
            agent_name=log.get("agent_name", "browser_agent"),
            timestamp=log.get("timestamp", state.created_at.isoformat()),
        ))

    return TaskDetailResponse(
        task_id=state.task_id,
        task=state.task,
        status=state.status.value,
        progress=state.progress,
        created_at=state.created_at.isoformat(),
        started_at=state.started_at.isoformat() if state.started_at else None,
        completed_at=state.completed_at.isoformat() if state.completed_at else None,
        loop_iterations=state.loop_iteration,
        current_step=state.current_step,
        messages=messages,
        toolkit_events=toolkit_events,
        thinking_logs=thinking_logs,
        result=state.result,
        error=state.error,
        notes_content=state.notes_content,
        user_id=state.user_id,
        project_id=state.project_id,
    )


class MessageRequest(BaseModel):
    """Message from client to server (used with SSE for bidirectional communication)."""
    type: str = Field(..., description="Message type")
    response: Optional[str] = Field(None, description="Human response text")


@router.post("/message/{task_id}")
async def send_message(task_id: str, request: MessageRequest):
    """
    Send a message to a running task.

    Used with SSE streaming to provide bidirectional communication.
    Currently supports:
    - human_response: Provide human response to agent question

    Args:
        task_id: Task ID
        request: Message data with type and payload
    """
    service = get_service()
    state = service._tasks.get(task_id)

    if not state:
        raise HTTPException(status_code=404, detail="Task not found")

    if request.type == "human_response":
        if request.response is None:
            raise HTTPException(status_code=400, detail="Response text required")

        success = await service.provide_human_response(task_id, request.response)
        if success:
            logger.info(f"Human response received for task {task_id}")
            return {"success": True, "message": "Response delivered"}
        else:
            raise HTTPException(status_code=400, detail="Failed to deliver response - no pending question")
    else:
        raise HTTPException(status_code=400, detail=f"Unknown message type: {request.type}")


# ============== Subtask Confirmation Endpoints (Eigent Migration) ==============

class SubtaskConfirmRequest(BaseModel):
    """Request to confirm subtask execution."""
    subtasks: List[Dict[str, Any]] = Field(..., description="Edited subtasks to confirm")


@router.post("/{task_id}/confirm-subtasks")
async def confirm_subtasks(task_id: str, request: SubtaskConfirmRequest):
    """
    Confirm subtask execution plan.

    After task decomposition, the frontend displays subtasks for user review.
    This endpoint confirms the plan and allows execution to proceed.

    Args:
        task_id: Task ID
        request: Confirmed subtasks (may be edited by user)
    """
    service = get_service()
    state = service._tasks.get(task_id)

    if not state:
        raise HTTPException(status_code=404, detail="Task not found")

    # Store confirmed subtasks in state and trigger the confirmation event
    state.plan = request.subtasks
    state.confirm_subtasks(request.subtasks)  # This unblocks the agent
    logger.info(f"Subtasks confirmed for task {task_id}: {len(request.subtasks)} subtasks")

    return {"success": True, "message": "Subtasks confirmed", "subtask_count": len(request.subtasks)}


@router.post("/{task_id}/cancel-subtasks")
async def cancel_subtasks(task_id: str):
    """
    Cancel subtask execution plan.

    User rejected the proposed plan. This will:
    1. Clear the plan
    2. Mark subtasks as cancelled
    3. Unblock the agent's wait_for_subtask_confirmation() call
    4. Agent will see cancelled=True and stop execution
    """
    service = get_service()
    state = service._tasks.get(task_id)

    if not state:
        raise HTTPException(status_code=404, detail="Task not found")

    # Clear plan
    state.plan = []

    # Mark subtasks as cancelled (agent will check this flag)
    state._subtasks_cancelled = True

    # Set the confirmation event to unblock wait_for_subtask_confirmation()
    # The agent will check _subtasks_cancelled flag and stop execution
    state._subtask_confirmation_event.set()

    logger.info(f"Subtasks cancelled for task {task_id} - agent will be unblocked")

    return {"success": True, "message": "Subtasks cancelled"}


# ============== Workspace File Endpoints ==============

@router.get("/workspace/{task_id}/file/{file_path:path}")
async def get_workspace_file(task_id: str, file_path: str):
    """
    Get contents of a file in task's directory.

    Supports files in workspace/, notes/, and other task directories.

    Args:
        task_id: Task ID
        file_path: Relative path to file within task directory (e.g., "notes/task_plan.md" or "workspace/output/result.txt")
    """
    import os
    
    service = get_service()
    state = service._tasks.get(task_id)

    if not state:
        raise HTTPException(status_code=404, detail="Task not found")

    if not state._dir_manager:
        raise HTTPException(status_code=404, detail="Task has no directory manager")

    task_root = state._dir_manager.task_root

    # Resolve file path relative to task_root
    full_path = os.path.join(task_root, file_path)

    # Security: ensure path is within task_root
    real_task_root = os.path.realpath(task_root)
    real_file = os.path.realpath(full_path)
    if not real_file.startswith(real_task_root):
        raise HTTPException(status_code=403, detail="Access denied - path outside task directory")

    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")

    if not os.path.isfile(full_path):
        raise HTTPException(status_code=400, detail="Path is not a file")

    try:
        # Try to read as text first
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return {
            "task_id": task_id,
            "file_path": file_path,
            "content": content,
            "encoding": "utf-8",
            "size_bytes": len(content.encode('utf-8'))
        }
    except UnicodeDecodeError:
        # Binary file - return as base64
        import base64
        with open(full_path, 'rb') as f:
            content = base64.b64encode(f.read()).decode('ascii')
        return {
            "task_id": task_id,
            "file_path": file_path,
            "content": content,
            "encoding": "base64",
            "size_bytes": os.path.getsize(full_path)
        }


@router.get("/workspace/{task_id}/files", response_model=WorkspaceFilesResponse)
async def list_workspace_files(task_id: str):
    """
    List files in task's working directory and notes directory.

    Returns list of files created by the task with total size.
    Includes both workspace/ and notes/ directories.
    """
    import os

    service = get_service()
    state = service._tasks.get(task_id)

    if not state:
        raise HTTPException(status_code=404, detail="Task not found")

    if not state._dir_manager:
        raise HTTPException(status_code=404, detail="Task has no directory manager")

    task_root = state._dir_manager.task_root
    files = []
    total_size = 0

    # Scan both workspace/ and notes/ directories
    directories_to_scan = [
        task_root / "workspace",
        task_root / "notes",
    ]

    try:
        for dir_path in directories_to_scan:
            if not dir_path.exists():
                continue
                
            for root, dirs, filenames in os.walk(dir_path):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for filename in filenames:
                    if not filename.startswith('.'):
                        file_path = os.path.join(root, filename)
                        # Use path relative to task_root to show directory structure
                        rel_path = os.path.relpath(file_path, task_root)
                        files.append(rel_path)
                        try:
                            total_size += os.path.getsize(file_path)
                        except OSError:
                            pass
    except Exception as e:
        logger.error(f"Error listing workspace files: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return WorkspaceFilesResponse(
        task_id=task_id,
        workspace=str(task_root),
        files=sorted(files),
        total_size_bytes=total_size
    )


@router.delete("/workspace/{task_id}", response_model=WorkspaceCleanupResponse)
async def cleanup_workspace(task_id: str, force: bool = False):
    """
    Clean up task's directory (workspace, notes, logs, browser data).

    Removes all files created by the task.
    By default, only allows cleanup after task completion.
    Use force=true to cleanup while task is still running.

    Args:
        task_id: Task ID
        force: If true, allows cleanup of running tasks
    """
    service = get_service()
    state = service._tasks.get(task_id)

    if not state:
        raise HTTPException(status_code=404, detail="Task not found")

    if not state._dir_manager:
        return WorkspaceCleanupResponse(
            task_id=task_id,
            cleaned=True,
            message="Task has no directory to clean"
        )

    # Check if task is still running
    if state.status in (TaskStatus.PENDING, TaskStatus.RUNNING) and not force:
        raise HTTPException(
            status_code=400,
            detail="Cannot cleanup task directory while task is running. Use force=true to override."
        )

    task_root = state._dir_manager.task_root
    freed_bytes = 0

    try:
        # Calculate size before cleanup (scan entire task_root)
        freed_bytes = state._dir_manager.get_disk_usage()

        # Perform cleanup (removes entire task directory)
        state._dir_manager.cleanup_all()

        return WorkspaceCleanupResponse(
            task_id=task_id,
            cleaned=True,
            message=f"Task directory cleaned: {task_root}",
            freed_bytes=freed_bytes
        )

    except Exception as e:
        logger.error(f"Error cleaning up workspace: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== SSE Streaming Endpoint ==============

SSE_IDLE_TIMEOUT_SECONDS = 600  # 10 minutes idle timeout (no data received)
SSE_HEARTBEAT_INTERVAL = 30  # 30 seconds


async def sse_stream_wrapper(
    state,
    request: Request,
    idle_timeout_seconds: int = SSE_IDLE_TIMEOUT_SECONDS,
    heartbeat_interval: int = SSE_HEARTBEAT_INTERVAL,
):
    """
    Wrap event queue as SSE stream with idle timeout handling.

    Following Eigent's pattern: timeout is based on idle time (no data received),
    not total connection time. This allows long-running tasks to stream indefinitely
    as long as data keeps flowing.

    Yields SSE-formatted events from the typed event queue.
    Closes the connection on:
    - Idle timeout reached (no data for idle_timeout_seconds)
    - Client disconnect
    - End/completed/failed/cancelled events
    """
    import time
    last_data_time = time.time()  # Track last data received time

    try:
        while True:
            # Check idle timeout (time since last data)
            elapsed_since_data = time.time() - last_data_time
            if elapsed_since_data >= idle_timeout_seconds:
                logger.info(f"SSE stream idle timeout for task {state.task_id} (no data for {idle_timeout_seconds}s)")
                yield sse_action(EndData(
                    task_id=state.task_id,
                    status="timeout",
                    message="Stream idle timeout"
                ))
                break

            # Check client disconnection
            if await request.is_disconnected():
                logger.info(f"SSE client disconnected for task {state.task_id}")
                break

            try:
                # Wait for event with heartbeat interval timeout
                event = await asyncio.wait_for(
                    state.get_event(),
                    timeout=heartbeat_interval
                )

                # Reset idle timer on data received
                last_data_time = time.time()

                # Yield SSE-formatted event
                yield sse_action(event)

                # Check for terminal events
                action = event.action
                if hasattr(action, 'value'):
                    action = action.value
                if action in ("end", "task_completed", "task_failed", "task_cancelled"):
                    break

            except asyncio.TimeoutError:
                # No event within interval, send heartbeat
                # Note: heartbeat doesn't reset idle timer - only actual data does
                yield sse_heartbeat()

    except asyncio.CancelledError:
        logger.info(f"SSE stream cancelled for task {state.task_id}")
    except Exception as e:
        logger.error(f"SSE stream error for task {state.task_id}: {e}")
        yield sse_action(EndData(
            task_id=state.task_id,
            status="error",
            message=str(e)
        ))


@router.get("/stream/{task_id}")
async def stream_task_events(task_id: str, request: Request):
    """
    SSE endpoint for streaming task events.

    Returns Server-Sent Events stream with real-time typed events.
    Event format: data: {"step": "action_type", "data": {...}}

    Terminal events that close the stream:
    - end
    - task_completed
    - task_failed
    - task_cancelled
    """
    service = get_service()
    state = service._tasks.get(task_id)

    if not state:
        raise HTTPException(status_code=404, detail="Task not found")

    return StreamingResponse(
        sse_stream_wrapper(state, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


# ============== WebSocket Endpoint ==============

@router.websocket("/ws/{task_id}")
async def task_progress_websocket(websocket: WebSocket, task_id: str):
    """
    Real-time task progress WebSocket (bidirectional).

    Server -> Client messages:
    - {"event": "connected", "task_id": "..."}
    - {"event": "task_started", "task_id": "...", "task": "..."}
    - {"event": "task_completed", "output": {...}}
    - {"event": "task_failed", "error": "..."}
    - {"event": "task_cancelled"}
    - {"event": "heartbeat"}
    - {"event": "human_question", "question": "...", "context": "..."}
    - {"event": "human_message", "title": "...", "description": "..."}

    Client -> Server messages:
    - {"type": "human_response", "response": "..."}
    """
    await websocket.accept()

    service = get_service()

    async def receive_messages():
        """Handle incoming messages from client."""
        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type")

                if msg_type == "human_response":
                    response = data.get("response", "")
                    success = await service.provide_human_response(task_id, response)
                    if success:
                        logger.info(f"Human response received for task {task_id}")
                    else:
                        logger.warning(f"Failed to deliver human response for task {task_id}")

        except WebSocketDisconnect:
            logger.info(f"WebSocket receive loop ended for task {task_id}")
        except Exception as e:
            logger.debug(f"WebSocket receive error for task {task_id}: {e}")

    async def send_progress():
        """Send progress updates to client."""
        try:
            # Send connection confirmation
            await websocket.send_json({
                "event": "connected",
                "task_id": task_id
            })

            # Subscribe to progress updates
            async for event in service.subscribe_progress(task_id):
                await websocket.send_json(event)

                # If task ended, break
                if event.get("event") in ["task_completed", "task_failed", "task_cancelled"]:
                    break

        except WebSocketDisconnect:
            logger.info(f"WebSocket send loop ended for task {task_id}")
        except Exception as e:
            logger.debug(f"WebSocket send error for task {task_id}: {e}")

    try:
        # Run send and receive concurrently
        send_task = asyncio.create_task(send_progress())
        receive_task = asyncio.create_task(receive_messages())

        # Wait for send task to complete (ends when task finishes)
        await send_task

        # Cancel receive task when done
        receive_task.cancel()
        try:
            await receive_task
        except asyncio.CancelledError:
            pass

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for task {task_id}")
    except Exception as e:
        logger.exception(f"WebSocket error for task {task_id}: {e}")
        try:
            await websocket.send_json({
                "event": "error",
                "message": str(e)
            })
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass
