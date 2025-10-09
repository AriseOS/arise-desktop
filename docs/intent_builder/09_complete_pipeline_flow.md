# Intent Builder 完整流程文档

**版本**: v2.0
**日期**: 2025-10-09
**状态**: 已确定

---

## 1. 概述

### 1.1 系统目标

将用户的浏览器操作记录转换为可执行的 Workflow。

```
输入: User Operations JSON + Task Description
输出: Workflow YAML (可由 BaseAgent 执行)
```

### 1.2 完整数据流

```
User Operations JSON + Task Description
  ↓
[IntentExtractor]
  ↓
Intent List
  ↓
[IntentMemoryGraph]
  ↓
(存储和检索)
  ↓
User Query
  ↓
[IntentRetriever]
  ↓
Retrieved Intent List
  ↓
[MetaFlowGenerator]
  ↓
MetaFlow YAML
  ↓
[WorkflowGenerator]
  ↓
Workflow YAML
  ↓
[BaseAgent]
  ↓
Execution Result
```

---

## 2. 核心组件

### 2.1 组件职责

| 组件 | 输入 | 输出 | 职责 |
|-----|------|------|------|
| **IntentExtractor** | User Operations JSON + Task Description | Intent List | 提取语义化的意图 |
| **IntentMemoryGraph** | Intent List | Stored Graph | 存储和管理意图 |
| **IntentRetriever** | User Query + Graph | Retrieved Intent List | 检索相关意图 |
| **MetaFlowGenerator** | Intent List + User Query | MetaFlow YAML | 生成中间表示 |
| **WorkflowGenerator** | MetaFlow YAML | Workflow YAML | 生成可执行工作流 |

### 2.2 数据结构

```python
# 原始数据
UserOperationsJSON = Dict[str, Any]

# 核心数据结构
Intent = {
    "id": str,
    "description": str,
    "operations": List[Operation]
}

IntentMemoryGraph = {
    "intents": Dict[str, Intent],
    "edges": List[Tuple[str, str]]
}

MetaFlow = {
    "version": str,
    "task_description": str,
    "nodes": List[Union[MetaFlowNode, LoopNode]]
}

Workflow = str  # YAML format
```

---

## 3. Demo 1: 学习流程（User Operations → Intent Graph）

### 3.1 场景描述

**目标**: 从用户操作记录中学习意图，存储到 Graph

**输入文件**: `browser-user-operation-tracker-example.json`

**任务描述**: "用户希望收集热门的第一页的咖啡的商品的相关信息"

### 3.2 执行步骤

#### Step 1: 加载数据

```python
import json

# 加载用户操作 JSON
with open('browser-user-operation-tracker-example.json') as f:
    data = json.load(f)

operations = data['operations']  # List[Dict]
task_description = "用户希望收集热门的第一页的咖啡的商品的相关信息"

print(f"Loaded {len(operations)} operations")
```

**输出**:
```
Loaded 16 operations
```

---

#### Step 2: 初始化组件

```python
from src.common.llm import AnthropicProvider
from src.intent_builder.extractors import IntentExtractor
from src.intent_builder.memory import IntentMemoryGraph

# 初始化 LLM
llm = AnthropicProvider(
    api_key=os.getenv('ANTHROPIC_API_KEY')
)

# 初始化提取器
extractor = IntentExtractor(llm)

# 初始化 Graph
graph = IntentMemoryGraph()
```

---

#### Step 3: 提取 Intent

```python
print("\n=== Step 1: 提取意图 ===")

# 调用 IntentExtractor
intents = await extractor.extract_intents(
    operations=operations,
    task_description=task_description
)

print(f"✅ 提取到 {len(intents)} 个意图:")
for i, intent in enumerate(intents, 1):
    print(f"  {i}. [{intent.id}] {intent.description}")
    print(f"     Operations: {len(intent.operations)} steps")
```

