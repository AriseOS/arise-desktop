"""Retrieval results - Result classes for retrieval operations."""

from typing import Any, Dict, List, Optional

from src.ontology.action import Action
from src.ontology.state import State


class RetrievalResult:
    """Result from a single retrieval task."""

    def __init__(
        self,
        success: bool,
        states: List[State],
        actions: List[Action],
        reasoning: str,
    ):
        """Initialize RetrievalResult.

        Args:
            success: Whether retrieval was successful.
            states: Retrieved states.
            actions: Retrieved actions.
            reasoning: Explanation of the result.
        """
        self.success = success
        self.states = states
        self.actions = actions
        self.reasoning = reasoning


class WorkflowResult:
    """Final workflow result."""

    def __init__(
        self,
        target: str,
        success: bool,
        workflow: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize WorkflowResult.

        Args:
            target: Original target.
            success: Whether retrieval was successful.
            workflow: Workflow JSON if successful.
            metadata: Additional metadata.
        """
        self.target = target
        self.success = success
        self.workflow = workflow
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "target": self.target,
            "success": self.success,
            "workflow": self.workflow,
            "metadata": self.metadata,
        }


__all__ = ["RetrievalResult", "WorkflowResult"]
