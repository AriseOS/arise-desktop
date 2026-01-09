# Agent-as-Step 架构设计文档 v2.0

## 1. 核心设计理念

### 1.1 设计原则

**Agent = 输入 + 处理方式 + 输出**

每个Agent都是一个**智能处理单元**，根据输入需求选择最合适的处理方式：
- **Text Agent**: 基于输入信息生成文本回答（最简单的LLM推理）
- **Tool Agent**: 调用现有工具完成任务
- **Code Agent**: 生成并执行代码解决问题
- **所有Agent都基于LLM进行智能决策**

### 1.2 Agent分类逻辑

```
用户需求 → Agent分析 → 选择处理方式
                    ├── Text Agent: 纯文本回答/推理
                    ├── Tool Agent: 有现成工具可用
                    └── Code Agent: 需要编程解决
```

---

## 2. 架构设计

### 2.1 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                WorkflowEngine                          │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                  Agent Executor                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │               Agent Router                              ││
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐││
│  │  │ Text Agent  │ │ Tool Agent  │ │    Code Agent       │││
│  │  │             │ │             │ │                     │││
│  │  │Input:       │ │Input:       │ │Input:               │││
│  │  │- question   │ │- task_desc  │ │- task_desc          │││
│  │  │- context    │ │- context    │ │- input_data         │││
│  │  │- style      │ │- constraints│ │- expected_output    │││
│  │  │             │ │             │ │                     │││
│  │  │Process:     │ │Process:     │ │Process:             │││
│  │  │- LLM推理    │ │- LLM分析    │ │- LLM生成代码        │││
│  │  │- 生成回答   │ │- 选择工具   │ │- 执行代码           │││
│  │  │             │ │- 调用工具   │ │- 返回结果           │││
│  │  │             │ │             │ │                     │││
│  │  │Output:      │ │Output:      │ │Output:              │││
│  │  │- answer     │ │- result     │ │- result             │││
│  │  │             │ │- tool_used  │ │- code_generated     │││
│  │  └─────────────┘ └─────────────┘ └─────────────────────┘││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                 Tool Registry                               │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐│
│  │browser_use  │ │android_use  │ │    Code Executor        ││
│  │             │ │             │ │                         ││
│  │- fill_form  │ │- read_chat  │ │- Python Runtime         ││
│  │- click      │ │- send_msg   │ │- Sandbox Environment    ││
│  │- extract    │ │- screenshot │ │- Safety Checker         ││
│  └─────────────┘ └─────────────┘ └─────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件关系

```python
# 组件依赖关系
WorkflowEngine
├── AgentExecutor
│   ├── TextAgent
│   │   └── Provider (文本生成)
│   ├── ToolAgent
│   │   ├── Provider (任务分析)
│   │   └── ToolRegistry (工具调用)
│   └── CodeAgent  
│       ├── Provider (代码生成)
│       └── CodeExecutor (代码执行)
└── AgentContext (上下文管理)
```

---

## 3. Agent详细设计

### 3.1 Text Agent

#### 3.1.1 输入输出规范

```python
class TextAgentInput(BaseModel):
    """Text Agent 输入规范"""
    question: str = Field(..., description="用户的问题或请求")
    context_data: Dict[str, Any] = Field(default_factory=dict, description="上下文信息")
    response_style: str = Field(default="professional", description="回答风格：professional/casual/technical")
    max_length: int = Field(default=500, description="最大回答长度")
    language: str = Field(default="zh", description="回答语言")

class TextAgentOutput(BaseModel):
    """Text Agent 输出规范"""
    success: bool = Field(..., description="生成是否成功")
    answer: str = Field(..., description="生成的回答")
    word_count: int = Field(..., description="回答字数")
    error_message: Optional[str] = Field(default=None, description="错误信息")
```

#### 3.1.2 处理逻辑

