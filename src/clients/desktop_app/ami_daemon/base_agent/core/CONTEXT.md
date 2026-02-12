# base_agent/core/

Core framework components for BaseAgent. No CAMEL-AI dependency.

## Files

| File | Purpose |
|------|---------|
| `ami_tool.py` | AMITool - Lightweight tool wrapper, generates Anthropic-native schemas from type hints |
| `ami_agent.py` | AMIAgent - Core agent loop with tool calling, context truncation (no summarization) |
| `ami_browser_agent.py` | AMIBrowserAgent - Browser agent with Memory page operations support |
| `ami_task_planner.py` | Memory-First task decomposition (query Memory -> decompose -> assign guide) |
| `ami_task_executor.py` | Lightweight task executor (~250 lines, sequential with dependency resolution) |
| `agent_factories.py` | Factory functions to create configured agents (browser, developer, etc.) |
| `orchestrator_agent.py` | Top-level Orchestrator that decides task handling approach |
| `schemas.py` | Data structures (AgentContext, AgentResult, etc.) |
| `token_usage.py` | TokenUsage and SessionTokenUsage for LLM cost tracking |
| `cost_calculator.py` | Model pricing and cost calculation utilities |
| `budget_controller.py` | Budget enforcement during task execution |
| `task_router.py` | Routes tasks to appropriate specialized agents |

### Deleted Files
- `base_agent.py` - Old BaseAgent class (used MemoryManager, no longer needed)
- `agent_registry.py` - Old registry system (replaced by AMITaskPlanner routing)
- `listen_chat_agent.py` - Replaced by `ami_agent.py`
- `listen_browser_agent.py` - Replaced by `ami_browser_agent.py`
- `ami_model_backend.py` - Replaced by direct AnthropicProvider calls

## Architecture

### Agent Stack (No CAMEL)

```
AMITool (tool schema generation)
  -> AMIAgent (core loop, tool calling, context truncation)
     -> AMIBrowserAgent (Memory page ops, URL-triggered queries)
        -> AnthropicProvider (direct Anthropic API calls)
```

**Key difference from CAMEL**: No auto-summarization. When context grows too large,
old tool_result content is truncated (replaced with "[Truncated]") while conversation
structure is preserved. The LLM still sees WHAT it did, just not full page snapshots.

### Data Flow (Anthropic Native)

```
Toolkit -> AMITool(callable) -> Anthropic tool schema {"name", "description", "input_schema"}
Agent -> AMIAgent.astep() -> AnthropicProvider.generate_with_tools()
Response -> AMIAgentResponse(text, tool_calls, stop_reason)
```

No OpenAI intermediate format. Messages stored directly as Anthropic expects.

### Task Execution Pipeline

```
Orchestrator Agent (entry point)
-> AMITaskPlanner (Memory-First decomposition via AnthropicProvider)
   -> AMITaskExecutor (sequential execution)
      -> Specialized AMIAgent/AMIBrowserAgent instances
```

### Agent Factories

All agents created via factory functions in `agent_factories.py`:
- `create_listen_browser_agent()` -> AMIBrowserAgent (with Memory page ops)
- `create_developer_agent()` -> AMIAgent
- `create_document_agent()` -> AMIAgent
- `create_multi_modal_agent()` -> AMIAgent
- `create_social_medium_agent()` -> AMIAgent
- `create_task_summary_provider()` -> AnthropicProvider (direct, no agent)

Each factory:
1. Initializes required toolkits
2. Sets TaskState for SSE events
3. Builds system prompt with environment variables
4. Creates AnthropicProvider
5. Returns AMIAgent/AMIBrowserAgent

### Orchestrator Agent (Persistent Session)

Entry point for ALL user requests. Runs as a persistent `OrchestratorSession` loop:
1. **Direct Reply**: Simple questions, greetings
2. **Tool Use**: Single operations (search, terminal, file ops)
3. **decompose_task**: Spawn parallel executor for complex tasks (non-blocking)
4. **inject_message**: Forward message to running executor's child agent
5. **replan_task**: Replace pending subtasks of a running executor with a new plan
6. **cancel_task**: Cancel a specific running executor

Key classes:
- `OrchestratorSession`: Persistent loop (wait for event -> Orchestrator.astep() -> handle -> repeat)
- `ExecutorHandle`: Tracks running executor (executor_id, task_label, async_task)
- `InjectMessageTool` / `CancelTaskTool`: New tools for message routing and cancellation
- All SSE events carry `executor_id` + `task_label` for frontend executor tracking

### Memory Integration

**Two-layer Memory usage**:
- Layer 1 (Planner): PlannerAgent outputs MemoryPlan (coverage + preferences + uncovered), AMITaskPlanner uses it as context for _fine_grained_decompose, then assigns workflow_guide from coverage items to browser subtasks -> injected via AMITaskExecutor._build_prompt()
- Layer 2 (Runtime): page operations auto-queried per URL change -> auto-injected by AMIAgent._enrich_message()

**Decoupled responsibility**:
- PlannerAgent (Memory layer): only analyzes Memory coverage, outputs `<memory_plan>` XML
- AMITaskPlanner (Agent layer): receives MemoryPlan, does subtask decomposition with worker capabilities, assigns agent_type/depends_on
