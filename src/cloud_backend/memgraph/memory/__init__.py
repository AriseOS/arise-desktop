"""Memory Layer - Memory management for States, Actions, and CognitivePhrase.

This module provides memory management capabilities for workflow-based
cognitive memory, including:
- State management (nodes in the graph)
- Action management (edges in the graph)
- CognitivePhrase management (high-level workflow patterns)
"""

# Abstract interfaces
from src.cloud_backend.memgraph.memory.memory import (
    ActionManager,
    CognitivePhraseManager,
    Memory,
    StateManager,
)

# Concrete implementations
from src.cloud_backend.memgraph.memory.workflow_memory import (
    GraphActionManager,
    GraphStateManager,
    InMemoryCognitivePhraseManager,
    WorkflowMemory,
)

__all__ = [
    # Abstract interfaces
    "StateManager",
    "ActionManager",
    "CognitivePhraseManager",
    "Memory",
    # Concrete implementations
    "GraphStateManager",
    "GraphActionManager",
    "InMemoryCognitivePhraseManager",
    "WorkflowMemory",
]
