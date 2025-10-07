# WorkflowGenerator 设计文档

**版本**: v1.0
**日期**: 2025-10-07
**状态**: 设计阶段

---

## 1. 问题定义

### 1.1 目标

将 MetaFlow（意图的组合和编排）转换为 BaseAgent 可执行的 YAML Workflow。

```
输入: MetaFlow (YAML)
输出: Workflow (YAML)
```

### 1.2 核心挑战

MetaFlow 是**给人看的**，包含：
- 意图的自然语言描述
- 用户操作的原始记录（operations）
- 循环的自然语言描述

Workflow 是**给机器执行的**，需要：
- 明确的 Agent 类型（tool_agent, scraper_agent, code_agent 等）
- 精确的数据流（变量定义、变量传递）
- 结构化的控制流（foreach 循环结构）
- 具体的任务描述（task）

**转换难点**：
1. 从 operations 推断应该使用哪种 Agent 类型
2. 推断意图之间的数据流（变量命名、依赖关系）
3. 从自然语言 description 生成结构化的循环
4. 决定一个意图生成几个 step

---

## 2. 输入输出定义

### 2.1 输入：MetaFlow

**格式**: YAML

**结构**:
```yaml
version: "1.0"
task_description: "从 Allegro 采集所有咖啡产品的价格"

nodes:
  # 普通节点
  - id: node_1
    intent_id: intent_001
    intent_name: "NavigateToAllegro"
    intent_description: "导航到 Allegro 首页"
    operations:
      - type: navigate
        timestamp: 1757730777260
        url: "https://allegro.pl/"
        page_title: "Navigated Page"
        element: {}

  # 循环节点
  - id: node_4
    type: loop
    description: "遍历产品列表，逐个访问产品页面并提取价格信息"
    children:
      - id: node_4_1
        intent_id: intent_004
        intent_name: "ExtractProductPrice"
        intent_description: "访问产品详情页并提取价格、标题等信息"
        operations:
          - type: navigate
            url: "{{current_product_url}}"
            element: {...}
          - type: select
            element: {textContent: "价格信息", ...}
          - type: copy_action
            data: {copiedText: "69,50 zł"}
```

**关键信息**：
- **task_description**: 用户的自然语言任务描述
- **intent_description**: 每个意图的详细描述（人类可读）
- **operations**: 用户操作的原始记录，包含详细的 DOM 信息
  - type: navigate, click, select, copy_action, input 等
  - url: 页面 URL
  - element: 包含 xpath, tagName, textContent, href 等
  - data: 操作相关数据（如 copiedText）
- **loop description**: 循环的自然语言描述

### 2.2 输出：Workflow YAML

**格式**: YAML（符合 BaseAgent workflow 规范）

**结构**:
```yaml
workflow:
  name: "Allegro Coffee Price Collection"
  description: "从 Allegro 采集所有咖啡产品的价格"

  steps:
    - id: navigate_to_allegro
      agent_type: tool_agent
      task: "导航到 Allegro 首页"
      config:
        tools: ["browser_use"]

    - id: enter_coffee_category
      agent_type: tool_agent
      task: "通过菜单进入咖啡产品分类页面"
      config:
        tools: ["browser_use"]

    - id: extract_product_list
      agent_type: scraper_agent
      task: "从分类页面提取所有咖啡产品的 URL 列表"
      output_key: product_list

    - id: extract_all_prices
      agent_type: foreach
      source: "{{product_list}}"
      item_var: current_product
      max_iterations: 50
      steps:
        - id: extract_single_product
          agent_type: scraper_agent
          task: "访问产品页面并提取价格、标题和销量信息"
          input:
            product_url: "{{current_product}}"
          output_key: product_info
```

**关键要素**：
- **agent_type**: tool_agent, scraper_agent, code_agent, foreach 等
- **task**: 具体的任务描述（给 Agent 看的）
- **output_key**: 输出变量名
- **变量引用**: `{{product_list}}`, `{{current_product}}`
- **foreach 结构**: source, item_var, max_iterations, steps

