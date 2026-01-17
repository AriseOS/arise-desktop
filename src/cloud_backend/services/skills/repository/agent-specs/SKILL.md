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
| `tavily_agent` | `operation`, `query` | - |

### Enum Values

| Agent | Field | Allowed Values |
|-------|-------|----------------|
| `storage_agent` | `operation` | `store`, `query`, `export` |
| `storage_agent` | `export_format` | `csv`, `excel`, `json` |
| `variable` | `operation` | `set`, `filter`, `slice`, `extend` |
| `scraper_agent` | `extraction_method` | `script`, `llm` |
| `scraper_agent` | `dom_scope` | `partial`, `full` |
| `tavily_agent` | `operation` | `search` |
| `tavily_agent` | `search_depth` | `basic`, `advanced` |

## Output Contract (IMPORTANT)

**All agents output to `data["result"]`**. Use `outputs: {result: variable_name}` format.

| Agent | Return Type | Description |
|-------|-------------|-------------|
| scraper_agent | `List[Dict]` | Extracted data list |
| text_agent | `Dict` | LLM response JSON |
| variable | `Any` | Operation result |
| browser_agent | `Dict` | `{url, title, success}` |
| storage_agent | `Dict` | `{count, ...}` |
| tavily_agent | `Dict` | `{query, results, answer?, images?}` - see details below |

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

**Collection naming rule**: If a workflow has multiple `storage_agent` steps:
- Same data structure + same purpose → Use the **same** `collection` name (data appends to same table)
- Same data structure but different purpose (user needs to view separately) → Use **different** `collection` names
- Different data structure → Use **different** `collection` names (e.g., `products`, `product_details`)

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
    data:                                  # Optional: input data (dict, list, or any value)
      content: "{{extracted_text}}"
  outputs:
    result: summary                  # Dict (LLM response)

# data can also be a list or variable reference
- id: analyze-products
  agent: text_agent
  inputs:
    instruction: "Analyze these products and find the best value"
    data: "{{products}}"             # Can be list, dict, or any JSON value
  outputs:
    result: analysis
```

## Control Flow

### foreach

**CRITICAL**: `foreach` value must be a YAML list, NOT a string.

```yaml
# Variable reference (quotes required for template syntax)
- foreach: "{{product_list}}"
  as: product
  do:
    - id: process-product
      agent: browser_agent
      inputs:
        target_url: "{{product.url}}"

# Literal list - NO QUOTES (YAML parses as actual list)
- foreach: [1, 2, 3, 4, 5]
  as: page_num
  do:
    - id: navigate-page
      agent: browser_agent
      inputs:
        target_url: "https://example.com/page/{{page_num}}"
```

**Common mistake**:
```yaml
# ❌ WRONG - quotes make it a string "[1, 2, 3]"
- foreach: "[1, 2, 3]"

# ✅ CORRECT - no quotes, YAML parses as list
- foreach: [1, 2, 3]
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

## tavily_agent

Web search agent powered by Tavily API.

**Required**: `operation`, `query`

### Operations

| Operation | Use Case | Output |
|-----------|----------|--------|
| `search` | Basic web search, get URL list | `{query, results, answer?, images?}` |

> Note: `research` operation is disabled (too expensive)

### Output Structure

The `search` operation returns a Dict with this structure:

```yaml
# Full response structure
{
  query: "original search query",
  results: [                        # Array of search results
    {
      title: "Page Title",
      url: "https://example.com/page",
      content: "Snippet of page content...",  # Text excerpt
      score: 0.95,                  # Relevance score (0-1)
      published_date: "2024-01-15"  # Optional: publication date
    },
    ...
  ],
  answer: "AI-generated summary...",  # Optional: only if include_answer=true
  images: [...]                        # Optional: only if include_images=true
}
```

### Accessing Results in Workflow

```yaml
# Store search results
- id: search-news
  agent: tavily_agent
  inputs:
    operation: search
    query: "AI news"
  outputs:
    result: search_data              # Full response object

# Access fields in next step
- id: process-results
  agent: text_agent
  inputs:
    instruction: "Summarize these news articles"
    data: "{{search_data.results}}"  # Access results array

# Or access specific result
- id: visit-first
  agent: browser_agent
  inputs:
    target_url: "{{search_data.results.0.url}}"  # First result's URL
```

### search operation

All Tavily SDK search parameters are supported:

```yaml
- id: search-news
  agent: tavily_agent
  inputs:
    operation: search                  # Required: "search"
    query: "AI news 2024"              # Required: search query
    max_results: 10                    # Optional: max results (default: 10)
    search_depth: basic                # Optional: "basic" | "advanced"
    topic: news                        # Optional: "general" | "news" | "finance"
    days: 3                            # Optional: limit to past N days (important for recent news!)
    time_range: week                   # Optional: "day" | "week" | "month" | "year"
    include_domains:                   # Optional: domain whitelist
      - "techcrunch.com"
    exclude_domains:                   # Optional: domain blacklist
      - "spam.com"
    include_answer: true               # Optional: include LLM-generated answer
    include_images: true               # Optional: include image results
    include_raw_content: false         # Optional: include raw page content
    country: us                        # Optional: country code for localized results
  outputs:
    result: search_results             # {results: [...], answer?: "...", images?: [...]}
```

**Key parameters for time-sensitive searches**:
- `days`: Limit to past N days (e.g., `days: 3` for "last 3 days")
- `time_range`: Broader time filter (`day`, `week`, `month`, `year`)
- `topic: news`: Optimizes for news content

### Example: "收集过去3天的10个热门AI新闻"

```yaml
steps:
  # 1. Search recent news with time filter
  - id: search-ai-news
    agent: tavily_agent
    inputs:
      operation: search
      query: "AI artificial intelligence news"
      max_results: 20
      days: 3                          # Key: limit to past 3 days
      topic: news                      # Optimize for news
      include_answer: true             # Get summary answer
    outputs:
      result: raw_results

  # 2. Filter/rank top 10 with LLM
  - id: filter-top-news
    agent: text_agent
    inputs:
      instruction: "从这些搜索结果中筛选出最重要的10条AI新闻，按重要性排序，返回 JSON 数组"
      data: "{{raw_results.results}}"
    outputs:
      result: top_10_news

  # 3. Store results
  - id: store-news
    agent: storage_agent
    inputs:
      operation: store
      collection: ai_news
      data: "{{top_10_news}}"
```