```python
class TextAgent:
    """文本生成Agent"""
    
    async def execute(self, input_data: TextAgentInput, context: AgentContext) -> TextAgentOutput:
        """
        执行流程：
        1. 构建提示词
        2. LLM生成回答
        3. 格式化输出
        """
        
        # Step 1: 构建提示词
        prompt = self._build_prompt(input_data, context)
        
        # Step 2: LLM生成回答
        try:
            response = await self.provider.generate_response(
                system_prompt="你是一个专业的AI助手",
                user_prompt=prompt
            )
            
            return TextAgentOutput(
                success=True,
                answer=response,
                word_count=len(response)
            )
            
        except Exception as e:
            return TextAgentOutput(
                success=False,
                answer="",
                word_count=0,
                error_message=str(e)
            )
    
    def _build_prompt(self, input_data: TextAgentInput, context: AgentContext) -> str:
        """构建提示词"""
        base_prompt = f"""
        请回答以下问题：{input_data.question}
        
        上下文信息：
        {self._format_context(input_data.context_data)}
        
        回答要求：
        - 风格：{input_data.response_style}
        - 语言：{input_data.language}
        - 长度限制：{input_data.max_length}字以内
        - 准确性：基于提供的上下文信息回答
        
        请提供清晰、准确的回答：
        """
        return base_prompt
    
    def _format_context(self, context_data: Dict[str, Any]) -> str:
        """格式化上下文数据"""
        if not context_data:
            return "无额外上下文"
        
        formatted = []
        for key, value in context_data.items():
            formatted.append(f"- {key}: {value}")
        return "\n".join(formatted)
```

#### 3.1.3 使用示例

```python
# 示例1: 简单问答
text_input = TextAgentInput(
    question="今天的会议安排是什么？",
    context_data={
        "meeting_list": ["10:00-产品评审", "14:00-技术讨论", "16:00-项目汇报"],
        "current_time": "2024-01-15 09:30"
    },
    response_style="professional"
)

result = await text_agent.execute(text_input, context)
# 输出: TextAgentOutput(success=True, answer="根据您的会议安排，今天有三个会议...")

# 示例2: 数据总结
text_input = TextAgentInput(
    question="请总结一下这次客户沟通的要点",
    context_data={
        "customer_name": "张三",
        "communication_content": "客户对产品很感兴趣，希望了解价格和交付时间",
        "next_steps": "发送报价单，安排技术演示"
    },
    response_style="casual",
    max_length=200
)

result = await text_agent.execute(text_input, context)
# 输出: 客户张三对我们的产品挺感兴趣的，主要关心价格和交付时间...
```

### 3.2 Tool Agent

#### 3.2.1 输入输出规范

```python
class ToolAgentInput(BaseModel):
    """Tool Agent 输入规范"""
    task_description: str = Field(..., description="任务描述，用自然语言描述要完成什么")
    context_data: Dict[str, Any] = Field(default_factory=dict, description="上下文数据")
    constraints: List[str] = Field(default_factory=list, description="约束条件")
    allowed_tools: List[str] = Field(default_factory=list, description="允许使用的工具列表")
    fallback_tools: List[str] = Field(default_factory=list, description="备选工具列表")
    confidence_threshold: float = Field(default=0.8, description="工具选择置信度阈值")

class ToolAgentOutput(BaseModel):
    """Tool Agent 输出规范"""
    success: bool = Field(..., description="执行是否成功")
    result: Any = Field(..., description="执行结果")
    tool_used: str = Field(..., description="使用的工具名称")
    action_taken: str = Field(..., description="执行的具体动作")
    confidence: float = Field(..., description="工具选择置信度 0-1")
    reasoning: str = Field(..., description="工具选择推理过程")
    alternatives_tried: List[str] = Field(default_factory=list, description="尝试过的备选工具")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="执行元数据")
    error_message: Optional[str] = Field(default=None, description="错误信息")
```

#### 3.2.2 处理逻辑