---

## 3. LLM 需要推断的内容

### 3.1 Operations → Agent Type 映射

从 operations 的类型和组合推断应该使用什么 Agent：

| Operations 特征 | 推荐 Agent 类型 |
|----------------|----------------|
| navigate, click, input, wait | tool_agent |
| select + copy_action | scraper_agent |
| 复杂的数据提取 | scraper_agent |
| 数据转换、计算 | code_agent |
| 数据存储 | storage_agent |

**LLM 需要理解**：
- operations 的语义（用户在做什么）
- 配合 intent_description 综合判断

### 3.2 数据流推断

**输出识别**：
- 从 operations 中识别数据产出（如 select + copy_action）
- 生成语义化的变量名（如 product_list, product_info, page_state）

**依赖识别**：
- 识别后续意图对前面数据的依赖
- 推断变量传递关系

**示例**：
```
Node 2: ExtractProductList
  operations: [select + copy_action]
  → 推断输出: product_list (类型: list)

Node 3 (loop): "遍历产品列表"
  → 推断依赖: 需要 product_list
  → 生成: source: "{{product_list}}"
```

### 3.3 循环结构推断

从循环节点的 description 推断：

```yaml
# Input
type: loop
description: "遍历产品列表，逐个访问产品页面并提取价格信息"

# Output
agent_type: foreach
source: "{{product_list}}"      # 从 "产品列表" 推断
item_var: current_product       # 从 "逐个" 推断变量名
max_iterations: 50              # 默认值或从上下文推断
```

**推断策略**：
- 关键词识别："遍历"、"逐个"、"所有"
- 向前查找数据来源（哪个 step 产生了列表）
- 生成语义化的循环变量名

### 3.4 Step 拆分决策

**原则**: 以 Step Agent 为最小单元

**LLM 决策**：
- 一个意图是否拆分成多个 step
- 相关操作是否合并到一个 step

**示例 1**（合并）:
```yaml
# Intent operations
operations:
  - type: click
  - type: wait

# 生成 1 个 step
- agent_type: tool_agent
  task: "点击咖啡分类并等待页面加载"
```

**示例 2**（拆分）:
```yaml
# Intent operations
operations:
  - type: navigate
  - type: select
  - type: copy_action

# 生成 2 个 step
- agent_type: tool_agent
  task: "导航到产品页面"
- agent_type: scraper_agent
  task: "提取产品价格和标题"
```

### 3.5 任务描述（task）生成

从 intent_description 和 operations 生成具体的 task：

```yaml
# Input
intent_description: "通过菜单进入咖啡产品分类页面"
operations:
  - type: click
    element: {textContent: "Kawy"}

# Output
task: "通过菜单进入咖啡产品分类页面"  # 可以直接使用或略微改写
```

---

## 4. 设计方案

### 4.1 整体架构

```
MetaFlow (YAML)
    ↓
WorkflowGenerator
    ├─ Prompt Builder    # 构建 LLM Prompt
    ├─ LLM Service       # 调用 LLM 生成 YAML
    ├─ YAML Validator    # 验证生成的 YAML
    └─ Retry Handler     # 处理失败重试
    ↓
Workflow (YAML)
```

### 4.2 核心组件

#### 4.2.1 PromptBuilder

**职责**: 构建发送给 LLM 的 prompt

**输入**:
- MetaFlow YAML 字符串
- Workflow 规范（精简版）
- Few-shot 示例（1 个完整示例）

**输出**: 完整的 prompt 字符串

**Prompt 结构**:
```
[系统角色]
你是一个 Workflow 生成专家...

[Workflow 规范]
（精简的 BaseAgent workflow 规范）

[转换要求]
1. Operations → Agent Type 映射规则
2. 数据流推断要求
3. Step 拆分原则
4. 变量命名规范
...

[示例]
（完整的 MetaFlow → Workflow 转换示例）

[任务]
请将以下 MetaFlow 转换为 Workflow YAML：
<metaflow>
...
</metaflow>

[输出要求]
只输出 YAML，不要其他解释。
```

