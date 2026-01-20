---
name: workflow-generation
description: Generate workflows from user's recorded browser actions.
---

# Workflow Generation

## Core Principle

**Understand the user's goal, not just replay every action.**

The recording shows what the user did, but not every action is meaningful:
- Some clicks are navigation → need to reproduce
- Some clicks are meaningless (clicking blank area) → skip
- Some scrolls trigger lazy loading → need to reproduce
- Some scrolls are just for viewing → skip (scraper gets full DOM)
- Select/extract shows what data user wants → use scraper_agent

## Generation Guidelines

### 1. Navigation Steps

**Click + navigate to target page:**
- Understand if this navigation is necessary for the goal
- Check the href/target URL:
  - **Static URL** (`/about`, `/products`, `/contact`) → use direct `target_url`
  - **Dynamic URL** (contains dates/IDs like `/weekly/2026/3`, `/product/123`) → use `scraper_agent` to extract href, then `browser_agent` to navigate

**Meaningless clicks:**
- Clicks on blank areas, accidental clicks → skip

### 2. Data Extraction

**Select/extract operations** indicate what data the user wants:
- Use `scraper_agent` with the xpath from the operation
- Group related extractions into one scraper step when on same page

### 3. Scroll Operations

**Usually skip** - `scraper_agent` can access full DOM without scrolling.

**Keep scroll when:**
- Page has lazy loading (look for `dataload` operations after scroll)
- Need to trigger content to load

### 4. Form Interactions

**Input/fill operations:**
- Use `browser_agent` with `interaction_steps`
- Include `text` field with the value

### 5. Static vs Dynamic URL

| Type | Pattern | Example | Action |
|------|---------|---------|--------|
| Static | Fixed path, no variables | `/about`, `/products` | Direct `target_url` |
| Dynamic | Contains date | `/weekly/2026/3`, `/news/2026-01-20` | Extract via scraper |
| Dynamic | Contains ID | `/product/12345`, `/user/abc` | Extract via scraper |
| Dynamic | Query params that change | `/search?q=xxx` | Extract via scraper |

## Output Format

### Workflow YAML (v2)

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

### Output Contract

**All agents output to `result` key**:

```yaml
outputs:
  result: variable_name    # → context.variables["variable_name"]
```

Reference in inputs: `"{{variable_name}}"` or `"{{variable_name.0.field}}"`

## Examples

### Static URL Navigation

```yaml
# User clicked "About" link with href="/about"
# Static URL → direct navigation
- id: go-to-about
  agent: browser_agent
  inputs:
    target_url: "https://example.com/about"
```

### Dynamic URL Navigation

```yaml
# User clicked "Weekly" tab with href="/leaderboard/weekly/2026/3"
# Dynamic URL (contains date) → extract first

- id: extract-weekly-link
  agent: scraper_agent
  inputs:
    extraction_method: script
    data_requirements:
      user_description: "Extract weekly leaderboard link"
      output_format:
        url: "Link URL"
      xpath_hints:
        url: "//a[contains(@class, 'navTab')]"  # xpath from operation
  outputs:
    result: weekly_link

- id: navigate-to-weekly
  agent: browser_agent
  inputs:
    target_url: "{{weekly_link.0.url}}"
```

### Data Extraction

```yaml
# User selected product names on the page
- id: extract-products
  agent: scraper_agent
  inputs:
    extraction_method: script
    data_requirements:
      user_description: "Extract product list"
      output_format:
        name: "Product name"
        url: "Product URL"
      xpath_hints:
        name: "//div[@class='product']/h3"  # xpath from select operation
  outputs:
    result: products
```

## Critical Constraints

1. **xpath_hints must be dict**: `{key: "//xpath"}`, NOT list
2. **Use xpath from operations** - don't invent new xpaths
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
