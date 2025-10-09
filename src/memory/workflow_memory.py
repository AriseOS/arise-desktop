"""Workflow Memory - Implementation of Memory Management.

This module provides concrete implementations of memory managers for
States, Actions, and CognitivePhrase units, using GraphStore for
graph-based storage.
"""

import math
from typing import Any, Dict, List, Optional

from src.graphstore.graph_store import GraphStore
from src.memory.memory import (
    ActionManager,
    CognitivePhraseManager,
    Memory,
    StateManager,
)
from src.ontology.action import Action
from src.ontology.cognitive_phrase import CognitivePhrase
from src.ontology.state import State


class GraphStateManager(StateManager):
    """GraphStore-based State Manager implementation.

    Manages State entities using GraphStore backend with node label 'State'.
    """

    def __init__(self, graph_store: GraphStore):
        """Initialize GraphStateManager.

        Args:
            graph_store: GraphStore instance for storage operations.
        """
        self.graph_store = graph_store
        self.node_label = "State"

    def create_state(self, state: State) -> bool:
        """Create a new state in GraphStore.

        Args:
            state: State object to create.

        Returns:
            True if created successfully, False otherwise.
        """
        try:
            properties = state.to_dict()
            self.graph_store.upsert_node(
                label=self.node_label, properties=properties, id_key="id"
            )
            return True
        except Exception as e:
            print(f"Error creating state: {e}")
            return False

    def get_state(self, state_id: str) -> Optional[State]:
        """Get a state by ID from GraphStore.

        Args:
            state_id: Unique state identifier.

        Returns:
            State object if found, None otherwise.
        """
        try:
            node = self.graph_store.get_node(
                label=self.node_label, id_value=state_id, id_key="id"
            )
            if node:
                return State.from_dict(node)
            return None
        except Exception as e:
            print(f"Error getting state: {e}")
            return None

    def update_state(self, state: State) -> bool:
        """Update an existing state in GraphStore.

        Args:
            state: State object with updated information.

        Returns:
            True if updated successfully, False otherwise.
        """
        try:
            properties = state.to_dict()
            self.graph_store.upsert_node(
                label=self.node_label, properties=properties, id_key="id"
            )
            return True
        except Exception as e:
            print(f"Error updating state: {e}")
            return False

    def delete_state(self, state_id: str) -> bool:
        """Delete a state from GraphStore.

        Args:
            state_id: Unique state identifier.

        Returns:
            True if deleted successfully, False otherwise.
        """
        try:
            self.graph_store.delete_node(
                label=self.node_label, id_value=state_id, id_key="id"
            )
            return True
        except Exception as e:
            print(f"Error deleting state: {e}")
            return False

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
        # Build query conditions
        conditions = []
        if user_id:
            conditions.append(f"n.user_id = '{user_id}'")
        if session_id:
            conditions.append(f"n.session_id = '{session_id}'")
        if start_time:
            conditions.append(f"n.timestamp >= {start_time}")
        if end_time:
            conditions.append(f"n.timestamp <= {end_time}")

        where_clause = " AND ".join(conditions) if conditions else "true"
        limit_clause = f"LIMIT {limit}" if limit else ""

        query = f"""
        MATCH (n:{self.node_label})
        WHERE {where_clause}
        RETURN n
        ORDER BY n.timestamp
        {limit_clause}
        """

        try:
            result = self.graph_store.run_script(query)
            states = []
            if result:
                for record in result:
                    node_data = record.get("n", {})
                    states.append(State.from_dict(node_data))
            return states
        except Exception as e:
            print(f"Error listing states: {e}")
            return []

    def batch_create_states(self, states: List[State]) -> bool:
        """Batch create multiple states.

        Args:
            states: List of State objects to create.

        Returns:
            True if all created successfully, False otherwise.
        """
        try:
            properties_list = [state.to_dict() for state in states]
            self.graph_store.upsert_nodes(
                label=self.node_label, properties_list=properties_list, id_key="id"
            )
            return True
        except Exception as e:
            print(f"Error batch creating states: {e}")
            return False

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
        try:
            # Use GraphStore's vector_search method
            results = self.graph_store.vector_search(
                label=self.node_label,
                property_key="embedding_vector",
                query_text_or_vector=query_vector,
                topk=top_k
            )

            states = []
            if results:
                for result in results:
                    # Extract node data from search result
                    node_data = result if isinstance(result, dict) else result.get("node", {})
                    if node_data:
                        states.append(State.from_dict(node_data))

            return states
        except Exception as e:
            print(f"Error searching states by embedding: {e}")
            # Fallback to simple in-memory cosine similarity if vector search fails
            return self._fallback_embedding_search(query_vector, top_k)

    def _fallback_embedding_search(
        self, query_vector: List[float], top_k: int
    ) -> List[State]:
        """Fallback embedding search using in-memory cosine similarity.

        Args:
            query_vector: Query embedding vector.
            top_k: Number of top results to return.

        Returns:
            List of top-k similar State objects.
        """
        def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
            """Calculate cosine similarity between two vectors."""
            if len(vec1) != len(vec2):
                return 0.0

            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            norm1 = math.sqrt(sum(a * a for a in vec1))
            norm2 = math.sqrt(sum(b * b for b in vec2))

            if norm1 == 0 or norm2 == 0:
                return 0.0

            return dot_product / (norm1 * norm2)

        # Get all states
        all_states = self.list_states()

        # Calculate similarities
        similarities = []
        for state in all_states:
            if state.embedding_vector:
                similarity = cosine_similarity(query_vector, state.embedding_vector)
                similarities.append((state, similarity))

        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Return top-k
        return [state for state, _ in similarities[:top_k]]


