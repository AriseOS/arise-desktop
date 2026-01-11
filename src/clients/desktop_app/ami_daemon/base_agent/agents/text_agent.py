"""
Text Agent - 基于LLM的文本生成Agent
"""
import re
import json
import logging
from typing import Any, Dict

try:
    from .base_agent import BaseStepAgent, AgentMetadata, InputSchema, FieldSchema
    from ..core.schemas import (
        AgentContext, AgentInput, AgentOutput
    )
except ImportError:
    # 绝对导入作为备选
    from base_agent.agents.base_agent import BaseStepAgent, AgentMetadata, InputSchema, FieldSchema
    from base_agent.core.schemas import (
        AgentContext, AgentInput, AgentOutput
    )


class TextAgent(BaseStepAgent):
    """Text generation agent using LLM"""

    INPUT_SCHEMA = InputSchema(
        description="Text generation agent for answering questions, generating text, summarizing content",
        fields={
            "instruction": FieldSchema(
                type="str",
                required=True,
                description="Task instruction for the LLM"
            ),
            "data": FieldSchema(
                type="any",
                required=False,
                description="Input data to provide context to the LLM (dict, list, or any JSON-serializable value)"
            ),
        },
        examples=[
            {
                "instruction": "Summarize the following article",
                "data": {"article": "...article content..."}
            },
            {
                "instruction": "Answer the question based on the provided data",
                "data": {"question": "What is the price?", "product_info": {"price": 99.99}}
            }
        ]
    )

    def __init__(self):
        metadata = AgentMetadata(
            name="text_agent",
            description="基于LLM的文本生成Agent，用于回答问题、生成文本、总结内容",
        )
        super().__init__(metadata)
        self.provider = None
        self.logger = logging.getLogger(__name__)
    
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
    
    def _build_complete_prompt(self, instruction: str, input_data: Dict[str, Any], expected_outputs: Dict[str, str]) -> str:
        """构建完整的大模型提示词，包含指令、输入和输出要求"""
        
        prompt_parts = []
        
        # 1. 添加任务指令
        prompt_parts.append(f"## 任务指令\n{instruction}")
        
        # 2. 添加输入数据
        if input_data:
            prompt_parts.append("## 输入数据")
            for key, value in input_data.items():
                if isinstance(value, (dict, list)):
                    prompt_parts.append(f"**{key}**:\n```json\n{self._format_json_value(value)}\n```")
                else:
                    prompt_parts.append(f"**{key}**: {value}")
        
        # 3. 添加输出格式要求
        if expected_outputs:
            prompt_parts.append("## 输出格式要求")
            prompt_parts.append("请严格按照以下JSON格式返回结果：")
            
            # 构建JSON模板
            output_template = {}
            for output_key, output_type in expected_outputs.items():
                output_template[output_key] = f"<{output_type}>"
            
            prompt_parts.append("```json")
            prompt_parts.append(self._format_json_value(output_template))
            prompt_parts.append("```")
            
            # 添加字段说明
            prompt_parts.append("**字段说明：**")
            for output_key, output_type in expected_outputs.items():
                prompt_parts.append(f"- **{output_key}**: {output_type}")
        
        # 4. 添加执行要求
        prompt_parts.append("""## 执行要求
1. 仔细阅读任务指令，理解要完成的具体任务
2. 基于提供的输入数据进行处理和分析
3. 严格按照输出格式要求返回结构化数据
4. 确保所有输出字段都填充准确、完整的内容
5. 输出必须是有效的JSON格式，以便后续工作流步骤正确解析

现在开始执行任务：""")
        
        return "\n\n".join(prompt_parts)
    
    def _format_json_value(self, value) -> str:
        """Format JSON value for display"""
        return json.dumps(value, ensure_ascii=False, indent=2)

    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        """Execute text generation with automatic JSON parsing"""
        try:
            # Ensure input is AgentInput type
            if isinstance(input_data, dict):
                agent_input = AgentInput(**input_data)
            else:
                agent_input = input_data

            # Get expected output format
            expected_outputs = agent_input.step_metadata.get('expected_outputs', {})

            # Build complete prompt
            complete_prompt = self._build_complete_prompt(
                instruction=agent_input.instruction,
                input_data=agent_input.data,
                expected_outputs=expected_outputs
            )

            self.logger.info(f"[TextAgent] Calling LLM provider")
            self.logger.info(f"  Provider type: {type(self.provider).__name__}")
            self.logger.info(f"  Provider has base_url: {hasattr(self.provider, 'base_url')}")
            if hasattr(self.provider, 'base_url'):
                self.logger.info(f"  Base URL: {self.provider.base_url}")
            if hasattr(self.provider, 'api_key'):
                self.logger.info(f"  API Key: {self.provider.api_key[:10]}..." if self.provider.api_key else "  API Key: None")
            self.logger.info(f"  Complete prompt length: {len(complete_prompt)} chars")

            # Use Provider's JSON generation capability
            # This automatically handles:
            # 1. Strong JSON constraints in prompts
            # 2. JSON repair with json-repair library
            # 3. Graceful fallback to raw text
            parsed_data = await self.provider.generate_json_response(
                system_prompt="You are a professional AI assistant. Return results in strict JSON format.",
                user_prompt=complete_prompt
            )

            self.logger.info(f"[TextAgent] LLM response received")
            self.logger.info(f"  Response type: {type(parsed_data)}")
            self.logger.info(f"  Response keys: {list(parsed_data.keys()) if isinstance(parsed_data, dict) else 'N/A'}")

            # 统一契约：输出放在 data["result"] 中，类型为 Dict
            return AgentOutput(
                success=True,
                data={"result": parsed_data},
                message="Text generation completed"
            )

        except Exception as e:
            self.logger.error(f"[TextAgent] Text generation failed: {str(e)}")
            self.logger.error(f"  Error type: {type(e).__name__}")
            import traceback
            self.logger.error(f"  Traceback: {traceback.format_exc()}")

            if context.logger:
                context.logger.error(f"Text generation failed: {str(e)}")

            return AgentOutput(
                success=False,
                data={},
                message=f"Text generation failed: {str(e)}"
            )
    
