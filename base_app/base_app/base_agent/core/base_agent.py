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
    WorkflowStep, WorkflowResult, Workflow, AgentCapabilitySpec, InterfaceSpec, ExtensionSpec,
    StepType, ErrorHandling
)
from .workflow_engine import WorkflowEngine
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
        memory_config: Optional[Dict[str, Any]] = None
    ):
        # 基础配置
        self.config = config or AgentConfig(name="BaseAgent")
        self.id = str(uuid.uuid4())
        
        # 核心组件
        self.tools: Dict[str, BaseTool] = {}
        self.hooks: Dict[str, List[Callable]] = {}
        
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
        
        # 工作流引擎
        self.workflow_engine = WorkflowEngine(agent_instance=self)
        
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
        workflow: Union[Workflow, List[WorkflowStep]], 
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
                WorkflowStep(
                    name="搜索记忆",
                    step_type=StepType.MEMORY,
                    memory_action="search",
                    query="用户偏好"
                ),
                WorkflowStep(
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
            # 如果传入的是步骤列表，使用WorkflowEngine执行
            return await self.workflow_engine.execute_steps(
                workflow, 
                input_data=input_data or {}
            )
        else:
            # 如果传入的是完整工作流，使用WorkflowEngine执行
            return await self.workflow_engine.execute_workflow(
                workflow, 
                input_data=input_data or {}
            )
    
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
                return str(result.final_result)
            else:
                return "处理完成，但未生成具体结果"
        else:
            error_msg = f"处理失败: {result.error_message}"
            logger.error(error_msg)
            return error_msg
    
    # ==================== 扩展接口 ====================
    
    def add_hook(self, event: str, callback: Callable) -> None:
        """
        添加钩子函数
        
        Args:
            event: 事件名称
            callback: 回调函数
            
        Example:
            # 添加工具调用前的钩子
            def log_tool_call(tool_name, action, **kwargs):
                print(f"调用工具: {tool_name}.{action}")
            
            self.add_hook('before_tool_call', log_tool_call)
        """
        if event not in self.hooks:
            self.hooks[event] = []
        self.hooks[event].append(callback)
        logger.debug(f"钩子已添加: {event}")
    
    def remove_hook(self, event: str, callback: Callable) -> bool:
        """
        移除钩子函数
        
        Args:
            event: 事件名称
            callback: 回调函数
            
        Returns:
            bool: 是否成功移除
        """
        if event in self.hooks and callback in self.hooks[event]:
            self.hooks[event].remove(callback)
            return True
        return False
    
    def get_capabilities(self) -> AgentCapabilitySpec:
        """
        获取Agent能力描述 - 供AI工具理解
        
        Returns:
            AgentCapabilitySpec: 能力规格说明
            
        这个方法返回完整的Agent能力描述，包括：
        - 标准接口定义
        - 支持的工具列表  
        - 扩展点说明
        - 使用示例
        
        AI工具（如Claude Code）可以基于这些信息生成定制Agent
        """
        return AgentCapabilitySpec(
            name=self.config.name,
            description=f"基于BaseAgent的{self.config.description}",
            interfaces={
                "execute": InterfaceSpec(
                    method_name="execute",
                    description="主执行方法，子类必须实现",
                    parameters={
                        "input_data": "Any - 输入数据",
                        "kwargs": "Dict - 额外参数"
                    },
                    return_type="AgentResult",
                    is_async=True,
                    is_required=True,
                    example_usage="""
async def execute(self, task: str, **kwargs) -> AgentResult:
    # 实现具体逻辑
    result = await self.use_tool('browser', 'navigate', {'url': task})
    return AgentResult(success=True, data=result.data)
"""
                ),
                "use_tool": InterfaceSpec(
                    method_name="use_tool",
                    description="调用注册的工具",
                    parameters={
                        "tool_name": "str - 工具名称",
                        "action": "str - 动作名称", 
                        "params": "Dict - 动作参数"
                    },
                    return_type="ToolResult",
                    is_async=True,
                    is_required=False,
                    example_usage="""
# 使用浏览器工具
result = await self.use_tool('browser', 'navigate', {'url': 'https://example.com'})

# 使用Android工具
result = await self.use_tool('android', 'read_chat', {'app': '微信', 'contact': '客户'})
"""
                ),
                "store_memory": InterfaceSpec(
                    method_name="store_memory",
                    description="存储状态信息",
                    parameters={
                        "key": "str - 存储键",
                        "value": "Any - 存储值",
                        "persistent": "bool - 是否持久化"
                    },
                    return_type="None",
                    is_async=True,
                    is_required=False,
                    example_usage="""
# 存储临时数据
await self.store_memory('temp_result', data)

# 存储持久化数据  
await self.store_memory('user_profile', profile, persistent=True)
"""
                ),
                "run_workflow": InterfaceSpec(
                    method_name="run_workflow", 
                    description="执行多步骤工作流",
                    parameters={
                        "steps": "List[WorkflowStep] - 工作流步骤"
                    },
                    return_type="WorkflowResult",
                    is_async=True,
                    is_required=False,
                    example_usage="""
steps = [
    WorkflowStep(name="读取数据", tool_name="file", action="read", params={"path": "data.json"}),
    WorkflowStep(name="处理数据", tool_name="processor", action="transform", params={"data": "{{step_0_result}}"})
]
result = await self.run_workflow(steps)
"""
                )
            },
            supported_tools=list(self.tools.keys()),
            extension_points={
                "hooks": ExtensionSpec(
                    name="事件钩子",
                    description="在特定事件触发时执行自定义逻辑",
                    extension_type="hook",
                    parameters={"event": "str", "callback": "Callable"},
                    how_to_extend="使用 add_hook() 方法添加事件监听器",
                    example="""
def my_hook(tool_name, action, **kwargs):
    print(f"调用工具: {tool_name}.{action}")

self.add_hook('before_tool_call', my_hook)
"""
                ),
                "custom_tools": ExtensionSpec(
                    name="自定义工具",
                    description="注册和使用自定义工具",
                    extension_type="plugin",
                    parameters={"name": "str", "tool": "BaseTool"},
                    how_to_extend="继承BaseTool实现自定义工具，然后注册",
                    example="""
class MyTool(BaseTool):
    async def execute(self, action, params, **kwargs):
        # 实现工具逻辑
        pass

self.register_tool('my_tool', MyTool())
"""
                ),
                "workflow_steps": ExtensionSpec(
                    name="自定义工作流步骤",
                    description="定义复杂的工作流逻辑",
                    extension_type="override",
                    parameters={"steps": "List[WorkflowStep]"},
                    how_to_extend="创建WorkflowStep对象，支持条件、依赖、错误处理",
                    example="""
steps = [
    WorkflowStep(
        name="条件步骤",
        tool_name="checker", 
        action="verify",
        condition="{{user_verified}} == True",
        error_handling="retry"
    )
]
"""
                )
            }
        )
    
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
        """创建用户问答默认工作流"""
        steps = [
            WorkflowStep(
                name="分析用户输入",
                step_type=StepType.CODE,
                code="""
# 分析用户输入，提取关键信息
user_input = variables.get('user_input', '')
print(f"分析用户输入: {user_input}")

# 简单的意图分析
if '天气' in user_input:
    intent = 'weather'
elif '时间' in user_input:
    intent = 'time'
else:
    intent = 'general'

result = {
    'user_input': user_input,
    'intent': intent,
    'keywords': user_input.split()
}
""",
                output_key="analysis_result"
            ),
            WorkflowStep(
                name="搜索相关记忆",
                step_type=StepType.MEMORY,
                memory_action="search",
                query="{{user_input}}",
                params={"limit": 3},
                output_key="memory_results",
                error_handling=ErrorHandling.CONTINUE
            ),
            WorkflowStep(
                name="生成响应",
                step_type=StepType.CODE,
                code="""
# 整合分析结果和记忆搜索结果
analysis = step_results.get('analysis_result', {})
memories = step_results.get('memory_results', [])

user_input = analysis.get('user_input', '用户输入')
intent = analysis.get('intent', 'general')

# 基于意图和记忆生成响应
if intent == 'weather':
    result = f"您询问天气情况。根据您的输入'{user_input}'，我建议您查看天气预报。"
elif intent == 'time':
    import datetime
    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    result = f"当前时间是: {current_time}"
else:
    if memories:
        memory_context = "\\n".join([str(m.get('content', '')) for m in memories[:2]])
        result = f"基于您的输入'{user_input}'和相关记忆，我为您提供以下回复：\\n{memory_context}"
    else:
        result = f"感谢您的输入：'{user_input}'。我已收到您的消息，但暂无相关记忆可参考。"

print(f"生成的响应: {result}")
""",
                output_key="final_response"
            ),
            WorkflowStep(
                name="存储交互记忆",
                step_type=StepType.MEMORY,
                memory_action="store",
                memory_key="last_interaction",
                memory_value="{{final_response}}",
                error_handling=ErrorHandling.CONTINUE
            )
        ]
        
        return Workflow(
            name="用户问答工作流",
            description="处理用户输入并生成响应的标准工作流",
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
            WorkflowStep(
                name="简单响应",
                step_type=StepType.CODE,
                code="""
user_input = variables.get('user_input', '未知输入')
result = f"您好！我收到了您的消息：{user_input}"
""",
                output_key="simple_response"
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
        
        return health_info