# Workflow 模块需求分析文档

## 产品概述

Workflow 模块是 BaseAgent 的核心执行框架，负责协调和管理Agent的整个执行流程。该模块将用户请求转化为可执行的步骤序列，通过调用 Agent、Tools 或执行代码来完成任务。

## 核心需求分析

### 1. 执行框架需求

#### 1.1 Workflow 作为主执行框架
- **统一入口**：所有用户请求都通过 workflow 进行处理
- **步骤编排**：将复杂任务分解为可管理的执行步骤
- **流程控制**：支持顺序执行、条件判断等基本控制流
- **状态管理**：跟踪整个执行过程的状态和结果

#### 1.2 多类型步骤支持
- **Agent 调用**：调用其他 Agent 处理复杂子任务
- **Tools 调用**：执行具体的工具操作（browser、android等）
- **Code 执行**：执行自定义代码逻辑
- **Memory 操作**：搜索和存储记忆信息

### 2. BaseAgent 执行模式

#### 2.1 标准执行流程
用户请求处理的标准流程：
1. **接收用户输入**：获取用户问题或指令
2. **工具调用**：根据需要调用相应的tools
3. **记忆搜索**：从memory中搜索相关历史信息
4. **信息整合**：将工具结果和记忆信息组织整合
5. **响应生成**：发送组织后的信息给用户
6. **等待下次输入**：准备处理下一个用户请求

#### 2.2 执行特点
- **问题复杂度**：主要处理中等复杂度的用户问题
- **工具优先**：优先通过工具获取实时信息
- **记忆辅助**：利用历史记忆提供上下文支持
- **响应及时**：快速响应用户，保持交互流畅

### 3. Workflow 结构需求

#### 3.1 WorkflowStep 定义
每个工作流步骤需要包含：
```python
class WorkflowStep:
    name: str                    # 步骤名称
    step_type: str              # 步骤类型: "agent" | "tool" | "code" | "memory"
    
    # 通用参数
    params: Dict[str, Any]       # 步骤参数
    condition: Optional[str]     # 执行条件（可选）
    
    # Agent 调用
    agent_name: Optional[str]    # Agent名称
    agent_input: Optional[Any]   # Agent输入
    
    # Tool 调用
    tool_name: Optional[str]     # 工具名称
    action: Optional[str]        # 工具动作
    
    # Code 执行
    code: Optional[str]          # 代码内容
    
    # Memory 操作
    memory_action: Optional[str] # memory动作: "search" | "store"
    query: Optional[str]         # 搜索查询
```

#### 3.2 Workflow 定义
```python
class Workflow:
    name: str                    # 工作流名称
    description: str             # 工作流描述
    steps: List[WorkflowStep]    # 执行步骤列表
    input_schema: Dict           # 输入参数定义
    output_schema: Dict          # 输出结果定义
```

### 4. 执行引擎需求

#### 4.1 WorkflowEngine 核心功能
- **步骤执行**：按顺序执行workflow中的各个步骤
- **上下文传递**：在步骤间传递执行结果和变量
- **错误处理**：捕获和处理执行过程中的异常
- **结果收集**：收集各步骤的执行结果

#### 4.2 执行接口
```python
class WorkflowEngine:
    async def execute_workflow(
        self, 
        workflow: Workflow, 
        input_data: Dict[str, Any]
    ) -> WorkflowResult
    
    async def execute_step(
        self, 
        step: WorkflowStep, 
        context: ExecutionContext
    ) -> StepResult
```

### 5. BaseAgent 集成需求

#### 5.1 默认 Workflow 模板
为 BaseAgent 创建标准的执行模板：
```python
# 用户问答处理 workflow
user_qa_workflow = Workflow(
    name="user_qa_processing",
    description="处理用户问题的标准流程",
    steps=[
        # 1. 分析用户输入
        WorkflowStep(
            name="analyze_input",
            step_type="code",
            code="# 分析用户输入，确定需要的工具"
        ),
        
        # 2. 搜索相关记忆
        WorkflowStep(
            name="search_memory",
            step_type="memory",
            memory_action="search",
            query="{{user_input}}"
        ),
        
        # 3. 调用工具获取信息
        WorkflowStep(
            name="use_tools",
            step_type="tool",
            tool_name="{{selected_tool}}",
            action="{{tool_action}}",
            condition="need_tool_info"
        ),
        
        # 4. 整合信息并响应
        WorkflowStep(
            name="generate_response",
            step_type="code",
            code="# 整合工具结果和记忆信息，生成响应"
        )
    ]
)
```

