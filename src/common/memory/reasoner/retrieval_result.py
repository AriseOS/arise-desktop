"""Retrieval results - Result classes for retrieval operations."""

from typing import Any, Dict, List, Optional

from src.common.memory.ontology.action import Action
from src.common.memory.ontology.state import State


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
    """Final workflow result.

    Contains both the workflow JSON representation and the original
    ontology objects (states and actions) used to construct it.
    """

    def __init__(
        self,
        target: str,
        success: bool,
        workflow: Optional[Dict[str, Any]] = None,
        states: Optional[List[State]] = None,
        actions: Optional[List[Action]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize WorkflowResult.

        Args:
            target: Original target description.
            success: Whether retrieval was successful.
            workflow: Workflow JSON if successful (for backward compatibility).
            states: List of State objects in the workflow.
            actions: List of Action objects connecting the states.
            metadata: Additional metadata (cognitive phrases, etc.).
        """
        self.target = target
        self.success = success
        self.workflow = workflow
        self.states = states or []
        self.actions = actions or []
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation including workflow JSON and metadata.
        """
        return {
            "target": self.target,
            "success": self.success,
            "workflow": self.workflow,
            "num_states": len(self.states),
            "num_actions": len(self.actions),
            "metadata": self.metadata,
        }


__all__ = ["RetrievalResult", "WorkflowResult"]
