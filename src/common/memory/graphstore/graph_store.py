"""Graph storage abstract base class module.

This module defines the standard interface for graph data storage, including
operations for node CRUD, relationship management, index creation, and graph
algorithm execution.
"""

from abc import ABC
from abc import abstractmethod


class GraphStore(ABC):
    """Abstract base class for graph storage.

    This class defines the standard interface for graph data operations,
    ensuring subclasses implement specific graph operations such as node
    CRUD, relationship handling, and index management.
    """

    @abstractmethod
    def close(self):
        """Close the graph storage instance."""

    @abstractmethod
    def initialize_schema(self, schema):
        """Initialize the graph schema.

        Args:
            schema: The definition of the graph schema.
        """

    @abstractmethod
    def upsert_node(self, label, properties, id_key='id',
                    extra_labels=('Entity',)):
        """Insert or update a single node.

        Args:
            label: The label of the node.
            properties: The properties of the node.
            id_key: The property key used as unique identifier,
                defaults to 'id'.
            extra_labels: Additional labels for the node,
                defaults to ('Entity',).
        """

    @abstractmethod
    def upsert_nodes(self, label, properties_list, id_key='id',
                     extra_labels=('Entity',)):
        """Batch insert or update multiple nodes.

        Args:
            label: The label of the nodes.
            properties_list: List of node properties.
            id_key: The property key used as unique identifier,
                defaults to 'id'.
            extra_labels: Additional labels for the nodes,
                defaults to ('Entity',).
        """

    @abstractmethod
    def batch_preprocess_node_properties(self, node_batch,
                                        extra_labels=('Entity',)):
        """Batch preprocess node properties.

        Args:
            node_batch: Batch node data.
            extra_labels: Additional labels for the nodes,
                defaults to ('Entity',).
        """

    @abstractmethod
    def get_node(self, label, id_value, id_key='id'):
        """Get a node by label and identifier.

        Args:
            label: The label of the node.
            id_value: The unique identifier value of the node.
            id_key: The property key used as unique identifier,
                defaults to 'id'.

        Returns:
            The matching node object.
        """

    @abstractmethod
    def delete_node(self, label, id_value, id_key='id'):
        """Delete the specified node.

        Args:
            label: The label of the node.
            id_value: The unique identifier value of the node.
            id_key: The property key used as unique identifier,
                defaults to 'id'.
        """

    @abstractmethod
    def delete_nodes(self, label, id_values, id_key='id'):
        """Batch delete multiple nodes.

        Args:
            label: The label of the nodes.
            id_values: List of unique identifier values of the nodes.
            id_key: The property key used as unique identifier,
                defaults to 'id'.
        """

    @abstractmethod
    def upsert_relationship(self, start_node_label, start_node_id_value,
                          end_node_label, end_node_id_value, rel_type,
                          properties, upsert_nodes=True,
                          start_node_id_key='id', end_node_id_key='id'):
        """Insert or update a relationship.

        Args:
            start_node_label: The label of the start node.
            start_node_id_value: The unique identifier value of the start node.
            end_node_label: The label of the end node.
            end_node_id_value: The unique identifier value of the end node.
            rel_type: The type of the relationship.
            properties: The properties of the relationship.
            upsert_nodes: Whether to also insert or update nodes,
                defaults to True.
            start_node_id_key: The unique identifier property key of the
                start node, defaults to 'id'.
            end_node_id_key: The unique identifier property key of the
                end node, defaults to 'id'.
        """

    @abstractmethod
    def upsert_relationships(self, start_node_label, end_node_label, rel_type,
                           relationships, upsert_nodes=True,
                           start_node_id_key='id', end_node_id_key='id'):
        """Batch insert or update multiple relationships.

        Args:
            start_node_label: The label of the start nodes.
            end_node_label: The label of the end nodes.
            rel_type: The type of the relationships.
            relationships: List of relationships.
            upsert_nodes: Whether to also insert or update nodes,
                defaults to True.
            start_node_id_key: The unique identifier property key of the
                start nodes, defaults to 'id'.
            end_node_id_key: The unique identifier property key of the
                end nodes, defaults to 'id'.
        """

    @abstractmethod
    def delete_relationship(self, start_node_label, start_node_id_value,
                          end_node_label, end_node_id_value, rel_type,
                          start_node_id_key='id', end_node_id_key='id'):
        """Delete the specified relationship.

        Args:
            start_node_label: The label of the start node.
            start_node_id_value: The unique identifier value of the start node.
            end_node_label: The label of the end node.
            end_node_id_value: The unique identifier value of the end node.
            rel_type: The type of the relationship.
            start_node_id_key: The unique identifier property key of the
                start node, defaults to 'id'.
            end_node_id_key: The unique identifier property key of the
                end node, defaults to 'id'.
        """

    @abstractmethod
    def delete_relationships(self, start_node_label, start_node_id_values,
                           end_node_label, end_node_id_values, rel_type,
                           start_node_id_key='id', end_node_id_key='id'):
        """Batch delete multiple relationships.

        Args:
            start_node_label: The label of the start nodes.
            start_node_id_values: List of unique identifier values of the
                start nodes.
            end_node_label: The label of the end nodes.
            end_node_id_values: List of unique identifier values of the
                end nodes.
            rel_type: The type of the relationships.
            start_node_id_key: The unique identifier property key of the
                start nodes, defaults to 'id'.
            end_node_id_key: The unique identifier property key of the
                end nodes, defaults to 'id'.
        """

    @abstractmethod
    def create_index(self, label, property_key, index_name=None):
        """Create a node index.

        Args:
            label: The label of the nodes.
            property_key: The property key to index.
            index_name: The name of the index, optional.
        """

    @abstractmethod
    def create_text_index(self, labels, property_keys, index_name=None):
        """Create a text index.

        Args:
            labels: List of node labels.
            property_keys: List of property keys to index.
            index_name: The name of the index, optional.
        """

    @abstractmethod
    def create_vector_index(self, label, property_key, index_name=None,
                          vector_dimensions=768, metric_type='cosine',
                          hnsw_m=None, hnsw_ef_construction=None):
        """Create a vector index.

        Args:
            label: The label of the nodes.
            property_key: The property key to index.
            index_name: The name of the index, optional.
            vector_dimensions: The dimension of vectors, defaults to 768.
            metric_type: The distance metric type, defaults to 'cosine'.
            hnsw_m: The m parameter for HNSW algorithm, defaults to None
                (which means m=16).
            hnsw_ef_construction: The ef_construction parameter for HNSW
                algorithm, defaults to None (which means ef_construction=100).
        """

    @abstractmethod
    def delete_index(self, index_name):
        """Delete the specified index.

        Args:
            index_name: The name of the index.
        """

    @abstractmethod
    def text_search(self, query_string, label_constraints=None, topk=10,
                    index_name=None):
        """Execute text search.

        Args:
            query_string: The query string.
            label_constraints: Label constraint conditions, optional.
            topk: Maximum number of results to return, defaults to 10.
            index_name: The name of the index, optional.

        Returns:
            List of search results.
        """

    @abstractmethod
    def vector_search(self, label, property_key, query_text_or_vector,
                     topk=10, index_name=None, ef_search=None):
        """Execute vector search.

        Args:
            label: The label of the nodes.
            property_key: The property key to index.
            query_text_or_vector: The query text or vector.
            topk: Maximum number of results to return, defaults to 10.
            index_name: The name of the index, optional.
            ef_search: The ef_search parameter for HNSW algorithm,
                specifying the number of potential candidate nodes, optional.

        Returns:
            List of search results.
        """

    @abstractmethod
    def execute_pagerank(self, iterations=20, damping_factor=0.85):
        """Execute PageRank algorithm.

        Args:
            iterations: Number of iterations, defaults to 20.
            damping_factor: Damping factor, defaults to 0.85.
        """

    @abstractmethod
    def get_pagerank_scores(self, start_nodes, target_type):
        """Get PageRank scores.

        Args:
            start_nodes: Starting nodes.
            target_type: Target node type.

        Returns:
            PageRank scores.
        """

    @abstractmethod
    def run_script(self, script):
        """Execute a script.

        Args:
            script: The script content to execute.
        """

    @abstractmethod
    def get_all_entity_labels(self):
        """Get all entity labels.

        Returns:
            List of entity labels.
        """

    @abstractmethod
    def query_relationships(self, start_node_label=None, start_node_id_value=None,
                          end_node_label=None, end_node_id_value=None,
                          rel_type=None, start_node_id_key='id', end_node_id_key='id'):
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

    @abstractmethod
    def query_nodes(self, label, filters=None, limit=None):
        """Query nodes with filters.

        Args:
            label: The label of the nodes to query.
            filters: Dictionary of property filters {property_key: value}.
            limit: Maximum number of results to return, optional.

        Returns:
            List of node dictionaries.
        """
