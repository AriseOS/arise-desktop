# MetaFlowGenerator 组件设计文档

**版本**: v2.0
**日期**: 2025-10-09
**状态**: 已确定

---

## 1. 概述

### 1.1 定义

**MetaFlowGenerator** 负责从 IntentMemoryGraph（图结构）生成 MetaFlow YAML。

### 1.2 职责

- **输入**: IntentMemoryGraph (nodes + edges) + Task Description + User Query
- **输出**: MetaFlow YAML
- **核心任务**:
  1. 从图结构中选择相关路径（基于 User Query）
  2. 将选中的 Intent 列表组装成 MetaFlow 节点
  3. 检测并生成循环结构
  4. 推断隐式节点（如缺少的列表提取节点）
  5. 推断数据流连接

### 1.3 设计策略

**LLM 全权负责**: 完全交给 LLM 处理，不使用规则推断

**理由**:
- 隐式节点生成逻辑复杂
- 数据流连接需要语义理解
- LLM 更灵活，可处理各种复杂情况

---

## 2. 架构设计

### 2.1 组件结构

```
MetaFlowGenerator
  ├── _build_prompt()           # 构建 LLM Prompt
  ├── _extract_yaml()           # 提取 YAML
  └── generate()                # 主流程
```

### 2.2 数据流

```
IntentMemoryGraph (nodes + edges) + Task Description + User Query
  ↓
[1] Build Prompt (包含 Graph 结构、Intent 信息和转换规则)
  ↓
LLM (选择相关路径 + 生成 MetaFlow)
  ↓
[2] Extract YAML from Response
  ↓
[3] Parse and Validate
  ↓
MetaFlow Object
```

**关键说明**:
- **输入是图结构**: MetaFlowGenerator 接收的是完整的图（nodes + edges），而非预先筛选的 Intent 列表
- **LLM 负责路径选择**: 当图有分支时（如 coffee 分支 vs book 分支），LLM 根据 User Query 选择相关路径
- **示例**:
  - Graph 包含两条路径: "coffee 产品信息收集" 和 "book 产品信息收集"
  - User Query: "收集咖啡商品信息"
  - LLM 识别并选择 coffee 分支的 Intent，过滤掉 book 分支

---

## 3. 详细设计

### 3.1 主流程方法

```python
class MetaFlowGenerator:
    """从 IntentMemoryGraph 生成 MetaFlow"""

    def __init__(self, llm_service: LLMService):
        self.llm = llm_service

    async def generate(
        self,
        graph: IntentMemoryGraph,
        task_description: str,
        user_query: str
    ) -> MetaFlow:
        """
        从 IntentMemoryGraph 生成 MetaFlow

        Args:
            graph: IntentMemoryGraph 对象（包含 nodes 和 edges）
            task_description: 任务的详细描述
            user_query: 用户的查询（用于路径选择、循环检测等）

        Returns:
            MetaFlow 对象

        说明:
            - graph 包含完整的图结构（可能有多条分支路径）
            - LLM 根据 user_query 选择相关路径上的 Intent
            - 例如: Graph 包含 coffee 和 book 两条路径，user_query="收集咖啡信息"
                    则 LLM 自动选择 coffee 分支，过滤掉 book 分支
        """
        # 1. 从图中获取所有 intents 和 edges
        intents = graph.get_all_intents()
        edges = graph.get_edges()  # List[Tuple[str, str]]

        # 2. 构建 Prompt（包含图结构信息）
        prompt = self._build_prompt(intents, edges, task_description, user_query)

        # 3. 调用 LLM 生成 MetaFlow YAML（LLM 负责路径选择）
        response = await self.llm.generate_response("", prompt)

        # 4. 提取 YAML（从 markdown code block）
        metaflow_yaml = self._extract_yaml(response)

        # 5. 解析并验证
        metaflow = MetaFlow.from_yaml(metaflow_yaml)

        return metaflow
```

---

### 3.2 Prompt 构建方法