```python
class ToolAgent:
    """工具调用Agent - 支持工具预筛选和置信度机制"""
    
    async def execute(self, input_data: ToolAgentInput, context: AgentContext) -> ToolAgentOutput:
        """
        执行流程：
        1. 获取Workflow层面预筛选的工具范围
        2. LLM分析任务并选择工具（带置信度）
        3. 执行工具调用，失败时尝试备选工具
        4. 格式化输出结果
        """
        
        # Step 1: 获取Workflow设计时预筛选的工具
        available_tools = self._get_filtered_tools(input_data)
        alternatives_tried = []
        
        # Step 2: LLM分析并选择工具
        tool_selection = await self._select_tool_with_confidence(
            input_data, available_tools
        )
        
        # Step 3: 检查置信度
        if tool_selection["confidence"] < input_data.confidence_threshold:
            context.logger.warning(
                f"工具选择置信度 {tool_selection['confidence']} 低于阈值 {input_data.confidence_threshold}"
            )
        
        # Step 4: 尝试执行工具调用
        primary_tools = [tool_selection["tool_name"]]
        all_tools_to_try = primary_tools + input_data.fallback_tools
        
        for tool_name in all_tools_to_try:
            try:
                parameters = tool_selection["parameters"].copy()
                
                result = await self.tool_registry.call_tool(
                    tool_name=tool_name,
                    action=tool_selection["action"],
                    **parameters
                )
                
                return ToolAgentOutput(
                    success=True,
                    result=result,
                    tool_used=tool_name,
                    action_taken=tool_selection["action"],
                    confidence=tool_selection["confidence"],
                    reasoning=tool_selection["reasoning"],
                    alternatives_tried=alternatives_tried,
                    metadata={"parameters": parameters}
                )
                
            except Exception as e:
                alternatives_tried.append(tool_name)
                context.logger.warning(f"工具 {tool_name} 执行失败: {str(e)}")
                continue
        
        # 所有工具都失败了
        return ToolAgentOutput(
            success=False,
            result=None,
            tool_used=tool_selection.get("tool_name", "unknown"),
            action_taken=tool_selection.get("action", "unknown"),
            confidence=tool_selection.get("confidence", 0.0),
            reasoning=tool_selection.get("reasoning", ""),
            alternatives_tried=alternatives_tried,
            error_message=f"所有工具都执行失败，尝试过: {alternatives_tried}"
        )
    
    def _get_filtered_tools(self, input_data: ToolAgentInput) -> List[str]:
        """获取预筛选的工具列表"""
        if input_data.allowed_tools:
            return input_data.allowed_tools
        else:
            # 如果没有预筛选，使用所有可用工具（不推荐）
            return self._get_all_available_tools()
    
    async def _select_tool_with_confidence(
        self, 
        input_data: ToolAgentInput, 
        available_tools: List[str]
    ) -> Dict[str, Any]:
        """LLM选择工具并返回置信度"""
        
        # 构建工具描述
        tool_descriptions = self._get_tool_descriptions(available_tools)
        
        analysis_prompt = f"""
        任务描述: {input_data.task_description}
        上下文数据: {input_data.context_data}
        约束条件: {input_data.constraints}
        
        可用工具及描述:
        {tool_descriptions}
        
        请分析这个任务应该：
        1. 使用哪个工具（必须从可用工具中选择）
        2. 调用什么动作
        3. 需要什么参数
        4. 你对这个选择的置信度（0-1）
        5. 选择这个工具的理由
        
        返回JSON格式：
        {{
            "tool_name": "工具名称",
            "action": "动作名称", 
            "parameters": {{参数字典}},
            "confidence": 0.95,
            "reasoning": "选择理由和分析过程"
        }}
        """
        
        # LLM推理得到工具选择结果
        tool_selection = await self.provider.analyze(analysis_prompt)
        
        # 验证选择的工具是否在允许范围内
        if tool_selection["tool_name"] not in available_tools:
            tool_selection["tool_name"] = available_tools[0]
            tool_selection["confidence"] = 0.3
            tool_selection["reasoning"] += " [警告: 原选择工具不可用，自动回退]"
        
        return tool_selection
    
    def _get_tool_descriptions(self, tool_names: List[str]) -> str:
        """获取工具的详细描述"""
        descriptions = []
        for tool_name in tool_names:
            tool_info = self.tool_registry.get_tool_info(tool_name)
            descriptions.append(f"- {tool_name}: {tool_info.get('description', '无描述')}")
        return "\n".join(descriptions)
```

