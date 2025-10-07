# 讨论记录 02 - MetaFlow 格式设计

**日期**: 2025-10-07
**状态**: 待讨论

---

## 需要明确的问题

### 1. MetaFlow 的职责边界

**问题**: MetaFlow 应该表达什么信息？包含哪些内容？

- [ ] 意图的执行顺序
- [ ] 意图之间的数据流
- [ ] 控制流（循环、条件）
- [ ] 执行配置（超时、重试等）
- [ ] 其他？

**已确定**:

应该表达意图的执行顺序和控制流

✅ MetaFlow 负责：
- 意图的执行顺序
- 控制流（循环）
- 每个意图的完整信息（包括操作步骤）

❌ MetaFlow 不负责：
- 数据流（由 LLM 在生成 YAML 时推断）
- 并行执行（暂不考虑）



---

### 2. 基本数据结构

**问题**: MetaFlow 用什么数据结构表示？

**选项 A**: 线性列表
```python
metaflow = [
    {"intent_id": "intent_1"},
    {"intent_id": "intent_2"},
    {"intent_id": "intent_3"}
]
```

**选项 B**: 树形结构
```python
metaflow = {
    "nodes": [
        {"intent": "intent_1"},
        {"intent": "intent_2"},
        {
            "type": "loop",
            "children": [{"intent": "intent_3"}]
        }
    ]
}
```

**选项 C**: 图结构（DAG）
```python
metaflow = {
    "nodes": [
        {"id": "n1", "intent": "intent_1"},
        {"id": "n2", "intent": "intent_2"}
    ],
    "edges": [
        {"from": "n1", "to": "n2", "data": "page_state"}
    ]
}
```

**选项 D**: 其他方案

**已确定: 选项 C - 图结构**

理由：
- 使用图结构（节点 + 边），可以表示顺序流和控制流
- 写成文件时使用 YAML 格式，参考现有的 workflow YAML 定义
- 人类可读，易于查看和理解
- 未来可扩展（条件分支、嵌套循环）

实际结构：
```yaml
version: "1.0"
task_description: "任务描述"
nodes:
  - id: node_1
    intent_id: intent_001
    intent_name: "..."
    intent_description: "..."
    operations: [...]
  - id: node_2
    type: loop
    description: "..."
    children: [...]
```

---

### 3. 数据流表示方式

**问题**: 意图之间如何传递数据？

**背景场景**:
```
Intent1: Navigate → 产生 page_state
Intent2: ExtractList → 需要 page_state，产生 product_list
Intent3: ExtractDetails → 需要 product_list
```

**选项 A**: 隐式推断（MetaFlow 不包含数据流信息）
```python
metaflow = [
    {"intent": "Navigate"},
    {"intent": "ExtractList"},
    {"intent": "ExtractDetails"}
]
# 生成 YAML 时根据意图的 inputs/outputs 自动推断
```

**选项 B**: 显式声明数据流
```python
metaflow = {
    "nodes": [
        {"id": "n1", "intent": "Navigate", "outputs": {"page": "page_state"}},
        {"id": "n2", "intent": "ExtractList",
         "inputs": {"page": "page_state"},
         "outputs": {"list": "product_list"}},
        {"id": "n3", "intent": "ExtractDetails",
         "inputs": {"list": "product_list"}}
    ]
}
```

**选项 C**: 部分显式（只在必要时声明）

**已确定: 选项 A - 隐式推断**

理由：
- MetaFlow 不包含数据流信息
- 在生成 workflow 的时候由 LLM 推断和生成
- 降低 MetaFlow 的复杂度
- LLM 根据意图的 operations 自动推断变量传递关系
- 给 LLM 最大的灵活性



---

### 4. 循环的表示方式

**问题**: 如何在 MetaFlow 中表示循环？

**需要表达的信息**:
- 循环来源（遍历哪个变量）
- 循环体（哪些意图在循环内）
- 循环变量名称（当前项叫什么）
- 最大迭代次数（可选）

**选项 A**: 作为特殊节点
```python
{
    "type": "loop",
    "source": "product_list",
    "item_var": "current_product",
    "children": [
        {"intent": "ExtractDetails"}
    ]
}
```

**选项 B**: 作为节点属性
```python
{
    "intent": "ExtractDetails",
    "loop": {
        "source": "product_list",
        "item_var": "current_product"
    }
}
```

**选项 C**: 其他方案
参考 workflow，foreach，loop

**已确定: 选项 A - 作为特殊节点，但只包含自然语言描述**

