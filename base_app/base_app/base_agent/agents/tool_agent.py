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
        """执行工具调用"""
        try:
            # 解析输入
            if isinstance(input_data, dict):
                tool_input = ToolAgentInput(**input_data)
            else:
                tool_input = input_data
            
            # Step 1: 获取Workflow设计时预筛选的工具
            available_tools = self._get_filtered_tools(tool_input)
            alternatives_tried = []
            
            # Step 2: LLM分析并选择工具
            tool_selection = await self._select_tool_with_confidence(
                tool_input, available_tools, context
            )
            
            # Step 3: 检查置信度
            if tool_selection["confidence"] < tool_input.confidence_threshold:
                # 置信度不足，记录警告但继续执行
                if context.logger:
                    context.logger.warning(
                        f"工具选择置信度 {tool_selection['confidence']} 低于阈值 {tool_input.confidence_threshold}"
                    )
            
            # Step 4: 尝试执行工具调用
            primary_tools = [tool_selection["tool_name"]]
            all_tools_to_try = primary_tools + tool_input.fallback_tools
            
            for tool_name in all_tools_to_try:
                try:
                    # 更新参数中的工具名（如果需要）
                    parameters = tool_selection["parameters"].copy()
                    
                    result = await self._call_tool(
                        tool_name=tool_name,
                        action=tool_selection["action"],
                        parameters=parameters,
                        context=context
                    )
                    
                    return ToolAgentOutput(
                        success=True,
                        result=result,
                        tool_used=tool_name,
                        action_taken=tool_selection["action"],
                        confidence=tool_selection["confidence"],
                        reasoning=tool_selection["reasoning"],
                        alternatives_tried=alternatives_tried,
                        metadata={"parameters": parameters}
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
                tool_used=tool_selection.get("tool_name", "unknown"),
                action_taken=tool_selection.get("action", "unknown"),
                confidence=tool_selection.get("confidence", 0.0),
                reasoning=tool_selection.get("reasoning", ""),
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
        # 这里应该从工具注册表获取，暂时返回默认工具
        return ["browser_use", "android_use", "llm_extract"]
    
    async def _select_tool_with_confidence(
        self, 
        input_data: ToolAgentInput, 
        available_tools: List[str],
        context: AgentContext
    ) -> Dict[str, Any]:
        """LLM选择工具并返回置信度"""
        
        # 构建工具描述
        tool_descriptions = self._get_tool_descriptions(available_tools)
        
        analysis_prompt = f"""
任务描述: {input_data.task_description}
上下文数据: {input_data.context_data}
约束条件: {input_data.constraints}

可用工具及描述:
{tool_descriptions}

请分析这个任务应该：
1. 使用哪个工具（必须从可用工具中选择）
2. 调用什么动作
3. 需要什么参数
4. 你对这个选择的置信度（0-1）
5. 选择这个工具的理由

返回JSON格式：
{{
    "tool_name": "工具名称",
    "action": "动作名称", 
    "parameters": {{参数字典}},
    "confidence": 0.95,
    "reasoning": "选择理由和分析过程"
}}
"""
        
        # Provider推理得到工具选择结果
        response = await self.provider.generate_response(
            system_prompt="你是一个工具选择专家。请分析任务需求并选择最合适的工具，返回JSON格式的结果。",
            user_prompt=analysis_prompt
        )
        
        try:
            tool_selection = json.loads(response.strip())
        except json.JSONDecodeError:
            # 如果JSON解析失败，返回默认选择
            tool_selection = {
                "tool_name": available_tools[0] if available_tools else "unknown",
                "action": "default",
                "parameters": {},
                "confidence": 0.3,
                "reasoning": "JSON解析失败，使用默认选择"
            }
        
        # 验证选择的工具是否在允许范围内
        if tool_selection["tool_name"] not in available_tools:
            # 如果选择了不可用的工具，降低置信度并选择第一个可用工具
            tool_selection["tool_name"] = available_tools[0] if available_tools else "unknown"
            tool_selection["confidence"] = 0.3
            tool_selection["reasoning"] += " [警告: 原选择工具不可用，自动回退]"
        
        return tool_selection
    
    def _get_tool_descriptions(self, tool_names: List[str]) -> str:
        """获取工具的详细描述"""
        descriptions = []
        for tool_name in tool_names:
            # 这里应该从工具注册表获取详细描述
            tool_desc = self._get_default_tool_description(tool_name)
            descriptions.append(f"- {tool_name}: {tool_desc}")
        return "\n".join(descriptions)
    
    def _get_default_tool_description(self, tool_name: str) -> str:
        """获取默认工具描述"""
        default_descriptions = {
            "browser_use": "网页浏览器操作工具，支持填写表单、点击按钮、提取网页内容等",
            "android_use": "Android设备操作工具，支持读取微信聊天、发送消息、截图等",
            "llm_extract": "LLM文本提取工具，支持从文本中提取实体、关键信息等"
        }
        return default_descriptions.get(tool_name, "无描述")
    
    async def _call_tool(
        self, 
        tool_name: str, 
        action: str, 
        parameters: Dict[str, Any],
        context: AgentContext
    ) -> Any:
        """调用具体工具"""
        if hasattr(context.agent_instance, 'call_tool'):
            return await context.agent_instance.call_tool(tool_name, action, **parameters)
        else:
            # 兼容性处理
            if hasattr(context.agent_instance, tool_name):
                tool = getattr(context.agent_instance, tool_name)
                if hasattr(tool, action):
                    return await getattr(tool, action)(**parameters)
        
        raise ValueError(f"无法调用工具 {tool_name} 的动作 {action}")
    
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