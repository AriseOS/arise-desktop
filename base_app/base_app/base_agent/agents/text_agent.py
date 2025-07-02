"""
Text Agent - 基于LLM的文本生成Agent
"""
import re
from typing import Any, Dict

try:
    from .base_agent import BaseStepAgent, AgentMetadata
    from ..core.schemas import (
        AgentCapability, AgentContext, 
        TextAgentInput, TextAgentOutput
    )
except ImportError:
    # 绝对导入作为备选
    from base_agent.agents.base_agent import BaseStepAgent, AgentMetadata
    from base_agent.core.schemas import (
        AgentCapability, AgentContext, 
        TextAgentInput, TextAgentOutput
    )


class TextAgent(BaseStepAgent):
    """文本生成Agent"""
    
    def __init__(self):
        metadata = AgentMetadata(
            name="text_agent",
            description="基于LLM的文本生成Agent，用于回答问题、生成文本、总结内容",
            capabilities=[AgentCapability.TEXT_GENERATION],
            input_schema={
                "question": {"type": "string", "required": True},
                "context_data": {"type": "object", "required": False},
                "response_style": {"type": "string", "required": False},
                "max_length": {"type": "integer", "required": False},
                "language": {"type": "string", "required": False}
            },
            output_schema={
                "success": {"type": "boolean"},
                "answer": {"type": "string"},
                "word_count": {"type": "integer"},
                "error_message": {"type": "string"}
            }
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
        if isinstance(input_data, TextAgentInput):
            return True
        if not isinstance(input_data, dict):
            return False
        return "question" in input_data
    
    async def execute(self, input_data: Any, context: AgentContext) -> TextAgentOutput:
        """执行文本生成"""
        try:
            # 解析输入
            if isinstance(input_data, dict):
                text_input = TextAgentInput(**input_data)
            else:
                text_input = input_data
            
            # 构建提示词
            prompt = self._build_prompt(text_input, context)
            
            # Provider生成回答
            response = await self.provider.generate_response(
                system_prompt="你是一个有用的AI助手，请根据用户的问题和上下文信息提供准确、有帮助的回答。",
                user_prompt=prompt
            )
            
            answer = response.strip()
            
            return TextAgentOutput(
                success=True,
                answer=answer,
                word_count=len(answer)
            )
            
        except Exception as e:
            if context.logger:
                context.logger.error(f"文本生成失败: {str(e)}")
            
            return TextAgentOutput(
                success=False,
                answer="",
                word_count=0,
                error_message=str(e)
            )
    
    def _build_prompt(self, input_data: TextAgentInput, context: AgentContext) -> str:
        """构建提示词"""
        base_prompt = f"""
请回答以下问题：{input_data.question}

上下文信息：
{self._format_context(input_data.context_data)}

回答要求：
- 风格：{input_data.response_style}
- 语言：{input_data.language}
- 长度限制：{input_data.max_length}字以内
- 准确性：基于提供的上下文信息回答

请提供清晰、准确的回答：
"""
        return base_prompt
    
    def _format_context(self, context_data: Dict[str, Any]) -> str:
        """格式化上下文数据"""
        if not context_data:
            return "无额外上下文"
        
        formatted = []
        for key, value in context_data.items():
            formatted.append(f"- {key}: {value}")
        return "\n".join(formatted)
    
    async def _resolve_prompt_variables(self, prompt: str, context: AgentContext) -> str:
        """解析提示词中的变量引用"""
        def replace_var(match):
            var_name = match.group(1).strip()
            return str(context.variables.get(var_name, f"{{{{{var_name}}}}}"))
        
        return re.sub(r'\{\{([^}]+)\}\}', replace_var, prompt)