"""
Agentcrafter Web Backend - FastAPI 服务器
"""
import uvicorn
import logging
from fastapi import FastAPI, HTTPException, Depends, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, Dict, List
import json

logger = logging.getLogger(__name__)

from database import get_db, init_db, User, ChatHistory, AgentBuildSession, GeneratedAgent
from auth import auth_service
from agent_service import agent_build_service
from recording_service import recording_service
from storage_service import storage_service
from learning_service import learning_service
from workflow_service import workflow_service

# 初始化数据库
init_db()

# 创建 FastAPI 应用
app = FastAPI(
    title="Agentcrafter API",
    description="Agentcrafter 用户系统和聊天 API",
    version="1.0.0"
)

# Global browser session manager
global_browser_session_info = None

# Global workflow task status storage
workflow_tasks: Dict[str, Dict] = {}

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 安全配置
security = HTTPBearer()

# WebSocket 连接管理器
class ConnectionManager:
    def __init__(self):
        # 存储构建进度连接: build_id -> List[WebSocket]
        self.build_connections: Dict[str, List[WebSocket]] = {}
        # 存储Agent对话连接: agent_id -> List[WebSocket]  
        self.chat_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect_build(self, websocket: WebSocket, build_id: str):
        await websocket.accept()
        if build_id not in self.build_connections:
            self.build_connections[build_id] = []
        self.build_connections[build_id].append(websocket)
        print(f"✅ 构建进度连接已建立: {build_id}")
    
    def disconnect_build(self, websocket: WebSocket, build_id: str):
        if build_id in self.build_connections:
            self.build_connections[build_id].remove(websocket)
            if not self.build_connections[build_id]:
                del self.build_connections[build_id]
        print(f"❌ 构建进度连接已断开: {build_id}")
    
    async def broadcast_build_progress(self, build_id: str, message: dict):
        if build_id in self.build_connections:
            disconnected = []
            for connection in self.build_connections[build_id]:
                try:
                    await connection.send_text(json.dumps(message))
                except:
                    disconnected.append(connection)
            
            # 清理断开的连接
            for conn in disconnected:
                self.disconnect_build(conn, build_id)
    
    async def connect_chat(self, websocket: WebSocket, agent_id: str):
        await websocket.accept()
        if agent_id not in self.chat_connections:
            self.chat_connections[agent_id] = []
        self.chat_connections[agent_id].append(websocket)
        print(f"✅ Agent对话连接已建立: {agent_id}")
    
    def disconnect_chat(self, websocket: WebSocket, agent_id: str):
        if agent_id in self.chat_connections:
            self.chat_connections[agent_id].remove(websocket)
            if not self.chat_connections[agent_id]:
                del self.chat_connections[agent_id]
        print(f"❌ Agent对话连接已断开: {agent_id}")

manager = ConnectionManager()

# 设置 WebSocket 管理器到 agent_build_service
agent_build_service.set_websocket_manager(manager)

