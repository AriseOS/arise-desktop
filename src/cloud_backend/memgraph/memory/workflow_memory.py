"""Workflow Memory - Implementation of Memory Management.

This module provides concrete implementations of memory managers for
States, Actions, and CognitivePhrase units, using GraphStore for
graph-based storage.
"""

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from src.cloud_backend.memgraph.graphstore.graph_store import GraphStore
from src.cloud_backend.memgraph.memory.memory import (
    ActionManager,
    CognitivePhraseManager,
    DomainManager,
    IntentSequenceManager,
    ManageManager,
    Memory,
    StateManager,
)
from src.cloud_backend.memgraph.memory.url_index import URLIndex
from src.cloud_backend.memgraph.ontology.action import Action
from src.cloud_backend.memgraph.ontology.cognitive_phrase import CognitivePhrase
from src.cloud_backend.memgraph.ontology.domain import Domain, Manage
from src.cloud_backend.memgraph.ontology.intent_sequence import IntentSequence
from src.cloud_backend.memgraph.ontology.page_instance import PageInstance
from src.cloud_backend.memgraph.ontology.state import State

logger = logging.getLogger(__name__)


class GraphDomainManager(DomainManager):
    """GraphStore-based Domain Manager implementation.

    Manages Domain entities using GraphStore backend with node label 'Domain'.
    """

    def __init__(self, graph_store: GraphStore):
        """Initialize GraphDomainManager.

        Args:
            graph_store: GraphStore instance for storage operations.
        """
        self.graph_store = graph_store
        self.node_label = "Domain"

    def create_domain(self, domain: Domain) -> bool:
        """Create a new domain in GraphStore.

        Args:
            domain: Domain object to create.

        Returns:
            True if created successfully, False otherwise.
        """
        try:
            properties = domain.to_dict()
            self.graph_store.upsert_node(
                label=self.node_label, properties=properties, id_key="id"
            )
            return True
        except Exception as e:
            logger.error(f" creating domain: {e}")
            return False

    def get_domain(self, domain_id: str) -> Optional[Domain]:
        """Get a domain by ID from GraphStore.

        Args:
            domain_id: Unique domain identifier.

        Returns:
            Domain object if found, None otherwise.
        """
        try:
            node = self.graph_store.get_node(
                label=self.node_label, id_value=domain_id, id_key="id"
            )
            if node:
                return Domain.from_dict(node)
            return None
        except Exception as e:
            logger.error(f" getting domain: {e}")
            return None

    def update_domain(self, domain: Domain) -> bool:
        """Update an existing domain in GraphStore.

        Args:
            domain: Domain object with updated information.

        Returns:
            True if updated successfully, False otherwise.
        """
        try:
            properties = domain.to_dict()
            self.graph_store.upsert_node(
                label=self.node_label, properties=properties, id_key="id"
            )
            return True
        except Exception as e:
            logger.error(f" updating domain: {e}")
            return False

    def delete_domain(self, domain_id: str) -> bool:
        """Delete a domain from GraphStore.

        Args:
            domain_id: Unique domain identifier.

        Returns:
            True if deleted successfully, False otherwise.
        """
        try:
            self.graph_store.delete_node(
                label=self.node_label, id_value=domain_id, id_key="id"
            )
            return True
        except Exception as e:
            logger.error(f" deleting domain: {e}")
            return False

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
        try:
            filters = {}
            if user_id:
                filters["user_id"] = user_id
            if domain_type:
                filters["domain_type"] = domain_type

            nodes = self.graph_store.query_nodes(
                label=self.node_label, filters=filters, limit=limit
            )
            return [Domain.from_dict(node) for node in nodes]
        except Exception as e:
            logger.error(f" listing domains: {e}")
            return []

    def batch_create_domains(self, domains: List[Domain]) -> bool:
        """Batch create multiple domains.

        Args:
            domains: List of Domain objects to create.

        Returns:
            True if all created successfully, False otherwise.
        """
        try:
            for domain in domains:
                if not self.create_domain(domain):
                    return False
            return True
        except Exception as e:
            logger.error(f" batch creating domains: {e}")
            return False


