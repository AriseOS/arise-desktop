"""
Core data structures for BaseAgent system
定义BaseAgent系统的核心数据结构
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, PrivateAttr
import logging

logger = logging.getLogger(__name__)


# ==================== Agent Core Schemas ====================

class AgentStatus(str, Enum):
    """Agent状态枚举"""
    CREATED = "created"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"


class AgentPriority(str, Enum):
    """Agent优先级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentConfig(BaseModel):
    """Agent配置"""
    name: str = Field(..., description="Agent名称")
    description: str = Field(default="", description="Agent描述")
    version: str = Field(default="1.0.0", description="版本号")
    priority: AgentPriority = Field(default=AgentPriority.MEDIUM, description="执行优先级")
    
    # LLM 配置
    llm_provider: str = Field(default="openai", description="LLM提供商")
    llm_model: str = Field(default="gpt-4o", description="LLM模型")
    api_key: str = Field(default="", description="API密钥")
    
    # 工具配置
    tools: List[str] = Field(default_factory=list, description="启用的工具列表")
    
    # 功能开关
    enable_logging: bool = Field(default=True, description="是否启用日志")
    enable_persistence: bool = Field(default=False, description="是否启用持久化")
    enable_monitoring: bool = Field(default=False, description="是否启用监控")
    
    # 执行配置
    max_execution_time: int = Field(default=3600, description="最大执行时间(秒)")
    max_memory_mb: int = Field(default=1024, description="最大内存使用(MB)")
    log_level: str = Field(default="INFO", description="日志级别")


class AgentState(BaseModel):
    """Agent状态信息"""
    agent_id: str = Field(..., description="Agent ID")
    status: AgentStatus = Field(default=AgentStatus.CREATED, description="当前状态")
    
    # 时间信息
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    started_at: Optional[datetime] = Field(default=None, description="启动时间")
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")
    
    # 执行信息
    execution_count: int = Field(default=0, description="执行次数")
    current_task: Optional[str] = Field(default=None, description="当前任务")
    current_step: Optional[str] = Field(default=None, description="当前步骤")
    step_index: int = Field(default=0, description="当前步骤索引")
    
    # 性能信息
    total_execution_time: float = Field(default=0.0, description="总执行时间")
    memory_usage_mb: float = Field(default=0.0, description="内存使用量(MB)")
    
    # 错误信息
    last_error: Optional[str] = Field(default=None, description="最后一次错误")
    error_count: int = Field(default=0, description="错误计数")


class AgentResult(BaseModel):
    """Agent执行结果"""
    success: bool = Field(..., description="执行是否成功")
    data: Any = Field(default=None, description="返回数据")
    message: str = Field(default="", description="执行消息")

    # 执行信息
    execution_time: float = Field(default=0.0, description="执行时间(秒)")
    task_id: Optional[str] = Field(default=None, description="任务ID")
    step_count: int = Field(default=0, description="执行步骤数")

    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")
    timestamp: datetime = Field(default_factory=datetime.now, description="执行时间戳")


# ==================== Agent-as-Step Schemas ====================

class AgentInput(BaseModel):
    """统一的Agent输入模型"""
    data: Dict[str, Any] = Field(default_factory=dict, description="输入数据")
    step_metadata: Dict[str, Any] = Field(default_factory=dict, description="步骤元数据")


