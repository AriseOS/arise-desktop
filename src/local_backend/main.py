"""
Ami Local Backend - 用户电脑上的执行引擎和云端代理

职责：
1. 录制控制（接收 Extension 事件）
2. 执行控制（BaseAgent 执行 Workflow）
3. 云端代理（统一管理 Cloud API 调用）
4. 本地存储（Workflow 缓存、执行历史）
"""

import uvicorn
import logging
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
# 当前文件: src/local-backend/main.py
# 需要到达: agentcrafter/ (项目根目录)
project_root = Path(__file__).parent.parent.parent  # 向上3层
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title="Ami Local Backend",
    description="用户电脑上的执行引擎和云端代理",
    version="2.0.0"
)

# CORS 配置（允许 Extension 和 Desktop App 访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Desktop App 和 Extension
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局服务实例
browser_manager = None
storage_manager = None
workflow_executor = None
cloud_client = None

@app.on_event("startup")
async def startup_event():
    """启动时初始化所有服务"""
    global browser_manager, storage_manager, workflow_executor, cloud_client
    
    try:
        print("\n" + "="*80)
        print("🚀 Ami Local Backend Starting...")
        print("="*80)
        
        from src.base_app.base_app.base_agent.tools.browser_session_manager import BrowserSessionManager
        from src.base_app.base_app.server.core.config_service import ConfigService
        from services.storage_manager import StorageManager
        from services.workflow_executor import WorkflowExecutor
        from services.cloud_client import CloudClient
        
        # 1. 初始化存储管理器
        storage_manager = StorageManager()
        print(f"✅ Storage Manager initialized")
        
        # 2. 初始化浏览器会话管理器
        browser_manager = await BrowserSessionManager.get_instance()
        config_service = ConfigService()
        headless = config_service.get('agent.tools.browser.headless', False)
        
        await browser_manager.get_or_create_session(
            session_id="global",
            config_service=config_service,
            headless=headless,
            keep_alive=True
        )
        
        print(f"✅ Global browser session initialized")
        print(f"   Session ID: global")
        print(f"   Headless: {headless}")
        
        # 3. 初始化 Workflow 执行器
        workflow_executor = WorkflowExecutor()
        print(f"✅ Workflow Executor initialized")
        
        # 4. 初始化 Cloud Client
        cloud_url = os.getenv("CLOUD_API_URL", "http://localhost:9000")
        cloud_client = CloudClient(base_url=cloud_url)
        print(f"✅ Cloud Client initialized: {cloud_url}")
        
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"❌ Failed to initialize services: {e}")
        import traceback
        traceback.print_exc()

@app.on_event("shutdown")
async def shutdown_event():
    """关闭时清理资源"""
    global browser_manager
    if browser_manager:
        await browser_manager.cleanup_all()
    print("✅ Local Backend shutdown complete")

# WebSocket 路由（供 Extension 使用）
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Extension 的 WebSocket 连接"""
    await websocket.accept()
    print("✅ WebSocket connection established")
    
    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")
            
            # 根据消息类型路由到对应的处理器
            if message_type == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {message_type}"
                })
                
    except WebSocketDisconnect:
        print("❌ WebSocket disconnected")
    except Exception as e:
        print(f"❌ WebSocket error: {e}")

# HTTP 路由
@app.get("/health")
def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "service": "local-backend",
        "version": "2.0.0",
        "browser_ready": browser_manager is not None,
        "services": {
            "storage": storage_manager is not None,
            "executor": workflow_executor is not None,
            "cloud": cloud_client is not None
        }
    }

@app.get("/")
def root():
    """根路径"""
    return {
        "service": "Ami Local Backend",
        "version": "2.0.0",
        "docs": "/docs"
    }

# ===== Workflow API =====

@app.post("/api/workflows/execute")
async def execute_workflow(data: dict):
    """
    执行 Workflow
    
    Body:
        {
            "user_id": "user123",
            "workflow_name": "从-allegro-抓取咖啡"
        }
        
    Returns:
        {"task_id": "..."}
    """
    user_id = data.get("user_id")
    workflow_name = data.get("workflow_name")
    
    if not user_id or not workflow_name:
        raise HTTPException(400, "Missing user_id or workflow_name")
    
    # 加载 Workflow YAML
    workflow_yaml = storage_manager.get_workflow(user_id, workflow_name)
    if not workflow_yaml:
        raise HTTPException(404, f"Workflow not found: {workflow_name}")
    
    # 执行
    task_id = await workflow_executor.execute_workflow(
        user_id=user_id,
        workflow_yaml=workflow_yaml
    )
    
    return {"task_id": task_id}

@app.get("/api/workflows/status/{task_id}")
def get_workflow_status(task_id: str):
    """
    查询执行状态
    
    Returns:
        {
            "task_id": "...",
            "status": "running|completed|failed",
            "progress": 0-100,
            "result": {...}
        }
    """
    status = workflow_executor.get_task_status(task_id)
    if not status:
        raise HTTPException(404, f"Task not found: {task_id}")
    
    return status

@app.get("/api/workflows/list")
def list_workflows(user_id: str):
    """
    列出所有 Workflow
    
    Query:
        user_id: 用户 ID
        
    Returns:
        [{"workflow_name": "...", "cached_at": "...", ...}, ...]
    """
    if not user_id:
        raise HTTPException(400, "Missing user_id")
    
    workflows = storage_manager.list_workflows(user_id)
    return workflows

@app.get("/api/workflows/{workflow_name}/history")
def get_execution_history(workflow_name: str, user_id: str, limit: int = 10):
    """
    获取执行历史
    
    Query:
        user_id: 用户 ID
        limit: 最多返回多少条（默认 10）
    """
    if not user_id:
        raise HTTPException(400, "Missing user_id")
    
    history = storage_manager.get_execution_history(user_id, workflow_name, limit)
    return history

# ===== Cloud Proxy API =====

@app.post("/api/cloud/login")
async def cloud_login(data: dict):
    """
    登录云端
    
    Body:
        {"username": "...", "password": "..."}
        
    Returns:
        {"token": "...", "user_id": ...}
    """
    username = data.get("username")
    password = data.get("password")
    
    if not username or not password:
        raise HTTPException(400, "Missing username or password")
    
    result = await cloud_client.login(username, password)
    return result

@app.post("/api/cloud/workflows/download")
async def download_workflow(data: dict):
    """
    从云端下载 Workflow
    
    Body:
        {
            "user_id": "user123",
            "workflow_name": "从-allegro-抓取咖啡"
        }
        
    Returns:
        {"success": true}
    """
    user_id = data.get("user_id")
    workflow_name = data.get("workflow_name")
    
    if not user_id or not workflow_name:
        raise HTTPException(400, "Missing user_id or workflow_name")
    
    # 从云端下载
    workflow_yaml = await cloud_client.download_workflow(workflow_name)
    
    # 保存到本地
    storage_manager.save_workflow(user_id, workflow_name, workflow_yaml)
    
    return {"success": True}

# ===== Storage API =====

@app.get("/api/storage/stats")
def get_storage_stats(user_id: str):
    """
    获取存储统计
    
    Query:
        user_id: 用户 ID
    """
    if not user_id:
        raise HTTPException(400, "Missing user_id")
    
    stats = storage_manager.get_storage_stats(user_id)
    return stats

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
