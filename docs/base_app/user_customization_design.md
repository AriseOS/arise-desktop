# BaseAgent 用户自定义接口设计 (基于现有架构)

## 设计概述

基于现有的 BaseAgent 架构，在 `/Users/shenyouren/workspace/arise-project/ami/ami/base_app/base_app/base_agent/core/base_agent.py` 中添加用户友好的接口，允许用户：

1. 通过简单的 Python API 创建自定义 Workflow
2. 注册自定义的 TextAgent、ToolAgent、CodeAgent
3. 动态组合和执行工作流

## 现有架构分析

### 核心组件
- `BaseAgent`: 主要的Agent基类，包含 `WorkflowEngine`
- `WorkflowEngine`: 工作流执行引擎，已支持 `AgentWorkflowStep`
- `AgentRegistry`: Agent注册系统
- `BaseStepAgent`: 步骤Agent基类
- `TextAgent/ToolAgent/CodeAgent`: 具体的Agent实现

### 数据结构
- `AgentWorkflowStep`: 工作流步骤定义
- `Workflow`: 完整工作流定义
- `AgentContext`: Agent执行上下文
- `WorkflowResult`: 工作流执行结果

## 用户自定义接口设计

### 1. 在 BaseAgent 中添加工作流创建函数

```python
# 在 BaseAgent 类中添加以下方法

class BaseAgent:
    # ... 现有代码 ...

    def create_workflow_builder(self, name: str, description: str = "") -> 'WorkflowBuilder':
        """
        创建工作流构建器 - 用户友好的工作流创建接口
        
        Args:
            name: 工作流名称
            description: 工作流描述
            
        Returns:
            WorkflowBuilder: 工作流构建器实例
            
        Example:
            builder = agent.create_workflow_builder("数据分析流程", "用于处理和分析数据")
            builder.add_text_step("理解需求", "分析用户的数据分析需求")
            builder.add_tool_step("读取数据", "从文件中读取数据", tools=["file_reader"])
            builder.add_code_step("分析数据", "进行统计分析", language="python")
            workflow = builder.build()
        """
        return WorkflowBuilder(name, description, self)

    def register_custom_agent(self, agent: BaseStepAgent) -> bool:
        """
        注册自定义Agent
        
        Args:
            agent: 继承自BaseStepAgent的自定义Agent实例
            
        Returns:
            bool: 注册是否成功
            
        Example:
            class MyCustomAgent(BaseStepAgent):
                def __init__(self):
                    metadata = AgentMetadata(
                        name="my_custom_agent",
                        description="我的自定义Agent",
                        capabilities=[AgentCapability.TEXT_GENERATION]
                    )
                    super().__init__(metadata)
                    
                async def execute(self, input_data, context):
                    # 自定义逻辑
                    return {"result": "custom processing"}
            
            custom_agent = MyCustomAgent()
            success = agent.register_custom_agent(custom_agent)
        """
        if not self.workflow_engine:
            logger.error("工作流引擎未初始化")
            return False
        
        try:
            self.workflow_engine.agent_registry.register_agent(agent)
            logger.info(f"自定义Agent注册成功: {agent.metadata.name}")
            return True
        except Exception as e:
            logger.error(f"自定义Agent注册失败: {e}")
            return False

    def create_custom_text_agent(self, 
                                name: str,
                                system_prompt: str,
                                response_style: str = "professional",
                                max_length: int = 500) -> 'CustomTextAgent':
        """
        创建自定义文本Agent
        
        Args:
            name: Agent名称
            system_prompt: 系统提示词
            response_style: 响应风格
            max_length: 最大响应长度
            
        Returns:
            CustomTextAgent: 自定义文本Agent实例
            
        Example:
            text_agent = agent.create_custom_text_agent(
                name="专业翻译员",
                system_prompt="你是一个专业的中英文翻译员，请提供准确、流畅的翻译。",
                response_style="professional"
            )
            agent.register_custom_agent(text_agent)
        """
        return CustomTextAgent(name, system_prompt, response_style, max_length)

    def create_custom_tool_agent(self,
                                name: str,
                                available_tools: List[str],
                                tool_selection_strategy: str = "best_match",
                                confidence_threshold: float = 0.8) -> 'CustomToolAgent':
        """
        创建自定义工具Agent
        
        Args:
            name: Agent名称
            available_tools: 可用工具列表
            tool_selection_strategy: 工具选择策略
            confidence_threshold: 置信度阈值
            
        Returns:
            CustomToolAgent: 自定义工具Agent实例
            
        Example:
            tool_agent = agent.create_custom_tool_agent(
                name="数据处理专家",
                available_tools=["excel_reader", "data_analyzer", "chart_generator"],
                tool_selection_strategy="best_match"
            )
            agent.register_custom_agent(tool_agent)
        """
        return CustomToolAgent(name, available_tools, tool_selection_strategy, confidence_threshold)

    def create_custom_code_agent(self,
                                name: str,
                                language: str = "python",
                                allowed_libraries: List[str] = None,
                                code_template: str = "") -> 'CustomCodeAgent':
        """
        创建自定义代码Agent
        
        Args:
            name: Agent名称
            language: 编程语言
            allowed_libraries: 允许的库列表
            code_template: 代码模板
            
        Returns:
            CustomCodeAgent: 自定义代码Agent实例
            
        Example:
            code_agent = agent.create_custom_code_agent(
                name="数据分析师",
                language="python",
                allowed_libraries=["pandas", "numpy", "matplotlib"],
                code_template="# 数据分析代码\\nimport pandas as pd\\nimport numpy as np\\n"
            )
            agent.register_custom_agent(code_agent)
        """
        return CustomCodeAgent(name, language, allowed_libraries or [], code_template)

    def list_available_agents(self) -> List[str]:
        """
        列出所有可用的Agent
        
        Returns:
            List[str]: Agent名称列表
            
        Example:
            agents = agent.list_available_agents()
            print(f"可用Agent: {agents}")
        """
        if not self.workflow_engine:
            return []
        
        return self.workflow_engine.agent_registry.list_agent_names()

    def get_agent_info(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """
        获取Agent信息
        
        Args:
            agent_name: Agent名称
            
        Returns:
            Optional[Dict[str, Any]]: Agent信息字典
            
        Example:
            info = agent.get_agent_info("text_agent")
            print(f"Agent信息: {info}")
        """
        if not self.workflow_engine:
            return None
        
        try:
            agent_instance = self.workflow_engine.agent_registry.get_agent(agent_name)
            if agent_instance:
                return {
                    "name": agent_instance.metadata.name,
                    "description": agent_instance.metadata.description,
                    "capabilities": [cap.value for cap in agent_instance.metadata.capabilities],
                    "input_schema": agent_instance.metadata.input_schema,
                    "output_schema": agent_instance.metadata.output_schema
                }
        except Exception as e:
            logger.error(f"获取Agent信息失败: {e}")
        
        return None

    async def run_custom_workflow(self, workflow: 'Workflow', input_data: Dict[str, Any] = None) -> WorkflowResult:
        """
        运行自定义工作流
        
        Args:
            workflow: 工作流实例
            input_data: 输入数据
            
        Returns:
            WorkflowResult: 工作流执行结果
            
        Example:
            result = await agent.run_custom_workflow(workflow, {"user_input": "分析这个数据"})
            print(f"执行结果: {result.final_result}")
        """
        return await self.run_workflow(workflow, input_data)
```

