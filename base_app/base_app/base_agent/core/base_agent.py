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
        from ..workflows.workflow_loader import load_workflow
        # 用户问答工作流 - 从YAML配置文件加载
        self._default_workflows["user_qa"] = load_workflow("user-qa-workflow")
    
    def _get_default_workflow(self, name: str) -> Workflow:
        """获取默认工作流"""
        if name in self._default_workflows:
            return self._default_workflows[name]
        else:
            raise ValueError(f"未找到默认工作流: {name}")
    
    
    
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

    # ==================== 用户自定义接口 ====================
    
    def create_workflow_builder(self, name: str, description: str = "") -> 'WorkflowBuilder':
        """
        创建工作流构建器 - 用户友好的工作流创建接口
        
        Args:
            name: 工作流名称
            description: 工作流描述
            
        Returns:
            WorkflowBuilder: 工作流构建器实例
            
        Example:
            builder = agent.create_workflow_builder("数据分析流程", "用于处理和分析数据")
            builder.add_text_step("理解需求", "分析用户的数据分析需求")
            builder.add_tool_step("读取数据", "从文件中读取数据", tools=["file_reader"])
            builder.add_code_step("分析数据", "进行统计分析", language="python")
            workflow = builder.build()
        """
        from .workflow_builder import WorkflowBuilder
        return WorkflowBuilder(name, description, self)

    def register_custom_agent(self, agent) -> bool:
        """
        注册自定义Agent
        
        Args:
            agent: 继承自BaseStepAgent的自定义Agent实例
            
        Returns:
            bool: 注册是否成功
            
        Example:
            from .custom_agents import CustomTextAgent
            
            custom_agent = CustomTextAgent(
                name="专业翻译员",
                system_prompt="你是一个专业的中英文翻译员。"
            )
            success = agent.register_custom_agent(custom_agent)
        """
        if not self.agent_workflow_engine:
            logger.error("工作流引擎未初始化")
            return False
        
        try:
            self.agent_workflow_engine.agent_registry.register_agent(agent)
            logger.info(f"自定义Agent注册成功: {agent.metadata.name}")
            return True
        except Exception as e:
            logger.error(f"自定义Agent注册失败: {e}")
            return False

    def create_custom_text_agent(self, 
                                name: str,
                                system_prompt: str,
                                response_style: str = "professional",
                                max_length: int = 500,
                                temperature: float = 0.7) -> 'CustomTextAgent':
        """
        创建自定义文本Agent
        
        Args:
            name: Agent名称
            system_prompt: 系统提示词
            response_style: 响应风格
            max_length: 最大响应长度
            temperature: 温度参数
            
        Returns:
            CustomTextAgent: 自定义文本Agent实例
            
        Example:
            text_agent = agent.create_custom_text_agent(
                name="专业翻译员",
                system_prompt="你是一个专业的中英文翻译员，请提供准确、流畅的翻译。",
                response_style="professional"
            )
            agent.register_custom_agent(text_agent)
        """
        from .custom_agents import CustomTextAgent
        return CustomTextAgent(name, system_prompt, response_style, max_length, temperature)

    def create_custom_tool_agent(self,
                                name: str,
                                available_tools: List[str],
                                tool_selection_strategy: str = "best_match",
                                confidence_threshold: float = 0.8,
                                max_tool_calls: int = 3) -> 'CustomToolAgent':
        """
        创建自定义工具Agent
        
        Args:
            name: Agent名称
            available_tools: 可用工具列表
            tool_selection_strategy: 工具选择策略
            confidence_threshold: 置信度阈值
            max_tool_calls: 最大工具调用次数
            
        Returns:
            CustomToolAgent: 自定义工具Agent实例
            
        Example:
            tool_agent = agent.create_custom_tool_agent(
                name="数据处理专家",
                available_tools=["excel_reader", "data_analyzer", "chart_generator"],
                tool_selection_strategy="best_match"
            )
            agent.register_custom_agent(tool_agent)
        """
        from .custom_agents import CustomToolAgent
        return CustomToolAgent(name, available_tools, tool_selection_strategy, confidence_threshold, max_tool_calls)

    def create_custom_code_agent(self,
                                name: str,
                                language: str = "python",
                                allowed_libraries: List[str] = None,
                                code_template: str = "",
                                execution_timeout: int = 30) -> 'CustomCodeAgent':
        """
        创建自定义代码Agent
        
        Args:
            name: Agent名称
            language: 编程语言
            allowed_libraries: 允许的库列表
            code_template: 代码模板
            execution_timeout: 执行超时时间
            
        Returns:
            CustomCodeAgent: 自定义代码Agent实例
            
        Example:
            code_agent = agent.create_custom_code_agent(
                name="数据分析师",
                language="python",
                allowed_libraries=["pandas", "numpy", "matplotlib"],
                code_template="# 数据分析代码\\nimport pandas as pd\\nimport numpy as np\\n"
            )
            agent.register_custom_agent(code_agent)
        """
        from .custom_agents import CustomCodeAgent
        return CustomCodeAgent(name, language, allowed_libraries or [], code_template, execution_timeout)

    def list_available_agents(self) -> List[str]:
        """
        列出所有可用的Agent
        
        Returns:
            List[str]: Agent名称列表
            
        Example:
            agents = agent.list_available_agents()
            print(f"可用Agent: {agents}")
        """
        if not self.agent_workflow_engine:
            return []
        
        return self.agent_workflow_engine.agent_registry.list_agent_names()

    def get_agent_info(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """
        获取Agent信息
        
        Args:
            agent_name: Agent名称
            
        Returns:
            Optional[Dict[str, Any]]: Agent信息字典
            
        Example:
            info = agent.get_agent_info("text_agent")
            print(f"Agent信息: {info}")
        """
        if not self.agent_workflow_engine:
            return None
        
        try:
            agent_instance = self.agent_workflow_engine.agent_registry.get_agent(agent_name)
            if agent_instance:
                return {
                    "name": agent_instance.metadata.name,
                    "description": agent_instance.metadata.description,
                    "capabilities": [cap.value for cap in agent_instance.metadata.capabilities],
                    "input_schema": agent_instance.metadata.input_schema,
                    "output_schema": agent_instance.metadata.output_schema,
                    "version": agent_instance.metadata.version,
                    "author": agent_instance.metadata.author
                }
        except Exception as e:
            logger.error(f"获取Agent信息失败: {e}")
        
        return None

    async def run_custom_workflow(self, workflow: 'Workflow', input_data: Dict[str, Any] = None) -> 'WorkflowResult':
        """
        运行自定义工作流
        
        Args:
            workflow: 工作流实例
            input_data: 输入数据
            
        Returns:
            WorkflowResult: 工作流执行结果
            
        Example:
            result = await agent.run_custom_workflow(workflow, {"user_input": "分析这个数据"})
            print(f"执行结果: {result.final_result}")
        """
        return await self.run_workflow(workflow, input_data)

    def create_quick_qa_workflow(self, name: str = "快速问答", system_prompt: str = None) -> 'Workflow':
        """
        创建快速问答工作流
        
        Args:
            name: 工作流名称
            system_prompt: 自定义系统提示词
            
        Returns:
            Workflow: 问答工作流实例
            
        Example:
            workflow = agent.create_quick_qa_workflow("智能助手", "你是一个友好的AI助手")
            result = await agent.run_custom_workflow(workflow, {"user_input": "你好"})
        """
        builder = self.create_workflow_builder(name, "快速问答工作流")
        
        if system_prompt:
            # 创建自定义文本Agent
            qa_agent = self.create_custom_text_agent(
                name=f"{name}_qa_agent",
                system_prompt=system_prompt,
                response_style="friendly"
            )
            self.register_custom_agent(qa_agent)
            
            builder.add_custom_step(
                name="回答问题",
                agent_name=f"{name}_qa_agent",
                instruction="回答用户的问题"
            )
        else:
            builder.add_text_step(
                name="回答问题",
                instruction="回答用户的问题",
                response_style="friendly"
            )
        
        return builder.build()

    def create_translation_workflow(self, source_lang: str = "中文", target_lang: str = "英文") -> 'Workflow':
        """
        创建翻译工作流
        
        Args:
            source_lang: 源语言
            target_lang: 目标语言
            
        Returns:
            Workflow: 翻译工作流实例
            
        Example:
            workflow = agent.create_translation_workflow("中文", "英文")
            result = await agent.run_custom_workflow(workflow, {"user_input": "你好世界"})
        """
        builder = self.create_workflow_builder("翻译服务", f"{source_lang}到{target_lang}的翻译服务")
        
        # 创建专业翻译Agent
        translator = self.create_custom_text_agent(
            name="专业翻译员",
            system_prompt=f"你是一个专业的{source_lang}到{target_lang}翻译员。请提供准确、流畅的翻译，保持原文的语调和风格。",
            response_style="professional"
        )
        self.register_custom_agent(translator)
        
        builder.add_custom_step(
            name="翻译文本",
            agent_name="专业翻译员",
            instruction=f"将{source_lang}文本翻译成{target_lang}"
        )
        
        return builder.build()

    def get_workflow_templates(self) -> Dict[str, Callable]:
        """
        获取可用的工作流模板
        
        Returns:
            Dict[str, Callable]: 模板名称到创建函数的映射
            
        Example:
            templates = agent.get_workflow_templates()
            qa_workflow = templates["问答"]()
        """
        return {
            "问答": self.create_quick_qa_workflow,
            "翻译": self.create_translation_workflow,
        }

    def validate_workflow(self, workflow: 'Workflow') -> List[str]:
        """
        验证工作流配置
        
        Args:
            workflow: 工作流实例
            
        Returns:
            List[str]: 验证错误列表
            
        Example:
            errors = agent.validate_workflow(workflow)
            if errors:
                print(f"工作流验证失败: {errors}")
        """
        errors = []
        
        if not workflow.steps:
            errors.append("工作流必须包含至少一个步骤")
        
        # 检查步骤名称重复
        step_names = [step.name for step in workflow.steps]
        if len(step_names) != len(set(step_names)):
            errors.append("步骤名称不能重复")
        
        # 检查Agent是否存在
        if self.agent_workflow_engine:
            available_agents = self.agent_workflow_engine.agent_registry.list_agent_names()
            for step in workflow.steps:
                if step.agent_type not in available_agents:
                    errors.append(f"步骤 '{step.name}' 使用的Agent '{step.agent_type}' 不存在")
        
        return errors

    def export_workflow(self, workflow: 'Workflow', file_path: str = None) -> str:
        """
        导出工作流配置
        
        Args:
            workflow: 工作流实例
            file_path: 导出文件路径（可选）
            
        Returns:
            str: 工作流JSON字符串
            
        Example:
            json_str = agent.export_workflow(workflow, "my_workflow.json")
        """
        import json
        from datetime import datetime
        
        def default_serializer(obj):
            """自定义JSON序列化器"""
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
        
        workflow_dict = workflow.model_dump() if hasattr(workflow, 'model_dump') else workflow.dict()
        json_str = json.dumps(workflow_dict, indent=2, ensure_ascii=False, default=default_serializer)
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(json_str)
                logger.info(f"工作流已导出到: {file_path}")
            except Exception as e:
                logger.error(f"导出工作流失败: {e}")
        
        return json_str

    def import_workflow(self, json_str: str = None, file_path: str = None) -> 'Workflow':
        """
        导入工作流配置
        
        Args:
            json_str: 工作流JSON字符串
            file_path: 导入文件路径
            
        Returns:
            Workflow: 工作流实例
            
        Example:
            workflow = agent.import_workflow(file_path="my_workflow.json")
        """
        import json
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    json_str = f.read()
                logger.info(f"从文件导入工作流: {file_path}")
            except Exception as e:
                logger.error(f"导入工作流文件失败: {e}")
                raise
        
        if not json_str:
            raise ValueError("必须提供json_str或file_path参数")
        
        try:
            workflow_dict = json.loads(json_str)
            workflow = Workflow(**workflow_dict)
            logger.info(f"工作流导入成功: {workflow.name}")
            return workflow
        except Exception as e:
            logger.error(f"解析工作流JSON失败: {e}")
            raise