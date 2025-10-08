"""
AgentCrafter Backend Configuration
Configuration file - manages database connections and other backend settings
"""
import os
import yaml
from typing import Optional, Dict, Any
from pathlib import Path

class BackendConfig:
    """Backend configuration class"""

    def __init__(self, config_path: Optional[str] = None):
        # Find project root
        self.project_root = self._find_project_root()
        self.backend_dir = Path(__file__).parent
        self.config_dir = self.backend_dir.parent / "config"

        # Load configuration
        self.config_data = self._load_config(config_path)

        # Database configuration
        self.database_url = self._get_database_url()

        # Server configuration
        self.host = self._get_config_value("server.host", "0.0.0.0")
        self.port = int(self._get_config_value("server.port", "8000"))
        self.reload = self._get_config_value("server.reload", True)

        # JWT configuration
        self.secret_key = self._get_config_value("security.secret_key", "your-secret-key-here-change-in-production")
        self.algorithm = self._get_config_value("security.algorithm", "HS256")
        self.access_token_expire_minutes = int(self._get_config_value("security.access_token_expire_minutes", "30"))

        # Logging configuration
        self.log_level = self._get_config_value("logging.level", "INFO")

    def _find_project_root(self) -> Path:
        """Find project root directory"""
        # Method 1: Via environment variable
        project_root_env = os.getenv("PROJECT_ROOT")
        if project_root_env:
            return Path(project_root_env).resolve()

        # Method 2: Default - infer from current file location
        # src/client/web/backend/config.py -> ../../../../ -> agentcrafter/
        return Path(__file__).parent.parent.parent.parent.parent

    def _load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        # Find config file
        if config_path:
            config_file = Path(config_path)
        else:
            # Default: src/client/web/config/backend.yaml
            config_file = self.config_dir / "backend.yaml"

        if not config_file.exists():
            print(f"Warning: Config file not found at {config_file}, using defaults")
            return {}

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            return config
        except Exception as e:
            print(f"Warning: Failed to load config file {config_file}: {e}")
            return {}

    def _get_config_value(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value with environment variable override

        Args:
            key: Dot-separated config key (e.g., "server.port")
            default: Default value if not found

        Returns:
            Configuration value (environment variable takes precedence)
        """
        # Convert dot notation to environment variable format
        # e.g., "server.port" -> "BACKEND_SERVER_PORT"
        env_key = "BACKEND_" + key.upper().replace(".", "_")

        # Check environment variable first
        env_value = os.getenv(env_key)
        if env_value is not None:
            # Try to convert to appropriate type based on default
            if isinstance(default, bool):
                return env_value.lower() in ("true", "1", "yes")
            elif isinstance(default, int):
                try:
                    return int(env_value)
                except ValueError:
                    pass
            return env_value

        # Get from config file
        keys = key.split(".")
        value = self.config_data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default

        # Expand environment variables in string values
        if isinstance(value, str) and "${" in value:
            value = self._expand_env_vars(value)

        return value if value is not None else default

    def _expand_env_vars(self, value: str) -> str:
        """Expand environment variables in config values"""
        import re
        pattern = r'\$\{([^}]+)\}'

        def replacer(match):
            env_var = match.group(1)
            return os.getenv(env_var, match.group(0))

        return re.sub(pattern, replacer, value)

    def _get_database_url(self) -> str:
        """Get database URL configuration"""
        # Check environment variable first
        env_db_url = os.getenv("DATABASE_URL")
        if env_db_url:
            return env_db_url

        # Check config file for direct URL
        db_url = self._get_config_value("database.url")
        if db_url:
            return db_url

        # Check config file for database path
        db_path = self._get_config_value("database.path")
        if db_path:
            # Expand environment variables
            if "${" in db_path:
                db_path = self._expand_env_vars(db_path)

            # Convert relative path to absolute
            if not os.path.isabs(db_path):
                db_path = os.path.join(self.project_root, db_path)
            return f"sqlite:///{db_path}"

        # Default: use backend directory database file
        default_db_path = self.backend_dir / "agentcrafter_users.db"
        return f"sqlite:///{default_db_path}"
    
    def get_database_config(self) -> dict:
        """Get database connection configuration"""
        config = {"url": self.database_url}

        # SQLite specific configuration
        if "sqlite" in self.database_url:
            config["connect_args"] = {"check_same_thread": False}

        return config

    def get_server_config(self) -> dict:
        """Get server configuration"""
        return {
            "host": self.host,
            "port": self.port,
            "reload": self.reload,
            "log_level": self.log_level.lower()
        }

    def get_jwt_config(self) -> dict:
        """Get JWT configuration"""
        return {
            "secret_key": self.secret_key,
            "algorithm": self.algorithm,
            "access_token_expire_minutes": self.access_token_expire_minutes
        }


# Global configuration instance
config = BackendConfig()


# Convenience functions
def get_database_url() -> str:
    """Get database URL"""
    return config.database_url


def get_database_config() -> dict:
    """Get database configuration"""
    return config.get_database_config()


def get_server_config() -> dict:
    """Get server configuration"""
    return config.get_server_config()


def get_jwt_config() -> dict:
    """Get JWT configuration"""
    return config.get_jwt_config()


# Print configuration (for debugging)
def print_config():
    """Print current configuration"""
    print("=== AgentCrafter Backend Configuration ===")
    print(f"Config file: {config.config_dir / 'backend.yaml'}")
    print(f"Database URL: {config.database_url}")
    print(f"Server: {config.host}:{config.port}")
    print(f"Reload: {config.reload}")
    print(f"Log Level: {config.log_level}")
    print("==========================================")


if __name__ == "__main__":
    print_config()