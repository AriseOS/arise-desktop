# ToolAgent Specification

**Agent Type**: `tool_agent`

## Purpose
Intelligent tool selection and execution with confidence-based mechanism.

## Input Parameters

### Required
```yaml
inputs:
  task_description: "What task to accomplish"  # Natural language task description
```

### Optional
```yaml
inputs:
  allowed_tools: ["tool1", "tool2"]   # Restrict to specific tools
  confidence_threshold: 0.8            # Min confidence for tool selection
  context_data: {}                     # Additional context for tool selection
  constraints: []                      # Task constraints
```

## Output
```yaml
outputs:
  result: "variable_name"       # Tool execution result
  tool_used: "tool_var"         # Tool name that was used
  confidence: "conf_var"        # Confidence score (0-1)
```

## Example

```yaml
- id: "execute-task"
  agent_type: "tool_agent"
  inputs:
    task_description: "Navigate to https://example.com and extract the main heading"
    allowed_tools: ["browser_use"]
    confidence_threshold: 0.7
  outputs:
    result: "task_result"
    tool_used: "selected_tool"
```

## How It Works

1. **First Round**: LLM selects best tool based on task
2. **Second Round**: LLM determines specific API call and parameters
3. **Execution**: Tool executes with generated parameters
