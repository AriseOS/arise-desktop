# intent_builder/core/

Core data structures for the intent-based workflow generation system.

## Files

| File | Purpose |
|------|---------|
| `intent.py` | Intent data structure - semantic abstraction of user operations |
| `intent_memory_graph.py` | Graph storage for intents with temporal edges |
| `metaflow.py` | MetaFlow intermediate representation (between Intent and Workflow) |
| `operation.py` | Operation data structure - single user action |

## Data Flow

```
User Operations → Intent → IntentMemoryGraph → MetaFlow → Workflow YAML
```

## Key Concepts

### Intent
Semantic abstraction of user operations - a complete subtask unit.

```python
@dataclass
class Intent:
    id: str                    # MD5 hash of description, e.g., "intent_a3f5b2c1"
    description: str           # Natural language description
    operations: List[Operation]  # Original operation sequence
    created_at: datetime
    source_session_id: str
```

**Design Principles:**
- Minimal: Only core fields
- Semantic ID: Hash of description for deduplication
- Complete context: Preserve all operations

### Operation
Single user action (click, navigate, input, copy, etc.)

```python
@dataclass
class Operation:
    type: str           # "click", "navigate", "input", "copy_action", etc.
    url: Optional[str]
    element: Optional[ElementInfo]
    value: Optional[str]
    timestamp: Optional[str]
```

### IntentMemoryGraph
Graph of Intent nodes with temporal edges.

- **Nodes**: Intent instances
- **Edges**: Temporal ordering (not causal)
- **Retrieval**: Semantic similarity via embeddings

### MetaFlow
Intermediate representation with control flow.

```python
class MetaFlow:
    task_description: str
    nodes: List[MetaFlowNode | LoopNode]
```

**Contains:**
- Intent nodes with operations
- Loop nodes (foreach over items)
- Data flow (variable references)
