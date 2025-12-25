# base_agent/memory/

Three-layer memory system for BaseAgent.

## Architecture

```
MemoryManager
├── Layer 1: Variables (in-memory)
│   └── Python dict, workflow variable passing
├── Layer 2: KV Storage (persistent)
│   └── SQLite, script caching, config storage
└── Layer 3: Long-term Memory (semantic)
    └── mem0 + ChromaDB (TODO: not yet enabled)
```

## Files

| File | Purpose |
|------|---------|
| `memory_manager.py` | Unified interface for all memory layers |
| `sqlite_kv_storage.py` | Layer 2: SQLite-based key-value storage |
| `mem0_memory.py` | Layer 3: Semantic memory via mem0 |

## Key Principle

**Memory belongs to users, not BaseAgent instances.**

```python
# Correct: specify user_id
agent1 = BaseAgent(..., user_id="user123")
agent2 = BaseAgent(..., user_id="user123")
# Both share the same memory

# Wrong: random ID, no persistence
agent = BaseAgent(...)  # Gets random agent_xxx-uuid
```

## Layer Details

### Layer 1: Variables
- Storage: Python `Dict[str, Any]`
- Lifetime: Process memory (lost on restart)
- Use: Workflow step-to-step data passing

### Layer 2: KV Storage
- Storage: SQLite database
- Lifetime: Disk persistent
- Use: Script caching, configuration, session state
- User isolation: Data keyed by `user_id`

### Layer 3: Long-term Memory
- Storage: mem0 + ChromaDB
- Lifetime: Disk persistent
- Use: Semantic search, learning from history
- Status: TODO - not yet enabled
