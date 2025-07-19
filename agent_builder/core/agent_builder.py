"""
AgentBuilder - 主控制器，协调整个Agent生成过程
"""

import os
import json
import logging
import uuid
from typing import Optional, Dict, Any
from datetime import datetime

from .schemas import GeneratedCode, LLMConfig
from .requirement_parser import RequirementParser
from .agent_designer import AgentDesigner
from .code_generator import CodeGenerator

# 导入BaseAgent的WorkflowBuilder和相关类
import sys
from pathlib import Path
base_app_path = Path(__file__).parent.parent.parent / "base_app"
sys.path.insert(0, str(base_app_path))
from base_app.base_agent.core.workflow_builder import WorkflowBuilder as BaseWorkflowBuilder
from base_app.base_agent.core.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class AgentBuilder:
    """AgentBuilder主控制器 - 协调整个Agent生成过程"""
    
    def __init__(self, llm_config: LLMConfig, db_session=None):
        """
        初始化AgentBuilder
        
        Args:
            llm_config: LLM配置
            db_session: 数据库会话（可选）
        """
        self.llm_config = llm_config
        self.db_session = db_session
        
        # 初始化核心组件
        self.requirement_parser = RequirementParser(llm_config)
        self.agent_designer = AgentDesigner(llm_config)
        self.code_generator = CodeGenerator(llm_config)
        
        # 初始化BaseAgent实例（用于WorkflowBuilder）
        self.base_agent = BaseAgent()
        
        
        logger.info(f"AgentBuilder初始化完成，使用LLM: {llm_config.provider}/{llm_config.model}")
    
    def _convert_steps_to_base_workflow(self, steps: list, step_agents: list, build_id: str) -> Any:
        """
        将AgentBuilder的步骤转换为BaseAgent的Workflow格式
        
        Args:
            steps: AgentBuilder步骤列表
            step_agents: StepAgent规格列表
            build_id: 构建ID
            
        Returns:
            BaseAgent Workflow对象
        """
        import json
        
        # 创建工作流名称和描述
        workflow_name = f"agentbuilder_workflow_{build_id[:8]}"
        workflow_description = f"AgentBuilder自动生成的工作流，包含{len(steps)}个步骤"
        
        # 创建BaseWorkflowBuilder实例
        workflow_builder = BaseWorkflowBuilder(
            name=workflow_name,
            description=workflow_description,
            agent_instance=self.base_agent
        )
        
        # 为步骤创建agent_spec映射
        agent_spec_map = {spec.get('step_id', f'step_{i+1}'): spec 
                         for i, spec in enumerate(step_agents)}
        
        # 转换每个步骤，使用生成的精确配置
        for i, step in enumerate(steps):
            step_id = f"step_{i+1}"
            
            # 处理StepDesign对象或字典
            if hasattr(step, 'name'):
                # StepDesign对象
                step_name = step.name or f'步骤{i+1}'
                agent_type = step.agent_type or 'text'
            else:
                # 字典对象
                step_name = step.get('name', f'步骤{i+1}')
                agent_type = step.get('agent_type', 'text')
            
            # 获取对应的agent规格，使用新的baseagent_config
            agent_spec = agent_spec_map.get(step_id, {})
            baseagent_config = agent_spec.get('baseagent_config', {})
            
            if agent_type == 'text' or agent_type == 'text_agent':
                # 使用生成的精确TextAgent配置
                workflow_builder.add_text_step(
                    name=step_name,
                    instruction=baseagent_config.get('agent_instruction', step.description if hasattr(step, 'description') else ''),
                    description=baseagent_config.get('description', step.description if hasattr(step, 'description') else ''),
                    user_task=baseagent_config.get('user_task'),
                    inputs=baseagent_config.get('inputs', {}),
                    outputs=baseagent_config.get('outputs', {}),
                    constraints=baseagent_config.get('constraints', []),
                    response_style=baseagent_config.get('response_style', 'professional'),
                    max_length=baseagent_config.get('max_length', 500),
                    timeout=baseagent_config.get('timeout', 300),
                    retry_count=baseagent_config.get('retry_count', 0),
                    condition=baseagent_config.get('condition')
                )
            elif agent_type == 'tool' or agent_type == 'tool_agent':
                # 使用生成的精确ToolAgent配置，映射字段名
                workflow_builder.add_tool_step(
                    name=step_name,
                    instruction=baseagent_config.get('agent_instruction', step.description if hasattr(step, 'description') else ''),
                    tools=baseagent_config.get('allowed_tools', ['browser_use']),  # 映射 allowed_tools -> tools
                    description=baseagent_config.get('description', step.description if hasattr(step, 'description') else ''),
                    user_task=baseagent_config.get('user_task'),
                    inputs=baseagent_config.get('inputs', {}),
                    outputs=baseagent_config.get('outputs', {}),
                    constraints=baseagent_config.get('constraints', []),
                    confidence_threshold=baseagent_config.get('confidence_threshold', 0.8),
                    fallback_tools=baseagent_config.get('fallback_tools', []),
                    timeout=baseagent_config.get('timeout', 300),
                    retry_count=baseagent_config.get('retry_count', 0),
                    condition=baseagent_config.get('condition')
                )
            elif agent_type == 'code' or agent_type == 'code_agent':
                # 使用生成的精确CodeAgent配置，映射字段名
                workflow_builder.add_code_step(
                    name=step_name,
                    instruction=baseagent_config.get('agent_instruction', step.description if hasattr(step, 'description') else ''),
                    description=baseagent_config.get('description', step.description if hasattr(step, 'description') else ''),
                    language='python',  # WorkflowBuilder不支持language参数，固定使用python
                    libraries=baseagent_config.get('allowed_libraries', ['pandas', 'numpy']),  # 映射 allowed_libraries -> libraries
                    expected_output_format=baseagent_config.get('expected_output_format', ''),
                    user_task=baseagent_config.get('user_task'),
                    inputs=baseagent_config.get('inputs', {}),
                    outputs=baseagent_config.get('outputs', {}),
                    constraints=baseagent_config.get('constraints', []),
                    timeout=baseagent_config.get('timeout', 300),
                    retry_count=baseagent_config.get('retry_count', 0),
                    condition=baseagent_config.get('condition')
                )
            else:
                # 使用生成的精确自定义Agent配置
                workflow_builder.add_custom_step(
                    name=step_name,
                    agent_name=baseagent_config.get('agent_name', agent_type),
                    instruction=baseagent_config.get('agent_instruction', step.description if hasattr(step, 'description') else ''),
                    description=baseagent_config.get('description', step.description if hasattr(step, 'description') else ''),
                    user_task=baseagent_config.get('user_task'),
                    inputs=baseagent_config.get('inputs', {}),
                    outputs=baseagent_config.get('outputs', {}),
                    constraints=baseagent_config.get('constraints', []),
                    timeout=baseagent_config.get('timeout', 300),
                    retry_count=baseagent_config.get('retry_count', 0),
                    condition=baseagent_config.get('condition')
                )
        
        # 构建并返回Workflow
        workflow = workflow_builder.build()
        logger.info(f"成功转换为BaseAgent Workflow: {workflow.name}")
        return workflow
    
    def create_build_metadata(self, user_id: int, user_description: str) -> str:
        """
        创建构建元数据，返回build_id
        
        Args:
            user_id: 用户ID
            user_description: 用户需求描述
            
        Returns:
            build_id: 构建ID
        """
        build_id = f"build_{uuid.uuid4().hex[:8]}_{int(datetime.now().timestamp())}"
        
        if self.db_session:
            # 导入数据库模型
            from client.web.backend.database import AgentBuild
            
            # 创建构建记录
            agent_build = AgentBuild(
                build_id=build_id,
                user_id=user_id,
                user_description=user_description,
                status="building",
                current_step="starting"
            )
            
            self.db_session.add(agent_build)
            self.db_session.commit()
            
            logger.info(f"创建构建元数据 - build_id: {build_id}")
        
        return build_id
    
    def update_build_step(self, build_id: str, step_name: str, step_data: Optional[Dict] = None):
        """
        更新构建步骤
        
        Args:
            build_id: 构建ID
            step_name: 步骤名称
            step_data: 步骤数据（可选）
        """
        if self.db_session:
            from client.web.backend.database import AgentBuild
            
            build = self.db_session.query(AgentBuild).filter_by(build_id=build_id).first()
            if build:
                build.current_step = step_name
                self.db_session.commit()
                logger.info(f"更新构建步骤 - build_id: {build_id}, step: {step_name}")
    
    def update_build_result(self, build_id: str, agent_purpose: str = None, 
                          generated_code: str = None, workflow_config: str = None, 
                          status: str = None, error_message: str = None,
                          steps_data: str = None, step_agents_data: str = None,
                          agent_types_data: str = None, workflow_data: str = None):
        """
        更新构建结果
        
        Args:
            build_id: 构建ID
            agent_purpose: Agent目的
            generated_code: 生成的代码
            workflow_config: 工作流配置
            status: 构建状态
            error_message: 错误信息
            steps_data: 步骤数据(JSON)
            step_agents_data: StepAgent数据(JSON)
            agent_types_data: Agent类型数据(JSON)
            workflow_data: BaseAgent Workflow数据(JSON)
        """
        if self.db_session:
            from client.web.backend.database import AgentBuild
            
            build = self.db_session.query(AgentBuild).filter_by(build_id=build_id).first()
            if build:
                if agent_purpose:
                    build.agent_purpose = agent_purpose
                if generated_code:
                    build.generated_code = generated_code
                if workflow_config:
                    build.workflow_config = workflow_config
                if status:
                    build.status = status
                    if status == "completed":
                        build.completed_at = datetime.utcnow()
                if error_message:
                    build.error_message = error_message
                if steps_data:
                    build.steps_data = steps_data
                if step_agents_data:
                    build.step_agents_data = step_agents_data
                if agent_types_data:
                    build.agent_types_data = agent_types_data
                if workflow_data:
                    build.workflow_data = workflow_data
                
                self.db_session.commit()
                logger.info(f"更新构建结果 - build_id: {build_id}, status: {status}")
    
    async def build_agent_from_description(self, 
                                         user_description: str,
                                         output_dir: str = "./generated_agents",
                                         agent_name: Optional[str] = None,
                                         user_id: Optional[int] = None,
                                         build_id: Optional[str] = None) -> Dict[str, Any]:
        """
        从自然语言描述构建Agent - 基于Context Engineering优化的完整流程
        
        Args:
            user_description: 用户的自然语言需求描述
            output_dir: 输出目录
            agent_name: 可选的Agent名称，如果不提供会自动生成
            user_id: 用户ID（用于数据库记录）
            build_id: 构建ID（如果提供则使用现有记录）
            
        Returns:
            Dict包含生成结果和文件路径
        """
        
        logger.info("开始从自然语言描述构建Agent")
        logger.info(f"用户描述: {user_description[:100]}...")
        
        # 如果没有提供build_id且有user_id，创建新的构建记录
        if not build_id and user_id is not None:
            build_id = self.create_build_metadata(user_id, user_description)
        
        try:
            # 1. 智能需求解析（已实现）
            logger.info("步骤1: 解析用户需求")
            self.update_build_step(build_id, "parsing_requirements")
            requirement = await self.requirement_parser.parse_requirements(user_description)
            logger.info(f"解析完成 - Agent目的: {requirement.agent_purpose}")
            
            # 保存需求解析结果
            self.update_build_result(build_id, agent_purpose=requirement.agent_purpose)
            
            # 2. 基于工具能力的步骤提取（已实现）
            logger.info("步骤2: 提取执行步骤")
            self.update_build_step(build_id, "extracting_steps")
            steps = await self.requirement_parser.extract_steps(
                user_description, requirement.agent_purpose
            )
            logger.info(f"步骤提取完成 - 共{len(steps)}个步骤")
            
            # 3. 成本效益优化的Agent类型判断（已实现）
            logger.info("步骤3: 判断Agent类型")
            self.update_build_step(build_id, "judging_agent_types")
            agent_types = await self.agent_designer.judge_agent_types(steps)
            logger.info(f"Agent类型判断完成: {agent_types}")
            
            # 4. 按需生成StepAgent（已实现）
            logger.info("步骤4: 生成StepAgent规格")
            self.update_build_step(build_id, "generating_step_agents")
            step_agents = await self.agent_designer.generate_step_agents(steps)
            logger.info(f"StepAgent生成完成 - 共{len(step_agents)}个Agent规格")
            
            # 存储中间产物到数据库
            import json
            
            # 将StepDesign对象转换为可序列化的字典
            serializable_steps = []
            for step in steps:
                if hasattr(step, 'dict'):
                    # 如果是Pydantic模型，使用dict()方法
                    serializable_steps.append(step.dict())
                elif hasattr(step, '__dict__'):
                    # 如果是普通对象，使用__dict__
                    serializable_steps.append(step.__dict__)
                else:
                    # 如果已经是字典，直接使用
                    serializable_steps.append(step)
            
            self.update_build_result(
                build_id,
                steps_data=json.dumps(serializable_steps, ensure_ascii=False),
                step_agents_data=json.dumps(step_agents, ensure_ascii=False),
                agent_types_data=json.dumps(agent_types, ensure_ascii=False)
            )
            
            # 5. 组合Workflow（使用BaseAgent WorkflowBuilder）
            logger.info("步骤5: 构建工作流")
            self.update_build_step(build_id, "building_workflow")
            workflow = self._convert_steps_to_base_workflow(steps, step_agents, build_id)
            logger.info(f"工作流构建完成 - {workflow.name}")
            print(workflow)
            
            # 存储BaseAgent Workflow到数据库
            # 使用model_dump替代弃用的dict()方法
            workflow_dict = workflow.model_dump() if hasattr(workflow, 'model_dump') else workflow.dict()
            self.update_build_result(
                build_id,
                workflow_data=json.dumps(workflow_dict, ensure_ascii=False, default=str)
            )
            
            # 7. 生成BaseAgent兼容代码（直接使用BaseAgent Workflow）
            logger.info("步骤7: 生成Python代码")
            self.update_build_step(build_id, "generating_code")
            
            # 直接使用BaseAgent Workflow对象，不再转换为字典格式
            generated_code = await self.code_generator.generate_agent_code(workflow, step_agents)
            logger.info("代码生成完成")
            
            # 保存生成的代码，workflow配置直接存储在workflow_data字段中
            self.update_build_result(
                build_id, 
                generated_code=generated_code.main_agent_code
            )
            
            # 8. 保存生成的文件
            logger.info("步骤8: 保存生成的文件")
            self.update_build_step(build_id, "saving_files")
            file_paths = await self._save_generated_files(
                generated_code, workflow, steps, output_dir, agent_name, build_id
            )
            logger.info(f"文件保存完成 - 主文件: {file_paths['agent_file']}")
            
            # 9. 测试生成的代码
            logger.info("步骤9: 测试生成的代码")
            self.update_build_step(build_id, "testing_code")
            test_result = self._test_generated_agent(file_paths['agent_file'])
            logger.info(f"代码测试完成 - 语法有效: {test_result['syntax_valid']}")
            
            # 10. 标记构建完成
            self.update_build_step(build_id, "completed")
            self.update_build_result(build_id, status="completed")
            
            # 11. 生成完整的构建报告
            build_report = self._generate_build_report(
                requirement, steps, workflow, generated_code, file_paths, test_result
            )
            build_report['build_id'] = build_id
            
            logger.info("Agent构建完成！")
            return build_report
            
        except Exception as e:
            logger.error(f"Agent构建失败: {str(e)}")
            # 更新构建失败状态
            self.update_build_result(build_id, status="failed", error_message=str(e))
            raise AgentBuildError(f"构建Agent时发生错误: {str(e)}") from e
    
    async def _save_generated_files(self, 
                                  generated_code: GeneratedCode,
                                  workflow: Any,
                                  steps: list,
                                  output_dir: str,
                                  agent_name: Optional[str],
                                  build_id: str) -> Dict[str, str]:
        """保存所有生成的文件到基于Agent ID的文件夹"""
        
        # 从build_id中提取Agent ID（取前8位）
        agent_id = build_id.split('_')[1][:8] if '_' in build_id else build_id[:8]
        
        # 创建基于Agent ID的文件夹
        agent_folder = os.path.join(output_dir, f"agent_{agent_id}")
        os.makedirs(agent_folder, exist_ok=True)
        
        # 文件路径
        file_paths = {
            'agent_folder': agent_folder,
            'agent_file': os.path.join(agent_folder, 'agent.py'),
            'config_file': os.path.join(agent_folder, 'config.json'),
            'workflow_file': os.path.join(agent_folder, 'workflow.yaml'),
            'metadata_file': os.path.join(agent_folder, 'metadata.json'),
            'readme_file': os.path.join(agent_folder, 'README.md'),
            'requirements_file': os.path.join(agent_folder, 'requirements.txt')
        }
        
        # 保存主Agent代码
        with open(file_paths['agent_file'], 'w', encoding='utf-8') as f:
            f.write(generated_code.main_agent_code)
        
        # 保存工作流配置
        with open(file_paths['workflow_file'], 'w', encoding='utf-8') as f:
            f.write(generated_code.workflow_config)
        
        # 保存Agent配置文件
        config_dict = {
            "name": generated_code.metadata.name,
            "agent_id": agent_id,
            "description": generated_code.metadata.description,
            "llm_provider": self.llm_config.provider,
            "llm_model": self.llm_config.model,
            "api_key": "${OPENAI_API_KEY}",
            "capabilities": generated_code.metadata.capabilities,
            "created_at": generated_code.metadata.created_at.isoformat()
        }
        
        with open(file_paths['config_file'], 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)
        
        # 保存元数据
        metadata_dict = {
            "name": generated_code.metadata.name,
            "agent_id": agent_id,
            "description": generated_code.metadata.description,
            "capabilities": generated_code.metadata.capabilities,
            "interface": generated_code.metadata.interface,
            "cost_analysis": generated_code.metadata.cost_analysis,
            "created_at": generated_code.metadata.created_at.isoformat(),
            "steps_count": len(steps),
            "workflow_complexity": getattr(workflow, 'complexity_score', "unknown") if hasattr(workflow, 'complexity_score') else "unknown"
        }
        
        with open(file_paths['metadata_file'], 'w', encoding='utf-8') as f:
            json.dump(metadata_dict, f, indent=2, ensure_ascii=False)
        
        # 生成README文档
        readme_content = self._generate_readme(generated_code, workflow, steps, agent_id)
        with open(file_paths['readme_file'], 'w', encoding='utf-8') as f:
            f.write(readme_content)
        
        # 生成requirements.txt
        requirements_content = self._generate_requirements()
        with open(file_paths['requirements_file'], 'w', encoding='utf-8') as f:
            f.write(requirements_content)
        
        return file_paths
    
    def _generate_readme(self, 
                        generated_code: GeneratedCode,
                        workflow: Any,
                        steps: list,
                        agent_id: str) -> str:
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
pip install -r requirements.txt
```

### 2. 配置API密钥

编辑代码中的API密钥配置：

设置环境变量：

```bash
export OPENAI_API_KEY="your-api-key-here"
```

或者编辑 config.json 文件中的 api_key 字段
```

