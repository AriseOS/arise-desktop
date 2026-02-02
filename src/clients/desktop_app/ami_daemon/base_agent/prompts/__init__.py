"""
Prompt Templates Module

Provides system prompts for all specialized agents, based on Eigent's
prompt patterns with XML-style sections and environment awareness.

Usage:
    from ..prompts import get_prompt, get_system_prompt, PromptContext

    # Get a prompt template
    prompt = get_prompt("browser_agent")

    # Get formatted system prompt
    context = PromptContext(working_directory="/path/to/work")
    system_prompt = get_system_prompt("browser_agent", context)

    # Or use the convenience function
    system_prompt = get_agent_system_prompt(
        "browser_agent",
        working_directory="/path/to/work",
        memory_reference="...",
    )
"""

# Base classes and utilities
from .base import (
    PromptContext,
    PromptTemplate,
    PromptSection,
    CompositePrompt,
    MEMORY_REFERENCE_SECTION,
    WORKFLOW_HINTS_SECTION,
    OPERATING_ENVIRONMENT_SECTION,
)

# Main agent prompts
from .browser_agent import (
    BROWSER_AGENT_SYSTEM_PROMPT,
    BROWSER_AGENT_SIMPLE_PROMPT,
    BROWSER_TOOL_CALLING_PROMPT,
)
from .react_browser import (
    REACT_BROWSER_SYSTEM_PROMPT,
    REACT_CONTINUE_PROMPT,
    REACT_ERROR_RECOVERY_PROMPT,
    REACT_COMPLETION_PROMPT,
    REACT_PAGE_ANALYSIS_PROMPT,
)
from .question_confirm import (
    QUESTION_CONFIRM_SYSTEM_PROMPT,
    QUICK_CONFIRM_PROMPT,
    OPTIONS_PROMPT,
    INFO_GATHERING_PROMPT,
)
from .developer import (
    DEVELOPER_SYSTEM_PROMPT,
    CODE_REVIEW_PROMPT,
    BUG_FIX_PROMPT,
    REFACTORING_PROMPT,
)
from .document import (
    DOCUMENT_AGENT_SYSTEM_PROMPT,
    NOTE_TAKING_PROMPT,
    DOCUMENT_SUMMARY_PROMPT,
    FORMAT_CONVERSION_PROMPT,
)
from .social_medium import (
    SOCIAL_MEDIUM_SYSTEM_PROMPT,
    EMAIL_COMPOSE_PROMPT,
    EMAIL_SUMMARY_PROMPT,
    CALENDAR_EVENT_PROMPT,
)
from .task_decomposition import (
    TASK_DECOMPOSITION_PROMPT,
    TASK_ASSIGNMENT_PROMPT,
    TASK_ROUTER_PROMPT,
    DEPENDENCY_RESOLUTION_PROMPT,
)

# Registry functions
from .registry import (
    PROMPT_REGISTRY,
    AUXILIARY_PROMPTS,
    AGENT_TYPES,
    get_prompt,
    get_system_prompt,
    get_auxiliary_prompt,
    get_agent_system_prompt,
    list_prompts,
    get_all_prompts,
)

__all__ = [
    # Base classes
    "PromptContext",
    "PromptTemplate",
    "PromptSection",
    "CompositePrompt",
    "MEMORY_REFERENCE_SECTION",
    "WORKFLOW_HINTS_SECTION",
    "OPERATING_ENVIRONMENT_SECTION",

    # Browser agent prompts
    "BROWSER_AGENT_SYSTEM_PROMPT",
    "BROWSER_AGENT_SIMPLE_PROMPT",
    "BROWSER_TOOL_CALLING_PROMPT",

    # ReAct browser prompts
    "REACT_BROWSER_SYSTEM_PROMPT",
    "REACT_CONTINUE_PROMPT",
    "REACT_ERROR_RECOVERY_PROMPT",
    "REACT_COMPLETION_PROMPT",
    "REACT_PAGE_ANALYSIS_PROMPT",

    # Question/confirm prompts
    "QUESTION_CONFIRM_SYSTEM_PROMPT",
    "QUICK_CONFIRM_PROMPT",
    "OPTIONS_PROMPT",
    "INFO_GATHERING_PROMPT",

    # Developer prompts
    "DEVELOPER_SYSTEM_PROMPT",
    "CODE_REVIEW_PROMPT",
    "BUG_FIX_PROMPT",
    "REFACTORING_PROMPT",

    # Document prompts
    "DOCUMENT_AGENT_SYSTEM_PROMPT",
    "NOTE_TAKING_PROMPT",
    "DOCUMENT_SUMMARY_PROMPT",
    "FORMAT_CONVERSION_PROMPT",

    # Social medium prompts
    "SOCIAL_MEDIUM_SYSTEM_PROMPT",
    "EMAIL_COMPOSE_PROMPT",
    "EMAIL_SUMMARY_PROMPT",
    "CALENDAR_EVENT_PROMPT",

    # Task decomposition prompts
    "TASK_DECOMPOSITION_PROMPT",
    "TASK_ASSIGNMENT_PROMPT",
    "TASK_ROUTER_PROMPT",
    "DEPENDENCY_RESOLUTION_PROMPT",

    # Registry
    "PROMPT_REGISTRY",
    "AUXILIARY_PROMPTS",
    "AGENT_TYPES",
    "get_prompt",
    "get_system_prompt",
    "get_auxiliary_prompt",
    "get_agent_system_prompt",
    "list_prompts",
    "get_all_prompts",
]
