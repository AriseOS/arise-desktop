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
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import httpx

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
workflow_memory = None  # WorkflowMemory for NL query
reasoner = None  # Reasoner for semantic retrieval

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

                # Run cleanup for Intent Builder sessions
                logger.debug(f"🧹 Running session cleanup...")
                cleaned_count = storage_service.cleanup_expired_sessions(timeout_minutes)

                if cleaned_count > 0:
                    logger.info(f"🧹 Cleaned {cleaned_count} expired Intent Builder sessions")

                # Run cleanup for Workflow Modification sessions (60 min timeout)
                mod_cleaned_count = storage_service.cleanup_expired_modification_sessions(60)

                if mod_cleaned_count > 0:
                    logger.info(f"🧹 Cleaned {mod_cleaned_count} expired Workflow Modification sessions")

                # Also cleanup expired sessions from in-memory _workflow_sessions dict
                expired_session_ids = []
                now = datetime.now()
                for session_id, session_data in _workflow_sessions.items():
                    created_at_str = session_data.get("created_at")
                    if created_at_str:
                        try:
                            created_at = datetime.fromisoformat(created_at_str)
                            if (now - created_at).total_seconds() > 60 * 60:  # 60 min timeout
                                expired_session_ids.append(session_id)
                        except (ValueError, TypeError):
                            pass

                for session_id in expired_session_ids:
                    try:
                        session = _workflow_sessions[session_id].get("session")
                        if session:
                            await session._disconnect()
                    except Exception as e:
                        logger.warning(f"Error disconnecting expired session {session_id}: {e}")
                    del _workflow_sessions[session_id]

                if expired_session_ids:
                    logger.info(f"🧹 Cleaned {len(expired_session_ids)} expired in-memory workflow sessions")

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
    global storage_service, workflow_service, workflow_memory, reasoner

    print("\n" + "="*80)
    print("☁️  Ami Cloud Backend Starting...")
    print("="*80)
    print(f"📝 Config: {config_service.config_path}")

    try:
        from services.storage_service import StorageService
        from src.cloud_backend.intent_builder.services import WorkflowService
        from src.cloud_backend.memgraph.graphstore.networkx_graph import NetworkXGraph
        from src.cloud_backend.memgraph.memory.workflow_memory import WorkflowMemory

        # 1. CORS already configured
        print(f"✅ CORS: {len(cors_origins)} allowed origins")

        # 2. Initialize storage service
        storage_base_path = config_service.get_storage_path()
        storage_service = StorageService(base_path=str(storage_base_path))
        print(f"✅ Storage: {storage_service.base_path}")

        # 3. Initialize WorkflowMemory (for NL query)
        graph_store = NetworkXGraph()
        workflow_memory = WorkflowMemory(graph_store)
        print("✅ Workflow Memory (for NL query)")

        # 3.1 Initialize EmbeddingService (for semantic search) - REQUIRED
        from src.cloud_backend.memgraph.services.embedding_service import EmbeddingService
        embedding_config = config_service.get("embedding", {})
        if not embedding_config:
            print("❌ FATAL: embedding config not found in cloud-backend.yaml")
            print("   Memory features require embedding service to function.")
            import sys
            sys.exit(1)

        EmbeddingService.configure_from_dict(embedding_config)
        if not EmbeddingService.is_available():
            print("❌ FATAL: EmbeddingService not available")
            print("   Check embedding config in cloud-backend.yaml:")
            print("   - api_key: must be set directly, OR")
            print("   - api_key_env: must be a valid environment variable name")
            import sys
            sys.exit(1)

        print(f"✅ Embedding Service: {embedding_config.get('provider', 'openai')} / {embedding_config.get('model', 'unknown')}")

        # 4. Initialize Reasoner (for semantic retrieval)
        # Note: Reasoner requires LLM client which needs user's API key
        # It will be initialized per-request with user's API key
        print("✅ Reasoner (ready for initialization)")

        # 4. Initialize WorkflowService (new architecture using Claude Agent SDK + Skills)
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
    """Upload recording and build State/Action Graph (NO LLM).

    This endpoint:
    1. Builds State/Action Graph using deterministic rules (NO LLM)
    2. Saves recording with graph data
    3. Optionally runs background AI analysis (with LLM) for task description
    4. Optionally adds to workflow memory for semantic search

    Body:
        {
            "user_id": "user123",
            "user_api_key": "ami_xxx...",  # User's Ami API key for LLM calls
            "task_description": "Search for coffee on Google",  # User's description of what they did
            "operations": [...],
            "dom_snapshots": {  # Optional: DOM snapshots captured during recording
                "https://example.com/page1": {...dom_dict...},
                "https://example.com/page2": {...dom_dict...}
            },
            "add_to_memory": true,  # Optional: auto-add to workflow memory (default: true)
            "generate_embeddings": true  # Generate embeddings for semantic search (default: true, required for query)
        }

    Returns:
        {
            "recording_id": "...",
            "graph": {
                "states": {...},
                "edges": [...],
                "phases": [...],
                "episodes": [...]
            },
            "memory": {  # Only if add_to_memory=true
                "states_added": 3,
                "states_merged": 1,
                "intent_sequences_added": 5
            }
        }

    Note: Graph building is deterministic and immediate (no LLM).
          AI analysis happens in background (with LLM).
          Memory addition is synchronous but fast (no LLM unless generate_embeddings=true).
    """
    user_id = data.get("user_id")
    user_api_key = data.get("user_api_key")
    task_description = data.get("task_description", "")
    user_query = data.get("user_query")
    operations = data.get("operations", [])
    dom_snapshots = data.get("dom_snapshots")  # URL -> DOM dict mapping
    # Allow client to provide recording_id (e.g., App Backend's session_id)
    recording_id = data.get("recording_id") or str(uuid.uuid4())
    # Memory options
    add_to_memory = data.get("add_to_memory", True)  # Default: auto-add to memory
    generate_embeddings = data.get("generate_embeddings", True)

    if not user_id:
        raise HTTPException(400, "Missing user_id")

    if not user_api_key:
        raise HTTPException(400, "Missing user_api_key")

    if not operations:
        raise HTTPException(400, "Missing operations")

    # Build State/Action Graph (NO LLM, deterministic)
    logger.info(f"Building graph for recording {recording_id}")
    try:
        from src.cloud_backend.graph_builder import GraphBuilder
        builder = GraphBuilder()
        graph = builder.build(operations)
        graph_dict = graph.to_dict()
        logger.info(f"Graph built: {len(graph.states)} states, {len(graph.edges)} edges")
    except Exception as e:
        logger.error(f"Failed to build graph: {e}")
        import traceback
        traceback.print_exc()
        graph_dict = None

    # Save recording with graph
    file_path = storage_service.save_recording(
        user_id,
        recording_id,
        operations,
        task_description=task_description,
        user_query=user_query,
        dom_snapshots=dom_snapshots,
        graph=graph_dict
    )

    logger.info(f"Recording uploaded: {recording_id} ({len(operations)} ops)")
    if dom_snapshots:
        logger.info(f"  DOM snapshots: {len(dom_snapshots)} URLs")
    if task_description:
        logger.info(f"  Task: {task_description}")
    if user_query:
        logger.info(f"  User query: {user_query}")

    # Add to workflow memory if requested
    memory_result = None
    if add_to_memory and workflow_memory:
        try:
            from src.cloud_backend.memgraph.thinker.workflow_processor import WorkflowProcessor

            # Setup embedding model if requested
            embedding_model = None
            if generate_embeddings and user_api_key:
                from src.cloud_backend.memgraph.services import EmbeddingService
                if EmbeddingService.is_available():
                    embedding_model = EmbeddingService.get_model()

            # Setup LLM providers for description generation (only if embeddings requested)
            llm_provider = None
            simple_llm_provider = None
            if generate_embeddings and user_api_key:
                from src.common.llm import AnthropicProvider
                llm_provider = AnthropicProvider(
                    api_key=user_api_key,
                    model_name=config_service.get("llm.anthropic.model", "claude-sonnet-4-5-20250929"),
                    base_url=config_service.get("llm.proxy_url")
                )
                # Create simple provider if configured
                simple_model = config_service.get("llm.anthropic.simple_model")
                if simple_model:
                    simple_llm_provider = AnthropicProvider(
                        api_key=user_api_key,
                        model_name=simple_model,
                        base_url=config_service.get("llm.proxy_url")
                    )

            # Create processor and process
            processor = WorkflowProcessor(
                llm_provider=llm_provider,
                memory=workflow_memory,
                embedding_model=embedding_model,
                simple_llm_provider=simple_llm_provider,
            )

            result = await processor.process_workflow(
                workflow_data={"operations": operations},
                user_id=user_id,
                session_id=recording_id,
                store_to_memory=True,
            )

            memory_result = {
                "states_added": result.metadata.get("new_states", 0),
                "states_merged": result.metadata.get("reused_states", 0),
                "page_instances_added": len(result.page_instances),
                "intent_sequences_added": len(result.intent_sequences),
                "actions_added": len(result.actions),
            }

            logger.info(f"✅ Added to memory: {memory_result['states_added']} new states, "
                       f"{memory_result['states_merged']} merged")

        except Exception as e:
            logger.warning(f"⚠️ Failed to add to memory: {e}")
            import traceback
            traceback.print_exc()

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

    response = {"recording_id": recording_id}
    if graph_dict:
        response["graph"] = graph_dict
    if memory_result:
        response["memory"] = memory_result

    return response


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


