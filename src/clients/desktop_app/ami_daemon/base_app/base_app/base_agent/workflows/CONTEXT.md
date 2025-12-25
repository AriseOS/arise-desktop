# base_agent/workflows/

YAML workflow definitions and loader.

## Structure

```
workflows/
├── builtin/     # System-provided workflows
├── user/        # User-created workflows
└── workflow_loader.py  # Loads and parses YAML workflows
```

## Workflow Format

```yaml
apiVersion: "ami.io/v1"
kind: "Workflow"

metadata:
  name: "workflow-name"
  description: "What this workflow does"
  version: "1.0.0"

inputs:
  user_input:
    type: "string"
    required: true

outputs:
  result:
    type: "object"

steps:
  - id: "step-1"
    agent_type: "text_agent"
    parameters:
      prompt: "Process: {{user_input}}"
    outputs:
      processed: "result"

  - id: "step-2"
    agent_type: "if"
    condition: "{{processed.status}} == 'ok'"
    then:
      - id: "success-step"
        agent_type: "text_agent"
        ...
    else:
      - id: "error-step"
        ...
```

## Control Flow

### Conditional (`if`)
```yaml
- id: "routing"
  agent_type: "if"
  condition: "{{variable}} == 'value'"
  then: [...]
  else: [...]
```

### Loop (`foreach`)
```yaml
- id: "process-items"
  agent_type: "foreach"
  items: "{{item_list}}"
  variable: "item"
  steps:
    - id: "process-one"
      agent_type: "scraper_agent"
      parameters:
        url: "{{item.url}}"
```

### Loop (`while`)
```yaml
- id: "retry-loop"
  agent_type: "while"
  condition: "{{retry_count}} < 3"
  steps: [...]
```

## Template Syntax

- `{{variable}}` - Simple variable reference
- `{{step_id.output_name}}` - Reference previous step output
- `{{item.field}}` - Access object field in loop
