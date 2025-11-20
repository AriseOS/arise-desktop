# Intent Builder Agent Guide

This directory contains documentation for the Intent Builder Agent to generate MetaFlow and Workflow from user operations.

## Quick Reference

### Agent Types

| Agent | Purpose | When to Use |
|-------|---------|-------------|
| `browser_agent` | Navigation and page interactions | Navigate to URLs, scroll pages |
| `scraper_agent` | Extract data from pages | Get structured data from current page |
| `text_agent` | LLM text processing | Translate, summarize, analyze |
| `autonomous_browser_agent` | Exploratory web tasks | Find information without known steps |
| `storage_agent` | Data persistence | Save to database |
| `variable` | Variable management | Initialize, set, append |
| `foreach` | Loop iteration | Process list of items |

### Common Patterns

#### Navigate → Extract
```yaml
- agent_type: "browser_agent"
  inputs:
    target_url: "https://example.com"

- agent_type: "scraper_agent"
  inputs:
    extraction_method: "script"
    data_requirements: ...
```

#### Click → Navigate (Extract Link First)
```yaml
# When MetaFlow shows click → navigate
- agent_type: "scraper_agent"
  inputs:
    data_requirements:
      xpath_hints:
        url: "//a[@class='link']"
  outputs:
    extracted_data: "link_data"

- agent_type: "browser_agent"
  inputs:
    target_url: "{{link_data.url}}"
```

#### Scroll (on Current Page)
```yaml
- agent_type: "browser_agent"
  inputs:
    interaction_steps:
      - action_type: "scroll"
        parameters:
          down: true
          num_pages: 5
```

#### Loop with Collection
```yaml
- agent_type: "variable"
  inputs:
    operation: "set"
    data:
      results: []

- agent_type: "foreach"
  source: "{{items}}"
  item_var: "item"
  steps:
    - agent_type: "scraper_agent"
      outputs:
        extracted_data: "data"

    - agent_type: "variable"
      inputs:
        operation: "append"
        source: "{{results}}"
        data: "{{data}}"
```

#### Text Processing
```yaml
- agent_type: "text_agent"
  inputs:
    instruction: "Translate to Chinese"
    data:
      content: "{{extracted_data}}"
  outputs:
    result: "translated_data"
```

### Key Decision Rules

1. **Navigation without extraction** → `browser_agent`
2. **Data extraction** → `scraper_agent`
3. **Semantic transformation** → `text_agent`
4. **No recorded steps for a goal** → `autonomous_browser_agent`
5. **Save to database** → `storage_agent`
6. **Simple data operations** → `variable`

### MetaFlow Inferred Nodes

When there's a gap between recorded operations and user query:

- **Translation/Summarization/Analysis** → Add `text_process` node with `(Inferred)`
- **Unrecorded sub-goal** → Add `autonomous_task` node with `(Inferred)`

## Directory Structure

```
agent_guide/
├── README.md                 # This file - Quick reference
├── metaflow/
│   ├── specification.md      # MetaFlow YAML structure
│   └── gap_analysis.md       # Inferred node generation
├── workflow/
│   ├── specification.md      # Workflow YAML structure
│   └── agent_selection.md    # Agent type selection principles
└── agents/
    ├── browser_agent.md      # Browser navigation
    ├── scraper_agent.md      # Data extraction
    ├── text_agent.md         # Text processing
    ├── autonomous_browser_agent.md  # Exploratory tasks
    ├── storage_agent.md      # Data persistence
    ├── variable.md           # Variable operations
    └── foreach.md            # Loop iteration
```

## Workflow Phases

### Phase 1: MetaFlow Generation

1. Read user operations and query
2. Map operations to intent nodes
3. Detect loop requirements
4. Analyze gaps and generate inferred nodes
5. Present MetaFlow to user for review

**Documents to read**:
- `metaflow/specification.md`
- `metaflow/gap_analysis.md`

### Phase 2: Workflow Generation

1. Read confirmed MetaFlow
2. Map each node to workflow steps
3. Select appropriate agent types
4. Configure step inputs/outputs
5. Validate and present to user

**Documents to read**:
- `workflow/specification.md`
- `workflow/agent_selection.md`
- `agents/*.md` (as needed)

## Important Reminders

### Separation of Concerns
- `browser_agent`: Navigation only
- `scraper_agent`: Extraction only (from current page)
- Don't skip navigation steps

### Scroll Operations
- Use `interaction_steps`, not just `target_url`
- If already on page, don't provide `target_url`

### Variable Scope in Loops
- `item_var` only available inside loop
- Use `variable` agent to persist data

### final_response
- Workflow should output `final_response` variable

### XPath Hints
- Extract from MetaFlow operations
- Critical for scraper accuracy
