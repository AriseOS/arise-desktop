"""
Core data structures for Intent Builder
"""

from .intent import Intent, generate_intent_id
from .intent_memory_graph import IntentMemoryGraph, IntentStorageBackend
from .operation import Operation, ElementInfo

__all__ = [
    # Intent data structures
    "Intent",
    "generate_intent_id",
    "IntentMemoryGraph",
    "IntentStorageBackend",
    # Shared Operation definition
    "Operation",
    "ElementInfo",
]