async def _generate_scripts_sync(
    workflow_yaml: str,
    dom_snapshots: Dict[str, Dict],
    workflow_dir: Path,
    api_key: str,
    base_url: Optional[str] = None,
    intents: Optional[List] = None
) -> Dict[str, Any]:
    """Synchronously generate scripts for workflow steps using DOM snapshots.

    This is called during workflow generation to populate the workflow directory
    with cached scripts (find_element.py, extraction_script.py) before returning
    the completed workflow to the user.

    Args:
        workflow_yaml: Workflow YAML content
        dom_snapshots: dom_id -> DOM dict mapping
        workflow_dir: Directory to save scripts
        api_key: Anthropic API key
        base_url: Optional API proxy URL
        intents: List of Intent objects for xpath_hints -> dom_id matching

    Returns:
        Script generation result dict with success, generated, skipped, failed counts
    """
    try:
        from src.cloud_backend.intent_builder.services import ScriptPregenerationService

        service = ScriptPregenerationService(
            config_service=config_service,
            api_key=api_key,
            base_url=base_url
        )

        result = await service.pregenerate_scripts(
            workflow_yaml=workflow_yaml,
            dom_snapshots=dom_snapshots,
            workflow_dir=workflow_dir,
            intents=intents
        )

        return result

    except Exception as e:
        logger.error(f"Script generation error: {e}")
        return {
            "success": False,
            "error": str(e),
            "generated": 0,
            "skipped": 0,
            "failed": 0
        }


async def _pregenerate_scripts_background(
    user_id: str,
    workflow_id: str,
    recording_id: str,
    workflow_yaml: str,
    api_key: str
):
    """Background task: Pre-generate scripts for workflow steps using DOM snapshots from recording

    NOTE: This function is deprecated. Script generation is now done synchronously
    during workflow generation. Keeping for backwards compatibility.

    This task runs after workflow generation to populate the workflow directory
    with cached scripts (find_element.py, extraction_script.py), eliminating
    the need to generate them during first execution.
    """
    try:
        logger.info(f"🔧 Background: Starting script pre-generation for workflow {workflow_id}")

        # Load DOM snapshots from recording
        dom_snapshots = storage_service.get_recording_dom_snapshots(user_id, recording_id)

        if not dom_snapshots:
            logger.info(f"ℹ️ Background: No DOM snapshots found for recording {recording_id}, skipping script pre-generation")
            return

        logger.info(f"📸 Background: Found {len(dom_snapshots)} DOM snapshots for script generation")

        # Get workflow directory
        workflow_dir = storage_service.get_workflow_path(user_id, workflow_id)

        # Create script pre-generation service
        from src.cloud_backend.intent_builder.services import ScriptPregenerationService

        service = ScriptPregenerationService(
            config_service=config_service,
            api_key=api_key,
            base_url=config_service.get("llm.proxy_url")
        )

        # Run script pre-generation
        result = await service.pregenerate_scripts(
            workflow_yaml=workflow_yaml,
            dom_snapshots=dom_snapshots,
            workflow_dir=workflow_dir
        )

        if result["success"]:
            logger.info(f"✅ Background: Script pre-generation complete for workflow {workflow_id}")
            logger.info(f"   Generated: {result['generated']}, Skipped: {result['skipped']}, Failed: {result['failed']}")
        else:
            logger.warning(f"⚠️ Background: Script pre-generation had issues for workflow {workflow_id}")
            logger.warning(f"   Generated: {result['generated']}, Skipped: {result['skipped']}, Failed: {result['failed']}")
            if result.get("error"):
                logger.warning(f"   Error: {result['error']}")

        # Update workflow metadata with script generation status
        try:
            metadata = await storage_service.get_workflow_metadata(user_id, workflow_id)
            if metadata:
                metadata["script_pregeneration"] = {
                    "completed": True,
                    "generated": result["generated"],
                    "skipped": result["skipped"],
                    "failed": result["failed"],
                    "details": result["details"]
                }
                await storage_service.save_workflow_metadata(user_id, workflow_id, metadata)
                logger.info(f"✅ Background: Updated workflow metadata with script generation status")
        except Exception as e:
            logger.warning(f"⚠️ Background: Failed to update workflow metadata: {e}")

    except Exception as e:
        logger.error(f"❌ Background: Script pre-generation failed for workflow {workflow_id}: {e}")
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


@app.patch("/api/v1/recordings/{recording_id}")
async def update_recording_metadata(recording_id: str, user_id: str, data: dict):
    """
    Update recording metadata (for sync from local)

    Query:
        user_id: User ID

    Body:
        {
            "workflow_id": "..." or null,  # Optional
            "task_description": "...",     # Optional
            "user_query": "...",           # Optional
            "updated_at": "..."            # Required for sync
        }
    """
    if not user_id:
        raise HTTPException(400, "Missing user_id")

    recording_path = storage_service._user_path(user_id) / "recordings" / recording_id
    if not recording_path.exists():
        raise HTTPException(404, f"Recording not found: {recording_id}")

    # Update operations.json
    operations_path = recording_path / "operations.json"
    if operations_path.exists():
        with open(operations_path, 'r') as f:
            ops_data = json.load(f)

        if "task_description" in data:
            ops_data["task_description"] = data["task_description"]
        if "user_query" in data:
            ops_data["user_query"] = data["user_query"]
        if "updated_at" in data:
            ops_data["updated_at"] = data["updated_at"]

        with open(operations_path, 'w') as f:
            json.dump(ops_data, f, indent=2, ensure_ascii=False)

    # Update metadata.json for workflow_id
    metadata_path = recording_path / "metadata.json"
    metadata = {}
    if metadata_path.exists():
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)

    if "workflow_id" in data:
        if data["workflow_id"] is None:
            metadata.pop("workflow_id", None)
        else:
            metadata["workflow_id"] = data["workflow_id"]
    if "updated_at" in data:
        metadata["updated_at"] = data["updated_at"]

    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"Recording {recording_id} metadata updated via sync")
    return {"success": True, "message": "Recording metadata updated"}


@app.delete("/api/v1/recordings/{recording_id}")
async def delete_recording(recording_id: str, user_id: str):
    """
    Delete a recording from Cloud Backend

    Query:
        user_id: User ID

    Returns:
        {"success": true, "message": "Recording deleted"}
    """
    if not user_id:
        raise HTTPException(400, "Missing user_id")

    try:
        success = storage_service.delete_recording(user_id, recording_id)

        if not success:
            raise HTTPException(404, f"Recording not found: {recording_id}")

        logger.info(f"Recording {recording_id} deleted for user {user_id}")
        return {"success": True, "message": "Recording deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete recording {recording_id}: {e}")
        raise HTTPException(500, f"Failed to delete recording: {e}")


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


# ===== Memory API =====
# Endpoints for managing user's Workflow Memory (States, Actions, IntentSequences)
# See docs/api/memory-api.md for detailed documentation

