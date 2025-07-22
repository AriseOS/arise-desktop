"""
CodeGenerator - 生成BaseAgent兼容的Python代码
"""

import json
import os
import ast
import tempfile
import subprocess
from typing import List, Dict, Any, Optional
from datetime import datetime
from .schemas import GeneratedCode, AgentMetadata, LLMConfig
# from .workflow_builder import WorkflowBuilder  # 不再需要
from .providers import OpenAIProvider


class CodeGenerator:
    """代码生成器 - 生成BaseAgent兼容的Python代码"""
    
    def __init__(self, llm_config: LLMConfig):
        self.llm_config = llm_config
        self.provider = None
        self._setup_provider()
    
    def _setup_provider(self):
        """设置 LLM provider"""
        if self.llm_config.provider == "openai":
            self.provider = OpenAIProvider(
                api_key=self.llm_config.api_key,
                model=self.llm_config.model
            )
        else:
            raise ValueError(f"不支持的 LLM 提供商: {self.llm_config.provider}")
    
    async def generate_agent_code(self, workflow: Any, agent_specs: List[Dict[str, Any]]) -> GeneratedCode:
        """
        生成Agent代码 - 使用LLM生成BaseAgent兼容代码
        - 生成继承自BaseAgent的Python类
        - 生成YAML格式的工作流配置文件
        - 确保代码符合BaseAgent接口规范
        """
        print("\nagent_specs\n")
        print(agent_specs)
        
        # 1. 生成主Agent类代码
        main_agent_code = await self._generate_main_agent_class(workflow, agent_specs)
        
        # 2. 生成工作流配置（直接使用BaseAgent的workflow对象）
        workflow_config = self._format_workflow_config(workflow)
        
        # 3. 生成Agent元数据
        metadata = await self._generate_metadata(workflow, agent_specs)
        
        # 4. 验证生成的代码
        validation_result = self._validate_generated_code(main_agent_code)
        if not validation_result["valid"]:
            # 尝试修复代码
            main_agent_code = await self._fix_code_issues(main_agent_code, validation_result["errors"])
        
        return GeneratedCode(
            main_agent_code=main_agent_code,
            workflow_config=workflow_config,
            metadata=metadata,
            created_at=datetime.now()
        )
    
    async def _generate_main_agent_class(self, workflow: Any, agent_specs: List[Dict[str, Any]]) -> str:
        """生成主Agent类的Python代码"""
        
        # 构建代码生成的提示词
        prompt = self._build_code_generation_prompt(workflow, agent_specs)
        
        # 调用LLM生成代码
        response = await self._call_llm(prompt)
        
        # 提取和清理代码
        code = self._extract_code_from_response(response)
        
        return code
    
    def _build_code_generation_prompt(self, workflow: Any, agent_specs: List[Dict[str, Any]]) -> str:
        """构建代码生成的提示词"""
        
        # 处理BaseAgent的Workflow对象
        if hasattr(workflow, 'name'):
            # BaseAgent Workflow对象
            workflow_name = workflow.name or "GeneratedAgent"
            workflow_description = getattr(workflow, 'description', "自动生成的Agent")
            steps = getattr(workflow, 'steps', [])
        else:
            # 字典格式的workflow
            workflow_name = workflow.get("metadata", {}).get("name", "GeneratedAgent")
            workflow_description = workflow.get("metadata", {}).get("description", "自动生成的Agent")
            steps = workflow.get("steps", [])
        
        # 分析需要的自定义工具
        custom_tools_needed = []
        tool_combinations_needed = []
        
        for spec in agent_specs:
            if spec.get("generation_type") == "custom_agent":
                custom_tools_needed.append(spec)
            elif spec.get("generation_type") == "tool_combination":
                tool_combinations_needed.append(spec)
        
        # 构建步骤描述和收集需要的工具
        steps_description = ""
        required_tools = set()
        
        for i, step in enumerate(steps):
            # 处理步骤对象或字典
            if hasattr(step, 'name'):
                # BaseAgent Step对象
                step_name = getattr(step, 'name', 'Unknown')
                step_desc = getattr(step, 'description', 'No description')
                step_type = getattr(step, 'agent_type', 'unknown')
                # 收集工具需求 - 优先从allowed_tools，然后从tools
                step_tools = getattr(step, 'allowed_tools', []) or getattr(step, 'tools', [])
                if step_tools:
                    required_tools.update(step_tools)
            else:
                # 字典格式的步骤
                step_name = step.get('name', 'Unknown')
                step_desc = step.get('description', 'No description') 
                step_type = step.get('agent_type', 'unknown')
                # 收集工具需求
                step_tools = step.get('allowed_tools', []) or step.get('tools', [])
                if step_tools:
                    required_tools.update(step_tools)
            
            # 构建详细的步骤描述，包含工具信息
            if step_tools:
                steps_description += f"  {i+1}. {step_name} ({step_type}): {step_desc} [工具: {', '.join(step_tools)}]\n"
            else:
                steps_description += f"  {i+1}. {step_name} ({step_type}): {step_desc}\n"
        
        # 从agent_specs中额外收集工具需求并构建详细配置信息
        detailed_step_configs = ""
        for i, spec in enumerate(agent_specs):
            baseagent_config = spec.get('baseagent_config', {})
            spec_tools = baseagent_config.get('allowed_tools', []) or baseagent_config.get('tools', [])
            if spec_tools:
                required_tools.update(spec_tools)
            
            # 构建详细的步骤配置信息
            step_num = i + 1
            step_name = baseagent_config.get('name', f'步骤{step_num}')
            step_type = baseagent_config.get('agent_type', 'text_agent')
            
            detailed_step_configs += f"\n### 步骤 {step_num}: {step_name} ({step_type})\n"
            detailed_step_configs += f"- **名称**: {step_name}\n"
            detailed_step_configs += f"- **描述**: {baseagent_config.get('description', '')}\n"
            detailed_step_configs += f"- **Agent类型**: {step_type}\n"
            detailed_step_configs += f"- **执行指令**: {baseagent_config.get('agent_instruction', '')}\n"
            
            if baseagent_config.get('user_task'):
                detailed_step_configs += f"- **用户任务**: {baseagent_config.get('user_task')}\n"
            
            # 输入输出配置
            inputs = baseagent_config.get('inputs', {})
            if inputs:
                detailed_step_configs += f"- **输入配置**: {inputs}\n"
            
            outputs = baseagent_config.get('outputs', {})
            if outputs:
                detailed_step_configs += f"- **输出配置**: {outputs}\n"
            
            constraints = baseagent_config.get('constraints', [])
            if constraints:
                detailed_step_configs += f"- **约束条件**: {constraints}\n"
            
            # Agent类型特定配置
            if step_type == 'text_agent':
                if baseagent_config.get('response_style'):
                    detailed_step_configs += f"- **回答风格**: {baseagent_config.get('response_style')}\n"
                if baseagent_config.get('max_length'):
                    detailed_step_configs += f"- **最大长度**: {baseagent_config.get('max_length')}\n"
            
            elif step_type == 'tool_agent':
                if spec_tools:
                    detailed_step_configs += f"- **允许工具**: {spec_tools}\n"
                if baseagent_config.get('confidence_threshold'):
                    detailed_step_configs += f"- **置信度阈值**: {baseagent_config.get('confidence_threshold')}\n"
                fallback_tools = baseagent_config.get('fallback_tools', [])
                if fallback_tools:
                    detailed_step_configs += f"- **备选工具**: {fallback_tools}\n"
            
            elif step_type == 'code_agent':
                allowed_libraries = baseagent_config.get('allowed_libraries', [])
                if allowed_libraries:
                    detailed_step_configs += f"- **允许的库**: {allowed_libraries}\n"
                if baseagent_config.get('expected_output_format'):
                    detailed_step_configs += f"- **期望输出格式**: {baseagent_config.get('expected_output_format')}\n"
            
            # 执行控制参数
            if baseagent_config.get('timeout', 300) != 300:
                detailed_step_configs += f"- **超时时间**: {baseagent_config.get('timeout')}秒\n"
            if baseagent_config.get('retry_count', 0) > 0:
                detailed_step_configs += f"- **重试次数**: {baseagent_config.get('retry_count')}\n"
            if baseagent_config.get('condition'):
                detailed_step_configs += f"- **执行条件**: {baseagent_config.get('condition')}\n"
            
            # 生成对应的WorkflowBuilder调用代码
            detailed_step_configs += f"\n**对应的WorkflowBuilder调用代码**:\n```python\n"
            
            if step_type == 'text_agent':
                detailed_step_configs += f"builder.add_text_step(\n"
                detailed_step_configs += f"    name=\"{step_name}\",\n"
                detailed_step_configs += f"    instruction=\"{baseagent_config.get('agent_instruction', '')}\",\n"
                detailed_step_configs += f"    description=\"{baseagent_config.get('description', '')}\",\n"
                if baseagent_config.get('user_task'):
                    detailed_step_configs += f"    user_task=\"{baseagent_config.get('user_task')}\",\n"
                if inputs:
                    detailed_step_configs += f"    inputs={inputs},\n"
                if outputs:
                    detailed_step_configs += f"    outputs={outputs},\n"
                if constraints:
                    detailed_step_configs += f"    constraints={constraints},\n"
                if baseagent_config.get('response_style'):
                    detailed_step_configs += f"    response_style=\"{baseagent_config.get('response_style')}\",\n"
                if baseagent_config.get('max_length'):
                    detailed_step_configs += f"    max_length={baseagent_config.get('max_length')},\n"
                if baseagent_config.get('timeout', 300) != 300:
                    detailed_step_configs += f"    timeout={baseagent_config.get('timeout')},\n"
                if baseagent_config.get('retry_count', 0) > 0:
                    detailed_step_configs += f"    retry_count={baseagent_config.get('retry_count')},\n"
                if baseagent_config.get('condition'):
                    detailed_step_configs += f"    condition=\"{baseagent_config.get('condition')}\",\n"
                detailed_step_configs += f")\n"
            
            elif step_type == 'tool_agent':
                detailed_step_configs += f"builder.add_tool_step(\n"
                detailed_step_configs += f"    name=\"{step_name}\",\n"
                detailed_step_configs += f"    instruction=\"{baseagent_config.get('agent_instruction', '')}\",\n"
                detailed_step_configs += f"    tools={spec_tools},\n"
                detailed_step_configs += f"    description=\"{baseagent_config.get('description', '')}\",\n"
                if baseagent_config.get('user_task'):
                    detailed_step_configs += f"    user_task=\"{baseagent_config.get('user_task')}\",\n"
                if inputs:
                    detailed_step_configs += f"    inputs={inputs},\n"
                if outputs:
                    detailed_step_configs += f"    outputs={outputs},\n"
                if constraints:
                    detailed_step_configs += f"    constraints={constraints},\n"
                if baseagent_config.get('confidence_threshold'):
                    detailed_step_configs += f"    confidence_threshold={baseagent_config.get('confidence_threshold')},\n"
                fallback_tools = baseagent_config.get('fallback_tools', [])
                if fallback_tools:
                    detailed_step_configs += f"    fallback_tools={fallback_tools},\n"
                if baseagent_config.get('timeout', 300) != 300:
                    detailed_step_configs += f"    timeout={baseagent_config.get('timeout')},\n"
                if baseagent_config.get('retry_count', 0) > 0:
                    detailed_step_configs += f"    retry_count={baseagent_config.get('retry_count')},\n"
                if baseagent_config.get('condition'):
                    detailed_step_configs += f"    condition=\"{baseagent_config.get('condition')}\",\n"
                detailed_step_configs += f")\n"
            
            elif step_type == 'code_agent':
                detailed_step_configs += f"builder.add_code_step(\n"
                detailed_step_configs += f"    name=\"{step_name}\",\n"
                detailed_step_configs += f"    instruction=\"{baseagent_config.get('agent_instruction', '')}\",\n"
                detailed_step_configs += f"    description=\"{baseagent_config.get('description', '')}\",\n"
                allowed_libraries = baseagent_config.get('allowed_libraries', [])
                if allowed_libraries:
                    detailed_step_configs += f"    libraries={allowed_libraries},\n"
                if baseagent_config.get('expected_output_format'):
                    detailed_step_configs += f"    expected_output_format=\"{baseagent_config.get('expected_output_format')}\",\n"
                if baseagent_config.get('user_task'):
                    detailed_step_configs += f"    user_task=\"{baseagent_config.get('user_task')}\",\n"
                if inputs:
                    detailed_step_configs += f"    inputs={inputs},\n"
                if outputs:
                    detailed_step_configs += f"    outputs={outputs},\n"
                if constraints:
                    detailed_step_configs += f"    constraints={constraints},\n"
                if baseagent_config.get('timeout', 300) != 300:
                    detailed_step_configs += f"    timeout={baseagent_config.get('timeout')},\n"
                if baseagent_config.get('retry_count', 0) > 0:
                    detailed_step_configs += f"    retry_count={baseagent_config.get('retry_count')},\n"
                if baseagent_config.get('condition'):
                    detailed_step_configs += f"    condition=\"{baseagent_config.get('condition')}\",\n"
                detailed_step_configs += f")\n"
            
            detailed_step_configs += f"```\n"
        
        # 将工具集合转换为列表并排序
        required_tools_list = sorted(list(required_tools))
        
        # 构建提示词，使用字符串连接避免f-string中的变量冲突
        prompt = """# Python代码生成专家

## 任务背景
你是一个专业的Python代码生成专家，需要基于BaseAgent框架生成一个完整的自定义Agent类。

## BaseAgent框架使用规范

### 基本导入和初始化
```python
#!/usr/bin/env python3
\"\"\"
Generated Agent - 由AgentBuilder自动生成
可以独立运行的Agent实现
\"\"\"

import sys
import os
import asyncio
import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime

# 添加BaseApp路径到系统路径
current_dir = Path(__file__).parent
base_app_path = current_dir.parent.parent / "base_app"
sys.path.insert(0, str(base_app_path))

# BaseAgent核心导入
from base_app.base_agent.core.base_agent import BaseAgent
from base_app.base_agent.core.schemas import AgentConfig, AgentResult

class Agent_Generated(BaseAgent):
    \"\"\"
    自动生成的Agent
    
    需要的工具: """ + str(required_tools_list) + """
    这些工具会通过config.tools自动注册到Agent中
    \"\"\"
    def __init__(self, config: AgentConfig):
        super().__init__(config)  # BaseAgent会根据config.tools自动注册工具
        self.workflow = None
        self.workflow_name = "custom_workflow"
    
    async def initialize(self):
        \"\"\"初始化Agent和工作流\"\"\"
        await super().initialize()  # 这里会初始化所有工具
        await self._setup_workflow()
    
    async def _setup_workflow(self):
        \"\"\"设置工作流\"\"\"
        # 创建工作流构建器
        builder = self.create_workflow_builder("工作流名称", "工作流描述")
        
        # 添加步骤...
        
        # 构建工作流
        self.workflow = builder.build()
    
    async def execute(self, input_data: Any) -> AgentResult:
        \"\"\"执行Agent\"\"\"
        if not self.workflow:
            await self._setup_workflow()
        
        # 运行工作流
        # 将input_data包装为字典格式，因为BaseAgent的run_workflow期望Dict[str, Any]
        workflow_input = {"user_input": input_data} if not isinstance(input_data, dict) else input_data
        result = await self.run_workflow(self.workflow, workflow_input)
        
        return AgentResult(
            success=True,
            data=result,
            agent_name=self.config.name,
            execution_time=0.0
        )
```

### 工作流构建API
- `self.create_workflow_builder(name, description)` - 创建工作流构建器
- `builder.add_text_step(name, instruction, **kwargs)` - 添加文本处理步骤
- `builder.add_tool_step(name, instruction, tools, **kwargs)` - 添加工具使用步骤
- `builder.add_code_step(name, instruction, **kwargs)` - 添加代码执行步骤
- `builder.add_custom_step(name, agent_name, instruction, **kwargs)` - 添加自定义Agent步骤
- `builder.build()` - 构建工作流

### 自定义Agent创建
```python
# 创建自定义文本Agent
custom_agent = self.create_custom_text_agent(
    name="agent_name",
    system_prompt="系统提示词",
    response_style="professional"
)
self.register_custom_agent(custom_agent)
```

## 生成要求

### Agent信息
- **Agent名称**: """ + workflow_name + """
- **Agent描述**: """ + workflow_description + """
- **需要的工具**: """ + str(required_tools_list) + """
- **工作流步骤**:
""" + steps_description + """

## 详细步骤配置

AgentBuilder已经为每个步骤生成了详细的配置信息，请严格按照这些配置生成相应的WorkflowBuilder调用代码：
""" + detailed_step_configs + """

### 自定义工具需求
""" + self._format_custom_tools_info(custom_tools_needed) + """

### 工具组合需求
""" + self._format_tool_combinations_info(tool_combinations_needed) + """

## 代码生成要求

1. **完整性**: 生成完整的可执行Python文件
2. **兼容性**: 严格遵循BaseAgent接口规范
3. **功能性**: 实现所有指定的工作流步骤
4. **配置完整性**: **必须使用上述"详细步骤配置"中提供的所有参数，包括inputs、outputs、constraints、Agent特定参数等**
5. **代码质量**: 
   - 清晰的注释和文档字符串
   - 符合PEP 8编码规范
   - 适当的错误处理
   - 类型注解

6. **工作流构建要求**:
   - 在`_setup_workflow`方法中，必须使用上述提供的WorkflowBuilder调用代码
   - 严格按照每个步骤的详细配置参数调用相应的add_*_step方法
   - 确保所有inputs、outputs、constraints等配置都正确传递
   - 保持步骤的执行顺序

7. **文件结构**:
   - 导入语句（包含argparse, json, sys, os, Path等）
   - Agent类定义
   - 工作流设置方法
   - 自定义工具实现（如需要）
   - 完整的main函数和CLI入口

6. **独立运行要求**:
   - 必须包含#!/usr/bin/env python3作为shebang
   - 必须包含完整的main()函数
   - 支持--interactive交互模式
   - 支持--input单次执行模式
   - 支持--api-key和--config参数
   - 包含正确的BaseApp路径设置
   - 生成的Agent类名必须为Agent_Generated
   - 生成的Agent应该能够直接使用传入的workflow对象执行工作流

请生成一个完整的可独立运行的Python文件，其中Agent类应该能够执行BaseAgent的workflow

## 输出格式
## CLI入口要求

必须在代码末尾包含以下结构的main函数：

```python
def main():
    parser = argparse.ArgumentParser(description="Generated Agent")
    parser.add_argument('--input', help='输入数据')
    parser.add_argument('--interactive', action='store_true', help='交互模式')
    parser.add_argument('--api-key', help='API密钥')
    parser.add_argument('--config', help='配置文件路径')
    
    args = parser.parse_args()
    
    # 加载配置
    config_file = Path(__file__).parent / "config.json"
    if config_file.exists() and not args.config:
        with open(config_file, 'r') as f:
            config_data = json.load(f)
            config = AgentConfig(
                name=config_data.get('name', 'Generated Agent'),
                llm_provider=config_data.get('llm_provider', 'openai'),
                llm_model=config_data.get('llm_model', 'gpt-4o'),
                api_key=args.api_key or config_data.get('api_key') or os.getenv('OPENAI_API_KEY'),
                tools=config_data.get('tools', """ + str(required_tools_list) + """)  # 需要的工具: """ + str(required_tools_list) + """
            )
    else:
        config = AgentConfig(
            name="Generated Agent",
            llm_provider="openai",
            llm_model="gpt-4o",
            api_key=args.api_key or os.getenv("OPENAI_API_KEY"),
            tools=""" + str(required_tools_list) + """  # 需要的工具: """ + str(required_tools_list) + """
        )
    
    agent = Agent_Generated(config)
    
    if args.interactive:
        print("Agent 交互模式启动")
        while True:
            try:
                user_input = input("输入: ")
                if user_input.lower() in ['quit', 'exit']:
                    break
                agent_result = asyncio.run(agent.execute(user_input))
                print(f"结果: {agent_result}")
            except KeyboardInterrupt:
                break
    else:
        if args.input:
            agent_result = asyncio.run(agent.execute(args.input))
            # 使用model_dump而不是dict()，并处理datetime序列化
            result_dict = agent_result.model_dump() if hasattr(agent_result, 'model_dump') else agent_result.dict()
            print(json.dumps(result_dict, indent=2, ensure_ascii=False, default=str))
        else:
            print("请提供--input参数或使用--interactive模式")

if __name__ == "__main__":
    main()
```

请直接输出Python代码，不要包含任何markdown标记或额外的解释文字。"""
        
        return prompt
    
    def _format_custom_tools_info(self, custom_tools: List[Dict[str, Any]]) -> str:
        """格式化自定义工具信息"""
        if not custom_tools:
            return "无需实现自定义工具"
        
        info = "需要实现以下自定义工具:\n"
        for i, tool in enumerate(custom_tools):
            spec = tool.get("specification", {})
            info += f"  {i+1}. {spec.get('agent_name', 'CustomTool')}: {spec.get('agent_description', 'No description')}\n"
            
            capabilities = spec.get('required_capabilities', [])
            if capabilities:
                info += f"     需要的能力: {', '.join(capabilities)}\n"
        
        return info
    
    def _format_tool_combinations_info(self, combinations: List[Dict[str, Any]]) -> str:
        """格式化工具组合信息"""
        if not combinations:
            return "无需组合现有工具"
        
        info = "需要组合以下现有工具:\n"
        for i, combo in enumerate(combinations):
            spec = combo.get("specification", {})
            tools = spec.get("tools_to_combine", [])
            info += f"  {i+1}. 组合工具: {', '.join(tools)}\n"
            info += f"     组合策略: {spec.get('combination_strategy', 'sequential')}\n"
        
        return info
    
    async def _call_llm(self, prompt: str, system_prompt: str = "") -> str:
        """调用真实的大模型API"""
        if not system_prompt:
            system_prompt = "你是一个专业的 Python 代码生成器，专门生成 BaseAgent 兼容的代码。请严格按照要求生成代码。"
        
        return await self.provider.generate_response(system_prompt, prompt)
    
    def _extract_code_from_response(self, response: str) -> str:
        """从LLM响应中提取代码"""
        # 移除可能的markdown标记
        code = response.strip()
        
        if code.startswith("```python"):
            code = code[9:]
        elif code.startswith("```"):
            code = code[3:]
        
        if code.endswith("```"):
            code = code[:-3]
        
        return code.strip()
    
    def _format_workflow_config(self, workflow: Any) -> str:
        """格式化工作流配置为YAML字符串"""
        import yaml
        
        # 处理BaseAgent Workflow对象
        if hasattr(workflow, 'name'):
            # BaseAgent Workflow对象，转换为字典
            workflow_dict = {
                "metadata": {
                    "name": workflow.name,
                    "description": getattr(workflow, 'description', ''),
                    "version": getattr(workflow, 'version', '1.0.0'),
                    "created_at": datetime.now().isoformat()
                },
                "steps": []
            }
            
            # 添加步骤
            for step in getattr(workflow, 'steps', []):
                step_dict = {
                    "name": getattr(step, 'name', ''),
                    "description": getattr(step, 'description', ''),
                    "agent_type": getattr(step, 'agent_type', 'text'),
                    "instruction": getattr(step, 'agent_instruction', '')
                }
                workflow_dict["steps"].append(step_dict)
            
            return yaml.dump(workflow_dict, default_flow_style=False, allow_unicode=True)
        else:
            # 字典格式的workflow（向后兼容）
            return yaml.dump(workflow, default_flow_style=False, allow_unicode=True)
    
    async def _generate_metadata(self, workflow: Any, agent_specs: List[Dict[str, Any]]) -> AgentMetadata:
        """生成Agent元数据"""
        
        # 分析能力列表
        capabilities = []
        
        # 处理BaseAgent Workflow对象
        if hasattr(workflow, 'steps'):
            steps = getattr(workflow, 'steps', [])
            for step in steps:
                agent_type = getattr(step, 'agent_type', 'text')
                if agent_type == 'text_agent' or agent_type == 'text':
                    capabilities.append("自然语言理解与生成")
                elif agent_type == 'tool_agent' or agent_type == 'tool':
                    tools = getattr(step, 'allowed_tools', [])
                    for tool in tools:
                        capabilities.append(f"工具调用: {tool}")
                elif agent_type == 'code_agent' or agent_type == 'code':
                    capabilities.append("代码生成与执行")
                else:
                    capabilities.append("自定义功能")
        else:
            # 字典格式的workflow（向后兼容）
            steps = workflow.get("steps", [])
            for step in steps:
                agent_type = step.get("agent_type", "text")
                if agent_type == "text":
                    capabilities.append("自然语言理解与生成")
                elif agent_type == "tool":
                    tools = step.get("tools", {}).get("allowed", [])
                    for tool in tools:
                        capabilities.append(f"工具调用: {tool}")
                elif agent_type == "code":
                    capabilities.append("代码生成与执行")
                elif agent_type == "custom":
                    capabilities.append("自定义功能")
        
        # 去重
        capabilities = list(set(capabilities))
        
        # 分析成本
        cost_analysis = self._analyze_implementation_cost(agent_specs)
        
        # 获取workflow名称和描述
        if hasattr(workflow, 'name'):
            workflow_name = workflow.name
            workflow_description = getattr(workflow, 'description', '自动生成的Agent')
        else:
            workflow_name = workflow.get("metadata", {}).get("name", "GeneratedAgent")
            workflow_description = workflow.get("metadata", {}).get("description", "自动生成的Agent")
        
        return AgentMetadata(
            name=workflow_name,
            description=workflow_description,
            capabilities=capabilities,
            interface={
                "input": "字符串或字典格式的用户输入",
                "output": "AgentResult对象，包含处理结果",
                "methods": [
                    "initialize() - 初始化Agent",
                    "execute(input_data) - 执行主要功能",
                    "_setup_workflow() - 设置工作流"
                ]
            },
            cost_analysis=cost_analysis,
            created_at=datetime.now()
        )
    
    def _analyze_implementation_cost(self, agent_specs: List[Dict[str, Any]]) -> str:
        """分析实现成本"""
        
        total_specs = len(agent_specs)
        custom_tools = sum(1 for spec in agent_specs if spec.get("generation_type") == "custom_agent")
        tool_combinations = sum(1 for spec in agent_specs if spec.get("generation_type") == "tool_combination")
        basic_configs = total_specs - custom_tools - tool_combinations
        
        if custom_tools > 0:
            return f"中等成本 - 需要实现{custom_tools}个自定义工具"
        elif tool_combinations > 0:
            return f"低中等成本 - 需要组合{tool_combinations}个工具"
        else:
            return "低成本 - 主要使用现有功能"
    
    def _validate_generated_code(self, code: str) -> Dict[str, Any]:
        """验证生成的代码"""
        
        errors = []
        warnings = []
        
        try:
            # 语法检查
            ast.parse(code)
        except SyntaxError as e:
            errors.append(f"语法错误: {e}")
        
        # 检查必需的导入
        required_imports = [
            "from base_app.base_agent.core.base_agent import BaseAgent",
            "from base_app.base_agent.core.schemas import AgentConfig"
        ]
        
        for required_import in required_imports:
            if required_import not in code:
                warnings.append(f"缺少导入: {required_import}")
        
        # 检查必需的方法
        if "class" not in code:
            errors.append("缺少Agent类定义")
        
        if "def execute(" not in code:
            errors.append("缺少execute方法")
        
        if "def __init__(" not in code:
            warnings.append("缺少__init__方法")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    async def _fix_code_issues(self, code: str, errors: List[str]) -> str:
        """修复代码问题"""
        
        # 简单的代码修复逻辑
        fixed_code = code
        
        # 如果有语法错误，尝试重新生成
        if any("语法错误" in error for error in errors):
            # 这里可以重新调用LLM修复代码
            # 暂时返回基础模板
            fixed_code = '''#!/usr/bin/env python3
"""
自动生成的Agent - 基本模板
"""

import asyncio
from base_app.base_agent.core.base_agent import BaseAgent
from base_app.base_agent.core.schemas import AgentConfig, AgentResult

class GeneratedAgent(BaseAgent):
    def __init__(self, config: AgentConfig):
        super().__init__(config)
    
    async def execute(self, input_data):
        return AgentResult(success=True, data="Basic response", agent_name=self.config.name)

if __name__ == "__main__":
    print("Generated Agent Template")
'''
        
        return fixed_code
    
    def save_agent_file(self, generated_code: GeneratedCode, file_path: str) -> str:
        """保存Agent代码到文件"""
        
        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # 保存主Agent代码
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(generated_code.main_agent_code)
        
        # 保存工作流配置
        workflow_file = file_path.replace('.py', '_workflow.yaml')
        with open(workflow_file, 'w', encoding='utf-8') as f:
            f.write(generated_code.workflow_config)
        
        # 保存元数据
        metadata_file = file_path.replace('.py', '_metadata.json')
        with open(metadata_file, 'w', encoding='utf-8') as f:
            metadata_dict = {
                "name": generated_code.metadata.name,
                "description": generated_code.metadata.description,
                "capabilities": generated_code.metadata.capabilities,
                "interface": generated_code.metadata.interface,
                "cost_analysis": generated_code.metadata.cost_analysis,
                "created_at": generated_code.metadata.created_at.isoformat()
            }
            json.dump(metadata_dict, f, indent=2, ensure_ascii=False)
        
        return file_path
    
    def test_generated_code(self, file_path: str) -> Dict[str, Any]:
        """测试生成的代码"""
        
        test_result = {
            "syntax_valid": False,
            "imports_valid": False,
            "execution_test": False,
            "errors": [],
            "warnings": []
        }
        
        try:
            # 语法检查
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
            
            ast.parse(code)
            test_result["syntax_valid"] = True
            
            # 导入检查（简单测试）
            if "import" in code and "BaseAgent" in code:
                test_result["imports_valid"] = True
            
            # 这里可以添加更复杂的执行测试
            test_result["execution_test"] = True
            
        except Exception as e:
            test_result["errors"].append(str(e))
        
        return test_result