"""
Specialized agent implementations for AMI Task Executor.

Agent Types:
- developer_agent: Coding, debugging, git operations
- document_agent: Document creation, Google Drive, Notion
- social_medium_agent: Email, calendar, communication
- question_confirm_agent: Human-in-the-loop confirmations
"""

# Specialized agents (used by agent_factories)
from .question_confirm_agent import QuestionConfirmAgent
from .developer_agent import DeveloperAgent
from .document_agent import DocumentAgent
from .social_medium_agent import SocialMediumAgent

__all__ = [
    'QuestionConfirmAgent',
    'DeveloperAgent',
    'DocumentAgent',
    'SocialMediumAgent',
]