**输出示例**:
```
=== Step 1: 提取意图 ===
✅ 提取到 4 个意图:
  1. [intent_a3f5b2c1] 导航到 Allegro 电商网站首页
     Operations: 1 steps
  2. [intent_b7e4c8d2] 通过菜单导航进入咖啡产品分类页面
     Operations: 3 steps
  3. [intent_c5a9e3f1] 从咖啡分类页面点击第一个商品查看详情
     Operations: 2 steps
  4. [intent_d8b2f4e6] 访问产品详情页并提取产品标题、价格、销量信息
     Operations: 10 steps
```

**内部流程**:
1. URL 切分: 16 operations → 3 segments
2. LLM 提取: 3 segments → 4 intents
3. 生成 Intent 对象

---

#### Step 4: 存入 Graph

```python
print("\n=== Step 2: 存入 Intent Graph ===")

# 添加 Intent 到 Graph
for i, intent in enumerate(intents):
    graph.add_intent(intent)

    # 添加边（时间顺序）
    if i > 0:
        graph.add_edge(intents[i-1].id, intent.id)

print(f"✅ Graph 包含 {len(graph.intents)} 个节点，{len(graph.edges)} 条边")
```

**输出**:
```
=== Step 2: 存入 Intent Graph ===
✅ Graph 包含 4 个节点，3 条边
```

**Graph 结构**:
```
intent_a3f5b2c1 → intent_b7e4c8d2 → intent_c5a9e3f1 → intent_d8b2f4e6
```

---

#### Step 5: 持久化

```python
print("\n=== Step 3: 保存 Intent Graph ===")

# 保存到文件
graph.save('intent_graph.json')

print("✅ Graph 已保存到 intent_graph.json")
```

**输出文件** (`intent_graph.json`):
```json
{
  "intents": {
    "intent_a3f5b2c1": {
      "id": "intent_a3f5b2c1",
      "description": "导航到 Allegro 电商网站首页",
      "operations": [...],
      "created_at": "2025-10-09T14:30:00",
      "source_session_id": "session_demo_001"
    },
    ...
  },
  "edges": [
    ["intent_a3f5b2c1", "intent_b7e4c8d2"],
    ["intent_b7e4c8d2", "intent_c5a9e3f1"],
    ["intent_c5a9e3f1", "intent_d8b2f4e6"]
  ],
  "metadata": {
    "created_at": "2025-10-09T14:30:00",
    "last_updated": "2025-10-09T14:30:05",
    "version": "2.0"
  }
}
```

---

### 3.3 Demo 1 完整代码

```python
async def demo1_learn_from_operations():
    """Demo 1: 从用户操作学习意图"""

    print("=" * 60)
    print("Demo 1: 从用户操作学习意图")
    print("=" * 60)

    # 1. 加载数据
    with open('tests/sample_data/browser-user-operation-tracker-example.json') as f:
        data = json.load(f)

    operations = data['operations']
    task_description = "用户希望收集热门的第一页的咖啡的商品的相关信息"

    print(f"\n📥 加载了 {len(operations)} 个操作")

    # 2. 初始化组件
    llm = AnthropicProvider()
    extractor = IntentExtractor(llm)
    graph = IntentMemoryGraph()

    # 3. 提取 Intent
    print("\n🔍 提取意图...")
    intents = await extractor.extract_intents(operations, task_description)

    print(f"\n✅ 提取到 {len(intents)} 个意图:")
    for i, intent in enumerate(intents, 1):
        print(f"  {i}. {intent.description}")

    # 4. 存入 Graph
    print("\n💾 存入 Intent Graph...")
    for i, intent in enumerate(intents):
        graph.add_intent(intent)
        if i > 0:
            graph.add_edge(intents[i-1].id, intent.id)

    print(f"✅ Graph: {len(graph.intents)} 节点, {len(graph.edges)} 边")

    # 5. 保存
    graph.save('intent_graph.json')
    print("\n✅ 已保存到 intent_graph.json")

    print("\n" + "=" * 60)
    print("Demo 1 完成！")
    print("=" * 60)
```

