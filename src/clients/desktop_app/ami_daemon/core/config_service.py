"""App Backend Configuration Service"""

from typing import Optional
from pathlib import Path
from src.common.config_service import ConfigService


class AppConfigService(ConfigService):
    """App Backend specific configuration service"""

    def __init__(self, config_path: Optional[str] = None):
        # If no config_path provided, use default location
        if config_path is None:
            # ami_daemon/core/config_service.py -> ami_daemon/config/app-backend.yaml
            default_config = Path(__file__).parent.parent / "config" / "app-backend.yaml"
            if default_config.exists():
                config_path = str(default_config)

        super().__init__(
            service_name="ami_daemon",
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
