# base_agent/memory/

Session and conversation memory for BaseAgent.

## Architecture

```
Memory Systems
└── Conversation Memory (session history)
    ├── ConversationStore
    │   └── Manages index.json and conversation lifecycle
    └── TranscriptManager
        └── Manages JSONL transcript files
```

## Files

| File | Purpose |
|------|---------|
| `session_manager.py` | Session-based conversation persistence |
| `conversation_types.py` | Type definitions for conversation storage |
| `conversation_store.py` | Conversation index management |
| `transcript_manager.py` | JSONL transcript file management |

## Key Principle

**Memory belongs to users, not Agent instances.**

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
