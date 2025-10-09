# Intent Builder 实现指南

**版本**: v2.0
**日期**: 2025-10-09
**状态**: 基于新架构更新

---

## 系统架构

Intent Builder 采用分层架构，将用户操作转换为可执行的 Workflow：

```
┌──────────────────────────────────────────────────────┐
│             Phase 1: Learning Phase                  │
│          (User Operations → Intent Graph)            │
└──────────────────────────────────────────────────────┘

User Operations JSON + Task Description
                ↓
┌────────────────────────────────┐
│      IntentExtractor           │
│  - URL 切分 (规则)              │
│  - Intent 生成 (LLM)           │
└────────────────────────────────┘
                ↓
         List[Intent]
                ↓
┌────────────────────────────────┐
│    IntentMemoryGraph           │
│  - 存储 Intent 节点             │
│  - 添加时间顺序边               │
│  - 语义检索 (embedding)         │
│  - JSON 持久化                  │
└────────────────────────────────┘


┌──────────────────────────────────────────────────────┐
│          Phase 2: Generation Phase                   │
│        (Intent Graph → Workflow)                     │
└──────────────────────────────────────────────────────┘

User Query + IntentMemoryGraph
                ↓
┌────────────────────────────────┐
│    Semantic Retrieval          │
│  - Embedding 相似度             │
│  - 检索相关 Intents             │
└────────────────────────────────┘
                ↓
        Retrieved Intents
                ↓
┌────────────────────────────────┐
│    MetaFlowGenerator           │
│  (LLM完成所有推理)              │
│  - 循环检测                     │
│  - 隐式节点生成                 │
│  - 数据流推断                   │
│  - 节点排序                     │
└────────────────────────────────┘
                ↓
           MetaFlow
                ↓
┌────────────────────────────────┐
│    WorkflowGenerator           │
│  (LLM生成YAML)                 │
│  - 转换为 BaseAgent Workflow   │
└────────────────────────────────┘
                ↓
         Workflow YAML
                ↓
┌────────────────────────────────┐
│         BaseAgent              │
└────────────────────────────────┘
```

## 核心组件

### Phase 1: Learning Phase 组件

#### 1. Intent 数据模型 (`core/intent.py`)

**职责**: 定义 Intent 的数据结构

**主要类**:
```python
@dataclass
class Intent:
    id: str                      # MD5 hash of description
    description: str             # 语义描述（LLM 生成）
    operations: List[Operation]  # 完整操作序列
    created_at: datetime
    source_session_id: str
```

**关键设计**:
- 极简结构，不包含 tags/category/inputs/outputs
- ID 基于 description 的 MD5 hash，支持未来去重
- operations 保留原始 User Operations JSON 格式（包括 copy_action）

详见：`intent_specification.md`

#### 2. IntentMemoryGraph (`core/intent_memory_graph.py`)

**职责**: 存储和检索 Intent

**核心接口**:
```python
class IntentMemoryGraph:
    def add_intent(self, intent: Intent) -> None
    def add_edge(self, from_id: str, to_id: str) -> None
    async def retrieve_similar(self, query: str, limit: int) -> List[Intent]
    def save(self, filepath: str) -> None
    @staticmethod
    def load(filepath: str) -> "IntentMemoryGraph"
```

**关键特性**:
- 语义相似度检索（OpenAI embedding）
- 时间顺序边
- JSON 持久化

详见：`intent_memory_graph_specification.md`

#### 3. IntentExtractor (`extractors/intent_extractor.py`)

**职责**: 从 User Operations JSON 提取 Intent

**核心方法**:
```python
async def extract_intents(
    self,
    operations: List[Dict],
    task_description: str
) -> List[Intent]:
    # Step 1: URL-based segmentation (规则)
    segments = self._split_by_url(operations)

    # Step 2: LLM extraction (1-N intents per segment)
    all_intents = []
    for segment in segments:
        intents = await self._extract_from_segment(segment, task_description)
        all_intents.extend(intents)

    return all_intents
```

**策略**:
- 规则切分（URL 变化）
- LLM 生成 description 和确定 operation_indices
- 一个 segment 可能生成 1-N 个 Intent

详见：`intent_extractor_design.md`

### Phase 2: Generation Phase 组件

#### 4. MetaFlowGenerator (`generators/metaflow_generator.py`)

**职责**: 从 Intents 生成 MetaFlow

**核心方法**:
```python
async def generate(
    self,
    intents: List[Intent],
    task_description: str,
    user_query: str
) -> MetaFlow:
    # LLM 完成所有推理
    prompt = self._build_prompt(intents, task_description, user_query)
    response = await self.llm.generate_response("", prompt)
    metaflow_yaml = self._extract_yaml(response)
    return MetaFlow.from_yaml(metaflow_yaml)
```

**LLM 职责**:
- 循环检测（关键词："所有"、"每个"）
- 隐式节点生成（如 ExtractList）
- 数据流推断（source_node, loop_variable）
- 节点排序

详见：`metaflow_generator_design.md`

#### 5. MetaFlow 数据模型 (`core/metaflow.py`)

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
