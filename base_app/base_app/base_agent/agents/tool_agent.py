"""
Tool Agent - 支持工具预筛选和置信度机制的工具调用Agent
"""
import json
from typing import Any, Dict, List

from .base_agent import BaseStepAgent, AgentMetadata
from ..core.schemas import (
    AgentContext, AgentInput, AgentOutput
)


class ToolAgent(BaseStepAgent):
    """工具调用Agent - 支持工具预筛选和置信度机制"""
    
    def __init__(self):
        metadata = AgentMetadata(
            name="tool_agent",
            description="工具调用Agent，支持两轮工具选择和置信度评估",
        )
        super().__init__(metadata)
        self.provider = None
        self.tool_registry = None
    
    async def initialize(self, context: AgentContext) -> bool:
        """初始化Tool Agent"""
        if not context.agent_instance:
            return False
        
        # 获取Provider
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
        if isinstance(input_data, AgentInput):
            return True
        if isinstance(input_data, dict):
            return "instruction" in input_data
        return False
    
    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        """执行工具调用 - 两轮沟通机制"""
        try:
            # 确保输入是AgentInput类型
            if isinstance(input_data, dict):
                agent_input = AgentInput(**input_data)
            else:
                agent_input = input_data
            
            # 从AgentInput中解析工具调用所需的参数
            tool_params = self._parse_tool_params(agent_input)
            
            # 第一轮：选择工具
            selected_tool = await self._select_tool_first_round(tool_params, context)
            
            # 第二轮：选择具体API和参数
            api_call = await self._select_api_and_params_second_round(
                tool_name=selected_tool["tool_name"],
                task_description=tool_params["task_description"],
                context_data=tool_params.get("context_data", {}),
                constraints=tool_params.get("constraints", []),
                context=context
            )
            
            # 检查置信度
            final_confidence = min(selected_tool["confidence"], api_call["confidence"])
            confidence_threshold = tool_params.get("confidence_threshold", 0.7)
            if final_confidence < confidence_threshold:
                if context.logger:
                    context.logger.warning(
                        f"最终置信度 {final_confidence} 低于阈值 {confidence_threshold}"
                    )
            
            # 执行API调用
            alternatives_tried = []
            fallback_tools = tool_params.get("fallback_tools", [])
            all_tools_to_try = [selected_tool["tool_name"]] + fallback_tools
            
            for tool_name in all_tools_to_try:
                try:
                    result = await self._call_tool(
                        tool_name=tool_name,
                        action=api_call["action"],
                        parameters=api_call["parameters"],
                        context=context
                    )
                    
                    if context.logger:
                        context.logger.info(f"工具调用成功: {result}")
                    
                    return AgentOutput(
                        success=True,
                        data={
                            "result": result,
                            "tool_used": tool_name,
                            "action_taken": api_call["action"],
                            "confidence": final_confidence,
                            "reasoning": f"工具选择: {selected_tool['reasoning']}; API选择: {api_call['reasoning']}",
                            "alternatives_tried": alternatives_tried,
                            "parameters": api_call["parameters"],
                            "tool_selection": selected_tool,
                            "api_selection": api_call
                        },
                        message="工具调用成功"
                    )
                    
                except Exception as e:
                    alternatives_tried.append(tool_name)
                    if context.logger:
                        context.logger.warning(f"工具 {tool_name} 执行失败: {str(e)}")
                    continue
            
            # 所有工具都失败了
            return AgentOutput(
                success=False,
                data={
                    "tool_used": selected_tool.get("tool_name", "unknown"),
                    "action_taken": api_call.get("action", "unknown"),
                    "confidence": final_confidence,
                    "reasoning": f"工具选择: {selected_tool.get('reasoning', '')}; API选择: {api_call.get('reasoning', '')}",
                    "alternatives_tried": alternatives_tried,
                },
                message=f"所有工具都执行失败，尝试过: {alternatives_tried}"
            )
            
        except Exception as e:
            if context.logger:
                context.logger.error(f"Tool Agent执行失败: {str(e)}")
            
            return AgentOutput(
                success=False,
                data={},
                message=f"Tool Agent执行失败: {str(e)}"
            )
    
    def _parse_tool_params(self, agent_input: AgentInput) -> Dict[str, Any]:
        """从AgentInput解析工具调用参数"""
        return {
            "task_description": agent_input.instruction,
            "context_data": agent_input.data,
            "constraints": agent_input.metadata.get("constraints", []),
            "allowed_tools": agent_input.metadata.get("allowed_tools", []),
            "fallback_tools": agent_input.metadata.get("fallback_tools", []),
            "confidence_threshold": agent_input.metadata.get("confidence_threshold", 0.7)
        }
    
    def _get_filtered_tools(self, tool_params: Dict[str, Any]) -> List[str]:
        """获取预筛选的工具列表"""
        if tool_params.get("allowed_tools"):
            return tool_params["allowed_tools"]
        else:
            return self._get_all_available_tools()
    
    def _get_all_available_tools(self) -> List[str]:
        """获取所有可用工具"""
        if self.tool_registry and hasattr(self.tool_registry, 'get_registered_tools'):
            return self.tool_registry.get_registered_tools()
        elif self.tool_registry and hasattr(self.tool_registry, 'tools'):
            return list(self.tool_registry.tools.keys())
        return ["browser_use"]  # 默认工具
    
    async def _select_tool_first_round(
        self, 
        tool_params: Dict[str, Any],
        context: AgentContext
    ) -> Dict[str, Any]:
        """第一轮：基于任务描述选择工具"""
        
        # 获取可用工具
        available_tools = self._get_filtered_tools(tool_params)
        
        # 获取工具描述信息
        tool_descriptions = await self._get_tool_descriptions_from_registry(available_tools, context)
        
        analysis_prompt = f"""
任务描述: {tool_params['task_description']}
上下文数据: {tool_params.get('context_data', {})}
约束条件: {tool_params.get('constraints', [])}

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
            result = self._parse_json_response(response)
            
            # 验证结果
            if result.get("tool_name") not in available_tools:
                raise ValueError(f"选择的工具 {result.get('tool_name')} 不在可用工具列表中")
            
            return {
                "tool_name": result["tool_name"],
                "confidence": float(result.get("confidence", 0.5)),
                "reasoning": result.get("reasoning", "")
            }
            
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
        
        # 获取工具的可用API信息
        tool_apis = await self._get_tool_apis(tool_name, context)
        
        api_prompt = f"""
