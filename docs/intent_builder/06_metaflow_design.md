# MetaFlow 设计文档

**版本**: v2.0
**日期**: 2025-10-09
**状态**: 已确定（基于新架构）

---

## 1. 定义

**MetaFlow（元工作流）** 是 Intent 到 Workflow 之间的中间表示，由 LLM 生成，包含完整的任务执行逻辑。

### 核心特点

- **给人看的**：人类可读的 YAML 格式，用户可以查看和理解
- **可执行的**：包含完整信息，可直接转换为 BaseAgent Workflow
- **由 LLM 生成**：MetaFlowGenerator 负责所有推理工作
- **包含推断结果**：隐式节点、数据流、控制流都在 MetaFlow 中明确表达

### 职责

MetaFlow 负责表达：
- ✅ Intent 的执行顺序
- ✅ 控制流（循环、循环来源、循环变量）
- ✅ 数据流（变量传递关系）
- ✅ 隐式节点（LLM 推断生成，如 ExtractList）
- ✅ 每个 Intent 的完整信息（operations）
- ❌ 并行执行（MVP 不支持）

### 与 v1.0 的主要变化

1. **数据流信息**：v2.0 在 MetaFlow 中明确包含数据流（v1.0 延迟到 Workflow 生成）
2. **隐式节点**：v2.0 包含 LLM 推断的隐式节点（标记 `type: hidden`）
3. **循环细节**：v2.0 明确指定循环来源节点和循环变量
4. **生成方式**：v2.0 强调 MetaFlow 完全由 LLM 生成，而非模板

---

## 2. 数据结构

### 2.1 整体结构

```yaml
version: "2.0"                    # MetaFlow 格式版本
task_description: "任务描述"       # 用户的自然语言任务描述

nodes:                            # 节点列表（按执行顺序）
  - id: <node_id>                 # 节点 ID
    intent_id: <intent_id>        # 关联的 Intent ID (可选，来自 IntentMemoryGraph)
    intent_name: "IntentName"     # Intent 名称（简化）
    intent_description: "..."     # Intent 描述
    operations: [...]             # 完整 operations

  - id: <node_id>
    # 没有 intent_id = LLM 推断生成的节点
    intent_name: "InferredNode"
    intent_description: "..."
    operations: [...]             # LLM 生成的 operations

control_flow:                     # 控制流信息（LLM 推断）
  loops:                          # 循环列表
    - loop_variable: <var_name>   # 循环变量名
      source_node: <node_id>      # 数据来源节点
      loop_body: [<node_id>, ...] # 循环体节点列表
```

**关键设计**：
- 所有节点格式统一，无需标记节点类型
- `intent_id` 可选：有则来自 IntentMemoryGraph，无则为 LLM 推断
- 移除嵌套的 `children` 结构，改用 `control_flow` 统一描述
- 明确指定 `source_node` 和 `loop_variable`

### 2.2 节点格式

所有节点使用统一格式：

```yaml
- id: node_1
  intent_id: intent_b7e4c8d2               # 可选：Intent ID（来自 IntentMemoryGraph）
  intent_name: "NavigateToAllegro"         # Intent 名称（简短标识）
  intent_description: "导航到 Allegro 首页"  # 人类可读描述
  operations:                              # 完整 operations
    - type: navigate
      timestamp: 1757730777260
      url: "https://allegro.pl/"
      page_title: "Navigated Page"
      element: {}
      data: {}
```

**字段说明**：
- `id`: 节点 ID（MetaFlow 内唯一）
- `intent_id`: Intent 在 IntentMemoryGraph 中的 ID（可选）
  - 有 `intent_id`：从 IntentMemoryGraph 检索来的节点
  - 无 `intent_id`：LLM 推断生成的节点
- `intent_name`: Intent 的简短名称（类似函数名）
- `intent_description`: Intent 的详细描述（给人看的）
- `operations`: 完整的操作列表（保留 User Operations JSON 的完整格式）

### 2.3 控制流：循环

v2.0 不使用嵌套的循环节点，改用 `control_flow` 部分统一描述：

```yaml
nodes:
  - id: node_3
    intent_name: ExtractProductList
    intent_description: "提取产品列表"
    operations: [...]

  - id: node_4
    intent_id: intent_c9f2d5e3
    intent_name: ExtractProductInfo
    intent_description: "提取单个产品信息"
    operations: [...]

control_flow:
  loops:
    - loop_variable: product_url        # 循环变量名
      source_node: node_3               # 数据来源（提供列表的节点）
      loop_body: [node_4]               # 循环体节点列表
```