### 2. 工作流构建器类

```python
class WorkflowBuilder:
    """工作流构建器 - 提供用户友好的工作流构建接口"""
    
    def __init__(self, name: str, description: str, agent_instance: BaseAgent):
        self.name = name
        self.description = description
        self.agent = agent_instance
        self.steps: List[AgentWorkflowStep] = []
        self.input_schema: Dict[str, Any] = {}
        self.output_schema: Dict[str, Any] = {}
    
    def add_text_step(self, 
                     name: str, 
                     instruction: str,
                     agent_name: str = "text_agent",
                     response_style: str = "professional",
                     max_length: int = 500,
                     condition: str = None) -> 'WorkflowBuilder':
        """
        添加文本处理步骤
        
        Args:
            name: 步骤名称
            instruction: Agent执行指令
            agent_name: 使用的Agent名称
            response_style: 响应风格
            max_length: 最大响应长度
            condition: 执行条件
            
        Returns:
            WorkflowBuilder: 返回自身支持链式调用
            
        Example:
            builder.add_text_step(
                name="理解用户需求",
                instruction="分析用户输入，理解其真实意图和需求",
                response_style="professional"
            )
        """
        step = AgentWorkflowStep(
            name=name,
            agent_type=agent_name,
            response_style=response_style,
            max_length=max_length,
            condition=condition
        )
        self.steps.append(step)
        return self
    
    def add_tool_step(self,
                     name: str,
                     instruction: str,
                     tools: List[str],
                     agent_name: str = "tool_agent",
                     confidence_threshold: float = 0.8,
                     condition: str = None) -> 'WorkflowBuilder':
        """
        添加工具使用步骤
        
        Args:
            name: 步骤名称
            instruction: Agent执行指令
            tools: 可用工具列表
            agent_name: 使用的Agent名称
            confidence_threshold: 置信度阈值
            condition: 执行条件
            
        Returns:
            WorkflowBuilder: 返回自身支持链式调用
            
        Example:
            builder.add_tool_step(
                name="搜索相关信息",
                instruction="根据用户需求搜索相关信息",
                tools=["search_engine", "knowledge_base"]
            )
        """
        step = AgentWorkflowStep(
            name=name,
            agent_type=agent_name,
            allowed_tools=tools,
            confidence_threshold=confidence_threshold,
            condition=condition
        )
        self.steps.append(step)
        return self
    
    def add_code_step(self,
                     name: str,
                     instruction: str,
                     language: str = "python",
                     libraries: List[str] = None,
                     agent_name: str = "code_agent",
                     condition: str = None) -> 'WorkflowBuilder':
        """
        添加代码执行步骤
        
        Args:
            name: 步骤名称
            instruction: Agent执行指令
            language: 编程语言
            libraries: 允许的库列表
            agent_name: 使用的Agent名称
            condition: 执行条件
            
        Returns:
            WorkflowBuilder: 返回自身支持链式调用
            
        Example:
            builder.add_code_step(
                name="数据分析",
                instruction="对数据进行统计分析和可视化",
                language="python",
                libraries=["pandas", "matplotlib"]
            )
        """
        step = AgentWorkflowStep(
            name=name,
            agent_type=agent_name,
            allowed_libraries=libraries or [],
            condition=condition
        )
        self.steps.append(step)
        return self
    
    def add_custom_step(self,
                       name: str,
                       agent_name: str,
                       instruction: str,
                       inputs: Dict[str, Any] = None,
                       condition: str = None) -> 'WorkflowBuilder':
        """
        添加自定义Agent步骤
        
        Args:
            name: 步骤名称
            agent_name: 自定义Agent名称
            instruction: Agent执行指令
            inputs: 输入配置
            condition: 执行条件
            
        Returns:
            WorkflowBuilder: 返回自身支持链式调用
            
        Example:
            builder.add_custom_step(
                name="专业翻译",
                agent_name="专业翻译员",
                instruction="将文本翻译成英文",
                inputs={"text": "{{user_input}}"}
            )
        """
        step = AgentWorkflowStep(
            name=name,
            agent_type=agent_name,
            inputs=inputs or {},
            condition=condition
        )
        self.steps.append(step)
        return self
    
    def set_input_schema(self, schema: Dict[str, Any]) -> 'WorkflowBuilder':
        """
        设置输入模式
        
        Args:
            schema: 输入模式定义
            
        Returns:
            WorkflowBuilder: 返回自身支持链式调用
            
        Example:
            builder.set_input_schema({
                "user_input": {"type": "string", "required": True, "description": "用户输入"},
                "file_path": {"type": "string", "required": False, "description": "文件路径"}
            })
        """
        self.input_schema = schema
        return self
    
    def set_output_schema(self, schema: Dict[str, Any]) -> 'WorkflowBuilder':
        """
        设置输出模式
        
        Args:
            schema: 输出模式定义
            
        Returns:
            WorkflowBuilder: 返回自身支持链式调用
        """
        self.output_schema = schema
        return self
    
    def build(self) -> Workflow:
        """
        构建工作流
        
        Returns:
            Workflow: 工作流实例
            
        Example:
            workflow = builder.build()
            result = await agent.run_custom_workflow(workflow, {"user_input": "Hello"})
        """
        return Workflow(
            name=self.name,
            description=self.description,
            steps=self.steps,
            input_schema=self.input_schema,
            output_schema=self.output_schema
        )
```

