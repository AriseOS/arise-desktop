# Memory-Guided Planning Design

## Overview

Enhance Quick Task's planning process by integrating workflow memory. The agent will query memory for similar tasks, use retrieved paths as planning reference, and track the correspondence between plan steps and memory path steps during execution.

## Current State

### Current Plan Generation Flow

```
EigentBrowserAgent._process_command()
  → get_snapshot()                      # Get current page DOM snapshot
  → _llm_call(is_initial=True)          # First LLM call
      → user_content = "Snapshot:\n{snapshot}\n\nTask: {prompt}"
      → system = EIGENT_SYSTEM_PROMPT
  → Returns { "plan": [...], "action": {...} }
```

### Current Prompt Structure

**System Prompt**: Defines role, action types, output format
**User Content**: `Snapshot:\n{snapshot}\n\nTask: {task}`

**Problem**: Plan is generated purely from page snapshot + task description, without leveraging historical knowledge of how similar tasks were accomplished.

## Requirements

### 1. Memory Query Integration

Before generating a plan, query the memory system for relevant workflow paths:
- Call `POST /api/v1/memory/query` with user's task description
- Retrieve paths with scores, steps, and intent sequences
- Pass retrieved information to LLM as planning reference

### 2. Plan Generation with Path Reference

When generating a plan, provide LLM with:
- Retrieved path description and score
- Each path step's state, action, and intent_sequence
- Clear indication that memory may not be relevant (no matching data)

LLM outputs:
- Plan steps with optional `path_ref` indicating correspondence to memory path steps
- The mapping is flexible (not necessarily 1:1)

### 3. Action Generation with Intent Reference

During execution, for each plan step:
- Look up `path_ref` to find corresponding memory path step
- If found, provide that step's `intent_sequence.intents` as action reference
- If `path_ref` is null, no memory reference available

## Design

### Data Flow

```
QuickTaskService.submit_task(task, user_id)
  │
  ├─→ Call memory/query API
  │     Request: { user_id, query: task, top_k: 3 }
  │     Response: { paths: [...], success: true }
  │
  └─→ EigentBrowserAgent.execute(task, memory_paths)
        │
        ├─→ _process_command()
        │     │
        │     ├─→ Initial _llm_call (plan generation)
        │     │     - Include full path description in prompt
        │     │     - LLM returns plan with path_ref mappings
        │     │     - Store mapping for later use
        │     │
        │     └─→ Loop: _llm_call (action generation)
        │           - Current plan step index → path_ref → intent reference
        │           - Include relevant intents in prompt
        │
        └─→ Return result
```

### Memory Query Response Structure

```json
{
  "success": true,
  "query": "original query",
  "paths": [
    {
      "score": 0.85,
      "description": "Start page → Target page",
      "start_url": "https://...",
      "steps": [
        {
          "state": {
            "id": "state_id",
            "description": "Page description",
            "page_title": "Page Title",
            "page_url": "https://...",
            "domain": "example.com"
          },
          "action": {
            "id": "action_id",
            "description": "Click on product card",
            "type": "click"
          },
          "intent_sequence": {
            "id": "seq_id",
            "description": "Navigate to product detail",
            "intents": [
              {"type": "click", "text": "Product Name", "value": null}
            ]
          }
        }
      ]
    }
  ]
}
```

### New Plan Output Format

```json
{
  "plan": [
    {"step": "Navigate to Product Hunt", "path_ref": null},
    {"step": "Click weekly leaderboard link", "path_ref": 0},
    {"step": "Click on target product card", "path_ref": 0},
    {"step": "Click Team tab", "path_ref": 1},
    {"step": "View team member details", "path_ref": 2}
  ],
  "action": {
    "type": "navigate",
    "url": "https://producthunt.com"
  }
}
```

**Mapping characteristics**:
- `path_ref` is the index of the memory path step (0-based)
- `path_ref: null` means no corresponding memory reference
- Multiple plan steps can reference the same path step (plan is more granular)
- One plan step can conceptually cover multiple path steps (plan is coarser)
- Not all path steps need to be referenced

### Prompt Design

#### System Prompt Addition

```
## Memory Reference

You may receive a "Reference Path" from the user's workflow memory. This path shows how similar tasks were accomplished before.

Guidelines:
- Use the reference path as guidance, but adapt to the actual page state
- The reference may not be relevant if this is a new type of task
- For each plan step, indicate which path step it corresponds to (path_ref), or null if no correspondence
- Intent sequences show specific actions that worked before - use them as hints

Plan output format:
{
  "plan": [
    {"step": "Step description", "path_ref": <path_step_index or null>},
    ...
  ],
  "action": {...}
}
```

