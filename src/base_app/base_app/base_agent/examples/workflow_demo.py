"""
Workflow 模块演示示例
展示如何使用 BaseAgent 的工作流功能
"""
import asyncio
import logging
from ..core import (
    BaseAgent, AgentConfig, WorkflowStep, Workflow, StepType, ErrorHandling
)

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def demo_basic_workflow():
    """演示基础工作流功能"""
    print("=== 基础工作流演示 ===")
    
    # 创建 BaseAgent 实例
    config = AgentConfig(name="WorkflowDemo", enable_logging=True)
    agent = BaseAgent(config=config, enable_memory=False)  # 不启用内存以简化演示
    
    # 定义工作流步骤
    steps = [
        WorkflowStep(
            name="步骤1：设置变量",
            step_type=StepType.CODE,
            code="""
# 设置一些基础变量
name = variables.get('user_name', '访客')
greeting = f"你好，{name}！"
numbers = [1, 2, 3, 4, 5]
result = {
    'greeting': greeting,
    'numbers': numbers,
    'total': sum(numbers)
}
print(f"步骤1执行：{result}")
""",
            output_key="step1_result"
        ),
        WorkflowStep(
            name="步骤2：数据处理",
            step_type=StepType.CODE,
            code="""
# 处理前一步的数据
prev_result = step_results.get('step1_result', {})
greeting = prev_result.get('greeting', '你好！')
numbers = prev_result.get('numbers', [])

# 计算一些统计信息
if numbers:
    stats = {
        'count': len(numbers),
        'sum': sum(numbers),
        'avg': sum(numbers) / len(numbers),
        'max': max(numbers),
        'min': min(numbers)
    }
else:
    stats = {}

result = {
    'greeting': greeting,
    'statistics': stats,
    'processed': True
}
print(f"步骤2执行：{result}")
""",
            output_key="step2_result"
        ),
        WorkflowStep(
            name="步骤3：生成报告",
            step_type=StepType.CODE,
            code="""
# 生成最终报告
step2_data = step_results.get('step2_result', {})
greeting = step2_data.get('greeting', '你好！')
stats = step2_data.get('statistics', {})

if stats:
    report = f\"\"\"{greeting}

数据处理报告：
- 数据个数：{stats.get('count', 0)}
- 总和：{stats.get('sum', 0)}
- 平均值：{stats.get('avg', 0):.2f}
- 最大值：{stats.get('max', 0)}
- 最小值：{stats.get('min', 0)}

处理完成！\"\"\"
else:
    report = f"{greeting}\\n无数据需要处理。"

result = report
print(f"步骤3执行：生成报告")
print(report)
""",
            output_key="final_report"
        )
    ]
    
    # 执行工作流
    result = await agent.run_workflow(steps, {"user_name": "张三"})
    
    print(f"\\n工作流执行结果：")
    print(f"- 成功：{result.success}")
    print(f"- 耗时：{result.total_execution_time:.2f}秒")
    print(f"- 完成步骤：{len(result.completed_steps)}")
    print(f"- 失败步骤：{len(result.failed_steps)}")
    
    if result.final_result:
        print(f"\\n最终结果：\\n{result.final_result}")


async def demo_conditional_workflow():
    """演示条件执行工作流"""
    print("\\n=== 条件执行工作流演示 ===")
    
    config = AgentConfig(name="ConditionalDemo", enable_logging=True)
    agent = BaseAgent(config=config, enable_memory=False)
    
    # 定义条件工作流
    steps = [
        WorkflowStep(
            name="输入分析",
            step_type=StepType.CODE,
            code="""
user_input = variables.get('user_input', '')
print(f"分析输入：{user_input}")

# 简单的条件判断
if '数字' in user_input or user_input.isdigit():
    task_type = 'number'
elif '文本' in user_input or any(c.isalpha() for c in user_input):
    task_type = 'text'
else:
    task_type = 'unknown'

result = {
    'input': user_input,
    'type': task_type
}
print(f"识别类型：{task_type}")
""",
            output_key="analysis"
        ),
        WorkflowStep(
            name="数字处理",
            step_type=StepType.CODE,
            condition="{{analysis.type}} == 'number'",
            code="""
analysis = step_results.get('analysis', {})
user_input = analysis.get('input', '')

# 提取数字并计算
import re
numbers = [int(x) for x in re.findall(r'\\d+', user_input)]

if numbers:
    result = {
        'numbers': numbers,
        'sum': sum(numbers),
        'count': len(numbers),
        'message': f"找到 {len(numbers)} 个数字，总和为 {sum(numbers)}"
    }
else:
    result = {'message': '未找到有效数字'}

print(f"数字处理结果：{result}")
""",
            output_key="number_result"
        ),
        WorkflowStep(
            name="文本处理",
            step_type=StepType.CODE,
            condition="{{analysis.type}} == 'text'",
            code="""
analysis = step_results.get('analysis', {})
user_input = analysis.get('input', '')

# 文本统计
words = user_input.split()
char_count = len(user_input)
word_count = len(words)

result = {
    'char_count': char_count,
    'word_count': word_count,
    'words': words,
    'message': f"文本包含 {char_count} 个字符，{word_count} 个词"
}

print(f"文本处理结果：{result}")
""",
            output_key="text_result"
        ),
        WorkflowStep(
            name="生成最终响应",
            step_type=StepType.CODE,
            code="""
analysis = step_results.get('analysis', {})
number_result = step_results.get('number_result')
text_result = step_results.get('text_result')

task_type = analysis.get('type', 'unknown')
user_input = analysis.get('input', '')

if task_type == 'number' and number_result:
    result = f"数字处理完成：{number_result.get('message', '')}"
elif task_type == 'text' and text_result:
    result = f"文本处理完成：{text_result.get('message', '')}"
else:
    result = f"无法识别输入类型：{user_input}"

print(f"最终响应：{result}")
""",
            output_key="final_response"
        )
    ]
    
    # 测试不同类型的输入
    test_cases = [
        "处理数字：123 456",
        "处理文本：这是一段测试文本",
        "未知输入：!@#"
    ]
    
    for test_input in test_cases:
        print(f"\\n测试输入：{test_input}")
        result = await agent.run_workflow(steps, {"user_input": test_input})
        
        if result.success and result.final_result:
            print(f"结果：{result.final_result}")
        else:
            print(f"执行失败：{result.error_message}")


