"""
AgentBuilder 基础 LLM Provider
"""

from abc import ABC, abstractmethod
from typing import Optional


class BaseProvider(ABC):
    """LLM Provider 基类"""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key
        self.model = model
        self._client = None
    
    @abstractmethod
    async def generate_response(self, system_prompt: str, user_prompt: str) -> str:
        """生成响应"""
        pass
    
    @abstractmethod
    async def _initialize_client(self):
        """初始化客户端"""
        pass