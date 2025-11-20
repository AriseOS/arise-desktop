# Intent Builder Agent Mode Design

## Overview

This document describes the design for converting the Intent Builder's MetaFlow and Workflow generation from single-shot LLM calls to a Claude Agent-based multi-turn conversational approach.

### Goals

1. **User Interaction**: Allow users to review and modify generated results at each stage
2. **Iterative Refinement**: Support multiple rounds of feedback and adjustment
3. **Transparency**: Show structured results (YAML) for user review

### Non-Goals

- Real-time execution feedback (future scope)
- Visual drag-and-drop editing (out of scope)

---

## Architecture

### Current Architecture

```
User Operations + Query
        ↓
IntentExtractor (single LLM call)
        ↓
IntentMemoryGraph
        ↓
MetaFlowGenerator (single LLM call)
        ↓
MetaFlow YAML
        ↓
WorkflowGenerator (single LLM call + auto-retry)
        ↓
Workflow YAML
```

### New Agent-Based Architecture

```
User Operations + Query
        ↓
┌─────────────────────────────────┐
│     Intent Builder Agent        │
│                                 │
│  [Phase 1: MetaFlow Generation] │
│  - Read domain knowledge docs   │
│  - Generate MetaFlow            │
│  - Present to user              │
│  - Handle user feedback         │
│  - Modify as requested          │
│                                 │
│  [Phase 2: Workflow Generation] │
│  - Read domain knowledge docs   │
│  - Generate Workflow            │
│  - Validate automatically       │
│  - Present to user              │
│  - Handle user feedback         │
│  - Modify as requested          │
└─────────────────────────────────┘
        ↓
Final Workflow YAML
```

---

## Agent Design

### System Prompt Structure

The Agent's system prompt contains:

1. **Role Definition**: Workflow generation assistant
2. **Phase Awareness**: Understanding of two-phase process
3. **Tool Usage Guide**: When and how to use each tool
4. **Core Principles**: High-level guidance (details in docs)

```markdown
# System Prompt Outline

## Role
You are an Intent Builder Agent that helps users generate MetaFlow and Workflow
from recorded browser operations.

## Workflow Phases

### Phase 1: MetaFlow Generation
1. Read the user's recorded operations and query
2. Read domain knowledge from docs/intent_builder/agent_guide/metaflow/
3. Generate MetaFlow YAML
4. Present to user and wait for feedback
5. Modify based on feedback until user confirms

### Phase 2: Workflow Generation
1. Read the confirmed MetaFlow
2. Read domain knowledge from docs/intent_builder/agent_guide/workflow/ and agents/
3. Generate Workflow YAML
4. Validate using WorkflowYAMLValidator
5. If validation fails, fix errors automatically
6. Present to user and wait for feedback
7. Modify based on feedback until user confirms

## Tool Usage
- Use Read to access domain knowledge documents
- Use Write to create new files, Edit to modify existing files
- Use Bash to run validation scripts
- Let the LLM decide between Write (full rewrite) and Edit (incremental change)

## Core Principles
- Always show YAML results to user before proceeding
- Wait for explicit user confirmation before moving to next phase
- When user requests changes, analyze whether to Edit or Write
- Preserve user's previous modifications when making new changes
```

### Tools

The Agent has access to these tools:

| Tool | Purpose | Usage |
|------|---------|-------|
| **Read** | Read files | Domain docs, current MetaFlow/Workflow, Intent Graph |
| **Write** | Create/overwrite files | Generate new MetaFlow/Workflow |
| **Edit** | Modify part of file | Incremental changes to existing files |
| **Bash** | Run commands | Execute validation scripts |
| **Glob** | Find files | Locate relevant documents |

### Context Available

The Agent has access to:

1. **User Operations**: The recorded browser operations (JSON)
2. **User Query**: What the user wants to achieve
3. **Intent Graph**: Extracted intents from operations
4. **Domain Knowledge**: Documentation in `docs/intent_builder/agent_guide/`
5. **Generated Artifacts**: MetaFlow and Workflow files
6. **Conversation History**: All previous exchanges with user

---

## Domain Knowledge Organization

### Directory Structure

