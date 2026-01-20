---
name: workflow-generation
description: Generate workflows from user's recorded browser actions.
---

# Workflow Generation

## Core Principle

**Understand the user's goal and intent operations with real-world web interaction logic to generate a workflow that accomplishes the task.**

## Generation Guidelines

### 1. Navigation Steps

**Web navigation is sequential.** Each page provides the context for the next action.

Note: Intermediate pages may be required because the target element only exists there, or the page provides necessary context.

**Click followed by navigate:**
- This is a navigation action. Check the **navigate's target URL**:
  - **Static URL** (`/about`, `/products`, `/makers`) → use direct `target_url`
  - **Dynamic URL** (contains dates/IDs like `/weekly/2026/3`, `/product/123`) → use `scraper_agent` to extract href from click element, then `browser_agent` to navigate

**Click without navigate following:**
- Page interaction (expand button, toggle) → use `interaction_steps`
- Meaningless click (blank area) → skip

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

**With existing URL variable:** When you have a base URL variable (e.g., `{{product.url}}`), check only the **new path segment** being added:
- Static suffix (`/makers`, `/team`, `/reviews`) → **directly concatenate**: `"{{product.url}}/makers"` (do NOT extract)
- Dynamic suffix (contains new ID/date) → extract via scraper

Example: If `{{product.url}}` = `/products/noodle-seed` and user clicks Team tab with href `/products/noodle-seed/makers`:
- The new segment is just `/makers` (static) → use `"{{product.url}}/makers"`

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
