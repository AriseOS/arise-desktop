# AgentCrafter 项目架构文档

## 项目概述

AgentCrafter 基于创新的 **Agent-as-Step 架构**，实现了从自然语言描述到可执行Agent的完整自动化生成流程。项目包含两大核心组件：**BaseAgent 框架**（运行时）和 **AgentBuilder 系统**（生成时）。

## 1. BaseAgent 中的 Workflow 引擎架构

### 1.1 核心引擎：AgentWorkflowEngine

**位置**: `base_app/base_agent/core/agent_workflow_engine.py`

BaseAgent的工作流引擎基于**Agent-as-Step**设计理念，每个工作流步骤都是一个独立的智能Agent：

```python
class AgentWorkflowEngine:
    async def execute_workflow(self, steps: List[AgentWorkflowStep]) -> WorkflowResult:
        # 1. 初始化执行上下文
        # 2. 逐步执行Agent步骤  
        # 3. 管理变量传递和结果映射
        # 4. 处理条件执行和错误恢复
```

**核心特性**：
- **上下文管理**: 维护全局变量状态，支持步骤间数据传递
- **变量解析**: 支持模板语法 `{{variable_name}}` 进行动态变量引用
- **条件执行**: 基于前序步骤结果决定是否执行当前步骤
- **错误处理**: 多级重试机制和错误恢复策略

### 1.2 工作流构建器：WorkflowBuilder

**位置**: `base_app/base_agent/core/workflow_builder.py`

提供用户友好的链式API构建工作流：

```python
builder = agent.create_workflow_builder("数据分析流程", "自动化数据处理")
builder.add_text_step("理解需求", "分析用户的数据分析需求") \
       .add_tool_step("获取数据", "使用浏览器获取数据", tools=["browser_use"]) \
       .add_code_step("处理数据", "清洗和分析数据", libraries=["pandas", "numpy"])
workflow = builder.build()
```

## 2. Agent-as-Step 架构实现

### 2.1 核心设计理念

每个工作流步骤就是一个专门的Agent，具备：

- **独立性**: 可独立初始化、执行和清理
- **专业性**: 针对特定任务类型优化（文本生成/工具调用/代码执行）
- **组合性**: 通过标准接口无缝组合成复杂工作流
- **智能性**: 基于上下文和约束条件智能决策

### 2.2 数据流架构

```
用户输入 → 上下文初始化 → Agent步骤1 → 变量更新 → Agent步骤2 → ... → 最终结果
                                ↓
                            输出映射 → 全局变量池 → 下一步输入解析
```

**变量传递机制**：
```python
# 第一步输出
outputs: {"analysis_result": "意图分析完成"}

# 第二步输入引用
inputs: {
    "task": "{{user_input}}",
    "context": "{{analysis_result}}"
}
```

## 3. Agent类型Schema定义

### 3.1 统一基础Schema：AgentWorkflowStep

**位置**: `base_app/base_agent/core/schemas.py`

```python
class AgentWorkflowStep(BaseModel):
    # 基础信息
    id: str
    name: str  
    description: str
    user_task: Optional[str]
    
    # Agent配置
    agent_type: str  # text_agent | tool_agent | code_agent
    agent_instruction: str
    
    # 输入输出定义
    inputs: Dict[str, Any]
    outputs: Dict[str, str]
    constraints: List[str]
    
    # 执行控制
    condition: Optional[str]
    timeout: int = 300
    retry_count: int = 0
```

### 3.2 三种核心Agent类型

#### 3.2.1 TextAgent - 文本生成专家

**Schema扩展字段**：
```python
# TextAgent特有配置
response_style: str = "professional"  # friendly, professional, concise
max_length: int = 500
temperature: float = 0.7
```

**功能特点**：
- 基于LLM的智能文本生成
- 支持多种回答风格（友好/专业/简洁）
- 可控制输出长度和创造性
- 适用场景：问答、分析、总结、创作

