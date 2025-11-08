# BaseAgent 上下文保持的动态加载架构设计

## 设计理念

基于对方案2潜在上下文丢失问题的分析，设计一个既支持动态加载又能保持完整上下文的架构。通过分层设计，确保从用户需求到技术实现的每个环节都保持清晰的上下文信息，为 Agentic Code 提供语义化的编程接口。

## 核心问题：上下文丢失的风险

### 原方案2的问题
1. **配置碎片化**：workflow、steps、memory 分离，缺少整体关联
2. **语义信息丢失**：技术配置缺少业务意图和设计决策
3. **需求与实现断层**：用户需求无法追溯到具体实现

### 解决方案：三层架构保持上下文

```
用户需求层 (Requirements Layer)
    ↓ (保持原始需求上下文)
设计层 (Design Layer)  
    ↓ (保持设计决策上下文)
实现层 (Implementation Layer)
```

## 架构设计

### 1. 核心数据结构

#### 1.1 完整的Agent定义
```python
class AgentDefinition:
    """完整的Agent定义，保持所有层次的上下文"""
    
    # ==================== 用户需求层 ====================
    user_requirements: str                      # 原始用户需求
    agent_purpose: str                         # Agent用途描述
    expected_capabilities: List[str]           # 期望能力列表
    business_constraints: List[str]            # 业务约束
    
    # ==================== 设计层 ====================
    workflow_design: WorkflowDesign           # 工作流设计
    step_designs: List[StepDesign]            # 步骤设计
    memory_design: MemoryDesign               # 记忆设计
    integration_design: IntegrationDesign     # 集成设计
    
    # ==================== 实现层 ====================
    workflow_config: Dict[str, Any]          # 工作流技术配置
    steps_config: List[Dict[str, Any]]       # 步骤技术配置
    memory_config: Dict[str, Any]            # 记忆技术配置
    
    # ==================== 上下文信息 ====================
    design_rationale: Dict[str, str]         # 设计决策说明
    implementation_notes: List[str]          # 实现注意事项
    context_mappings: Dict[str, str]         # 需求→设计→实现映射
    
    # ==================== 元数据 ====================
    created_by: str = "Agentic Code"         # 创建者
    creation_time: datetime                   # 创建时间
    version: str = "1.0.0"                   # 版本
    tags: List[str] = []                      # 标签
```

#### 1.2 工作流设计（保持业务上下文）
```python
class WorkflowDesign:
    """工作流设计，保持业务逻辑上下文"""
    
    name: str                                 # 工作流名称
    purpose: str                              # 业务目的
    business_logic: str                       # 业务逻辑描述
    target_scenarios: List[str]              # 目标场景
    
    # 流程设计
    step_flows: List[StepFlow]               # 步骤流转关系
    decision_points: List[DecisionPoint]     # 决策点
    error_handling: List[ErrorHandling]     # 错误处理策略
    
    # 性能设计
    expected_execution_time: int             # 预期执行时间
    parallel_opportunities: List[str]       # 并行执行机会
    
    # 业务规则
    business_rules: List[BusinessRule]       # 业务规则
    quality_requirements: List[str]          # 质量要求

class StepFlow:
    """步骤流转（保持流程上下文）"""
    
    from_step: str                           # 源步骤
    to_step: str                             # 目标步骤
    condition: Optional[str]                 # 流转条件
    business_reason: str                     # 业务原因
    data_transfer: Dict[str, str]           # 数据传递说明

class DecisionPoint:
    """决策点（保持决策上下文）"""
    
    step_id: str                            # 决策步骤ID
    decision_logic: str                     # 决策逻辑描述
    decision_criteria: List[str]            # 决策标准
    options: Dict[str, str]                 # 选项说明
    fallback_strategy: str                  # 兜底策略

class BusinessRule:
    """业务规则（保持规则上下文）"""
    
    rule_id: str                            # 规则ID
    description: str                        # 规则描述
    condition: str                          # 触发条件
    action: str                             # 执行动作
    priority: int                           # 优先级
    rationale: str                          # 设立原因
```

