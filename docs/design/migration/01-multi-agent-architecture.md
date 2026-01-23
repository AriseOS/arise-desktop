# Multi-Agent Architecture Migration Guide

## Overview

This document describes how to migrate Eigent's multi-agent architecture (based on CAMEL framework) to the 2ami system.

## Eigent's Current Architecture

### 1. Agent Types (from `third-party/eigent/backend/app/service/task.py`)

Eigent defines 5 specialized agents:

```python
# Agent type definitions
browser_agent = "browser_agent"      # Web automation and browser interactions
developer_agent = "developer_agent"  # Development tasks and coding operations
document_agent = "document_agent"    # Document management and processing
social_medium_agent = "social_medium_agent"  # Social media interactions
question_confirm_agent = "question_confirm_agent"  # Human confirmation and Q&A
```

### 2. Core Components

#### ListenChatAgent (`third-party/eigent/backend/app/utils/agent.py`)

The base agent class that extends CAMEL's ChatAgent with:
- Event emission through `task_lock.put_queue()`
- Budget tracking via `ModelProcessingError` exception handling
- Tool execution monitoring via `@listen_toolkit` decorator

```python
class ListenChatAgent(ChatAgent):
    def __init__(self, api_task_id: str, agent_id: str, ...):
        self.api_task_id = api_task_id
        self.agent_id = agent_id
        # Sends ActionCreateAgentData event on creation
        asyncio.create_task(task_lock.put_queue(ActionCreateAgentData(...)))

    def step(self, input_message, response_format=None):
        try:
            # Send activation event
            asyncio.create_task(task_lock.put_queue(ActionActivateAgentData(...)))
            res = super().step(input_message, response_format)
        except ModelProcessingError as e:
            if "Budget has been exceeded" in str(e):
                asyncio.create_task(task_lock.put_queue(ActionBudgetNotEnough()))
        return res
```

#### Workforce (`third-party/eigent/backend/app/utils/workforce.py`)

Multi-agent orchestration extending CAMEL's Workforce:
- Task decomposition via `eigent_make_sub_tasks()`
- Task assignment via `_find_assignee()`
- Progress tracking via action events

### 3. Event System

Events are defined in `task.py`:

```python
class Action(str, Enum):
    create_agent = "create_agent"
    activate_agent = "activate_agent"
    assign_task = "assign_task"
    task_state = "task_state"
    budget_not_enough = "budget_not_enough"
    end = "end"

@dataclass
class ActionCreateAgentData:
    action: Action = Action.create_agent
    data: dict = field(default_factory=dict)
    # data = {"agent_id": ..., "agent_type": ..., "description": ...}

@dataclass
class ActionActivateAgentData:
    action: Action = Action.activate_agent
    data: dict = field(default_factory=dict)
    # data = {"agent_id": ..., "tool_name": ..., "tool_input": ...}
```

---

## Migration Plan for 2ami

### Phase 1: Create Specialized Agent Classes

Create new agent types inheriting from `BaseStepAgent`:

```
src/clients/desktop_app/ami_daemon/base_agent/agents/
├── __init__.py                    # Update to export new agents
├── question_confirm_agent.py      # NEW
├── developer_agent.py             # NEW
├── document_agent.py              # NEW
├── social_medium_agent.py         # NEW
└── eigent_style_browser_agent.py  # Already exists (browser_agent)
```

#### 1.1 QuestionConfirmAgent

Handles human-in-the-loop confirmations and Q&A.

```python
# src/clients/desktop_app/ami_daemon/base_agent/agents/question_confirm_agent.py

from .base_agent import BaseStepAgent, AgentMetadata, InputSchema, FieldSchema
from ..core.schemas import AgentContext, AgentInput, AgentOutput
from ..tools.toolkits import HumanToolkit

QUESTION_CONFIRM_SYSTEM_PROMPT = """
You are a Question Confirmation Agent responsible for:
1. Clarifying ambiguous user requests
2. Confirming critical actions before execution
3. Gathering additional information when needed
4. Presenting options and collecting user decisions

When you need user input, use the ask_human tool with clear, concise questions.
Always provide context about why you're asking.
"""

class QuestionConfirmAgent(BaseStepAgent):
    INPUT_SCHEMA = InputSchema(
        description="Agent for human confirmation and Q&A interactions",
        fields={
            "question": FieldSchema(type="str", required=True, description="Question to ask"),
            "context": FieldSchema(type="str", required=False, description="Context for the question"),
            "options": FieldSchema(type="list", required=False, description="Options to present"),
        }
    )

    def __init__(self):
        metadata = AgentMetadata(
            name="question_confirm_agent",
            description="Handles human-in-the-loop confirmations and Q&A",
            version="1.0.0",
            tags=["human", "confirmation", "qa"],
        )
        super().__init__(metadata)
        self._human_toolkit = None

    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        # Initialize HumanToolkit and handle the interaction
        ...
```

