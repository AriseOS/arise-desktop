"""
Agent Router - Agent路由器
"""
import json
from typing import Dict, Any

from .agent_registry import AgentRegistry
from ..core.schemas import AgentContext


class AgentRouter:
    """Agent路由器"""
    
    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self.llm_client = None
    
    async def route_to_agent(self, task_description: str, context: AgentContext) -> str:
        """
        根据任务描述自动选择合适的Agent
        
        Args:
            task_description: 任务描述
            context: Agent执行上下文
            
        Returns:
            str: Agent类型 (text_agent | tool_agent | code_agent)
        """
        if not self.llm_client:
            if context.agent_instance and hasattr(context.agent_instance, 'llm_client'):
                self.llm_client = context.agent_instance.llm_client
            else:
                # 如果没有LLM客户端，使用简单的规则路由
                return self._rule_based_routing(task_description)
        
        try:
            # 获取可用工具列表
            available_tools = self._get_available_tools(context)
            
            routing_prompt = f"""
任务描述: {task_description}
可用工具: {available_tools}

请判断这个任务应该用哪种Agent来处理：

1. Text Agent: 如果只需要生成文本回答
2. Tool Agent: 如果有现成的工具可以完成任务
3. Code Agent: 如果需要编写代码来解决问题

判断依据：
- 如果任务是"回答问题"、"解释说明"、"总结内容"等，用Text Agent
- 如果任务是"填写表单"、"点击按钮"、"读取聊天"等，用Tool Agent  
- 如果任务是"数据分析"、"格式转换"、"复杂计算"等，用Code Agent

只返回：text_agent 或 tool_agent 或 code_agent
"""
            
            response = await self.llm_client.chat_completion(
                messages=[{"role": "user", "content": routing_prompt}],
                temperature=0.3
            )
            
            agent_type = response.choices[0].message.content.strip().lower()
            
            # 验证返回的Agent类型
            valid_types = ["text_agent", "tool_agent", "code_agent"]
            if agent_type in valid_types:
                return agent_type
            else:
                # 如果LLM返回了无效类型，使用规则路由
                return self._rule_based_routing(task_description)
                
        except Exception as e:
            if context.logger:
                context.logger.warning(f"LLM路由失败，使用规则路由: {str(e)}")
            return self._rule_based_routing(task_description)
    
    def _rule_based_routing(self, task_description: str) -> str:
        """基于规则的简单路由"""
        task_lower = task_description.lower()
        
        # Text Agent关键词
        text_keywords = [
            "回答", "解答", "说明", "解释", "总结", "描述", "介绍", 
            "什么是", "如何理解", "含义", "意思", "定义"
        ]
        
        # Tool Agent关键词
        tool_keywords = [
            "填写", "点击", "打开", "关闭", "发送", "接收", "读取", 
            "获取", "下载", "上传", "表单", "按钮", "网页", "微信", "聊天"
        ]
        
        # Code Agent关键词
        code_keywords = [
            "分析", "计算", "处理", "转换", "格式化", "统计", "排序", 
            "筛选", "算法", "数据", "编程", "代码", "函数"
        ]
        
        # 检查关键词匹配
        for keyword in text_keywords:
            if keyword in task_lower:
                return "text_agent"
        
        for keyword in tool_keywords:
            if keyword in task_lower:
                return "tool_agent"
        
        for keyword in code_keywords:
            if keyword in task_lower:
                return "code_agent"
        
        # 默认返回text_agent
        return "text_agent"
    
    def _get_available_tools(self, context: AgentContext) -> str:
        """获取可用工具列表"""
        try:
            if context.agent_instance and hasattr(context.agent_instance, 'available_tools'):
                tools = context.agent_instance.available_tools
                return ", ".join(tools)
            else:
                # 返回默认工具列表
                return "browser_use, android_use, llm_extract"
        except:
            return "browser_use, android_use, llm_extract"
    
    async def route_with_confidence(
        self, 
        task_description: str, 
        context: AgentContext
    ) -> Dict[str, Any]:
        """
        带置信度的路由选择
        
        Returns:
            Dict: {
                "agent_type": str,
                "confidence": float,
                "reasoning": str
            }
        """
        if not self.llm_client:
            if context.agent_instance and hasattr(context.agent_instance, 'llm_client'):
                self.llm_client = context.agent_instance.llm_client
            else:
                return {
                    "agent_type": self._rule_based_routing(task_description),
                    "confidence": 0.7,
                    "reasoning": "基于规则的路由选择"
                }
        
        try:
            available_tools = self._get_available_tools(context)
            
            routing_prompt = f"""
任务描述: {task_description}
可用工具: {available_tools}

请分析这个任务应该用哪种Agent来处理，并给出置信度和理由：

1. Text Agent: 如果只需要生成文本回答
2. Tool Agent: 如果有现成的工具可以完成任务  
3. Code Agent: 如果需要编写代码来解决问题

返回JSON格式：
{{
    "agent_type": "text_agent/tool_agent/code_agent",
    "confidence": 0.95,
    "reasoning": "选择理由"
}}
"""
            
            response = await self.llm_client.chat_completion(
                messages=[{"role": "user", "content": routing_prompt}],
                temperature=0.3
            )
            
            try:
                result = json.loads(response.choices[0].message.content.strip())
                
                # 验证结果
                valid_types = ["text_agent", "tool_agent", "code_agent"]
                if result.get("agent_type") not in valid_types:
                    result["agent_type"] = self._rule_based_routing(task_description)
                    result["confidence"] = 0.5
                    result["reasoning"] = "LLM返回无效类型，使用规则回退"
                
                return result
                
            except json.JSONDecodeError:
                return {
                    "agent_type": self._rule_based_routing(task_description),
                    "confidence": 0.5,
                    "reasoning": "JSON解析失败，使用规则回退"
                }
                
        except Exception as e:
            if context.logger:
                context.logger.warning(f"置信度路由失败: {str(e)}")
            
            return {
                "agent_type": self._rule_based_routing(task_description),
                "confidence": 0.6,
                "reasoning": f"路由异常，使用规则回退: {str(e)}"
            }