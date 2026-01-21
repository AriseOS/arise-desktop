#!/usr/bin/env python3
"""
App Backend Daemon - HTTP API Version
Provides REST API endpoints for desktop app communication
"""
import sys
import os
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from contextlib import asynccontextmanager

import uvicorn
import platform
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
        # daemon.py is at: src/clients/desktop_app/ami_daemon/daemon.py
        # Project root is 4 levels up
        project_root = Path(__file__).parent.parent.parent.parent.parent
        return project_root

# Add project root to sys.path
project_root = get_project_root()
sys.path.insert(0, str(project_root))

from src.clients.desktop_app.ami_daemon.core.config_service import get_config
from src.clients.desktop_app.ami_daemon.core.logging_config import setup_logging
from src.clients.desktop_app.ami_daemon.services.storage_manager import StorageManager
from src.clients.desktop_app.ami_daemon.services.browser_manager import BrowserManager
from src.clients.desktop_app.ami_daemon.services.workflow_executor import WorkflowExecutor
from src.clients.desktop_app.ami_daemon.services.workflow_history import WorkflowHistoryManager
from src.clients.desktop_app.ami_daemon.services.cdp_recorder import CDPRecorder
from src.clients.desktop_app.ami_daemon.services.cloud_client import CloudClient
from src.clients.desktop_app.ami_daemon.base_agent.tools.browser_use.extension_installer import ensure_extensions_installed
from src.clients.desktop_app.ami_daemon.routers.quick_task import router as quick_task_router, configure_service as configure_quick_task

# Load configuration first (needed for logging setup)
config = get_config()

# Configure logging with rotating file handlers from config
# - app.log: Main system log (rotates based on config)
# - error.log: Error-only log (WARNING and above)
# Note: Workflow execution logs are written separately to workflow_history/
log_level_str = config.get("logging.level", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)
log_dir = setup_logging(
    console_level=log_level,
    file_level=log_level,
    max_bytes=config.get("logging.max_bytes", 10 * 1024 * 1024),
    backup_count=config.get("logging.backup_count", 5),
)
logger = logging.getLogger(__name__)
logger.info("App Backend daemon starting")

# Global service instances
storage_manager = StorageManager(config.get("storage.base_path"))
browser_manager: Optional[BrowserManager] = None
workflow_executor: Optional[WorkflowExecutor] = None
history_manager: Optional[WorkflowHistoryManager] = None
cdp_recorder: Optional[CDPRecorder] = None
cloud_client: Optional[CloudClient] = None

# Version check result (populated on startup)
version_check_result: Optional[Dict[str, Any]] = None

# App version from config
APP_VERSION = config.get("app.version", "0.0.1")

# Magic identifier for health check (used to verify this is our daemon, not another service)
# Format: "ami-daemon-{version}"
DAEMON_MAGIC = f"ami-daemon-{APP_VERSION}"


def get_platform_identifier() -> str:
    """Get platform identifier for version check

    Returns:
        Platform string like "macos-arm64", "windows-x64", etc.
    """
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        if machine == "arm64":
            return "macos-arm64"
        else:
            return "macos-x64"
    elif system == "windows":
        return "windows-x64"
    elif system == "linux":
        return "linux-x64"
    else:
        return f"{system}-{machine}"

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
    global browser_manager, workflow_executor, history_manager, cdp_recorder, cloud_client, version_check_result

    # ========== STARTUP ==========
    logger.info("=" * 60)
    logger.info(f"Starting Ami App Backend v{APP_VERSION}...")
    logger.info("=" * 60)

    try:
        # Initialize cloud client first (needed for version check)
        cloud_client = CloudClient(
            api_url=config.get("cloud.api_url", "https://api.ami.com")
        )
        logger.info("✓ Cloud client initialized")
        logger.info(f"  Cloud Backend URL: {config.get('cloud.api_url', 'https://api.ami.com')}")

        # Version check with Cloud Backend
        platform_id = get_platform_identifier()
        logger.info(f"✓ Checking version compatibility (v{APP_VERSION} on {platform_id})...")
        version_check_result = await cloud_client.check_version(APP_VERSION, platform_id)

        if not version_check_result.get("compatible", True):
            logger.warning("=" * 60)
            logger.warning("⚠️  VERSION UPDATE REQUIRED")
            logger.warning(f"   Current version: {APP_VERSION}")
            logger.warning(f"   Minimum version: {version_check_result.get('minimum_version')}")
            logger.warning(f"   Update URL: {version_check_result.get('update_url')}")
            logger.warning("=" * 60)
            # Store result but continue startup - frontend will handle blocking
        else:
            logger.info(f"✓ Version {APP_VERSION} is compatible")

        # Install bundled browser extensions to browser-use cache (avoids Google download in China)
        if ensure_extensions_installed():
            logger.info("✓ Browser extensions installed")
        else:
            logger.warning("⚠️ Browser extensions not available (may need to download from Google)")

        # Initialize browser manager (but do NOT start browser yet - on-demand startup)
        browser_manager = BrowserManager(config_service=config)
        logger.info("✓ Browser manager initialized (browser not started - will start on demand)")

        # Initialize workflow history manager
        history_manager = WorkflowHistoryManager(
            base_path=storage_manager.base_path,
            retention_days=60,
        )
        # Clean up old runs on startup
        cleaned = history_manager.cleanup_old_runs()
        if cleaned > 0:
            logger.info(f"✓ Workflow history manager initialized (cleaned {cleaned} old runs)")
        else:
            logger.info("✓ Workflow history manager initialized")

        # Initialize workflow executor with history manager and cloud client for auto-upload
        workflow_executor = WorkflowExecutor(
            storage_manager, browser_manager, history_manager,
            cloud_client=cloud_client,
            auto_upload_logs=True
        )

        # Set up progress callback for WebSocket updates
        workflow_executor.set_progress_callback(ws_manager.send_progress_update)
        logger.info("✓ Workflow executor initialized with WebSocket progress callback")

        # Initialize CDP recorder
        cdp_recorder = CDPRecorder(storage_manager, browser_manager)
        logger.info("✓ CDP recorder initialized")

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

# Include quick task router
app.include_router(quick_task_router)


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


class CurrentOperationsResponse(BaseModel):
    """Response model for getting current recording operations"""
    is_recording: bool
    session_id: Optional[str] = None
    operations_count: int = 0
    operations: List[Dict[str, Any]] = []


class UploadRecordingRequest(BaseModel):
    task_description: str
    user_query: Optional[str] = None  # What user wants to do
    user_id: str


class UploadRecordingResponse(BaseModel):
    recording_id: str
    status: str


class AnalyzeRecordingRequest(BaseModel):
    """Request model for analyzing recording"""
    user_id: str  # session_id is in URL path


class AnalyzeRecordingResponse(BaseModel):
    """Response model for recording analysis"""
    name: str
    task_description: str
    user_query: str
    detected_patterns: Dict[str, Any]


class UpdateRecordingMetadataRequest(BaseModel):
    """Request model for updating recording metadata"""
    task_description: str
    user_query: str
    name: Optional[str] = None
    user_id: str  # session_id is in URL path


class GenerateWorkflowResponse(BaseModel):
    """Unified workflow generation response"""
    workflow_id: Optional[str] = None
    workflow_name: str
    local_path: str
    status: str = "success"


class ExecuteWorkflowRequest(BaseModel):
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


# Workflow History Models
class WorkflowHistoryEntry(BaseModel):
    """Entry in the workflow history list"""
    task_id: str  # Unified execution identifier
    workflow_id: str
    workflow_name: str
    started_at: str
    status: str
    error_summary: Optional[str] = None


class WorkflowHistoryListResponse(BaseModel):
    """Response for listing workflow history"""
    runs: List[WorkflowHistoryEntry]
    total: int


class WorkflowRunDetail(BaseModel):
    """Detailed information about a workflow run"""
    task_id: str  # Unified execution identifier
    workflow_id: str
    workflow_name: str
    user_id: str
    device_id: str
    app_version: str
    started_at: str
    finished_at: Optional[str] = None
    status: str
    error_summary: Optional[str] = None
    steps_total: int
    steps_completed: int


