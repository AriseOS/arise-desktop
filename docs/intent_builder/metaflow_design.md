# MetaFlow 设计文档

**版本**: v1.0
**日期**: 2025-10-07
**状态**: 已确定

---

## 1. 定义

**MetaFlow（元工作流）** 是意图的组合和编排，描述完成任务的执行逻辑。

### 核心特点

- **给人看的**：人类可读，用户可以查看和理解
- **可执行的**：包含完整信息，可由 LLM 转换为 YAML Workflow
- **可修改的**：未来支持用户通过自然语言修改

### 职责

MetaFlow 负责表达：
- ✅ 意图的执行顺序
- ✅ 控制流（循环）
- ✅ 每个意图的完整信息（包括操作步骤）
- ❌ 数据流（由 LLM 在生成 YAML 时推断）
- ❌ 并行执行（暂不考虑）

---

## 2. 数据结构

### 2.1 整体结构

```yaml
version: "1.0"                    # MetaFlow 格式版本
task_description: "任务描述"       # 用户的自然语言任务描述

nodes:                            # 节点列表（按执行顺序）
  - id: <node_id>                 # 节点 ID（从意图记忆中来）
    intent_id: <intent_id>        # 关联的意图 ID
    intent_name: "IntentName"     # 意图名称
    intent_description: "..."     # 意图描述
    operations: [...]             # 操作步骤列表

  - id: <node_id>
    type: loop                    # 循环节点
    description: "..."            # 循环说明
    children: [...]               # 循环体（子节点）
```

### 2.2 普通节点

```yaml
- id: node_1
  intent_id: intent_001                      # 意图在记忆系统中的 ID
  intent_name: "NavigateToAllegro"           # 意图名称（简短标识）
  intent_description: "导航到 Allegro 首页"  # 人类可读描述
  operations:                                # 具体操作步骤
    - action: navigate
      params:
        url: "https://allegro.pl/"
```

**字段说明**：
- `id`: 节点 ID（从意图记忆中来）
- `intent_id`: 意图在记忆系统中的唯一标识
- `intent_name`: 意图的简短名称（类似函数名）
- `intent_description`: 意图的详细描述（给人看的）
- `operations`: 具体的操作步骤列表（从意图记忆中复制）

### 2.3 循环节点

```yaml
- id: node_4
  type: loop                                  # 节点类型：循环
  description: "遍历产品列表，逐个提取价格信息"  # 循环的自然语言描述
  children:                                   # 循环体
    - id: node_4_1
      intent_id: intent_004
      intent_name: "ExtractProductPrice"
      intent_description: "提取单个产品的价格信息"
      operations:
        - action: extract
          params:
            fields: ["price", "title"]
```

**设计原则**：
- 循环节点**只有自然语言描述**
- 不指定循环来源（source）、循环变量（item_var）等
- 所有细节由 LLM 在生成 workflow 时决定

### 2.4 Operations 格式

**核心理念**: Operations = 用户实际操作的详细记录，告诉 LLM "如何完成意图"

operations 是从用户操作记录（意图记忆）中获取的，包含完整的上下文信息：

```yaml
operations:
  - type: <operation_type>
    timestamp: <timestamp>
    url: "<page_url>"
    page_title: "<page_title>"
    element:
      xpath: "<xpath>"
      tagName: "<tag>"
      className: "<classes>"
      textContent: "<text>"
      href: "<href>"
      # ... 其他元素属性
    data:
      <operation_specific_data>
```

**为什么需要这些详细信息？**

LLM 需要这些信息来生成正确的 workflow 配置：
- **xpath/selector**: 精确定位元素
- **textContent**: 推断期望的数据格式和 sample_data
- **element 属性**: 理解用户操作的目标和语义
- **url/page_title**: 理解页面上下文

**支持的 operation 类型**：

| Type | 说明 | 包含信息 |
|------|------|---------|
| `navigate` | 导航到 URL | url, page_title |
| `click` | 点击元素 | element (xpath, textContent, href) |
| `input` | 输入文本 | element, value (input_value) |
| `extract` | **提取数据** | target, element (xpath, textContent), value |
| `wait` | 等待 | duration |
| `scroll` | 滚动 | direction, distance |
| `store` | **存储数据** | collection, fields |

**extract operation（数据提取）**：

