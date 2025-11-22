"""
Core data structures for BaseAgent and Workflow system
定义BaseAgent和工作流系统的核心数据结构
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
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
    
    # 工作流配置
    default_workflow: Optional[str] = Field(default=None, description="默认工作流名称")
    enable_workflow_cache: bool = Field(default=True, description="是否启用工作流缓存")


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
    current_workflow: Optional[str] = Field(default=None, description="当前工作流")
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
    workflow_id: Optional[str] = Field(default=None, description="工作流ID")
    step_count: int = Field(default=0, description="执行步骤数")
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")
    timestamp: datetime = Field(default_factory=datetime.now, description="执行时间戳")


# ==================== Agent-as-Step Schemas ====================

class AgentInput(BaseModel):
    """统一的Agent输入模型"""
    instruction: str = Field(..., description="执行指令")
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
    # 工作流信息
    workflow_id: str = Field(..., description="工作流ID (用于脚本组织)")
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
    timeout: int = Field(default=300, description="超时时间")
    retry_count: int = Field(default=0, description="重试次数")

    # 日志和监控
    logger: Optional[Any] = Field(default=None, description="日志记录器")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="执行指标")

    # 私有字段 - 浏览器会话管理
    _browser_session_manager: Optional[Any] = PrivateAttr(default=None)
    _browser_session_info: Optional[Any] = PrivateAttr(default=None)

    class Config:
        """Pydantic配置"""
        arbitrary_types_allowed = True

    async def get_browser_session(self):
        """获取浏览器会话（懒加载）

        第一次调用时创建会话，后续调用返回已有会话。
        所有需要浏览器的Agent都会共享同一个会话。
        """
        if not self._browser_session_info:
            # 动态导入，避免循环依赖
            from ..tools.browser_session_manager import BrowserSessionManager

            # 获取会话管理器
            if not self._browser_session_manager:
                self._browser_session_manager = await BrowserSessionManager.get_instance()

            # 获取配置服务
            config_service = getattr(self.agent_instance, 'config_service', None)

            # 创建或获取会话 (使用 browser_session_id 以便多个 workflow 共享同一会话)
            self._browser_session_info = await self._browser_session_manager.get_or_create_session(
                session_id=self.browser_session_id,
                config_service=config_service,
                headless=False,  # 可以从配置中读取
                keep_alive=True
            )

            if self.logger:
                self.logger.info(f"Workflow {self.workflow_id} 使用浏览器会话 {self.browser_session_id}")
            else:
                logger.info(f"Workflow {self.workflow_id} 使用浏览器会话 {self.browser_session_id}")

        return self._browser_session_info

    async def cleanup_browser_session(self):
        """清理浏览器会话引用

        释放会话引用，但不关闭浏览器（可能有其他workflow在使用）。
        """
        if self._browser_session_info and self._browser_session_manager:
            self._browser_session_manager.release_session(self.browser_session_id)
            if self.logger:
                self.logger.info(f"Workflow {self.workflow_id} 释放浏览器会话引用")
            else:
                logger.info(f"Workflow {self.workflow_id} 释放浏览器会话引用")

            self._browser_session_info = None


# ==================== Workflow Schemas ====================

class StepType(str, Enum):
    """工作流步骤类型"""
    AGENT = "agent"        # 调用其他Agent
    TOOL = "tool"          # 调用工具
    CODE = "code"          # 执行代码
    MEMORY = "memory"      # 内存操作
    IF = "if"              # 条件分支控制
    WHILE = "while"        # 循环控制


class ErrorHandling(str, Enum):
    """错误处理策略"""
    STOP = "stop"          # 停止整个工作流
    CONTINUE = "continue"  # 继续执行下一步
    RETRY = "retry"        # 重试当前步骤
    SKIP = "skip"          # 跳过当前步骤


class AgentWorkflowStep(BaseModel):
    """Agent工作流步骤"""
    # 基础信息
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="步骤名称")
    description: str = Field(default="", description="步骤描述")
    
    # Agent配置
    agent_type: str = Field(..., description="Agent类型: text_agent | tool_agent | code_agent | if | while | foreach")
    user_task: Optional[str] = Field(default=None, description="用户具体任务内容")
    
    # 输入配置
    inputs: Dict[str, Any] = Field(default_factory=dict, description="输入映射")
    constraints: List[str] = Field(default_factory=list, description="约束条件")
    
    # Tool Agent 特有配置
    allowed_tools: List[str] = Field(default_factory=list, description="允许使用的工具列表")
    fallback_tools: List[str] = Field(default_factory=list, description="备选工具列表") 
    confidence_threshold: float = Field(default=0.8, description="工具选择置信度阈值")
    
    # Code Agent 特有配置
    allowed_libraries: List[str] = Field(default_factory=list, description="允许使用的代码库")
    expected_output_format: str = Field(default="", description="期望的输出格式")
    
    # Text Agent 特有配置
    response_style: str = Field(default="professional", description="回答风格")
    max_length: int = Field(default=500, description="最大回答长度")
    
    # 输出配置  
    outputs: Dict[str, str] = Field(default_factory=dict, description="输出映射")
    
    # 执行控制
    condition: Optional[str] = Field(default=None, description="执行条件")
    timeout: int = Field(default=300, description="超时时间")
    retry_count: int = Field(default=0, description="重试次数")
    
    # 控制流相关字段 (仅当agent_type为if/while/foreach时使用)
    then: Optional[List['AgentWorkflowStep']] = Field(default=None, description="if条件为真时执行的步骤")
    else_: Optional[List['AgentWorkflowStep']] = Field(default=None, alias="else", description="if条件为假时执行的步骤")
    steps: Optional[List['AgentWorkflowStep']] = Field(default=None, description="while/foreach循环体步骤")
    max_iterations: Optional[int] = Field(default=None, description="while/foreach最大循环次数，None表示无限制")
    loop_timeout: Optional[int] = Field(default=300, description="while/foreach循环超时时间")

    # foreach 特有配置
    source: Optional[str] = Field(default=None, description="foreach遍历的源列表变量名（如 '{{all_product_urls}}'）")
    item_var: Optional[str] = Field(default="item", description="foreach当前项的变量名")
    index_var: Optional[str] = Field(default="index", description="foreach当前索引的变量名")

    # Variable Agent 特有配置
    operation: Optional[str] = Field(default=None, description="Variable operation type")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Data for set operation")
    source: Optional[str] = Field(default=None, description="Source variable for operations")
    field: Optional[str] = Field(default=None, description="Field for extract operation")
    value: Optional[Any] = Field(default=None, description="Value for increment/decrement")
    expression: Optional[str] = Field(default=None, description="Expression for calculate")
    updates: Optional[Dict[str, Any]] = Field(default=None, description="Updates for update operation")
    current_page: Optional[Any] = Field(default=None, description="Current page for condition check")
    max_pages: Optional[Any] = Field(default=None, description="Max pages for condition check")
    items_found: Optional[Any] = Field(default=None, description="Items found for condition check")


class StepResult(BaseModel):
    """单步执行结果"""
    step_id: str = Field(..., description="步骤ID")
    success: bool = Field(..., description="执行是否成功")
    data: Any = Field(default=None, description="步骤输出数据")
    message: str = Field(default="", description="执行消息")
    
    # 执行信息
    execution_time: float = Field(default=0.0, description="执行时间(秒)")
    retry_count: int = Field(default=0, description="实际重试次数")
    
    # 状态信息
    started_at: datetime = Field(default_factory=datetime.now, description="开始时间")
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")
    
    # 错误信息
    error: Optional[str] = Field(default=None, description="错误信息")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")
    
    # 控制流相关字段 (仅当step_type为控制流时使用)
    step_type: Optional[str] = Field(default="agent", description="步骤类型：agent/if/while")
    condition_result: Optional[bool] = Field(default=None, description="条件评估结果")
    branch_executed: Optional[str] = Field(default=None, description="执行的分支：then/else/loop")
    iterations_executed: Optional[int] = Field(default=None, description="实际执行的循环次数")
    exit_reason: Optional[str] = Field(default=None, description="退出原因")
    sub_step_results: List['StepResult'] = Field(default_factory=list, description="子步骤执行结果")


class ExecutionContext(BaseModel):
    """工作流执行上下文"""
    workflow_id: str = Field(..., description="工作流ID")
    
    # 执行状态
    current_step_index: int = Field(default=0, description="当前步骤索引")
    completed_steps: List[str] = Field(default_factory=list, description="已完成步骤")
    failed_steps: List[str] = Field(default_factory=list, description="失败步骤")
    
    # 数据存储
    variables: Dict[str, Any] = Field(default_factory=dict, description="执行变量")
    step_results: Dict[str, Any] = Field(default_factory=dict, description="步骤结果")
    
    # 时间信息
    started_at: datetime = Field(default_factory=datetime.now, description="开始时间")
    
    # 配置信息
    max_execution_time: int = Field(default=3600, description="最大执行时间")
    enable_parallel: bool = Field(default=False, description="是否启用并行执行")


class Workflow(BaseModel):
    """完整工作流定义"""
    # 基础信息
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="工作流ID")
    name: str = Field(..., description="工作流名称")
    description: str = Field(default="", description="工作流描述")
    version: str = Field(default="1.0.0", description="版本号")
    
    # 步骤定义
    steps: List['AgentWorkflowStep'] = Field(..., description="工作流步骤")
    
    # 输入输出定义
    input_schema: Dict[str, Any] = Field(default_factory=dict, description="输入参数定义")
    output_schema: Dict[str, Any] = Field(default_factory=dict, description="输出结果定义")
    
    # 执行配置
    max_execution_time: int = Field(default=3600, description="最大执行时间(秒)")
    enable_parallel: bool = Field(default=False, description="是否启用并行执行")
    enable_cache: bool = Field(default=True, description="是否启用缓存")
    
    # 元数据
    tags: List[str] = Field(default_factory=list, description="标签")
    author: str = Field(default="AgentCrafter", description="作者")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")


class WorkflowResult(BaseModel):
    """工作流执行结果"""
    # 基础结果
    success: bool = Field(..., description="执行是否成功")
    workflow_id: str = Field(..., description="工作流ID")
    
    # 执行统计
    completed_steps: List[str] = Field(default_factory=list, description="已完成步骤")
    failed_steps: List[str] = Field(default_factory=list, description="失败步骤")
    step_results: Dict[str, Any] = Field(default_factory=dict, description="步骤结果")
    steps: List['StepResult'] = Field(default_factory=list, description="步骤执行结果列表")
    
    # 时间信息
    total_execution_time: float = Field(default=0.0, description="总执行时间(秒)")
    started_at: datetime = Field(default_factory=datetime.now, description="开始时间")
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")
    
    # 输出数据
    final_result: Any = Field(default=None, description="最终结果")
    output_variables: Dict[str, Any] = Field(default_factory=dict, description="输出变量")
    
    # 错误信息
    error_message: Optional[str] = Field(default=None, description="错误消息")
    error_details: List[Dict[str, Any]] = Field(default_factory=list, description="详细错误信息")
    
    # 性能信息
    memory_usage_mb: float = Field(default=0.0, description="内存使用量(MB)")
    step_execution_times: Dict[str, float] = Field(default_factory=dict, description="各步骤执行时间")


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