# Startup event: Initialize global browser session
@app.on_event("startup")
async def startup_event():
    """Initialize global browser session on backend startup"""
    global global_browser_session_info

    try:
        print("\n" + "="*80)
        print("🌐 Initializing global browser session...")
        print("="*80)

        from src.base_app.base_app.base_agent.tools.browser_session_manager import BrowserSessionManager
        from src.base_app.base_app.server.core.config_service import ConfigService

        # Get browser session manager instance
        session_manager = await BrowserSessionManager.get_instance()

        # Load config service
        config_service = ConfigService()

        # Get browser config
        headless = config_service.get('agent.tools.browser.headless', False)

        # Create global browser session with fixed session_id="global"
        global_browser_session_info = await session_manager.get_or_create_session(
            session_id="global",
            config_service=config_service,
            headless=headless,
            keep_alive=True
        )

        print(f"✅ Global browser session created successfully!")
        print(f"   Session ID: global")
        print(f"   Headless: {headless}")
        print("="*80 + "\n")

    except Exception as e:
        print(f"❌ Failed to initialize global browser session: {e}")
        import traceback
        traceback.print_exc()
        # Don't fail server startup if browser initialization fails
        global_browser_session_info = None

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup global browser session on backend shutdown"""
    global global_browser_session_info

    if global_browser_session_info:
        try:
            print("\n" + "="*80)
            print("🔻 Cleaning up global browser session...")
            print("="*80)

            from src.base_app.base_app.base_agent.tools.browser_session_manager import BrowserSessionManager

            session_manager = await BrowserSessionManager.get_instance()
            await session_manager.close_session("global", force=True)

            print("✅ Global browser session closed successfully!")
            print("="*80 + "\n")

        except Exception as e:
            print(f"❌ Failed to cleanup global browser session: {e}")

# Pydantic 模型
class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    full_name: Optional[str] = None

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    is_active: bool
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    session_id: str

# Agent 构建相关模型
class AgentBuildRequest(BaseModel):
    description: str
    agent_name: Optional[str] = None

class AgentBuildResponse(BaseModel):
    build_id: str
    status: str
    message: str

class BuildStatusResponse(BaseModel):
    build_id: str
    status: str
    current_step: Optional[str] = None
    progress_message: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None

class AgentInfo(BaseModel):
    agent_id: str
    name: str
    description: str
    capabilities: list
    workflow_data: dict
    cost_analysis: str
    created_at: str

class AgentListItem(BaseModel):
    agent_id: str
    name: str
    description: str
    cost_analysis: str
    created_at: str

# 依赖项：获取当前用户
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    token = credentials.credentials
    user = auth_service.get_current_user(db, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

# API 路由
@app.post("/api/register", response_model=TokenResponse)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """用户注册"""
    try:
        # 创建用户
        user = auth_service.create_user(
            db, 
            user_data.username, 
            user_data.email, 
            user_data.password,
            user_data.full_name
        )
        
        # 创建访问令牌
        access_token = auth_service.create_access_token(
            data={"sub": user.username}
        )
        
        # 更新最后登录时间
        user.last_login = datetime.utcnow()
        db.commit()
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                full_name=user.full_name,
                is_active=user.is_active,
                created_at=user.created_at
            )
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="注册失败")

@app.post("/api/login", response_model=TokenResponse)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """用户登录"""
    user = auth_service.authenticate_user(db, user_data.username, user_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 创建访问令牌
    access_token = auth_service.create_access_token(
        data={"sub": user.username}
    )
    
    # 更新最后登录时间
    user.last_login = datetime.utcnow()
    db.commit()
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            created_at=user.created_at
        )
    )

@app.get("/api/ping")
async def ping(current_user: User = Depends(get_current_user)):
    """简单的认证检查 - 用于定期验证token是否有效"""
    return {"status": "ok", "user_id": current_user.id}

@app.get("/api/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """获取当前用户信息"""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        created_at=current_user.created_at
    )

@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    chat_data: ChatMessage, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """聊天接口"""
    # 这里可以集成实际的AI聊天逻辑
    # 目前返回简单的回复
    response_text = f"你好 {current_user.username}！你说：{chat_data.message}"
    
    # 生成会话ID
    session_id = chat_data.session_id or f"session_{current_user.id}_{datetime.utcnow().timestamp()}"
    
    # 保存聊天记录
    chat_record = ChatHistory(
        user_id=current_user.id,
        session_id=session_id,
        message=chat_data.message,
        response=response_text
    )
    db.add(chat_record)
    db.commit()
    
    return ChatResponse(
        response=response_text,
        session_id=session_id
    )

# Agent 构建相关 API
@app.post("/api/agents/build", response_model=AgentBuildResponse)
async def build_agent(
    build_request: AgentBuildRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """开始构建 Agent"""
    try:
        result = await agent_build_service.start_agent_build(
            user_id=current_user.id,
            description=build_request.description,
            agent_name=build_request.agent_name,
            db=db
        )
        
        return AgentBuildResponse(
            build_id=result["build_id"],
            status=result["status"],
            message=result["message"]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"构建启动失败: {str(e)}")

@app.get("/api/agents/build/{build_id}/status", response_model=BuildStatusResponse)
async def get_build_status(
    build_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取构建状态"""
    status = agent_build_service.get_build_status(build_id, db)
    
    if not status:
        raise HTTPException(status_code=404, detail="构建会话不存在")
    
    # 验证用户权限
    build_session = db.query(AgentBuildSession).filter(
        AgentBuildSession.build_id == build_id,
        AgentBuildSession.user_id == current_user.id
    ).first()
    
    if not build_session:
        raise HTTPException(status_code=403, detail="无权访问此构建会话")
    
    return BuildStatusResponse(**status)