class GraphManageManager(ManageManager):
    """GraphStore-based Manage Manager implementation.

    Manages Manage edges (Domain -> State) using GraphStore backend.
    """

    def __init__(self, graph_store: GraphStore):
        """Initialize GraphManageManager.

        Args:
            graph_store: GraphStore instance for storage operations.
        """
        self.graph_store = graph_store
        self.rel_type = "MANAGES"

    def create_manage(self, manage: Manage) -> bool:
        """Create a new manage edge in GraphStore.

        Args:
            manage: Manage object to create.

        Returns:
            True if created successfully, False otherwise.
        """
        try:
            properties = manage.to_dict()
            self.graph_store.upsert_relationship(
                start_node_label="Domain",
                start_node_id_value=manage.domain_id,
                end_node_label="State",
                end_node_id_value=manage.state_id,
                rel_type=self.rel_type,
                properties=properties,
            )
            return True
        except Exception as e:
            logger.error(f" creating manage edge: {e}")
            return False

    def get_manage(self, domain_id: str, state_id: str) -> Optional[Manage]:
        """Get a manage edge by domain and state IDs.

        Args:
            domain_id: Domain ID (source).
            state_id: State ID (target).

        Returns:
            Manage object if found, None otherwise.
        """
        try:
            # Query relationships between domain and state
            rels = self.graph_store.query_relationships(
                start_node_label="Domain",
                start_node_id_value=domain_id,
                end_node_label="State",
                end_node_id_value=state_id,
                rel_type=self.rel_type
            )

            if rels and len(rels) > 0:
                # Get the first relationship
                rel_data = rels[0]['rel']
                return Manage.from_dict(rel_data)
            return None
        except Exception as e:
            logger.error(f" getting manage edge: {e}")
            return None

    def update_manage(self, manage: Manage) -> bool:
        """Update an existing manage edge in GraphStore.

        Args:
            manage: Manage object with updated information.

        Returns:
            True if updated successfully, False otherwise.
        """
        try:
            properties = manage.to_dict()
            self.graph_store.upsert_relationship(
                start_node_label="Domain",
                start_node_id_value=manage.domain_id,
                end_node_label="State",
                end_node_id_value=manage.state_id,
                rel_type=self.rel_type,
                properties=properties,
                upsert_nodes=False
            )
            return True
        except Exception as e:
            logger.error(f" updating manage edge: {e}")
            return False

    def delete_manage(self, domain_id: str, state_id: str) -> bool:
        """Delete a manage edge from GraphStore.

        Args:
            domain_id: Domain ID (source).
            state_id: State ID (target).

        Returns:
            True if deleted successfully, False otherwise.
        """
        try:
            self.graph_store.delete_relationship(
                start_node_label="Domain",
                start_node_id_value=domain_id,
                end_node_label="State",
                end_node_id_value=state_id,
                rel_type=self.rel_type
            )
            return True
        except Exception as e:
            logger.error(f" deleting manage edge: {e}")
            return False

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
        try:
            # Query relationships with filters
            rels = self.graph_store.query_relationships(
                start_node_label="Domain",
                start_node_id_value=domain_id,
                end_node_label="State",
                end_node_id_value=state_id,
                rel_type=self.rel_type
            )

            manages = []
            for rel_data_dict in rels:
                rel_props = rel_data_dict['rel']

                # Build Manage object
                manage = Manage.from_dict(rel_props)

                # Apply user_id filter if specified
                if user_id and manage.user_id != user_id:
                    continue

                manages.append(manage)

            return manages
        except Exception as e:
            logger.error(f" listing manage edges: {e}")
            return []

    def batch_create_manages(self, manages: List[Manage]) -> bool:
        """Batch create multiple manage edges.

        Args:
            manages: List of Manage objects to create.

        Returns:
            True if all created successfully, False otherwise.
        """
        try:
            for manage in manages:
                if not self.create_manage(manage):
                    return False
            return True
        except Exception as e:
            logger.error(f" batch creating manage edges: {e}")
            return False


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
            logger.error(f" creating state: {e}")
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
            logger.error(f" getting state: {e}")
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
            logger.error(f" updating state: {e}")
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
            logger.error(f" deleting state: {e}")
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
        try:
            # Build filters for query_nodes
            filters = {}
            if user_id:
                filters["user_id"] = user_id
            if session_id:
                filters["session_id"] = session_id

            # Query nodes with basic filters
            nodes = self.graph_store.query_nodes(
                label=self.node_label,
                filters=filters if filters else None,
                limit=None  # Will filter and limit after time filtering
            )

            # Convert to State objects
            states = [State.from_dict(node) for node in nodes]

            # Apply time filters (not supported by query_nodes directly)
            if start_time:
                states = [s for s in states if s.timestamp >= start_time]
            if end_time:
                states = [s for s in states if s.timestamp <= end_time]

            # Sort by timestamp
            states.sort(key=lambda s: s.timestamp)

            # Apply limit
            if limit:
                states = states[:limit]

            return states
        except Exception as e:
            logger.error(f" listing states: {e}")
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
            logger.error(f" batch creating states: {e}")
            return False

    def search_states_by_embedding(
        self, query_vector: List[float], top_k: int = 10
    ) -> List[tuple[State, float]]:
        """Search states by embedding vector similarity.

        Args:
            query_vector: Query embedding vector.
            top_k: Number of top results to return.

        Returns:
            List of tuples (State, similarity_score).
        """
        # Try Neo4j native vector search first
        try:
            results = self.graph_store.vector_search(
                label="State",
                property_key="embedding_vector",
                query_text_or_vector=query_vector,
                topk=top_k,
            )
            states = []
            for node, score in results:
                state = State.from_dict(node)
                states.append((state, score))
            return states
        except Exception as e:
            # Fallback to in-memory search if vector index not available
            logger.warning(f"Neo4j vector search failed, using fallback: {e}")
            return self._fallback_embedding_search(query_vector, top_k)

    def _fallback_embedding_search(
        self, query_vector: List[float], top_k: int
    ) -> List[tuple[State, float]]:
        """Fallback embedding search using in-memory cosine similarity.

        Args:
            query_vector: Query embedding vector.
            top_k: Number of top results to return.

        Returns:
            List of tuples (State, similarity_score).
        """
        def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
            """Calculate cosine similarity between two vectors."""
            if not vec1 or not vec2 or len(vec1) != len(vec2):
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

        # Return top-k with scores
        return similarities[:top_k]

    def get_connected_actions(
        self,
        state_id: str,
        direction: str = "outgoing"
    ) -> List[Action]:
        """Get actions connected to the given state.

        Args:
            state_id: State ID to query from.
            direction: Direction to query - "outgoing" for actions where this state is source,
                      "incoming" for actions where this state is target, "both" for all.

        Returns:
            List of Action objects connected to the state.
        """
        try:
            actions = []

            if direction in ("outgoing", "both"):
                # Query outgoing actions (state is source)
                rels = self.graph_store.query_relationships(
                    start_node_label=self.node_label,
                    start_node_id_value=state_id,
                    end_node_label=self.node_label
                )
                for rel_data in rels:
                    rel_props = rel_data['rel']
                    start_node = rel_data['start']
                    end_node = rel_data['end']

                    # Create Action object
                    action_dict = dict(rel_props)
                    if 'source' not in action_dict:
                        action_dict['source'] = start_node.get('id')
                    if 'target' not in action_dict:
                        action_dict['target'] = end_node.get('id')

                    actions.append(Action(**action_dict))

            if direction in ("incoming", "both"):
                # Query incoming actions (state is target)
                rels = self.graph_store.query_relationships(
                    start_node_label=self.node_label,
                    end_node_label=self.node_label,
                    end_node_id_value=state_id
                )
                for rel_data in rels:
                    rel_props = rel_data['rel']
                    start_node = rel_data['start']
                    end_node = rel_data['end']

                    # Avoid duplicates when direction is "both"
                    if direction == "both" and start_node.get('id') == state_id:
                        continue

                    # Create Action object
                    action_dict = dict(rel_props)
                    if 'source' not in action_dict:
                        action_dict['source'] = start_node.get('id')
                    if 'target' not in action_dict:
                        action_dict['target'] = end_node.get('id')

                    actions.append(Action(**action_dict))

            return actions
        except Exception as e:
            logger.error(f" getting connected actions: {e}")
            return []

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
        if k < 1:
            raise ValueError(f"k must be >= 1, got {k}")

        try:
            # Track states at each hop level
            current_level = {state_id}
            visited = {state_id}

            # Traverse k hops
            for hop in range(k):
                next_level = set()

                for current_state_id in current_level:
                    # Get connected actions
                    actions = self.get_connected_actions(current_state_id, direction)

                    # Get neighbor state IDs
                    for action in actions:
                        if direction == "outgoing":
                            neighbor_id = action.target
                        elif direction == "incoming":
                            neighbor_id = action.source
                        else:  # "both"
                            # For "both", get the other end of the edge
                            if action.source == current_state_id:
                                neighbor_id = action.target
                            else:
                                neighbor_id = action.source

                        # Add to next level if not visited
                        if neighbor_id not in visited:
                            next_level.add(neighbor_id)
                            visited.add(neighbor_id)

                current_level = next_level

                # If no more neighbors, stop early
                if not current_level:
                    break

            # Get full State objects for k-hop neighbors
            k_hop_states = []
            for neighbor_id in current_level:
                state = self.get_state(neighbor_id)
                if state:
                    k_hop_states.append(state)

            return k_hop_states
        except Exception as e:
            logger.error(f" getting k-hop neighbors: {e}")
            return []



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
                start_node_id_key="id",
                end_node_id_key="id",
            )
            return True
        except Exception as e:
            logger.error(f" creating action: {e}")
            return False

    def get_action(self, source_id: str, target_id: str) -> Optional[Action]:
        """Get an action by source and target IDs.

        Args:
            source_id: Source state ID.
            target_id: Target state ID.

        Returns:
            Action object if found, None otherwise.
        """
        try:
            # Query relationships between the two states
            rels = self.graph_store.query_relationships(
                start_node_label=self.node_label,
                start_node_id_value=source_id,
                end_node_label=self.node_label,
                end_node_id_value=target_id
            )

            if rels and len(rels) > 0:
                # Get the first relationship
                rel_data = rels[0]['rel']
                start_node = rels[0]['start']
                end_node = rels[0]['end']

                # Build Action object
                action_dict = dict(rel_data)
                if 'source' not in action_dict:
                    action_dict['source'] = start_node.get('id')
                if 'target' not in action_dict:
                    action_dict['target'] = end_node.get('id')

                return Action(**action_dict)
            return None
        except Exception as e:
            logger.error(f" getting action: {e}")
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
            logger.error(f" updating action: {e}")
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
            # Query to find the relationship type first
            rels = self.graph_store.query_relationships(
                start_node_label=self.node_label,
                start_node_id_value=source_id,
                end_node_label=self.node_label,
                end_node_id_value=target_id
            )

            if not rels:
                return False

            # Delete the first relationship found
            # Note: If there are multiple relationships, only the first is deleted
            rel_data = rels[0]['rel']

            # Use the actual relationship type stored in _rel_type
            rel_type = rel_data.get('_rel_type')
            if not rel_type:
                # Fallback: construct from properties 'type' field
                prop_type = rel_data.get('type')
                if prop_type:
                    rel_type = self.rel_type_prefix + prop_type.upper().replace(" ", "_")

            return self.graph_store.delete_relationship(
                start_node_label=self.node_label,
                start_node_id_value=source_id,
                end_node_label=self.node_label,
                end_node_id_value=target_id,
                rel_type=rel_type if rel_type else ""
            )
        except Exception as e:
            logger.error(f" deleting action: {e}")
            return False

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
        try:
            # Query relationships with filters
            rels = self.graph_store.query_relationships(
                start_node_label=self.node_label,
                start_node_id_value=source_id,
                end_node_label=self.node_label,
                end_node_id_value=target_id,
                rel_type=None  # Don't filter by rel_type, will filter by action.type later
            )

            actions = []
            for rel_data_dict in rels:
                rel_props = rel_data_dict['rel']
                start_node = rel_data_dict['start']
                end_node = rel_data_dict['end']

                # Build Action object
                action_dict = dict(rel_props)
                if 'source' not in action_dict:
                    action_dict['source'] = start_node.get('id')
                if 'target' not in action_dict:
                    action_dict['target'] = end_node.get('id')

                action = Action(**action_dict)

                # Apply additional filters
                if action_type and action.type != action_type:
                    continue
                if user_id and action.user_id != user_id:
                    continue

                actions.append(action)

            return actions
        except Exception as e:
            logger.error(f" listing actions: {e}")
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
            logger.error(f" batch creating actions: {e}")
            return False

    def find_shortest_path(
        self,
        source_id: str,
        target_id: str,
        state_manager: Optional["GraphStateManager"] = None,
    ) -> Optional[Tuple[List["State"], List[Action]]]:
        """Find shortest path between two states using BFS.

        Args:
            source_id: Source state ID.
            target_id: Target state ID.
            state_manager: Optional StateManager to retrieve State objects.

        Returns:
            Tuple of (states, actions) representing the path if found,
            None if no path exists.
        """
        from collections import deque

        if source_id == target_id:
            return ([], [])

        try:
            # BFS to find shortest path
            visited = set()
            # Queue: (current_state_id, path_of_state_ids, path_of_actions)
            queue = deque([(source_id, [source_id], [])])
            visited.add(source_id)

            while queue:
                current_id, path_ids, path_actions = queue.popleft()

                # Get outgoing actions from current state
                outgoing = self.list_outgoing_actions(current_id)

                for action in outgoing:
                    next_id = action.target

                    if next_id == target_id:
                        # Found the target - build result
                        final_path_ids = path_ids + [next_id]
                        final_actions = path_actions + [action]

                        # Convert state IDs to State objects if state_manager provided
                        if state_manager:
                            states = []
                            for state_id in final_path_ids:
                                state = state_manager.get_state(state_id)
                                if state:
                                    states.append(state)
                            return (states, final_actions)
                        else:
                            # Return empty states list if no state_manager
                            return ([], final_actions)

                    if next_id not in visited:
                        visited.add(next_id)
                        queue.append((
                            next_id,
                            path_ids + [next_id],
                            path_actions + [action]
                        ))

            return None  # No path found
        except Exception as e:
            logger.error(f" finding shortest path: {e}")
            return None

    def list_outgoing_actions(
        self,
        state_id: str,
    ) -> List[Action]:
        """List all outgoing actions from a state.

        Returns all actions where the given state is the source.

        Args:
            state_id: State ID to get outgoing actions for.

        Returns:
            List of Action objects originating from the state.
        """
        return self.list_actions(source_id=state_id)