#### 1.3 步骤设计（保持执行上下文）
```python
class StepDesign:
    """步骤设计，保持执行上下文"""
    
    step_id: str                            # 步骤ID
    name: str                               # 步骤名称
    purpose: str                            # 业务目的
    
    # 输入输出设计
    input_description: str                  # 输入说明
    expected_input_format: str              # 预期输入格式
    output_description: str                 # 输出说明
    expected_output_format: str             # 预期输出格式
    
    # 执行设计
    implementation_strategy: str            # 实现策略 (text_agent/tool_agent/code_agent)
    execution_approach: str                 # 执行方法描述
    business_rules: List[str]              # 适用的业务规则
    error_scenarios: List[ErrorScenario]   # 错误场景处理
    
    # 性能设计
    timeout_requirement: int               # 超时要求
    retry_strategy: str                    # 重试策略
    success_criteria: List[str]           # 成功标准
    
    # Agent特定设计
    text_agent_design: Optional[TextAgentDesign] = None
    tool_agent_design: Optional[ToolAgentDesign] = None
    code_agent_design: Optional[CodeAgentDesign] = None

class TextAgentDesign:
    """文本Agent设计"""
    
    prompt_strategy: str                    # 提示词策略
    response_style: str                     # 回答风格
    context_usage: str                      # 上下文使用方式
    prompt_template: str                    # 提示词模板
    fallback_responses: List[str]          # 兜底回答

class ToolAgentDesign:
    """工具Agent设计"""
    
    tool_selection_strategy: str           # 工具选择策略
    available_tools: List[str]             # 可用工具
    tool_usage_scenarios: Dict[str, str]   # 工具使用场景
    fallback_tools: List[str]              # 备选工具
    confidence_threshold: float            # 置信度阈值

class CodeAgentDesign:
    """代码Agent设计"""
    
    code_generation_strategy: str          # 代码生成策略
    allowed_libraries: List[str]           # 允许的库
    code_templates: List[str]              # 代码模板
    security_constraints: List[str]        # 安全约束
    execution_environment: str             # 执行环境
```

#### 1.4 记忆设计（保持记忆上下文）
```python
class MemoryDesign:
    """记忆设计，保持记忆管理上下文"""
    
    memory_purpose: str                     # 记忆用途
    storage_strategy: str                   # 存储策略
    retrieval_strategy: str                # 检索策略
    
    # 记忆类型设计
    short_term_memory: ShortTermMemoryDesign
    long_term_memory: LongTermMemoryDesign
    working_memory: WorkingMemoryDesign
    
    # 记忆管理规则
    retention_policy: str                   # 保留策略
    privacy_rules: List[str]               # 隐私规则
    sharing_rules: List[str]               # 共享规则

class ShortTermMemoryDesign:
    """短期记忆设计"""
    
    purpose: str                           # 用途
    retention_duration: int               # 保留时长
    storage_format: str                   # 存储格式
    cleanup_strategy: str                 # 清理策略

class LongTermMemoryDesign:
    """长期记忆设计"""
    
    purpose: str                          # 用途
    indexing_strategy: str                # 索引策略
    search_capabilities: List[str]        # 搜索能力
    embedding_model: str                  # 嵌入模型
```

### 2. 上下文保持的Builder接口

