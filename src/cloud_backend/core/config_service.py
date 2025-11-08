"""Cloud Backend Configuration Service"""

from typing import Optional
from pathlib import Path
from src.common.config_service import ConfigService


class CloudConfigService(ConfigService):
    """Cloud Backend specific configuration service"""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__(
            service_name="cloud_backend",
            config_path=config_path,
            env_prefix="CLOUD_BACKEND"
        )

    def get_db_path(self) -> Path:
        """Get database path (for SQLite)"""
        db_path = self.get("database.sqlite.path", "~/.ami-server/database/ami.db")
        return Path(db_path).expanduser().resolve()

    def get_log_path(self) -> Path:
        """Get log file path"""
        log_path = self.get("logging.file", "~/.ami-server/logs/cloud-backend.log")
        return Path(log_path).expanduser().resolve()


# Global config instance
_config_instance: Optional[CloudConfigService] = None


def get_config(config_path: Optional[str] = None) -> CloudConfigService:
    """Get global configuration instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = CloudConfigService(config_path)
    return _config_instance
