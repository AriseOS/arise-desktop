---
name: workflow-generation
description: How to generate workflows that automate user's recorded browser actions.
---

# Workflow Generation

## What We're Building

Users record their browser actions - clicks, navigation, data extraction. We're creating a Workflow YAML that can **replay those actions automatically**.

Think about it:
- User recorded: Open site → Click "Products" → Click "Electronics" → Extract product list
- Workflow runs on a fresh browser, starting from nothing
- It needs to follow the exact same path to reach the same page state

## The Recording Data

The Intent sequence contains everything the user did:

```yaml
- description: "Navigate to product category"
  operations:
    - type: "click"
      url: "https://shop.com"
      xpath: "//*[@id='nav']/a[2]"
      text: "Products"
    - type: "click"
      url: "https://shop.com/products"
      xpath: "//*[@id='categories']/div[3]"
      text: "Electronics"
```

Each operation is meaningful:
- **xpath**: The exact element the user clicked
- **url**: The page they were on
- **text**: What the element displayed

## Generating the Workflow

### 1. Reproduce the User's Path

Map each recorded operation to workflow steps:

```yaml
steps:
  - id: "open-site"
    name: "Open Website"
    agent_type: "browser_agent"
    inputs:
      target_url: "https://shop.com"

  - id: "click-products"
    name: "Click Products Menu"
    agent_type: "browser_agent"
    inputs:
      action: "click"
      element_description: "Products navigation link"

  - id: "click-electronics"
    name: "Click Electronics Category"
    agent_type: "browser_agent"
    inputs:
      action: "click"
      element_description: "Electronics category"
```

Don't skip steps - the workflow runs from scratch.

### 2. Use XPath for Extraction

When the user extracted data, the xpath shows which elements they selected. Pass this to scraper_agent:

```yaml
- id: "extract-products"
  name: "Extract Product List"
  agent_type: "scraper_agent"
  inputs:
    data_requirements:
      user_description: "Extract product list"
      output_format:
        name: "Product name"
        price: "Price"
      xpath_hints:
        name: "//*[@class='product-card']/h3"
        price: "//*[@class='product-card']/span[@class='price']"
```

The `xpath_hints` help locate the same elements the user interacted with.

### 3. Handle Loops

If the user query mentions "all items", "repeat", or a count like "10 products" → use foreach:

```yaml
- id: "process-each"
  name: "Process Each Product"
  agent_type: "foreach"
  source: "{{product_list}}"
  item_var: "product"
  max_iterations: 10
  steps:
    - id: "visit-product"
      name: "Visit Product Page"
      agent_type: "browser_agent"
      inputs:
        target_url: "{{product.url}}"
```

### 4. Validate

Use the workflow-validation skill to check your YAML before outputting.

## Agent Roles

| Agent | What it does |
|-------|--------------|
| browser_agent | Navigate, click, interact with pages |
| scraper_agent | Extract data from the current page (doesn't navigate) |
| storage_agent | Save data to database |
| text_agent | Transform/summarize text |

## CRITICAL: Agent Specs Lookup Required

**Before writing ANY agent step, you MUST call the `agent-specs` skill to get the exact input format.**

Each agent has strictly defined parameters. Do NOT guess parameter names or values.

| When using... | You MUST first run |
|---------------|-------------------|
| browser_agent | `/agent-specs` to check browser_agent inputs |
| scraper_agent | `/agent-specs` to check scraper_agent inputs |
| storage_agent | `/agent-specs` to check storage_agent inputs |
| text_agent | `/agent-specs` to check text_agent inputs |

**Common mistakes to avoid:**
- Using `insert` instead of `store` for storage_agent
- Missing required fields like `operation` or `collection`
- Wrong parameter names or structures

The agent-specs skill contains the authoritative specification. Always verify before generating.

## Variable Syntax

```yaml
"{{variable}}"           # Simple reference
"{{object.field}}"       # Object field
"{{list.0.field}}"       # First item (scraper returns List[Dict])
```

## Workflow Structure (v2 Format)

**Always use v2 format:**

```yaml
apiVersion: "ami.io/v2"
name: workflow-name
description: "What this workflow does"

input: category_url          # Single input (or inputs: {...})

steps:
  - id: navigate
    agent: browser_agent     # Use 'agent:' (preferred over 'agent_type:')
    inputs:
      target_url: "{{category_url}}"

  - id: extract
    agent: scraper_agent
    inputs:
      extraction_method: script
      dom_scope: full
      data_requirements:
        user_description: "Extract products"
        output_format:
          name: "Product name"
    outputs:
      extracted_data: products
```

**Key v2 features:**
- No `kind:` or `metadata:` wrapper
- Use `agent:` instead of `agent_type:`
- Control flow as top-level keys: `foreach:`, `if:`, `while:`
- `final_response` is optional (not required for data collection)

### Step Required Fields

Every step MUST have:
- `id`: Unique identifier (e.g., "navigate-home", "extract-products")
- `agent`: One of the valid agent types

Optional:
- `name`: Human-readable name
- `inputs`: Agent-specific inputs
- `outputs`: Save results to variables

### Complete Step Example (v2)

```yaml
- id: extract-product-urls
  agent: scraper_agent
  inputs:
    extraction_method: script
    dom_scope: full
    data_requirements:
      user_description: "Extract all product URLs"
      output_format:
        url: "Product URL"
  outputs:
    extracted_data: product_urls
```

Use 2-space indentation.

## Workflow Goal

The workflow's goal is to **complete the user's task**, not to produce output.

Common goals:
- Store extracted data to database (data is accessible later via UI)
- Export data to a file
- Complete a series of browser actions

End the workflow when the goal is achieved. Don't add extra steps just to "return" or "display" data.
