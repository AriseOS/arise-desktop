"""
Ami Cloud Backend - Server-side data processing and AI analysis center

Runs on server, using:
- Server local filesystem (/var/lib/ami/ or ~/ami-server/)
- Local PostgreSQL database
- LLM API (Anthropic Claude / OpenAI GPT)

Responsibilities:
1. User management (registration, login, token management)
2. Recording data processing (receive, store to server filesystem)
3. AI analysis (Intent extraction, direct Workflow generation using Claude Agent SDK)
4. Workflow management (store to server filesystem, provide download)
5. Workflow dialogue modification (WorkflowBuilderSession for conversational editing)
6. Statistics (execution reporting, success rate analysis)
"""

import uvicorn
import logging
import sys
import uuid
import asyncio
import json
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from typing import Optional

# 添加项目根目录到 Python 路径
# 当前文件: src/cloud-backend/main.py
# 需要到达: ami/ (项目根目录)
project_root = Path(__file__).parent.parent.parent  # 向上3层
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)

# Load configuration early (before creating app)
from core.config_service import CloudConfigService
config_service = CloudConfigService()

# Global service instances
storage_service = None
workflow_service = None  # New WorkflowService (replaces old WorkflowGenerationService)

# Background task management
cleanup_task = None
cleanup_task_running = False

def start_session_cleanup_task(timeout_minutes: int, interval_minutes: int):
    """Start background task to cleanup expired Intent Builder sessions"""
    global cleanup_task, cleanup_task_running

    async def cleanup_loop():
        global cleanup_task_running
        cleanup_task_running = True
        logger.info(f"🧹 Session cleanup task started (timeout={timeout_minutes}min, interval={interval_minutes}min)")

        while cleanup_task_running:
            try:
                # Wait for interval
                await asyncio.sleep(interval_minutes * 60)

                # Run cleanup
                logger.debug(f"🧹 Running session cleanup...")
                cleaned_count = storage_service.cleanup_expired_sessions(timeout_minutes)

                if cleaned_count > 0:
                    logger.info(f"🧹 Cleaned {cleaned_count} expired sessions")

            except asyncio.CancelledError:
                logger.info("🧹 Session cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Session cleanup error: {e}")
                # Continue running despite errors

    # Start the background task
    cleanup_task = asyncio.create_task(cleanup_loop())

def stop_session_cleanup_task():
    """Stop the background cleanup task"""
    global cleanup_task, cleanup_task_running

    cleanup_task_running = False
    if cleanup_task:
        cleanup_task.cancel()
        logger.info("🧹 Session cleanup task stopped")

# Create FastAPI application
app = FastAPI(
    title="Ami Cloud Backend",
    description="Server-side AI analysis and data storage",
    version="2.0.0"
)

# Setup CORS from config (must be done before app starts)
cors_origins = config_service.get("cors.allow_origins", ["*"])
cors_credentials = config_service.get("cors.allow_credentials", True)
cors_methods = config_service.get("cors.allow_methods", ["*"])
cors_headers = config_service.get("cors.allow_headers", ["*"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_credentials,
    allow_methods=cors_methods,
    allow_headers=cors_headers,
)

# Add request context middleware for logging
from core.middleware import RequestContextMiddleware
app.add_middleware(RequestContextMiddleware)

@app.on_event("startup")
async def startup_event():
    """Startup initialization"""
    global storage_service, workflow_service

    print("\n" + "="*80)
    print("☁️  Ami Cloud Backend Starting...")
    print("="*80)
    print(f"📝 Config: {config_service.config_path}")

    try:
        from services.storage_service import StorageService
        from src.cloud_backend.intent_builder.services import WorkflowService

        # 1. CORS already configured
        print(f"✅ CORS: {len(cors_origins)} allowed origins")

        # 2. Initialize storage service
        storage_base_path = config_service.get_storage_path()
        storage_service = StorageService(base_path=str(storage_base_path))
        print(f"✅ Storage: {storage_service.base_path}")

        # 3. Initialize WorkflowService (new architecture using Claude Agent SDK + Skills)
        workflow_service = WorkflowService(
            config_service=config_service,
            base_url=config_service.get("llm.proxy_url")
        )
        print("✅ Workflow Service (Claude Agent SDK + Skills)")

        # 4. Setup structured logging
        log_level = config_service.get("logging.level", "INFO")
        json_logging = config_service.get("logging.json_format", True)
        log_file = config_service.get("logging.file", None)
        max_bytes = config_service.get("logging.max_bytes", 100 * 1024 * 1024)
        backup_count = config_service.get("logging.backup_count", 5)
        loki_url = config_service.get("logging.loki_url", None)

        from core.logging_config import setup_logging
        setup_logging(
            service_name="cloud_backend",
            level=log_level,
            json_format=json_logging,
            log_file=log_file,
            max_bytes=max_bytes,
            backup_count=backup_count,
            loki_url=loki_url,
        )
        log_info = f"✅ Logging: {log_level} (JSON={json_logging})"
        if log_file:
            log_info += f" -> {log_file}"
        print(log_info)

        # 5. Start session cleanup background task
        session_timeout_minutes = config_service.get("session.timeout_minutes", 30)
        cleanup_interval_minutes = config_service.get("session.cleanup_interval_minutes", 5)
        start_session_cleanup_task(session_timeout_minutes, cleanup_interval_minutes)
        print(f"✅ Session Cleanup: timeout={session_timeout_minutes}min, interval={cleanup_interval_minutes}min")

        # 6. TODO: Initialize database connection
        # db_type = config_service.get("database.type", "sqlite")
        # if db_type == "postgresql":
        #     from database.connection import init_db
        #     await init_db(config_service)

        print("="*80)
        print("✅ Cloud Backend Ready!")
        print(f"   Server: http://{config_service.get('server.host')}:{config_service.get('server.port')}")
        print(f"   Docs: http://localhost:{config_service.get('server.port')}/docs")
        print("="*80 + "\n")

    except Exception as e:
        print(f"❌ Failed to initialize services: {e}")
        import traceback
        traceback.print_exc()

@app.on_event("shutdown")
async def shutdown_event():
    """关闭时清理资源"""
    # Stop session cleanup task
    stop_session_cleanup_task()

    # TODO: 关闭数据库连接
    print("✅ Cloud Backend shutdown complete")

# 健康检查
@app.get("/health")
def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "service": "cloud-backend",
        "version": "2.0.0"
    }

@app.get("/")
def root():
    """根路径"""
    return {
        "service": "Ami Cloud Backend",
        "version": "2.0.0",
        "docs": "/docs"
    }


# ===== Version Check API =====

def get_minimum_app_version() -> str:
    """Get minimum app version from config"""
    return config_service.get("app.minimum_version", "0.0.1")

def parse_version(version: str) -> tuple:
    """Parse semantic version string to tuple for comparison"""
    try:
        parts = version.split(".")
        return tuple(int(p) for p in parts)
    except (ValueError, AttributeError):
        return (0, 0, 0)

def is_version_compatible(client_version: str, minimum_version: str) -> bool:
    """Check if client version meets minimum requirement"""
    client = parse_version(client_version)
    minimum = parse_version(minimum_version)
    return client >= minimum


