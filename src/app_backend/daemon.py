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

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add project root to sys.path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.app_backend.core.config_service import get_config
from src.app_backend.services.storage_manager import StorageManager
from src.app_backend.services.browser_manager import BrowserManager
from src.app_backend.services.workflow_executor import WorkflowExecutor
from src.app_backend.services.cdp_recorder import CDPRecorder
from src.app_backend.services.cloud_client import CloudClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Load configuration
config = get_config()

# Global service instances
storage_manager = StorageManager(config.get("storage.base_path"))
browser_manager: Optional[BrowserManager] = None
workflow_executor: Optional[WorkflowExecutor] = None
cdp_recorder: Optional[CDPRecorder] = None
cloud_client: Optional[CloudClient] = None

# FastAPI app
app = FastAPI(
    title="Ami App Backend",
    description="HTTP API for desktop app communication",
    version="1.0.0"
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
    user_id: str = "default_user"


class UploadRecordingResponse(BaseModel):
    recording_id: str
    status: str


class GenerateMetaflowRequest(BaseModel):
    task_description: str
    user_id: str = "default_user"


class GenerateMetaflowResponse(BaseModel):
    metaflow_id: str
    local_path: str


class GenerateWorkflowRequest(BaseModel):
    """Unified workflow generation request

    Supports multiple generation modes:
    1. From recording: provide session_id + task_description
    2. From text description: provide task_description only
    3. From MetaFlow: provide metaflow_id
    """
    user_id: str = "default_user"
    task_description: Optional[str] = None

    # Optional fields based on generation mode
    session_id: Optional[str] = None              # For recording-based generation
    metaflow_id: Optional[str] = None             # For MetaFlow-based generation


class GenerateWorkflowResponse(BaseModel):
    """Unified workflow generation response"""
    workflow_name: str
    local_path: str
    status: str = "success"


class ExecuteWorkflowRequest(BaseModel):
    workflow_name: str
    user_id: str = "default_user"


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
    is_downloaded: bool = False
    source: str = "unknown"  # "cloud", "local", or "both"


class ListWorkflowsResponse(BaseModel):
    workflows: list[WorkflowInfo]


# ============================================================================
# Startup/Shutdown Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global browser_manager, workflow_executor, cdp_recorder, cloud_client

    logger.info("Initializing App Backend services...")

    # Initialize browser manager (but do NOT start browser yet - on-demand startup)
    browser_manager = BrowserManager(config_service=config)
    logger.info("✓ Browser manager initialized (browser not started - will start on demand)")

    # Initialize workflow executor
    workflow_executor = WorkflowExecutor(storage_manager, browser_manager)
    logger.info("✓ Workflow executor initialized")

    # Initialize CDP recorder
    cdp_recorder = CDPRecorder(storage_manager, browser_manager)
    logger.info("✓ CDP recorder initialized")

    # Initialize cloud client
    cloud_client = CloudClient(
        api_url=config.get("cloud.api_url", "https://api.ami.com")
    )
    logger.info("✓ Cloud client initialized")

    logger.info("App Backend daemon ready!")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down App Backend...")

    if browser_manager:
        await browser_manager.cleanup()
        logger.info("✓ Browser cleaned up")

    logger.info("Shutdown complete")


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
async def get_dashboard(user_id: str = "default_user"):
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
        result = await cdp_recorder.start_recording(request.url, metadata=metadata)
        logger.info(f"Recording started: session_id={result['session_id']}")
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


@app.get("/api/recordings")
async def list_recordings(user_id: str = "default_user"):
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
async def list_recordings_legacy(user_id: str = "default_user"):
    """List all recordings for a user (legacy endpoint)"""
    return await list_recordings(user_id)


@app.get("/api/recordings/{session_id}")
async def get_recording_detail(session_id: str, user_id: str = "default_user"):
    """Get detailed recording information"""
    try:
        logger.info(f"Getting recording detail: session_id={session_id}")
        detail = storage_manager.get_recording_detail(user_id, session_id)

        if detail is None:
            raise HTTPException(status_code=404, detail=f"Recording not found: {session_id}")

        return detail
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get recording detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/recordings/{session_id}")
async def delete_recording(session_id: str, user_id: str = "default_user"):
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
async def upload_recording_to_cloud(request: UploadRecordingRequest):
    """Upload recording to Cloud Backend for intent extraction"""
    try:
        logger.info(f"Uploading recording from session: {request.session_id}")

        # Load operations from local storage
        recording_data = storage_manager.get_recording(
            request.user_id, request.session_id
        )
        operations = recording_data.get("operations", [])

        # Upload recording to Cloud Backend (with task_description)
        recording_id = await cloud_client.upload_recording(
            operations, request.task_description, request.user_id
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
async def generate_metaflow(request: GenerateMetaflowRequest):
    """Generate MetaFlow from user's Intent Memory Graph"""
    try:
        logger.info(f"Generating MetaFlow for task: {request.task_description}")

        # Call Cloud Backend to generate MetaFlow
        result = await cloud_client.generate_metaflow(
            request.task_description, request.user_id
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
            "local_path": local_path
        }

    except Exception as e:
        logger.error(f"Failed to generate MetaFlow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Workflow APIs
# ============================================================================

@app.post("/api/workflows/generate", response_model=GenerateWorkflowResponse)
async def generate_workflow(request: GenerateWorkflowRequest):
    """Unified Workflow Generation Endpoint

    Supports multiple generation modes:
    1. From recording: provide session_id + task_description
    2. From text description: provide task_description only
    3. From MetaFlow: provide metaflow_id

    All modes call Cloud Backend for AI-powered workflow generation.
    """
    try:
        logger.info(f"Generating workflow for user: {request.user_id}")

        # Determine generation mode and execute appropriate flow
        metaflow_id = None
        workflow_name = None
        workflow_yaml = None

        # Mode 1: From MetaFlow (direct generation)
        if request.metaflow_id:
            logger.info(f"Mode: Generate from MetaFlow {request.metaflow_id}")
            metaflow_id = request.metaflow_id

        # Mode 2: From Recording
        elif request.session_id:
            logger.info(f"Mode: Generate from recording {request.session_id}")

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

            # Upload recording to Cloud Backend
            logger.info("Uploading recording to Cloud Backend...")
            await cloud_client.upload_recording(
                operations=operations,
                task_description=request.task_description or "Auto-generated from recording",
                user_id=request.user_id
            )

            # Generate MetaFlow from recording
            logger.info("Generating MetaFlow from recording...")
            metaflow_result = await cloud_client.generate_metaflow(
                task_description=request.task_description or "Auto-generated from recording",
                user_id=request.user_id
            )
            metaflow_id = metaflow_result["metaflow_id"]
            metaflow_yaml = metaflow_result["metaflow_yaml"]

            # Save MetaFlow locally
            storage_manager.save_metaflow(
                request.user_id,
                metaflow_id,
                metaflow_yaml,
                request.task_description or "Auto-generated from recording"
            )
            logger.info(f"MetaFlow saved: {metaflow_id}")

        # Mode 3: From Text Description
        else:
            logger.info("Mode: Generate from text description")

            if not request.task_description:
                raise HTTPException(
                    status_code=400,
                    detail="task_description is required when not providing session_id or metaflow_id"
                )

            # Generate MetaFlow from task description
            logger.info(f"Generating MetaFlow from task: {request.task_description[:50]}...")
            metaflow_result = await cloud_client.generate_metaflow(
                task_description=request.task_description,
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
            logger.info(f"MetaFlow saved: {metaflow_id}")

        # Common: Generate Workflow from MetaFlow (all modes converge here)
        logger.info(f"Generating Workflow from MetaFlow: {metaflow_id}")
        workflow_result = await cloud_client.generate_workflow(
            metaflow_id=metaflow_id,
            user_id=request.user_id
        )

        workflow_name = workflow_result["workflow_name"]
        workflow_yaml = workflow_result["workflow_yaml"]

        # Save Workflow locally
        storage_manager.save_workflow(
            request.user_id,
            workflow_name,
            workflow_yaml
        )

        local_path = str(
            storage_manager._user_path(request.user_id) / "workflows" /
            workflow_name / "workflow.yaml"
        )

        logger.info(f"✅ Workflow generated and saved: {workflow_name} at {local_path}")

        return {
            "workflow_name": workflow_name,
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
async def execute_workflow(request: ExecuteWorkflowRequest):
    """Execute a workflow asynchronously"""
    try:
        logger.info(f"Executing workflow: {request.workflow_name}")
        result = await workflow_executor.execute_workflow_async(
            request.user_id, request.workflow_name
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


@app.get("/api/workflows", response_model=ListWorkflowsResponse)
async def list_workflows(user_id: str = "default_user"):
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
                workflows_dict[wf['agent_id']] = {
                    'agent_id': wf['agent_id'],
                    'name': wf.get('name', wf['agent_id']),
                    'description': wf.get('description', ''),
                    'created_at': wf.get('created_at'),
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
                # Use local metadata if cloud doesn't have it
                if not workflows_dict[wf_id].get('name'):
                    workflows_dict[wf_id]['name'] = local_info['name']
                if not workflows_dict[wf_id].get('description'):
                    workflows_dict[wf_id]['description'] = local_info['description']
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
async def get_workflow_detail(workflow_id: str, user_id: str = "default_user"):
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

        # Extract workflow metadata
        name = workflow_data.get('name', workflow_id)
        description = workflow_data.get('description', '')

        # Extract steps
        steps_list = []
        steps_data = workflow_data.get('steps', [])

        for idx, step in enumerate(steps_data):
            step_id = step.get('id', f"step-{idx}")
            steps_list.append({
                'id': step_id,
                'name': step.get('name', step_id),
                'type': step.get('type', 'unknown'),
                'description': step.get('description', ''),
                'branch': step.get('branch'),
                'agent_type': step.get('agent_type'),
                'prompt': step.get('prompt'),
                'tool': step.get('tool')
            })

        # Extract connections (if exists) or auto-generate
        connections = workflow_data.get('connections', [])

        response_data = {
            'workflow_id': workflow_id,
            'name': name,
            'description': description,
            'steps': steps_list,
            'connections': connections
        }

        logger.info(f"Loaded workflow detail: {workflow_id}")
        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/workflows/{workflow_id}")
async def delete_workflow(workflow_id: str, user_id: str = "default_user"):
    """Delete a workflow and all its execution history"""
    try:
        logger.info(f"Deleting workflow: workflow_id={workflow_id}")
        success = storage_manager.delete_workflow(user_id, workflow_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

        logger.info(f"Workflow deleted: {workflow_id}")
        return {"status": "success", "message": "Workflow deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Start HTTP server"""
    port = config.get("daemon.port", 8765)
    host = config.get("daemon.host", "127.0.0.1")

    logger.info(f"Starting App Backend daemon on {host}:{port}")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