#### 3.2.2 ToolAgent - 工具调用专家  

**Schema扩展字段**：
```python
# ToolAgent特有配置
allowed_tools: List[str]
confidence_threshold: float = 0.8
fallback_tools: List[str] = []
tool_selection_strategy: str = "best_match"
```

**两轮智能决策机制**：
1. **工具选择轮**: 从允许工具列表中选择最适合的工具
2. **参数确定轮**: 根据工具API文档确定具体操作和参数

**功能特点**：
- 智能工具选择和参数推理
- 置信度评估和备选方案
- 支持工具：browser_use、android_tool、memory_tool等
- 适用场景：网页自动化、应用操作、信息提取

#### 3.2.3 CodeAgent - 代码执行专家

**Schema扩展字段**：  
```python
# CodeAgent特有配置
language: str = "python"
allowed_libraries: List[str]
expected_output_format: str
security_level: str = "safe"
```

**安全执行机制**：
- AST语法树安全检查，禁止危险函数
- 沙箱执行环境，限制系统访问
- 库导入白名单控制
- 执行时间和资源限制

**功能特点**：
- 代码生成和安全执行
- 支持pandas、numpy等数据处理库
- 结构化输出格式控制
- 适用场景：数据分析、计算任务、文件处理

## 4. AgentBuilder 生成架构

### 4.1 智能生成流程

AgentBuilder负责将自然语言需求转换为完整的Agent实现：

```
用户描述 → 需求解析 → 步骤提取 → Agent类型判断 → Schema生成 → Workflow组装 → 代码生成
```

### 4.2 核心组件

#### 4.2.1 RequirementParser - 需求解析器

**位置**: `agent_builder/core/requirement_parser.py`

```python
class RequirementParser:
    async def parse_requirements(self, description: str) -> RequirementAnalysis:
        # 提取Agent目的、关键任务、性能要求
        
    async def extract_steps(self, description: str, purpose: str) -> List[StepDesign]:
        # 基于现有工具能力分解执行步骤
```

**智能分析能力**：
- 理解用户意图和核心需求
- 基于工具知识库推荐合适的执行步骤
- 考虑技术可行性和资源约束

#### 4.2.2 AgentDesigner - Agent设计器

**位置**: `agent_builder/core/agent_designer.py`

```python
class AgentDesigner:
    async def judge_agent_types(self, steps: List[StepDesign]) -> Dict[str, str]:
        # 基于成本效益优化选择Agent类型
        
    async def generate_step_agents(self, steps: List[StepDesign]) -> List[Dict[str, Any]]:
        # 生成符合BaseAgent规范的完整Agent配置
```

**智能设计原则**：
- **成本效益优化**: TextAgent < ToolAgent < CodeAgent < CustomAgent
- **能力匹配原则**: 确保Agent类型能完成指定任务  
- **技术可行性**: 考虑现有工具覆盖和实现难度

#### 4.2.3 CodeGenerator - 代码生成器

**位置**: `agent_builder/core/code_generator.py`

**生成完整Agent包**：
```python
# 生成的Agent结构
class Agent_Generated(BaseAgent):
    """
    需要的工具: ['browser_use', 'llm_extract']
    这些工具会通过config.tools自动注册
    """
    def __init__(self, config: AgentConfig):
        super().__init__(config)  # 自动工具注册
        
    async def _setup_workflow(self):
        builder = self.create_workflow_builder(name, description)
        # 添加所有步骤...
        self.workflow = builder.build()
        
    async def execute(self, input_data: Any) -> AgentResult:
        result = await self.run_workflow(self.workflow, input_data)
        return AgentResult(success=True, data=result)
```

## 5. 生成代码集成BaseAgent执行

### 5.1 无缝集成架构

生成的Agent完全继承BaseAgent的所有能力：

