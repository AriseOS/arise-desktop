# base_agent/workflows/

YAML workflow definitions and loader.

## Structure

```
workflows/
├── user/        # User-created workflows
└── workflow_loader.py  # Loads and parses YAML workflows
```

## Workflow Format (v2)

```yaml
apiVersion: "ami.io/v2"
name: workflow-name
description: "What this workflow does"

input: url   # Single input shorthand
# OR
inputs:      # Multiple inputs
  url: string
  max_items: number

steps:
  - id: navigate
    agent: browser_agent
    inputs:
      target_url: "{{url}}"

  - id: scrape
    agent: scraper_agent
    inputs:
      extraction_method: llm
      data_requirements:
        user_description: "Extract products"
        output_format:
          name: string
          price: number
    outputs:
      extracted_data: products
```

## Control Flow (v2 Syntax)

### Conditional (`if`)
```yaml
- if: "{{status}} == 'ok'"
  then:
    - agent: text_agent
      inputs: ...
  else:
    - agent: text_agent
      inputs: ...
```

### Loop (`foreach`)
```yaml
- foreach: "{{products}}"
  as: product
  do:
    - agent: storage_agent
      inputs:
        operation: store
        data: "{{product}}"
```

### Loop (`while`)
```yaml
- while: "{{has_next}}"
  do:
    - agent: browser_agent
      inputs: ...
```

## Legacy v1 Format

Still supported for compatibility:

```yaml
apiVersion: "ami.io/v1"
kind: "Workflow"

metadata:
  name: "workflow-name"
  description: "..."

steps:
  - id: "loop"
    agent_type: "foreach"    # v1: agent_type instead of foreach:
    source: "{{items}}"
    item_var: "item"
    steps: [...]
```

## Template Syntax

- `{{variable}}` - Simple variable reference
- `{{item.field}}` - Access object field
- `{{list.0.field}}` - Access list item by index
- `{{list.length}}` - Get list length

## ConditionEvaluator

Evaluates condition expressions with operators:
- Comparison: `==`, `!=`, `>`, `<`, `>=`, `<=`
- Logical: `and`, `or`, `not`
- Built-in functions: `len()`, `str()`, `int()`, `float()`, `bool()`

Example conditions:
```yaml
condition: "{{count}} > 0"
condition: "{{status}} == 'done'"
condition: "{{has_next}} and {{count}} < 100"
```
