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

### Structure Validation
- Required root fields: `apiVersion`, `kind`, `metadata`, `steps`
- Required metadata: `name`, `description`
- Step IDs are unique

### Agent Type Validation
Valid agent types:
- `browser_agent`
- `scraper_agent`
- `storage_agent`
- `variable`
- `foreach`
- `if`
- `while`
- `text_agent`
- `code_agent`
- `tool_agent`
- `autonomous_browser_agent`

### Variable Validation
- Variables must be defined before use
- Check `{{variable}}` references have prior definitions
- Workflow inputs count as defined variables

### Control Flow Validation
- `foreach`: requires `source` and `steps`
- `if`: requires `condition` and `then`/`then_steps`
- `while`: requires `condition` and `steps`

### Agent-Specific Validation
- `foreach`: must have `source` and `steps`
- `if`: must have `condition` and `then`
- `code_agent`: must have `code` at step level
- `text_agent`: must have `instruction` inside `inputs` (i.e., `inputs.instruction`)

### Final Response Check
- Warning if no step outputs `final_response`
- Workflow should return a result to user

## Output Format

```
VALIDATION PASSED
```

or

```
VALIDATION FAILED
Errors (N):
  1. Missing required field: 'metadata.name'
  2. Undefined variable '{{product}}' referenced in step 'extract' inputs
Warnings (M):
  1. No step outputs 'final_response'
```

## Fixing Common Errors

### "Missing required field"
Add the required field to your YAML.

### "Undefined variable"
Ensure the variable is either:
1. Defined in workflow `inputs`
2. Output by a previous step

### "Invalid agent_type"
Use one of the valid agent types listed above.

### "Duplicate step id"
Make each step ID unique within the workflow.

### "foreach missing 'source'"
Add `source: "{{list_variable}}"` to the foreach step.

## Validation Loop

If validation fails:
1. Read the error messages
2. Fix each error in the YAML
3. Re-run validation
4. Repeat until VALIDATION PASSED
