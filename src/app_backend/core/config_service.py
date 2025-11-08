"""App Backend Configuration Service"""

from typing import Optional
from src.common.config_service import ConfigService


class AppConfigService(ConfigService):
    """App Backend specific configuration service"""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__(
            service_name="app_backend",
            config_path=config_path,
            env_prefix="APP_BACKEND"
        )


# Global config instance
_config_instance: Optional[AppConfigService] = None


def get_config(config_path: Optional[str] = None) -> AppConfigService:
    """Get global configuration instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = AppConfigService(config_path)
    return _config_instance
