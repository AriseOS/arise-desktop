# MetaFlow 规范文档

**版本**: v1.0
**日期**: 2025-10-07
**状态**: 设计阶段

---

## 1. 概述

MetaFlow（元工作流）是意图的组合和编排，描述完成任务的执行逻辑。

### 1.1 设计目标

- **人类可读**: 用户可以理解和审查
- **可执行**: 包含足够信息供 LLM 转换为 YAML Workflow
- **明确数据流**: 显式声明输入输出和变量引用

### 1.2 职责范围

- ✅ 意图的执行顺序
- ✅ 控制流（循环）
- ✅ 数据流（输入输出、变量引用）
- ✅ 每个意图的完整信息（包括操作步骤）
- ❌ 具体的 Agent 实现细节（由 LLM 推断）
- ❌ 并行执行（MVP 不支持）

---

## 2. 顶层结构

```yaml
version: "1.0"                    # MetaFlow 格式版本
task_description: "任务描述"       # 用户的自然语言任务描述

nodes:                            # 节点列表（按执行顺序）
  - <普通节点>
  - <循环节点>
```

---

## 3. 节点类型

### 3.1 普通节点

```yaml
- id: <node_id>                           # 节点唯一标识
  intent_id: <intent_id>                  # 关联的意图 ID（来自记忆系统）
  intent_name: <intent_name>              # 意图名称（简短标识）
  intent_description: <description>       # 意图描述（人类可读）

  operations:                             # 操作步骤列表
    - <operation>

  inputs:                                 # 可选：输入参数
    <key>: <value_or_variable_ref>

  outputs:                                # 可选：输出声明
    <output_key>: <variable_name>
```

**字段说明**：

| 字段 | 必需 | 类型 | 说明 |
|------|------|------|------|
| `id` | 是 | string | 节点唯一标识 |
| `intent_id` | 是 | string | 意图在记忆系统中的 ID |
| `intent_name` | 是 | string | 意图名称（类似函数名） |
| `intent_description` | 是 | string | 意图的详细描述 |
| `operations` | 是 | array | 操作步骤列表 |
| `inputs` | 否 | object | 输入参数，支持变量引用 |
| `outputs` | 否 | object | 输出声明，key 是输出字段，value 是变量名 |

### 3.2 循环节点

```yaml
- id: <node_id>                           # 节点唯一标识
  type: loop                              # 节点类型：循环
  description: <description>              # 循环的自然语言描述

  source: <variable_ref>                  # 循环数据源（变量引用）
  item_var: <variable_name>               # 循环变量名

  children:                               # 循环体（子节点列表）
    - <普通节点>
```

**字段说明**：

| 字段 | 必需 | 类型 | 说明 |
|------|------|------|------|
| `id` | 是 | string | 节点唯一标识 |
| `type` | 是 | string | 固定值 "loop" |
| `description` | 是 | string | 循环的自然语言描述 |
| `source` | 是 | string | 循环数据源（变量引用，格式：`{{variable}}`） |
| `item_var` | 是 | string | 循环变量名（在 children 中可引用） |
| `children` | 是 | array | 循环体，包含一个或多个节点 |

---

## 4. Operations 规范

### 4.1 通用结构

```yaml
- type: <operation_type>
  timestamp: <timestamp>          # 可选：时间戳
  url: <url>                      # 可选：当前页面 URL
  page_title: <title>             # 可选：页面标题
  element:                        # 可选：操作的 DOM 元素
    xpath: <xpath>
    tagName: <tag>
    className: <classes>
    textContent: <text>
    href: <href>
  <type_specific_fields>          # 根据 type 不同有不同字段
```

### 4.2 支持的 Operation 类型

#### navigate - 导航

```yaml
- type: navigate
  url: <url>                      # 目标 URL，支持变量引用 {{variable}}
  page_title: <title>
```

#### click - 点击

```yaml
- type: click
  url: <current_url>
  page_title: <title>
  element:
    xpath: <xpath>
    tagName: <tag>
    textContent: <text>
    href: <href>                  # 如果是链接
```

#### input - 输入

```yaml
- type: input
  element:
    xpath: <xpath>
    tagName: <tag>
  value: <input_value>            # 输入的内容，支持变量引用
```

#### extract - 提取数据

```yaml
- type: extract
  target: <field_name>            # 字段名（语义化）
  element:
    xpath: <xpath>
    tagName: <tag>
    textContent: <full_text>      # 元素完整文本
  value: <extracted_value>        # 用户实际想要的数据（可能是 textContent 子集）
```

