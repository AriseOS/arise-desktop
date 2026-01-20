---
name: agent-specs
description: Agent specifications for workflow generation.
---

# Agent Specifications

## Required Inputs

| Agent | Required Inputs | Conditional Required |
|-------|-----------------|---------------------|
| `browser_agent` | - | `target_url` or `interaction_steps` (at least one) |
| `scraper_agent` | `data_requirements` | - |
| `text_agent` | `instruction` | - |
| `storage_agent` | `operation`, `collection` | `data` (when store), `export_format` (when export) |
| `variable` | `operation`, `data` | `field` (when filter) |
| `tavily_agent` | `operation`, `query` | - |

## Enum Values

| Agent | Field | Allowed Values |
|-------|-------|----------------|
| `storage_agent` | `operation` | `store`, `query`, `export` |
| `storage_agent` | `export_format` | `csv`, `excel`, `json` |
| `variable` | `operation` | `set`, `filter`, `slice`, `extend` |
| `scraper_agent` | `extraction_method` | `script`, `llm` |
| `tavily_agent` | `operation` | `search` |

## Output Types

| Agent | Return Type | Description |
|-------|-------------|-------------|
| `scraper_agent` | `List[Dict]` | Extracted data, access: `{{var.0.field}}` |
| `browser_agent` | `Dict` | `{url, title, success, clipboard_content?}` |
| `text_agent` | `Dict` | LLM response |
| `storage_agent` | `Dict` | `{count, ...}` |
| `variable` | `Any` | Depends on operation |
| `tavily_agent` | `Dict` | `{query, results: [...], answer?, images?}` |

---

## browser_agent

Navigate and interact with pages. Does NOT extract data.

```yaml
# Navigate to URL
- id: go-to-page
  agent: browser_agent
  inputs:
    target_url: "https://example.com"

# Click/Fill/Scroll - use interaction_steps
- id: click-and-fill
  agent: browser_agent
  inputs:
    interaction_steps:
      - task: "Click login button"
        xpath_hints:
          button: "//button[@id='login']"   # MUST be dict, not list
      - task: "Fill email"
        xpath_hints:
          email: "//input[@name='email']"
        text: "user@example.com"
      - task: "Scroll down"
        xpath_hints: {}                      # Empty dict for scroll
        text: "down"
```

### Tab Operations

```yaml
# Open new tab
- task: "Open in new tab"
  action: "new_tab"
  url: "https://example.com"

# Switch tab (0 = first tab)
- task: "Switch to first tab"
  action: "switch_tab"
  tab_index: 0

# Close current tab
- task: "Close tab"
  action: "close_tab"
```

### Clipboard Capture

When clicking copy buttons, add `outputs` to capture clipboard:

```yaml
- id: click-copy
  agent: browser_agent
  inputs:
    interaction_steps:
      - task: "Click copy button"
        xpath_hints:
          btn: "//button[@class='copy']"
  outputs:
    result: copy_result    # Access: {{copy_result.clipboard_content}}
```

---

## scraper_agent

Extract data from current page. Does NOT navigate.

```yaml
- id: extract-products
  agent: scraper_agent
  inputs:
    data_requirements:
      user_description: "Extract product list"
      output_format:
        name: "Product name"
        url: "Product URL"
      xpath_hints:                    # Use xpath from recorded operation
        name: "//div[@class='item']/h3"
        url: "//div[@class='item']/a"
    extraction_method: script         # "script" or "llm"
  outputs:
    result: products                  # List[Dict], access: {{products.0.name}}
```

---

## text_agent

LLM-based text generation/transformation.

```yaml
- id: summarize
  agent: text_agent
  inputs:
    instruction: "Summarize this content in Chinese"   # REQUIRED
    data: "{{extracted_text}}"                         # Optional input
  outputs:
    result: summary
```

---

## storage_agent

Store, query, or export data.

```yaml
# Store data
- id: store
  agent: storage_agent
  inputs:
    operation: store
    collection: products
    data: "{{products}}"
    upsert_key: url              # Optional: update if exists

# Query data
- id: query
  agent: storage_agent
  inputs:
    operation: query
    collection: products
    filters:
      price: {"$lt": 100}
    limit: 10
  outputs:
    result: query_result

# Export (rarely needed - app handles export)
- id: export
  agent: storage_agent
  inputs:
    operation: export
    collection: products
    export_format: csv           # csv, excel, json
```

---

## variable

Data operations without LLM.

```yaml
# set - Create/combine data
- id: combine
  agent: variable
  inputs:
    operation: set
    data:
      url: "{{product.url}}"
      name: "{{details.0.name}}"
  outputs:
    result: combined

# filter - Filter list by field
- id: filter
  agent: variable
  inputs:
    operation: filter
    data: "{{products}}"
    field: "status"
    contains: "active"          # Or: equals: "active"
  outputs:
    result: filtered

# slice - Get subset of list
- id: slice
  agent: variable
  inputs:
    operation: slice
    data: "{{products}}"
    start: 0
    end: 10
  outputs:
    result: first_10

# extend - Merge lists
- id: extend
  agent: variable
  inputs:
    operation: extend
    data: "{{all_items}}"
    items: "{{new_items}}"
  outputs:
    result: merged
```

---

## tavily_agent

Web search via Tavily API.

```yaml
- id: search
  agent: tavily_agent
  inputs:
    operation: search
    query: "AI news 2024"
    max_results: 10
    days: 3                      # Limit to past N days
    topic: news                  # general, news, finance
  outputs:
    result: search_data          # Access: {{search_data.results.0.url}}
```

Output structure:
```yaml
{
  query: "...",
  results: [
    {title, url, content, score, published_date},
    ...
  ],
  answer: "...",    # If include_answer: true
  images: [...]     # If include_images: true
}
```

---

## Control Flow

### foreach

```yaml
- foreach: "{{items}}"           # Variable reference
  as: item
  do:
    - id: process
      agent: browser_agent
      inputs:
        target_url: "{{item.url}}"

- foreach: [1, 2, 3]             # Literal list - NO QUOTES
  as: num
  do: [...]
```

### if / while

```yaml
- if: "{{has_next}}"
  then:
    - id: click-next
      agent: browser_agent
      inputs:
        interaction_steps:
          - task: "Click next"
            xpath_hints:
              next: "//a[text()='Next']"

- while: "{{has_more}}"
  do:
    - id: load-more
      ...
```
