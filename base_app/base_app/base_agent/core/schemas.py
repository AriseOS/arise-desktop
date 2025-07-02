"""
Core data structures for BaseAgent and Workflow system
定义BaseAgent和工作流系统的核心数据结构
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


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

class AgentCapability(str, Enum):
    """Agent能力类型"""
    TEXT_GENERATION = "text_generation"
    TOOL_CALLING = "tool_calling"
    CODE_EXECUTION = "code_execution"
    MEMORY_MANAGEMENT = "memory_management"
    DATA_PROCESSING = "data_processing"


class TextAgentInput(BaseModel):
    """Text Agent 输入规范"""
    question: str = Field(..., description="用户的问题或请求")
    context_data: Dict[str, Any] = Field(default_factory=dict, description="上下文信息")
    response_style: str = Field(default="professional", description="回答风格：professional/casual/technical")
    max_length: int = Field(default=500, description="最大回答长度")
    language: str = Field(default="zh", description="回答语言")


class TextAgentOutput(BaseModel):
    """Text Agent 输出规范"""
    success: bool = Field(..., description="生成是否成功")
    answer: str = Field(..., description="生成的回答")
    word_count: int = Field(..., description="回答字数")
    error_message: Optional[str] = Field(default=None, description="错误信息")


class ToolAgentInput(BaseModel):
    """Tool Agent 输入规范"""
    task_description: str = Field(..., description="任务描述，用自然语言描述要完成什么")
    context_data: Dict[str, Any] = Field(default_factory=dict, description="上下文数据")
    constraints: List[str] = Field(default_factory=list, description="约束条件")
    allowed_tools: List[str] = Field(default_factory=list, description="允许使用的工具列表")
    fallback_tools: List[str] = Field(default_factory=list, description="备选工具列表")
    confidence_threshold: float = Field(default=0.8, description="工具选择置信度阈值")


class ToolAgentOutput(BaseModel):
    """Tool Agent 输出规范"""
    success: bool = Field(..., description="执行是否成功")
    result: Any = Field(..., description="执行结果")
    tool_used: str = Field(..., description="使用的工具名称")
    action_taken: str = Field(..., description="执行的具体动作")
    confidence: float = Field(..., description="工具选择置信度 0-1")
    reasoning: str = Field(..., description="工具选择推理过程")
    alternatives_tried: List[str] = Field(default_factory=list, description="尝试过的备选工具")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="执行元数据")
    error_message: Optional[str] = Field(default=None, description="错误信息")


class CodeAgentInput(BaseModel):
    """Code Agent 输入规范"""
    task_description: str = Field(..., description="任务描述，用自然语言描述要完成什么")
    input_data: Any = Field(..., description="输入数据")
    expected_output_format: str = Field(..., description="期望的输出格式描述")
    constraints: List[str] = Field(default_factory=list, description="约束条件")
    libraries_allowed: List[str] = Field(default_factory=list, description="允许使用的库")


class CodeAgentOutput(BaseModel):
    """Code Agent 输出规范"""
    success: bool = Field(..., description="执行是否成功")
    result: Any = Field(..., description="代码执行结果")
    code_generated: str = Field(..., description="生成的代码")
    execution_info: Dict[str, Any] = Field(default_factory=dict, description="执行信息")
    stdout: str = Field(default="", description="标准输出")
    stderr: str = Field(default="", description="错误输出")
    error_message: Optional[str] = Field(default=None, description="错误信息")


class AgentContext(BaseModel):
    """Agent执行上下文"""
    # 工作流信息
    workflow_id: str = Field(..., description="工作流ID")
    step_id: str = Field(..., description="当前步骤ID")
    
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


# ==================== Workflow Schemas ====================

class StepType(str, Enum):
    """工作流步骤类型"""
    AGENT = "agent"        # 调用其他Agent
    TOOL = "tool"          # 调用工具
    CODE = "code"          # 执行代码
    MEMORY = "memory"      # 内存操作


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
    agent_type: str = Field(..., description="Agent类型: text_agent | tool_agent | code_agent | auto")
    task_description: str = Field(..., description="任务描述")
    
    # 输入配置
    input_ports: Dict[str, Any] = Field(default_factory=dict, description="输入映射")
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
    output_ports: Dict[str, str] = Field(default_factory=dict, description="输出映射")
    
    # 执行控制
    condition: Optional[str] = Field(default=None, description="执行条件")
    timeout: int = Field(default=300, description="超时时间")
    retry_count: int = Field(default=0, description="重试次数")


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