#### 3.2.3 使用示例

```python
# 示例1: 填写表单（预筛选工具）
tool_input = ToolAgentInput(
    task_description="在企业微信中填写路演申请表单",
    context_data={
        "customer_name": "张三",
        "presentation_time": "2024年1月15日下午2点",
        "form_url": "https://work.weixin.qq.com/form/123"
    },
    constraints=["必须填写所有必填字段", "提交前需要检查数据准确性"],
    allowed_tools=["browser_use"],  # 预筛选：只允许使用浏览器工具
    fallback_tools=["android_use"],  # 备选：如果浏览器失败，尝试手机端
    confidence_threshold=0.8
)

result = await tool_agent.execute(tool_input, context)
# 输出: ToolAgentOutput(
#   success=True, 
#   result="表单提交成功", 
#   tool_used="browser_use", 
#   action_taken="fill_form",
#   confidence=0.95,
#   reasoning="任务明确是网页表单操作，browser_use是最佳选择"
# )

# 示例2: 移动端操作（多工具回退）
tool_input = ToolAgentInput(
    task_description="读取微信中与张三的聊天记录",
    context_data={"contact_name": "张三"},
    allowed_tools=["android_use"],
    fallback_tools=["browser_use"],  # 如果手机端失败，尝试网页版微信
    confidence_threshold=0.7
)

result = await tool_agent.execute(tool_input, context)
# 如果android_use失败，会自动尝试browser_use
```

### 3.3 Code Agent

#### 3.3.1 输入输出规范

```python
class CodeAgentInput(BaseModel):
    """Code Agent 输入规范"""
    task_description: str = Field(..., description="任务描述，用自然语言描述要完成什么")
    input_data: Any = Field(..., description="输入数据")
    expected_output_format: str = Field(..., description="期望的输出格式描述")
    constraints: List[str] = Field(default_factory=list, description="约束条件")
    libraries_allowed: List[str] = Field(default_factory=list, description="允许使用的库")

class CodeAgentOutput(BaseModel):
    """Code Agent 输出规范"""
    success: bool = Field(..., description="执行是否成功")
    result: Any = Field(..., description="代码执行结果")
    code_generated: str = Field(..., description="生成的代码")
    execution_info: Dict[str, Any] = Field(default_factory=dict, description="执行信息")
    stdout: str = Field(default="", description="标准输出")
    stderr: str = Field(default="", description="错误输出")
    error_message: Optional[str] = Field(default=None, description="错误信息")
```

#### 3.3.2 处理逻辑