```python
def _build_prompt(
    self,
    intents: List[Intent],
    edges: List[Tuple[str, str]],
    task_desc: str,
    user_query: str
) -> str:
    """构建 MetaFlow 生成提示词（包含图结构信息）"""

    # 格式化 Intent 列表
    intent_descriptions = []
    for intent in intents:
        intent_descriptions.append({
            "id": intent.id,
            "description": intent.description,
            "operations": [
                {
                    "type": op['type'],
                    "url": op.get('url', ''),
                    "element": {
                        k: v for k, v in op.get('element', {}).items()
                        if k in ['xpath', 'tagName', 'textContent', 'href']
                    },
                    **({k: v for k, v in op.items()
                       if k in ['target', 'value', 'data']})
                }
                for op in intent.operations
            ]
        })

    # 格式化边信息
    edges_formatted = [
        {"from": from_id, "to": to_id}
        for from_id, to_id in edges
    ]

    return f"""将以下 Intent 图结构转换为 MetaFlow YAML。

## 任务描述
{task_desc}

## 用户查询
{user_query}

## Intent Graph 结构

### Nodes (Intents)
{json.dumps(intent_descriptions, indent=2, ensure_ascii=False)}

### Edges (Intent 执行顺序)
{json.dumps(edges_formatted, indent=2, ensure_ascii=False)}

**重要说明 - 路径选择**:
- 图中可能包含多条分支路径（例如: coffee 分支、book 分支等）
- 你需要根据 "用户查询" 选择相关的路径
- 只使用与用户查询相关的 Intent，忽略无关分支
- 例如: 如果用户查询是 "收集咖啡信息"，则只选择 coffee 相关的 Intent，忽略 book 相关的 Intent

---

{self._get_metaflow_spec()}

---

{self._get_conversion_rules()}

---

## 输出要求

输出完整的 MetaFlow YAML（符合上述规范）。

注意：
- **路径过滤**: 只包含与用户查询相关的 Intent，忽略图中的无关分支
- 只输出 YAML，不要其他解释
- 确保 YAML 格式正确，可以被解析
- 如果需要循环，检测用户查询中的关键词（"所有"、"每个"等）
- 如果循环需要列表数据但 Intent 中没有提供，插入隐式的 ExtractList 节点
"""
```

---

### 3.3 MetaFlow 规范说明

```python
def _get_metaflow_spec(self) -> str:
    """获取 MetaFlow 规范"""
    return """# MetaFlow 规范

## 基本结构

```yaml
version: "1.0"
task_description: "任务描述"

nodes:
  # 普通节点
  - id: node_1
    intent_id: intent_xxx
    intent_name: "NavigateToSite"
    intent_description: "导航到网站"
    operations:
      - type: navigate
        url: "https://example.com"
        element: {}
    outputs:  # 可选：如果这个节点产生输出
      output_key: "variable_name"

  # 循环节点
  - id: node_2
    type: loop
    description: "遍历列表，处理每个项目"
    source: "{{list_variable}}"
    item_var: "current_item"
    children:
      - id: node_2_1
        intent_id: intent_yyy
        intent_name: "ProcessItem"
        intent_description: "处理单个项目"
        operations: [...]
        inputs:  # 可选：使用循环变量
          item_url: "{{current_item.url}}"
        outputs:
          result: "item_result"
```

## 关键点

1. **普通节点**: 直接映射 Intent
   - `intent_id`: Intent 的 ID
   - `intent_name`: 简化的名称（PascalCase）
   - `intent_description`: Intent 的 description
   - `operations`: Intent 的 operations（完整复制）

2. **outputs**: 如果节点产生数据（特别是 extract 操作）
   - 格式：`{output_key: "variable_name"}`
   - 例如：`{"product_urls": "product_urls"}`

3. **循环节点**: 用于遍历列表
   - `type: loop`
   - `description`: 循环的自然语言描述
   - `source`: 数据源（引用前面节点的 output）
   - `item_var`: 循环变量名
   - `children`: 循环体（子节点列表）

4. **数据流**: 使用 `{{variable_name}}` 引用变量
   - 前面节点的 output 可以被后面节点引用
   - 循环变量在 children 中可用：`{{current_item.field}}`
"""
```