class InMemoryCognitivePhraseManager(CognitivePhraseManager):
    """In-memory CognitivePhrase Manager.

    Manages CognitivePhrase entities in memory. All cognitive phrases are stored
    permanently with unique IDs.

    Attributes:
        phrases: Dictionary mapping phrase_id to CognitivePhrase.
    """

    def __init__(self):
        """Initialize InMemoryCognitivePhraseManager.

        All cognitive phrases are stored without limit.
        """
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

            # Add new phrase - all phrases are stored permanently
            self.phrases[phrase.id] = phrase
            return True
        except Exception as e:
            logger.error(f" creating phrase: {e}")
            return False

    def get_phrase(self, phrase_id: str) -> Optional[CognitivePhrase]:
        """Get a cognitive phrase by ID.

        Args:
            phrase_id: Unique phrase identifier.

        Returns:
            CognitivePhrase object if found, None otherwise.
        """
        phrase = self.phrases.get(phrase_id)
        if phrase:
            # Record access for tracking
            phrase.record_access()
        return phrase

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
            logger.error(f" updating phrase: {e}")
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
            logger.error(f" deleting phrase: {e}")
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
        """List cognitive phrases with optional filters, ordered by access frequency.

        Args:
            user_id: Filter by user ID.
            session_id: Filter by session ID.
            goal_id: Deprecated, ignored for compatibility.
            start_time: Filter by start timestamp.
            end_time: Filter by end timestamp.
            limit: Maximum number of results.

        Returns:
            List of CognitivePhrase objects matching the filters, ordered by access_count desc.
        """
        results = []

        for phrase in self.phrases.values():
            # Apply filters
            if user_id and phrase.user_id != user_id:
                continue
            if session_id and phrase.session_id != session_id:
                continue
            if start_time and phrase.start_timestamp < start_time:
                continue
            if end_time and phrase.start_timestamp > end_time:
                continue

            results.append(phrase)

        # Sort by access_count (descending) then by last_access_time (descending)
        results.sort(key=lambda p: (p.access_count, p.last_access_time or 0), reverse=True)

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


