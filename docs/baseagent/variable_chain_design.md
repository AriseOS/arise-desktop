# AgentBuilder 变量链条修复设计方案

## 问题描述

当前AgentBuilder生成的Agent配置中，inputs和outputs是描述文字而不是变量引用，导致：
1. 步骤间无法传递数据
2. 变量链条断裂
3. Agent无法形成完整的工作流

## 设计目标

修复变量链条，实现：
- 正确的变量引用机制（`{{variable_name}}`格式）
- 完整的数据传递链条
- 智能的变量选择逻辑

## 核心设计方案

### 1. 混合变量传递机制

**设计理念**: 结合结构化数据和语义理解的优势

**第一个Agent（意图分析）**:
```json
{
  "inputs": {"user_message": "{{user_input}}"},
  "outputs": {
    "structured_data": "parsed_intent_data",
    "semantic_context": "full_user_context", 
    "confidence": "analysis_confidence"
  }
}
```

**后续Agent**:
```json
{
  "inputs": {
    "task_info": "{{parsed_intent_data}}",
    "context": "{{full_user_context}}"
  },
  "outputs": {
    "result": "step2_output",
    "metadata": "step2_metadata"
  }
}
```

### 2. 变量命名规范

**输入变量**:
- `{{user_input}}`: 工作流初始用户输入
- `{{step{N}_{field}}}`: 引用第N步的特定字段输出

**输出变量**:
- `step{N}_{field_name}`: 第N步的特定输出
- 例：`step1_analysis`, `step2_result`, `step3_final`

### 3. 上下文感知配置生成

**核心流程**:
```python
async def generate_step_agents(self, steps: List[StepDesign]) -> List[Dict[str, Any]]:
    generated_agents = []
    available_variables = ["user_input"]  # 跟踪可用变量
    
    for i, step in enumerate(steps):
        # 构建可用变量上下文信息
        context_info = self._build_variable_context(available_variables)
        
        # 生成Agent配置（传入上下文信息）
        agent_spec = await self._generate_agent_with_context(
            step, i, len(steps), context_info
        )
        
        # 更新可用变量列表
        outputs = agent_spec.get('baseagent_config', {}).get('outputs', {})
        available_variables.extend(outputs.values())
        
        generated_agents.append(agent_spec)
    
    return generated_agents
```

## 具体实现方案

### 1. 修改AgentDesigner类

**新增方法**:
```python
def _build_variable_context(self, available_variables: List[str]) -> str:
    """构建可用变量的上下文信息"""
    
    if not available_variables:
        return "## 输入数据\n- {{user_input}}: 用户输入的原始消息"
    
    context = "## 可用的上下文变量（根据业务需要选择使用）:\n"
    context += "- {{user_input}}: 工作流初始输入\n"
    
    for var in available_variables[1:]:  # 跳过user_input
        context += f"- {{{{{var}}}}}: 前序步骤的输出数据\n"
    
    context += "\n请根据当前步骤的业务逻辑，智能选择需要的输入变量。"
    return context
```

### 2. 修改配置生成方法签名

**所有四个配置生成方法**都需要添加context参数：
```python
async def _generate_text_agent_config(
    self, 
    step: StepDesign, 
    step_index: int, 
    total_steps: int,
    variable_context: str  # 新增参数
) -> Dict[str, Any]:
```

### 3. 修改提示词模板

**❌ 当前错误模板**:
```json
"inputs": {"input_key": "input_description"},
"outputs": {"output_key": "output_description"}
```

**✅ 修复后模板**:
```json
"inputs": {"field_name": "{{variable_name}}"},
"outputs": {"field_name": "variable_to_store"}
```

### 4. 智能意图分析架构 ⭐ 重要更新

**条件性意图分析**:
```python
# 在parse_requirements阶段智能判断是否需要意图分析
needs_intent_analysis = parsed_data.get('needs_intent_analysis', False)

# 在extract_steps阶段根据判断结果添加意图分析步骤
steps = await self.extract_steps(user_input, agent_purpose, needs_intent_analysis)
```

**判断标准**:
- **需要意图分析**: 用户输入开放、需要处理多种任务类型、需要动态路由
- **无需意图分析**: 任务目标明确、流程固定、单一功能专用工具

**第一个Agent灵活处理**:
```python
if step_index == 0:
    # 第一个Agent根据实际业务逻辑定义，不强制意图分析
    context_info = """
    ## 输入数据
    - {{user_input}}: 用户输入的原始消息
    
    请根据当前步骤的实际业务逻辑定义合适的输出变量。
    """
```

## 提示词改进策略

### 1. 自然引导，避免强制

**❌ 错误方式**:
```
你必须使用以下所有变量...
你的inputs必须包含...
```

**✅ 正确方式**:
```
根据步骤的业务逻辑，从可用变量中选择需要的输入。
无需强制使用所有变量，只选择对当前任务有意义的变量。
```

### 2. 提供清晰示例

在提示词中包含正确的变量引用示例：
```
## 变量引用格式示例
输入引用: "field_name": "{{source_variable}}"
输出定义: "field_name": "target_variable_name"

## 实际示例
"inputs": {
  "user_question": "{{user_input}}",
  "analysis_result": "{{step1_analysis}}"
},
"outputs": {
  "tool_result": "step2_output",
  "confidence": "step2_confidence"
}
```

## 实施步骤

### Phase 1: 核心修复
1. 修改`generate_step_agents`方法，添加变量跟踪
2. 修改所有四个`_generate_*_agent_config`方法签名
3. 修改提示词模板，使用正确的变量引用格式

### Phase 2: 测试验证
1. 生成测试Agent，验证变量链条正确性
2. 确保第一个Agent输出混合格式数据
3. 验证后续Agent能正确选择和引用变量

## 预期效果

修复后的Agent将具备：
- **完整数据流**: 从user_input到final_result的完整传递链
- **智能变量选择**: Agent根据业务需要选择相关变量
- **灵活数据格式**: 支持结构化和语义化两种数据传递方式
- **可调试性**: 清晰的变量来源和去向

## 不包含的功能

- ❌ 复杂的依赖分析
- ❌ 可视化变量关系图
- ❌ 后向兼容处理
- ❌ 变量类型检查
- ❌ 循环依赖检测

此设计专注于解决当前核心问题：将描述文字修复为正确的变量引用，建立完整的数据传递链条。