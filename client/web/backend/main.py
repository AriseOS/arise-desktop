"""
Agentcrafter Web Backend - FastAPI 服务器
"""
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, Dict, List
import json

from database import get_db, init_db, User, ChatHistory, AgentBuildSession, GeneratedAgent
from auth import auth_service
from agent_service import agent_build_service

# 初始化数据库
init_db()

# 创建 FastAPI 应用
app = FastAPI(
    title="Agentcrafter API",
    description="Agentcrafter 用户系统和聊天 API",
    version="1.0.0"
)

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """列出用户的所有 Agent"""
    agents = agent_build_service.list_user_agents(current_user.id, db)
    
    return [AgentListItem(**agent) for agent in agents]

@app.get("/api/agents/{agent_id}/workflow")
async def get_agent_workflow(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取 Agent 的工作流数据"""
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