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
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# 添加项目根目录到 Python 路径
# 当前文件: src/cloud-backend/main.py
# 需要到达: agentcrafter/ (项目根目录)
project_root = Path(__file__).parent.parent.parent  # 向上3层
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)

# Load configuration early (before creating app)
from core.config_service import CloudConfigService
config_service = CloudConfigService()

# Global service instances
storage_service = None
workflow_generation_service = None

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
        workflow_generation_service = WorkflowGenerationService(llm_provider_name=llm_provider)
        print(f"✅ Workflow Generation ({llm_provider})")

        # 4. Setup logging
        log_level = config_service.get("logging.level", "INFO")
        logging.basicConfig(
            level=getattr(logging, log_level),
            format=config_service.get("logging.format", "%(asctime)s [%(levelname)8s] %(message)s")
        )
        print(f"✅ Logging: {log_level}")

        # 5. TODO: Initialize database connection
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

    if not user_id:
        raise HTTPException(400, "Missing user_id")

    if not operations:
        raise HTTPException(400, "Missing operations")

    recording_id = str(uuid.uuid4())

    # Save recording to filesystem (with task_description and user_query)
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

@app.post("/api/users/{user_id}/generate_metaflow")
async def generate_metaflow(user_id: str, data: dict):
    """
    Generate MetaFlow from user's Intent Memory Graph

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
            user_query=user_query
        )

        # Generate metaflow_id
        metaflow_id = f"metaflow_{uuid.uuid4().hex[:12]}"

        # Save MetaFlow to server filesystem
        storage_service.save_metaflow(
            user_id=user_id,
            metaflow_id=metaflow_id,
            metaflow_yaml=metaflow_yaml,
            task_description=task_description
        )

        logger.info(f"✅ MetaFlow generated and saved: {metaflow_id}")

        return {
            "metaflow_id": metaflow_id,
            "metaflow_yaml": metaflow_yaml,
            "task_description": task_description,
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
async def generate_metaflow_from_recording(recording_id: str, data: dict):
    """
    Generate MetaFlow from a specific recording (using only that recording's intents)

    This endpoint generates MetaFlow using ONLY the intents extracted from this recording,
    NOT from the user's global Intent Memory Graph. This is useful when the user wants
    to create a workflow based on a specific demonstration.

    Body:
        {
            "user_id": "user123",
            "task_description": "Search coffee on Google"
        }

    Returns:
        {
            "metaflow_id": "metaflow_xxx",
            "metaflow_yaml": "...",
            "status": "success"
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

    try:
        # Load recording data
        recording_data = storage_service.get_recording(user_id, recording_id)
        if not recording_data:
            raise HTTPException(404, f"Recording not found: {recording_id}")

        operations = recording_data.get("operations", [])
        if not operations:
            raise HTTPException(400, f"Recording {recording_id} has no operations")

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
            user_query=user_query
        )

        # Generate metaflow_id
        metaflow_id = f"metaflow_{uuid.uuid4().hex[:12]}"

        # Save MetaFlow to server filesystem
        storage_service.save_metaflow(
            user_id=user_id,
            metaflow_id=metaflow_id,
            metaflow_yaml=metaflow_yaml,
            task_description=task_description
        )

        logger.info(f"✅ MetaFlow generated and saved: {metaflow_id}")

        return {
            "metaflow_id": metaflow_id,
            "metaflow_yaml": metaflow_yaml,
            "task_description": task_description,
            "status": "success"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ MetaFlow generation from recording failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"MetaFlow generation failed: {str(e)}")


@app.post("/api/metaflows/{metaflow_id}/generate_workflow")
async def generate_workflow_from_metaflow(metaflow_id: str, data: dict):
    """
    Generate Workflow YAML from MetaFlow

    Body:
        {
            "user_id": "user123"
        }

    Returns:
        {
            "workflow_name": "workflow_xxx",
            "status": "success"
        }
    """
    user_id = data.get("user_id")

    if not user_id:
        raise HTTPException(400, "Missing user_id")

    # Load MetaFlow data
    metaflow_data = storage_service.get_metaflow(user_id, metaflow_id)
    if not metaflow_data:
        raise HTTPException(404, f"MetaFlow not found: {metaflow_id}")

    metaflow_yaml = metaflow_data.get("metaflow_yaml")
    task_description = metaflow_data.get("task_description", "")

    logger.info(f"🚀 [API] Generating Workflow from MetaFlow: {metaflow_id}")
    logger.info(f"👤 User: {user_id}")
    if task_description:
        logger.info(f"📝 Task Description: {task_description}")

    try:
        # Generate Workflow from MetaFlow
        workflow_yaml = await workflow_generation_service.generate_workflow_from_metaflow(
            metaflow_yaml=metaflow_yaml
        )

        # Extract workflow_name from YAML
        import yaml
        workflow_dict = yaml.safe_load(workflow_yaml)
        workflow_name = workflow_dict.get("name", f"workflow_{uuid.uuid4().hex[:12]}")

        # Save Workflow to server filesystem
        storage_service.save_workflow(
            user_id=user_id,
            workflow_name=workflow_name,
            workflow_yaml=workflow_yaml,
            metaflow_yaml=metaflow_yaml
        )

        logger.info(f"✅ Workflow generated and saved: {workflow_name}")

        return {
            "workflow_name": workflow_name,
            "workflow_yaml": workflow_yaml,
            "status": "success"
        }

    except Exception as e:
        logger.error(f"❌ Workflow generation failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Workflow generation failed: {str(e)}")


# ===== Workflows API =====

@app.get("/api/workflows")
async def list_workflows(user_id: str):
    """
    列出用户的所有 Workflow
    
    Query:
        user_id: 用户 ID
    
    Returns:
        [{"name": "...", "created_at": "...", ...}, ...]
    """
    if not user_id:
        raise HTTPException(400, "Missing user_id")
    
    # 从文件系统读取
    workflow_names = storage_service.list_workflows(user_id)
    
    # TODO: 从数据库读取元数据
    # workflows = db.query(Workflow).filter(Workflow.user_id == user_id).all()
    
    return [{"name": name} for name in workflow_names]

@app.get("/api/workflows/{workflow_name}/download")
async def download_workflow(workflow_name: str, user_id: str):
    """
    下载 Workflow YAML
    
    Query:
        user_id: 用户 ID
    
    Returns:
        {"yaml": "..."}
    """
    if not user_id:
        raise HTTPException(400, "Missing user_id")
    
    # 从服务器文件系统读取
    workflow_yaml = storage_service.get_workflow(user_id, workflow_name)
    
    if not workflow_yaml:
        raise HTTPException(404, f"Workflow not found: {workflow_name}")
    
    logger.info(f"Workflow downloaded: {workflow_name}")
    return {"yaml": workflow_yaml}

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
