"""
Text Agent - 基于LLM的文本生成Agent
"""
import re
import json
import logging
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
        """格式化JSON值"""
        return json.dumps(value, ensure_ascii=False, indent=2)
    
    def _parse_json_response(self, raw_response: str) -> Dict[str, Any]:
        """解析Agent返回的JSON格式输出，提取实际值"""
        try:
            # 移除markdown代码块标记
            if raw_response.startswith('```json'):
                # 提取```json和```之间的内容
                start = raw_response.find('```json') + 7
                end = raw_response.rfind('```')
                if end > start:
                    json_content = raw_response[start:end].strip()
                else:
                    json_content = raw_response
            elif raw_response.startswith('```'):
                # 处理没有json标识的代码块
                start = raw_response.find('```') + 3
                end = raw_response.rfind('```')
                if end > start:
                    json_content = raw_response[start:end].strip()
                else:
                    json_content = raw_response
            else:
                json_content = raw_response.strip()
            
            # 尝试解析JSON
            parsed_data = json.loads(json_content)
            
            # 如果解析成功且是字典，返回解析后的数据
            if isinstance(parsed_data, dict):
                return parsed_data
            else:
                # 如果不是字典，包装在answer字段中
                return {"answer": parsed_data}
                
        except (json.JSONDecodeError, Exception) as e:
            self.logger.warning(f"解析Agent JSON输出失败: {str(e)}, 原始输出: {raw_response}")
            # 如果解析失败，返回原始输出包装在answer字段中
            return {"answer": raw_response}
    
    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        """执行文本生成"""
        try:
            # 确保输入是AgentInput类型
            if isinstance(input_data, dict):
                agent_input = AgentInput(**input_data)
            else:
                agent_input = input_data
            
            # 获取期望的输出格式
            expected_outputs = agent_input.step_metadata.get('expected_outputs', {})
            
            # 构建完整的prompt
            complete_prompt = self._build_complete_prompt(
                instruction=agent_input.instruction,
                input_data=agent_input.data,
                expected_outputs=expected_outputs
            )
            
            # Provider生成回答
            response = await self.provider.generate_response(
                system_prompt="你是一个专业的AI助手，严格按照要求返回JSON格式的结果。",
                user_prompt=complete_prompt
            )
            
            # 解析JSON响应
            parsed_data = self._parse_json_response(response)
            
            return AgentOutput(
                success=True,
                data=parsed_data,
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
    
