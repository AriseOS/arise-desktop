"""
RequirementParser - 使用大模型解析自然语言需求
"""

import json
import uuid
from typing import List, Dict, Any
from .schemas import ParsedRequirement, StepDesign, LLMConfig
from .tool_capability_analyzer import ToolCapabilityAnalyzer
from .providers import OpenAIProvider


class RequirementParser:
    """需求解析器 - 使用大模型解析自然语言需求"""
    
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
    
    async def parse_requirements(self, user_input: str) -> ParsedRequirement:
        """
        解析用户需求
        - 理解用户的整体需求
        - 提取Agent的核心目的
        - 识别业务流程
        """
        
        # 构建解析需求的prompt
        parse_prompt = self._build_parse_prompt(user_input)
        
        # 调用大模型进行需求解析
        response = await self._call_llm(parse_prompt)
        
        # 解析大模型返回的结果
        parsed_data = self._parse_llm_response(response)
        
        # 提取步骤设计
        steps = await self.extract_steps(user_input, parsed_data['agent_purpose'])
        
        return ParsedRequirement(
            original_text=user_input,
            agent_purpose=parsed_data['agent_purpose'],
            process_steps=steps
        )
    
    async def extract_steps(self, user_input: str, agent_purpose: str) -> List[StepDesign]:
        """
        提取执行步骤
        - 从需求中提取具体的执行步骤
        - 分析步骤间的逻辑关系
        """
        
        # 构建步骤提取的prompt
        steps_prompt = self._build_steps_prompt(user_input, agent_purpose)
        # logger.info("\n\n\nsteps_prompt\n")
        # logger.info(steps_prompt)
        print("\n\n\nsteps_prompt\n")
        print(steps_prompt)
        
        # 调用大模型进行步骤提取
        response = await self._call_llm(steps_prompt)
        
        # 解析步骤数据
        steps_data = self._parse_steps_response(response)
        # print("\n\n\nsteps_data\n")
        # print(steps_data)
        
        # 转换为StepDesign对象
        steps = []
        for step_data in steps_data:
            # 合并config和tool_implementation信息
            agent_config = step_data.get('config', {})
            tool_impl = step_data.get('tool_implementation', {})
            
            # 将工具实现信息加入配置
            agent_config.update({
                'tool_approach': tool_impl.get('approach', 'reuse_existing'),
                'existing_tools': tool_impl.get('existing_tools', []),
                'new_tool_requirements': tool_impl.get('new_tool_requirements', ''),
                'cost_analysis': tool_impl.get('cost_analysis', 'low'),
                'type_rationale': step_data.get('type_rationale', '')
            })
            
            step = StepDesign(
                step_id=str(uuid.uuid4()),
                name=step_data['name'],
                description=step_data['description'],
                agent_type=step_data.get('agent_type', 'text'),
                agent_config=agent_config
            )
            steps.append(step)
        
        return steps
    
    def _build_parse_prompt(self, user_input: str) -> str:
        """构建需求解析的prompt - 使用context engineering优化信息流"""
        return f"""# AI Agent需求分析专家

## 任务背景
你是一个专业的AI Agent需求分析师，专门将用户的自然语言需求转换为结构化的Agent设计规范。你需要准确理解用户意图，识别核心功能，并确定最适合的实现方式。

## 核心分析框架
基于用户需求，你需要分析以下关键维度：

### 1. 功能定位分析
- **主要功能**：Agent的核心能力是什么？
- **应用场景**：在什么情况下使用？
- **价值输出**：为用户创造什么价值？

### 2. 交互模式分析
- **输入类型**：用户会提供什么样的输入？
- **输出期望**：用户期望得到什么样的输出？
- **交互流程**：用户和Agent如何交互？

## 待分析的用户需求
```
{user_input}
```

## 输出要求
请基于以上分析框架，返回JSON格式的结构化分析结果：

```json
{{
    "agent_purpose": "Agent的核心目的和价值定位（简洁明确，突出核心功能）",
    "functional_scope": "Agent的功能边界和能力范围",
    "input_characteristics": "预期输入的特征和类型",
    "output_characteristics": "预期输出的特征和格式",
    "interaction_pattern": "用户与Agent的交互模式描述"
}}
```

## 关键要求
1. **准确性**：确保理解用户的真实意图，不要过度解读
2. **可操作性**：分析结果应该能够指导后续的Agent设计
3. **边界清晰**：明确Agent能做什么，不能做什么
4. **实现可行性**：考虑技术实现的可行性"""
    
    def _build_steps_prompt(self, user_input: str, agent_purpose: str) -> str:
        """构建步骤提取的prompt - 使用context engineering优化信息流"""
        
        # 获取现有工具能力摘要
        tools_summary = self.tool_analyzer.get_existing_tools_summary()
        
        return f"""# AI Agent工作流设计专家

## 任务背景
你是一个专业的AI Agent工作流设计师，专门将用户需求分解为可执行的工作流步骤。你需要基于用户需求、Agent目的和现有工具能力，设计出逻辑清晰、高效可执行且成本最优的工作流。

## 设计原则
### 1. 成本效益原则 (最重要)
- **优先复用现有工具**：能用现有工具解决的问题，不要重新实现
- **工具组合策略**：多个现有工具组合使用，优于实现新工具
- **实现成本评估**：新工具实现 > 工具组合 > 直接复用

### 2. 原子性原则
- 每个步骤都应该是独立、完整的任务单元
- 步骤之间有明确的输入输出关系
- 避免步骤过于复杂或功能重叠

### 3. 技术可行性原则
- 每个步骤都应该是技术上可实现的
- 考虑不同Agent类型的能力边界和限制
- 优化资源使用和执行效率

{tools_summary}

## Agent类型能力参考
### Text Agent
- **擅长**：自然语言理解、文本分析、内容生成、推理判断、决策制定
- **适用场景**：文本处理、问答、总结、分析、创作、逻辑推理
- **实现成本**：低 (无需额外开发)
- **限制**：无法直接操作外部系统或执行代码

### Tool Agent  
- **擅长**：调用外部API、搜索信息、数据获取、系统集成、自动化操作
- **适用场景**：信息检索、API调用、数据查询、外部服务交互、网页操作、设备控制
- **实现成本**：低到高 (取决于是否需要新工具)
- **限制**：依赖外部服务可用性和现有工具覆盖范围

### Code Agent
- **擅长**：代码生成、数据处理、计算分析、脚本执行、算法实现
- **适用场景**：数据分析、代码生成、计算任务、自动化脚本、数学计算
- **实现成本**：低到中 (代码生成相对简单)
- **限制**：需要明确的技术要求和输入规范

### Custom Agent
- **擅长**：特定领域的专业任务、复杂业务逻辑、多工具协调
- **适用场景**：需要专门定制的复杂任务、跨系统集成
- **实现成本**：高 (需要专门开发和测试)
- **限制**：需要额外的开发和配置，维护成本高

## 输入信息
### 用户原始需求
```
{user_input}
```

### Agent核心目的
```
{agent_purpose}
```

## 输出要求
基于以上信息，请设计一个清晰且成本最优的工作流步骤序列：

```json
{{
    "workflow_analysis": "对整个工作流的分析和设计思路，重点说明工具选择的成本考量",
    "steps": [
        {{
            "name": "步骤名称（简洁明确）",
            "description": "步骤的详细描述（包含输入、处理、输出）",
            "agent_type": "最适合的Agent类型：text/tool/code/custom",
            "type_rationale": "选择该Agent类型的原因和依据",
            "tool_implementation": {{
                "approach": "实现方案：reuse_existing/combine_existing/implement_new",
                "existing_tools": ["如果使用现有工具，列出具体工具名称"],
                "new_tool_requirements": "如果需要新工具，描述具体要求",
                "cost_analysis": "成本分析：low/medium/high，并说明原因"
            }},
            "config": {{
                "key_parameters": "关键配置参数",
                "expected_input": "期望的输入格式",
                "expected_output": "期望的输出格式"
            }}
        }}
    ],
    "data_flow": "描述步骤之间的数据流转关系",
    "overall_cost_assessment": "整体成本评估和优化建议"
}}
```

## 关键要求
1. **成本最优**：优先选择成本最低的实现方案
2. **完整性**：覆盖从输入到输出的完整流程
3. **可追溯性**：每个设计决策都有明确的理由和成本考量
4. **实用性**：确保设计的工作流能够实际执行并达到预期效果
5. **可扩展性**：为未来的功能扩展留有余地"""
    
    async def _call_llm(self, prompt: str, system_prompt: str = "") -> str:
        """调用真实的大模型API"""
        if not system_prompt:
            system_prompt = "你是一个专业的需求分析师，请严格按照要求的 JSON 格式回复。"
        
        return await self.provider.generate_response(system_prompt, prompt)
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """解析大模型返回的需求分析结果"""
        try:
            # 尝试提取JSON部分
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
            else:
                return json.loads(response)
        except json.JSONDecodeError:
            # 如果JSON解析失败，尝试提取关键信息
            return {
                "agent_purpose": "智能助手",
                "functional_scope": "处理用户请求",
                "input_characteristics": "自然语言输入",
                "output_characteristics": "文本回复",
                "interaction_pattern": "问答交互"
            }
    
    def _parse_steps_response(self, response: str) -> List[Dict[str, Any]]:
        """解析大模型返回的步骤提取结果"""
        try:
            # 尝试提取JSON部分
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
            else:
                data = json.loads(response)
            
            return data.get("steps", [])
        except json.JSONDecodeError:
            # 如果JSON解析失败，返回默认步骤
            return [
                {
                    "name": "处理请求",
                    "description": "处理用户输入的请求",
                    "agent_type": "text",
                    "type_rationale": "适合文本处理任务",
                    "config": {
                        "expected_input": "用户文本输入",
                        "expected_output": "处理结果"
                    }
                }
            ]