#!/usr/bin/env python3
"""
BaseAgent 用户自定义接口使用示例
"""
import asyncio
import sys
import os
import logging

# 添加path到sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from base_app.base_agent.core.base_agent import BaseAgent
from base_app.base_agent.core.schemas import AgentConfig

# 设置日志级别
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def example_1_simple_qa():
    """示例1: 创建简单问答Agent"""
    print("=== 示例1: 简单问答Agent ===")
    
    # 创建BaseAgent实例
    config = AgentConfig(
        name="智能助手",
        llm_provider="openai",
        llm_model="gpt-4o",
        api_key="your-api-key-here"  # 替换为真实的API密钥
    )
    
    agent = BaseAgent(config)
    await agent.initialize()
    
    # 方法1: 使用内置模板
    qa_workflow = agent.create_quick_qa_workflow("智能助手", "你是一个友好的AI助手，请用简洁的语言回答问题。")
    
    # 方法2: 手动构建工作流
    builder = agent.create_workflow_builder("问答助手", "回答用户问题的工作流")
    builder.add_text_step(
        name="理解问题",
        instruction="分析用户问题，理解其意图和需求",
        response_style="professional"
    ).add_text_step(
        name="生成回答",
        instruction="基于问题理解，生成准确、有用的回答",
        response_style="friendly"
    )
    
    manual_workflow = builder.build()
    
    # 模拟执行（需要真实API密钥）
    print(f"✓ 创建了问答工作流: {qa_workflow.name}")
    print(f"✓ 创建了手动工作流: {manual_workflow.name}")
    print(f"✓ 工作流步骤数: {len(manual_workflow.steps)}")

async def example_2_custom_translator():
    """示例2: 创建自定义翻译Agent"""
    print("\n=== 示例2: 自定义翻译Agent ===")
    
    config = AgentConfig(
        name="翻译助手",
        llm_provider="openai",
        llm_model="gpt-4o",
        api_key="your-api-key-here"
    )
    
    agent = BaseAgent(config)
    await agent.initialize()
    
    # 创建自定义翻译Agent
    translator = agent.create_custom_text_agent(
        name="专业翻译员",
        system_prompt="""你是一个专业的中英文翻译员。请遵循以下规则：
1. 提供准确、流畅的翻译
2. 保持原文的语调和风格
3. 对于专业术语，提供准确的翻译
4. 如果遇到歧义，选择最合适的翻译""",
        response_style="professional",
        temperature=0.3  # 降低温度以提高翻译一致性
    )
    
    # 注册自定义Agent
    agent.register_custom_agent(translator)
    
    # 创建翻译工作流
    builder = agent.create_workflow_builder("翻译服务", "专业翻译服务")
    builder.add_custom_step(
        name="翻译文本",
        agent_name="专业翻译员",
        instruction="将用户输入的文本进行翻译"
    )
    
    translation_workflow = builder.build()
    
    # 或者使用内置模板
    auto_workflow = agent.create_translation_workflow("中文", "英文")
    
    print(f"✓ 创建了专业翻译Agent: {translator.metadata.name}")
    print(f"✓ 创建了翻译工作流: {translation_workflow.name}")
    print(f"✓ 可用Agent: {agent.list_available_agents()}")

async def example_3_data_analysis():
    """示例3: 数据分析工作流"""
    print("\n=== 示例3: 数据分析工作流 ===")
    
    config = AgentConfig(
        name="数据分析师",
        llm_provider="openai",
        llm_model="gpt-4o",
        api_key="your-api-key-here"
    )
    
    agent = BaseAgent(config)
    await agent.initialize()
    
    # 创建数据分析相关的自定义Agent
    data_analyst = agent.create_custom_text_agent(
        name="数据分析专家",
        system_prompt="""你是一个专业的数据分析师。你的任务是：
1. 理解用户的数据分析需求
2. 提供数据分析方法建议
3. 解释分析结果
4. 生成分析报告""",
        response_style="technical"
    )
    
    code_generator = agent.create_custom_code_agent(
        name="Python数据分析师",
        language="python",
        allowed_libraries=["pandas", "numpy", "matplotlib", "seaborn"],
        code_template="""import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# 数据分析代码
"""
    )
    
    # 注册自定义Agent
    agent.register_custom_agent(data_analyst)
    agent.register_custom_agent(code_generator)
    
    # 创建数据分析工作流
    builder = agent.create_workflow_builder("数据分析流程", "完整的数据分析工作流")
    
    builder.add_custom_step(
        name="需求分析",
        agent_name="数据分析专家",
        instruction="分析用户的数据分析需求，确定分析目标和方法"
    ).add_text_step(
        name="数据读取",
        instruction="根据用户提供的数据源，读取和预处理数据",
        agent_name="tool_agent"
    ).add_custom_step(
        name="生成分析代码",
        agent_name="Python数据分析师",
        instruction="根据需求分析结果，生成相应的Python数据分析代码"
    ).add_custom_step(
        name="结果解释",
        agent_name="数据分析专家",
        instruction="解释分析结果，生成分析报告"
    )
    
    analysis_workflow = builder.build()
    
    print(f"✓ 创建了数据分析工作流: {analysis_workflow.name}")
    print(f"✓ 工作流步骤: {[step.name for step in analysis_workflow.steps]}")

