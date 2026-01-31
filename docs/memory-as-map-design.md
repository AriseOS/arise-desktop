# Memory as Map: Simplified Memory Usage Design

## 1. Core Philosophy

**Memory is a Tool, Agent is the Decision Maker.**

```
Memory provides information.
Agent decides what to do with it.
```

---

## 2. Three Query Interfaces

Memory provides three simple query interfaces. Agent can call any of them at any time.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Memory Three Interfaces                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. query_cognitive_phrase(task) → CognitivePhrase | None                    │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  Query: Is there a user-recorded complete workflow for this task?      │ │
│  │                                                                        │ │
│  │  Returns:                                                              │ │
│  │    - CognitivePhrase with state_path + action_path                    │ │
│  │    - Or None if not found                                             │ │
│  │                                                                        │ │
│  │  Example:                                                              │ │
│  │    query_cognitive_phrase("View team info on Product Hunt")           │ │
│  │    → CognitivePhrase:                                                 │ │
│  │        states: [Homepage, Leaderboard, ProductDetail, TeamSection]    │ │
│  │        actions: [ClickNav, ClickProduct, ClickTeamTab]                │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  2. query_path(task) → Path | None                                           │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  Query: Can Memory find a path to reach the goal?                      │ │
│  │                                                                        │ │
│  │  Returns:                                                              │ │
│  │    - Path with states + actions (retrieved from graph)                │ │
│  │    - Or None if no path found                                         │ │
│  │                                                                        │ │
│  │  Example:                                                              │ │
│  │    query_path("Find pricing page on example.com")                     │ │
│  │    → Path:                                                            │ │
│  │        states: [Homepage, PricingPage]                                │ │
│  │        actions: [ClickPricingLink]                                    │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  3. query_states(task) → List[State]                                         │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  Query: What pages/states are related to this task?                    │ │
│  │                                                                        │ │
│  │  Returns:                                                              │ │
│  │    - List of relevant State objects (with intent_sequences)           │ │
│  │    - Empty list if nothing found                                      │ │
│  │                                                                        │ │
│  │  Example:                                                              │ │
│  │    query_states("Product Hunt product page")                          │ │
│  │    → [State(ProductDetailPage, intents=[ClickTeam, ClickUpvote, ...])]│ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Task Planning Flow (Critical)

**Task decomposition MUST happen AFTER Memory query.**

Memory result guides how to decompose the task.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Task Planning Flow (Mandatory)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  User Task: "Find AI products on Product Hunt and check team info"          │
│                                                                              │
│  Step 1: Query Memory FIRST (before decomposition)                           │
│  ─────────────────────────────────────────────────                           │
│    # Query cognitive_phrase first (user-recorded workflow)                   │
│    phrase = await memory.query_cognitive_phrase(task)                        │
│                                                                              │
│    # If no phrase, query path (retrieved from graph)                         │
│    path = None                                                               │
│    if not phrase:                                                            │
│        path = await memory.query_path(task)                                  │
│                                                                              │
│  Step 2: Decompose task WITH Memory context                                  │
│  ─────────────────────────────────────────────                               │
│    subtasks = await decompose_task(                                          │
│        task=task,                                                            │
│        cognitive_phrase=phrase,  # Complete workflow if found                │
│        path=path,                # Retrieved path if found                   │
│    )                                                                         │
│                                                                              │
│  Step 3: LLM decomposes based on Memory                                      │
│  ─────────────────────────────────────────                                   │
│    If phrase exists:                                                         │
│      → Use phrase's state_path as subtask structure                         │
│      → "Memory has user-recorded workflow, follow this path"                │
│                                                                              │
│    Elif path exists:                                                         │
│      → Use path's states as navigation guide                                │
│      → "Memory has retrieved path, decompose along this route"              │
│                                                                              │
│    Else:                                                                     │
│      → No Memory guidance, decompose from scratch                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Why Memory BEFORE Decomposition?

```
WITHOUT Memory first:
  Task: "View team on Product Hunt"
  LLM guesses: → "Search Google" → "Find website" → "Click around"
  Result: Inefficient, may not find the right path

WITH Memory first:
  Task: "View team on Product Hunt"
  Memory: "I have a recorded workflow: Home → Leaderboard → Product → Team"
  LLM plans: → Follow the known path with minor adaptations
  Result: Efficient, follows proven path
```

