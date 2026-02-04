"""Memory Layer - Abstract Memory Management Interface.

This module provides abstract interfaces for managing memory components including
States, Actions, and CognitivePhrase units.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from src.common.memory.ontology.action import Action
from src.common.memory.ontology.cognitive_phrase import CognitivePhrase
from src.common.memory.ontology.domain import Domain, Manage
from src.common.memory.ontology.intent_sequence import IntentSequence
from src.common.memory.ontology.state import State


class DomainManager(ABC):
    """Abstract Domain Manager for Domain CRUD operations.

    Manages Domain entities using GraphStore backend.
    """

    @abstractmethod
    def create_domain(self, domain: Domain) -> bool:
        """Create a new domain.

        Args:
            domain: Domain object to create.

        Returns:
            True if created successfully, False otherwise.
        """

    @abstractmethod
    def get_domain(self, domain_id: str) -> Optional[Domain]:
        """Get a domain by ID.

        Args:
            domain_id: Unique domain identifier.

        Returns:
            Domain object if found, None otherwise.
        """

    @abstractmethod
    def update_domain(self, domain: Domain) -> bool:
        """Update an existing domain.

        Args:
            domain: Domain object with updated information.

        Returns:
            True if updated successfully, False otherwise.
        """

    @abstractmethod
    def delete_domain(self, domain_id: str) -> bool:
        """Delete a domain.

        Args:
            domain_id: Unique domain identifier.

        Returns:
            True if deleted successfully, False otherwise.
        """

    @abstractmethod
    def list_domains(
        self,
        user_id: Optional[str] = None,
        domain_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Domain]:
        """List domains with optional filters.

        Args:
            user_id: Filter by user ID.
            domain_type: Filter by domain type ('website' or 'app').
            limit: Maximum number of results.

        Returns:
            List of Domain objects matching the filters.
        """

    @abstractmethod
    def batch_create_domains(self, domains: List[Domain]) -> bool:
        """Batch create multiple domains.

        Args:
            domains: List of Domain objects to create.

        Returns:
            True if all created successfully, False otherwise.
        """


class ManageManager(ABC):
    """Abstract Manage Manager for Manage edge CRUD operations.

    Manages Manage edges (Domain -> State connections) using GraphStore backend.
    """

    @abstractmethod
    def create_manage(self, manage: Manage) -> bool:
        """Create a new manage edge.

        Args:
            manage: Manage object to create.

        Returns:
            True if created successfully, False otherwise.
        """

    @abstractmethod
    def get_manage(self, domain_id: str, state_id: str) -> Optional[Manage]:
        """Get a manage edge by domain and state IDs.

        Args:
            domain_id: Domain ID (source).
            state_id: State ID (target).

        Returns:
            Manage object if found, None otherwise.
        """

    @abstractmethod
    def update_manage(self, manage: Manage) -> bool:
        """Update an existing manage edge.

        Args:
            manage: Manage object with updated information.

        Returns:
            True if updated successfully, False otherwise.
        """

    @abstractmethod
    def delete_manage(self, domain_id: str, state_id: str) -> bool:
        """Delete a manage edge.

        Args:
            domain_id: Domain ID (source).
            state_id: State ID (target).

        Returns:
            True if deleted successfully, False otherwise.
        """

    @abstractmethod
    def list_manages(
        self,
        domain_id: Optional[str] = None,
        state_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[Manage]:
        """List manage edges with optional filters.

        Args:
            domain_id: Filter by domain ID.
            state_id: Filter by state ID.
            user_id: Filter by user ID.

        Returns:
            List of Manage objects matching the filters.
        """

    @abstractmethod
    def batch_create_manages(self, manages: List[Manage]) -> bool:
        """Batch create multiple manage edges.

        Args:
            manages: List of Manage objects to create.

        Returns:
            True if all created successfully, False otherwise.
        """


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
    ) -> List[tuple[State, float]]:
        """Search states by embedding vector similarity.

        Args:
            query_vector: Query embedding vector.
            top_k: Number of top results to return.

        Returns:
            List of (State, similarity_score) tuples for top-k similar states.
        """

    @abstractmethod
    def get_connected_actions(
        self,
        state_id: str,
        direction: str = "outgoing"
    ) -> List["Action"]:
        """Get actions connected to the given state.

        Args:
            state_id: State ID to query from.
            direction: Direction to query - "outgoing" for actions where this state is source,
                      "incoming" for actions where this state is target, "both" for all.

        Returns:
            List of Action objects connected to the state.
        """

    @abstractmethod
    def get_k_hop_neighbors(
        self,
        state_id: str,
        k: int = 1,
        direction: str = "outgoing"
    ) -> List[State]:
        """Get states that are k hops away from the given state.

        A k-hop neighbor is a state reachable by traversing exactly k action edges.
        For k=1, returns direct neighbors. For k=2, returns neighbors of neighbors, etc.

        Args:
            state_id: Starting state ID.
            k: Number of hops (degrees of separation). Must be >= 1.
            direction: Direction to traverse - "outgoing" follows action edges forward,
                      "incoming" follows action edges backward, "both" follows edges in both directions.

        Returns:
            List of State objects that are exactly k hops away.
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
        user_id: Optional[str] = None,
    ) -> List[Action]:
        """List actions with optional filters.

        Args:
            source_id: Filter by source state ID.
            target_id: Filter by target state ID.
            action_type: Filter by action type.
            user_id: Filter by user ID.

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

    @abstractmethod
    def find_shortest_path(
        self,
        source_id: str,
        target_id: str,
    ) -> Optional[Tuple[List["State"], List[Action]]]:
        """Find shortest path between two states (v2).

        Uses BFS or graph-native shortest path algorithm to find
        the path with minimum number of actions between two states.

        Args:
            source_id: Source state ID.
            target_id: Target state ID.

        Returns:
            Tuple of (states, actions) representing the path if found,
            None if no path exists.
        """

    @abstractmethod
    def list_outgoing_actions(
        self,
        state_id: str,
    ) -> List[Action]:
        """List all outgoing actions from a state (v2).

        Returns all actions where the given state is the source.

        Args:
            state_id: State ID to get outgoing actions for.

        Returns:
            List of Action objects originating from the state.
        """


class IntentSequenceManager(ABC):
    """Abstract IntentSequence Manager for IntentSequence CRUD operations (v2).

    Manages IntentSequence as independent graph nodes with HAS_SEQUENCE
    relationships to States.
    """

    @abstractmethod
    def create_sequence(self, sequence: IntentSequence) -> bool:
        """Create a new IntentSequence node.

        Args:
            sequence: IntentSequence object to create.

        Returns:
            True if created successfully, False otherwise.
        """

    @abstractmethod
    def get_sequence(self, sequence_id: str) -> Optional[IntentSequence]:
        """Get an IntentSequence by ID.

        Args:
            sequence_id: Unique sequence identifier.

        Returns:
            IntentSequence object if found, None otherwise.
        """

    @abstractmethod
    def update_sequence(self, sequence: IntentSequence) -> bool:
        """Update an existing IntentSequence.

        Args:
            sequence: IntentSequence object with updated information.

        Returns:
            True if updated successfully, False otherwise.
        """

    @abstractmethod
    def delete_sequence(self, sequence_id: str) -> bool:
        """Delete an IntentSequence.

        Args:
            sequence_id: Unique sequence identifier.

        Returns:
            True if deleted successfully, False otherwise.
        """

    @abstractmethod
    def link_to_state(self, state_id: str, sequence_id: str) -> bool:
        """Create HAS_SEQUENCE relationship from State to IntentSequence.

        Args:
            state_id: State ID (source).
            sequence_id: IntentSequence ID (target).

        Returns:
            True if created successfully, False otherwise.
        """

    @abstractmethod
    def unlink_from_state(self, state_id: str, sequence_id: str) -> bool:
        """Remove HAS_SEQUENCE relationship.

        Args:
            state_id: State ID (source).
            sequence_id: IntentSequence ID (target).

        Returns:
            True if removed successfully, False otherwise.
        """

    @abstractmethod
    def list_by_state(self, state_id: str) -> List[IntentSequence]:
        """List all IntentSequences belonging to a State.

        Args:
            state_id: State ID to query.

        Returns:
            List of IntentSequence objects linked to this State.
        """

    @abstractmethod
    def search_by_embedding(
        self,
        query_vector: List[float],
        state_id: Optional[str] = None,
        top_k: int = 10
    ) -> List[Tuple[IntentSequence, float]]:
        """Search IntentSequences by embedding vector similarity.

        Args:
            query_vector: Query embedding vector.
            state_id: Optional filter to specific State.
            top_k: Number of top results to return.

        Returns:
            List of (IntentSequence, similarity_score) tuples.
        """

    @abstractmethod
    def batch_create_sequences(self, sequences: List[IntentSequence]) -> bool:
        """Batch create multiple IntentSequences.

        Args:
            sequences: List of IntentSequence objects to create.

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
    access to Domains, States, Actions, Manages, CognitivePhrases and IntentSequences.

    Attributes:
        domain_manager: DomainManager instance for Domain operations.
        state_manager: StateManager instance for State operations.
        action_manager: ActionManager instance for Action operations.
        manage_manager: ManageManager instance for Manage operations.
        phrase_manager: CognitivePhraseManager instance for CognitivePhrase operations.
        intent_sequence_manager: IntentSequenceManager instance for IntentSequence operations (v2).
    """

    def __init__(
        self,
        domain_manager: DomainManager,
        state_manager: StateManager,
        action_manager: ActionManager,
        manage_manager: ManageManager,
        phrase_manager: CognitivePhraseManager,
        intent_sequence_manager: Optional[IntentSequenceManager] = None,
    ):
        """Initialize Memory with component managers.

        Args:
            domain_manager: DomainManager instance.
            state_manager: StateManager instance.
            action_manager: ActionManager instance.
            manage_manager: ManageManager instance.
            phrase_manager: CognitivePhraseManager instance.
            intent_sequence_manager: IntentSequenceManager instance (optional, v2).
        """
        self.domain_manager = domain_manager
        self.state_manager = state_manager
        self.action_manager = action_manager
        self.manage_manager = manage_manager
        self.phrase_manager = phrase_manager
        self.intent_sequence_manager = intent_sequence_manager

    # Domain operations
    def create_domain(self, domain: Domain) -> bool:
        """Create a new domain."""
        return self.domain_manager.create_domain(domain)

    def get_domain(self, domain_id: str) -> Optional[Domain]:
        """Get a domain by ID."""
        return self.domain_manager.get_domain(domain_id)

    def update_domain(self, domain: Domain) -> bool:
        """Update an existing domain."""
        return self.domain_manager.update_domain(domain)

    def delete_domain(self, domain_id: str) -> bool:
        """Delete a domain."""
        return self.domain_manager.delete_domain(domain_id)

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

    # Manage operations
    def create_manage(self, manage: Manage) -> bool:
        """Create a new manage edge."""
        return self.manage_manager.create_manage(manage)

    def get_manage(self, domain_id: str, state_id: str) -> Optional[Manage]:
        """Get a manage edge."""
        return self.manage_manager.get_manage(domain_id, state_id)

    def update_manage(self, manage: Manage) -> bool:
        """Update an existing manage edge."""
        return self.manage_manager.update_manage(manage)

    def delete_manage(self, domain_id: str, state_id: str) -> bool:
        """Delete a manage edge."""
        return self.manage_manager.delete_manage(domain_id, state_id)

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

    # ============ V2 Query Methods (Lightweight, no LLM) ============

    def query_navigation_path(
        self,
        start_state_id: str,
        end_state_id: str,
    ) -> Optional[Tuple[List["State"], List[Action]]]:
        """Find navigation path between two states (v2 lightweight method).

        Uses BFS to find shortest path. Does not use LLM for semantic matching.
        For semantic state resolution, use Reasoner.query() instead.

        Args:
            start_state_id: Source state ID (must be exact ID).
            end_state_id: Target state ID (must be exact ID).

        Returns:
            Tuple of (states, actions) if path found, None otherwise.
        """
        return self.action_manager.find_shortest_path(
            source_id=start_state_id,
            target_id=end_state_id,
            state_manager=self.state_manager,
        )

    def get_page_capabilities(self, state_id: str) -> Dict[str, Any]:
        """Get all available actions and navigations for a state (v2 exploration).

        Lists all IntentSequences and outgoing Actions for a given state.

        Args:
            state_id: State ID to explore.

        Returns:
            Dictionary with 'sequences' and 'navigations' lists.
        """
        sequences = []
        if self.intent_sequence_manager:
            sequences = self.intent_sequence_manager.list_by_state(state_id)

        navigations = self.action_manager.list_outgoing_actions(state_id)

        return {
            "sequences": sequences,
            "navigations": navigations,
            "state_id": state_id,
        }

    def list_page_actions(
        self,
        state_id: str,
    ) -> List["IntentSequence"]:
        """List all IntentSequences for a state (v2 convenience method).

        Args:
            state_id: State ID.

        Returns:
            List of IntentSequence objects for the state.
        """
        if not self.intent_sequence_manager:
            return []
        return self.intent_sequence_manager.list_by_state(state_id)


__all__ = [
    "DomainManager",
    "ManageManager",
    "StateManager",
    "ActionManager",
    "IntentSequenceManager",
    "CognitivePhraseManager",
    "Memory",
]
