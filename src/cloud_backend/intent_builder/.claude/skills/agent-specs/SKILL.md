---
name: agent-specs
description: Agent specifications for workflow generation. Lists all valid agent types and their purposes.
---

# Agent Specifications

## All Valid Agent Types

| Agent Type | Purpose |
|------------|---------|
| `browser_agent` | Navigate, click, fill forms, scroll |
| `scraper_agent` | Extract data from current page |
| `storage_agent` | Store, query, export data |
| `text_agent` | Generate/transform text with LLM |
| `variable` | Set/manipulate variables |
| `foreach` | Loop over a list |
| `if` | Conditional branching |
| `while` | Conditional loop |
| `code_agent` | Execute code |
| `tool_agent` | Call external tools |

**Note**: Use exactly these names. For example, use `variable` (not `variable_agent`).

## Quick Reference

### browser_agent
- Navigate, click, fill forms, scroll
- Does NOT extract data (use scraper_agent)
- See `references/browser_agent.md`

### scraper_agent
- Extract data from current page
- Does NOT navigate (use browser_agent first)
- **ALWAYS use `extraction_method: "script"`**
- Output is always `List[Dict]`
- See `references/scraper_agent.md`

### storage_agent
- Store, query, export data
- Use `upsert_key` to update existing records
- See `references/storage_agent.md`

### text_agent
- Generate or transform text using LLM
- Requires `inputs.instruction` field
- See `references/text_agent.md`
```yaml
- id: "summarize"
  name: "Summarize Content"
  agent_type: "text_agent"
  inputs:
    instruction: "Summarize this content"
    content: "{{extracted_text}}"
  outputs:
    summary: "summary_result"
```

### variable
- Combine, filter, or slice data (no LLM)
- **Agent type is `variable`** (not `variable_agent`)
- **Output key is always `result`**
- See `references/variable_agent.md`
```yaml
- id: "combine-data"
  name: "Combine Data"
  agent_type: "variable"
  inputs:
    operation: "set"
    data:
      url: "{{product.url}}"
      name: "{{details.0.name}}"
  outputs:
    result: "complete_product"
```

### foreach
- Loop over items in a list
```yaml
- id: "process-items"
  name: "Process Items"
  agent_type: "foreach"
  source: "{{items}}"
  item_var: "item"
  max_iterations: 10
  steps:
    - id: "process-one"
      name: "Process One Item"
      ...
```

## Step Required Fields

Every step MUST have these three fields:
- `id`: Unique identifier
- `name`: Human-readable name
- `agent_type`: One of the valid types listed above

## Cooperation Pattern

**browser_agent handles navigation → scraper_agent extracts data**

```yaml
# Step 1: Navigate
- id: "navigate"
  name: "Navigate to Page"
  agent_type: "browser_agent"
  inputs:
    target_url: "https://example.com"

# Step 2: Extract (from current page)
- id: "extract"
  name: "Extract Data"
  agent_type: "scraper_agent"
  inputs:
    data_requirements:
      output_format:
        title: "Page title"
  outputs:
    extracted_data: "result"
```

## When to Read Full Specs

Read the full specification when you need:
- Complete input parameter options
- Output format details
- Advanced usage patterns
- Specific examples

Use: `Read references/<agent>_agent.md`
