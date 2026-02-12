"""
Memory management package for BaseAgent

Provides:

1. **SessionManager** - Simple session-based conversation persistence
   - JSONL files for each session
   - 30 min timeout auto-creates new session
   - Carries context from previous session

Key Principle: Memory belongs to users, not Agent instances.
"""

# Session-based conversation persistence
from .session_manager import (
    SessionManager,
    generate_session_id,
    generate_message_id,
    SESSION_TIMEOUT_MINUTES,
    CONTEXT_MESSAGES_COUNT,
)

__all__ = [
    # Session Management
    "SessionManager",
    "generate_session_id",
    "generate_message_id",
    "SESSION_TIMEOUT_MINUTES",
    "CONTEXT_MESSAGES_COUNT",
]