### 3. 自定义Agent类

```python
class CustomTextAgent(BaseStepAgent):
    """自定义文本Agent"""
    
    def __init__(self, name: str, system_prompt: str, response_style: str = "professional", max_length: int = 500):
        metadata = AgentMetadata(
            name=name,
            description=f"自定义文本Agent: {name}",
            capabilities=[AgentCapability.TEXT_GENERATION],
            input_schema={
                "question": {"type": "string", "required": True},
                "context_data": {"type": "object", "required": False}
            },
            output_schema={
                "success": {"type": "boolean"},
                "answer": {"type": "string"},
                "error_message": {"type": "string"}
            }
        )
        super().__init__(metadata)
        self.system_prompt = system_prompt
        self.response_style = response_style
        self.max_length = max_length
        self.provider = None
    
    async def initialize(self, context: AgentContext) -> bool:
        """初始化自定义Text Agent"""
        if not context.agent_instance:
            return False
        
        # 从BaseAgent获取provider
        self.provider = context.agent_instance.provider
        if not self.provider:
            logger.error("Provider未设置")
            return False
        
        self.is_initialized = True
        return True
    
    async def execute(self, input_data: Any, context: AgentContext) -> Any:
        """执行自定义文本生成"""
        if not self.is_initialized:
            await self.initialize(context)
        
        # 使用自定义系统提示词
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": str(input_data)}
        ]
        
        try:
            response = await self.provider.generate_text(
                messages,
                max_tokens=self.max_length,
                temperature=0.7
            )
            
            return TextAgentOutput(
                success=True,
                answer=response,
                word_count=len(response)
            )
        except Exception as e:
            logger.error(f"自定义文本Agent执行失败: {e}")
            return TextAgentOutput(
                success=False,
                answer="",
                word_count=0,
                error_message=str(e)
            )
    
    async def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        return isinstance(input_data, str) and len(input_data.strip()) > 0


class CustomToolAgent(BaseStepAgent):
    """自定义工具Agent"""
    
    def __init__(self, name: str, available_tools: List[str], tool_selection_strategy: str = "best_match", confidence_threshold: float = 0.8):
        metadata = AgentMetadata(
            name=name,
            description=f"自定义工具Agent: {name}",
            capabilities=[AgentCapability.TOOL_CALLING],
            input_schema={
                "task_description": {"type": "string", "required": True},
                "context_data": {"type": "object", "required": False}
            },
            output_schema={
                "success": {"type": "boolean"},
                "result": {"type": "object"},
                "tool_used": {"type": "string"},
                "error_message": {"type": "string"}
            }
        )
        super().__init__(metadata)
        self.available_tools = available_tools
        self.tool_selection_strategy = tool_selection_strategy
        self.confidence_threshold = confidence_threshold
        self.tools_registry = None
    
    async def initialize(self, context: AgentContext) -> bool:
        """初始化自定义Tool Agent"""
        if not context.agent_instance:
            return False
        
        # 从BaseAgent获取tools_registry
        self.tools_registry = context.agent_instance.tools
        if not self.tools_registry:
            logger.error("工具注册表未设置")
            return False
        
        self.is_initialized = True
        return True
    
    async def execute(self, input_data: Any, context: AgentContext) -> Any:
        """执行自定义工具调用"""
        if not self.is_initialized:
            await self.initialize(context)
        
        task_description = str(input_data)
        
        # 简单的工具选择逻辑（可以根据需要扩展）
        selected_tool = None
        for tool_name in self.available_tools:
            if tool_name in self.tools_registry:
                selected_tool = tool_name
                break
        
        if not selected_tool:
            return ToolAgentOutput(
                success=False,
                result=None,
                tool_used="",
                action_taken="",
                confidence=0.0,
                reasoning="未找到可用工具",
                error_message="没有可用的工具"
            )
        
        try:
            # 调用工具
            tool_result = await context.agent_instance.use_tool(
                selected_tool, 
                "execute", 
                {"task": task_description}
            )
            
            return ToolAgentOutput(
                success=tool_result.success,
                result=tool_result.data,
                tool_used=selected_tool,
                action_taken="execute",
                confidence=0.9,
                reasoning=f"选择了工具 {selected_tool} 来完成任务",
                error_message=tool_result.error_message if not tool_result.success else None
            )
        except Exception as e:
            logger.error(f"自定义工具Agent执行失败: {e}")
            return ToolAgentOutput(
                success=False,
                result=None,
                tool_used=selected_tool,
                action_taken="execute",
                confidence=0.0,
                reasoning="工具执行失败",
                error_message=str(e)
            )
    
    async def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        return isinstance(input_data, str) and len(input_data.strip()) > 0


class CustomCodeAgent(BaseStepAgent):
    """自定义代码Agent"""
    
    def __init__(self, name: str, language: str = "python", allowed_libraries: List[str] = None, code_template: str = ""):
        metadata = AgentMetadata(
            name=name,
            description=f"自定义代码Agent: {name}",
            capabilities=[AgentCapability.CODE_EXECUTION],
            input_schema={
                "task_description": {"type": "string", "required": True},
                "input_data": {"type": "object", "required": False}
            },
            output_schema={
                "success": {"type": "boolean"},
                "result": {"type": "object"},
                "code_generated": {"type": "string"},
                "error_message": {"type": "string"}
            }
        )
        super().__init__(metadata)
        self.language = language
        self.allowed_libraries = allowed_libraries or []
        self.code_template = code_template
        self.provider = None
    
    async def initialize(self, context: AgentContext) -> bool:
        """初始化自定义Code Agent"""
        if not context.agent_instance:
            return False
        
        # 从BaseAgent获取provider
        self.provider = context.agent_instance.provider
        if not self.provider:
            logger.error("Provider未设置")
            return False
        
        self.is_initialized = True
        return True
    
    async def execute(self, input_data: Any, context: AgentContext) -> Any:
        """执行自定义代码生成"""
        if not self.is_initialized:
            await self.initialize(context)
        
        task_description = str(input_data)
        
        # 构建代码生成提示
        prompt = f"""
请根据以下任务描述生成{self.language}代码：

任务描述：{task_description}

要求：
1. 只能使用以下库：{', '.join(self.allowed_libraries)}
2. 代码应该是完整可执行的
3. 包含必要的错误处理

代码模板：
{self.code_template}

请生成代码：
"""
        
        try:
            messages = [
                {"role": "system", "content": f"你是一个专业的{self.language}程序员，请生成高质量的代码。"},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.provider.generate_text(messages, max_tokens=1000)
            
            # 简单的代码提取（实际应用中可能需要更复杂的处理）
            code = response.strip()
            
            return CodeAgentOutput(
                success=True,
                result={"generated_code": code},
                code_generated=code,
                execution_info={"language": self.language, "libraries": self.allowed_libraries}
            )
        except Exception as e:
            logger.error(f"自定义代码Agent执行失败: {e}")
            return CodeAgentOutput(
                success=False,
                result=None,
                code_generated="",
                error_message=str(e)
            )
    
    async def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        return isinstance(input_data, str) and len(input_data.strip()) > 0
```

