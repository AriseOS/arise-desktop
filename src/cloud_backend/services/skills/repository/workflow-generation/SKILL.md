---
name: workflow-generation
description: Generate workflows from user's recorded browser actions.
---

# Workflow Generation

## Core Principle

**The workflow should replay the user's recorded actions.** Do not skip steps or optimize away navigation - the user recorded those steps for a reason.

## App Environment

- User records browser actions → converted to intent operations (your input)
- You generate a workflow YAML → the app executes it
- `storage_agent` stores data → user exports via app UI (no export steps needed in workflow)

## Output Contract

**All agents output to `result` key**:

```yaml
outputs:
  result: variable_name    # → context.variables["variable_name"]
```

Reference in inputs: `"{{variable_name}}"` or `"{{variable_name.0.field}}"`

## Input: Intent Operations

Each operation has:
- `type`: click, scroll, extract, navigate, input, select, newtab, closetab
- `url`: Page URL when action occurred
- `element`: Contains `xpath`, `href`, `tagName`, `textContent`

## Output: Workflow YAML (v2)

```yaml
apiVersion: "ami.io/v2"
name: workflow-name
description: "What this workflow does"

steps:
  - id: step-id
    name: "Human-readable name"  # REQUIRED
    agent: agent_type
    inputs: {...}
    outputs:                     # Omit if no output needed
      result: variable_name
```

## Mapping Rules

| Operation | Workflow Step |
|-----------|---------------|
| navigate | `browser_agent` with `target_url` |
| click (no href) | `browser_agent` with `interaction_steps` |
| click (with href) | `scraper_agent` extract URL → `browser_agent` navigate |
| click (copy button) | `browser_agent` with `interaction_steps` + outputs |
| extract | `scraper_agent` |
| scroll | `browser_agent` with `interaction_steps` |
| input/fill | `browser_agent` with `interaction_steps` + `text` |
| newtab | `browser_agent` with `action: new_tab` |
| closetab | `browser_agent` with `action: close_tab` |

For Agent input details, see `agent-specs` skill.

## Key Rule: Click with href

When click element has `href`, use **two steps** (extract URL then navigate):

```yaml
# Step 1: Extract link URL using xpath from operation
- id: extract-link
  agent: scraper_agent
  inputs:
    extraction_method: script
    data_requirements:
      user_description: "Extract link URL"
      output_format:
        url: "Link href"
      xpath_hints:
        url: "//*[@id='nav']/a[2]"  # Use exact xpath from operation
  outputs:
    result: link_info

# Step 2: Navigate to extracted URL
- id: navigate-to-link
  agent: browser_agent
  inputs:
    target_url: "{{link_info.0.url}}"
```

**Do NOT** hardcode URLs or skip navigation steps.

## Critical Constraints

1. **xpath_hints must be dict**: `{key: "//xpath"}`, NOT list
2. **Use exact xpath from operation** - never construct or invent new xpaths
3. **Never write `outputs: null`** - omit the field if not needed
4. **foreach value must be YAML list**: `[1,2,3]` NOT `"[1,2,3]"`

## foreach Syntax

```yaml
# Variable reference
- foreach: "{{items}}"
  as: item
  do:
    - id: process
      agent: browser_agent
      inputs:
        target_url: "{{item.url}}"

# Literal list - NO QUOTES
- foreach: [1, 2, 3]
  as: num
  do: [...]
```

## Variable Reference

```yaml
"{{variable}}"           # Entire variable
"{{object.field}}"       # Dict field
"{{list.0.field}}"       # First item's field
"{{list.length}}"        # List length
```