---

### 3.4 转换规则说明

```python
def _get_conversion_rules(self) -> str:
    """获取转换规则"""
    return """# 转换规则

## 1. Intent → MetaFlowNode 映射

每个 Intent 生成一个 MetaFlowNode：

```yaml
# Intent
Intent(
  id="intent_a3f5b2c1",
  description="导航到 Allegro 首页",
  operations=[...]
)

# MetaFlowNode
- id: node_1
  intent_id: intent_a3f5b2c1
  intent_name: "NavigateToAllegro"  # 从 description 提取
  intent_description: "导航到 Allegro 首页"
  operations: [...]  # 完整复制
```

## 2. 循环检测和生成

**检测关键词**: "所有"、"全部"、"每个"、"遍历"、"all"、"every"、"each"

**生成循环结构**:
1. 检测到循环关键词
2. 识别需要遍历的 Intent（通常是提取详情的 Intent）
3. 检查是否有列表提取节点
4. 如果没有 → 插入隐式节点

**示例**:
```yaml
# 用户查询："收集所有咖啡商品信息"
# Intent 列表：[NavigateToCategory, ExtractProductDetail]

# 生成结果：
nodes:
  - id: node_1
    # NavigateToCategory
    ...

  - id: node_2  # 隐式节点（推断）
    intent_id: implicit_extract_list
    intent_name: "ExtractProductList"
    intent_description: "提取商品列表（推断节点）"
    operations:
      - type: extract
        target: "product_urls"
        element:
          xpath: "<PLACEHOLDER>"  # 占位符，由 WorkflowGenerator 填充
          tagName: "A"
        value: []  # 表示是列表
    outputs:
      product_urls: "product_urls"

  - id: node_3  # 循环节点
    type: loop
    description: "遍历商品列表，提取详细信息"
    source: "{{product_urls}}"
    item_var: "current_product"
    children:
      - id: node_3_1
        # ExtractProductDetail
        inputs:
          product_url: "{{current_product.url}}"
        ...
```

## 3. 隐式节点生成规则

**触发条件**:
- 检测到循环需求
- Intent 列表中没有提取列表的节点

**生成内容**:
```yaml
- id: node_implicit
  intent_id: implicit_extract_list
  intent_name: "ExtractProductList"
  intent_description: "提取产品列表（推断节点）"
  operations:
    - type: extract
      target: "product_urls"  # 根据语义推断
      element:
        xpath: "<PLACEHOLDER>"  # 使用占位符
        tagName: "A"
      value: []  # 列表类型
  outputs:
    product_urls: "product_urls"
```

**注意**:
- `xpath` 使用占位符 `<PLACEHOLDER>`
- 由后续的 WorkflowGenerator 填充具体值
- `target` 和 `outputs` 根据上下文推断

## 4. 数据流连接规则

**outputs 推断**:
- 如果 operations 中有 `extract` 操作 → 生成 outputs
- `extract.target` 作为 output key
- 例如：`extract(target="price")` → `outputs: {price: "price"}`

**inputs 引用**:
- 循环内的节点需要引用循环变量
- 格式：`{{item_var.field}}`
- 例如：`{{current_product.url}}`

**变量命名**:
- 列表变量：`product_urls`, `all_products`, `item_list`
- 循环变量：`current_product`, `current_item`, `item`
- 结果变量：`product_info`, `item_data`, `result`

## 5. intent_name 生成规则

从 `intent_description` 提取关键动词和名词，生成 PascalCase 名称：

- "导航到 Allegro 首页" → "NavigateToAllegro"
- "进入咖啡分类页面" → "EnterCoffeeCategory"
- "提取产品信息" → "ExtractProductInfo"

## 6. 节点顺序

按 Intent 的顺序排列，但：
- 隐式节点插入在循环节点之前
- 循环节点包含子节点（children）

## 7. 示例

**输入**:
- Intents: [NavigateToCategory, ExtractDetail]
- Query: "收集所有商品信息"

**输出**:
```yaml
version: "1.0"
task_description: "收集所有商品信息"

