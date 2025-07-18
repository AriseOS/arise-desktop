#!/usr/bin/env python3
"""
AgentBuilder 复杂测试脚本 - 支持分步测试各个模块
"""

import sys
import os
import asyncio
import logging
import argparse
import json
import tempfile
from typing import Optional, Dict, Any
from pathlib import Path

# 初始化日志
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')

# 添加项目路径
current_dir = Path(__file__).parent.parent.parent  # agentcrafter/
sys.path.insert(0, str(current_dir))  # agentcrafter
sys.path.insert(0, str(current_dir / 'agent_builder'))  # agent_builder
sys.path.insert(0, str(current_dir / 'client' / 'web' / 'backend'))  # backend

from core.agent_builder import AgentBuilder
from core.schemas import LLMConfig, ParsedRequirement, StepDesign
from core.requirement_parser import RequirementParser
from core.agent_designer import AgentDesigner
from core.workflow_builder import WorkflowBuilder
from core.code_generator import CodeGenerator

# 数据库相关导入
try:
    from database import SessionLocal, init_db
    DATABASE_AVAILABLE = True
    print("✅ 数据库模块导入成功")
except ImportError as e:
    print(f"⚠️ 警告: 无法导入数据库模块: {e}")
    print("将在无数据库模式下运行测试")
    DATABASE_AVAILABLE = False
    SessionLocal = None