@app.post("/api/v1/app/version-check")
async def check_app_version(data: dict):
    """
    Check if app version is compatible

    Body:
        {
            "version": "0.0.1",
            "platform": "macos-arm64" | "macos-x64" | "windows-x64" | "linux-x64"
        }

    Returns:
        {
            "compatible": true/false,
            "minimum_version": "0.0.1",
            "update_url": "http://..." (only if not compatible),
            "message": "..." (optional message)
        }
    """
    client_version = data.get("version", "0.0.0")
    platform = data.get("platform", "unknown")

    minimum_version = get_minimum_app_version()
    compatible = is_version_compatible(client_version, minimum_version)

    response = {
        "compatible": compatible,
        "minimum_version": minimum_version,
        "client_version": client_version
    }

    if not compatible:
        # Build platform-specific download URL
        # Only macos-arm64 and windows-x64 are currently supported
        base_url = "http://download.ariseos.com/releases/latest"

        platform_urls = {
            "macos-arm64": f"{base_url}/macos-arm64/Ami-latest-macos-arm64.dmg",
            "windows-x64": f"{base_url}/windows-x64/Ami-latest-windows-x64.zip",
        }

        response["update_url"] = platform_urls.get(platform, base_url)
        response["message"] = f"Please update Ami to version {minimum_version} or later"

        logger.info(f"Version check: {client_version} < {minimum_version} (platform: {platform})")
    else:
        logger.debug(f"Version check: {client_version} is compatible")

    return response


# ===== Auth API =====

@app.post("/api/v1/auth/login")
async def login(data: dict):
    """
    用户登录
    
    Body:
        {"username": "...", "password": "..."}
        
    Returns:
        {"token": "...", "user_id": "..."}
    """
    username = data.get("username")
    password = data.get("password")
    
    if not username or not password:
        raise HTTPException(400, "Missing username or password")
    
    # TODO: 实现真正的数据库查询和密码验证
    # from database.models import User
    # user = db.query(User).filter(User.username == username).first()
    # if not user or not verify_password(password, user.hashed_password):
    #     raise HTTPException(401, "Invalid credentials")
    
    # TODO: 生成真实的 JWT token
    # from services.auth_service import create_access_token
    # token = create_access_token(user_id=user.id)
    
    # 临时实现：接受任何登录
    logger.info(f"User login: {username}")
    return {
        "token": f"token_{username}_{uuid.uuid4().hex[:8]}",
        "user_id": username
    }

@app.post("/api/v1/auth/register")
async def register(data: dict):
    """
    用户注册
    
    Body:
        {"username": "...", "email": "...", "password": "..."}
    """
    # TODO: 实现注册逻辑
    return {"success": True, "user_id": data.get("username")}

# ===== Recordings API =====

@app.post("/api/v1/recordings")
async def upload_recording(data: dict):
    """
    Upload recording and add intents to user's Intent Memory Graph (async)

    Body:
        {
            "user_id": "user123",
            "user_api_key": "ami_xxx...",  # User's Ami API key for LLM calls
            "task_description": "Search for coffee on Google",  # User's description of what they did
            "operations": [...]
        }

    Returns:
        {"recording_id": "..."}

    Note: Intent extraction happens in background. Graph is updated asynchronously.
    """
    user_id = data.get("user_id")
    user_api_key = data.get("user_api_key")
    task_description = data.get("task_description", "")
    user_query = data.get("user_query")
    operations = data.get("operations", [])
    # Allow client to provide recording_id (e.g., App Backend's session_id)
    recording_id = data.get("recording_id") or str(uuid.uuid4())

    if not user_id:
        raise HTTPException(400, "Missing user_id")

    if not user_api_key:
        raise HTTPException(400, "Missing user_api_key")

    if not operations:
        raise HTTPException(400, "Missing operations")

    # Save recording to filesystem first (with provided task_description and user_query)
    file_path = storage_service.save_recording(
        user_id,
        recording_id,
        operations,
        task_description=task_description,
        user_query=user_query
    )

    logger.info(f"Recording uploaded: {recording_id} ({len(operations)} ops)")
    if task_description:
        logger.info(f"  Task: {task_description}")
    if user_query:
        logger.info(f"  User query: {user_query}")

    # Start background task to auto-generate task_description and user_query if not provided
    if not task_description or not user_query:
        logger.info(f"Starting background AI analysis for recording {recording_id}")
        asyncio.create_task(
            analyze_and_update_recording_background(
                user_id=user_id,
                recording_id=recording_id,
                operations=operations,
                has_task_description=bool(task_description),
                has_user_query=bool(user_query)
            )
        )

    # Start background task to extract intents and add to user's graph
    asyncio.create_task(
        add_intents_to_user_graph_background(
            user_id,
            recording_id,
            operations,
            task_description,
            user_api_key
        )
    )

    return {"recording_id": recording_id}


async def analyze_and_update_recording_background(
    user_id: str,
    recording_id: str,
    operations: list,
    has_task_description: bool,
    has_user_query: bool
):
    """Background task: Analyze recording and update with AI-generated descriptions"""
    try:
        logger.info(f"🤖 Background: Analyzing recording {recording_id}")

        from services.recording_analysis_service import RecordingAnalysisService
        analysis_service = RecordingAnalysisService()

        # Call AI to analyze operations
        analysis_result = await analysis_service.analyze_operations(
            operations=operations,
            user_id=user_id
        )

        task_description = None
        user_query = None

        if not has_task_description:
            task_description = analysis_result.get("task_description", "")
            logger.info(f"✨ Generated task_description: {task_description[:100]}...")

        if not has_user_query:
            user_query = analysis_result.get("user_query", "")
            logger.info(f"✨ Generated user_query: {user_query[:100]}...")

        # Update recording with AI-generated descriptions
        storage_service.update_recording(
            user_id=user_id,
            recording_id=recording_id,
            task_description=task_description,
            user_query=user_query
        )

        logger.info(f"✅ Background: Recording {recording_id} analysis complete")

    except Exception as e:
        logger.error(f"❌ Background: Failed to analyze recording {recording_id}: {e}")
        import traceback
        traceback.print_exc()


async def add_intents_to_user_graph_background(
    user_id: str,
    recording_id: str,
    operations: list,
    task_description: str,
    user_api_key: str
):
    """Background task: Extract intents from operations and add to user's Intent Graph"""
    try:
        logger.info(f"🔄 Background: Adding intents from recording {recording_id} to user {user_id}'s graph")
        if task_description:
            logger.info(f"   Task description: {task_description}")

        # Get user's Intent Graph file path
        graph_filepath = storage_service.get_user_intent_graph_path(user_id)

        # Create a WorkflowService with user's API key for this request
        from src.cloud_backend.intent_builder.services import WorkflowService
        service = WorkflowService(
            config_service=config_service,
            api_key=user_api_key,
            base_url=config_service.get("llm.proxy_url")
        )

        # Extract intents and add to graph
        new_intents_count = await service.add_intents_to_graph(
            operations=operations,
            graph_filepath=str(graph_filepath),
            task_description=task_description
        )

        logger.info(f"✅ Background: Added {new_intents_count} intents from recording {recording_id}")

    except Exception as e:
        logger.error(f"❌ Background: Failed to add intents from recording {recording_id}: {e}")
        import traceback
        traceback.print_exc()


