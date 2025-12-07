"""
Ami Cloud Backend - 服务器端数据处理和 AI 分析中心

运行在服务器上，使用：
- 服务器本地文件系统（/var/lib/ami/ 或 ~/ami-server/）
- 本地 PostgreSQL 数据库
- LLM API（Anthropic Claude / OpenAI GPT）

职责：
1. 用户管理（注册、登录、Token 管理）
2. 录制数据处理（接收、存储到服务器文件系统）
3. AI 分析（Intent 提取、MetaFlow 生成、Workflow 生成）
4. Workflow 管理（存储到服务器文件系统、提供下载）
5. 统计分析（执行上报、成功率分析）
"""

import uvicorn
import logging
import sys
import uuid
import asyncio
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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
workflow_generation_service = None

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

@app.on_event("startup")
async def startup_event():
    """Startup initialization"""
    global storage_service, workflow_generation_service

    print("\n" + "="*80)
    print("☁️  Ami Cloud Backend Starting...")
    print("="*80)
    print(f"📝 Config: {config_service.config_path}")

    try:
        from services.storage_service import StorageService
        from services.workflow_generation_service import WorkflowGenerationService

        # 1. CORS already configured
        print(f"✅ CORS: {len(cors_origins)} allowed origins")

        # 2. Initialize storage service
        storage_base_path = config_service.get_storage_path()
        storage_service = StorageService(base_path=str(storage_base_path))
        print(f"✅ Storage: {storage_service.base_path}")

        # 3. Initialize Workflow Generation Service
        llm_provider = config_service.get("llm.default_provider", "anthropic")
        workflow_generation_service = WorkflowGenerationService(
            llm_provider_name=llm_provider,
            config_service=config_service
        )
        print(f"✅ Workflow Generation ({llm_provider})")

        # 4. Setup logging
        log_level = config_service.get("logging.level", "INFO")
        logging.basicConfig(
            level=getattr(logging, log_level),
            format=config_service.get("logging.format", "%(asctime)s [%(levelname)8s] %(message)s")
        )
        print(f"✅ Logging: {log_level}")

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

# ===== Auth API =====

@app.post("/api/auth/login")
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

@app.post("/api/auth/register")
async def register(data: dict):
    """
    用户注册
    
    Body:
        {"username": "...", "email": "...", "password": "..."}
    """
    # TODO: 实现注册逻辑
    return {"success": True, "user_id": data.get("username")}

# ===== Recordings API =====

@app.post("/api/recordings/upload")
async def upload_recording(data: dict):
    """
    Upload recording and add intents to user's Intent Memory Graph (async)

    Body:
        {
            "user_id": "user123",
            "task_description": "Search for coffee on Google",  # User's description of what they did
            "operations": [...]
        }

    Returns:
        {"recording_id": "..."}

    Note: Intent extraction happens in background. Graph is updated asynchronously.
    """
    user_id = data.get("user_id")
    task_description = data.get("task_description", "")
    user_query = data.get("user_query")
    operations = data.get("operations", [])
    # Allow client to provide recording_id (e.g., App Backend's session_id)
    recording_id = data.get("recording_id") or str(uuid.uuid4())

    if not user_id:
        raise HTTPException(400, "Missing user_id")

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
            task_description
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
    task_description: str
):
    """Background task: Extract intents from operations and add to user's Intent Graph"""
    try:
        logger.info(f"🔄 Background: Adding intents from recording {recording_id} to user {user_id}'s graph")
        if task_description:
            logger.info(f"   Task description: {task_description}")

        # Get user's Intent Graph file path
        graph_filepath = storage_service.get_user_intent_graph_path(user_id)

        # Extract intents and add to graph (with task_description)
        new_intents_count = await workflow_generation_service.add_intents_to_graph(
            operations=operations,
            graph_filepath=graph_filepath,
            task_description=task_description
        )

        logger.info(f"✅ Background: Added {new_intents_count} intents from recording {recording_id}")

    except Exception as e:
        logger.error(f"❌ Background: Failed to add intents from recording {recording_id}: {e}")
        import traceback
        traceback.print_exc()