已选择工具: {tool_name}
任务描述: {task_description}
上下文数据: {context_data}
约束条件: {constraints}

该工具可用的API操作:
{tool_apis}

请基于任务需求选择具体的API操作和参数。

返回JSON格式：
{{
    "action": "API操作名称",
    "parameters": {{"参数名": "参数值"}},
    "confidence": 0.0到1.0之间的置信度,
    "reasoning": "选择这个API和参数的理由"
}}
"""
        
        try:
            response = await self.provider.generate_response(
                system_prompt="你是一个API选择专家。请根据任务需求选择合适的API操作和参数，返回严格的JSON格式结果。",
                user_prompt=api_prompt
            )
            
            if context.logger:
                context.logger.info(f"第二轮LLM原始响应: {response}")
            
            result = self._parse_json_response(response)
            
            return {
                "action": result.get("action", "navigate_and_extract"),
                "parameters": result.get("parameters", {"instruction": task_description}),
                "confidence": float(result.get("confidence", 0.5)),
                "reasoning": result.get("reasoning", "")
            }
            
        except Exception as e:
            if context.logger:
                context.logger.error(f"第二轮API选择失败: {str(e)}")
        
        # 默认返回通用操作
        return {
            "action": "navigate_and_extract",
            "parameters": {"instruction": task_description},
            "confidence": 0.3,
            "reasoning": "使用默认API操作，原因：LLM响应解析失败"
        }
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """解析LLM的JSON响应"""
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
        
        return json.loads(response_clean)
    
    async def _get_tool_descriptions_from_registry(self, available_tools: List[str], context: AgentContext) -> str:
        """从工具注册表获取工具描述"""
        descriptions = []
        for tool_name in available_tools:
            try:
                tool_instance = await self._get_tool_instance(tool_name, context)
                if hasattr(tool_instance, 'get_description'):
                    desc = tool_instance.get_description()
                else:
                    desc = f"{tool_name} - 工具描述不可用"
                descriptions.append(f"- {tool_name}: {desc}")
            except Exception as e:
                descriptions.append(f"- {tool_name}: 获取描述失败 ({str(e)})")
        
        return "\\n".join(descriptions) if descriptions else "无可用工具"
    
    async def _get_tool_apis(self, tool_name: str, context: AgentContext) -> str:
        """获取工具的API信息"""
        try:
            tool_instance = await self._get_tool_instance(tool_name, context)
            if hasattr(tool_instance, 'get_available_actions'):
                actions = tool_instance.get_available_actions()
                return "\\n".join([f"- {action}" for action in actions])
            else:
                return "- navigate_and_extract: 导航并提取信息"
        except Exception:
            return "- navigate_and_extract: 导航并提取信息（默认操作）"
    
    async def _get_tool_instance(self, tool_name: str, context: AgentContext):
        """获取工具实例"""
        if hasattr(self.tool_registry, 'get_tool'):
            return self.tool_registry.get_tool(tool_name)
        elif hasattr(self.tool_registry, 'tools') and tool_name in self.tool_registry.tools:
            return self.tool_registry.tools[tool_name]
        else:
            raise ValueError(f"工具 {tool_name} 不存在")
    
    async def _call_tool(
        self, 
        tool_name: str, 
        action: str, 
        parameters: Dict[str, Any], 
        context: AgentContext
    ) -> Any:
        """调用具体的工具"""
        # 解析变量
        resolved_params = await self._resolve_variables(parameters, context)
        
        # 调用工具
        if hasattr(context.agent_instance, 'use_tool'):
            return await context.agent_instance.use_tool(tool_name, action, resolved_params)
        else:
            raise ValueError("工具调用接口不可用")
    
    async def _resolve_variables(self, params: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
        """解析参数中的变量"""
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                var_name = value[2:-2].strip()
                resolved[key] = context.variables.get(var_name, value)
            else:
                resolved[key] = value
        return resolved