---

## 4. Demo 2: 生成流程（Intent Graph → Workflow）

### 4.1 场景描述

**目标**: 从 Intent Graph 生成可执行的 Workflow

**输入**:
- Intent Graph (`intent_graph.json`)
- User Query ("收集所有咖啡商品信息")

**输出**: Workflow YAML

### 4.2 执行步骤

#### Step 1: 加载 Graph

```python
print("\n=== Step 1: 加载 Intent Graph ===")

# 加载已保存的 Graph
graph = IntentMemoryGraph.load('intent_graph.json')

print(f"✅ 加载了 {len(graph.intents)} 个意图")
```

**输出**:
```
=== Step 1: 加载 Intent Graph ===
✅ 加载了 4 个意图
```

---

#### Step 2: 检索相关 Intent

```python
print("\n=== Step 2: 检索相关意图 ===")

# 用户查询
user_query = "我想爬取图书分类的商品信息"

# 初始化检索器
embedding_service = OpenAIEmbeddingService()
retriever = IntentRetriever(graph, embedding_service)

# 检索
retrieved_intents = await retriever.retrieve(user_query, limit=5)

print(f"✅ 检索到 {len(retrieved_intents)} 个相关意图:")
for i, intent in enumerate(retrieved_intents, 1):
    print(f"  {i}. {intent.description}")
```

**输出示例**:
```
=== Step 2: 检索相关意图 ===
✅ 检索到 4 个相关意图:
  1. 导航到 Allegro 电商网站首页
  2. 通过菜单导航进入咖啡产品分类页面
  3. 从咖啡分类页面点击第一个商品查看详情
  4. 访问产品详情页并提取产品标题、价格、销量信息
```

**注**: MVP 可以简化，直接使用所有 Intent（不做检索）

---

#### Step 3: 生成 MetaFlow

```python
print("\n=== Step 3: 生成 MetaFlow ===")

# 初始化生成器
metaflow_generator = MetaFlowGenerator(llm)

# 生成
task_description = "爬取图书分类的商品信息"
metaflow = await metaflow_generator.generate(
    intents=retrieved_intents,
    task_description=task_description,
    user_query=user_query
)

print(f"✅ MetaFlow 包含 {len(metaflow.nodes)} 个节点")

# 检查是否有循环
loop_nodes = [n for n in metaflow.nodes if isinstance(n, LoopNode)]
print(f"   循环节点: {len(loop_nodes)}")

# 保存
metaflow_yaml = metaflow.to_yaml()
with open('generated_metaflow.yaml', 'w', encoding='utf-8') as f:
    f.write(metaflow_yaml)

print("✅ 已保存到 generated_metaflow.yaml")
```

**输出**:
```
=== Step 3: 生成 MetaFlow ===
✅ MetaFlow 包含 5 个节点
   循环节点: 1
✅ 已保存到 generated_metaflow.yaml
```

**生成的 MetaFlow** (`generated_metaflow.yaml`):
```yaml
version: "1.0"
task_description: "爬取图书分类的商品信息"

nodes:
  - id: node_1
    intent_id: intent_a3f5b2c1
    intent_name: "NavigateToAllegro"
    intent_description: "导航到 Allegro 电商网站首页"
    operations: [...]

  - id: node_2
    intent_id: intent_b7e4c8d2
    intent_name: "EnterCategory"
    intent_description: "通过菜单导航进入分类页面"
    operations: [...]

  - id: node_3
    intent_id: implicit_extract_list
    intent_name: "ExtractProductList"
    intent_description: "提取商品列表（推断节点）"
    operations:
      - type: extract
        target: "product_urls"
        element: {xpath: "<PLACEHOLDER>", tagName: "A"}
        value: []
    outputs:
      product_urls: "product_urls"

  - id: node_4
    type: loop
    description: "遍历商品列表，提取详细信息"
    source: "{{product_urls}}"
    item_var: "current_product"
    children:
      - id: node_4_1
        intent_id: intent_d8b2f4e6
        intent_name: "ExtractProductInfo"
        intent_description: "提取产品详细信息"
        operations: [...]
        inputs:
          product_url: "{{current_product.url}}"
        outputs:
          product_info: "product_info"
```