### 3.2 Task Decomposition Prompt (Updated)

```python
TASK_DECOMPOSITION_PROMPT = """
You are a Task Planner. Decompose the task into subtasks.

## TASK
{task}

## MEMORY CONTEXT
{memory_context}

## RULES

1. **If CognitivePhrase exists**:
   - This is a user-verified workflow. Use it as your primary guide.
   - Create subtasks that follow the phrase's state path.
   - Each state in the path can become a subtask.

2. **If Path exists (but no CognitivePhrase)**:
   - This is a retrieved navigation path. Use it as reference.
   - Decompose along this path's structure.

3. **If only States exist**:
   - These are known pages. Consider them when planning.
   - Your subtasks may involve these pages.

4. **If no Memory**:
   - Decompose based on your reasoning.
   - Be prepared for exploration.

## OUTPUT
Return subtasks as JSON.
"""
```

---

## 4. Query Timing Rules

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Query Timing Rules                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  At Task/Subtask START:                                                      │
│  ──────────────────────                                                      │
│    → Query cognitive_phrase (user-recorded workflow)                        │
│    → Query path (retrieved navigation path)                                 │
│                                                                              │
│    Purpose: Get complete navigation guidance for the task                   │
│                                                                              │
│  During Agent Loop:                                                          │
│  ───────────────────                                                         │
│    → Query states ONLY (current page info)                                  │
│                                                                              │
│    Purpose: Get available operations on current page                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.1 At Task/Subtask Start

```python
# When starting a task or subtask
async def on_task_start(task_description: str):
    # First try cognitive_phrase (user-recorded, highest value)
    phrase = await memory.query_cognitive_phrase(task_description)

    if phrase:
        # Has complete user-recorded workflow
        inject_context(format_cognitive_phrase(phrase))
        return

    # No phrase, try path (retrieved from graph)
    path = await memory.query_path(task_description)
    if path:
        inject_context(format_path(path))
```

### 4.2 During Agent Loop

```python
# In agent loop, when exploring pages
async def on_page_visit(page_description: str):
    # Only query states - what can I do on this page?
    states = await memory.query_states(page_description)
    if states:
        inject_context(format_states(states))
```

**Key Points:**
- Task/Subtask start → query `cognitive_phrase` or `path`
- Agent loop → query `states` only
- Agent decides how to use the information
- Memory is a tool, Agent is the decision maker

---

## 4. Backend API Mapping

| Interface | Backend API | Notes |
|-----------|-------------|-------|
| `query_cognitive_phrase` | `/api/v1/memory/phrase/query` | Query CognitivePhrase only |
| `query_path` | `/api/v1/memory/query` | Returns states from Reasoner (uses reasoner.plan internally) |
| `query_states` | `/api/v1/memory/query` | Same endpoint, for agent loop context |

**Note**: `/api/v1/memory/query` internally calls `reasoner.plan()`, so both `query_path` and `query_states`
use the same endpoint. The difference is in usage timing and how Agent uses the result.

### 4.1 New Endpoint: Query CognitivePhrase

```
POST /api/v1/memory/phrase/query
{
    "user_id": "xxx",
    "query": "View team info on Product Hunt"
}

Response:
{
    "success": true,
    "phrase": {
        "id": "phrase_xxx",
        "label": "View PH team info",
        "description": "...",
        "state_path": ["state_1", "state_2", ...],
        "states": [...],    // Full state objects
        "actions": [...]    // Full action objects
    }
}

// Or if not found:
{
    "success": true,
    "phrase": null
}
```

### 4.2 Existing: Query Path (Reasoner)

```
POST /api/v1/reasoner/plan
{
    "user_id": "xxx",
    "target": "Find pricing page"
}

Response:
{
    "success": true,
    "states": [...],
    "actions": [...],
    "metadata": {
        "method": "task_dag"  // Not cognitive_phrase_match
    }
}
```

### 4.3 Existing: Query States

```
POST /api/v1/memory/query
{
    "user_id": "xxx",
    "query": "Product Hunt product page"
}

Response:
{
    "success": true,
    "paths": [
        {
            "state": {
                "description": "Product Detail Page",
                "intent_sequences": [...]
            }
        },
        ...
    ]
}
```

---

## 5. Implementation

