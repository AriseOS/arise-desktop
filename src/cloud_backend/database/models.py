"""
统一用户数据库系统 - 供 Agentbuilder 和 BaseApp 共享使用
"""
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from pathlib import Path

# 使用 ConfigService 统一管理配置
from src.cloud_backend.core.config_service import get_config

# 获取配置服务
_config_service = get_config()

# 从 baseapp.yaml 获取用户数据库配置
def get_database_url() -> str:
    """Get database URL from ConfigService"""
    db_path = _config_service.get('data.databases.users')
    if not db_path:
        raise ValueError("Database path not configured in baseapp.yaml: data.databases.users")
    
    # Expand user directory
    db_path = os.path.expanduser(db_path)
    return f"sqlite:///{db_path}"

def get_database_config() -> dict:
    """Get database configuration"""
    db_url = get_database_url()
    config = {"url": db_url}
    
    # SQLite specific configuration
    if "sqlite" in db_url:
        config["connect_args"] = {"check_same_thread": False}
    
    return config

# 数据库配置 - 通过 ConfigService 管理
DATABASE_URL = get_database_url()
db_config = get_database_config()

# 创建数据库引擎
engine = create_engine(
    db_config["url"], 
    connect_args=db_config.get("connect_args", {})
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

# Agent构建会话模型 - 重构为最简版本
class AgentBuild(Base):
    __tablename__ = "agent_builds"
    
    build_id = Column(String(255), primary_key=True)
    user_id = Column(Integer, nullable=False)
    
    # 基本信息
    user_description = Column(Text, nullable=False)
    status = Column(String(50), default="building")  # building, completed, failed
    current_step = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    
    # 构建结果
    agent_purpose = Column(Text, nullable=True)  # 解析后的Agent目的
    generated_code = Column(Text, nullable=True)  # 生成的Python代码
    workflow_config = Column(Text, nullable=True)  # 生成的YAML配置
    
    # 中间产物存储 (JSON格式)
    steps_data = Column(Text, nullable=True)  # 步骤提取结果
    step_agents_data = Column(Text, nullable=True)  # StepAgent规格数据
    agent_types_data = Column(Text, nullable=True)  # Agent类型判断结果
    workflow_data = Column(Text, nullable=True)  # BaseAgent Workflow对象数据
    
    # 时间戳
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

# 保留原有的兼容性，暂时不删除
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

# 录制会话模型 - 存储workflow录制数据
class RecordingSessionDB(Base):
    __tablename__ = "recording_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), unique=True, index=True, nullable=False)
    user_id = Column(Integer, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # 录制数据 (JSON格式)
    recording_data = Column(Text, nullable=False)  # 完整的JSON数据

    # 统计信息
    operation_count = Column(Integer, default=0)

    # 时间戳
    started_at = Column(DateTime, default=datetime.utcnow)
    stopped_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

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

# 检查数据库文件是否存在
def check_database_file():
    """检查数据库文件是否存在"""
    db_config = get_database_config()
    db_url = db_config["url"]
    
    if "sqlite" in db_url:
        # 提取SQLite文件路径
        if db_url.startswith("sqlite:///"):
            db_file_path = db_url[10:]  # 移除 "sqlite:///" 前缀
            db_file = Path(db_file_path)
            
            if not db_file.exists():
                print(f"数据库文件不存在: {db_file_path}")
                
                # 确保父目录存在
                db_file.parent.mkdir(parents=True, exist_ok=True)
                print(f"创建数据库目录: {db_file.parent}")
                
                return False
            else:
                print(f"数据库文件已存在: {db_file_path}")
                return True
    else:
        # 对于PostgreSQL、MySQL等，假设数据库服务器已配置
        print("使用远程数据库，跳过文件检查")
        return True
    
    return False

# 初始化数据库
def init_db():
    """初始化数据库 - 检查文件存在性并创建表结构"""
    print("正在检查数据库配置...")
    
    # 打印数据库配置信息
    db_url = get_database_url()
    print(f"数据库URL: {db_url}")
    
    # 检查数据库文件
    db_exists = check_database_file()
    
    # 创建表结构
    print("正在创建/更新数据库表结构...")
    create_tables()
    
    if db_exists:
        print("✅ 数据库初始化完成 (使用现有数据库)")
    else:
        print("✅ 数据库初始化完成 (创建新数据库)")
    
    return True

if __name__ == "__main__":
    init_db()