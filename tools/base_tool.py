"""
基础工具类定义
定义所有工具必须实现的统一接口
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from enum import Enum
import asyncio
import logging

logger = logging.getLogger(__name__)


class ToolStatus(str, Enum):
    """工具状态枚举"""
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class ToolMetadata(BaseModel):
    """工具元数据"""
    name: str = Field(..., description="工具名称")
    description: str = Field(..., description="工具描述")
    version: str = Field(default="1.0.0", description="工具版本")
    author: str = Field(default="AgentCrafter", description="工具作者")
    tags: List[str] = Field(default_factory=list, description="工具标签")
    category: str = Field(default="general", description="工具分类")


class ToolResult(BaseModel):
    """工具执行结果"""
    success: bool = Field(..., description="执行是否成功")
    data: Any = Field(default=None, description="返回数据")
    message: str = Field(default="", description="执行消息")
    status: ToolStatus = Field(default=ToolStatus.SUCCESS, description="执行状态")
    execution_time: float = Field(default=0.0, description="执行时间(秒)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")


class ToolConfig(BaseModel):
    """工具配置基类"""
    timeout: int = Field(default=300, description="超时时间(秒)")
    retry_count: int = Field(default=3, description="重试次数")
    retry_delay: float = Field(default=1.0, description="重试延迟(秒)")
    enable_logging: bool = Field(default=True, description="是否启用日志")
    max_memory_mb: int = Field(default=512, description="最大内存使用(MB)")


class BaseTool(ABC):
    """
    工具基类
    所有工具都必须继承此类并实现必要的方法
    """
    
    def __init__(self, config: Optional[ToolConfig] = None):
        self.config = config or ToolConfig()
        self.status = ToolStatus.IDLE
        self._metadata: Optional[ToolMetadata] = None
        
    @property
    @abstractmethod
    def metadata(self) -> ToolMetadata:
        """返回工具元数据"""
        pass
    
    @abstractmethod
    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        **kwargs
    ) -> ToolResult:
        """
        执行工具操作
        
        Args:
            action: 动作名称
            params: 动作参数
            **kwargs: 额外参数
            
        Returns:
            ToolResult: 执行结果
        """
        pass
    
    @abstractmethod
    async def validate_params(
        self,
        action: str, 
        params: Dict[str, Any]
    ) -> bool:
        """
        验证参数是否有效
        
        Args:
            action: 动作名称
            params: 参数字典
            
        Returns:
            bool: 参数是否有效
        """
        pass
    
    @abstractmethod
    def get_available_actions(self) -> List[str]:
        """
        获取工具支持的所有动作
        
        Returns:
            List[str]: 动作名称列表
        """
        pass
    
    async def initialize(self) -> bool:
        """
        初始化工具
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            self.status = ToolStatus.RUNNING
            success = await self._initialize()
            if success:
                self.status = ToolStatus.IDLE
            else:
                self.status = ToolStatus.ERROR
            return success
        except Exception as e:
            logger.error(f"工具初始化失败: {e}")
            self.status = ToolStatus.ERROR
            return False
    
    async def cleanup(self) -> bool:
        """
        清理工具资源
        
        Returns:
            bool: 清理是否成功
        """
        try:
            success = await self._cleanup()
            self.status = ToolStatus.IDLE
            return success
        except Exception as e:
            logger.error(f"工具清理失败: {e}")
            return False
    
    async def health_check(self) -> bool:
        """
        健康检查
        
        Returns:
            bool: 工具是否健康
        """
        try:
            return await self._health_check()
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return False
    
    async def _initialize(self) -> bool:
        """子类实现的初始化逻辑"""
        return True
    
    async def _cleanup(self) -> bool:
        """子类实现的清理逻辑"""
        return True
    
    async def _health_check(self) -> bool:
        """子类实现的健康检查逻辑"""
        return self.status != ToolStatus.ERROR
    
    def get_schema(self, action: str) -> Dict[str, Any]:
        """
        获取指定动作的参数模式
        
        Args:
            action: 动作名称
            
        Returns:
            Dict[str, Any]: JSON Schema
        """
        return {
            "type": "object",
            "properties": {},
            "required": []
        }
    
    async def execute_with_retry(
        self,
        action: str,
        params: Dict[str, Any],
        **kwargs
    ) -> ToolResult:
        """
        带重试的执行方法
        
        Args:
            action: 动作名称
            params: 动作参数
            **kwargs: 额外参数
            
        Returns:
            ToolResult: 执行结果
        """
        import time
        
        last_error = None
        start_time = time.time()
        
        for attempt in range(self.config.retry_count + 1):
            try:
                # 设置超时
                result = await asyncio.wait_for(
                    self.execute(action, params, **kwargs),
                    timeout=self.config.timeout
                )
                
                if result.success:
                    result.execution_time = time.time() - start_time
                    return result
                    
                last_error = result.message
                
            except asyncio.TimeoutError:
                last_error = f"执行超时 ({self.config.timeout}秒)"
                logger.warning(f"工具执行超时: {action}")
                
            except Exception as e:
                last_error = str(e)
                logger.error(f"工具执行异常: {action}, 错误: {e}")
            
            if attempt < self.config.retry_count:
                await asyncio.sleep(self.config.retry_delay)
        
        # 所有重试都失败
        return ToolResult(
            success=False,
            message=f"执行失败，已重试 {self.config.retry_count} 次: {last_error}",
            status=ToolStatus.ERROR,
            execution_time=time.time() - start_time
        )