**关键说明**：
- `target`: 字段名，隐式表示这是一个输出
- `element.textContent`: 元素的完整文本内容
- `value`: 用户实际选择和复制的数据（从 copiedText 来）

**为什么 value 很重要？**

用户可能只选择了元素中的部分内容：
```
element.textContent: "cena 69,50 złAllegro Smart! to darmowe dostawy..."
value:               "69,50 zł"
```
告诉 LLM：用户只想要价格数值，不要其他文字。

#### store - 存储数据

```yaml
- type: store
  params:
    collection: <collection_name>  # 可选：存储目标
    fields: [<field1>, <field2>]   # 引用前面 extract 的 target
```

#### wait - 等待

```yaml
- type: wait
  duration: <milliseconds>
```

#### scroll - 滚动

```yaml
- type: scroll
  direction: <up|down|left|right>
  distance: <pixels>
```

---

## 5. 变量引用规范

### 5.1 引用格式

变量引用使用双花括号语法：`{{variable_name}}`

### 5.2 变量来源

1. **节点输出**：通过 `outputs` 声明的变量
2. **extract target**：extract operation 的 target 隐式声明输出变量
3. **循环变量**：loop 的 `item_var` 在 children 中可用

### 5.3 引用示例

```yaml
# 节点 A 输出
- id: node_a
  operations:
    - type: extract
      target: "product_urls"  # 隐式输出变量
      value: []
  outputs:
    product_urls: "product_urls"  # 显式声明

# 节点 B 引用
- id: node_b
  type: loop
  source: "{{product_urls}}"  # 引用 node_a 的输出
  item_var: "current_product"
  children:
    - id: node_b_1
      operations:
        - type: navigate
          url: "{{current_product.url}}"  # 引用循环变量的属性
```

### 5.4 变量作用域

- 全局作用域：节点 outputs 声明的变量在后续所有节点中可用
- 循环作用域：loop 的 item_var 只在 children 中可用

---

## 6. 数据流规范

### 6.1 输出声明

**通过 outputs 字段**：

```yaml
outputs:
  <output_key>: <variable_name>
```

示例：
```yaml
outputs:
  product_urls: "product_urls"
  message: "scrape_message"
```

**隐式输出（通过 extract）**：

extract operation 的 `target` 自动成为输出变量（但仍建议在 outputs 中显式声明）。

### 6.2 输入引用

**通过 inputs 字段**：

```yaml
inputs:
  <key>: <value_or_variable_ref>
```

示例：
```yaml
inputs:
  product_url: "{{current_product.url}}"
  max_count: 10
```

### 6.3 数据流示例

```yaml
# 节点 1: 提取产品列表
- id: node_1
  intent_name: "ExtractProductList"
  operations:
    - type: extract
      target: "product_urls"
      value: ["url1", "url2"]
  outputs:
    product_urls: "product_urls"

# 节点 2: 循环处理
- id: node_2
  type: loop
  source: "{{product_urls}}"
  item_var: "current_product"
  children:
    - id: node_2_1
      operations:
        - type: navigate
          url: "{{current_product}}"  # 使用循环变量
        - type: extract
          target: "title"
          value: "Product Title"
      outputs:
        title: "product_title"
```

---

## 7. 完整示例

### 任务：从 Allegro 采集第一页咖啡产品信息

