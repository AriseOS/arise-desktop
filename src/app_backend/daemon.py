#!/usr/bin/env python3
"""
App Backend Daemon - HTTP API Version
Provides REST API endpoints for desktop app communication
"""
import sys
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional

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
    title="AgentCrafter App Backend",
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
    metaflow_id: str
    user_id: str = "default_user"


class GenerateWorkflowResponse(BaseModel):
    workflow_name: str
    local_path: str


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


class ListWorkflowsResponse(BaseModel):
    workflows: list[str]


# ============================================================================
# Startup/Shutdown Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global browser_manager, workflow_executor, cdp_recorder, cloud_client

    logger.info("Initializing App Backend services...")

    # Initialize browser manager with config service
    browser_manager = BrowserManager(
        headless=config.get("browser.headless", False),
        config_service=config
    )
    await browser_manager.init_global_session()
    logger.info("✓ Browser manager initialized")

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
# Recording APIs
# ============================================================================

@app.post("/api/recording/start", response_model=StartRecordingResponse)
async def start_recording(request: StartRecordingRequest):
    """Start CDP recording session"""
    try:
        logger.info(f"Starting recording: url={request.url}, title={request.title}")

        # Prepare metadata
        metadata = request.task_metadata or {}
        metadata.update({
            "title": request.title,
            "description": request.description
        })

        result = await cdp_recorder.start_recording(request.url, metadata=metadata)
        logger.info(f"Recording started: session_id={result['session_id']}")
        return result
    except Exception as e:
        logger.error(f"Failed to start recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/recording/stop", response_model=StopRecordingResponse)
async def stop_recording():
    """Stop recording and save"""
    try:
        logger.info("Stopping recording...")
        result = await cdp_recorder.stop_recording()
        logger.info(f"Recording stopped: {result['operations_count']} operations")
        return result
    except Exception as e:
        logger.error(f"Failed to stop recording: {e}")
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
    """Generate Workflow from MetaFlow"""
    try:
        logger.info(f"Generating Workflow from MetaFlow: {request.metaflow_id}")

        # Call Cloud Backend to generate Workflow
        result = await cloud_client.generate_workflow(
            request.metaflow_id, request.user_id
        )

        workflow_name = result["workflow_name"]
        workflow_yaml = result["workflow_yaml"]

        # Save to local storage
        storage_manager.save_workflow(
            request.user_id, workflow_name, workflow_yaml
        )

        local_path = str(
            storage_manager._user_path(request.user_id) / "workflows" /
            workflow_name / "workflow.yaml"
        )

        logger.info(f"Workflow saved locally: {local_path}")

        return {
            "workflow_name": workflow_name,
            "local_path": local_path
        }

    except Exception as e:
        logger.error(f"Failed to generate workflow: {e}")
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
    """List all workflows for a user"""
    try:
        workflows = storage_manager.list_workflows(user_id)
        return {"workflows": workflows}
    except Exception as e:
        logger.error(f"Failed to list workflows: {e}")
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
