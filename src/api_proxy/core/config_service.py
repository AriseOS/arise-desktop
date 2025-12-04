"""API Proxy Configuration Service"""

from typing import Optional
from pathlib import Path
from src.common.config_service import ConfigService


class ApiProxyConfigService(ConfigService):
    """API Proxy specific configuration service"""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__(
            service_name="api_proxy",
            config_path=config_path,
            env_prefix="API_PROXY"
        )

    def get_db_type(self) -> str:
        """Get database type (postgresql or sqlite)"""
        return self.get("database.type", "postgresql")

    def get_db_url(self) -> str:
        """Get database URL based on type"""
        db_type = self.get_db_type()

        if db_type == "sqlite":
            db_path = self.get("database.sqlite.path", "~/.ami/database/api_proxy.db")
            db_path = Path(db_path).expanduser().resolve()
            # Ensure parent directory exists
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{db_path}"
        else:  # postgresql
            host = self.get("database.postgresql.host", "localhost")
            port = self.get("database.postgresql.port", 5432)
            database = self.get("database.postgresql.database", "ami_proxy")
            username = self.get("database.postgresql.username", "ami_user")
            password = self.get("database.postgresql.password", "ami_password")
            return f"postgresql://{username}:{password}@{host}:{port}/{database}"

    def get_jwt_secret_key(self) -> str:
        """Get JWT secret key"""
        return self.get("jwt.secret_key", "your-secret-key-change-in-production")

    def get_jwt_algorithm(self) -> str:
        """Get JWT algorithm"""
        return self.get("jwt.algorithm", "HS256")

    def get_jwt_expire_minutes(self) -> int:
        """Get JWT access token expiration time"""
        return self.get("jwt.access_token_expire_minutes", 43200)

    def get_anthropic_api_key(self) -> str:
        """Get Anthropic API key from config or environment"""
        import os
        # Priority: environment variable > config file
        return os.getenv("ANTHROPIC_API_KEY") or self.get("llm.anthropic.api_key", "")

    def get_log_path(self) -> Path:
        """Get log file path"""
        log_path = self.get("logging.file", "~/.ami/logs/api-proxy.log")
        path = Path(log_path).expanduser().resolve()
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


# Global config instance
_config_instance: Optional[ApiProxyConfigService] = None


def get_config(config_path: Optional[str] = None) -> ApiProxyConfigService:
    """Get global configuration instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = ApiProxyConfigService(config_path)
    return _config_instance
