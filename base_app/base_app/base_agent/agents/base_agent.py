"""
Base Agent class for Agent-as-Step architecture
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ..core.schemas import  AgentContext


class AgentMetadata(BaseModel):
    """Agent元数据"""
    name: str = Field(..., description="Agent名称")
    description: str = Field(..., description="Agent描述")


class BaseStepAgent(ABC):
    """Agent基类"""
    
    def __init__(self, metadata: AgentMetadata):
        self.metadata = metadata
        self.is_initialized = False
    
    @abstractmethod
    async def initialize(self, context: AgentContext) -> bool:
        """初始化Agent"""
        pass
    
    @abstractmethod
    async def execute(self, input_data: Any, context: AgentContext) -> Any:
        """执行Agent任务"""
        pass
    
    @abstractmethod
    async def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        pass
    
    async def cleanup(self, context: AgentContext) -> None:
        """清理资源"""
        pass