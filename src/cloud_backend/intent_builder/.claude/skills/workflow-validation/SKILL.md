---
name: workflow-validation
description: Validate generated Workflow YAML. Use after generating a workflow to check for errors. Run the validate.py script and fix any reported issues.
---

# Workflow Validation

## Usage

After generating a Workflow YAML, validate it by running:

```bash
python scripts/validate.py workflow.yaml
```

Or validate YAML content directly:

```bash
echo 'your yaml content' | python scripts/validate.py -
```

## What It Checks

### Structure Validation (v2 Format)
- Required root fields: `apiVersion`, `name`, `steps`
- `apiVersion` must start with `ami.io/v`
- Step IDs are unique

### Agent Type Validation
Valid agent types:
- `browser_agent`
- `scraper_agent`
- `storage_agent`
- `variable`
- `text_agent`
- `tool_agent`
- `autonomous_browser_agent`

### Control Flow (v2 Syntax)
Control flow uses top-level keys:
- `foreach:` with `as:` and `do:` (or `steps:`)
- `if:` with `then:` and optional `else:`
- `while:` with `do:` (or `steps:`)

### Variable Validation
- Variables must be defined before use
- Check `{{variable}}` references have prior definitions
- Workflow inputs count as defined variables

### Agent-Specific Validation
- `text_agent`: must have `inputs.instruction`
- `storage_agent`: must have `inputs.operation`
- `scraper_agent`: must have `inputs.data_requirements`

### Final Response Check
- Warning if no step outputs `final_response`
- This is optional for data collection workflows

## Output Format

```
VALIDATION PASSED
```

or

```
VALIDATION FAILED
Errors (N):
  1. Missing required field: 'name'
  2. Undefined variable '{{product}}' referenced in step 'extract' inputs
Warnings (M):
  1. No step outputs 'final_response'
```

## Fixing Common Errors

### "Missing required field"
Add the required field to your YAML.

### "Undefined variable"
Ensure the variable is either:
1. Defined in workflow `input:` or `inputs:`
2. Output by a previous step
3. A loop variable (like `item` in foreach)

### "Invalid agent type"
Use one of the valid agent types listed above. Use `agent:` instead of `agent_type:`.

### "Duplicate step id"
Make each step ID unique within the workflow.

### "foreach missing source"
Use v2 syntax: `foreach: "{{list_variable}}"` instead of `source: ...`

## v2 Format Notes

v2 format differences from v1:
- No `kind:` or `metadata:` wrapper needed
- Use `name:` at root level (not `metadata.name`)
- Use `agent:` instead of `agent_type:` (both work)
- Control flow as top-level keys (`foreach:`, `if:`, `while:`)
- `final_response` is optional

## Validation Loop

If validation fails:
1. Read the error messages
2. Fix each error in the YAML
3. Re-run validation
4. Repeat until VALIDATION PASSED