class GraphActionManager(ActionManager):
    """GraphStore-based Action Manager implementation.

    Manages Action entities (edges) using GraphStore backend.
    """

    def __init__(self, graph_store: GraphStore):
        """Initialize GraphActionManager.

        Args:
            graph_store: GraphStore instance for storage operations.
        """
        self.graph_store = graph_store
        self.node_label = "State"
        self.rel_type_prefix = "ACTION_"

    def create_action(self, action: Action) -> bool:
        """Create a new action (edge) in GraphStore.

        Args:
            action: Action object to create.

        Returns:
            True if created successfully, False otherwise.
        """
        try:
            properties = action.to_dict()
            rel_type = self.rel_type_prefix + action.type.upper().replace(" ", "_")

            self.graph_store.upsert_relationship(
                start_node_label=self.node_label,
                start_node_id_value=action.source,
                end_node_label=self.node_label,
                end_node_id_value=action.target,
                rel_type=rel_type,
                properties=properties,
                upsert_nodes=False,  # Assume nodes already exist
                start_node_id_key="id",
                end_node_id_key="id",
            )
            return True
        except Exception as e:
            print(f"Error creating action: {e}")
            return False

    def get_action(self, source_id: str, target_id: str) -> Optional[Action]:
        """Get an action by source and target IDs.

        Args:
            source_id: Source state ID.
            target_id: Target state ID.

        Returns:
            Action object if found, None otherwise.
        """
        query = f"""
        MATCH (source:{self.node_label} {{id: '{source_id}'}})-[r]->(target:{self.node_label} {{id: '{target_id}'}})
        RETURN r
        """

        try:
            result = self.graph_store.run_script(query)
            if result and len(result) > 0:
                rel_data = result[0].get("r", {})
                return Action(**rel_data)
            return None
        except Exception as e:
            print(f"Error getting action: {e}")
            return None

    def update_action(self, action: Action) -> bool:
        """Update an existing action in GraphStore.

        Args:
            action: Action object with updated information.

        Returns:
            True if updated successfully, False otherwise.
        """
        try:
            properties = action.to_dict()
            rel_type = self.rel_type_prefix + action.type.upper().replace(" ", "_")

            self.graph_store.upsert_relationship(
                start_node_label=self.node_label,
                start_node_id_value=action.source,
                end_node_label=self.node_label,
                end_node_id_value=action.target,
                rel_type=rel_type,
                properties=properties,
                upsert_nodes=False,
                start_node_id_key="id",
                end_node_id_key="id",
            )
            return True
        except Exception as e:
            print(f"Error updating action: {e}")
            return False

    def delete_action(self, source_id: str, target_id: str) -> bool:
        """Delete an action from GraphStore.

        Args:
            source_id: Source state ID.
            target_id: Target state ID.

        Returns:
            True if deleted successfully, False otherwise.
        """
        try:
            # Need to know the rel_type to delete
            # For now, delete all relationships between the nodes
            query = f"""
            MATCH (source:{self.node_label} {{id: '{source_id}'}})-[r]->(target:{self.node_label} {{id: '{target_id}'}})
            DELETE r
            """
            self.graph_store.run_script(query)
            return True
        except Exception as e:
            print(f"Error deleting action: {e}")
            return False

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
        # Build query conditions
        source_match = f"{{id: '{source_id}'}}" if source_id else ""
        target_match = f"{{id: '{target_id}'}}" if target_id else ""

        query = f"""
        MATCH (source:{self.node_label}{source_match})-[r]->(target:{self.node_label}{target_match})
        RETURN r
        """

        try:
            result = self.graph_store.run_script(query)
            actions = []
            if result:
                for record in result:
                    rel_data = record.get("r", {})
                    action = Action(**rel_data)
                    if action_type is None or action.type == action_type:
                        actions.append(action)
            return actions
        except Exception as e:
            print(f"Error listing actions: {e}")
            return []

    def batch_create_actions(self, actions: List[Action]) -> bool:
        """Batch create multiple actions.

        Args:
            actions: List of Action objects to create.

        Returns:
            True if all created successfully, False otherwise.
        """
        try:
            for action in actions:
                if not self.create_action(action):
                    return False
            return True
        except Exception as e:
            print(f"Error batch creating actions: {e}")
            return False


