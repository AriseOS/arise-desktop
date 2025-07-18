"""
AgentCrafter Backend Configuration
配置文件 - 管理数据库连接和其他后端设置
"""
import os
from typing import Optional
from pathlib import Path

def load_env_file(env_path: str = None):
    """加载 .env 文件"""
    if env_path is None:
        # 查找 .env 文件的位置
        current_dir = Path(__file__).parent.parent  # client/web/
        env_path = current_dir / ".env"
        
        if not env_path.exists():
            # 也尝试查找项目根目录的 .env
            root_dir = current_dir.parent.parent # agentcrafter/
            env_path = root_dir / ".env"
    
    env_path = Path(env_path)
    if not env_path.exists():
        return  # 没有 .env 文件，使用系统环境变量
    
    # 读取并解析 .env 文件
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过注释和空行
                if not line or line.startswith('#'):
                    continue
                
                # 解析 KEY=VALUE 格式
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # 移除引号
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    # 只有当环境变量不存在时才设置
                    if key not in os.environ:
                        os.environ[key] = value
    except Exception as e:
        print(f"警告: 无法加载 .env 文件 {env_path}: {e}")

# 在模块加载时自动加载 .env 文件
load_env_file()

class BackendConfig:
    """后端配置类"""
    
    def __init__(self):
        # 获取项目根目录 (通过环境变量或自动检测)
        self.project_root = self._find_project_root()
        self.backend_dir = Path(__file__).parent
        
        # 数据库配置
        self.database_url = self._get_database_url()
        
        # 服务器配置
        self.host = os.getenv("BACKEND_HOST", "0.0.0.0")
        self.port = int(os.getenv("BACKEND_PORT", "8000"))
        self.reload = os.getenv("BACKEND_RELOAD", "true").lower() == "true"
        
        # JWT配置
        self.secret_key = os.getenv("SECRET_KEY", "your-secret-key-here-change-in-production")
        self.algorithm = "HS256"
        self.access_token_expire_minutes = 30
        
        # 日志配置
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
    
    def _find_project_root(self) -> Path:
        """查找项目根目录"""
        # 方式1: 通过环境变量指定
        project_root_env = os.getenv("PROJECT_ROOT")
        if project_root_env:
            return Path(project_root_env).resolve()
        
        # 方式2: 默认假设 - 基于当前文件位置推算
        # client/web/backend/config.py -> ../../../ -> agentcrafter/
        return Path(__file__).parent.parent.parent.parent
        
    def _get_database_url(self) -> str:
        """获取数据库URL配置"""
        # 从环境变量获取
        env_db_url = os.getenv("DATABASE_URL")
        if env_db_url:
            return env_db_url
            
        # 从配置文件获取数据库路径
        db_path = os.getenv("DATABASE_PATH")
        if db_path:
            # 如果是相对路径，转换为绝对路径
            if not os.path.isabs(db_path):
                db_path = os.path.join(self.project_root, db_path)
            return f"sqlite:///{db_path}"
            
        # 默认配置：使用backend目录下的数据库文件
        default_db_path = self.backend_dir / "agentcrafter_users.db"
        return f"sqlite:///{default_db_path}"
    
    def get_database_config(self) -> dict:
        """获取数据库连接配置"""
        config = {"url": self.database_url}
        
        # SQLite特殊配置
        if "sqlite" in self.database_url:
            config["connect_args"] = {"check_same_thread": False}
            
        return config
    
    def get_server_config(self) -> dict:
        """获取服务器配置"""
        return {
            "host": self.host,
            "port": self.port,
            "reload": self.reload,
            "log_level": self.log_level.lower()
        }
    
    def get_jwt_config(self) -> dict:
        """获取JWT配置"""
        return {
            "secret_key": self.secret_key,
            "algorithm": self.algorithm,
            "access_token_expire_minutes": self.access_token_expire_minutes
        }

# 全局配置实例
config = BackendConfig()

# 便捷函数
def get_database_url() -> str:
    """获取数据库URL"""
    return config.database_url

def get_database_config() -> dict:
    """获取数据库配置"""
    return config.get_database_config()

def get_server_config() -> dict:
    """获取服务器配置"""
    return config.get_server_config()

def get_jwt_config() -> dict:
    """获取JWT配置"""
    return config.get_jwt_config()

# 打印配置信息（用于调试）
def print_config():
    """打印当前配置"""
    print("=== AgentCrafter Backend Configuration ===")
    print(f"Database URL: {config.database_url}")
    print(f"Server: {config.host}:{config.port}")
    print(f"Reload: {config.reload}")
    print(f"Log Level: {config.log_level}")
    print("==========================================")

if __name__ == "__main__":
    print_config()