#### 2.1 主Builder类
```python
class ContextualAgentBuilder:
    """保持上下文的Agent构建器"""
    
    def __init__(self):
        self.agent_definition = AgentDefinition()
        self.context_tracker = ContextTracker()  # 上下文追踪器
    
    # ==================== 需求层接口 ====================
    
    def set_user_requirements(self, requirements: str) -> 'ContextualAgentBuilder':
        """设置用户需求（保持原始上下文）"""
        self.agent_definition.user_requirements = requirements
        self.context_tracker.record_requirement("user_input", requirements)
        return self
    
    def define_agent_purpose(self, purpose: str) -> 'ContextualAgentBuilder':
        """定义Agent用途（保持业务上下文）"""
        self.agent_definition.agent_purpose = purpose
        self.context_tracker.record_design_decision("agent_purpose", purpose, 
                                                   "基于用户需求分析得出")
        return self
    
    def add_capability_requirement(self, capability: str, reason: str = "") -> 'ContextualAgentBuilder':
        """添加能力需求（保持需求上下文）"""
        self.agent_definition.expected_capabilities.append(capability)
        self.context_tracker.record_requirement("capability", capability, reason)
        return self
    
    def add_business_constraint(self, constraint: str, reason: str = "") -> 'ContextualAgentBuilder':
        """添加业务约束（保持约束上下文）"""
        self.agent_definition.business_constraints.append(constraint)
        self.context_tracker.record_constraint("business", constraint, reason)
        return self
    
    # ==================== 设计层接口 ====================
    
    def design_workflow(self, name: str, purpose: str, business_logic: str) -> 'WorkflowDesigner':
        """设计工作流（保持业务上下文）"""
        workflow_design = WorkflowDesign(
            name=name,
            purpose=purpose,
            business_logic=business_logic
        )
        self.agent_definition.workflow_design = workflow_design
        self.context_tracker.record_design_decision("workflow_design", 
                                                   f"设计了工作流: {name}", 
                                                   f"目的: {purpose}")
        return WorkflowDesigner(workflow_design, self)
    
    def design_step(self, step_id: str, name: str, purpose: str) -> 'StepDesigner':
        """设计步骤（保持执行上下文）"""
        step_design = StepDesign(
            step_id=step_id,
            name=name,
            purpose=purpose
        )
        self.agent_definition.step_designs.append(step_design)
        self.context_tracker.record_design_decision("step_design", 
                                                   f"设计了步骤: {step_id}", 
                                                   f"目的: {purpose}")
        return StepDesigner(step_design, self)
    
    def design_memory(self, purpose: str, storage_strategy: str) -> 'MemoryDesigner':
        """设计记忆（保持记忆上下文）"""
        memory_design = MemoryDesign(
            memory_purpose=purpose,
            storage_strategy=storage_strategy
        )
        self.agent_definition.memory_design = memory_design
        self.context_tracker.record_design_decision("memory_design", 
                                                   f"设计了记忆系统", 
                                                   f"目的: {purpose}")
        return MemoryDesigner(memory_design, self)
    
    # ==================== 实现层接口 ====================
    
    def generate_configurations(self) -> Dict[str, Any]:
        """从设计生成技术配置（保持设计→实现的映射）"""
        
        # 生成工作流配置
        workflow_config = self._generate_workflow_config()
        
        # 生成步骤配置
        steps_config = self._generate_steps_config()
        
        # 生成记忆配置
        memory_config = self._generate_memory_config()
        
        # 记录实现决策
        self.context_tracker.record_implementation("configuration_generation", 
                                                  "生成了技术配置", 
                                                  "基于设计层的决策")
        
        return {
            "workflow": workflow_config,
            "steps": steps_config,
            "memory": memory_config,
            "context": {
                "user_requirements": self.agent_definition.user_requirements,
                "agent_purpose": self.agent_definition.agent_purpose,
                "design_rationale": self.agent_definition.design_rationale,
                "context_mappings": self.context_tracker.get_mappings(),
                "implementation_notes": self.agent_definition.implementation_notes
            }
        }
    
    def build_agent(self) -> 'DynamicBaseAgent':
        """构建最终的Agent实例"""
        configurations = self.generate_configurations()
        
        agent = DynamicBaseAgent()
        agent.load_components(configurations)
        
        # 注入上下文信息到Agent
        agent.set_context_info(configurations["context"])
        
        return agent
```