```yaml
version: "1.0"
task_description: "用户希望收集热门的第一页的咖啡的商品的相关信息"

nodes:
  # 节点 1: 导航到首页
  - id: node_1
    intent_id: intent_001
    intent_name: "NavigateToAllegro"
    intent_description: "导航到 Allegro 电商网站首页"
    operations:
      - type: navigate
        timestamp: 1757730777260
        url: "https://allegro.pl/"
        page_title: "Navigated Page"

  # 节点 2: 进入咖啡分类
  - id: node_2
    intent_id: intent_002
    intent_name: "EnterCoffeeCategory"
    intent_description: "通过菜单导航进入咖啡产品分类页面"
    operations:
      - type: click
        element:
          xpath: "//div[2]/div[1]/.../button/i"
          tagName: "I"
      - type: click
        element:
          xpath: "//div[2]/div[1]/.../li[1]/a"
          tagName: "A"
          textContent: "Kawy"
          href: "https://allegro.pl/kategoria/produkty-spozywcze-kawa-74030"
      - type: navigate
        url: "https://allegro.pl/kategoria/produkty-spozywcze-kawa-74030"
        page_title: "Kawa - Allegro"

  # 节点 2.5: 提取产品列表（推断节点）
  - id: node_2_5
    intent_id: intent_002_5
    intent_name: "ExtractProductList"
    intent_description: "从分类页面提取所有产品的链接"
    operations:
      - type: extract
        target: "product_urls"
        element:
          xpath: "//*[@id='search-results']//article//a"
          tagName: "A"
        value: []  # 列表类型
    outputs:
      product_urls: "product_urls"

  # 节点 3: 循环处理产品
  - id: node_3
    type: loop
    description: "遍历产品列表，逐个访问详情页并收集产品信息"
    source: "{{product_urls}}"
    item_var: "current_product"
    children:
      - id: node_3_1
        intent_id: intent_003
        intent_name: "CollectProductInfo"
        intent_description: "访问产品详情页，提取并存储产品的标题、价格、销量信息"
        inputs:
          product_url: "{{current_product.url}}"
        operations:
          # 点击产品链接
          - type: click
            element:
              xpath: "//*[@id='search-results']/.../h2/a"
              tagName: "A"
              textContent: "Kawa ziarnista 1kg BRAZYLIA Santos..."
              href: "{{current_product.url}}"

          # 导航到详情页
          - type: navigate
            url: "{{current_product.url}}"
            page_title: "Product Detail Page"

          # 提取标题
          - type: extract
            target: "title"
            element:
              xpath: "//*[@id='showproduct-left-column-wrapper']/.../h1"
              tagName: "H1"
              textContent: "Kawa ziarnista 1kg BRAZYLIA Santos Świeżo Palona 100% ARABICA Tommy Cafe"
            value: "Kawa ziarnista 1kg BRAZYLIA Santos Świeżo Palona 100% ARABICA Tommy Cafe"

          # 提取价格
          - type: extract
            target: "price"
            element:
              xpath: "//*[@id='showproduct-right-column-wrapper']/.../div[1]"
              tagName: "DIV"
              textContent: "cena 69,50 złAllegro Smart! to darmowe dostawy i zwroty..."
            value: "69,50 zł"  # 只要价格

          # 提取销量
          - type: extract
            target: "sales_count"
            element:
              xpath: "//*[@id='showproduct-left-column-wrapper']/.../div[2]"
              tagName: "DIV"
              textContent: "3 308 osób kupiło ostatnio"
            value: "3 308 osób kupiło ostatnio"

          # 存储数据
          - type: store
            params:
              collection: "daily_products"
              fields: ["title", "price", "sales_count"]

        outputs:
          product_info: "product_info"
```

---

## 8. 约束和限制

### 8.1 MVP 限制

1. **控制流**：只支持线性序列 + 单层循环（不支持嵌套循环）
2. **条件分支**：不支持（未来扩展）
3. **并行执行**：不支持（未来扩展）
4. **错误处理**：不显式定义（由 LLM 生成 workflow 时处理）

### 8.2 命名约定

1. **节点 ID**：使用 `node_<number>` 或语义化名称
2. **意图名称**：PascalCase，如 `NavigateToAllegro`
3. **变量名**：snake_case，如 `product_urls`, `current_product`
4. **字段名**：snake_case，如 `page_title`, `text_content`

### 8.3 数据类型

支持的数据类型（通过 value 推断）：
- **string**: 单个字符串
- **array**: 列表（value 为 `[]` 或数组）
- **object**: 对象（value 为 `{}`）

---

## 9. 与 Workflow 的对应关系

| MetaFlow | Workflow |
|----------|----------|
| 节点 | Step |
| intent_description | agent_instruction |
| operations | inputs (转换后) |
| outputs | outputs |
| loop.source | foreach.source |
| loop.item_var | foreach.item_var |
| extract.target | scraper_agent 的 output_format 字段 |
| extract.value | scraper_agent 的 sample_data |

---

## 10. 设计原则

1. **显式优于隐式**：重要的数据流用 outputs/inputs 显式声明
2. **人类可读**：使用自然语言描述和语义化命名
3. **完整性**：包含 LLM 生成 workflow 所需的所有信息
4. **简洁性**：不包含 workflow 实现细节（agent_type, agent_instruction 等）
5. **可扩展**：格式设计考虑未来扩展（条件、嵌套循环等）

---

## 11. 参考

- BaseAgent Workflow 规范: `docs/baseagent/workflow_specification.md`
- 用户操作示例: `tests/sample_data/browser-user-operation-tracker-example.json`
- MetaFlow 设计文档: `metaflow_design.md`
