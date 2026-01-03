# base_agent/agents/

Agent implementations for the BaseAgent framework.

## Agent Types

### Core Agents (BaseStepAgent subclasses)

| File | Agent | Purpose |
|------|-------|---------|
| `text_agent.py` | TextAgent | LLM-based text generation, structured JSON output |
| `tool_agent.py` | ToolAgent | Tool calling with two-phase decision (select tool -> select API) |
| `browser_agent.py` | BrowserAgent | Page navigation + intelligent interaction (click/input/scroll) |
| `scraper_agent.py` | ScraperAgent | Data extraction with Claude Agent SDK |
| `storage_agent.py` | StorageAgent | SQLite storage with LLM-generated SQL |
| `variable_agent.py` | VariableAgent | Variable manipulation and transformation |
| `autonomous_browser_agent.py` | AutonomousBrowserAgent | Self-directed browser automation |

### Infrastructure

| File | Purpose |
|------|---------|
| `base_agent.py` | BaseStepAgent abstract class |

## ScraperAgent Architecture

### Overview

ScraperAgent uses **Claude Agent SDK** to generate Python extraction scripts that parse DOM data. The key insight is that Claude Agent can iteratively analyze DOM structure using tools, write scripts, test them, and fix issues autonomously.

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
                                       │ 1. Setup Workspace│
                                       │    - Create dir   │
                                       │    - Copy skills  │
                                       │    - Save DOM     │
                                       └────────┬─────────┘
                                                │
                                       ┌────────▼─────────┐
                                       │ 2. Claude Agent   │
                                       │    - Read files   │
                                       │    - Use dom_tools│
                                       │    - Write script │
                                       │    - Test & fix   │
                                       └────────┬─────────┘
                                                │
                                       ┌────────▼─────────┐
                                       │ 3. Execute Script │
                                       │    - Load script  │
                                       │    - Run on DOM   │
                                       │    - Return data  │
                                       └──────────────────┘
```

### Key Components

1. **Workspace Setup** (`_generate_extraction_script_with_llm`)
   - Creates script directory: `~/.ami/users/{user}/workflows/{workflow}/{step}/scraper_script_{hash}/`
   - Copies skills from `base_app/.claude/skills/` to workspace
   - Saves `requirement.json` (user requirements) and `dom_data.json` (page DOM)

2. **Claude Agent SDK** (`ClaudeAgentProvider.run_task_stream`)
   - Uses `dom-extraction` skill for guidance
   - Tools available: `find`, `container`, `analyze`, `children`, `print`
   - Generates `extraction_script.py` with `extract_data_from_page(dom_dict)` function

3. **Script Execution** (`_execute_generated_script_direct`)
   - Wraps script in `execute_extraction()` function
   - Passes DOM dict (not HTML) to extraction function
   - Applies `max_items` limit if specified

### DOM Tools (`.claude/skills/dom-extraction/tools/dom_tools.py`)

Claude Agent uses these tools to analyze DOM structure:

| Command | Purpose | Virtual Container Support |
|---------|---------|---------------------------|
| `find <xpath>` | Find element by exact xpath match | No |
| `container <xpath>` | Build virtual container from children | Yes |
| `analyze <xpath>` | Analyze container structure (children count, tags) | Yes |
| `children <xpath> [tag]` | List children of container | Yes |
| `print <xpath> [depth]` | Print element structure | No |
| `fields <xpath>` | List available fields (text, href, src) count | Yes |
| `extract <xpath> <field>` | Extract all values of a field | Yes |

**Virtual Containers**: Container elements often don't have their own `xpath` attribute (filtered out during DOM serialization). The `container`, `analyze`, and `children` commands can build "virtual containers" by finding all child elements whose xpath starts with the given prefix.

### Script Caching

- Scripts cached by hash of `user_description` + `output_format`
- Path: `~/.ami/users/{user}/workflows/{workflow}/{step}/scraper_script_{hash}/extraction_script.py`
- Cached scripts reused across executions with same requirements

### Auto-Fix Feature

When `auto_fix_missing_fields: true`:
1. Check extraction result for missing/null fields
2. If missing, call Claude Agent to analyze why (data not in DOM vs script bug)
3. If script bug, Claude Agent fixes and re-executes

## Key Design Decisions

- **LLM generates scripts** - Adapts to actual page/data structure, not hardcoded
- **Script caching** - File-based cache for reuse across similar pages
- **Claude Agent SDK** - Iterative refinement with tool use, not single-shot generation
- **Skills system** - SKILL.md files guide Claude through complex tasks
- **Virtual containers** - Handle DOM structures where containers are filtered out
- **Simple dispatch** - Agents are created via `AGENT_TYPES` dict in engine

## Variable Agent Operations

| Operation | Purpose |
|-----------|---------|
| `set` | Initialize/combine variables |
| `filter` | Filter list by condition |
| `slice` | Slice list by index |

**Note**: Variable agent simplified to 3 operations. Output key is always `result`.

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