#### 2.2 专用设计器类
```python
class WorkflowDesigner:
    """工作流设计器（保持设计上下文）"""
    
    def __init__(self, workflow_design: WorkflowDesign, builder: ContextualAgentBuilder):
        self.workflow_design = workflow_design
        self.builder = builder
    
    def add_step_flow(self, from_step: str, to_step: str, 
                     condition: str = None, reason: str = "") -> 'WorkflowDesigner':
        """添加步骤流转（保持业务逻辑上下文）"""
        flow = StepFlow(
            from_step=from_step,
            to_step=to_step,
            condition=condition,
            business_reason=reason
        )
        self.workflow_design.step_flows.append(flow)
        
        self.builder.context_tracker.record_design_decision(
            "step_flow", 
            f"添加流转: {from_step} -> {to_step}",
            reason or "业务流程需要"
        )
        return self
    
    def add_decision_point(self, step_id: str, decision_logic: str, 
                          options: Dict[str, str], reason: str = "") -> 'WorkflowDesigner':
        """添加决策点（保持决策上下文）"""
        decision = DecisionPoint(
            step_id=step_id,
            decision_logic=decision_logic,
            options=options
        )
        self.workflow_design.decision_points.append(decision)
        
        self.builder.context_tracker.record_design_decision(
            "decision_point",
            f"在步骤 {step_id} 添加决策点",
            reason or "业务逻辑需要条件分支"
        )
        return self
    
    def add_business_rule(self, rule_id: str, description: str, 
                         condition: str, action: str, reason: str = "") -> 'WorkflowDesigner':
        """添加业务规则（保持规则上下文）"""
        rule = BusinessRule(
            rule_id=rule_id,
            description=description,
            condition=condition,
            action=action,
            rationale=reason
        )
        self.workflow_design.business_rules.append(rule)
        return self
    
    def finish_design(self) -> ContextualAgentBuilder:
        """完成工作流设计，返回主Builder"""
        return self.builder

class StepDesigner:
    """步骤设计器（保持步骤上下文）"""
    
    def __init__(self, step_design: StepDesign, builder: ContextualAgentBuilder):
        self.step_design = step_design
        self.builder = builder
    
    def as_text_agent(self, prompt_strategy: str, response_style: str = "professional",
                     reason: str = "") -> 'StepDesigner':
        """设计为文本Agent（保持设计决策上下文）"""
        self.step_design.implementation_strategy = "text_agent"
        self.step_design.text_agent_design = TextAgentDesign(
            prompt_strategy=prompt_strategy,
            response_style=response_style
        )
        
        self.builder.context_tracker.record_design_decision(
            "step_implementation",
            f"步骤 {self.step_design.step_id} 实现为 TextAgent",
            reason or f"需要文本生成能力，策略: {prompt_strategy}"
        )
        return self
    
    def as_tool_agent(self, tools: List[str], selection_strategy: str = "best_match",
                     reason: str = "") -> 'StepDesigner':
        """设计为工具Agent（保持工具选择上下文）"""
        self.step_design.implementation_strategy = "tool_agent"
        self.step_design.tool_agent_design = ToolAgentDesign(
            available_tools=tools,
            tool_selection_strategy=selection_strategy
        )
        
        self.builder.context_tracker.record_design_decision(
            "step_implementation",
            f"步骤 {self.step_design.step_id} 实现为 ToolAgent",
            reason or f"需要工具调用能力，工具: {tools}"
        )
        return self
    
    def as_code_agent(self, libraries: List[str], generation_strategy: str = "template_based",
                     reason: str = "") -> 'StepDesigner':
        """设计为代码Agent（保持代码生成上下文）"""
        self.step_design.implementation_strategy = "code_agent"
        self.step_design.code_agent_design = CodeAgentDesign(
            allowed_libraries=libraries,
            code_generation_strategy=generation_strategy
        )
        
        self.builder.context_tracker.record_design_decision(
            "step_implementation",
            f"步骤 {self.step_design.step_id} 实现为 CodeAgent",
            reason or f"需要代码生成能力，库: {libraries}"
        )
        return self
    
    def set_input_output(self, input_desc: str, output_desc: str, 
                        input_format: str = "", output_format: str = "") -> 'StepDesigner':
        """设置输入输出说明（保持数据流上下文）"""
        self.step_design.input_description = input_desc
        self.step_design.output_description = output_desc
        self.step_design.expected_input_format = input_format
        self.step_design.expected_output_format = output_format
        return self
    
    def add_business_rule(self, rule: str) -> 'StepDesigner':
        """添加业务规则（保持规则上下文）"""
        self.step_design.business_rules.append(rule)
        return self
    
    def finish_design(self) -> ContextualAgentBuilder:
        """完成步骤设计，返回主Builder"""
        return self.builder

class MemoryDesigner:
    """记忆设计器（保持记忆上下文）"""
    
    def __init__(self, memory_design: MemoryDesign, builder: ContextualAgentBuilder):
        self.memory_design = memory_design
        self.builder = builder
    
    def configure_short_term(self, purpose: str, retention_hours: int = 24) -> 'MemoryDesigner':
        """配置短期记忆"""
        self.memory_design.short_term_memory = ShortTermMemoryDesign(
            purpose=purpose,
            retention_duration=retention_hours * 3600
        )
        return self
    
    def configure_long_term(self, purpose: str, indexing_strategy: str = "semantic") -> 'MemoryDesigner':
        """配置长期记忆"""
        self.memory_design.long_term_memory = LongTermMemoryDesign(
            purpose=purpose,
            indexing_strategy=indexing_strategy
        )
        return self
    
    def finish_design(self) -> ContextualAgentBuilder:
        """完成记忆设计，返回主Builder"""
        return self.builder
```

