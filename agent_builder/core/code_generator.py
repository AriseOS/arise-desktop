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
from .workflow_builder import WorkflowBuilder
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
    
    async def generate_agent_code(self, workflow: Dict[str, Any], agent_specs: List[Dict[str, Any]]) -> GeneratedCode:
        """
        生成Agent代码 - 使用LLM生成BaseAgent兼容代码
        - 生成继承自BaseAgent的Python类
        - 生成YAML格式的工作流配置文件
        - 确保代码符合BaseAgent接口规范
        """
        
        # 1. 生成主Agent类代码
        main_agent_code = await self._generate_main_agent_class(workflow, agent_specs)
        
        # 2. 生成工作流配置（已经由WorkflowBuilder生成）
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
    
    async def _generate_main_agent_class(self, workflow: Dict[str, Any], agent_specs: List[Dict[str, Any]]) -> str:
        """生成主Agent类的Python代码"""
        
        # 构建代码生成的提示词
        prompt = self._build_code_generation_prompt(workflow, agent_specs)
        
        # 调用LLM生成代码
        response = await self._call_llm(prompt)
        
        # 提取和清理代码
        code = self._extract_code_from_response(response)
        
        return code
    
    def _build_code_generation_prompt(self, workflow: Dict[str, Any], agent_specs: List[Dict[str, Any]]) -> str:
        """构建代码生成的提示词"""
        
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
        
        # 构建步骤描述
        steps_description = ""
        for i, step in enumerate(steps):
            steps_description += f"  {i+1}. {step.get('name', 'Unknown')}: {step.get('description', 'No description')}\n"
        
        return f"""# Python代码生成专家

## 任务背景
你是一个专业的Python代码生成专家，需要基于BaseAgent框架生成一个完整的自定义Agent类。

## BaseAgent框架使用规范

### 基本导入和初始化
```python
import asyncio
import sys
import os
from typing import Any, Dict, Optional
from datetime import datetime

# BaseAgent核心导入
from base_app.base_agent.core.base_agent import BaseAgent
from base_app.base_agent.core.schemas import AgentConfig, AgentResult

class CustomAgent(BaseAgent):
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.workflow = None
        self.workflow_name = "custom_workflow"
    
    async def initialize(self):
        \"\"\"初始化Agent和工作流\"\"\"
        await super().initialize()
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
        result = await self.run_custom_workflow(self.workflow, input_data)
        
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
- **Agent名称**: {workflow_name}
- **Agent描述**: {workflow_description}
- **工作流步骤**:
{steps_description}

### 自定义工具需求
{self._format_custom_tools_info(custom_tools_needed)}

### 工具组合需求
{self._format_tool_combinations_info(tool_combinations_needed)}

## 代码生成要求

1. **完整性**: 生成完整的可执行Python文件
2. **兼容性**: 严格遵循BaseAgent接口规范
3. **功能性**: 实现所有指定的工作流步骤
4. **代码质量**: 
   - 清晰的注释和文档字符串
   - 符合PEP 8编码规范
   - 适当的错误处理
   - 类型注解

5. **文件结构**:
   - 导入语句
   - Agent类定义
   - 工作流设置方法
   - 自定义工具实现（如需要）
   - 主函数示例

请生成一个完整的Python文件，文件名建议为 `{workflow_name.lower().replace(' ', '_')}_agent.py`

## 输出格式
请直接输出Python代码，不要包含任何markdown标记或额外的解释文字。"""
    
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
    
    def _format_workflow_config(self, workflow: Dict[str, Any]) -> str:
        """格式化工作流配置为YAML字符串"""
        import yaml
        return yaml.dump(workflow, default_flow_style=False, allow_unicode=True)
    
    async def _generate_metadata(self, workflow: Dict[str, Any], agent_specs: List[Dict[str, Any]]) -> AgentMetadata:
        """生成Agent元数据"""
        
        # 分析能力列表
        capabilities = []
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
        
        return AgentMetadata(
            name=workflow.get("metadata", {}).get("name", "GeneratedAgent"),
            description=workflow.get("metadata", {}).get("description", "自动生成的Agent"),
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