```python
class CodeAgent:
    """代码生成执行Agent"""
    
    async def execute(self, input_data: CodeAgentInput, context: AgentContext) -> CodeAgentOutput:
        """
        执行流程：
        1. LLM分析任务需求
        2. 生成Python代码
        3. 代码安全检查
        4. 执行代码
        5. 返回结果
        """
        
        # Step 1: LLM生成代码
        code_prompt = f"""
        任务描述: {input_data.task_description}
        输入数据: {input_data.input_data}
        期望输出格式: {input_data.expected_output_format}
        约束条件: {input_data.constraints}
        允许使用的库: {input_data.libraries_allowed}
        
        请生成Python代码来完成这个任务。要求：
        1. 代码要能处理给定的输入数据
        2. 输出格式要符合期望
        3. 只使用允许的库
        4. 代码要安全，不能有恶意操作
        5. 最后要将结果赋值给变量'result'
        
        只返回Python代码，不要解释：
        ```python
        # 你的代码
        ```
        """
        
        # LLM生成代码
        generated_code = await self.provider.generate_code(code_prompt)
        
        # Step 2: 代码安全检查
        if not await self._is_code_safe(generated_code):
            return CodeAgentOutput(
                success=False,
                result=None,
                code_generated=generated_code,
                error_message="生成的代码不安全"
            )
        
        # Step 3: 执行代码
        try:
            execution_result = await self.code_executor.execute(
                code=generated_code,
                input_data=input_data.input_data,
                timeout=30,
                allowed_libraries=input_data.libraries_allowed
            )
            
            return CodeAgentOutput(
                success=True,
                result=execution_result.result,
                code_generated=generated_code,
                execution_info=execution_result.info,
                stdout=execution_result.stdout,
                stderr=execution_result.stderr
            )
            
        except Exception as e:
            return CodeAgentOutput(
                success=False,
                result=None,
                code_generated=generated_code,
                error_message=str(e)
            )
```

#### 3.3.3 使用示例

```python
# 示例1: 数据分析
code_input = CodeAgentInput(
    task_description="分析聊天记录中的情感倾向，统计正面、负面、中性的比例",
    input_data={
        "chat_messages": [
            "今天天气真好！",
            "这个产品太差了",
            "会议时间确定了吗？"
        ]
    },
    expected_output_format="字典格式：{'positive': 比例, 'negative': 比例, 'neutral': 比例}",
    constraints=["使用中文情感分析", "结果保留2位小数"],
    libraries_allowed=["re", "collections", "math"]
)

result = await code_agent.execute(code_input, context)
# 输出: CodeAgentOutput(success=True, result={'positive': 0.33, 'negative': 0.33, 'neutral': 0.33}, code_generated="...")
```

### 3.4 Agent选择策略

#### 3.4.1 自动路由逻辑

```python
class AgentRouter:
    """Agent路由器"""
    
    async def route_to_agent(self, task_description: str, context: AgentContext) -> str:
        """
        根据任务描述自动选择合适的Agent
        """
        
        routing_prompt = f"""
        任务描述: {task_description}
        可用工具: {self._get_available_tools()}
        
        请判断这个任务应该用哪种Agent来处理：
        
        1. text_agent: 如果只需要生成文本回答
        2. tool_agent: 如果有现成的工具可以完成任务
        3. code_agent: 如果需要编写代码来解决问题
        
        判断依据：
        - 如果任务是"回答问题"、"解释说明"、"总结内容"等，用text_agent
        - 如果任务是"填写表单"、"点击按钮"、"读取聊天"等，用tool_agent  
        - 如果任务是"数据分析"、"格式转换"、"复杂计算"等，用code_agent
        
        只返回：text_agent 或 tool_agent 或 code_agent
        """
        
        agent_type = await self.provider.analyze(routing_prompt)
        return agent_type.strip().lower()
```

---

## 4. 工具选择优化策略

### 4.1 核心问题与解决方案

**问题**: 当系统中可用工具过多时，LLM可能无法准确选择合适的工具，导致选择错误或效率低下。

**解决方案**: **Workflow层面工具预筛选 + Agent层面置信度机制**

#### 4.1.1 设计理念

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Workflow设计   │───▶│   Tool Agent    │───▶│   工具执行      │
│  (人工预筛选)   │    │  (智能选择)     │    │  (自动回退)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
     │                        │                       │
     ▼                        ▼                       ▼
