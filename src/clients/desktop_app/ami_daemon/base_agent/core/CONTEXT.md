# base_agent/core/

Core framework components for BaseAgent.

## Files

| File | Purpose |
|------|---------|
| `base_agent.py` | Main BaseAgent class - the container that executes workflows |
| `workflow_engine.py` | Workflow execution engine with Agent dispatch |
| `schemas.py` | Data structures (AgentContext, AgentResult, WorkflowStep, etc.) |

## Key Concepts

### BaseAgent

Stateless container that:
- Loads and executes workflows
- Provides memory access (via user_id)

```python
agent = BaseAgent(config, user_id="user123")
result = await agent.run_workflow(workflow, input_data)
```

### WorkflowEngine

Executes workflow steps with:
- Agent type dispatch via `AGENT_TYPES` dict
- Conditional execution (`if/else`)
- Loop control (`while`, `foreach`)
- Variable passing via template syntax `{{variable_name}}`
- Single-step execution support (`execute_step()`)
- Resume from step (`execute_workflow_from()`)

```python
AGENT_TYPES = {
    'text_agent': TextAgent,
    'variable': VariableAgent,
    'scraper_agent': ScraperAgent,
    'storage_agent': StorageAgent,
    'browser_agent': BrowserAgent,
    'autonomous_browser_agent': AutonomousBrowserAgent,
}
```

### AgentContext

Carries state through workflow execution:
- `variables`: Dict of workflow variables
- `memory_manager`: Reference to MemoryManager
- `agent_instance`: Reference to BaseAgent

## Workflow Execution Flow

```
1. Parse YAML → List[WorkflowStep]
2. Initialize AgentContext
3. For each step:
   a. Resolve templates in parameters
   b. Create Agent instance from AGENT_TYPES
   c. Execute agent
   d. Store outputs in context
4. Return final result
```

## Single-Step Execution

For debugging or testing individual steps:

```python
engine = WorkflowEngine(agent)

# Execute single step with provided variables
result = await engine.execute_step(
    step=some_step,
    variables={"url": "https://example.com"}
)

# Execute workflow from specific step
result = await engine.execute_workflow_from(
    steps=workflow.steps,
    start_from="scrape",
    variables={"category_url": "https://example.com/products"}
)
```