#### 4.2.2 LLMService

**职责**: 调用 LLM API 生成 YAML

**配置**:
- Model: Claude Sonnet 3.5 或 GPT-4
- Temperature: 0.1（低温度，保证确定性）
- Max tokens: 4000

**输入**: Prompt 字符串
**输出**: 生成的 YAML 字符串

#### 4.2.3 YAMLValidator

**职责**: 验证生成的 YAML 是否合法

**验证项**:
1. YAML 格式正确（可解析）
2. 必需字段存在（workflow.name, steps 等）
3. Agent 类型合法（tool_agent, scraper_agent 等）
4. 变量引用格式正确（`{{variable_name}}`）
5. foreach 结构完整（source, item_var, steps）

**实现**:
```python
import yaml
from pydantic import BaseModel, ValidationError

class WorkflowValidator:
    def validate(self, yaml_str: str) -> tuple[bool, str]:
        """
        Returns:
            (success: bool, error_message: str)
        """
        try:
            # 1. Parse YAML
            data = yaml.safe_load(yaml_str)

            # 2. Validate structure with Pydantic
            WorkflowSchema(**data)

            # 3. Custom validation
            self._validate_variables(data)
            self._validate_agent_types(data)

            return True, ""
        except Exception as e:
            return False, str(e)
```

#### 4.2.4 RetryHandler

**职责**: 处理生成失败的重试逻辑

**策略**:
- 最多重试 3 次
- 每次重试在 prompt 中增加错误信息
- 如果 3 次都失败，抛出异常

**流程**:
```python
for attempt in range(3):
    yaml_str = llm_service.generate(prompt)
    success, error = validator.validate(yaml_str)

    if success:
        return yaml_str
    else:
        # 在 prompt 中添加错误信息
        prompt += f"\n\n上次生成失败，错误: {error}\n请修正后重新生成。"

raise GenerationError("Failed after 3 attempts")
```

### 4.3 执行流程

```python
class WorkflowGenerator:
    def __init__(self, llm_service, prompt_builder, validator):
        self.llm_service = llm_service
        self.prompt_builder = prompt_builder
        self.validator = validator

    async def generate(self, metaflow: MetaFlow) -> str:
        """
        将 MetaFlow 转换为 Workflow YAML

        Args:
            metaflow: MetaFlow 对象

        Returns:
            workflow_yaml: 可执行的 YAML 字符串

        Raises:
            GenerationError: 生成失败
        """
        # 1. 构建 prompt
        metaflow_yaml = metaflow.to_yaml()
        prompt = self.prompt_builder.build(metaflow_yaml)

        # 2. LLM 生成 + 重试
        for attempt in range(3):
            try:
                # 调用 LLM
                workflow_yaml = await self.llm_service.generate(prompt)

                # 验证
                success, error = self.validator.validate(workflow_yaml)

                if success:
                    return workflow_yaml
                else:
                    # 添加错误信息到 prompt
                    prompt = self._add_error_feedback(prompt, error)

            except Exception as e:
                if attempt == 2:  # 最后一次
                    raise GenerationError(f"Failed after 3 attempts: {e}")
                continue

        raise GenerationError("Failed after 3 attempts")

    def _add_error_feedback(self, prompt: str, error: str) -> str:
        return f"{prompt}\n\n上次生成的 YAML 验证失败。\n错误: {error}\n\n请修正后重新生成。"
```

---

## 5. Prompt 设计（详细）

### 5.1 Prompt 模板

