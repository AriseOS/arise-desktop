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
| `ami_workforce.py` | CAMEL-based Workforce (task decomposition + worker management) |
| `ami_worker.py` | Worker wrapper for agents (AMISingleAgentWorker) |
| `listen_chat_agent.py` | ChatAgent with SSE event emission (ported from Eigent) |
| `agent_factories.py` | Factory functions to create configured agents (browser_agent, etc.) |

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

## AMIWorkforce (CAMEL-based)

CAMEL Workforce integration for multi-agent task coordination.
Ported from Eigent's Workforce pattern.

### Architecture

```
AMIWorkforce (extends CAMEL Workforce)
├── task_agent: LLM for task decomposition
├── pending_tasks: CAMEL TaskChannel
├── workers:
│   └── AMISingleAgentWorker → ListenChatAgent (with toolkits)
└── failure_handling: retry + replan (CAMEL built-in)
```

### Usage

```python
from .ami_workforce import AMIWorkforce
from .ami_worker import AMISingleAgentWorker
from .agent_factories import create_browser_agent

# Create Workforce
workforce = AMIWorkforce(task_id, task_state, ...)

# Create browser agent using factory (Eigent pattern)
browser_agent = create_browser_agent(
    task_state=state,
    task_id=task_id,
    working_directory=working_directory,
    ...
)

# Create worker wrapping the ListenChatAgent
worker = AMISingleAgentWorker(
    description="Web research",
    worker=browser_agent,
    task_state=state,
)
workforce.add_single_agent_worker(worker)

# Decompose and execute
subtasks = await workforce.decompose_task(task)
await workforce.start_with_subtasks(subtasks)
```

### SSE Events

| Event | Trigger |
|-------|---------|
| `streaming_decompose` | During task decomposition |
| `task_decomposed` | After decomposition complete |
| `subtask_state` | Subtask state change (RUNNING/DONE/FAILED) |
| `workforce_started` | Workforce begins |
| `workforce_completed` | All tasks done |
| `worker_assigned` | Task assigned to worker |
| `dynamic_tasks_added` | New subtasks discovered |