理由：
- 循环节点只有 type, description, children
- description 是自然语言描述，例如："遍历产品列表，逐个提取价格信息"
- 不指定 source（循环来源）、item_var（循环变量）、max_iterations 等细节
- 所有具体细节由 LLM 在生成 workflow 时推断
- 保持 MetaFlow 简单、人类可读

示例：
```yaml
- id: node_4
  type: loop
  description: "遍历产品列表，逐个访问产品页面并提取价格信息"
  children:
    - id: node_4_1
      intent_id: intent_004
      intent_name: "ExtractProductPrice"
      operations: [...]
```



---

### 5. 变量命名策略

**问题**: MetaFlow 中的变量名由谁来定？如何命名？

**选项 A**: 生成 MetaFlow 时就确定变量名
```python
{"outputs": {"page": "page_state_001"}}  # 明确的变量名
```

**选项 B**: 只用占位符，生成 YAML 时再命名
```python
{"outputs": {"page": "$output_1"}}  # 占位符
```

**选项 C**: 使用意图的输出字段名
```python
# Intent 定义了 outputs={"page": "PageState"}
# MetaFlow 直接引用 "page"
```


**已确定: 选项 A - 生成 YAML 时由 LLM 确定变量名**

理由：
- MetaFlow 不包含数据流信息，因此也不需要确定变量名
- 在 MetaFlow → YAML 的转换过程中，由 LLM 决定所有变量命名
- LLM 根据上下文生成语义化的变量名（如 page_state, product_list 等）
- 最大灵活性



---

### 6. MetaFlow 到 YAML 的映射关系

**问题**: 一个 MetaFlow 节点对应多少个 YAML step？

**场景**:
```
Intent(label="ExtractProductInfo")
内部可能需要:
  1. 点击产品
  2. 等待页面加载
  3. 提取数据
```

**选项 A**: 一对一映射
- 一个意图 → 一个 Agent step
- 意图内部的细节在 atomic_intents 中，但最终只生成一个 step

**选项 B**: 一对多映射
- 一个意图 → 多个 Agent step
- 根据 atomic_intents 展开

**已确定: 由 LLM 决定（一对多映射）**

理由：
- 一个意图可能包含多个操作（operations）
- MetaFlow 节点包含完整的 operations 列表
- 在生成 YAML 时，由 LLM 根据 operations 的复杂度决定生成几个 step
- 可能是一对一（简单意图），也可能是一对多（复杂意图）
- 给 LLM 最大的灵活性

关键点：
- Intent 存储 4 个域：id, name, description, operations
- MetaFlow 节点包含意图的完整信息（4 个域）
- operations 是从意图记忆中复制的原始数据

### 7. 生成 YAML 的策略

**问题**: MetaFlow → YAML 使用什么策略？

**选项 A**: 纯模板生成
```python
def metaflow_to_yaml(metaflow):
    for node in metaflow.nodes:
        if node.intent.type == "Navigate":
            yield {"agent_type": "tool_agent", "action": "go_to_url"}
```
- 优点: 确定、快速、可控
- 缺点: 需要 MetaFlow 非常结构化

**选项 B**: 纯 LLM 生成
```python
yaml = llm.generate(f"将这个 MetaFlow 转换为 YAML: {metaflow}")
```
- 优点: 灵活
- 缺点: 不确定、慢、成本高

**选项 C**: 混合策略
```python
try:
    return template_generator(metaflow)
except InsufficientInfo:
    return llm_generator(metaflow)
```
- 尽量用模板，必要时用 LLM

**已确定: 选项 B - 纯 LLM 生成**

理由：
- 最大灵活性，LLM 可以根据上下文做出最优决策
- 不需要维护复杂的模板系统
- LLM 负责：
  - 理解每个意图的 operations
  - 决定用什么 Agent 类型（tool_agent, scraper_agent 等）
  - 推断数据流（变量命名和传递）
  - 理解循环的 description，生成 foreach 结构
  - 决定循环来源、循环变量名等
  - 决定一个意图生成几个 YAML step



---

### 8. MetaFlow 的可读性要求

**问题**: MetaFlow 需要人类可读吗？

**场景考虑**:
- 只是内部中间表示（机器可解析即可）
- 需要给用户展示（未来版本支持用户修改）
- 需要调试时查看

**已确定: MetaFlow 必须人类可读**

理由：
- MetaFlow 就是给人来确定能不能满足人的需要的
- 未来版本支持用户查看 MetaFlow → 提出修改建议 → LLM 修改 MetaFlow
- 使用 YAML 格式（易读易编辑）
- 每个节点都有清晰的 name 和 description
- 循环用自然语言描述，人类容易理解
- 调试时也需要查看 MetaFlow 理解任务逻辑

---

### 9. 格式选择

