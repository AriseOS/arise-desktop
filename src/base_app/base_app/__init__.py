"""
BaseApp - AI Agent Assistant Application

BaseApp 是一个基于 BaseAgent 的完整应用程序，提供 Web UI、CLI 和 API 三种交互方式。
"""

__version__ = "1.0.0"
__author__ = "BaseApp Team"
__description__ = "AI Agent Assistant Application"

# Lazy imports to avoid circular dependencies when package is imported
# from .base_agent.core import BaseAgent
# from .server.main import create_app, run_server
# from .cli.main import cli

# __all__ = ["BaseAgent", "create_app", "run_server", "cli"]