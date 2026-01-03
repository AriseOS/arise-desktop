# BrowserAgent Specification

**Agent Type**: `browser_agent`

## Purpose

Browser interactions: navigate, click, fill, scroll. **browser_agent handles navigation and interactions, NOT data extraction**.

**IMPORTANT - Separation of Concerns**:
- browser_agent: Navigation + Interactions (click, fill, scroll)
- scraper_agent: Data extraction

## Input Parameters

### Navigate
```yaml
inputs:
  operation: navigate              # Optional, inferred if target_url present
  target_url: "https://example.com"
```

### Click
```yaml
inputs:
  operation: click
  xpath_hints: ["//button[@id='submit']"]
  # OR
  task: "Click the submit button"  # Natural language description
```

### Fill
```yaml
inputs:
  operation: fill
  xpath_hints: ["//input[@name='email']"]
  text: "user@example.com"
```

### Scroll
```yaml
inputs:
  operation: scroll
  direction: down                  # up | down
  # OR
  task: "Scroll to the bottom"
```

## Output

```yaml
outputs:
  result: variable_name
```

**Return Format**:
```yaml
{
  "success": true,
  "message": "Operation completed",
  "current_url": "https://..."
}
```

## Examples (v2 Format)

### Navigate Only
```yaml
- id: navigate-to-page
  agent: browser_agent
  inputs:
    target_url: "https://example.com/products"
```

### Click Button
```yaml
- id: click-submit
  agent: browser_agent
  inputs:
    operation: click
    xpath_hints: ["//button[contains(@aria-label, 'Submit')]"]
```

### Fill Form Field
```yaml
- id: fill-email
  agent: browser_agent
  inputs:
    operation: fill
    xpath_hints: ["//input[@aria-label='Email']"]
    text: "{{user_email}}"
```

### Scroll Page
```yaml
- id: scroll-down
  agent: browser_agent
  inputs:
    operation: scroll
    direction: down
```

### Multiple Interactions (interaction_steps)
```yaml
- id: compose-email
  agent: browser_agent
  inputs:
    target_url: "https://mail.example.com"
    interaction_steps:
      - task: "Click the 'New' button"
        xpath_hints:
          button: "//button[contains(@aria-label, 'New')]"

      - task: "Fill in the recipient"
        xpath_hints:
          to_field: "//input[@aria-label='To']"
        text: "{{recipient_email}}"

      - task: "Fill in the subject"
        xpath_hints:
          subject: "//input[@aria-label='Subject']"
        text: "{{subject}}"
  timeout: 120
```

## Cooperation with ScraperAgent

**Pattern**: browser_agent navigates/interacts → scraper_agent extracts

```yaml
steps:
  # Step 1: Navigate and click to reveal data
  - id: navigate-and-expand
    agent: browser_agent
    inputs:
      target_url: "https://example.com/orders"
      interaction_steps:
        - task: "Click 'Show Details' button"
          xpath_hints:
            button: "//button[@class='show-details']"

  # Step 2: Extract data from current page
  - id: extract-data
    agent: scraper_agent
    inputs:
      data_requirements:
        user_description: "Extract order details"
        output_format:
          order_id: "Order ID"
          status: "Status"
    outputs:
      extracted_data: order_info
```

## XPath Hints Guidelines

Provide multiple hints for robustness:

```yaml
xpath_hints:
  by_aria: "//button[@aria-label='Submit']"        # Preferred: aria-label
  by_text: "//button[contains(text(), 'Submit')]"  # Fallback: text content
  by_class: "//button[contains(@class, 'submit')]" # Less stable: class
```

Claude Agent uses hints as references but searches actual DOM.

## How It Works

1. **Get DOM**: Fetch page DOM with interactive elements
2. **Check Cache**: Reuse cached script if exists
3. **Claude Agent**: Generate `find_element.py` to locate target element
4. **Execute**: Run script → get element → perform operation
5. **Retry**: If failed, feedback to Claude Agent and retry

Scripts are cached in `~/.ami/data/scripts/` for reuse.
