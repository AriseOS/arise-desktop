"""
Common Configuration Service

A unified configuration service for all backend services (App Backend, Cloud Backend).
Manages configuration via YAML files and environment variables.
"""
import os
import re
import yaml
from typing import Dict, Any, Optional
from pathlib import Path


class ConfigService:
    """Base Configuration Service for all backends"""

    def __init__(
        self,
        service_name: str,
        config_path: Optional[str] = None,
        env_prefix: Optional[str] = None
    ):
        """
        Initialize configuration service

        Args:
            service_name: Service name (e.g., "app_backend", "cloud_backend")
            config_path: Optional path to config file
            env_prefix: Environment variable prefix (e.g., "APP_BACKEND", "CLOUD_BACKEND")
        """
        self.service_name = service_name
        self.env_prefix = env_prefix or service_name.upper()
        self.config_data: Dict[str, Any] = {}
        self.project_root = self._find_project_root()
        self.config_path = self._find_config_file(config_path)
        self._load_config()

    def _find_project_root(self) -> Path:
        """Find project root directory (ami/)"""
        # Method 1: Via environment variable
        if project_root_env := os.getenv("PROJECT_ROOT"):
            return Path(project_root_env).resolve()

        # Method 2: Calculate from current file location
        # Current file: src/common/config_service.py
        # Project root: ../../ (up 2 levels to ami/)
        return Path(__file__).parent.parent.parent.resolve()

    def _find_config_file(self, config_path: Optional[str] = None) -> str:
        """Find configuration file with priority order"""
        search_paths = []

        # 1. Environment variable (highest priority)
        env_var = f"{self.env_prefix}_CONFIG"
        if env_path := os.environ.get(env_var):
            env_path = Path(env_path).expanduser()
            if env_path.exists():
                return str(env_path)
            else:
                raise FileNotFoundError(
                    f"Config file specified by {env_var} not found: {env_path}"
                )

        # 2. Command line argument
        if config_path:
            config_path = Path(config_path).expanduser()
            if config_path.exists():
                return str(config_path)
            else:
                raise FileNotFoundError(f"Specified config file not found: {config_path}")

        # 3. Default config in service directory
        # src/{service_name}/config/{service_name}.yaml
        service_dir = self.project_root / "src" / self.service_name
        config_filename = f"{self.service_name.replace('_', '-')}.yaml"
        default_config = service_dir / "config" / config_filename
        search_paths.append(default_config)

        # 4. User config directory
        search_paths.append(Path.home() / ".ami" / config_filename)

        # 5. System-wide configuration
        search_paths.extend([
            Path(f'/etc/ami/{config_filename}'),
            Path(f'/usr/local/etc/ami/{config_filename}')
        ])

        for path in search_paths:
            if path.exists():
                return str(path)

        raise FileNotFoundError(
            f"Config file not found. Searched paths: {[str(p) for p in search_paths]}"
        )

    def _load_config(self):
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config_data = yaml.safe_load(f) or {}
            print(f"✅ Loaded config from: {self.config_path}")

            # Process configuration (expand variables, set defaults)
            self._process_config()
        except Exception as e:
            raise RuntimeError(f"Failed to load config from {self.config_path}: {e}")

    def _process_config(self):
        """Process special configuration values"""
        # Auto-detect storage base_path
        if self.get("storage.base_path") == "auto":
            self.config_data["storage"]["base_path"] = self._get_default_storage_path()

        # Expand variables like ${storage.base_path}
        self._expand_vars(self.config_data)

    def _get_default_storage_path(self) -> str:
        """Get default storage path based on platform"""
        home = Path.home()
        # Use ~/.ami/ for all platforms
        return str(home / ".ami")

    def _expand_vars(self, data: Any):
        """Recursively expand ${key} references in config"""
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str):
                    data[key] = self._expand_string(value)
                else:
                    self._expand_vars(value)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, str):
                    data[i] = self._expand_string(item)
                else:
                    self._expand_vars(item)

    def _expand_string(self, value: str) -> str:
        """Expand ${...} references in a string"""
        if "${" not in value:
            return value

        pattern = r'\$\{([^}]+)\}'

        def replacer(match):
            ref = match.group(1)
            config_val = self.get(ref)
            if config_val is not None:
                return str(config_val)
            # Try environment variable
            return os.getenv(ref, match.group(0))

        return re.sub(pattern, replacer, value)

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation

        Supports environment variable override with pattern:
        key_path="server.port" -> env var="{ENV_PREFIX}_SERVER_PORT"

        Args:
            key_path: Dot-separated path (e.g., "server.port")
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        # Check environment variable override
        env_key = f"{self.env_prefix}_{key_path.replace('.', '_').upper()}"
        env_value = os.getenv(env_key)
        if env_value is not None:
            return self._convert_type(env_value)

        # Get from config
        keys = key_path.split('.')
        value = self.config_data

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def _convert_type(self, value: str) -> Any:
        """Convert string to appropriate type"""
        if value.lower() in ('true', 'yes', '1'):
            return True
        if value.lower() in ('false', 'no', '0'):
            return False

        try:
            return int(value)
        except ValueError:
            pass

        try:
            return float(value)
        except ValueError:
            pass

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

    def get_path(self, key_path: str) -> Path:
        """
        Get config value as Path object (expanded)

        Args:
            key_path: Config key in dot notation (e.g., "data.browser_data")

        Returns:
            Path object for the configuration value
        """
        value = self.get(key_path)
        if value is None:
            # Return default based on key_path
            if key_path == "data.browser_data":
                return Path(self.get("storage.base_path")) / "browser_data"
            raise ValueError(f"Config key not found: {key_path}")

        return Path(value).expanduser().resolve()

    def get_storage_path(self) -> Path:
        """Get storage base path (expanded)"""
        base_path = self.get("storage.base_path", "~/.ami")
        return Path(base_path).expanduser().resolve()

    def reload(self):
        """Reload configuration from file"""
        self._load_config()

    def __repr__(self) -> str:
        return f"ConfigService(service='{self.service_name}', config_path='{self.config_path}')"