#### 5.2 Agent 接口集成
```python
class BaseAgent:
    def __init__(self):
        self.workflow_engine = WorkflowEngine()
        self.default_workflow = self._load_default_workflow()
    
    async def process_user_input(self, user_input: str) -> str:
        """处理用户输入的主方法"""
        result = await self.workflow_engine.execute_workflow(
            self.default_workflow,
            {"user_input": user_input}
        )
        return result.final_response
```

### 6. 高级功能需求

#### 6.1 条件执行
- **简单条件**：支持基于前一步结果的条件判断
- **跳转逻辑**：根据条件跳过或执行特定步骤
- **变量引用**：步骤间通过变量引用传递数据

#### 6.2 并行执行（未来扩展）
- **独立步骤**：识别可以并行执行的独立步骤
- **结果合并**：合并并行步骤的执行结果
- **依赖管理**：处理步骤间的依赖关系

### 7. 错误处理需求

#### 7.1 步骤级错误处理
- **异常捕获**：捕获单个步骤的执行异常
- **重试机制**：对失败步骤进行有限次数重试
- **降级处理**：提供备用执行方案

#### 7.2 Workflow 级错误处理
- **整体回滚**：在严重错误时停止整个workflow
- **部分结果**：即使部分步骤失败也返回可用结果
- **错误报告**：详细记录错误信息和执行状态

### 8. 性能和监控需求

#### 8.1 执行监控
- **步骤计时**：记录每个步骤的执行时间
- **资源使用**：监控内存和计算资源使用
- **执行日志**：详细记录执行过程

#### 8.2 性能优化
- **缓存机制**：缓存常用步骤的执行结果
- **懒加载**：按需加载工具和资源
- **资源管理**：合理管理系统资源

### 9. 扩展性需求

#### 9.1 自定义步骤类型
- **插件机制**：支持注册自定义步骤类型
- **步骤库**：提供常用步骤的预定义库
- **模板系统**：支持workflow模板的创建和共享

#### 9.2 动态workflow
- **运行时修改**：支持在执行过程中修改workflow
- **条件分支**：根据运行时条件选择不同的执行路径
- **用户交互**：支持在workflow中插入用户交互步骤

### 10. 实现优先级

#### 10.1 第一阶段（核心功能）
1. WorkflowEngine 基础实现
2. 支持 agent、tool、code、memory 四种基本步骤类型
3. BaseAgent 的默认 workflow 集成
4. 基本的错误处理和日志记录

#### 10.2 第二阶段（增强功能）
1. 条件执行和变量引用
2. Workflow 模板系统
3. 性能监控和优化
4. 更丰富的错误处理机制

#### 10.3 第三阶段（高级功能）
1. 并行执行支持
2. 动态 workflow 修改
3. 用户交互步骤
4. 插件化扩展机制

## 成功标准

### 功能完整性
- ✅ 支持四种基本步骤类型的执行
- ✅ BaseAgent 能通过 workflow 处理用户请求
- ✅ 步骤间能正确传递数据和上下文
- ✅ 基本的错误处理和恢复机制

### 易用性
- ✅ 提供简洁清晰的 API 接口
- ✅ 丰富的文档和使用示例
- ✅ 合理的默认配置和模板

### 可扩展性
- ✅ 支持自定义步骤类型
- ✅ 支持自定义 workflow 定义
- ✅ 为未来功能扩展预留接口

这个需求分析为 Workflow 模块的实现提供了清晰的方向和具体的功能要求，确保实现的系统既满足当前需求又具备未来扩展的能力。