nodes:
  - id: node_1
    intent_id: intent_001
    intent_name: "NavigateToCategory"
    intent_description: "进入商品分类页面"
    operations: [...]

  - id: node_2
    intent_id: implicit_extract_list
    intent_name: "ExtractProductList"
    intent_description: "提取商品列表（推断）"
    operations:
      - type: extract
        target: "product_urls"
        element: {xpath: "<PLACEHOLDER>", tagName: "A"}
        value: []
    outputs:
      product_urls: "product_urls"

  - id: node_3
    type: loop
    description: "遍历商品列表，提取详细信息"
    source: "{{product_urls}}"
    item_var: "current_product"
    children:
      - id: node_3_1
        intent_id: intent_002
        intent_name: "ExtractProductDetail"
        intent_description: "提取产品详细信息"
        operations: [...]
        inputs:
          product_url: "{{current_product.url}}"
        outputs:
          product_info: "product_info"
```
"""
```

---

### 3.5 YAML 提取方法

```python
def _extract_yaml(self, llm_response: str) -> str:
    """从 LLM 响应中提取 YAML"""
    import re

    # 尝试提取 ```yaml ... ``` 代码块
    match = re.search(r'```yaml\n(.*?)\n```', llm_response, re.DOTALL)
    if match:
        return match.group(1)

    # 如果没有代码块，假设整个响应就是 YAML
    return llm_response
```

---

## 4. 完整示例

### 4.1 输入 - 简单线性图

**IntentMemoryGraph** (简单线性路径):
```python
# Nodes
intents = [
  Intent(
    id="intent_a3f5b2c1",
    description="导航到 Allegro 电商网站首页",
    operations=[
      {"type": "navigate", "url": "https://allegro.pl/", "element": {}}
    ]
  ),
  Intent(
    id="intent_b7e4c8d2",
    description="通过菜单导航进入咖啡产品分类页面",
    operations=[
      {"type": "click", "element": {"textContent": "Kawy", ...}},
      {"type": "navigate", "url": "https://allegro.pl/kawa", ...}
    ]
  ),
  Intent(
    id="intent_c9f2d5e3",
    description="访问产品详情页，提取产品的标题、价格、销量信息",
    operations=[
      {"type": "navigate", "url": "...", ...},
      {"type": "select", ...},
      {"type": "copy_action", "data": {"copiedText": "..."}}
    ]
  )
]

# Edges (线性连接)
edges = [
  ("intent_a3f5b2c1", "intent_b7e4c8d2"),  # 首页 → 咖啡分类
  ("intent_b7e4c8d2", "intent_c9f2d5e3"),  # 咖啡分类 → 产品详情
]
```

**Task Description**:
```
"用户希望收集热门的第一页的咖啡的商品的相关信息"
```

**User Query**:
```
"收集所有咖啡商品信息"
```

---

### 4.2 LLM 输出（期望）

````yaml
version: "1.0"
task_description: "用户希望收集热门的第一页的咖啡的商品的相关信息"

nodes:
  # 节点 1: 导航到首页
  - id: node_1
    intent_id: intent_a3f5b2c1
    intent_name: "NavigateToAllegro"
    intent_description: "导航到 Allegro 电商网站首页"
    operations:
      - type: navigate
        url: "https://allegro.pl/"
        element: {}

  # 节点 2: 进入咖啡分类
  - id: node_2
    intent_id: intent_b7e4c8d2
    intent_name: "EnterCoffeeCategory"
    intent_description: "通过菜单导航进入咖啡产品分类页面"
    operations:
      - type: click
        element:
          textContent: "Kawy"
          href: "https://allegro.pl/kawa"
      - type: navigate
        url: "https://allegro.pl/kawa"

  # 节点 2.5: 隐式节点 - 提取产品列表
  - id: node_2_5
    intent_id: implicit_extract_list
    intent_name: "ExtractProductList"
    intent_description: "从咖啡分类页面提取所有产品的链接（推断节点）"
    operations:
      - type: extract
        target: "product_urls"
        element:
          xpath: "<PLACEHOLDER>"
          tagName: "A"
        value: []
    outputs:
      product_urls: "product_urls"

  # 节点 3: 循环 - 收集所有产品信息
  - id: node_3
    type: loop
    description: "遍历产品列表，逐个访问详情页并收集产品信息"
    source: "{{product_urls}}"
    item_var: "current_product"
    children:
      - id: node_3_1
        intent_id: intent_c9f2d5e3
        intent_name: "CollectProductInfo"
        intent_description: "访问产品详情页，提取产品的标题、价格、销量信息"
        inputs:
          product_url: "{{current_product.url}}"
        operations:
          - type: navigate
            url: "{{current_product.url}}"
          - type: select
            element: {...}
          - type: copy_action
            data:
              copiedText: "..."
        outputs:
          product_info: "product_info"
