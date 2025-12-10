#!/usr/bin/env python3
"""
App Backend Daemon - HTTP API Version
Provides REST API endpoints for desktop app communication
"""
import sys
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Header, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
import json

# Detect if running in PyInstaller bundle
def get_project_root() -> Path:
    """Get project root, handling both development and PyInstaller environments"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running in PyInstaller bundle
        # sys._MEIPASS is the temporary folder where PyInstaller extracts files
        bundle_dir = Path(sys._MEIPASS)
        return bundle_dir
    else:
        # Running from source
        project_root = Path(__file__).parent.parent.parent
        return project_root

# Add project root to sys.path
project_root = get_project_root()
sys.path.insert(0, str(project_root))

from src.app_backend.core.config_service import get_config
from src.app_backend.services.storage_manager import StorageManager
from src.app_backend.services.browser_manager import BrowserManager
from src.app_backend.services.workflow_executor import WorkflowExecutor
from src.app_backend.services.cdp_recorder import CDPRecorder
from src.app_backend.services.cloud_client import CloudClient

# Configure logging with both console and file output
log_format = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'

# Create formatters and handlers
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(log_format))

# File handler - log to ~/.ami/logs/app-backend.log
log_dir = Path.home() / '.ami' / 'logs'
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / 'app-backend.log'

file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)  # File gets DEBUG level
file_handler.setFormatter(logging.Formatter(log_format))

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)  # Capture all levels
root_logger.addHandler(console_handler)
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)
logger.info(f"Logging to file: {log_file}")

# Load configuration
config = get_config()

# Global service instances
storage_manager = StorageManager(config.get("storage.base_path"))
browser_manager: Optional[BrowserManager] = None
workflow_executor: Optional[WorkflowExecutor] = None
cdp_recorder: Optional[CDPRecorder] = None
cloud_client: Optional[CloudClient] = None

# WebSocket connection manager
class WebSocketConnectionManager:
    """Manage WebSocket connections for real-time progress updates"""

    def __init__(self):
        # Map task_id to list of active WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.lock = asyncio.Lock()

    async def connect(self, task_id: str, websocket: WebSocket):
        """Connect a WebSocket for a specific task"""
        await websocket.accept()
        async with self.lock:
            if task_id not in self.active_connections:
                self.active_connections[task_id] = []
            self.active_connections[task_id].append(websocket)
            logger.info(f"WebSocket connected for task {task_id}. Total connections: {len(self.active_connections[task_id])}")

    async def disconnect(self, task_id: str, websocket: WebSocket):
        """Disconnect a WebSocket"""
        async with self.lock:
            if task_id in self.active_connections:
                if websocket in self.active_connections[task_id]:
                    self.active_connections[task_id].remove(websocket)
                    logger.info(f"WebSocket disconnected for task {task_id}. Remaining: {len(self.active_connections[task_id])}")
                if not self.active_connections[task_id]:
                    del self.active_connections[task_id]

    async def send_progress_update(self, task_id: str, data: dict):
        """Send progress update to all connected clients for a task"""
        async with self.lock:
            if task_id not in self.active_connections:
                return

            connections = self.active_connections[task_id].copy()

        # Send to all connections outside the lock to avoid blocking
        disconnected = []
        for connection in connections:
            try:
                await connection.send_json(data)
            except Exception as e:
                logger.error(f"Failed to send progress update: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        if disconnected:
            async with self.lock:
                if task_id in self.active_connections:
                    for conn in disconnected:
                        if conn in self.active_connections[task_id]:
                            self.active_connections[task_id].remove(conn)
                    if not self.active_connections[task_id]:
                        del self.active_connections[task_id]

ws_manager = WebSocketConnectionManager()


# ============================================================================
# Application Lifespan Management
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - startup and shutdown

    This lifespan context manager is called by uvicorn:
    - On startup: Initialize all services
    - On shutdown: Cleanup all resources (triggered by SIGTERM/SIGINT)
    """
    global browser_manager, workflow_executor, cdp_recorder, cloud_client

    # ========== STARTUP ==========
    logger.info("=" * 60)
    logger.info("Starting App Backend services...")
    logger.info("=" * 60)

    try:
        # Initialize browser manager (but do NOT start browser yet - on-demand startup)
        browser_manager = BrowserManager(config_service=config)
        logger.info("✓ Browser manager initialized (browser not started - will start on demand)")

        # Initialize workflow executor
        workflow_executor = WorkflowExecutor(storage_manager, browser_manager)

        # Set up progress callback for WebSocket updates
        workflow_executor.set_progress_callback(ws_manager.send_progress_update)
        logger.info("✓ Workflow executor initialized with WebSocket progress callback")

        # Initialize CDP recorder
        cdp_recorder = CDPRecorder(storage_manager, browser_manager)
        logger.info("✓ CDP recorder initialized")

        # Initialize cloud client (without user_api_key initially)
        cloud_client = CloudClient(
            api_url=config.get("cloud.api_url", "https://api.ami.com")
        )
        logger.info("✓ Cloud client initialized")
        logger.info(f"  Cloud Backend URL: {config.get('cloud.api_url', 'https://api.ami.com')}")
        logger.info(f"  API Proxy URL: {config.get('api_proxy.url', 'http://localhost:8080')}")

        logger.info("=" * 60)
        logger.info("✅ App Backend ready!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Failed to initialize services: {e}")
        raise

    # ========== APPLICATION RUNNING ==========
    yield

    # ========== SHUTDOWN ==========
    logger.info("=" * 60)
    logger.info("Shutting down App Backend...")
    logger.info("=" * 60)

    await cleanup_resources()

    logger.info("=" * 60)
    logger.info("✅ Shutdown complete")
    logger.info("=" * 60)


# FastAPI app with lifespan
app = FastAPI(
    title="Ami App Backend",
    description="HTTP API for desktop app communication",
    version="1.0.0",
    lifespan=lifespan  # Use lifespan instead of @app.on_event
)

# Add CORS middleware for desktop app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Desktop app can connect from any origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Request/Response Models
# ============================================================================

class StartRecordingRequest(BaseModel):
    url: str
    user_id: str  # User ID for multi-user support
    title: Optional[str] = ""
    description: Optional[str] = ""
    task_metadata: Optional[Dict[str, Any]] = None  # User's natural language description of what they're doing


class StartRecordingResponse(BaseModel):
    session_id: str
    status: str
    url: str


class StopRecordingResponse(BaseModel):
    session_id: str
    operations_count: int
    local_file_path: str


class UploadRecordingRequest(BaseModel):
    session_id: str
    task_description: str
    user_query: Optional[str] = None  # What user wants to do
    user_id: str


class UploadRecordingResponse(BaseModel):
    recording_id: str
    status: str


class GenerateMetaflowRequest(BaseModel):
    task_description: str
    user_query: Optional[str] = None  # What user wants to do
    user_id: str


class GenerateMetaflowResponse(BaseModel):
    metaflow_id: str
    metaflow_yaml: str  # Include YAML content for frontend preview
    local_path: str


class GenerateMetaflowFromRecordingRequest(BaseModel):
    """Request model for generating MetaFlow from recording"""
    session_id: str
    task_description: str
    user_query: Optional[str] = None  # What user wants to do
    user_id: str


class AnalyzeRecordingRequest(BaseModel):
    """Request model for analyzing recording"""
    session_id: str
    user_id: str


class AnalyzeRecordingResponse(BaseModel):
    """Response model for recording analysis"""
    name: str
    task_description: str
    user_query: str
    detected_patterns: Dict[str, Any]


class UpdateRecordingMetadataRequest(BaseModel):
    """Request model for updating recording metadata"""
    session_id: str
    task_description: str
    user_query: str
    name: Optional[str] = None
    user_id: str


class GenerateWorkflowRequest(BaseModel):
    """Request model for generating Workflow from MetaFlow

    Workflow generation MUST be from MetaFlow.
    User must review and confirm MetaFlow before generating Workflow.
    """
    metaflow_id: str
    user_id: str


class GenerateWorkflowResponse(BaseModel):
    """Unified workflow generation response"""
    workflow_id: Optional[str] = None
    workflow_name: str
    local_path: str
    status: str = "success"


