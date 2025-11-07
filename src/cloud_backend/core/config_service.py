"""
Cloud Backend Configuration Service

Manages configuration via YAML files and environment variables.
"""
import os
import yaml
from typing import Dict, Any, Optional
from pathlib import Path


class CloudConfigService:
    """Cloud Backend Configuration Service"""

    def __init__(self, config_path: Optional[str] = None):
        self.config_data: Dict[str, Any] = {}
        self.project_root = self._find_project_root()
        self.config_path = self._find_config_file(config_path)
        self._load_config()

    def _find_project_root(self) -> Path:
        """Find project root directory (agentcrafter/)"""
        # Method 1: Via environment variable
        if project_root_env := os.getenv("PROJECT_ROOT"):
            return Path(project_root_env).resolve()

        # Method 2: Calculate from current file location
        # Current file: src/cloud-backend/core/config_service.py
        # Project root: ../../../ (up 3 levels to agentcrafter/)
        return Path(__file__).parent.parent.parent.parent.resolve()

    def _find_config_file(self, config_path: Optional[str] = None) -> str:
        """Find configuration file with priority order"""
        search_paths = []

        # 1. Environment variable (highest priority)
        if env_path := os.environ.get('CLOUD_BACKEND_CONFIG'):
            env_path = Path(env_path).expanduser()
            if env_path.exists():
                return str(env_path)
            else:
                raise FileNotFoundError(
                    f"Config file specified by CLOUD_BACKEND_CONFIG not found: {env_path}"
                )

        # 2. Command line argument
        if config_path:
            config_path = Path(config_path).expanduser()
            if config_path.exists():
                return str(config_path)
            else:
                raise FileNotFoundError(f"Specified config file not found: {config_path}")

        # 3. Default config in project
        # cloud-backend/config/cloud-backend.yaml
        code_dir = Path(__file__).parent.parent  # src/cloud-backend/
        default_config = code_dir / 'config' / 'cloud-backend.yaml'
        search_paths.append(default_config)

        # 4. User config directory
        search_paths.append(Path.home() / '.ami' / 'cloud-backend.yaml')

        # 5. System-wide configuration
        search_paths.extend([
            Path('/etc/ami/cloud-backend.yaml'),
            Path('/usr/local/etc/ami/cloud-backend.yaml')
        ])

        for path in search_paths:
            if path.exists():
                return str(path)

        # No config found - create default
        default_path = code_dir / 'config' / 'cloud-backend.yaml'
        print(f"⚠️  No config found, creating default: {default_path}")
        self._create_default_config(default_path)
        return str(default_path)

    def _create_default_config(self, config_path: Path):
        """Create default configuration file"""
        config_path.parent.mkdir(parents=True, exist_ok=True)

        default_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 9000,
                "debug": False,
                "reload": False
            },
            "storage": {
                "type": "filesystem",  # filesystem or s3
                "base_path": "~/ami-server",  # For filesystem storage
                # S3 configuration (optional)
                # "s3_bucket": "ami-cloud-storage",
                # "s3_region": "us-east-1"
            },
            "database": {
                "type": "sqlite",  # sqlite or postgresql
                "sqlite": {
                    "path": "~/ami-server/database/ami.db"
                },
                # PostgreSQL configuration (optional)
                # "postgresql": {
                #     "host": "localhost",
                #     "port": 5432,
                #     "database": "ami",
                #     "user": "ami_user",
                #     "password_env": "DB_PASSWORD"
                # }
            },
            "llm": {
                "default_provider": "anthropic",  # anthropic or openai
                "anthropic": {
                    "api_key_env": "ANTHROPIC_API_KEY",
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 4096
                },
                "openai": {
                    "api_key_env": "OPENAI_API_KEY",
                    "model": "gpt-4",
                    "max_tokens": 4096
                }
            },
            "workflow_generation": {
                "save_intermediates": True,  # Save intent_graph, metaflow
                "timeout_seconds": 300,  # 5 minutes
                "max_retries": 3
            },
            "auth": {
                "secret_key_env": "JWT_SECRET_KEY",
                "algorithm": "HS256",
                "access_token_expire_minutes": 60
            },
            "logging": {
                "level": "INFO",  # DEBUG, INFO, WARNING, ERROR
                "format": "%(asctime)s [%(levelname)8s] %(message)s",
                "file": "~/ami-server/logs/cloud-backend.log"
            }
        }

        with open(config_path, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False, sort_keys=False)

        print(f"✅ Created default config: {config_path}")

    def _load_config(self):
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                self.config_data = yaml.safe_load(f) or {}
            print(f"✅ Loaded config from: {self.config_path}")
        except Exception as e:
            raise RuntimeError(f"Failed to load config from {self.config_path}: {e}")

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation

        Args:
            key_path: Dot-separated path (e.g., "server.host")
            default: Default value if key not found

        Returns:
            Configuration value or default

        Example:
            config.get("server.port")  # Returns 9000
            config.get("llm.anthropic.model")  # Returns "claude-3-5-sonnet-20241022"
        """
        keys = key_path.split('.')
        value = self.config_data

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        # Check if value references an environment variable
        if isinstance(value, str) and value.endswith('_env'):
            # This is an environment variable key
            env_key = self.config_data
            for key in keys:
                if isinstance(env_key, dict) and key in env_key:
                    env_key = env_key[key]
            if isinstance(env_key, str):
                return os.getenv(env_key, default)

        return value

    def get_env(self, key_path: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get value from environment variable specified in config

        Args:
            key_path: Path to env variable key (e.g., "llm.anthropic.api_key_env")
            default: Default value if env variable not set

        Returns:
            Environment variable value or default
        """
        env_key = self.get(key_path)
        if env_key:
            return os.getenv(env_key, default)
        return default

    def get_storage_path(self) -> Path:
        """Get storage base path (expanded)"""
        base_path = self.get("storage.base_path", "~/ami-server")
        return Path(base_path).expanduser().resolve()

    def get_db_path(self) -> Path:
        """Get database path (for SQLite)"""
        db_path = self.get("database.sqlite.path", "~/ami-server/database/ami.db")
        return Path(db_path).expanduser().resolve()

    def get_log_path(self) -> Path:
        """Get log file path"""
        log_path = self.get("logging.file", "~/ami-server/logs/cloud-backend.log")
        return Path(log_path).expanduser().resolve()

    def reload(self):
        """Reload configuration from file"""
        self._load_config()

    def __repr__(self) -> str:
        return f"CloudConfigService(config_path='{self.config_path}')"
