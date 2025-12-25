# base_agent/core/

Core framework components for BaseAgent.

## Files

| File | Purpose |
|------|---------|
| `base_agent.py` | Main BaseAgent class - the container that executes workflows |
| `agent_workflow_engine.py` | Workflow execution engine with step routing |
| `schemas.py` | Data structures (AgentContext, AgentResult, WorkflowStep, etc.) |
| `state_manager.py` | State persistence across workflow execution |
| `workflow_builder.py` | Programmatic workflow construction |

## Key Concepts

### BaseAgent

Stateless container that:
- Loads and executes workflows
- Manages agent registry
- Provides memory access (via user_id)

```python
agent = BaseAgent(config, user_id="user123")
result = await agent.run_workflow(workflow, input_data)
```

### AgentWorkflowEngine

Executes workflow steps sequentially with:
- Agent type routing (text_agent, tool_agent, scraper_agent, etc.)
- Conditional execution (`if/else`)
- Loop control (`while`, `foreach`)
- Variable passing via template syntax `{{variable_name}}`

### AgentContext

Carries state through workflow execution:
- `variables`: Dict of workflow variables
- `memory`: Reference to MemoryManager
- `history`: Execution trace

## Workflow Execution Flow

```
1. Parse YAML → List[WorkflowStep]
2. Initialize AgentContext
3. For each step:
   a. Resolve templates in parameters
   b. Route to appropriate agent
   c. Execute agent
   d. Store outputs in context
4. Return final result
```