```
# 系统角色
你是一个 Workflow 生成专家，负责将 MetaFlow 转换为 BaseAgent 可执行的 YAML Workflow。

# Workflow 规范（精简版）

BaseAgent Workflow YAML 格式：

```yaml
workflow:
  name: "workflow_name"
  description: "workflow_description"

  steps:
    - id: step_id
      agent_type: tool_agent | scraper_agent | code_agent | foreach
      task: "具体任务描述"
      config: {...}          # 可选
      output_key: var_name   # 可选，输出变量名
      input: {...}           # 可选，输入参数

    - id: loop_step_id
      agent_type: foreach
      source: "{{list_variable}}"
      item_var: item_name
      max_iterations: 50
      steps: [...]           # 循环体
```

Agent 类型说明：
- tool_agent: 浏览器操作（navigate, click, input, wait, scroll）
- scraper_agent: 数据提取（从页面提取结构化数据）
- code_agent: 代码执行（数据转换、计算）
- foreach: 循环控制（遍历列表）

变量引用格式：`{{variable_name}}`

---

# 转换要求

## 1. Operations → Agent Type 映射

根据 operations 的类型和组合选择合适的 agent_type：

- **navigate, click, input, wait, scroll** → tool_agent
- **select + copy_action（数据提取）** → scraper_agent
- **复杂数据提取** → scraper_agent
- **数据转换、计算** → code_agent

注意：
- 一个意图可以生成一个或多个 step
- 相关的 operations 可以合并到一个 step
- 每个 step 必须是一个完整的 agent

## 2. 数据流推断

- 识别产生输出的 step（通常包含 select + copy_action）
- 为输出生成语义化的变量名（如 product_list, product_info）
- 识别依赖关系，使用 `{{variable_name}}` 引用前面的输出
- 循环中的变量使用 item_var 定义的名称

## 3. 循环处理

从循环节点的 description 推断：
- **source**: 向前查找产生列表的 step 的 output_key
- **item_var**: 根据语义生成变量名（如 current_product, item）
- **max_iterations**: 默认 50，或根据上下文调整

关键词识别："遍历"、"逐个"、"所有"、"每个"

## 4. Task 生成

- 优先使用 intent_description 作为 task
- 根据 operations 的具体内容适当调整
- 保持清晰、具体、可执行

---

# 示例

## 输入 MetaFlow

```yaml
version: "1.0"
task_description: "从 Allegro 采集所有咖啡产品的价格"

nodes:
  - id: node_1
    intent_id: intent_001
    intent_name: "NavigateToAllegro"
    intent_description: "导航到 Allegro 首页"
    operations:
      - type: navigate
        url: "https://allegro.pl/"
        element: {}

  - id: node_2
    intent_id: intent_002
    intent_name: "EnterCoffeeCategory"
    intent_description: "通过菜单进入咖啡产品分类页面"
    operations:
      - type: click
        element:
          textContent: "Kawy"
          href: "https://allegro.pl/kategoria/produkty-spozywcze-kawa-74030"
      - type: wait
        duration: 2000

  - id: node_3
    intent_id: intent_003
    intent_name: "ExtractProductList"
    intent_description: "从分类页面提取所有咖啡产品的 URL 列表"
    operations:
      - type: select
        element:
          tagName: "A"
          className: "product-link"
      - type: copy_action
        data:
          copiedText: "https://allegro.pl/oferta/..."

  - id: node_4
    type: loop
    description: "遍历产品列表，逐个访问产品页面并提取价格信息"
    children:
      - id: node_4_1
        intent_id: intent_004
        intent_name: "ExtractProductPrice"
        intent_description: "访问产品详情页并提取价格、标题等信息"
        operations:
          - type: navigate
            url: "{{current_product_url}}"
          - type: select
            element:
              tagName: "H1"
              textContent: "产品标题"
          - type: copy_action
          - type: select
            element:
              textContent: "69,50 zł"
          - type: copy_action
