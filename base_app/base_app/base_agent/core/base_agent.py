"""
BaseAgent 基础框架
所有定制Agent的基础类，提供标准化接口和能力
"""
import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Callable, Union
from datetime import datetime
import json

from .schemas import (
    AgentConfig, AgentResult, AgentState, AgentStatus, AgentPriority,
    WorkflowResult, Workflow, AgentCapabilitySpec, InterfaceSpec, ExtensionSpec,
    StepType, ErrorHandling, AgentWorkflowStep
)
from .agent_workflow_engine import AgentWorkflowEngine
from ..tools.base_tool import BaseTool, ToolResult, ToolStatus
from ..memory.memory_manager import MemoryManager

logger = logging.getLogger(__name__)


class BaseAgent:
    """
    通用Agent基础框架
    所有定制Agent都继承此类，提供标准化接口
    
    核心设计原则：
    1. 标准化接口 - 为AI工具提供清晰的扩展规范
    2. 工具集成 - 无缝集成各种外部工具
    3. 状态管理 - 完整的执行状态和内存管理
    4. 可扩展性 - 支持钩子和插件机制
    """
    
    def __init__(
        self, 
        config: Optional[AgentConfig] = None,
        enable_memory: bool = False,
        memory_config: Optional[Dict[str, Any]] = None,
        provider_config: Optional[Dict[str, Any]] = None
    ):
        # 基础配置
        self.config = config or AgentConfig(name="BaseAgent")
        self.id = str(uuid.uuid4())
        
        # 核心组件
        self.tools: Dict[str, BaseTool] = {}
        self.hooks: Dict[str, List[Callable]] = {}
        
        # Provider初始化
        self.provider = None
        self.provider_config = provider_config or {}
        self._initialize_provider()
        
        # 内存管理
        self.memory_manager = None
        if enable_memory:
            try:
                self.memory_manager = MemoryManager(
                    enable_long_term_memory=True,
                    user_id=f"agent_{self.id}",
                    mem0_config=memory_config
                )
                logger.info("内存管理器初始化成功")
            except Exception as e:
                logger.warning(f"内存管理器初始化失败: {e}")
        
        # Agent工作流引擎
        try:
            self.agent_workflow_engine = AgentWorkflowEngine(agent_instance=self)
            logger.info("Agent工作流引擎初始化成功")
        except ImportError as e:
            logger.error(f"Agent工作流引擎初始化失败: {e}")
            self.agent_workflow_engine = None
        
        # 状态管理
        self.state = AgentState(
            agent_id=self.id,
            status=AgentStatus.CREATED
        )
        
        # 执行统计
        self._execution_history: List[Dict[str, Any]] = []
        self._last_checkpoint: Optional[datetime] = None
        
        # 默认工作流
        self._default_workflows = {}
        self._load_default_workflows()
        
        # 初始化日志
        self._setup_logging()
        
        logger.info(f"BaseAgent {self.config.name} ({self.id}) 初始化完成")
    
    # ==================== 标准化接口 ====================
    
    async def execute(self, input_data: Any, **kwargs) -> AgentResult:
        """
        主执行入口 - 子类必须实现
        
        Args:
            input_data: 输入数据
            **kwargs: 额外参数
            
        Returns:
            AgentResult: 执行结果
            
        Example:
            async def execute(self, task: str, **kwargs) -> AgentResult:
                # 实现具体的Agent逻辑
                result = await self.use_tool('browser', 'navigate', {'url': 'https://example.com'})
                return AgentResult(success=True, data=result.data)
        """
        raise NotImplementedError("子类必须实现 execute 方法")
    
    async def initialize(self) -> bool:
        """
        初始化Agent
        
        Returns:
            bool: 初始化是否成功
            
        Example:
            async def initialize(self) -> bool:
                # 初始化工具
                await self.register_tool('browser', BrowserTool())
                # 加载配置
                await self.load_memory('user_preferences')
                return await super().initialize()
        """
        try:
            self.state.status = AgentStatus.INITIALIZING
            await self._trigger_hook('before_initialize')
            
            # 初始化Provider
            if self.provider:
                provider_success = await self.initialize_provider_async()
                if not provider_success:
                    logger.error("Provider初始化失败，无法进行大模型推理")
                    self.state.status = AgentStatus.FAILED
                    return False
            else:
                logger.error("Provider未设置，无法进行大模型推理")
                self.state.status = AgentStatus.FAILED
                return False
            
            # 初始化所有工具
            for tool_name, tool in self.tools.items():
                success = await tool.initialize()
                if not success:
                    logger.error(f"工具 {tool_name} 初始化失败")
                    return False
            
            self.state.status = AgentStatus.READY
            self.state.started_at = datetime.now()
            
            await self._trigger_hook('after_initialize')
            logger.info(f"Agent {self.config.name} 初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"Agent初始化失败: {e}")
            self.state.status = AgentStatus.FAILED
            return False
    
    async def cleanup(self) -> bool:
        """
        清理资源
        
        Returns:
            bool: 清理是否成功
            
        Example:
            async def cleanup(self) -> bool:
                # 保存状态
                await self.save_checkpoint()
                # 清理自定义资源
                await self.custom_cleanup()
                return await super().cleanup()
        """
        try:
            await self._trigger_hook('before_cleanup')
            
            # 清理所有工具
            for tool_name, tool in self.tools.items():
                await tool.cleanup()
            
            # 保存最终状态
            if self.config.enable_persistence:
                await self.save_checkpoint()
            
            self.state.status = AgentStatus.STOPPED
            self.state.completed_at = datetime.now()
            
            await self._trigger_hook('after_cleanup')
            logger.info(f"Agent {self.config.name} 清理完成")
            return True
            
        except Exception as e:
            logger.error(f"Agent清理失败: {e}")
            return False
    
    # ==================== 工具调用接口 ====================
    
    async def use_tool(
        self, 
        tool_name: str, 
        action: str, 
        params: Dict[str, Any],
        **kwargs
    ) -> ToolResult:
        """
        标准化工具调用接口
        
        Args:
            tool_name: 工具名称
            action: 动作名称
            params: 动作参数
            **kwargs: 额外参数
            
        Returns:
            ToolResult: 工具执行结果
            
        Raises:
            ValueError: 工具未注册或参数无效
            
        Example:
            # 使用浏览器工具导航
            result = await self.use_tool('browser', 'navigate', {
                'url': 'https://example.com'
            })
            
            # 使用Android工具读取微信
            result = await self.use_tool('android', 'read_chat', {
                'app': '微信',
                'contact': '客户A'
            })
        """
        if tool_name not in self.tools:
            raise ValueError(f"工具 '{tool_name}' 未注册")
        
        tool = self.tools[tool_name]
        
        try:
            await self._trigger_hook('before_tool_call', tool_name=tool_name, action=action)
            
            # 记录工具调用
            call_info = {
                'tool': tool_name,
                'action': action,
                'params': params,
                'timestamp': datetime.now()
            }
            self._execution_history.append(call_info)
            
            # 执行工具调用
            result = await tool.execute_with_retry(action, params, **kwargs)
            
            # 更新调用记录
            call_info['result'] = {
                'success': result.success,
                'execution_time': result.execution_time
            }
            
            await self._trigger_hook('after_tool_call', tool_name=tool_name, result=result)
            
            logger.debug(f"工具调用完成: {tool_name}.{action} -> {result.success}")
            return result
            
        except Exception as e:
            logger.error(f"工具调用失败: {tool_name}.{action}, 错误: {e}")
            return ToolResult(
                success=False,
                message=f"工具调用失败: {str(e)}",
                status=ToolStatus.ERROR
            )
    
    def register_tool(self, name: str, tool: BaseTool) -> None:
        """
        注册工具
        
        Args:
            name: 工具名称
            tool: 工具实例
            
        Example:
            # 注册浏览器工具
            self.register_tool('browser', BrowserTool(config))
            
            # 注册自定义工具
            self.register_tool('custom', MyCustomTool())
        """
        if not isinstance(tool, BaseTool):
            raise ValueError(f"工具必须继承自 BaseTool")
        
        self.tools[name] = tool
        logger.info(f"工具 '{name}' 注册成功: {tool.metadata.description}")
    
    def unregister_tool(self, name: str) -> bool:
        """
        注销工具
        
        Args:
            name: 工具名称
            
        Returns:
            bool: 是否成功注销
        """
        if name in self.tools:
            del self.tools[name]
            logger.info(f"工具 '{name}' 已注销")
            return True
        return False
    
    def get_registered_tools(self) -> List[str]:
        """
        获取已注册的工具列表
        
        Returns:
            List[str]: 工具名称列表
        """
        return list(self.tools.keys())
    
    # ==================== 内存管理接口 ====================
    
    async def store_memory(self, key: str, value: Any) -> None:
        """
        存储临时变量
        
        Args:
            key: 存储键
            value: 存储值
            
        Example:
            # 存储临时数据
            await self.store_memory('temp_data', {'result': 'success'})
        """
        if self.memory_manager:
            await self.memory_manager.store_memory(key, value)
        else:
            # 如果没有memory_manager，使用简单的变量存储
            if not hasattr(self, '_variables'):
                self._variables = {}
            self._variables[key] = value
        
        logger.debug(f"临时变量存储: {key}")
    
    async def get_memory(self, key: str, default: Any = None) -> Any:
        """
        获取临时变量
        
        Args:
            key: 存储键
            default: 默认值
            
        Returns:
            Any: 存储的值
            
        Example:
            # 获取变量
            temp_data = await self.get_memory('temp_data')
        """
        if self.memory_manager:
            return await self.memory_manager.get_memory(key, default)
        else:
            # 如果没有memory_manager，使用简单的变量存储
            if not hasattr(self, '_variables'):
                self._variables = {}
            return self._variables.get(key, default)
    
    async def clear_memory(self) -> None:
        """
        清空临时变量
        """
        if self.memory_manager:
            await self.memory_manager.clear_memory()
        else:
            if hasattr(self, '_variables'):
                self._variables.clear()
        
        logger.info("临时变量已清空")
    
    # 长期记忆接口
    async def add_long_term_memory(self, content: str, user_id: str = None) -> Optional[str]:
        """
        添加长期记忆
        
        Args:
            content: 记忆内容
            user_id: 用户ID
            
        Returns:
            Optional[str]: 记忆ID
        """
        if self.memory_manager:
            return await self.memory_manager.add_long_term_memory(content, user_id)
        else:
            logger.warning("长期记忆未启用")
            return None
    
    async def search_long_term_memory(
        self, 
        query: str, 
        user_id: str = None, 
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        搜索长期记忆
        
        Args:
            query: 搜索查询
            user_id: 用户ID
            limit: 结果数量限制
            
        Returns:
            List[Dict[str, Any]]: 搜索结果
        """
        if self.memory_manager:
            return await self.memory_manager.search_long_term_memory(query, user_id, limit)
        else:
            logger.warning("长期记忆未启用")
            return []
    
    # ==================== 工作流接口 ====================
    
    async def run_workflow(
        self, 
        workflow: Union[Workflow, List[AgentWorkflowStep]], 
        input_data: Dict[str, Any] = None
    ) -> WorkflowResult:
        """
        执行工作流
        
        Args:
            workflow: 工作流定义或步骤列表
            input_data: 输入数据
            
        Returns:
            WorkflowResult: 工作流执行结果
            
        Example:
            # 使用步骤列表
            steps = [
                AgentWorkflowStep(
                    name="搜索记忆",
                    step_type=StepType.MEMORY,
                    memory_action="search",
                    query="用户偏好"
                ),
                AgentWorkflowStep(
                    name="生成响应",
                    step_type=StepType.CODE,
                    code="result = f'基于记忆: {step_results}'"
                )
            ]
            result = await self.run_workflow(steps)
            
            # 使用完整工作流
            workflow = Workflow(name="用户问答", steps=steps)
            result = await self.run_workflow(workflow, {"user_input": "你好"})
        """
        if isinstance(workflow, list):
            # 现在所有步骤都是AgentWorkflowStep，直接使用Agent工作流引擎
            if self.agent_workflow_engine:
                return await self.agent_workflow_engine.execute_workflow(
                    workflow,
                    input_data=input_data or {}
                )
            else:
                raise RuntimeError("Agent工作流引擎未初始化，无法执行工作流")
        else:
            # 现在所有工作流都使用AgentWorkflowStep，直接使用Agent工作流引擎
            if self.agent_workflow_engine:
                return await self.agent_workflow_engine.execute_workflow(
                    workflow.steps,
                    workflow_id=workflow.name,
                    input_data=input_data or {}
                )
            else:
                raise RuntimeError("Agent工作流引擎未初始化，无法执行工作流")
    
    async def process_user_input(self, user_input: str, user_id: str = None) -> str:
        """
        处理用户输入的主方法 - BaseAgent的标准执行流程
        
        Args:
            user_input: 用户输入
            user_id: 用户ID
            
        Returns:
            str: 处理结果
            
        这是BaseAgent的核心方法，按照以下流程处理用户输入：
        1. 分析用户输入
        2. 搜索相关记忆
        3. 根据需要调用工具
        4. 整合信息并生成响应
        """
        # 获取或创建默认的用户问答工作流
        workflow = self._get_default_workflow("user_qa")
        
        # 执行工作流
        result = await self.run_workflow(workflow, {
            "user_input": user_input,
            "user_id": user_id or f"user_{int(time.time())}"
        })
        
        if result.success:
            # 返回最终结果
            if result.final_result:
                logger.info(f"result.final_result: {str(result.final_result)}")
                return str(result.final_result)
            else:
                return "处理完成，但未生成具体结果"
        else:
            error_msg = f"处理失败: {result.error_message}"
            logger.error(error_msg)
            return error_msg
    
    
    # ==================== 状态管理 ====================
    
    async def save_checkpoint(self) -> bool:
        """
        保存检查点
        
        Returns:
            bool: 是否保存成功
        """
        try:
            if not self.config.enable_persistence:
                return True
            
            checkpoint_data = {
                'state': self.state.dict(),
                'variables': self.variables,
                'memory': self.memory,
                'execution_history': self._execution_history[-10:]  # 只保存最近10条
            }
            
            # 实际实现中这里应该保存到数据库或文件
            logger.debug(f"检查点已保存: {self.id}")
            self._last_checkpoint = datetime.now()
            return True
            
        except Exception as e:
            logger.error(f"保存检查点失败: {e}")
            return False
    
    async def restore_checkpoint(self, checkpoint_id: str) -> bool:
        """
        恢复检查点
        
        Args:
            checkpoint_id: 检查点ID
            
        Returns:
            bool: 是否恢复成功
        """
        try:
            # 实际实现中这里应该从数据库或文件加载
            logger.debug(f"检查点已恢复: {checkpoint_id}")
            return True
            
        except Exception as e:
            logger.error(f"恢复检查点失败: {e}")
            return False
    
    # ==================== 私有方法 ====================
    
    def _load_default_workflows(self) -> None:
        """加载默认工作流"""
        # 用户问答工作流
        self._default_workflows["user_qa"] = self._create_user_qa_workflow()
    
    def _get_default_workflow(self, name: str) -> Workflow:
        """获取默认工作流"""
        if name in self._default_workflows:
            return self._default_workflows[name]
        else:
            logger.warning(f"未找到默认工作流: {name}")
            return self._create_simple_workflow()
    
    def _create_user_qa_workflow(self) -> Workflow:
        """创建用户问答默认工作流 - 基于Provider的3步式架构"""
        
        steps = [
            # 步骤1: 意图识别 (Text Agent + Provider)
            AgentWorkflowStep(
                id="intent_analysis",
                name="意图识别",
                description="使用大模型分析用户意图，判断需要工具调用、复杂分析还是普通聊天",
                agent_type="text_agent",
                task_description="分析用户输入，判断意图类型。请只返回以下三个选项之一：'tool'(需要工具调用)、'code'(需要复杂分析/计算)、'chat'(普通聊天)",
                input_ports={
                    "context_data": {
                        "user_input": "{{user_input}}",
                        "instruction": "请仔细分析用户输入的意图。如果用户需要搜索信息、获取实时数据、访问网页等，请返回'tool'；如果用户需要复杂计算、数据分析、代码生成等，请返回'code'；如果是普通问答、聊天，请返回'chat'。请只返回一个单词。"
                    }
                },
                response_style="concise",
                max_length=10,
                output_ports={
                    "answer": "intent_type"
                }
            ),
            
            # 步骤2a: 工具调用 (Tool Agent，条件执行)
            AgentWorkflowStep(
                id="tool_execution",
                name="工具调用",
                description="当意图为工具调用时，执行相应的工具操作",
                agent_type="tool_agent",
                task_description="根据用户输入执行工具调用（当前暂时返回占位符结果）",
                input_ports={
                    "context_data": {
                        "user_input": "{{user_input}}",
                        "task": "执行工具调用"
                    }
                },
                allowed_tools=[],  # 暂时留白
                condition="{{intent_type}} == 'tool'",
                output_ports={
                    "result": "tool_result"
                }
            ),
            
            # 步骤2b: 复杂分析 (Code Agent，条件执行)
            AgentWorkflowStep(
                id="code_analysis",
                name="复杂分析",
                description="当意图为复杂分析时，执行代码生成和运行",
                agent_type="code_agent",
                task_description="根据用户需求执行复杂分析（当前暂时返回占位符结果）",
                input_ports={
                    "input_data": "{{user_input}}"
                },
                expected_output_format="分析结果",
                allowed_libraries=[],  # 暂时留白
                condition="{{intent_type}} == 'code'",
                output_ports={
                    "result": "code_result"
                }
            ),
            
            # 步骤3: 统一回复生成 (Text Agent + Provider)
            AgentWorkflowStep(
                id="final_response",
                name="生成最终回复",
                description="基于意图类型和前面步骤的结果，生成最终的用户回复",
                agent_type="text_agent",
                task_description="根据用户问题和所有可用信息，生成友好、有用的回复",
                input_ports={
                    "context_data": {
                        "user_input": "{{user_input}}",
                        "intent_type": "{{intent_type}}",
                        "tool_result": "{{tool_result}}",
                        "code_result": "{{code_result}}",
                        "instructions": "请根据用户的原始问题和可用的结果信息，生成一个友好、准确的回复。如果有工具调用结果，请基于结果回答；如果有代码分析结果，请解释结果；如果是普通聊天，请直接友好回复。"
                    }
                },
                response_style="helpful",
                max_length=500,
                output_ports={
                    "answer": "final_response"
                }
            )
        ]
        
        return Workflow(
            name="用户问答工作流-Provider架构",
            description="基于Provider的3步式用户问答工作流：意图识别 → 条件执行(工具/代码) → 统一回复",
            steps=steps,
            input_schema={
                "user_input": {"type": "string", "description": "用户输入"},
                "user_id": {"type": "string", "description": "用户ID", "optional": True}
            },
            output_schema={
                "final_response": {"type": "string", "description": "最终响应"}
            }
        )
    
    def _create_simple_workflow(self) -> Workflow:
        """创建简单的默认工作流"""
        steps = [
            AgentWorkflowStep(
                id="simple_response",
                name="简单响应",
                description="提供简单的默认响应",
                agent_type="text_agent",
                task_description="为用户输入提供简单的确认响应",
                input_ports={
                    "context_data": {
                        "user_input": "{{user_input}}"
                    }
                },
                response_style="friendly",
                max_length=100,
                output_ports={
                    "answer": "simple_response"
                }
            )
        ]
        
        return Workflow(
            name="简单工作流",
            description="简单的响应工作流",
            steps=steps
        )
    
    def _setup_logging(self) -> None:
        """设置日志"""
        if self.config.enable_logging:
            logging.basicConfig(
                level=getattr(logging, self.config.log_level),
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
    
    async def _trigger_hook(self, event: str, **kwargs) -> None:
        """触发钩子"""
        if event in self.hooks:
            for callback in self.hooks[event]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(**kwargs)
                    else:
                        callback(**kwargs)
                except Exception as e:
                    logger.error(f"钩子执行失败 {event}: {e}")
    
    
    # ==================== 便利方法 ====================
    
    def get_status(self) -> AgentStatus:
        """获取当前状态"""
        return self.state.status
    
    def get_execution_history(self) -> List[Dict[str, Any]]:
        """获取执行历史"""
        return self._execution_history.copy()
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """获取工具信息"""
        if tool_name in self.tools:
            tool = self.tools[tool_name]
            return {
                'name': tool_name,
                'metadata': tool.metadata.dict(),
                'actions': tool.get_available_actions(),
                'status': tool.status.value
            }
        return None
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        health_info = {
            'agent_id': self.id,
            'status': self.state.status.value,
            'uptime': (datetime.now() - self.state.created_at).total_seconds(),
            'tools': {},
            'memory_usage': len(self.memory) + len(self.variables),
            'execution_count': self.state.execution_count
        }
        
        # 检查所有工具健康状态
        for tool_name, tool in self.tools.items():
            health_info['tools'][tool_name] = await tool.health_check()
        
        # 检查Provider健康状态
        if self.provider:
            health_info['provider'] = {
                'type': type(self.provider).__name__,
                'initialized': getattr(self.provider, 'is_initialized', False),
                'model': getattr(self.provider, 'model_name', 'unknown')
            }
        
        return health_info
    
    # ==================== Provider管理 ====================
    
    def _initialize_provider(self) -> None:
        """初始化Provider"""
        try:
            # 默认使用OpenAI Provider
            provider_type = self.provider_config.get('type', 'openai')
            
            if provider_type == 'openai':
                from ..providers.openai_provider import OpenAIProvider
                api_key = self.provider_config.get('api_key')
                model_name = self.provider_config.get('model_name')
                self.provider = OpenAIProvider(api_key=api_key, model_name=model_name)
            elif provider_type == 'anthropic':
                from ..providers.anthropic_provider import AnthropicProvider
                api_key = self.provider_config.get('api_key')
                model_name = self.provider_config.get('model_name')
                self.provider = AnthropicProvider(api_key=api_key, model_name=model_name)
            else:
                logger.warning(f"未知的Provider类型: {provider_type}")
                return
            
            logger.info(f"Provider初始化成功: {provider_type}")
            
        except Exception as e:
            logger.error(f"Provider初始化失败: {e}")
            self.provider = None
    
    async def initialize_provider_async(self) -> bool:
        """异步初始化Provider"""
        if not self.provider:
            logger.warning("Provider未设置")
            return False
        
        try:
            await self.provider._initialize_client()
            logger.info("Provider异步初始化完成")
            return True
        except Exception as e:
            logger.error(f"Provider异步初始化失败: {e}")
            return False
    
    def get_provider_info(self) -> Dict[str, Any]:
        """获取Provider信息"""
        if not self.provider:
            return {"status": "not_initialized"}
        
        return {
            "type": type(self.provider).__name__,
            "model": getattr(self.provider, 'model_name', 'unknown'),
            "initialized": getattr(self.provider, 'is_initialized', False),
            "api_key_set": bool(getattr(self.provider, 'api_key', None))
        }