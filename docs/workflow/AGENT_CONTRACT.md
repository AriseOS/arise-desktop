# Agent Input/Output Contract

本文档定义了所有 Agent 的输入输出契约，是 workflow 生成和执行的统一规范。

## 核心原则

1. **Output 统一用 `result` key** - 所有 Agent 的输出数据都放在 `AgentOutput.data["result"]` 中
2. **类型明确** - 每个 Agent 的返回类型固定，不会变化
3. **Workflow outputs 简化** - 只需写 `result: 变量名`

## Agent 契约总览

| Agent | 返回类型 | 说明 |
|-------|---------|------|
| scraper_agent | `List[Dict]` | 提取的数据列表 |
| text_agent | `Dict` | LLM 返回的 JSON 对象 |
| variable | `Any` | 操作结果（类型取决于操作） |
| browser_agent | `None` | 无数据输出 |
| storage_agent | `Dict` | 操作结果 |

---

## scraper_agent

### 功能
从当前页面提取结构化数据。不负责导航，需先用 browser_agent 导航到目标页面。

### 输入

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `extraction_method` | `"script" \| "llm"` | 是 | 推荐使用 `"script"` |
| `dom_scope` | `"full" \| "partial"` | 否 | 列表用 `full`，单项用 `partial` |
| `data_requirements.user_description` | `string` | 是 | 描述要提取什么 |
| `data_requirements.output_format` | `Dict[str, str]` | 是 | `{字段名: 字段描述}` |
| `data_requirements.xpath_hints` | `Dict[str, str]` | 否 | XPath 提示 |
| `max_items` | `int` | 否 | 最大提取数量 |

### 输出

| Key | 类型 | 说明 |
|-----|------|------|
| `result` | `List[Dict]` | 提取的数据列表，字段由 `output_format` 定义 |

### 示例

```yaml
- id: extract-products
  agent_type: scraper_agent
  inputs:
    extraction_method: script
    dom_scope: full
    data_requirements:
      user_description: "提取产品名称和价格"
      output_format:
        name: "产品名称"
        price: "价格"
  outputs:
    result: products    # context.variables["products"] = List[Dict]
```

---

## text_agent

### 功能
使用 LLM 生成或处理文本。

### 输入

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `instruction` | `string` | 是 | 任务指令 |
| `<任意字段>` | `any` | 否 | 传入 LLM 的数据 |

### 输出

| Key | 类型 | 说明 |
|-----|------|------|
| `result` | `Dict` | LLM 返回的 JSON，字段由 `outputs` 中的 key 定义 |

**注意**：`outputs` 中定义的 key（除了 `result`）会作为 `expected_outputs` 传给 LLM，LLM 返回的 JSON 会包含这些字段。

### 示例

```yaml
- id: summarize
  agent_type: text_agent
  inputs:
    instruction: "总结产品列表，给出推荐"
    products: "{{products}}"
  outputs:
    result: summary     # context.variables["summary"] = Dict
```

如果需要 LLM 返回特定字段结构：

```yaml
- id: analyze
  agent_type: text_agent
  inputs:
    instruction: "分析产品并给出评分"
    products: "{{products}}"
  outputs:
    result: analysis    # LLM 返回完整 JSON 对象
```

---

## variable

### 功能
变量操作，不使用 LLM。支持 4 种操作：`set`, `filter`, `slice`, `extend`。

### 操作类型

#### set - 设置/组合变量

```yaml
- id: combine-data
  agent_type: variable
  inputs:
    operation: set
    data:
      url: "{{product.url}}"
      name: "{{details.0.name}}"
      price: "{{details.0.price}}"
  outputs:
    result: complete_product    # Dict
```

#### filter - 过滤列表

```yaml
- id: filter-products
  agent_type: variable
  inputs:
    operation: filter
    data: "{{products}}"
    field: "category"
    contains: "electronics"     # 或 equals: "exact_value"
  outputs:
    result: filtered            # List[Dict]
```

#### slice - 切片列表

```yaml
- id: get-first-10
  agent_type: variable
  inputs:
    operation: slice
    data: "{{products}}"
    start: 0
    end: 10
  outputs:
    result: first_10            # List[Dict]
```

#### extend - 扩展列表

将新元素（单个或列表）合并到列表末尾。

```yaml
# 添加单个元素
- id: extend-one
  agent_type: variable
  inputs:
    operation: extend
    data: "{{all_items}}"
    items: "{{new_item}}"       # 单个元素会被加入列表
  outputs:
    result: updated_items       # List

# 合并两个列表
- id: extend-list
  agent_type: variable
  inputs:
    operation: extend
    data: "{{list_a}}"
    items: "{{list_b}}"         # list_b 的元素会逐个加入 list_a
  outputs:
    result: merged_list         # List
```

**注意**：使用 `items`（复数）而非 `item`，表示可以是单个元素或列表。

