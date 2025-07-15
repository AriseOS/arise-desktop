# AgentBuilder 架构设计文档

## 设计概述

AgentBuilder 是一个基于 Agentic Code 技术的智能Agent生成系统，将自然语言需求转换为可执行的BaseAgent实例。系统采用简单的模块化设计，专注于核心功能的实现。

## 总体架构

### 1. 架构层次图

```
┌─────────────────────────────────────────────────────────────┐
│                    用户接口层                                 │
│                   自然语言输入                                │
└─────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────┐
│                  AgentBuilder 核心层                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐      │
│  │需求解析模块 │  │Agent设计模块 │  │   代码生成模块   │      │
│  │RequirementParser│ │AgentDesigner│ │  CodeGenerator  │      │
│  └─────────────┘  └─────────────┘  └─────────────────┘      │
│               ┌─────────────────┐                           │
│               │工作流组装模块    │                           │
│               │WorkflowBuilder  │                           │
│               └─────────────────┘                           │
└─────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────┐
│                   Agentic Code 集成层                        │
│                   AI 分析和生成                               │
└─────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────┐
│                   BaseAgent 基础层                           │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐  │
│  │  Agent Registry │  │ Workflow Engine │  │  Tool System │  │
│  └─────────────────┘  └─────────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 2. 核心组件关系图（基于实际实现）

```
                    ┌─────────────────┐
                    │  AgentBuilder   │
                    │   主控制器      │
                    └─────────┬───────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
 ┌──────▼─────────────┐  ┌───▼──────────┐  ┌────▼──────────────┐
 │RequirementParser   │  │AgentDesigner │  │  CodeGenerator    │
 │  智能需求解析      │  │ 智能设计器   │  │   代码生成器      │
 │  +LLM集成         │  │ +成本优化    │  │   +LLM集成       │
 └────────────────────┘  └──────────────┘  └───────────────────┘
           │                     │                    │
           └─────────────────────┼────────────────────┘
                                 │
 ┌───────────────────────────────▼───────────────────────────────┐
 │              ToolCapabilityAnalyzer               │
 │                工具能力分析器                     │
 │  +现有工具能力矩阵  +成本效益分析                 │
 └───────────────────────────────────────────────────┘
                                 │
                    ┌─────────▼────────┐
                    │ WorkflowBuilder  │
                    │  工作流组装器    │
                    │  (待实现)        │
                    └──────────────────┘
```

## 核心模块设计

### 1. AgentBuilder 主控制器（已实现核心组件）

```python
class AgentBuilder:
    """AgentBuilder 主控制器 - 协调整个Agent生成过程"""
    
    def __init__(self, llm_config: LLMConfig):
        # 已实现的核心组件
        self.requirement_parser = RequirementParser(llm_config)
        self.agent_designer = AgentDesigner(llm_config)
        # 待实现的组件
        self.workflow_builder = WorkflowBuilder()
        self.code_generator = CodeGenerator(llm_config)
    
    async def build_agent_from_description(self, user_description: str) -> GeneratedCode:
        """从自然语言描述构建Agent - 基于Context Engineering优化"""
        
        # 1. 智能需求解析（已实现）
        requirement = await self.requirement_parser.parse_requirements(user_description)
        
        # 2. 基于工具能力的步骤提取（已实现）
        steps = await self.requirement_parser.extract_steps(
            user_description, requirement.agent_purpose
        )
        
        # 3. 成本效益优化的Agent类型判断（已实现）
        agent_types = await self.agent_designer.judge_agent_types(steps)
        
        # 4. 按需生成StepAgent（已实现）
        step_agents = await self.agent_designer.generate_step_agents(steps)
        
        # 5. 组合Workflow（待实现）
        workflow = await self.workflow_builder.build_workflow(steps, step_agents)
        
        # 6. 注册Workflow（待实现）
        await self.workflow_builder.register_workflow(workflow)
        
        # 7. 生成BaseAgent兼容代码（待实现）
        generated_code = await self.code_generator.generate_agent_code(workflow, step_agents)
        
        return generated_code
