"""
Tool Agent - 支持工具预筛选和置信度机制的工具调用Agent
"""
import json
from typing import Any, Dict, List

from .base_agent import BaseStepAgent, AgentMetadata
from ..core.schemas import (
    AgentCapability, AgentContext,
    ToolAgentInput, ToolAgentOutput
)


class ToolAgent(BaseStepAgent):
    """工具调用Agent - 支持工具预筛选和置信度机制"""
    
    def __init__(self):
        metadata = AgentMetadata(
            name="tool_agent",
            description="智能工具调用Agent，支持工具预筛选和置信度评估",
            capabilities=[AgentCapability.TOOL_CALLING],
            input_schema={
                "task_description": {"type": "string", "required": True},
                "context_data": {"type": "object", "required": False},
                "constraints": {"type": "array", "required": False},
                "allowed_tools": {"type": "array", "required": False},
                "fallback_tools": {"type": "array", "required": False},
                "confidence_threshold": {"type": "number", "required": False}
            },
            output_schema={
                "success": {"type": "boolean"},
                "result": {"type": "any"},
                "tool_used": {"type": "string"},
                "action_taken": {"type": "string"},
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
                "alternatives_tried": {"type": "array"},
                "metadata": {"type": "object"},
                "error_message": {"type": "string"}
            }
        )
        super().__init__(metadata)
        self.provider = None
        self.tool_registry = None
    
    async def initialize(self, context: AgentContext) -> bool:
        """初始化Tool Agent"""
        if not context.agent_instance:
            return False
        
        # 验证Provider和工具注册表是否可用
        if not hasattr(context.agent_instance, 'provider') or not context.agent_instance.provider:
            if context.logger:
                context.logger.error("Provider不可用")
            return False
        
        self.provider = context.agent_instance.provider
        self.tool_registry = context.tools_registry or context.agent_instance
        self.is_initialized = True
        return True
    
    async def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        if isinstance(input_data, ToolAgentInput):
            return True
        if not isinstance(input_data, dict):
            return False
        return "task_description" in input_data
    
    async def execute(self, input_data: Any, context: AgentContext) -> ToolAgentOutput:
        """执行工具调用 - 两轮沟通机制"""
        try:
            # 解析输入
            if isinstance(input_data, dict):
                tool_input = ToolAgentInput(**input_data)
            else:
                tool_input = input_data
            
            # 第一轮：选择工具
            selected_tool = await self._select_tool_first_round(tool_input, context)
            
            # 第二轮：选择具体API和参数
            api_call = await self._select_api_and_params_second_round(
                tool_name=selected_tool["tool_name"],
                task_description=tool_input.task_description,
                context_data=tool_input.context_data,
                constraints=tool_input.constraints,
                context=context
            )
            
            # 检查置信度
            final_confidence = min(selected_tool["confidence"], api_call["confidence"])
            if final_confidence < tool_input.confidence_threshold:
                if context.logger:
                    context.logger.warning(
                        f"最终置信度 {final_confidence} 低于阈值 {tool_input.confidence_threshold}"
                    )
            
            # 执行API调用
            alternatives_tried = []
            all_tools_to_try = [selected_tool["tool_name"]] + tool_input.fallback_tools
            
            for tool_name in all_tools_to_try:
                try:
                    result = await self._call_tool(
                        tool_name=tool_name,
                        action=api_call["action"],
                        parameters=api_call["parameters"],
                        context=context
                    )
                    
                    return ToolAgentOutput(
                        success=True,
                        result=result,
                        tool_used=tool_name,
                        action_taken=api_call["action"],
                        confidence=final_confidence,
                        reasoning=f"工具选择: {selected_tool['reasoning']}; API选择: {api_call['reasoning']}",
                        alternatives_tried=alternatives_tried,
                        metadata={
                            "parameters": api_call["parameters"],
                            "tool_selection": selected_tool,
                            "api_selection": api_call
                        }
                    )
                    
                except Exception as e:
                    alternatives_tried.append(tool_name)
                    if context.logger:
                        context.logger.warning(f"工具 {tool_name} 执行失败: {str(e)}")
                    continue
            
            # 所有工具都失败了
            return ToolAgentOutput(
                success=False,
                result=None,
                tool_used=selected_tool.get("tool_name", "unknown"),
                action_taken=api_call.get("action", "unknown"),
                confidence=final_confidence,
                reasoning=f"工具选择: {selected_tool.get('reasoning', '')}; API选择: {api_call.get('reasoning', '')}",
                alternatives_tried=alternatives_tried,
                error_message=f"所有工具都执行失败，尝试过: {alternatives_tried}"
            )
            
        except Exception as e:
            if context.logger:
                context.logger.error(f"Tool Agent执行失败: {str(e)}")
            
            return ToolAgentOutput(
                success=False,
                result=None,
                tool_used="unknown",
                action_taken="unknown",
                confidence=0.0,
                reasoning="",
                alternatives_tried=[],
                error_message=str(e)
            )
    
    def _get_filtered_tools(self, input_data: ToolAgentInput) -> List[str]:
        """获取预筛选的工具列表"""
        # 直接使用Workflow层面预筛选的工具
        if input_data.allowed_tools:
            return input_data.allowed_tools
        else:
            # 如果没有预筛选，使用所有可用工具（不推荐）
            return self._get_all_available_tools()
    
    def _get_all_available_tools(self) -> List[str]:
        """获取所有可用工具"""
        # 优先从tool_registry获取
        if self.tool_registry and hasattr(self.tool_registry, 'get_registered_tools'):
            return self.tool_registry.get_registered_tools()
        elif self.tool_registry and hasattr(self.tool_registry, 'tools'):
            return list(self.tool_registry.tools.keys())
        return []
    
    async def _select_tool_first_round(
        self, 
        input_data: ToolAgentInput, 
        context: AgentContext
    ) -> Dict[str, Any]:
        """第一轮：基于任务描述选择工具"""
        
        # 获取可用工具
        available_tools = self._get_filtered_tools(input_data)
        
        # 获取工具描述信息
        tool_descriptions = await self._get_tool_descriptions_from_registry(available_tools, context)
        
        analysis_prompt = f"""
任务描述: {input_data.task_description}
上下文数据: {input_data.context_data}
约束条件: {input_data.constraints}

可用工具及描述:
{tool_descriptions}

请根据任务描述分析应该使用哪个工具。只需要选择工具，不需要选择具体的API操作。

返回JSON格式：
{{
    "tool_name": "选择的工具名称",
    "confidence": 0.0到1.0之间的置信度,
    "reasoning": "选择这个工具的理由"
}}
"""
        
        try:
            response = await self.provider.generate_response(
                system_prompt="你是一个工具选择专家。请分析任务需求并选择最合适的工具，返回严格的JSON格式结果。",
                user_prompt=analysis_prompt
            )
            
            if context.logger:
                context.logger.info(f"第一轮LLM原始响应: {response}")
            
            # 处理可能的非JSON响应
            if not response or not response.strip():
                raise ValueError("LLM返回空响应")
            
            # 尝试提取JSON（有时LLM会返回带说明的文本）
            response_clean = response.strip()
            if "```json" in response_clean:
                # 提取json代码块
                start = response_clean.find("```json") + 7
                end = response_clean.find("```", start)
                response_clean = response_clean[start:end].strip()
            elif "{" in response_clean:
                # 提取第一个JSON对象
                start = response_clean.find("{")
                end = response_clean.rfind("}") + 1
                response_clean = response_clean[start:end]
            
            result = json.loads(response_clean)
            
            # 验证结果
            if result.get("tool_name") not in available_tools:
                raise ValueError(f"选择的工具 {result.get('tool_name')} 不在可用工具列表中")
            
            return {
                "tool_name": result["tool_name"],
                "confidence": float(result.get("confidence", 0.5)),
                "reasoning": result.get("reasoning", "")
            }
            
        except json.JSONDecodeError as e:
            if context.logger:
                context.logger.error(f"第一轮JSON解析失败: {str(e)}, 原始响应: {response}")
        except Exception as e:
            if context.logger:
                context.logger.error(f"第一轮工具选择失败: {str(e)}")
        
        # 默认返回第一个可用工具
        return {
            "tool_name": available_tools[0] if available_tools else "browser_use",
            "confidence": 0.3,
            "reasoning": f"自动选择默认工具，原因：LLM响应解析失败"
        }
    
    async def _select_api_and_params_second_round(
        self,
        tool_name: str,
        task_description: str,
        context_data: Any,
        constraints: List[str],
        context: AgentContext
    ) -> Dict[str, Any]:
        """第二轮：基于选中的工具选择具体API和参数"""
        
        # 获取工具实例和详细API描述
        tool_instance = await self._get_tool_instance(tool_name, context)
        if not tool_instance:
            raise ValueError(f"无法获取工具实例: {tool_name}")
        
        # 获取工具的详细动作描述
        actions_description = tool_instance.get_actions_description()
        actions_text = self._format_actions_description(actions_description)
        
        analysis_prompt = f"""
任务描述: {task_description}
上下文数据: {context_data}
约束条件: {constraints}

选中的工具: {tool_name}

该工具的可用API操作：
{actions_text}

请根据任务描述选择最合适的API操作并生成参数。

返回JSON格式：
{{
    "action": "选择的API操作名称",
    "parameters": {{"参数名": "参数值"}},
    "confidence": 0.0到1.0之间的置信度,
    "reasoning": "选择这个API和参数的理由"
}}
"""
        
        try:
            response = await self.provider.generate_response(
                system_prompt="你是一个API选择专家。请分析任务需求并选择最合适的API操作和参数，返回严格的JSON格式结果。",
                user_prompt=analysis_prompt
            )
            
            if context.logger:
                context.logger.info(f"第二轮LLM原始响应: {response}")
            
            # 处理可能的非JSON响应
            if not response or not response.strip():
                raise ValueError("LLM返回空响应")
            
            # 尝试提取JSON
            response_clean = response.strip()
            if "```json" in response_clean:
                start = response_clean.find("```json") + 7
                end = response_clean.find("```", start)
                response_clean = response_clean[start:end].strip()
            elif "{" in response_clean:
                start = response_clean.find("{")
                end = response_clean.rfind("}") + 1
                response_clean = response_clean[start:end]
            
            result = json.loads(response_clean)
            
            # 验证动作是否存在
            available_actions = [action.name for action in actions_description]
            if result.get("action") not in available_actions:
                raise ValueError(f"选择的动作 {result.get('action')} 不在可用动作列表中")
            
            return {
                "action": result["action"],
                "parameters": result.get("parameters", {}),
                "confidence": float(result.get("confidence", 0.5)),
                "reasoning": result.get("reasoning", "")
            }
            
        except json.JSONDecodeError as e:
            if context.logger:
                context.logger.error(f"第二轮JSON解析失败: {str(e)}, 原始响应: {response}")
        except Exception as e:
            if context.logger:
                context.logger.error(f"第二轮API选择失败: {str(e)}")
        
        # 默认使用execute_task操作
        return {
            "action": "execute_task",
            "parameters": {"task": task_description},
            "confidence": 0.3,
            "reasoning": f"自动选择execute_task操作，原因：LLM响应解析失败"
        }
    
    async def _get_tool_descriptions_from_registry(
        self, 
        available_tools: List[str], 
        context: AgentContext
    ) -> str:
        """从工具注册表获取工具描述"""
        descriptions = []
        
        for tool_name in available_tools:
            try:
                tool_instance = await self._get_tool_instance(tool_name, context)
                if tool_instance:
                    tool_desc = tool_instance.get_tool_description()
                    descriptions.append(f"""
- {tool_desc.name}: {tool_desc.description}
  分类: {tool_desc.category}
  版本: {tool_desc.version}
""")
                else:
                    descriptions.append(f"- {tool_name}: 工具描述不可用")
            except Exception as e:
                descriptions.append(f"- {tool_name}: 获取描述失败 - {str(e)}")
        
        return "\n".join(descriptions)
    
    async def _get_tool_instance(self, tool_name: str, context: AgentContext):
        """获取工具实例"""
        if context.logger:
            context.logger.info(f"尝试获取工具实例: {tool_name}")
        
        # 优先从agent_instance获取工具
        if hasattr(context.agent_instance, 'tools'):
            if context.logger:
                available_tools = list(context.agent_instance.tools.keys()) if context.agent_instance.tools else []
                context.logger.info(f"agent_instance.tools中的工具: {available_tools}")
            
            if context.agent_instance.tools:
                tool_instance = context.agent_instance.tools.get(tool_name)
                if tool_instance:
                    if context.logger:
                        context.logger.info(f"成功从agent_instance获取工具: {tool_name}")
                    return tool_instance
        
        # 备用：从tools_registry获取
        if self.tool_registry and hasattr(self.tool_registry, 'tools'):
            if context.logger:
                registry_tools = list(self.tool_registry.tools.keys()) if self.tool_registry.tools else []
                context.logger.info(f"tools_registry中的工具: {registry_tools}")
            
            tool_instance = self.tool_registry.tools.get(tool_name)
            if tool_instance:
                if context.logger:
                    context.logger.info(f"成功从tools_registry获取工具: {tool_name}")
                return tool_instance
        
        if context.logger:
            context.logger.error(f"无法获取工具实例: {tool_name}, agent_instance: {context.agent_instance}, tools_registry: {self.tool_registry}")
        
        return None
    
    def _format_actions_description(self, actions_description: List) -> str:
        """格式化动作描述为文本"""
        formatted = []
        
        for action in actions_description:
            examples_text = ""
            if action.examples:
                examples_text = "\n  示例:\n" + "\n".join([
                    f"    - {ex.get('description', '')}: {ex.get('params', {})}"
                    for ex in action.examples[:2]  # 只显示前2个示例
                ])
            
            formatted.append(f"""
{action.name}: {action.description}
  必需参数: {action.required_params}
  参数结构: {action.parameters}{examples_text}
""")
        
        return "\n".join(formatted)
    
    async def _call_tool(
        self, 
        tool_name: str, 
        action: str, 
        parameters: Dict[str, Any],
        context: AgentContext
    ) -> Any:
        """调用具体工具"""
        tool_instance = await self._get_tool_instance(tool_name, context)
        if not tool_instance:
            raise ValueError(f"工具 {tool_name} 不存在")
        
        return await tool_instance.execute(action, parameters)
    
    async def _resolve_variables(self, params: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
        """解析参数中的变量引用"""
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                var_name = value[2:-2].strip()
                resolved[key] = context.variables.get(var_name, value)
            else:
                resolved[key] = value
        return resolved