#### 2.3 上下文追踪器
```python
class ContextTracker:
    """上下文追踪器，记录从需求到实现的完整链路"""
    
    def __init__(self):
        self.requirement_records = []      # 需求记录
        self.design_decisions = []         # 设计决策
        self.implementation_records = []   # 实现记录
        self.constraint_records = []       # 约束记录
        self.mappings = {}                # 映射关系
    
    def record_requirement(self, req_type: str, content: str, reason: str = ""):
        """记录需求"""
        record = {
            "type": req_type,
            "content": content,
            "reason": reason,
            "timestamp": datetime.now(),
            "id": f"req_{len(self.requirement_records)}"
        }
        self.requirement_records.append(record)
        return record["id"]
    
    def record_design_decision(self, decision_type: str, content: str, rationale: str = ""):
        """记录设计决策"""
        record = {
            "type": decision_type,
            "content": content,
            "rationale": rationale,
            "timestamp": datetime.now(),
            "id": f"design_{len(self.design_decisions)}"
        }
        self.design_decisions.append(record)
        return record["id"]
    
    def record_implementation(self, impl_type: str, content: str, basis: str = ""):
        """记录实现决策"""
        record = {
            "type": impl_type,
            "content": content,
            "basis": basis,
            "timestamp": datetime.now(),
            "id": f"impl_{len(self.implementation_records)}"
        }
        self.implementation_records.append(record)
        return record["id"]
    
    def create_mapping(self, requirement_id: str, design_id: str, implementation_id: str):
        """创建需求→设计→实现的映射"""
        self.mappings[requirement_id] = {
            "design": design_id,
            "implementation": implementation_id
        }
    
    def get_context_chain(self, item_id: str) -> Dict[str, Any]:
        """获取完整的上下文链"""
        # 返回从需求到实现的完整追踪链
        pass
    
    def get_mappings(self) -> Dict[str, Any]:
        """获取所有映射关系"""
        return {
            "requirement_to_design": self.mappings,
            "design_decisions": self.design_decisions,
            "implementation_records": self.implementation_records
        }
```

### 3. 为Agentic Code提供的示例

