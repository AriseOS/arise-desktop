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

# Budget management
from .token_usage import TokenUsage, SessionTokenUsage
from .cost_calculator import (
    MODEL_PRICING,
    calculate_cost,
    calculate_cost_breakdown,
    estimate_tokens,
    get_pricing,
    get_model_tier,
    get_cheaper_model,
)
from .budget_controller import (
    BudgetConfig,
    BudgetController,
    BudgetExceedAction,
    BudgetExceededException,
)

# Agent registry and routing
from .agent_registry import (
    AgentType,
    AgentInfo,
    AgentRegistry,
    get_registry,
    register_agent,
    get_agent,
    create_agent,
    register_default_agents,
    BROWSER_AGENT,
    DEVELOPER_AGENT,
    DOCUMENT_AGENT,
    SOCIAL_MEDIUM_AGENT,
    QUESTION_CONFIRM_AGENT,
)
from .task_router import (
    TaskRouter,
    RoutingResult,
    get_router,
    route_task,
)

# Task orchestrator for multi-agent coordination
from .task_orchestrator import (
    TaskOrchestrator,
    OrchestratorConfig,
    OrchestratorResult,
    OrchestratorState,
    SubTask,
    SubTaskState,
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
    "ErrorHandling",

    # Budget management
    "TokenUsage",
    "SessionTokenUsage",
    "MODEL_PRICING",
    "calculate_cost",
    "calculate_cost_breakdown",
    "estimate_tokens",
    "get_pricing",
    "get_model_tier",
    "get_cheaper_model",
    "BudgetConfig",
    "BudgetController",
    "BudgetExceedAction",
    "BudgetExceededException",

    # Agent registry and routing
    "AgentType",
    "AgentInfo",
    "AgentRegistry",
    "get_registry",
    "register_agent",
    "get_agent",
    "create_agent",
    "register_default_agents",
    "BROWSER_AGENT",
    "DEVELOPER_AGENT",
    "DOCUMENT_AGENT",
    "SOCIAL_MEDIUM_AGENT",
    "QUESTION_CONFIRM_AGENT",
    "TaskRouter",
    "RoutingResult",
    "get_router",
    "route_task",

    # Task orchestrator
    "TaskOrchestrator",
    "OrchestratorConfig",
    "OrchestratorResult",
    "OrchestratorState",
    "SubTask",
    "SubTaskState",
]