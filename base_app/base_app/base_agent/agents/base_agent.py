"""
Base Agent class for Agent-as-Step architecture
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ..core.schemas import AgentCapability, AgentContext


class AgentMetadata(BaseModel):
    """Agent元数据"""
    name: str = Field(..., description="Agent名称")
    description: str = Field(..., description="Agent描述")
    version: str = Field(default="1.0.0", description="版本号")
    capabilities: List[AgentCapability] = Field(..., description="Agent能力列表")
    input_schema: Dict[str, Any] = Field(..., description="输入数据结构")
    output_schema: Dict[str, Any] = Field(..., description="输出数据结构")
    author: str = Field(default="", description="作者")
    tags: List[str] = Field(default_factory=list, description="标签")


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