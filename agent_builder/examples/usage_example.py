#!/usr/bin/env python3
"""
AgentBuilder 使用示例
演示如何使用AgentBuilder从自然语言描述生成完整的Agent
"""

import asyncio
import os
import sys

# 添加路径以便导入AgentBuilder
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.schemas import LLMConfig
from core.agent_builder import AgentBuilder, build_agent


async def example_1_simple_qa_agent():
    """示例1: 创建简单问答Agent"""
    print("=== 示例1: 简单问答Agent ===")
    
    user_description = """
    我需要一个智能问答助手，能够：
    1. 理解用户的问题
    2. 生成友好、准确的回答
    3. 保持专业但亲切的语调
    """
    
    # 使用便捷函数创建Agent
    result = await build_agent(
        user_description=user_description,
        llm_provider="openai",
        llm_model="gpt-4o",
        api_key="your-api-key-here",  # 请替换为实际的API密钥
        output_dir="./generated_agents/qa_agent",
        agent_name="intelligent_qa_assistant"
    )
    
    if result["success"]:
        print("✅ Agent创建成功！")
        print(f"📁 主文件: {result['files']['agent_file']}")
        print(f"📋 功能: {', '.join(result['agent_info']['capabilities'])}")
    else:
        print("❌ Agent创建失败")
    
    return result


async def example_2_data_analysis_agent():
    """示例2: 创建数据分析Agent"""
    print("\n=== 示例2: 数据分析Agent ===")
    
    user_description = """
    我需要一个数据分析助手，功能包括：
    1. 理解用户的数据分析需求
    2. 使用Python代码进行数据处理
    3. 生成数据可视化图表
    4. 提供分析结论和建议
    """
    
    # 使用AgentBuilder类
    llm_config = LLMConfig(
        provider="openai",
        model="gpt-4o",
        api_key="your-api-key-here"  # 请替换为实际的API密钥
    )
    
    builder = AgentBuilder(llm_config)
    
    result = await builder.build_agent_from_description(
        user_description=user_description,
        output_dir="./generated_agents/data_analysis_agent",
        agent_name="data_analysis_assistant"
    )
    
    if result["success"]:
        print("✅ 数据分析Agent创建成功！")
        summary = builder.get_build_summary(result)
        print(summary)
    else:
        print("❌ 数据分析Agent创建失败")
    
    return result


async def example_3_translation_agent():
    """示例3: 创建翻译Agent"""
    print("\n=== 示例3: 翻译Agent ===")
    
    user_description = """
    创建一个专业翻译Agent，具备以下能力：
    1. 检测输入文本的语言
    2. 将文本翻译成目标语言（中英互译）
    3. 保持原文的语调和风格
    4. 对专业术语进行准确翻译
    5. 提供翻译质量评估
    """
    
    result = await build_agent(
        user_description=user_description,
        llm_provider="anthropic",  # 使用不同的LLM提供商
        llm_model="claude-3-sonnet-20240229",
        api_key="your-anthropic-api-key-here",
        output_dir="./generated_agents/translation_agent",
        agent_name="professional_translator"
    )
    
    return result


async def example_4_complex_workflow_agent():
    """示例4: 创建复杂工作流Agent"""
    print("\n=== 示例4: 复杂工作流Agent ===")
    
    user_description = """
    我需要一个内容创作助手，工作流程如下：
    1. 分析用户输入的主题和要求
    2. 如果需要，搜索相关背景信息
    3. 生成内容大纲
    4. 编写详细内容
    5. 检查内容质量并优化
    6. 如果是技术内容，生成示例代码
    7. 最终整理和格式化输出
    """
    
    llm_config = LLMConfig(
        provider="openai",
        model="gpt-4o",
        api_key="your-api-key-here"
    )
    
    builder = AgentBuilder(llm_config)
    
    result = await builder.build_agent_from_description(
        user_description=user_description,
        output_dir="./generated_agents/content_creator_agent",
        agent_name="content_creation_assistant"
    )
    
    if result["success"]:
        print("✅ 内容创作Agent创建成功！")
        print(f"📊 工作流复杂度: {result['workflow_info']['steps_count']}步")
        print(f"🤖 使用的Agent类型: {', '.join(result['workflow_info']['agent_types_used'])}")
        print(f"💰 实现成本: {result['agent_info']['cost_analysis']}")
    
    return result