记忆系统理解用户的选择、复制操作后，精简为 extract：

```yaml
- type: extract
  target: "price"           # 字段名（语义化）
  element:
    xpath: "//*[@id='price-container']"
    tagName: "DIV"
    textContent: "cena 69,50 złAllegro Smart! to darmowe dostawy i zwroty..."  # 元素完整内容
  value: "69,50 zł"         # 用户实际想要的数据（从 copiedText）
```

**关键信息说明**：

1. **target**: 字段名，说明提取的是什么数据（如 "price", "title"）
2. **element.textContent**: 元素的完整文本内容
3. **value** (来自 copiedText): **用户实际选择和复制的数据**

**为什么 value 很重要？**

用户可能只选择了元素中的部分内容：

```
element.textContent: "cena 69,50 zł Allegro Smart! to darmowe dostawy..."
value (copiedText):  "69,50 zł"
```

这告诉 LLM：
- 用户只想要价格数值 "69,50 zł"
- 不要 "cena" 前缀和后面的配送信息
- 生成 scraper 时需要提取特定部分

**store operation（数据存储）**：

表达用户要"保存数据"的意图：

```yaml
- type: store
  params:
    collection: "daily_products"  # 存储目标（可选）
    fields: ["title", "price", "sales_count"]  # 引用前面的 extract target
```

**为什么 extract 和 store 要分开？**

增强表示能力，支持多种场景：
- 只提取不存储（临时查看数据）
- 提取后存储（数据收集）
- 批量提取 + 统一存储（多个 extract + 一个 store）

**完整示例**：

```yaml
# 提取并存储产品信息
operations:
  - type: extract
    target: "title"
    element:
      xpath: "//*[@id='product-title']"
      tagName: "H1"
      textContent: "Kawa ziarnista 1kg BRAZYLIA Santos Świeżo Palona 100% ARABICA Tommy Cafe"
    value: "Kawa ziarnista 1kg BRAZYLIA Santos Świeżo Palona 100% ARABICA Tommy Cafe"

  - type: extract
    target: "price"
    element:
      xpath: "//*[@id='price-section']"
      tagName: "DIV"
      textContent: "cena 69,50 złAllegro Smart! to darmowe dostawy i zwroty: Kurierem..."
    value: "69,50 zł"  # 只要价格，不要其他文字

  - type: extract
    target: "sales_count"
    element:
      xpath: "//*[@id='sales-info']"
      tagName: "DIV"
      textContent: "3 308 osób kupiło ostatnio"
    value: "3 308 osób kupiło ostatnio"

  - type: store
    params:
      collection: "daily_products"
      fields: ["title", "price", "sales_count"]
```

**注意**：
- operations 从用户操作追踪系统理解并精简后得到
- 原始的 select + copy_action → 精简为 extract
- value（copiedText）表示用户实际想要的数据，可能是 textContent 的子集
- LLM 用 value 推断数据格式和生成 sample_data

---

## 3. 完整示例

### 任务：从 Allegro 采集所有咖啡产品的价格

```yaml
version: "1.0"
task_description: "从 Allegro 采集所有咖啡产品的价格"

nodes:
  # 节点 1: 导航到首页
  - id: node_1
    intent_id: intent_001
    intent_name: "NavigateToAllegro"
    intent_description: "导航到 Allegro 首页"
    operations:
      - action: navigate
        params:
          url: "https://allegro.pl/"

  # 节点 2: 进入咖啡分类
  - id: node_2
    intent_id: intent_002
    intent_name: "EnterCoffeeCategory"
    intent_description: "通过菜单进入咖啡产品分类页面"
    operations:
      - action: click
        params:
          selector: "text:Kawy"
      - action: wait
        params:
          duration: 2000

  # 节点 3: 提取产品列表
  - id: node_3
    intent_id: intent_003
    intent_name: "ExtractProductList"
    intent_description: "从分类页面提取所有咖啡产品的 URL 列表"
    operations:
      - action: extract
        params:
          fields: ["product_urls"]

  # 节点 4: 循环提取每个产品的价格
  - id: node_4
    type: loop
    description: "遍历产品列表，逐个访问产品页面并提取价格信息"
    children:
      - id: node_4_1
        intent_id: intent_004
        intent_name: "ExtractProductPrice"
        intent_description: "访问产品详情页并提取价格、标题等信息"
        operations:
          - action: navigate
            params:
              url: "{{current_product_url}}"
          - action: extract
            params:
              fields: ["title", "price", "sales_info"]
```

