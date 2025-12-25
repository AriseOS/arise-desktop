# ami_daemon/base_app/

BaseAgent framework - the core agent runtime for Ami.

## Architecture

Three-layer design: **BaseAgent Core** + **Workflow Engine** + **Step-as-Agent Execution**

```
AgentWorkflowEngine
├── AgentRegistry - Manages available agent types
├── AgentExecutor - Handles agent execution
├── AgentRouter - Routes between agents
└── ConditionEvaluator - Evaluates conditions
```

## Directories (see each CONTEXT.md for details)

- `base_app/base_agent/core/` - Core framework (BaseAgent, workflow engine, schemas)
- `base_app/base_agent/agents/` - Agent implementations (TextAgent, ToolAgent, ScraperAgent, etc.)
- `base_app/base_agent/tools/` - Tool integrations (browser, memory)
- `base_app/base_agent/workflows/` - YAML workflow definitions
- `base_app/base_agent/memory/` - Three-layer memory system

## Built-in Agent Types

- **TextAgent** - LLM-based text generation, structured JSON output
- **ToolAgent** - Tool calling with two-phase decision (select tool, then API)
- **CodeAgent** - Python code generation with AST safety checks
- **ScraperAgent** - Plan-Generate-Exec pattern for web scraping

## Workflow Configuration

YAML-driven with support for:
- Conditionals (`if/else`)
- Loops (`while`, `foreach`)
- Variable passing (`{{variable_name}}`)

## Memory Architecture

**Core Principle**: Memory binds to users, not BaseAgent instances.

```python
# Correct: specify user_id for memory persistence
agent = BaseAgent(config, user_id="user123")

# Multiple instances share same user's memory
agent1 = BaseAgent(..., user_id="user123")
agent2 = BaseAgent(..., user_id="user123")
```

## Key Entry Points

- `base_app/base_agent/core/base_agent.py` - Main BaseAgent class
- `base_app/base_agent/core/agent_workflow_engine.py` - Workflow engine
- `base_app/base_agent/agents/` - All agent implementations