async def example_4_conditional_workflow():
    """示例4: 条件执行工作流"""
    print("\n=== 示例4: 条件执行工作流 ===")
    
    config = AgentConfig(
        name="智能助手",
        llm_provider="openai",
        llm_model="gpt-4o",
        api_key="your-api-key-here"
    )
    
    agent = BaseAgent(config)
    await agent.initialize()
    
    # 创建意图分析Agent
    intent_analyzer = agent.create_custom_text_agent(
        name="意图分析器",
        system_prompt="""你是一个意图分析专家。请分析用户输入并返回以下类型之一：
- "chat": 普通聊天对话
- "translate": 翻译请求
- "code": 代码生成请求
- "search": 搜索请求

只返回类型，不要添加其他内容。""",
        response_style="concise"
    )
    
    # 创建专门的处理Agent
    translator = agent.create_custom_text_agent(
        name="翻译专家",
        system_prompt="你是专业翻译员，请提供准确的翻译。",
        response_style="professional"
    )
    
    code_assistant = agent.create_custom_code_agent(
        name="代码助手",
        language="python",
        allowed_libraries=["requests", "json", "datetime"],
        code_template="# Python代码\n"
    )
    
    # 注册所有Agent
    agent.register_custom_agent(intent_analyzer)
    agent.register_custom_agent(translator)
    agent.register_custom_agent(code_assistant)
    
    # 创建条件执行工作流
    builder = agent.create_workflow_builder("智能分发", "根据意图分发到不同处理Agent")
    
    # 意图分析步骤
    builder.add_custom_step(
        name="意图分析",
        agent_name="意图分析器",
        instruction="分析用户输入的意图类型"
    )
    
    # 条件执行步骤
    builder.add_text_step(
        name="聊天处理",
        instruction="进行友好的对话交流",
        condition="{{step_results.意图分析.answer}} == 'chat'",
        response_style="friendly"
    )
    
    builder.add_custom_step(
        name="翻译处理",
        agent_name="翻译专家",
        instruction="翻译用户的文本",
        condition="{{step_results.意图分析.answer}} == 'translate'"
    )
    
    builder.add_custom_step(
        name="代码处理",
        agent_name="代码助手",
        instruction="生成用户需要的代码",
        condition="{{step_results.意图分析.answer}} == 'code'"
    )
    
    builder.add_text_step(
        name="搜索处理",
        instruction="搜索相关信息",
        condition="{{step_results.意图分析.answer}} == 'search'",
        agent_name="tool_agent"
    )
    
    conditional_workflow = builder.build()
    
    print(f"✓ 创建了条件执行工作流: {conditional_workflow.name}")
    print(f"✓ 工作流步骤数: {len(conditional_workflow.steps)}")

async def example_5_workflow_management():
    """示例5: 工作流管理功能"""
    print("\n=== 示例5: 工作流管理功能 ===")
    
    config = AgentConfig(
        name="工作流管理器",
        llm_provider="openai",
        llm_model="gpt-4o",
        api_key="your-api-key-here"
    )
    
    agent = BaseAgent(config)
    await agent.initialize()
    
    # 创建一个简单工作流
    builder = agent.create_workflow_builder("示例工作流", "用于演示工作流管理功能")
    builder.add_text_step("步骤1", "第一个步骤")
    builder.add_text_step("步骤2", "第二个步骤")
    
    workflow = builder.build()
    
    # 1. 验证工作流
    errors = agent.validate_workflow(workflow)
    if errors:
        print(f"⚠ 工作流验证错误: {errors}")
    else:
        print("✓ 工作流验证通过")
    
    # 2. 导出工作流
    json_str = agent.export_workflow(workflow, "example_workflow.json")
    print(f"✓ 工作流已导出到文件 (长度: {len(json_str)} 字符)")
    
    # 3. 导入工作流
    imported_workflow = agent.import_workflow(file_path="example_workflow.json")
    print(f"✓ 工作流已导入: {imported_workflow.name}")
    
    # 4. 获取工作流模板
    templates = agent.get_workflow_templates()
    print(f"✓ 可用工作流模板: {list(templates.keys())}")
    
    # 5. 获取Agent信息
    agent_info = agent.get_agent_info("text_agent")
    print(f"✓ 内置Agent信息: {agent_info['name']} - {agent_info['description']}")
    
    # 6. 列出所有可用Agent
    available_agents = agent.list_available_agents()
    print(f"✓ 可用Agent列表: {available_agents}")