#### 3.1 完整的Agent创建示例
```python
async def create_data_analysis_agent():
    """
    用户需求：我需要一个数据分析助手，能够读取Excel文件，进行统计分析，并生成可视化报告
    
    这个示例展示了如何保持从需求到实现的完整上下文
    """
    
    # 1. 创建上下文化构建器
    builder = ContextualAgentBuilder()
    
    # 2. 设置用户需求层（保持原始需求上下文）
    builder.set_user_requirements(
        "我需要一个数据分析助手，能够读取Excel文件，进行统计分析，并生成可视化报告"
    ).define_agent_purpose(
        "协助用户完成Excel数据的读取、统计分析和可视化报告生成"
    ).add_capability_requirement(
        "file_reading", "用户需要读取Excel文件"
    ).add_capability_requirement(
        "statistical_analysis", "用户需要进行统计分析"
    ).add_capability_requirement(
        "visualization", "用户需要生成图表和报告"
    ).add_business_constraint(
        "data_privacy", "不能将用户数据发送到外部服务"
    )
    
    # 3. 设计工作流（保持业务逻辑上下文）
    workflow_designer = builder.design_workflow(
        name="数据分析工作流",
        purpose="指导用户完成从数据读取到报告生成的完整流程",
        business_logic="理解需求 → 读取数据 → 数据预处理 → 统计分析 → 生成可视化 → 生成报告"
    )
    
    # 添加流程步骤和决策点
    workflow_designer.add_step_flow(
        "understand_requirements", "read_excel_file",
        reason="必须先理解用户的具体分析需求和文件位置"
    ).add_step_flow(
        "read_excel_file", "preprocess_data",
        condition="file_reading_success",
        reason="文件读取成功后需要进行数据预处理"
    ).add_decision_point(
        "preprocess_data",
        "根据数据质量决定预处理策略",
        {
            "clean_data": "数据有缺失值或异常值需要清理",
            "transform_data": "数据格式需要转换",
            "direct_analysis": "数据质量良好，直接分析"
        },
        reason="不同的数据质量需要不同的处理方式"
    ).add_step_flow(
        "preprocess_data", "statistical_analysis",
        reason="数据预处理完成后进行统计分析"
    ).add_step_flow(
        "statistical_analysis", "generate_visualizations",
        reason="统计分析完成后生成可视化图表"
    ).add_step_flow(
        "generate_visualizations", "create_report",
        reason="可视化完成后整合成最终报告"
    ).add_business_rule(
        "data_privacy_rule",
        "所有数据处理必须在本地完成",
        "data_processing_start",
        "use_local_tools_only",
        reason="用户明确要求数据隐私保护"
    ).finish_design()
    
    # 4. 设计各个步骤（保持执行上下文）
    
    # 需求理解步骤
    builder.design_step(
        "understand_requirements",
        "理解分析需求",
        "与用户对话，明确分析目标、文件位置、期望的分析类型"
    ).as_text_agent(
        prompt_strategy="结构化提问，引导用户提供关键信息",
        response_style="friendly_professional",
        reason="需要友好地引导用户提供完整的需求信息"
    ).set_input_output(
        "用户的初始请求",
        "结构化的分析需求（文件路径、分析类型、期望输出）",
        "自然语言文本",
        "JSON格式的需求描述"
    ).add_business_rule(
        "必须获取文件路径和分析目标才能继续"
    ).finish_design()
    
    # 文件读取步骤
    builder.design_step(
        "read_excel_file",
        "读取Excel文件",
        "根据用户提供的文件路径读取Excel数据"
    ).as_tool_agent(
        tools=["excel_reader", "csv_reader", "data_validator"],
        selection_strategy="auto_detect_format",
        reason="需要自动检测文件格式并选择合适的读取工具"
    ).set_input_output(
        "文件路径和读取参数",
        "DataFrame格式的数据",
        "文件路径字符串",
        "pandas.DataFrame对象"
    ).add_business_rule(
        "如果文件读取失败，必须提供清晰的错误信息"
    ).finish_design()
    
    # 数据预处理步骤
    builder.design_step(
        "preprocess_data",
        "数据预处理",
        "检查数据质量，处理缺失值，进行必要的数据转换"
    ).as_code_agent(
        libraries=["pandas", "numpy"],
        generation_strategy="adaptive_based_on_data_quality",
        reason="数据预处理需要根据具体数据情况生成定制化的处理代码"
    ).set_input_output(
        "原始DataFrame数据",
        "清理后的DataFrame数据",
        "pandas.DataFrame",
        "pandas.DataFrame + 数据质量报告"
    ).finish_design()
    
    # 统计分析步骤
    builder.design_step(
        "statistical_analysis",
        "统计分析",
        "根据用户需求进行描述性统计、相关性分析等"
    ).as_code_agent(
        libraries=["pandas", "numpy", "scipy", "statsmodels"],
        generation_strategy="analysis_type_based",
        reason="不同的分析需求需要生成不同的统计分析代码"
    ).set_input_output(
        "预处理后的数据和分析需求",
        "统计分析结果",
        "DataFrame + 分析参数",
        "统计结果字典"
    ).finish_design()
    
    # 可视化生成步骤
    builder.design_step(
        "generate_visualizations",
        "生成可视化",
        "根据分析结果生成合适的图表"
    ).as_code_agent(
        libraries=["matplotlib", "seaborn", "plotly"],
        generation_strategy="chart_type_recommendation",
        reason="需要根据数据类型智能推荐和生成合适的图表类型"
    ).set_input_output(
        "统计分析结果",
        "图表文件和图表描述",
        "统计结果 + 图表偏好",
        "图表文件路径列表 + 图表说明"
    ).finish_design()
    
    # 报告生成步骤
    builder.design_step(
        "create_report",
        "创建分析报告",
        "整合所有分析结果和图表，生成完整的分析报告"
    ).as_text_agent(
        prompt_strategy="template_based_report_generation",
        response_style="professional_report",
        reason="需要生成专业格式的分析报告"
    ).set_input_output(
        "统计结果、图表、用户需求",
        "完整的分析报告",
        "分析结果字典 + 图表列表",
        "Markdown格式的报告文档"
    ).finish_design()
    
    # 5. 设计记忆系统（保持记忆上下文）
    builder.design_memory(
        purpose="记住用户的分析偏好和历史数据处理经验",
        storage_strategy="hybrid_local_vector"
    ).configure_short_term(
        purpose="当前会话的分析上下文和中间结果",
        retention_hours=8
    ).configure_long_term(
        purpose="用户的分析偏好、常用数据格式、历史分析模式",
        indexing_strategy="semantic_similarity"
    ).finish_design()
    
    # 6. 生成最终Agent
    agent = builder.build_agent()
    
    return agent

# ==================== Agentic Code 可以生成的简化版本 ====================

async def create_simple_qa_agent():
    """简化的问答Agent创建示例"""
    
    builder = ContextualAgentBuilder()
    
    # 设置需求
    builder.set_user_requirements("我需要一个智能问答助手") \
           .define_agent_purpose("回答用户的各种问题") \
           .add_capability_requirement("text_generation", "需要生成高质量的回答")
    
    # 设计简单工作流
    workflow_designer = builder.design_workflow(
        name="问答工作流",
        purpose="理解问题并提供准确回答",
        business_logic="理解问题 → 搜索知识 → 生成回答"
    )
    
    workflow_designer.add_step_flow("understand_question", "search_knowledge") \
                    .add_step_flow("search_knowledge", "generate_answer") \
                    .finish_design()
    
    # 设计步骤
    builder.design_step("understand_question", "理解问题", "分析用户问题的意图和关键信息") \
           .as_text_agent("intent_extraction", reason="需要理解用户真实意图") \
           .finish_design()
    
    builder.design_step("search_knowledge", "搜索知识", "搜索相关知识和信息") \
           .as_tool_agent(["search_engine", "knowledge_base"], reason="需要获取外部信息") \
           .finish_design()
    
    builder.design_step("generate_answer", "生成回答", "基于搜索结果生成最终回答") \
           .as_text_agent("answer_synthesis", reason="需要整合信息生成回答") \
           .finish_design()
    
    # 构建Agent
    return builder.build_agent()
```