```

### 2. 需求解析模块（已实现）

```python
class RequirementParser:
    """需求解析器 - 使用LLM和Context Engineering解析自然语言需求"""
    
    def __init__(self, llm_config: LLMConfig):
        self.llm_config = llm_config
        self.tool_analyzer = ToolCapabilityAnalyzer()
        self._setup_llm_client()
    
    async def parse_requirements(self, user_input: str) -> ParsedRequirement:
        """
        解析用户需求 - 使用Context Engineering优化的提示词
        - 理解用户的整体需求和业务目标
        - 分析功能定位、交互模式、输入输出特征
        - 确保实现可行性评估
        """
        # 使用优化的提示词进行深度分析
        parse_prompt = self._build_parse_prompt(user_input)
        response = await self._call_llm(parse_prompt)
        return self._parse_llm_response(response)
    
    async def extract_steps(self, user_input: str, agent_purpose: str) -> List[StepDesign]:
        """
        提取执行步骤 - 基于Context Engineering和工具能力分析
        - 结合现有工具能力矩阵进行成本敏感分解
        - 应用最优控制原则：复用 > 组合 > 实现
        - 提供每个步骤的成本效益分析
        """
        # 使用包含工具能力信息的优化提示词
        steps_prompt = self._build_steps_prompt(user_input, agent_purpose)
        response = await self._call_llm(steps_prompt)
        return self._parse_steps_response(response)
```

### 3. Agent设计模块（已实现）

```python
class AgentDesigner:
    """Agent设计器 - 智能判断Agent类型和生成StepAgent"""
    
    def __init__(self, llm_config: LLMConfig):
        self.llm_config = llm_config
        self.tool_analyzer = ToolCapabilityAnalyzer()
        self._setup_llm_client()
    
    async def judge_agent_types(self, steps: List[StepDesign]) -> Dict[str, str]:
        """
        判断Agent类型 - 基于成本效益的智能判断
        - 结合现有工具能力矩阵进行优化选择
        - 提供实现置信度和替代方案分析
        - 支持Text/Tool/Code/Custom四种类型
        """
        # 使用包含成本效益分析的优化提示词
        judgment_prompt = self._build_agent_type_judgment_prompt(steps)
        response = await self._call_llm(judgment_prompt)
        return self._parse_agent_type_judgment(response)
    
    async def generate_step_agents(self, steps: List[StepDesign]) -> List[Dict[str, Any]]:
        """
        生成StepAgent - 按需生成新的专用StepAgent
        - 基于工具实现方案生成相应规格
        - 只在必要时生成自定义Agent或工具组合
        - 提供详细的实现指导和配置信息
        """
        generated_agents = []
        for step in steps:
            tool_approach = step.agent_config.get('tool_approach', 'reuse_existing')
            if tool_approach == 'implement_new':
                agent_spec = await self._generate_custom_agent_spec(step)
            elif tool_approach == 'combine_existing':
                agent_spec = await self._generate_tool_combination_spec(step)
            else:
                agent_spec = self._generate_basic_agent_spec(step)
            generated_agents.append(agent_spec)
        return generated_agents
```

### 4. 工作流组装模块

```python
class WorkflowBuilder:
    """工作流组装器 - 将steps组合成完整的Workflow"""
    
    async def build_workflow(self, steps: List[StepDesign], agents: List[StepAgent]) -> Workflow:
        """
        构建工作流
        - 将steps组合成完整的Workflow
        - 配置步骤间的数据流转
        """
        # 使用BaseAgent的workflow_builder接口
        pass
    
    async def register_workflow(self, workflow: Workflow) -> None:
        """
        注册工作流
        - 将Workflow注册到BaseAgent系统
        - 配置工作流的元数据
        """
        # 使用BaseAgent的workflow注册接口
        pass