## 使用示例

### 1. 创建简单的问答工作流

```python
from base_agent.core.base_agent import BaseAgent
from base_agent.core.schemas import AgentConfig

# 创建BaseAgent实例
config = AgentConfig(
    name="CustomAgent",
    llm_provider="openai",
    llm_model="gpt-4",
    api_key="your-api-key"
)

agent = BaseAgent(config)
await agent.initialize()

# 创建工作流
builder = agent.create_workflow_builder("智能问答", "回答用户问题的工作流")

builder.add_text_step(
    name="理解问题",
    instruction="分析用户问题，理解其意图和需求"
).add_text_step(
    name="生成回答",
    instruction="基于问题理解，生成准确、有用的回答"
)

workflow = builder.build()

# 执行工作流
result = await agent.run_custom_workflow(workflow, {"user_input": "什么是人工智能？"})
print(result.final_result)
```

### 2. 创建自定义Agent并使用

```python
# 创建自定义文本Agent
translator = agent.create_custom_text_agent(
    name="专业翻译员",
    system_prompt="你是一个专业的中英文翻译员。请提供准确、流畅的翻译，保持原文的语调和风格。",
    response_style="professional"
)

# 注册自定义Agent
agent.register_custom_agent(translator)

# 创建使用自定义Agent的工作流
builder = agent.create_workflow_builder("翻译服务", "提供专业翻译服务")
builder.add_custom_step(
    name="翻译文本",
    agent_name="专业翻译员",
    instruction="将用户输入的中文翻译成英文"
)

workflow = builder.build()
result = await agent.run_custom_workflow(workflow, {"user_input": "你好，世界！"})
print(result.final_result)
```