async def demo_memory_workflow():
    """演示内存操作工作流"""
    print("\\n=== 内存操作工作流演示 ===")
    
    config = AgentConfig(name="MemoryDemo", enable_logging=True)
    agent = BaseAgent(config=config, enable_memory=False)  # 使用简单内存存储
    
    # 定义内存操作工作流
    steps = [
        WorkflowStep(
            name="存储用户信息",
            step_type=StepType.MEMORY,
            memory_action="store",
            memory_key="user_profile",
            memory_value={
                "name": "{{user_name}}",
                "age": "{{user_age}}",
                "interests": ["编程", "音乐", "阅读"]
            },
            output_key="store_result"
        ),
        WorkflowStep(
            name="存储会话历史",
            step_type=StepType.MEMORY,
            memory_action="store", 
            memory_key="session_history",
            memory_value=["用户登录", "查看个人资料", "{{current_action}}"],
            output_key="history_result"
        ),
        WorkflowStep(
            name="读取用户信息",
            step_type=StepType.MEMORY,
            memory_action="get",
            memory_key="user_profile",
            params={"default": {}},
            output_key="user_info"
        ),
        WorkflowStep(
            name="生成个性化响应",
            step_type=StepType.CODE,
            code="""
user_info = step_results.get('user_info', {})
current_action = variables.get('current_action', '未知操作')

if user_info:
    name = user_info.get('name', '用户')
    age = user_info.get('age', '未知')
    interests = user_info.get('interests', [])
    
    interest_text = '、'.join(interests) if interests else '无'
    
    result = f\"\"\"
个性化响应：
你好，{name}！
年龄：{age}
兴趣爱好：{interest_text}
当前操作：{current_action}

很高兴为您服务！
\"\"\"
else:
    result = f"你好！当前操作：{current_action}"

print(result.strip())
""",
            output_key="personalized_response"
        )
    ]
    
    # 执行内存工作流
    result = await agent.run_workflow(steps, {
        "user_name": "李四",
        "user_age": "25",
        "current_action": "查看个人资料"
    })
    
    if result.success and result.final_result:
        print(result.final_result)
    else:
        print(f"执行失败：{result.error_message}")


async def demo_user_qa_workflow():
    """演示用户问答工作流（BaseAgent的默认行为）"""
    print("\\n=== 用户问答工作流演示 ===")
    
    config = AgentConfig(name="UserQADemo", enable_logging=True)
    agent = BaseAgent(config=config, enable_memory=False)
    
    # 测试不同类型的用户输入
    test_questions = [
        "现在几点了？",
        "今天天气怎么样？",
        "你能帮我做什么？"
    ]
    
    for question in test_questions:
        print(f"\\n用户问题：{question}")
        
        # 使用 BaseAgent 的默认处理方法
        response = await agent.process_user_input(question, "demo_user")
        print(f"Agent响应：{response}")


async def main():
    """主演示函数"""
    print("BaseAgent Workflow 模块演示")
    print("=" * 50)
    
    try:
        # 运行各种演示
        await demo_basic_workflow()
        await demo_conditional_workflow()
        await demo_memory_workflow()
        await demo_user_qa_workflow()
        
        print("\\n=" * 50)
        print("所有演示完成！")
        
    except Exception as e:
        logger.error(f"演示过程中发生错误: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())