````

---

### 4.3 输入 - 分支图（路径选择场景）

**IntentMemoryGraph** (包含两条分支路径):
```python
# Nodes - 包含 coffee 和 book 两条路径
intents = [
  # 共同的起点
  Intent(
    id="intent_homepage",
    description="导航到 Allegro 电商网站首页",
    operations=[...]
  ),

  # Coffee 分支
  Intent(
    id="intent_coffee_category",
    description="通过菜单导航进入咖啡产品分类页面",
    operations=[...]
  ),
  Intent(
    id="intent_coffee_detail",
    description="访问咖啡产品详情页，提取产品信息",
    operations=[...]
  ),

  # Book 分支
  Intent(
    id="intent_book_category",
    description="通过菜单导航进入图书产品分类页面",
    operations=[...]
  ),
  Intent(
    id="intent_book_detail",
    description="访问图书产品详情页，提取产品信息",
    operations=[...]
  ),
]

# Edges - 展示分支结构
edges = [
  # 首页连接到两个分支
  ("intent_homepage", "intent_coffee_category"),
  ("intent_homepage", "intent_book_category"),

  # Coffee 分支内部连接
  ("intent_coffee_category", "intent_coffee_detail"),

  # Book 分支内部连接
  ("intent_book_category", "intent_book_detail"),
]
```

**User Query** (选择 Coffee 分支):
```
"收集咖啡商品信息"
```

**期望结果**:
- LLM 识别到 user_query 与 coffee 相关
- 只选择 coffee 路径: homepage → coffee_category → coffee_detail
- **过滤掉** book 相关的 Intent (intent_book_category, intent_book_detail)
- 生成的 MetaFlow 只包含 3 个节点（不是 5 个）

### 4.4 解析结果

```python
metaflow = MetaFlow.from_yaml(metaflow_yaml)

print(f"Version: {metaflow.version}")
print(f"Task: {metaflow.task_description}")
print(f"Nodes: {len(metaflow.nodes)}")

# 检查循环节点
loop_nodes = [n for n in metaflow.nodes if isinstance(n, LoopNode)]
print(f"Loop nodes: {len(loop_nodes)}")
```

---

## 5. 错误处理

### 5.1 YAML 格式错误

```python
try:
    metaflow = MetaFlow.from_yaml(metaflow_yaml)
except yaml.YAMLError as e:
    logger.error(f"Invalid YAML: {e}")
    # 重试或返回错误
```

### 5.2 LLM 未返回 YAML

```python
if not metaflow_yaml or len(metaflow_yaml.strip()) == 0:
    logger.error("LLM returned empty response")
    # 重试或使用默认策略
```

### 5.3 验证 MetaFlow 结构

```python
def validate_metaflow(metaflow: MetaFlow) -> bool:
    """验证 MetaFlow 结构"""
    # 检查必需字段
    if not metaflow.version or not metaflow.task_description:
        return False

    # 检查节点
    if not metaflow.nodes:
        return False

    # 检查循环节点的 source
    for node in metaflow.nodes:
        if isinstance(node, LoopNode):
            if not node.source or not node.item_var:
                return False

    return True
```

---

## 6. 测试策略

### 6.1 单元测试

