#!/usr/bin/env python3
"""
测试用户自定义接口的实现
"""
import asyncio
import sys
import os
import logging

# 添加path到sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'base_app'))

from base_app.base_agent.core.base_agent import BaseAgent
from base_app.base_agent.core.schemas import AgentConfig
from base_app.base_agent.core.custom_agents import CustomTextAgent, CustomToolAgent, CustomCodeAgent

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_workflow_builder():
    """测试工作流构建器"""
    print("=== 测试工作流构建器 ===")
    
    # 创建BaseAgent实例
    config = AgentConfig(
        name="TestAgent",
        llm_provider="openai",
        llm_model="gpt-4o",
        api_key="test-key"  # 在实际测试中需要真实的API密钥
    )
    
    agent = BaseAgent(config)
    
    try:
        # 创建工作流构建器
        builder = agent.create_workflow_builder("测试工作流", "用于测试的工作流")
        print(f"✓ 成功创建工作流构建器: {builder}")
        
        # 添加步骤
        builder.add_text_step(
            name="理解需求",
            instruction="分析用户输入，理解其需求",
            response_style="professional"
        )
        
        builder.add_text_step(
            name="生成回答",
            instruction="基于需求理解，生成有用的回答",
            response_style="friendly"
        )
        
        print(f"✓ 成功添加步骤，当前步骤数: {builder.get_step_count()}")
        print(f"✓ 步骤名称: {builder.get_step_names()}")
        
        # 构建工作流
        workflow = builder.build()
        print(f"✓ 成功构建工作流: {workflow.name}")
        print(f"✓ 工作流步骤数: {len(workflow.steps)}")
        
        # 验证工作流
        errors = agent.validate_workflow(workflow)
        if errors:
            print(f"⚠ 工作流验证发现问题: {errors}")
        else:
            print("✓ 工作流验证通过")
        
        # 导出工作流
        json_str = agent.export_workflow(workflow)
        print(f"✓ 成功导出工作流 (长度: {len(json_str)})")
        
        return True
        
    except Exception as e:
        print(f"✗ 工作流构建器测试失败: {e}")
        return False

async def test_custom_agents():
    """测试自定义Agent"""
    print("\n=== 测试自定义Agent ===")
    
    config = AgentConfig(
        name="TestAgent",
        llm_provider="openai",
        llm_model="gpt-4o",
        api_key="test-key"
    )
    
    agent = BaseAgent(config)
    
    try:
        # 测试自定义文本Agent
        text_agent = agent.create_custom_text_agent(
            name="专业翻译员",
            system_prompt="你是一个专业的中英文翻译员。",
            response_style="professional"
        )
        print(f"✓ 成功创建自定义文本Agent: {text_agent.metadata.name}")
        
        # 注册自定义Agent
        success = agent.register_custom_agent(text_agent)
        print(f"✓ 自定义Agent注册结果: {success}")
        
        # 测试自定义工具Agent
        tool_agent = agent.create_custom_tool_agent(
            name="数据处理专家",
            available_tools=["file_reader", "data_analyzer"],
            tool_selection_strategy="best_match"
        )
        print(f"✓ 成功创建自定义工具Agent: {tool_agent.metadata.name}")
        
        # 测试自定义代码Agent
        code_agent = agent.create_custom_code_agent(
            name="Python分析师",
            language="python",
            allowed_libraries=["pandas", "numpy"],
            code_template="import pandas as pd\nimport numpy as np\n\n"
        )
        print(f"✓ 成功创建自定义代码Agent: {code_agent.metadata.name}")
        
        # 列出可用Agent
        available_agents = agent.list_available_agents()
        print(f"✓ 可用Agent列表: {available_agents}")
        
        # 获取Agent信息
        if "专业翻译员" in available_agents:
            agent_info = agent.get_agent_info("专业翻译员")
            print(f"✓ Agent信息: {agent_info}")
        
        return True
        
    except Exception as e:
        print(f"✗ 自定义Agent测试失败: {e}")
        return False

async def test_workflow_templates():
    """测试工作流模板"""
    print("\n=== 测试工作流模板 ===")
    
    config = AgentConfig(
        name="TestAgent",
        llm_provider="openai",
        llm_model="gpt-4o",
        api_key="test-key"
    )
    
    agent = BaseAgent(config)
    
    try:
        # 测试快速问答工作流
        qa_workflow = agent.create_quick_qa_workflow("智能助手", "你是一个友好的AI助手")
        print(f"✓ 成功创建问答工作流: {qa_workflow.name}")
        
        # 测试翻译工作流
        translation_workflow = agent.create_translation_workflow("中文", "英文")
        print(f"✓ 成功创建翻译工作流: {translation_workflow.name}")
        
        # 获取工作流模板
        templates = agent.get_workflow_templates()
        print(f"✓ 可用工作流模板: {list(templates.keys())}")
        
        return True
        
    except Exception as e:
        print(f"✗ 工作流模板测试失败: {e}")
        return False

