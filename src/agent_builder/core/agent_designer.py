"""
AgentDesigner - 使用大模型进行Agent类型判断和StepAgent生成
"""

import json
import uuid
from typing import List, Dict, Any, Tuple
from .schemas import StepDesign, LLMConfig
from .tool_capability_analyzer import ToolCapabilityAnalyzer, ToolGapAnalysis
from .providers import OpenAIProvider


class AgentDesigner:
    """Agent设计器 - 智能判断Agent类型和生成StepAgent"""
    
    def __init__(self, llm_config: LLMConfig):
        self.llm_config = llm_config
        self.tool_analyzer = ToolCapabilityAnalyzer()
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
    
    async def judge_agent_types(self, steps: List[StepDesign]) -> Dict[str, str]:
        """判断每个步骤需要的Agent类型（Text/Tool/Code/Custom）"""
        
        # 构建Agent类型判断的prompt
        judgment_prompt = self._build_agent_type_judgment_prompt(steps)
        
        # 调用大模型进行判断
        response = await self._call_llm(judgment_prompt)
        
        # 解析判断结果
        judgment_result = self._parse_agent_type_judgment(response)
        
        return judgment_result
    
    async def generate_step_agents(self, steps: List[StepDesign]) -> List[Dict[str, Any]]:
        """生成符合BaseAgent要求的精确Step配置，支持变量链条"""
        
        generated_agents = []
        available_variables = ["user_input"]  # 跟踪可用变量
        
        for i, step in enumerate(steps):
            # 构建可用变量上下文信息
            context_info = self._build_variable_context(available_variables, i, len(steps))
            
            # 根据Agent类型调用大模型生成具体配置（传入上下文信息）
            if step.agent_type in ['text', 'text_agent']:
                agent_spec = await self._generate_text_agent_config(step, i, len(steps), context_info)
            elif step.agent_type in ['tool', 'tool_agent']:
                agent_spec = await self._generate_tool_agent_config(step, i, len(steps), context_info)
            elif step.agent_type in ['code', 'code_agent']:
                agent_spec = await self._generate_code_agent_config(step, i, len(steps), context_info)
            else:
                # 自定义Agent
                agent_spec = await self._generate_custom_agent_config(step, i, len(steps), context_info)
            
            # 更新可用变量列表
            outputs = agent_spec.get('baseagent_config', {}).get('outputs', {})
            available_variables.extend(outputs.values())
            
            generated_agents.append(agent_spec)
            
        print("generated_agents\n")
        print(generated_agents) 
        return generated_agents
    
    async def _generate_text_agent_config(self, step: StepDesign, step_index: int, total_steps: int, variable_context: str) -> Dict[str, Any]:
        """生成TextAgent的BaseAgent配置"""
        
        # 构建LLM分析prompt
        prompt = f"""# BaseAgent TextAgent配置专家

## 任务
为以下工作流步骤生成精确的BaseAgent TextAgent配置参数。

## 步骤信息
- 步骤名称: {step.name}
- 步骤描述: {step.description}
- 步骤位置: 第{step_index + 1}步，共{total_steps}步
- 现有配置: {step.agent_config}

{variable_context}

## AgentWorkflowStep完整字段要求
需要生成完整的AgentWorkflowStep兼容配置，包括：

### 基础字段:
- name: 步骤名称
- description: 步骤描述  
- agent_type: Agent类型
- agent_instruction: Agent执行指令
- user_task: 用户具体任务内容(可选)

### 输入输出配置:
- inputs: 输入映射配置（使用{{{{变量名}}}}格式引用变量）
- outputs: 输出映射配置（定义要存储的变量名）
- constraints: 约束条件列表

### Text Agent特有字段:
- response_style: 响应风格
- max_length: 最大响应长度

### 执行控制:
- condition: 执行条件(可选)
- timeout: 超时时间
- retry_count: 重试次数

## 输出要求
严格按照以下JSON格式输出，注意inputs使用变量引用格式：

```json
{{
    "step_id": "step_{step_index + 1}",
    "agent_type": "text_agent",
    "baseagent_config": {{
        "name": "步骤名称",
        "description": "步骤描述",
        "agent_type": "text_agent",
        "agent_instruction": "具体的Agent执行指令",
        "user_task": "用户具体任务内容或null",
        "inputs": {{"field_name": "{{{{variable_name}}}}"}},
        "outputs": {{"field_name": "variable_to_store"}},
        "constraints": ["约束条件列表"],
        "response_style": "professional/casual/technical",
        "max_length": 数值,
        "condition": null,
        "timeout": 数值,
        "retry_count": 数值
    }}
}}
```"""

        response = await self._call_llm(prompt)
        return self._parse_agent_config_response(response, step.step_id)
    
    async def _generate_tool_agent_config(self, step: StepDesign, step_index: int, total_steps: int, variable_context: str) -> Dict[str, Any]:
        """生成ToolAgent的BaseAgent配置"""
        
        existing_tools = step.agent_config.get('existing_tools', [])
        
        prompt = f"""# BaseAgent ToolAgent配置专家

## 任务
为以下工作流步骤生成精确的BaseAgent ToolAgent配置参数。

## 步骤信息
- 步骤名称: {step.name}
- 步骤描述: {step.description}
- 步骤位置: 第{step_index + 1}步，共{total_steps}步
- 现有工具: {existing_tools}
- 工具策略: {step.agent_config.get('tool_approach', 'reuse_existing')}

{variable_context}

## AgentWorkflowStep完整字段要求
需要生成完整的AgentWorkflowStep兼容配置，包括：

### 基础字段:
- name: 步骤名称
- description: 步骤描述  
- agent_type: Agent类型
- agent_instruction: Agent执行指令
- user_task: 用户具体任务内容(可选)

### 输入输出配置:
- inputs: 输入映射配置（使用{{{{变量名}}}}格式引用变量）
- outputs: 输出映射配置（定义要存储的变量名）
- constraints: 约束条件列表

### Tool Agent特有字段:
- allowed_tools: 允许使用的工具列表 (注意:字段名是allowed_tools,不是tools)
- fallback_tools: 备选工具列表
- confidence_threshold: 置信度阈值

### 执行控制:
- condition: 执行条件(可选)
- timeout: 超时时间
- retry_count: 重试次数

## 可用工具列表参考
常见工具: browser_use, web_search, file_manager, data_processor, email_sender

## 输出要求
严格按照以下JSON格式输出，注意inputs使用变量引用格式：

```json
{{
    "step_id": "step_{step_index + 1}",
    "agent_type": "tool_agent",
    "baseagent_config": {{
        "name": "步骤名称",
        "description": "步骤描述",
        "agent_type": "tool_agent",
        "agent_instruction": "具体的Agent执行指令",
        "user_task": "用户具体任务内容或null",
        "inputs": {{"field_name": "{{{{variable_name}}}}"}},
        "outputs": {{"field_name": "variable_to_store"}},
        "constraints": ["约束条件列表"],
        "allowed_tools": ["工具名称列表"],
        "fallback_tools": ["备选工具列表"],
        "confidence_threshold": 0.8,
        "condition": null,
        "timeout": 数值,
        "retry_count": 数值
    }}
}}
```"""

        response = await self._call_llm(prompt)
        return self._parse_agent_config_response(response, step.step_id)
    
    async def _generate_code_agent_config(self, step: StepDesign, step_index: int, total_steps: int, variable_context: str) -> Dict[str, Any]:
        """生成CodeAgent的BaseAgent配置"""
        
        allowed_libraries = step.agent_config.get('allowed_libraries', [])
        
        prompt = f"""# BaseAgent CodeAgent配置专家

## 任务
为以下工作流步骤生成精确的BaseAgent CodeAgent配置参数。

## 步骤信息
- 步骤名称: {step.name}
- 步骤描述: {step.description}
- 步骤位置: 第{step_index + 1}步，共{total_steps}步
- 建议库: {allowed_libraries}

{variable_context}

## AgentWorkflowStep完整字段要求
需要生成完整的AgentWorkflowStep兼容配置，包括：

### 基础字段:
- name: 步骤名称
- description: 步骤描述  
- agent_type: Agent类型
- agent_instruction: Agent执行指令
- user_task: 用户具体任务内容(可选)

### 输入输出配置:
- inputs: 输入映射配置（使用{{{{变量名}}}}格式引用变量）
- outputs: 输出映射配置（定义要存储的变量名）
- constraints: 约束条件列表

### Code Agent特有字段:
- allowed_libraries: 允许使用的代码库列表 (注意:字段名是allowed_libraries,不是libraries)
- expected_output_format: 期望的输出格式

### 执行控制:
- condition: 执行条件(可选)
- timeout: 超时时间
- retry_count: 重试次数

## 常用库参考
数据处理: pandas, numpy, json, csv
可视化: matplotlib, seaborn, plotly
网络: requests, urllib, httpx
文本: re, string, nltk

## 输出要求
严格按照以下JSON格式输出，注意inputs使用变量引用格式：

```json
{{
    "step_id": "step_{step_index + 1}",
    "agent_type": "code_agent",
    "baseagent_config": {{
        "name": "步骤名称",
        "description": "步骤描述",
        "agent_type": "code_agent",
        "agent_instruction": "具体的Agent执行指令",
        "user_task": "用户具体任务内容或null",
        "inputs": {{"field_name": "{{{{variable_name}}}}"}},
        "outputs": {{"field_name": "variable_to_store"}},
        "constraints": ["约束条件列表"],
        "allowed_libraries": ["库名称列表"],
        "expected_output_format": "输出格式描述",
        "condition": null,
        "timeout": 数值,
        "retry_count": 数值
    }}
}}
```"""

        response = await self._call_llm(prompt)
        return self._parse_agent_config_response(response, step.step_id)
    
    async def _generate_custom_agent_config(self, step: StepDesign, step_index: int, total_steps: int, variable_context: str) -> Dict[str, Any]:
        """生成自定义Agent的BaseAgent配置"""
        
        prompt = f"""# BaseAgent 自定义Agent配置专家

## 任务
为以下工作流步骤生成精确的BaseAgent自定义Agent配置参数。

## 步骤信息
- 步骤名称: {step.name}
- 步骤描述: {step.description}
- 步骤位置: 第{step_index + 1}步，共{total_steps}步
- Agent类型: {step.agent_type}

{variable_context}

## AgentWorkflowStep完整字段要求
需要生成完整的AgentWorkflowStep兼容配置，包括：

### 基础字段:
- name: 步骤名称
- description: 步骤描述  
- agent_type: Agent类型
- agent_instruction: Agent执行指令
- user_task: 用户具体任务内容(可选)

### 输入输出配置:
- inputs: 输入映射配置（使用{{{{变量名}}}}格式引用变量）
- outputs: 输出映射配置（定义要存储的变量名）
- constraints: 约束条件列表

### 执行控制:
- condition: 执行条件(可选)
- timeout: 超时时间
- retry_count: 重试次数

## 输出要求
严格按照以下JSON格式输出，注意inputs使用变量引用格式：

```json
{{
    "step_id": "step_{step_index + 1}",
    "agent_type": "{step.agent_type}",
    "baseagent_config": {{
        "name": "步骤名称",
        "description": "步骤描述",
        "agent_type": "{step.agent_type}",
        "agent_instruction": "具体的Agent执行指令",
        "user_task": "用户具体任务内容或null",
        "inputs": {{"field_name": "{{{{variable_name}}}}"}},
        "outputs": {{"field_name": "variable_to_store"}},
        "constraints": ["约束条件列表"],
        "condition": null,
        "timeout": 数值,
        "retry_count": 数值
    }}
}}
```"""

        response = await self._call_llm(prompt)
        return self._parse_agent_config_response(response, step.step_id)
    
    def _parse_agent_config_response(self, response: str, step_id: str) -> Dict[str, Any]:
        """解析LLM返回的Agent配置"""
        print("stepAgent response: \n ")
        print(response)
        try:
            # 提取JSON部分
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_str = response[json_start:json_end]
                config = json.loads(json_str)
                return config
            else:
                raise ValueError("No valid JSON found")
        except (json.JSONDecodeError, ValueError) as e:
            # 如果解析失败，返回基础配置
            return {
                "step_id": step_id,
                "agent_type": "text_agent",
                "baseagent_config": {
                    "agent_instruction": "执行文本处理任务",
                    "response_style": "professional",
                    "max_length": 500,
                    "timeout": 300,
                    "retry_count": 0,
                    "condition": None
                },
                "parse_error": str(e),
                "raw_response": response
            }
    
    def _build_agent_type_judgment_prompt(self, steps: List[StepDesign]) -> str:
        """构建Agent类型判断的prompt"""
        
        # 获取现有工具能力摘要
        tools_summary = self.tool_analyzer.get_existing_tools_summary()
        
        # 构建步骤信息
        steps_info = []
        for i, step in enumerate(steps):
            step_info = {
                "step_index": i + 1,
                "name": step.name,
                "description": step.description,
                "current_agent_type": step.agent_type,
                "tool_approach": step.agent_config.get('tool_approach', 'reuse_existing'),
                "existing_tools": step.agent_config.get('existing_tools', []),
                "cost_analysis": step.agent_config.get('cost_analysis', 'low')
            }
            steps_info.append(step_info)
        
        steps_json = json.dumps(steps_info, indent=2, ensure_ascii=False)
        
        return f"""# Agent类型优化专家

## 任务背景
你是一个专业的Agent类型优化专家，负责根据具体的步骤需求和现有工具能力，确定每个步骤的最优Agent类型和实现方案。你需要基于成本效益分析，确保选择最合适的Agent类型。

## 优化原则
### 1. 成本效益最优化
- **Text Agent**: 成本最低，适合纯文本处理、推理、分析任务
- **Tool Agent**: 成本取决于工具复杂度，适合需要外部交互的任务
- **Code Agent**: 中等成本，适合计算、数据处理、算法实现
- **Custom Agent**: 成本最高，仅在无法通过其他方式实现时使用

### 2. 能力匹配原则
- 选择的Agent类型必须能够完成所需任务
- 避免过度设计，不要选择能力过剩的Agent类型
- 考虑Agent之间的数据传递和协作

### 3. 技术可行性原则
- 确保所选Agent类型在技术上可行
- 考虑现有工具的覆盖范围和质量
- 评估实现难度和维护成本

{tools_summary}

## 当前步骤分析
以下是当前设计的工作流步骤：

```json
{steps_json}
```

## 输出要求
基于以上信息，请对每个步骤的Agent类型选择进行优化和验证：

```json
{{
    "optimization_analysis": "整体优化分析和建议",
    "step_judgments": [
        {{
            "step_index": 1,
            "recommended_agent_type": "text/tool/code/custom",
            "optimization_rationale": "优化理由和成本效益分析",
            "implementation_confidence": "实现置信度：high/medium/low",
            "alternative_approaches": [
                {{
                    "agent_type": "备选Agent类型",
                    "pros": ["优点列表"],
                    "cons": ["缺点列表"],
                    "cost_comparison": "成本比较"
                }}
            ],
            "tool_requirements": {{
                "approach": "reuse_existing/combine_existing/implement_new",
                "specific_tools": ["具体工具名称"],
                "custom_requirements": "自定义需求描述",
                "estimated_effort": "预估工作量：low/medium/high"
            }}
        }}
    ],
    "overall_recommendations": "整体建议和潜在风险",
    "cost_benefit_summary": "成本效益总结"
}}
```

## 关键要求
1. **成本敏感性**：始终选择成本效益最优的方案
2. **技术可行性**：确保推荐的方案可以实际实现
3. **系统一致性**：考虑Agent之间的协作和数据流
4. **风险评估**：识别潜在的技术风险和实现难点
5. **可扩展性**：为未来的功能扩展留有余地"""
    
    async def _generate_custom_agent_spec(self, step: StepDesign) -> Dict[str, Any]:
        """生成自定义Agent的详细规格"""
        
        prompt = self._build_custom_agent_generation_prompt(step)
        response = await self._call_llm(prompt)
        
        try:
            spec = json.loads(response)
            return {
                "step_id": step.step_id,
                "agent_type": "custom",
                "generation_type": "custom_agent",
                "specification": spec
            }
        except json.JSONDecodeError:
            return {
                "step_id": step.step_id,
                "agent_type": "custom",
                "generation_type": "custom_agent",
                "specification": {
                    "error": "Failed to parse custom agent specification",
                    "raw_response": response
                }
            }
    
    def _build_custom_agent_generation_prompt(self, step: StepDesign) -> str:
        """构建自定义Agent生成的prompt"""
        
        new_tool_requirements = step.agent_config.get('new_tool_requirements', '')
        
        return f"""# 自定义Agent规格设计专家

## 任务背景
你需要为一个特定的工作流步骤设计一个自定义Agent的详细规格。这个Agent需要实现现有工具无法覆盖的特定功能。

## 步骤信息
- **步骤名称**: {step.name}
- **步骤描述**: {step.description}
- **新工具需求**: {new_tool_requirements}
- **成本分析**: {step.agent_config.get('cost_analysis', 'high')}

## 设计要求
基于BaseAgent架构，设计一个自定义Agent的完整规格：

```json
{{
    "agent_name": "自定义Agent的名称",
    "agent_description": "Agent的详细描述",
    "base_class": "BaseAgent或其他基类",
    "required_capabilities": [
        "需要实现的核心能力列表"
    ],
    "tool_requirements": [
        {{
            "tool_name": "需要的工具名称",
            "tool_description": "工具功能描述",
            "implementation_approach": "实现方法",
            "complexity": "low/medium/high"
        }}
    ],
    "interface_specification": {{
        "input_schema": "输入数据结构",
        "output_schema": "输出数据结构",
        "error_handling": "错误处理策略"
    }},
    "implementation_guidance": {{
        "key_methods": ["需要实现的关键方法"],
        "dependencies": ["依赖的库或服务"],
        "testing_strategy": "测试策略",
        "performance_considerations": "性能考虑"
    }},
    "integration_notes": "与BaseAgent框架集成的注意事项"
}}
```

## 关键要求
1. **符合BaseAgent架构**：确保设计符合现有框架
2. **实现可行性**：确保设计可以实际实现
3. **性能优化**：考虑性能和资源使用
4. **维护友好**：设计易于维护和扩展的结构"""
    
    async def _generate_tool_combination_spec(self, step: StepDesign) -> Dict[str, Any]:
        """生成工具组合的详细规格"""
        
        existing_tools = step.agent_config.get('existing_tools', [])
        
        return {
            "step_id": step.step_id,
            "agent_type": "tool",
            "generation_type": "tool_combination",
            "specification": {
                "combination_strategy": "sequential",
                "tools_to_combine": existing_tools,
                "orchestration_logic": f"Orchestrate tools for: {step.description}",
                "data_flow": "Define data flow between tools",
                "error_handling": "Handle errors in tool combination"
            }
        }
    
    def _build_variable_context(self, available_variables: List[str], step_index: int, total_steps: int) -> str:
        """构建可用变量的上下文信息"""
        
        if step_index == 0:
            # 第一个Agent根据实际情况定义
            return """## 输入数据
- {{user_input}}: 用户输入的原始消息

## 变量引用格式
输入引用: \"field_name\": \"{{variable_name}}\"
输出定义: \"field_name\": \"variable_to_store_as\"

## 示例
\"inputs\": {
  \"user_question\": \"{{user_input}}\"
},
\"outputs\": {
  \"result\": \"step1_output\",
  \"metadata\": \"step1_metadata\"
}

请根据当前步骤的实际业务逻辑定义合适的输出变量。"""
        
        if not available_variables or len(available_variables) <= 1:
            return """## 输入数据
- {{user_input}}: 用户输入的原始消息

## 变量引用格式
输入引用: \"field_name\": \"{{variable_name}}\"
输出定义: \"field_name\": \"variable_to_store_as\"

请根据当前步骤的业务逻辑，智能选择需要的输入变量。"""
        
        context = """## 可用的上下文变量（根据业务需要选择使用）:
- {{user_input}}: 工作流初始输入
"""
        
        for var in available_variables[1:]:  # 跳过user_input
            context += f"- {{{{{var}}}}}: 前序步骤的输出数据\n"
        
        context += """
## 变量引用格式示例
输入引用: \"field_name\": \"{{source_variable}}\"
输出定义: \"field_name\": \"target_variable_name\"

## 实际示例
\"inputs\": {
  \"user_question\": \"{{user_input}}\",
  \"analysis_result\": \"{{step1_analysis}}\"
},
\"outputs\": {
  \"tool_result\": \"step2_output\",
  \"confidence\": \"step2_confidence\"
}

请根据当前步骤的业务逻辑，智能选择需要的输入变量。
无需强制使用所有变量，只选择对当前任务有意义的变量。"""
        
        return context
    
    def _generate_basic_agent_spec(self, step: StepDesign) -> Dict[str, Any]:
        """生成基本Agent的配置规格"""
        
        return {
            "step_id": step.step_id,
            "agent_type": step.agent_type,
            "generation_type": "basic_config",
            "specification": {
                "configuration": step.agent_config,
                "instructions": step.description,
                "parameters": step.agent_config.get('key_parameters', ''),
                "expected_behavior": f"Execute step: {step.name}"
            }
        }
    
    async def _call_llm(self, prompt: str, system_prompt: str = "") -> str:
        """调用真实的大模型API"""
        if not system_prompt:
            system_prompt = "你是一个专业的 Agent 设计师，请严格按照要求的 JSON 格式回复。"
        
        return await self.provider.generate_response(system_prompt, prompt)
    
    def _parse_agent_type_judgment(self, response: str) -> Dict[str, str]:
        """解析Agent类型判断结果"""
        try:
            # 尝试提取JSON部分
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
            else:
                data = json.loads(response)
            
            # 提取每个步骤的推荐Agent类型
            result = {}
            for judgment in data.get("step_judgments", []):
                step_index = judgment.get("step_index", 0)
                agent_type = judgment.get("recommended_agent_type", "text")
                result[f"step_{step_index}"] = agent_type
            
            return result
        except json.JSONDecodeError:
            # 如果解析失败，返回默认值
            return {"step_1": "text", "step_2": "text"}