**测试 Prompt 构建**:
```python
def test_build_prompt():
    generator = MetaFlowGenerator(mock_llm)

    intents = [Intent(...), Intent(...)]
    prompt = generator._build_prompt(intents, "task", "query")

    assert "task" in prompt
    assert "query" in prompt
    assert len(intents) > 0
```

**测试 YAML 提取**:
```python
def test_extract_yaml():
    generator = MetaFlowGenerator(mock_llm)

    response = """
Here is the MetaFlow:

```yaml
version: "1.0"
task_description: "test"
nodes: []
```
"""
    yaml_str = generator._extract_yaml(response)

    assert "version:" in yaml_str
    assert "1.0" in yaml_str
```

### 6.2 集成测试

```python
@pytest.mark.asyncio
async def test_generate_metaflow():
    llm = AnthropicProvider()
    generator = MetaFlowGenerator(llm)

    # 创建简单的图结构
    storage = InMemoryIntentStorage()
    graph = IntentMemoryGraph(storage)

    intent1 = Intent(id="intent_1", description="导航到首页", operations=[...])
    intent2 = Intent(id="intent_2", description="提取数据", operations=[...])

    graph.add_intent(intent1)
    graph.add_intent(intent2)
    graph.add_edge(intent1.id, intent2.id)

    # 从图生成 MetaFlow
    metaflow = await generator.generate(
        graph,
        "收集商品信息",
        "收集所有商品信息"
    )

    assert metaflow.version == "1.0"
    assert len(metaflow.nodes) >= 2

@pytest.mark.asyncio
async def test_generate_metaflow_with_branching():
    """测试分支图的路径选择"""
    llm = AnthropicProvider()
    generator = MetaFlowGenerator(llm)

    # 创建分支图结构
    storage = InMemoryIntentStorage()
    graph = IntentMemoryGraph(storage)

    homepage = Intent(id="homepage", description="导航到首页", operations=[...])
    coffee = Intent(id="coffee", description="进入咖啡分类", operations=[...])
    book = Intent(id="book", description="进入图书分类", operations=[...])

    graph.add_intent(homepage)
    graph.add_intent(coffee)
    graph.add_intent(book)

    # 创建分支结构
    graph.add_edge(homepage.id, coffee.id)
    graph.add_edge(homepage.id, book.id)

    # User query 指定 coffee 分支
    metaflow = await generator.generate(
        graph,
        "收集商品信息",
        "收集咖啡商品信息"
    )

    # 验证只包含 coffee 路径
    intent_ids = [node.intent_id for node in metaflow.nodes if hasattr(node, 'intent_id')]
    assert homepage.id in intent_ids
    assert coffee.id in intent_ids
    assert book.id not in intent_ids  # book 分支应该被过滤
```

---

## 7. MVP 范围

### 包含功能

1. ✅ 基于 LLM 的 MetaFlow 生成
2. ✅ **从图结构输入（nodes + edges）**
3. ✅ **基于 User Query 的路径选择**（过滤无关分支）
4. ✅ 循环检测和生成
5. ✅ 隐式节点推断
6. ✅ 数据流连接
7. ✅ YAML 解析和验证

### 不包含功能

1. ❌ 规则based 推断
2. ❌ 重试机制（由上层处理）
3. ❌ 结果缓存
4. ❌ 多种生成策略

---

## 8. 性能考虑

### 8.1 时间复杂度

- **Prompt 构建**: O(N)，N = Intent 数量
- **LLM 调用**: O(T)，T = LLM 响应时间（通常 5-15 秒）
- **YAML 解析**: O(M)，M = YAML 大小

### 8.2 优化方向（未来）

1. **Prompt 优化**: 减少 Prompt 大小，加快 LLM 响应
2. **缓存**: 相似 Intent 列表的结果缓存
3. **流式输出**: 使用 LLM 流式 API

---

## 9. 参考资料

- Intent 规范: `intent_specification.md`
- MetaFlow 规范: `metaflow_specification.md`
- 讨论记录: `discussions/04_intent_architecture_decisions.md`
- IntentExtractor 设计: `intent_extractor_design.md`
