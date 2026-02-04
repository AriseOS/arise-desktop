"""Task Tool - Base class for all task execution tools.

This module defines the base interface for tools that can execute tasks in the reasoning process.
Each tool must implement the execute method to perform its specific functionality.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.common.memory.ontology.action import Action
from src.common.memory.ontology.state import State


class ToolResult:
    """Result from executing a tool."""

    def __init__(
        self,
        success: bool,
        *,
        states: Optional[List[State]] = None,
        actions: Optional[List[Action]] = None,
        data: Optional[Dict[str, Any]] = None,
        reasoning: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize ToolResult.

        Args:
            success: Whether the tool execution was successful.
            states: List of states produced by the tool (if applicable).
            actions: List of actions produced by the tool (if applicable).
            data: Additional data returned by the tool.
            reasoning: Explanation of the result.
            metadata: Additional metadata about the execution.
        """
        self.success = success
        self.states = states or []
        self.actions = actions or []
        self.data = data or {}
        self.reasoning = reasoning
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "states": [s.to_dict() for s in self.states],
            "actions": [a.to_dict() for a in self.actions],
            "data": self.data,
            "reasoning": self.reasoning,
            "metadata": self.metadata,
        }


class TaskTool(ABC):
    """Base class for task execution tools.

    Each tool must implement the execute method to perform its specific functionality.
    Tools can be used by the Reasoner to execute tasks in the TaskDAG.
    """

    def __init__(self, name: str, description: str = ""):
        """Initialize TaskTool.

        Args:
            name: Name of the tool.
            description: Description of what the tool does.
        """
        self.name = name
        self.description = description

    @abstractmethod
    def execute(
        self, target: str, parameters: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """Execute the tool with the given target and parameters.

        Args:
            target: Target description or query for the tool.
            parameters: Additional parameters for tool execution.

        Returns:
            ToolResult containing the execution results.
        """

    def validate_parameters(self, _parameters: Dict[str, Any]) -> bool:
        """Validate tool parameters.

        Returns:
            True if parameters are valid, False otherwise.
        """
        return True

    def get_required_parameters(self) -> List[str]:
        """Get list of required parameter names.

        Returns:
            List of required parameter names.
        """
        return []

    def get_optional_parameters(self) -> Dict[str, Any]:
        """Get dictionary of optional parameters with their default values.

        Returns:
            Dictionary of {parameter_name: default_value}.
        """
        return {}

    def __str__(self) -> str:
        """String representation of the tool."""
        return f"{self.name}: {self.description}"

    def __repr__(self) -> str:
        """Representation of the tool."""
        return f"TaskTool(name='{self.name}')"


__all__ = ["TaskTool", "ToolResult"]
