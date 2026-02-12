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
| `text_agent.py` | TextAgent | `inputs.instruction` |
| `browser_agent.py` | BrowserAgent | `inputs.target_url` or `inputs.interaction_steps` |
| `scraper_agent.py` | ScraperAgent | `inputs.data_requirements` |
| `storage_agent.py` | StorageAgent | `inputs.operation`, `inputs.collection` |
| `variable_agent.py` | VariableAgent | `inputs.operation`, `inputs.data` |
| `autonomous_browser_agent.py` | AutonomousBrowserAgent | `inputs.task` |
| `tavily_agent.py` | TavilyAgent | `inputs.operation`, `inputs.query` |

### Specialized Agents (Eigent Migration)

| File | Agent | Purpose |
|------|-------|---------|
| `question_confirm_agent.py` | QuestionConfirmAgent | Human-in-the-loop confirmations and Q&A |
| `developer_agent.py` | DeveloperAgent | Coding, debugging, git operations |
| `document_agent.py` | DocumentAgent | Google Drive, Notion, document creation |
| `social_medium_agent.py` | SocialMediumAgent | Email (Gmail), calendar, communication |

These agents are used by `TaskOrchestrator` for multi-agent coordination.

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
- Path: `~/.ami/users/{user}/workflows/{workflow}/{step}/extraction_script.py`
- Scripts stored directly in step directory (no hash subdirectory)
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

## BrowserAgent Tab Operations

BrowserAgent supports multi-tab workflows via the `action` field in `interaction_steps`:

### Supported Tab Actions

| Action | Required Fields | Description |
|--------|-----------------|-------------|
| `new_tab` | `url` | Open URL in a new browser tab |
| `switch_tab` | `tab_index` | Switch to tab by index (0 = first tab) |
| `close_tab` | `tab_index` (optional) | Close tab by index, or current tab if not specified |

### Usage Example

```yaml
interaction_steps:
  - task: "Open competitor site in new tab"
    action: "new_tab"
    url: "https://competitor.com/product"

  - task: "Switch back to original tab"
    action: "switch_tab"
    tab_index: 0

  - task: "Close current tab"
    action: "close_tab"
```

### Implementation Details

- **Tab Tracking**: Initial tabs are recorded at workflow start (`_initial_tab_ids`)
- **Auto Cleanup**: Extra tabs opened during workflow are automatically closed on completion
- **Output**: Response includes `current_tab_index` and `open_tabs_count`
- **Events Used**: `NavigateToUrlEvent(new_tab=True)`, `SwitchTabEvent`, `CloseTabEvent` from browser-use

### Key Methods

| Method | Purpose |
|--------|---------|
| `_get_open_tabs()` | Returns list of open tabs with tab_id, url, title |
| `_execute_new_tab(url, context)` | Opens URL in new tab |
| `_execute_switch_tab(tab_index, context)` | Switches to tab by index |
| `_execute_close_tab(tab_index, context)` | Closes tab (None = current tab) |
| `_cleanup_extra_tabs()` | Closes tabs not in initial set |

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
| `tavily_agent.py` | `src/cloud_backend/services/skills/repository/agent-specs/SKILL.md` |

Also update `docs/base_app/*_agent_spec.md` (source of truth for specs).

## EigentStyleBrowserAgent

Full Tool-calling architecture browser agent ported from CAMEL-AI/Eigent. Uses Anthropic tool_use API with complete Toolkit system:

- **SearchToolkit** - Web search
- **TerminalToolkit** - Terminal commands
- **HumanToolkit** - Human-in-the-loop
- **BrowserToolkit** - Browser operations
- **MemoryToolkit** - Memory system integration
- **TaskPlanningToolkit** - Task planning and tracking

### Key Components

- **PageSnapshot** (`tools/eigent_browser/page_snapshot.py`) - DOM → YAML-like snapshot
- **ActionExecutor** (`tools/eigent_browser/action_executor.py`) - Execute browser actions
- **HybridBrowserSession** (`tools/eigent_browser/browser_session.py`) - Multi-tab browser management
- **unified_analyzer.js** - JS script for DOM analysis and element ref assignment
