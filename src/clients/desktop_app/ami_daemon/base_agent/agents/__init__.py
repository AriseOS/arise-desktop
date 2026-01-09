"""
Agent-as-Step implementation module

This module provides step agents for workflow execution.
Each agent defines an INPUT_SCHEMA that specifies its input requirements.
"""
from .base_agent import BaseStepAgent, AgentMetadata, InputSchema, FieldSchema
from .text_agent import TextAgent
from .variable_agent import VariableAgent
from .browser_agent import BrowserAgent
from .scraper_agent import ScraperAgent
from .storage_agent import StorageAgent
from .autonomous_browser_agent import AutonomousBrowserAgent

__all__ = [
    # Base classes and schema
    'BaseStepAgent',
    'AgentMetadata',
    'InputSchema',
    'FieldSchema',
    # Agents
    'TextAgent',
    'VariableAgent',
    'BrowserAgent',
    'ScraperAgent',
    'StorageAgent',
    'AutonomousBrowserAgent',
]


def get_all_agent_schemas() -> dict:
    """Get input schemas for all registered agents.

    Returns:
        Dict mapping agent type names to their InputSchema objects.
        Useful for workflow builders and documentation generation.
    """
    return {
        'text_agent': TextAgent.get_input_schema(),
        'variable': VariableAgent.get_input_schema(),
        'browser_agent': BrowserAgent.get_input_schema(),
        'scraper_agent': ScraperAgent.get_input_schema(),
        'storage_agent': StorageAgent.get_input_schema(),
        'autonomous_browser_agent': AutonomousBrowserAgent.get_input_schema(),
    }