```

### 5. 代码生成模块

```python
class CodeGenerator:
    """代码生成器 - 生成BaseAgent兼容的Python代码"""
    
    async def generate_agent_code(self, workflow: Workflow, agents: List[StepAgent]) -> GeneratedCode:
        """
        生成Agent代码
        - 生成继承自BaseAgent的Python类
        - 生成工作流配置文件
        """
        # 调用Agentic Code生成代码
        pass
    
    async def generate_metadata(self, workflow: Workflow) -> AgentMetadata:
        """
        生成Agent元数据
        - 生成Agent的功能描述
        - 生成接口定义和使用说明
        """
        # 生成标准化的元数据
        pass
```

## 数据结构设计

### 1. 核心数据结构

```python
@dataclass
class ParsedRequirement:
    """解析后的需求"""
    original_text: str                    # 原始需求文本
    agent_purpose: str                    # Agent目的
    process_steps: List[StepDesign]       # 执行步骤

@dataclass
class StepDesign:
    """步骤设计"""
    step_id: str                         # 步骤ID
    name: str                            # 步骤名称
    description: str                     # 步骤描述
    agent_type: str                      # Agent类型：text/tool/code/custom
    agent_config: Dict[str, Any]         # Agent配置参数

@dataclass
class GeneratedCode:
    """生成的代码"""
    main_agent_code: str                 # 主Agent类代码
    workflow_config: str                 # 工作流配置文件
    metadata: AgentMetadata              # Agent元数据
    
@dataclass
class AgentMetadata:
    """Agent元数据"""
    name: str                            # Agent名称
    description: str                     # Agent描述
    capabilities: List[str]              # 能力列表
    interface: Dict[str, Any]            # 接口定义
```

## 与BaseAgent集成

### 1. 使用BaseAgent接口

```python
# 生成的Agent需要继承BaseAgent
class GeneratedAgent(BaseAgent):
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        # 加载生成的workflow
        self.workflow = self.load_workflow("generated_workflow.yaml")
    
    async def execute(self, input_data: Any) -> AgentResult:
        # 执行生成的workflow
        result = await self.run_workflow(self.workflow, input_data)
        return result
```

### 2. 工作流配置格式

```yaml
# generated_workflow.yaml
name: "Generated Agent Workflow"
description: "Auto-generated workflow"
steps:
  - id: "step1"
    name: "理解问题"
    agent_type: "text_agent"
    agent_instruction: "分析用户输入，理解问题意图"
    
  - id: "step2"
    name: "生成回答"
    agent_type: "text_agent"
    agent_instruction: "根据问题生成合适的回答"
```

## 实现策略

### 1. 阶段化实现

**Phase 1: 基础功能**
- 实现RequirementParser的基本需求解析
- 实现AgentDesigner的简单Agent类型判断
- 实现WorkflowBuilder的基本workflow组装
- 实现CodeGenerator的基本代码生成

**Phase 2: 集成优化**
- 集成Agentic Code技术
- 完善与BaseAgent的接口集成
- 优化代码生成质量

### 2. 技术选型

- **自然语言处理**: 使用Agentic Code技术
- **代码生成**: 基于字符串模板和代码拼接
- **工作流引擎**: 复用BaseAgent的workflow_builder
- **数据结构**: 使用Python dataclass

## 技术要点

### 1. 与BaseAgent的集成
- 生成的Agent必须继承BaseAgent
- 使用BaseAgent的workflow系统
- 遵循BaseAgent的接口规范

### 2. 代码生成策略
- 使用字符串模板生成Python代码
- 生成标准的YAML工作流配置
- 确保生成的代码符合Python语法规范

### 3. 质量保证
- 对生成的代码进行语法检查
- 验证workflow配置的正确性
- 提供清晰的错误信息和调试支持

## 成功标准

### 功能性标准
- 能够解析简单的自然语言需求
- 能够生成可执行的BaseAgent代码
- 能够正确判断Agent类型（Text/Tool/Code/Custom）
- 能够组装和注册Workflow

### 质量标准
- 生成的代码能够在BaseAgent框架中正确运行
- 生成的Agent符合BaseAgent接口规范
- 提供清晰的Agent元数据和文档
- 系统具有良好的错误处理和日志记录