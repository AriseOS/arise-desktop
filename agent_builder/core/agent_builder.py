"""
AgentBuilder - 主控制器，协调整个Agent生成过程
"""

import os
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from .schemas import GeneratedCode, LLMConfig
from .requirement_parser import RequirementParser
from .agent_designer import AgentDesigner
from .workflow_builder import WorkflowBuilder
from .code_generator import CodeGenerator

logger = logging.getLogger(__name__)


class AgentBuilder:
    """AgentBuilder主控制器 - 协调整个Agent生成过程"""
    
    def __init__(self, llm_config: LLMConfig):
        """
        初始化AgentBuilder
        
        Args:
            llm_config: LLM配置
        """
        self.llm_config = llm_config
        
        # 初始化核心组件
        self.requirement_parser = RequirementParser(llm_config)
        self.agent_designer = AgentDesigner(llm_config)
        self.workflow_builder = WorkflowBuilder()
        self.code_generator = CodeGenerator(llm_config)
        
        logger.info(f"AgentBuilder初始化完成，使用LLM: {llm_config.provider}/{llm_config.model}")
    
    async def build_agent_from_description(self, 
                                         user_description: str,
                                         output_dir: str = "./generated_agents",
                                         agent_name: Optional[str] = None) -> Dict[str, Any]:
        """
        从自然语言描述构建Agent - 基于Context Engineering优化的完整流程
        
        Args:
            user_description: 用户的自然语言需求描述
            output_dir: 输出目录
            agent_name: 可选的Agent名称，如果不提供会自动生成
            
        Returns:
            Dict包含生成结果和文件路径
        """
        
        logger.info("开始从自然语言描述构建Agent")
        logger.info(f"用户描述: {user_description[:100]}...")
        
        try:
            # 1. 智能需求解析（已实现）
            logger.info("步骤1: 解析用户需求")
            requirement = await self.requirement_parser.parse_requirements(user_description)
            logger.info(f"解析完成 - Agent目的: {requirement.agent_purpose}")
            
            # 2. 基于工具能力的步骤提取（已实现）
            logger.info("步骤2: 提取执行步骤")
            steps = await self.requirement_parser.extract_steps(
                user_description, requirement.agent_purpose
            )
            logger.info(f"步骤提取完成 - 共{len(steps)}个步骤")
            
            # 3. 成本效益优化的Agent类型判断（已实现）
            logger.info("步骤3: 判断Agent类型")
            agent_types = await self.agent_designer.judge_agent_types(steps)
            logger.info(f"Agent类型判断完成: {agent_types}")
            
            # 4. 按需生成StepAgent（已实现）
            logger.info("步骤4: 生成StepAgent规格")
            step_agents = await self.agent_designer.generate_step_agents(steps)
            logger.info(f"StepAgent生成完成 - 共{len(step_agents)}个Agent规格")
            
            # 5. 组合Workflow（已实现）
            logger.info("步骤5: 构建工作流")
            workflow = await self.workflow_builder.build_workflow(steps, step_agents)
            logger.info(f"工作流构建完成 - {workflow['metadata']['name']}")
            
            # 6. 注册Workflow（已实现）
            logger.info("步骤6: 注册工作流")
            registration_result = await self.workflow_builder.register_workflow(workflow)
            logger.info(f"工作流注册完成 - ID: {registration_result['workflow_id']}")
            
            # 7. 生成BaseAgent兼容代码（已实现）
            logger.info("步骤7: 生成Python代码")
            generated_code = await self.code_generator.generate_agent_code(workflow, step_agents)
            logger.info("代码生成完成")
            
            # 8. 保存生成的文件
            logger.info("步骤8: 保存生成的文件")
            file_paths = await self._save_generated_files(
                generated_code, workflow, steps, output_dir, agent_name
            )
            logger.info(f"文件保存完成 - 主文件: {file_paths['agent_file']}")
            
            # 9. 测试生成的代码
            logger.info("步骤9: 测试生成的代码")
            test_result = self._test_generated_agent(file_paths['agent_file'])
            logger.info(f"代码测试完成 - 语法有效: {test_result['syntax_valid']}")
            
            # 10. 生成完整的构建报告
            build_report = self._generate_build_report(
                requirement, steps, workflow, generated_code, file_paths, test_result
            )
            
            logger.info("Agent构建完成！")
            return build_report
            
        except Exception as e:
            logger.error(f"Agent构建失败: {str(e)}")
            raise AgentBuildError(f"构建Agent时发生错误: {str(e)}") from e
    
    async def _save_generated_files(self, 
                                  generated_code: GeneratedCode,
                                  workflow: Dict[str, Any],
                                  steps: list,
                                  output_dir: str,
                                  agent_name: Optional[str]) -> Dict[str, str]:
        """保存所有生成的文件"""
        
        # 确定文件名
        if agent_name:
            base_name = agent_name.lower().replace(' ', '_').replace('-', '_')
        else:
            base_name = generated_code.metadata.name.lower().replace(' ', '_').replace('-', '_')
        
        # 确保基础名称是有效的Python标识符
        if not base_name.replace('_', '').isalnum():
            base_name = f"generated_agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 文件路径
        file_paths = {
            'agent_file': os.path.join(output_dir, f"{base_name}.py"),
            'workflow_file': os.path.join(output_dir, f"{base_name}_workflow.yaml"),
            'metadata_file': os.path.join(output_dir, f"{base_name}_metadata.json"),
            'readme_file': os.path.join(output_dir, f"{base_name}_README.md"),
            'requirements_file': os.path.join(output_dir, f"{base_name}_requirements.txt")
        }
        
        # 保存主Agent代码
        with open(file_paths['agent_file'], 'w', encoding='utf-8') as f:
            f.write(generated_code.main_agent_code)
        
        # 保存工作流配置
        with open(file_paths['workflow_file'], 'w', encoding='utf-8') as f:
            f.write(generated_code.workflow_config)
        
        # 保存元数据
        metadata_dict = {
            "name": generated_code.metadata.name,
            "description": generated_code.metadata.description,
            "capabilities": generated_code.metadata.capabilities,
            "interface": generated_code.metadata.interface,
            "cost_analysis": generated_code.metadata.cost_analysis,
            "created_at": generated_code.metadata.created_at.isoformat(),
            "steps_count": len(steps),
            "workflow_complexity": workflow.get("complexity_score", "unknown")
        }
        
        with open(file_paths['metadata_file'], 'w', encoding='utf-8') as f:
            json.dump(metadata_dict, f, indent=2, ensure_ascii=False)
        
        # 生成README文档
        readme_content = self._generate_readme(generated_code, workflow, steps, base_name)
        with open(file_paths['readme_file'], 'w', encoding='utf-8') as f:
            f.write(readme_content)
        
        # 生成requirements.txt
        requirements_content = self._generate_requirements()
        with open(file_paths['requirements_file'], 'w', encoding='utf-8') as f:
            f.write(requirements_content)
        
        return file_paths
    
    def _generate_readme(self, 
                        generated_code: GeneratedCode,
                        workflow: Dict[str, Any],
                        steps: list,
                        base_name: str) -> str:
        """生成README文档"""
        
        steps_list = ""
        for i, step in enumerate(steps):
            steps_list += f"{i+1}. **{step.name}** ({step.agent_type}): {step.description}\n"
        
        capabilities_list = ""
        for capability in generated_code.metadata.capabilities:
            capabilities_list += f"- {capability}\n"
        
        return f"""# {generated_code.metadata.name}

{generated_code.metadata.description}

## 概述

这是一个由AgentBuilder自动生成的智能Agent，基于BaseAgent框架构建。

## 功能特性

{capabilities_list}

## 工作流步骤

{steps_list}

## 安装和使用

### 1. 安装依赖

```bash
pip install -r {base_name}_requirements.txt
```

### 2. 配置API密钥

编辑代码中的API密钥配置：

```python
config = AgentConfig(
    name="{generated_code.metadata.name}",
    llm_provider="{self.llm_config.provider}",
    llm_model="{self.llm_config.model}",
    api_key="your-api-key-here"  # 请替换为实际的API密钥
)
```

### 3. 运行Agent

```bash
python {base_name}.py
```

### 4. 编程方式使用

```python
import asyncio
from {base_name} import GeneratedAgent
from base_app.base_agent.core.schemas import AgentConfig

async def main():
    config = AgentConfig(
        name="{generated_code.metadata.name}",
        llm_provider="{self.llm_config.provider}",
        api_key="your-api-key"
    )
    
    agent = GeneratedAgent(config)
    await agent.initialize()
    
    result = await agent.execute("你的输入")
    print(result.data)

if __name__ == "__main__":
    asyncio.run(main())
```

## 实现成本分析

{generated_code.metadata.cost_analysis}

## 技术架构

- **基础框架**: BaseAgent
- **工作流引擎**: Agent Workflow Engine
- **LLM提供商**: {self.llm_config.provider}
- **模型**: {self.llm_config.model}

## 文件说明

- `{base_name}.py` - 主Agent实现代码
- `{base_name}_workflow.yaml` - 工作流配置文件
- `{base_name}_metadata.json` - Agent元数据
- `{base_name}_requirements.txt` - Python依赖包
- `{base_name}_README.md` - 本说明文档

## 生成信息

- **生成时间**: {generated_code.created_at.strftime('%Y-%m-%d %H:%M:%S')}
- **AgentBuilder版本**: 1.0.0
- **工作流复杂度**: {workflow.get('complexity_score', '未评估')}

## 支持与反馈

如有问题或建议，请联系AgentBuilder开发团队。
"""
    
    def _generate_requirements(self) -> str:
        """生成requirements.txt内容"""
        
        return """# AgentBuilder生成的Agent依赖包
# 请根据实际需要调整版本号

# BaseAgent核心依赖
pydantic>=2.0.0
pyyaml>=6.0
asyncio
typing-extensions>=4.0.0

# LLM提供商依赖
openai>=1.0.0
anthropic>=0.3.0

# 常用工具依赖  
requests>=2.28.0
aiohttp>=3.8.0

# 数据处理依赖
pandas>=1.5.0
numpy>=1.21.0

# 其他常用依赖
python-dotenv>=0.19.0
loguru>=0.6.0
"""
    
    def _test_generated_agent(self, agent_file_path: str) -> Dict[str, Any]:
        """测试生成的Agent代码"""
        
        return self.code_generator.test_generated_code(agent_file_path)
    
    def _generate_build_report(self,
                             requirement,
                             steps,
                             workflow,
                             generated_code,
                             file_paths,
                             test_result) -> Dict[str, Any]:
        """生成完整的构建报告"""
        
        return {
            "success": True,
            "agent_info": {
                "name": generated_code.metadata.name,
                "description": generated_code.metadata.description,
                "capabilities": generated_code.metadata.capabilities,
                "cost_analysis": generated_code.metadata.cost_analysis
            },
            "build_summary": {
                "steps_count": len(steps),
                "workflow_complexity": workflow.get("complexity_score", "unknown"),
                "estimated_execution_time": workflow.get("estimated_execution_time", 0),
                "generated_files_count": len(file_paths)
            },
            "files": file_paths,
            "code_quality": {
                "syntax_valid": test_result.get("syntax_valid", False),
                "imports_valid": test_result.get("imports_valid", False),
                "execution_test": test_result.get("execution_test", False),
                "errors": test_result.get("errors", []),
                "warnings": test_result.get("warnings", [])
            },
            "workflow_info": {
                "name": workflow["metadata"]["name"],
                "steps_count": len(workflow.get("steps", [])),
                "has_conditions": any("condition" in step for step in workflow.get("steps", [])),
                "agent_types_used": list(set(step.get("agent_type", "unknown") for step in workflow.get("steps", [])))
            },
            "generation_details": {
                "llm_provider": self.llm_config.provider,
                "llm_model": self.llm_config.model,
                "created_at": generated_code.created_at.isoformat(),
                "builder_version": "1.0.0"
            }
        }
    
    def get_build_summary(self, build_report: Dict[str, Any]) -> str:
        """获取构建摘要的文本描述"""
        
        if not build_report.get("success"):
            return "Agent构建失败"
        
        agent_info = build_report["agent_info"]
        build_summary = build_report["build_summary"]
        
        summary = f"""
🎉 Agent构建成功！

📋 Agent信息:
   名称: {agent_info['name']}
   描述: {agent_info['description']}
   能力: {len(agent_info['capabilities'])}项功能

🔧 构建摘要:
   工作流步骤: {build_summary['steps_count']}个
   复杂度: {build_summary['workflow_complexity']}
   预估执行时间: {build_summary['estimated_execution_time']}秒
   生成文件: {build_summary['generated_files_count']}个

📁 主要文件:
   - Agent代码: {os.path.basename(build_report['files']['agent_file'])}
   - 工作流配置: {os.path.basename(build_report['files']['workflow_file'])}
   - 使用说明: {os.path.basename(build_report['files']['readme_file'])}

✅ 代码质量:
   语法检查: {'通过' if build_report['code_quality']['syntax_valid'] else '失败'}
   导入检查: {'通过' if build_report['code_quality']['imports_valid'] else '失败'}
   
💡 成本分析: {agent_info['cost_analysis']}
"""
        
        return summary.strip()