class ExecuteWorkflowRequest(BaseModel):
    workflow_name: str
    user_id: str


class ExecuteWorkflowResponse(BaseModel):
    task_id: str
    status: str


class WorkflowStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: int
    current_step: int
    total_steps: int
    message: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class WorkflowInfo(BaseModel):
    agent_id: str
    name: str
    description: str
    created_at: Optional[str] = None
    last_run: Optional[str] = None
    is_downloaded: bool = False
    source: str = "unknown"  # "cloud", "local", or "both"


class ListWorkflowsResponse(BaseModel):
    workflows: list[WorkflowInfo]


# ============================================================================
# Startup/Shutdown Events (REMOVED - now using lifespan)
# ============================================================================
# The old @app.on_event("startup") and @app.on_event("shutdown") decorators
# have been replaced with the lifespan context manager above.
# This ensures proper cleanup when uvicorn receives SIGTERM/SIGINT.


# ============================================================================
# Helper Functions
# ============================================================================

def update_cloud_client_api_key(api_key: Optional[str]):
    """Update Cloud Client's user API key for subsequent requests

    Args:
        api_key: User's Ami API key from X-Ami-API-Key header
    """
    if cloud_client and api_key:
        cloud_client.set_user_api_key(api_key)
        logger.debug(f"Updated cloud client API key: {api_key[:10]}...")


# ============================================================================
# Health Check
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "browser_ready": browser_manager.is_ready() if browser_manager else False
    }


# ============================================================================
# Browser Control APIs
# ============================================================================

@app.post("/api/browser/start")
async def start_browser(headless: bool = False):
    """Start browser on demand

    Args:
        headless: Whether to run in headless mode (default: False)

    Returns:
        Browser status including PID and state
    """
    try:
        if not browser_manager:
            raise HTTPException(status_code=500, detail="Browser manager not initialized")

        logger.info(f"API: Starting browser (headless={headless})")
        result = await browser_manager.start_browser(headless=headless)

        return result

    except RuntimeError as e:
        logger.error(f"Failed to start browser: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error starting browser: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/browser/stop")
async def stop_browser():
    """Stop browser gracefully

    Returns:
        Browser status
    """
    try:
        if not browser_manager:
            raise HTTPException(status_code=500, detail="Browser manager not initialized")

        logger.info("API: Stopping browser")
        result = await browser_manager.stop_browser()

        return result

    except RuntimeError as e:
        logger.error(f"Failed to stop browser: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error stopping browser: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/browser/status")
async def get_browser_status():
    """Get current browser status

    Returns:
        Detailed browser status including state, PID, and health info
    """
    try:
        if not browser_manager:
            raise HTTPException(status_code=500, detail="Browser manager not initialized")

        status = browser_manager.get_status()
        return status

    except Exception as e:
        logger.error(f"Failed to get browser status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/browser/window/layout")
async def get_window_layout():
    """Get current window layout information

    Returns:
        Window layout details including screen size and window positions
    """
    try:
        if not browser_manager:
            raise HTTPException(status_code=500, detail="Browser manager not initialized")

        layout_info = browser_manager.window_manager.get_layout_info()
        return layout_info

    except Exception as e:
        logger.error(f"Failed to get window layout: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/browser/window/update")