async def example_6_advanced_customization():
    """示例6: 高级自定义功能"""
    print("\n=== 示例6: 高级自定义功能 ===")
    
    config = AgentConfig(
        name="高级助手",
        llm_provider="openai",
        llm_model="gpt-4o",
        api_key="your-api-key-here"
    )
    
    agent = BaseAgent(config)
    await agent.initialize()
    
    # 创建复杂的自定义Agent
    advanced_analyst = agent.create_custom_text_agent(
        name="高级分析师",
        system_prompt="""你是一个高级业务分析师，具有以下能力：
1. 深度分析复杂业务问题
2. 提供结构化的解决方案
3. 考虑多种情况和风险
4. 生成详细的分析报告

请用专业、结构化的方式回答问题。""",
        response_style="professional",
        max_length=1000,
        temperature=0.7
    )
    
    # 创建工具Agent with更多配置
    tool_specialist = agent.create_custom_tool_agent(
        name="工具专家",
        available_tools=["web_search", "data_processor", "file_manager"],
        tool_selection_strategy="confidence_based",
        confidence_threshold=0.9,
        max_tool_calls=5
    )
    
    # 注册Agent
    agent.register_custom_agent(advanced_analyst)
    agent.register_custom_agent(tool_specialist)
    
    # 创建复杂工作流
    builder = agent.create_workflow_builder("企业分析流程", "企业级分析和处理流程")
    
    # 设置详细的输入输出模式
    builder.set_input_schema({
        "business_question": {
            "type": "string", 
            "required": True, 
            "description": "业务问题或需求"
        },
        "context": {
            "type": "object", 
            "required": False, 
            "description": "业务上下文信息"
        },
        "priority": {
            "type": "string", 
            "required": False, 
            "description": "优先级：high/medium/low"
        }
    })
    
    builder.set_output_schema({
        "analysis_result": {
            "type": "string", 
            "description": "分析结果"
        },
        "recommendations": {
            "type": "array", 
            "description": "建议列表"
        },
        "risk_assessment": {
            "type": "object", 
            "description": "风险评估"
        }
    })
    
    # 添加复杂步骤
    builder.add_custom_step(
        name="深度分析",
        agent_name="高级分析师",
        instruction="对业务问题进行深度分析，识别关键要素和潜在风险",
        timeout=600  # 10分钟超时
    ).add_custom_step(
        name="数据收集",
        agent_name="工具专家",
        instruction="根据分析需求收集相关数据和信息",
        timeout=300
    ).add_custom_step(
        name="综合评估",
        agent_name="高级分析师",
        instruction="结合分析结果和收集的数据，进行综合评估",
        timeout=600
    ).add_text_step(
        name="报告生成",
        instruction="生成最终的分析报告和建议",
        response_style="professional",
        max_length=2000
    )
    
    enterprise_workflow = builder.build()
    
    print(f"✓ 创建了企业级工作流: {enterprise_workflow.name}")
    print(f"✓ 工作流包含输入模式: {len(enterprise_workflow.input_schema)} 个字段")
    print(f"✓ 工作流包含输出模式: {len(enterprise_workflow.output_schema)} 个字段")
    
    # 展示工作流详细信息
    workflow_dict = builder.to_dict()
    print(f"✓ 工作流详细信息: {workflow_dict['name']} - {workflow_dict['step_count']} 步骤")

async def main():
    """主函数 - 运行所有示例"""
    print("BaseAgent 用户自定义接口使用示例")
    print("=" * 50)
    
    examples = [
        example_1_simple_qa,
        example_2_custom_translator,
        example_3_data_analysis,
        example_4_conditional_workflow,
        example_5_workflow_management,
        example_6_advanced_customization
    ]
    
    for example in examples:
        try:
            await example()
        except Exception as e:
            print(f"❌ 示例执行失败: {e}")
    
    print("\n" + "=" * 50)
    print("所有示例执行完成！")
    print("\n注意：这些示例需要真实的API密钥才能执行工作流。")
    print("请将 'your-api-key-here' 替换为您的实际API密钥。")

if __name__ == "__main__":
    asyncio.run(main())