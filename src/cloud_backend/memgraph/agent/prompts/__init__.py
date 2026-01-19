"""Prompts for agent module."""

from src.cloud_backend.memgraph.agent.prompts.browser_action_generation_prompt import (
    BrowserActionGenerationPrompt,
    BrowserActionGenerationInput,
    BrowserActionGenerationOutput,
    BrowserActionNode,
)

__all__ = [
    'BrowserActionGenerationPrompt',
    'BrowserActionGenerationInput',
    'BrowserActionGenerationOutput',
    'BrowserActionNode',
]