**关键点**:
- ✅ 检测到循环关键词（"所有"）
- ✅ 插入了隐式节点（ExtractProductList）
- ✅ 推断了数据流（product_urls → loop.source）

---

#### Step 4: 生成 Workflow

```python
print("\n=== Step 4: 生成 Workflow ===")

# 初始化 WorkflowGenerator（已有）
workflow_generator = WorkflowGenerator()

# 生成
workflow_yaml = await workflow_generator.generate(metaflow)

print(f"✅ Workflow 生成成功")

# 保存
with open('generated_workflow.yaml', 'w', encoding='utf-8') as f:
    f.write(workflow_yaml)

print("✅ 已保存到 generated_workflow.yaml")
```

**输出**:
```
=== Step 4: 生成 Workflow ===
✅ Workflow 生成成功
✅ 已保存到 generated_workflow.yaml
```

**生成的 Workflow** (`generated_workflow.yaml`):
```yaml
apiVersion: "agentcrafter.io/v1"
kind: "Workflow"

metadata:
  name: "book-collection-workflow"
  description: "爬取图书分类的商品信息"
  version: "1.0.0"

inputs:
  max_products:
    type: "integer"
    description: "最多爬取的商品数量"
    default: 10

outputs:
  product_details:
    type: "array"
    description: "商品详细信息"
  final_response:
    type: "string"
    description: "完成消息"

config:
  max_execution_time: 1800
  enable_parallel: false

steps:
  - id: "init-vars"
    name: "初始化变量"
    agent_type: "variable"
    agent_instruction: "Initialize collection variables"
    inputs:
      operation: "set"
      data:
        all_product_urls: []
        all_product_details: []
    outputs:
      all_product_urls: "all_product_urls"
      all_product_details: "all_product_details"
    timeout: 10

  - id: "navigate-to-site"
    name: "导航到网站"
    agent_type: "tool_agent"
    agent_instruction: "导航到 Allegro 电商网站首页"
    inputs:
      task_description: "Navigate to Allegro homepage"
      allowed_tools: ["browser_use"]
    timeout: 30

  - id: "enter-category"
    name: "进入分类"
    agent_type: "tool_agent"
    agent_instruction: "通过菜单导航进入图书分类页面"
    inputs:
      task_description: "Enter book category"
      allowed_tools: ["browser_use"]
    timeout: 30

  - id: "extract-product-list"
    name: "提取商品列表"
    agent_type: "scraper_agent"
    agent_instruction: "从分类页面提取所有商品的URL"
    inputs:
      extraction_method: "script"
      dom_scope: "full"
      data_requirements:
        user_description: "提取商品URL列表"
        output_format:
          url: "商品URL"
        sample_data:
          - url: "https://allegro.pl/oferta/book-123"
    outputs:
      extracted_data: "product_urls"
    timeout: 60

  - id: "save-urls"
    name: "保存URL列表"
    agent_type: "variable"
    agent_instruction: "保存商品URL列表"
    inputs:
      operation: "set"
      data:
        all_product_urls: "{{product_urls}}"
    outputs:
      all_product_urls: "all_product_urls"
    timeout: 10

  - id: "collect-product-details"
    name: "收集商品详情"
    agent_type: "foreach"
    description: "遍历商品列表，提取详细信息"
    source: "{{all_product_urls}}"
    item_var: "current_product"
    index_var: "product_index"
    max_iterations: 10
    loop_timeout: 900
    steps:
      - id: "scrape-product"
        name: "爬取商品详情"
        agent_type: "scraper_agent"
        agent_instruction: "访问商品页面并提取详细信息"
        inputs:
          extraction_method: "llm"
          target_path: "{{current_product.url}}"
          data_requirements:
            user_description: "提取商品标题、价格、描述"
            output_format:
              title: "商品标题"
              price: "商品价格"
              description: "商品描述"
        outputs:
          extracted_data: "product_info"
        timeout: 45

      - id: "append-product"
        name: "添加到列表"
        agent_type: "variable"
        agent_instruction: "将商品信息添加到列表"
        inputs:
          operation: "append"
          source: "{{all_product_details}}"
          data: "{{product_info}}"
        outputs:
          result: "all_product_details"
        timeout: 10

      - id: "store-product"
        name: "存储到数据库"
        agent_type: "storage_agent"
        agent_instruction: "持久化商品信息"
        inputs:
          operation: "store"
          collection: "books"
          data: "{{product_info}}"
        outputs:
          message: "store_message"
        timeout: 10

  - id: "prepare-output"
    name: "准备输出"
    agent_type: "variable"
    agent_instruction: "组织最终结果"
    inputs:
      operation: "set"
      data:
        product_details: "{{all_product_details}}"
        final_response: "Successfully collected {{product_index}} products"
    outputs:
      product_details: "product_details"
      final_response: "final_response"
    timeout: 10
```