---

## 4. 与 Intent 的关系

### Intent 的存储格式

Intent 在记忆系统中的存储格式（4 个域）：

```python
class Intent(BaseModel):
    id: str                      # 数据库唯一标识
    name: str                    # 简短名称
    description: str             # 人类可读描述
    operations: List[Operation]  # 操作步骤列表
```

### MetaFlow 节点 = Intent 的完整副本

**MetaFlow 普通节点包含 Intent 的所有信息**：

```
Intent (记忆系统)              MetaFlow Node (YAML)
──────────────────────────────────────────────────────
id: "intent_001"          →     intent_id: intent_001
name: "NavigateToAllegro" →     intent_name: "NavigateToAllegro"
description: "..."        →     intent_description: "..."
operations: [...]         →     operations: [...]
```

**为什么要复制完整信息？**
1. MetaFlow 是独立文档，用户查看时无需查询数据库
2. 给人看的，需要完整的上下文
3. LLM 生成 workflow 时需要完整信息

**节点 ID 来源**：
- 从意图记忆系统中获取
- MetaFlow 生成时从意图继承 ID

---

## 5. 生成策略

### MetaFlow → YAML Workflow

**策略**: 纯 LLM 生成

```python
def generate_workflow(metaflow: MetaFlow) -> str:
    """
    使用 LLM 将 MetaFlow 转换为 YAML Workflow

    LLM 负责：
    1. 理解每个意图的 operations
    2. 决定用什么 Agent 类型（tool_agent, scraper_agent 等）
    3. 推断数据流（变量命名和传递）
    4. 理解循环的 description，生成 foreach 结构
    5. 决定循环来源、循环变量名等
    6. 决定一个意图生成几个 YAML step
    """

    prompt = f"""
将以下 MetaFlow 转换为 BaseAgent 的 YAML Workflow。

MetaFlow:
{metaflow_yaml}

要求：
- 根据 operations 选择合适的 agent 类型
- 推断意图之间的数据流和变量传递
- 循环节点根据 description 生成 foreach 结构，推断循环来源和变量
- 生成完整可执行的 YAML
"""

    yaml_workflow = llm.generate(prompt)
    return yaml_workflow
```

**LLM 的职责和自由度**：
- 推断数据流（哪些变量需要传递）
- 变量命名（page_state, product_list 等）
- 循环细节（source, item_var, max_iterations）
- 一个意图生成几个 step（根据复杂度决定）
- Agent 类型选择

---

## 6. 设计原则

### 6.1 人类可读优先

MetaFlow 是给人看的：
- 使用 YAML 格式（易读易编辑）
- 每个节点都有清晰的 name 和 description
- 循环用自然语言描述，人类容易理解

### 6.2 信息完整性

MetaFlow 包含生成 YAML 所需的所有信息：
- 意图的完整定义（4 个域）
- 具体的操作步骤（operations）
- 控制流信息（循环的 description）

### 6.3 简单性

**只加必要的东西**：
- 顶层只有 3 个字段：version, task_description, nodes
- 循环节点只有 type, description, children
- 不加任何当前用不到的功能

**MVP 支持**：
- 线性序列
- 简单循环（一层，不嵌套）

**暂不支持**：
- 条件分支（if/else）
- 嵌套循环
- 并行执行
- 元信息（created_at, author 等）

### 6.4 灵活性

把复杂度交给 LLM：
- 不强制规定数据流格式
- 不强制规定循环的具体参数
- 不强制规定一个意图对应几个 step
- LLM 根据上下文自行判断

---

## 7. 数据类型定义

### Python 数据模型