#### 1.2 DeveloperAgent

Handles coding tasks and development operations.

```python
# src/clients/desktop_app/ami_daemon/base_agent/agents/developer_agent.py

DEVELOPER_SYSTEM_PROMPT = """
You are a Senior Developer Agent responsible for:
1. Writing, modifying, and reviewing code
2. Understanding codebases and architectural patterns
3. Debugging and fixing issues
4. Creating tests and documentation

Available tools:
- Terminal: Execute shell commands (git, npm, pip, etc.)
- File operations: Read, write, and edit files
- Search: Find code patterns and definitions

Always explain your reasoning before making changes.
Follow best practices and the existing code style.
"""

class DeveloperAgent(BaseStepAgent):
    # Uses TerminalToolkit, FileToolkit (new), SearchToolkit
    ...
```

#### 1.3 DocumentAgent

Handles document processing and management.

```python
# src/clients/desktop_app/ami_daemon/base_agent/agents/document_agent.py

DOCUMENT_SYSTEM_PROMPT = """
You are a Document Management Agent responsible for:
1. Creating, editing, and organizing documents
2. Extracting information from documents
3. Converting between document formats
4. Managing document metadata

You have access to Google Drive and Notion for cloud document operations.
"""

class DocumentAgent(BaseStepAgent):
    # Uses NoteTakingToolkit, GoogleDriveMCPToolkit (new), NotionMCPToolkit (new)
    ...
```

### Phase 2: Create Agent Registry and Router

#### 2.1 Agent Registry

```python
# src/clients/desktop_app/ami_daemon/base_agent/core/agent_registry.py

from typing import Dict, Type
from ..agents import (
    EigentStyleBrowserAgent,
    QuestionConfirmAgent,
    DeveloperAgent,
    DocumentAgent,
    SocialMediumAgent,
)

AGENT_REGISTRY: Dict[str, Type[BaseStepAgent]] = {
    "browser_agent": EigentStyleBrowserAgent,
    "question_confirm_agent": QuestionConfirmAgent,
    "developer_agent": DeveloperAgent,
    "document_agent": DocumentAgent,
    "social_medium_agent": SocialMediumAgent,
}

def get_agent_for_task(task_type: str) -> Type[BaseStepAgent]:
    """Get the appropriate agent class for a task type."""
    return AGENT_REGISTRY.get(task_type, EigentStyleBrowserAgent)
```

#### 2.2 Task Router Agent

```python
# src/clients/desktop_app/ami_daemon/base_agent/agents/task_router_agent.py

TASK_ROUTER_SYSTEM_PROMPT = """
You are a Task Router that analyzes user requests and assigns them to specialized agents.

Available agents:
- browser_agent: Web automation, research, data collection
- developer_agent: Coding, debugging, git operations
- document_agent: Document creation, Google Drive, Notion
- social_medium_agent: Email, social media interactions
- question_confirm_agent: User confirmations and Q&A

Analyze the task and return the most appropriate agent type.
"""

class TaskRouterAgent(BaseStepAgent):
    """Routes tasks to appropriate specialized agents."""

    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        task = input_data.get("task", "")

        # Use LLM to determine best agent
        agent_type = await self._determine_agent_type(task)

        return AgentOutput(
            success=True,
            data={"agent_type": agent_type, "task": task}
        )
```

### Phase 3: Implement Workforce-like Orchestration

#### 3.1 TaskOrchestrator

