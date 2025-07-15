# AgentBuilder 需求分析文档

## 概述

AgentBuilder 是一个智能Agent生成系统，接受用户的自然语言描述，通过先进的LLM技术和context engineering原则解析需求，生成包含完整工作流和按需生成的StepAgent的新Agent。该系统基于现有的BaseAgent架构，遵循成本效益最优化的实现策略。

## 设计原则

### 1. Context Engineering 优化原则
- **最优信息流**：精心设计LLM提示词，确保提供关键信息获得最佳结果
- **成本效益分析**：每个决策都基于成本效益考虑
- **智能工具选择**：优先复用现有工具 > 组合工具 > 实现新工具

### 2. 最优控制理论应用
- **决策优化**：基于现有工具能力矩阵进行智能决策
- **资源配置**：最小化实现成本，最大化功能价值
- **风险控制**：评估技术可行性和实现复杂度

## 核心需求

### 1. 智能需求解析
- **深度理解**：使用LLM深度理解用户的整体需求和业务目标
- **结构化提取**：将自然语言转换为结构化的Agent设计
- **上下文保持**：在整个分析链中保持完整的上下文信息

### 2. 成本敏感的Agent类型判断
- **智能判断**：基于工具能力矩阵判断最优Agent类型（Text/Tool/Code/Custom）
- **成本分析**：评估不同实现方案的成本效益
- **按需生成**：只在必要时生成新的专用StepAgent

### 3. 工具能力分析
- **现有工具评估**：分析现有工具的能力覆盖范围
- **差距识别**：识别功能差距和实现需求
- **方案推荐**：基于成本效益推荐最优实现方案

### 4. Workflow智能组合
- **步骤组合**：将steps组合成逻辑清晰的Workflow
- **数据流设计**：确保步骤间的数据正确传递
- **Workflow注册**：将组装好的Workflow进行注册

### 5. 代码生成
- **BaseAgent兼容代码**：生成配合BaseAgent可以运行的Python代码
- **Agent元数据**：生成Agent的功能描述和接口定义

## 详细功能需求

### 1. 需求解析器 (RequirementParser)
```python
class RequirementParser:
    """需求解析器 - 使用LLM和context engineering解析自然语言需求"""
    
    def __init__(self, llm_config: LLMConfig):
        self.llm_config = llm_config
        self.tool_analyzer = ToolCapabilityAnalyzer()
    
    async def parse_requirements(self, user_input: str) -> ParsedRequirement:
        """解析用户需求 - 使用优化的提示词进行深度理解"""
        # 使用context engineering优化的提示词
        # 理解用户的整体需求、功能定位、交互模式
        pass
    
    async def extract_steps(self, user_input: str, agent_purpose: str) -> List[StepDesign]:
        """提取执行步骤 - 基于现有工具能力进行智能分解"""
        # 结合工具能力矩阵，进行成本敏感的步骤设计
        # 优化信息流，确保LLM获得最佳决策信息
        pass
```

### 2. 工具能力分析器 (ToolCapabilityAnalyzer)
```python
class ToolCapabilityAnalyzer:
    """工具能力分析器 - 分析现有工具能力并支持新工具需求识别"""
    
    def get_existing_tools_summary(self) -> str:
        """获取现有工具能力摘要 - 为LLM提供工具选择依据"""
        pass
    
    def analyze_tool_requirements(self, step_requirement: str) -> ToolGapAnalysis:
        """分析步骤需求的工具实现方案"""
        pass
```

### 3. Agent设计器 (AgentDesigner)
```python
class AgentDesigner:
    """Agent设计器 - 智能判断Agent类型和生成StepAgent"""
    
    def __init__(self, llm_config: LLMConfig):
        self.llm_config = llm_config
        self.tool_analyzer = ToolCapabilityAnalyzer()
    
    async def judge_agent_types(self, steps: List[StepDesign]) -> Dict[str, str]:
        """判断Agent类型 - 基于成本效益分析的智能判断"""
        # 使用包含工具能力矩阵的优化提示词
        # 进行成本敏感的Agent类型选择
        pass
    
    async def generate_step_agents(self, steps: List[StepDesign]) -> List[Dict[str, Any]]:
        """按需生成StepAgent - 只在必要时生成新Agent"""
        # 基于工具实现方案生成Agent规格
        pass
```

### 3. 工作流组装器 (WorkflowBuilder)
```python
class WorkflowBuilder:
    """工作流组装器 - 将steps组合成Workflow"""
    
    async def build_workflow(self, steps: List[StepDesign], agents: List[StepAgent]) -> Workflow:
        """将steps组合成一个完整的Workflow"""
        pass
    
    async def register_workflow(self, workflow: Workflow) -> None:
        """将组装好的Workflow进行注册"""
        pass
```

### 4. 代码生成器 (CodeGenerator)
```python
class CodeGenerator:
    """代码生成器 - 生成BaseAgent兼容的Python代码"""
    
    async def generate_agent_code(self, workflow: Workflow, agents: List[StepAgent]) -> GeneratedCode:
        """生成配合BaseAgent可以运行的Python代码"""
        pass
    
    async def generate_metadata(self, workflow: Workflow) -> AgentMetadata:
        """生成Agent的功能描述和接口定义"""
        pass
```