class WorkflowRunLog(BaseModel):
    """A single log entry from a workflow run"""
    ts: str
    step: int
    action: str
    target: Optional[str] = None
    status: str
    duration_ms: Optional[int] = None
    message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class WorkflowRunDetailResponse(BaseModel):
    """Response for getting workflow run detail"""
    meta: WorkflowRunDetail
    logs: List[WorkflowRunLog]
    workflow_yaml: Optional[str] = None


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
# Health Check & Version Info
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint with magic identifier for daemon detection"""
    return {
        "status": "ok",
        "magic": DAEMON_MAGIC,
        "version": APP_VERSION,
        "browser_ready": browser_manager.is_ready() if browser_manager else False
    }


@app.get("/api/v1/app/version")
async def get_app_version():
    """Get app version and update status

    Returns:
        {
            "version": "0.0.1",
            "platform": "macos-arm64",
            "compatible": true/false,
            "update_required": true/false,
            "minimum_version": "0.0.1",
            "update_url": "http://..." (if update required)
        }
    """
    platform_id = get_platform_identifier()

    response = {
        "version": APP_VERSION,
        "platform": platform_id,
        "compatible": True,
        "update_required": False
    }

    if version_check_result:
        response["compatible"] = version_check_result.get("compatible", True)
        response["update_required"] = not response["compatible"]
        response["minimum_version"] = version_check_result.get("minimum_version")

        if not response["compatible"]:
            response["update_url"] = version_check_result.get("update_url")
            response["message"] = version_check_result.get("message")

    return response


@app.post("/api/v1/app/diagnostic")
async def upload_diagnostic(data: dict = None):
    """Collect and upload diagnostic package to Cloud Backend.

    This endpoint collects:
    - Recent system logs (last 1000 lines)
    - Recent workflow execution summaries (last 20)
    - Device and app information

    Body:
        {
            "user_id": "required - user identifier",
            "user_description": "optional - description of the issue..."
        }

    Returns:
        {
            "success": true,
            "diagnostic_id": "DIAG-20250115-abc123"
        }
    """
    import platform as plat
    from pathlib import Path
    from datetime import datetime
    import uuid

    if not cloud_client:
        raise HTTPException(status_code=500, detail="Cloud client not initialized")

    # Validate user_id
    user_id = data.get("user_id") if data else None
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing user_id")

    try:
        user_description = data.get("user_description") if data else None

        # Generate diagnostic ID
        date_str = datetime.now().strftime("%Y%m%d")
        random_str = uuid.uuid4().hex[:6].upper()
        diagnostic_id = f"DIAG-{date_str}-{random_str}"

        # Collect system logs (last 5000 lines)
        system_logs = []
        log_path = Path.home() / ".ami" / "logs" / "app.log"
        if log_path.exists():
            try:
                # Cross-platform encoding handling:
                # - utf-8-sig: Auto-removes BOM if present (Windows), acts as utf-8 if not (macOS/Linux)
                # - errors="replace": Replaces invalid bytes with � instead of raising exceptions
                # - This ensures JSON serialization works regardless of file encoding issues
                with open(log_path, "r", encoding="utf-8-sig", errors="replace") as f:
                    lines = f.readlines()
                    # Strip each line to remove platform-specific line endings and control chars
                    system_logs = [line.strip() for line in lines[-5000:]]  # Last 5000 lines
            except Exception as e:
                logger.warning(f"Failed to read system logs: {e}")

        # Collect recent workflow executions
        recent_executions = []
        if history_manager:
            try:
                runs = history_manager.list_runs(limit=20)
                recent_executions = [run.to_dict() for run in runs]
            except Exception as e:
                logger.warning(f"Failed to get recent executions: {e}")

        # Collect device info
        device_info = {
            "os": plat.system(),
            "os_version": plat.release(),
            "os_full": plat.platform(),
            "machine": plat.machine(),
            "python_version": plat.python_version(),
            "app_version": APP_VERSION,
            "platform_id": get_platform_identifier(),
        }

        # Build diagnostic package
        diagnostic_data = {
            "type": "diagnostic",
            "diagnostic_id": diagnostic_id,
            "device_id": history_manager.device_id if history_manager else "unknown",
            "app_version": APP_VERSION,
            "timestamp": datetime.now().isoformat(),
            "system_logs": system_logs,
            "recent_executions": recent_executions,
            "device_info": device_info,
            "user_description": user_description,
        }

        # Upload to cloud
        result = await cloud_client.upload_diagnostic(diagnostic_data, user_id)

        if result.get("success"):
            return {
                "success": True,
                "diagnostic_id": result.get("diagnostic_id", diagnostic_id),
                "message": "Diagnostic package uploaded successfully"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload diagnostic: {result.get('error')}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to collect/upload diagnostic: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/app/shutdown")
async def shutdown_app():
    """Graceful shutdown endpoint for cross-platform process termination.

    This endpoint is called by the Tauri app (especially on Windows) to trigger
    a graceful shutdown of the daemon. It ensures all resources are properly
    cleaned up before the process exits.

    Flow:
    1. Respond to the HTTP request immediately (so caller knows shutdown started)
    2. Schedule cleanup and exit in background
    3. Process exits after cleanup completes

    Returns:
        {"success": true, "message": "Shutdown initiated"}
    """
    import os
    import signal

    logger.info("🛑 Shutdown requested via API")

    async def cleanup_and_exit():
        """Background task to cleanup and exit"""
        await asyncio.sleep(0.1)  # Let response be sent first
        logger.info("Starting graceful shutdown...")

        try:
            await cleanup_resources()
            cleanup_port_file()
            logger.info("✅ Cleanup complete, exiting process")
        except Exception as e:
            logger.error(f"Error during shutdown cleanup: {e}")
        finally:
            # Exit the process
            # Use os._exit to ensure immediate termination after cleanup
            os._exit(0)

    # Schedule cleanup in background so we can respond first
    asyncio.create_task(cleanup_and_exit())

    return {"success": True, "message": "Shutdown initiated"}


# ============================================================================
# Browser Control APIs
# ============================================================================

@app.post("/api/v1/browser/start")
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


@app.post("/api/v1/browser/stop")
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


@app.get("/api/v1/browser/status")
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


@app.get("/api/v1/browser/window/layout")
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


@app.post("/api/v1/browser/window/update")
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

        return {
            "layout": browser_manager.window_manager.get_layout_info(),
            "applied": False,
            "message": "Window arrangement is disabled"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update window layout: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/browser/window/arrange")
async def arrange_windows():
    """Manually trigger window arrangement (disabled)

    Returns:
        Disabled message
    """
    return {
        "success": False,
        "message": "Window arrangement is disabled due to macOS permission issues"
    }


# ============================================================================
# Dashboard API
# ============================================================================

@app.get("/api/v1/dashboard")
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

            # Format creation time
            created_at_str = workflow.get('created_at')
            created_date = "unknown"
            if created_at_str:
                try:
                    dt = datetime.fromisoformat(created_at_str)
                    created_date = dt.strftime("%Y-%m-%d")
                except Exception:
                    pass

            recent_workflows.append({
                "id": workflow_id,
                "name": workflow['name'],
                "lastRun": last_run,
                "status": status,
                "createdDate": created_date
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

@app.post("/api/v1/recordings/start", response_model=StartRecordingResponse)
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
            # start_browser returns when browser is fully ready - no sleep needed
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


@app.post("/api/v1/recordings/stop", response_model=StopRecordingResponse)
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


@app.get("/api/v1/recordings/current/operations", response_model=CurrentOperationsResponse)
async def get_current_operations():
    """Get current recording operations in real-time

    This endpoint is used for polling during active recording to show
    real-time feedback of captured user operations.
    """
    try:
        if not cdp_recorder or not cdp_recorder._is_recording:
            return CurrentOperationsResponse(
                is_recording=False,
                session_id=None,
                operations_count=0,
                operations=[]
            )

        return CurrentOperationsResponse(
            is_recording=True,
            session_id=cdp_recorder.current_session_id,
            operations_count=len(cdp_recorder.operations),
            operations=cdp_recorder.operations
        )

    except Exception as e:
        logger.error(f"Failed to get current operations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/recordings/{session_id}/analyze", response_model=AnalyzeRecordingResponse)
async def analyze_recording(
    session_id: str,
    request: AnalyzeRecordingRequest,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """Analyze recording and generate suggested task_description and user_query using AI"""
    try:
        logger.info(f"Analyzing recording: session_id={session_id}")
        logger.info(f"X-Ami-API-Key header received: {x_ami_api_key[:10] if x_ami_api_key else 'None'}...")

        # Set user API key on cloud client
        if x_ami_api_key:
            cloud_client.set_user_api_key(x_ami_api_key)
            logger.info(f"Set user API key on cloud client: {x_ami_api_key[:10]}...")
            logger.info(f"CloudClient headers: {dict(cloud_client.client.headers)}")
        else:
            logger.warning("No X-Ami-API-Key header provided")

        # 1. Load recording
        recording_data = storage_manager.get_recording(request.user_id, session_id)
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


@app.patch("/api/v1/recordings/{session_id}")
async def update_recording_metadata(session_id: str, request: UpdateRecordingMetadataRequest):
    """Update recording metadata with task_description and user_query after user confirmation"""
    try:
        logger.info(f"Updating metadata for recording: session_id={session_id}")
        if request.name:
            logger.info(f"  Name: {request.name}")
        if request.task_description:
            logger.info(f"  Task Description: {request.task_description[:100]}...")
        if request.user_query:
            logger.info(f"  User Query: {request.user_query[:100]}...")

        # Update metadata in storage
        storage_manager.update_recording_metadata(
            user_id=request.user_id,
            session_id=session_id,
            task_description=request.task_description,
            user_query=request.user_query,
            name=request.name
        )

        logger.info("Metadata updated successfully")
        return {"success": True, "message": "Metadata updated"}

    except Exception as e:
        logger.error(f"Failed to update metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/recordings/{session_id}/workflow")
async def clear_recording_workflow(session_id: str, user_id: str):
    """Clear the workflow_id from a recording (when workflow is deleted)"""
    try:
        logger.info(f"Clearing workflow_id for recording: session_id={session_id}")
        storage_manager.clear_recording_workflow_id(user_id, session_id)

        # Get updated recording to sync to cloud
        recording = storage_manager.get_recording(user_id, session_id)
        updated_at = recording.get("updated_at")

        # Sync to cloud (background, don't block response)
        try:
            await cloud_client.update_recording_metadata(
                recording_id=session_id,
                user_id=user_id,
                workflow_id="",  # Empty string signals "clear"
                updated_at=updated_at
            )
            logger.info("Synced workflow_id clear to Cloud")
        except Exception as sync_error:
            logger.warning(f"Failed to sync to Cloud (will retry on next access): {sync_error}")

        logger.info("Workflow ID cleared successfully")
        return {"success": True, "message": "Workflow ID cleared"}
    except Exception as e:
        logger.error(f"Failed to clear workflow_id: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/recordings")
async def list_recordings(user_id: str):
    """List all recordings for a user, merging local and cloud data"""
    try:
        logger.info(f"Listing recordings for user: {user_id}")

        # Step 1: Get local recordings
        local_recordings = storage_manager.list_recordings(user_id)
        local_by_id = {r["session_id"]: r for r in local_recordings}
        logger.info(f"Found {len(local_recordings)} local recordings")

        # Step 2: Get cloud recordings (best effort)
        try:
            cloud_recordings = await cloud_client.list_recordings(user_id)
            logger.info(f"Found {len(cloud_recordings)} cloud recordings")

            # Merge cloud recordings into local list
            for cloud_rec in cloud_recordings:
                recording_id = cloud_rec.get("recording_id")
                if recording_id and recording_id not in local_by_id:
                    # Cloud-only recording - add to list with cloud_only flag
                    local_by_id[recording_id] = {
                        "session_id": recording_id,
                        "name": cloud_rec.get("task_description", ""),
                        "created_at": cloud_rec.get("created_at"),
                        "workflow_id": cloud_rec.get("workflow_id"),
                        "cloud_only": True  # Flag to indicate not downloaded locally
                    }
        except Exception as cloud_error:
            logger.warning(f"Failed to fetch cloud recordings: {cloud_error}")

        # Sort by created_at (newest first)
        recordings = sorted(
            local_by_id.values(),
            key=lambda x: x.get("created_at") or "",
            reverse=True
        )

        return {
            "recordings": recordings,
            "count": len(recordings)
        }
    except Exception as e:
        logger.error(f"Failed to list recordings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/recordings/{session_id}")
async def get_recording_detail(session_id: str, user_id: str):
    """Get detailed recording information with cloud sync"""
    try:
        logger.info(f"Getting recording detail: session_id={session_id}")
        detail = storage_manager.get_recording_detail(user_id, session_id)

        # If not found locally, try to download from cloud
        if detail is None:
            logger.info(f"Recording not found locally, trying cloud: {session_id}")
            try:
                cloud_recording = await cloud_client.get_recording(session_id, user_id)
                if cloud_recording and cloud_recording.get("operations"):
                    # Download from cloud and save locally
                    logger.info(f"Downloading recording from cloud: {session_id}")
                    recording_data = {
                        "operations": cloud_recording.get("operations", []),
                        "task_metadata": {
                            "task_description": cloud_recording.get("task_description"),
                            "user_query": cloud_recording.get("user_query")
                        },
                        "workflow_id": cloud_recording.get("workflow_id"),
                        "updated_at": cloud_recording.get("updated_at"),
                        "created_at": cloud_recording.get("created_at")
                    }
                    storage_manager.save_recording(user_id, session_id, recording_data, update_timestamp=False)
                    logger.info(f"Recording downloaded from cloud: {session_id}")

                    # Now get the detail from local storage
                    detail = storage_manager.get_recording_detail(user_id, session_id)
            except Exception as cloud_error:
                logger.warning(f"Failed to download from cloud: {cloud_error}")

        if detail is None:
            raise HTTPException(status_code=404, detail=f"Recording not found: {session_id}")

        # Try to sync with Cloud Backend based on updated_at timestamp
        try:
            cloud_recording = await cloud_client.get_recording(session_id, user_id)
            if cloud_recording:
                local_updated_at = detail.get("updated_at")
                cloud_updated_at = cloud_recording.get("updated_at")

                logger.info(f"Recording sync check: local={local_updated_at}, cloud={cloud_updated_at}")

                # Compare timestamps to determine sync direction
                from src.common.timestamp_utils import parse_timestamp
                local_dt = parse_timestamp(local_updated_at) if local_updated_at else None
                cloud_dt = parse_timestamp(cloud_updated_at) if cloud_updated_at else None

                if cloud_dt and (not local_dt or cloud_dt > local_dt):
                    # Cloud is newer - update local with cloud data
                    logger.info(f"Cloud is newer, updating local recording")
                    storage_manager.update_recording_from_cloud(user_id, session_id, cloud_recording)
                    # Refresh detail with updated data
                    detail = storage_manager.get_recording_detail(user_id, session_id)
                elif local_dt and (not cloud_dt or local_dt > cloud_dt):
                    # Local is newer - upload to cloud
                    logger.info(f"Local is newer, syncing to cloud")
                    local_recording = storage_manager.get_recording(user_id, session_id)
                    task_metadata = local_recording.get("task_metadata", {})
                    try:
                        await cloud_client.update_recording_metadata(
                            recording_id=session_id,
                            user_id=user_id,
                            workflow_id=local_recording.get("workflow_id", ""),
                            task_description=task_metadata.get("task_description"),
                            user_query=task_metadata.get("user_query"),
                            updated_at=local_updated_at
                        )
                        logger.info("Synced local recording to Cloud")
                    except Exception as sync_error:
                        logger.warning(f"Failed to sync to Cloud: {sync_error}")

                # After sync, use local data (it's now authoritative)
                if detail.get("workflow_id"):
                    pass  # Keep local workflow_id
                elif cloud_recording.get("workflow_id"):
                    detail["workflow_id"] = cloud_recording["workflow_id"]
                if cloud_recording.get("task_description") and not detail.get("name"):
                    detail["name"] = cloud_recording["task_description"]

        except Exception as e:
            logger.warning(f"Could not sync with Cloud: {e}")

        return detail
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get recording detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/recordings/{session_id}")
async def delete_recording(session_id: str, user_id: str):
    """Delete a recording from both local and cloud storage"""
    try:
        logger.info(f"Deleting recording: session_id={session_id}")

        # Step 1: Delete from local storage
        success = storage_manager.delete_recording(user_id, session_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Recording not found: {session_id}")

        logger.info(f"Recording deleted from local storage: {session_id}")

        # Step 2: Sync deletion to cloud (best effort, don't fail if cloud delete fails)
        try:
            cloud_success = await cloud_client.delete_recording(session_id, user_id)
            if cloud_success:
                logger.info(f"Recording deleted from cloud: {session_id}")
            else:
                logger.warning(f"Recording not found in cloud or already deleted: {session_id}")
        except Exception as cloud_error:
            # Don't fail the request if cloud deletion fails
            logger.warning(f"Failed to delete recording from cloud (continuing): {cloud_error}")

        return {"status": "success", "message": "Recording deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Recording Upload API
# ============================================================================

@app.post("/api/v1/recordings/{session_id}/upload", response_model=UploadRecordingResponse)
async def upload_recording_to_cloud(
    session_id: str,
    request: UploadRecordingRequest,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """Upload recording to Cloud Backend for intent extraction

    Headers:
        X-Ami-API-Key: User's Ami API key (optional, for API Proxy)
    """
    try:
        logger.info(f"Uploading recording from session: {session_id}")

        # Update cloud client with user's API key if provided
        update_cloud_client_api_key(x_ami_api_key)

        # Load operations from local storage (includes dom_snapshots if available)
        recording_data = storage_manager.get_recording(
            request.user_id, session_id
        )
        operations = recording_data.get("operations", [])
        dom_snapshots = recording_data.get("dom_snapshots", {})

        # Upload recording to Cloud Backend (with task_description, user_query, and DOM snapshots)
        # Use session_id as recording_id to keep IDs in sync between local and cloud
        recording_id = await cloud_client.upload_recording(
            operations=operations,
            task_description=request.task_description,
            user_query=request.user_query,
            user_id=request.user_id,
            recording_id=session_id,
            dom_snapshots=dom_snapshots
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
# Workflow Resource Sync Functions
# ============================================================================

async def sync_workflow_resources(workflow_id: str, user_id: str) -> Dict[str, Any]:
    """Synchronize workflow resources between local and cloud

    This is the main sync orchestration function called when user views workflow.
    It compares timestamps and decides whether to upload or download.

    Args:
        workflow_id: Workflow ID
        user_id: User ID

    Returns:
        dict with sync result:
        {
            "synced": true/false,
            "direction": "upload"/"download"/"none",
            "message": "...",
            "files_transferred": 5
        }
    """
    from src.common.services.simple_sync import SimpleSync

    try:
        logger.info(f"[Sync] Checking sync for workflow {workflow_id}")

        # Get local workflow path
        home_dir = Path.home()
        ami_root = home_dir / ".ami"
        local_workflow_path = ami_root / "users" / user_id / "workflows" / workflow_id

        # Read local metadata
        local_metadata_path = local_workflow_path / "metadata.json"
        local_metadata = None
        local_updated_at = None

        if local_metadata_path.exists():
            with open(local_metadata_path, 'r', encoding='utf-8') as f:
                local_metadata = json.load(f)
                local_updated_at = local_metadata.get("updated_at")

        # Get cloud metadata
        cloud_metadata = await cloud_client.get_workflow_metadata(workflow_id, user_id)
        cloud_updated_at = cloud_metadata.get("updated_at") if cloud_metadata else None

        logger.info(f"[Sync] Timestamps - Local: {local_updated_at}, Cloud: {cloud_updated_at}")

        # Decide sync direction based on timestamps
        if not local_updated_at and not cloud_updated_at:
            logger.info(f"[Sync] No metadata found on either side for {workflow_id}")
            return {"synced": False, "direction": "none", "message": "No metadata found"}

        # Parse timestamps for proper comparison
        from src.common.timestamp_utils import parse_timestamp, compare_timestamps

        local_dt = parse_timestamp(local_updated_at) if local_updated_at else None
        cloud_dt = parse_timestamp(cloud_updated_at) if cloud_updated_at else None

        if not cloud_dt or (local_dt and local_dt > cloud_dt):
            # Local is newer or cloud doesn't exist → Upload
            logger.info(f"[Sync] Local is newer, uploading to cloud")
            return await upload_to_cloud(workflow_id, user_id, local_metadata, local_workflow_path)

        elif not local_dt or cloud_dt > local_dt:
            # Cloud is newer or local doesn't exist → Download
            logger.info(f"[Sync] Cloud is newer, downloading from cloud")
            return await download_from_cloud(workflow_id, user_id, cloud_metadata, local_workflow_path)

        else:
            # Timestamps are equal → No sync needed
            logger.info(f"[Sync] Timestamps match, no sync needed for {workflow_id}")
            return {"synced": False, "direction": "none", "message": "Already in sync"}

    except Exception as e:
        logger.error(f"[Sync] Failed to sync workflow {workflow_id}: {e}")
        return {"synced": False, "direction": "error", "message": str(e)}


async def download_from_cloud(
    workflow_id: str,
    user_id: str,
    cloud_metadata: Dict[str, Any],
    local_workflow_path: Path
) -> Dict[str, Any]:
    """Download resources from cloud to local

    Args:
        workflow_id: Workflow ID
        user_id: User ID
        cloud_metadata: Cloud metadata.json content
        local_workflow_path: Local workflow directory path

    Returns:
        Sync result dict
    """
    logger.info(f"[Download] Starting download from cloud for {workflow_id}")

    files_downloaded = 0
    errors = []

    try:
        # Step 1: Download workflow.yaml (required)
        try:
            logger.info(f"[Download] Downloading workflow.yaml")
            workflow_yaml_content = await cloud_client.download_workflow_file(workflow_id, "workflow.yaml", user_id)

            # Save workflow.yaml to local
            workflow_yaml_path = local_workflow_path / "workflow.yaml"
            workflow_yaml_path.parent.mkdir(parents=True, exist_ok=True)
            workflow_yaml_path.write_bytes(workflow_yaml_content)

            logger.info(f"[Download] ✓ workflow.yaml ({len(workflow_yaml_content)} bytes)")
            files_downloaded += 1
        except Exception as e:
            error_msg = f"Failed to download workflow.yaml: {e}"
            logger.error(f"[Download] ✗ {error_msg}")
            errors.append(error_msg)
            # workflow.yaml is critical - if it fails, the whole download fails
            raise Exception(f"Cannot download workflow without workflow.yaml: {e}")

        # Step 2: Process each resource type
        resources = cloud_metadata.get("resources", {})

        for resource_type, resource_list in resources.items():
            if not isinstance(resource_list, list):
                continue

            logger.info(f"[Download] Processing {len(resource_list)} {resource_type}")

            for resource in resource_list:
                step_id = resource.get("step_id")
                files = resource.get("files", [])

                logger.info(f"[Download] Resource: step {step_id} ({len(files)} files)")

                for filename in files:
                    try:
                        # Construct file path: step_id/filename
                        file_path = f"{step_id}/{filename}"

                        # Download file
                        content = await cloud_client.download_workflow_file(workflow_id, file_path, user_id)

                        # Save to local
                        local_file_path = local_workflow_path / step_id / filename
                        local_file_path.parent.mkdir(parents=True, exist_ok=True)
                        local_file_path.write_bytes(content)

                        logger.info(f"[Download] ✓ {file_path} ({len(content)} bytes)")
                        files_downloaded += 1

                    except Exception as e:
                        error_msg = f"Failed to download {filename}: {e}"
                        logger.error(f"[Download] ✗ {error_msg}")
                        errors.append(error_msg)

        # Save local metadata with cloud timestamp (CRITICAL: preserve timestamp)
        local_metadata_path = local_workflow_path / "metadata.json"
        local_metadata_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_metadata_path, 'w', encoding='utf-8') as f:
            json.dump(cloud_metadata, f, indent=2, ensure_ascii=False)

        logger.info(f"[Download] Saved metadata.json (timestamp: {cloud_metadata.get('updated_at')})")

        result = {
            "synced": True,
            "direction": "download",
            "message": f"Downloaded {files_downloaded} files from cloud",
            "files_transferred": files_downloaded
        }

        if errors:
            result["errors"] = errors

        return result

    except Exception as e:
        logger.error(f"[Download] Failed: {e}")
        return {
            "synced": False,
            "direction": "download",
            "message": f"Download failed: {e}",
            "files_transferred": files_downloaded,
            "errors": errors
        }


async def upload_to_cloud(
    workflow_id: str,
    user_id: str,
    local_metadata: Dict[str, Any],
    local_workflow_path: Path
) -> Dict[str, Any]:
    """Upload resources from local to cloud

    Args:
        workflow_id: Workflow ID
        user_id: User ID
        local_metadata: Local metadata.json content
        local_workflow_path: Local workflow directory path

    Returns:
        Sync result dict
    """
    from src.common.services.simple_sync import SimpleSync

    logger.info(f"[Upload] Starting upload to cloud for {workflow_id}")

    files_uploaded = 0
    errors = []
    sync = SimpleSync()  # Use default ignore patterns

    try:
        # Step 1: Upload workflow.yaml (required)
        workflow_yaml_path = local_workflow_path / "workflow.yaml"
        if workflow_yaml_path.exists():
            try:
                logger.info(f"[Upload] Uploading workflow.yaml")
                workflow_yaml_content = workflow_yaml_path.read_bytes()
                success = await cloud_client.upload_workflow_file(workflow_id, "workflow.yaml", workflow_yaml_content, user_id)
                if success:
                    logger.info(f"[Upload] ✓ workflow.yaml ({len(workflow_yaml_content)} bytes)")
                    files_uploaded += 1
                else:
                    error_msg = "Failed to upload workflow.yaml"
                    logger.error(f"[Upload] ✗ {error_msg}")
                    errors.append(error_msg)
            except Exception as e:
                error_msg = f"Failed to upload workflow.yaml: {e}"
                logger.error(f"[Upload] ✗ {error_msg}")
                errors.append(error_msg)
                # workflow.yaml is critical - if it fails, we should report but continue
        else:
            logger.warning(f"[Upload] workflow.yaml not found at {workflow_yaml_path}")

        # Step 2: Process each resource type
        resources = local_metadata.get("resources", {})

        for resource_type, resource_list in resources.items():
            if not isinstance(resource_list, list):
                continue

            logger.info(f"[Upload] Processing {len(resource_list)} {resource_type}")

            for resource in resource_list:
                step_id = resource.get("step_id")

                # Collect files using SimpleSync (auto-ignore dom_snapshots/, etc.)
                resource_path = local_workflow_path / step_id

                if not resource_path.exists():
                    logger.warning(f"[Upload] Resource path not found: {resource_path}")
                    continue

                files_to_upload = sync.collect_files(resource_path)
                logger.info(f"[Upload] Resource: step {step_id} ({len(files_to_upload)} files after filtering)")

                for rel_path, abs_path in files_to_upload.items():
                    try:
                        # Construct cloud file path: step_id/filename
                        file_path = f"{step_id}/{rel_path}"

                        # Read file content
                        content = abs_path.read_bytes()

                        # Upload file
                        success = await cloud_client.upload_workflow_file(workflow_id, file_path, content, user_id)

                        if success:
                            logger.info(f"[Upload] ✓ {file_path} ({len(content)} bytes)")
                            files_uploaded += 1
                        else:
                            error_msg = f"Upload returned false for {rel_path}"
                            logger.error(f"[Upload] ✗ {error_msg}")
                            errors.append(error_msg)

                    except Exception as e:
                        error_msg = f"Failed to upload {rel_path}: {e}"
                        logger.error(f"[Upload] ✗ {error_msg}")
                        errors.append(error_msg)

        # Upload metadata with local timestamp (CRITICAL: preserve timestamp)
        success = await cloud_client.save_workflow_metadata(workflow_id, local_metadata, user_id)

        if success:
            logger.info(f"[Upload] Saved metadata.json to cloud (timestamp: {local_metadata.get('updated_at')})")
        else:
            logger.error(f"[Upload] Failed to save metadata.json to cloud")
            errors.append("Failed to save metadata")

        result = {
            "synced": True,
            "direction": "upload",
            "message": f"Uploaded {files_uploaded} files to cloud",
            "files_transferred": files_uploaded
        }

        if errors:
            result["errors"] = errors

        return result

    except Exception as e:
        logger.error(f"[Upload] Failed: {e}")
        return {
            "synced": False,
            "direction": "upload",
            "message": f"Upload failed: {e}",
            "files_transferred": files_uploaded,
            "errors": errors
        }


# ============================================================================
# Workflow Sync API Endpoints
# ============================================================================

@app.get("/api/v1/workflows/{workflow_id}/sync/status")
async def get_workflow_sync_status(workflow_id: str, user_id: str):
    """Check sync status between local and cloud

    Returns:
        {
            "needs_sync": bool,
            "direction": "upload" | "download" | "none",
            "local_updated_at": str | null,
            "cloud_updated_at": str | null
        }
    """
    try:
        logger.info(f"[SyncStatus] Checking sync status for workflow {workflow_id}")

        # Get local workflow path
        home_dir = Path.home()
        ami_root = home_dir / ".ami"
        local_workflow_path = ami_root / "users" / user_id / "workflows" / workflow_id

        # Read local metadata
        local_metadata_path = local_workflow_path / "metadata.json"
        local_updated_at = None

        if local_metadata_path.exists():
            with open(local_metadata_path, 'r', encoding='utf-8') as f:
                local_metadata = json.load(f)
                local_updated_at = local_metadata.get("updated_at")

        # Get cloud metadata
        cloud_metadata = await cloud_client.get_workflow_metadata(workflow_id, user_id)
        cloud_updated_at = cloud_metadata.get("updated_at") if cloud_metadata else None

        # Determine sync direction
        from src.common.timestamp_utils import parse_timestamp

        local_dt = parse_timestamp(local_updated_at) if local_updated_at else None
        cloud_dt = parse_timestamp(cloud_updated_at) if cloud_updated_at else None

        if not local_dt and not cloud_dt:
            direction = "none"
            needs_sync = False
        elif not cloud_dt or (local_dt and local_dt > cloud_dt):
            direction = "upload"
            needs_sync = True
        elif not local_dt or cloud_dt > local_dt:
            direction = "download"
            needs_sync = True
        else:
            direction = "none"
            needs_sync = False

        return {
            "needs_sync": needs_sync,
            "direction": direction,
            "local_updated_at": local_updated_at,
            "cloud_updated_at": cloud_updated_at
        }

    except Exception as e:
        logger.error(f"[SyncStatus] Failed to check sync status for {workflow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/workflows/{workflow_id}/sync")
async def sync_workflow(workflow_id: str, user_id: str, data: dict = None):
    """Synchronize workflow resources between local and cloud

    Request body (optional):
        direction: "upload" | "download" | null (auto-detect based on timestamps)

    Returns:
        {
            "success": bool,
            "message": str,
            "synced_resources": list,
            "errors": list
        }
    """
    try:
        direction = data.get("direction") if data else None
        logger.info(f"[Sync] Sync request for workflow {workflow_id}, direction={direction}")

        if direction == "download":
            # Force download from cloud
            cloud_metadata = await cloud_client.get_workflow_metadata(workflow_id, user_id)
            if not cloud_metadata:
                raise HTTPException(status_code=404, detail="Workflow not found in cloud")

            home_dir = Path.home()
            ami_root = home_dir / ".ami"
            local_workflow_path = ami_root / "users" / user_id / "workflows" / workflow_id

            result = await download_from_cloud(workflow_id, user_id, cloud_metadata, local_workflow_path)

        elif direction == "upload":
            # Force upload to cloud
            home_dir = Path.home()
            ami_root = home_dir / ".ami"
            local_workflow_path = ami_root / "users" / user_id / "workflows" / workflow_id
            local_metadata_path = local_workflow_path / "metadata.json"

            if not local_metadata_path.exists():
                raise HTTPException(status_code=404, detail="Workflow not found locally")

            with open(local_metadata_path, 'r', encoding='utf-8') as f:
                local_metadata = json.load(f)

            result = await upload_to_cloud(workflow_id, user_id, local_metadata, local_workflow_path)

        else:
            # Auto-detect direction based on timestamps
            result = await sync_workflow_resources(workflow_id, user_id)

        # Transform result to match expected frontend format
        return {
            "success": result.get("synced", False) or result.get("direction") == "none",
            "message": result.get("message", ""),
            "synced_resources": [],  # Could be enhanced to list actual files
            "errors": result.get("errors", [])
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Sync] Failed to sync workflow {workflow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Workflow APIs
# ============================================================================

@app.post("/api/v1/workflows/generate")
async def generate_workflow_direct(
    data: dict,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """Generate Workflow directly from Recording or task description

    Proxies to Cloud Backend's /api/v1/workflows/generate endpoint.
    This bypasses MetaFlow and uses the new WorkflowBuilder architecture.

    If recording_id is provided, this endpoint will:
    1. Load operations from local storage
    2. Send operations directly to Cloud Backend (no need for recording to exist in Cloud)

    Request body:
        user_id: str - User ID (required)
        task_description: str - Task description (required)
        recording_id: str - Recording ID (optional, loads from local storage)
        user_query: str - User query (optional)
        enable_dialogue: bool - Keep session for follow-up dialogue (default: true)
        enable_semantic_validation: bool - Enable semantic validation (default: true)

    Returns:
        workflow_id: str - Generated Workflow ID
        workflow_yaml: str - Workflow YAML content
        session_id: str - Dialogue session ID (if enable_dialogue=true)
        validation_result: dict - Validation result (if enable_semantic_validation=true)
    """
    try:
        user_id = data.get("user_id")
        recording_id = data.get("recording_id")

        logger.info(f"Generating workflow for user: {user_id}")

        if not x_ami_api_key:
            raise HTTPException(status_code=401, detail="X-Ami-API-Key header required")

        # If recording_id is provided, load operations from local storage
        # and send them directly (Cloud Backend doesn't need the recording)
        if recording_id:
            logger.info(f"Loading recording from local storage: {recording_id}")
            recording_data = storage_manager.get_recording(user_id, recording_id)
            if not recording_data:
                raise HTTPException(status_code=404, detail=f"Recording not found locally: {recording_id}")

            operations = recording_data.get("operations", [])
            if not operations:
                raise HTTPException(status_code=400, detail=f"Recording {recording_id} has no operations")

            logger.info(f"Loaded {len(operations)} operations from local recording")

            # Build request with operations instead of recording_id
            cloud_request = {
                "user_id": user_id,
                "task_description": data.get("task_description"),
                "operations": operations,  # Send operations directly
                "user_query": data.get("user_query"),
                "enable_dialogue": data.get("enable_dialogue", True),
                "enable_semantic_validation": data.get("enable_semantic_validation", True),
                "source_recording_id": recording_id  # For traceability
            }
        else:
            # No recording_id, just forward the request as-is
            cloud_request = data

        # Set the API key for cloud client
        cloud_client.set_user_api_key(x_ami_api_key)

        # Call Cloud Backend's generate endpoint
        import httpx
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{cloud_client.api_url}/api/v1/workflows/generate",
                json=cloud_request,
                headers={"X-Ami-API-Key": x_ami_api_key}
            )
            response.raise_for_status()
            result = response.json()

        logger.info(f"Workflow generated: {result.get('workflow_id')}")
        return result

    except httpx.HTTPStatusError as e:
        logger.error(f"Cloud Backend error: {e.response.status_code} {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/workflows/generate-stream")
async def generate_workflow_stream(
    data: dict,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """Generate Workflow with streaming progress updates (SSE)

    Same as /api/v1/workflows/generate but returns SSE stream for Lovable-style progress display.

    If recording_id is provided, this endpoint will:
    1. Load operations from local storage
    2. Send operations directly to Cloud Backend

    Returns SSE stream with events:
        data: {"status": "analyzing", "progress": 10, "message": "Analyzing recording..."}
        data: {"status": "generating", "progress": 50, "message": "Generating workflow..."}
        data: {"status": "completed", "progress": 100, "workflow_id": "...", "workflow_yaml": "..."}
    """
    from starlette.responses import StreamingResponse
    import httpx

    user_id = data.get("user_id")
    recording_id = data.get("recording_id")

    logger.info(f"Generating workflow (stream) for user: {user_id}")

    if not x_ami_api_key:
        raise HTTPException(status_code=401, detail="X-Ami-API-Key header required")

    # If recording_id is provided, load operations from local storage and upload to cloud first
    if recording_id:
        logger.info(f"Loading recording from local storage: {recording_id}")
        recording_data = storage_manager.get_recording(user_id, recording_id)
        if not recording_data:
            raise HTTPException(status_code=404, detail=f"Recording not found locally: {recording_id}")

        operations = recording_data.get("operations", [])
        if not operations:
            raise HTTPException(status_code=400, detail=f"Recording {recording_id} has no operations")

        logger.info(f"Loaded {len(operations)} operations from local recording")

        # Get dom_snapshots for script pre-generation
        dom_snapshots = recording_data.get("dom_snapshots", {})
        logger.info(f"[Upload] DOM snapshots in recording_data: {len(dom_snapshots)} URLs")
        if dom_snapshots:
            logger.info(f"[Upload] DOM snapshot URLs: {list(dom_snapshots.keys())}")

        # Upload recording to cloud first (so cloud can access dom_snapshots)
        logger.info(f"[Upload] Uploading recording {recording_id} to cloud...")
        try:
            update_cloud_client_api_key(x_ami_api_key)
            await cloud_client.upload_recording(
                operations=operations,
                task_description=data.get("task_description", ""),
                user_query=data.get("user_query"),
                user_id=user_id,
                recording_id=recording_id,
                dom_snapshots=dom_snapshots
            )
            logger.info(f"[Upload] SUCCESS: Recording {recording_id} uploaded with {len(dom_snapshots)} DOM snapshots")
        except Exception as e:
            logger.error(f"[Upload] FAILED: {e}")
            import traceback
            logger.error(f"[Upload] Traceback: {traceback.format_exc()}")

        # Build request with operations instead of recording_id
        cloud_request = {
            "user_id": user_id,
            "task_description": data.get("task_description"),
            "operations": operations,
            "user_query": data.get("user_query"),
            "enable_dialogue": data.get("enable_dialogue", True),
            "enable_semantic_validation": data.get("enable_semantic_validation", True),
            "source_recording_id": recording_id
        }
    else:
        cloud_request = data

    async def stream_generator():
        try:
            logger.info(f"[Stream Debug] Starting stream to Cloud Backend: {cloud_client.api_url}/api/v1/workflows/generate-stream")
            # Use longer timeout and disable read timeout for streaming
            timeout_config = httpx.Timeout(300.0, read=None)
            async with httpx.AsyncClient(timeout=timeout_config) as client:
                logger.info(f"[Stream Debug] httpx client created, sending POST request...")
                async with client.stream(
                    "POST",
                    f"{cloud_client.api_url}/api/v1/workflows/generate-stream",
                    json=cloud_request,
                    headers={"X-Ami-API-Key": x_ami_api_key}
                ) as response:
                    logger.info(f"[Stream Debug] Got response status: {response.status_code}")
                    if response.status_code != 200:
                        error_text = await response.aread()
                        logger.error(f"Cloud Backend error: {response.status_code} {error_text}")
                        yield f"data: {json.dumps({'status': 'failed', 'message': error_text.decode()})}\n\n"
                        return

                    logger.info(f"[Stream Debug] Starting to iterate over response lines...")
                    line_count = 0
                    last_line = None
                    try:
                        async for line in response.aiter_lines():
                            line_count += 1
                            logger.info(f"[Stream Debug] Received line #{line_count}: {line[:100]}..." if len(line) > 100 else f"[Stream Debug] Received line #{line_count}: {line}")
                            if line:
                                last_line = line
                                # SSE events need double newline to separate
                                yield line + "\n\n"
                                await asyncio.sleep(0.01)  # Small delay to ensure buffer flush
                        logger.info(f"[Stream Debug] Stream ended normally, total lines received: {line_count}")
                    except httpx.RemoteProtocolError as e:
                        logger.warning(f"[Stream Debug] Protocol error after {line_count} lines: {e}")
                        # This is expected when server closes connection after completion
                        # Check if we received a completion event in the last line
                        if last_line and '"status"' in last_line:
                            try:
                                # Extract JSON from SSE format (remove "data: " prefix if present)
                                json_str = last_line.replace("data: ", "").strip()
                                last_event = json.loads(json_str)
                                if last_event.get("status") == "completed":
                                    logger.info(f"[Stream Debug] Last event was completion, stream ended successfully")
                                    # The completion event was received, but connection closed before we could yield it
                                    # This is expected behavior - the generator ending triggers connection close
                                    # The event should have already been yielded in the main loop
                                else:
                                    logger.warning(f"[Stream Debug] Last event status: {last_event.get('status')}")
                            except Exception as parse_error:
                                logger.warning(f"[Stream Debug] Could not parse last line as JSON: {parse_error}")
                        logger.info(f"[Stream Debug] Total lines received before disconnect: {line_count}")
        except Exception as e:
            logger.error(f"Stream error: {e}")
            import traceback
            logger.error(f"[Stream Debug] Traceback: {traceback.format_exc()}")
            yield f"data: {json.dumps({'status': 'failed', 'message': str(e)})}\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# ===== Workflow Session APIs (Proxy to Cloud Backend) =====

@app.post("/api/v1/workflow-sessions")
async def create_workflow_session(
    data: dict,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """Create a dialogue session for modifying an existing Workflow.

    Proxies to Cloud Backend.

    Body:
        {
            "user_id": "...",
            "workflow_id": "...",
            "workflow_yaml": "..."
        }
    """
    import httpx

    if not x_ami_api_key:
        raise HTTPException(status_code=401, detail="X-Ami-API-Key header required")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{cloud_client.api_url}/api/v1/workflow-sessions",
                json=data,
                headers={"X-Ami-API-Key": x_ami_api_key}
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        logger.error(f"Failed to create workflow session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/workflow-sessions/{session_id}/chat")
async def workflow_session_chat_stream(
    session_id: str,
    data: dict,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """Send a message to modify workflow via dialogue (SSE stream).

    Proxies to Cloud Backend with SSE streaming.

    Body:
        {"message": "把第3步改成抓取更多字段"}

    Returns SSE stream with events:
        data: {"type": "text", "content": "..."}
        data: {"type": "complete", "workflow_updated": true, "workflow_yaml": "..."}
    """
    from starlette.responses import StreamingResponse
    import httpx

    if not x_ami_api_key:
        raise HTTPException(status_code=401, detail="X-Ami-API-Key header required")

    async def stream_generator():
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream(
                    "POST",
                    f"{cloud_client.api_url}/api/v1/workflow-sessions/{session_id}/chat",
                    json=data,
                    headers={"X-Ami-API-Key": x_ami_api_key}
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        logger.error(f"Cloud Backend error: {response.status_code} {error_text}")
                        yield f"data: {json.dumps({'type': 'error', 'message': error_text.decode()})}\n\n"
                        return

                    async for line in response.aiter_lines():
                        if line:
                            yield line + "\n\n"
        except Exception as e:
            logger.error(f"Workflow session chat stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.delete("/api/v1/workflow-sessions/{session_id}")
async def close_workflow_session(
    session_id: str,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """Close a workflow modification session.

    Proxies to Cloud Backend.
    """
    import httpx

    if not x_ami_api_key:
        raise HTTPException(status_code=401, detail="X-Ami-API-Key header required")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{cloud_client.api_url}/api/v1/workflow-sessions/{session_id}",
                headers={"X-Ami-API-Key": x_ami_api_key}
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        logger.error(f"Failed to close workflow session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/workflows/{workflow_id}/execute", response_model=ExecuteWorkflowResponse)
async def execute_workflow(
    workflow_id: str,
    request: ExecuteWorkflowRequest,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """Execute a workflow asynchronously

    Headers:
        X-Ami-API-Key: User's Ami API key (required for LLM calls via API Proxy)
    """
    try:
        logger.info(f"Executing workflow: {workflow_id}")

        if not x_ami_api_key:
            logger.warning("No X-Ami-API-Key header provided for workflow execution")
        else:
            logger.info(f"Using user API key for workflow execution: {x_ami_api_key[:10]}...")

        result = await workflow_executor.execute_workflow_async(
            user_id=request.user_id,
            workflow_id=workflow_id,
            user_api_key=x_ami_api_key
        )
        logger.info(f"Workflow execution started: task_id={result['task_id']}")
        return result
    except Exception as e:
        logger.error(f"Failed to execute workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/executions/{task_id}", response_model=WorkflowStatusResponse)
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


@app.post("/api/v1/executions/{task_id}/stop")
async def stop_workflow_execution(task_id: str):
    """Stop a running workflow execution

    Args:
        task_id: Task ID to stop

    Returns:
        - success: Whether stop was successful
        - stopped_at_step: Step index where workflow was stopped
        - message: Human-readable status
    """
    try:
        result = await workflow_executor.stop_workflow(task_id)
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/executions/{task_id}/results")
async def get_execution_results(task_id: str):
    """Get execution results for a completed workflow

    Args:
        task_id: Task ID (unified execution identifier)

    Returns:
        - stats: Execution statistics (status, duration, totalRecords, timestamp)
        - results: Scraped data array
        - workflow_name: Human-readable workflow name
    """
    if not history_manager:
        raise HTTPException(status_code=503, detail="History manager not initialized")

    try:
        # Get execution metadata from history
        meta = history_manager.get_run_meta_by_id(task_id)
        if not meta:
            raise HTTPException(status_code=404, detail=f"Execution not found: {task_id}")

        # Calculate duration
        duration = "N/A"
        if meta.started_at and meta.finished_at:
            try:
                from datetime import datetime
                start = datetime.fromisoformat(meta.started_at.replace('Z', '+00:00'))
                end = datetime.fromisoformat(meta.finished_at.replace('Z', '+00:00'))
                duration_seconds = (end - start).total_seconds()
                if duration_seconds < 60:
                    duration = f"{int(duration_seconds)}s"
                else:
                    minutes = int(duration_seconds // 60)
                    seconds = int(duration_seconds % 60)
                    duration = f"{minutes}m {seconds}s"
            except Exception:
                pass

        # Build stats
        stats = {
            "status": "success" if meta.status == "completed" else meta.status,
            "duration": duration,
            "totalRecords": 0,  # Will be updated if we have data
            "timestamp": meta.finished_at or meta.started_at
        }

        # Try to get scraped data from execution result
        # The result is stored by StorageManager in the same execution directory
        results = []
        if meta.task_id:
            # Search for result data in the execution directory
            result = history_manager._find_execution_by_task_id(task_id)
            if result:
                user_id, workflow_id, exec_path = result
                result_file = exec_path / "result.json"
                if result_file.exists():
                    import json
                    with open(result_file, 'r', encoding='utf-8') as f:
                        result_data = json.load(f)
                        # Extract scraped data if available
                        if isinstance(result_data.get("result"), dict):
                            data = result_data["result"].get("data", [])
                            if isinstance(data, list):
                                results = data
                                stats["totalRecords"] = len(data)

        return {
            "stats": stats,
            "results": results,
            "workflow_name": meta.workflow_name
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get execution results: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/v1/executions/{task_id}")
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


# ============================================================================
# Workflow History API
# ============================================================================

@app.get("/api/v1/workflows/{workflow_id}/history", response_model=WorkflowHistoryListResponse)
async def list_workflow_history(
    workflow_id: str,
    user_id: str,
    limit: int = 100,
    status: Optional[str] = None,
):
    """List execution history for a specific workflow

    Args:
        workflow_id: Workflow identifier
        user_id: User identifier
        limit: Maximum number of runs to return (default 100)
        status: Filter by status (completed, failed, running)

    Returns:
        List of workflow run entries for this workflow
    """
    if not history_manager:
        raise HTTPException(status_code=503, detail="History manager not initialized")

    try:
        runs = history_manager.list_workflow_executions(
            user_id=user_id,
            workflow_id=workflow_id,
            limit=limit
        )

        # Apply status filter if provided
        if status:
            runs = [r for r in runs if r.status == status]

        return WorkflowHistoryListResponse(
            runs=[
                WorkflowHistoryEntry(
                    task_id=r.task_id,
                    workflow_id=r.workflow_id,
                    workflow_name=r.workflow_name,
                    started_at=r.started_at,
                    status=r.status,
                    error_summary=r.error_summary,
                )
                for r in runs
            ],
            total=len(runs),
        )
    except Exception as e:
        logger.error(f"Failed to list workflow history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/workflows/{workflow_id}/history/{task_id}", response_model=WorkflowRunDetailResponse)
async def get_workflow_run_detail(workflow_id: str, task_id: str, user_id: str):
    """Get execution logs and details for a specific workflow run

    Args:
        workflow_id: Workflow identifier
        task_id: The task identifier (unified execution identifier)
        user_id: User identifier

    Returns:
        Run metadata, logs, and workflow YAML
    """
    if not history_manager:
        raise HTTPException(status_code=503, detail="History manager not initialized")

    try:
        meta = history_manager.get_run_meta(user_id, workflow_id, task_id)
        if not meta:
            raise HTTPException(status_code=404, detail=f"Run not found: {task_id}")

        logs = history_manager.get_run_logs(user_id, workflow_id, task_id)
        workflow_yaml = history_manager.get_workflow_yaml(user_id, workflow_id)

        return WorkflowRunDetailResponse(
            meta=WorkflowRunDetail(
                task_id=meta.task_id,
                workflow_id=meta.workflow_id,
                workflow_name=meta.workflow_name,
                user_id=meta.user_id,
                device_id=meta.device_id,
                app_version=meta.app_version,
                started_at=meta.started_at,
                finished_at=meta.finished_at,
                status=meta.status,
                error_summary=meta.error_summary,
                steps_total=meta.steps_total,
                steps_completed=meta.steps_completed,
            ),
            logs=[
                WorkflowRunLog(
                    ts=log.ts,
                    step=log.step,
                    action=log.action,
                    target=log.target,
                    status=log.status,
                    duration_ms=log.duration_ms,
                    message=log.message,
                    metadata=log.metadata,
                )
                for log in logs
            ],
            workflow_yaml=workflow_yaml,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow run logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/workflows", response_model=ListWorkflowsResponse)
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


@app.get("/api/v1/workflows/{workflow_id}")
async def get_workflow_detail(workflow_id: str, user_id: str):
    """Get detailed workflow data for visualization

    Returns:
        - metadata: from metadata.json (workflow_id, workflow_name, source_recording_id, created_at, etc.)
        - steps/connections: from workflow.yaml
        - workflow_yaml: raw YAML content

    Auto-sync workflow resources before returning details
    """
    try:
        # Auto-sync workflow resources with Cloud Backend
        # This ensures user always sees the latest version
        try:
            sync_result = await sync_workflow_resources(workflow_id, user_id)
            if sync_result.get("synced"):
                logger.info(f"Workflow auto-synced: {sync_result.get('direction')} - {sync_result.get('message')}")
        except Exception as e:
            # Don't block page load if sync fails
            logger.warning(f"Auto-sync failed for workflow {workflow_id}: {e}")

        # Check if workflow exists locally
        if not storage_manager.workflow_exists(user_id, workflow_id):
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

        # Read metadata.json (system metadata)
        metadata = storage_manager.get_workflow_metadata(user_id, workflow_id) or {}

        # Read workflow YAML
        workflow_yaml = storage_manager.get_workflow(user_id, workflow_id)

        # Parse YAML to extract steps and connections
        import yaml
        workflow_data = yaml.safe_load(workflow_yaml)

        if not isinstance(workflow_data, dict):
            raise HTTPException(status_code=500, detail="Invalid workflow format")

        # Get name/description from YAML top-level fields (not metadata section)
        yaml_name = workflow_data.get('name', '')
        yaml_description = workflow_data.get('description', '')

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

        # Build response with clear data sources:
        # - metadata: from metadata.json
        # - name/description: from workflow.yaml top-level
        # - steps/connections: from workflow.yaml
        response_data = {
            # System metadata from metadata.json
            'workflow_id': metadata.get('workflow_id', workflow_id),
            'workflow_name': metadata.get('workflow_name', yaml_name or workflow_id),
            'source_recording_id': metadata.get('source_recording_id'),
            'created_at': metadata.get('created_at'),
            'updated_at': metadata.get('updated_at'),
            'resources': metadata.get('resources'),
            # YAML content
            'name': yaml_name or metadata.get('workflow_name', workflow_id),  # Display name
            'description': yaml_description,
            'steps': steps_list,
            'connections': connections,
            'workflow_yaml': workflow_yaml,
            # Full metadata object for frontend
            'metadata': metadata
        }

        logger.info(f"Loaded workflow detail: {workflow_id}, name={response_data['workflow_name']}")
        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/v1/workflows/{workflow_id}")
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


@app.delete("/api/v1/workflows/{workflow_id}")
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

        # Step 3: Delete workflow data (collections in storage.db and related caches)
        data_deleted_count = 0
        try:
            import aiosqlite

            storage_db_path = Path(config.get("data.databases.storage"))
            kv_db_path = Path(config.get("data.databases.kv"))

            if storage_db_path.exists():
                suffix = f"_{user_id}_{workflow_id}"

                async with aiosqlite.connect(str(storage_db_path)) as db:
                    # Find all tables belonging to this workflow
                    cursor = await db.execute("""
                        SELECT name FROM sqlite_master
                        WHERE type='table' AND name LIKE ?
                    """, (f"%{suffix}",))
                    tables = await cursor.fetchall()

                    # Drop each table
                    for (table_name,) in tables:
                        if table_name.endswith(suffix):
                            await db.execute(f"DROP TABLE IF EXISTS {table_name}")
                            data_deleted_count += 1
                            logger.info(f"  Dropped data table: {table_name}")

                    await db.commit()

                # Clean up related caches from kv.db
                if kv_db_path.exists() and data_deleted_count > 0:
                    async with aiosqlite.connect(str(kv_db_path)) as db:
                        # Delete all cache entries for this workflow
                        cursor = await db.execute(
                            "DELETE FROM kv_storage WHERE key LIKE ?",
                            (f"%_{user_id}_{workflow_id}%",)
                        )
                        cache_deleted = cursor.rowcount
                        await db.commit()
                        if cache_deleted > 0:
                            logger.info(f"  Deleted {cache_deleted} cache entries for workflow")

            if data_deleted_count > 0:
                logger.info(f"✓ Deleted {data_deleted_count} data collections for workflow: {workflow_id}")
        except Exception as e:
            logger.warning(f"⚠ Failed to delete workflow data: {e}")

        # Step 4: Determine success
        if not cloud_deleted and not local_deleted:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

        logger.info(f"✅ Workflow deletion complete: {workflow_id} (Cloud: {cloud_deleted}, Local: {local_deleted}, Data collections: {data_deleted_count})")
        return {
            "status": "success",
            "message": "Workflow deleted",
            "deleted_from_cloud": cloud_deleted,
            "deleted_from_local": local_deleted,
            "deleted_data_collections": data_deleted_count
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Workflow Data APIs (per-workflow data isolation)
# Table naming: {collection}_{user_id}_{workflow_id}
# ============================================================================

@app.get("/api/v1/workflows/{workflow_id}/data/collections")
async def list_workflow_collections(workflow_id: str, user_id: str):
    """List all data collections for a specific workflow

    Table naming convention: {collection}_{user_id}_{workflow_id}

    Returns collections from storage.db with:
    - Collection name
    - Record count
    - Size estimate
    - Field names
    """
    try:
        logger.info(f"Listing collections for workflow: {workflow_id}, user: {user_id}")

        import aiosqlite

        collections = []
        storage_db_path = Path(config.get("data.databases.storage"))

        if not storage_db_path.exists():
            logger.info("Storage database does not exist yet")
            return {"collections": collections}

        # Table name pattern: {collection}_{user_id}_{workflow_id}
        suffix = f"_{user_id}_{workflow_id}"

        async with aiosqlite.connect(str(storage_db_path)) as db:
            # Get all tables for this user + workflow
            cursor = await db.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name LIKE ?
                ORDER BY name
            """, (f"%{suffix}",))
            tables = await cursor.fetchall()

            for (table_name,) in tables:
                # Parse collection name from table name
                # Format: {collection}_{user_id}_{workflow_id}
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
                try:
                    cursor = await db.execute(f"SELECT COUNT(*) FROM dbstat WHERE name=?", (table_name,))
                    page_count = (await cursor.fetchone())[0]
                    size_bytes = page_count * 4096  # SQLite default page size
                except Exception:
                    # dbstat may not be available in all SQLite builds
                    size_bytes = 0

                collections.append({
                    "collection_name": collection_name,
                    "table_name": table_name,
                    "records_count": row_count,
                    "size_bytes": size_bytes,
                    "fields": field_names
                })

        logger.info(f"Found {len(collections)} collections for workflow {workflow_id}")
        return {"collections": collections}

    except Exception as e:
        logger.error(f"Failed to list collections: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/workflows/{workflow_id}/data/collections/{collection_name}")