**设计原则**：
- 节点列表是平铺的，没有嵌套
- 循环信息在 `control_flow.loops` 中明确描述
- `source_node` 指向提供列表数据的节点
- `loop_body` 列出循环体内的节点 ID
- 所有这些都由 LLM 在生成 MetaFlow 时推断

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
| `input` | 输入文本 | element, data.value |
| `select` | 选择文本 | element, data.selectedText |
| `copy_action` | **复制操作** | element, data.copiedText |
| `wait` | 等待 | data.duration |
| `scroll` | 滚动 | data.direction, data.distance |

**关键操作说明：copy_action**

`copy_action` 表示用户复制了页面上的文本，这是用户想要提取数据的重要信号：

```yaml
- type: select
  timestamp: 1757730781507
  url: "https://allegro.pl/oferta/..."
  element:
    xpath: "//*[@id='price-section']"
    tagName: "DIV"
    textContent: "cena 69,50 złAllegro Smart! to darmowe dostawy..."
  data:
    selectedText: "cena69,50 zł\n"

- type: copy_action
  timestamp: 1757730781650
  element:
    xpath: "//*[@id='price-section']"
    tagName: "DIV"
    textContent: "cena 69,50 złAllegro Smart! to darmowe dostawy..."
  data:
    copiedText: "69,50 zł"
    textLength: 13
    copyMethod: "selection"
```

**为什么保留 copy_action？**

1. **用户意图明确**：复制动作表明用户想要这个数据
2. **数据精确**：`copiedText` 是用户实际选择的内容，可能是 `textContent` 的子集
3. **LLM 理解**：WorkflowGenerator 的 LLM 可以理解 `copy_action` 的语义，生成正确的数据提取逻辑

**LLM 如何理解 copy_action？**

```
element.textContent: "cena 69,50 zł Allegro Smart! to darmowe dostawy..."
data.copiedText:     "69,50 zł"
```

LLM 推断：
- 用户只想要价格数值部分
- 生成 workflow 时需要从该元素中提取 "69,50 zł" 这样的模式
- 可以生成相应的正则表达式或选择器

**完整示例**：

```yaml
# 用户操作：导航 → 选择 → 复制（保留原始格式）
operations:
  - type: navigate
    timestamp: 1757730780000
    url: "https://allegro.pl/oferta/kawa-..."
    page_title: "Kawa ziarnista..."
    element: {}
    data: {}

  - type: select
    timestamp: 1757730781000
    url: "https://allegro.pl/oferta/kawa-..."
    element:
      xpath: "//*[@id='product-title']"
      tagName: "H1"
      textContent: "Kawa ziarnista 1kg BRAZYLIA Santos..."
    data:
      selectedText: "Kawa ziarnista 1kg BRAZYLIA Santos..."

  - type: copy_action
    timestamp: 1757730781100
    element:
      xpath: "//*[@id='product-title']"
      tagName: "H1"
      textContent: "Kawa ziarnista 1kg BRAZYLIA Santos..."
    data:
      copiedText: "Kawa ziarnista 1kg BRAZYLIA Santos..."

  - type: select
    timestamp: 1757730782000
    element:
      xpath: "//*[@id='price-section']"
      tagName: "DIV"
      textContent: "cena 69,50 złAllegro Smart! to darmowe dostawy..."
    data:
      selectedText: "cena69,50 zł\n"

  - type: copy_action
    timestamp: 1757730782100
    element:
      xpath: "//*[@id='price-section']"
      tagName: "DIV"
      textContent: "cena 69,50 złAllegro Smart! to darmowe dostawy..."
    data:
      copiedText: "69,50 zł"  # 用户只复制了价格部分
```

**注意**：
- operations 保留 User Operations JSON 的原始格式
- `copy_action` 保留在 operations 中，不转换为 extract
- LLM (WorkflowGenerator) 理解 copy_action 的语义，生成相应的提取逻辑
- `copiedText` 可能是 `textContent` 的子集，告诉 LLM 用户想要的精确数据

---

## 3. 完整示例

### 任务：从 Allegro 采集所有咖啡产品的价格