## 架构优势

### 1. **完整的上下文保持**
- 从用户原始需求到最终实现的完整追踪链路
- 每个设计决策都有明确的业务原因
- 支持上下文的查询和调试

### 2. **分层清晰的接口**
- 需求层：保持用户原始意图
- 设计层：保持业务逻辑和设计决策
- 实现层：保持技术配置和实现细节

### 3. **Agentic Code 友好**
- 提供语义化的编程接口
- 清晰的构建步骤和上下文指导
- 自动生成包含上下文的配置

### 4. **可维护和可扩展**
- 配置包含完整的上下文信息
- 便于后续修改和优化
- 支持增量式的功能扩展

## 实施计划

### Phase 1: 核心数据结构 (1周)
1. 实现 `AgentDefinition` 和相关数据结构
2. 实现 `ContextTracker` 上下文追踪器
3. 定义完整的接口规范

### Phase 2: Builder 框架 (2周)
1. 实现 `ContextualAgentBuilder` 主类
2. 实现各种专用设计器 (WorkflowDesigner, StepDesigner, MemoryDesigner)
3. 实现配置生成逻辑

### Phase 3: 动态加载集成 (1周)
1. 扩展 `DynamicBaseAgent` 支持上下文信息
2. 实现配置到技术实现的转换
3. 集成测试和验证

### Phase 4: 文档和示例 (1周)
1. 编写完整的使用文档
2. 创建多个示例Agent
3. 性能测试和优化

## 结论

这个上下文保持的动态加载架构解决了方案2的核心问题：

- **保持了需求的完整上下文**：从用户原始需求到最终实现的完整追踪
- **提供了语义化的接口**：Agentic Code 可以理解业务意图，而不仅仅是技术配置
- **维护了设计的可追溯性**：每个决策都有明确的原因和依据
- **支持了灵活的动态加载**：保持了方案2的技术优势

通过分层设计和上下文追踪，这个架构为 Agentic Code 提供了一个既保持语义信息又支持技术实现的完整框架。