**问题**: MetaFlow 用什么格式存储和传递？

**选项**:
- Python 字典
- JSON
- Pydantic/Dataclass
- 自定义 DSL
- 其他

**已确定: YAML + Pydantic**

理由：
- YAML: 人类可读，易于查看和编辑
- Pydantic: 数据验证和类型检查，保证格式正确
- 两者结合：既有可读性又有可验证性

实现：
```python
from pydantic import BaseModel
from typing import List, Union
import yaml

class MetaFlow(BaseModel):
    version: str = "1.0"
    task_description: str
    nodes: List[Union[MetaFlowNode, LoopNode]]

    def to_yaml(self) -> str:
        return yaml.dump(self.dict(), allow_unicode=True)

    @classmethod
    def from_yaml(cls, yaml_str: str):
        return cls(**yaml.safe_load(yaml_str))
```


---

### 10. 扩展性考虑

**问题**: 如何平衡 MVP 的简单性和未来的扩展性？

**MVP 需要支持**:
- 线性序列
- 简单循环

**未来可能需要**:
- 条件分支（if/else）
- 嵌套循环
- 并行执行
- 错误处理

**已确定: 只加必要的东西，但保持可扩展性**

理由：
- MVP 阶段只支持线性序列和简单循环（一层，不嵌套）
- 设计上不冲突，未来可以自然扩展
- 扩展方向：
  - 条件分支：增加 type: condition 节点
  - 嵌套循环：loop 的 children 中可以有 loop
  - 并行执行：增加 type: parallel 节点
  - 错误处理：增加 error_handling 配置

设计原则：
- 顶层只有 3 个字段：version, task_description, nodes
- 不加任何当前用不到的功能
- 保持简单，未来需要时再扩展



---

## 示例验证

### 基于咖啡采集的完整示例

**任务**: "从 Allegro 采集所有咖啡产品的价格"

**意图列表**:
```python
intents = [
    Intent(id="intent_1", label="NavigateToAllegro"),
    Intent(id="intent_2", label="EnterCoffeeCategory"),
    Intent(id="intent_3", label="ExtractProductList",
           outputs={"product_urls": "list"}),
    Intent(id="intent_4", label="ExtractProductPrice",
           inputs={"product_url": "string"},
           outputs={"price": "string"})
]
```

**请根据你上面的回答，写出对应的 MetaFlow 示例**:

```python
metaflow =
# 请在这里填写完整的 MetaFlow 数据结构




```

---

## 关键设计结论

### Intent 的存储格式

Intent 在记忆系统中存储 4 个域：
1. **id**: 数据库唯一标识
2. **name**: 简短名称（类似函数名）
3. **description**: 人类可读描述
4. **operations**: 操作步骤列表

```python
class Intent(BaseModel):
    id: str
    name: str
    description: str
    operations: List[Operation]  # 具体的操作步骤
```

### MetaFlow 节点 = Intent 的完整副本

**关键洞察**:
> "metaflow 就是的每个节点的信息都来自记忆系统，而不是 metaflow 自定义的。我们生成 metaflow 的过程，大概率是一个从记忆系统中直接捞数据上来的过程。"

MetaFlow 的普通节点包含 Intent 的所有 4 个域：
```yaml
- id: node_1                        # 节点 ID（从意图记忆中来）
  intent_id: intent_001              # 意图 ID → 对应 Intent.id
  intent_name: "NavigateToAllegro"   # 意图名称 → 对应 Intent.name
  intent_description: "导航到 Allegro 首页"  # → 对应 Intent.description
  operations:                        # 操作步骤 → 对应 Intent.operations
    - action: navigate
      params:
        url: "https://allegro.pl/"
```

### Operations 格式

- operations 是从意图记忆中复制的原始数据
- 格式由意图记忆系统决定
- MetaFlow 只负责存储和传递
- 未来会随记忆系统进一步细化

### 循环节点设计

循环节点只包含自然语言描述，不包含技术细节：
```yaml
- id: node_4
  type: loop
  description: "遍历产品列表，逐个访问产品页面并提取价格信息"  # 只有描述
  children:
    - id: node_4_1
      intent_id: intent_004
      operations: [...]
```

**不包含的内容**（由 LLM 在生成 workflow 时决定）：
- source: 循环来源
- item_var: 循环变量名
- max_iterations: 最大迭代次数

### 节点 ID 来源

- 节点 ID 从意图记忆系统中获取
- MetaFlow 生成时从意图继承 ID
- 保持与记忆系统的一致性

---

## 备注

基于以上讨论结论，已生成正式的 MetaFlow 设计文档：`metaflow_design.md`