**关键点**:
- ✅ LLM 推断了合适的 Agent 类型
- ✅ LLM 连接了数据流
- ✅ LLM 生成了完整的 foreach 结构
- ✅ 包含了必要的变量管理步骤

---

#### Step 5: 执行 Workflow（可选）

```python
print("\n=== Step 5: 执行 Workflow (可选) ===")

# 初始化 BaseAgent
from src.base_app.base_app.base_agent.core.base_agent import BaseAgent

agent = BaseAgent(
    config_service=config,
    user_id="demo_user"
)

# 执行
result = await agent.run_workflow_from_file('generated_workflow.yaml')

print(f"✅ Workflow 执行完成")
print(f"   结果: {result.get('final_response')}")
```

---

### 4.3 Demo 2 完整代码

```python
async def demo2_generate_workflow():
    """Demo 2: 从 Intent Graph 生成 Workflow"""

    print("=" * 60)
    print("Demo 2: 从 Intent Graph 生成 Workflow")
    print("=" * 60)

    # 1. 加载 Graph
    print("\n📂 加载 Intent Graph...")
    graph = IntentMemoryGraph.load('intent_graph.json')
    print(f"✅ 加载了 {len(graph.intents)} 个意图")

    # 2. 用户查询
    user_query = "我想爬取图书分类的商品信息"
    task_description = "爬取图书分类的商品信息"

    print(f"\n❓ 用户查询: {user_query}")

    # 3. 检索 Intent（MVP 可简化：直接使用所有 Intent）
    retrieved_intents = list(graph.intents.values())
    print(f"\n✅ 使用 {len(retrieved_intents)} 个意图")

    # 4. 生成 MetaFlow
    print("\n🔧 生成 MetaFlow...")
    llm = AnthropicProvider()
    metaflow_generator = MetaFlowGenerator(llm)

    metaflow = await metaflow_generator.generate(
        intents=retrieved_intents,
        task_description=task_description,
        user_query=user_query
    )

    print(f"✅ MetaFlow: {len(metaflow.nodes)} 节点")

    # 保存
    with open('generated_metaflow.yaml', 'w', encoding='utf-8') as f:
        f.write(metaflow.to_yaml())
    print("   保存到 generated_metaflow.yaml")

    # 5. 生成 Workflow
    print("\n🔧 生成 Workflow...")
    workflow_generator = WorkflowGenerator()
    workflow_yaml = await workflow_generator.generate(metaflow)

    # 保存
    with open('generated_workflow.yaml', 'w', encoding='utf-8') as f:
        f.write(workflow_yaml)
    print("✅ 保存到 generated_workflow.yaml")

    print("\n" + "=" * 60)
    print("Demo 2 完成！")
    print("可以使用 BaseAgent 执行 generated_workflow.yaml")
    print("=" * 60)
```

