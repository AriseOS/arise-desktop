"""
配置管理服务
支持YAML配置文件和环境变量
"""
import os
import yaml
from typing import Dict, Any, Optional
from pathlib import Path


class ConfigService:
    """配置管理服务"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_data: Dict[str, Any] = {}
        self.config_path = self._find_config_file(config_path)
        self._load_config()
    
    def _find_config_file(self, config_path: Optional[str] = None) -> str:
        """查找配置文件"""
        if config_path and Path(config_path).exists():
            return config_path
        
        # 按优先级查找配置文件
        search_paths = [
            "./baseapp.yaml",
            "./config/baseapp.yaml", 
            Path.home() / ".baseapp" / "config.yaml",
            "/etc/baseapp/config.yaml"
        ]
        
        for path in search_paths:
            if Path(path).exists():
                return str(path)
        
        # 如果没有找到，创建默认配置
        default_path = "./config/baseapp.yaml"
        self._create_default_config(default_path)
        return default_path
    
    def _create_default_config(self, config_path: str):
        """创建默认配置文件"""
        default_config = {
            "app": {
                "name": "BaseApp",
                "version": "1.0.0",
                "host": "0.0.0.0",
                "port": 8000,
                "debug": False
            },
            "agent": {
                "name": "BaseApp Agent",
                "memory": {
                    "enabled": True,
                    "provider": "mem0",
                    "config": {
                        "version": "v1.1",
                        "llm": {
                            "provider": "openai",
                            "config": {
                                "api_key": "${OPENAI_API_KEY}",
                                "model": "gpt-4o-mini"
                            }
                        },
                        "embedder": {
                            "provider": "openai",
                            "config": {
                                "api_key": "${OPENAI_API_KEY}",
                                "model": "text-embedding-3-small"
                            }
                        },
                        "vector_store": {
                            "provider": "chroma",
                            "config": {
                                "collection_name": "mem0_collection",
                                "path": "./data/chroma_db"
                            }
                        }
                    }
                },
                "llm": {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "api_key": "${OPENAI_API_KEY}"
                },
                "tools": {
                    "enabled": ["browser", "memory"],
                    "browser": {
                        "headless": True,
                        "timeout": 30
                    }
                }
            },
            "database": {
                "type": "sqlite",
                "url": "./data/baseapp.db"
            },
            "logging": {
                "level": "INFO",
                "file": "./logs/baseapp.log",
                "max_size": "10MB",
                "backup_count": 5
            }
        }
        
        # 确保目录存在
        Path(config_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)
    
    def _load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config_data = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Warning: Failed to load config file {self.config_path}: {e}")
            self.config_data = {}
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值，支持点分割的键名
        
        Args:
            key: 配置键，支持 "app.port" 格式
            default: 默认值
            
        Returns:
            配置值
        """
        # 首先检查环境变量
        env_value = self._get_env_value(key)
        if env_value is not None:
            return env_value
        
        # 然后从配置文件获取
        return self._get_nested_value(self.config_data, key, default)
    
    def _get_env_value(self, key: str) -> Optional[Any]:
        """从环境变量获取配置值"""
        # 将点分割键转换为环境变量格式
        env_key = key.upper().replace('.', '_')
        env_key = f"BASEAPP_{env_key}"
        
        value = os.getenv(env_key)
        if value is not None:
            # 尝试转换类型
            return self._convert_env_value(value)
        
        # 检查一些特殊的环境变量
        special_mappings = {
            "agent.llm.api_key": "OPENAI_API_KEY",
            "anthropic.api_key": "ANTHROPIC_API_KEY"
        }
        
        if key in special_mappings:
            return os.getenv(special_mappings[key])
        
        return None
    
    def _convert_env_value(self, value: str) -> Any:
        """转换环境变量值的类型"""
        # 布尔值
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        
        # 数字
        try:
            if '.' in value:
                return float(value)
            else:
                return int(value)
        except ValueError:
            pass
        
        # 字符串
        return value
    
    def _get_nested_value(self, data: Dict, key: str, default: Any) -> Any:
        """获取嵌套字典的值"""
        keys = key.split('.')
        current = data
        
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return default
        
        # 处理环境变量引用
        if isinstance(current, str) and current.startswith('${') and current.endswith('}'):
            env_var = current[2:-1]
            return os.getenv(env_var, default)
        
        return current
    
    def set(self, key: str, value: Any):
        """设置配置值"""
        keys = key.split('.')
        current = self.config_data
        
        # 创建嵌套字典结构
        for k in keys[:-1]:
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]
        
        current[keys[-1]] = value
    
    def save(self):
        """保存配置到文件"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config_data, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            raise RuntimeError(f"Failed to save config: {e}")
    
    def reload(self):
        """重新加载配置"""
        self._load_config()
    
    def get_all(self) -> Dict[str, Any]:
        """获取所有配置"""
        return self.config_data.copy()
    
    def validate(self) -> Dict[str, Any]:
        """验证配置"""
        errors = []
        warnings = []
        
        # 检查必需的配置
        required_configs = [
            "app.name",
            "app.port", 
            "agent.name",
            "agent.llm.provider",
            "agent.llm.model"
        ]
        
        for config_key in required_configs:
            value = self.get(config_key)
            if value is None:
                errors.append(f"Missing required config: {config_key}")
        
        # 检查API密钥
        llm_provider = self.get("agent.llm.provider")
        if llm_provider == "openai":
            api_key = self.get("agent.llm.api_key")
            if not api_key:
                errors.append("OpenAI API key is required when using OpenAI provider")
        
        # 检查端口范围
        port = self.get("app.port")
        if port and (not isinstance(port, int) or port < 1 or port > 65535):
            errors.append("Invalid port number")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }