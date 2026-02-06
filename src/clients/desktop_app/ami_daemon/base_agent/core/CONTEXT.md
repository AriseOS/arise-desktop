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
| `ami_task_planner.py` | Memory-First task decomposition (query Memory → decompose with context → assign guide) |
| `ami_task_executor.py` | **NEW** Lightweight task executor (~250 lines, replaces CAMEL Workforce) |
| `~~ami_workforce.py~~` | ❌ DELETED - Replaced by AMITaskExecutor |
| `~~ami_worker.py~~` | ❌ DELETED - No longer needed |
| `~~task_orchestrator.py~~` | ❌ DELETED - Replaced by Orchestrator Agent |
| `listen_chat_agent.py` | ChatAgent with SSE event emission (ported from Eigent) |
| `agent_factories.py` | Factory functions to create configured agents (browser_agent, etc.) |
| `orchestrator_agent.py` | **NEW** Top-level Orchestrator that decides task handling approach |

## Key Concepts

### Orchestrator Agent (LLM-driven Task Classification)

The Orchestrator Agent is the entry point for ALL user requests, replacing hardcoded classification logic with LLM-powered decision making.

**Decision Paths**:
1. **Direct Reply**: Simple questions, greetings, clarifications
2. **Tool Use**: Single operations (search, terminal commands, file operations)
3. **decompose_task**: Complex multi-step tasks → triggers AMITaskPlanner + AMITaskExecutor

**Available Tools**:
- `search_google`: Web search
- `shell_exec`: Terminal operations
- `write_note`, `read_note`: Note-taking for coordination
- `ask_human_via_console`: Ask user for clarification
- `decompose_task`: Trigger multi-agent task execution

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

# Check if decompose_task was triggered
if decompose_tool.triggered:
    task_description = decompose_tool.task_description
    # Start AMITaskPlanner → AMITaskExecutor pipeline
else:
    # Use orchestrator's direct response
    reply = response.msg.content
```

**System Prompt Structure**:
- Role definition (coordinator in multi-agent system)
- Team descriptions (Browser, Developer, Document, Social agents)
- Environment info (OS, working directory, date)
- Tool descriptions with usage guidelines
- Critical instruction: Don't expand user's request in decompose_task

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

## AMI Task Execution Pipeline (Replaces CAMEL Workforce)

Lightweight, controllable multi-agent task execution system.

### Architecture

```
Orchestrator Agent (entry point)
├── Decides: direct reply / tool use / decompose_task
└── If decompose_task → triggers:

AMITaskPlanner (Memory-First 分解)
├── Step 1: Query Memory for whole task (single query)
├── Step 2: Inject Memory context into decompose prompt
├── Step 3: Fine-grained decompose (1-2 tool calls each)
├── Step 4: Assign workflow_guide to browser subtasks (whole injection)
└── Returns: List[AMISubtask]

AMITaskExecutor (顺序执行)
├── Resolves dependencies
├── Builds prompt with workflow_guide as explicit instruction
├── Routes to specialized agents via factories
├── Emits SSE events (SubtaskStateData, AgentReportData)
└── Returns: Aggregated results

Specialized Agents (created via factories)
├── BrowserAgent / ListenBrowserAgent
├── DeveloperAgent
├── DocumentAgent
├── SocialMediumAgent
└── MultiModalAgent
```

### Key Improvements vs CAMEL Workforce

| Aspect | CAMEL Workforce | AMI Executor |
|--------|-----------------|--------------|
| Code size | ~6000 lines | ~650 lines |
| Prompt control | Fixed template | Direct control |
| workflow_guide | metadata (additional_info) | Explicit instruction |
| Complexity | Agent Pool, worker clone, coordinator | Simple sequential execution |
| Debuggability | Complex node matching | Straightforward logic |

### Usage

```python
from .ami_task_planner import AMITaskPlanner
from .ami_task_executor import AMITaskExecutor
from .agent_factories import (
    create_browser_agent,
    create_developer_agent,
    create_document_agent,
)

# 1. Decompose task
planner = AMITaskPlanner(task_state, memory_toolkit, llm_config)
subtasks = await planner.decompose(user_request)

# 2. Create agents
agents = {
    "browser": create_browser_agent(task_state, task_id, ...),
    "code": create_developer_agent(task_state, task_id, ...),
    "document": create_document_agent(task_state, task_id, ...),
}

# 3. Execute
executor = AMITaskExecutor(task_id, task_state, agents, user_request)
results = await executor.execute(subtasks)
```

### SSE Events

| Event | Trigger | Data |
|-------|---------|------|
| `task_decomposed` | After decomposition complete | List of subtasks |
| `subtask_state` | Subtask state change | RUNNING/DONE/FAILED |
| `agent_report` | Agent starts executing | "Executing: {task_name}" |
| `assign_task` | Task assigned to agent | Task details |
| `agent_thinking` | LLM is processing | Thinking state |
