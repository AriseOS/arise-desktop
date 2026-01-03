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
| `tool_agent` | Call external tools |

**Control Flow** (use as top-level keys in v2):
| Syntax | Purpose |
|--------|---------|
| `foreach:` | Loop over a list |
| `if:` | Conditional branching |
| `while:` | Conditional loop |

**Note**: Use `agent:` (preferred) or `agent_type:` for agent steps.

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
- id: summarize
  agent: text_agent
  inputs:
    instruction: "Summarize this content"
    content: "{{extracted_text}}"
  outputs:
    result: summary
```

### variable
- Combine, filter, or slice data (no LLM)
- **Agent type is `variable`** (not `variable_agent`)
- **Output key is always `result`**
- **Operations: set, filter, slice**
- See `references/variable_agent.md`
```yaml
- id: combine-data
  agent: variable
  inputs:
    operation: set
    data:
      url: "{{product.url}}"
      name: "{{details.0.name}}"
  outputs:
    result: complete_product
```

### Control Flow (v2 Syntax)

**foreach** - Loop over items:
```yaml
- foreach: "{{items}}"
  as: item
  do:
    - id: process-one
      agent: scraper_agent
      ...
```

**if** - Conditional:
```yaml
- if: "{{condition}} == true"
  then:
    - id: do-something
      agent: text_agent
      ...
  else:
    - id: do-other
      ...
```

**while** - Conditional loop:
```yaml
- while: "{{has_more}}"
  do:
    - id: process
      agent: browser_agent
      ...
```

## Step Required Fields

Every agent step MUST have:
- `id`: Unique identifier
- `agent` (or `agent_type`): One of the valid types

Optional:
- `name`: Human-readable name
- `inputs`: Agent-specific inputs
- `outputs`: Output variable mapping
- `condition`: Skip if false
- `timeout`: Step timeout

## Cooperation Pattern

**browser_agent handles navigation → scraper_agent extracts data**

```yaml
# Step 1: Navigate
- id: navigate
  agent: browser_agent
  inputs:
    target_url: "https://example.com"

# Step 2: Extract (from current page)
- id: extract
  agent: scraper_agent
  inputs:
    data_requirements:
      output_format:
        title: "Page title"
  outputs:
    extracted_data: result
```

## When to Read Full Specs

Read the full specification when you need:
- Complete input parameter options
- Output format details
- Advanced usage patterns
- Specific examples

Use: `Read references/<agent>_agent.md`