### 3. 运行Agent

```bash
python agent.py --interactive
```

### 4. 编程方式使用

```python
import asyncio
from agent import Agent_{agent_id}
from base_app.base_agent.core.schemas import AgentConfig

async def main():
    config = AgentConfig(
        name="{generated_code.metadata.name}",
        llm_provider="{self.llm_config.provider}",
        api_key="your-api-key"
    )
    
    agent = Agent_{agent_id}(config)
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

- `agent.py` - 主Agent实现代码
- `config.json` - Agent配置文件
- `workflow.yaml` - 工作流配置文件
- `metadata.json` - Agent元数据
- `requirements.txt` - Python依赖包
- `README.md` - 本说明文档

## 生成信息

- **生成时间**: {generated_code.created_at.strftime('%Y-%m-%d %H:%M:%S')}
- **AgentBuilder版本**: 1.0.0
- **工作流复杂度**: {getattr(workflow, 'complexity_score', '未评估') if hasattr(workflow, 'complexity_score') else '未评估'}

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
                             workflow: Any,
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
                "workflow_complexity": getattr(workflow, 'complexity_score', "unknown") if hasattr(workflow, 'complexity_score') else "unknown",
                "estimated_execution_time": getattr(workflow, 'estimated_execution_time', 0) if hasattr(workflow, 'estimated_execution_time') else 0,
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
                "name": getattr(workflow, 'name', "Unknown") if hasattr(workflow, 'name') else "Unknown",
                "steps_count": len(getattr(workflow, 'steps', [])) if hasattr(workflow, 'steps') else 0,
                "has_conditions": False,  # 简化处理，BaseAgent workflow通常没有条件
                "agent_types_used": []  # 简化处理，从steps中提取类型较复杂
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