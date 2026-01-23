# base_agent/core/

Core framework components for BaseAgent.

## Files

| File | Purpose |
|------|---------|
| `base_agent.py` | Main BaseAgent class - the container that executes workflows |
| `workflow_engine.py` | Workflow execution engine with Agent dispatch |
| `schemas.py` | Data structures (AgentContext, AgentResult, WorkflowStep, etc.) |
| `token_usage.py` | TokenUsage and SessionTokenUsage for LLM cost tracking |
| `cost_calculator.py` | Model pricing and cost calculation utilities |
| `budget_controller.py` | Budget enforcement during task execution |
| `agent_registry.py` | Central agent registration and lookup |
| `task_router.py` | Routes tasks to appropriate specialized agents |
| `task_orchestrator.py` | Multi-agent task coordination (Eigent Workforce pattern) |

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

### Budget Management (Eigent Migration)

Track LLM token usage and enforce budgets:

```python
from .token_usage import TokenUsage, SessionTokenUsage
from .budget_controller import BudgetController, BudgetConfig

# Configure budget
config = BudgetConfig(max_total_cost=10.0, max_input_tokens=500000)
controller = BudgetController(config)

# Record usage
usage = TokenUsage(input_tokens=1000, output_tokens=500, model="claude-sonnet-4-5-20250929")
controller.record_usage(usage)

# Check remaining budget
print(f"Remaining: ${controller.remaining_budget}")
```

### Agent Registry and Task Router (Eigent Migration)

Central registry for specialized agents:

```python
from .agent_registry import AgentType, get_registry, create_agent
from .task_router import TaskRouter

# Create agent by type
agent = create_agent(AgentType.BROWSER)

# Route task to appropriate agent
router = TaskRouter()
result = router.route("Send email to john@example.com")
# result.agent_type = "social_medium_agent"
```

### TaskOrchestrator (Eigent Workforce Pattern)

Coordinates multi-agent task execution:

```python
from .task_orchestrator import TaskOrchestrator, OrchestratorConfig

config = OrchestratorConfig(max_concurrent_tasks=3)
orchestrator = TaskOrchestrator(task_id="task_123", config=config)

result = await orchestrator.execute(
    "Research AI trends and write a summary document"
)
# Decomposes task, assigns to browser_agent and document_agent
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
