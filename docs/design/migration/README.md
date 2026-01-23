# Tier 1 Migration: Critical Features from Eigent

This directory contains detailed analysis and implementation plans for migrating 4 critical features from Eigent to 2ami.

## Overview

Based on analysis of `third-party/eigent/` source code compared to `src/clients/desktop_app/ami_daemon/base_agent/`, we identified these features as critical gaps:

| Feature | Eigent | 2ami Current | Priority |
|---------|--------|--------------|----------|
| Conversation History | `TaskLock.conversation_history[]` | Missing | P0 |
| Event System (SSE) | 27 Action types + SSE streaming | Queue-based, limited events | P0 |
| Toolkit Decorators | `@listen_toolkit`, `@auto_listen_toolkit` | Manual event emission | P0 |
| Working Directory | Per-task: `~/eigent/{user}/project/task/` | Global process directory | P0 |

## Documents

1. **[01-conversation-history.md](./01-conversation-history.md)**
   - Multi-turn conversation context preservation
   - Context building for LLM prompt injection
   - History length management (100KB cap)

2. **[02-event-system.md](./02-event-system.md)**
   - 27+ Action types (activate/deactivate agent/toolkit, terminal, etc.)
   - SSE (Server-Sent Events) streaming format
   - Queue-based event architecture

3. **[03-toolkit-decorators.md](./03-toolkit-decorators.md)**
   - `@listen_toolkit` method decorator
   - `@auto_listen_toolkit` class decorator
   - Automatic event emission on tool execution

4. **[04-working-directory.md](./04-working-directory.md)**
   - Per-task isolated workspace: `~/.ami/users/{user}/projects/{project}/tasks/{task}/`
   - User and project isolation
   - Automatic cleanup for old tasks

## Implementation Order

```
Phase 1: Foundation
├── Working Directory (04) - Isolated workspaces
└── Event System (02) - Action types and SSE

Phase 2: Integration
├── Toolkit Decorators (03) - Requires Event System
└── Conversation History (01) - Requires Working Directory

Phase 3: Testing & Polish
├── Integration tests
└── Frontend SSE client updates
```

## Key Files to Create

```
src/clients/desktop_app/ami_daemon/base_agent/
├── events/                          # NEW PACKAGE
│   ├── __init__.py
│   ├── action_types.py              # Action enum + ActionData models
│   ├── sse.py                       # SSE formatting utilities
│   └── toolkit_listen.py            # @listen_toolkit decorators
├── workspace/                       # NEW PACKAGE
│   ├── __init__.py
│   └── directory_manager.py         # WorkingDirectoryManager
└── services/
    └── context_builder.py           # Conversation context builder
```

## Key Files to Modify

```
src/clients/desktop_app/ami_daemon/
├── services/quick_task_service.py   # TaskState + conversation + workspace
├── routers/quick_task.py            # SSE endpoints
└── base_agent/
    ├── tools/toolkits/
    │   ├── base_toolkit.py          # Add _task_state support
    │   ├── terminal_toolkit.py      # Apply decorators
    │   └── browser_toolkit.py       # Apply decorators
    └── agents/
        └── eigent_style_browser_agent.py  # Context injection
```

## Quick Reference: Eigent Source Locations

| Feature | Eigent File | Key Lines |
|---------|------------|-----------|
| TaskLock (state) | `backend/app/service/task.py` | 260-363 |
| Action enum | `backend/app/service/task.py` | 18-48 |
| SSE formatting | `backend/app/model/chat.py` | 145-147 |
| SSE streaming | `backend/app/controller/chat_controller.py` | 41-128 |
| @listen_toolkit | `backend/app/utils/listen/toolkit_listen.py` | 79-296 |
| @auto_listen_toolkit | `backend/app/utils/listen/toolkit_listen.py` | 317-401 |
| Working directory | `backend/app/model/chat.py` | 95-103 |
| Context building | `backend/app/service/chat_service.py` | 177-228 |

## Estimated Effort

| Feature | New Files | Modified Files | Complexity |
|---------|-----------|----------------|------------|
| Conversation History | 1 | 2 | Medium |
| Event System | 2 | 2 | High |
| Toolkit Decorators | 1 | 5 | Medium |
| Working Directory | 1 | 4 | Medium |
| **Total** | **5** | **~10** | **High** |

## Testing Strategy

Each document includes specific testing recommendations:

1. **Unit Tests**: Individual functions and classes
2. **Integration Tests**: Full flows with multiple components
3. **Manual Testing**: Real-world scenarios with actual browser/terminal

## Notes

- All implementations follow 2ami coding style (CLAUDE.md)
- Pydantic models used for data validation
- asyncio throughout for async compatibility
- Type hints required for all public APIs