• 根据业务经验           • 在预筛选范围内         • 主工具失败时
• 限定工具范围           • LLM选择最佳工具        • 自动尝试备选工具
• 指定备选方案           • 返回置信度分数         • 记录尝试过程
```

#### 4.1.2 优势分析

| 层面 | 责任 | 优势 |
|------|------|------|
| **Workflow设计** | 人工预筛选工具范围 | 结合业务经验，避免明显错误选择 |
| **Tool Agent** | LLM在限定范围内选择 | 减少选择空间，提高准确率 |
| **执行机制** | 自动回退和重试 | 提供容错能力，增强系统鲁棒性 |

---

## 5. 系统集成

### 5.1 更新的AgentWorkflowStep

```python
class AgentWorkflowStep(BaseModel):
    """Agent工作流步骤"""
    # 基础信息
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="步骤名称")
    description: str = Field(default="", description="步骤描述")
    
    # Agent配置
    agent_type: str = Field(..., description="Agent类型: text_agent | tool_agent | code_agent | auto")
    task_description: str = Field(..., description="任务描述")
    
    # 输入配置 (更新的字段名)
    input_ports: Dict[str, Any] = Field(default_factory=dict, description="输入映射")
    constraints: List[str] = Field(default_factory=list, description="约束条件")
    
    # Tool Agent 特有配置
    allowed_tools: List[str] = Field(default_factory=list, description="允许使用的工具列表")
    fallback_tools: List[str] = Field(default_factory=list, description="备选工具列表") 
    confidence_threshold: float = Field(default=0.8, description="工具选择置信度阈值")
    
    # Code Agent 特有配置
    allowed_libraries: List[str] = Field(default_factory=list, description="允许使用的代码库")
    expected_output_format: str = Field(default="", description="期望的输出格式")
    
    # Text Agent 特有配置
    response_style: str = Field(default="professional", description="回答风格")
    max_length: int = Field(default=500, description="最大回答长度")
    
    # 输出配置 (更新的字段名)
    output_ports: Dict[str, str] = Field(default_factory=dict, description="输出映射")
    
    # 执行控制
    condition: Optional[str] = Field(default=None, description="执行条件")
    timeout: int = Field(default=300, description="超时时间")
    retry_count: int = Field(default=0, description="重试次数")
```

### 5.2 最终结果提取机制

**重要更新**: 工作流引擎现在采用新的最终结果提取逻辑：

```python
# WorkflowEngine 中的关键变化
async def execute_workflow(self, steps: List[AgentWorkflowStep], ...):
    executed_steps = []
    last_step_output = None  # 跟踪最后一步的输出
    
    for step in steps:
        # 执行步骤...
        step_result = await self._execute_agent_step(step, context)
        
        # 更新上下文变量和最后一步输出
        if step_result.success and step.output_ports:
            await self._update_context_variables(step_result, step.output_ports, context)
            # 每次成功执行都更新最后一步输出
            last_step_output = await self._extract_step_outputs(step_result, step.output_ports)
    
    return WorkflowResult(
        success=True,
        workflow_id=workflow_id,
        steps=executed_steps,
        # 新的逻辑：返回最后一步的输出，而不是全部上下文变量
        final_result=last_step_output if last_step_output is not None else context.variables,
        total_execution_time=time.time() - start_time
    )