async def update_window_layout(app_width_percent: float):
    """Update window layout with new app width percentage

    Args:
        app_width_percent: Percentage of screen width for app (0.0 to 1.0)

    Returns:
        Updated layout information
    """
    try:
        if not browser_manager:
            raise HTTPException(status_code=500, detail="Browser manager not initialized")

        if not 0.0 <= app_width_percent <= 1.0:
            raise HTTPException(
                status_code=400,
                detail="app_width_percent must be between 0.0 and 1.0"
            )

        logger.info(f"API: Updating window layout to {app_width_percent*100:.0f}% app width")

        # Update layout preferences
        layout = browser_manager.window_manager.update_layout(app_width_percent)

        # If browser is running, apply the new layout
        if browser_manager.state.value == "running" and browser_manager._browser_pid:
            result = browser_manager.window_manager.arrange_windows(
                browser_pid=browser_manager._browser_pid,
                app_name="Ami"
            )

            return {
                "layout": browser_manager.window_manager.get_layout_info(),
                "applied": result.get("success", False)
            }
        else:
            return {
                "layout": browser_manager.window_manager.get_layout_info(),
                "applied": False,
                "message": "Layout saved but not applied (browser not running)"
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update window layout: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/browser/window/arrange")
async def arrange_windows():
    """Manually trigger window arrangement

    Returns:
        Arrangement result
    """
    try:
        if not browser_manager:
            raise HTTPException(status_code=500, detail="Browser manager not initialized")

        if browser_manager.state.value != "running" or not browser_manager._browser_pid:
            raise HTTPException(
                status_code=400,
                detail="Browser must be running to arrange windows"
            )

        logger.info("API: Arranging windows")

        result = browser_manager.window_manager.arrange_windows(
            browser_pid=browser_manager._browser_pid,
            app_name="Ami"
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to arrange windows: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Dashboard API
# ============================================================================

@app.get("/api/dashboard")
async def get_dashboard(user_id: str):
    """Get dashboard statistics and recent workflows for user"""
    try:
        logger.info(f"Getting dashboard for user: {user_id}")

        # Get all workflows
        workflows_info = storage_manager.get_local_workflows_info(user_id)
        total_workflows = len(workflows_info)

        # Get all recordings
        recordings = storage_manager.list_recordings(user_id)
        total_recordings = len(recordings)

        # Get recent workflows with execution info
        recent_workflows = []
        workflow_items = sorted(
            workflows_info.values(),
            key=lambda x: x.get('created_at') or '',
            reverse=True
        )[:2]  # Get 2 most recent

        for workflow in workflow_items:
            workflow_id = workflow['agent_id']

            # Get last execution info
            last_exec = storage_manager.get_workflow_last_execution(user_id, workflow_id)

            if last_exec:
                # Calculate relative time
                from datetime import datetime
                try:
                    exec_time = datetime.fromisoformat(last_exec['timestamp'])
                    now = datetime.now()
                    delta = now - exec_time

                    if delta.days > 0:
                        last_run = f"{delta.days} day{'s' if delta.days > 1 else ''} ago"
                    elif delta.seconds >= 3600:
                        hours = delta.seconds // 3600
                        last_run = f"{hours} hour{'s' if hours > 1 else ''} ago"
                    elif delta.seconds >= 60:
                        minutes = delta.seconds // 60
                        last_run = f"{minutes} minute{'s' if minutes > 1 else ''} ago"
                    else:
                        last_run = "just now"

                    status = last_exec['status']
                except Exception:
                    last_run = "unknown"
                    status = "unknown"
            else:
                last_run = "never"
                status = "not_run"

            recent_workflows.append({
                "id": workflow_id,
                "name": workflow['name'],
                "lastRun": last_run,
                "status": status
            })

        dashboard_data = {
            "has_workflows": total_workflows > 0,
            "total_workflows": total_workflows,
            "total_recordings": total_recordings,
            "recent_workflows": recent_workflows
        }

        logger.info(f"Dashboard data: {total_workflows} workflows, {total_recordings} recordings")
        return dashboard_data

    except Exception as e:
        logger.error(f"Failed to get dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Recording APIs
# ============================================================================

@app.post("/api/recording/start", response_model=StartRecordingResponse)
async def start_recording(request: StartRecordingRequest):
    """Start CDP recording session

    This will automatically start the browser if it's not running
    """
    try:
        logger.info(f"Starting recording: url={request.url}, title={request.title}")

        # 1. Ensure browser is running
        browser_status = browser_manager.get_status()
        if not browser_status["is_running"]:
            logger.info("Browser not running, starting browser for recording...")
            await browser_manager.start_browser(headless=False)

            # Wait for browser to be fully ready
            await asyncio.sleep(2)
            logger.info("Browser ready for recording")

        # 2. Prepare metadata
        metadata = request.task_metadata or {}
        metadata.update({
            "title": request.title,
            "description": request.description
        })

        # 3. Start recording
        result = await cdp_recorder.start_recording(
            url=request.url,
            user_id=request.user_id,
            metadata=metadata
        )
        logger.info(f"Recording started: session_id={result['session_id']}, user_id={request.user_id}")
        return result

    except Exception as e:
        logger.error(f"Failed to start recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/recording/stop", response_model=StopRecordingResponse)
async def stop_recording():
    """Stop recording and save

    This will automatically close the browser after recording stops
    """
    try:
        logger.info("Stopping recording...")

        # 1. Stop recording
        result = await cdp_recorder.stop_recording()
        logger.info(f"Recording stopped: {result['operations_count']} operations")

        # 2. Close browser automatically
        browser_status = browser_manager.get_status()
        if browser_status["is_running"]:
            logger.info("Closing browser after recording...")
            await browser_manager.stop_browser()
            logger.info("Browser closed")

        return result

    except Exception as e:
        logger.error(f"Failed to stop recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/recording/analyze", response_model=AnalyzeRecordingResponse)
async def analyze_recording(
    request: AnalyzeRecordingRequest,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """Analyze recording and generate suggested task_description and user_query using AI"""
    try:
        logger.info(f"Analyzing recording: session_id={request.session_id}")
        logger.info(f"X-Ami-API-Key header received: {x_ami_api_key[:10] if x_ami_api_key else 'None'}...")

        # Set user API key on cloud client
        if x_ami_api_key:
            cloud_client.set_user_api_key(x_ami_api_key)
            logger.info(f"Set user API key on cloud client: {x_ami_api_key[:10]}...")
            logger.info(f"CloudClient headers: {dict(cloud_client.client.headers)}")
        else:
            logger.warning("No X-Ami-API-Key header provided")

        # 1. Load recording
        recording_data = storage_manager.get_recording(request.user_id, request.session_id)
        if not recording_data:
            raise HTTPException(status_code=404, detail="Recording not found")

        operations = recording_data.get("operations", [])
        logger.info(f"Loaded {len(operations)} operations from recording")

        # 2. Call Cloud Backend to analyze
        logger.info("Calling Cloud Backend to analyze recording...")
        analysis_result = await cloud_client.analyze_recording_operations(
            operations=operations,
            user_id=request.user_id
        )

        logger.info(f"Analysis complete:")
        logger.info(f"  Name: {analysis_result.get('name', 'NOT_GENERATED')}")
        logger.info(f"  Task Description: {analysis_result['task_description'][:100]}...")
        logger.info(f"  User Query: {analysis_result['user_query'][:100]}...")
        logger.info(f"  Patterns: {analysis_result['patterns']}")

        return AnalyzeRecordingResponse(
            name=analysis_result.get("name", "Unnamed Task"),
            task_description=analysis_result["task_description"],
            user_query=analysis_result["user_query"],
            detected_patterns=analysis_result["patterns"]
        )

    except Exception as e:
        logger.error(f"Failed to analyze recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/recording/update-metadata")
async def update_recording_metadata(request: UpdateRecordingMetadataRequest):
    """Update recording metadata with task_description and user_query after user confirmation"""
    try:
        logger.info(f"Updating metadata for recording: session_id={request.session_id}")
        if request.name:
            logger.info(f"  Name: {request.name}")
        logger.info(f"  Task Description: {request.task_description[:100]}...")
        logger.info(f"  User Query: {request.user_query[:100]}...")

        # Update metadata in storage
        storage_manager.update_recording_metadata(
            user_id=request.user_id,
            session_id=request.session_id,
            task_description=request.task_description,
            user_query=request.user_query,
            name=request.name
        )

        logger.info("Metadata updated successfully")
        return {"success": True, "message": "Metadata updated"}

    except Exception as e:
        logger.error(f"Failed to update metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recordings")
async def list_recordings(user_id: str):
    """List all recordings for a user"""
    try:
        logger.info(f"Listing recordings for user: {user_id}")
        recordings = storage_manager.list_recordings(user_id)
        logger.info(f"Found {len(recordings)} recordings")
        return {
            "recordings": recordings,
            "count": len(recordings)
        }
    except Exception as e:
        logger.error(f"Failed to list recordings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recordings/list")
async def list_recordings_legacy(user_id: str):
    """List all recordings for a user (legacy endpoint)"""
    return await list_recordings(user_id)


@app.get("/api/recordings/{session_id}")
async def get_recording_detail(session_id: str, user_id: str):
    """Get detailed recording information"""
    try:
        logger.info(f"Getting recording detail: session_id={session_id}")
        detail = storage_manager.get_recording_detail(user_id, session_id)

        if detail is None:
            raise HTTPException(status_code=404, detail=f"Recording not found: {session_id}")

        # Try to get metaflow_id and task_description from Cloud Backend
        # The recording_id in Cloud Backend is the same as session_id
        try:
            cloud_recording = await cloud_client.get_recording(session_id, user_id)
            if cloud_recording:
                if cloud_recording.get("metaflow_id"):
                    detail["metaflow_id"] = cloud_recording["metaflow_id"]
                    logger.info(f"Found metaflow_id from Cloud: {detail['metaflow_id']}")

                # Use task_description from Cloud as recording name if available
                if cloud_recording.get("task_description"):
                    detail["name"] = cloud_recording["task_description"]
                    logger.info(f"Using task_description as name: {detail['name'][:50]}...")
        except Exception as e:
            logger.warning(f"Could not fetch data from Cloud: {e}")

        return detail
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get recording detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/recordings/{session_id}")
async def delete_recording(session_id: str, user_id: str):
    """Delete a recording"""
    try:
        logger.info(f"Deleting recording: session_id={session_id}")
        success = storage_manager.delete_recording(user_id, session_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Recording not found: {session_id}")

        logger.info(f"Recording deleted: {session_id}")
        return {"status": "success", "message": "Recording deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Recording Upload API
# ============================================================================

@app.post("/api/recordings/upload", response_model=UploadRecordingResponse)
async def upload_recording_to_cloud(
    request: UploadRecordingRequest,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """Upload recording to Cloud Backend for intent extraction

    Headers:
        X-Ami-API-Key: User's Ami API key (optional, for API Proxy)
    """
    try:
        logger.info(f"Uploading recording from session: {request.session_id}")

        # Update cloud client with user's API key if provided
        update_cloud_client_api_key(x_ami_api_key)

        # Load operations from local storage
        recording_data = storage_manager.get_recording(
            request.user_id, request.session_id
        )
        operations = recording_data.get("operations", [])

        # Upload recording to Cloud Backend (with task_description and user_query)
        # Use session_id as recording_id to keep IDs in sync between local and cloud
        recording_id = await cloud_client.upload_recording(
            operations=operations,
            task_description=request.task_description,
            user_query=request.user_query,
            user_id=request.user_id,
            recording_id=request.session_id
        )
        logger.info(f"Recording uploaded: {recording_id}")

        return {
            "recording_id": recording_id,
            "status": "success"
        }

    except Exception as e:
        logger.error(f"Failed to upload recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MetaFlow APIs
# ============================================================================

@app.post("/api/metaflows/generate", response_model=GenerateMetaflowResponse)
async def generate_metaflow(
    request: GenerateMetaflowRequest,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """Generate MetaFlow from user's Intent Memory Graph

    Headers:
        X-Ami-API-Key: User's Ami API key (optional, for API Proxy)
    """
    try:
        logger.info(f"Generating MetaFlow for task: {request.task_description}")

        # Update cloud client with user's API key if provided
        update_cloud_client_api_key(x_ami_api_key)

        # Call Cloud Backend to generate MetaFlow
        result = await cloud_client.generate_metaflow(
            task_description=request.task_description,
            user_query=request.user_query,
            user_id=request.user_id
        )

        metaflow_id = result["metaflow_id"]
        metaflow_yaml = result["metaflow_yaml"]
        task_desc = result.get("task_description", "")

        # Save to local storage
        storage_manager.save_metaflow(
            request.user_id, metaflow_id, metaflow_yaml, task_desc
        )

        local_path = str(
            storage_manager._user_path(request.user_id) / "metaflows" /
            metaflow_id / "metaflow.yaml"
        )

        logger.info(f"MetaFlow saved locally: {local_path}")

        return {
            "metaflow_id": metaflow_id,
            "metaflow_yaml": metaflow_yaml,
            "local_path": local_path
        }

    except Exception as e:
        logger.error(f"Failed to generate MetaFlow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/metaflows/from-recording", response_model=GenerateMetaflowResponse)
async def generate_metaflow_from_recording(request: GenerateMetaflowFromRecordingRequest):
    """Generate MetaFlow from recording

    This endpoint:
    1. Loads the recording data
    2. Uploads recording to Cloud Backend
    3. Calls Cloud Backend to generate MetaFlow from recording's intents only
    4. Saves MetaFlow locally
    5. Returns metaflow_yaml for frontend preview
    """
    try:
        logger.info(f"Generating MetaFlow from recording: {request.session_id}")

        # Load recording data
        recording_data = storage_manager.get_recording(
            request.user_id, request.session_id
        )
        operations = recording_data.get("operations", [])

        if not operations:
            raise HTTPException(
                status_code=400,
                detail=f"No operations found in recording: {request.session_id}"
            )

        # Extract task_metadata from recording
        task_metadata = recording_data.get("task_metadata", {})

        # Use task_description and user_query from recording if not provided in request
        task_description = request.task_description or task_metadata.get("task_description", "")
        user_query = request.user_query or task_metadata.get("user_query")

        logger.info(f"📝 Task Description: {task_description[:80]}...")
        if user_query:
            logger.info(f"🎯 User Query: {user_query[:80]}...")
        else:
            logger.info(f"⚠️  No user_query available")

        # Upload recording to Cloud Backend (use session_id as recording_id to keep IDs in sync)
        logger.info("Uploading recording to Cloud Backend...")
        recording_id = await cloud_client.upload_recording(
            operations=operations,
            task_description=task_description,
            user_query=user_query,
            user_id=request.user_id,
            recording_id=request.session_id  # Use session_id to keep Cloud and Local IDs in sync
        )
        logger.info(f"Recording uploaded: {recording_id}")

        # Generate MetaFlow from recording (using only that recording's intents)
        logger.info("Generating MetaFlow from recording's intents only...")
        metaflow_result = await cloud_client.generate_metaflow_from_recording(
            recording_id=recording_id,
            task_description=task_description,
            user_query=user_query,
            user_id=request.user_id
        )

        metaflow_id = metaflow_result["metaflow_id"]
        metaflow_yaml = metaflow_result["metaflow_yaml"]

        # Save MetaFlow locally
        storage_manager.save_metaflow(
            request.user_id,
            metaflow_id,
            metaflow_yaml,
            request.task_description
        )

        local_path = str(
            storage_manager._user_path(request.user_id) / "metaflows" /
            metaflow_id / "metaflow.yaml"
        )

        logger.info(f"MetaFlow saved locally: {local_path}")

        return {
            "metaflow_id": metaflow_id,
            "metaflow_yaml": metaflow_yaml,
            "local_path": local_path
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate MetaFlow from recording: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metaflows")
async def list_metaflows(user_id: str):
    """List all MetaFlows for user (proxy to Cloud Backend)"""
    try:
        metaflows = await cloud_client.list_metaflows(user_id)
        return metaflows
    except Exception as e:
        logger.error(f"Failed to list metaflows: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metaflows/{metaflow_id}")
async def get_metaflow(metaflow_id: str, user_id: str):
    """Get MetaFlow detail (proxy to Cloud Backend)"""
    try:
        metaflow = await cloud_client.get_metaflow(metaflow_id, user_id)
        return metaflow
    except Exception as e:
        logger.error(f"Failed to get metaflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/metaflows/{metaflow_id}")
async def update_metaflow(metaflow_id: str, data: dict):
    """Update MetaFlow YAML and sync to both Cloud and local storage

    Sync Strategy:
    1. Update Cloud Backend first (primary source)
    2. Update local storage (cache)
    3. Return success if at least one succeeds
    """
    try:
        user_id = data.get("user_id")
        metaflow_yaml = data.get("metaflow_yaml")

        if not metaflow_yaml:
            raise HTTPException(status_code=400, detail="Missing metaflow_yaml")

        logger.info(f"Updating metaflow: metaflow_id={metaflow_id}")

        # Step 1: Update Cloud Backend first (primary source)
        cloud_updated = False
        try:
            result = await cloud_client.update_metaflow(metaflow_id, metaflow_yaml, user_id)
            cloud_updated = True
            logger.info(f"✓ MetaFlow updated in Cloud: {metaflow_id}")
        except Exception as e:
            logger.warning(f"⚠ Failed to update metaflow in Cloud: {e}")

        # Step 2: Update local storage (cache)
        local_updated = False
        try:
            if storage_manager.metaflow_exists(user_id, metaflow_id):
                storage_manager.save_metaflow(user_id, metaflow_id, metaflow_yaml)
                local_updated = True
                logger.info(f"✓ MetaFlow updated in local storage: {metaflow_id}")
            else:
                logger.warning(f"⚠ MetaFlow not found in local storage: {metaflow_id}")
        except Exception as e:
            logger.warning(f"⚠ Failed to update metaflow in local storage: {e}")

        # Step 3: Return success if at least one succeeded
        if not cloud_updated and not local_updated:
            raise HTTPException(status_code=500, detail="Failed to update metaflow in both Cloud and local storage")

        logger.info(f"✅ MetaFlow update complete: {metaflow_id} (Cloud: {cloud_updated}, Local: {local_updated})")
        return {
            "success": True,
            "updated_in_cloud": cloud_updated,
            "updated_in_local": local_updated
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update metaflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Workflow APIs
# ============================================================================

@app.post("/api/workflows/from-metaflow")
async def generate_workflow_from_metaflow_api(data: dict):
    """Generate Workflow from MetaFlow (alternative endpoint used by frontend)"""
    try:
        metaflow_id = data.get("metaflow_id")
        user_id = data.get("user_id")

        if not metaflow_id:
            raise HTTPException(status_code=400, detail="Missing metaflow_id")

        logger.info(f"Generating Workflow from MetaFlow: {metaflow_id}")

        # Generate Workflow from MetaFlow via Cloud Backend
        workflow_result = await cloud_client.generate_workflow(
            metaflow_id=metaflow_id,
            user_id=user_id
        )

        workflow_id = workflow_result.get("workflow_id")
        workflow_name = workflow_result["workflow_name"]
        workflow_yaml = workflow_result["workflow_yaml"]

        logger.info(f"Cloud returned: workflow_id={workflow_id}, workflow_name={workflow_name}")

        # Save Workflow locally using workflow_id as directory name
        save_id = workflow_id or workflow_name
        storage_manager.save_workflow(
            user_id,
            save_id,
            workflow_yaml
        )

        logger.info(f"Workflow saved locally with id: {save_id}")

        return {
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "workflow_yaml": workflow_yaml,
            "status": "success"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate workflow: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/workflows/generate", response_model=GenerateWorkflowResponse)
async def generate_workflow(
    request: GenerateWorkflowRequest,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """Generate Workflow from MetaFlow

    This endpoint only generates workflow from a confirmed MetaFlow.
    User must review MetaFlow before calling this endpoint.

    Workflow generation flow:
    1. User generates MetaFlow (via /api/metaflows/generate or /api/metaflows/from-recording)
    2. User reviews MetaFlow in UI
    3. User confirms and calls this endpoint with metaflow_id
    4. Workflow is generated from the confirmed MetaFlow

    Headers:
        X-Ami-API-Key: User's Ami API key (optional, for API Proxy)
    """
    try:
        logger.info(f"Generating Workflow from MetaFlow: {request.metaflow_id}")

        # Update cloud client with user's API key if provided
        update_cloud_client_api_key(x_ami_api_key)

        # Generate Workflow from MetaFlow via Cloud Backend
        workflow_result = await cloud_client.generate_workflow(
            metaflow_id=request.metaflow_id,
            user_id=request.user_id
        )

        # Debug: log the full response from Cloud Backend
        logger.info(f"Cloud Backend response keys: {workflow_result.keys()}")
        logger.info(f"Cloud Backend workflow_id: {workflow_result.get('workflow_id')}")
        logger.info(f"Cloud Backend workflow_name: {workflow_result.get('workflow_name')}")

        workflow_id = workflow_result.get("workflow_id")
        workflow_name = workflow_result["workflow_name"]
        workflow_yaml = workflow_result["workflow_yaml"]

        # Save Workflow locally
        storage_manager.save_workflow(
            request.user_id,
            workflow_id or workflow_name,
            workflow_yaml
        )

        local_path = str(
            storage_manager._user_path(request.user_id) / "workflows" /
            (workflow_id or workflow_name) / "workflow.yaml"
        )

        logger.info(f"✅ Workflow generated and saved: {workflow_id} ({workflow_name}) at {local_path}")

        return {
            "workflow_name": workflow_name,
            "workflow_id": workflow_id,
            "local_path": local_path,
            "status": "success"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate workflow: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/workflow/execute", response_model=ExecuteWorkflowResponse)
async def execute_workflow(
    request: ExecuteWorkflowRequest,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """Execute a workflow asynchronously

    Headers:
        X-Ami-API-Key: User's Ami API key (required for LLM calls via API Proxy)
    """
    try:
        logger.info(f"Executing workflow: {request.workflow_name}")

        if not x_ami_api_key:
            logger.warning("No X-Ami-API-Key header provided for workflow execution")
        else:
            logger.info(f"Using user API key for workflow execution: {x_ami_api_key[:10]}...")

        result = await workflow_executor.execute_workflow_async(
            user_id=request.user_id,
            workflow_name=request.workflow_name,
            user_api_key=x_ami_api_key
        )
        logger.info(f"Workflow execution started: task_id={result['task_id']}")
        return result
    except Exception as e:
        logger.error(f"Failed to execute workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workflow/status/{task_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(task_id: str):
    """Get workflow execution status"""
    try:
        result = workflow_executor.get_task_status(task_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/workflow/{task_id}")
async def workflow_progress_websocket(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for real-time workflow execution progress updates

    The client connects with task_id to receive real-time progress updates
    for that specific workflow execution.

    Message format:
    {
        "type": "progress_update",
        "task_id": "task_xxx",
        "status": "running|completed|failed",
        "progress": 50,
        "current_step": 2,
        "total_steps": 5,
        "step_info": {
            "name": "Step 2: Extract data",
            "status": "in_progress|completed|failed",
            "result": "...",
            "duration": 1.5
        },
        "message": "Processing...",
        "logs": [...],
        "timestamp": "2024-12-03T12:00:00"
    }
    """
    await ws_manager.connect(task_id, websocket)
    logger.info(f"Client connected to workflow progress stream: task_id={task_id}")

    try:
        # Small delay to ensure connection is fully established
        await asyncio.sleep(0.1)

        # Send initial status if task exists
        initial_status = workflow_executor.get_task_status(task_id)
        if initial_status:
            try:
                await websocket.send_json({
                    "type": "initial_status",
                    "data": initial_status,
                    "timestamp": datetime.now().isoformat()
                })
                logger.info(f"Sent initial status to client for task {task_id}")
            except Exception as e:
                logger.error(f"Failed to send initial status: {e}")

        # Keep connection alive and handle client messages
        while True:
            try:
                # Wait for client messages (heartbeat, etc.)
                data = await websocket.receive_text()

                # Handle heartbeat
                if data == "ping":
                    try:
                        await websocket.send_text("pong")
                    except Exception as e:
                        logger.error(f"Failed to send pong: {e}")
                        break

            except WebSocketDisconnect:
                logger.info(f"Client disconnected from workflow progress stream: task_id={task_id}")
                break
            except Exception as e:
                logger.error(f"Error in WebSocket loop: {e}")
                break

    finally:
        await ws_manager.disconnect(task_id, websocket)


@app.get("/api/workflows", response_model=ListWorkflowsResponse)
async def list_workflows(user_id: str):
    """List all workflows for a user (Cloud + Local merged)

    Strategy:
    1. Fetch workflows from Cloud Backend (primary source)
    2. Check which ones are downloaded locally
    3. Add local-only workflows
    4. Return merged list with download status
    """
    try:
        workflows_dict = {}

        # Step 1: Try to fetch from Cloud Backend
        try:
            cloud_workflows = await cloud_client.list_workflows(user_id)
            for wf in cloud_workflows:
                agent_id = wf['agent_id']
                # Cloud Backend should always return valid name, but use agent_id as ultimate fallback
                name = wf.get('name') or agent_id

                workflows_dict[agent_id] = {
                    'agent_id': agent_id,
                    'name': name,
                    'description': wf.get('description', ''),
                    'created_at': wf.get('created_at'),
                    'last_run': None,
                    'is_downloaded': False,
                    'source': 'cloud'
                }
            logger.info(f"Fetched {len(cloud_workflows)} workflows from Cloud")
        except Exception as e:
            logger.warning(f"Cloud unavailable, using local workflows only: {e}")

        # Step 2: Get local workflows info
        local_workflows = storage_manager.get_local_workflows_info(user_id)

        # Step 3: Merge - mark cloud workflows as downloaded if they exist locally
        for wf_id, local_info in local_workflows.items():
            if wf_id in workflows_dict:
                # Cloud workflow exists locally - mark as downloaded
                workflows_dict[wf_id]['is_downloaded'] = True
                workflows_dict[wf_id]['source'] = 'both'

                # Prefer local metadata (more complete and up-to-date)
                # Only use cloud metadata if local doesn't have it
                local_name = local_info.get('name')
                if local_name and local_name != wf_id:
                    # Local has a valid name (not just the ID)
                    workflows_dict[wf_id]['name'] = local_name

                local_desc = local_info.get('description')
                if local_desc:
                    workflows_dict[wf_id]['description'] = local_desc

                # Add last_run from local execution history
                workflows_dict[wf_id]['last_run'] = local_info.get('last_run')
            else:
                # Local-only workflow
                workflows_dict[wf_id] = local_info

        # Convert to list and sort by created_at (newest first)
        workflows_list = list(workflows_dict.values())
        workflows_list.sort(
            key=lambda x: x.get('created_at') or '',
            reverse=True
        )

        logger.info(f"Returning {len(workflows_list)} workflows total")
        return {"workflows": workflows_list}

    except Exception as e:
        logger.error(f"Failed to list workflows: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workflows/{workflow_id}/detail")
async def get_workflow_detail(workflow_id: str, user_id: str):
    """Get detailed workflow data for visualization

    Returns workflow structure with steps and connections for ReactFlow
    """
    try:
        # Check if workflow exists locally
        if not storage_manager.workflow_exists(user_id, workflow_id):
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

        # Read workflow YAML
        workflow_yaml = storage_manager.get_workflow(user_id, workflow_id)

        # Parse YAML to extract steps and connections
        import yaml
        workflow_data = yaml.safe_load(workflow_yaml)

        if not isinstance(workflow_data, dict):
            raise HTTPException(status_code=500, detail="Invalid workflow format")

        # Extract workflow metadata from metadata section
        metadata = workflow_data.get('metadata', {})
        name = metadata.get('name', workflow_id)
        description = metadata.get('description', '')

        # Extract steps
        steps_data = workflow_data.get('steps', [])

        def process_steps(steps_in):
            results = []
            for idx, step in enumerate(steps_in):
                # Preserved all original keys from step to ensure nothing is lost, 
                # but explicitely handle known fields for clarity
                processed_step = step.copy()
                
                # Ensure id exists
                step_id = step.get('id', f"step-{idx}")
                processed_step['id'] = step_id
                
                # Recursively process children/steps
                if 'steps' in step and isinstance(step['steps'], list):
                    processed_step['steps'] = process_steps(step['steps'])
                
                if 'children' in step and isinstance(step['children'], list):
                    processed_step['children'] = process_steps(step['children'])
                    
                results.append(processed_step)
            return results

        steps_list = process_steps(steps_data)

        # Extract connections (if exists) or auto-generate
        connections = workflow_data.get('connections', [])

        response_data = {
            'workflow_id': workflow_id,
            'name': name,
            'description': description,
            'steps': steps_list,
            'connections': connections,
            'workflow_yaml': workflow_yaml  # Add raw YAML for display
        }

        # 获取追溯信息（反向追溯功能）
        try:
            logger.info(f"Fetching traceability info from Cloud Backend for workflow: {workflow_id}")
            cloud_workflow = await cloud_client.get_workflow(workflow_id, user_id)
            if cloud_workflow:
                response_data['source_metaflow_id'] = cloud_workflow.get("source_metaflow_id")
                response_data['source_recording_id'] = cloud_workflow.get("source_recording_id")
                logger.info(f"Traceability info retrieved: metaflow={response_data.get('source_metaflow_id')}, recording={response_data.get('source_recording_id')}")
            else:
                logger.warning(f"No workflow data found in Cloud Backend for: {workflow_id}")
                response_data['source_metaflow_id'] = None
                response_data['source_recording_id'] = None
        except Exception as e:
            logger.warning(f"Could not fetch traceability info from Cloud Backend: {e}")
            response_data['source_metaflow_id'] = None
            response_data['source_recording_id'] = None

        logger.info(f"Loaded workflow detail: {workflow_id}")
        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/workflows/{workflow_id}")
async def update_workflow(workflow_id: str, data: dict):
    """Update Workflow YAML and sync to both Cloud and local storage

    Sync Strategy:
    1. Update Cloud Backend first (primary source)
    2. Update local storage (cache)
    3. Return success if at least one succeeds
    """
    try:
        user_id = data.get("user_id")
        workflow_yaml = data.get("workflow_yaml")

        if not workflow_yaml:
            raise HTTPException(status_code=400, detail="Missing workflow_yaml")

        logger.info(f"Updating workflow: workflow_id={workflow_id}")

        # Step 1: Update Cloud Backend first (primary source)
        cloud_updated = False
        try:
            result = await cloud_client.update_workflow(workflow_id, workflow_yaml, user_id)
            cloud_updated = True
            logger.info(f"✓ Workflow updated in Cloud: {workflow_id}")
        except Exception as e:
            logger.warning(f"⚠ Failed to update workflow in Cloud: {e}")

        # Step 2: Update local storage (cache)
        local_updated = False
        try:
            if storage_manager.workflow_exists(user_id, workflow_id):
                storage_manager.save_workflow(user_id, workflow_id, workflow_yaml)
                local_updated = True
                logger.info(f"✓ Workflow updated in local storage: {workflow_id}")
            else:
                logger.warning(f"⚠ Workflow not found in local storage: {workflow_id}")
        except Exception as e:
            logger.warning(f"⚠ Failed to update workflow in local storage: {e}")

        # Step 3: Return success if at least one succeeded
        if not cloud_updated and not local_updated:
            raise HTTPException(status_code=500, detail="Failed to update workflow in both Cloud and local storage")

        logger.info(f"✅ Workflow update complete: {workflow_id} (Cloud: {cloud_updated}, Local: {local_updated})")
        return {
            "success": True,
            "updated_in_cloud": cloud_updated,
            "updated_in_local": local_updated
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/workflows/{workflow_id}")
async def delete_workflow(workflow_id: str, user_id: str):
    """Delete a workflow from both Cloud and local storage

    Sync Strategy:
    1. Delete from Cloud Backend first (if exists)
    2. Delete from local storage
    3. Cloud is primary source, local is cache
    """
    try:
        logger.info(f"Deleting workflow: workflow_id={workflow_id}")

        # Step 1: Try to delete from Cloud Backend first
        cloud_deleted = False
        try:
            cloud_deleted = await cloud_client.delete_workflow(workflow_id, user_id)
            if cloud_deleted:
                logger.info(f"✓ Workflow deleted from Cloud: {workflow_id}")
            else:
                logger.warning(f"⚠ Workflow not found in Cloud or delete failed: {workflow_id}")
        except Exception as e:
            logger.warning(f"⚠ Cloud deletion failed (Cloud may be unavailable): {e}")

        # Step 2: Delete from local storage
        local_deleted = storage_manager.delete_workflow(user_id, workflow_id)

        if local_deleted:
            logger.info(f"✓ Workflow deleted from local storage: {workflow_id}")
        else:
            logger.warning(f"⚠ Workflow not found in local storage: {workflow_id}")

        # Step 3: Determine success
        if not cloud_deleted and not local_deleted:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

        logger.info(f"✅ Workflow deletion complete: {workflow_id} (Cloud: {cloud_deleted}, Local: {local_deleted})")
        return {
            "status": "success",
            "message": "Workflow deleted",
            "deleted_from_cloud": cloud_deleted,
            "deleted_from_local": local_deleted
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Data Management APIs (Collections Only)
# ============================================================================

@app.get("/api/data/collections")
async def list_collections(user_id: str):
    """List all data collections with metadata

    Returns collections from storage.db with:
    - Collection name
    - Record count
    - Size estimate
    - Field names
    """
    try:
        logger.info(f"Listing collections for user: {user_id}")

        import aiosqlite
        from datetime import datetime

        collections = []
        storage_db_path = Path(config.get("data.databases.storage"))

        if not storage_db_path.exists():
            logger.info("Storage database does not exist yet")
            return {"collections": collections}

        async with aiosqlite.connect(str(storage_db_path)) as db:
            # Get all tables for this user
            cursor = await db.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name LIKE ?
                ORDER BY name
            """, (f"%_{user_id}",))
            tables = await cursor.fetchall()

            for (table_name,) in tables:
                # Parse collection name from table name (format: {collection}_{user_id})
                # Remove the "_{user_id}" suffix to get the collection name
                suffix = f"_{user_id}"
                if table_name.endswith(suffix):
                    collection_name = table_name[:-len(suffix)]
                else:
                    collection_name = table_name

                # Get row count
                cursor = await db.execute(f"SELECT COUNT(*) FROM {table_name}")
                row_count = (await cursor.fetchone())[0]

                # Get column info
                cursor = await db.execute(f"PRAGMA table_info({table_name})")
                columns = await cursor.fetchall()
                # Filter out internal columns
                field_names = [col[1] for col in columns if col[1] not in ['id', 'created_at', 'updated_at']]

                # Get table size estimate (number of pages * page size)
                cursor = await db.execute(f"SELECT COUNT(*) FROM dbstat WHERE name=?", (table_name,))
                page_count = (await cursor.fetchone())[0]
                size_bytes = page_count * 4096  # SQLite default page size

                collections.append({
                    "collection_name": collection_name,
                    "table_name": table_name,
                    "records_count": row_count,
                    "size_bytes": size_bytes,
                    "fields": field_names
                })

        logger.info(f"Found {len(collections)} collections")
        return {"collections": collections}

    except Exception as e:
        logger.error(f"Failed to list collections: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/data/collections/{collection_name}")
async def get_collection_detail(collection_name: str, user_id: str, limit: int = 10):
    """Get collection detail with data preview

    Args:
        collection_name: Name of the collection
        user_id: User ID (default: default_user)
        limit: Number of records to preview (default: 10)

    Returns:
        Collection metadata and preview data
    """
    try:
        logger.info(f"Getting collection detail: {collection_name} (limit: {limit})")

        import aiosqlite

        storage_db_path = Path(config.get("data.databases.storage"))

        if not storage_db_path.exists():
            raise HTTPException(status_code=404, detail="Storage database not found")

        table_name = f"{collection_name}_{user_id}"

        async with aiosqlite.connect(str(storage_db_path)) as db:
            # Check if table exists
            cursor = await db.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name = ?
            """, (table_name,))

            if not await cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"Collection not found: {collection_name}")

            # Get total count
            cursor = await db.execute(f"SELECT COUNT(*) FROM {table_name}")
            total_count = (await cursor.fetchone())[0]

            # Get column info
            cursor = await db.execute(f"PRAGMA table_info({table_name})")
            columns = await cursor.fetchall()
            all_fields = [col[1] for col in columns]
            data_fields = [col[1] for col in columns if col[1] not in ['id', 'created_at', 'updated_at']]

            # Get table size
            cursor = await db.execute(f"SELECT COUNT(*) FROM dbstat WHERE name=?", (table_name,))
            page_count = (await cursor.fetchone())[0]
            size_bytes = page_count * 4096

            # Get preview data
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM {table_name} ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            rows = await cursor.fetchall()

            # Convert to list of dicts
            preview_data = [dict(row) for row in rows]

            logger.info(f"Collection detail loaded: {total_count} records, previewing {len(preview_data)}")

            return {
                "collection_name": collection_name,
                "table_name": table_name,
                "total_records": total_count,
                "size_bytes": size_bytes,
                "fields": data_fields,
                "all_fields": all_fields,
                "preview_data": preview_data,
                "preview_count": len(preview_data)
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get collection detail: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/data/collections/{collection_name}")
async def delete_collection(collection_name: str, user_id: str):
    """Delete a collection and its related caches

    Args:
        collection_name: Name of the collection to delete
        user_id: User ID (default: default_user)

    Returns:
        Success message
    """
    try:
        logger.info(f"Deleting collection: {collection_name}")

        import aiosqlite

        storage_db_path = Path(config.get("data.databases.storage"))
        kv_db_path = Path(config.get("data.databases.kv"))

        if not storage_db_path.exists():
            raise HTTPException(status_code=404, detail="Storage database not found")

        table_name = f"{collection_name}_{user_id}"

        # Step 1: Drop the table from storage.db
        async with aiosqlite.connect(str(storage_db_path)) as db:
            # Check if table exists
            cursor = await db.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name = ?
            """, (table_name,))

            if not await cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"Collection not found: {collection_name}")

            # Drop the table
            await db.execute(f"DROP TABLE {table_name}")
            await db.commit()

            logger.info(f"✓ Dropped table: {table_name}")

        # Step 2: Delete related caches from kv.db
        # Cache key patterns for StorageAgent (updated format with user_id):
        # - storage_insert_{collection}_{user_id}
        # - storage_query_{collection}_{user_id}_{config_hash}
        # - storage_export_{collection}_{user_id}_{config_hash}
        cache_deleted_count = 0

        if kv_db_path.exists():
            async with aiosqlite.connect(str(kv_db_path)) as db:
                # Delete all cache entries related to this collection
                # Use exact prefix matching: storage_{operation}_{collection}_{user_id}
                patterns = [
                    f"storage_insert_{collection_name}_{user_id}",     # Exact match
                    f"storage_query_{collection_name}_{user_id}%",     # With hash suffix
                    f"storage_export_{collection_name}_{user_id}%",    # With hash suffix
                ]

                for pattern in patterns:
                    cursor = await db.execute(
                        "DELETE FROM kv_storage WHERE key LIKE ?",
                        (pattern,)
                    )
                    deleted = cursor.rowcount
                    if deleted > 0:
                        cache_deleted_count += deleted
                        logger.info(f"✓ Deleted {deleted} cache entries matching: {pattern}")

                await db.commit()

        logger.info(f"✅ Collection deleted: {collection_name} (table + {cache_deleted_count} cache entries)")

        return {
            "status": "success",
            "message": f"Collection '{collection_name}' deleted successfully",
            "cache_cleared": cache_deleted_count
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete collection: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/data/collections/{collection_name}/export")
async def export_collection(collection_name: str, user_id: str, limit: Optional[int] = None):
    """Export collection data as CSV

    Args:
        collection_name: Name of the collection
        user_id: User ID (default: default_user)
        limit: Optional limit on number of rows to export

    Returns:
        CSV file as downloadable attachment
    """
    try:
        logger.info(f"Exporting collection: {collection_name} (limit: {limit})")

        import aiosqlite
        import csv
        import io

        storage_db_path = Path(config.get("data.databases.storage"))

        if not storage_db_path.exists():
            raise HTTPException(status_code=404, detail="Storage database not found")

        table_name = f"{collection_name}_{user_id}"

        async with aiosqlite.connect(str(storage_db_path)) as db:
            # Check if table exists
            cursor = await db.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name = ?
            """, (table_name,))

            if not await cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"Collection not found: {collection_name}")

            # Query data
            db.row_factory = aiosqlite.Row
            if limit:
                cursor = await db.execute(
                    f"SELECT * FROM {table_name} ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
            else:
                cursor = await db.execute(f"SELECT * FROM {table_name} ORDER BY created_at DESC")

            rows = await cursor.fetchall()

            if not rows:
                raise HTTPException(status_code=404, detail="No data to export")

            # Create CSV in memory
            output = io.StringIO()
            fieldnames = rows[0].keys()
            writer = csv.DictWriter(output, fieldnames=fieldnames)

            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))

            # Return as downloadable file
            output.seek(0)

            logger.info(f"Exported {len(rows)} records from {collection_name}")

            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename={collection_name}_{user_id}.csv"
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export collection: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Intent Builder Agent APIs (SSE Streaming Proxy)
# ============================================================================

class StartIntentBuilderRequest(BaseModel):
    """Request model for starting Intent Builder session"""
    user_id: str
    user_query: str
    task_description: Optional[str] = None
    session_id: Optional[str] = None  # For resuming from recording
    metaflow_id: Optional[str] = None  # MetaFlow ID being modified
    workflow_id: Optional[str] = None  # Workflow ID being modified
    current_metaflow_yaml: Optional[str] = None  # Current MetaFlow content for context
    current_workflow_yaml: Optional[str] = None  # Current Workflow content for context
    phase: Optional[str] = None  # 'metaflow' or 'workflow'


class IntentBuilderChatRequest(BaseModel):
    """Request model for Intent Builder chat"""
    message: str


@app.post("/api/intent-builder/start")
async def start_intent_builder_session(
    request: StartIntentBuilderRequest,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """
    Start a new Intent Builder Agent session via Cloud Backend

    Headers:
        X-Ami-API-Key: User's Ami API key (optional, for API Proxy)

    Returns:
        {"session_id": "..."}
    """
    try:
        logger.info(f"Starting Intent Builder session for user: {request.user_id}")

        # Set user API key on cloud client
        if x_ami_api_key:
            cloud_client.set_user_api_key(x_ami_api_key)
            logger.info(f"Set user API key on cloud client: {x_ami_api_key[:10]}...")
        else:
            logger.warning("No X-Ami-API-Key header provided")

        # Forward to Cloud Backend
        result = await cloud_client.start_intent_builder_session(
            user_id=request.user_id,
            user_query=request.user_query,
            task_description=request.task_description,
            metaflow_id=request.metaflow_id,
            workflow_id=request.workflow_id,
            current_metaflow_yaml=request.current_metaflow_yaml,
            current_workflow_yaml=request.current_workflow_yaml,
            phase=request.phase
        )

        logger.info(f"Intent Builder session started: {result['session_id']}")
        return result

    except Exception as e:
        logger.error(f"Failed to start Intent Builder session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/intent-builder/{session_id}/stream")
async def stream_intent_builder_start(session_id: str):
    """
    Stream the initial response from Intent Builder Agent (SSE proxy)

    Returns SSE stream forwarded from Cloud Backend
    """
    try:
        logger.info(f"Streaming Intent Builder start: {session_id}")

        async def event_generator():
            async for event in cloud_client.stream_intent_builder_start(session_id):
                yield event

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    except Exception as e:
        logger.error(f"Failed to stream Intent Builder: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/intent-builder/{session_id}/chat")
async def stream_intent_builder_chat(session_id: str, request: IntentBuilderChatRequest):
    """
    Send a message and stream the response (SSE proxy)

    Returns SSE stream forwarded from Cloud Backend
    """
    try:
        logger.info(f"Streaming Intent Builder chat: {session_id}")

        async def event_generator():
            async for event in cloud_client.stream_intent_builder_chat(
                session_id, request.message
            ):
                yield event

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    except Exception as e:
        logger.error(f"Failed to stream Intent Builder chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/intent-builder/{session_id}/state")
async def get_intent_builder_state(session_id: str):
    """
    Get current state of Intent Builder session
    """
    try:
        return await cloud_client.get_intent_builder_state(session_id)
    except Exception as e:
        logger.error(f"Failed to get Intent Builder state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/intent-builder/{session_id}")
async def close_intent_builder_session(session_id: str):
    """
    Close and cleanup Intent Builder session
    """
    try:
        return await cloud_client.close_intent_builder_session(session_id)
    except Exception as e:
        logger.error(f"Failed to close Intent Builder session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Scraper Optimization Endpoints
# ============================================================================

class LoadWorkspaceRequest(BaseModel):
    """Request to load script workspace context"""
    user_id: str
    workflow_id: str
    step_id: str


class LoadWorkspaceResponse(BaseModel):
    """Response with workspace context"""
    success: bool
    script_path: Optional[str] = None
    requirement: Optional[Dict] = None
    script_content: Optional[str] = None
    has_script: bool = False
    cached_urls: List[Dict] = []  # List of cached DOM URLs
    error: Optional[str] = None


class ChatWithClaudeRequest(BaseModel):
    """Request to chat with Claude about script optimization"""
    user_id: str
    workflow_id: str
    step_id: str
    message: str
    conversation_history: List[Dict] = []


class ChatWithClaudeResponse(BaseModel):
    """Response from Claude chat"""
    success: bool
    response: str
    error: Optional[str] = None


@app.post("/api/scraper-optimization/load-workspace", response_model=LoadWorkspaceResponse)
async def load_scraper_workspace(request: LoadWorkspaceRequest):
    """Load script workspace context for optimization

    Args:
        request: Request with user_id, workflow_id, step_id

    Returns:
        Workspace context including script, requirements, etc.
    """
    try:
        from src.app_backend.services.scraper_optimization_service import ScraperOptimizationService

        service = ScraperOptimizationService(config)

        # Get script workspace
        workspace = service.get_script_workspace(
            request.user_id,
            request.workflow_id,
            request.step_id
        )

        if not workspace:
            return LoadWorkspaceResponse(
                success=False,
                error=f"Script workspace not found for workflow={request.workflow_id}, step={request.step_id}"
            )

        # Load workspace context
        context = service.load_workspace_context(workspace)

        return LoadWorkspaceResponse(
            success=True,
            script_path=context["script_path"],
            requirement=context["requirement"],
            script_content=context["script_content"],
            has_script=context["has_script"],
            cached_urls=context["cached_urls"]
        )

    except Exception as e:
        logger.error(f"Failed to load workspace: {e}", exc_info=True)
        return LoadWorkspaceResponse(
            success=False,
            error=str(e)
        )


@app.post("/api/scraper-optimization/chat", response_model=ChatWithClaudeResponse)
async def chat_with_claude_for_optimization(
    request: ChatWithClaudeRequest,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """Chat with Claude Agent for script optimization

    This endpoint:
    1. Loads the script workspace
    2. Passes user message to Claude Agent
    3. Claude analyzes, potentially modifies the script
    4. Returns Claude's response

    Args:
        request: Chat request with message and conversation history
        x_ami_api_key: User's API key from X-Ami-API-Key header

    Returns:
        Claude's response
    """
    try:
        from src.app_backend.services.scraper_optimization_service import ScraperOptimizationService

        service = ScraperOptimizationService(config)

        # Get script workspace
        workspace = service.get_script_workspace(
            request.user_id,
            request.workflow_id,
            request.step_id
        )

        if not workspace:
            return ChatWithClaudeResponse(
                success=False,
                response="",
                error=f"Script workspace not found for workflow={request.workflow_id}, step={request.step_id}"
            )

        # Chat with Claude (pass user's API key)
        result = await service.chat_with_claude(
            workspace=workspace,
            user_message=request.message,
            conversation_history=request.conversation_history,
            user_api_key=x_ami_api_key
        )

        return ChatWithClaudeResponse(
            success=result["success"],
            response=result["response"],
            error=result.get("error")
        )

    except Exception as e:
        logger.error(f"Chat with Claude failed: {e}", exc_info=True)
        return ChatWithClaudeResponse(
            success=False,
            response="",
            error=str(e)
        )


# ============================================================================
# Main Entry Point
# ============================================================================
# Resource Cleanup
# ============================================================================

async def cleanup_resources():
    """Cleanup all resources before shutdown

    This function is called by the lifespan shutdown context manager
    when uvicorn receives SIGTERM/SIGINT from the parent process (Tauri).
    """
    global browser_manager, workflow_executor, cdp_recorder, cloud_client

    logger.info("🧹 Cleaning up resources...")

    cleanup_errors = []

    try:
        # 1. Stop active recording if any
        if cdp_recorder and cdp_recorder._is_recording:
            logger.info("Stopping active recording...")
            try:
                await asyncio.wait_for(cdp_recorder.stop_recording(), timeout=3.0)
                logger.info("✓ Recording stopped")
            except asyncio.TimeoutError:
                logger.warning("⚠️  Recording stop timeout")
                cleanup_errors.append("Recording stop timeout")
            except Exception as e:
                logger.error(f"⚠️  Failed to stop recording: {e}")
                cleanup_errors.append(f"Recording: {e}")

        # 2. Cancel running workflow tasks
        if workflow_executor:
            logger.info("Checking for running workflow tasks...")
            running_tasks = [
                task_id for task_id, task in workflow_executor.tasks.items()
                if task.status == "running"
            ]

            if running_tasks:
                logger.info(f"Found {len(running_tasks)} running tasks, marking as cancelled...")
                for task_id in running_tasks:
                    task = workflow_executor.tasks[task_id]
                    task.status = "cancelled"
                    task.message = "Cancelled due to shutdown"
                logger.info("✓ Running tasks cancelled")
            else:
                logger.info("✓ No running tasks")

        # 3. Stop all browser sessions through BrowserManager
        # BrowserManager now manages ALL sessions (recording + workflows)
        if browser_manager:
            try:
                # Check if there are any managed sessions
                browser_status = browser_manager.get_status()
                total_sessions = browser_status.get('total_sessions', 0)

                if total_sessions > 0:
                    logger.info(f"Stopping browser manager ({total_sessions} sessions)...")
                    await asyncio.wait_for(
                        browser_manager.cleanup(),
                        timeout=5.0
                    )
                    logger.info("✓ Browser manager stopped, all sessions closed")
                else:
                    logger.info("✓ No active browser sessions")
            except asyncio.TimeoutError:
                logger.error("⚠️  Browser manager cleanup timeout")
                cleanup_errors.append("Browser manager: timeout")
            except Exception as e:
                logger.error(f"⚠️  Browser manager cleanup error: {e}")
                cleanup_errors.append(f"Browser manager: {e}")

        # 4. Close cloud client connection
        if cloud_client:
            logger.info("Closing cloud client...")
            try:
                await asyncio.wait_for(cloud_client.close(), timeout=2.0)
                logger.info("✓ Cloud client closed")
            except asyncio.TimeoutError:
                logger.warning("⚠️  Cloud client close timeout")
                cleanup_errors.append("Cloud client timeout")
            except Exception as e:
                logger.error(f"⚠️  Failed to close cloud client: {e}")
                cleanup_errors.append(f"Cloud: {e}")

        # 5. Summary
        if cleanup_errors:
            logger.warning(f"⚠️  Cleanup completed with {len(cleanup_errors)} errors: {cleanup_errors}")
        else:
            logger.info("✅ All resources cleaned up successfully")

    except Exception as e:
        logger.error(f"❌ Critical error during cleanup: {e}")
        import traceback
        traceback.print_exc()


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Start HTTP server"""
    port = config.get("daemon.port", 8765)
    host = config.get("daemon.host", "127.0.0.1")

    # DO NOT register signal handlers - uvicorn handles them automatically
    # and will call our lifespan shutdown context manager

    logger.info("=" * 60)
    logger.info(f"Starting App Backend daemon on {host}:{port}")
    logger.info("Process will respond to SIGTERM/SIGINT for graceful shutdown")
    logger.info("=" * 60)

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
