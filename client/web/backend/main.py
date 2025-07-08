"""
Agentcrafter Web Backend - FastAPI 服务器
"""
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from database import get_db, init_db, User, ChatHistory
from auth import auth_service

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