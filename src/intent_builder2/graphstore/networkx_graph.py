"""NetworkX-based graph storage implementation module.

This module implements a NetworkX-based graph data storage system, suitable for
medium-scale graph data operations and analysis. NetworkX provides rich graph
algorithms and analysis capabilities.
"""

import copy
from typing import Any, Dict, List, Optional, Tuple, Union

import networkx as nx
import numpy as np

from src.graphstore.graph_store import GraphStore


class NetworkXGraphStorage(GraphStore):
    """NetworkX-based graph storage implementation.

    Uses NetworkX's DiGraph to store graph data in memory, including nodes,
    relationships, and index information. Provides rich graph algorithm support
    and good performance.
    """

    def __init__(self):
        """Initialize NetworkX graph storage."""
        # Use directed graph
        self._graph = nx.DiGraph()

        # Index storage
        self._indexes: Dict[str, Dict[str, Any]] = {}

        # PageRank scores storage
        self._pagerank_scores: Dict[Tuple[str, Any], float] = {}

        # Graph schema storage
        self._schema: Optional[Any] = None

        # Node key mapping: (label, id_value) -> node_id
        self._node_key_to_id: Dict[Tuple[str, Any], str] = {}
        self._node_id_counter = 0

    def _get_node_id(self, label: str, id_value: Any) -> Optional[str]:
        """Get the internal ID of a node.

        Args:
            label: The node label.
            id_value: The node ID value.

        Returns:
            The internal node ID, or None if it doesn't exist.
        """
        return self._node_key_to_id.get((label, id_value))

    def _create_node_id(self, label: str, id_value: Any) -> str:
        """Create a new internal node ID.

        Args:
            label: The node label.
            id_value: The node ID value.

        Returns:
            The new internal node ID.
        """
        node_key = (label, id_value)
        if node_key in self._node_key_to_id:
            return self._node_key_to_id[node_key]

        node_id = f"node_{self._node_id_counter}"
        self._node_id_counter += 1
        self._node_key_to_id[node_key] = node_id
        return node_id

    def close(self):
        """Close the graph storage instance.

        Clears all data in the graph.
        """
        self._graph.clear()
        self._indexes.clear()
        self._pagerank_scores.clear()
        self._node_key_to_id.clear()
        self._schema = None

    def initialize_schema(self, schema):
        """Initialize the graph schema.

        Args:
            schema: The graph schema definition.
        """
        self._schema = schema

    def upsert_node(
        self,
        label: str,
        properties: Dict[str, Any],
        id_key: str = "id",
        extra_labels: Tuple[str, ...] = ("Entity",),
    ):
        """Insert or update a single node.

        Args:
            label: The label of the node.
            properties: The properties of the node.
            id_key: The property key used as a unique identifier. Defaults to "id".
            extra_labels: Additional labels for the node. Defaults to ("Entity",).

        Raises:
            ValueError: If id_key is missing from the properties dictionary.
        """
        if id_key not in properties:
            raise ValueError(f"Missing id_key in properties: {id_key}")

        id_value = properties[id_key]
        node_id = self._create_node_id(label, id_value)

        # Merge labels
        all_labels = list(extra_labels) + [label]

        # Create node attributes
        node_attrs = {"label": label, "labels": all_labels, **copy.deepcopy(properties)}

        # Add or update node
        if self._graph.has_node(node_id):
            # Update existing node
            self._graph.nodes[node_id].update(node_attrs)
        else:
            # Add new node
            self._graph.add_node(node_id, **node_attrs)

    def upsert_nodes(
        self,
        label: str,
        properties_list: List[Dict[str, Any]],
        id_key: str = "id",
        extra_labels: Tuple[str, ...] = ("Entity",),
    ):
        """Batch insert or update multiple nodes.

        Args:
            label: The label of the nodes.
            properties_list: List of node properties.
            id_key: The property key used as a unique identifier. Defaults to "id".
            extra_labels: Additional labels for the nodes. Defaults to ("Entity",).
        """
        for properties in properties_list:
            self.upsert_node(label, properties, id_key, extra_labels)

    def batch_preprocess_node_properties(
        self,
        node_batch: List[Dict[str, Any]],
        extra_labels: Tuple[str, ...] = ("Entity",),
    ):
        """Batch preprocess node properties.

        Args:
            node_batch: Batch of node data.
            extra_labels: Additional labels for the nodes. Defaults to ("Entity",).

        Returns:
            Preprocessed node data.
        """
        # For NetworkX implementation, no special preprocessing needed
        return node_batch

    def get_node(
        self, label: str, id_value: Any, id_key: str = "id"
    ) -> Optional[Dict[str, Any]]:
        """Get a node by label and identifier.

        Args:
            label: The label of the node.
            id_value: The unique identifier value of the node.
            id_key: The property key used as a unique identifier. Defaults to "id".

        Returns:
            The matching node object, or None if it doesn't exist.
        """
        node_id = self._get_node_id(label, id_value)
        if node_id is None or not self._graph.has_node(node_id):
            return None

        # Return a copy of node attributes
        return dict(self._graph.nodes[node_id])

    def delete_node(self, label: str, id_value: Any, id_key: str = "id"):
        """Delete a specified node.

        Args:
            label: The label of the node.
            id_value: The unique identifier value of the node.
            id_key: The property key used as a unique identifier. Defaults to "id".
        """
        node_id = self._get_node_id(label, id_value)
        if node_id and self._graph.has_node(node_id):
            self._graph.remove_node(node_id)
            # Clean up mapping
            node_key = (label, id_value)
            if node_key in self._node_key_to_id:
                del self._node_key_to_id[node_key]

    def delete_nodes(self, label: str, id_values: List[Any], id_key: str = "id"):
        """Batch delete multiple nodes.

        Args:
            label: The label of the nodes.
            id_values: List of unique identifier values for the nodes.
            id_key: The property key used as a unique identifier. Defaults to "id".
        """
        for id_value in id_values:
            self.delete_node(label, id_value, id_key)

    def upsert_relationship(
        self,
        start_node_label: str,
        start_node_id_value: Any,
        end_node_label: str,
        end_node_id_value: Any,
        rel_type: str,
        properties: Dict[str, Any],
        upsert_nodes: bool = True,
        start_node_id_key: str = "id",
        end_node_id_key: str = "id",
    ):
        """Insert or update a relationship.

        Args:
            start_node_label: The label of the start node.
            start_node_id_value: The unique identifier value of the start node.
            end_node_label: The label of the end node.
            end_node_id_value: The unique identifier value of the end node.
            rel_type: The type of the relationship.
            properties: The properties of the relationship.
            upsert_nodes: Whether to insert or update nodes as well. Defaults to True.
            start_node_id_key: The unique identifier property key for the start node.
                Defaults to "id".
            end_node_id_key: The unique identifier property key for the end node.
                Defaults to "id".

        Raises:
            ValueError: If start or end node doesn't exist and upsert_nodes is False.
        """
        # Create nodes if needed
        if upsert_nodes:
            if self._get_node_id(start_node_label, start_node_id_value) is None:
                self.upsert_node(
                    start_node_label, {start_node_id_key: start_node_id_value}
                )
            if self._get_node_id(end_node_label, end_node_id_value) is None:
                self.upsert_node(end_node_label, {end_node_id_key: end_node_id_value})

        start_node_id = self._get_node_id(start_node_label, start_node_id_value)
        end_node_id = self._get_node_id(end_node_label, end_node_id_value)

        if start_node_id is None or end_node_id is None:
            raise ValueError("Start or end node doesn't exist")

        # Create edge attributes
        edge_attrs = {"type": rel_type, **copy.deepcopy(properties)}

        # Add or update edge
        if self._graph.has_edge(start_node_id, end_node_id):
            self._graph[start_node_id][end_node_id].update(edge_attrs)
        else:
            self._graph.add_edge(start_node_id, end_node_id, **edge_attrs)

    def upsert_relationships(
        self,
        start_node_label: str,
        end_node_label: str,
        rel_type: str,
        relationships: List[Dict[str, Any]],
        upsert_nodes: bool = True,
        start_node_id_key: str = "id",
        end_node_id_key: str = "id",
    ):
        """Batch insert or update multiple relationships.

        Args:
            start_node_label: The label of the start nodes.
            end_node_label: The label of the end nodes.
            rel_type: The type of the relationships.
            relationships: List of relationships, each containing start and end node
                IDs and properties.
            upsert_nodes: Whether to insert or update nodes as well. Defaults to True.
            start_node_id_key: The unique identifier property key for the start nodes.
                Defaults to "id".
            end_node_id_key: The unique identifier property key for the end nodes.
                Defaults to "id".
        """
        for rel in relationships:
            start_id = rel.get("start_id") or rel.get(start_node_id_key)
            end_id = rel.get("end_id") or rel.get(end_node_id_key)
            properties = {
                k: v
                for k, v in rel.items()
                if k not in ["start_id", "end_id", start_node_id_key, end_node_id_key]
            }

            self.upsert_relationship(
                start_node_label,
                start_id,
                end_node_label,
                end_id,
                rel_type,
                properties,
                upsert_nodes,
                start_node_id_key,
                end_node_id_key,
            )

    def delete_relationship(
        self,
        start_node_label: str,
        start_node_id_value: Any,
        end_node_label: str,
        end_node_id_value: Any,
        rel_type: str,
        start_node_id_key: str = "id",
        end_node_id_key: str = "id",
    ):
        """Delete a specified relationship.

        Args:
            start_node_label: The label of the start node.
            start_node_id_value: The unique identifier value of the start node.
            end_node_label: The label of the end node.
            end_node_id_value: The unique identifier value of the end node.
            rel_type: The type of the relationship.
            start_node_id_key: The unique identifier property key for the start node.
                Defaults to "id".
            end_node_id_key: The unique identifier property key for the end node.
                Defaults to "id".
        """
        start_node_id = self._get_node_id(start_node_label, start_node_id_value)
        end_node_id = self._get_node_id(end_node_label, end_node_id_value)

        if (
            start_node_id
            and end_node_id
            and self._graph.has_edge(start_node_id, end_node_id)
        ):
            # Check if relationship type matches
            edge_data = self._graph[start_node_id][end_node_id]
            if edge_data.get("type") == rel_type:
                self._graph.remove_edge(start_node_id, end_node_id)

    def delete_relationships(
        self,
        start_node_label: str,
        start_node_id_values: List[Any],
        end_node_label: str,
        end_node_id_values: List[Any],
        rel_type: str,
        start_node_id_key: str = "id",
        end_node_id_key: str = "id",
    ):
        """Batch delete multiple relationships.

        Args:
            start_node_label: The label of the start nodes.
            start_node_id_values: List of unique identifier values for the start nodes.
            end_node_label: The label of the end nodes.
            end_node_id_values: List of unique identifier values for the end nodes.
            rel_type: The type of the relationships.
            start_node_id_key: The unique identifier property key for the start nodes.
                Defaults to "id".
            end_node_id_key: The unique identifier property key for the end nodes.
                Defaults to "id".
        """
        for start_id_value in start_node_id_values:
            for end_id_value in end_node_id_values:
                self.delete_relationship(
                    start_node_label,
                    start_id_value,
                    end_node_label,
                    end_id_value,
                    rel_type,
                    start_node_id_key,
                    end_node_id_key,
                )

    def create_index(
        self, label: str, property_key: str, index_name: Optional[str] = None
    ):
        """Create a node index.

        Args:
            label: The label of the nodes.
            property_key: The property key to index.
            index_name: The name of the index. If not provided, a default name will
                be generated.
        """
        if index_name is None:
            index_name = f"idx_{label}_{property_key}"

        self._indexes[index_name] = {
            "type": "property",
            "label": label,
            "property_key": property_key,
        }

    def create_text_index(
        self,
        labels: List[str],
        property_keys: List[str],
        index_name: Optional[str] = None,
    ):
        """Create a text index.

        Args:
            labels: List of node labels.
            property_keys: List of property keys to index.
            index_name: The name of the index. If not provided, a default name will
                be generated.
        """
        if index_name is None:
            index_name = f"text_idx_{'_'.join(labels)}"

        self._indexes[index_name] = {
            "type": "text",
            "labels": labels,
            "property_keys": property_keys,
        }

    def create_vector_index(
        self,
        label: str,
        property_key: str,
        index_name: Optional[str] = None,
        vector_dimensions: int = 768,
        metric_type: str = "cosine",
        hnsw_m: Optional[int] = None,
        hnsw_ef_construction: Optional[int] = None,
    ):
        """Create a vector index.

        Args:
            label: The label of the nodes.
            property_key: The property key to index.
            index_name: The name of the index. If not provided, a default name will
                be generated.
            vector_dimensions: The dimensionality of the vectors. Defaults to 768.
            metric_type: The distance metric type. Defaults to "cosine".
            hnsw_m: The m parameter for the HNSW algorithm. If not provided,
                defaults to 16.
            hnsw_ef_construction: The ef_construction parameter for the HNSW
                algorithm. If not provided, defaults to 100.
        """
        if index_name is None:
            index_name = f"vector_idx_{label}_{property_key}"

        self._indexes[index_name] = {
            "type": "vector",
            "label": label,
            "property_key": property_key,
            "vector_dimensions": vector_dimensions,
            "metric_type": metric_type,
            "hnsw_m": hnsw_m or 16,
            "hnsw_ef_construction": hnsw_ef_construction or 100,
        }

    def delete_index(self, index_name: str):
        """Delete a specified index.

        Args:
            index_name: The name of the index to delete.
        """
        if index_name in self._indexes:
            del self._indexes[index_name]

    def text_search(
        self,
        query_string: str,
        label_constraints: Optional[List[str]] = None,
        topk: int = 10,
        index_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a text search.

        Args:
            query_string: The query string.
            label_constraints: Label constraint conditions.
            topk: The maximum number of results to return. Defaults to 10.
            index_name: The name of the index to use.

        Returns:
            List of search results.
        """
        results = []
        query_lower = query_string.lower()

        # Find relevant index
        index_info = None
        if index_name and index_name in self._indexes:
            index_info = self._indexes[index_name]

        for node_id in self._graph.nodes():
            node_data = self._graph.nodes[node_id]
            label = node_data.get("label")

            # Check label constraints
            if label_constraints and label not in label_constraints:
                continue

            # If index is specified, check if label matches
            if index_info and label not in index_info.get("labels", [label]):
                continue

            # Search node properties
            score = 0

            # Determine which property keys to search
            search_keys = node_data.keys()
            if index_info:
                search_keys = index_info.get("property_keys", search_keys)

            for key in search_keys:
                value = node_data.get(key, "")
                if isinstance(value, str) and query_lower in value.lower():
                    score += value.lower().count(query_lower)

            if score > 0:
                results.append({"node": dict(node_data), "score": score})

        # Sort by score and return top-k
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:topk]

    def vector_search(
        self,
        label: str,
        property_key: str,
        query_text_or_vector: Union[str, List[float], np.ndarray],
        topk: int = 10,
        index_name: Optional[str] = None,
        ef_search: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a vector search.

        Args:
            label: The label of the nodes.
            property_key: The property key to search.
            query_text_or_vector: The query text or vector.
            topk: The maximum number of results to return. Defaults to 10.
            index_name: The name of the index to use.
            ef_search: The ef_search parameter for the HNSW algorithm, specifying
                the number of potential candidate nodes.

        Returns:
            List of search results.

        Raises:
            NotImplementedError: If query is text, as text queries require
                embedding model support.
        """
        results = []

        # If query is text, need to convert to vector (simplified here)
        if isinstance(query_text_or_vector, str):
            # In real applications, this should call an embedding model
            raise NotImplementedError("Text queries require embedding model support")

        query_vector = np.array(query_text_or_vector)

        # Find relevant index
        index_info = None
        if index_name and index_name in self._indexes:
            index_info = self._indexes[index_name]
            metric_type = index_info.get("metric_type", "cosine")
        else:
            metric_type = "cosine"

        # Search all nodes with matching labels
        for node_id in self._graph.nodes():
            node_data = self._graph.nodes[node_id]
            node_label = node_data.get("label")

            if node_label != label:
                continue

            if property_key not in node_data:
                continue

            node_vector = np.array(node_data[property_key])

            # Calculate similarity
            if metric_type == "cosine":
                # Cosine similarity
                similarity = np.dot(query_vector, node_vector) / (
                    np.linalg.norm(query_vector) * np.linalg.norm(node_vector)
                )
                distance = 1 - similarity
            elif metric_type == "euclidean":
                # Euclidean distance
                distance = np.linalg.norm(query_vector - node_vector)
            else:
                # Default to cosine distance
                similarity = np.dot(query_vector, node_vector) / (
                    np.linalg.norm(query_vector) * np.linalg.norm(node_vector)
                )
                distance = 1 - similarity

            results.append(
                {
                    "node": dict(node_data),
                    "distance": float(distance),
                    "similarity": (
                        float(1 - distance) if metric_type == "cosine" else None
                    ),
                }
            )

        # Sort by distance and return top-k
        results.sort(key=lambda x: x["distance"])
        return results[:topk]

    def execute_pagerank(self, iterations: int = 20, damping_factor: float = 0.85):
        """Execute the PageRank algorithm.

        Args:
            iterations: The number of iterations. Defaults to 20.
            damping_factor: The damping factor. Defaults to 0.85.
        """
        # Use NetworkX's PageRank algorithm
        try:
            pagerank = nx.pagerank(
                self._graph, alpha=damping_factor, max_iter=iterations
            )

            # Store results to internal dictionary
            # Need to map node_id back to (label, id_value)
            self._pagerank_scores.clear()

            for node_id, score in pagerank.items():
                # Find corresponding (label, id_value)
                for (label, id_value), nid in self._node_key_to_id.items():
                    if nid == node_id:
                        self._pagerank_scores[(label, id_value)] = score
                        break
        except Exception:
            # If graph is empty or other errors, clear scores
            self._pagerank_scores.clear()

    def get_pagerank_scores(
        self, start_nodes: List[Tuple[str, Any]], target_type: str
    ) -> Dict[Any, float]:
        """Get PageRank scores.

        Args:
            start_nodes: List of start nodes, each element is a (label, id_value) tuple.
            target_type: The target node type.

        Returns:
            Dictionary of PageRank scores, with node IDs as keys and scores as values.
        """
        scores = {}

        for (label, id_value), score in self._pagerank_scores.items():
            # Check if this is the target type
            if label == target_type:
                scores[id_value] = score

        return scores

    def run_script(self, script: str):
        """Execute a script.

        Args:
            script: The script content to execute.

        Raises:
            NotImplementedError: NetworkX implementation does not support script execution.
        """
        # NetworkX implementation doesn't support complex script execution
        raise NotImplementedError("NetworkX graph storage does not support script execution")

    def get_all_entity_labels(self) -> List[str]:
        """Get all entity labels.

        Returns:
            List of entity labels.
        """
        labels = set()
        for node_id in self._graph.nodes():
            node_data = self._graph.nodes[node_id]
            label = node_data.get("label")
            if label:
                labels.add(label)

        return sorted(list(labels))

    # Additional helper methods

    def get_all_nodes(self) -> List[Dict[str, Any]]:
        """Get all nodes.

        Returns:
            List of all nodes.
        """
        nodes = []
        for node_id in self._graph.nodes():
            nodes.append(dict(self._graph.nodes[node_id]))
        return nodes

    def get_all_relationships(self) -> List[Dict[str, Any]]:
        """Get all relationships.

        Returns:
            List of all relationships.
        """
        relationships = []
        for start_id, end_id, edge_data in self._graph.edges(data=True):
            # Find corresponding label and id_value
            start_label = self._graph.nodes[start_id].get("label")
            end_label = self._graph.nodes[end_id].get("label")
            start_id_value = self._graph.nodes[start_id].get("id")
            end_id_value = self._graph.nodes[end_id].get("id")

            relationships.append(
                {
                    "start_node": {"label": start_label, "id": start_id_value},
                    "end_node": {"label": end_label, "id": end_id_value},
                    "type": edge_data.get("type"),
                    "properties": {k: v for k, v in edge_data.items() if k != "type"},
                }
            )
        return relationships

    def get_node_relationships(
        self, label: str, id_value: Any, direction: str = "both"
    ) -> List[Dict[str, Any]]:
        """Get all relationships of a node.

        Args:
            label: The label of the node.
            id_value: The unique identifier value of the node.
            direction: The relationship direction, can be "in", "out", or "both".
                Defaults to "both".

        Returns:
            List of relationships.
        """
        node_id = self._get_node_id(label, id_value)
        if node_id is None:
            return []

        relationships = []

        # Outgoing edges
        if direction in ("out", "both"):
            for _, target_id, edge_data in self._graph.out_edges(node_id, data=True):
                target_label = self._graph.nodes[target_id].get("label")
                target_id_value = self._graph.nodes[target_id].get("id")

                relationships.append(
                    {
                        "direction": "out",
                        "type": edge_data.get("type"),
                        "target_node": {"label": target_label, "id": target_id_value},
                        "properties": {
                            k: v for k, v in edge_data.items() if k != "type"
                        },
                    }
                )

        # Incoming edges
        if direction in ("in", "both"):
            for source_id, _, edge_data in self._graph.in_edges(node_id, data=True):
                source_label = self._graph.nodes[source_id].get("label")
                source_id_value = self._graph.nodes[source_id].get("id")

                relationships.append(
                    {
                        "direction": "in",
                        "type": edge_data.get("type"),
                        "source_node": {"label": source_label, "id": source_id_value},
                        "properties": {
                            k: v for k, v in edge_data.items() if k != "type"
                        },
                    }
                )

        return relationships

    def clear(self):
        """Clear all data in the graph."""
        self._graph.clear()
        self._node_key_to_id.clear()
        self._pagerank_scores.clear()

    def __len__(self) -> int:
        """Return the number of nodes in the graph.

        Returns:
            The number of nodes.
        """
        return self._graph.number_of_nodes()

    def __repr__(self) -> str:
        """Return the string representation of the graph.

        Returns:
            String representation of the graph.
        """
        return (
            f"NetworkXGraphStorage(nodes={self._graph.number_of_nodes()}, "
            f"edges={self._graph.number_of_edges()}, "
            f"indexes={len(self._indexes)})"
        )