@app.get("/api/agents/{agent_id}", response_model=AgentInfo)
async def get_agent_info(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取生成的 Agent 信息"""
    agent_info = agent_build_service.get_generated_agent(agent_id, current_user.id, db)
    
    if not agent_info:
        raise HTTPException(status_code=404, detail="Agent 不存在或无权访问")
    
    return AgentInfo(**agent_info)

@app.get("/api/agents", response_model=list[AgentListItem])
async def list_user_agents(
    default: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """列出用户的所有 Agent"""
    agents = agent_build_service.list_user_agents(current_user.id, db, default=default)

    return [AgentListItem(**agent) for agent in agents]

@app.get("/api/agents/{agent_id}/workflow")
async def get_agent_workflow(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取 Agent 的工作流数据"""
    # Handle sample workflow
    if agent_id == "sample-workflow":
        return {
            "agent_id": agent_id,
            "steps": [
                {
                    "id": "start",
                    "name": "Start",
                    "type": "start",
                    "description": "Browser session sharing test workflow start"
                },
                {
                    "id": "get-example-title",
                    "name": "Get Example.com Title",
                    "type": "scraper_agent",
                    "description": "Visit example.com and extract page title"
                },
                {
                    "id": "get-baidu-hot",
                    "name": "Get Baidu Hot Search",
                    "type": "scraper_agent",
                    "description": "Access Baidu hot search page and get the first hot search term"
                },
                {
                    "id": "summarize-results",
                    "name": "Summarize Results",
                    "type": "text_agent",
                    "description": "Summarize the collected data"
                },
                {
                    "id": "prepare-output",
                    "name": "Prepare Output",
                    "type": "text_agent",
                    "description": "Format the final output"
                },
                {
                    "id": "end",
                    "name": "End",
                    "type": "end",
                    "description": "Workflow completed"
                }
            ],
            "connections": [
                {"from": "start", "to": "get-example-title"},
                {"from": "get-example-title", "to": "get-baidu-hot"},
                {"from": "get-baidu-hot", "to": "summarize-results"},
                {"from": "summarize-results", "to": "prepare-output"},
                {"from": "prepare-output", "to": "end"}
            ],
            "metadata": {
                "name": "Browser Session Test Workflow",
                "description": "Sample workflow demonstrating browser automation and data collection",
                "capabilities": ["browser_automation", "data_extraction", "text_processing"],
                "cost_analysis": "sample"
            }
        }

    agent_info = agent_build_service.get_generated_agent(agent_id, current_user.id, db)

    if not agent_info:
        raise HTTPException(status_code=404, detail="Agent 不存在或无权访问")

    return {
        "agent_id": agent_id,
        "workflow": agent_info["workflow_data"],
        "metadata": {
            "name": agent_info["name"],
            "description": agent_info["description"],
            "capabilities": agent_info["capabilities"],
            "cost_analysis": agent_info["cost_analysis"]
        }
    }

# 添加执行工作流的API接口
@app.get("/api/agents/workflow/{workflow_name}/execute")
async def execute_workflow(
    workflow_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """执行指定的工作流

    Args:
        workflow_name: Workflow name to execute
    """
    print(f"Received execute workflow request:")
    print(f"  Workflow Name: {workflow_name}")
    print(f"  User ID: {current_user.id}")
    print(f"  User Name: {current_user.username}")

    from base_app.base_agent.core.base_agent import BaseAgent
    from base_app.base_agent.core.schemas import AgentConfig
    from base_app.base_agent.workflows.workflow_loader import load_workflow
    from base_app.server.core.config_service import ConfigService
    import asyncio
    import uuid

    # Generate task ID
    task_id = f"task_{workflow_name}_{uuid.uuid4().hex[:8]}"

    # Initialize task status
    workflow_tasks[task_id] = {
        "task_id": task_id,
        "workflow_name": workflow_name,
        "status": "running",
        "progress": 0,
        "message": "Workflow execution started",
        "user_id": current_user.id,
        "started_at": datetime.utcnow().isoformat(),
        "completed_at": None,
        "result": None,
        "error": None
    }

    async def run_workflow_async(task_id: str):
        try:
            # Update status
            workflow_tasks[task_id]["message"] = "Initializing workflow"
            workflow_tasks[task_id]["progress"] = 10

            # 初始化配置服务
            config_service = ConfigService()

            # 获取LLM配置
            llm_provider = config_service.get('agent.llm.provider', 'openai')
            llm_model = config_service.get('agent.llm.model', 'gpt-4o')
            api_key = config_service.get('agent.llm.api_key')

            # 创建BaseAgent配置
            agent_config = AgentConfig(
                name="WorkflowTestRunner",
                llm_provider=llm_provider,
                llm_model=llm_model,
                api_key=api_key or ""
            )

            # 创建provider配置
            provider_config = {
                'type': llm_provider,
                'api_key': api_key if api_key else None,
                'model_name': llm_model
            }

            workflow_tasks[task_id]["message"] = "Creating BaseAgent instance"
            workflow_tasks[task_id]["progress"] = 20

            # 创建BaseAgent实例 (传递 user_id 实现 Memory 隔离)
            base_agent = BaseAgent(
                agent_config,
                config_service=config_service,
                provider_config=provider_config,
                user_id=str(current_user.id)  # 传递用户ID，同一用户的多次请求可以共享 Memory（如脚本缓存）
            )

            # 初始化BaseAgent
            workflow_tasks[task_id]["message"] = "Initializing BaseAgent"
            workflow_tasks[task_id]["progress"] = 30
            await base_agent.initialize()

            # 加载工作流
            workflow_tasks[task_id]["message"] = "Loading workflow"
            workflow_tasks[task_id]["progress"] = 40
            workflow = load_workflow(workflow_name)

            # Force workflow to use global browser session
            original_workflow_name = workflow.name
            workflow.name = "global"  # Force use global session
            print(f"🔄 Forcing workflow '{original_workflow_name}' to use global browser session")

            # 执行工作流
            workflow_tasks[task_id]["message"] = "Executing workflow"
            workflow_tasks[task_id]["progress"] = 50

            result = await base_agent.run_workflow(
                workflow=workflow,
                input_data={}
            )

            # Update completion status
            workflow_tasks[task_id]["status"] = "completed"
            workflow_tasks[task_id]["progress"] = 100
            workflow_tasks[task_id]["message"] = "Workflow execution completed"
            workflow_tasks[task_id]["completed_at"] = datetime.utcnow().isoformat()
            workflow_tasks[task_id]["result"] = {
                "success": result.success,
                "data": str(result.final_result) if hasattr(result, 'final_result') else None
            }

            print(f"✅ Workflow execution completed with success: {result.success}")
            return result
        except Exception as e:
            # Update error status
            workflow_tasks[task_id]["status"] = "failed"
            workflow_tasks[task_id]["message"] = f"Workflow execution failed: {str(e)}"
            workflow_tasks[task_id]["completed_at"] = datetime.utcnow().isoformat()
            workflow_tasks[task_id]["error"] = str(e)

            print(f"❌ Failed to execute workflow: {e}")
            import traceback
            traceback.print_exc()

    # 在后台执行工作流
    asyncio.create_task(run_workflow_async(task_id))
    print(f"Started workflow execution for {workflow_name} with task_id: {task_id}")

    return {
        "success": True,
        "task_id": task_id,
        "message": f"Workflow {workflow_name} execution started",
        "workflow_name": workflow_name,
        "user_id": current_user.id,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/agents/workflow/task/{task_id}/status")
async def get_workflow_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get workflow task execution status

    Args:
        task_id: Task ID returned from execute endpoint
    """
    if task_id not in workflow_tasks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    task_info = workflow_tasks[task_id]

    # Verify user owns this task
    if task_info["user_id"] != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized to access this task"
        )

    return task_info

@app.get("/api/agents/workflow/{workflow_name}/results")
async def get_workflow_results(
    workflow_name: str,
    begin: Optional[str] = None,
    end: Optional[str] = None,
    limit: Optional[int] = None,
    current_user: User = Depends(get_current_user)
):
    """Get results from workflow executions stored in storage.db

    Args:
        workflow_name: Name of the workflow (e.g., 'allegro-coffee-collection-workflow')
        begin: Optional start time filter (ISO format, e.g., '2025-10-20T19:00:00')
        end: Optional end time filter (ISO format, e.g., '2025-10-20T20:00:00')
        limit: Optional limit on number of results

    Returns:
        Results data from the workflow's storage collection
    """
    import aiosqlite
    from pathlib import Path

    # Get storage database path
    storage_db_path = Path.home() / ".local/share/baseapp/storage.db"

    # Map workflow name to collection name(s)
    # Single collection workflows use string, multi-collection workflows use list
    workflow_collection_map = {
        "allegro-coffee-collection-workflow": "allegro_coffee_products",
        "amazon-coffee-collection-workflow": "amazon_coffee_products",
        "coffee-market-analysis-workflow": ["allegro_products", "amazon_products"],
        "producthunt-weekly-leaderboard-scraper": "producthunt_weekly_products"
    }

    # Determine collections to query
    if workflow_name in workflow_collection_map:
        collection_config = workflow_collection_map[workflow_name]
        collections = collection_config if isinstance(collection_config, list) else [collection_config]
    else:
        # Generic: use workflow name as collection
        collection = workflow_name.replace("-workflow", "").replace("-", "_")
        collections = [collection]

    try:
        async with aiosqlite.connect(str(storage_db_path)) as sqlite_db:
            sqlite_db.row_factory = aiosqlite.Row

            all_results = {}
            total_count = 0

            # Query each collection
            for collection in collections:
                table_name = f"{collection}_{current_user.id}"

                # Build query with time range filter
                query = f"SELECT * FROM {table_name}"
                params = []
                conditions = []

                if begin:
                    conditions.append("created_at >= ?")
                    params.append(begin)

                if end:
                    conditions.append("created_at <= ?")
                    params.append(end)

                if conditions:
                    query += " WHERE " + " AND ".join(conditions)

                query += " ORDER BY created_at DESC"

                if limit:
                    query += " LIMIT ?"
                    params.append(limit)

                try:
                    cursor = await sqlite_db.execute(query, params)
                    rows = await cursor.fetchall()

                    # Convert to list of dicts
                    results = [dict(row) for row in rows]
                    all_results[collection] = results
                    total_count += len(results)
                except Exception as e:
                    # If table doesn't exist or query fails, skip this collection
                    print(f"Warning: Failed to query {table_name}: {str(e)}")
                    all_results[collection] = []

            return {
                "workflow_name": workflow_name,
                "collections": list(all_results.keys()),
                "total_results": total_count,
                "time_range": {
                    "begin": begin,
                    "end": end
                },
                "results": all_results
            }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query workflow results: {str(e)}"
        )

# WebSocket 路由

@app.websocket("/ws/agents/build/{build_id}")
async def websocket_build_progress(websocket: WebSocket, build_id: str):
    """WebSocket 构建进度推送"""
    await manager.connect_build(websocket, build_id)
    try:
        while True:
            # 保持连接，等待客户端消息或连接断开
            data = await websocket.receive_text()
            # 可以处理客户端发送的消息，比如停止构建请求
            message = json.loads(data)
            if message.get("action") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        manager.disconnect_build(websocket, build_id)

@app.websocket("/ws/agents/{agent_id}/chat")  
async def websocket_agent_chat(websocket: WebSocket, agent_id: str):
    """WebSocket Agent 对话"""
    await manager.connect_chat(websocket, agent_id)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "chat":
                # TODO: 处理与Agent的对话
                # 这里需要调用生成的Agent进行对话
                user_message = message.get("message", "")
                
                # 模拟Agent回复
                response = {
                    "type": "chat_response",
                    "message": f"Agent回复: {user_message}",
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                await websocket.send_text(json.dumps(response))
            
    except WebSocketDisconnect:
        manager.disconnect_chat(websocket, agent_id)

# ===== Recording API =====

class RecordingStartRequest(BaseModel):
    title: str
    description: Optional[str] = ""

class RecordingStopRequest(BaseModel):
    session_id: str

class RecordingOperationRequest(BaseModel):
    session_id: str
    operation: dict

# Learning Phase Models
class ExtractIntentsRequest(BaseModel):
    session_id: str

class GenerateMetaflowRequest(BaseModel):
    session_id: str

# Workflow Models
class GenerateWorkflowRequest(BaseModel):
    session_id: str

@app.post("/api/recording/start")
async def start_recording(
    request: RecordingStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start a new workflow recording session"""
    # Create recording session
    result = await recording_service.create_session(
        title=request.title,
        description=request.description or "",
        user_id=current_user.id
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "Failed to start recording")
        )

    return result

@app.post("/api/recording/stop")
async def stop_recording(
    request: RecordingStopRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Stop a recording session and return captured operations"""
    from database import RecordingSessionDB
    import json

    # Stop recording session
    result = await recording_service.stop_session(
        session_id=request.session_id,
        user_id=current_user.id
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.get("error", "Recording session not found")
        )

    # Get session data for JSON export
    session_data = await recording_service.get_session_data(
        session_id=request.session_id,
        user_id=current_user.id
    )

    # Format as standard JSON structure
    from datetime import datetime
    export_data = {
        "session_info": {
            "session_id": request.session_id,
            "title": session_data.get("title", ""),
            "description": session_data.get("description", ""),
            "start_time": session_data.get("start_time", datetime.utcnow().isoformat()),
            "total_operations": len(result.get("operations", []))
        },
        "operations": result.get("operations", [])
    }

    # Print JSON data before saving
    print(f"\n{'='*80}")
    print(f"📝 Recording Session Completed: {request.session_id}")
    print(f"{'='*80}")
    print("\n🎬 Generated JSON Structure:")
    print(json.dumps(export_data, indent=2, ensure_ascii=False))
    print(f"\n{'='*80}")

    # Save to database
    try:
        db_session = RecordingSessionDB(
            session_id=request.session_id,
            user_id=current_user.id,
            title=session_data.get("title", ""),
            description=session_data.get("description", ""),
            recording_data=json.dumps(export_data, ensure_ascii=False),
            operation_count=len(result.get("operations", [])),
            started_at=datetime.fromisoformat(session_data.get("start_time")),
            stopped_at=datetime.utcnow()
        )

        db.add(db_session)
        db.commit()
        db.refresh(db_session)

        print(f"✅ Recording saved to database with ID: {db_session.id}")
        print(f"{'='*80}\n")

    except Exception as e:
        print(f"❌ Failed to save recording to database: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()

    # Save to file system storage
    try:
        storage_service.save_learning_operations(
            user_id=current_user.id,
            session_id=request.session_id,
            operations=result.get("operations", []),
            title=session_data.get("title", ""),
            description=session_data.get("description", ""),
            started_at=session_data.get("start_time", datetime.utcnow().isoformat()),
            stopped_at=datetime.utcnow().isoformat()
        )
        print(f"✅ Recording saved to file system storage")
    except Exception as e:
        print(f"❌ Failed to save recording to file system: {e}")
        import traceback
        traceback.print_exc()

    return result

@app.get("/api/recording/status/{session_id}")
async def get_recording_status(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get status of a recording session"""
    # Get session status
    status_data = await recording_service.get_session_status(
        session_id=session_id,
        user_id=current_user.id
    )

    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording session not found"
        )

    return status_data

@app.post("/api/recording/operation")
async def add_recording_operation(
    request: RecordingOperationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add an operation to a recording session (from Chrome extension)"""
    session_id = request.session_id

    # Get session
    if session_id not in recording_service.active_sessions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording session not found"
        )

    session = recording_service.active_sessions[session_id]

    # Verify user owns this session
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized"
        )

    # Add operation
    session.add_operation(request.operation)

    return {
        "success": True,
        "operation_count": len(session.operation_list)
    }

# ===== Learning Phase APIs =====

@app.post("/api/learning/extract-intents")
async def extract_intents(
    request: ExtractIntentsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Extract intents from recorded operations"""
    try:
        result = await learning_service.extract_intents(
            user_id=current_user.id,
            session_id=request.session_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Intent extraction failed: {e}")
        raise HTTPException(status_code=500, detail=f"Intent extraction failed: {str(e)}")

@app.post("/api/learning/generate-metaflow")
async def generate_metaflow(
    request: GenerateMetaflowRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate MetaFlow from extracted intents"""
    try:
        result = await learning_service.generate_metaflow(
            user_id=current_user.id,
            session_id=request.session_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"MetaFlow generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"MetaFlow generation failed: {str(e)}")

@app.get("/api/learning/sessions")
async def list_learning_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all learning sessions for current user"""
    sessions = learning_service.list_sessions(current_user.id)
    return {
        "success": True,
        "sessions": sessions,
        "total": len(sessions)
    }

@app.get("/api/learning/sessions/{session_id}")
async def get_learning_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get learning session details"""
    session = learning_service.get_session_status(current_user.id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "success": True,
        "session": session
    }

@app.delete("/api/learning/sessions/{session_id}")
async def delete_learning_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a learning session"""
    success = learning_service.delete_session(current_user.id, session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "success": True,
        "session_id": session_id,
        "message": "Session deleted successfully"
    }

# ===== Workflow Management APIs =====

@app.post("/api/workflows/generate")
async def generate_workflow(
    request: GenerateWorkflowRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate workflow from MetaFlow"""
    try:
        result = await workflow_service.generate_workflow(
            user_id=current_user.id,
            session_id=request.session_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Workflow generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Workflow generation failed: {str(e)}")

@app.get("/api/workflows")
async def list_workflows(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all workflows for current user"""
    workflows = workflow_service.list_workflows(current_user.id)
    return {
        "success": True,
        "workflows": workflows,
        "total": len(workflows)
    }

@app.get("/api/workflows/{workflow_name}")
async def get_workflow_details(
    workflow_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get workflow details"""
    workflow = workflow_service.get_workflow(current_user.id, workflow_name)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {
        "success": True,
        "workflow": workflow
    }

@app.delete("/api/workflows/{workflow_name}")
async def delete_workflow(
    workflow_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a workflow"""
    success = workflow_service.delete_workflow(current_user.id, workflow_name)
    if not success:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {
        "success": True,
        "workflow_name": workflow_name,
        "message": "Workflow deleted successfully"
    }

# ===== Workflow Execution APIs =====

@app.post("/api/workflows/{workflow_name}/execute")
async def execute_workflow_new(
    workflow_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Execute a workflow"""
    try:
        result = await workflow_service.execute_workflow(
            user_id=current_user.id,
            workflow_name=workflow_name
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Workflow execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Workflow execution failed: {str(e)}")

@app.get("/api/workflows/executions/{task_id}")
async def get_execution_status_new(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get workflow execution status"""
    execution = workflow_service.get_execution_status(current_user.id, task_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return {
        "success": True,
        "execution": execution
    }

@app.get("/api/workflows/{workflow_name}/executions")
async def list_workflow_executions(
    workflow_name: str,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List execution history for a workflow"""
    executions = workflow_service.list_executions(current_user.id, workflow_name, limit)
    return {
        "success": True,
        "workflow_name": workflow_name,
        "executions": executions,
        "total": len(executions)
    }

@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "service": "agentcrafter-backend"}

@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Agentcrafter Backend API",
        "version": "1.0.0",
        "docs": "/docs"
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)