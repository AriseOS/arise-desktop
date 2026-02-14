"""
Common Agent Module

Core agent classes extracted from ami_daemon for use by external modules
(llm providers, memory planner/learner, etc.).
"""

from .ami_tool import AMITool
from .ami_agent import AMIAgent, AMIAgentResponse
from .schemas import (
    AgentConfig,
    AgentState,
    AgentStatus,
    AgentPriority,
    AgentResult,
    AgentInput,
    AgentOutput,
    AgentContext,
    InterfaceSpec,
    ExtensionSpec,
    AgentCapabilitySpec,
)
from .token_usage import TokenUsage, SessionTokenUsage
from .cost_calculator import (
    MODEL_PRICING,
    MODEL_ALIASES,
    DEFAULT_MODEL,
    resolve_model_name,
    get_pricing,
    calculate_cost,
    calculate_cost_breakdown,
    estimate_tokens,
    estimate_cost_for_text,
    get_model_tier,
    get_cheaper_model,
)
from .budget_controller import (
    BudgetController,
    BudgetConfig,
    BudgetState,
    BudgetExceedAction,
    BudgetExceededException,
)

__all__ = [
    # Agent
    "AMITool",
    "AMIAgent",
    "AMIAgentResponse",
    # Schemas
    "AgentConfig",
    "AgentState",
    "AgentStatus",
    "AgentPriority",
    "AgentResult",
    "AgentInput",
    "AgentOutput",
    "AgentContext",
    "InterfaceSpec",
    "ExtensionSpec",
    "AgentCapabilitySpec",
    # Token usage
    "TokenUsage",
    "SessionTokenUsage",
    # Cost calculator
    "MODEL_PRICING",
    "MODEL_ALIASES",
    "DEFAULT_MODEL",
    "resolve_model_name",
    "get_pricing",
    "calculate_cost",
    "calculate_cost_breakdown",
    "estimate_tokens",
    "estimate_cost_for_text",
    "get_model_tier",
    "get_cheaper_model",
    # Budget
    "BudgetController",
    "BudgetConfig",
    "BudgetState",
    "BudgetExceedAction",
    "BudgetExceededException",
]