### 3. 创建数据分析工作流

```python
# 创建自定义工具Agent
data_processor = agent.create_custom_tool_agent(
    name="数据处理器",
    available_tools=["file_reader", "data_analyzer"],
    tool_selection_strategy="best_match"
)

# 创建自定义代码Agent
data_analyst = agent.create_custom_code_agent(
    name="数据分析师",
    language="python",
    allowed_libraries=["pandas", "numpy", "matplotlib"],
    code_template="import pandas as pd\nimport numpy as np\nimport matplotlib.pyplot as plt\n\n"
)

# 注册自定义Agent
agent.register_custom_agent(data_processor)
agent.register_custom_agent(data_analyst)

# 创建数据分析工作流
builder = agent.create_workflow_builder("数据分析", "完整的数据分析流程")

builder.add_text_step(
    name="理解需求",
    instruction="分析用户的数据分析需求，确定分析目标和方法"
).add_custom_step(
    name="读取数据",
    agent_name="数据处理器",
    instruction="读取用户指定的数据文件"
).add_custom_step(
    name="分析数据",
    agent_name="数据分析师",
    instruction="对数据进行统计分析和可视化"
).add_text_step(
    name="生成报告",
    instruction="基于分析结果生成完整的分析报告"
)

workflow = builder.build()
result = await agent.run_custom_workflow(workflow, {
    "user_input": "请分析sales_data.csv文件中的销售趋势",
    "file_path": "sales_data.csv"
})
print(result.final_result)
```