class AgentBuildError(Exception):
    """Agent构建错误"""
    pass


# 便捷函数
async def build_agent(user_description: str,
                     llm_provider: str = "openai",
                     llm_model: str = "gpt-4o",
                     api_key: str = "",
                     output_dir: str = "./generated_agents",
                     agent_name: Optional[str] = None) -> Dict[str, Any]:
    """
    便捷的Agent构建函数
    
    Args:
        user_description: 用户需求描述
        llm_provider: LLM提供商
        llm_model: LLM模型
        api_key: API密钥
        output_dir: 输出目录
        agent_name: Agent名称
    
    Returns:
        构建报告
    """
    
    llm_config = LLMConfig(
        provider=llm_provider,
        model=llm_model,
        api_key=api_key
    )
    
    builder = AgentBuilder(llm_config)
    return await builder.build_agent_from_description(
        user_description=user_description,
        output_dir=output_dir,
        agent_name=agent_name
    )


# 命令行接口支持
def main():
    """命令行主函数"""
    import argparse
    import asyncio
    
    parser = argparse.ArgumentParser(description="AgentBuilder - 从自然语言生成AI Agent")
    parser.add_argument("description", help="Agent需求描述")
    parser.add_argument("--provider", default="openai", help="LLM提供商")
    parser.add_argument("--model", default="gpt-4o", help="LLM模型")
    parser.add_argument("--api-key", required=True, help="API密钥")
    parser.add_argument("--output", default="./generated_agents", help="输出目录")
    parser.add_argument("--name", help="Agent名称")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # 构建Agent
    async def build():
        try:
            result = await build_agent(
                user_description=args.description,
                llm_provider=args.provider,
                llm_model=args.model,
                api_key=args.api_key,
                output_dir=args.output,
                agent_name=args.name
            )
            
            # 输出结果
            builder = AgentBuilder(LLMConfig(provider=args.provider, model=args.model, api_key=""))
            summary = builder.get_build_summary(result)
            print(summary)
            
            return result
            
        except Exception as e:
            print(f"❌ 构建失败: {e}")
            return None
    
    result = asyncio.run(build())
    exit(0 if result else 1)


if __name__ == "__main__":
    main()