```
docs/intent_builder/agent_guide/
├── README.md                         # Quick reference for Agent
├── metaflow/
│   ├── specification.md              # MetaFlow YAML structure
│   └── gap_analysis.md               # Inferred node generation principles
├── workflow/
│   ├── specification.md              # Workflow YAML structure
│   └── agent_selection.md            # Agent type selection principles
└── agents/
    ├── browser_agent.md              # browser_agent capabilities
    ├── scraper_agent.md              # scraper_agent capabilities
    ├── text_agent.md                 # text_agent capabilities
    ├── autonomous_browser_agent.md   # autonomous_browser_agent capabilities
    ├── storage_agent.md              # storage_agent capabilities
    └── variable.md                   # variable agent capabilities
```

### Document Content Sources

The content for these documents will be extracted from:

- `src/intent_builder/generators/metaflow_generator.py` → `metaflow/*.md`
- `src/intent_builder/generators/prompt_builder.py` → `workflow/*.md`, `agents/*.md`
- `docs/baseagent/*_spec.md` → `agents/*.md`

### README.md (Quick Reference)

A condensed reference containing:
- Available agent types and their one-line descriptions
- Common patterns (navigate → extract, click → navigate, etc.)
- Links to detailed docs for each topic

---

## Workflow Details

### Phase 1: MetaFlow Generation

```
┌─────────────────────────────────────────────┐
│ Agent receives: User Operations + Query      │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Agent reads:                                 │
│ - docs/intent_builder/agent_guide/README.md │
│ - metaflow/specification.md                 │
│ - metaflow/gap_analysis.md                  │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Agent generates MetaFlow YAML                │
│ - Maps operations to intents                 │
│ - Detects loops                              │
│ - Generates inferred nodes if needed         │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Agent presents MetaFlow to user              │
│ - Shows YAML in formatted block              │
│ - Explains key decisions                     │
│ - Asks for confirmation or feedback          │
└─────────────────────────────────────────────┘
                    ↓
          ┌────────┴────────┐
          ↓                 ↓
    [User confirms]   [User requests changes]
          ↓                 ↓
    Proceed to        Agent modifies
    Phase 2           (Edit or Write)
                            ↓
                      Present again
                            ↓
                      (loop until confirmed)
```

### Phase 2: Workflow Generation

```
┌─────────────────────────────────────────────┐
│ Agent reads confirmed MetaFlow               │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Agent reads:                                 │
│ - workflow/specification.md                 │
│ - workflow/agent_selection.md               │
│ - agents/*.md (as needed)                   │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Agent generates Workflow YAML                │
│ - Maps MetaFlow nodes to workflow steps      │
│ - Selects appropriate agent types            │
│ - Generates complete step configurations     │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Agent validates Workflow                     │
│ - Calls WorkflowYAMLValidator               │
│ - If errors, automatically fixes and retries │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Agent presents Workflow to user              │
│ - Shows YAML in formatted block              │
│ - Reports validation status                  │
│ - Asks for confirmation or feedback          │
└─────────────────────────────────────────────┘
                    ↓
          ┌────────┴────────┐
          ↓                 ↓
    [User confirms]   [User requests changes]
          ↓                 ↓
       Complete       Agent modifies
                      (Edit or Write)
                            ↓
                      Re-validate
                            ↓
                      Present again
                            ↓
                      (loop until confirmed)
```

---

## Validation

### Existing Validation Code

Location: `src/intent_builder/validators/yaml_validator.py`

Class: `WorkflowYAMLValidator`

Method: `validate(workflow_yaml: str) -> Tuple[bool, str]`

### Agent Invocation

The Agent calls validation through Python:

```python
from src.intent_builder.validators.yaml_validator import WorkflowYAMLValidator

validator = WorkflowYAMLValidator()
is_valid, error_message = validator.validate(workflow_yaml_string)
```

Or via Bash:

```bash
python -c "
from src.intent_builder.validators.yaml_validator import WorkflowYAMLValidator
validator = WorkflowYAMLValidator()
with open('path/to/workflow.yaml') as f:
    result = validator.validate(f.read())
print('Valid:', result[0])
if not result[0]:
    print('Error:', result[1])
"
```