@app.post("/api/v1/recordings/analyze")
async def analyze_recording(data: dict, x_ami_api_key: Optional[str] = Header(None)):
    """
    Analyze recording operations using AI and generate suggested descriptions

    Body:
        {
            "operations": [...],
            "user_id": "user123"
        }

    Headers:
        X-Ami-API-Key: User's API key (required)

    Returns:
        {
            "task_description": "What user did",
            "user_query": "What user wants to achieve",
            "patterns": {
                "loop_detected": true/false,
                "loop_count": N,
                "extracted_fields": ["field1", "field2"],
                "navigation_depth": N
            }
        }
    """
    operations = data.get("operations", [])
    user_id = data.get("user_id")

    if not user_id:
        raise HTTPException(400, "Missing user_id")

    if not operations:
        raise HTTPException(400, "Missing operations")

    if not x_ami_api_key:
        raise HTTPException(400, "Missing X-Ami-API-Key header")

    logger.info(f"Analyzing recording with {len(operations)} operations for user {user_id}")

    try:
        # Create LLM provider with user's API key through API Proxy
        from src.common.llm.anthropic_provider import AnthropicProvider
        llm_provider = AnthropicProvider(
            api_key=x_ami_api_key,
            base_url=config_service.get("llm.proxy_url", "https://api.ariseos.com/api")
        )

        # Import and initialize analysis service
        from services.recording_analysis_service import RecordingAnalysisService
        analysis_service = RecordingAnalysisService(llm_provider=llm_provider)

        # Analyze operations
        result = await analysis_service.analyze_operations(
            operations=operations,
            user_id=user_id
        )

        return result

    except Exception as e:
        logger.error(f"Failed to analyze recording: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Analysis failed: {str(e)}")



# ===== Recordings API (List/Detail) =====

@app.get("/api/v1/recordings")
async def list_recordings(user_id: str):
    """
    List all recordings for user with metadata

    Query:
        user_id: User ID

    Returns:
        [{"recording_id": "...", "task_description": "...", "created_at": "...", "metaflow_id": "..."}, ...]
    """
    if not user_id:
        raise HTTPException(400, "Missing user_id")

    recordings = storage_service.list_recordings(user_id)
    return recordings


@app.get("/api/v1/recordings/{recording_id}")
async def get_recording(recording_id: str, user_id: str):
    """
    Get recording detail

    Query:
        user_id: User ID

    Returns:
        {
            "recording_id": "...",
            "task_description": "...",
            "user_query": "...",
            "created_at": "...",
            "operations_count": N,
            "operations": [...],
            "metaflow_id": "..."
        }
    """
    if not user_id:
        raise HTTPException(400, "Missing user_id")

    recording = storage_service.get_recording(user_id, recording_id)
    if not recording:
        raise HTTPException(404, f"Recording not found: {recording_id}")

    return recording


# ===== Workflows API =====

@app.get("/api/v1/workflows")
async def list_workflows(user_id: str):
    """
    List all Workflows for user

    Query:
        user_id: User ID

    Returns:
        [{"workflow_id": "...", "workflow_name": "...", "created_at": "...", "updated_at": "..."}, ...]
    """
    if not user_id:
        raise HTTPException(400, "Missing user_id")

    workflows = storage_service.list_workflows(user_id)
    return workflows


@app.get("/api/v1/users/{user_id}/workflows")
async def list_workflows_restful(user_id: str):
    """
    List all Workflows for user (RESTful style)

    This is an alias for GET /api/workflows?user_id={user_id}
    Used by App Backend for consistency with other RESTful endpoints.

    Path:
        user_id: User ID

    Returns:
        {
            "workflows": [
                {
                    "agent_id": "workflow_xxx",  // workflow_id
                    "name": "workflow_name",
                    "description": "Workflow description",
                    "created_at": "timestamp"
                },
                ...
            ]
        }
    """
    try:
        logger.info(f"Listing workflows for user: {user_id}")
        workflows = storage_service.list_workflows(user_id)
        logger.info(f"Found {len(workflows)} workflows")

        # Transform to App Backend expected format
        formatted_workflows = []
        for wf in workflows:
            workflow_id = wf.get("workflow_id")
            workflow_name = wf.get("workflow_name")

            # Use workflow_id as fallback if workflow_name is None or empty
            display_name = workflow_name if workflow_name else workflow_id

            formatted_workflows.append({
                "agent_id": workflow_id,  # App Backend uses agent_id
                "name": display_name,
                "description": display_name,  # Use name as description
                "created_at": wf.get("created_at")
            })

        return {"workflows": formatted_workflows}
    except Exception as e:
        logger.error(f"Failed to list workflows: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to list workflows: {str(e)}")


@app.get("/api/v1/workflows/{workflow_id}")
async def get_workflow(workflow_id: str, user_id: str):
    """
    Get Workflow detail

    Query:
        user_id: User ID

    Returns:
        {
            "workflow_id": "...",
            "workflow_name": "...",
            "workflow_yaml": "...",
            "created_at": "...",
            "updated_at": "..."
        }
    """
    if not user_id:
        raise HTTPException(400, "Missing user_id")

    workflow = storage_service.get_workflow(user_id, workflow_id)
    if not workflow:
        raise HTTPException(404, f"Workflow not found: {workflow_id}")

    return workflow


@app.put("/api/v1/workflows/{workflow_id}")
async def update_workflow(workflow_id: str, data: dict):
    """
    Update Workflow YAML content

    Body:
        {
            "user_id": "user123",
            "workflow_yaml": "..."
        }

    Returns:
        {"success": true}
    """
    user_id = data.get("user_id")
    workflow_yaml = data.get("workflow_yaml")

    if not user_id:
        raise HTTPException(400, "Missing user_id")
    if not workflow_yaml:
        raise HTTPException(400, "Missing workflow_yaml")

    # Check if Workflow exists
    existing = storage_service.get_workflow(user_id, workflow_id)
    if not existing:
        raise HTTPException(404, f"Workflow not found: {workflow_id}")

    storage_service.update_workflow_yaml(user_id, workflow_id, workflow_yaml)
    logger.info(f"Workflow updated via API: {workflow_id}")

    return {"success": True}


@app.get("/api/v1/workflows/{workflow_id}/download")
async def download_workflow(workflow_id: str, user_id: str):
    """
    Download Workflow YAML

    Query:
        user_id: User ID

    Returns:
        {"yaml": "..."}
    """
    if not user_id:
        raise HTTPException(400, "Missing user_id")

    workflow = storage_service.get_workflow(user_id, workflow_id)
    if not workflow:
        raise HTTPException(404, f"Workflow not found: {workflow_id}")

    logger.info(f"Workflow downloaded: {workflow_id}")
    return {"yaml": workflow.get("workflow_yaml", "")}


