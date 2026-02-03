"""
Memory management package for BaseAgent

Provides memory systems:

1. **MemoryManager** - Three-layer memory for workflow state
   - Layer 1: Variables (in-memory, temporary)
   - Layer 2: KV Storage (SQLite, persistent)
   - Layer 3: Long-term Memory (mem0, semantic - TODO)

2. **SessionManager** - Simple session-based conversation persistence
   - JSONL files for each session
   - 30 min timeout auto-creates new session
   - Carries context from previous session

3. **LongTermMemory** - MEMORY.md and daily logs
   - Persistent facts and notes
   - Daily activity logging

Key Principle: Memory belongs to users, not Agent instances.
"""

# Layer 1-3 Memory (workflow state)
from .memory_manager import MemoryManager
from .mem0_memory import Mem0Memory
from .sqlite_kv_storage import SQLiteKVStorage

# Session-based conversation persistence
from .session_manager import (
    SessionManager,
    generate_session_id,
    generate_message_id,
    SESSION_TIMEOUT_MINUTES,
    CONTEXT_MESSAGES_COUNT,
)

# Long-term Memory
from .long_term_memory import (
    LongTermMemory,
    get_long_term_memory,
    DEFAULT_MEMORY_PATH,
    MEMORY_FILE,
    DAILY_LOG_FORMAT,
    MEMORY_SECTIONS,
)

__all__ = [
    # Layer 1-3 Memory
    "MemoryManager",
    "Mem0Memory",
    "SQLiteKVStorage",

    # Session Management
    "SessionManager",
    "generate_session_id",
    "generate_message_id",
    "SESSION_TIMEOUT_MINUTES",
    "CONTEXT_MESSAGES_COUNT",

    # Long-term Memory
    "LongTermMemory",
    "get_long_term_memory",
    "DEFAULT_MEMORY_PATH",
    "MEMORY_FILE",
    "DAILY_LOG_FORMAT",
    "MEMORY_SECTIONS",
]
