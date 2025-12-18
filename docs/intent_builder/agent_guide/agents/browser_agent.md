# BrowserAgent Specification

**Agent Type**: `browser_agent`

## Purpose

Browser interactions: navigate, click, fill, scroll. **browser_agent handles navigation and interactions, NOT data extraction**.

**IMPORTANT - Separation of Concerns**:
- browser_agent: Navigation + Interactions (click, fill, scroll)
- scraper_agent: Data extraction

## Input Parameters

### Optional
```yaml
inputs:
  target_url: "https://example.com"     # URL to navigate to first
  interaction_steps:                     # List of interactions to perform
    - task: "Description of action"      # What to do (Claude Agent finds element)
      xpath_hints:                       # Hints to help locate element
        hint_name: "//xpath/expression"
      text: "input text"                 # For fill operations only
```

**Note**: At least one of `target_url` or `interaction_steps` must be provided.

## Output

```yaml
outputs:
  result: "variable_name"   # Operation result
```

**Return Format**:
```yaml
{
  "success": true,
  "message": "All steps completed",
  "current_url": "https://...",
  "steps_executed": 3
}
```

## Supported Operations

| Operation | How to Specify | Description |
|-----------|----------------|-------------|
| Navigate | `target_url: "url"` | Navigate to URL |
| Click | `task: "Click the button"` | Click element (task contains "click") |
| Fill | `task: "Fill the field"` + `text: "value"` | Fill input (task contains "fill/input/enter" + text provided) |
| Scroll | `action_type: "scroll"` | Scroll page up/down |
| Scroll to Element | `task: "Scroll to section"` | Scroll to make element visible (task contains "scroll to") |

## Examples

### Navigate Only
```yaml
- id: "navigate-to-page"
  agent_type: "browser_agent"
  inputs:
    target_url: "https://example.com/products"
```

### Click Button
```yaml
- id: "click-new-mail"
  agent_type: "browser_agent"
  inputs:
    interaction_steps:
      - task: "Click the 'New mail' button"
        xpath_hints:
          button: "//button[contains(@aria-label, 'New mail')]"
```

### Fill Form
```yaml
- id: "fill-email"
  agent_type: "browser_agent"
  inputs:
    interaction_steps:
      - task: "Enter email in the recipient field"
        xpath_hints:
          to_field: "//input[@aria-label='To']"
        text: "{{recipient_email}}"
```

### Scroll Page
```yaml
- id: "scroll-down"
  agent_type: "browser_agent"
  inputs:
    interaction_steps:
      - action_type: "scroll"
        parameters:
          down: true
          num_pages: 2
```

### Scroll to Element
```yaml
- id: "scroll-to-section"
  agent_type: "browser_agent"
  inputs:
    interaction_steps:
      - task: "Scroll to the References section"
        xpath_hints:
          section: "//h2[@id='References']"
```

### Complete Workflow: Navigate + Click + Fill
```yaml
- id: "compose-email"
  agent_type: "browser_agent"
  inputs:
    target_url: "https://outlook.live.com/mail/"
    interaction_steps:
      - task: "Click the 'New mail' button"
        xpath_hints:
          button: "//button[contains(@aria-label, 'New')]"

      - task: "Fill in the recipient email"
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
  - id: "navigate-and-expand"
    agent_type: "browser_agent"
    inputs:
      target_url: "https://example.com/orders"
      interaction_steps:
        - task: "Click 'Show Details' button"
          xpath_hints:
            button: "//button[@class='show-details']"

  # Step 2: Extract data from current page
  - id: "extract-data"
    agent_type: "scraper_agent"
    inputs:
      data_requirements:
        user_description: "Extract order details"
        output_format:
          order_id: "Order ID"
          status: "Status"
    outputs:
      extracted_data: "order_info"
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