```python
# src/clients/desktop_app/ami_daemon/base_agent/core/task_orchestrator.py

from typing import List, Dict, Any
from dataclasses import dataclass
from enum import Enum

class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class SubTask:
    id: str
    content: str
    state: TaskState
    assigned_agent: str
    dependencies: List[str]
    result: Any = None

class TaskOrchestrator:
    """Orchestrates multi-agent task execution."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.subtasks: List[SubTask] = []
        self.agents: Dict[str, BaseStepAgent] = {}
        self._event_queue: asyncio.Queue = asyncio.Queue()

    async def decompose_task(self, task: str) -> List[SubTask]:
        """Use LLM to decompose task into subtasks."""
        # Similar to Eigent's _decompose_task
        ...

    async def assign_task(self, subtask: SubTask) -> str:
        """Assign subtask to appropriate agent."""
        router = TaskRouterAgent()
        result = await router.execute({"task": subtask.content}, context)
        return result.data["agent_type"]

    async def execute(self, task: str) -> Any:
        """Execute the full orchestration workflow."""
        # 1. Decompose task
        subtasks = await self.decompose_task(task)

        # 2. Assign agents
        for subtask in subtasks:
            subtask.assigned_agent = await self.assign_task(subtask)

        # 3. Execute with dependency resolution
        return await self._execute_with_dependencies(subtasks)
```

### Phase 4: Event System Integration

#### 4.1 Event Types

```python
# src/clients/desktop_app/ami_daemon/base_agent/events/event_types.py

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict

class EventType(str, Enum):
    AGENT_CREATED = "agent_created"
    AGENT_ACTIVATED = "agent_activated"
    TASK_ASSIGNED = "task_assigned"
    TASK_STATE_CHANGED = "task_state_changed"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    BUDGET_EXCEEDED = "budget_exceeded"
    ORCHESTRATION_ENDED = "orchestration_ended"

@dataclass
class AgentEvent:
    event_type: EventType
    task_id: str
    agent_id: str
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)
```

#### 4.2 Event Emitter Mixin

```python
# src/clients/desktop_app/ami_daemon/base_agent/events/event_emitter.py

import asyncio
from typing import Optional, Callable

class EventEmitterMixin:
    """Mixin for agents to emit events."""

    _event_queue: Optional[asyncio.Queue] = None
    _event_callback: Optional[Callable] = None

    def set_event_queue(self, queue: asyncio.Queue):
        self._event_queue = queue

    def set_event_callback(self, callback: Callable):
        self._event_callback = callback

    async def emit_event(self, event: AgentEvent):
        if self._event_queue:
            await self._event_queue.put(event)
        if self._event_callback:
            if asyncio.iscoroutinefunction(self._event_callback):
                await self._event_callback(event)
            else:
                self._event_callback(event)
```

---

## File Changes Required

### New Files to Create

```
src/clients/desktop_app/ami_daemon/base_agent/
├── agents/
│   ├── question_confirm_agent.py   # NEW
│   ├── developer_agent.py          # NEW
│   ├── document_agent.py           # NEW
│   └── social_medium_agent.py      # NEW
├── core/
│   ├── agent_registry.py           # NEW
│   └── task_orchestrator.py        # NEW
└── events/
    ├── __init__.py                 # UPDATE
    ├── event_types.py              # NEW
    └── event_emitter.py            # NEW
```

### Files to Modify

1. `src/clients/desktop_app/ami_daemon/base_agent/agents/__init__.py`
   - Export new agent classes

2. `src/clients/desktop_app/ami_daemon/base_agent/agents/base_agent.py`
   - Add EventEmitterMixin

3. `src/clients/desktop_app/ami_daemon/routers/quick_task.py`
   - Add support for multi-agent routing

---

## Implementation Priority

1. **Phase 1.1**: QuestionConfirmAgent (high priority - enables human-in-the-loop)
2. **Phase 1.2**: DeveloperAgent (medium priority - coding tasks)
3. **Phase 2**: Agent Registry (high priority - required for routing)
4. **Phase 3**: TaskOrchestrator (medium priority - enables complex workflows)
5. **Phase 4**: Event System (low priority - enhancement)

---

## Testing Strategy

1. Unit tests for each new agent
2. Integration tests for agent routing
3. E2E tests for multi-agent workflows
4. Performance tests for orchestration overhead

---

## References

- Eigent source: `third-party/eigent/backend/app/`
- CAMEL framework: https://github.com/camel-ai/camel
- Current 2ami agents: `src/clients/desktop_app/ami_daemon/base_agent/agents/`