### 输出

| Key | 类型 | 说明 |
|-----|------|------|
| `result` | `Any` | 操作结果，类型取决于操作 |

---

## browser_agent

### 功能
浏览器操作：导航、点击、填写、滚动。

### 输入

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `target_url` | `string` | 否 | 目标 URL |
| `interaction_steps` | `List[Dict]` | 否 | 交互步骤 |

### 输出

**browser_agent 通常不需要输出数据**。如果需要，可以获取页面信息。

| Key | 类型 | 说明 |
|-----|------|------|
| `result` | `Dict \| None` | `{url, title}` 或 null |

### 示例

```yaml
- id: navigate
  agent_type: browser_agent
  inputs:
    target_url: "https://example.com"
  outputs: null                 # 不需要输出
```

---

## storage_agent

### 功能
数据持久化存储。支持 `store`, `query`, `export` 操作。

### 操作类型

#### store - 存储数据

```yaml
- id: save-products
  agent_type: storage_agent
  inputs:
    operation: store
    collection: products
    data: "{{products}}"
    upsert_key: url             # 可选，用于去重更新
  outputs:
    result: store_result        # {count: N}
```

#### query - 查询数据

```yaml
- id: query-products
  agent_type: storage_agent
  inputs:
    operation: query
    collection: products
    filters:
      category: "electronics"
    limit: 10
  outputs:
    result: query_result        # {data: List[Dict], count: N}
```

### 输出

| Key | 类型 | 说明 |
|-----|------|------|
| `result` | `Dict` | `{count: N}` 或 `{data: [...], count: N}` |

---

## 变量引用规则

### 基本引用

```yaml
"{{variable}}"                  # 引用整个变量，保留原类型
```

### 嵌套访问

```yaml
"{{product.name}}"              # 访问 Dict 字段
"{{products.0.name}}"           # 访问列表第一个元素的字段
"{{products.length}}"           # 获取列表长度
```

### 字符串模板

```yaml
"共 {{products.length}} 个产品" # 转换为字符串
```

---

## Workflow outputs 与变量引用

### outputs 格式

```yaml
outputs:
  result: variable_name         # Agent.data["result"] → context.variables["variable_name"]
```

### 无输出

```yaml
outputs: null                   # 或省略 outputs
```

### outputs 到 inputs 的数据流

```yaml
# Step 1: scraper_agent 提取数据
- id: extract
  agent_type: scraper_agent
  inputs:
    data_requirements:
      user_description: "提取产品列表"
      output_format:
        name: "产品名称"
        price: "价格"
  outputs:
    result: products            # Agent 返回 List[Dict]
                                # → context.variables["products"] = [{name: "A", price: 10}, ...]

# Step 2: 在后续步骤的 inputs 中引用
- id: store
  agent_type: storage_agent
  inputs:
    operation: store
    collection: products
    data: "{{products}}"        # 引用上一步的输出变量
  outputs:
    result: store_result

# Step 3: 访问嵌套字段
- id: process
  agent_type: text_agent
  inputs:
    instruction: "总结产品"
    first_product: "{{products.0}}"        # 第一个产品对象
    first_name: "{{products.0.name}}"      # 第一个产品的名称
    count: "{{products.length}}"           # 产品数量
  outputs:
    result: summary
```

**关键点**：
1. `outputs: {result: X}` 中的 `X` 是变量名，存入 `context.variables["X"]`
2. 后续步骤用 `"{{X}}"` 引用这个变量
3. 支持嵌套访问：`"{{X.field}}"`, `"{{X.0.field}}"`, `"{{X.length}}"`

---

## 完整 Workflow 示例

```yaml
apiVersion: ami.io/v2
name: extract-products
description: "提取产品信息并存储"

input: url

steps:
  # 1. 导航到页面
  - id: navigate
    agent_type: browser_agent
    inputs:
      target_url: "{{url}}"
    outputs: null

  # 2. 提取产品列表
  - id: extract
    agent_type: scraper_agent
    inputs:
      extraction_method: script
      dom_scope: full
      data_requirements:
        user_description: "提取产品信息"
        output_format:
          name: "产品名称"
          price: "价格"
          url: "产品链接"
    outputs:
      result: products

  # 3. 过滤有效产品
  - id: filter
    agent_type: variable
    inputs:
      operation: filter
      data: "{{products}}"
      field: "price"
      contains: "$"
    outputs:
      result: valid_products

  # 4. 存储到数据库
  - id: store
    agent_type: storage_agent
    inputs:
      operation: store
      collection: products
      data: "{{valid_products}}"
    outputs:
      result: store_result

  # 5. 生成总结
  - id: summarize
    agent_type: text_agent
    inputs:
      instruction: "总结提取的产品信息"
      products: "{{valid_products}}"
      count: "{{store_result.count}}"
    outputs:
      result: summary
```
