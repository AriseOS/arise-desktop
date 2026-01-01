# Loop Detection and Generation

## Problem

Users demonstrate a task on a few items, but intent is to repeat for many items.

## Solution

Detect repeated patterns and convert to `foreach` loop.

## Pattern Recognition

### From User Query

Keywords indicating loop requirement:
- "all products", "every item", "each page"
- "10 items", "first 5", "up to 20"
- "repeat for", "do the same for"

### From Intent Sequence

Look for repeated structure:
```
navigate → extract → navigate → extract → navigate → extract
```

This suggests: `foreach: navigate → extract`

## Transformation Rules

### Rule 1: Extract List → Process Each

**User Action**: Extracted URLs, then visited 2-3 manually

**Transform to**:
```yaml
# Extract list
- id: "extract-urls"
  agent_type: "scraper_agent"
  inputs:
    data_requirements:
      output_format:
        url: "Item URL"
  outputs:
    extracted_data: "item_urls"

# Process each
- id: "process-items"
  agent_type: "foreach"
  source: "{{item_urls}}"
  item_var: "item"
  max_iterations: 10  # From user query or default
  steps:
    - id: "navigate-item"
      agent_type: "browser_agent"
      inputs:
        target_url: "{{item.url}}"
    - id: "extract-item"
      agent_type: "scraper_agent"
      ...
```

### Rule 2: Repeated Click-Extract Pattern

**User Action**:
1. Click item 1 → extract
2. Go back
3. Click item 2 → extract
4. Go back
5. Click item 3 → extract

**Transform to**:
```yaml
- id: "extract-item-urls"
  agent_type: "scraper_agent"
  inputs:
    data_requirements:
      output_format:
        url: "Item URL"
  outputs:
    extracted_data: "items"

- id: "process-items"
  agent_type: "foreach"
  source: "{{items}}"
  item_var: "current_item"
  steps:
    - id: "navigate"
      agent_type: "browser_agent"
      inputs:
        target_url: "{{current_item.url}}"
    - id: "extract"
      agent_type: "scraper_agent"
      ...
```

## Loop Configuration

### max_iterations

Set based on:
- User query: "first 10 items" → `max_iterations: 10`
- Default: `max_iterations: 20`
- Unlimited (careful): `max_iterations: 100`

### item_var and index_var

```yaml
- id: "loop"
  agent_type: "foreach"
  source: "{{items}}"
  item_var: "current_item"   # Access: {{current_item.field}}
  index_var: "idx"           # Access: {{idx}} (0-based)
```

## Common Patterns

### List Page → Detail Pages
```yaml
steps:
  - id: "get-list"
    agent_type: "browser_agent"
    inputs:
      target_url: "{{list_url}}"

  - id: "extract-links"
    agent_type: "scraper_agent"
    outputs:
      extracted_data: "items"

  - id: "process-each"
    agent_type: "foreach"
    source: "{{items}}"
    item_var: "item"
    steps:
      - id: "go-to-detail"
        agent_type: "browser_agent"
        inputs:
          target_url: "{{item.url}}"
      - id: "extract-detail"
        agent_type: "scraper_agent"
        outputs:
          extracted_data: "detail"
      - id: "store"
        agent_type: "storage_agent"
        inputs:
          operation: "store"
          collection: "items"
          data: "{{detail}}"
```

### Pagination
```yaml
steps:
  - id: "init"
    agent_type: "variable"
    inputs:
      operation: "set"
      data:
        page_urls: ["page1", "page2", "page3"]  # Or dynamically extracted
    outputs:
      page_urls: "page_urls"

  - id: "process-pages"
    agent_type: "foreach"
    source: "{{page_urls}}"
    item_var: "page_url"
    steps:
      - id: "navigate-page"
        agent_type: "browser_agent"
        inputs:
          target_url: "{{page_url}}"
      - id: "extract-page-items"
        agent_type: "scraper_agent"
        ...
```

## Output

When loop is detected and generated:
```
Loop Detection Applied:
- Pattern: 3 repeated navigate→extract sequences
- Generated: foreach loop over extracted URLs
- Max iterations: 10 (from user query)
```
