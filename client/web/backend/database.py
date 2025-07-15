"""
统一用户数据库系统 - 供 Agentbuilder 和 BaseApp 共享使用
"""
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

# 数据库URL - 可以通过环境变量配置
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agentcrafter_users.db")

# 创建数据库引擎
engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# 创建会话
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 基础模型
Base = declarative_base()

# 用户模型
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

# 用户会话模型 (用于管理登录状态)
class UserSession(Base):
    __tablename__ = "user_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    session_token = Column(String(255), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

# 聊天历史模型
class ChatHistory(Base):
    __tablename__ = "chat_history"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    session_id = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    response = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# Agent构建会话模型
class AgentBuildSession(Base):
    __tablename__ = "agent_build_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    build_id = Column(String(100), unique=True, index=True, nullable=False)
    user_id = Column(Integer, nullable=False)
    description = Column(Text, nullable=False)  # 用户需求描述
    agent_name = Column(String(100), nullable=True)  # 可选的Agent名称
    status = Column(String(50), default="building")  # building, completed, failed
    current_step = Column(String(100), nullable=True)  # 当前构建步骤
    progress_message = Column(Text, nullable=True)  # 进度消息
    error_message = Column(Text, nullable=True)  # 错误信息
    result_data = Column(Text, nullable=True)  # 构建结果 (JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

# 生成的Agent信息模型
class GeneratedAgent(Base):
    __tablename__ = "generated_agents"
    
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(String(100), unique=True, index=True, nullable=False)
    build_session_id = Column(String(100), nullable=False)  # 关联构建会话
    user_id = Column(Integer, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    capabilities = Column(Text, nullable=True)  # JSON array
    workflow_data = Column(Text, nullable=True)  # 工作流数据 (JSON)
    code_path = Column(String(255), nullable=True)  # 生成的代码文件路径
    workflow_path = Column(String(255), nullable=True)  # 工作流文件路径
    metadata_path = Column(String(255), nullable=True)  # 元数据文件路径
    cost_analysis = Column(String(100), nullable=True)  # 成本分析
    status = Column(String(50), default="active")  # active, inactive, deleted
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# 创建数据表
def create_tables():
    Base.metadata.create_all(bind=engine)

# 获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 初始化数据库
def init_db():
    create_tables()
    print("Database initialized successfully")

if __name__ == "__main__":
    init_db()