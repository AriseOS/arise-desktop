# base_agent/core/

Core framework components for BaseAgent.

## Files

| File | Purpose |
|------|---------|
| `base_agent.py` | Main BaseAgent class - the container for agent execution |
| `schemas.py` | Data structures (AgentContext, AgentResult, etc.) |
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
| `orchestrator_agent.py` | **NEW** Top-level Orchestrator that decides task handling approach |

## Key Concepts

### Orchestrator Agent (NEW - LLM-driven Task Classification)

The Orchestrator Agent replaces hardcoded classification rules with LLM-powered decisions.
Instead of `_classify_task()` determining simple vs complex tasks, the Orchestrator decides:

1. **Direct Reply**: Simple questions, greetings, clarifications
2. **Tool Use**: Single operations (search, browse one page, read file)
3. **decompose_task**: Complex multi-step tasks requiring Workforce

```python
from .orchestrator_agent import create_orchestrator_agent, DecomposeTaskTool

# Create Orchestrator
orchestrator, decompose_tool = await create_orchestrator_agent(
    task_state=state,
    task_id=task_id,
    working_directory=working_directory,
    ...
)

# Run Orchestrator
response = await orchestrator.astep(user_message)

# Check if Workforce should be triggered
if decompose_tool.triggered:
    task_description = decompose_tool.task_description
    # Start Workforce execution...
else:
    # Use orchestrator's direct response
    reply = response.msg.content
```

### BaseAgent

Stateless container that:
- Manages agent lifecycle and tools
- Provides memory access (via user_id)
- Coordinates with BrowserManager for browser sessions

```python
agent = BaseAgent(config, user_id="user123", browser_manager=browser_manager)
await agent.initialize()
result = await agent.execute(task_input)
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

Carries state through task execution:
- `variables`: Dict of task variables
- `memory_manager`: Reference to MemoryManager
- `agent_instance`: Reference to BaseAgent

## AMIWorkforce (CAMEL-based)

CAMEL Workforce integration for multi-agent task coordination.
Ported from Eigent's Workforce pattern.

### Architecture

```
Orchestrator Agent (entry point)
├── Decides: direct reply / tool use / decompose_task
└── If decompose_task → triggers:

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