class GraphCognitivePhraseManager(CognitivePhraseManager):
    """GraphStore-based CognitivePhrase Manager.

    Manages CognitivePhrase entities using GraphStore for persistent storage.
    This enables CognitivePhrases to be stored in Neo4j alongside States and Actions.

    Attributes:
        graph_store: GraphStore instance for persistence.
        node_label: Label for CognitivePhrase nodes (default: "CognitivePhrase").
    """

    def __init__(self, graph_store: "GraphStore", node_label: str = "CognitivePhrase"):
        """Initialize GraphCognitivePhraseManager.

        Args:
            graph_store: GraphStore instance for persistence.
            node_label: Label for CognitivePhrase nodes.
        """
        self.graph_store = graph_store
        self.node_label = node_label

    def create_phrase(self, phrase: CognitivePhrase) -> bool:
        """Create a new cognitive phrase in GraphStore.

        Args:
            phrase: CognitivePhrase object to create.

        Returns:
            True if created successfully, False otherwise.
        """
        try:
            # Check if already exists
            existing = self.graph_store.get_node(
                label=self.node_label, id_value=phrase.id, id_key="id"
            )
            if existing:
                return False  # Already exists

            # Convert to dict for storage
            phrase_data = phrase.to_dict()
            self.graph_store.upsert_node(
                label=self.node_label,
                properties=phrase_data,
                id_key="id",
            )
            return True
        except Exception as e:
            logger.error(f" creating phrase: {e}")
            return False

    def get_phrase(self, phrase_id: str) -> Optional[CognitivePhrase]:
        """Get a cognitive phrase by ID from GraphStore.

        Args:
            phrase_id: Unique phrase identifier.

        Returns:
            CognitivePhrase object if found, None otherwise.
        """
        try:
            node = self.graph_store.get_node(
                label=self.node_label, id_value=phrase_id, id_key="id"
            )
            if node:
                phrase = CognitivePhrase.from_dict(node)
                # Record access and update in store
                phrase.record_access()
                self.update_phrase(phrase)
                return phrase
            return None
        except Exception as e:
            logger.error(f" getting phrase: {e}")
            return None

    def update_phrase(self, phrase: CognitivePhrase) -> bool:
        """Update an existing cognitive phrase in GraphStore.

        Args:
            phrase: CognitivePhrase object with updated information.

        Returns:
            True if updated successfully, False otherwise.
        """
        try:
            phrase_data = phrase.to_dict()
            self.graph_store.upsert_node(
                label=self.node_label,
                properties=phrase_data,
                id_key="id",
            )
            return True
        except Exception as e:
            logger.error(f" updating phrase: {e}")
            return False

    def delete_phrase(self, phrase_id: str) -> bool:
        """Delete a cognitive phrase from GraphStore.

        Args:
            phrase_id: Unique phrase identifier.

        Returns:
            True if deleted successfully, False otherwise.
        """
        try:
            return self.graph_store.delete_node(
                label=self.node_label, id_value=phrase_id, id_key="id"
            )
        except Exception as e:
            logger.error(f" deleting phrase: {e}")
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
            goal_id: Deprecated, ignored for compatibility.
            start_time: Filter by start timestamp.
            end_time: Filter by end timestamp.
            limit: Maximum number of results.

        Returns:
            List of CognitivePhrase objects matching the filters.
        """
        try:
            # Build filters
            filters = {}
            if user_id:
                filters["user_id"] = user_id
            if session_id:
                filters["session_id"] = session_id

            # Query nodes
            nodes = self.graph_store.query_nodes(
                label=self.node_label,
                filters=filters if filters else None,
                limit=limit,
            )

            # Convert to CognitivePhrase objects
            phrases = []
            for node in nodes:
                try:
                    phrase = CognitivePhrase.from_dict(node)

                    # Apply time filters (not supported by basic query_nodes)
                    if start_time and phrase.start_timestamp < start_time:
                        continue
                    if end_time and phrase.start_timestamp > end_time:
                        continue

                    phrases.append(phrase)
                except Exception as e:
                    logger.error(f" converting phrase: {e}")
                    continue

            # Sort by access_count (descending) then by last_access_time (descending)
            phrases.sort(
                key=lambda p: (p.access_count, p.last_access_time or 0), reverse=True
            )

            # Apply limit after filtering
            if limit:
                phrases = phrases[:limit]

            return phrases
        except Exception as e:
            logger.error(f" listing phrases: {e}")
            return []

    def search_phrases_by_embedding(
        self, query_vector: List[float], top_k: int = 10
    ) -> List[CognitivePhrase]:
        """Search cognitive phrases by embedding vector using GraphStore vector search.

        Args:
            query_vector: Query embedding vector.
            top_k: Number of top results to return.

        Returns:
            List of top-k similar CognitivePhrase objects.
        """
        try:
            # Try to use GraphStore's vector search
            results = self.graph_store.vector_search(
                label=self.node_label,
                property_key="embedding_vector",
                query_text_or_vector=query_vector,
                topk=top_k,
            )

            phrases = []
            for node, score in results:
                try:
                    phrase = CognitivePhrase.from_dict(node)
                    phrases.append(phrase)
                except Exception as e:
                    logger.error(f" converting phrase from vector search: {e}")
                    continue

            return phrases
        except Exception as e:
            # Fallback to manual cosine similarity if vector search not available
            logger.warning(f"Vector search failed, using fallback: {e}")
            return self._search_phrases_by_embedding_fallback(query_vector, top_k)

    def _search_phrases_by_embedding_fallback(
        self, query_vector: List[float], top_k: int = 10
    ) -> List[CognitivePhrase]:
        """Fallback embedding search using manual cosine similarity.

        Args:
            query_vector: Query embedding vector.
            top_k: Number of top results to return.

        Returns:
            List of top-k similar CognitivePhrase objects.
        """

        def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
            """Calculate cosine similarity between two vectors."""
            if not vec1 or not vec2 or len(vec1) != len(vec2):
                return 0.0

            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            norm1 = math.sqrt(sum(a * a for a in vec1))
            norm2 = math.sqrt(sum(b * b for b in vec2))

            if norm1 == 0 or norm2 == 0:
                return 0.0

            return dot_product / (norm1 * norm2)

        # Get all phrases
        all_phrases = self.list_phrases()

        # Calculate similarities
        similarities = []
        for phrase in all_phrases:
            if phrase.embedding_vector:
                similarity = cosine_similarity(query_vector, phrase.embedding_vector)
                similarities.append((phrase, similarity))

        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Return top-k
        return [phrase for phrase, _ in similarities[:top_k]]


class GraphIntentSequenceManager(IntentSequenceManager):
    """GraphStore-based IntentSequence Manager (v2).

    Manages IntentSequence as independent graph nodes with HAS_SEQUENCE
    relationships to States. This enables vector search on IntentSequences.

    Deduplication Strategy:
        1. Content hash (exact match): Fast MD5 comparison of intent content
        2. Embedding similarity (semantic match): Cosine similarity >= threshold

    Attributes:
        graph_store: GraphStore instance for persistence.
        node_label: Label for IntentSequence nodes (default: "IntentSequence").
        rel_type: Relationship type for HAS_SEQUENCE (default: "HAS_SEQUENCE").
        similarity_threshold: Cosine similarity threshold for dedup (default: 0.95).
    """

    # Default similarity threshold for embedding-based deduplication
    DEFAULT_SIMILARITY_THRESHOLD = 0.95

    def __init__(
        self,
        graph_store: GraphStore,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    ):
        """Initialize GraphIntentSequenceManager.

        Args:
            graph_store: GraphStore instance for storage operations.
            similarity_threshold: Cosine similarity threshold for deduplication.
                Sequences with similarity >= threshold are considered duplicates.
                Default: 0.95 (very similar descriptions are deduplicated).
        """
        self.graph_store = graph_store
        self.node_label = "IntentSequence"
        self.rel_type = "HAS_SEQUENCE"
        self.similarity_threshold = similarity_threshold

    def create_sequence(self, sequence: IntentSequence) -> bool:
        """Create a new IntentSequence node with deduplication.

        Deduplication is based on a content hash of the intents list.
        If a sequence with the same content hash already exists, the
        creation is skipped and the existing sequence's ID is preserved.

        Args:
            sequence: IntentSequence object to create.

        Returns:
            True if created (or already exists), False on error.
        """
        try:
            if not sequence.content_hash:
                sequence.content_hash = self._compute_content_hash(sequence)
            properties = sequence.to_dict()
            self.graph_store.upsert_node(
                label=self.node_label, properties=properties, id_key="id"
            )
            return True
        except Exception as e:
            logger.error(f" creating IntentSequence: {e}")
            return False

    def find_duplicate(self, sequence: IntentSequence, state_id: str) -> Optional[str]:
        """Check if a duplicate IntentSequence already exists for a State.

        Deduplication strategy (within the same State):
        1. Content hash match: Exact match based on MD5 of intent content (fast)
        2. Embedding similarity: If both have embeddings and similarity >= threshold

        Args:
            sequence: IntentSequence to check.
            state_id: State ID to check within.

        Returns:
            Existing sequence ID if duplicate found, None otherwise.
        """
        existing_seqs = self.list_by_state(state_id)
        if not existing_seqs:
            return None

        # Step 1: Content hash exact match (fast path)
        content_hash = self._compute_content_hash(sequence)
        if content_hash:
            for existing in existing_seqs:
                existing_hash = existing.content_hash or self._compute_content_hash(existing)
                if existing_hash == content_hash:
                    return existing.id

        # Step 2: Embedding similarity match (semantic dedup)
        # Only if the new sequence has an embedding vector
        if sequence.embedding_vector:
            for existing in existing_seqs:
                if existing.embedding_vector:
                    similarity = self._cosine_similarity(
                        sequence.embedding_vector, existing.embedding_vector
                    )
                    if similarity >= self.similarity_threshold:
                        logger.debug(
                            f"[IntentSequenceDedup] Found similar sequence: "
                            f"similarity={similarity:.4f} >= threshold={self.similarity_threshold}"
                        )
                        return existing.id

        return None

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors.

        Args:
            vec1: First embedding vector.
            vec2: Second embedding vector.

        Returns:
            Cosine similarity score in range [-1, 1], or 0.0 if invalid.
        """
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    @staticmethod
    def _compute_content_hash(sequence: IntentSequence) -> Optional[str]:
        """Compute a content hash for deduplication.

        Based on intent types, text, and values in order.
        Normalizes None to '' for consistent hashing across Intent objects and dicts.

        Args:
            sequence: IntentSequence to hash.

        Returns:
            MD5 hex digest, or None if cannot compute.
        """
        import hashlib

        if not sequence.intents:
            return None

        intent_keys = []
        for intent in sequence.intents:
            if hasattr(intent, "type"):
                # Intent object: .text may be None
                key = f"{intent.type}:{intent.text or ''}:{intent.value or ''}"
            elif isinstance(intent, dict):
                # Dict: .get() may return None
                key = f"{intent.get('type') or ''}:{intent.get('text') or ''}:{intent.get('value') or ''}"
            else:
                continue
            intent_keys.append(key)

        if not intent_keys:
            return None

        return hashlib.md5("|".join(intent_keys).encode()).hexdigest()

    def get_sequence(self, sequence_id: str) -> Optional[IntentSequence]:
        """Get an IntentSequence by ID.

        Args:
            sequence_id: Unique sequence identifier.

        Returns:
            IntentSequence object if found, None otherwise.
        """
        try:
            node = self.graph_store.get_node(
                label=self.node_label, id_value=sequence_id, id_key="id"
            )
            if node:
                return IntentSequence.from_dict(node)
            return None
        except Exception as e:
            logger.error(f" getting IntentSequence: {e}")
            return None

    def update_sequence(self, sequence: IntentSequence) -> bool:
        """Update an existing IntentSequence.

        Args:
            sequence: IntentSequence object with updated information.

        Returns:
            True if updated successfully, False otherwise.
        """
        try:
            properties = sequence.to_dict()
            self.graph_store.upsert_node(
                label=self.node_label, properties=properties, id_key="id"
            )
            return True
        except Exception as e:
            logger.error(f" updating IntentSequence: {e}")
            return False

    def delete_sequence(self, sequence_id: str) -> bool:
        """Delete an IntentSequence.

        Args:
            sequence_id: Unique sequence identifier.

        Returns:
            True if deleted successfully, False otherwise.
        """
        try:
            return self.graph_store.delete_node(
                label=self.node_label, id_value=sequence_id, id_key="id"
            )
        except Exception as e:
            logger.error(f" deleting IntentSequence: {e}")
            return False

    def link_to_state(self, state_id: str, sequence_id: str) -> bool:
        """Create HAS_SEQUENCE relationship from State to IntentSequence.

        Args:
            state_id: State ID (source).
            sequence_id: IntentSequence ID (target).

        Returns:
            True if created successfully, False otherwise.
        """
        try:
            self.graph_store.upsert_relationship(
                start_node_label="State",
                start_node_id_value=state_id,
                end_node_label=self.node_label,
                end_node_id_value=sequence_id,
                rel_type=self.rel_type,
                properties={},
            )
            return True
        except Exception as e:
            logger.error(f" linking IntentSequence to State: {e}")
            return False

    def unlink_from_state(self, state_id: str, sequence_id: str) -> bool:
        """Remove HAS_SEQUENCE relationship.

        Args:
            state_id: State ID (source).
            sequence_id: IntentSequence ID (target).

        Returns:
            True if removed successfully, False otherwise.
        """
        try:
            return self.graph_store.delete_relationship(
                start_node_label="State",
                start_node_id_value=state_id,
                end_node_label=self.node_label,
                end_node_id_value=sequence_id,
                rel_type=self.rel_type,
            )
        except Exception as e:
            logger.error(f" unlinking IntentSequence from State: {e}")
            return False

    def list_by_state(self, state_id: str) -> List[IntentSequence]:
        """List all IntentSequences belonging to a State.

        Args:
            state_id: State ID to query.

        Returns:
            List of IntentSequence objects linked to this State.
        """
        try:
            # Query HAS_SEQUENCE relationships
            rels = self.graph_store.query_relationships(
                start_node_label="State",
                start_node_id_value=state_id,
                end_node_label=self.node_label,
                rel_type=self.rel_type,
            )

            sequences = []
            for rel_data in rels:
                end_node = rel_data.get("end", {})
                if end_node:
                    try:
                        seq = IntentSequence.from_dict(end_node)
                        sequences.append(seq)
                    except Exception as e:
                        logger.error(f" parsing IntentSequence: {e}")
                        continue

            return sequences
        except Exception as e:
            logger.error(f" listing IntentSequences by State: {e}")
            return []

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
        # Pre-fetch state sequence IDs once if filtering by state
        state_seq_ids = None
        if state_id:
            state_seqs = self.list_by_state(state_id)
            state_seq_ids = {s.id for s in state_seqs}

        results = self.graph_store.vector_search(
            label=self.node_label,
            property_key="embedding_vector",
            vector=query_vector,
            limit=top_k * 2 if state_id else top_k,
        )

        sequences_with_scores = []
        for node, score in results:
            try:
                seq = IntentSequence.from_dict(node)

                if state_seq_ids is not None and seq.id not in state_seq_ids:
                    continue

                sequences_with_scores.append((seq, score))

                if len(sequences_with_scores) >= top_k:
                    break
            except Exception as e:
                logger.error(f" parsing IntentSequence from search: {e}")
                continue

        return sequences_with_scores[:top_k]

    def batch_create_sequences(self, sequences: List[IntentSequence]) -> bool:
        """Batch create multiple IntentSequences.

        Args:
            sequences: List of IntentSequence objects to create.

        Returns:
            True if all created successfully, False otherwise.
        """
        try:
            for seq in sequences:
                if not self.create_sequence(seq):
                    return False
            return True
        except Exception as e:
            logger.error(f" batch creating IntentSequences: {e}")
            return False


