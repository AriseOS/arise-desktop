"""Memory-Powered Planner Agent.

Provides a PlannerAgent that uses Memory tools to recall workflows,
explore the memory graph, understand user preferences, and output
an execution-oriented step plan (MemoryPlan).

The PlannerAgent only handles Memory-layer concerns. Subtask
decomposition (agent_type, depends_on) is done by AMITaskPlanner.
"""

from .models import (
    EnrichedPhrase,
    MemoryPlan,
    PlanResult,
    PlanStep,
)
from .tools import PlannerTools

# PlannerAgent imported lazily to avoid circular import with AMIAgent
# Use: from src.common.memory.planner.planner_agent import PlannerAgent

__all__ = [
    "PlannerAgent",
    "PlanResult",
    "MemoryPlan",
    "PlanStep",
    "EnrichedPhrase",
    "PlannerTools",
]


def __getattr__(name):
    if name == "PlannerAgent":
        from .planner_agent import PlannerAgent
        return PlannerAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
