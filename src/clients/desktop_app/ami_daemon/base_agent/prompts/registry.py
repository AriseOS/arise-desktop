"""
Prompt Registry Module

Central registry for all prompt templates with easy access by agent type.
Based on Eigent's pattern of specialized prompts per agent.

References:
- Eigent: third-party/eigent/backend/app/utils/agent.py
- Eigent: third-party/eigent/backend/app/service/task.py
"""

from typing import Dict, Optional

from .base import PromptTemplate, PromptContext
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


# Main prompt registry - maps agent types to their system prompts
# These are the same agent types used in Eigent
PROMPT_REGISTRY: Dict[str, PromptTemplate] = {
    # Primary agents (from Eigent's task.py)
    "browser_agent": BROWSER_AGENT_SYSTEM_PROMPT,
    "developer_agent": DEVELOPER_SYSTEM_PROMPT,
    "document_agent": DOCUMENT_AGENT_SYSTEM_PROMPT,
    "social_medium_agent": SOCIAL_MEDIUM_SYSTEM_PROMPT,
    "question_confirm_agent": QUESTION_CONFIRM_SYSTEM_PROMPT,

    # Alternative browser prompts
    "browser_agent_simple": BROWSER_AGENT_SIMPLE_PROMPT,
    "browser_tool_calling": BROWSER_TOOL_CALLING_PROMPT,
    "react_browser": REACT_BROWSER_SYSTEM_PROMPT,

    # Task management prompts
    "task_decomposition": TASK_DECOMPOSITION_PROMPT,
    "task_assignment": TASK_ASSIGNMENT_PROMPT,
    "task_router": TASK_ROUTER_PROMPT,
}


# Extended prompt registry for auxiliary prompts
AUXILIARY_PROMPTS: Dict[str, PromptTemplate] = {
    # Browser/ReAct
    "react_continue": REACT_CONTINUE_PROMPT,
    "react_error_recovery": REACT_ERROR_RECOVERY_PROMPT,
    "react_completion": REACT_COMPLETION_PROMPT,
    "react_page_analysis": REACT_PAGE_ANALYSIS_PROMPT,

    # Question/Confirm
    "quick_confirm": QUICK_CONFIRM_PROMPT,
    "options": OPTIONS_PROMPT,
    "info_gathering": INFO_GATHERING_PROMPT,

    # Developer
    "code_review": CODE_REVIEW_PROMPT,
    "bug_fix": BUG_FIX_PROMPT,
    "refactoring": REFACTORING_PROMPT,

    # Document
    "note_taking": NOTE_TAKING_PROMPT,
    "document_summary": DOCUMENT_SUMMARY_PROMPT,
    "format_conversion": FORMAT_CONVERSION_PROMPT,

    # Social Medium
    "email_compose": EMAIL_COMPOSE_PROMPT,
    "email_summary": EMAIL_SUMMARY_PROMPT,
    "calendar_event": CALENDAR_EVENT_PROMPT,

    # Task
    "dependency_resolution": DEPENDENCY_RESOLUTION_PROMPT,
}


def get_prompt(
    prompt_name: str,
    include_auxiliary: bool = True
) -> Optional[PromptTemplate]:
    """Get a prompt template by name.

    Args:
        prompt_name: Name of the prompt (agent type or prompt name)
        include_auxiliary: Whether to search auxiliary prompts too

    Returns:
        PromptTemplate if found, None otherwise
    """
    # Check main registry first
    if prompt_name in PROMPT_REGISTRY:
        return PROMPT_REGISTRY[prompt_name]

    # Check auxiliary if enabled
    if include_auxiliary and prompt_name in AUXILIARY_PROMPTS:
        return AUXILIARY_PROMPTS[prompt_name]

    return None


def get_system_prompt(
    agent_type: str,
    context: Optional[PromptContext] = None,
    **kwargs
) -> str:
    """Get formatted system prompt for an agent type.

    Args:
        agent_type: The type of agent (browser_agent, developer_agent, etc.)
        context: Optional PromptContext with environment info
        **kwargs: Additional variables for template substitution

    Returns:
        Formatted system prompt string

    Raises:
        KeyError: If agent_type is not found
    """
    prompt = PROMPT_REGISTRY.get(agent_type)
    if not prompt:
        # Default to browser agent for unknown types
        prompt = BROWSER_AGENT_SYSTEM_PROMPT

    return prompt.format(context, **kwargs)


def get_auxiliary_prompt(
    prompt_name: str,
    context: Optional[PromptContext] = None,
    **kwargs
) -> str:
    """Get formatted auxiliary prompt by name.

    Args:
        prompt_name: Name of the auxiliary prompt
        context: Optional PromptContext
        **kwargs: Additional variables

    Returns:
        Formatted prompt string

    Raises:
        KeyError: If prompt_name is not found
    """
    prompt = AUXILIARY_PROMPTS.get(prompt_name)
    if not prompt:
        raise KeyError(f"Auxiliary prompt '{prompt_name}' not found")

    return prompt.format(context, **kwargs)


def list_prompts() -> Dict[str, list]:
    """List all available prompts by category.

    Returns:
        Dictionary with 'main' and 'auxiliary' prompt lists
    """
    return {
        "main": list(PROMPT_REGISTRY.keys()),
        "auxiliary": list(AUXILIARY_PROMPTS.keys()),
    }


def get_all_prompts() -> Dict[str, PromptTemplate]:
    """Get all prompts (main and auxiliary).

    Returns:
        Combined dictionary of all prompts
    """
    return {**PROMPT_REGISTRY, **AUXILIARY_PROMPTS}


# Agent type constants (matching Eigent's definitions)
AGENT_TYPES = {
    "BROWSER": "browser_agent",
    "DEVELOPER": "developer_agent",
    "DOCUMENT": "document_agent",
    "SOCIAL_MEDIUM": "social_medium_agent",
    "QUESTION_CONFIRM": "question_confirm_agent",
}


def get_agent_system_prompt(
    agent_type: str,
    working_directory: str = "",
    memory_reference: str = "",
    workflow_hints: str = "",
    **kwargs
) -> str:
    """Convenience function to get agent prompt with common context.

    Args:
        agent_type: Type of agent
        working_directory: Current working directory
        memory_reference: Memory/workflow reference content
        workflow_hints: Workflow hints content
        **kwargs: Additional context variables

    Returns:
        Formatted system prompt
    """
    context = PromptContext(
        working_directory=working_directory,
        memory_reference=memory_reference,
        workflow_hints=workflow_hints,
        custom_context=kwargs,
    )
    return get_system_prompt(agent_type, context)