## 数据结构设计

### 1. 基础数据结构
```python
@dataclass
class ParsedRequirement:
    """解析后的需求"""
    original_text: str                    # 原始需求文本
    agent_purpose: str                    # Agent目的
    process_steps: List['StepDesign']     # 执行步骤
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class StepDesign:
    """步骤设计"""
    step_id: str                         # 步骤ID
    name: str                            # 步骤名称
    description: str                     # 步骤描述
    agent_type: str                      # Agent类型：text/tool/code/custom
    agent_config: Dict[str, Any]         # Agent配置参数（包含工具实现信息）

@dataclass
class ToolCapability:
    """工具能力描述"""
    name: str                           # 工具名称
    description: str                    # 工具描述
    category: str                       # 工具分类
    actions: List[str]                  # 支持的动作列表
    action_details: Dict[str, Any]      # 动作详细信息
    implementation_complexity: str      # 实现复杂度: low/medium/high
    dependencies: List[str]             # 依赖列表
    examples: List[Dict[str, Any]]      # 使用示例

@dataclass
class ToolGapAnalysis:
    """工具差距分析"""
    requirement_description: str        # 需求描述
    existing_tools_match: List[str]     # 匹配的现有工具
    capability_gaps: List[str]          # 能力差距
    implementation_suggestion: str      # 实现建议
    estimated_complexity: str          # 预估复杂度
    recommended_approach: str          # 推荐方案

@dataclass
class LLMConfig:
    """LLM配置"""
    provider: str                       # LLM提供商：openai/anthropic
    model: str                          # 模型名称
    api_key: str                        # API密钥
    temperature: float = 0.7            # 温度参数
    max_tokens: int = 4000              # 最大token数
    
@dataclass
class GeneratedCode:
    """生成的代码"""
    main_agent_code: str                # 主Agent类代码
    workflow_config: str                # 工作流配置
    metadata: 'AgentMetadata'           # Agent元数据
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class AgentMetadata:
    """Agent元数据"""
    name: str                           # Agent名称
    description: str                    # Agent描述
    capabilities: List[str]             # 能力列表
    interface: Dict[str, Any]           # 接口定义
    cost_analysis: str                  # 成本分析
    created_at: datetime = field(default_factory=datetime.now)
```

## 核心流程

### AgentBuilder主流程（基于最优控制理论）
```python
class AgentBuilder:
    """AgentBuilder主类 - 协调整个Agent生成过程"""
    
    def __init__(self, llm_config: LLMConfig):
        self.requirement_parser = RequirementParser(llm_config)
        self.agent_designer = AgentDesigner(llm_config)
        self.workflow_builder = WorkflowBuilder()
        self.code_generator = CodeGenerator(llm_config)
    
    async def build_agent_from_description(self, user_description: str) -> GeneratedCode:
        """从自然语言描述构建Agent - 遵循最优控制流程"""
        
        # 1. 智能需求解析（包含功能定位和交互模式分析）
        requirement = await self.requirement_parser.parse_requirements(user_description)
        
        # 2. 基于工具能力的步骤提取（成本敏感的分解）
        steps = await self.requirement_parser.extract_steps(
            user_description, requirement.agent_purpose
        )
        
        # 3. 成本效益优化的Agent类型判断
        agent_types = await self.agent_designer.judge_agent_types(steps)
        
        # 4. 按需生成StepAgent（避免不必要的实现）
        step_agents = await self.agent_designer.generate_step_agents(steps)
        
        # 5. 组合Workflow（确保数据流正确）
        workflow = await self.workflow_builder.build_workflow(steps, step_agents)
        
        # 6. 注册Workflow
        await self.workflow_builder.register_workflow(workflow)
        
        # 7. 生成BaseAgent兼容代码
        generated_code = await self.code_generator.generate_agent_code(workflow, step_agents)
        
        return generated_code
```

### 决策流程（符合最优控制理论）
1. **Workflow设计** - 确定每个步骤的逻辑关系
2. **步骤分析** - 确定每个步骤具体要做什么
3. **能力评估** - 判断现有Agent是否能完成，是否需要新工具
4. **成本优化** - 选择成本最低的实现方案
5. **代码生成** - 生成最终的可执行代码

## 与BaseAgent集成

### 生成的Agent代码示例
```python
# 生成的Agent类需要继承BaseAgent
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

## 使用示例

### 简单问答Agent
```python
# 用户输入
user_description = """
我需要一个助手，能够：
1. 理解用户的问题
2. 生成回答
"""

# 生成Agent
agent_builder = AgentBuilder()
result = await agent_builder.build_agent_from_description(user_description)

# 使用生成的Agent
agent = GeneratedAgent(config)
response = await agent.execute({"user_input": "你好"})
```

## 成功标准

### 功能性标准
- 能够解析自然语言需求
- 能够判断Agent类型
- 能够生成可执行的BaseAgent代码
- 能够注册和运行Workflow

### 质量标准
- 生成的代码能够在BaseAgent框架中正确运行
- 生成的Agent符合BaseAgent接口规范
- 提供清晰的Agent元数据和文档