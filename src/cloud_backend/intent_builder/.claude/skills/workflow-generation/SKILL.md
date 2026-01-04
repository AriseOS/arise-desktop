---
name: workflow-generation
description: Generate workflows from user's recorded browser actions.
---

# Workflow Generation

## Goal

Convert user's recorded browser actions (intent operations) into a replayable Workflow YAML.

## Input: Intent Operations

Each intent contains operations. Each operation has:
- `type`: click, scroll, extract, navigate, input, select
- `url`: Page URL when action occurred
- `dom_id`: Hash ID (12 chars) linking to DOM snapshot file, null if no DOM captured
- `element`: Contains `xpath`, `href`, `tagName`, `textContent`

### Using DOM Snapshots

Each operation has a `dom_id` field pointing to the DOM snapshot captured at that URL.
The DOM file is located at `dom_snapshots/{dom_id}.json`.

To generate accurate scripts:
1. Check if operation has `dom_id` (not null)
2. Read the DOM file at `dom_snapshots/{dom_id}.json`
3. Match `element.xpath` in the DOM to find `interactive_index`
4. If element not found in DOM (hover/popup), use fallback strategy

See: `references/recording_format.md` for full format specification.

## Output: Workflow YAML (v2)

```yaml
apiVersion: "ami.io/v2"
name: workflow-name
description: "What this workflow does"

steps:
  - id: step-id
    name: "Human-readable step name"  # REQUIRED - every step must have a name
    agent: agent_type
    inputs: {...}
    outputs: {...}
```

**Required step fields**: `id`, `name`, `agent`

## Mapping Rules

| Operation | Workflow Step |
|-----------|---------------|
| click (no href) | `browser_agent` + `interaction_steps` |
| click (with href) | `scraper_agent` extract URL + `browser_agent` navigate |
| extract | `scraper_agent` |
| scroll | `browser_agent` + `interaction_steps` |
| navigate | `browser_agent` + `target_url` |

## Key Rule: Click with href

When click element has href, use **two steps**:

```yaml
# Step 1: Extract link URL
- id: extract-link-url
  agent: scraper_agent
  inputs:
    extraction_method: script
    dom_scope: full
    data_requirements:
      user_description: "Extract the link URL"
      output_format:
        url: "Link href"
      xpath_hints:
        url: "//a[contains(text(), 'Products')]"
  outputs:
    extracted_data: link_info

# Step 2: Navigate
- id: navigate-to-link
  agent: browser_agent
  inputs:
    target_url: "{{link_info.0.url}}"
```

**Do NOT** use `browser_agent` `interaction_steps` for click + navigate.

## Script Generation Integration

After workflow generation, scripts are automatically generated for:
- `browser_agent` with `interaction_steps`: generates `find_element.py`
- `scraper_agent` with `extraction_method: script`: generates `extraction_script.py`

### When Script Generation May Fail

Script generation uses DOM snapshots captured during recording. It may fail when:
1. **Hover/dropdown elements**: The element is inside a hover menu (not visible in initial DOM)
2. **Dynamic content**: The element is loaded after JavaScript execution
3. **Incorrect selectors**: The xpath doesn't match any element in the DOM

### Fallback Strategy

If script generation fails for a step, modify the workflow:

**For hover menu clicks** → Use scraper_agent to extract URL, then browser_agent to navigate:
```yaml
# Instead of: browser_agent click on hover menu item
# Use:
- id: extract-menu-link
  agent: scraper_agent
  inputs:
    extraction_method: script
    data_requirements:
      user_description: "Extract the menu item link URL"
      output_format:
        url: "Menu item href"
      xpath_hints:
        url: "//nav//a[contains(text(), 'Target')]"
  outputs:
    extracted_data: menu_link

- id: navigate-to-target
  agent: browser_agent
  inputs:
    target_url: "{{menu_link.0.url}}"
```

**For dynamic content** → Add explicit navigation or wait steps before extraction.

## Constraints

- `xpath_hints` must be **dict**: `{key: "//xpath"}`, NOT list
- Workflow runs from blank browser - include full path
- Use original URL/href from operation, never simplify
- For loops ("all items", "each product"), use `foreach`
- **No separate data saving step** - do NOT add `storage_agent` steps to save/export data unless user explicitly requests it. Extracted data is usually saved in previous steps; users view and download it themselves.

## Variable Syntax

```yaml
"{{variable}}"           # Simple reference
"{{object.field}}"       # Object field
"{{list.0.field}}"       # First item of list
```

## Example

**Intent operations**:
```yaml
- type: click
  url: "https://shop.com"
  element:
    href: "https://shop.com/products"
    textContent: "Products"
- type: extract
  url: "https://shop.com/products"
```

**Generated workflow**:
```yaml
apiVersion: "ami.io/v2"
name: extract-products
description: "Extract products from shop"

steps:
  - id: extract-products-link
    agent: scraper_agent
    inputs:
      extraction_method: script
      dom_scope: full
      data_requirements:
        user_description: "Extract Products link URL"
        output_format:
          url: "Link href"
        xpath_hints:
          url: "//a[contains(text(), 'Products')]"
    outputs:
      extracted_data: products_link

  - id: navigate-to-products
    agent: browser_agent
    inputs:
      target_url: "{{products_link.0.url}}"

  - id: extract-products
    agent: scraper_agent
    inputs:
      extraction_method: script
      dom_scope: full
      data_requirements:
        user_description: "Extract product list"
        output_format:
          name: "Product name"
          url: "Product URL"
    outputs:
      extracted_data: product_list
```
