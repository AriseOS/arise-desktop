# Intent Builder 实现指南

## 系统架构

Intent Builder 采用分层架构，将 MetaFlow 转换为 Workflow YAML：

```
┌─────────────────────────────────────────────────────────────┐
│                      MetaFlow Input                         │
│  (用户意图的中间表示，包含意图、操作、数据流)                 │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   WorkflowGenerator                         │
│  (主生成器，orchestrate 整个转换流程)                         │
└──────┬──────────────────┬──────────────────┬────────────────┘
       │                  │                  │
       ▼                  ▼                  ▼
┏━━━━━━━━━━━━━┓  ┏━━━━━━━━━━━━━┓  ┏━━━━━━━━━━━━━━━━┓
┃ PromptBuilder┃  ┃ LLMService  ┃  ┃ YAMLValidator  ┃
┃ (构建提示词) ┃  ┃ (调用LLM)   ┃  ┃ (验证结果)     ┃
┗━━━━━━━━━━━━━┛  ┗━━━━━━━━━━━━━┛  ┗━━━━━━━━━━━━━━━━┛
       │                  │                  │
       └──────────────────┴──────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   Workflow YAML Output                      │
│  (可执行的 BaseAgent Workflow 定义)                          │
└─────────────────────────────────────────────────────────────┘
```

## 核心组件

### 1. MetaFlow 数据模型 (`core/metaflow.py`)

**职责**: 定义 MetaFlow 的数据结构

**主要类**:
- `OperationType`: 操作类型枚举 (navigate, click, extract, store, wait, scroll)
- `ElementInfo`: DOM 元素信息
- `Operation`: 单个用户操作
- `MetaFlowNode`: 常规意图节点
- `LoopNode`: 循环节点
- `MetaFlow`: 顶层结构

**关键设计**:
- 使用 Pydantic BaseModel 进行数据验证
- 支持 YAML 序列化/反序列化
- 明确的输入输出定义（inputs/outputs）
- 循环节点包含 source（数据源）和 item_var（循环变量）

**示例**:
```python
metaflow = MetaFlow.from_yaml_file("metaflow.yaml")
print(metaflow.task_description)
for node in metaflow.nodes:
    print(node.intent_name, node.operations)
```

### 2. PromptBuilder (`generators/prompt_builder.py`)

**职责**: 构建完整的 LLM 提示词

**组成部分**:
1. **System Role**: 定义 LLM 的角色和职责
2. **Workflow Specification**: 简化的 BaseAgent Workflow 规范
3. **Conversion Requirements**: 详细的转换规则和推断要求
4. **Example**: 一个完整的转换示例（few-shot learning）
5. **Task**: 具体的 MetaFlow 输入

**核心方法**:
```python
builder = PromptBuilder()
prompt = builder.build(metaflow_yaml)
```

**设计亮点**:
- **数据流推断规则**: 教 LLM 如何推断变量初始化、输出变量、数据收集模式
- **Agent 类型映射**: navigate/click → tool_agent, extract → scraper_agent, store → storage_agent
- **Step 拆分策略**: 一个意图可能生成多个 workflow step
- **extraction_method 选择**: 何时用 script vs llm
- **完整示例**: coffee collection 端到端示例

### 3. LLMService (`generators/llm_service.py`)

**职责**: 调用 LLM API 生成 Workflow YAML

**支持的 Provider**:
- Anthropic Claude (默认，推荐)
- OpenAI GPT-4

**关键特性**:
- 异步 API 调用
- 自动提取 YAML（从 markdown code blocks）
- 可配置 temperature 和 max_tokens
- 环境变量配置

**示例**:
```python
# 使用 Claude
llm = LLMService(provider="anthropic")
result = await llm.generate(prompt)

# 使用 GPT-4
llm = LLMService(provider="openai", model="gpt-4-turbo-preview")
result = await llm.generate(prompt)
```

### 4. WorkflowYAMLValidator (`validators/yaml_validator.py`)

**职责**: 验证生成的 Workflow YAML 是否合法

**验证内容**:
1. YAML 语法正确性
2. 必需字段存在（apiVersion, kind, metadata, steps）
3. kind 必须是 "Workflow"
4. metadata 必须包含 name
5. steps 不能为空
6. 每个 step 必须有 id, name, agent_type
7. agent_type 必须是合法值
8. foreach 必须有 source, item_var, steps
9. （可选）使用 Pydantic 模型进行严格验证

**返回**:
```python
validator = WorkflowYAMLValidator()
is_valid, error_message = validator.validate(workflow_yaml)
```

### 5. WorkflowGenerator (`generators/workflow_generator.py`)

**职责**: 主生成器，orchestrate 整个转换流程

**流程**:
1. 将 MetaFlow 转为 YAML 字符串
2. 使用 PromptBuilder 构建完整提示词
3. 调用 LLMService 生成 Workflow YAML
4. 使用 WorkflowYAMLValidator 验证
5. 如果验证失败，添加错误反馈重试（最多 max_retries 次）

**重试机制**:
- 默认最多重试 3 次
- 每次重试将错误信息加入提示词
- 指导 LLM 修复问题

**示例**:
```python
generator = WorkflowGenerator(max_retries=3)
workflow_yaml = await generator.generate(metaflow)
```

## 关键设计决策

### 1. 为什么使用纯 LLM 生成？