@app.post("/api/v1/memory/add")
async def add_to_memory(
    data: dict,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """
    Add Recording to User's Workflow Memory

    This endpoint processes a recording and adds its States, Actions, and IntentSequences
    to the user's workflow memory. Unlike POST /api/v1/recordings, this endpoint focuses
    solely on memory management without storing the recording itself.

    The processing pipeline:
    1. Parse recording operations
    2. Segment by URL (each unique URL becomes a State)
    3. Deduplicate States (same URL reuses existing State)
    4. Create PageInstances for each URL visit
    5. Create IntentSequences from operations within each State
    6. Create Actions for state transitions
    7. Optionally generate embeddings for semantic search

    Headers:
        X-Ami-API-Key: User's API key (required for embedding generation)

    Body:
        {
            "user_id": "user123",                    // Required: User identifier
            "recording_id": "recording_xxx",        // Optional: Load from existing recording
            "operations": [...],                     // Optional: Direct operations array
            "session_id": "session_xxx",            // Optional: Session identifier
            "generate_embeddings": true             // Generate embeddings (default: true, required for query)
        }

    Note: Either recording_id or operations must be provided.

    Returns:
        {
            "success": true,
            "states_added": 3,                      // New States created
            "states_merged": 1,                     // Existing States reused
            "page_instances_added": 4,              // PageInstances created
            "intent_sequences_added": 5,            // IntentSequences created
            "actions_added": 2,                     // Actions created
            "processing_time_ms": 150
        }

    Errors:
        400: Missing user_id, or neither recording_id nor operations provided
        404: Recording not found (when using recording_id)
        500: Processing failed
    """
    import time
    start_time = time.time()

    user_id = data.get("user_id")
    recording_id = data.get("recording_id")
    operations = data.get("operations")
    session_id = data.get("session_id")
    generate_embeddings = data.get("generate_embeddings", True)

    if not user_id:
        raise HTTPException(400, "Missing user_id")

    if not recording_id and not operations:
        raise HTTPException(400, "Either recording_id or operations must be provided")

    # Load operations from recording if recording_id provided
    if recording_id and not operations:
        recording = storage_service.get_recording(user_id, recording_id)
        if not recording:
            raise HTTPException(404, f"Recording not found: {recording_id}")
        operations = recording.get("operations", [])
        if not session_id:
            session_id = recording.get("session_id")

    if not operations:
        raise HTTPException(400, "No operations to process")

    try:
        # Import WorkflowProcessor
        from src.cloud_backend.memgraph.thinker.workflow_processor import WorkflowProcessor

        # Setup embedding model if requested
        embedding_model = None
        if generate_embeddings and x_ami_api_key:
            from src.cloud_backend.memgraph.services import EmbeddingService
            if EmbeddingService.is_available():
                embedding_model = EmbeddingService.get_model()

        # Setup LLM providers for description generation
        llm_provider = None
        simple_llm_provider = None
        if generate_embeddings and x_ami_api_key:
            from src.common.llm import AnthropicProvider
            llm_provider = AnthropicProvider(
                api_key=x_ami_api_key,
                model_name=config_service.get("llm.anthropic.model", "claude-sonnet-4-5-20250929"),
                base_url=config_service.get("llm.proxy_url")
            )
            # Create simple provider if configured
            simple_model = config_service.get("llm.anthropic.simple_model")
            if simple_model:
                simple_llm_provider = AnthropicProvider(
                    api_key=x_ami_api_key,
                    model_name=simple_model,
                    base_url=config_service.get("llm.proxy_url")
                )

        # Create processor
        processor = WorkflowProcessor(
            llm_provider=llm_provider,
            memory=workflow_memory,
            embedding_model=embedding_model,
            simple_llm_provider=simple_llm_provider,
        )

        # Process workflow (async)
        result = await processor.process_workflow(
            workflow_data={"operations": operations},
            user_id=user_id,
            session_id=session_id,
            store_to_memory=True,
        )

        processing_time_ms = int((time.time() - start_time) * 1000)

        logger.info(f"✅ Added to memory for user {user_id}: "
                   f"{result.metadata.get('new_states', 0)} new states, "
                   f"{result.metadata.get('reused_states', 0)} merged, "
                   f"{len(result.intent_sequences)} sequences")

        return {
            "success": True,
            "states_added": result.metadata.get("new_states", 0),
            "states_merged": result.metadata.get("reused_states", 0),
            "page_instances_added": len(result.page_instances),
            "intent_sequences_added": len(result.intent_sequences),
            "actions_added": len(result.actions),
            "processing_time_ms": processing_time_ms
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to add to memory: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to add to memory: {str(e)}")


@app.post("/api/v1/memory/query")
async def query_memory(
    data: dict,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """
    Query User's Workflow Memory using Natural Language

    This endpoint performs intelligent semantic search on the user's workflow memory.
    The system automatically analyzes the query and returns the most relevant operation paths.

    Query Processing:
    1. Generate embedding for query text
    2. Find matching States using semantic similarity
    3. Search paths between States on graph (if applicable)
    4. For each State, find relevant IntentSequences
    5. Return complete operation paths

    Headers:
        X-Ami-API-Key: User's API key (required for embedding generation)

    Body:
        {
            "user_id": "user123",                    // Required: User identifier
            "query": "通过榜单查看产品团队信息",        // Required: Natural language query
            "top_k": 3,                              // Optional: Number of paths to return (default: 3)
            "min_score": 0.5,                        // Optional: Minimum similarity score (default: 0.5)
            "domain": "producthunt.com"              // Optional: Filter by domain
        }

    Returns:
        {
            "success": true,
            "query": "通过榜单查看产品团队信息",
            "paths": [...],
            "total_paths": 1
        }

    Errors:
        400: Missing user_id or query
        503: Memory service not initialized
        500: Query failed
    """
    logger.info(f"🔍 Memory query request received: data={data}")

    if workflow_memory is None:
        raise HTTPException(503, "Memory service not initialized")

    if not x_ami_api_key:
        raise HTTPException(400, "Missing X-Ami-API-Key header")

    user_id = data.get("user_id")
    query = data.get("query")
    top_k = data.get("top_k", 3)
    min_score = data.get("min_score", 0.5)
    domain = data.get("domain")
    max_depth = data.get("max_depth", 10)

    if not user_id:
        raise HTTPException(400, "Missing user_id")
    if not query:
        raise HTTPException(400, "Missing query")

    try:
        # Import EmbeddingService
        from src.cloud_backend.memgraph.services.embedding_service import EmbeddingService

        if not EmbeddingService.is_available():
            logger.warning("EmbeddingService not available")
            raise HTTPException(500, "Embedding service not available")

        # Step 1: Generate embedding for query
        query_embedding = EmbeddingService.embed(query)
        if not query_embedding:
            raise HTTPException(500, "Failed to generate query embedding")

        # Step 2: Find matching States by embedding similarity
        state_results = workflow_memory.state_manager.search_states_by_embedding(
            query_vector=query_embedding,
            top_k=top_k * 2,  # Get more candidates
            user_id=user_id,
        )

        # Filter by min_score and domain
        matching_states = []
        for state, score in state_results:
            if score < min_score:
                continue
            if domain and state.domain != domain:
                continue
            matching_states.append((state, score))

        if not matching_states:
            logger.info(f"No matching states found for query: {query}")
            return {
                "success": True,
                "query": query,
                "paths": [],
                "total_paths": 0,
                "message": "No matching states found"
            }

        # Step 3: Build paths
        # For now, we treat each matching state as a potential endpoint
        # and try to find paths to it from other states
        paths = []

        for target_state, target_score in matching_states[:top_k]:
            # Find the best IntentSequence for this state
            best_intent_seq = None
            best_seq_score = 0.0

            if target_state.intent_sequences:
                # Search within this state's IntentSequences
                for seq in target_state.intent_sequences:
                    if seq.embedding_vector:
                        # Calculate cosine similarity with query
                        import math
                        dot = sum(a * b for a, b in zip(query_embedding, seq.embedding_vector))
                        norm1 = math.sqrt(sum(a * a for a in query_embedding))
                        norm2 = math.sqrt(sum(b * b for b in seq.embedding_vector))
                        seq_score = dot / (norm1 * norm2) if norm1 > 0 and norm2 > 0 else 0.0
                        if seq_score > best_seq_score:
                            best_seq_score = seq_score
                            best_intent_seq = seq

            # Format intents for response
            intents_data = []
            if best_intent_seq and best_intent_seq.intents:
                for intent in best_intent_seq.intents[:10]:  # Limit to 10 intents
                    if hasattr(intent, "to_dict"):
                        intent_dict = intent.to_dict()
                    else:
                        intent_dict = intent
                    intents_data.append({
                        "type": intent_dict.get("type"),
                        "text": intent_dict.get("text"),
                        "value": intent_dict.get("value"),
                    })

            # Build step for this state
            step = {
                "state": {
                    "id": target_state.id,
                    "description": target_state.description,
                    "page_title": target_state.page_title,
                    "page_url": target_state.page_url,
                    "domain": target_state.domain,
                },
                "action": None,  # No action for single-point query
                "intent_sequence": {
                    "id": best_intent_seq.id if best_intent_seq else None,
                    "description": best_intent_seq.description if best_intent_seq else None,
                    "intents": intents_data,
                } if best_intent_seq else None,
            }

            # Try to find incoming paths to this state
            # Get all user states and try to find paths
            all_states = workflow_memory.state_manager.list_states()
            user_states = [s for s in all_states if getattr(s, 'user_id', None) == user_id]

            # Find the best path to this target state
            best_path = None
            best_path_length = float('inf')

            for source_state in user_states:
                if source_state.id == target_state.id:
                    continue
                path = workflow_memory.find_path(
                    from_state_id=source_state.id,
                    to_state_id=target_state.id,
                    max_depth=max_depth,
                )
                if path and len(path) > 1 and len(path) < best_path_length:
                    best_path = path
                    best_path_length = len(path)

            if best_path and len(best_path) > 1:
                # Format full path with IntentSequences
                path_steps = []
                for i, (state, action) in enumerate(best_path):
                    # Find best IntentSequence for this state
                    state_intent_seq = None
                    if state.intent_sequences:
                        # Use first non-empty IntentSequence
                        for seq in state.intent_sequences:
                            if seq.intents:
                                state_intent_seq = seq
                                break

                    # Format intents
                    state_intents = []
                    if state_intent_seq and state_intent_seq.intents:
                        for intent in state_intent_seq.intents[:5]:
                            if hasattr(intent, "to_dict"):
                                intent_dict = intent.to_dict()
                            else:
                                intent_dict = intent
                            state_intents.append({
                                "type": intent_dict.get("type"),
                                "text": intent_dict.get("text"),
                                "value": intent_dict.get("value"),
                            })

                    path_step = {
                        "state": {
                            "id": state.id,
                            "description": state.description,
                            "page_title": state.page_title,
                            "page_url": state.page_url,
                            "domain": state.domain,
                        },
                        "action": {
                            "id": action.id,
                            "description": action.description,
                            "type": action.type,
                        } if action else None,
                        "intent_sequence": {
                            "id": state_intent_seq.id if state_intent_seq else None,
                            "description": state_intent_seq.description if state_intent_seq else None,
                            "intents": state_intents,
                        } if state_intent_seq else None,
                    }
                    path_steps.append(path_step)

                paths.append({
                    "score": round(target_score, 4),
                    "description": f"从 {best_path[0][0].description or best_path[0][0].page_title} 到 {target_state.description or target_state.page_title}",
                    "steps": path_steps,
                })
            else:
                # No path found, return single state as result
                paths.append({
                    "score": round(target_score, 4),
                    "description": target_state.description or target_state.page_title,
                    "steps": [step],
                })

        # Sort by score and limit to top_k
        paths.sort(key=lambda x: x["score"], reverse=True)
        paths = paths[:top_k]

        logger.info(f"✅ Memory query for user {user_id}: '{query}' -> {len(paths)} paths")

        return {
            "success": True,
            "query": query,
            "paths": paths,
            "total_paths": len(paths),
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"❌ Memory query failed: {e}\n{error_trace}")
        print(f"❌ Memory query error:\n{error_trace}")
        raise HTTPException(500, f"Memory query failed: {str(e)}")


@app.get("/api/v1/memory/stats")
async def get_memory_stats(
    user_id: str,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """
    Get User's Workflow Memory Statistics

    This endpoint returns statistics about the user's workflow memory,
    including counts of States, IntentSequences, PageInstances, and Actions.

    Headers:
        X-Ami-API-Key: User's API key (optional)

    Query Parameters:
        user_id: User identifier (required)

    Returns:
        {
            "success": true,
            "user_id": "user123",
            "stats": {
                "total_states": 10,
                "total_intent_sequences": 25,
                "total_page_instances": 15,
                "total_actions": 8,
                "domains": ["producthunt.com", "google.com"],
                "url_index_size": 12
            }
        }

    Errors:
        400: Missing user_id
        500: Failed to get stats
    """
    if not user_id:
        raise HTTPException(400, "Missing user_id")

    try:
        # Get all states for user
        all_states = workflow_memory.state_manager.list_states(user_id=user_id)

        # Calculate statistics
        total_intent_sequences = 0
        total_page_instances = 0
        domains = set()

        for state in all_states:
            total_intent_sequences += len(state.intent_sequences)
            total_page_instances += len(state.instances)
            if state.domain:
                domains.add(state.domain)

        # Get actions count
        total_actions = len(workflow_memory.action_manager.list_actions(user_id=user_id))

        # Get URL index stats
        url_index_stats = workflow_memory.url_index.get_stats()

        logger.info(f"✅ Memory stats for user {user_id}: {len(all_states)} states")

        return {
            "success": True,
            "user_id": user_id,
            "stats": {
                "total_states": len(all_states),
                "total_intent_sequences": total_intent_sequences,
                "total_page_instances": total_page_instances,
                "total_actions": total_actions,
                "domains": sorted(list(domains)),
                "url_index_size": url_index_stats.get("total_urls", 0),
            }
        }

    except Exception as e:
        logger.error(f"❌ Failed to get memory stats: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to get memory stats: {str(e)}")


@app.delete("/api/v1/memory")
async def clear_memory(
    user_id: str,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """
    Clear User's Workflow Memory

    This endpoint deletes all States, Actions, and related data from the user's
    workflow memory. This operation is irreversible.

    Headers:
        X-Ami-API-Key: User's API key (optional)

    Query Parameters:
        user_id: User identifier (required)

    Returns:
        {
            "success": true,
            "deleted_states": 10,
            "deleted_actions": 8
        }

    Errors:
        400: Missing user_id
        500: Failed to clear memory
    """
    if not user_id:
        raise HTTPException(400, "Missing user_id")

    try:
        # Get counts before deletion
        all_states = workflow_memory.state_manager.list_states(user_id=user_id)
        all_actions = workflow_memory.action_manager.list_actions(user_id=user_id)
        states_count = len(all_states)
        actions_count = len(all_actions)

        # Delete all actions first (they reference states)
        for action in all_actions:
            workflow_memory.delete_action(action.source, action.target)

        # Delete all states
        for state in all_states:
            workflow_memory.delete_state(state.id)

        # Clear URL index for user
        workflow_memory.url_index.clear()

        logger.info(f"✅ Memory cleared for user {user_id}: {states_count} states, {actions_count} actions")

        return {
            "success": True,
            "deleted_states": states_count,
            "deleted_actions": actions_count,
        }

    except Exception as e:
        logger.error(f"❌ Failed to clear memory: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to clear memory: {str(e)}")


# ===== Helper Functions for NL Query =====

async def _ensure_user_memory_loaded(user_id: str, session_id: Optional[str] = None):
    """
    Ensure user's recordings are loaded into WorkflowMemory.

    This function loads States/Actions from the user's recordings into the global
    workflow_memory for natural language querying.

    Args:
        user_id: User ID
        session_id: Optional session ID to filter recordings
    """
    global workflow_memory

    if not workflow_memory:
        raise HTTPException(500, "WorkflowMemory not initialized")

    logger.info(f"Loading memory for user {user_id}")

    # Get user's recordings from storage
    recordings = storage_service.list_recordings(user_id)

    # Filter by session if specified
    if session_id:
        recordings = [r for r in recordings if r.get("session_id") == session_id]

    if not recordings:
        logger.warning(f"No recordings found for user {user_id}")
        return

    # Load each recording's graph into memory
    loaded_count = 0
    for recording_meta in recordings:
        recording_id = recording_meta.get("recording_id")

        # Get full recording data with graph
        recording = storage_service.get_recording(user_id, recording_id)
        if not recording:
            continue

        graph_dict = recording.get("graph")
        if not graph_dict:
            continue

        # Convert graph dict to StateActionGraph
        try:
            from src.cloud_backend.graph_builder.models import StateActionGraph
            graph = StateActionGraph.from_dict(graph_dict)

            # Store states with intents to memory
            for state in graph.states.values():
                workflow_memory.create_state(state)

            # Store actions to memory
            for action in graph.actions:
                workflow_memory.create_action(action)

            loaded_count += 1
            logger.debug(f"Loaded recording {recording_id}: {len(graph.states)} states, {len(graph.actions)} actions")

        except Exception as e:
            logger.warning(f"Failed to load recording {recording_id}: {e}")
            continue

    logger.info(f"✅ Loaded {loaded_count} recordings into memory for user {user_id}")


async def _get_reasoner_for_user(x_ami_api_key: str):
    """
    Get or create a Reasoner instance with user's API key.

    Args:
        x_ami_api_key: User's API key

    Returns:
        Reasoner instance
    """
    from src.cloud_backend.memgraph.reasoner.reasoner import Reasoner
    from src.common.llm.anthropic_provider import AnthropicProvider

    # Create LLM provider with user's API key
    llm_provider = AnthropicProvider(
        api_key=x_ami_api_key,
        base_url=config_service.get("llm.proxy_url", "https://api.ariseos.com/api")
    )

    # Create Reasoner with memory and LLM provider
    reasoner = Reasoner(
        memory=workflow_memory,
        llm_provider=llm_provider,
        max_depth=3
    )

    return reasoner


@app.post("/api/v1/workflows/query")
async def query_workflow_from_memory(
    data: dict,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key")
):
    """
    Query Workflow from Memory using Natural Language

    This endpoint allows users to retrieve workflows from memory using natural language queries.
    It uses the Reasoner to semantically match the query against stored States/Actions/Intents.

    Headers:
        X-Ami-API-Key: User's API key (required)

    Body:
        {
            "user_id": "user123",
            "query": "Fill out the login form",
            "session_id": "session_456",        // Optional: filter by session
            "top_k": 5,                          // Optional: number of results (default: 5)
            "min_confidence": 0.7                // Optional: minimum confidence score (default: 0.7)
        }

    Returns:
        {
            "workflow": {...},                   // Executable workflow JSON/YAML
            "confidence": 0.85,
            "matched_states": [...],
            "matched_actions": [...],
            "status": "success"
        }
    """
    if not x_ami_api_key:
        raise HTTPException(400, "Missing X-Ami-API-Key header")

    user_id = data.get("user_id")
    query = data.get("query")
    session_id = data.get("session_id")
    top_k = data.get("top_k", 5)
    min_confidence = data.get("min_confidence", 0.7)

    if not user_id:
        raise HTTPException(400, "Missing user_id")
    if not query:
        raise HTTPException(400, "Missing query")

    try:
        # Ensure user's memory is loaded
        await _ensure_user_memory_loaded(user_id, session_id)

        # Get Reasoner instance with user's API key
        user_reasoner = await _get_reasoner_for_user(x_ami_api_key)

        # Query memory using Reasoner
        result = await user_reasoner.plan(query, user_id=user_id, session_id=session_id)

        if not result or not result.success:
            return {
                "workflow": None,
                "confidence": 0.0,
                "matched_states": [],
                "matched_actions": [],
                "status": "no_match",
                "message": "No matching workflow found in memory"
            }

        logger.info(f"✅ Workflow retrieved from memory for query: {query}")

        return {
            "workflow": result.workflow,
            "confidence": result.confidence if hasattr(result, 'confidence') else 1.0,
            "matched_states": [s.id for s in result.states] if hasattr(result, 'states') else [],
            "matched_actions": [a.id for a in result.actions] if hasattr(result, 'actions') else [],
            "status": "success"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Workflow query failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Workflow query failed: {str(e)}")


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

        # Try to get graph from recording first (preferred path)
        graph = None
        recording_data = None

        if recording_id:
            recording_data = storage_service.get_recording(user_id, recording_id)
            if recording_data:
                graph = recording_data.get("graph")
                if graph:
                    logger.info(f"📊 Using graph from recording: {len(graph.get('states', {}))} states, {len(graph.get('edges', []))} edges")
                    operations = recording_data.get("operations", [])
                else:
                    logger.info("📹 Recording found but no graph, will use operations")
                    operations = recording_data.get("operations", [])
            else:
                raise HTTPException(404, f"Recording not found: {recording_id}")

        # If no graph yet, try to get operations and build/extract
        if not graph and not intent_sequence:
            # Try direct operations first (from App Backend)
            if operations:
                logger.info(f"📹 Using direct operations: {len(operations)} operations")
                recording_id = source_recording_id  # Use source_recording_id for traceability

            if operations:
                # Fall back to intent extraction (legacy path)
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
                logger.info(f"✅ Extracted {len(intent_sequence)} intents (legacy path)")

        if not graph and not intent_sequence:
            raise HTTPException(400, "No graph, intent_sequence, operations, or recording_id provided")

        # Create WorkflowService and generate
        service = WorkflowService(
            config_service=config_service,
            api_key=x_ami_api_key,
            base_url=config_service.get("llm.proxy_url")
        )

        # Create request with graph (preferred) or intent_sequence (legacy)
        request = GenerationRequest(
            recording_id=recording_id,
            task_description=task_description,
            user_query=data.get("user_query"),
            graph=graph,  # NEW: Graph from Graph Builder
            intent_sequence=intent_sequence,  # LEGACY: Intent extraction path
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

    The generation task runs in background and continues even if client disconnects.

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

    # Create a queue for communication between background task and SSE stream
    progress_queue: asyncio.Queue = asyncio.Queue()

    async def background_generation_task():
        """
        Background task that performs the actual generation.
        Communicates progress via the queue.
        This task continues even if client disconnects.
        """
        try:
            logger.info(f"🚀 [Background] Starting workflow generation for user {user_id}")

            # Import the new WorkflowService
            from src.cloud_backend.intent_builder.services import (
                WorkflowService,
                GenerationRequest,
                GenerationStatus
            )

            # Initial progress
            await progress_queue.put({'status': 'pending', 'progress': 0, 'message': 'Starting...'})

            # Try to get graph from recording first (preferred path)
            graph = None
            local_intent_sequence = intent_sequence
            local_operations = operations
            local_recording_id = recording_id or source_recording_id
            recording_data = None

            # Try to load recording and get graph
            if recording_id:
                await progress_queue.put({'status': 'analyzing', 'progress': 10, 'message': 'Loading recording...'})
                recording_data = storage_service.get_recording(user_id, recording_id)
                if not recording_data:
                    await progress_queue.put({'status': 'failed', 'progress': 0, 'message': 'Recording not found', '_done': True})
                    return

                graph = recording_data.get("graph")
                if graph:
                    logger.info(f"📊 [Stream] Using graph from recording: {len(graph.get('states', {}))} states, {len(graph.get('edges', []))} edges")
                    await progress_queue.put({'status': 'analyzing', 'progress': 15, 'message': 'Using State/Action Graph'})
                else:
                    logger.info("📹 [Stream] Recording found but no graph, will use operations")
                    local_operations = recording_data.get("operations", [])

            # If no graph yet and no intent_sequence, try to get operations
            if not graph and not local_intent_sequence:
                # If we have direct operations from App Backend, use them
                if not local_operations and operations:
                    logger.info(f"📹 [Stream] Using direct operations: {len(operations)} operations")
                    local_operations = operations
                    await progress_queue.put({'status': 'analyzing', 'progress': 10, 'message': f'Processing {len(local_operations)} operations...'})

                # Extract intents from operations if we have them (legacy path)
                if local_operations:
                    await progress_queue.put({'status': 'analyzing', 'progress': 20, 'message': f'Extracting intents from {len(local_operations)} operations...'})

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
                    await progress_queue.put({'status': 'understanding', 'progress': 30, 'message': f'Extracted {len(local_intent_sequence)} intents'})

            # Verify we have either graph or intent_sequence
            if not graph and not local_intent_sequence:
                await progress_queue.put({'status': 'failed', 'progress': 0, 'message': 'No graph, intent sequence, or operations', '_done': True})
                return

            # Create service and generate with streaming
            service = WorkflowService(
                config_service=config_service,
                api_key=x_ami_api_key,
                base_url=config_service.get("llm.proxy_url")
            )

            # Load DOM snapshots for script generation
            dom_snapshots = None
            if local_recording_id:
                dom_snapshots = storage_service.get_recording_dom_snapshots(user_id, local_recording_id)
                if dom_snapshots:
                    logger.info(f"📸 [Background] Loaded {len(dom_snapshots)} DOM snapshots for script generation")

            # Create request with graph (preferred) or intent_sequence (legacy)
            request = GenerationRequest(
                recording_id=local_recording_id,
                task_description=task_description,
                user_query=user_query,
                graph=graph,
                intent_sequence=local_intent_sequence,
                enable_semantic_validation=enable_semantic_validation,
                dom_snapshots=dom_snapshots
            )

            # Stream progress and track session_id
            logger.info(f"📊 [Background] Starting to stream progress...")
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
                    if progress.details.startswith("Session ID: "):
                        session_id = progress.details.replace("Session ID: ", "")
                        logger.info(f"✅ [Stream] Extracted session_id from completed event: {session_id}")
                    else:
                        logger.warning(f"⚠️ [Stream] Completed event details don't match expected format: {progress.details}")

                logger.info(f"📊 [Background] Progress: {progress.status.value} - {progress.progress}%")
                await progress_queue.put(event_data)

            # Get final result from cached stream result
            logger.info(f"🔧 [Background] Getting cached result for session: {session_id}")

            if session_id:
                response = service.pop_stream_result(session_id)
                if response:
                    logger.info(f"🔧 [Background] Retrieved cached response: success={response.success}")
                else:
                    logger.warning(f"⚠️ [Background] No cached result for session {session_id}")
                    response = None
            else:
                logger.info(f"🔧 [Background] No session_id, final status was: {final_status}")
                response = None

            # Handle case where we don't have a cached result
            if response is None:
                if final_status == "failed":
                    logger.error(f"❌ [Background] Generation failed: {final_message}")
                    await progress_queue.put({'status': 'failed', 'progress': 0, 'message': final_message or 'Generation failed', '_done': True})
                    return
                else:
                    logger.error(f"❌ [Background] Unexpected: No cached result and status was {final_status}")
                    await progress_queue.put({'status': 'failed', 'progress': 0, 'message': 'Internal error: no generation result', '_done': True})
                    return

            if response.success:
                # Save workflow
                workflow_id = f"workflow_{uuid.uuid4().hex[:12]}"
                import yaml
                workflow_dict = yaml.safe_load(response.workflow_yaml)
                workflow_name = workflow_dict.get("name", workflow_id)

                logger.info(f"✅ [Background] Saving workflow: {workflow_id} - {workflow_name} for user: {user_id}")
                storage_service.save_workflow(
                    user_id=user_id,
                    workflow_id=workflow_id,
                    workflow_yaml=response.workflow_yaml,
                    workflow_name=workflow_name,
                    source_recording_id=local_recording_id
                )
                logger.info(f"✅ [Background] Workflow saved to disk")

                # Link recording to workflow
                if local_recording_id:
                    try:
                        storage_service.update_recording_workflow(user_id, local_recording_id, workflow_id)
                        logger.info(f"✅ [Background] Recording {local_recording_id} linked to Workflow {workflow_id}")
                    except Exception as e:
                        logger.warning(f"⚠️ [Background] Failed to link recording to workflow: {e}")

                # TEMPORARY: Skip script pre-generation (scripts generated on-demand during execution)
                script_gen_result = None
                # if dom_snapshots and local_recording_id:
                #     await progress_queue.put({'status': 'generating_scripts', 'progress': 90, 'message': 'Generating scripts for workflow steps...'})
                #
                #     try:
                #         workflow_dir = storage_service.get_workflow_path(user_id, workflow_id)
                #         local_intents = intents if intents else None
                #         script_gen_result = await _generate_scripts_sync(
                #             workflow_yaml=response.workflow_yaml,
                #             dom_snapshots=dom_snapshots,
                #             workflow_dir=workflow_dir,
                #             api_key=x_ami_api_key,
                #             base_url=config_service.get("llm.proxy_url"),
                #             intents=local_intents
                #         )
                #         if script_gen_result:
                #             logger.info(f"🔧 [Background] Script generation: generated={script_gen_result.get('generated', 0)}, "
                #                        f"skipped={script_gen_result.get('skipped', 0)}, failed={script_gen_result.get('failed', 0)}")
                #
                #             # Update metadata.json with resources info for client sync
                #             if script_gen_result.get('generated', 0) > 0:
                #                 await storage_service.update_workflow_resources(user_id, workflow_id)
                #                 logger.info(f"🔧 [Background] Updated metadata with generated scripts")
                #     except Exception as e:
                #         logger.warning(f"⚠️ [Background] Script generation failed: {e}")

                logger.info(f"✅ [Background] Workflow saved successfully")
                completion_data = {
                    'status': 'completed',
                    'progress': 100,
                    'workflow_id': workflow_id,
                    'workflow_name': workflow_name,
                    'message': 'Workflow generated successfully',
                    '_done': True
                }
                if script_gen_result:
                    completion_data['script_generation'] = {
                        'generated': script_gen_result.get('generated', 0),
                        'skipped': script_gen_result.get('skipped', 0),
                        'failed': script_gen_result.get('failed', 0)
                    }
                await progress_queue.put(completion_data)

            else:
                logger.error(f"❌ [Background] Generation failed: {response.error}")
                await progress_queue.put({'status': 'failed', 'progress': 0, 'message': response.error, '_done': True})

        except Exception as e:
            logger.error(f"❌ [Background] Exception: {e}")
            import traceback
            traceback.print_exc()
            await progress_queue.put({'status': 'failed', 'progress': 0, 'message': str(e), '_done': True})

    # Start the background task - it will continue even if client disconnects
    background_task = asyncio.create_task(background_generation_task())
    logger.info(f"🚀 [Stream] Background generation task started for user {user_id}")

    async def event_generator():
        """
        SSE event generator that reads from the progress queue.
        If client disconnects, the background task continues running.
        Sends keepalive every 15 seconds to prevent client timeout.
        """
        try:
            while True:
                try:
                    # Wait for next progress event with short timeout for keepalive
                    event_data = await asyncio.wait_for(progress_queue.get(), timeout=15.0)

                    # Check if this is the final event
                    is_done = event_data.pop('_done', False)

                    yield f"data: {json.dumps(event_data)}\n\n"

                    if is_done:
                        logger.info(f"📊 [Stream] Generation completed, closing stream")
                        break

                except asyncio.TimeoutError:
                    # Check if background task is still running
                    if background_task.done():
                        logger.warning(f"⚠️ [Stream] Background task ended without sending completion")
                        yield f"data: {json.dumps({'status': 'failed', 'progress': 0, 'message': 'Generation task ended unexpectedly'})}\n\n"
                        break
                    # Send keepalive to prevent client timeout (SSE comment format)
                    yield f": keepalive\n\n"
                    continue

        except asyncio.CancelledError:
            # Client disconnected - background task continues
            logger.info(f"🔄 [Stream] Client disconnected, background task continues running")
            raise

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
            "workflow_yaml": "apiVersion: v1\\nkind: Workflow\\n...",
            "chat_history": [  // Optional - restore context from previous session
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": "..."}
            ]
        }

    Returns:
        {
            "session_id": "session_xyz789",
            "success": true,
            "history_restored": true  // If chat_history was provided and injected
        }
    """
    if not x_ami_api_key:
        raise HTTPException(400, "Missing X-Ami-API-Key header")

    user_id = data.get("user_id")
    workflow_id = data.get("workflow_id")
    workflow_yaml = data.get("workflow_yaml")
    chat_history = data.get("chat_history")  # Optional: list of {role, content}

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

        # Create WorkflowModificationSession with storage_service for session directory management
        session = WorkflowModificationSession(
            workflow_yaml=workflow_yaml,
            user_id=user_id,
            workflow_id=workflow_id,
            storage_service=storage_service,
            config_service=config_service,
            api_key=x_ami_api_key,
            base_url=config_service.get("llm.proxy_url"),
            session_id=session_id,
            chat_history=chat_history  # Pass chat history to session
        )

        # Connect the session (copies workflow to session directory)
        await session._connect()

        # Store session reference
        _workflow_sessions[session_id] = {
            "session": session,
            "user_id": user_id,
            "workflow_id": workflow_id,
            "created_at": datetime.now().isoformat()
        }

        history_restored = bool(chat_history and len(chat_history) > 0)
        logger.info(f"✅ Workflow modification session created: {session_id}, history_restored={history_restored}")

        return {
            "session_id": session_id,
            "success": True,
            "history_restored": history_restored
        }

    except Exception as e:
        import traceback
        logger.error(f"❌ Failed to create workflow session: {e}")
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
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
    logger.info(f"📦 [chat endpoint] Raw data received: {data}")
    logger.info(f"📦 [chat endpoint] Data type: {type(data)}")

    if session_id not in _workflow_sessions:
        logger.error(f"❌ [chat endpoint] Session not found: {session_id}")
        raise HTTPException(404, f"Session not found: {session_id}")

    message = data.get("message")
    logger.info(f"📦 [chat endpoint] Message value: {message}, type: {type(message)}")
    if not message:
        raise HTTPException(400, "Missing message")

    logger.info(f"📝 [chat endpoint] Message: {str(message)[:100]}...")

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

            # After chat completes, sync modified files from session back to original workflow
            # This syncs both workflow.yaml and extraction_script.py changes
            try:
                synced_files = storage_service.sync_session_to_workflow(
                    user_id=user_id,
                    session_id=session_id
                )
                if synced_files:
                    logger.info(f"✅ Synced {len(synced_files)} files: {synced_files}")
                    # Send sync_required event to trigger frontend sync to local client
                    sync_event = {
                        "type": "sync_required",
                        "files": synced_files
                    }
                    yield f"data: {json.dumps(sync_event)}\n\n"
            except Exception as e:
                logger.error(f"Failed to sync session to workflow: {e}")

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

    Disconnects from Claude Agent and cleans up session directory.
    """
    if session_id not in _workflow_sessions:
        raise HTTPException(404, f"Session not found: {session_id}")

    session_data = _workflow_sessions[session_id]
    session = session_data["session"]

    try:
        # Disconnect from Claude Agent
        await session._disconnect()
    except Exception as e:
        logger.warning(f"Error disconnecting session: {e}")

    try:
        # Cleanup session directory
        session.cleanup()
    except Exception as e:
        logger.warning(f"Error cleaning up session: {e}")

    del _workflow_sessions[session_id]
    logger.info(f"✅ Workflow session closed and cleaned up: {session_id}")

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
            "task_id": "task_workflow_abc12345",
            "user_id": "user123",
            "device_id": "device_xxx",
            "workflow_id": "workflow_name",
            "workflow_name": "Workflow Display Name",
            "meta": {
                "task_id": "task_workflow_abc12345",
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
        {"success": true, "task_id": "task_workflow_abc12345"}
    """
    task_id = data.get("task_id")
    user_id = data.get("user_id")
    workflow_id = data.get("workflow_id")
    workflow_name = data.get("workflow_name")
    meta = data.get("meta", {})
    logs = data.get("logs", [])
    device_info = data.get("device_info", {})

    if not user_id:
        raise HTTPException(400, "Missing user_id")
    if not task_id:
        raise HTTPException(400, "Missing task_id")
    if not workflow_id:
        raise HTTPException(400, "Missing workflow_id")

    try:
        # Store the execution log
        log_path = storage_service.get_user_workflow_logs_path(user_id, workflow_id)
        log_path.mkdir(parents=True, exist_ok=True)

        # Save log file as {task_id}.json
        log_file = log_path / f"{task_id}.json"
        log_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))

        logger.info(
            f"Workflow log uploaded: {task_id} "
            f"(workflow={workflow_name}, status={meta.get('status')}, "
            f"steps={meta.get('steps_completed')}/{meta.get('steps_total')})"
        )

        return {
            "success": True,
            "task_id": task_id,
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
    except HTTPException:
        # Re-raise HTTPException as-is (don't wrap 404 in 500)
        raise
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

    Special handling for dom_snapshots/*.json:
        - Automatically updates dom_snapshots/url_index.json with step_id mapping
        - Enables copy_workflow_to_session to find correct DOM for each step
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

        # Special handling: update url_index.json when saving DOM snapshots
        if path.startswith("dom_snapshots/") and path.endswith(".json") and path != "dom_snapshots/url_index.json":
            try:
                _update_dom_url_index(workflow_path, path, content)
            except Exception as e:
                # Don't fail the upload if url_index update fails
                logger.warning(f"Failed to update url_index.json: {e}")

        return {"success": True, "size": len(content)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save file {path} for {workflow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _update_dom_url_index(workflow_path: Path, dom_file_path: str, content: bytes):
    """Update dom_snapshots/url_index.json with step_id mapping

    Called when a DOM snapshot is saved. Extracts metadata from the snapshot
    and updates the url_index.json file.

    Args:
        workflow_path: Path to workflow directory
        dom_file_path: Relative path like "dom_snapshots/abc123.json"
        content: The DOM snapshot file content (JSON bytes)
    """
    import json

    # Parse DOM snapshot to get metadata
    try:
        snapshot_data = json.loads(content.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning(f"Failed to parse DOM snapshot {dom_file_path}: {e}")
        return

    url = snapshot_data.get("url")
    step_id = snapshot_data.get("step_id")
    url_hash = snapshot_data.get("url_hash")
    timestamp = snapshot_data.get("timestamp")

    if not url:
        logger.warning(f"DOM snapshot {dom_file_path} missing 'url' field")
        return

    # Get filename from path
    dom_filename = dom_file_path.split("/")[-1]  # e.g., "abc123.json"

    # Load existing url_index.json or create new
    url_index_path = workflow_path / "dom_snapshots" / "url_index.json"
    url_index = []

    if url_index_path.exists():
        try:
            with open(url_index_path, 'r', encoding='utf-8') as f:
                url_index = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load url_index.json, creating new: {e}")
            url_index = []

    # Find existing entry by url or filename, update or append
    entry_found = False
    for entry in url_index:
        if entry.get("url") == url or entry.get("file") == dom_filename:
            # Update existing entry
            entry["url"] = url
            entry["file"] = dom_filename
            entry["step_id"] = step_id
            entry["captured_at"] = timestamp
            entry_found = True
            logger.info(f"Updated url_index entry: url={url}, step_id={step_id}")
            break

    if not entry_found:
        # Append new entry
        url_index.append({
            "url": url,
            "file": dom_filename,
            "step_id": step_id,
            "captured_at": timestamp
        })
        logger.info(f"Added url_index entry: url={url}, step_id={step_id}")

    # Save updated url_index.json
    with open(url_index_path, 'w', encoding='utf-8') as f:
        json.dump(url_index, f, indent=2, ensure_ascii=False)

    logger.info(f"Updated dom_snapshots/url_index.json ({len(url_index)} entries)")


class GenerateScriptRequest(BaseModel):
    """Request body for script generation API

    Design principles:
    - Minimize data transfer by reusing cloud-stored data
    - For scraper: cloud has workflow (data_requirements) + dom_snapshots from recording
    - For browser: need current DOM since page may have changed

    Fields:
        step_id: Step identifier to locate step config in workflow YAML
        script_type: "scraper" or "browser"
        page_url: Current page URL (for DOM matching / absolute URL conversion)
        dom_data: Optional - only needed for browser scripts (runtime DOM)
                 For scraper, cloud uses dom_snapshots from recording
    """
    step_id: str
    script_type: str  # "scraper" or "browser"
    page_url: str
    dom_data: Optional[Dict[str, Any]] = None  # DOM data from client


@app.post("/api/v1/workflows/{workflow_id}/generate-script-stream")
async def generate_script_stream(
    workflow_id: str,
    request: GenerateScriptRequest,
    x_user_id: str = Header(..., alias="X-User-Id"),
    x_api_key: str = Header(None, alias="X-Api-Key"),
    authorization: str = Header(None)
):
    """
    Generate script with SSE streaming progress updates.

    SSE Events:
    - {"type": "progress", "message": "...", "turn": N}
    - {"type": "complete", "success": true, "script_path": "...", "script_content": "...", "turns": N}
    - {"type": "error", "message": "..."}
    """
    import yaml

    request_id = f"req_{uuid.uuid4().hex[:12]}"
    logger.info(f"[{request_id}] Generate script stream request: workflow={workflow_id}, step={request.step_id}, type={request.script_type}")

    # Validate inputs before starting stream
    api_key = x_api_key
    if not api_key and authorization:
        if authorization.startswith("Bearer "):
            api_key = authorization[7:]

    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")

    if request.script_type not in ["scraper", "browser"]:
        raise HTTPException(status_code=400, detail="script_type must be 'scraper' or 'browser'")

    workflow_dir = storage_service.get_workflow_path(x_user_id, workflow_id)
    if not workflow_dir.exists():
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

    workflow_yaml_path = workflow_dir / "workflow.yaml"
    if not workflow_yaml_path.exists():
        raise HTTPException(status_code=404, detail="workflow.yaml not found")

    async def event_generator():
        """Generate SSE events for script generation progress"""
        progress_queue = asyncio.Queue()

        async def progress_callback(level: str, message: str, data: dict):
            """Callback to receive progress updates from script generator"""
            await progress_queue.put({
                "type": "progress",
                "level": level,
                "message": message,
                "turn": data.get("turn", 0),
                "tool_name": data.get("tool_name")
            })

        try:
            # Load workflow
            workflow_yaml = workflow_yaml_path.read_text(encoding='utf-8')
            workflow = yaml.safe_load(workflow_yaml)

            step_config = _find_step_in_workflow(workflow, request.step_id)
            if not step_config:
                yield f"data: {json.dumps({'type': 'error', 'message': f'Step not found: {request.step_id}'})}\n\n"
                return

            step_inputs = step_config.get("inputs", {})

            # Send initial progress
            yield f"data: {json.dumps({'type': 'progress', 'message': 'Starting script generation...', 'turn': 0})}\n\n"

            # Import generators
            from src.common.script_generation import ScraperScriptGenerator, BrowserScriptGenerator, ScraperRequirement, BrowserTask
            import hashlib

            if request.script_type == "scraper":
                data_requirements = step_inputs.get("data_requirements", {})
                if not data_requirements:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Step has no data_requirements'})}\n\n"
                    return

                # Use client-uploaded DOM
                # page_url may be extracted from wrapped DOM or from request
                page_url = request.page_url
                if request.dom_data:
                    # Handle both wrapped {"url": ..., "dom": {...}} and direct DOM format
                    if isinstance(request.dom_data, dict) and "dom" in request.dom_data:
                        dom_dict = request.dom_data["dom"]
                        page_url = request.dom_data.get("url") or request.page_url
                    else:
                        dom_dict = request.dom_data
                    yield f"data: {json.dumps({'type': 'progress', 'message': 'Using client-uploaded DOM', 'turn': 0})}\n\n"
                else:
                    dom_dict = _find_dom_for_step(workflow_dir, step_inputs, page_url)
                    if not dom_dict:
                        yield f"data: {json.dumps({'type': 'error', 'message': 'No DOM data provided'})}\n\n"
                        return
                    yield f"data: {json.dumps({'type': 'progress', 'message': 'Using recorded DOM snapshot', 'turn': 0})}\n\n"

                # Build requirement
                requirement = ScraperRequirement(
                    user_description=data_requirements.get("user_description", "Extract data"),
                    output_format=data_requirements.get("output_format", {}),
                    xpath_hints=data_requirements.get("xpath_hints", {}),
                    sample_data=data_requirements.get("sample_data", [])
                )

                # Working directory is now directly the step directory (no hash subdirectory)
                working_dir = workflow_dir / request.step_id
                working_dir.mkdir(parents=True, exist_ok=True)

                # Create generator and run with streaming
                generator = ScraperScriptGenerator(config_service)

                # Run generation in background task
                async def run_generation():
                    return await generator.generate(
                        requirement=requirement,
                        dom_dict=dom_dict,
                        working_dir=working_dir,
                        api_key=api_key,
                        base_url=config_service.get("llm.base_url"),
                        page_url=page_url,
                        progress_callback=progress_callback
                    )

                generation_task = asyncio.create_task(run_generation())
                script_name = "extraction_script.py"

            else:  # browser
                if not request.dom_data:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'dom_data is required for browser script'})}\n\n"
                    return

                # Handle both wrapped {"url": ..., "dom": {...}} and direct DOM format
                if isinstance(request.dom_data, dict) and "dom" in request.dom_data:
                    dom_dict = request.dom_data["dom"]
                    page_url = request.dom_data.get("url") or request.page_url
                else:
                    dom_dict = request.dom_data
                    page_url = request.page_url

                # Build task
                operation = step_inputs.get("operation", "click")
                task_desc = step_inputs.get("task") or step_inputs.get("description") or f"{operation} element"
                xpath_hints = step_inputs.get("xpath_hints", {})
                if isinstance(xpath_hints, list):
                    xpath_hints = {"target": xpath_hints[0]} if xpath_hints else {}
                text = step_inputs.get("text") or step_inputs.get("value")

                task = BrowserTask(
                    task=task_desc,
                    operation=operation,
                    xpath_hints=xpath_hints,
                    text=text
                )

                # Working directory is now directly the step directory (no hash subdirectory)
                working_dir = workflow_dir / request.step_id
                working_dir.mkdir(parents=True, exist_ok=True)

                # Create generator and run with streaming
                generator = BrowserScriptGenerator(config_service)

                async def run_generation():
                    return await generator.generate(
                        task=task,
                        dom_dict=dom_dict,
                        working_dir=working_dir,
                        api_key=api_key,
                        base_url=config_service.get("llm.base_url"),
                        page_url=page_url,
                        progress_callback=progress_callback
                    )

                generation_task = asyncio.create_task(run_generation())
                script_name = "find_element.py"

            # Stream progress events while generation runs
            while not generation_task.done():
                try:
                    # Wait for progress update with timeout
                    progress = await asyncio.wait_for(progress_queue.get(), timeout=5.0)
                    yield f"data: {json.dumps(progress)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield f": keepalive\n\n"

            # Drain remaining progress events
            while not progress_queue.empty():
                try:
                    progress = progress_queue.get_nowait()
                    yield f"data: {json.dumps(progress)}\n\n"
                except asyncio.QueueEmpty:
                    break

            # Get result
            result = await generation_task

            if not result.success:
                yield f"data: {json.dumps({'type': 'error', 'message': result.error})}\n\n"
                return

            # Read script content
            script_content = ""
            if result.script_path and result.script_path.exists():
                script_content = result.script_path.read_text(encoding='utf-8')

            # Script path is now directly in step directory (no hash subdirectory)
            script_path = f"{request.step_id}/{script_name}"

            # Update workflow metadata
            try:
                metadata = storage_service.load_workflow_metadata(x_user_id, workflow_id) or {}
                if "generated_scripts" not in metadata:
                    metadata["generated_scripts"] = {}
                metadata["generated_scripts"][request.step_id] = {
                    "script_type": request.script_type,
                    "script_path": script_path,
                    "generated_at": datetime.utcnow().isoformat(),
                    "turns": result.turns
                }

                # Update resources for sync (include dom_tools.py)
                if "resources" not in metadata:
                    metadata["resources"] = {}
                resource_type = "scraper_scripts" if request.script_type == "scraper" else "browser_scripts"
                if resource_type not in metadata["resources"]:
                    metadata["resources"][resource_type] = []

                # Build files list
                files_to_sync = [script_name]
                if request.script_type == "scraper":
                    # Include dom_tools.py for scraper scripts
                    dom_tools_path = working_dir / "dom_tools.py"
                    if dom_tools_path.exists():
                        files_to_sync.append("dom_tools.py")

                # Add or update resource entry
                resource_entry = {
                    "step_id": request.step_id,
                    "files": files_to_sync
                }
                # Remove existing entry for this step if exists
                metadata["resources"][resource_type] = [
                    r for r in metadata["resources"][resource_type]
                    if r.get("step_id") != request.step_id
                ]
                metadata["resources"][resource_type].append(resource_entry)

                # Update timestamp
                metadata["updated_at"] = datetime.utcnow().isoformat()

                storage_service.save_workflow_metadata(x_user_id, workflow_id, metadata)
                logger.info(f"[{request_id}] Updated metadata with resources: {files_to_sync}")
            except Exception as e:
                logger.warning(f"[{request_id}] Failed to update metadata: {e}")

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete', 'success': True, 'script_path': script_path, 'script_content': script_content, 'turns': result.turns})}\n\n"

            logger.info(f"[{request_id}] Script generated: {script_path} ({result.turns} turns)")

        except Exception as e:
            logger.error(f"[{request_id}] Script generation error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# ============================================================================
# Tavily API - Web search and research via CRS
# ============================================================================


class TavilySearchRequest(BaseModel):
    """Request for Tavily search operation - aligned with Tavily SDK"""
    query: str
    max_results: int = 10
    search_depth: str = "basic"  # basic, advanced, fast, ultra-fast
    topic: Optional[str] = None  # general, news, finance
    days: Optional[int] = None  # Limit to past N days
    time_range: Optional[str] = None  # day, week, month, year
    include_domains: Optional[List[str]] = None
    exclude_domains: Optional[List[str]] = None
    include_answer: Optional[bool] = None
    include_raw_content: Optional[bool] = None
    include_images: Optional[bool] = None
    country: Optional[str] = None


class TavilyResearchRequest(BaseModel):
    """Request for Tavily research operation - aligned with Tavily SDK"""
    query: str
    stream: bool = False
    model: Optional[str] = None  # mini, pro, auto
    citation_format: Optional[str] = None  # numbered, mla, apa, chicago


@app.post("/api/v1/tavily/search")
async def tavily_search(
    request: TavilySearchRequest,
    x_ami_api_key: str = Header(..., alias="X-Ami-API-Key")
):
    """
    Execute Tavily search via CRS

    Returns list of search results with title, url, snippet.
    Supports all Tavily SDK search parameters.
    """
    tavily_url = config_service.get("tavily.api_url", "https://api.ariseos.com/tavily")
    tavily_endpoint = f"{tavily_url.rstrip('/')}/search"

    # Build payload with all supported parameters
    payload = {
        "query": request.query,
        "search_depth": request.search_depth,
        "max_results": request.max_results,
    }

    # Optional parameters - only include if set
    if request.topic:
        payload["topic"] = request.topic
    if request.days is not None:
        payload["days"] = request.days
    if request.time_range:
        payload["time_range"] = request.time_range
    if request.include_domains:
        payload["include_domains"] = request.include_domains
    if request.exclude_domains:
        payload["exclude_domains"] = request.exclude_domains
    if request.include_answer is not None:
        payload["include_answer"] = request.include_answer
    if request.include_raw_content is not None:
        payload["include_raw_content"] = request.include_raw_content
    if request.include_images is not None:
        payload["include_images"] = request.include_images
    if request.country:
        payload["country"] = request.country

    # CRS uses Authorization: Bearer header for authentication
    headers = {
        "Authorization": f"Bearer {x_ami_api_key}",
        "Content-Type": "application/json",
    }

    logger.info(f"Tavily search: query={request.query[:50]}..., depth={request.search_depth}, topic={request.topic}, days={request.days}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                tavily_endpoint,
                json=payload,
                headers=headers,
                timeout=60.0
            )
            response.raise_for_status()
            data = response.json()

            # Process results - preserve all fields from Tavily API
            results = []
            for r in data.get("results", []):
                result = {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", "")[:500] if r.get("content") else "",
                    "published_date": r.get("published_date"),
                    "score": r.get("score"),
                }
                # Include raw_content if requested and available
                if request.include_raw_content and r.get("raw_content"):
                    result["raw_content"] = r.get("raw_content")
                results.append(result)

            # Build response
            response_data = {
                "results": results,
                "query": request.query,
                "total": len(results)
            }

            # Include answer if available
            if data.get("answer"):
                response_data["answer"] = data.get("answer")

            # Include images if available
            if data.get("images"):
                response_data["images"] = data.get("images")

            logger.info(f"Tavily search completed: {len(results)} results")
            return response_data

    except httpx.HTTPStatusError as e:
        logger.error(f"Tavily search failed: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Tavily API error: {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"Tavily search request error: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to reach Tavily API: {str(e)}")


@app.post("/api/v1/tavily/research")
async def tavily_research(
    request: TavilyResearchRequest,
    x_ami_api_key: str = Header(..., alias="X-Ami-API-Key")
):
    """
    Execute Tavily deep research via CRS

    Supports both streaming and non-streaming modes.
    Returns comprehensive analysis report with sources.
    """
    tavily_url = config_service.get("tavily.api_url", "https://api.ariseos.com/tavily")
    tavily_endpoint = f"{tavily_url.rstrip('/')}/research"

    # Build payload for Tavily research
    # Note: CRS uses "input" field instead of "query" for research endpoint
    payload = {
        "input": request.query,
        "stream": request.stream,
    }

    # Optional parameters
    if request.model:
        payload["model"] = request.model
    if request.citation_format:
        payload["citation_format"] = request.citation_format

    # CRS uses Authorization: Bearer header for authentication
    headers = {
        "Authorization": f"Bearer {x_ami_api_key}",
        "Content-Type": "application/json",
    }

    logger.info(f"Tavily research: query={request.query[:50]}..., stream={request.stream}, model={request.model}")

    try:
        if request.stream:
            # Streaming response
            async def event_generator():
                try:
                    async with httpx.AsyncClient() as client:
                        async with client.stream(
                            "POST",
                            tavily_endpoint,
                            json=payload,
                            headers=headers,
                            timeout=300.0
                        ) as response:
                            response.raise_for_status()
                            async for chunk in response.aiter_bytes():
                                yield chunk
                except httpx.HTTPStatusError as e:
                    logger.error(f"Tavily research stream failed: {e.response.status_code}")
                    error_event = f'data: {{"type": "error", "message": "HTTP {e.response.status_code}"}}\n\n'
                    yield error_event.encode('utf-8')
                except Exception as e:
                    logger.error(f"Tavily research stream error: {e}")
                    error_event = f'data: {{"type": "error", "message": "{str(e)}"}}\n\n'
                    yield error_event.encode('utf-8')

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            # Non-streaming response
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    tavily_endpoint,
                    json=payload,
                    headers=headers,
                    timeout=300.0
                )
                response.raise_for_status()
                result = response.json()
                logger.info(f"Tavily research completed")
                return result

    except httpx.HTTPStatusError as e:
        logger.error(f"Tavily research failed: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Tavily API error: {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"Tavily research request error: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to reach Tavily API: {str(e)}")


def _find_step_in_workflow(workflow: Dict, step_id: str) -> Optional[Dict]:
    """Recursively find step by ID in workflow

    Handles nested steps in foreach, if/then/else, while loops
    """
    def search_steps(steps: List[Dict]) -> Optional[Dict]:
        for step in steps:
            # Check if this is the step we're looking for
            if step.get("id") == step_id:
                return step

            # Check nested steps
            for key in ["do", "then", "else", "steps"]:
                if key in step:
                    nested = step[key]
                    if isinstance(nested, list):
                        result = search_steps(nested)
                        if result:
                            return result

        return None

    return search_steps(workflow.get("steps", []))


def _find_dom_for_step(
    workflow_dir: Path,
    step_inputs: Dict,
    page_url: str
) -> Optional[Dict]:
    """Find DOM snapshot for a step

    Strategy:
    1. Load dom_snapshots.json from workflow directory
    2. Match by xpath_hints -> find operation with matching xpath -> get dom_id
    3. Fallback: match by URL

    Args:
        workflow_dir: Workflow directory containing dom_snapshots.json
        step_inputs: Step inputs containing xpath_hints
        page_url: Current page URL for matching

    Returns:
        DOM dict if found, None otherwise
    """
    # Load dom_snapshots
    dom_snapshots_file = workflow_dir / "dom_snapshots.json"
    if not dom_snapshots_file.exists():
        logger.warning(f"dom_snapshots.json not found in {workflow_dir}")
        return None

    try:
        dom_snapshots = json.loads(dom_snapshots_file.read_text(encoding='utf-8'))
    except Exception as e:
        logger.error(f"Failed to load dom_snapshots.json: {e}")
        return None

    if not dom_snapshots:
        logger.warning("dom_snapshots.json is empty")
        return None

    logger.info(f"Loaded {len(dom_snapshots)} DOM snapshots")

    # Extract xpath_hints from step inputs
    data_req = step_inputs.get("data_requirements", {})
    xpath_hints = data_req.get("xpath_hints", {})

    # Load intents for xpath -> dom_id mapping
    intents_file = workflow_dir / "intents.json"
    intents = []
    if intents_file.exists():
        try:
            intents = json.loads(intents_file.read_text(encoding='utf-8'))
            logger.info(f"Loaded {len(intents)} intents")
        except Exception as e:
            logger.warning(f"Failed to load intents.json: {e}")

    # Strategy 1: Match xpath_hints against intent operations
    if xpath_hints and intents:
        for hint_xpath in xpath_hints.values():
            # Normalize xpath for comparison
            hint_normalized = hint_xpath.replace("'", '"')

            for intent in intents:
                operations = intent.get("operations", [])
                for op in operations:
                    element = op.get("element", {})
                    op_xpath = element.get("xpath", "")
                    dom_id = op.get("dom_id")

                    if dom_id and op_xpath:
                        op_normalized = op_xpath.replace("'", '"')
                        if op_normalized == hint_normalized:
                            if dom_id in dom_snapshots:
                                dom_data = dom_snapshots[dom_id]
                                # dom_data is {"url": ..., "dom": ...}
                                dom_dict = dom_data.get("dom") if isinstance(dom_data, dict) else dom_data
                                logger.info(f"Matched DOM via xpath_hints -> dom_id={dom_id}")
                                return dom_dict

    # Strategy 2: Match by URL
    for dom_id, dom_data in dom_snapshots.items():
        dom_url = dom_data.get("url") if isinstance(dom_data, dict) else None
        if dom_url == page_url:
            dom_dict = dom_data.get("dom") if isinstance(dom_data, dict) else dom_data
            logger.info(f"Matched DOM via URL={page_url}")
            return dom_dict

    # Strategy 3: Return first available DOM (fallback)
    if dom_snapshots:
        first_id = list(dom_snapshots.keys())[0]
        first_data = dom_snapshots[first_id]
        dom_dict = first_data.get("dom") if isinstance(first_data, dict) else first_data
        logger.warning(f"No exact match, using first DOM snapshot (dom_id={first_id})")
        return dom_dict

    return None


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
