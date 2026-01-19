"""Agent module for executing workflows.

This module provides base agent infrastructure and specialized agents
for executing workflows in different environments.

NOTE: Browser-related components (BrowserAgent, PlaywrightBrowser) have been removed.
"""

from src.cloud_backend.memgraph.agent.base_agent import BaseAgent, AgentResult

__all__ = [
    'BaseAgent',
    'AgentResult',
]