```

### 5.3 工作流执行示例

```python
# 完整的工作流定义（在设计阶段就预筛选工具）
workflow_steps = [
    AgentWorkflowStep(
        name="获取客户聊天记录",
        agent_type="tool_agent",
        task_description="从微信中读取与指定客户的聊天记录",
        # 工作流设计者在这里预筛选工具，避免LLM选择错误
        allowed_tools=["android_use"],  # 明确只能用手机端操作
        fallback_tools=["browser_use"], # 失败时尝试网页版
        confidence_threshold=0.8,
        input_ports={
            "context_data": {
                "customer_name": "{{customer_name}}"
            }
        },
        output_ports={
            "result": "chat_content"
        }
    ),
    
    AgentWorkflowStep(
        name="提取关键信息",
        agent_type="code_agent", 
        task_description="从聊天记录中提取客户姓名、路演时间、地点等关键信息",
        input_ports={
            "input_data": "{{chat_content}}"
        },
        constraints=["输出必须是JSON格式", "时间格式为YYYY-MM-DD HH:MM"],
        output_ports={
            "result": "extracted_info"
        }
    ),
    
    AgentWorkflowStep(
        name="填写路演申请表",
        agent_type="tool_agent", 
        task_description="在企业微信中填写路演申请表单",
        # 表单填写明确使用浏览器工具
        allowed_tools=["browser_use"],
        fallback_tools=["android_use"],  # 网页失败时尝试手机端
        confidence_threshold=0.9,  # 表单操作要求高置信度
        input_ports={
            "context_data": "{{extracted_info}}"
        },
        constraints=["必须填写所有必填字段"],
        output_ports={
            "result": "form_result"
        }
    ),
    
    AgentWorkflowStep(
        name="生成确认回复",
        agent_type="text_agent",
        task_description="根据表单提交结果，生成给客户的确认回复消息",
        input_ports={
            "context_data": {
                "customer_name": "{{customer_name}}",
                "form_result": "{{form_result}}",
                "extracted_info": "{{extracted_info}}"
            }
        },
        constraints=["语调要专业友好", "包含下一步安排"],
        output_ports={
            "answer": "reply_message"
        }
    )
]

# 执行工作流
engine = WorkflowEngine()
result = await engine.execute_workflow(
    steps=workflow_steps,
    input_data={"customer_name": "张三"}
)

# 新的行为：final_result 现在直接是最后一步的输出
print(f"客户回复消息: {result.final_result}")  # 直接是 reply_message 的值
```

---

## 6. 架构优势与改进

### 6.1 设计优势

1. **输入输出明确**: 每个Agent都有清晰的输入输出规范
2. **智能化路由**: 基于LLM自动选择最合适的处理方式
3. **统一接口**: Text、Tool、Code三种Agent都遵循相同的接口规范
4. **高度灵活**: 支持从简单问答到复杂任务的任意组合
5. **数据流清晰**: 新的最终结果提取机制让输出更直观

### 6.2 技术优势

1. **简化架构**: 只有三种Agent类型，覆盖所有业务场景，易于理解和维护
2. **LLM驱动**: 所有决策都由LLM进行，智能化程度高
3. **安全可控**: Code Agent有安全检查机制
4. **可扩展性**: 易于添加新的工具和能力
5. **容错机制**: 工具回退和重试机制提高系统鲁棒性

### 6.3 最新改进

1. **最终结果优化**: `final_result` 现在只返回最后一步的实际输出，避免冗余信息
2. **字段名称统一**: 使用 `input_ports` 和 `output_ports` 替代旧的映射字段名
3. **执行引擎简化**: 移除了复杂的端口连接机制，采用更直观的变量引用方式
4. **数据流追踪**: 新增了最后一步输出的自动追踪机制

---

## 7. 实施状态

### 7.1 已完成功能 ✅
- [x] 实现基础的TextAgent、ToolAgent和CodeAgent
- [x] 实现AgentRouter自动路由
- [x] 集成工具预筛选机制
- [x] 集成到WorkflowEngine
- [x] 完善最终结果提取逻辑
- [x] 移除过时的WorkflowStep类

### 7.2 当前架构特点
- [x] 完善置信度机制和自动回退
- [x] 支持多种Agent类型的条件执行
- [x] 实现变量引用和数据流管理
- [x] 添加执行监控和日志

### 7.3 持续优化方向
- [ ] 性能优化和工具选择算法优化
- [ ] 错误处理完善和恢复机制
- [ ] 更多工具集成和工具描述完善
- [ ] 并行执行支持

---

这个架构设计更加聚焦实用，完全基于最新的代码实现，提供了清晰的Agent分工和高效的执行机制。新的最终结果提取逻辑让工作流的输出更加直观和易用。