#!/usr/bin/env python3
"""
App Backend Daemon - HTTP API Version
Provides REST API endpoints for desktop app communication

Usage:
    python daemon.py [--debug]

Options:
    --debug    Enable debug mode for browser operations and other diagnostics
"""
import sys
import os
import argparse
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

# Parse command line arguments early (before imports that might use AMI_DEBUG)
def parse_args():
    parser = argparse.ArgumentParser(description="Ami Daemon - Backend service for Ami desktop app")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode for browser operations")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default: 8765)")
    return parser.parse_args()

# Parse args and set AMI_DEBUG environment variable if --debug is specified
_args = parse_args()
if _args.debug:
    os.environ["AMI_DEBUG"] = "1"
    print("[DEBUG MODE ENABLED] Browser operations will log detailed information")

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
from src.clients.desktop_app.ami_daemon.services.recording_service import RecordingService
from src.clients.desktop_app.ami_daemon.services.replay import ReplayService
from src.clients.desktop_app.ami_daemon.services.cloud_client import CloudClient
from src.clients.desktop_app.ami_daemon.routers.quick_task import router as quick_task_router
from src.clients.desktop_app.ami_daemon.routers.integrations import router as integrations_router
from src.clients.desktop_app.ami_daemon.routers.settings import router as settings_router
from src.clients.desktop_app.ami_daemon.routers.session import router as session_router
# Note: Memory API is proxied to Cloud Backend via cloud_client
# Local memory service is disabled for now

# Load configuration first (needed for logging setup)
config = get_config()

# Set CAMEL_WORKDIR from config to prevent context files from being written in src-tauri/
# This avoids Tauri dev mode triggering rebuild when agent writes files
_camel_workdir = config.get("camel.workdir")
if _camel_workdir:
    Path(_camel_workdir).mkdir(parents=True, exist_ok=True)
    os.environ["CAMEL_WORKDIR"] = _camel_workdir

# Configure logging with rotating file handlers from config
# - app.log: Main system log (rotates based on config)
# - error.log: Error-only log (WARNING and above)
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
recording_service: Optional[RecordingService] = None
replay_service: Optional[ReplayService] = None
cloud_client: Optional[CloudClient] = None
# Memory API is proxied to Cloud Backend via cloud_client (local memory disabled)

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
    global browser_manager, workflow_executor, history_manager, cdp_recorder, recording_service, replay_service, cloud_client, version_check_result

    # ========== STARTUP ==========
    logger.info("=" * 60)
    logger.info(f"Starting Ami App Backend v{APP_VERSION}...")
    logger.info("=" * 60)

    try:
        # Initialize cloud client (needed for version check and Memory API proxy)
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

        # Initialize HybridBrowserSession with daemon lifecycle (V3)
        from src.clients.desktop_app.ami_daemon.base_agent.tools.eigent_browser.browser_session import HybridBrowserSession

        auto_start = config.get("browser.auto_start", False)
        if auto_start:
            try:
                await HybridBrowserSession.start_daemon_session(config=config)
                logger.info("✓ Browser session started (HybridBrowserSession V3)")
            except Exception as e:
                logger.warning(f"⚠️ Browser auto-start failed: {e}")
                logger.info("  Browser will start on first task")
        else:
            logger.info("✓ Browser auto-start disabled (will start on first task)")

        # Initialize legacy browser manager (kept for backward compatibility)
        browser_manager = BrowserManager(config_service=config)
        logger.info("✓ Legacy browser manager initialized")

        # Initialize Recording service (using HybridBrowserSession)
        recording_service = RecordingService(storage_manager)
        logger.info("✓ Recording service initialized (HybridBrowserSession)")

        # Initialize Replay service
        replay_service = ReplayService(storage_manager)
        logger.info("✓ Replay service initialized")

        # Inject cloud_client into quick_task router for memory queries
        from src.clients.desktop_app.ami_daemon.routers.quick_task import set_cloud_client
        set_cloud_client(cloud_client)
        logger.info("✓ Quick Task service configured with CloudClient for memory queries")

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

# Include routers
app.include_router(quick_task_router)
app.include_router(integrations_router)
app.include_router(settings_router)
app.include_router(session_router)


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


class ReplayRecordingRequest(BaseModel):
    """Request model for replaying a recording"""
    user_id: str
    wait_between_operations: float = 0.5
    stop_on_error: bool = False
    start_from_index: int = 0
    end_at_index: Optional[int] = None