```python
from pydantic import BaseModel
from typing import List, Union, Dict, Any
import yaml

class Operation(BaseModel):
    """单个操作"""
    action: str                    # 操作类型
    params: Dict[str, Any]         # 操作参数

class MetaFlowNode(BaseModel):
    """MetaFlow 普通节点"""
    id: str
    intent_id: str
    intent_name: str
    intent_description: str
    operations: List[Operation]

class LoopNode(BaseModel):
    """循环节点"""
    id: str
    type: str = "loop"
    description: str               # 循环的自然语言描述
    children: List[MetaFlowNode]

class MetaFlow(BaseModel):
    """MetaFlow 完整定义"""
    version: str = "1.0"
    task_description: str
    nodes: List[Union[MetaFlowNode, LoopNode]]

    def to_yaml(self) -> str:
        """转换为 YAML 字符串"""
        return yaml.dump(self.dict(), allow_unicode=True)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "MetaFlow":
        """从 YAML 字符串加载"""
        data = yaml.safe_load(yaml_str)
        return cls(**data)
```

---

## 8. 使用流程

### 8.1 生成 MetaFlow

```python
# 1. 用户提供任务描述
user_description = "从 Allegro 采集所有咖啡产品的价格"

# 2. 从记忆系统检索相关意图
retrieved_intents = intent_retriever.retrieve(user_description)

# 3. 生成 MetaFlow
metaflow = metaflow_generator.generate(
    intents=retrieved_intents,
    user_description=user_description
)

# 4. 保存为 YAML 文件
with open("metaflow.yaml", "w") as f:
    f.write(metaflow.to_yaml())
```

### 8.2 用户查看（MVP 不支持修改）

```bash
# 用户查看 MetaFlow
cat metaflow.yaml

# 用户可以理解任务逻辑
# MVP 阶段：用户只能查看，不能修改
# 未来版本：用户可以提出修改意见，LLM 修改 MetaFlow
```

### 8.3 生成并执行 Workflow

```python
# 使用 LLM 生成 YAML Workflow
workflow_yaml = workflow_generator.generate(metaflow)

# 执行
agent = BaseAgent(...)
result = await agent.run_workflow(workflow_yaml)
```

---

## 9. 未来扩展方向

### 9.1 交互式修改（未来版本）

```
用户: "第 3 步不对，应该先搜索而不是直接点击分类"
LLM: 修改 MetaFlow 节点 3
输出: 修改后的 metaflow.yaml
```

### 9.2 条件分支（未来版本）

```yaml
- id: node_5
  type: condition
  description: "如果价格超过 100，则加入高价列表"
  then: [...]
  else: [...]
```

### 9.3 嵌套循环（未来版本）

```yaml
- id: node_6
  type: loop
  description: "遍历所有分类"
  children:
    - id: node_6_1
      type: loop
      description: "遍历当前分类的所有产品"
      children: [...]
```

---

## 10. 与其他组件的关系

### 生成流程

```
Intent Memory Graph
    ↓ retrieve
Retrieved Intents
    ↓ MetaFlowGenerator
MetaFlow (YAML)
    ↓ WorkflowGenerator (LLM)
YAML Workflow
    ↓ BaseAgent
Execution Result
```

### 关键接口

```python
# MetaFlowGenerator
class MetaFlowGenerator:
    async def generate(
        self,
        intents: List[Intent],
        user_description: str
    ) -> MetaFlow:
        """从意图列表生成 MetaFlow"""
        pass

# WorkflowGenerator
class WorkflowGenerator:
    async def generate(
        self,
        metaflow: MetaFlow
    ) -> str:
        """将 MetaFlow 转换为 YAML Workflow"""
        pass
```

---

## 11. 设计决策记录

| 问题 | 决策 | 理由 |
|-----|------|------|
| 基本结构 | 图结构，YAML 格式 | 参考 workflow，人类可读 |
| 数据流 | 不包含 | LLM 在生成时推断 |
| 循环格式 | 只有 description | 细节由 LLM 决定 |
| 变量命名 | 生成 workflow 时由 LLM 决定 | 灵活性 |
| 生成策略 | 纯 LLM | 最大灵活性 |
| 可读性 | 人类可读优先 | MetaFlow 是给人看的 |
| 格式 | YAML + Pydantic | 易读 + 可验证 |
| 顶层字段 | 只要必须的 | 不加无用功能 |
| operations | 从记忆中来 | 未来会细化 |
| 节点 ID | 从记忆中来 | 保持一致性 |

---

## 12. 参考

- 讨论记录: `discussions/02_metaflow_format.md`
- BaseAgent Workflow 规范: `../baseagent/workflow_specification.md`
- 系统整体设计: `design_overview.md`