- **自动工具注册**: 根据config.tools自动注册所需工具
- **内置工作流引擎**: 直接使用BaseAgent的workflow执行能力
- **标准化接口**: 支持同步/异步调用，CLI和编程接口
- **完整生态**: 日志、监控、错误处理、状态管理

### 5.2 配置驱动的工具管理

**config.json示例**：
```json
{
  "name": "智能数据分析助手",
  "tools": ["browser_use", "llm_extract", "file_manager"],
  "llm_provider": "openai",
  "llm_model": "gpt-4o"
}
```

**自动工具注册**：
```python
# BaseAgent自动根据config.tools注册工具
def _auto_register_tools(self):
    for tool_name in self.config.tools:
        tool = self._create_tool_instance(tool_name)
        self.register_tool(tool_name, tool)
```

### 5.3 多种使用方式

#### CLI模式
```bash
python agent.py --interactive  # 交互模式
python agent.py --input "分析这个网站的内容"  # 单次执行
```

#### 编程接口
```python
config = AgentConfig(name="Agent", tools=["browser_use"])
agent = Agent_Generated(config)
result = await agent.execute("用户任务")
```

## 6. 项目当前进展和技术亮点

### 6.1 已实现的核心功能

✅ **BaseAgent运行时框架**
- 完整的Agent-as-Step工作流引擎
- 三种核心Agent类型（Text/Tool/Code）
- 统一的Schema定义和类型安全
- 自动工具注册和管理系统

✅ **AgentBuilder自动生成系统**  
- 智能需求解析和步骤提取
- 基于成本效益的Agent类型优化
- 完整的代码生成和文件管理
- 生成可独立运行的Agent包

✅ **工程化特性**
- 类型安全的Pydantic Schema
- 完整的错误处理和重试机制
- 详细的执行日志和监控
- 语法检查和基础测试

### 6.2 技术创新点

🚀 **Agent-as-Step统一架构**
- 首创将AI Agent作为工作流原子执行单元
- 实现了模块化、可组合的AI任务处理

🚀 **二阶段智能生成**  
- 设计阶段：AI驱动的架构设计和优化
- 代码阶段：自动生成完整可执行系统

🚀 **成本效益优化引擎**
- 基于工具可用性和任务复杂度智能选择Agent类型
- 最小化资源消耗，最大化任务完成质量

🚀 **配置驱动的工具生态**
- 动态工具注册，无需硬编码依赖
- 统一的工具接口，易于扩展新能力

### 6.3 架构优势

- **开发效率**: 从需求描述到可运行Agent，全程自动化
- **可维护性**: 清晰的模块边界和标准化接口
- **可扩展性**: 插件化架构，支持自定义Agent和工具
- **企业级**: 完整的错误处理、监控和安全机制

这个架构代表了AI Agent系统工程化的重要进展，通过Agent-as-Step的创新设计，实现了既灵活又强大的AI自动化开发框架。

## 7. 未来发展方向

### 7.1 短期目标

🎯 **工具生态扩展**
- 集成更多专业工具（图像处理、文档操作、API调用等）
- 支持自定义工具快速接入
- 建立工具市场和共享机制

🎯 **性能优化**
- 并行执行引擎，支持步骤间并发
- 智能缓存和结果复用
- 动态资源分配和负载均衡

🎯 **用户体验提升**
- 可视化工作流设计器
- 实时执行监控和调试
- 丰富的模板和示例库

### 7.2 长期愿景

🌟 **企业级Agent平台**
- 多租户支持和权限管理
- 高可用和水平扩展
- 企业数据安全和合规

🌟 **AI-Native开发范式**
- 自然语言驱动的软件开发
- 智能代码重构和优化
- 自动化测试和部署

🌟 **通用智能助手生态**
- 跨领域知识图谱集成
- 多模态交互（文本、语音、图像）
- 个性化学习和适应

---

*AgentCrafter项目致力于推动AI Agent技术的工程化落地，为下一代智能软件开发奠定基础。*