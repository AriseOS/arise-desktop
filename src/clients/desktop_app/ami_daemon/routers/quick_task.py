"""
Quick Task API

Independent task execution interface, separate from Workflow.
Users input natural language tasks, and the Agent completes them autonomously.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Header
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import logging
import os

from ..services.quick_task_service import QuickTaskService, TaskStatus
from ..core.config_service import get_config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/quick-task", tags=["Quick Task"])

# Load config for LLM settings
config = get_config()

# Service instance
_service: Optional[QuickTaskService] = None


def get_service() -> QuickTaskService:
    global _service
    if _service is None:
        _service = QuickTaskService()
    return _service


def configure_service(api_key: str, model: Optional[str] = None):
    """Configure the service with LLM credentials."""
    service = get_service()
    service.configure_llm(api_key, model)


# ============== Request/Response Models ==============

class TaskRequest(BaseModel):
    """Task execution request"""
    task: str = Field(..., description="Task description", min_length=1, max_length=2000)
    start_url: Optional[str] = Field(None, description="Optional starting URL")
    max_steps: int = Field(15, description="Maximum steps", ge=1, le=50)
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


# ============== REST Endpoints ==============

@router.post("/execute", response_model=TaskResponse)
async def execute_task(
    request: TaskRequest,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key"),
):
    """
    Submit task for execution.

    Headers:
    - X-Ami-API-Key: User's Ami API key (ami_xxxxx format). Required for LLM calls via CRS.

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

    # Configure LLM - use X-Ami-API-Key with CRS proxy
    if x_ami_api_key:
        if use_proxy:
            # Use CRS (Claude Relay Service) proxy
            service.configure_llm(
                api_key=x_ami_api_key,
                model=llm_model,
                base_url=proxy_url
            )
            logger.info(f"Quick Task using CRS proxy: {proxy_url}")
        else:
            # Direct API call (not recommended for production)
            service.configure_llm(api_key=x_ami_api_key, model=llm_model)
            logger.info("Quick Task using direct Anthropic API")
    else:
        # Fallback to environment variable (for local development)
        env_api_key = os.environ.get("ANTHROPIC_API_KEY")
        if env_api_key:
            service.configure_llm(api_key=env_api_key, model=llm_model)
            logger.warning("Using ANTHROPIC_API_KEY env var (no X-Ami-API-Key header)")
        else:
            logger.warning("No API key provided - LLM calls will fail")

    try:
        task_id = await service.submit_task(
            task=request.task,
            start_url=request.start_url,
            max_steps=request.max_steps,
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


# ============== WebSocket Endpoint ==============

@router.websocket("/ws/{task_id}")
async def task_progress_websocket(websocket: WebSocket, task_id: str):
    """
    Real-time task progress WebSocket.

    Message format:
    - {"event": "connected", "task_id": "..."}
    - {"event": "task_started", "task_id": "...", "task": "..."}
    - {"event": "task_completed", "output": {...}}
    - {"event": "task_failed", "error": "..."}
    - {"event": "task_cancelled"}
    - {"event": "heartbeat"}
    """
    await websocket.accept()

    service = get_service()

    try:
        # Send connection confirmation
        await websocket.send_json({
            "event": "connected",
            "task_id": task_id
        })

        # Subscribe to progress updates
        async for event in service.subscribe_progress(task_id):
            await websocket.send_json(event)

            # If task ended, close connection
            if event.get("event") in ["task_completed", "task_failed", "task_cancelled"]:
                break

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