@app.post("/api/analyze_recording")
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
    user_id = data.get("user_id", "default_user")

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


@app.post("/api/users/{user_id}/generate_metaflow")
async def generate_metaflow(
    user_id: str,
    data: dict,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """
    Generate MetaFlow from user's Intent Memory Graph

    Headers:
        X-Ami-API-Key: User's Ami API key (optional, for API Proxy)

    Body:
        {
            "task_description": "Search coffee on Google"
        }

    Returns:
        {
            "metaflow_id": "metaflow_xxx",
            "metaflow_yaml": "...",
            "status": "success"
        }
    """
    task_description = data.get("task_description")
    user_query = data.get("user_query")

    if not task_description:
        raise HTTPException(400, "Missing task_description")

    logger.info(f"🚀 [API] Generating MetaFlow for user {user_id}")
    logger.info(f"📝 Task Description: {task_description}")
    if user_query:
        logger.info(f"🎯 User Query: {user_query}")
    else:
        logger.info(f"⚠️  No user_query provided")

    if x_ami_api_key:
        logger.info(f"🔑 Using API Proxy with user key: {x_ami_api_key[:10]}...")

    try:
        # Get user's Intent Graph file path
        graph_filepath = storage_service.get_user_intent_graph_path(user_id)

        # Check if graph exists
        from pathlib import Path
        if not Path(graph_filepath).exists():
            raise HTTPException(404, f"User {user_id} has no Intent Graph yet. Please upload recordings first.")

        # Generate MetaFlow from Intent Graph (use user_query if provided, otherwise fallback to task_description)
        metaflow_yaml = await workflow_generation_service.generate_metaflow_from_graph_file(
            graph_filepath=graph_filepath,
            task_description=task_description,
            user_query=user_query,
            user_api_key=x_ami_api_key
        )

        # Generate metaflow_id
        metaflow_id = f"metaflow_{uuid.uuid4().hex[:12]}"

        # Save MetaFlow to server filesystem (from Intent Graph, no specific recording)
        storage_service.save_metaflow(
            user_id=user_id,
            metaflow_id=metaflow_id,
            metaflow_yaml=metaflow_yaml,
            user_query=user_query or task_description,
            recording_id=None,  # 从Intent Graph生成，没有特定的recording
            source_type="from_intent_graph"
        )

        logger.info(f"✅ MetaFlow generated and saved: {metaflow_id}")

        return {
            "metaflow_id": metaflow_id,
            "metaflow_yaml": metaflow_yaml,
            "user_query": user_query or task_description,
            "status": "success"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ MetaFlow generation failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"MetaFlow generation failed: {str(e)}")


@app.post("/api/recordings/{recording_id}/generate_metaflow")
async def generate_metaflow_from_recording(
    recording_id: str,
    data: dict,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """
    Generate MetaFlow from a specific recording (using only that recording's intents)

    This endpoint generates MetaFlow using ONLY the intents extracted from this recording,
    NOT from the user's global Intent Memory Graph. This is useful when the user wants
    to create a workflow based on a specific demonstration.

    Overwrite Mode (1 Recording → 1 MetaFlow):
    - If recording already has a MetaFlow, it will be DELETED and replaced with a new one
    - This implements the requirement: "1 Recording → 1 MetaFlow (Overwrite on Regeneration)"

    Headers:
        X-Ami-API-Key: User's Ami API key (optional, for API Proxy)

    Body:
        {
            "user_id": "user123",
            "task_description": "Search coffee on Google"
        }

    Returns:
        {
            "metaflow_id": "metaflow_xxx",
            "metaflow_yaml": "...",
            "status": "success",
            "old_metaflow_id": "metaflow_old" (if overwrite happened)
        }
    """
    user_id = data.get("user_id")
    task_description = data.get("task_description")
    user_query = data.get("user_query")

    if not user_id:
        raise HTTPException(400, "Missing user_id")
    if not task_description:
        raise HTTPException(400, "Missing task_description")

    logger.info(f"🚀 [API] Generating MetaFlow from recording {recording_id}")
    logger.info(f"👤 User: {user_id}")

    if x_ami_api_key:
        logger.info(f"🔑 Using API Proxy with user key: {x_ami_api_key[:10]}...")

    try:
        # Load recording data
        recording_data = storage_service.get_recording(user_id, recording_id)
        if not recording_data:
            raise HTTPException(404, f"Recording not found: {recording_id}")

        operations = recording_data.get("operations", [])
        if not operations:
            raise HTTPException(400, f"Recording {recording_id} has no operations")

        # Check if recording already has a MetaFlow (for overwrite mode)
        old_metaflow_id = recording_data.get("metaflow_id")
        if old_metaflow_id:
            logger.info(f"⚠️  Recording already has MetaFlow: {old_metaflow_id}")
            logger.info(f"🗑️  Deleting old MetaFlow (overwrite mode)...")
            storage_service.delete_metaflow(user_id, old_metaflow_id)
            logger.info(f"✅ Old MetaFlow deleted: {old_metaflow_id}")
        else:
            logger.info(f"✨ First time generating MetaFlow for this recording")

        # Try to get user_query from recording if not provided in request
        if not user_query:
            user_query = recording_data.get("user_query")
            if user_query:
                logger.info(f"📖 Using user_query from recording data")

        logger.info(f"📹 Recording loaded: {len(operations)} operations")
        logger.info(f"📝 Task Description: {task_description}")
        if user_query:
            logger.info(f"🎯 User Query: {user_query}")
        else:
            logger.info(f"⚠️  No user_query available")

        # Generate MetaFlow from recording operations only (use user_query if available)
        metaflow_yaml = await workflow_generation_service.generate_metaflow_from_recording(
            operations=operations,
            task_description=task_description,
            user_query=user_query,
            user_api_key=x_ami_api_key
        )

        # Generate new metaflow_id
        metaflow_id = f"metaflow_{uuid.uuid4().hex[:12]}"

        # Save MetaFlow to server filesystem with source recording info
        storage_service.save_metaflow(
            user_id=user_id,
            metaflow_id=metaflow_id,
            metaflow_yaml=metaflow_yaml,
            user_query=user_query or task_description,
            recording_id=recording_id,
            source_type="from_recording"
        )

        # Establish Recording → MetaFlow relationship (update to new metaflow_id)
        storage_service.update_recording_metaflow(user_id, recording_id, metaflow_id)

        logger.info(f"✅ MetaFlow generated and saved: {metaflow_id}")
        logger.info(f"✅ Recording {recording_id} linked to MetaFlow {metaflow_id}")

        result = {
            "metaflow_id": metaflow_id,
            "metaflow_yaml": metaflow_yaml,
            "user_query": user_query or task_description,
            "source_recording_id": recording_id,
            "source_type": "from_recording",
            "status": "success"
        }

        # Include old_metaflow_id if overwrite happened
        if old_metaflow_id:
            result["old_metaflow_id"] = old_metaflow_id
            result["message"] = "Old MetaFlow deleted, new one generated (overwrite mode)"
            logger.info(f"📋 Overwrite completed: {old_metaflow_id} → {metaflow_id}")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ MetaFlow generation from recording failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"MetaFlow generation failed: {str(e)}")


@app.post("/api/metaflows/{metaflow_id}/generate_workflow")
async def generate_workflow_from_metaflow(
    metaflow_id: str,
    data: dict,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """
    Generate Workflow YAML from MetaFlow

    Note: MetaFlow modifications are now saved in real-time by Intent Builder Agent,
    so this endpoint only needs to generate Workflow from the current MetaFlow.

    Headers:
        X-Ami-API-Key: User's Ami API key (optional, for API Proxy)

    Body:
        {
            "user_id": "user123",
            "session_id": "ib_xxx123"  // Optional: Agent session ID for cleanup
        }

    Returns:
        {
            "workflow_name": "workflow_xxx",
            "status": "success"
        }
    """
    user_id = data.get("user_id")
    session_id = data.get("session_id")  # Optional: Agent session ID for cleanup

    if not user_id:
        raise HTTPException(400, "Missing user_id")

    if x_ami_api_key:
        logger.info(f"🔑 Using API Proxy with user key: {x_ami_api_key[:10]}...")

    # Clean up Agent session directory if provided
    if session_id:
        logger.info(f"🗑️  Cleaning up Agent session: {session_id}")
        working_dir = storage_service.get_user_intent_builder_path(user_id, session_id)

        if working_dir.exists():
            import shutil
            try:
                shutil.rmtree(working_dir)
                logger.info(f"✅ Agent session directory cleaned up: {session_id}")
            except Exception as e:
                logger.warning(f"Failed to cleanup session directory: {e}")
        else:
            logger.info(f"⚠️  Session directory does not exist: {working_dir}")

    # Load MetaFlow data (now updated if Agent modified it)
    metaflow_data = storage_service.get_metaflow(user_id, metaflow_id)
    if not metaflow_data:
        raise HTTPException(404, f"MetaFlow not found: {metaflow_id}")

    metaflow_yaml = metaflow_data.get("metaflow_yaml")
    user_query = metaflow_data.get("user_query", "")

    logger.info(f"🚀 [API] Generating Workflow from MetaFlow: {metaflow_id}")
    logger.info(f"👤 User: {user_id}")
    if user_query:
        logger.info(f"🎯 User Query: {user_query}")

    # Log the MetaFlow that will be used for Workflow generation
    logger.info(f"📏 MetaFlow length for Workflow generation: {len(metaflow_yaml)} characters")
    logger.info(f"📄 MetaFlow FULL CONTENT for Workflow generation:\n{metaflow_yaml}")

    try:
        # Generate Workflow from MetaFlow
        logger.info(f"⚙️  Calling workflow_generation_service.generate_workflow_from_metaflow()...")
        workflow_yaml = await workflow_generation_service.generate_workflow_from_metaflow(
            metaflow_yaml=metaflow_yaml,
            user_api_key=x_ami_api_key
        )
        logger.info(f"✅ Workflow generation completed, length: {len(workflow_yaml)} characters")

        # Extract workflow_name from YAML
        import yaml
        workflow_dict = yaml.safe_load(workflow_yaml)
        workflow_name = workflow_dict.get("name", f"workflow_{uuid.uuid4().hex[:12]}")

        # Get source recording ID from metaflow metadata for reverse traceability
        source_recording_id = metaflow_data.get("source_recording_id")
        if source_recording_id:
            logger.info(f"📋 Source recording for traceability: {source_recording_id}")

        # Generate workflow_id
        workflow_id = f"workflow_{uuid.uuid4().hex[:12]}"

        # Save Workflow to server filesystem with source metaflow info
        storage_service.save_workflow(
            user_id=user_id,
            workflow_id=workflow_id,
            workflow_yaml=workflow_yaml,
            workflow_name=workflow_name,
            metaflow_id=metaflow_id,
            source_recording_id=source_recording_id
        )

        # Establish MetaFlow → Workflow relationship
        storage_service.update_metaflow_workflow(user_id, metaflow_id, workflow_id)

        logger.info(f"✅ Workflow generated and saved: {workflow_id} ({workflow_name})")
        logger.info(f"✅ MetaFlow {metaflow_id} linked to Workflow {workflow_id}")

        return {
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "workflow_yaml": workflow_yaml,
            "source_metaflow_id": metaflow_id,  # 返回来源metaflow信息
            "source_recording_id": source_recording_id,  # 返回原始recording信息
            "status": "success"
        }

    except Exception as e:
        logger.error(f"❌ Workflow generation failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Workflow generation failed: {str(e)}")


# ===== Recordings API (List/Detail) =====

@app.get("/api/recordings")
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


@app.get("/api/recordings/{recording_id}")
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


# ===== MetaFlows API =====

@app.get("/api/metaflows")
async def list_metaflows(user_id: str):
    """
    List all MetaFlows for user

    Query:
        user_id: User ID

    Returns:
        [{"metaflow_id": "...", "user_query": "...", "workflow_id": "...", "created_at": "..."}, ...]
    """
    if not user_id:
        raise HTTPException(400, "Missing user_id")

    metaflows = storage_service.list_metaflows(user_id)
    return metaflows


@app.get("/api/metaflows/{metaflow_id}")
async def get_metaflow(metaflow_id: str, user_id: str):
    """
    Get MetaFlow detail

    Query:
        user_id: User ID

    Returns:
        {
            "metaflow_id": "...",
            "metaflow_yaml": "...",
            "user_query": "...",
            "workflow_id": "...",
            "created_at": "...",
            "updated_at": "..."
        }
    """
    if not user_id:
        raise HTTPException(400, "Missing user_id")

    metaflow = storage_service.get_metaflow(user_id, metaflow_id)
    if not metaflow:
        raise HTTPException(404, f"MetaFlow not found: {metaflow_id}")

    return metaflow


@app.put("/api/metaflows/{metaflow_id}")
async def update_metaflow(metaflow_id: str, data: dict):
    """
    Update MetaFlow YAML content

    Body:
        {
            "user_id": "user123",
            "metaflow_yaml": "..."
        }

    Returns:
        {"success": true}
    """
    user_id = data.get("user_id")
    metaflow_yaml = data.get("metaflow_yaml")

    if not user_id:
        raise HTTPException(400, "Missing user_id")
    if not metaflow_yaml:
        raise HTTPException(400, "Missing metaflow_yaml")

    # Check if MetaFlow exists
    existing = storage_service.get_metaflow(user_id, metaflow_id)
    if not existing:
        raise HTTPException(404, f"MetaFlow not found: {metaflow_id}")

    storage_service.update_metaflow_yaml(user_id, metaflow_id, metaflow_yaml)
    logger.info(f"MetaFlow updated via API: {metaflow_id}")

    return {"success": True}


# ===== Workflows API =====

@app.get("/api/workflows")
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


@app.get("/api/users/{user_id}/workflows")
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


@app.get("/api/workflows/{workflow_id}")
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


@app.put("/api/workflows/{workflow_id}")
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


@app.get("/api/workflows/{workflow_id}/download")
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


@app.delete("/api/workflows/{workflow_id}")
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

# ===== Executions API =====

@app.post("/api/executions/report")
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


# ===== Intent Builder Agent API (SSE Streaming) =====

# Store active agent sessions
_agent_sessions: dict = {}


@app.post("/api/intent-builder/start")
async def start_intent_builder_session(data: dict, x_ami_api_key: Optional[str] = Header(None)):
    """
    Start a new Intent Builder Agent session

    Body:
        {
            "user_id": "user123",
            "user_query": "Create a workflow to scrape products",
            "task_description": "Optional additional context",
            "user_operations_path": "Optional path to operations JSON",
            "intent_graph_path": "Optional path to intent graph",
            "metaflow_id": "Optional MetaFlow ID being modified",
            "workflow_id": "Optional Workflow ID being modified",
            "current_metaflow_yaml": "Optional current MetaFlow content",
            "current_workflow_yaml": "Optional current Workflow content",
            "phase": "metaflow or workflow"
        }

    Headers:
        X-Ami-API-Key: User's API key (required)

    Returns:
        {"session_id": "..."}
    """
    if not x_ami_api_key:
        raise HTTPException(400, "Missing X-Ami-API-Key header")

    user_id = data.get("user_id", "default_user")
    user_query = data.get("user_query")
    task_description = data.get("task_description")
    user_operations_path = data.get("user_operations_path")
    intent_graph_path = data.get("intent_graph_path")
    metaflow_id = data.get("metaflow_id")  # For modification mode
    workflow_id = data.get("workflow_id")  # For modification mode
    current_metaflow_yaml = data.get("current_metaflow_yaml")
    current_workflow_yaml = data.get("current_workflow_yaml")
    phase = data.get("phase", "metaflow")

    if not user_query:
        raise HTTPException(400, "Missing user_query")

    # Create session ID
    session_id = f"ib_{uuid.uuid4().hex[:12]}"

    # Get working directory for this session
    working_dir = storage_service.get_user_intent_builder_path(user_id, session_id)

    # Save session metadata (metaflow_id, workflow_id, etc.) for Agent to use
    session_metadata = {
        "user_id": user_id,
        "session_id": session_id,
        "phase": phase
    }
    if metaflow_id:
        session_metadata["metaflow_id"] = metaflow_id
    if workflow_id:
        session_metadata["workflow_id"] = workflow_id

    metadata_path = working_dir / "session_metadata.json"
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(session_metadata, f, indent=2)
    logger.info(f"Saved session metadata to {metadata_path}")

    # Write current MetaFlow/Workflow to working directory so Agent can read them
    if current_metaflow_yaml:
        metaflow_path = working_dir / "metaflow.yaml"
        with open(metaflow_path, 'w', encoding='utf-8') as f:
            f.write(current_metaflow_yaml)
        logger.info(f"Wrote current MetaFlow to {metaflow_path}")

    if current_workflow_yaml:
        workflow_path = working_dir / "workflow.yaml"
        with open(workflow_path, 'w', encoding='utf-8') as f:
            f.write(current_workflow_yaml)
        logger.info(f"Wrote current Workflow to {workflow_path}")

    # Build enhanced query with context
    enhanced_query = user_query
    if current_metaflow_yaml and phase == "metaflow":
        enhanced_query = f"""You are modifying an existing MetaFlow.

The current MetaFlow is saved at: {working_dir}/metaflow.yaml

User's modification request: {user_query}

Please:
1. Read the current metaflow.yaml
2. Understand its structure
3. Make the requested modifications
4. Write the updated metaflow.yaml
5. Explain what you changed"""

    elif current_workflow_yaml and phase == "workflow":
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
    from src.intent_builder.agent import IntentBuilderAgent

    agent = IntentBuilderAgent(
        working_dir=str(working_dir),
        user_operations_path=user_operations_path,
        intent_graph_path=intent_graph_path,
        user_api_key=x_ami_api_key,
        config_service=config_service
    )

    # Set agent phase
    agent.phase = phase

    # Store session
    _agent_sessions[session_id] = {
        "agent": agent,
        "user_id": user_id,
        "user_query": enhanced_query,
        "task_description": task_description,
        "phase": phase,
        "created_at": asyncio.get_event_loop().time()
    }

    logger.info(f"Intent Builder session started: {session_id} for user {user_id}, phase: {phase}")

    return {"session_id": session_id}


@app.get("/api/intent-builder/{session_id}/stream")
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


@app.post("/api/intent-builder/{session_id}/chat")
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


@app.get("/api/intent-builder/{session_id}/state")
async def get_intent_builder_state(session_id: str):
    """
    Get current state of Intent Builder session

    Returns:
        {
            "phase": "metaflow" or "workflow",
            "metaflow_confirmed": bool,
            "workflow_confirmed": bool,
            "metaflow_path": "...",
            "workflow_path": "...",
            "message_count": int
        }
    """
    if session_id not in _agent_sessions:
        raise HTTPException(404, f"Session not found: {session_id}")

    session = _agent_sessions[session_id]
    agent = session["agent"]

    return agent.get_state()


@app.get("/api/intent-builder/sessions/{session_id}/status")
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


@app.delete("/api/intent-builder/{session_id}")
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
