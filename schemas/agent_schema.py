"""
Agent相关的数据结构定义
定义Agent的标准Schema和数据模型
"""
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
import uuid


class AgentStatus(str, Enum):
    """Agent状态枚举"""
    CREATED = "created"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class AgentPriority(str, Enum):
    """Agent优先级枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class AgentResult(BaseModel):
    """Agent执行结果"""
    success: bool = Field(..., description="执行是否成功")
    data: Any = Field(default=None, description="返回数据")
    message: str = Field(default="", description="执行消息")
    status: AgentStatus = Field(default=AgentStatus.COMPLETED, description="执行状态")
    execution_time: float = Field(default=0.0, description="执行时间(秒)")
    error_details: Optional[Dict[str, Any]] = Field(default=None, description="错误详情")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")


class AgentConfig(BaseModel):
    """Agent配置"""
    name: str = Field(..., description="Agent名称")
    description: str = Field(default="", description="Agent描述")
    version: str = Field(default="1.0.0", description="Agent版本")
    
    # 执行配置
    timeout: int = Field(default=300, description="超时时间(秒)")
    max_retries: int = Field(default=3, description="最大重试次数")
    retry_delay: float = Field(default=1.0, description="重试延迟(秒)")
    priority: AgentPriority = Field(default=AgentPriority.MEDIUM, description="执行优先级")
    
    # 资源配置
    max_memory_mb: int = Field(default=512, description="最大内存使用(MB)")
    max_cpu_percent: float = Field(default=50.0, description="最大CPU使用率(%)")
    
    # 日志配置
    enable_logging: bool = Field(default=True, description="是否启用日志")
    log_level: str = Field(default="INFO", description="日志级别")
    
    # 持久化配置
    enable_persistence: bool = Field(default=True, description="是否启用状态持久化")
    checkpoint_interval: int = Field(default=60, description="检查点间隔(秒)")


class WorkflowStep(BaseModel):
    """工作流步骤定义"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="步骤ID")
    name: str = Field(..., description="步骤名称")
    description: str = Field(default="", description="步骤描述")
    
    # 执行配置
    tool_name: str = Field(..., description="使用的工具名称")
    action: str = Field(..., description="执行的动作")
    params: Dict[str, Any] = Field(default_factory=dict, description="动作参数")
    
    # 流程控制
    depends_on: List[str] = Field(default_factory=list, description="依赖的步骤ID")
    condition: Optional[str] = Field(default=None, description="执行条件")
    timeout: Optional[int] = Field(default=None, description="步骤超时时间")
    retry_count: int = Field(default=0, description="重试次数")
    
    # 结果处理
    output_key: Optional[str] = Field(default=None, description="输出结果的存储键")
    error_handling: str = Field(default="stop", description="错误处理策略: stop, continue, retry")


class WorkflowResult(BaseModel):
    """工作流执行结果"""
    success: bool = Field(..., description="工作流是否成功")
    completed_steps: List[str] = Field(default_factory=list, description="已完成步骤ID")
    failed_steps: List[str] = Field(default_factory=list, description="失败步骤ID")
    step_results: Dict[str, Any] = Field(default_factory=dict, description="各步骤结果")
    total_execution_time: float = Field(default=0.0, description="总执行时间")
    error_message: Optional[str] = Field(default=None, description="错误信息")


