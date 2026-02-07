"""
BaseAgent Core Module
Provides Agent base framework and data structures
"""

from .base_agent import BaseAgent
from .schemas import (
    # Agent related
    AgentConfig, AgentResult, AgentState, AgentStatus, AgentPriority,
    AgentCapabilitySpec, InterfaceSpec, ExtensionSpec,
    AgentContext, AgentInput, AgentOutput,
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

# AMI Agents (replaces CAMEL ChatAgent/ListenChatAgent)
from .ami_tool import AMITool
from .ami_agent import AMIAgent, AMIAgentResponse
from .ami_browser_agent import AMIBrowserAgent

# AMI Task Executor (replaces CAMEL Workforce)
from .ami_task_executor import AMITaskExecutor, AMISubtask, SubtaskState
from .ami_task_planner import AMITaskPlanner
from .agent_factories import (
    create_provider,
    create_browser_agent,
    create_listen_browser_agent,
    create_developer_agent,
    create_document_agent,
    create_multi_modal_agent,
    create_social_medium_agent,
    create_task_summary_provider,
    summarize_subtasks_results,
)

# Orchestrator Agent (LLM-driven task classification)
from .orchestrator_agent import (
    create_orchestrator_agent,
    run_orchestrator,
    DecomposeTaskTool,
)

__all__ = [
    # Core classes
    "BaseAgent",

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

    # AMI Agents
    "AMITool",
    "AMIAgent",
    "AMIAgentResponse",
    "AMIBrowserAgent",

    # AMI Task Executor
    "AMITaskExecutor",
    "AMISubtask",
    "SubtaskState",
    "AMITaskPlanner",
    "create_provider",
    "create_browser_agent",
    "create_listen_browser_agent",
    "create_developer_agent",
    "create_document_agent",
    "create_multi_modal_agent",
    "create_social_medium_agent",
    "create_task_summary_provider",
    "summarize_subtasks_results",

    # Orchestrator Agent
    "create_orchestrator_agent",
    "run_orchestrator",
    "DecomposeTaskTool",
]