```

## 输出 Workflow

```yaml
workflow:
  name: "Allegro Coffee Price Collection"
  description: "从 Allegro 采集所有咖啡产品的价格"

  steps:
    - id: navigate_to_allegro
      agent_type: tool_agent
      task: "导航到 Allegro 首页 https://allegro.pl/"
      config:
        tools: ["browser_use"]

    - id: enter_coffee_category
      agent_type: tool_agent
      task: "点击咖啡分类菜单进入咖啡产品页面"
      config:
        tools: ["browser_use"]

    - id: extract_product_list
      agent_type: scraper_agent
      task: "从咖啡分类页面提取所有产品的 URL，保存为列表"
      output_key: product_list

    - id: extract_all_prices
      agent_type: foreach
      source: "{{product_list}}"
      item_var: current_product
      max_iterations: 50
      steps:
        - id: extract_single_product
          agent_type: scraper_agent
          task: "访问产品页面并提取产品标题和价格信息"
          input:
            product_url: "{{current_product}}"
          output_key: product_info
```

---

# 任务

请将以下 MetaFlow 转换为 Workflow YAML：

```yaml
{metaflow_yaml}
```

# 输出要求

只输出 YAML 格式的 workflow，不要有其他解释或说明。
确保 YAML 格式正确，可以被解析。
```

### 5.2 Prompt 关键点

1. **规范精简**: 只包含最核心的格式说明（~100 行）
2. **明确约束**: 清楚说明 Operations → Agent Type 的映射规则
3. **完整示例**: 提供一个包含循环的完整示例
4. **输出限制**: 强调只输出 YAML，不要解释

---

## 6. 实施计划

### Phase 1: 基础实现

1. 实现 PromptBuilder
2. 实现 LLMService（接入 Claude/GPT-4）
3. 实现 YAMLValidator（基础验证）
4. 实现 WorkflowGenerator（主流程）
5. 编写单元测试

### Phase 2: 完善和优化

1. 增强 YAMLValidator（更严格的验证）
2. 优化 Prompt（根据实际效果调整）
3. 添加更多 few-shot 示例（如果需要）
4. 性能优化（缓存、并行）

### Phase 3: 集成测试

1. 使用咖啡采集示例测试
2. 测试不同类型的任务
3. 测试边界情况（复杂循环、多种 agent 类型）
4. 修正和迭代

---

## 7. 风险和缓解

### 风险 1: LLM 生成的数据流不一致

**描述**: 变量名不匹配，导致引用失败

**缓解**:
- 在 YAMLValidator 中增加变量引用检查
- 如果检查失败，在重试时提供错误反馈

### 风险 2: YAML 格式错误

**描述**: LLM 生成的 YAML 无法解析

**缓解**:
- YAML parser 验证
- 重试机制（最多 3 次）

### 风险 3: Agent Type 选择不合适

**描述**: LLM 选择了错误的 agent_type

**缓解**:
- 在 Prompt 中提供清晰的映射规则
- 提供典型示例
- 后期可以增加规则验证

### 风险 4: 循环推断失败

**描述**: LLM 无法正确推断循环的 source

**缓解**:
- 在示例中展示清晰的循环推断逻辑
- 在 description 中使用明确的关键词
- 必要时可以在 MetaFlow 中增加轻量级提示（未来迭代）

---

## 8. 评估指标

### 成功指标

1. **生成成功率**: > 90%（前 3 次尝试内成功）
2. **YAML 格式正确率**: 100%（可解析）
3. **变量引用正确率**: > 95%（变量名匹配）
4. **Agent Type 准确率**: > 90%（符合预期）
5. **执行成功率**: > 80%（生成的 workflow 可以成功执行）

### 测试场景

1. 线性 workflow（无循环）
2. 单层循环
3. 多种 agent 类型混合
4. 复杂数据流（多个输出、多个依赖）

---

## 9. 参考资料

- BaseAgent Workflow 规范: `docs/baseagent/workflow_specification.md`
- 用户操作示例: `tests/sample_data/browser-user-operation-tracker-example.json`
- MetaFlow 设计: `metaflow_design.md`
- 讨论记录: `discussions/03_workflow_generation_discussion.md`