class AgentState(BaseModel):
    """Agent状态"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="状态ID")
    agent_id: str = Field(..., description="Agent ID")
    status: AgentStatus = Field(..., description="当前状态")
    
    # 执行上下文
    current_step: Optional[str] = Field(default=None, description="当前执行步骤")
    step_index: int = Field(default=0, description="步骤索引")
    variables: Dict[str, Any] = Field(default_factory=dict, description="变量状态")
    memory: Dict[str, Any] = Field(default_factory=dict, description="内存状态")
    
    # 时间信息
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    started_at: Optional[datetime] = Field(default=None, description="开始时间")
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")
    
    # 执行统计
    execution_count: int = Field(default=0, description="执行次数")
    success_count: int = Field(default=0, description="成功次数")
    error_count: int = Field(default=0, description="错误次数")


class AgentCapabilitySpec(BaseModel):
    """Agent能力规格描述"""
    name: str = Field(..., description="能力名称")
    description: str = Field(..., description="能力描述")
    
    # 接口定义
    interfaces: Dict[str, "InterfaceSpec"] = Field(default_factory=dict, description="接口规格")
    
    # 工具支持
    supported_tools: List[str] = Field(default_factory=list, description="支持的工具列表")
    
    # 扩展点
    extension_points: Dict[str, "ExtensionSpec"] = Field(default_factory=dict, description="扩展点")
    
    # 示例代码
    examples: List["CodeExample"] = Field(default_factory=list, description="使用示例")


class InterfaceSpec(BaseModel):
    """接口规格定义"""
    method_name: str = Field(..., description="方法名称")
    description: str = Field(..., description="方法描述")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="参数定义")
    return_type: str = Field(..., description="返回类型")
    is_async: bool = Field(default=True, description="是否异步方法")
    is_required: bool = Field(default=False, description="是否必须实现")
    example_usage: str = Field(default="", description="使用示例")


class ExtensionSpec(BaseModel):
    """扩展点规格定义"""
    name: str = Field(..., description="扩展点名称")
    description: str = Field(..., description="扩展点描述")
    extension_type: str = Field(..., description="扩展类型: hook, plugin, override")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="扩展参数")
    how_to_extend: str = Field(..., description="扩展方法说明")
    example: str = Field(default="", description="扩展示例")


class CodeExample(BaseModel):
    """代码示例"""
    title: str = Field(..., description="示例标题")
    description: str = Field(..., description="示例描述")
    code: str = Field(..., description="示例代码")
    language: str = Field(default="python", description="编程语言")
    tags: List[str] = Field(default_factory=list, description="示例标签")


class AgentTemplate(BaseModel):
    """Agent模板定义"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="模板ID")
    name: str = Field(..., description="模板名称")
    description: str = Field(..., description="模板描述")
    category: str = Field(..., description="模板分类")
    
    # 模板内容
    base_code: str = Field(..., description="基础代码模板")
    config_template: AgentConfig = Field(..., description="配置模板")
    workflow_template: List[WorkflowStep] = Field(default_factory=list, description="工作流模板")
    
    # 模板元数据
    required_tools: List[str] = Field(default_factory=list, description="需要的工具")
    capabilities: List[str] = Field(default_factory=list, description="模板能力")
    use_cases: List[str] = Field(default_factory=list, description="使用场景")
    
    # 版本信息
    version: str = Field(default="1.0.0", description="模板版本")
    author: str = Field(default="AgentCrafter", description="模板作者")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")


class AgentCreationRequest(BaseModel):
    """Agent创建请求"""
    name: str = Field(..., description="Agent名称")
    description: str = Field(..., description="Agent描述")
    requirements: str = Field(..., description="用户需求描述")
    
    # 可选配置
    preferred_tools: List[str] = Field(default_factory=list, description="偏好工具")
    template_id: Optional[str] = Field(default=None, description="基础模板ID")
    config: Optional[AgentConfig] = Field(default=None, description="自定义配置")
    
    # 生成选项
    generate_tests: bool = Field(default=True, description="是否生成测试")
    generate_docs: bool = Field(default=True, description="是否生成文档")
    include_examples: bool = Field(default=True, description="是否包含示例")


class AgentCreationResult(BaseModel):
    """Agent创建结果"""
    success: bool = Field(..., description="创建是否成功")
    agent_id: str = Field(..., description="生成的Agent ID")
    
    # 生成内容
    agent_code: str = Field(..., description="生成的Agent代码")
    config: AgentConfig = Field(..., description="Agent配置")
    workflow: List[WorkflowStep] = Field(default_factory=list, description="工作流定义")
    
    # 文档和测试
    documentation: str = Field(default="", description="生成的文档")
    test_code: str = Field(default="", description="生成的测试代码")
    usage_examples: List[CodeExample] = Field(default_factory=list, description="使用示例")
    
    # 推荐信息
    recommended_tools: List[str] = Field(default_factory=list, description="推荐工具")
    design_analysis: Dict[str, Any] = Field(default_factory=dict, description="设计分析")
    
    # 元数据
    generation_time: float = Field(default=0.0, description="生成耗时")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


# 更新前向引用
AgentCapabilitySpec.model_rebuild()
InterfaceSpec.model_rebuild()
ExtensionSpec.model_rebuild()
CodeExample.model_rebuild()