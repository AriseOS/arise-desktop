"""
Base Toolkit - Foundation for all tool integrations.

Ported from CAMEL-AI/Eigent project for Tool-calling architecture.
Supports both OpenAI and Anthropic tool use formats.

Features:
- Uses CAMEL's FunctionTool for full compatibility with CAMEL agents
- Task state integration for event emission via decorators
"""

import logging
from abc import ABC
from typing import Any, List, Optional

# Re-export CAMEL's FunctionTool for all toolkits to use
from camel.toolkits import FunctionTool

logger = logging.getLogger(__name__)


class BaseToolkit(ABC):
    """Base class for all toolkits.

    A toolkit is a collection of related tools that can be used by agents.

    Attributes:
        timeout: Optional timeout for tool operations in seconds.
        agent_name: Name of the agent using this toolkit (for event tracking).
        _task_state: Task state for event emission via decorators.
    """

    # Agent name for event tracking (can be overridden by subclasses)
    agent_name: str = "unknown"

    # Task state for event emission (set by agent before tool execution)
    _task_state: Optional[Any] = None

    def __init__(self, timeout: Optional[float] = None):
        """Initialize the toolkit.

        Args:
            timeout: Optional timeout for tool operations in seconds.
        """
        self.timeout = timeout
        self._task_state = None

    def set_task_state(self, state: Any) -> None:
        """Set task state for event emission.

        This is called by the agent before executing tools to enable
        automatic event emission via @listen_toolkit decorators.

        Args:
            state: TaskState instance with event emitter.
        """
        self._task_state = state

    def get_task_state(self) -> Optional[Any]:
        """Get current task state.

        Returns:
            TaskState instance or None if not set.
        """
        return self._task_state

    def get_tools(self) -> List[FunctionTool]:
        """Return a list of FunctionTool objects.

        Subclasses should override this to return their specific tools.

        Returns:
            List of FunctionTool objects representing available tools.
        """
        raise NotImplementedError("Subclasses must implement get_tools()")

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit.

        Returns:
            String name of the toolkit (without 'Toolkit' suffix).
        """
        name = cls.__name__
        if name.endswith("Toolkit"):
            name = name[:-7]  # Remove "Toolkit" suffix
        return name