**优点**:
- 灵活性高，可以处理各种复杂场景
- 可以推断隐式信息（变量管理、数据流）
- 容易扩展和改进（修改 prompt 即可）

**缺点**:
- 依赖 LLM 质量
- 可能需要多次重试
- 成本相对规则引擎高

**决策**: MVP 阶段采用纯 LLM 方式，后续可优化为混合方式（规则 + LLM）

### 2. 为什么需要 MetaFlow？

MetaFlow 是 Intent Memory Graph 和 Workflow 之间的桥梁：

- **Intent Memory Graph**: 记录用户所有行为和意图，是持久化的知识库
- **MetaFlow**: 针对特定任务，从 Intent Graph 中提取相关节点，形成执行计划
- **Workflow**: 最终的可执行定义，包含所有实现细节

**关系**:
```
Intent Graph (知识库)
  → MetaFlow (执行计划)
    → Workflow (可执行代码)
```

### 3. 数据流的处理

**问题**: MetaFlow 不包含完整的数据流信息（如变量初始化、中间变量）

**解决方案**: LLM 推断
- MetaFlow 提供语义信息（意图、操作、显式 I/O）
- LLM 负责推断实现细节（变量管理、step 拆分、agent 选择）

**示例**:
```yaml
# MetaFlow 中只有 extract 操作
operations:
  - type: extract
    target: "product_urls"
    value: []

# LLM 推断出需要三个 steps:
# 1. scraper_agent: 提取数据
# 2. variable agent: 保存到变量
# 3. (可选) storage_agent: 持久化
```

### 4. Operations 格式

Operations 来自用户的实际操作记录，包含完整的 DOM 信息：

```yaml
- type: extract
  target: "price"
  element:
    xpath: "//*[@id='price']"
    textContent: "cena 69,50 złAllegro Smart!..."
  value: "69,50 zł"  # 用户实际选择的部分
```

**关键**:
- `element.textContent`: 完整的元素文本
- `value`: 用户实际想要的部分（可能是子串）
- 这告诉 LLM 用户真正关心什么数据

## 开发流程

### 添加新的 Agent 类型

1. 在 `PromptBuilder` 的 `_get_workflow_spec()` 中添加 agent 说明
2. 在 `_get_conversion_requirements()` 中添加转换规则
3. 在 `WorkflowYAMLValidator._validate_step()` 中添加验证规则
4. 更新示例

### 优化 Prompt

修改 `PromptBuilder` 的方法：
- `_get_system_role()`: 修改角色定义
- `_get_workflow_spec()`: 修改规范说明
- `_get_conversion_requirements()`: 修改转换规则
- `_get_example()`: 修改示例

### 添加新的 LLM Provider

1. 在 `LLMService.__init__()` 中添加 provider 分支
2. 实现 `_generate_<provider>()` 方法
3. 更新文档

## 测试策略

### 单元测试

测试各个组件独立功能：

```python
# 测试 PromptBuilder
builder = PromptBuilder()
prompt = builder.build(test_metaflow_yaml)
assert "System Role" in prompt

# 测试 Validator
validator = WorkflowYAMLValidator()
is_valid, error = validator.validate(test_workflow_yaml)
assert is_valid
```

### 集成测试

测试端到端流程：

```python
metaflow = MetaFlow.from_yaml_file("test.yaml")
generator = WorkflowGenerator()
workflow_yaml = await generator.generate(metaflow)
# 验证生成的 workflow 是否符合预期
```

### 回归测试

保存成功的生成结果作为参考：

```
tests/fixtures/
  ├── coffee_collection_metaflow.yaml
  └── coffee_collection_workflow.yaml  # 期望的输出
```

## 未来优化方向

### 短期（1-2 个月）

1. **优化 Prompt**: 根据实际生成结果调整提示词
2. **增加更多示例**: 支持更多场景的 few-shot 示例
3. **改进验证**: 更严格的 YAML 验证规则
4. **错误分析**: 统计常见错误，针对性优化

### 中期（3-6 个月）

1. **混合生成**: 简单场景用规则，复杂场景用 LLM
2. **结构化输出**: 使用 LLM 的 structured output 功能
3. **增量生成**: 支持修改已有 workflow
4. **缓存优化**: 相似 MetaFlow 复用生成结果

### 长期（6+ 个月）

1. **Fine-tuned Model**: 训练专门的模型
2. **多 Agent 协作**: 不同 agent 负责不同部分（规划、生成、验证）
3. **用户反馈闭环**: 根据用户修改学习改进
4. **可视化编辑**: 提供图形化界面编辑 MetaFlow

## 故障排查

### 生成失败

1. 检查 API key 是否设置
2. 检查 MetaFlow 格式是否正确
3. 查看 LLM 返回的原始内容（日志）
4. 检查验证错误信息

### 生成结果不符合预期

1. 检查 MetaFlow 的语义是否清晰
2. 优化 operations 的描述
3. 调整 Prompt
4. 增加相关示例

### 验证失败

1. 查看具体的验证错误
2. 检查是否是新的 agent 类型（需要添加验证规则）
3. 检查 LLM 是否理解了 workflow 规范

## 参考资料

- [MetaFlow 规范](metaflow_specification.md)
- [Workflow 规范](../baseagent/workflow_specification.md)
- [BaseAgent 架构](../baseagent/ARCHITECTURE.md)
- [Prompt 设计讨论](discussions/03_workflow_generation_discussion.md)