class InMemoryCognitivePhraseManager(CognitivePhraseManager):
    """In-memory CognitivePhrase Manager implementation.

    Manages CognitivePhrase entities in memory (not using GraphStore).
    This is a simple implementation that can be extended to use
    a persistent storage backend.
    """

    def __init__(self):
        """Initialize InMemoryCognitivePhraseManager."""
        self.phrases: Dict[str, CognitivePhrase] = {}

    def create_phrase(self, phrase: CognitivePhrase) -> bool:
        """Create a new cognitive phrase.

        Args:
            phrase: CognitivePhrase object to create.

        Returns:
            True if created successfully, False otherwise.
        """
        try:
            if phrase.id in self.phrases:
                return False  # Already exists
            self.phrases[phrase.id] = phrase
            return True
        except Exception as e:
            print(f"Error creating phrase: {e}")
            return False

    def get_phrase(self, phrase_id: str) -> Optional[CognitivePhrase]:
        """Get a cognitive phrase by ID.

        Args:
            phrase_id: Unique phrase identifier.

        Returns:
            CognitivePhrase object if found, None otherwise.
        """
        return self.phrases.get(phrase_id)

    def update_phrase(self, phrase: CognitivePhrase) -> bool:
        """Update an existing cognitive phrase.

        Args:
            phrase: CognitivePhrase object with updated information.

        Returns:
            True if updated successfully, False otherwise.
        """
        try:
            if phrase.id not in self.phrases:
                return False  # Doesn't exist
            self.phrases[phrase.id] = phrase
            return True
        except Exception as e:
            print(f"Error updating phrase: {e}")
            return False

    def delete_phrase(self, phrase_id: str) -> bool:
        """Delete a cognitive phrase.

        Args:
            phrase_id: Unique phrase identifier.

        Returns:
            True if deleted successfully, False otherwise.
        """
        try:
            if phrase_id in self.phrases:
                del self.phrases[phrase_id]
                return True
            return False
        except Exception as e:
            print(f"Error deleting phrase: {e}")
            return False

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
        results = []

        for phrase in self.phrases.values():
            # Apply filters
            if user_id and phrase.user_id != user_id:
                continue
            if session_id and phrase.session_id != session_id:
                continue
            if goal_id and phrase.goal_id != goal_id:
                continue
            if start_time and phrase.start_timestamp < start_time:
                continue
            if end_time and phrase.start_timestamp > end_time:
                continue

            results.append(phrase)

        # Sort by timestamp
        results.sort(key=lambda p: p.start_timestamp)

        # Apply limit
        if limit:
            results = results[:limit]

        return results

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
        # Simple cosine similarity implementation
        def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
            """Calculate cosine similarity between two vectors."""
            if len(vec1) != len(vec2):
                return 0.0

            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            norm1 = math.sqrt(sum(a * a for a in vec1))
            norm2 = math.sqrt(sum(b * b for b in vec2))

            if norm1 == 0 or norm2 == 0:
                return 0.0

            return dot_product / (norm1 * norm2)

        # Calculate similarities
        similarities = []
        for phrase in self.phrases.values():
            if phrase.embedding_vector:
                similarity = cosine_similarity(query_vector, phrase.embedding_vector)
                similarities.append((phrase, similarity))

        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Return top-k
        return [phrase for phrase, _ in similarities[:top_k]]


