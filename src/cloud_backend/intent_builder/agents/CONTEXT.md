# intent_builder/agents/

Claude Agent SDK based workflow generation.

## Overview

Replaces the old `generators/` module with a single Claude Agent that:
1. Reads specification documents via tools
2. Generates Workflow YAML
3. Validates and iterates with feedback

## Files

| File | Purpose |
|------|---------|
| `workflow_builder.py` | Main agent classes |
| `tools/read_spec.py` | Tool for reading spec documents |
| `tools/validate.py` | RuleValidator for workflow validation |

## Classes

### WorkflowBuilder

One-shot workflow generation.

```python
builder = WorkflowBuilder(api_key="...")
result = await builder.build(task_description, intent_sequence)

if result.success:
    workflow = result.workflow
```

### WorkflowBuilderSession

Interactive session with multi-turn dialogue support.

```python
async with WorkflowBuilderSession(api_key="...") as session:
    # Initial generation
    result = await session.generate(task_description, intent_sequence)

    # Follow-up dialogue
    response = await session.chat("Why did you use browser_agent here?")
    response = await session.chat("Change step 3 to extract more fields")

    # Get current workflow
    workflow = session.get_current_workflow()
```

### WorkflowModificationSession

Session for modifying existing workflows via dialogue. Supports both
workflow YAML modifications and scraper script regeneration.

```python
session = WorkflowModificationSession(
    workflow_yaml=existing_yaml,
    user_id="user1",
    workflow_id="workflow_123",
    storage_service=storage_service,
    api_key="..."
)

await session._connect()
async for event in session.chat_stream("抓取列表数据不对"):
    print(event)  # StreamEvent with type, message, etc.
await session._disconnect()
```

**Features:**
- Pre-computes scraper diagnostic context (directory structure, requirements, script output)
- Guides Claude to read `scraper-fix` skill for extraction issues
- Syncs modified files back to original workflow
- Responds to users with a high-level workflow explanation and change summary (no full YAML output)

## Tools

### read_spec

Reads specification files from `docs/base_app/`:
- `workflow_specification.md`
- `browser_agent_spec.md`
- `scraper_agent_spec.md`
- `storage_agent_spec.md`

### validate (RuleValidator)

Validates workflow structure:
- Required fields (apiVersion, kind, metadata, steps)
- Valid agent types (browser_agent, scraper_agent, storage_agent, variable, foreach, if, while, text_agent, code_agent, autonomous_browser_agent)
- Agent-specific fields:
  - `code_agent`: requires `code` at step level
  - `text_agent`: requires `instruction` inside `inputs`
  - Control flow (foreach/if/while): requires appropriate structure fields
- Variable references have definitions
- Unique step IDs

**Important**: Both `agents/tools/validate.py` and `.claude/skills/workflow-validation/scripts/validate.py` must be kept in sync. These validators mirror the actual BaseApp `workflow_loader.py` validation.

## System Prompt

Concise rules in system prompt, detailed specs via tools:

```
Core Rules:
1. browser_agent navigates, scraper_agent extracts (separate)
2. Variables must be defined before use
3. scraper_agent returns List[Dict], access single with .0.field
4. foreach variables only available inside loop
5. Each step needs unique ID
```
