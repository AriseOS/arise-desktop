"""NetworkX-based implementation of GraphStore.

This module provides a production-grade implementation of the GraphStore interface
using NetworkX as the underlying graph library. It supports all standard graph
operations including node/relationship management, indexing, search, and algorithms.

Note: This implementation is single-threaded and does not include concurrency controls.
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx
import numpy as np

from src.cloud_backend.memgraph.graphstore.graph_store import GraphStore


class NetworkXGraph(GraphStore):
    """NetworkX-based graph store implementation.

    This implementation uses NetworkX's DiGraph as the core data structure,
    with additional indexing for efficient lookups. All nodes and relationships
    are stored in the NetworkX graph, with separate indexes maintained for
    fast access by label, ID, and properties.

    Attributes:
        _graph: NetworkX directed graph storing all nodes and edges
        _node_index: Maps (label, id_value) to internal node key
        _label_index: Maps label to set of node keys with that label
        _text_indexes: Maps index name to set of searchable property keys
        _vector_indexes: Maps index name to property key for vector embeddings
        _pagerank_scores: Cached PageRank scores
    """

    def __init__(self, directed: bool = True):
        """Initialize NetworkX graph store.

        Args:
            directed: If True, create a directed graph; otherwise undirected.
        """
        self._graph = nx.DiGraph() if directed else nx.Graph()

        # Indexing structures for fast lookups
        self._node_index: Dict[Tuple[str, Any], str] = {}  # (label, id_value) -> node_key
        self._label_index: Dict[str, Set[str]] = defaultdict(set)  # label -> {node_keys}
        self._text_indexes: Dict[str, Set[str]] = {}  # index_name -> {property_keys}
        self._vector_indexes: Dict[str, str] = {}  # index_name -> property_key
        self._pagerank_scores: Optional[Dict[str, float]] = None

    def close(self) -> None:
        """Close the graph storage instance.

        For NetworkX in-memory implementation, this is a no-op.
        """
        pass

    def initialize_schema(self, schema: Any) -> None:
        """Initialize the graph schema.

        For NetworkX in-memory implementation, this is a no-op as schema
        is not enforced.

        Args:
            schema: The definition of the graph schema (unused).
        """
        pass

    def _generate_node_key(self, label: str, id_value: Any) -> str:
        """Generate internal node key from label and ID.

        Args:
            label: Node label/type
            id_value: Node ID value

        Returns:
            String key in format "Label:id_value"
        """
        return f"{label}:{id_value}"

    def _get_node_key(self, label: str, id_value: Any, id_key: str = 'id') -> Optional[str]:
        """Get internal node key for a node.

        Args:
            label: Node label
            id_value: Node ID value
            id_key: Property key for the ID (default: 'id')

        Returns:
            Internal node key if found, None otherwise
        """
        return self._node_index.get((label, id_value))

    def upsert_node(self, label: str, properties: Dict[str, Any],
                   id_key: str = 'id') -> None:
        """Insert or update a single node.

        Args:
            label: Node label/type
            properties: Node properties including the ID
            id_key: Property key that contains the node ID (default: 'id')

        Raises:
            ValueError: If id_key is not in properties
        """
        if id_key not in properties:
            raise ValueError(f"Property '{id_key}' not found in node properties")

        id_value = properties[id_key]
        node_key = self._generate_node_key(label, id_value)

        # Prepare node data
        node_data = {
            '_label': label,
            '_id_key': id_key,
            '_id_value': id_value,
            **properties
        }

        # Add or update node in graph
        if self._graph.has_node(node_key):
            # Update existing node
            self._graph.nodes[node_key].update(node_data)
        else:
            # Add new node
            self._graph.add_node(node_key, **node_data)
            self._node_index[(label, id_value)] = node_key
            self._label_index[label].add(node_key)

        # Invalidate PageRank cache
        self._pagerank_scores = None

    def upsert_nodes(self, nodes: List[Tuple[str, Dict[str, Any]]],
                    id_key: str = 'id') -> None:
        """Insert or update multiple nodes.

        Args:
            nodes: List of (label, properties) tuples
            id_key: Property key that contains the node ID (default: 'id')
        """
        for label, properties in nodes:
            self.upsert_node(label, properties, id_key)

    def get_node(self, label: str, id_value: Any, id_key: str = 'id') -> Optional[Dict[str, Any]]:
        """Retrieve a node by label and ID.

        Args:
            label: Node label
            id_value: Node ID value
            id_key: Property key for the ID (default: 'id')

        Returns:
            Node properties dict if found, None otherwise
        """
        node_key = self._get_node_key(label, id_value, id_key)
        if node_key is None or not self._graph.has_node(node_key):
            return None

        # Return copy without internal metadata
        node_data = dict(self._graph.nodes[node_key])
        return {k: v for k, v in node_data.items() if not k.startswith('_')}

    def delete_node(self, label: str, id_value: Any, id_key: str = 'id') -> bool:
        """Delete a node by label and ID.

        Args:
            label: Node label
            id_value: Node ID value
            id_key: Property key for the ID (default: 'id')

        Returns:
            True if node was deleted, False if not found
        """
        node_key = self._get_node_key(label, id_value, id_key)
        if node_key is None or not self._graph.has_node(node_key):
            return False

        # Remove from indexes
        self._node_index.pop((label, id_value), None)
        self._label_index[label].discard(node_key)

        # Remove node from graph (also removes connected edges)
        self._graph.remove_node(node_key)

        # Invalidate PageRank cache
        self._pagerank_scores = None
        return True

    def delete_nodes(self, label: str, id_values: List[Any], id_key: str = 'id') -> int:
        """Delete multiple nodes by label and IDs.

        Args:
            label: Node label
            id_values: List of node ID values
            id_key: Property key for the ID (default: 'id')

        Returns:
            Number of nodes deleted
        """
        deleted_count = 0
        for id_value in id_values:
            if self.delete_node(label, id_value, id_key):
                deleted_count += 1
        return deleted_count

    def batch_preprocess_node_properties(self, nodes: List[Tuple[str, Dict[str, Any]]],
                                        id_key: str = 'id') -> List[Tuple[str, Dict[str, Any]]]:
        """Preprocess node properties before batch insertion.

        This is a placeholder for any preprocessing logic needed before batch operations.

        Args:
            nodes: List of (label, properties) tuples
            id_key: Property key for the ID (default: 'id')

        Returns:
            Preprocessed list of (label, properties) tuples
        """
        # No preprocessing needed for NetworkX implementation
        return nodes

    def upsert_relationship(self, start_node_label: str, start_node_id_value: Any,
                          end_node_label: str, end_node_id_value: Any,
                          rel_type: str, properties: Optional[Dict[str, Any]] = None,
                          start_node_id_key: str = 'id', end_node_id_key: str = 'id') -> None:
        """Create or update a relationship between two nodes.

        Args:
            start_node_label: Label of the source node
            start_node_id_value: ID value of the source node
            end_node_label: Label of the target node
            end_node_id_value: ID value of the target node
            rel_type: Type/label of the relationship
            properties: Optional relationship properties
            start_node_id_key: Property key for start node ID (default: 'id')
            end_node_id_key: Property key for end node ID (default: 'id')

        Raises:
            ValueError: If either node does not exist
        """
        start_key = self._get_node_key(start_node_label, start_node_id_value, start_node_id_key)
        end_key = self._get_node_key(end_node_label, end_node_id_value, end_node_id_key)

        if start_key is None or not self._graph.has_node(start_key):
            raise ValueError(f"Start node {start_node_label}:{start_node_id_value} not found")
        if end_key is None or not self._graph.has_node(end_key):
            raise ValueError(f"End node {end_node_label}:{end_node_id_value} not found")

        # Prepare edge data
        edge_data = {
            '_rel_type': rel_type,
            '_start_label': start_node_label,
            '_end_label': end_node_label,
            **(properties or {})
        }

        # Add or update edge
        self._graph.add_edge(start_key, end_key, key=rel_type, **edge_data)

        # Invalidate PageRank cache
        self._pagerank_scores = None

    def upsert_relationships(self, relationships: List[Tuple[str, Any, str, Any, str, Optional[Dict[str, Any]]]],
                           start_node_id_key: str = 'id', end_node_id_key: str = 'id') -> None:
        """Create or update multiple relationships.

        Args:
            relationships: List of (start_label, start_id, end_label, end_id, rel_type, properties) tuples
            start_node_id_key: Property key for start node IDs (default: 'id')
            end_node_id_key: Property key for end node IDs (default: 'id')
        """
        for rel in relationships:
            start_label, start_id, end_label, end_id, rel_type, properties = rel
            self.upsert_relationship(
                start_label, start_id, end_label, end_id, rel_type, properties,
                start_node_id_key, end_node_id_key
            )

    def delete_relationship(self, start_node_label: str, start_node_id_value: Any,
                          end_node_label: str, end_node_id_value: Any,
                          rel_type: str,
                          start_node_id_key: str = 'id', end_node_id_key: str = 'id') -> bool:
        """Delete a relationship between two nodes.

        Args:
            start_node_label: Label of the source node
            start_node_id_value: ID value of the source node
            end_node_label: Label of the target node
            end_node_id_value: ID value of the target node
            rel_type: Type of the relationship to delete
            start_node_id_key: Property key for start node ID (default: 'id')
            end_node_id_key: Property key for end node ID (default: 'id')

        Returns:
            True if relationship was deleted, False if not found
        """
        start_key = self._get_node_key(start_node_label, start_node_id_value, start_node_id_key)
        end_key = self._get_node_key(end_node_label, end_node_id_value, end_node_id_key)

        if start_key is None or end_key is None:
            return False

        if not self._graph.has_edge(start_key, end_key):
            return False

        # For MultiDiGraph, we'd need to check key; for DiGraph, just remove edge
        try:
            self._graph.remove_edge(start_key, end_key)
            self._pagerank_scores = None
            return True
        except nx.NetworkXError:
            return False

    def delete_relationships(self, relationships: List[Tuple[str, Any, str, Any, str]],
                           start_node_id_key: str = 'id', end_node_id_key: str = 'id') -> int:
        """Delete multiple relationships.

        Args:
            relationships: List of (start_label, start_id, end_label, end_id, rel_type) tuples
            start_node_id_key: Property key for start node IDs (default: 'id')
            end_node_id_key: Property key for end node IDs (default: 'id')

        Returns:
            Number of relationships deleted
        """
        deleted_count = 0
        for start_label, start_id, end_label, end_id, rel_type in relationships:
            if self.delete_relationship(start_label, start_id, end_label, end_id, rel_type,
                                       start_node_id_key, end_node_id_key):
                deleted_count += 1
        return deleted_count

    def query_relationships(self, start_node_label: Optional[str] = None,
                          start_node_id_value: Optional[Any] = None,
                          end_node_label: Optional[str] = None,
                          end_node_id_value: Optional[Any] = None,
                          rel_type: Optional[str] = None,
                          start_node_id_key: str = 'id',
                          end_node_id_key: str = 'id') -> List[Dict[str, Any]]:
        """Query relationships with optional filters.

        Args:
            start_node_label: Filter by start node label (optional)
            start_node_id_value: Filter by start node ID (optional)
            end_node_label: Filter by end node label (optional)
            end_node_id_value: Filter by end node ID (optional)
            rel_type: Filter by relationship type (optional)
            start_node_id_key: Property key for start node ID (default: 'id')
            end_node_id_key: Property key for end node ID (default: 'id')

        Returns:
            List of relationship dictionaries with 'start', 'end', and 'rel' keys
        """
        results = []

        # Determine which edges to iterate over
        if start_node_id_value is not None and start_node_label is not None:
            start_key = self._get_node_key(start_node_label, start_node_id_value, start_node_id_key)
            if start_key is None or not self._graph.has_node(start_key):
                return []
            edges = self._graph.out_edges(start_key, data=True)
        elif end_node_id_value is not None and end_node_label is not None:
            end_key = self._get_node_key(end_node_label, end_node_id_value, end_node_id_key)
            if end_key is None or not self._graph.has_node(end_key):
                return []
            edges = self._graph.in_edges(end_key, data=True)
        else:
            edges = self._graph.edges(data=True)

        # Filter edges
        for start_key, end_key, edge_data in edges:
            start_data = self._graph.nodes[start_key]
            end_data = self._graph.nodes[end_key]

            # Apply filters
            if start_node_label and start_data.get('_label') != start_node_label:
                continue
            if end_node_label and end_data.get('_label') != end_node_label:
                continue
            if rel_type and edge_data.get('_rel_type') != rel_type:
                continue

            # Build result
            start_props = {k: v for k, v in start_data.items() if not k.startswith('_')}
            end_props = {k: v for k, v in end_data.items() if not k.startswith('_')}
            rel_props = {k: v for k, v in edge_data.items() if not k.startswith('_')}
            # Include _rel_type for delete operations
            rel_props['_rel_type'] = edge_data.get('_rel_type')

            results.append({
                'start': start_props,
                'end': end_props,
                'rel': rel_props
            })

        return results

    def query_nodes(self, label: str, filters: Optional[Dict[str, Any]] = None,
                   limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Query nodes by label with optional property filters.

        Args:
            label: Node label to filter by
            filters: Optional dict of property filters (exact match)
            limit: Maximum number of results to return (optional)

        Returns:
            List of node property dictionaries
        """
        results = []
        node_keys = self._label_index.get(label, set())

        for node_key in node_keys:
            if not self._graph.has_node(node_key):
                continue

            node_data = self._graph.nodes[node_key]

            # Apply filters
            if filters:
                match = True
                for key, value in filters.items():
                    if node_data.get(key) != value:
                        match = False
                        break
                if not match:
                    continue

            # Add to results (without internal metadata)
            node_props = {k: v for k, v in node_data.items() if not k.startswith('_')}
            results.append(node_props)

            # Check limit
            if limit and len(results) >= limit:
                break

        return results

    def create_index(self, label: str, property_key: str) -> None:
        """Create an index on a node property.

        Note: NetworkX doesn't have native indexing; this is tracked for compatibility.

        Args:
            label: Node label
            property_key: Property to index
        """
        # Index tracking for compatibility; actual lookups still scan
        index_name = f"{label}_{property_key}"
        if index_name not in self._text_indexes:
            self._text_indexes[index_name] = {property_key}

    def create_text_index(self, label: str, property_keys: List[str]) -> None:
        """Create a text search index on multiple properties.

        Args:
            label: Node label
            property_keys: List of properties to include in text search
        """
        index_name = f"{label}_text"
        self._text_indexes[index_name] = set(property_keys)

    def create_vector_index(self, label: str, property_key: str,
                          dimensions: int, similarity: str = 'cosine') -> None:
        """Create a vector similarity index.

        Args:
            label: Node label
            property_key: Property containing vector embeddings
            dimensions: Vector dimension size
            similarity: Similarity metric ('cosine' or 'euclidean')
        """
        index_name = f"{label}_vector"
        self._vector_indexes[index_name] = property_key

    def delete_index(self, label: str, property_key: str) -> None:
        """Delete an index.

        Args:
            label: Node label
            property_key: Property that was indexed
        """
        index_name = f"{label}_{property_key}"
        self._text_indexes.pop(index_name, None)
        self._vector_indexes.pop(index_name, None)

    def text_search(self, label: str, search_text: str,
                   property_keys: Optional[List[str]] = None,
                   limit: int = 10) -> List[Dict[str, Any]]:
        """Search nodes by text content.

        Args:
            label: Node label to search
            search_text: Text to search for (case-insensitive substring match)
            property_keys: Properties to search in (if None, search all)
            limit: Maximum number of results

        Returns:
            List of matching node property dictionaries
        """
        results = []
        search_lower = search_text.lower()
        node_keys = self._label_index.get(label, set())

        for node_key in node_keys:
            if not self._graph.has_node(node_key):
                continue

            node_data = self._graph.nodes[node_key]

            # Search in specified properties or all properties
            props_to_search = property_keys if property_keys else [
                k for k in node_data.keys() if not k.startswith('_')
            ]

            match = False
            for prop_key in props_to_search:
                value = node_data.get(prop_key)
                if value is not None and search_lower in str(value).lower():
                    match = True
                    break

            if match:
                node_props = {k: v for k, v in node_data.items() if not k.startswith('_')}
                results.append(node_props)

                if len(results) >= limit:
                    break

        return results

    def vector_search(self, label: str, vector: List[float],
                     property_key: str = 'embedding',
                     limit: int = 10, similarity: str = 'cosine') -> List[Tuple[Dict[str, Any], float]]:
        """Search nodes by vector similarity.

        Args:
            label: Node label to search
            vector: Query vector
            property_key: Property containing embeddings
            limit: Maximum number of results
            similarity: Similarity metric ('cosine' or 'euclidean')

        Returns:
            List of (node_properties, similarity_score) tuples, sorted by score
        """
        results = []
        query_vec = np.array(vector)
        node_keys = self._label_index.get(label, set())

        for node_key in node_keys:
            if not self._graph.has_node(node_key):
                continue

            node_data = self._graph.nodes[node_key]
            embedding = node_data.get(property_key)

            if embedding is None:
                continue

            node_vec = np.array(embedding)

            # Calculate similarity
            if similarity == 'cosine':
                score = np.dot(query_vec, node_vec) / (
                    np.linalg.norm(query_vec) * np.linalg.norm(node_vec)
                )
            elif similarity == 'euclidean':
                score = -np.linalg.norm(query_vec - node_vec)  # Negative distance
            else:
                raise ValueError(f"Unsupported similarity metric: {similarity}")

            node_props = {k: v for k, v in node_data.items() if not k.startswith('_')}
            results.append((node_props, float(score)))

        # Sort by score (descending) and limit
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def execute_pagerank(self, alpha: float = 0.85, max_iter: int = 100) -> None:
        """Execute PageRank algorithm and cache results.

        Args:
            alpha: Damping parameter (default: 0.85)
            max_iter: Maximum iterations (default: 100)
        """
        if self._graph.number_of_nodes() == 0:
            self._pagerank_scores = {}
            return

        self._pagerank_scores = nx.pagerank(self._graph, alpha=alpha, max_iter=max_iter)

    def get_pagerank_scores(self, label: Optional[str] = None,
                           limit: int = 10) -> List[Tuple[Dict[str, Any], float]]:
        """Get PageRank scores for nodes.

        Args:
            label: Optional label to filter nodes
            limit: Maximum number of results

        Returns:
            List of (node_properties, pagerank_score) tuples, sorted by score
        """
        if self._pagerank_scores is None:
            self.execute_pagerank()

        results = []

        for node_key, score in self._pagerank_scores.items():
            if not self._graph.has_node(node_key):
                continue

            node_data = self._graph.nodes[node_key]

            # Filter by label if specified
            if label and node_data.get('_label') != label:
                continue

            node_props = {k: v for k, v in node_data.items() if not k.startswith('_')}
            results.append((node_props, score))

        # Sort by score (descending) and limit
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def run_script(self, script: str, parameters: Optional[Dict[str, Any]] = None) -> Any:
        """Execute a custom script/query.

        Note: This is a placeholder for custom query execution.

        Args:
            script: Script or query string
            parameters: Optional parameters for the script

        Returns:
            Script execution results

        Raises:
            NotImplementedError: Custom script execution not supported
        """
        raise NotImplementedError("Custom script execution not supported in NetworkX implementation")

    def get_all_entity_labels(self) -> List[str]:
        """Get all unique node labels in the graph.

        Returns:
            List of unique node labels
        """
        return list(self._label_index.keys())

    def clear(self) -> None:
        """Clear all data from the graph."""
        self._graph.clear()
        self._node_index.clear()
        self._label_index.clear()
        self._text_indexes.clear()
        self._vector_indexes.clear()
        self._pagerank_scores = None

    def get_statistics(self) -> Dict[str, Any]:
        """Get graph statistics.

        Returns:
            Dictionary containing graph statistics
        """
        return {
            'num_nodes': self._graph.number_of_nodes(),
            'num_edges': self._graph.number_of_edges(),
            'num_labels': len(self._label_index),
            'labels': list(self._label_index.keys()),
            'is_directed': isinstance(self._graph, nx.DiGraph),
            'density': nx.density(self._graph) if self._graph.number_of_nodes() > 0 else 0.0
        }
