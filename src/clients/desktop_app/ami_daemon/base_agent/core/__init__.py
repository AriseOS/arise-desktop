"""
BaseAgent Core Module
Provides Agent base framework, workflow engine and data structures

Note: WorkflowEngine is NOT imported here to avoid circular imports.
Import it directly: from .workflow_engine import WorkflowEngine
"""

from .base_agent import BaseAgent
from .schemas import (
    # Agent related
    AgentConfig, AgentResult, AgentState, AgentStatus, AgentPriority,
    AgentCapabilitySpec, InterfaceSpec, ExtensionSpec,
    AgentContext, AgentInput, AgentOutput,

    # Workflow related
    AgentWorkflowStep, Workflow, WorkflowResult,
    ExecutionContext, StepResult, StepType, ErrorHandling
)

# Lazy import for WorkflowEngine to avoid circular imports
def __getattr__(name):
    if name == "WorkflowEngine":
        from .workflow_engine import WorkflowEngine
        return WorkflowEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    # Core classes
    "BaseAgent",
    "WorkflowEngine",  # Available via __getattr__

    # Agent data structures
    "AgentConfig",
    "AgentResult",
    "AgentState",
    "AgentStatus",
    "AgentPriority",
    "AgentCapabilitySpec",
    "InterfaceSpec",
    "ExtensionSpec",
    "AgentContext",
    "AgentInput",
    "AgentOutput",

    # Workflow data structures
    "AgentWorkflowStep",
    "Workflow",
    "WorkflowResult",
    "ExecutionContext",
    "StepResult",
    "StepType",
    "ErrorHandling"
]