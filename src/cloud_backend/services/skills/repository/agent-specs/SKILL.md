---
name: agent-specs
description: Agent specifications for workflow generation.
---

# Agent Specifications

## Output Contract (IMPORTANT)

**All agents output to `data["result"]`**. Use `outputs: {result: variable_name}` format.

| Agent | Return Type | Description |
|-------|-------------|-------------|
| scraper_agent | `List[Dict]` | Extracted data list |
| text_agent | `Dict` | LLM response JSON |
| variable | `Any` | Operation result |
| browser_agent | `Dict` | `{url, title, success}` |
| storage_agent | `Dict` | `{count, ...}` |

### outputs → inputs 数据流

```yaml
# Step 1: 输出到变量
- id: extract
  agent: scraper_agent
  inputs: {...}
  outputs:
    result: products          # Agent.data["result"] → context.variables["products"]

# Step 2: 在 inputs 中引用变量
- id: store
  agent: storage_agent
  inputs:
    operation: store
    data: "{{products}}"      # 引用整个变量
  outputs:
    result: store_result

# Step 3: 访问嵌套字段
- id: navigate
  agent: browser_agent
  inputs:
    target_url: "{{products.0.url}}"    # 第一个元素的 url 字段
```

**规则**:
- `outputs: {result: X}` → 存入 `context.variables["X"]`
- `inputs` 中用 `"{{X}}"` 引用
- 嵌套访问: `"{{X.field}}"`, `"{{X.0.field}}"`, `"{{X.length}}"`

## browser_agent

Navigate and interact with pages. Does NOT extract data.

```yaml
# Navigate only
- id: go-to-page
  agent: browser_agent
  inputs:
    target_url: "https://example.com"
  outputs: null                      # Usually no output needed

# Interactions (click, fill, scroll)
- id: click-button
  agent: browser_agent
  inputs:
    interaction_steps:
      - task: "Click the submit button"
        xpath_hints:
          button: "//button[@id='submit']"  # MUST be dict!
      - task: "Fill email field"
        xpath_hints:
          email: "//input[@name='email']"
        text: "user@example.com"
```

**Critical**: `xpath_hints` must be **dict** `{key: "//xpath"}`, NOT list.

## scraper_agent

Extract data from current page. Does NOT navigate.

```yaml
- id: extract-products
  agent: scraper_agent
  inputs:
    extraction_method: script        # Always use "script"
    dom_scope: full                  # "full" for lists, "partial" for single item
    data_requirements:
      user_description: "Extract product list"
      output_format:
        name: "Product name"
        url: "Product URL"
      xpath_hints:                   # Optional hints from recording
        name: "//*[@class='product']/h3"
        url: "//*[@class='product']/a"
  outputs:
    result: product_list             # List[Dict]
```

Access first item: `{{product_list.0.name}}`

## storage_agent

Store, query, or export data.

```yaml
# Store
- id: store-data
  agent: storage_agent
  inputs:
    operation: store
    collection: products
    data: "{{products}}"
    upsert_key: url                  # Optional: update if exists
  outputs:
    result: store_result             # {count: N, ...}

# Export
- id: export-csv
  agent: storage_agent
  inputs:
    operation: export
    collection: products
    format: csv
    filename: products.csv
  outputs:
    result: export_result
```

## variable

Data operations without LLM. Supports: `set`, `filter`, `slice`, `extend`.

```yaml
# set - Combine data
- id: combine-data
  agent: variable
  inputs:
    operation: set
    data:
      url: "{{product.url}}"
      name: "{{details.0.name}}"
  outputs:
    result: complete_product

# filter - Filter list
- id: filter-active
  agent: variable
  inputs:
    operation: filter
    data: "{{products}}"
    field: "status"
    contains: "active"               # OR equals: "active"
  outputs:
    result: active_products

# slice - Slice list
- id: get-first-10
  agent: variable
  inputs:
    operation: slice
    data: "{{products}}"
    start: 0
    end: 10
  outputs:
    result: first_10

# extend - Extend list
- id: merge-lists
  agent: variable
  inputs:
    operation: extend
    data: "{{all_products}}"
    items: "{{new_products}}"
  outputs:
    result: merged_products
```

## text_agent

Generate or transform text using LLM.

```yaml
- id: summarize
  agent: text_agent
  inputs:
    instruction: "Summarize this content"
    content: "{{extracted_text}}"
  outputs:
    result: summary                  # Dict (LLM response)
```

## Control Flow

### foreach
```yaml
- foreach: "{{product_list}}"
  as: product
  do:
    - id: process-product
      agent: browser_agent
      inputs:
        target_url: "{{product.url}}"
```

### if
```yaml
- if: "{{has_next}}"
  then:
    - id: click-next
      agent: browser_agent
      inputs:
        interaction_steps:
          - task: "Click next page"
            xpath_hints:
              next: "//a[contains(text(), 'Next')]"
```

### while
```yaml
- while: "{{has_more}}"
  do:
    - id: load-more
      agent: browser_agent
      inputs:
        interaction_steps:
          - task: "Click load more"
            xpath_hints:
              button: "//button[contains(text(), 'Load')]"
```

## Variable Reference Rules

```yaml
"{{variable}}"                       # Entire variable (preserves type)
"{{product.name}}"                   # Dict field access
"{{products.0.name}}"                # List index access
"{{products.length}}"                # List length
"Total: {{products.length}} items"   # String template (converts to string)
```
