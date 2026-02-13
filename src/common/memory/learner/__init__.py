"""Post-execution Learner Agent.

Provides a LearnerAgent that analyzes completed task executions
and creates CognitivePhrases for successful browser workflows.
Mirrors PlannerAgent architecture (AMIAgent + Memory tools).

The LearnerAgent only handles Memory-layer concerns.
Execution data collection is done by ExecutionDataCollector on the client.
"""

from .models import (
    LearnResult,
    LearningPlan,
    PhraseCandidate,
    SubtaskExecutionData,
    TaskExecutionData,
    ToolUseRecord,
)
from .tools import LearnerTools

# LearnerAgent imported lazily to avoid circular import with AMIAgent
# Use: from src.common.memory.learner.learner_agent import LearnerAgent

__all__ = [
    "LearnerAgent",
    "LearnResult",
    "LearningPlan",
    "PhraseCandidate",
    "TaskExecutionData",
    "SubtaskExecutionData",
    "ToolUseRecord",
    "LearnerTools",
]


def __getattr__(name):
    if name == "LearnerAgent":
        from .learner_agent import LearnerAgent
        return LearnerAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
