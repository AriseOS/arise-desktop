# base_agent/agents/

Agent implementations for the BaseAgent framework.

## Agent Types

### Core Agents (BaseStepAgent subclasses)

| File | Agent | Purpose |
|------|-------|---------|
| `text_agent.py` | TextAgent | LLM-based text generation, structured JSON output |
| `tool_agent.py` | ToolAgent | Tool calling with two-phase decision (select tool → select API) |
| `code_agent.py` | CodeAgent | Python code generation with AST safety checks |
| `browser_agent.py` | BrowserAgent | Page navigation + intelligent interaction (click/input/scroll) |
| `scraper_agent.py` | ScraperAgent | Data extraction with Plan-Generate-Execute pattern |
| `storage_agent.py` | StorageAgent | SQLite storage with LLM-generated SQL |
| `variable_agent.py` | VariableAgent | Variable manipulation and transformation |
| `autonomous_browser_agent.py` | AutonomousBrowserAgent | Self-directed browser automation |

### Infrastructure

| File | Purpose |
|------|---------|
| `base_agent.py` | BaseStepAgent abstract class |
| `agent_registry.py` | Agent type registration and discovery |
| `agent_executor.py` | Agent execution orchestration |
| `agent_router.py` | Inter-agent routing and communication |

## Common Pattern: Plan-Generate-Execute

Used by ScraperAgent, BrowserAgent, StorageAgent:

```
1. Plan: Analyze target (DOM/data structure)
2. Generate: LLM creates script (Python/SQL)
3. Execute: Run script with caching
4. Verify: Validate results
```

## Key Design Decisions

- **LLM generates scripts** - Adapts to actual page/data structure, not hardcoded
- **Script caching** - KV storage for reuse across similar pages
- **Verification** - Post-execution validation with retry/repair

## See Also

- `scraper_agent.py` - Reference implementation of Plan-Generate-Execute
- `browser_agent.py` - Intelligent DOM-based interaction
- `storage_agent.py` - LLM-generated SQL for flexible storage