class ReplayRecordingResponse(BaseModel):
    """Response model for replay execution"""
    replay_id: str
    status: str
    recording_session_id: Optional[str] = None
    execution_summary: Optional[Dict[str, Any]] = None
    timing: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ReplayPreviewResponse(BaseModel):
    """Response model for recording preview before replay"""
    session_id: str
    created_at: Optional[str] = None
    operations_count: int
    operation_summary: Dict[str, int]
    task_metadata: Dict[str, Any]
    operations: List[Dict[str, Any]]


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

@app.get("/api/v1/health")
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
            "device_id": "unknown",
            "app_version": APP_VERSION,
            "timestamp": datetime.now().isoformat(),
            "system_logs": system_logs,
            "recent_executions": [],
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
    """Get dashboard statistics for user"""
    try:
        logger.info(f"Getting dashboard for user: {user_id}")

        # Get all recordings
        recordings = storage_manager.list_recordings(user_id)
        total_recordings = len(recordings)

        dashboard_data = {
            "has_workflows": False,
            "total_workflows": 0,
            "total_recordings": total_recordings,
            "recent_workflows": []
        }

        logger.info(f"Dashboard data: {total_recordings} recordings")
        return dashboard_data

    except Exception as e:
        logger.error(f"Failed to get dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Recording APIs
# ============================================================================

@app.post("/api/v1/recordings/start", response_model=StartRecordingResponse)
async def start_recording(request: StartRecordingRequest):
    """Start recording session using HybridBrowserSession

    This uses the new RecordingService with better anti-detection capabilities.
    The browser will be started automatically if not running.
    """
    try:
        logger.info(f"Starting recording: url={request.url}, title={request.title}")

        # Prepare metadata
        metadata = request.task_metadata or {}
        metadata.update({
            "title": request.title,
            "description": request.description
        })

        # Start recording using new RecordingService
        # (RecordingService handles browser startup internally)
        result = await recording_service.start_recording(
            url=request.url,
            user_id=request.user_id,
            metadata=metadata,
            headless=False,
        )
        logger.info(f"Recording started: session_id={result['session_id']}, user_id={request.user_id}")
        return result

    except Exception as e:
        logger.error(f"Failed to start recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/recordings/stop", response_model=StopRecordingResponse)
async def stop_recording():
    """Stop recording and save

    This stops the recording and saves operations to local storage.
    The browser remains open for potential subsequent recordings.
    """
    try:
        logger.info("Stopping recording...")

        # Stop recording using new RecordingService
        result = await recording_service.stop_recording()
        logger.info(f"Recording stopped: {result['operations_count']} operations")

        # Close browser after recording
        await recording_service.close_browser()
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
        if not recording_service or not recording_service.is_recording():
            return CurrentOperationsResponse(
                is_recording=False,
                session_id=None,
                operations_count=0,
                operations=[]
            )

        return CurrentOperationsResponse(
            is_recording=True,
            session_id=recording_service.current_session_id,
            operations_count=recording_service.get_operations_count(),
            operations=recording_service.get_operations()
        )

    except Exception as e:
        logger.error(f"Failed to get current operations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/recordings/{session_id}/replay/preview", response_model=ReplayPreviewResponse)
async def get_replay_preview(session_id: str, user_id: str):
    """Get recording preview before replay

    Shows recording details and operation summary to help user decide
    whether to replay and which range to replay.
    """
    try:
        logger.info(f"Getting replay preview for session: {session_id}")
        preview = replay_service.get_recording_preview(session_id, user_id)
        return ReplayPreviewResponse(**preview)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Recording not found")
    except Exception as e:
        logger.error(f"Failed to get replay preview: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/recordings/{session_id}/replay", response_model=ReplayRecordingResponse)
async def replay_recording_endpoint(session_id: str, request: ReplayRecordingRequest):
    """Replay a recorded session

    Executes operations from a recording step-by-step using the recorded
    sequence. Opens a new browser and performs each operation exactly as
    it was recorded (without intent extraction or optimization).
    """
    try:
        logger.info(f"Starting replay for session: {session_id}")
        logger.info(f"  User: {request.user_id}")
        logger.info(f"  Options: wait={request.wait_between_operations}s, stop_on_error={request.stop_on_error}")

        # Create a new browser session for replay
        from src.clients.desktop_app.ami_daemon.base_agent.tools.eigent_browser import HybridBrowserSession

        browser_session = HybridBrowserSession(
            session_id=f"replay_{session_id}",
            headless=False,  # Show browser window during replay
            user_data_dir=None,  # Use temporary profile (no persistent data)
            stealth=True  # Enable stealth mode to avoid detection
        )

        try:
            # Ensure browser is started
            await browser_session.ensure_browser()
            logger.info("Browser session started for replay")

            # Execute replay
            report = await replay_service.replay_recording(
                session_id=session_id,
                user_id=request.user_id,
                browser_session=browser_session,
                wait_between_operations=request.wait_between_operations,
                stop_on_error=request.stop_on_error,
                start_from_index=request.start_from_index,
                end_at_index=request.end_at_index
            )

            # Log completion status
            if report.get('status') == 'completed' and 'execution_summary' in report:
                logger.info(f"Replay completed: {report['execution_summary']['success_rate']*100:.1f}% success")
            elif report.get('status') == 'failed':
                logger.error(f"Replay failed: {report.get('error', 'Unknown error')}")

            return ReplayRecordingResponse(**report)

        finally:
            # Keep browser open for user to inspect results
            # User can manually close it or it will be cleaned up on exit
            logger.info("Replay finished, browser remains open for inspection")

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Recording not found")
    except Exception as e:
        logger.error(f"Failed to replay recording: {e}", exc_info=True)
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

        if not x_ami_api_key:
            raise HTTPException(status_code=401, detail="X-Ami-API-Key header required")

        # 1. Load recording
        recording_data = storage_manager.get_recording(request.user_id, session_id)
        if not recording_data:
            raise HTTPException(status_code=404, detail="Recording not found")

        operations = recording_data.get("operations", [])
        logger.info(f"Loaded {len(operations)} operations from recording")

        # 2. Analyze locally using LLM
        from src.clients.desktop_app.ami_daemon.services.recording_analyzer import analyze_recording as analyze_ops
        analysis_result = await analyze_ops(
            operations=operations,
            api_key=x_ami_api_key,
        )

        logger.info(f"Analysis complete:")
        logger.info(f"  Name: {analysis_result.get('name', 'NOT_GENERATED')}")
        logger.info(f"  Task Description: {analysis_result['task_description'][:100]}...")
        logger.info(f"  User Query: {analysis_result['user_query'][:100] if analysis_result['user_query'] else 'N/A'}...")
        logger.info(f"  Patterns: {analysis_result['patterns']}")

        return AnalyzeRecordingResponse(
            name=analysis_result.get("name", "Unnamed Task"),
            task_description=analysis_result["task_description"],
            user_query=analysis_result["user_query"],
            detected_patterns=analysis_result["patterns"]
        )

    except HTTPException:
        raise
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
# Intent Builder Agent APIs (SSE Streaming Proxy)
# ============================================================================

# ============================================================================
# Memory API Endpoints (Local Personal Memory)
# ============================================================================


class AddToMemoryRequest(BaseModel):
    """Request model for adding to memory."""
    user_id: Optional[str] = None  # User ID for private memory database isolation
    recording_id: Optional[str] = None  # Load operations from existing recording
    operations: Optional[List[Dict[str, Any]]] = None  # Direct operations array
    session_id: Optional[str] = None
    generate_embeddings: bool = True


class QueryMemoryRequest(BaseModel):
    """Request model for querying memory."""
    target: Optional[str] = None
    query: Optional[str] = None  # Alias for target (backward compatibility)
    current_state: Optional[str] = None
    start_state: Optional[str] = None
    end_state: Optional[str] = None
    as_type: Optional[str] = None
    top_k: int = 10


@app.post("/api/v1/memory/add")
async def add_to_memory(
    request: AddToMemoryRequest,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key"),
):
    """
    Add Recording to Personal Memory (Proxy to Cloud Backend)

    Processes operations and adds States, Actions, and IntentSequences
    to the workflow memory graph via Cloud Backend.

    Headers:
        X-Ami-API-Key: API key for LLM (required for description generation)

    Body:
        Either recording_id OR operations must be provided:
        - recording_id: Load operations from existing recording
        - operations: Direct operations array

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
        logger.info(
            f"[memory/add] Received request: recording_id={request.recording_id}, "
            f"operations={len(request.operations) if request.operations else 0}, "
            f"session_id={request.session_id}"
        )
        logger.info(
            f"[memory/add] Incoming X-Ami-API-Key prefix: "
            f"{x_ami_api_key[:8] + '...' if x_ami_api_key else 'None'}"
        )

        if not cloud_client:
            logger.error("[memory/add] Cloud client not initialized")
            return {"success": False, "error": "Cloud client not initialized"}

        # Get operations - either from recording_id or directly
        operations = request.operations
        session_id = request.session_id

        if request.recording_id and not operations:
            # Load operations from local recording
            recording_data = storage_manager.get_recording(request.user_id, request.recording_id)
            if not recording_data:
                logger.warning(f"[memory/add] Recording not found: {request.recording_id}")
                return {
                    "success": False,
                    "error": f"Recording not found: {request.recording_id}",
                }
            operations = recording_data.get("operations", [])
            if not session_id:
                session_id = recording_data.get("session_id") or request.recording_id
            logger.info(f"[memory/add] Loaded {len(operations)} operations from recording {request.recording_id}")

        if not operations:
            logger.warning("[memory/add] No operations provided")
            return {
                "success": False,
                "error": "No operations provided (either recording_id or operations required)",
            }

        # Set API key for cloud client
        if x_ami_api_key:
            cloud_client.set_user_api_key(x_ami_api_key)

        logger.info(f"[memory/add] Proxying {len(operations)} operations to Cloud Backend...")

        result = await cloud_client.add_to_memory(
            user_id=request.user_id,
            operations=operations,
            session_id=session_id,
        )

        logger.info(f"[memory/add] Result: states_added={result.get('states_added')}, "
                   f"states_merged={result.get('states_merged')}, "
                   f"intent_sequences={result.get('intent_sequences_added')}")
        return result

    except Exception as e:
        logger.error(f"[memory/add] Failed: {e}")
        import traceback
        logger.error(f"[memory/add] Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/memory/query")
async def query_memory(
    request: QueryMemoryRequest,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    """
    Query Personal Memory using Natural Language (Proxy to Cloud Backend)

    Supports three query types (auto-detected):
    - Task query: Find complete workflow for a task
    - Navigation query: Find path between two states (if start_state and end_state provided)
    - Action query: Find available actions in current state (if current_state provided)

    Headers:
        X-Ami-API-Key: API key for LLM (required for reasoning)
        X-User-Id: User ID for private memory routing (required)
    """
    try:
        if not cloud_client:
            return {"success": False, "error": "Cloud client not initialized"}

        # Support both 'target' and 'query' parameter names
        query_text = request.target or request.query or ""

        # Set API key for cloud client
        if x_ami_api_key:
            cloud_client.set_user_api_key(x_ami_api_key)

        logger.info(f"[memory/query] Proxying query to Cloud Backend: {query_text[:50]}...")

        result = await cloud_client.query_memory(
            user_id=x_user_id,
            query=query_text,
            top_k=request.top_k,
        )

        logger.info(f"[memory/query] Result: type={result.get('query_type')}, "
                   f"success={result.get('success')}")
        return result

    except Exception as e:
        logger.error(f"[memory/query] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/memory/stats")
async def get_memory_stats(
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    """
    Get Memory Statistics (Proxy to Cloud Backend)

    Headers:
        X-User-Id: User ID for private memory routing (required)
    """
    try:
        if not cloud_client:
            return {"success": False, "error": "Cloud client not initialized"}

        if x_ami_api_key:
            cloud_client.set_user_api_key(x_ami_api_key)

        logger.info("[memory/stats] Proxying stats request to Cloud Backend...")

        result = await cloud_client.get_memory_stats(user_id=x_user_id)
        logger.info(f"[memory/stats] Result: {result}")
        return result

    except Exception as e:
        logger.error(f"[memory/stats] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/memory/debug")
async def debug_memory():
    """
    Debug endpoint - not available in proxy mode.

    Returns error message indicating this endpoint requires local memory.
    """
    return {
        "success": False,
        "error": "Debug endpoint not available in proxy mode. Memory is proxied to Cloud Backend.",
    }


@app.delete("/api/v1/memory")
async def clear_memory(
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    """
    Clear Memory (Proxy to Cloud Backend)

    Headers:
        X-User-Id: User ID for private memory routing (required)
    """
    try:
        if not cloud_client:
            return {"success": False, "error": "Cloud client not initialized"}

        if x_ami_api_key:
            cloud_client.set_user_api_key(x_ami_api_key)

        logger.info("[memory/clear] Proxying clear request to Cloud Backend...")

        result = await cloud_client.clear_memory(user_id=x_user_id)
        logger.info(f"[memory/clear] Result: {result}")
        return result

    except Exception as e:
        logger.error(f"[memory/clear] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CognitivePhrase API Endpoints (Proxy to Cloud Backend)
# ============================================================================

@app.get("/api/v1/memory/phrases")
async def list_cognitive_phrases(
    limit: int = 50,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    """
    List CognitivePhrases from Memory (Proxy to Cloud Backend)

    Query Parameters:
        limit: Maximum number of phrases to return (default: 50)

    Headers:
        X-User-Id: User ID for private memory routing (required)
    """
    try:
        if not cloud_client:
            return {"success": False, "error": "Cloud client not initialized"}

        if x_ami_api_key:
            cloud_client.set_user_api_key(x_ami_api_key)

        logger.info(f"[memory/phrases] Proxying list request to Cloud Backend (limit={limit})...")

        result = await cloud_client.list_cognitive_phrases(limit=limit, user_id=x_user_id)
        logger.info(f"[memory/phrases] Found {result.get('total', 0)} cognitive phrases")
        return result

    except Exception as e:
        logger.error(f"[memory/phrases] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/memory/phrases/{phrase_id}")
async def get_cognitive_phrase(
    phrase_id: str,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    """
    Get CognitivePhrase Detail with States and IntentSequences (Proxy to Cloud Backend)

    Path Parameters:
        phrase_id: CognitivePhrase ID

    Headers:
        X-User-Id: User ID for private memory routing (required)
    """
    try:
        if not cloud_client:
            return {"success": False, "error": "Cloud client not initialized"}

        if x_ami_api_key:
            cloud_client.set_user_api_key(x_ami_api_key)

        logger.info(f"[memory/phrases] Proxying get request to Cloud Backend: {phrase_id}...")

        result = await cloud_client.get_cognitive_phrase(phrase_id, user_id=x_user_id)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=f"Phrase {phrase_id} not found")

        logger.info(f"[memory/phrases] Got cognitive phrase: {phrase_id}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[memory/phrases] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/memory/phrases/{phrase_id}")
async def delete_cognitive_phrase(
    phrase_id: str,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    """
    Delete a CognitivePhrase from Memory (Proxy to Cloud Backend)

    Path Parameters:
        phrase_id: CognitivePhrase ID to delete

    Headers:
        X-User-Id: User ID for private memory routing (required)
    """
    try:
        if not cloud_client:
            return {"success": False, "error": "Cloud client not initialized"}

        if x_ami_api_key:
            cloud_client.set_user_api_key(x_ami_api_key)

        logger.info(f"[memory/phrases] Proxying delete request to Cloud Backend: {phrase_id}...")

        result = await cloud_client.delete_cognitive_phrase(phrase_id, user_id=x_user_id)
        if result.get("success"):
            logger.info(f"[memory/phrases] Deleted cognitive phrase: {phrase_id}")
            return result
        else:
            raise HTTPException(status_code=404, detail=f"Phrase {phrase_id} not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[memory/phrases] Failed: {e}")
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
    global browser_manager
    global recording_service, cloud_client

    logger.info("🧹 Cleaning up resources...")

    cleanup_errors = []

    try:
        # 1. Stop active recording if any
        if recording_service and recording_service.is_recording():
            logger.info("Stopping active recording...")
            try:
                await asyncio.wait_for(recording_service.stop_recording(), timeout=3.0)
                await recording_service.close_browser()
                logger.info("✓ Recording stopped")
            except asyncio.TimeoutError:
                logger.warning("⚠️  Recording stop timeout")
                cleanup_errors.append("Recording stop timeout")
            except Exception as e:
                logger.error(f"⚠️  Failed to stop recording: {e}")
                cleanup_errors.append(f"Recording: {e}")

        # 2. Stop HybridBrowserSession daemon session (V3)
        from src.clients.desktop_app.ami_daemon.base_agent.tools.eigent_browser.browser_session import HybridBrowserSession
        if HybridBrowserSession.get_daemon_session():
            logger.info("Stopping HybridBrowserSession daemon session...")
            try:
                await asyncio.wait_for(
                    HybridBrowserSession.stop_daemon_session(),
                    timeout=5.0
                )
                logger.info("✓ HybridBrowserSession daemon session stopped")
            except asyncio.TimeoutError:
                logger.warning("⚠️  HybridBrowserSession stop timeout")
                cleanup_errors.append("HybridBrowserSession: timeout")
            except Exception as e:
                logger.error(f"⚠️  HybridBrowserSession error: {e}")
                cleanup_errors.append(f"HybridBrowserSession: {e}")

        # 4. Stop legacy browser manager
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

        # 6. Close cloud client connection
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

        # 7. Summary
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

    url = f"http://{host}:{port}/api/v1/health"
    try:
        # Disable proxy for localhost connections to avoid 502 errors
        proxy_handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(proxy_handler)
        req = urllib.request.Request(url, method='GET')
        with opener.open(req, timeout=timeout) as response:
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
    # Use command line port if specified, otherwise use config
    start_port = _args.port if _args.port != 8765 else config.get("daemon.port", 8765)
    host = config.get("daemon.host", "127.0.0.1")

    if _args.debug:
        logger.info("=" * 60)
        logger.info("DEBUG MODE ENABLED")
        logger.info("Browser operations will log detailed diagnostic information")
        logger.info("=" * 60)

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