#### User Content - Initial Call (Plan Generation)

```
Snapshot:
{snapshot}

Reference Path (score: 0.85):
Note: Retrieved from memory based on similar tasks. May not be relevant for new task types.

Path Step 0: Product Hunt Weekly Leaderboard
  URL: https://producthunt.com/leaderboard/weekly
  Action: Click product card to view details
  Intents: [click on "Product Name" link]

Path Step 1: Product Detail Page
  URL: https://producthunt.com/posts/product-name
  Action: Click Team tab
  Intents: [click on "Team" tab button]

Path Step 2: Team Members Section
  URL: https://producthunt.com/posts/product-name (same page, different section)
  Action: None (target reached)
  Intents: []

Task: Find team members of top product on Product Hunt weekly leaderboard
```

#### User Content - Subsequent Calls (Action Generation)

```
Snapshot:
{snapshot}

History:
1. ✅ navigate -> Navigated to https://producthunt.com
2. ✅ click -> Clicked on "This Week" link

Current Plan Step: "Click on target product card" (path_ref: 0)
Reference Intents: [click on "Product Name" link]

Task: Find team members of top product on Product Hunt weekly leaderboard
```

### Implementation Changes

#### 1. QuickTaskService

```python
async def submit_task(self, task: str, user_id: str, ...):
    # Query memory before executing
    memory_paths = await self._query_memory(task, user_id)

    # Pass to agent
    input_data = AgentInput(data={
        "task": task,
        "memory_paths": memory_paths,  # New field
        ...
    })
```

#### 2. EigentBrowserAgent

New instance variables:
```python
self._memory_paths: List[Dict] = []      # Retrieved paths
self._plan_with_refs: List[Dict] = []    # Plan steps with path_ref
self._current_plan_step: int = 0         # Current execution step
```

Modified `_process_command`:
```python
async def _process_command(self, prompt: str, memory_paths: List[Dict], ...):
    # Build memory reference for prompt
    memory_reference = self._format_memory_paths(memory_paths)

    # Initial LLM call with memory reference
    plan_resp = self._llm_call(prompt, snapshot, is_initial=True,
                                memory_reference=memory_reference)

    # Store plan with path_ref mappings
    self._plan_with_refs = plan_resp.get("plan", [])

    # During execution loop
    while action and steps < max_steps:
        # Get current step's intent reference
        intent_reference = self._get_intent_reference(self._current_plan_step)

        # Call LLM with intent reference
        action = self._llm_call(..., intent_reference=intent_reference)

        self._current_plan_step += 1
```

New helper methods:
```python
def _format_memory_paths(self, paths: List[Dict]) -> str:
    """Format memory paths for prompt."""

def _get_intent_reference(self, plan_step_index: int) -> Optional[str]:
    """Get intent reference for current plan step."""
    if plan_step_index >= len(self._plan_with_refs):
        return None

    step = self._plan_with_refs[plan_step_index]
    path_ref = step.get("path_ref")

    if path_ref is None:
        return None

    # Get intents from memory path step
    path_step = self._memory_paths[0]["steps"][path_ref]
    intents = path_step.get("intent_sequence", {}).get("intents", [])

    return self._format_intents(intents)
```

## Edge Cases

### 1. No Memory Match

When memory query returns empty paths:
- Don't include "Reference Path" section in prompt
- Or include a note: "No reference path found in memory. Plan from scratch."

### 2. Low Score Match

When best path score is below threshold (e.g., 0.3):
- Include path but with warning: "Reference Path (score: 0.32 - low confidence)"
- LLM should rely more on snapshot than memory

### 3. Path Step Out of Bounds

When `path_ref` exceeds available path steps:
- Treat as `path_ref: null`
- Log warning for debugging

### 4. Multiple Paths

When memory returns multiple paths:
- Use highest-scored path as primary reference
- Optionally mention alternatives: "Alternative paths available with scores: 0.72, 0.65"

## Success Metrics

1. **Plan Quality**: Plans should be more accurate when memory has relevant paths
2. **Action Accuracy**: Actions should succeed more often with intent references
3. **Graceful Degradation**: Performance should not degrade when memory has no relevant data

## Future Enhancements

1. **Learning from Execution**: After successful task completion, add the executed path to memory
2. **Multi-Path Reasoning**: Use multiple retrieved paths to synthesize better plans
3. **Confidence-Based Switching**: Dynamically switch between memory-guided and pure LLM modes based on match confidence
