"""Workflow Memory - Implementation of Memory Management.

This module provides concrete implementations of memory managers for
States, Actions, and CognitivePhrase units, using GraphStore for
graph-based storage.
"""

import math
from typing import Any, Dict, List, Optional

from src.cloud_backend.memgraph.graphstore.graph_store import GraphStore
from src.cloud_backend.memgraph.memory.memory import (
    ActionManager,
    CognitivePhraseManager,
    DomainManager,
    ManageManager,
    Memory,
    StateManager,
)
from src.cloud_backend.memgraph.ontology.action import Action
from src.cloud_backend.memgraph.ontology.cognitive_phrase import CognitivePhrase
from src.cloud_backend.memgraph.ontology.domain import Domain, Manage
from src.cloud_backend.memgraph.ontology.intent import Intent
from src.cloud_backend.memgraph.ontology.state import State


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
            print(f"Error creating domain: {e}")
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
            print(f"Error getting domain: {e}")
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
            print(f"Error updating domain: {e}")
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
            print(f"Error deleting domain: {e}")
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
            print(f"Error listing domains: {e}")
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
            print(f"Error batch creating domains: {e}")
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
                upsert_nodes=False  # Nodes should already exist
            )
            return True
        except Exception as e:
            print(f"Error creating manage edge: {e}")
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
            print(f"Error getting manage edge: {e}")
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
            print(f"Error updating manage edge: {e}")
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
            print(f"Error deleting manage edge: {e}")
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
            print(f"Error listing manage edges: {e}")
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
            print(f"Error batch creating manage edges: {e}")
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
                    start_node = rel_data['start_node']
                    end_node = rel_data['end_node']

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
                    start_node = rel_data['start_node']
                    end_node = rel_data['end_node']

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
            print(f"Error getting connected actions: {e}")
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
            print(f"Error getting k-hop neighbors: {e}")
            return []

    def search_intents_by_embedding(
        self, query_vector: List[float], top_k: int = 10
    ) -> List[tuple[Intent, State, float]]:
        """Search intents by embedding vector similarity.

        Since intents are embedded within states, this method searches through
        all states and their contained intents to find the most similar ones.

        Args:
            query_vector: Query embedding vector.
            top_k: Number of top results to return.

        Returns:
            List of tuples (Intent, State, similarity_score) for top-k similar intents,
            where State is the parent state containing the intent.
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

        try:
            # Get all states
            all_states = self.list_states()

            # Collect all intents with their parent states and calculate similarities
            similarities = []
            for state in all_states:
                if not state.intents:
                    continue

                for intent_data in state.intents:
                    # Convert intent data to Intent object if needed
                    if isinstance(intent_data, dict):
                        intent = Intent.from_dict(intent_data)
                    elif isinstance(intent_data, Intent):
                        intent = intent_data
                    else:
                        continue

                    # Calculate similarity if intent has embedding
                    if intent.embedding_vector:
                        similarity = cosine_similarity(query_vector, intent.embedding_vector)
                        similarities.append((intent, state, similarity))

            # Sort by similarity (descending)
            similarities.sort(key=lambda x: x[2], reverse=True)

            # Return top-k
            return similarities[:top_k]
        except Exception as e:
            print(f"Error searching intents by embedding: {e}")
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
                start_node = rels[0]['start_node']
                end_node = rels[0]['end_node']

                # Build Action object
                action_dict = dict(rel_data)
                if 'source' not in action_dict:
                    action_dict['source'] = start_node.get('id')
                if 'target' not in action_dict:
                    action_dict['target'] = end_node.get('id')

                return Action(**action_dict)
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
            rel_type = rel_data.get('type')

            if rel_type:
                # Use the relationship type from properties
                formatted_rel_type = self.rel_type_prefix + rel_type.upper().replace(" ", "_")
            else:
                # Fallback: try to delete with any relationship type
                # This may not work for all GraphStore implementations
                formatted_rel_type = None

            return self.graph_store.delete_relationship(
                start_node_label=self.node_label,
                start_node_id_value=source_id,
                end_node_label=self.node_label,
                end_node_id_value=target_id,
                rel_type=formatted_rel_type if formatted_rel_type else ""
            )
        except Exception as e:
            print(f"Error deleting action: {e}")
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
                start_node = rel_data_dict['start_node']
                end_node = rel_data_dict['end_node']

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
            print(f"Error creating phrase: {e}")
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
            graph_store: GraphStore instance for Domain, State, Action, and Manage storage.
            phrase_manager: Optional CognitivePhraseManager instance.
                If not provided, uses InMemoryCognitivePhraseManager.
                All cognitive phrases are stored permanently with unique IDs.
        """
        domain_manager = GraphDomainManager(graph_store)
        state_manager = GraphStateManager(graph_store)
        action_manager = GraphActionManager(graph_store)
        manage_manager = GraphManageManager(graph_store)

        if phrase_manager is None:
            phrase_manager = InMemoryCognitivePhraseManager()

        super().__init__(
            domain_manager,
            state_manager,
            action_manager,
            manage_manager,
            phrase_manager
        )
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
    "GraphDomainManager",
    "GraphManageManager",
    "GraphStateManager",
    "GraphActionManager",
    "InMemoryCognitivePhraseManager",
    "WorkflowMemory",
]
