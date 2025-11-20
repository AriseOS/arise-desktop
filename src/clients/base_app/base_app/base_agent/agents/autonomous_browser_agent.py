"""
Autonomous Browser Agent - 自主浏览器 Agent
"""
from typing import Any, Dict

from .base_agent import BaseStepAgent, AgentMetadata
from .tool_agent import ToolAgent
from ..core.schemas import AgentContext, AgentInput, AgentOutput
from ..tools.browser_use.autonomous_browser import AutonomousBrowserTool


class AutonomousBrowserAgent(BaseStepAgent):
    """
    自主浏览器 Agent
    
    这是一个专门用于自主浏览器操作的 Agent，它实际上是对 ToolAgent + AutonomousBrowserTool 的封装。
    在 Workflow 中使用 autonomous_browser_agent 类型时，会调用此 Agent。
    """
    
    def __init__(self):
        metadata = AgentMetadata(
            name="autonomous_browser_agent",
            description="自主浏览器 Agent，支持通过自然语言指令进行网页探索和操作",
            version="1.0.0",
            tags=["browser", "autonomous", "web"],
        )
        super().__init__(metadata)
        self.tool = None
        
    async def initialize(self, context: AgentContext) -> bool:
        """初始化 Agent"""
        try:
            # 创建 AutonomousBrowserTool 实例
            # 注意：这里我们需要从 context 获取配置，或者使用默认配置
            # 暂时使用默认配置，后续可以从 context.agent_config 获取
            self.tool = AutonomousBrowserTool()
            
            # 初始化工具 (主要是 LLM)
            # 如果 context 中有 provider，尝试复用配置
            if context.agent_instance and hasattr(context.agent_instance, 'provider'):
                # TODO: 传递 LLM 配置给 Tool
                pass
                
            # 调用工具的内部初始化
            # AutonomousBrowserTool._initialize() 是内部方法，但在 BaseTool 中通常不需要显式调用，
            # 除非有特定的初始化逻辑。BrowserTool 在 execute 时会检查 LLM 是否初始化。
            
            self.is_initialized = True
            return True
        except Exception as e:
            if context.logger:
                context.logger.error(f"AutonomousBrowserAgent 初始化失败: {str(e)}")
            return False
            
    async def validate_input(self, input_data: Any) -> bool:
        """验证输入"""
        if isinstance(input_data, (dict, AgentInput)):
            return True
        return False
        
    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        """执行任务"""
        try:
            # 解析输入
            task = ""
            max_actions = 20
            
            if isinstance(input_data, AgentInput):
                task = input_data.instruction
                if input_data.data:
                    max_actions = input_data.data.get("max_actions", 20)
            elif isinstance(input_data, dict):
                task = input_data.get("task") or input_data.get("instruction", "")
                max_actions = input_data.get("max_actions", 20)
                
            if not task:
                return AgentOutput(
                    success=False,
                    message="缺少任务描述 (task 或 instruction)",
                    data={}
                )
                
            # 调用工具
            # 构造参数
            params = {
                "task": task,
                "max_actions": max_actions
            }
            
            # 执行
            result = await self.tool.execute("execute", params)
            
            return AgentOutput(
                success=result.success,
                data=result.data,
                message=result.message
            )
            
        except Exception as e:
            if context.logger:
                context.logger.error(f"AutonomousBrowserAgent 执行失败: {str(e)}")
            return AgentOutput(
                success=False,
                message=f"执行失败: {str(e)}",
                data={}
            )
            
    async def cleanup(self, context: AgentContext):
        """清理资源"""
        if self.tool:
            await self.tool._cleanup()