class WorkflowMemory(Memory):
    """Workflow Memory implementation.

    Concrete implementation of Memory interface for managing workflow-based
    memory with States, Actions, and CognitivePhrases.
    """

    def __init__(
        self,
        graph_store: GraphStore,
        phrase_manager: Optional[CognitivePhraseManager] = None,
    ):
        """Initialize WorkflowMemory.

        Args:
            graph_store: GraphStore instance for State and Action storage.
            phrase_manager: Optional CognitivePhraseManager instance.
                If not provided, uses InMemoryCognitivePhraseManager.
        """
        state_manager = GraphStateManager(graph_store)
        action_manager = GraphActionManager(graph_store)

        if phrase_manager is None:
            phrase_manager = InMemoryCognitivePhraseManager()

        super().__init__(state_manager, action_manager, phrase_manager)
        self.graph_store = graph_store

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
        # Create the state
        if not self.create_state(state):
            return False

        # Create the action if provided
        if previous_state_id and action:
            # Ensure action connects previous state to current state
            action.source = previous_state_id
            action.target = state.id
            return self.create_action(action)

        return True

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
        # Get all states for the session
        states = self.state_manager.list_states(
            session_id=session_id, start_time=start_time, end_time=end_time
        )

        if not states:
            return {
                "session_id": session_id,
                "states": [],
                "actions": [],
                "metadata": {"state_count": 0, "action_count": 0},
            }

        # Get state IDs
        state_ids = [state.id for state in states]

        # Get actions between these states
        actions = []
        for i in range(len(state_ids) - 1):
            action = self.action_manager.get_action(state_ids[i], state_ids[i + 1])
            if action:
                actions.append(action)

        return {
            "session_id": session_id,
            "states": [state.to_dict() for state in states],
            "actions": [action.to_dict() for action in actions],
            "metadata": {
                "state_count": len(states),
                "action_count": len(actions),
                "start_time": states[0].timestamp if states else None,
                "end_time": states[-1].timestamp if states else None,
            },
        }

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
        # Get trajectory
        trajectory = self.get_workflow_trajectory(session_id, start_time, end_time)

        if not trajectory["states"]:
            return None

        # Extract states
        states = [State.from_dict(s) for s in trajectory["states"]]
        actions = [Action(**a) for a in trajectory["actions"]]

        # Create CognitivePhrase
        phrase = CognitivePhrase(
            label=label,
            description=description,
            start_timestamp=states[0].timestamp,
            end_timestamp=(
                states[-1].timestamp if len(states) > 0 else states[0].timestamp
            ),
            duration=(
                (states[-1].timestamp - states[0].timestamp) if len(states) > 1 else 0
            ),
            user_id=states[0].user_id if states else None,
            session_id=session_id,
            states=states,
            state_ids=[s.id for s in states],
            actions=actions,
        )

        # Save the phrase
        if self.create_phrase(phrase):
            return phrase
        return None

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
        if not query_phrase.embedding_vector:
            return []

        return self.phrase_manager.search_phrases_by_embedding(
            query_vector=query_phrase.embedding_vector, top_k=top_k
        )

    def export_memory(self) -> Dict[str, Any]:
        """Export all memory data.

        Returns:
            Dictionary containing all states, actions, and phrases.
        """
        # Get all states
        states = self.state_manager.list_states()

        # Get all actions
        actions = self.action_manager.list_actions()

        # Get all phrases
        phrases = self.phrase_manager.list_phrases()

        return {
            "states": [state.to_dict() for state in states],
            "actions": [action.to_dict() for action in actions],
            "phrases": [phrase.to_dict() for phrase in phrases],
            "metadata": {
                "state_count": len(states),
                "action_count": len(actions),
                "phrase_count": len(phrases),
            },
        }

    def import_memory(self, data: Dict[str, Any]) -> bool:
        """Import memory data.

        Args:
            data: Dictionary containing memory data.

        Returns:
            True if imported successfully, False otherwise.
        """
        try:
            # Import states
            if "states" in data:
                states = [State.from_dict(s) for s in data["states"]]
                if not self.state_manager.batch_create_states(states):
                    return False

            # Import actions
            if "actions" in data:
                actions = [Action(**a) for a in data["actions"]]
                if not self.action_manager.batch_create_actions(actions):
                    return False

            # Import phrases
            if "phrases" in data:
                for phrase_data in data["phrases"]:
                    phrase = CognitivePhrase.from_dict(phrase_data)
                    if not self.create_phrase(phrase):
                        return False

            return True
        except Exception as e:
            print(f"Error importing memory: {e}")
            return False


__all__ = [
    "GraphStateManager",
    "GraphActionManager",
    "InMemoryCognitivePhraseManager",
    "WorkflowMemory",
]