class AgentBuilderTester:
    """AgentBuilder 测试器 - 支持分步测试"""
    
    def __init__(self, api_key: str, provider: str = "openai", model: str = "gpt-4o", user_id: int = 1):
        self.llm_config = LLMConfig(
            provider=provider,
            model=model,
            api_key=api_key
        )
        self.user_id = user_id  # 测试用户ID
        self.db_session = None
        
        # 初始化数据库会话
        if DATABASE_AVAILABLE:
            try:
                # 确保数据库已初始化
                init_db()
                # 创建数据库会话，和backend使用相同的方式
                self.db_session = SessionLocal()
                print(f"✅ 数据库会话创建成功")
            except Exception as e:
                print(f"⚠️ 数据库会话创建失败: {e}")
                self.db_session = None
        
        # 创建AgentBuilder实例，传入db_session
        self.builder = AgentBuilder(self.llm_config, self.db_session)
        
        print(f"✅ AgentBuilderTester初始化完成")
        print(f"   LLM: {provider}/{model}")
        print(f"   用户ID: {user_id}")
        print(f"   数据库: {'启用' if self.db_session else '禁用'}")
    
    def cleanup(self):
        """清理资源"""
        if self.db_session:
            self.db_session.close()
            print("🧹 数据库会话已关闭")
    
    def __del__(self):
        """析构函数"""
        self.cleanup()
    
    def get_mock_requirement(self, user_description: str) -> ParsedRequirement:
        """获取模拟的需求解析结果"""
        return ParsedRequirement(
            original_text=user_description,
            agent_purpose="智能工作汇报助手，帮助用户自动总结工作内容并生成汇报"
        )
    
    def get_mock_steps(self) -> list:
        """获取模拟的步骤提取结果"""
        return [
            {
                "name": "收集工作数据",
                "description": "从各种来源收集用户的工作数据，包括邮件、日历、任务管理系统等",
                "agent_type": "tool",
                "type_rationale": "需要调用多个API和工具来收集数据",
                "tool_implementation": {
                    "approach": "combine_existing",
                    "existing_tools": ["email_tool", "calendar_tool", "task_tool"],
                    "new_tool_requirements": "",
                    "cost_analysis": "medium - 需要组合多个现有工具"
                },
                "config": {
                    "key_parameters": "data_sources=['email', 'calendar', 'tasks']",
                    "expected_input": "用户授权和数据源配置",
                    "expected_output": "结构化的工作数据"
                }
            },
            {
                "name": "分析工作内容",
                "description": "分析收集到的工作数据，提取关键信息和重要事件",
                "agent_type": "text",
                "type_rationale": "文本分析和信息提取是text agent的核心能力",
                "tool_implementation": {
                    "approach": "reuse_existing",
                    "existing_tools": [],
                    "new_tool_requirements": "",
                    "cost_analysis": "low - 直接使用text agent内置能力"
                },
                "config": {
                    "key_parameters": "analysis_depth='detailed', focus_areas=['achievements', 'challenges', 'progress']",
                    "expected_input": "结构化的工作数据",
                    "expected_output": "分析后的工作摘要"
                }
            },
            {
                "name": "生成工作汇报",
                "description": "基于分析结果生成专业的工作汇报文档",
                "agent_type": "text",
                "type_rationale": "文档生成是text agent的强项",
                "tool_implementation": {
                    "approach": "reuse_existing",
                    "existing_tools": [],
                    "new_tool_requirements": "",
                    "cost_analysis": "low - 直接使用text agent内置能力"
                },
                "config": {
                    "key_parameters": "format='professional', style='concise', sections=['summary', 'achievements', 'challenges', 'next_steps']",
                    "expected_input": "分析后的工作摘要",
                    "expected_output": "格式化的工作汇报文档"
                }
            }
        ]
    
    def get_mock_step_designs(self) -> list:
        """获取模拟的StepDesign对象"""
        steps = self.get_mock_steps()
        step_designs = []
        for i, step in enumerate(steps):
            step_design = StepDesign(
                step_id=f"step_{i+1}",
                name=step['name'],
                description=step['description'],
                agent_type=step['agent_type'],
                agent_config=step['config']
            )
            step_designs.append(step_design)
        return step_designs
    
    def get_mock_agent_types(self) -> dict:
        """获取模拟的Agent类型判断结果"""
        return {
            "step_1": "tool",
            "step_2": "text", 
            "step_3": "text"
        }
    
    def get_mock_step_agents(self) -> list:
        """获取模拟的StepAgent生成结果"""
        return [
            {
                "step_id": "step_1",
                "generation_type": "tool_combination",
                "base_agent_type": "tool",
                "agent_name": "WorkDataCollector",
                "agent_description": "专门用于收集工作数据的工具组合Agent",
                "required_tools": ["email_tool", "calendar_tool", "task_tool"],
                "combination_strategy": "parallel_execution",
                "interface_specification": {
                    "input_schema": "用户授权和数据源配置",
                    "output_schema": "结构化的工作数据",
                    "error_handling": "优雅处理API调用失败"
                }
            },
            {
                "step_id": "step_2",
                "generation_type": "basic_config",
                "base_agent_type": "text",
                "agent_instruction": "分析工作数据，提取关键信息和重要事件",
                "response_style": "analytical",
                "expected_behavior": "Execute step: 分析工作内容"
            },
            {
                "step_id": "step_3", 
                "generation_type": "basic_config",
                "base_agent_type": "text",
                "agent_instruction": "基于分析结果生成专业的工作汇报文档",
                "response_style": "professional",
                "expected_behavior": "Execute step: 生成工作汇报"
            }
        ]
    
    def get_mock_workflow(self) -> dict:
        """获取模拟的工作流"""
        return {
            "metadata": {
                "name": "工作汇报自动化工作流",
                "description": "自动收集、分析和生成工作汇报的智能工作流",
                "version": "1.0",
                "created_at": "2024-01-01T00:00:00"
            },
            "steps": [
                {
                    "id": "step_1",
                    "name": "收集工作数据",
                    "agent_type": "tool",
                    "agent_instruction": "收集工作数据",
                    "tools": {
                        "allowed": ["email_tool", "calendar_tool", "task_tool"],
                        "required": ["email_tool"]
                    },
                    "input_variables": ["user_auth", "data_sources"],
                    "output_variables": ["work_data"]
                },
                {
                    "id": "step_2", 
                    "name": "分析工作内容",
                    "agent_type": "text",
                    "agent_instruction": "分析工作数据，提取关键信息",
                    "input_variables": ["work_data"],
                    "output_variables": ["work_summary"]
                },
                {
                    "id": "step_3",
                    "name": "生成工作汇报", 
                    "agent_type": "text",
                    "agent_instruction": "生成专业的工作汇报文档",
                    "input_variables": ["work_summary"],
                    "output_variables": ["report"]
                }
            ],
            "data_flow": {
                "start": "step_1",
                "transitions": [
                    {"from": "step_1", "to": "step_2"},
                    {"from": "step_2", "to": "step_3"}
                ]
            },
            "complexity_score": "medium",
            "estimated_execution_time": 30
        }
    
    async def test_all_steps(self, user_description: str, output_dir: str = "./output"):
        """测试完整的构建流程"""
        print("🚀 开始完整构建流程测试")
        print(f"用户描述: {user_description}")
        print(f"用户ID: {self.user_id}")
        print("=" * 60)
        
        try:
            result = await self.builder.build_agent_from_description(
                user_id=self.user_id,
                user_description=user_description,
                output_dir=output_dir
            )
            
            print("✅ 完整构建流程成功")
            print(f"构建结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
            return result
            
        except Exception as e:
            print(f"❌ 完整构建流程失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def test_step_1_requirement_parsing(self, user_description: str):
        """测试步骤1: 需求解析"""
        print("📝 测试步骤1: 需求解析")
        print(f"用户描述: {user_description}")
        print("-" * 40)
        
        try:
            parser = RequirementParser(self.llm_config)
            
            # 测试需求解析
            requirement = await parser.parse_requirements(user_description)
            print(f"✅ 需求解析成功")
            print(f"Agent目的: {requirement.agent_purpose}")
            print(f"原始文本: {requirement.original_text}")
            
            return requirement
            
        except Exception as e:
            print(f"❌ 需求解析失败: {e}")
            return None
    
    async def test_step_2_steps_extraction(self, user_description: str, agent_purpose: str):
        """测试步骤2: 步骤提取"""
        print("🔍 测试步骤2: 步骤提取")
        print(f"Agent目的: {agent_purpose}")
        print("-" * 40)
        
        try:
            parser = RequirementParser(self.llm_config)
            
            # 测试步骤提取
            steps = await parser.extract_steps(user_description, agent_purpose)
            print(f"✅ 步骤提取成功，共提取 {len(steps)} 个步骤")
            
            for i, step in enumerate(steps, 1):
                print(f"步骤 {i}: {step.get('name', 'Unknown')}")
                print(f"  描述: {step.get('description', 'No description')}")
                print(f"  Agent类型: {step.get('agent_type', 'Unknown')}")
                print(f"  工具方案: {step.get('tool_implementation', {}).get('approach', 'Unknown')}")
                print()
            
            return steps
            
        except Exception as e:
            print(f"❌ 步骤提取失败: {e}")
            return None
    
    async def test_step_3_agent_type_judgment(self, steps: list):
        """测试步骤3: Agent类型判断"""
        print("🏗️ 测试步骤3: Agent类型判断")
        print(f"输入步骤数: {len(steps)}")
        print("-" * 40)
        
        try:
            # 转换为StepDesign对象
            step_designs = []
            for i, step in enumerate(steps):
                step_design = StepDesign(
                    step_id=f"step_{i+1}",
                    name=step.get('name', f'步骤{i+1}'),
                    description=step.get('description', ''),
                    agent_type=step.get('agent_type', 'text'),
                    agent_config=step.get('config', {})
                )
                step_designs.append(step_design)
            
            designer = AgentDesigner(self.llm_config)
            
            # 测试Agent类型判断
            agent_types = await designer.judge_agent_types(step_designs)
            print(f"✅ Agent类型判断成功")
            
            for step_key, agent_type in agent_types.items():
                print(f"{step_key}: {agent_type}")
            
            return agent_types
            
        except Exception as e:
            print(f"❌ Agent类型判断失败: {e}")
            return None
    
    async def test_step_4_agent_generation(self, steps: list):
        """测试步骤4: StepAgent生成"""
        print("🤖 测试步骤4: StepAgent生成")
        print(f"输入步骤数: {len(steps)}")
        print("-" * 40)
        
        try:
            # 转换为StepDesign对象
            step_designs = []
            for i, step in enumerate(steps):
                step_design = StepDesign(
                    step_id=f"step_{i+1}",
                    name=step.get('name', f'步骤{i+1}'),
                    description=step.get('description', ''),
                    agent_type=step.get('agent_type', 'text'),
                    agent_config=step.get('config', {})
                )
                step_designs.append(step_design)
            
            designer = AgentDesigner(self.llm_config)
            
            # 测试StepAgent生成
            step_agents = await designer.generate_step_agents(step_designs)
            print(f"✅ StepAgent生成成功，共生成 {len(step_agents)} 个Agent规格")
            
            for i, agent_spec in enumerate(step_agents, 1):
                print(f"Agent规格 {i}:")
                print(f"  生成类型: {agent_spec.get('generation_type', 'Unknown')}")
                print(f"  基础类型: {agent_spec.get('base_agent_type', 'Unknown')}")
                if agent_spec.get('agent_name'):
                    print(f"  Agent名称: {agent_spec['agent_name']}")
                print()
            
            return step_agents
            
        except Exception as e:
            print(f"❌ StepAgent生成失败: {e}")
            return None
    
    async def test_step_5_workflow_building(self, steps: list, step_agents: list):
        """测试步骤5: 工作流构建"""
        print("⚙️ 测试步骤5: 工作流构建")
        print(f"输入步骤数: {len(steps)}, Agent规格数: {len(step_agents)}")
        print("-" * 40)
        
        try:
            # 转换为StepDesign对象
            step_designs = []
            for i, step in enumerate(steps):
                step_design = StepDesign(
                    step_id=f"step_{i+1}",
                    name=step.get('name', f'步骤{i+1}'),
                    description=step.get('description', ''),
                    agent_type=step.get('agent_type', 'text'),
                    agent_config=step.get('config', {})
                )
                step_designs.append(step_design)
            
            workflow_builder = WorkflowBuilder()
            
            # 测试工作流构建
            workflow = await workflow_builder.build_workflow(step_designs, step_agents)
            print(f"✅ 工作流构建成功")
            print(f"工作流名称: {workflow.get('metadata', {}).get('name', 'Unknown')}")
            print(f"工作流步骤数: {len(workflow.get('steps', []))}")
            
            return workflow
            
        except Exception as e:
            print(f"❌ 工作流构建失败: {e}")
            return None
    
    async def test_step_6_workflow_registration(self, workflow: dict):
        """测试步骤6: 工作流注册"""
        print("📋 测试步骤6: 工作流注册")
        print(f"工作流名称: {workflow.get('metadata', {}).get('name', 'Unknown')}")
        print("-" * 40)
        
        try:
            workflow_builder = WorkflowBuilder()
            
            # 测试工作流注册
            registration_result = await workflow_builder.register_workflow(workflow)
            print(f"✅ 工作流注册成功")
            print(f"注册结果: {registration_result}")
            
            return registration_result
            
        except Exception as e:
            print(f"❌ 工作流注册失败: {e}")
            return None
    
    async def test_step_7_code_generation(self, workflow: dict, step_agents: list):
        """测试步骤7: 代码生成"""
        print("💻 测试步骤7: 代码生成")
        print(f"工作流步骤数: {len(workflow.get('steps', []))}, Agent规格数: {len(step_agents)}")
        print("-" * 40)
        
        try:
            code_generator = CodeGenerator(self.llm_config)
            
            # 测试代码生成
            generated_code = await code_generator.generate_agent_code(workflow, step_agents)
            print(f"✅ 代码生成成功")
            print(f"Agent名称: {generated_code.metadata.name}")
            print(f"Agent描述: {generated_code.metadata.description}")
            print(f"Agent能力: {generated_code.metadata.capabilities}")
            print(f"成本分析: {generated_code.metadata.cost_analysis}")
            print(f"代码长度: {len(generated_code.main_agent_code)} 字符")
            
            return generated_code
            
        except Exception as e:
            print(f"❌ 代码生成失败: {e}")
            return None
    
    async def test_individual_step(self, step: int, user_description: str):
        """测试单个步骤 - 使用 mock 数据进行独立测试"""
        print(f"🎯 单步测试模式 - 步骤 {step}")
        print("📦 使用 mock 数据进行独立测试")
        print("=" * 60)
        
        if step == 1:
            return await self.test_step_1_requirement_parsing(user_description)
        elif step == 2:
            # 使用 mock 需求解析结果
            mock_requirement = self.get_mock_requirement(user_description)
            print(f"📦 使用 mock 需求解析结果: {mock_requirement.agent_purpose}")
            return await self.test_step_2_steps_extraction(user_description, mock_requirement.agent_purpose)
        elif step == 3:
            # 使用 mock 步骤提取结果
            mock_steps = self.get_mock_steps()
            print(f"📦 使用 mock 步骤提取结果: {len(mock_steps)} 个步骤")
            return await self.test_step_3_agent_type_judgment(mock_steps)
        elif step == 4:
            # 使用 mock 步骤提取结果
            mock_steps = self.get_mock_steps()
            print(f"📦 使用 mock 步骤提取结果: {len(mock_steps)} 个步骤")
            return await self.test_step_4_agent_generation(mock_steps)
        elif step == 5:
            # 使用 mock 步骤和 StepAgent 数据
            mock_steps = self.get_mock_steps()
            mock_step_agents = self.get_mock_step_agents()
            print(f"📦 使用 mock 数据: {len(mock_steps)} 个步骤, {len(mock_step_agents)} 个Agent规格")
            return await self.test_step_5_workflow_building(mock_steps, mock_step_agents)
        elif step == 6:
            # 使用 mock 工作流数据
            mock_workflow = self.get_mock_workflow()
            print(f"📦 使用 mock 工作流: {mock_workflow['metadata']['name']}")
            return await self.test_step_6_workflow_registration(mock_workflow)
        elif step == 7:
            # 使用 mock 工作流和 StepAgent 数据
            mock_workflow = self.get_mock_workflow()
            mock_step_agents = self.get_mock_step_agents()
            print(f"📦 使用 mock 数据: 工作流 + {len(mock_step_agents)} 个Agent规格")
            return await self.test_step_7_code_generation(mock_workflow, mock_step_agents)
        else:
            print(f"❌ 无效的步骤编号: {step}")
            return None


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="AgentBuilder 复杂测试脚本")
    parser.add_argument("--step", type=int, help="测试特定步骤 (1-7)")
    parser.add_argument("--description", "-d", required=True, help="用户需求描述")
    parser.add_argument("--output", "-o", default="./output", help="输出目录")
    parser.add_argument("--provider", default="openai", help="LLM提供商")
    parser.add_argument("--model", default="gpt-4o", help="LLM模型")
    parser.add_argument("--api-key", help="API密钥 (可通过OPENAI_API_KEY环境变量设置)")
    parser.add_argument("--user-id", type=int, default=1, help="测试用户ID (默认: 1)")
    
    args = parser.parse_args()
    
    # 获取API密钥
    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ 错误: 未设置API密钥")
        print("请通过 --api-key 参数或 OPENAI_API_KEY 环境变量设置")
        return
    
    # 创建测试器
    tester = AgentBuilderTester(api_key, args.provider, args.model, args.user_id)
    
    print("🧪 AgentBuilder 复杂测试脚本")
    print(f"提供商: {args.provider}")
    print(f"模型: {args.model}")
    print(f"用户ID: {args.user_id}")
    print(f"用户描述: {args.description}")
    print("=" * 60)
    
    try:
        if args.step:
            # 单步测试
            await tester.test_individual_step(args.step, args.description)
        else:
            # 完整测试
            await tester.test_all_steps(args.description, args.output)
            
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 确保资源被清理
        tester.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