### 4. 条件执行工作流

```python
# 创建带条件的工作流
builder = agent.create_workflow_builder("智能助手", "根据用户意图执行不同操作")

builder.add_text_step(
    name="意图分析",
    instruction="分析用户输入，判断是问答、翻译、还是计算需求。返回：chat/translate/calculate"
).add_text_step(
    name="问答处理",
    instruction="回答用户的问题",
    condition="{{step_results.意图分析.answer}} == 'chat'"
).add_custom_step(
    name="翻译处理",
    agent_name="专业翻译员",
    instruction="翻译用户的文本",
    condition="{{step_results.意图分析.answer}} == 'translate'"
).add_code_step(
    name="计算处理",
    instruction="执行用户的计算请求",
    condition="{{step_results.意图分析.answer}} == 'calculate'"
)

workflow = builder.build()
result = await agent.run_custom_workflow(workflow, {"user_input": "请将'Hello World'翻译成中文"})
print(result.final_result)
```

## 实现要点

### 1. 代码文件修改
- 在 `base_agent.py` 中添加上述方法
- 创建新的 `workflow_builder.py` 文件
- 创建新的 `custom_agents.py` 文件

### 2. 兼容性保证
- 所有新功能都是在现有架构基础上的扩展
- 不破坏现有的工作流执行逻辑
- 支持现有的 YAML 配置方式

### 3. 扩展性设计
- 用户可以继承 `BaseStepAgent` 创建完全自定义的Agent
- 支持动态注册和发现Agent
- 提供完整的Agent生命周期管理

### 4. 错误处理和验证
- 完整的输入验证
- 详细的错误信息和日志
- 优雅的错误恢复机制

## 总结

这个设计完全基于现有的BaseAgent架构，通过在BaseAgent类中添加用户友好的接口，让用户可以：

1. **简单创建工作流**：通过WorkflowBuilder提供链式API
2. **自定义Agent**：支持创建和注册自定义的各种Agent
3. **灵活组合**：可以混合使用内置Agent和自定义Agent
4. **保持兼容性**：不破坏现有的代码结构和功能

这种设计既保持了现有架构的强大功能，又提供了用户友好的自定义接口，是一个实用且可扩展的解决方案。