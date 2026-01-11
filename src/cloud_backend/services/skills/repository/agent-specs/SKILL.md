---
name: agent-specs
description: Agent specifications for workflow generation.
---

# Agent Specifications

## Required Inputs (CRITICAL)

Each agent has required inputs that MUST be provided. Missing required inputs will cause validation errors.

| Agent | Required Inputs | Conditional Required |
|-------|-----------------|---------------------|
| `text_agent` | `instruction` | - |
| `variable` | `operation`, `data` | `field` (when operation=filter) |
| `scraper_agent` | `data_requirements` | - |
| `browser_agent` | - | At least one of `target_url` or `interaction_steps` |
| `storage_agent` | `operation`, `collection` | `data` (when operation=store), `export_format` (when operation=export) |
| `autonomous_browser_agent` | `task` | - |

### Enum Values

| Agent | Field | Allowed Values |
|-------|-------|----------------|
| `storage_agent` | `operation` | `store`, `query`, `export` |
| `storage_agent` | `export_format` | `csv`, `excel`, `json` |
| `variable` | `operation` | `set`, `filter`, `slice`, `extend` |
| `scraper_agent` | `extraction_method` | `script`, `llm` |
| `scraper_agent` | `dom_scope` | `partial`, `full` |

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

**Required**: At least one of `target_url` or `interaction_steps`

```yaml
# Navigate only (no outputs needed - just omit the field)
- id: go-to-page
  agent: browser_agent
  inputs:
    target_url: "https://example.com"  # URL to navigate to

# Interactions (click, fill, scroll)
- id: click-button
  agent: browser_agent
  inputs:
    interaction_steps:                 # List of interactions
      - task: "Click the submit button"
        xpath_hints:
          button: "//button[@id='submit']"  # MUST be dict!
      - task: "Fill email field"
        xpath_hints:
          email: "//input[@name='email']"
        text: "user@example.com"
    timeout: 30                        # Optional: seconds (default: 30)
```

**Critical**: `xpath_hints` must be **dict** `{key: "//xpath"}`, NOT list.

## scraper_agent

Extract data from current page. Does NOT navigate.

**Required**: `data_requirements`

```yaml
- id: extract-products
  agent: scraper_agent
  inputs:
    data_requirements:               # Required: extraction specification
      user_description: "Extract product list"
      output_format:
        name: "Product name"
        url: "Product URL"
      xpath_hints:                   # Optional hints from recording
        name: "//*[@class='product']/h3"
        url: "//*[@class='product']/a"
    extraction_method: script        # Optional: "script" | "llm" (default: "llm")
    dom_scope: full                  # Optional: "full" | "partial" (default: "partial")
    max_items: 0                     # Optional: 0 = unlimited
    timeout: 30                      # Optional: seconds
  outputs:
    result: product_list             # List[Dict]
```

Access first item: `{{product_list.0.name}}`

## storage_agent

Store, query, or export data.

**Required**: `operation`, `collection`
**Conditional**: `data` (when operation=store), `export_format` (when operation=export)

```yaml
# Store (requires: operation, collection, data)
- id: store-data
  agent: storage_agent
  inputs:
    operation: store                 # Required: "store" | "query" | "export"
    collection: products             # Required: collection name
    data: "{{products}}"             # Required for store operation
    upsert_key: url                  # Optional: update if exists
  outputs:
    result: store_result             # {count: N, ...}

# Query (requires: operation, collection)
- id: query-data
  agent: storage_agent
  inputs:
    operation: query
    collection: products
    filters:                         # Optional
      price: {"$lt": 100}
    limit: 10                        # Optional
  outputs:
    result: query_result

# Export (requires: operation, collection, export_format)
- id: export-csv
  agent: storage_agent
  inputs:
    operation: export
    collection: products
    export_format: csv               # Required for export: "csv" | "excel" | "json"
    output_path: /tmp/products.csv   # Optional
  outputs:
    result: export_result
```

## variable

Data operations without LLM. Supports: `set`, `filter`, `slice`, `extend`.

**Required**: `operation`, `data`
**Conditional**: `field` (when operation=filter)

```yaml
# set - Combine data (requires: operation, data)
- id: combine-data
  agent: variable
  inputs:
    operation: set                   # Required: "set" | "filter" | "slice" | "extend"
    data:                            # Required: input data
      url: "{{product.url}}"
      name: "{{details.0.name}}"
  outputs:
    result: complete_product

# filter - Filter list (requires: operation, data, field)
- id: filter-active
  agent: variable
  inputs:
    operation: filter
    data: "{{products}}"             # Required: list to filter
    field: "status"                  # Required for filter: field to check
    contains: "active"               # OR equals: "active"
  outputs:
    result: active_products

# slice - Slice list (requires: operation, data)
- id: get-first-10
  agent: variable
  inputs:
    operation: slice
    data: "{{products}}"             # Required: list to slice
    start: 0                         # Optional: start index
    end: 10                          # Optional: end index
  outputs:
    result: first_10

# extend - Extend list (requires: operation, data)
- id: merge-lists
  agent: variable
  inputs:
    operation: extend
    data: "{{all_products}}"         # Required: base list
    items: "{{new_products}}"        # Optional: items to add
  outputs:
    result: merged_products
```

## text_agent

Generate or transform text using LLM.

**Required**: `instruction`

```yaml
- id: summarize
  agent: text_agent
  inputs:
    instruction: "Summarize this content"  # Required: task instruction for LLM
    data:                                  # Optional: input data for context
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
