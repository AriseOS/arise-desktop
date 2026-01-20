"""Memory-based graph storage implementation module.

This module implements a memory-based graph data storage system, suitable for
small-scale graph data operations and testing scenarios.
"""

import copy
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from src.cloud_backend.memgraph.graphstore.graph_store import GraphStore


class MemoryGraph(GraphStore):
    """Memory-based graph storage implementation.

    Uses Python dictionaries and lists to store graph data in memory, including
    nodes, relationships, and index information. Suitable for small-scale
    datasets and rapid prototyping.
    """

    def __init__(self):
        """Initialize memory graph storage."""
        # Node storage: {(label, id_value): {properties, labels}}
        self._nodes: Dict[Tuple[str, Any], Dict[str, Any]] = {}

        # Relationship storage: [(start_key, end_key, rel_type, properties)]
        self._relationships: List[Tuple[Tuple[str, Any], Tuple[str, Any], str, Dict[str, Any]]] = []

        # Index storage
        self._indexes: Dict[str, Dict[str, Any]] = {}

        # PageRank scores storage
        self._pagerank_scores: Dict[Tuple[str, Any], float] = {}

        # Graph schema storage
        self._schema: Optional[Any] = None

    def close(self):
        """Close the graph storage instance.

        Clears all data in memory.
        """
        self._nodes.clear()
        self._relationships.clear()
        self._indexes.clear()
        self._pagerank_scores.clear()
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
        extra_labels: Tuple[str, ...] = ("Entity",)
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
        node_key = (label, id_value)

        # Merge labels
        all_labels = list(extra_labels) + [label]

        # Store node
        self._nodes[node_key] = {
            "properties": copy.deepcopy(properties),
            "labels": all_labels
        }

    def upsert_nodes(
        self,
        label: str,
        properties_list: List[Dict[str, Any]],
        id_key: str = "id",
        extra_labels: Tuple[str, ...] = ("Entity",)
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
        extra_labels: Tuple[str, ...] = ("Entity",)
    ):
        """Batch preprocess node properties.

        Args:
            node_batch: Batch of node data.
            extra_labels: Additional labels for the nodes. Defaults to ("Entity",).

        Returns:
            Preprocessed node data.
        """
        # For memory implementation, no special preprocessing needed
        return node_batch

    def get_node(
        self,
        label: str,
        id_value: Any,
        id_key: str = "id"
    ) -> Optional[Dict[str, Any]]:
        """Get a node by label and identifier.

        Args:
            label: The label of the node.
            id_value: The unique identifier value of the node.
            id_key: The property key used as a unique identifier. Defaults to "id".

        Returns:
            The matching node object, or None if it doesn't exist.
        """
        node_key = (label, id_value)
        node = self._nodes.get(node_key)

        if node:
            return {
                "labels": node["labels"],
                **node["properties"]
            }
        return None

    def delete_node(
        self,
        label: str,
        id_value: Any,
        id_key: str = "id"
    ):
        """Delete a specified node.

        Args:
            label: The label of the node.
            id_value: The unique identifier value of the node.
            id_key: The property key used as a unique identifier. Defaults to "id".
        """
        node_key = (label, id_value)

        # Delete node
        if node_key in self._nodes:
            del self._nodes[node_key]

        # Delete related relationships
        self._relationships = [
            rel for rel in self._relationships
            if node_key not in (rel[0], rel[1])
        ]

    def delete_nodes(
        self,
        label: str,
        id_values: List[Any],
        id_key: str = "id"
    ):
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
        """
        start_key = (start_node_label, start_node_id_value)
        end_key = (end_node_label, end_node_id_value)

        # Create nodes if needed
        if upsert_nodes:
            if start_key not in self._nodes:
                self.upsert_node(
                    start_node_label,
                    {start_node_id_key: start_node_id_value}
                )
            if end_key not in self._nodes:
                self.upsert_node(
                    end_node_label,
                    {end_node_id_key: end_node_id_value}
                )

        # Remove existing same relationship
        self._relationships = [
            rel for rel in self._relationships
            if not (rel[0] == start_key and rel[1] == end_key and rel[2] == rel_type)
        ]

        # Add new relationship
        self._relationships.append(
            (start_key, end_key, rel_type, copy.deepcopy(properties))
        )

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
            properties = {k: v for k, v in rel.items()
                          if k not in ["start_id", "end_id", start_node_id_key, end_node_id_key]}

            self.upsert_relationship(
                start_node_label,
                start_id,
                end_node_label,
                end_id,
                rel_type,
                properties,
                upsert_nodes,
                start_node_id_key,
                end_node_id_key
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
        start_key = (start_node_label, start_node_id_value)
        end_key = (end_node_label, end_node_id_value)

        self._relationships = [
            rel for rel in self._relationships
            if not (rel[0] == start_key and rel[1] == end_key and rel[2] == rel_type)
        ]

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
        start_keys = {(start_node_label, id_val) for id_val in start_node_id_values}
        end_keys = {(end_node_label, id_val) for id_val in end_node_id_values}

        self._relationships = [
            rel for rel in self._relationships
            if not (rel[0] in start_keys and rel[1] in end_keys and rel[2] == rel_type)
        ]

    def create_index(
        self,
        label: str,
        property_key: str,
        index_name: Optional[str] = None
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
            "property_key": property_key
        }

    def create_text_index(
        self,
        labels: List[str],
        property_keys: List[str],
        index_name: Optional[str] = None
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
            "property_keys": property_keys
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
            "hnsw_ef_construction": hnsw_ef_construction or 100
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
        index_name: Optional[str] = None
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

        for node_key, node_data in self._nodes.items():
            label, id_value = node_key

            # Check label constraints
            if label_constraints and label not in label_constraints:
                continue

            # If index is specified, check if label matches
            if index_info and label not in index_info.get("labels", [label]):
                continue

            # Search node properties
            score = 0
            properties = node_data["properties"]

            # Determine which property keys to search
            search_keys = properties.keys()
            if index_info:
                search_keys = index_info.get("property_keys", search_keys)

            for key in search_keys:
                value = properties.get(key, "")
                if isinstance(value, str) and query_lower in value.lower():
                    score += value.lower().count(query_lower)

            if score > 0:
                results.append({
                    "node": self.get_node(label, id_value),
                    "score": score
                })

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
        for node_key, node_data in self._nodes.items():
            node_label, id_value = node_key

            if node_label != label:
                continue

            properties = node_data["properties"]
            if property_key not in properties:
                continue

            node_vector = np.array(properties[property_key])

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

            results.append({
                "node": self.get_node(label, id_value),
                "distance": float(distance),
                "similarity": float(1 - distance) if metric_type == "cosine" else None
            })

        # Sort by distance and return top-k
        results.sort(key=lambda x: x["distance"])
        return results[:topk]

    def execute_pagerank(
        self,
        iterations: int = 20,
        damping_factor: float = 0.85
    ):
        """Execute the PageRank algorithm.

        Args:
            iterations: The number of iterations. Defaults to 20.
            damping_factor: The damping factor. Defaults to 0.85.
        """
        # Initialize PageRank scores
        num_nodes = len(self._nodes)
        if num_nodes == 0:
            return

        # Initialize all node PageRank values
        for node_key in self._nodes:
            self._pagerank_scores[node_key] = 1.0 / num_nodes

        # Build out-degree dictionary
        out_degree = {}
        for node_key in self._nodes:
            out_degree[node_key] = 0

        for rel in self._relationships:
            start_key = rel[0]
            out_degree[start_key] = out_degree.get(start_key, 0) + 1

        # Iteratively calculate PageRank
        for _ in range(iterations):
            new_scores = {}

            for node_key in self._nodes:
                # Calculate contribution from other nodes
                rank_sum = 0.0
                for rel in self._relationships:
                    if rel[1] == node_key:  # Relationship pointing to current node
                        start_key = rel[0]
                        out_deg = out_degree.get(start_key, 1)
                        if out_deg > 0:
                            rank_sum += self._pagerank_scores[start_key] / out_deg

                # Apply PageRank formula
                new_scores[node_key] = (1 - damping_factor) / num_nodes + damping_factor * rank_sum

            self._pagerank_scores = new_scores

    def get_pagerank_scores(
        self,
        start_nodes: List[Tuple[str, Any]],
        target_type: str
    ) -> Dict[Any, float]:
        """Get PageRank scores.

        Args:
            start_nodes: List of start nodes, each element is a (label, id_value) tuple.
            target_type: The target node type.

        Returns:
            Dictionary of PageRank scores, with node IDs as keys and scores as values.
        """
        scores = {}

        for node_key, score in self._pagerank_scores.items():
            label, id_value = node_key

            # Check if this is the target type
            if label == target_type:
                scores[id_value] = score

        return scores

    def run_script(self, script: str):
        """Execute a script.

        Args:
            script: The script content to execute.

        Raises:
            NotImplementedError: Memory implementation does not support script execution.
        """
        # Memory implementation doesn't support complex script execution
        raise NotImplementedError("Memory graph storage does not support script execution")

    def get_all_entity_labels(self) -> List[str]:
        """Get all entity labels.

        Returns:
            List of entity labels.
        """
        labels = set()
        for node_key in self._nodes:
            label, _ = node_key
            labels.add(label)

        return sorted(list(labels))

    def query_relationships(
        self,
        start_node_label: Optional[str] = None,
        start_node_id_value: Optional[Any] = None,
        end_node_label: Optional[str] = None,
        end_node_id_value: Optional[Any] = None,
        rel_type: Optional[str] = None,
        start_node_id_key: str = 'id',
        end_node_id_key: str = 'id'
    ) -> List[Dict[str, Any]]:
        """Query relationships with optional filters.

        Args:
            start_node_label: The label of the start node, optional.
            start_node_id_value: The unique identifier value of the start node, optional.
            end_node_label: The label of the end node, optional.
            end_node_id_value: The unique identifier value of the end node, optional.
            rel_type: The type of the relationship, optional.
            start_node_id_key: The unique identifier property key of the start node, defaults to 'id'.
            end_node_id_key: The unique identifier property key of the end node, defaults to 'id'.

        Returns:
            List of relationship dictionaries with keys: 'rel', 'start_node', 'end_node'.
        """
        results = []

        for rel in self._relationships:
            start_key, end_key, r_type, properties = rel

            # Apply filters
            if start_node_label is not None and start_key[0] != start_node_label:
                continue
            if start_node_id_value is not None and start_key[1] != start_node_id_value:
                continue
            if end_node_label is not None and end_key[0] != end_node_label:
                continue
            if end_node_id_value is not None and end_key[1] != end_node_id_value:
                continue
            if rel_type is not None and r_type != rel_type:
                continue

            # Get full node data
            start_node = self.get_node(start_key[0], start_key[1])
            end_node = self.get_node(end_key[0], end_key[1])

            results.append({
                'rel': {
                    'type': r_type,
                    **properties
                },
                'start_node': start_node,
                'end_node': end_node
            })

        return results

    def query_nodes(
        self,
        label: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Query nodes with filters.

        Args:
            label: The label of the nodes to query.
            filters: Dictionary of property filters {property_key: value}.
            limit: Maximum number of results to return, optional.

        Returns:
            List of node dictionaries.
        """
        results = []

        for node_key, node_data in self._nodes.items():
            node_label, id_value = node_key

            # Check label match
            if node_label != label:
                continue

            # Apply property filters
            if filters:
                properties = node_data["properties"]
                match = True
                for key, value in filters.items():
                    if properties.get(key) != value:
                        match = False
                        break
                if not match:
                    continue

            # Add to results
            results.append(self.get_node(label, id_value))

            # Check limit
            if limit is not None and len(results) >= limit:
                break

        return results

    # Additional helper methods

    def get_all_nodes(self) -> List[Dict[str, Any]]:
        """Get all nodes.

        Returns:
            List of all nodes.
        """
        nodes = []
        for node_key in self._nodes:
            label, id_value = node_key
            nodes.append(self.get_node(label, id_value))
        return nodes

    def get_all_relationships(self) -> List[Dict[str, Any]]:
        """Get all relationships.

        Returns:
            List of all relationships.
        """
        relationships = []
        for rel in self._relationships:
            start_key, end_key, rel_type, properties = rel
            relationships.append({
                "start_node": {"label": start_key[0], "id": start_key[1]},
                "end_node": {"label": end_key[0], "id": end_key[1]},
                "type": rel_type,
                "properties": properties
            })
        return relationships

    def get_node_relationships(
        self,
        label: str,
        id_value: Any,
        direction: str = "both"
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
        node_key = (label, id_value)
        relationships = []

        for rel in self._relationships:
            start_key, end_key, rel_type, properties = rel

            if direction in ("out", "both") and start_key == node_key:
                relationships.append({
                    "direction": "out",
                    "type": rel_type,
                    "target_node": {"label": end_key[0], "id": end_key[1]},
                    "properties": properties
                })

            if direction in ("in", "both") and end_key == node_key:
                relationships.append({
                    "direction": "in",
                    "type": rel_type,
                    "source_node": {"label": start_key[0], "id": start_key[1]},
                    "properties": properties
                })

        return relationships

    def clear(self):
        """Clear all data in the graph."""
        self._nodes.clear()
        self._relationships.clear()
        self._pagerank_scores.clear()

    def __len__(self) -> int:
        """Return the number of nodes in the graph.

        Returns:
            The number of nodes.
        """
        return len(self._nodes)

    def __repr__(self) -> str:
        """Return the string representation of the graph.

        Returns:
            String representation of the graph.
        """
        return (
            f"MemoryGraph(nodes={len(self._nodes)}, "
            f"relationships={len(self._relationships)}, "
            f"indexes={len(self._indexes)})"
        )
