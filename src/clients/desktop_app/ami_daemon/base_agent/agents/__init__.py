"""
Agent-as-Step implementation module

This module provides step agents for workflow execution.
Each agent defines an INPUT_SCHEMA that specifies its input requirements.

Agent Types (from Eigent):
- browser_agent: Web automation and browser interactions
- developer_agent: Coding, debugging, git operations
- document_agent: Document creation, Google Drive, Notion
- social_medium_agent: Email, calendar, communication
- question_confirm_agent: Human-in-the-loop confirmations
"""
from .base_agent import BaseStepAgent, AgentMetadata, InputSchema, FieldSchema
from .text_agent import TextAgent
from .variable_agent import VariableAgent
from .browser_agent import BrowserAgent
from .scraper_agent import ScraperAgent
from .storage_agent import StorageAgent
from .autonomous_browser_agent import AutonomousBrowserAgent
from .tavily_agent import TavilyAgent
from .eigent_browser_agent import EigentBrowserAgent
from .eigent_style_browser_agent import EigentStyleBrowserAgent

# New specialized agents (from Eigent migration)
from .question_confirm_agent import QuestionConfirmAgent
from .developer_agent import DeveloperAgent
from .document_agent import DocumentAgent
from .social_medium_agent import SocialMediumAgent

__all__ = [
    # Base classes and schema
    'BaseStepAgent',
    'AgentMetadata',
    'InputSchema',
    'FieldSchema',

    # Original agents
    'TextAgent',
    'VariableAgent',
    'BrowserAgent',
    'ScraperAgent',
    'StorageAgent',
    'AutonomousBrowserAgent',
    'TavilyAgent',
    'EigentBrowserAgent',
    'EigentStyleBrowserAgent',

    # New specialized agents (Eigent migration)
    'QuestionConfirmAgent',
    'DeveloperAgent',
    'DocumentAgent',
    'SocialMediumAgent',
]


def get_all_agent_schemas() -> dict:
    """Get input schemas for all registered agents.

    Returns:
        Dict mapping agent type names to their InputSchema objects.
        Useful for workflow builders and documentation generation.
    """
    return {
        # Original agents
        'text_agent': TextAgent.get_input_schema(),
        'variable': VariableAgent.get_input_schema(),
        'browser_agent': BrowserAgent.get_input_schema(),
        'scraper_agent': ScraperAgent.get_input_schema(),
        'storage_agent': StorageAgent.get_input_schema(),
        'autonomous_browser_agent': AutonomousBrowserAgent.get_input_schema(),
        'tavily_agent': TavilyAgent.get_input_schema(),
        'eigent_browser_agent': EigentBrowserAgent.get_input_schema(),
        'eigent_style_browser_agent': EigentStyleBrowserAgent.get_input_schema(),

        # New specialized agents
        'question_confirm_agent': QuestionConfirmAgent.get_input_schema(),
        'developer_agent': DeveloperAgent.get_input_schema(),
        'document_agent': DocumentAgent.get_input_schema(),
        'social_medium_agent': SocialMediumAgent.get_input_schema(),
    }