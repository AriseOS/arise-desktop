"""
Agent-as-Step 工作流演示
"""
import asyncio
import logging
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from base_agent.core.agent_workflow_engine import AgentWorkflowEngine
from base_agent.core.schemas import AgentWorkflowStep

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockLLMClient:
    """模拟LLM客户端"""
    
    async def chat_completion(self, messages, max_tokens=None, temperature=0.7):
        """模拟LLM调用"""
        user_message = messages[-1]["content"]
        
        # 简单的模拟响应
        if "text_agent" in user_message or "tool_agent" in user_message or "code_agent" in user_message:
            if "回答问题" in user_message or "总结" in user_message:
                content = "text_agent"
            elif "填写表单" in user_message or "读取聊天" in user_message:
                content = "tool_agent"
            elif "数据分析" in user_message or "计算" in user_message:
                content = "code_agent"
            else:
                content = "text_agent"
        elif "今天的会议安排" in user_message:
            content = "根据您的会议安排，今天有三个重要会议：10:00的产品评审会议、14:00的技术讨论会议，以及16:00的项目汇报会议。请注意合理安排时间。"
        elif "请总结一下" in user_message:
            content = "客户张三对我们的产品表现出浓厚兴趣，主要关心产品价格和交付时间。下一步需要发送详细报价单并安排技术演示，以进一步推进合作。"
        elif "tool_name" in user_message:
            content = '{"tool_name": "android_use", "action": "read_chat", "parameters": {"contact": "张三"}, "confidence": 0.9, "reasoning": "任务是读取微信聊天记录，android_use是最合适的工具"}'
        elif "input_data" in user_message and "提取" in user_message:
            content = '''
import re
import json

# 从聊天内容中提取关键信息
chat_text = str(input_data)

# 提取客户名称
customer_match = re.search(r'客户[:：]([^，,。.\\n]+)', chat_text)
customer = customer_match.group(1).strip() if customer_match else "未知客户"

# 提取时间信息
time_match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日|明天|后天|\d{1,2}月\d{1,2}日)', chat_text)
time_info = time_match.group(1) if time_match else "未指定时间"

# 提取地点信息
location_match = re.search(r'(地点|位置|地址)[:：]([^，,。.\\n]+)', chat_text)
location = location_match.group(2).strip() if location_match else "未指定地点"

result = {
    "customer_name": customer,
    "presentation_time": time_info,
    "location": location
}
'''
        else:
            content = "这是模拟的LLM响应"
        
        class MockChoice:
            def __init__(self, content):
                self.message = type('obj', (object,), {'content': content})
        
        class MockResponse:
            def __init__(self, content):
                self.choices = [MockChoice(content)]
        
        return MockResponse(content)


class MockBaseAgent:
    """模拟BaseAgent"""
    
    def __init__(self):
        self.llm_client = MockLLMClient()
        self.available_tools = ["browser_use", "android_use", "llm_extract"]
    
    async def call_tool(self, tool_name, action, **params):
        """模拟工具调用"""
        if tool_name == "android_use" and action == "read_chat":
            return "张三: 明天下午2点的路演准备得怎么样了？\n我: 已经准备好了，地点确认是会议室A吗？\n张三: 是的，到时候见。"
        elif tool_name == "browser_use" and action == "fill_form":
            return "表单提交成功，申请ID: APP-2024-001"
        else:
            return f"模拟{tool_name}工具调用结果"


async def run_demo():
    """运行演示"""
    logger.info("开始Agent-as-Step工作流演示")
    
    # 创建模拟Agent实例
    mock_agent = MockBaseAgent()
    
    # 创建工作流引擎
    engine = AgentWorkflowEngine(mock_agent)
    
    # 定义工作流步骤
    workflow_steps = [
        AgentWorkflowStep(
            name="获取客户聊天记录",
            agent_type="tool_agent",
            task_description="从微信中读取与指定客户的聊天记录",
            allowed_tools=["android_use"],
            fallback_tools=["browser_use"],
            confidence_threshold=0.8,
            input_ports={
                "context_data": {
                    "customer_name": "{{customer_name}}"
                }
            },
            output_ports={
                "result": "chat_content"
            }
        ),
        
        AgentWorkflowStep(
            name="提取关键信息",
            agent_type="code_agent",
            task_description="从聊天记录中提取客户姓名、路演时间、地点等关键信息",
            allowed_libraries=["re", "json"],
            expected_output_format="字典格式，包含customer_name, presentation_time, location字段",
            input_ports={
                "input_data": "{{chat_content}}"
            },
            constraints=["输出必须是JSON格式", "时间格式为YYYY-MM-DD HH:MM"],
            output_ports={
                "result": "extracted_info"
            }
        ),
        
        AgentWorkflowStep(
            name="填写路演申请表",
            agent_type="tool_agent",
            task_description="在企业微信中填写路演申请表单",
            allowed_tools=["browser_use"],
            fallback_tools=["android_use"],
            confidence_threshold=0.9,
            input_ports={
                "context_data": "{{extracted_info}}"
            },
            constraints=["必须填写所有必填字段"],
            output_ports={
                "result": "form_result"
            }
        ),
        
        AgentWorkflowStep(
            name="生成确认回复",
            agent_type="text_agent",
            task_description="根据表单提交结果，生成给客户的确认回复消息",
            response_style="professional",
            max_length=200,
            input_ports={
                "question": "请生成一个专业的确认回复",
                "context_data": {
                    "customer_name": "{{customer_name}}",
                    "form_result": "{{form_result}}",
                    "extracted_info": "{{extracted_info}}"
                }
            },
            constraints=["语调要专业友好", "包含下一步安排"],
            output_ports={
                "answer": "reply_message"
            }
        )
    ]
    
    # 执行工作流
    logger.info("开始执行工作流...")
    result = await engine.execute_workflow(
        steps=workflow_steps,
        input_data={"customer_name": "张三"}
    )
    
    # 输出结果
    logger.info(f"工作流执行结果: {result.success}")
    logger.info(f"执行时间: {result.total_execution_time:.2f}秒")
    logger.info(f"执行步骤数: {len(result.steps)}")
    
    if result.success:
        logger.info("最终结果:")
        for key, value in result.final_result.items():
            logger.info(f"  {key}: {value}")
        
        logger.info("\n步骤执行详情:")
        for i, step in enumerate(result.steps, 1):
            logger.info(f"  步骤{i}: {step.success} - {step.message}")
            if hasattr(step.data, 'answer'):
                logger.info(f"    回答: {step.data.answer}")
            elif hasattr(step.data, 'result'):
                logger.info(f"    结果: {step.data.result}")
    else:
        logger.error(f"工作流执行失败: {result.error_message}")
    
    # 显示Agent统计信息
    stats = engine.get_agent_stats()
    logger.info(f"\nAgent统计信息: {stats}")


if __name__ == "__main__":
    asyncio.run(run_demo())