### 5.1 MemoryToolkit Interface

```python
# In memory_toolkit.py

class MemoryToolkit:
    """Memory query toolkit for Agent."""

    async def query_cognitive_phrase(self, task: str) -> Optional[CognitivePhrase]:
        """Query for user-recorded complete workflow.

        Args:
            task: Task description

        Returns:
            CognitivePhrase if found, None otherwise
        """
        # Call /api/v1/memory/phrase/query
        ...

    async def query_path(self, task: str) -> Optional[Path]:
        """Query for a navigation path to the goal.

        Args:
            task: Task description

        Returns:
            Path (states + actions) if found, None otherwise
        """
        # Call /api/v1/reasoner/plan
        # Only return if method != "cognitive_phrase_match"
        ...

    async def query_states(self, task: str) -> List[State]:
        """Query for related page states.

        Args:
            task: Task description

        Returns:
            List of relevant State objects
        """
        # Call /api/v1/memory/query
        ...
```

### 5.2 Data Classes

```python
@dataclass
class CognitivePhrase:
    """User-recorded complete workflow."""
    id: str
    label: str
    description: str
    states: List[State]
    actions: List[Action]


@dataclass
class Path:
    """Retrieved navigation path."""
    states: List[State]
    actions: List[Action]


@dataclass
class State:
    """Page state with available operations."""
    id: str
    description: str
    page_url: str
    intent_sequences: List[IntentSequence]
```

### 5.3 Context Formatters

```python
def format_cognitive_phrase(phrase: CognitivePhrase) -> str:
    """Format CognitivePhrase for LLM context."""
    lines = ["## Workflow Guide (User Recorded)\n"]
    lines.append(f"**{phrase.label}**: {phrase.description}\n")
    lines.append("**Path:**")
    for i, state in enumerate(phrase.states, 1):
        lines.append(f"  {i}. {state.description}")
        if state.page_url:
            lines.append(f"     URL: {state.page_url}")
    return "\n".join(lines)


def format_path(path: Path) -> str:
    """Format retrieved path for LLM context."""
    lines = ["## Navigation Path\n"]
    for i, state in enumerate(path.states, 1):
        lines.append(f"  {i}. {state.description}")
    return "\n".join(lines)


def format_states(states: List[State]) -> str:
    """Format scattered states for LLM context."""
    lines = ["## Related Pages\n"]
    for state in states[:5]:
        lines.append(f"- **{state.description}**")
        for intent in state.intent_sequences[:3]:
            lines.append(f"  - {intent.description}")
    return "\n".join(lines)
```

---

## 6. Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Summary                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Three Simple Interfaces:                                                    │
│                                                                              │
│    1. query_cognitive_phrase(task) → Complete workflow or None              │
│    2. query_path(task)             → Navigation path or None                │
│    3. query_states(task)           → Related pages or []                    │
│                                                                              │
│  Agent Autonomy:                                                             │
│                                                                              │
│    - Call when needed                                                        │
│    - Use result as reference                                                 │
│    - Decide whether to follow                                                │
│    - Adapt to actual situation                                               │
│                                                                              │
│  Simple Rule:                                                                │
│                                                                              │
│    Memory provides information.                                              │
│    Agent makes decisions.                                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Implementation Checklist

### Backend
- [x] Add `/api/v1/memory/phrase/query` endpoint (query CognitivePhrase only)

### Agent Side (MemoryToolkit)
- [x] Add `query_cognitive_phrase()` method
- [x] Add `query_path()` method (wraps reasoner/plan)
- [x] Add `query_states()` method (wraps memory/query)
- [x] Add data classes: `CognitivePhrase`, `Path`, `State`
- [x] Add formatters: `format_cognitive_phrase()`, `format_path()`, `format_states()`

### Integration
- [x] Call Memory at task start (in `execute()`)
- [x] Call Memory at subtask start (in `_run_agent_loop()`)
- [x] Inject formatted context into LLM prompt

### Cleanup (TODO)
- [ ] Remove old `_call_reasoner()` method
- [ ] Remove old `_build_workflow_hints()` method
- [ ] Remove old `_format_workflow_hints_for_prompt()` method
- [ ] Remove old `_format_paths_for_sse()` method
- [ ] Remove `memory_level` / `reasoner_result` parameters
- [ ] Remove `workflow_hints` handling code