async def test_complex_workflow():
    """测试复杂工作流"""
    print("\n=== 测试复杂工作流 ===")
    
    config = AgentConfig(
        name="TestAgent",
        llm_provider="openai",
        llm_model="gpt-4o",
        api_key="test-key"
    )
    
    agent = BaseAgent(config)
    
    try:
        # 创建自定义Agent
        analyzer = agent.create_custom_text_agent(
            name="需求分析师",
            system_prompt="你是一个专业的需求分析师，擅长分析用户的真实需求。",
            response_style="technical"
        )
        agent.register_custom_agent(analyzer)
        
        # 创建复杂工作流
        builder = agent.create_workflow_builder("智能分析流程", "完整的需求分析和处理流程")
        
        # 添加多个步骤
        builder.add_custom_step(
            name="需求分析",
            agent_name="需求分析师",
            instruction="深入分析用户的需求，识别关键要素"
        ).add_text_step(
            name="方案生成",
            instruction="基于需求分析结果，生成解决方案",
            response_style="professional"
        ).add_text_step(
            name="结果汇总",
            instruction="整合分析结果和解决方案，形成最终报告",
            response_style="professional"
        )
        
        # 设置输入输出模式
        builder.set_input_schema({
            "user_input": {"type": "string", "required": True, "description": "用户输入"},
            "context": {"type": "object", "required": False, "description": "上下文信息"}
        })
        
        builder.set_output_schema({
            "analysis": {"type": "string", "description": "需求分析结果"},
            "solution": {"type": "string", "description": "解决方案"},
            "final_report": {"type": "string", "description": "最终报告"}
        })
        
        # 构建工作流
        workflow = builder.build()
        print(f"✓ 成功创建复杂工作流: {workflow.name}")
        print(f"✓ 工作流步骤数: {len(workflow.steps)}")
        
        # 验证工作流
        errors = agent.validate_workflow(workflow)
        if errors:
            print(f"⚠ 工作流验证发现问题: {errors}")
        else:
            print("✓ 复杂工作流验证通过")
        
        # 导出工作流
        json_str = agent.export_workflow(workflow, "test_complex_workflow.json")
        print(f"✓ 成功导出复杂工作流到文件")
        
        # 导入工作流
        imported_workflow = agent.import_workflow(file_path="test_complex_workflow.json")
        print(f"✓ 成功导入工作流: {imported_workflow.name}")
        
        return True
        
    except Exception as e:
        print(f"✗ 复杂工作流测试失败: {e}")
        return False

async def test_agent_validation():
    """测试Agent输入验证"""
    print("\n=== 测试Agent输入验证 ===")
    
    try:
        # 测试CustomTextAgent验证
        text_agent = CustomTextAgent(
            name="测试文本Agent",
            system_prompt="测试提示词"
        )
        
        # 测试有效输入
        valid_input_1 = "这是一个有效的输入"
        valid_input_2 = {"question": "这是一个问题"}
        invalid_input = ""
        
        print(f"✓ 文本Agent验证 '{valid_input_1}': {await text_agent.validate_input(valid_input_1)}")
        print(f"✓ 文本Agent验证 {valid_input_2}: {await text_agent.validate_input(valid_input_2)}")
        print(f"✓ 文本Agent验证 '{invalid_input}': {await text_agent.validate_input(invalid_input)}")
        
        # 测试CustomToolAgent验证
        tool_agent = CustomToolAgent(
            name="测试工具Agent",
            available_tools=["tool1", "tool2"]
        )
        
        valid_task = "执行数据分析任务"
        invalid_task = ""
        
        print(f"✓ 工具Agent验证 '{valid_task}': {await tool_agent.validate_input(valid_task)}")
        print(f"✓ 工具Agent验证 '{invalid_task}': {await tool_agent.validate_input(invalid_task)}")
        
        # 测试CustomCodeAgent验证
        code_agent = CustomCodeAgent(
            name="测试代码Agent",
            language="python"
        )
        
        valid_code_task = "生成数据处理代码"
        invalid_code_task = ""
        
        print(f"✓ 代码Agent验证 '{valid_code_task}': {await code_agent.validate_input(valid_code_task)}")
        print(f"✓ 代码Agent验证 '{invalid_code_task}': {await code_agent.validate_input(invalid_code_task)}")
        
        return True
        
    except Exception as e:
        print(f"✗ Agent验证测试失败: {e}")
        return False

async def main():
    """主测试函数"""
    print("开始测试用户自定义接口实现...")
    
    test_results = []
    
    # 运行各种测试
    test_results.append(await test_workflow_builder())
    test_results.append(await test_custom_agents())
    test_results.append(await test_workflow_templates())
    test_results.append(await test_complex_workflow())
    test_results.append(await test_agent_validation())
    
    # 汇总测试结果
    passed = sum(test_results)
    total = len(test_results)
    
    print(f"\n=== 测试结果汇总 ===")
    print(f"通过测试: {passed}/{total}")
    print(f"成功率: {passed/total*100:.1f}%")
    
    if passed == total:
        print("🎉 所有测试通过！")
    else:
        print("⚠️  部分测试失败，请检查实现")
    
    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)