@app.delete("/api/v1/workflows/{workflow_id}")
async def delete_workflow(workflow_id: str, user_id: str):
    """
    Delete a Workflow from Cloud Backend

    Query:
        user_id: User ID

    Returns:
        {"success": true, "message": "Workflow deleted"}
    """
    if not user_id:
        raise HTTPException(400, "Missing user_id")

    # Delete workflow from storage
    success = storage_service.delete_workflow(user_id, workflow_id)

    if not success:
        raise HTTPException(404, f"Workflow not found: {workflow_id}")

    logger.info(f"Workflow deleted from Cloud: {workflow_id}")
    return {"success": True, "message": "Workflow deleted"}


# ===== NEW: Direct Workflow Generation API (v2) =====
# These endpoints use the new WorkflowBuilder (Claude Agent SDK) architecture
# They bypass the MetaFlow intermediate layer

# Store active workflow builder sessions
_workflow_sessions: dict = {}


@app.post("/api/v1/workflows/generate")
async def generate_workflow_direct(
    data: dict,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """
    Generate Workflow directly from Recording or Intent sequence (NEW v2 API)

    This endpoint uses the new WorkflowBuilder architecture which:
    - Bypasses the MetaFlow intermediate layer
    - Uses Claude Agent SDK for generation
    - Includes two-layer validation (rule + semantic)
    - Supports follow-up dialogue for workflow modification

    Headers:
        X-Ami-API-Key: User's API key (required)

    Body:
        {
            "user_id": "user123",
            "task_description": "Extract product info from website",
            "recording_id": "recording_xxx",           // Optional: generate from recording
            "intent_sequence": [...],                  // Optional: provide Intent sequence directly
            "enable_semantic_validation": true,        // Enable semantic validation (default: true)
            "enable_dialogue": true                    // Keep session for follow-up dialogue (default: true)
        }

    Returns:
        {
            "workflow_id": "workflow_xxx",
            "workflow_name": "extract-products",
            "workflow_yaml": "...",
            "session_id": "ws_xxx",                    // If enable_dialogue=true
            "validation_result": {...},
            "status": "success"
        }
    """
    if not x_ami_api_key:
        raise HTTPException(400, "Missing X-Ami-API-Key header")

    user_id = data.get("user_id")
    task_description = data.get("task_description")
    recording_id = data.get("recording_id")
    operations = data.get("operations")  # Direct operations from App Backend
    source_recording_id = data.get("source_recording_id")  # For traceability
    intent_sequence = data.get("intent_sequence")
    enable_semantic_validation = data.get("enable_semantic_validation", True)
    enable_dialogue = data.get("enable_dialogue", True)

    if not user_id:
        raise HTTPException(400, "Missing user_id")
    if not task_description:
        raise HTTPException(400, "Missing task_description")

    logger.info(f"🚀 [API v2] Generating Workflow directly for user {user_id}")
    logger.info(f"📝 Task Description: {task_description}")

    try:
        # Import the new WorkflowService
        from src.cloud_backend.intent_builder.services import (
            WorkflowService,
            GenerationRequest
        )

        # Get operations from:
        # 1. Direct operations parameter (from App Backend proxy)
        # 2. recording_id (from Cloud Backend storage)
        if not intent_sequence:
            # Try direct operations first (from App Backend)
            if operations:
                logger.info(f"📹 Using direct operations: {len(operations)} operations")
                recording_id = source_recording_id  # Use source_recording_id for traceability
            elif recording_id:
                # Fallback to loading from Cloud Backend storage
                recording_data = storage_service.get_recording(user_id, recording_id)
                if not recording_data:
                    raise HTTPException(404, f"Recording not found: {recording_id}")

                operations = recording_data.get("operations", [])
                if not operations:
                    raise HTTPException(400, f"Recording {recording_id} has no operations")

                logger.info(f"📹 Loaded recording from storage: {len(operations)} operations")

            if operations:
                # Extract intents from operations
                from src.cloud_backend.intent_builder.extractors.intent_extractor import IntentExtractor
                from src.common.llm import AnthropicProvider

                llm = AnthropicProvider(
                    api_key=x_ami_api_key,
                    base_url=config_service.get("llm.proxy_url")
                )
                extractor = IntentExtractor(llm_provider=llm)

                intents = await extractor.extract_intents(
                    operations=operations,
                    task_description=task_description,
                    source_session_id=recording_id or source_recording_id
                )
                intent_sequence = [intent.to_dict() for intent in intents]
                logger.info(f"✅ Extracted {len(intent_sequence)} intents")

        if not intent_sequence:
            raise HTTPException(400, "No intent_sequence, operations, or recording_id provided")

        # Create WorkflowService and generate
        service = WorkflowService(
            config_service=config_service,
            api_key=x_ami_api_key,
            base_url=config_service.get("llm.proxy_url")
        )

        request = GenerationRequest(
            recording_id=recording_id,
            task_description=task_description,
            intent_sequence=intent_sequence,
            enable_semantic_validation=enable_semantic_validation
        )

        response = await service.generate(request, enable_dialogue=enable_dialogue)

        if not response.success:
            raise HTTPException(500, f"Workflow generation failed: {response.error}")

        # Generate workflow_id and save
        workflow_id = response.workflow_id or f"workflow_{uuid.uuid4().hex[:12]}"

        # Extract workflow name from YAML
        import yaml
        workflow_dict = yaml.safe_load(response.workflow_yaml)
        workflow_name = workflow_dict.get("metadata", {}).get("name", workflow_id)

        # Save workflow to storage
        storage_service.save_workflow(
            user_id=user_id,
            workflow_id=workflow_id,
            workflow_yaml=response.workflow_yaml,
            workflow_name=workflow_name,
            source_recording_id=recording_id
        )

        # Link recording to workflow (reverse link)
        if recording_id:
            try:
                storage_service.update_recording_workflow(user_id, recording_id, workflow_id)
                logger.info(f"✅ Recording {recording_id} linked to Workflow {workflow_id}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to link recording to workflow: {e}")

        logger.info(f"✅ Workflow generated and saved: {workflow_id}")

        result = {
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "workflow_yaml": response.workflow_yaml,
            "source_recording_id": recording_id,
            "status": "success"
        }

        if response.session_id:
            result["session_id"] = response.session_id
            # Store session reference for later dialogue
            _workflow_sessions[response.session_id] = {
                "service": service,
                "user_id": user_id,
                "workflow_id": workflow_id,
                "created_at": asyncio.get_event_loop().time()
            }

        if response.validation_result:
            result["validation_result"] = response.validation_result.to_dict()

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Workflow generation failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Workflow generation failed: {str(e)}")


@app.post("/api/v1/workflows/generate-stream")
async def generate_workflow_stream(
    data: dict,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """
    Generate Workflow with streaming progress updates (SSE)

    Same as POST /api/v1/workflows/generate but returns SSE stream
    for Lovable-style progress display.

    Returns SSE stream with events:
        data: {"status": "analyzing", "progress": 10, "message": "分析录制内容..."}
        data: {"status": "understanding", "progress": 30, "message": "理解用户意图..."}
        data: {"status": "generating", "progress": 60, "message": "生成 Workflow 步骤..."}
        data: {"status": "validating", "progress": 90, "message": "校验 Workflow..."}
        data: {"status": "completed", "progress": 100, "workflow_id": "xxx", "workflow": {...}}
    """
    if not x_ami_api_key:
        raise HTTPException(400, "Missing X-Ami-API-Key header")

    user_id = data.get("user_id")
    task_description = data.get("task_description")
    user_query = data.get("user_query")  # User's goal/intent (e.g., "repeat for 10 items")
    recording_id = data.get("recording_id")
    operations = data.get("operations")  # Direct operations from App Backend
    source_recording_id = data.get("source_recording_id")  # For traceability
    intent_sequence = data.get("intent_sequence")
    enable_semantic_validation = data.get("enable_semantic_validation", True)

    if not user_id:
        raise HTTPException(400, "Missing user_id")
    if not task_description:
        raise HTTPException(400, "Missing task_description")

    # Log user_query if provided
    if user_query:
        logger.info(f"📝 [Stream] User query: {user_query}")

    async def event_generator():
        try:
            logger.info(f"🚀 [Stream] Starting workflow generation for user {user_id}")

            # Import the new WorkflowService
            from src.cloud_backend.intent_builder.services import (
                WorkflowService,
                GenerationRequest,
                GenerationStatus
            )

            # Initial progress
            yield f"data: {json.dumps({'status': 'pending', 'progress': 0, 'message': 'Starting...'})}\n\n"

            # Get intent sequence or operations
            local_intent_sequence = intent_sequence
            local_operations = operations
            local_recording_id = recording_id or source_recording_id

            # If we have direct operations from App Backend, use them
            if not local_intent_sequence and local_operations:
                yield f"data: {json.dumps({'status': 'analyzing', 'progress': 10, 'message': f'Processing {len(local_operations)} operations...'})}\n\n"

            # If no operations yet, try to load from recording
            elif not local_intent_sequence and recording_id:
                yield f"data: {json.dumps({'status': 'analyzing', 'progress': 10, 'message': 'Loading recording...'})}\n\n"

                recording_data = storage_service.get_recording(user_id, recording_id)
                if not recording_data:
                    yield f"data: {json.dumps({'status': 'failed', 'progress': 0, 'message': 'Recording not found'})}\n\n"
                    return

                local_operations = recording_data.get("operations", [])

            # Extract intents from operations if we have them
            if local_operations and not local_intent_sequence:
                yield f"data: {json.dumps({'status': 'analyzing', 'progress': 20, 'message': f'Extracting intents from {len(local_operations)} operations...'})}\n\n"

                from src.cloud_backend.intent_builder.extractors.intent_extractor import IntentExtractor
                from src.common.llm import AnthropicProvider

                llm = AnthropicProvider(
                    api_key=x_ami_api_key,
                    base_url=config_service.get("llm.proxy_url")
                )
                extractor = IntentExtractor(llm_provider=llm)

                intents = await extractor.extract_intents(
                    operations=local_operations,
                    task_description=task_description,
                    source_session_id=local_recording_id,
                    user_query=user_query
                )
                local_intent_sequence = [intent.to_dict() for intent in intents]

                yield f"data: {json.dumps({'status': 'understanding', 'progress': 30, 'message': f'Extracted {len(local_intent_sequence)} intents'})}\n\n"

            if not local_intent_sequence:
                yield f"data: {json.dumps({'status': 'failed', 'progress': 0, 'message': 'No intent sequence'})}\n\n"
                return

            # Create service and generate with streaming
            service = WorkflowService(
                config_service=config_service,
                api_key=x_ami_api_key,
                base_url=config_service.get("llm.proxy_url")
            )

            request = GenerationRequest(
                recording_id=local_recording_id,
                task_description=task_description,
                user_query=user_query,
                intent_sequence=local_intent_sequence,
                enable_semantic_validation=enable_semantic_validation
            )

            # Stream progress and track session_id
            logger.info(f"📊 [Stream] Starting to stream progress...")
            session_id = None
            final_status = None
            final_message = None

            async for progress in service.generate_stream(request):
                event_data = {
                    "status": progress.status.value,
                    "progress": progress.progress,
                    "message": progress.message
                }
                if progress.details:
                    event_data["details"] = progress.details

                # Track final status for result retrieval
                final_status = progress.status.value
                final_message = progress.message

                # Extract session_id from COMPLETED event details
                if progress.status.value == "completed" and progress.details:
                    # Details format: "Session ID: xxx"
                    if progress.details.startswith("Session ID: "):
                        session_id = progress.details.replace("Session ID: ", "")

                logger.info(f"📊 [Stream] Progress: {progress.status.value} - {progress.progress}%")
                yield f"data: {json.dumps(event_data)}\n\n"

            # Get final result from cached stream result (instead of calling generate() again)
            logger.info(f"🔧 [Stream] Getting cached result for session: {session_id}")

            # If we got a session_id from COMPLETED, retrieve the cached result
            if session_id:
                response = service.pop_stream_result(session_id)
                if response:
                    logger.info(f"🔧 [Stream] Retrieved cached response: success={response.success}")
                else:
                    logger.warning(f"⚠️ [Stream] No cached result for session {session_id}")
                    response = None
            else:
                # No session_id means generation failed during streaming
                logger.info(f"🔧 [Stream] No session_id, final status was: {final_status}")
                response = None

            # Handle case where we don't have a cached result
            if response is None:
                if final_status == "failed":
                    logger.error(f"❌ [Stream] Generation failed: {final_message}")
                    # Already yielded FAILED event during streaming, just return
                    return
                else:
                    logger.error(f"❌ [Stream] Unexpected: No cached result and status was {final_status}")
                    yield f"data: {json.dumps({'status': 'failed', 'progress': 0, 'message': 'Internal error: no generation result'})}\n\n"
                    return

            if response.success:
                # Save workflow
                workflow_id = f"workflow_{uuid.uuid4().hex[:12]}"
                import yaml
                workflow_dict = yaml.safe_load(response.workflow_yaml)
                workflow_name = workflow_dict.get("metadata", {}).get("name", workflow_id)

                logger.info(f"✅ [Stream] Saving workflow: {workflow_id} - {workflow_name} for user: {user_id}")
                storage_service.save_workflow(
                    user_id=user_id,
                    workflow_id=workflow_id,
                    workflow_yaml=response.workflow_yaml,
                    workflow_name=workflow_name,
                    source_recording_id=local_recording_id
                )
                logger.info(f"✅ [Stream] Workflow saved to disk")

                # Link recording to workflow (reverse link)
                if local_recording_id:
                    try:
                        storage_service.update_recording_workflow(user_id, local_recording_id, workflow_id)
                        logger.info(f"✅ [Stream] Recording {local_recording_id} linked to Workflow {workflow_id}")
                    except Exception as e:
                        logger.warning(f"⚠️ [Stream] Failed to link recording to workflow: {e}")

                logger.info(f"✅ [Stream] Workflow saved successfully, sending completion event")
                yield f"data: {json.dumps({'status': 'completed', 'progress': 100, 'workflow_id': workflow_id, 'workflow_name': workflow_name, 'message': 'Workflow generated successfully'})}\n\n"
            else:
                logger.error(f"❌ [Stream] Generation failed: {response.error}")
                yield f"data: {json.dumps({'status': 'failed', 'progress': 0, 'message': response.error})}\n\n"

        except Exception as e:
            logger.error(f"❌ [Stream] Exception: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'status': 'failed', 'progress': 0, 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/api/v1/workflow-sessions")
async def create_workflow_session(
    data: dict,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """
    Create a dialogue session for modifying an existing Workflow.

    Body:
        {
            "user_id": "user123",
            "workflow_id": "workflow_abc123",
            "workflow_yaml": "apiVersion: v1\\nkind: Workflow\\n..."
        }

    Returns:
        {
            "session_id": "session_xyz789",
            "success": true
        }
    """
    if not x_ami_api_key:
        raise HTTPException(400, "Missing X-Ami-API-Key header")

    user_id = data.get("user_id")
    workflow_id = data.get("workflow_id")
    workflow_yaml = data.get("workflow_yaml")

    if not user_id:
        raise HTTPException(400, "Missing user_id")
    if not workflow_id:
        raise HTTPException(400, "Missing workflow_id")
    if not workflow_yaml:
        raise HTTPException(400, "Missing workflow_yaml")

    try:
        from src.cloud_backend.intent_builder.agents.workflow_builder import WorkflowModificationSession
        import uuid

        session_id = str(uuid.uuid4())

        # Create WorkflowModificationSession
        session = WorkflowModificationSession(
            workflow_yaml=workflow_yaml,
            config_service=config_service,
            api_key=x_ami_api_key,
            base_url=config_service.get("llm.proxy_url"),
            session_id=session_id
        )

        # Connect the session
        await session._connect()

        # Store session reference
        _workflow_sessions[session_id] = {
            "session": session,
            "user_id": user_id,
            "workflow_id": workflow_id,
            "created_at": datetime.now().isoformat()
        }

        logger.info(f"✅ Workflow modification session created: {session_id}")

        return {
            "session_id": session_id,
            "success": True
        }

    except Exception as e:
        logger.error(f"❌ Failed to create workflow session: {e}")
        raise HTTPException(500, f"Failed to create session: {str(e)}")


@app.post("/api/v1/workflow-sessions/{session_id}/chat")
async def workflow_session_chat(
    session_id: str,
    data: dict,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """
    Chat with a workflow modification session (SSE stream).

    Body:
        {"message": "把第3步改成抓取更多字段"}

    Returns SSE stream with events:
        data: {"type": "text", "content": "..."}
        data: {"type": "workflow_updated", "workflow_yaml": "..."}
        data: {"type": "complete", "message": "...", "workflow_yaml": "..."}
    """
    logger.info(f"🔄 [chat endpoint] Received chat request for session {session_id}")

    if session_id not in _workflow_sessions:
        logger.error(f"❌ [chat endpoint] Session not found: {session_id}")
        raise HTTPException(404, f"Session not found: {session_id}")

    message = data.get("message")
    if not message:
        raise HTTPException(400, "Missing message")

    logger.info(f"📝 [chat endpoint] Message: {message[:100]}...")

    session_data = _workflow_sessions[session_id]
    session = session_data["session"]
    user_id = session_data["user_id"]
    workflow_id = session_data["workflow_id"]

    logger.info(f"📋 [chat endpoint] Found session, user={user_id}, workflow={workflow_id}")

    async def event_generator():
        logger.info(f"🚀 [event_generator] Starting to stream events...")
        try:
            workflow_updated = False
            final_yaml = None
            event_count = 0

            logger.info(f"🔄 [event_generator] Calling session.chat_stream()...")
            async for event in session.chat_stream(message):
                event_count += 1
                logger.info(f"📨 [event_generator] Received event #{event_count}: type={event.type}")

                event_data = {
                    "type": event.type,
                    "message": event.message
                }

                if event.workflow_yaml:
                    event_data["workflow_yaml"] = event.workflow_yaml
                    final_yaml = event.workflow_yaml

                if event.type == "workflow_updated":
                    workflow_updated = True

                sse_data = f"data: {json.dumps(event_data)}\n\n"
                logger.info(f"📤 [event_generator] Yielding SSE: {sse_data[:100]}...")
                yield sse_data

            logger.info(f"✅ [event_generator] Stream complete, {event_count} events sent")

            # If workflow was updated, save it
            if workflow_updated and final_yaml:
                try:
                    storage_service.update_workflow_yaml(
                        user_id=user_id,
                        workflow_id=workflow_id,
                        workflow_yaml=final_yaml
                    )
                    logger.info(f"✅ Workflow updated via dialogue: {workflow_id}")
                except Exception as e:
                    logger.error(f"Failed to save updated workflow: {e}")

        except Exception as e:
            logger.error(f"❌ Workflow chat stream error: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    logger.info(f"📤 [chat endpoint] Returning StreamingResponse...")
    return StreamingResponse(
        event_generator(),
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
    """
    Close a workflow modification session.
    """
    if session_id not in _workflow_sessions:
        raise HTTPException(404, f"Session not found: {session_id}")

    session_data = _workflow_sessions[session_id]
    session = session_data["session"]

    try:
        await session._disconnect()
    except Exception as e:
        logger.warning(f"Error disconnecting session: {e}")

    del _workflow_sessions[session_id]
    logger.info(f"✅ Workflow session closed: {session_id}")

    return {"success": True}


# ===== Executions API =====

@app.post("/api/v1/executions/report")
async def report_execution(data: dict):
    """
    上报执行统计

    Body:
        {
            "workflow_name": "...",
            "status": "success|failed",
            "duration": 12.5,
            "error": "..."
        }
    """
    workflow_name = data.get("workflow_name")
    status = data.get("status")

    # TODO: 保存到数据库

    logger.info(f"Execution reported: {workflow_name} - {status}")
    return {"success": True}


# ===== Workflow Logs API =====

@app.post("/api/v1/logs/workflow")
async def upload_workflow_log(data: dict, x_ami_api_key: Optional[str] = Header(None)):
    """
    Upload workflow execution log from client.

    This endpoint receives detailed execution logs including step-by-step
    actions, timing, and results for analysis and debugging.

    Body:
        {
            "type": "workflow_run",
            "run_id": "uuid",
            "user_id": "user123",
            "device_id": "device_xxx",
            "workflow_id": "workflow_name",
            "workflow_name": "Workflow Display Name",
            "meta": {
                "run_id": "uuid",
                "workflow_id": "...",
                "workflow_name": "...",
                "user_id": "...",
                "device_id": "...",
                "app_version": "0.0.1",
                "started_at": "2024-01-01T00:00:00Z",
                "finished_at": "2024-01-01T00:01:00Z",
                "status": "completed|failed",
                "error_summary": null,
                "steps_total": 5,
                "steps_completed": 5,
                "uploaded": false
            },
            "logs": [
                {
                    "ts": "2024-01-01T00:00:01Z",
                    "step": 0,
                    "action": "navigate",
                    "target": "https://example.com",
                    "status": "completed",
                    "duration_ms": 1500,
                    "message": "Step 1: Navigate to page"
                }
            ],
            "workflow_yaml": "name: ...\nsteps: ...",
            "device_info": {
                "os": "Darwin",
                "os_version": "23.0.0",
                "app_version": "0.0.1"
            }
        }

    Headers:
        X-Ami-API-Key: User's API key (optional but recommended)

    Returns:
        {"success": true, "run_id": "uuid"}
    """
    run_id = data.get("run_id")
    user_id = data.get("user_id")
    workflow_id = data.get("workflow_id")
    workflow_name = data.get("workflow_name")
    meta = data.get("meta", {})
    logs = data.get("logs", [])
    device_info = data.get("device_info", {})

    if not user_id:
        raise HTTPException(400, "Missing user_id")
    if not run_id:
        raise HTTPException(400, "Missing run_id")
    if not workflow_id:
        raise HTTPException(400, "Missing workflow_id")

    try:
        # Store the execution log
        log_path = storage_service.get_user_workflow_logs_path(user_id, workflow_id)
        log_path.mkdir(parents=True, exist_ok=True)

        # Save log file as {run_id}.json
        log_file = log_path / f"{run_id}.json"
        log_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))

        logger.info(
            f"Workflow log uploaded: {run_id} "
            f"(workflow={workflow_name}, status={meta.get('status')}, "
            f"steps={meta.get('steps_completed')}/{meta.get('steps_total')})"
        )

        return {
            "success": True,
            "run_id": run_id,
            "message": "Workflow log uploaded successfully"
        }

    except Exception as e:
        logger.error(f"Failed to save workflow log: {e}")
        raise HTTPException(500, f"Failed to save log: {str(e)}")


@app.post("/api/v1/logs/diagnostic")
async def upload_diagnostic_log(data: dict, x_ami_api_key: Optional[str] = Header(None)):
    """
    Upload diagnostic package from client.

    This endpoint receives diagnostic packages containing system logs,
    recent workflow executions, and device information for debugging.

    Body:
        {
            "type": "diagnostic",
            "diagnostic_id": "DIAG-20250115-ABC123",
            "user_id": "user123",
            "device_id": "device_xxx",
            "app_version": "0.0.1",
            "timestamp": "2024-01-15T10:30:00Z",
            "system_logs": ["line1", "line2", ...],
            "recent_executions": [...],
            "device_info": {...},
            "user_description": "Optional description of the issue"
        }

    Headers:
        X-Ami-API-Key: User's API key (optional but recommended)

    Returns:
        {"success": true, "diagnostic_id": "DIAG-..."}
    """
    diagnostic_id = data.get("diagnostic_id")
    user_id = data.get("user_id")
    device_id = data.get("device_id")
    timestamp = data.get("timestamp")

    if not user_id:
        raise HTTPException(400, "Missing user_id")
    if not diagnostic_id:
        raise HTTPException(400, "Missing diagnostic_id")

    try:
        # Store the diagnostic package
        diag_path = storage_service.base_path / "diagnostics" / user_id
        diag_path.mkdir(parents=True, exist_ok=True)

        # Save diagnostic file
        diag_file = diag_path / f"{diagnostic_id}.json"
        diag_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))

        logger.info(
            f"Diagnostic uploaded: {diagnostic_id} "
            f"(user={user_id}, device={device_id}, "
            f"logs={len(data.get('system_logs', []))} lines, "
            f"executions={len(data.get('recent_executions', []))})"
        )

        return {
            "success": True,
            "diagnostic_id": diagnostic_id,
            "message": "Diagnostic package received successfully"
        }

    except Exception as e:
        logger.error(f"Failed to save diagnostic: {e}")
        raise HTTPException(500, f"Failed to save diagnostic: {str(e)}")


# ===== Intent Builder Agent API (SSE Streaming) =====

# Store active agent sessions
_agent_sessions: dict = {}


@app.post("/api/v1/intent-builder/sessions")
async def start_intent_builder_session(data: dict, x_ami_api_key: Optional[str] = Header(None)):
    """
    Start a new Intent Builder Agent session for Workflow modification

    Body:
        {
            "user_id": "user123",
            "user_query": "Create a workflow to scrape products",
            "task_description": "Optional additional context",
            "user_operations_path": "Optional path to operations JSON",
            "intent_graph_path": "Optional path to intent graph",
            "workflow_id": "Optional Workflow ID being modified",
            "current_workflow_yaml": "Optional current Workflow content"
        }

    Headers:
        X-Ami-API-Key: User's API key (required)

    Returns:
        {"session_id": "..."}
    """
    if not x_ami_api_key:
        raise HTTPException(400, "Missing X-Ami-API-Key header")

    user_id = data.get("user_id")
    user_query = data.get("user_query")
    task_description = data.get("task_description")
    user_operations_path = data.get("user_operations_path")
    intent_graph_path = data.get("intent_graph_path")
    workflow_id = data.get("workflow_id")  # For modification mode
    current_workflow_yaml = data.get("current_workflow_yaml")

    if not user_id:
        raise HTTPException(400, "Missing user_id")
    if not user_query:
        raise HTTPException(400, "Missing user_query")

    # Create session ID
    session_id = f"ib_{uuid.uuid4().hex[:12]}"

    # Get working directory for this session
    working_dir = storage_service.get_user_intent_builder_path(user_id, session_id)

    # Save session metadata for Agent to use
    session_metadata = {
        "user_id": user_id,
        "session_id": session_id
    }
    if workflow_id:
        session_metadata["workflow_id"] = workflow_id

    metadata_path = working_dir / "session_metadata.json"
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(session_metadata, f, indent=2)
    logger.info(f"Saved session metadata to {metadata_path}")

    # Write current Workflow to working directory so Agent can read it
    if current_workflow_yaml:
        workflow_path = working_dir / "workflow.yaml"
        with open(workflow_path, 'w', encoding='utf-8') as f:
            f.write(current_workflow_yaml)
        logger.info(f"Wrote current Workflow to {workflow_path}")

    # Build enhanced query with context
    enhanced_query = user_query
    if current_workflow_yaml:
        enhanced_query = f"""You are modifying an existing Workflow.

The current Workflow is saved at: {working_dir}/workflow.yaml

User's modification request: {user_query}

Please:
1. Read the current workflow.yaml
2. Understand its structure
3. Make the requested modifications
4. Write the updated workflow.yaml
5. Explain what you changed"""

    # Create agent instance
    from src.cloud_backend.intent_builder.agent import IntentBuilderAgent

    agent = IntentBuilderAgent(
        working_dir=str(working_dir),
        user_operations_path=user_operations_path,
        intent_graph_path=intent_graph_path,
        user_api_key=x_ami_api_key,
        config_service=config_service
    )

    # Store session
    _agent_sessions[session_id] = {
        "agent": agent,
        "user_id": user_id,
        "user_query": enhanced_query,
        "task_description": task_description,
        "created_at": asyncio.get_event_loop().time()
    }

    logger.info(f"Intent Builder session started: {session_id} for user {user_id}")

    return {"session_id": session_id}


@app.get("/api/v1/intent-builder/sessions/{session_id}/stream")
async def stream_intent_builder_start(session_id: str):
    """
    Stream the initial response from Intent Builder Agent (SSE)

    This endpoint starts the agent and streams events as SSE.

    Returns:
        SSE stream with events:
        - {"type": "text", "content": "..."}
        - {"type": "tool_use", "tool_name": "Read", "tool_input": {...}}
        - {"type": "tool_result", "content": "..."}
        - {"type": "complete", "result": {...}}
        - {"type": "error", "content": "..."}
    """
    if session_id not in _agent_sessions:
        raise HTTPException(404, f"Session not found: {session_id}")

    session = _agent_sessions[session_id]
    agent = session["agent"]
    user_query = session["user_query"]
    task_description = session.get("task_description")

    async def event_generator():
        try:
            async for event in agent.start_stream(user_query, task_description):
                # Format as SSE
                event_data = json.dumps(event.to_dict(), ensure_ascii=False)
                yield f"data: {event_data}\n\n"
        except Exception as e:
            logger.error(f"Error in stream: {e}")
            error_event = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@app.post("/api/v1/intent-builder/sessions/{session_id}/chat")
async def stream_intent_builder_chat(session_id: str, data: dict):
    """
    Send a message and stream the response (SSE)

    Body:
        {"message": "Add a scroll step before extraction"}

    Returns:
        SSE stream with events
    """
    if session_id not in _agent_sessions:
        raise HTTPException(404, f"Session not found: {session_id}")

    message = data.get("message")
    if not message:
        raise HTTPException(400, "Missing message")

    session = _agent_sessions[session_id]
    agent = session["agent"]

    async def event_generator():
        try:
            async for event in agent.chat_stream(message):
                event_data = json.dumps(event.to_dict(), ensure_ascii=False)
                yield f"data: {event_data}\n\n"
        except Exception as e:
            logger.error(f"Error in chat stream: {e}")
            error_event = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/v1/intent-builder/sessions/{session_id}/state")
async def get_intent_builder_state(session_id: str):
    """
    Get current state of Intent Builder session

    Returns:
        {
            "workflow_path": "...",
            "message_count": int
        }
    """
    if session_id not in _agent_sessions:
        raise HTTPException(404, f"Session not found: {session_id}")

    session = _agent_sessions[session_id]
    agent = session["agent"]

    return agent.get_state()


@app.get("/api/v1/intent-builder/sessions/{session_id}/status")
async def get_session_status(session_id: str, user_id: str):
    """
    Get session status from filesystem (age, expiry time, etc.)

    Query params:
        user_id: User ID

    Returns:
        {
            "session_id": "...",
            "user_id": "...",
            "working_dir": "...",
            "last_active_at": "2025-11-28T10:25:00Z",
            "age_minutes": 15.5,
            "minutes_until_expiry": 14.5,
            "status": "active" | "expired"
        }
    """
    if not user_id:
        raise HTTPException(400, "Missing user_id query parameter")

    # Get session timeout from config
    session_timeout = config_service.get("session.timeout_minutes", 30)

    # Get session info from storage service
    session_info = storage_service.get_session_info(user_id, session_id, session_timeout)

    if not session_info:
        raise HTTPException(404, f"Session not found: {session_id}")

    return session_info


@app.delete("/api/v1/intent-builder/sessions/{session_id}")
async def close_intent_builder_session(session_id: str):
    """
    Close and cleanup Intent Builder session
    """
    if session_id not in _agent_sessions:
        raise HTTPException(404, f"Session not found: {session_id}")

    session = _agent_sessions[session_id]
    agent = session["agent"]

    # Disconnect agent
    await agent.disconnect()

    # Remove from sessions
    del _agent_sessions[session_id]

    logger.info(f"Intent Builder session closed: {session_id}")

    return {"success": True}


# ===== Workflow Resource Sync API =====

# ============================================================================
# Workflow Resource Sync APIs (Simple File CRUD)
# ============================================================================

@app.get("/api/v1/workflows/{workflow_id}/metadata")
async def get_workflow_metadata(workflow_id: str, user_id: str):
    """
    Get workflow metadata from cloud storage

    Returns:
        metadata.json content
    """
    try:
        metadata = await storage_service.get_workflow_metadata(user_id, workflow_id)
        if not metadata:
            raise HTTPException(status_code=404, detail=f"Metadata not found for workflow {workflow_id}")
        return metadata
    except Exception as e:
        logger.error(f"Failed to get metadata for {workflow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/v1/workflows/{workflow_id}/metadata")
async def save_workflow_metadata(workflow_id: str, user_id: str, metadata: dict):
    """
    Save workflow metadata to cloud storage

    Body: metadata.json content (JSON)

    Returns:
        {"success": true}
    """
    try:
        success = await storage_service.save_workflow_metadata(user_id, workflow_id, metadata)
        return {"success": success}
    except Exception as e:
        logger.error(f"Failed to save metadata for {workflow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/workflows/{workflow_id}/files")
async def get_workflow_file(workflow_id: str, user_id: str, path: str):
    """
    Get a single file from workflow

    Args:
        path: Relative path like "extract-daily-link/scraper_script_922ed7ac/extraction_script.py"

    Returns:
        File bytes (binary)
    """
    try:
        workflow_path = storage_service.get_workflow_path(user_id, workflow_id)
        file_path = workflow_path / path

        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {path}")

        # Security: Ensure file is within workflow directory
        if not str(file_path.resolve()).startswith(str(workflow_path.resolve())):
            raise HTTPException(status_code=403, detail="Access denied")

        return FileResponse(file_path)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get file {path} for {workflow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/v1/workflows/{workflow_id}/files")
async def save_workflow_file(
    workflow_id: str,
    user_id: str,
    path: str,
    file: UploadFile
):
    """
    Save a single file to workflow

    Args:
        path: Relative path like "extract-daily-link/scraper_script_922ed7ac/extraction_script.py"
        file: File upload (multipart/form-data)

    Returns:
        {"success": true, "size": 12345}
    """
    try:
        workflow_path = storage_service.get_workflow_path(user_id, workflow_id)
        file_path = workflow_path / path

        # Security: Ensure file is within workflow directory
        if not str(file_path.resolve()).startswith(str(workflow_path.resolve())):
            raise HTTPException(status_code=403, detail="Access denied")

        # Create parent directory
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Read and save file
        content = await file.read()
        file_path.write_bytes(content)

        logger.info(f"Saved file {path} ({len(content)} bytes) for {workflow_id}")

        return {"success": True, "size": len(content)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save file {path} for {workflow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    # Load config to get server settings
    from core.config_service import CloudConfigService
    temp_config = CloudConfigService()

    uvicorn.run(
        "main:app",
        host=temp_config.get("server.host", "0.0.0.0"),
        port=temp_config.get("server.port", 9000),
        reload=temp_config.get("server.reload", False),
        log_level=temp_config.get("logging.level", "info").lower()
    )
