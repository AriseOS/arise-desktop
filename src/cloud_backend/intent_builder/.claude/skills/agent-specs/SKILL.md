---
name: agent-specs
description: Agent specifications for workflow generation.
---

# Agent Specifications

## browser_agent

Navigate and interact with pages. Does NOT extract data.

```yaml
# Navigate only
- id: go-to-page
  agent: browser_agent
  inputs:
    target_url: "https://example.com"

# Interactions (click, fill, scroll)
- id: click-button
  agent: browser_agent
  inputs:
    interaction_steps:
      - task: "Click the submit button"
        xpath_hints:
          button: "//button[@id='submit']"  # MUST be dict!
      - task: "Fill email field"
        xpath_hints:
          email: "//input[@name='email']"
        text: "user@example.com"
```

**Critical**: `xpath_hints` must be **dict** `{key: "//xpath"}`, NOT list.

## scraper_agent

Extract data from current page. Does NOT navigate.

```yaml
- id: extract-products
  agent: scraper_agent
  inputs:
    extraction_method: script    # Always use "script"
    dom_scope: full              # "full" for lists, "partial" for single item
    data_requirements:
      user_description: "Extract product list"
      output_format:
        name: "Product name"
        url: "Product URL"
      xpath_hints:               # Optional hints from recording
        name: "//*[@class='product']/h3"
        url: "//*[@class='product']/a"
  outputs:
    extracted_data: product_list  # Always returns List[Dict]
```

Access first item: `{{product_list.0.name}}`

## storage_agent

Store, query, or export data.

```yaml
# Store
- id: store-data
  agent: storage_agent
  inputs:
    operation: store
    collection: products
    data: "{{product}}"
    upsert_key: url              # Optional: update if exists

# Export
- id: export-csv
  agent: storage_agent
  inputs:
    operation: export
    collection: products
    format: csv
    filename: products.csv
```

## variable

Combine or transform data (no LLM).

```yaml
- id: combine-data
  agent: variable                 # NOT "variable_agent"
  inputs:
    operation: set
    data:
      url: "{{product.url}}"
      name: "{{details.0.name}}"
  outputs:
    result: complete_product      # Output key is always "result"
```

## text_agent

Generate or transform text using LLM.

```yaml
- id: summarize
  agent: text_agent
  inputs:
    instruction: "Summarize this content"
    content: "{{extracted_text}}"
  outputs:
    result: summary
```

## Control Flow

### foreach
```yaml
- foreach: "{{product_list}}"
  as: product
  do:
    - id: process-product
      agent: browser_agent
      inputs:
        target_url: "{{product.url}}"
```

### if
```yaml
- if: "{{has_next}}"
  then:
    - id: click-next
      agent: browser_agent
      inputs:
        interaction_steps:
          - task: "Click next page"
            xpath_hints:
              next: "//a[contains(text(), 'Next')]"
```

### while
```yaml
- while: "{{has_more}}"
  do:
    - id: load-more
      agent: browser_agent
      inputs:
        interaction_steps:
          - task: "Click load more"
            xpath_hints:
              button: "//button[contains(text(), 'Load')]"
```