---

## 5. 端到端流程（Demo 1 + Demo 2）

### 5.1 完整代码

```python
async def demo_full_pipeline():
    """完整流程: User Operations → Workflow"""

    print("=" * 70)
    print("完整流程: User Operations → Workflow")
    print("=" * 70)

    # ===== Part 1: 学习流程 =====
    print("\n" + "=" * 70)
    print("Part 1: 学习流程（User Operations → Intent Graph）")
    print("=" * 70)

    # 加载数据
    with open('tests/sample_data/browser-user-operation-tracker-example.json') as f:
        data = json.load(f)

    operations = data['operations']
    task_description = "用户希望收集咖啡商品信息"

    # 初始化
    llm = AnthropicProvider()
    extractor = IntentExtractor(llm)
    graph = IntentMemoryGraph()

    # 提取 Intent
    print("\n[1/3] 提取意图...")
    intents = await extractor.extract_intents(operations, task_description)
    print(f"      ✅ 提取到 {len(intents)} 个意图")

    # 存入 Graph
    print("\n[2/3] 存入 Graph...")
    for i, intent in enumerate(intents):
        graph.add_intent(intent)
        if i > 0:
            graph.add_edge(intents[i-1].id, intent.id)
    print(f"      ✅ Graph: {len(graph.intents)} 节点, {len(graph.edges)} 边")

    # 保存
    print("\n[3/3] 保存 Graph...")
    graph.save('intent_graph.json')
    print("      ✅ 已保存")

    # ===== Part 2: 生成流程 =====
    print("\n" + "=" * 70)
    print("Part 2: 生成流程（Intent Graph → Workflow）")
    print("=" * 70)

    user_query = "收集所有咖啡商品信息"

    # 生成 MetaFlow
    print("\n[1/2] 生成 MetaFlow...")
    metaflow_generator = MetaFlowGenerator(llm)
    metaflow = await metaflow_generator.generate(
        intents=list(graph.intents.values()),
        task_description=task_description,
        user_query=user_query
    )
    print(f"      ✅ {len(metaflow.nodes)} 节点")

    with open('generated_metaflow.yaml', 'w', encoding='utf-8') as f:
        f.write(metaflow.to_yaml())

    # 生成 Workflow
    print("\n[2/2] 生成 Workflow...")
    workflow_generator = WorkflowGenerator()
    workflow_yaml = await workflow_generator.generate(metaflow)
    print("      ✅ Workflow 生成成功")

    with open('generated_workflow.yaml', 'w', encoding='utf-8') as f:
        f.write(workflow_yaml)

    # ===== 完成 =====
    print("\n" + "=" * 70)
    print("✅ 完整流程完成！")
    print("=" * 70)
    print("\n生成的文件:")
    print("  - intent_graph.json")
    print("  - generated_metaflow.yaml")
    print("  - generated_workflow.yaml")
    print("\n下一步:")
    print("  运行: baseapp run-workflow generated_workflow.yaml")


if __name__ == "__main__":
    import asyncio
    asyncio.run(demo_full_pipeline())
```

---

## 6. 数据流总结

### 6.1 学习阶段

```
browser-user-operation-tracker-example.json (16 ops)
  ↓ URL 切分
3 Segments
  ↓ LLM 提取 (IntentExtractor)
4 Intents
  ↓ 存储
intent_graph.json
```

### 6.2 生成阶段

