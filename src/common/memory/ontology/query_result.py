"""Query Result - Unified query result models for Memory Graph V2.

This module provides unified result structures for task-level, navigation-level,
and action-level queries.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from src.common.memory.ontology.action import Action
from src.common.memory.ontology.cognitive_phrase import (
    CognitivePhrase,
    ExecutionStep,
)
from src.common.memory.ontology.intent_sequence import IntentSequence
from src.common.memory.ontology.state import State


class SubTaskResult(BaseModel):
    """Result for a single subtask from task decomposition."""

    task_id: str = Field(..., description="Subtask identifier")
    target: str = Field(..., description="Subtask target description")

    # Reference to global path by indices, not full path storage
    path_state_indices: List[int] = Field(
        default_factory=list,
        description="Indices into global path states that this subtask operates on"
    )

    found: bool = Field(
        default=False,
        description="Whether this subtask has navigation info (path_state_indices non-empty)"
    )


class NavigationResult(BaseModel):
    """Navigation query specific result.

    Contains ordered lists of states and actions representing the path
    from start to end state.
    """

    states: List[State] = Field(default_factory=list, description="Ordered states in path")
    actions: List[Action] = Field(default_factory=list, description="Actions connecting states")


class TaskResult(BaseModel):
    """Task query specific result.

    Contains execution plan and optional cognitive phrase for task execution.
    """

    execution_plan: List[ExecutionStep] = Field(
        default_factory=list, description="Structured execution plan"
    )
    cognitive_phrase: Optional[CognitivePhrase] = Field(
        default=None, description="Matched cognitive phrase if found"
    )


class QueryResult(BaseModel):
    """Unified query result for all query types.

    Supports task-level, navigation-level, and action-level query results
    with type-specific data and convenient conversion methods.
    """

    # Meta information
    query_type: Literal["navigation", "action", "task"] = Field(
        ..., description="Type of query that produced this result"
    )
    success: bool = Field(..., description="Whether the query succeeded")

    # Common fields (populated based on query_type)
    states: List[State] = Field(
        default_factory=list, description="States involved in the result"
    )
    actions: List[Action] = Field(
        default_factory=list, description="Actions involved in the result"
    )
    intent_sequences: List[IntentSequence] = Field(
        default_factory=list, description="IntentSequences for action queries"
    )

    # Task-level specific
    cognitive_phrase: Optional[CognitivePhrase] = Field(
        default=None, description="Matched cognitive phrase for task queries"
    )
    execution_plan: List[ExecutionStep] = Field(
        default_factory=list, description="Structured execution plan for task queries"
    )
    subtasks: List[SubTaskResult] = Field(
        default_factory=list, description="Subtask decomposition results for task queries"
    )

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional query metadata"
    )

    # ============ Convenience Conversion Methods ============

    def as_navigation(self) -> NavigationResult:
        """Convert to navigation-specific result.

        Returns:
            NavigationResult with states and actions.

        Raises:
            ValueError: If this is not a navigation query result.
        """
        if self.query_type != "navigation":
            raise ValueError(
                f"Cannot convert {self.query_type} query result to NavigationResult"
            )
        return NavigationResult(states=self.states, actions=self.actions)

    def as_task(self) -> TaskResult:
        """Convert to task-specific result.

        Returns:
            TaskResult with execution plan and cognitive phrase.

        Raises:
            ValueError: If this is not a task query result.
        """
        if self.query_type != "task":
            raise ValueError(f"Cannot convert {self.query_type} query result to TaskResult")
        return TaskResult(
            execution_plan=self.execution_plan,
            cognitive_phrase=self.cognitive_phrase,
        )

    # ============ Factory Methods ============

    @classmethod
    def navigation_success(
        cls,
        states: List[State],
        actions: List[Action],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "QueryResult":
        """Create a successful navigation result."""
        return cls(
            query_type="navigation",
            success=True,
            states=states,
            actions=actions,
            metadata=metadata or {},
        )

    @classmethod
    def navigation_failure(
        cls,
        error: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "QueryResult":
        """Create a failed navigation result."""
        return cls(
            query_type="navigation",
            success=False,
            metadata={"error": error, **(metadata or {})},
        )

    @classmethod
    def action_success(
        cls,
        intent_sequences: List[IntentSequence],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "QueryResult":
        """Create a successful action result."""
        return cls(
            query_type="action",
            success=True,
            intent_sequences=intent_sequences,
            metadata=metadata or {},
        )

    @classmethod
    def action_failure(
        cls,
        error: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "QueryResult":
        """Create a failed action result."""
        return cls(
            query_type="action",
            success=False,
            metadata={"error": error, **(metadata or {})},
        )

    @classmethod
    def task_success(
        cls,
        states: List[State],
        actions: List[Action],
        execution_plan: Optional[List[ExecutionStep]] = None,
        cognitive_phrase: Optional[CognitivePhrase] = None,
        subtasks: Optional[List[SubTaskResult]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "QueryResult":
        """Create a successful task result."""
        return cls(
            query_type="task",
            success=True,
            states=states,
            actions=actions,
            execution_plan=execution_plan or [],
            cognitive_phrase=cognitive_phrase,
            subtasks=subtasks or [],
            metadata=metadata or {},
        )

    @classmethod
    def task_failure(
        cls,
        error: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "QueryResult":
        """Create a failed task result."""
        return cls(
            query_type="task",
            success=False,
            metadata={"error": error, **(metadata or {})},
        )


__all__ = ["QueryResult", "NavigationResult", "TaskResult", "SubTaskResult"]