参考 `examples/coffee_collection_metaflow.yaml`

```yaml
version: "2.0"
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

  # 节点 3: 提取产品列表（LLM 推断的隐式节点）
  - id: node_3
    # 没有 intent_id，因为这是 LLM 推断生成的
    intent_name: "ExtractProductList"
    intent_description: "提取产品列表链接"
    operations:
      - type: extract_links
        element:
          selector: ".product-item a"
        data:
          link_pattern: "/oferta/*"

  # 节点 4: 提取单个产品信息（在循环体内）
  - id: node_4
    intent_id: intent_c9f2d5e3
    intent_name: "ExtractProductInfo"
    intent_description: "访问产品详情页并提取价格、标题等信息"
    operations:
      - type: navigate
        url: "{{product_url}}"
      - type: select
        element: {...}
      - type: copy_action
        data:
          copiedText: "..."

control_flow:
  loops:
    - loop_variable: product_url
      source_node: node_3
      loop_body: [node_4]
```

---

## 4. 与 Intent 的关系

### Intent 的存储格式（v2.0）

Intent 在 IntentMemoryGraph 中的存储格式（极简）：

```python
@dataclass
class Intent:
    id: str                      # MD5 hash of description
    description: str             # 语义描述
    operations: List[Operation]  # 完整操作序列
    created_at: datetime         # 创建时间
    source_session_id: str       # 来源会话
```

### MetaFlow 节点包含 Intent 信息

**从 IntentMemoryGraph 检索的节点**：

```
Intent (IntentMemoryGraph)         MetaFlow Node
────────────────────────────────────────────────────────
id: "intent_b7e4c8d2"         →    intent_id: intent_b7e4c8d2
description: "导航到..."       →    intent_description: "导航到..."
operations: [...]             →    operations: [...]
                                   intent_name: "NavigateToAllegro"  (LLM生成简称)
```

**LLM 推断生成的节点**：

```
MetaFlow Node (无 intent_id)
────────────────────────────
intent_name: "ExtractProductList"
intent_description: "提取产品列表"
operations: [...]  # LLM 根据任务推断生成
```

**为什么要复制完整信息？**
1. MetaFlow 是独立文档，包含完整上下文
2. WorkflowGenerator 需要 operations 来生成 YAML
3. 用户查看时无需查询 IntentMemoryGraph

---

## 5. 生成策略

### 5.1 Intent + User Query → MetaFlow

**由 MetaFlowGenerator 生成，完全依赖 LLM**：

```python
async def generate(
    self,
    intents: List[Intent],
    task_description: str,
    user_query: str
) -> MetaFlow:
    """
    LLM 负责：
    1. 循环检测：从 user_query 识别关键词（"所有"、"每个"）
    2. 隐式节点生成：推断缺失的节点（如 ExtractList）
    3. 数据流连接：推断变量传递关系
    4. 节点排序：确定执行顺序
    5. 生成 control_flow
    """

    prompt = self._build_prompt(intents, task_description, user_query)
    response = await self.llm.generate_response("", prompt)
    metaflow_yaml = self._extract_yaml(response)
    return MetaFlow.from_yaml(metaflow_yaml)
```

**LLM 推断能力**：
- **循环检测**：识别 "所有"、"每个"等关键词
- **隐式节点**：如果有循环但无 ExtractList，自动生成
- **数据流**：推断 `source_node` 和 `loop_variable`
- **节点顺序**：根据语义排列节点

详见：`metaflow_generator_design.md`

### 5.2 MetaFlow → YAML Workflow

**由 WorkflowGenerator 生成（已有实现）**：

```python
async def generate(self, metaflow: MetaFlow) -> str:
    """
    LLM 负责：
    1. 理解每个节点的 operations
    2. 选择合适的 Agent 类型（scraper_agent, tool_agent）
    3. 理解 copy_action 的语义，生成数据提取逻辑
    4. 根据 control_flow.loops 生成 foreach 结构
    5. 生成完整可执行的 YAML
    """

    prompt = self._build_workflow_prompt(metaflow)
    yaml_workflow = await self.llm.generate(prompt)
    return yaml_workflow
```

**LLM 职责**：
- 理解 operations（包括 copy_action）
- 生成 BaseAgent Workflow YAML
- Agent 类型选择
- 参数配置（xpath, sample_data等）

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
