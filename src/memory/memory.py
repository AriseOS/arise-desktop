"""Memory Layer - Abstract Memory Management Interface.

This module provides abstract interfaces for managing memory components including
States, Actions, and CognitivePhrase units.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.ontology.action import Action
from src.ontology.cognitive_phrase import CognitivePhrase
from src.ontology.state import State


class StateManager(ABC):
    """Abstract State Manager for State CRUD operations.

    Manages State entities using GraphStore backend.
    """

    @abstractmethod
    def create_state(self, state: State) -> bool:
        """Create a new state.

        Args:
            state: State object to create.

        Returns:
            True if created successfully, False otherwise.
        """

    @abstractmethod
    def get_state(self, state_id: str) -> Optional[State]:
        """Get a state by ID.

        Args:
            state_id: Unique state identifier.

        Returns:
            State object if found, None otherwise.
        """

    @abstractmethod
    def update_state(self, state: State) -> bool:
        """Update an existing state.

        Args:
            state: State object with updated information.

        Returns:
            True if updated successfully, False otherwise.
        """

    @abstractmethod
    def delete_state(self, state_id: str) -> bool:
        """Delete a state.

        Args:
            state_id: Unique state identifier.

        Returns:
            True if deleted successfully, False otherwise.
        """

    @abstractmethod
    def list_states(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[State]:
        """List states with optional filters.

        Args:
            user_id: Filter by user ID.
            session_id: Filter by session ID.
            start_time: Filter by start timestamp.
            end_time: Filter by end timestamp.
            limit: Maximum number of results.

        Returns:
            List of State objects matching the filters.
        """

    @abstractmethod
    def batch_create_states(self, states: List[State]) -> bool:
        """Batch create multiple states.

        Args:
            states: List of State objects to create.

        Returns:
            True if all created successfully, False otherwise.
        """

    @abstractmethod
    def search_states_by_embedding(
        self, query_vector: List[float], top_k: int = 10
    ) -> List[State]:
        """Search states by embedding vector similarity.

        Args:
            query_vector: Query embedding vector.
            top_k: Number of top results to return.

        Returns:
            List of top-k similar State objects.
        """


class ActionManager(ABC):
    """Abstract Action Manager for Action CRUD operations.

    Manages Action entities (edges) using GraphStore backend.
    """

    @abstractmethod
    def create_action(self, action: Action) -> bool:
        """Create a new action (edge).

        Args:
            action: Action object to create.

        Returns:
            True if created successfully, False otherwise.
        """

    @abstractmethod
    def get_action(self, source_id: str, target_id: str) -> Optional[Action]:
        """Get an action by source and target IDs.

        Args:
            source_id: Source state ID.
            target_id: Target state ID.

        Returns:
            Action object if found, None otherwise.
        """

    @abstractmethod
    def update_action(self, action: Action) -> bool:
        """Update an existing action.

        Args:
            action: Action object with updated information.

        Returns:
            True if updated successfully, False otherwise.
        """

    @abstractmethod
    def delete_action(self, source_id: str, target_id: str) -> bool:
        """Delete an action.

        Args:
            source_id: Source state ID.
            target_id: Target state ID.

        Returns:
            True if deleted successfully, False otherwise.
        """

    @abstractmethod
    def list_actions(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        action_type: Optional[str] = None,
    ) -> List[Action]:
        """List actions with optional filters.

        Args:
            source_id: Filter by source state ID.
            target_id: Filter by target state ID.
            action_type: Filter by action type.

        Returns:
            List of Action objects matching the filters.
        """

    @abstractmethod
    def batch_create_actions(self, actions: List[Action]) -> bool:
        """Batch create multiple actions.

        Args:
            actions: List of Action objects to create.

        Returns:
            True if all created successfully, False otherwise.
        """


class CognitivePhraseManager(ABC):
    """Abstract CognitivePhrase Manager for CognitivePhrase CRUD operations.

    Manages CognitivePhrase entities directly (not through GraphStore).
    """

    @abstractmethod
    def create_phrase(self, phrase: CognitivePhrase) -> bool:
        """Create a new cognitive phrase.

        Args:
            phrase: CognitivePhrase object to create.

        Returns:
            True if created successfully, False otherwise.
        """

    @abstractmethod
    def get_phrase(self, phrase_id: str) -> Optional[CognitivePhrase]:
        """Get a cognitive phrase by ID.

        Args:
            phrase_id: Unique phrase identifier.

        Returns:
            CognitivePhrase object if found, None otherwise.
        """

    @abstractmethod
    def update_phrase(self, phrase: CognitivePhrase) -> bool:
        """Update an existing cognitive phrase.

        Args:
            phrase: CognitivePhrase object with updated information.

        Returns:
            True if updated successfully, False otherwise.
        """

    @abstractmethod
    def delete_phrase(self, phrase_id: str) -> bool:
        """Delete a cognitive phrase.

        Args:
            phrase_id: Unique phrase identifier.

        Returns:
            True if deleted successfully, False otherwise.
        """

    @abstractmethod
    def list_phrases(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        goal_id: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[CognitivePhrase]:
        """List cognitive phrases with optional filters.

        Args:
            user_id: Filter by user ID.
            session_id: Filter by session ID.
            goal_id: Filter by goal ID.
            start_time: Filter by start timestamp.
            end_time: Filter by end timestamp.
            limit: Maximum number of results.

        Returns:
            List of CognitivePhrase objects matching the filters.
        """

    @abstractmethod
    def search_phrases_by_embedding(
        self, query_vector: List[float], top_k: int = 10
    ) -> List[CognitivePhrase]:
        """Search cognitive phrases by embedding vector.

        Args:
            query_vector: Query embedding vector.
            top_k: Number of top results to return.

        Returns:
            List of top-k similar CognitivePhrase objects.
        """


class Memory(ABC):
    """Abstract Memory interface integrating all memory components.

    This is the main interface for memory operations, providing unified
    access to States, Actions, and CognitivePhrases.

    Attributes:
        state_manager: StateManager instance for State operations.
        action_manager: ActionManager instance for Action operations.
        phrase_manager: CognitivePhraseManager instance for CognitivePhrase operations.
    """

    def __init__(
        self,
        state_manager: StateManager,
        action_manager: ActionManager,
        phrase_manager: CognitivePhraseManager,
    ):
        """Initialize Memory with component managers.

        Args:
            state_manager: StateManager instance.
            action_manager: ActionManager instance.
            phrase_manager: CognitivePhraseManager instance.
        """
        self.state_manager = state_manager
        self.action_manager = action_manager
        self.phrase_manager = phrase_manager

    # State operations
    def create_state(self, state: State) -> bool:
        """Create a new state."""
        return self.state_manager.create_state(state)

    def get_state(self, state_id: str) -> Optional[State]:
        """Get a state by ID."""
        return self.state_manager.get_state(state_id)

    def update_state(self, state: State) -> bool:
        """Update an existing state."""
        return self.state_manager.update_state(state)

    def delete_state(self, state_id: str) -> bool:
        """Delete a state."""
        return self.state_manager.delete_state(state_id)

    # Action operations
    def create_action(self, action: Action) -> bool:
        """Create a new action."""
        return self.action_manager.create_action(action)

    def get_action(self, source_id: str, target_id: str) -> Optional[Action]:
        """Get an action."""
        return self.action_manager.get_action(source_id, target_id)

    def update_action(self, action: Action) -> bool:
        """Update an existing action."""
        return self.action_manager.update_action(action)

    def delete_action(self, source_id: str, target_id: str) -> bool:
        """Delete an action."""
        return self.action_manager.delete_action(source_id, target_id)

    # CognitivePhrase operations
    def create_phrase(self, phrase: CognitivePhrase) -> bool:
        """Create a new cognitive phrase."""
        return self.phrase_manager.create_phrase(phrase)

    def get_phrase(self, phrase_id: str) -> Optional[CognitivePhrase]:
        """Get a cognitive phrase by ID."""
        return self.phrase_manager.get_phrase(phrase_id)

    def update_phrase(self, phrase: CognitivePhrase) -> bool:
        """Update an existing cognitive phrase."""
        return self.phrase_manager.update_phrase(phrase)

    def delete_phrase(self, phrase_id: str) -> bool:
        """Delete a cognitive phrase."""
        return self.phrase_manager.delete_phrase(phrase_id)

    # High-level operations
    @abstractmethod
    def add_workflow_step(
        self,
        state: State,
        previous_state_id: Optional[str] = None,
        action: Optional[Action] = None,
    ) -> bool:
        """Add a workflow step (state with optional transition).

        Args:
            state: State to add.
            previous_state_id: Previous state ID to link from.
            action: Optional Action to create the link.

        Returns:
            True if added successfully, False otherwise.
        """

    @abstractmethod
    def get_workflow_trajectory(
        self,
        session_id: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get a workflow trajectory for a session.

        Args:
            session_id: Session ID.
            start_time: Optional start time filter.
            end_time: Optional end time filter.

        Returns:
            Dictionary containing states, actions, and metadata.
        """

    @abstractmethod
    def create_phrase_from_trajectory(
        self,
        session_id: str,
        label: str,
        description: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Optional[CognitivePhrase]:
        """Create a CognitivePhrase from a workflow trajectory.

        Args:
            session_id: Session ID.
            label: Phrase label.
            description: Optional phrase description.
            start_time: Optional start time filter.
            end_time: Optional end time filter.

        Returns:
            Created CognitivePhrase if successful, None otherwise.
        """

    @abstractmethod
    def search_similar_workflows(
        self, query_phrase: CognitivePhrase, top_k: int = 10
    ) -> List[CognitivePhrase]:
        """Search for similar workflow patterns.

        Args:
            query_phrase: Query CognitivePhrase.
            top_k: Number of top results to return.

        Returns:
            List of similar CognitivePhrase objects.
        """

    @abstractmethod
    def export_memory(self) -> Dict[str, Any]:
        """Export all memory data.

        Returns:
            Dictionary containing all states, actions, and phrases.
        """

    @abstractmethod
    def import_memory(self, data: Dict[str, Any]) -> bool:
        """Import memory data.

        Args:
            data: Dictionary containing memory data.

        Returns:
            True if imported successfully, False otherwise.
        """


__all__ = [
    "StateManager",
    "ActionManager",
    "CognitivePhraseManager",
    "Memory",
]