### Validation Flow

1. Agent generates Workflow YAML
2. Agent calls validator
3. If invalid:
   - Agent reads error message
   - Agent fixes the specific issue
   - Agent re-validates
   - Repeat until valid (or max retries)
4. Present validated Workflow to user

---

## User Interaction Patterns

### Confirmation

```
Agent: Here is the generated MetaFlow:

​```yaml
version: "1.0"
task_description: "Collect coffee products"
nodes:
  - id: node_1
    ...
​```

This MetaFlow includes:
- Navigation to coffee category
- Product list extraction
- Loop for collecting details

Do you want to proceed to Workflow generation, or would you like to modify this?
```

### Modification Request

```
User: Change the loop to only process 5 items instead of all

Agent: I'll modify the MetaFlow to limit the loop to 5 items.

[Agent uses Edit tool to update max_iterations]

Updated MetaFlow:

​```yaml
...
  - id: node_3
    type: loop
    max_iterations: 5
    ...
​```

Is this correct?
```

### Complex Modification

```
User: Add a translation step after extraction to translate to Chinese

Agent: I'll add a text processing node for translation. Let me update the MetaFlow.

[Agent analyzes this is a significant change, uses Write to regenerate]

Updated MetaFlow:

​```yaml
...
  - id: node_4
    intent_id: inferred_text_process
    intent_name: "TranslateToChiense"
    intent_description: "Translate extracted data to Chinese (Inferred)"
    operations:
      - type: text_process
        params:
          source: "{{product_data}}"
    outputs:
      translated_data: "translated_data"
​```

I've added a translation node that will process the extracted product data. Is this what you wanted?
```

---

## File Locations

### Generated Artifacts

```
output/
├── metaflow.yaml          # Generated MetaFlow
├── workflow.yaml          # Generated Workflow
└── intent_graph.json      # Intent Graph (input)
```

### Working Directory

The Agent operates in a working directory containing:
- User operations JSON
- Intent Graph
- Output directory for generated files

---

## Implementation Considerations

### Agent SDK vs Claude Code CLI

Two implementation options:

**Option A: Claude Code CLI with Custom Commands**
- Use Claude Code's slash command system
- Implement as a custom command that sets up the context
- Pros: Quick to implement, uses existing infrastructure
- Cons: Limited control over agent behavior

**Option B: Agent SDK (Python/TypeScript)**
- Build custom agent using Claude Agent SDK
- Full control over tools and system prompt
- Pros: Maximum flexibility, can integrate with existing code
- Cons: More implementation work

Recommendation: Start with **Option B** for full control.

### State Management

The Agent needs to track:
- Current phase (MetaFlow or Workflow)
- Generated artifacts (paths to files)
- User confirmation status

Options:
- File-based: Write state to a JSON file
- In-memory: Pass through conversation context
- Hybrid: Key state in context, details in files

Recommendation: **Hybrid** - phase and status in context, artifacts in files.

### Error Handling

- **Document not found**: Agent should gracefully handle missing docs
- **Validation failure**: Agent should report specific errors and attempt fixes
- **User ambiguity**: Agent should ask clarifying questions

---

## Future Enhancements

### Phase 3: Script Generation (Separate Scope)

After Workflow generation, could add:
- Script generation for scraper_agent
- User review and modification of scripts
- This is a separate conversation loop within the workflow

### Execution Feedback

- Run workflow and capture results/errors
- Present execution feedback to user
- Allow modifications based on runtime behavior

### Version Control

- Track versions of MetaFlow and Workflow
- Allow user to revert to previous versions
- Compare changes between versions

---

## Summary

This design converts the Intent Builder from a single-shot generation system to an interactive agent-based system where:

1. **Users can review and modify** at both MetaFlow and Workflow stages
2. **Agent reads domain knowledge** from organized documentation
3. **Validation is automatic** but transparent
4. **Modifications are intelligent** - Agent decides between Edit and Write
5. **Context is preserved** throughout the conversation

The key benefit is **user control** - users can now shape the generated workflow to match their exact needs through natural conversation, rather than accepting whatever the single-shot generation produces.
