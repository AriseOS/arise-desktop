"""
CLI工具函数
"""
import os
from pathlib import Path
from typing import Dict, Any


def format_uptime(seconds: float) -> str:
    """格式化运行时间"""
    if seconds < 60:
        return f"{int(seconds)}秒"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes}分{int(seconds % 60)}秒"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}时{minutes}分"


def get_pid_file() -> Path:
    """获取PID文件路径"""
    return Path.home() / ".baseapp" / "baseapp.pid"


def get_config_dir() -> Path:
    """获取配置目录"""
    return Path.home() / ".baseapp"


def ensure_config_dir():
    """确保配置目录存在"""
    config_dir = get_config_dir()
    config_dir.mkdir(exist_ok=True)
    return config_dir


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes == 0:
        return "0B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"


def truncate_text(text: str, max_length: int = 80) -> str:
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


def validate_port(port: int) -> bool:
    """验证端口号"""
    return 1 <= port <= 65535


def get_default_editor() -> str:
    """获取默认编辑器"""
    return os.environ.get('EDITOR', 'nano')


def safe_json_loads(text: str) -> Dict[str, Any]:
    """安全的JSON解析"""
    import json
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}