async def get_workflow_collection_detail(workflow_id: str, collection_name: str, user_id: str, limit: int = 100):
    """Get collection detail with data preview for a specific workflow

    Args:
        workflow_id: Workflow ID
        collection_name: Name of the collection
        user_id: User ID
        limit: Number of records to return (default: 100)

    Returns:
        Collection metadata and data
    """
    try:
        logger.info(f"Getting collection detail: {collection_name} for workflow {workflow_id} (limit: {limit})")

        import aiosqlite

        storage_db_path = Path(config.get("data.databases.storage"))

        if not storage_db_path.exists():
            raise HTTPException(status_code=404, detail="Storage database not found")

        table_name = f"{collection_name}_{user_id}_{workflow_id}"

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
            try:
                cursor = await db.execute(f"SELECT COUNT(*) FROM dbstat WHERE name=?", (table_name,))
                page_count = (await cursor.fetchone())[0]
                size_bytes = page_count * 4096
            except Exception:
                size_bytes = 0

            # Get data
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM {table_name} ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            rows = await cursor.fetchall()

            # Convert to list of dicts
            data = [dict(row) for row in rows]

            logger.info(f"Collection detail loaded: {total_count} records, returning {len(data)}")

            return {
                "collection_name": collection_name,
                "table_name": table_name,
                "total_records": total_count,
                "size_bytes": size_bytes,
                "fields": data_fields,
                "all_fields": all_fields,
                "data": data,
                "returned_count": len(data)
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get collection detail: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/workflows/{workflow_id}/data/collections/{collection_name}")
async def delete_workflow_collection(workflow_id: str, collection_name: str, user_id: str):
    """Delete a collection and its related caches for a specific workflow

    Args:
        workflow_id: Workflow ID
        collection_name: Name of the collection to delete
        user_id: User ID

    Returns:
        Success message
    """
    try:
        logger.info(f"Deleting collection: {collection_name} for workflow {workflow_id}")

        import aiosqlite

        storage_db_path = Path(config.get("data.databases.storage"))
        kv_db_path = Path(config.get("data.databases.kv"))

        if not storage_db_path.exists():
            raise HTTPException(status_code=404, detail="Storage database not found")

        table_name = f"{collection_name}_{user_id}_{workflow_id}"

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

            logger.info(f"Dropped table: {table_name}")

        # Step 2: Delete related caches from kv.db
        # Cache key patterns for StorageAgent:
        # - storage_insert_{collection}_{user_id}_{workflow_id}
        # - storage_query_{collection}_{user_id}_{workflow_id}_{config_hash}
        # - storage_export_{collection}_{user_id}_{workflow_id}_{config_hash}
        cache_deleted_count = 0

        if kv_db_path.exists():
            async with aiosqlite.connect(str(kv_db_path)) as db:
                # Delete all cache entries related to this collection
                patterns = [
                    f"storage_insert_{collection_name}_{user_id}_{workflow_id}%",
                    f"storage_query_{collection_name}_{user_id}_{workflow_id}%",
                    f"storage_export_{collection_name}_{user_id}_{workflow_id}%",
                ]

                for pattern in patterns:
                    cursor = await db.execute(
                        "DELETE FROM kv_storage WHERE key LIKE ?",
                        (pattern,)
                    )
                    deleted = cursor.rowcount
                    if deleted > 0:
                        cache_deleted_count += deleted
                        logger.info(f"Deleted {deleted} cache entries matching: {pattern}")

                await db.commit()

        logger.info(f"Collection deleted: {collection_name} (table + {cache_deleted_count} cache entries)")

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


@app.get("/api/v1/workflows/{workflow_id}/data/collections/{collection_name}/export")
async def export_workflow_collection(workflow_id: str, collection_name: str, user_id: str, limit: Optional[int] = None):
    """Export collection data as CSV for a specific workflow

    Args:
        workflow_id: Workflow ID
        collection_name: Name of the collection
        user_id: User ID
        limit: Optional limit on number of rows to export

    Returns:
        CSV file as downloadable attachment
    """
    try:
        logger.info(f"Exporting collection: {collection_name} for workflow {workflow_id} (limit: {limit})")

        import aiosqlite
        import csv
        import io

        storage_db_path = Path(config.get("data.databases.storage"))

        if not storage_db_path.exists():
            raise HTTPException(status_code=404, detail="Storage database not found")

        table_name = f"{collection_name}_{user_id}_{workflow_id}"

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
                    "Content-Disposition": f"attachment; filename={collection_name}_{workflow_id}.csv"
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

# ============================================================================
# Memory API Endpoints
# ============================================================================

class AddToMemoryRequest(BaseModel):
    """Request model for adding to memory"""
    user_id: str
    recording_id: Optional[str] = None
    operations: Optional[List[Dict[str, Any]]] = None
    session_id: Optional[str] = None
    generate_embeddings: bool = True


class QueryMemoryRequest(BaseModel):
    """Request model for querying memory

    The system automatically analyzes the query and returns the most relevant
    operation paths with States, Actions, and IntentSequences.
    """
    user_id: str
    query: str
    top_k: int = 3
    min_score: float = 0.5
    domain: Optional[str] = None


@app.post("/api/v1/memory/add")
async def add_to_memory(
    request: AddToMemoryRequest,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """
    Add Recording to User's Workflow Memory

    This endpoint processes a recording and adds its States, Actions, and IntentSequences
    to the user's workflow memory for semantic search.

    Headers:
        X-Ami-API-Key: User's API key (required for embedding generation)

    Returns:
        {
            "success": true,
            "states_added": 3,
            "states_merged": 1,
            "page_instances_added": 4,
            "intent_sequences_added": 5,
            "actions_added": 2,
            "processing_time_ms": 150
        }
    """
    try:
        logger.info(f"Adding to memory for user: {request.user_id}")

        # Set user API key on cloud client
        if x_ami_api_key:
            cloud_client.set_user_api_key(x_ami_api_key)

        # Forward to Cloud Backend
        result = await cloud_client.add_to_memory(
            user_id=request.user_id,
            recording_id=request.recording_id,
            operations=request.operations,
            session_id=request.session_id,
            generate_embeddings=request.generate_embeddings
        )

        logger.info(f"Memory add result: {result.get('states_added')} added, "
                   f"{result.get('states_merged')} merged")
        return result

    except Exception as e:
        logger.error(f"Failed to add to memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/memory/query")
async def query_memory(
    request: QueryMemoryRequest,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """
    Query User's Workflow Memory using Natural Language

    This endpoint performs intelligent semantic search on the user's workflow memory.
    The system automatically analyzes the query and returns the most relevant
    operation paths with States, Actions, and IntentSequences.

    Headers:
        X-Ami-API-Key: User's API key (required)

    Returns:
        {
            "success": true,
            "query": "通过榜单查看产品团队信息",
            "paths": [
                {
                    "score": 0.85,
                    "description": "从榜单页到团队页的操作路径",
                    "steps": [
                        {"state": {...}, "action": {...}, "intent_sequence": {...}},
                        ...
                    ]
                }
            ],
            "total_paths": 1
        }
    """
    if not x_ami_api_key:
        raise HTTPException(status_code=400, detail="X-Ami-API-Key header is required")

    try:
        logger.info(f"Querying memory for user: {request.user_id}, query: {request.query[:50]}...")

        # Set user API key on cloud client
        cloud_client.set_user_api_key(x_ami_api_key)

        # Forward to Cloud Backend
        result = await cloud_client.query_memory(
            user_id=request.user_id,
            query=request.query,
            top_k=request.top_k,
            min_score=request.min_score,
            domain=request.domain
        )

        logger.info(f"Memory query result: {result.get('total_paths')} paths")
        return result

    except Exception as e:
        logger.error(f"Failed to query memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/memory/stats")
async def get_memory_stats(
    user_id: str,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """
    Get User's Workflow Memory Statistics

    Query Parameters:
        user_id: User identifier

    Returns:
        {
            "success": true,
            "user_id": "user123",
            "stats": {
                "total_states": 10,
                "total_intent_sequences": 25,
                "total_page_instances": 15,
                "total_actions": 8,
                "domains": ["producthunt.com"],
                "url_index_size": 12
            }
        }
    """
    try:
        logger.info(f"Getting memory stats for user: {user_id}")

        # Set user API key on cloud client
        if x_ami_api_key:
            cloud_client.set_user_api_key(x_ami_api_key)

        # Forward to Cloud Backend
        result = await cloud_client.get_memory_stats(user_id=user_id)

        logger.info(f"Memory stats: {result.get('stats', {}).get('total_states', 0)} states")
        return result

    except Exception as e:
        logger.error(f"Failed to get memory stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/memory")
async def clear_memory(
    user_id: str,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """
    Clear User's Workflow Memory

    Query Parameters:
        user_id: User identifier

    Returns:
        {
            "success": true,
            "deleted_states": 10,
            "deleted_actions": 8
        }
    """
    try:
        logger.info(f"Clearing memory for user: {user_id}")

        # Set user API key on cloud client
        if x_ami_api_key:
            cloud_client.set_user_api_key(x_ami_api_key)

        # Forward to Cloud Backend
        result = await cloud_client.clear_memory(user_id=user_id)

        logger.info(f"Memory cleared: {result.get('deleted_states')} states")
        return result

    except Exception as e:
        logger.error(f"Failed to clear memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Intent Builder API Endpoints
# ============================================================================

class StartIntentBuilderRequest(BaseModel):
    """Request model for starting Intent Builder session"""
    user_id: str
    user_query: str
    task_description: Optional[str] = None
    session_id: Optional[str] = None  # For resuming from recording
    workflow_id: Optional[str] = None  # Workflow ID being modified
    current_workflow_yaml: Optional[str] = None  # Current Workflow content for context


class IntentBuilderChatRequest(BaseModel):
    """Request model for Intent Builder chat"""
    message: str


@app.post("/api/v1/intent-builder/sessions")
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
            workflow_id=request.workflow_id,
            current_workflow_yaml=request.current_workflow_yaml
        )

        logger.info(f"Intent Builder session started: {result['session_id']}")
        return result

    except Exception as e:
        logger.error(f"Failed to start Intent Builder session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/intent-builder/sessions/{session_id}/stream")
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


@app.post("/api/v1/intent-builder/sessions/{session_id}/chat")
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


@app.get("/api/v1/intent-builder/sessions/{session_id}/state")
async def get_intent_builder_state(session_id: str):
    """
    Get current state of Intent Builder session
    """
    try:
        return await cloud_client.get_intent_builder_state(session_id)
    except Exception as e:
        logger.error(f"Failed to get Intent Builder state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/intent-builder/sessions/{session_id}")
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
# Single Instance Management
# ============================================================================

def get_ami_dir() -> Path:
    """Get the .ami directory path."""
    return Path.home() / ".ami"


def get_port_file_path() -> Path:
    """Get the path to the daemon port file."""
    return get_ami_dir() / "daemon.port"


def check_existing_daemon(host: str, port: int, timeout: float = 2.0) -> tuple[bool, bool]:
    """Check if a daemon is already running on the given port.

    Args:
        host: Host to check
        port: Port to check
        timeout: Timeout for health check request

    Returns:
        Tuple of (is_our_daemon, port_is_occupied):
        - (True, True): Our daemon is running and healthy
        - (False, True): Port is occupied by another service
        - (False, False): Port is free (connection refused)
    """
    import urllib.request
    import urllib.error

    url = f"http://{host}:{port}/health"
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                # Check magic number to verify it's our daemon
                data = json.loads(response.read().decode('utf-8'))
                magic = data.get("magic", "")
                if magic.startswith("ami-daemon-"):
                    logger.info(f"Found our daemon at {host}:{port} (magic: {magic})")
                    return (True, True)
                else:
                    logger.warning(f"Port {port} is occupied by unknown service (no valid magic)")
                    return (False, True)
    except urllib.error.HTTPError as e:
        # Got HTTP response but not 200 - port is occupied by another service
        logger.warning(f"Port {port} is occupied by another service: HTTP {e.code}")
        return (False, True)
    except (urllib.error.URLError, OSError) as e:
        # Connection refused or timeout - port is free
        logger.info(f"Port {port} is free: {e}")
        return (False, False)

    return (False, False)


def read_port_file() -> Optional[int]:
    """Read the daemon port from file.

    Returns:
        Port number if file exists and valid, None otherwise
    """
    port_file = get_port_file_path()
    try:
        if port_file.exists():
            content = port_file.read_text().strip()
            return int(content)
    except (ValueError, OSError) as e:
        logger.warning(f"Failed to read port file: {e}")
    return None


def write_port_file(port: int) -> None:
    """Write the daemon port to file for frontend discovery.

    Args:
        port: The port number daemon is running on
    """
    port_file = get_port_file_path()
    port_file.parent.mkdir(parents=True, exist_ok=True)
    port_file.write_text(str(port))
    logger.info(f"Port file written: {port_file} -> {port}")


def cleanup_port_file() -> None:
    """Remove the port file on shutdown."""
    port_file = get_port_file_path()
    try:
        if port_file.exists():
            port_file.unlink()
            logger.info(f"Port file removed: {port_file}")
    except Exception as e:
        logger.warning(f"Failed to remove port file: {e}")


def find_available_port(host: str, start_port: int, max_attempts: int = 10) -> int:
    """Find an available port starting from start_port.

    Uses HTTP health check first (to detect any HTTP service), then falls back to socket test.

    Args:
        host: Host to bind to
        start_port: Port to start searching from
        max_attempts: Maximum number of ports to try

    Returns:
        Available port number

    Raises:
        RuntimeError: If no available port found
    """
    import socket

    for port in range(start_port, start_port + max_attempts):
        # First, check if any service is responding on this port
        is_our_daemon, port_occupied = check_existing_daemon(host, port)

        if is_our_daemon:
            # Our daemon is already running on this port - should not happen here,
            # but skip this port just in case
            logger.warning(f"Port {port} has our daemon running, skipping")
            continue

        if port_occupied:
            # Port is occupied by another service
            logger.warning(f"Port {port} is occupied by another service, skipping")
            continue

        # Port seems free from HTTP perspective, now verify with socket bind
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                # Do NOT use SO_REUSEADDR - we want to detect if port is truly free
                s.bind((host, port))
                logger.info(f"Port {port} is available")
                return port
        except OSError as e:
            logger.warning(f"Port {port} socket bind failed: {e}")
            continue

    raise RuntimeError(f"No available port found in range {start_port}-{start_port + max_attempts - 1}")


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Start HTTP server with single-instance support"""
    start_port = config.get("daemon.port", 8765)
    host = config.get("daemon.host", "127.0.0.1")

    # Check if another daemon is already running (from port file)
    existing_port = read_port_file()
    if existing_port is not None:
        is_our_daemon, port_occupied = check_existing_daemon(host, existing_port)

        if is_our_daemon:
            # Our daemon is already running - exit gracefully
            logger.info("=" * 60)
            logger.info(f"Another daemon is already running on port {existing_port}")
            logger.info("This instance will exit. Frontend should connect to existing daemon.")
            logger.info("=" * 60)
            return  # Exit without error - this is expected behavior

        # Port file exists but it's not our daemon - clean up stale file
        logger.info(f"Stale port file found (port {existing_port}), cleaning up...")
        cleanup_port_file()

    # Find an available port (in case default port is occupied by other apps)
    try:
        port = find_available_port(host, start_port)
    except RuntimeError as e:
        logger.error(f"Failed to find available port: {e}")
        return

    # Write port to file for frontend discovery
    write_port_file(port)

    # DO NOT register signal handlers - uvicorn handles them automatically
    # and will call our lifespan shutdown context manager

    logger.info("=" * 60)
    logger.info(f"Starting App Backend daemon on {host}:{port}")
    logger.info("Process will respond to SIGTERM/SIGINT for graceful shutdown")
    logger.info("=" * 60)

    try:
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info"
        )
    finally:
        # Clean up port file on exit
        cleanup_port_file()


if __name__ == "__main__":
    # Fix for PyInstaller on Windows: ensure stdout/stderr are not None
    # This prevents AttributeError in uvicorn's logging setup
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w', encoding='utf-8')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w', encoding='utf-8')

    # Force UTF-8 encoding for Windows console output
    # This prevents UnicodeEncodeError when printing emoji or non-ASCII characters
    if sys.platform == 'win32':
        if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    main()