class WorkflowMemory(Memory):
    """Workflow Memory implementation.

    Concrete implementation of Memory interface for managing workflow-based
    memory with States, Actions, and CognitivePhrases.

    New Features (from memory-graph-ontology-design.md):
        - URL Index: Fast URL to State lookup using in-memory Dict
        - State Merge: Real-time merge when same URL is encountered
        - PageInstance: Concrete URL instances within abstract States
        - IntentSequence: Ordered operation sequences with semantic search
    """

    def __init__(
        self,
        graph_store: GraphStore,
        phrase_manager: Optional[CognitivePhraseManager] = None,
        build_url_index: bool = True,
        use_graph_phrase_manager: bool = True,
        intent_sequence_dedup_threshold: Optional[float] = None,
    ):
        """Initialize WorkflowMemory.

        Args:
            graph_store: GraphStore instance for Domain, State, Action, and Manage storage.
            phrase_manager: Optional CognitivePhraseManager instance.
                If not provided and use_graph_phrase_manager is True, uses GraphCognitivePhraseManager.
                Otherwise uses InMemoryCognitivePhraseManager.
                All cognitive phrases are stored permanently with unique IDs.
            build_url_index: Whether to build URL index from graph on init (default True).
            use_graph_phrase_manager: Whether to use GraphCognitivePhraseManager for persistent
                storage of CognitivePhrases (default True). Set to False to use in-memory storage.
            intent_sequence_dedup_threshold: Cosine similarity threshold for IntentSequence
                deduplication. If None, uses GraphIntentSequenceManager default (0.95).
        """
        domain_manager = GraphDomainManager(graph_store)
        state_manager = GraphStateManager(graph_store)
        action_manager = GraphActionManager(graph_store)
        manage_manager = GraphManageManager(graph_store)

        # Create IntentSequenceManager with optional custom threshold
        if intent_sequence_dedup_threshold is not None:
            intent_sequence_manager = GraphIntentSequenceManager(
                graph_store, similarity_threshold=intent_sequence_dedup_threshold
            )
        else:
            intent_sequence_manager = GraphIntentSequenceManager(graph_store)

        if phrase_manager is None:
            if use_graph_phrase_manager:
                phrase_manager = GraphCognitivePhraseManager(graph_store)
            else:
                phrase_manager = InMemoryCognitivePhraseManager()

        super().__init__(
            domain_manager,
            state_manager,
            action_manager,
            manage_manager,
            phrase_manager,
            intent_sequence_manager,
        )
        self.graph_store = graph_store

        # Initialize URL index for fast URL to State lookup
        self.url_index = URLIndex()
        if build_url_index:
            url_count = self.url_index.build_from_graph(graph_store)
            if url_count > 0:
                logger.info(f"URLIndex: Loaded {url_count} URLs from graph")

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
            logger.error(f" importing memory: {e}")
            return False

    # ==================== NEW METHODS FOR ABSTRACT STATE DESIGN ====================

    def find_state_by_url(self, url: str) -> Optional[State]:
        """Find the State that contains the given URL.

        This method uses the URL index for O(1) lookup to find which
        State a URL belongs to. This is the core method for State
        deduplication (same URL = same State).

        Args:
            url: URL to look up.

        Returns:
            State object if found, None otherwise.
        """
        state_id = self.url_index.find_state_by_url(url)
        if state_id:
            return self.get_state(state_id)
        return None

    def find_state_by_path_sig(self, domain: str, path_sig: str) -> Optional[State]:
        """Find a State by domain + path signature.

        This is a secondary deduplication method used when URL lookup fails.

        Args:
            domain: Normalized domain key (e.g., "example.com").
            path_sig: Stable path signature.

        Returns:
            State object if found, None otherwise.
        """
        if not domain or not path_sig:
            return None

        try:
            nodes = self.graph_store.query_nodes(
                label="State",
                filters={"domain": domain, "path_sig": path_sig},
                limit=1,
            )
            if nodes:
                return State.from_dict(nodes[0])
        except Exception as e:
            print(f"Error finding state by path_sig: {e}")
        return None

    def find_or_create_state(
        self,
        url: str,
        page_title: Optional[str] = None,
        timestamp: int = 0,
        description: Optional[str] = None,
        domain: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        path_sig: Optional[str] = None,
    ) -> tuple[State, bool]:
        """Find existing State by URL or create a new one.

        This implements the real-time merge logic from design doc 8.5:
        - Check URL index
        - If URL miss and path_sig provided, try path-based lookup
        - If exists → reuse existing State
        - If not → create new State

        Args:
            url: URL to look up or create State for.
            page_title: Page title (used when creating new State).
            timestamp: Timestamp (used when creating new State).
            description: Description (used when creating new State).
            domain: Domain this State belongs to.
            user_id: User ID.
            session_id: Session ID.
            path_sig: Stable path signature (optional).

        Returns:
            Tuple of (State, is_new) where is_new is True if State was created.
        """
        # Check if URL exists in index
        existing_state = self.find_state_by_url(url)
        if existing_state:
            return existing_state, False

        # Optional: path-based deduplication (within same domain)
        if path_sig and domain:
            existing_state = self.find_state_by_path_sig(domain, path_sig)
            if existing_state:
                return existing_state, False

        # Create new State
        state = State(
            page_url=url,
            page_title=page_title,
            timestamp=timestamp,
            description=description,
            domain=domain,
            path_sig=path_sig,
            user_id=user_id,
            session_id=session_id,
            instances=[],
        )

        # Save to graph
        if self.create_state(state):
            # Add to URL index
            self.url_index.add_url(url, state.id)
            return state, True

        raise RuntimeError(f"Failed to create State for URL: {url}")

    def add_page_instance(
        self,
        state_id: str,
        instance: PageInstance,
    ) -> bool:
        """Add a PageInstance to an existing State.

        This method adds a concrete URL instance to an abstract State,
        and updates the URL index accordingly.

        Args:
            state_id: ID of the State to add instance to.
            instance: PageInstance to add.

        Returns:
            True if added successfully, False otherwise.
        """
        try:
            # Get existing state
            state = self.get_state(state_id)
            if not state:
                logger.error(f": State {state_id} not found")
                return False

            # Add instance to state
            state.add_instance(instance)

            # Update state in graph
            if not self.state_manager.update_state(state):
                return False

            # Update URL index
            self.url_index.add_url(instance.url, state_id)

            return True
        except Exception as e:
            logger.error(f" adding page instance: {e}")
            return False

    def find_path(
        self,
        from_state_id: str,
        to_state_id: str,
        max_depth: int = 10,
    ) -> Optional[List[tuple[State, Optional[Action]]]]:
        """Find the shortest path between two States.

        This implements the path finding from design doc 4.2:
        - BFS to find shortest path
        - Return list of (State, Action) tuples

        Args:
            from_state_id: Starting State ID.
            to_state_id: Target State ID.
            max_depth: Maximum number of edges (transitions) to traverse.

        Returns:
            List of (State, Action) tuples representing the path,
            or None if no path found. Action is None for the first State.
        """
        if from_state_id == to_state_id:
            state = self.get_state(from_state_id)
            return [(state, None)] if state else None

        # BFS to find shortest path
        from collections import deque

        # Queue entries: (current_state_id, path_so_far)
        # path_so_far is a list of (state_id, action_to_reach_it)
        queue = deque([(from_state_id, [(from_state_id, None)])])
        visited = {from_state_id}

        while queue:
            current_id, path = queue.popleft()

            # path length = number of nodes, edges = nodes - 1
            # max_depth is edge count, so check: (len(path) - 1) >= max_depth
            if len(path) - 1 >= max_depth:
                continue

            # Get outgoing actions from current state
            actions = self.state_manager.get_connected_actions(current_id, direction="outgoing")

            for action in actions:
                next_id = action.target

                if next_id == to_state_id:
                    # Found the target
                    path.append((next_id, action))
                    # Convert to State objects
                    result = []
                    for state_id, action_obj in path:
                        state = self.get_state(state_id)
                        if state:
                            result.append((state, action_obj))
                    return result

                if next_id not in visited:
                    visited.add(next_id)
                    new_path = path + [(next_id, action)]
                    queue.append((next_id, new_path))

        return None  # No path found

    def rebuild_url_index(self) -> int:
        """Rebuild the URL index from the graph store.

        This can be used if the index gets out of sync or after
        bulk operations.

        Returns:
            Number of URLs indexed.
        """
        return self.url_index.build_from_graph(self.graph_store)


__all__ = [
    "GraphDomainManager",
    "GraphManageManager",
    "GraphStateManager",
    "GraphActionManager",
    "InMemoryCognitivePhraseManager",
    "GraphCognitivePhraseManager",
    "WorkflowMemory",
    "URLIndex",
]