class AgentOutput(BaseModel):
    """统一的Agent输出模型"""
    success: bool = Field(..., description="执行是否成功")
    data: Dict[str, Any] = Field(default_factory=dict, description="输出数据") 
    message: str = Field(default="", description="执行消息")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class AgentContext(BaseModel):
    """Agent执行上下文"""
    # 任务信息
    workflow_id: str = Field(..., description="任务ID (用于数据隔离，历史原因保留名称)")
    step_id: str = Field(..., description="当前步骤ID")
    user_id: str = Field(default="default_user", description="用户ID")
    browser_session_id: str = Field(default="global", description="浏览器会话ID (用于会话共享)")

    # 数据上下文
    variables: Dict[str, Any] = Field(default_factory=dict, description="上下文变量")
    step_results: Dict[str, Any] = Field(default_factory=dict, description="步骤结果")

    # 执行环境
    agent_instance: Optional[Any] = Field(default=None, description="BaseAgent实例")
    tools_registry: Optional[Any] = Field(default=None, description="工具注册表")
    memory_manager: Optional[Any] = Field(default=None, description="内存管理器")

    # 执行控制
    timeout: Optional[int] = Field(default=None, description="超时时间，None表示无超时")
    retry_count: int = Field(default=0, description="重试次数")

    # 日志和监控
    logger: Optional[Any] = Field(default=None, description="日志记录器")
    log_callback: Optional[Any] = Field(default=None, description="日志回调函数 (async callable)")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="执行指标")

    # 私有字段 - 浏览器会话信息
    _browser_session_info: Optional[Any] = PrivateAttr(default=None)

    class Config:
        """Pydantic配置"""
        arbitrary_types_allowed = True

    async def get_browser_session(self):
        """获取浏览器会话（懒加载）

        第一次调用时从 BrowserManager 获取会话，后续调用返回已有会话。
        所有浏览器会话必须通过 BrowserManager 统一管理。

        Returns:
            HybridBrowserSession: 浏览器会话实例
        """
        if not self._browser_session_info:
            # 获取 browser_manager（必须存在）
            browser_manager = getattr(self.agent_instance, 'browser_manager', None)

            if not browser_manager:
                error_msg = (
                    "BrowserManager is required but not found in agent_instance. "
                    "BaseAgent must be initialized with browser_manager parameter."
                )
                if self.logger:
                    self.logger.error(error_msg)
                else:
                    logger.error(error_msg)
                raise RuntimeError(error_msg)

            # 通过 BrowserManager 获取全局会话
            session = browser_manager.global_session

            if not session:
                error_msg = (
                    "Browser session not found in BrowserManager. "
                    "BrowserManager.start_browser() must be called first."
                )
                if self.logger:
                    self.logger.error(error_msg)
                else:
                    logger.error(error_msg)
                raise RuntimeError(error_msg)

            self._browser_session_info = session

            if self.logger:
                self.logger.info(
                    f"AgentContext retrieved browser session from BrowserManager"
                )
            else:
                logger.info(
                    f"AgentContext retrieved browser session from BrowserManager"
                )

        return self._browser_session_info

    async def cleanup_browser_session(self):
        """清理浏览器会话引用

        Note: 浏览器会话的实际关闭由 BrowserManager 统一管理。
        AgentContext 只需清理本地引用即可。
        """
        if self._browser_session_info:
            if self.logger:
                self.logger.info(
                    "AgentContext cleanup browser session reference "
                    "(actual session managed by BrowserManager)"
                )
            else:
                logger.info(
                    "AgentContext cleanup browser session reference "
                    "(actual session managed by BrowserManager)"
                )

            self._browser_session_info = None


# ==================== Extension Schemas ====================

class InterfaceSpec(BaseModel):
    """接口规格定义"""
    method_name: str = Field(..., description="方法名称")
    description: str = Field(..., description="方法描述")
    parameters: Dict[str, str] = Field(default_factory=dict, description="参数定义")
    return_type: str = Field(..., description="返回类型")
    is_async: bool = Field(default=False, description="是否异步")
    is_required: bool = Field(default=False, description="是否必须实现")
    example_usage: str = Field(default="", description="使用示例")


class ExtensionSpec(BaseModel):
    """扩展点规格定义"""
    name: str = Field(..., description="扩展点名称")
    description: str = Field(..., description="扩展点描述")
    extension_type: str = Field(..., description="扩展类型")
    parameters: Dict[str, str] = Field(default_factory=dict, description="参数定义")
    how_to_extend: str = Field(..., description="扩展方法说明")
    example: str = Field(default="", description="扩展示例")


class AgentCapabilitySpec(BaseModel):
    """Agent能力规格说明"""
    name: str = Field(..., description="Agent名称")
    description: str = Field(..., description="Agent描述")
    interfaces: Dict[str, InterfaceSpec] = Field(default_factory=dict, description="接口定义")
    supported_tools: List[str] = Field(default_factory=list, description="支持的工具")
    extension_points: Dict[str, ExtensionSpec] = Field(default_factory=dict, description="扩展点")