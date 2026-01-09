# base_agent/agents/

Agent implementations for the BaseAgent framework.

## INPUT_SCHEMA System

Each agent defines an `INPUT_SCHEMA` that specifies its input requirements. This enables:
1. **Automatic validation** - `BaseStepAgent.validate_input()` validates against schema
2. **Documentation generation** - Schema fields include descriptions and examples
3. **Workflow builder integration** - Intent Builder can query agent schemas

```python
# Get schema for a specific agent
from src.clients.desktop_app.ami_daemon.base_agent.agents import StorageAgent
schema = StorageAgent.get_input_schema()
print(schema.fields)  # {'operation': FieldSchema(...), 'collection': FieldSchema(...), ...}

# Get all agent schemas
from src.clients.desktop_app.ami_daemon.base_agent.agents import get_all_agent_schemas
all_schemas = get_all_agent_schemas()
```

## Agent Types

### Core Agents (BaseStepAgent subclasses)

| File | Agent | Required Inputs |
|------|-------|-----------------|
| `text_agent.py` | TextAgent | `instruction` |
| `browser_agent.py` | BrowserAgent | (none, uses `target_url` or `interaction_steps`) |
| `scraper_agent.py` | ScraperAgent | `data_requirements` |
| `storage_agent.py` | StorageAgent | `operation`, `collection` |
| `variable_agent.py` | VariableAgent | `operation`, `data` |
| `autonomous_browser_agent.py` | AutonomousBrowserAgent | `task` |

### Infrastructure

| File | Purpose |
|------|---------|
| `base_agent.py` | BaseStepAgent abstract class with `InputSchema`, `FieldSchema` |

## ScraperAgent Architecture

### Overview

ScraperAgent calls **cloud API** to generate Python extraction scripts that parse DOM data. Script generation runs on the cloud backend using Claude Agent SDK.

### Workflow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ScraperAgent.execute()                        │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
            [Script Cached?]                [No Cache]
                    │                             │
                    ▼                             ▼
           Load & Execute              ┌──────────────────┐
                                       │ 1. Call Cloud API │
                                       │    - POST /generate-script
                                       │    - Send step_id, page_url
                                       │    - Cloud uses DOM from recording
                                       └────────┬─────────┘
                                                │
                                       ┌────────▼─────────┐
                                       │ 2. Cloud Backend  │
                                       │    - Claude Agent │
                                       │    - Generate script
                                       │    - Return content
                                       └────────┬─────────┘
                                                │
                                       ┌────────▼─────────┐
                                       │ 3. Execute Script │
                                       │    - Save locally │
                                       │    - Run on DOM   │
                                       │    - Return data  │
                                       └──────────────────┘
```

### Key Components

1. **Cloud API Call** (`cloud_client.generate_script`)
   - Sends `workflow_id`, `step_id`, `script_type`, `page_url`
   - Cloud has DOM snapshots from recording, no need to upload
   - Returns generated script content

2. **Cloud Backend** (runs Claude Agent SDK)
   - Uses `dom-extraction` skill for guidance
   - Generates `extraction_script.py` with `extract_data_from_page(dom_dict)` function

3. **Script Execution** (`_execute_generated_script_direct`)
   - Wraps script in `execute_extraction()` function
   - Passes DOM dict (not HTML) to extraction function
   - Applies `max_items` limit if specified

### Script Caching

- Scripts cached locally after first cloud generation
- Path: `~/.ami/users/{user}/workflows/{workflow}/{step}/scraper_script_{hash}/extraction_script.py`
- Cached scripts reused across executions with same requirements

## Key Design Decisions

- **Cloud-based script generation** - Claude Agent SDK runs on cloud, desktop app only executes scripts
- **Script caching** - File-based cache for reuse across similar pages
- **Skills system** - SKILL.md files guide Claude through complex tasks (on cloud)
- **Simple dispatch** - Agents are created via `AGENT_TYPES` dict in engine

## Variable Agent Operations

| Operation | Purpose |
|-----------|---------|
| `set` | Initialize/combine variables |
| `filter` | Filter list by condition |
| `slice` | Slice list by index |
| `extend` | Extend list with new elements |

**Note**: Output key is always `result` for consistent workflow mapping.

## See Also

- `scraper_agent.py` - Main implementation
- `base_app/.claude/skills/dom-extraction/` - DOM extraction skill
- `tools/browser_use/dom_extractor.py` - DOM serialization logic
- `browser_agent.py` - Intelligent DOM-based interaction
- `storage_agent.py` - LLM-generated SQL for flexible storage

## Skills Synchronization

**IMPORTANT**: When modifying agent behavior (inputs, outputs, capabilities), update the corresponding Skills:

| Agent | Skill to Update |
|-------|-----------------|
| `browser_agent.py` | `src/cloud_backend/intent_builder/.claude/skills/agent-specs/references/browser_agent.md` |
| `scraper_agent.py` | `src/cloud_backend/intent_builder/.claude/skills/agent-specs/references/scraper_agent.md` |
| `storage_agent.py` | `src/cloud_backend/intent_builder/.claude/skills/agent-specs/references/storage_agent.md` |

Also update `docs/base_app/*_agent_spec.md` (source of truth for specs).
