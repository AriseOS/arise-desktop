"""
Text Agent - 基于LLM的文本生成Agent
"""
import re
from typing import Any, Dict

try:
    from .base_agent import BaseStepAgent, AgentMetadata
    from ..core.schemas import (
        AgentContext, AgentInput, AgentOutput
    )
except ImportError:
    # 绝对导入作为备选
    from base_agent.agents.base_agent import BaseStepAgent, AgentMetadata
    from base_agent.core.schemas import (
        AgentContext, AgentInput, AgentOutput
    )


class TextAgent(BaseStepAgent):
    """文本生成Agent"""
    
    def __init__(self):
        metadata = AgentMetadata(
            name="text_agent",
            description="基于LLM的文本生成Agent，用于回答问题、生成文本、总结内容",
        )
        super().__init__(metadata)
        self.provider = None
    
    async def initialize(self, context: AgentContext) -> bool:
        """初始化Text Agent"""
        if not context.agent_instance:
            return False
        
        # 验证Provider是否可用
        if not hasattr(context.agent_instance, 'provider') or not context.agent_instance.provider:
            if context.logger:
                context.logger.error("Provider不可用")
            return False
        
        self.provider = context.agent_instance.provider
        self.is_initialized = True
        return True
    
    async def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        if isinstance(input_data, AgentInput):
            return True
        if isinstance(input_data, dict):
            return "instruction" in input_data
        return False
    
    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        """执行文本生成"""
        try:
            # 确保输入是AgentInput类型
            if isinstance(input_data, dict):
                agent_input = AgentInput(**input_data)
            else:
                agent_input = input_data
            
            # Provider生成回答
            response = await self.provider.generate_response(
                system_prompt="你是一个专业的AI助手，根据指令完成文本生成任务。",
                user_prompt=agent_input.instruction
            )
            
            answer = response.strip()
            
            return AgentOutput(
                success=True,
                data={"answer": answer},
                message="文本生成完成"
            )
            
        except Exception as e:
            if context.logger:
                context.logger.error(f"文本生成失败: {str(e)}")
            
            return AgentOutput(
                success=False,
                data={},
                message=f"文本生成失败: {str(e)}"
            )
    
