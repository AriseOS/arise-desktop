# base_agent/memory/

Multi-layer memory system for BaseAgent.

## Architecture

```
Memory Systems
├── Layer 1-3: MemoryManager (workflow state)
│   ├── Layer 1: Variables (in-memory)
│   │   └── Python dict, workflow variable passing
│   ├── Layer 2: KV Storage (persistent)
│   │   └── SQLite, script caching, config storage
│   └── Layer 3: Long-term Memory (semantic)
│       └── mem0 + ChromaDB (TODO: not yet enabled)
│
└── Conversation Memory (session history)
    ├── ConversationStore
    │   └── Manages index.json and conversation lifecycle
    └── TranscriptManager
        └── Manages JSONL transcript files
```

## Files

| File | Purpose |
|------|---------|
| `memory_manager.py` | Unified interface for workflow memory layers |
| `sqlite_kv_storage.py` | Layer 2: SQLite-based key-value storage |
| `mem0_memory.py` | Layer 3: Semantic memory via mem0 |
| `conversation_types.py` | Type definitions for conversation storage |
| `conversation_store.py` | Conversation index management |
| `transcript_manager.py` | JSONL transcript file management |

## Key Principle

**Memory belongs to users, not Agent instances.**

```python
# Correct: specify user_id
agent1 = BaseAgent(..., user_id="user123")
agent2 = BaseAgent(..., user_id="user123")
# Both share the same memory

# Wrong: random ID, no persistence
agent = BaseAgent(...)  # Gets random agent_xxx-uuid
```

## Conversation Memory

Session history storage based on OpenClaw's design.

### File Structure
```
~/.ami/conversations/
├── index.json                    # Conversation index
└── {user_id}/
    └── {conversation_id}.jsonl   # Transcript file
```

### JSONL Format
```jsonl
{"type":"header","version":1,"conversation_id":"conv_abc","user_id":"user1","created_at":"..."}
{"type":"message","id":"msg_1","role":"user","content":"Hello","timestamp":"..."}
{"type":"message","id":"msg_2","role":"assistant","content":"Hi!","timestamp":"..."}
{"type":"event","event_type":"task_started","task_id":"task_1","timestamp":"..."}
```

### Agent Integration
Agent uses ConversationMemoryToolkit to search history:
- `search_conversations(query)` - Search by keyword
- `get_conversation_messages(conversation_id)` - Get messages
- `get_recent_conversations()` - List recent

### Design Principle (from OpenClaw)
- Agent decides when to search (guided by System Prompt)
- Memory is a tool, not auto-injected context
- Search before answering questions about past work

## References

- Design doc: `docs/conversation-memory-design.md`
- OpenClaw memory: `third-party/openclaw/docs/concepts/memory.md`
- Toolkit: `base_agent/tools/toolkits/conversation_memory_toolkit.py`