async def example_5_testing_generated_agent():
    """示例5: 测试生成的Agent"""
    print("\n=== 示例5: 测试生成的Agent ===")
    
    # 首先生成一个简单的Agent
    user_description = "创建一个能够回答编程问题的助手"
    
    result = await build_agent(
        user_description=user_description,
        llm_provider="openai",
        llm_model="gpt-4o",
        api_key="your-api-key-here",
        output_dir="./generated_agents/test_agent",
        agent_name="programming_helper"
    )
    
    if result["success"]:
        agent_file = result['files']['agent_file']
        print(f"✅ Agent生成成功: {agent_file}")
        
        # 检查代码质量
        code_quality = result['code_quality']
        print(f"🔍 代码质量检查:")
        print(f"   语法正确: {'✅' if code_quality['syntax_valid'] else '❌'}")
        print(f"   导入正确: {'✅' if code_quality['imports_valid'] else '❌'}")
        print(f"   可执行性: {'✅' if code_quality['execution_test'] else '❌'}")
        
        if code_quality['errors']:
            print(f"❌ 发现错误: {', '.join(code_quality['errors'])}")
        
        if code_quality['warnings']:
            print(f"⚠️  警告: {', '.join(code_quality['warnings'])}")
        
        # 显示生成的文件
        print(f"\n📁 生成的文件:")
        for file_type, file_path in result['files'].items():
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                print(f"   {file_type}: {os.path.basename(file_path)} ({file_size} bytes)")
    
    return result


async def example_6_batch_generation():
    """示例6: 批量生成多个Agent"""
    print("\n=== 示例6: 批量生成多个Agent ===")
    
    agents_to_create = [
        {
            "name": "weather_assistant",
            "description": "创建一个天气查询助手，能够查询和分析天气信息"
        },
        {
            "name": "math_tutor",
            "description": "创建一个数学辅导老师，能够解答数学问题并提供详细解释"
        },
        {
            "name": "code_reviewer",
            "description": "创建一个代码审查助手，能够分析代码质量并提供改进建议"
        }
    ]
    
    results = []
    
    for i, agent_spec in enumerate(agents_to_create):
        print(f"\n正在创建Agent {i+1}/{len(agents_to_create)}: {agent_spec['name']}")
        
        try:
            result = await build_agent(
                user_description=agent_spec['description'],
                llm_provider="openai",
                llm_model="gpt-4o",
                api_key="your-api-key-here",
                output_dir=f"./generated_agents/batch_{agent_spec['name']}",
                agent_name=agent_spec['name']
            )
            
            if result["success"]:
                print(f"✅ {agent_spec['name']} 创建成功")
                results.append(result)
            else:
                print(f"❌ {agent_spec['name']} 创建失败")
                
        except Exception as e:
            print(f"❌ {agent_spec['name']} 创建出错: {e}")
    
    print(f"\n📊 批量创建完成: {len(results)}/{len(agents_to_create)} 个Agent创建成功")
    
    return results


async def main():
    """主函数 - 运行所有示例"""
    print("🚀 AgentBuilder 使用示例")
    print("=" * 50)
    
    try:
        # 运行所有示例
        await example_1_simple_qa_agent()
        await example_2_data_analysis_agent()
        await example_3_translation_agent()
        await example_4_complex_workflow_agent()
        await example_5_testing_generated_agent()
        await example_6_batch_generation()
        
        print("\n🎉 所有示例运行完成！")
        print("\n💡 提示:")
        print("1. 请将示例中的API密钥替换为真实的密钥")
        print("2. 生成的Agent文件位于 ./generated_agents/ 目录下")
        print("3. 每个Agent都包含完整的使用说明和示例代码")
        print("4. 可以直接运行生成的Python文件来测试Agent")
        
    except Exception as e:
        print(f"❌ 示例运行失败: {e}")
        raise


if __name__ == "__main__":
    # 确保输出目录存在
    os.makedirs("./generated_agents", exist_ok=True)
    
    # 运行示例
    asyncio.run(main())