```
用户查询: "收集所有咖啡商品信息"
  ↓ 检索/选择
4 Intents (从 Graph)
  ↓ LLM 组装 (MetaFlowGenerator)
MetaFlow (5 nodes, 包含隐式节点和循环)
  ↓ LLM 转换 (WorkflowGenerator)
Workflow (10+ steps, 可执行)
```

---

## 7. 关键设计点

### 7.1 Intent 切分粒度

- **规则**: URL 变化触发切分
- **LLM**: 进一步细分为多个 Intent
- **结果**: 粗粒度，一个明确的子目标 = 一个 Intent

### 7.2 数据流推断

- **隐式节点**: LLM 推断需要的 ExtractList 节点
- **变量连接**: LLM 推断 outputs → inputs 的引用
- **循环变量**: LLM 推断循环变量的字段引用

### 7.3 LLM 使用边界

| 任务 | 方法 |
|-----|------|
| URL 切分 | 规则 |
| Intent 描述生成 | LLM |
| Intent 切分（segment 内） | LLM |
| MetaFlow 组装 | LLM |
| 隐式节点生成 | LLM |
| 数据流连接 | LLM |
| Workflow 生成 | LLM |

**原则**: 规则处理结构化问题，LLM 处理语义问题

---

## 8. 测试和验证

### 8.1 单元测试

```python
# 测试 IntentExtractor
@pytest.mark.asyncio
async def test_intent_extractor():
    extractor = IntentExtractor(llm)
    intents = await extractor.extract_intents(ops, "task")
    assert len(intents) > 0

# 测试 IntentMemoryGraph
def test_intent_memory_graph():
    graph = IntentMemoryGraph()
    graph.add_intent(intent1)
    assert len(graph.intents) == 1

# 测试 MetaFlowGenerator
@pytest.mark.asyncio
async def test_metaflow_generator():
    generator = MetaFlowGenerator(llm)
    metaflow = await generator.generate(intents, "task", "query")
    assert len(metaflow.nodes) > 0
```

### 8.2 集成测试

```python
@pytest.mark.asyncio
async def test_full_pipeline():
    """测试完整流程"""

    # 1. 提取 Intent
    intents = await extractor.extract_intents(operations, task_desc)
    assert len(intents) > 0

    # 2. 存入 Graph
    for intent in intents:
        graph.add_intent(intent)

    # 3. 生成 MetaFlow
    metaflow = await metaflow_generator.generate(intents, task_desc, query)
    assert len(metaflow.nodes) >= len(intents)

    # 4. 生成 Workflow
    workflow_yaml = await workflow_generator.generate(metaflow)
    assert "apiVersion" in workflow_yaml
    assert "steps:" in workflow_yaml

    # 5. 验证 Workflow 可解析
    workflow = yaml.safe_load(workflow_yaml)
    assert workflow['kind'] == 'Workflow'
```

---

## 9. 性能考虑

### 9.1 时间估算

| 阶段 | 操作 | 时间 |
|-----|------|------|
| 加载数据 | 读文件 | < 1s |
| URL 切分 | 规则处理 | < 1s |
| Intent 提取 | LLM (3次) | ~15-30s |
| 存入 Graph | 内存操作 | < 1s |
| 保存 Graph | 写文件 | < 1s |
| 生成 MetaFlow | LLM (1次) | ~10-15s |
| 生成 Workflow | LLM (1次) | ~10-15s |
| **总计** | | **~40-60s** |

### 9.2 优化方向

1. **并行化**: 多个 segment 并行调用 LLM
2. **缓存**: 相似 Intent 的结果缓存
3. **批处理**: 减少 LLM 调用次数

---

## 10. 参考资料

- 讨论记录: `discussions/04_intent_architecture_decisions.md`
- Intent 规范: `intent_specification.md`
- IntentExtractor 设计: `intent_extractor_design.md`
- MetaFlowGenerator 设计: `metaflow_generator_design.md`
- WorkflowGenerator 设计: `workflow_generator_design.md`
