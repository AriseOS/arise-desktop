"""Neo4j-based implementation of GraphStore.

This module provides a production-grade implementation of the GraphStore interface
using Neo4j as the backend. It supports persistent storage, ACID transactions,
native vector indexing, and graph algorithms.

Requirements:
    - neo4j >= 5.0
    - Neo4j Server >= 5.11 (for vector index support)
    - Optional: graphdatascience for PageRank
"""

import json
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple, Union

from src.common.memory.graphstore.graph_store import GraphStore

logger = logging.getLogger(__name__)



class Neo4jGraphStore(GraphStore):
    """Neo4j-based graph store implementation.

    This implementation uses Neo4j as the backend, providing:
    - Persistent storage with ACID transactions
    - Native vector indexing for semantic search
    - Fulltext search capabilities
    - Graph algorithms via GDS (optional)

    Thread-safety:
        The driver is thread-safe and can be shared.
        Sessions are created per-operation and are not shared.

    Attributes:
        _driver: Neo4j driver instance
        _database: Database name
        _vector_dimensions: Default vector dimensions for indexes
    """

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str = "neo4j",
        max_connection_pool_size: int = 50,
        connection_timeout: float = 30.0,
        vector_dimensions: int = 1024,
    ):
        """Initialize Neo4j connection.

        Args:
            uri: Neo4j connection URI (e.g., "neo4j://localhost:7687")
            user: Username for authentication
            password: Password for authentication
            database: Database name (default: "neo4j")
            max_connection_pool_size: Maximum connection pool size
            connection_timeout: Connection timeout in seconds
            vector_dimensions: Default embedding vector dimensions

        Raises:
            ImportError: If neo4j package is not installed
            ServiceUnavailable: If cannot connect to Neo4j
        """
        try:
            from neo4j import GraphDatabase
        except ImportError:
            raise ImportError(
                "neo4j package is required. Install with: pip install neo4j"
            )

        self._uri = uri
        self._user = user
        self._password = password
        self._database = database
        self._vector_dimensions = vector_dimensions

        self._driver = GraphDatabase.driver(
            uri,
            auth=(user, password),
            max_connection_pool_size=max_connection_pool_size,
            connection_timeout=connection_timeout,
        )

        # Verify connectivity
        try:
            self._driver.verify_connectivity()
            logger.info(f"Connected to Neo4j at {uri}, database: {database}")
        except Exception as e:
            self._driver.close()
            raise RuntimeError(
                f"Failed to connect to Neo4j at {uri}.\n"
                f"Error: {e}\n\n"
                f"To fix this:\n"
                f"  1. Start Neo4j: docker run -d -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/{password} neo4j:5.15\n"
                f"  2. Or use a different backend (surrealdb, networkx, memory) in config\n"
                f"  3. Check if Neo4j is running: curl http://localhost:7474"
            ) from e

        # Track created indexes
        self._text_indexes: Dict[str, set] = {}
        self._vector_indexes: Dict[str, str] = {}
        self._pagerank_executed: bool = False

    def close(self) -> None:
        """Close the driver and release resources."""
        if self._driver:
            self._driver.close()
            logger.info("Neo4j connection closed")

    def initialize_schema(self, schema: Any = None) -> None:
        """Initialize database schema with constraints and indexes.

        Creates unique constraints and indexes for the ontology model.

        Args:
            schema: Optional schema definition (unused, for interface compatibility)
        """
        constraints = [
            "CREATE CONSTRAINT domain_id IF NOT EXISTS FOR (d:Domain) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT state_id IF NOT EXISTS FOR (s:State) REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT phrase_id IF NOT EXISTS FOR (p:CognitivePhrase) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT intent_sequence_id IF NOT EXISTS FOR (seq:IntentSequence) REQUIRE seq.id IS UNIQUE",
        ]

        indexes = [
            "CREATE INDEX state_user_id IF NOT EXISTS FOR (s:State) ON (s.user_id)",
            "CREATE INDEX state_session_id IF NOT EXISTS FOR (s:State) ON (s.session_id)",
            "CREATE INDEX domain_user_id IF NOT EXISTS FOR (d:Domain) ON (d.user_id)",
            "CREATE INDEX phrase_user_id IF NOT EXISTS FOR (p:CognitivePhrase) ON (p.user_id)",
            "CREATE INDEX intent_sequence_state_id IF NOT EXISTS FOR (seq:IntentSequence) ON (seq.state_id)",
        ]

        # V2: Vector indexes for semantic search (requires Neo4j 5.11+)
        # Index names follow format: {label.lower()}_{property_key} to match vector_search()
        vector_indexes = [
            f"""CREATE VECTOR INDEX state_embedding_vector IF NOT EXISTS
            FOR (s:State) ON s.embedding_vector
            OPTIONS {{indexConfig: {{`vector.dimensions`: {self._vector_dimensions}}}}}""",
            f"""CREATE VECTOR INDEX cognitivephrase_embedding_vector IF NOT EXISTS
            FOR (p:CognitivePhrase) ON p.embedding_vector
            OPTIONS {{indexConfig: {{`vector.dimensions`: {self._vector_dimensions}}}}}""",
            f"""CREATE VECTOR INDEX intentsequence_embedding_vector IF NOT EXISTS
            FOR (seq:IntentSequence) ON seq.embedding_vector
            OPTIONS {{indexConfig: {{`vector.dimensions`: {self._vector_dimensions}}}}}""",
        ]

        with self._driver.session(database=self._database) as session:
            for cypher in constraints + indexes:
                try:
                    session.run(cypher)
                except Exception as e:
                    logger.warning(f"Schema initialization warning: {e}")

            # Vector indexes may fail on older Neo4j versions
            for cypher in vector_indexes:
                try:
                    session.run(cypher)
                    logger.info("Vector index created successfully")
                except Exception as e:
                    logger.warning(f"Vector index creation skipped (may require Neo4j 5.11+): {e}")

        logger.info("Schema initialized")

    # ==================== Helper Methods ====================

    def _serialize_properties(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Serialize complex properties to JSON strings.

        Neo4j only supports primitive types (str, int, float, bool) and
        arrays of primitives. All dicts and complex lists must be serialized.

        Args:
            properties: Original properties dict

        Returns:
            Dict with complex types serialized to JSON strings
        """
        result = {}
        for key, value in properties.items():
            if value is None:
                continue

            # embedding_vector: keep as native float[] (Neo4j supports this)
            if key == "embedding_vector" and isinstance(value, list):
                result[key] = value
                continue

            # Dict: always serialize to JSON (Neo4j doesn't support Map)
            if isinstance(value, dict):
                result[f"{key}_json"] = json.dumps(value, default=str, ensure_ascii=False)
                continue

            # List: check if it's a primitive list or complex list
            if isinstance(value, list):
                if len(value) == 0:
                    # Empty list - store as empty JSON array string
                    result[f"{key}_json"] = "[]"
                elif self._is_primitive_list(value):
                    # Primitive list (all same type) - Neo4j supports this
                    result[key] = value
                else:
                    # Complex list (objects, mixed types) - serialize to JSON
                    result[f"{key}_json"] = json.dumps(value, default=str, ensure_ascii=False)
                continue

            # Primitive types: store directly
            result[key] = value

        return result

    def _is_primitive_list(self, value: list) -> bool:
        """Check if a list contains only primitive values of the same type.

        Neo4j supports arrays of primitives (all same type).

        Args:
            value: List to check

        Returns:
            True if list is primitive and homogeneous
        """
        if not value:
            return False

        first_type = type(value[0])

        # Only these types are supported in Neo4j arrays
        if first_type not in (str, int, float, bool):
            return False

        # Check all elements are same type
        return all(isinstance(v, first_type) for v in value)

    def _deserialize_properties(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Deserialize JSON strings back to Python objects.

        Args:
            properties: Properties from Neo4j

        Returns:
            Dict with JSON strings deserialized
        """
        result = {}
        for key, value in properties.items():
            if key.endswith("_json") and isinstance(value, str):
                original_key = key[:-5]  # Remove _json suffix
                try:
                    result[original_key] = json.loads(value)
                except json.JSONDecodeError:
                    result[original_key] = value
            else:
                result[key] = value
        return result

    def _execute_write(self, work_func, *args, **kwargs):
        """Execute a write transaction with automatic retry.

        Args:
            work_func: Transaction function to execute
            *args: Arguments to pass to work_func
            **kwargs: Keyword arguments to pass to work_func

        Returns:
            Result from work_func
        """
        with self._driver.session(database=self._database) as session:
            return session.execute_write(work_func, *args, **kwargs)

    def _execute_read(self, work_func, *args, **kwargs):
        """Execute a read transaction.

        Args:
            work_func: Transaction function to execute
            *args: Arguments to pass to work_func
            **kwargs: Keyword arguments to pass to work_func

        Returns:
            Result from work_func
        """
        with self._driver.session(database=self._database) as session:
            return session.execute_read(work_func, *args, **kwargs)

    # ==================== Node Operations ====================

    def upsert_node(
        self,
        label: str,
        properties: Dict[str, Any],
        id_key: str = "id",
        extra_labels: Tuple[str, ...] = ("Entity",),
    ) -> None:
        """Insert or update a single node.

        Args:
            label: Node label
            properties: Node properties including the ID
            id_key: Property key for unique identifier (default: 'id')
            extra_labels: Additional labels (unused, for interface compatibility)

        Raises:
            ValueError: If id_key not in properties
        """
        if id_key not in properties:
            raise ValueError(f"Property '{id_key}' not found in node properties")

        id_value = properties[id_key]
        serialized = self._serialize_properties(properties)

        def _work(tx):
            tx.run(
                f"""
                MERGE (n:{label} {{{id_key}: $id}})
                SET n = $props
                """,
                id=id_value,
                props=serialized,
            )

        self._execute_write(_work)
        self._pagerank_executed = False

    def upsert_nodes(
        self,
        label: str,
        properties_list: List[Dict[str, Any]],
        id_key: str = "id",
        extra_labels: Tuple[str, ...] = ("Entity",),
    ) -> None:
        """Batch insert or update multiple nodes.

        Args:
            label: Node label
            properties_list: List of node properties
            id_key: Property key for unique identifier
            extra_labels: Additional labels (unused)
        """
        if not properties_list:
            return

        serialized_list = [self._serialize_properties(p) for p in properties_list]

        def _work(tx):
            tx.run(
                f"""
                UNWIND $nodes AS node
                MERGE (n:{label} {{{id_key}: node.{id_key}}})
                SET n = node
                """,
                nodes=serialized_list,
            )

        self._execute_write(_work)
        self._pagerank_executed = False

    def batch_preprocess_node_properties(
        self,
        node_batch: List[Tuple[str, Dict[str, Any]]],
        extra_labels: Tuple[str, ...] = ("Entity",),
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Preprocess node properties before batch insertion.

        Args:
            node_batch: List of (label, properties) tuples
            extra_labels: Additional labels (unused)

        Returns:
            Preprocessed list of (label, properties) tuples
        """
        return [(label, self._serialize_properties(props)) for label, props in node_batch]

    def get_node(
        self,
        label: str,
        id_value: Any,
        id_key: str = "id",
    ) -> Optional[Dict[str, Any]]:
        """Get a node by label and ID.

        Args:
            label: Node label
            id_value: Unique identifier value
            id_key: Property key for unique identifier

        Returns:
            Node properties dict if found, None otherwise
        """

        def _work(tx):
            result = tx.run(
                f"MATCH (n:{label} {{{id_key}: $id}}) RETURN n",
                id=id_value,
            )
            record = result.single()
            if record:
                return dict(record["n"])
            return None

        node_data = self._execute_read(_work)
        if node_data:
            return self._deserialize_properties(node_data)
        return None

    def delete_node(
        self,
        label: str,
        id_value: Any,
        id_key: str = "id",
    ) -> bool:
        """Delete a node and its relationships.

        Args:
            label: Node label
            id_value: Unique identifier value
            id_key: Property key for unique identifier

        Returns:
            True if node was deleted, False if not found
        """

        def _work(tx):
            result = tx.run(
                f"""
                MATCH (n:{label} {{{id_key}: $id}})
                DETACH DELETE n
                RETURN count(n) AS deleted
                """,
                id=id_value,
            )
            record = result.single()
            return record["deleted"] > 0 if record else False

        deleted = self._execute_write(_work)
        if deleted:
            self._pagerank_executed = False
        return deleted

    def delete_nodes(
        self,
        label: str,
        id_values: List[Any],
        id_key: str = "id",
    ) -> int:
        """Batch delete multiple nodes.

        Args:
            label: Node label
            id_values: List of unique identifier values
            id_key: Property key for unique identifier

        Returns:
            Number of nodes deleted
        """
        if not id_values:
            return 0

        def _work(tx):
            result = tx.run(
                f"""
                MATCH (n:{label})
                WHERE n.{id_key} IN $ids
                DETACH DELETE n
                RETURN count(n) AS deleted
                """,
                ids=id_values,
            )
            record = result.single()
            return record["deleted"] if record else 0

        deleted = self._execute_write(_work)
        if deleted > 0:
            self._pagerank_executed = False
        return deleted

    def query_nodes(
        self,
        label: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Query nodes with optional filters.

        Args:
            label: Node label to query
            filters: Dictionary of property filters (exact match)
            limit: Maximum number of results

        Returns:
            List of node property dictionaries
        """

        def _work(tx):
            where_clause = ""
            params = {}

            if filters:
                conditions = []
                for i, (key, value) in enumerate(filters.items()):
                    param_name = f"p{i}"
                    conditions.append(f"n.{key} = ${param_name}")
                    params[param_name] = value
                where_clause = "WHERE " + " AND ".join(conditions)

            limit_clause = f"LIMIT {limit}" if limit else ""

            query = f"MATCH (n:{label}) {where_clause} RETURN n {limit_clause}"
            result = tx.run(query, **params)
            return [dict(record["n"]) for record in result]

        nodes = self._execute_read(_work)
        return [self._deserialize_properties(n) for n in nodes]

    # ==================== Relationship Operations ====================

    def upsert_relationship(
        self,
        start_node_label: str,
        start_node_id_value: Any,
        end_node_label: str,
        end_node_id_value: Any,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None,
        upsert_nodes: bool = True,
        start_node_id_key: str = "id",
        end_node_id_key: str = "id",
    ) -> None:
        """Insert or update a relationship.

        Args:
            start_node_label: Label of the start node
            start_node_id_value: ID value of the start node
            end_node_label: Label of the end node
            end_node_id_value: ID value of the end node
            rel_type: Relationship type
            properties: Relationship properties
            upsert_nodes: Whether to create nodes if not exist (unused in Neo4j)
            start_node_id_key: ID property key for start node
            end_node_id_key: ID property key for end node
        """
        serialized = self._serialize_properties(properties or {})

        def _work(tx):
            tx.run(
                f"""
                MATCH (a:{start_node_label} {{{start_node_id_key}: $start_id}})
                MATCH (b:{end_node_label} {{{end_node_id_key}: $end_id}})
                MERGE (a)-[r:{rel_type}]->(b)
                SET r = $props
                """,
                start_id=start_node_id_value,
                end_id=end_node_id_value,
                props=serialized,
            )

        self._execute_write(_work)
        self._pagerank_executed = False

    def upsert_relationships(
        self,
        start_node_label: str,
        end_node_label: str,
        rel_type: str,
        relationships: List[Dict[str, Any]],
        upsert_nodes: bool = True,
        start_node_id_key: str = "id",
        end_node_id_key: str = "id",
    ) -> None:
        """Batch insert or update multiple relationships.

        Args:
            start_node_label: Label of the start nodes
            end_node_label: Label of the end nodes
            rel_type: Relationship type
            relationships: List of relationship dicts with start_id, end_id, and properties
            upsert_nodes: Whether to create nodes if not exist
            start_node_id_key: ID property key for start nodes
            end_node_id_key: ID property key for end nodes
        """
        if not relationships:
            return

        processed = []
        for rel in relationships:
            processed.append({
                "start_id": rel.get("start_id") or rel.get("source"),
                "end_id": rel.get("end_id") or rel.get("target"),
                "props": self._serialize_properties(rel.get("properties", {})),
            })

        def _work(tx):
            tx.run(
                f"""
                UNWIND $rels AS rel
                MATCH (a:{start_node_label} {{{start_node_id_key}: rel.start_id}})
                MATCH (b:{end_node_label} {{{end_node_id_key}: rel.end_id}})
                MERGE (a)-[r:{rel_type}]->(b)
                SET r = rel.props
                """,
                rels=processed,
            )

        self._execute_write(_work)
        self._pagerank_executed = False

    def delete_relationship(
        self,
        start_node_label: str,
        start_node_id_value: Any,
        end_node_label: str,
        end_node_id_value: Any,
        rel_type: str,
        start_node_id_key: str = "id",
        end_node_id_key: str = "id",
    ) -> bool:
        """Delete a relationship.

        Args:
            start_node_label: Label of the start node
            start_node_id_value: ID value of the start node
            end_node_label: Label of the end node
            end_node_id_value: ID value of the end node
            rel_type: Relationship type
            start_node_id_key: ID property key for start node
            end_node_id_key: ID property key for end node

        Returns:
            True if relationship was deleted
        """

        def _run_delete(rel_type: str) -> bool:
            def _work(tx):
                result = tx.run(
                    f"""
                    MATCH (a:{start_node_label} {{{start_node_id_key}: $start_id}})
                          -[r:{rel_type}]->
                          (b:{end_node_label} {{{end_node_id_key}: $end_id}})
                    DELETE r
                    RETURN count(r) AS deleted
                    """,
                    start_id=start_node_id_value,
                    end_id=end_node_id_value,
                )
                record = result.single()
                return record["deleted"] > 0 if record else False

            return self._execute_write(_work)

        return _run_delete(rel_type)

    def delete_relationships(
        self,
        start_node_label: str,
        start_node_id_values: List[Any],
        end_node_label: str,
        end_node_id_values: List[Any],
        rel_type: str,
        start_node_id_key: str = "id",
        end_node_id_key: str = "id",
    ) -> int:
        """Batch delete multiple relationships.

        Args:
            start_node_label: Label of the start nodes
            start_node_id_values: List of start node ID values
            end_node_label: Label of the end nodes
            end_node_id_values: List of end node ID values
            rel_type: Relationship type
            start_node_id_key: ID property key for start nodes
            end_node_id_key: ID property key for end nodes

        Returns:
            Number of relationships deleted
        """
        if not start_node_id_values or not end_node_id_values:
            return 0

        pairs = list(zip(start_node_id_values, end_node_id_values))

        def _run_delete(rel_type: str) -> int:
            def _work(tx):
                result = tx.run(
                    f"""
                    UNWIND $pairs AS pair
                    MATCH (a:{start_node_label} {{{start_node_id_key}: pair[0]}})
                          -[r:{rel_type}]->
                          (b:{end_node_label} {{{end_node_id_key}: pair[1]}})
                    DELETE r
                    RETURN count(r) AS deleted
                    """,
                    pairs=pairs,
                )
                record = result.single()
                return record["deleted"] if record else 0

            return self._execute_write(_work)

        return _run_delete(rel_type)

    def query_relationships(
        self,
        start_node_label: Optional[str] = None,
        start_node_id_value: Optional[Any] = None,
        end_node_label: Optional[str] = None,
        end_node_id_value: Optional[Any] = None,
        rel_type: Optional[str] = None,
        start_node_id_key: str = "id",
        end_node_id_key: str = "id",
    ) -> List[Dict[str, Any]]:
        """Query relationships with optional filters.

        Args:
            start_node_label: Filter by start node label
            start_node_id_value: Filter by start node ID
            end_node_label: Filter by end node label
            end_node_id_value: Filter by end node ID
            rel_type: Filter by relationship type
            start_node_id_key: ID property key for start node
            end_node_id_key: ID property key for end node

        Returns:
            List of dicts with 'start', 'end', 'rel' keys
        """

        def _work(tx):
            # Build match pattern
            start_pattern = f"(a:{start_node_label})" if start_node_label else "(a)"
            end_pattern = f"(b:{end_node_label})" if end_node_label else "(b)"
            rel_pattern = f"[r:{rel_type}]" if rel_type else "[r]"

            conditions = []
            params = {}

            if start_node_id_value is not None:
                conditions.append(f"a.{start_node_id_key} = $start_id")
                params["start_id"] = start_node_id_value
            if end_node_id_value is not None:
                conditions.append(f"b.{end_node_id_key} = $end_id")
                params["end_id"] = end_node_id_value

            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

            query = f"""
                MATCH {start_pattern}-{rel_pattern}->{end_pattern}
                {where_clause}
                RETURN a, r, b
            """
            result = tx.run(query, **params)

            relationships = []
            for record in result:
                start_props = self._deserialize_properties(dict(record["a"]))
                end_props = self._deserialize_properties(dict(record["b"]))
                rel_props = self._deserialize_properties(dict(record["r"]))
                rel_props["_rel_type"] = record["r"].type

                relationships.append({
                    "start": start_props,
                    "end": end_props,
                    "rel": rel_props,
                })

            return relationships

        return self._execute_read(_work)

    # ==================== Index Operations ====================

    def create_index(
        self,
        label: str,
        property_key: str,
        index_name: Optional[str] = None,
    ) -> None:
        """Create a property index.

        Args:
            label: Node label
            property_key: Property to index
            index_name: Optional index name
        """
        name = index_name or f"{label.lower()}_{property_key}"

        def _work(tx):
            tx.run(
                f"CREATE INDEX {name} IF NOT EXISTS FOR (n:{label}) ON (n.{property_key})"
            )

        self._execute_write(_work)
        logger.info(f"Created index: {name}")

    def create_text_index(
        self,
        labels: Union[str, List[str]],
        property_keys: List[str],
        index_name: Optional[str] = None,
    ) -> None:
        """Create a fulltext index.

        Args:
            labels: Node label(s)
            property_keys: List of properties to index
            index_name: Optional index name
        """
        if isinstance(labels, str):
            labels = [labels]

        label_str = "|".join(labels)
        name = index_name or f"{labels[0].lower()}_fulltext"
        props_str = ", ".join([f"n.{p}" for p in property_keys])

        def _work(tx):
            tx.run(
                f"""
                CREATE FULLTEXT INDEX {name} IF NOT EXISTS
                FOR (n:{label_str})
                ON EACH [{props_str}]
                """
            )

        self._execute_write(_work)
        self._text_indexes[name] = set(property_keys)
        logger.info(f"Created fulltext index: {name}")

    def create_vector_index(
        self,
        label: str,
        property_key: str,
        index_name: Optional[str] = None,
        vector_dimensions: int = 1024,
        metric_type: str = "cosine",
        hnsw_m: Optional[int] = None,
        hnsw_ef_construction: Optional[int] = None,
    ) -> None:
        """Create a vector index.

        Args:
            label: Node label
            property_key: Property containing vector embeddings
            index_name: Optional index name
            vector_dimensions: Vector dimension size
            metric_type: Distance metric ('cosine' or 'euclidean')
            hnsw_m: HNSW m parameter (optional)
            hnsw_ef_construction: HNSW ef_construction parameter (optional)
        """
        name = index_name or f"{label.lower()}_{property_key}"

        def _work(tx):
            tx.run(
                f"""
                CREATE VECTOR INDEX {name} IF NOT EXISTS
                FOR (n:{label})
                ON n.{property_key}
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: {vector_dimensions},
                        `vector.similarity_function`: '{metric_type}'
                    }}
                }}
                """
            )

        self._execute_write(_work)
        self._vector_indexes[name] = property_key
        logger.info(f"Created vector index: {name} (dimensions={vector_dimensions})")

    def delete_index(self, index_name: str) -> None:
        """Delete an index.

        Args:
            index_name: Name of the index to delete
        """

        def _work(tx):
            tx.run(f"DROP INDEX {index_name} IF EXISTS")

        self._execute_write(_work)
        self._text_indexes.pop(index_name, None)
        self._vector_indexes.pop(index_name, None)
        logger.info(f"Deleted index: {index_name}")

    def recreate_vector_indexes(self) -> None:
        """Drop and recreate all vector indexes with current dimension settings.

        Use this when changing vector dimensions (e.g., from 768 to 1024).
        This is a destructive operation - existing embeddings will need to be re-indexed.
        """
        # Vector index names used in initialize_schema
        vector_index_names = [
            "state_embedding_vector",
            "cognitivephrase_embedding_vector",
            "intentsequence_embedding_vector",
        ]

        for index_name in vector_index_names:
            try:
                self.delete_index(index_name)
                logger.info(f"Dropped vector index: {index_name}")
            except Exception as e:
                logger.warning(f"Failed to drop index {index_name}: {e}")

        # Recreate with current dimensions
        vector_indexes = [
            f"""CREATE VECTOR INDEX state_embedding_vector IF NOT EXISTS
            FOR (s:State) ON s.embedding_vector
            OPTIONS {{indexConfig: {{`vector.dimensions`: {self._vector_dimensions}}}}}""",
            f"""CREATE VECTOR INDEX cognitivephrase_embedding_vector IF NOT EXISTS
            FOR (p:CognitivePhrase) ON p.embedding_vector
            OPTIONS {{indexConfig: {{`vector.dimensions`: {self._vector_dimensions}}}}}""",
            f"""CREATE VECTOR INDEX intentsequence_embedding_vector IF NOT EXISTS
            FOR (seq:IntentSequence) ON seq.embedding_vector
            OPTIONS {{indexConfig: {{`vector.dimensions`: {self._vector_dimensions}}}}}""",
        ]

        with self._driver.session(database=self._database) as session:
            for cypher in vector_indexes:
                try:
                    session.run(cypher)
                    logger.info(f"Recreated vector index with {self._vector_dimensions} dimensions")
                except Exception as e:
                    logger.warning(f"Failed to create vector index: {e}")

    # ==================== Search Operations ====================

    def text_search(
        self,
        query_string: str,
        label_constraints: Optional[List[str]] = None,
        topk: int = 10,
        index_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Execute fulltext search.

        Args:
            query_string: Search query
            label_constraints: Optional label filters
            topk: Maximum results
            index_name: Index to search (uses first available if not specified)

        Returns:
            List of matching node dictionaries with score
        """
        if index_name is None:
            if self._text_indexes:
                index_name = list(self._text_indexes.keys())[0]
            else:
                logger.warning("No fulltext index available")
                return []

        def _work(tx):
            result = tx.run(
                f"""
                CALL db.index.fulltext.queryNodes($index, $query)
                YIELD node, score
                RETURN node, score
                LIMIT $limit
                """,
                index=index_name,
                query=query_string,
                limit=topk,
            )
            return [
                {
                    **self._deserialize_properties(dict(record["node"])),
                    "_score": record["score"],
                }
                for record in result
            ]

        return self._execute_read(_work)

    def vector_search(
        self,
        label: str,
        property_key: str,
        query_text_or_vector: Union[str, List[float]],
        topk: int = 10,
        index_name: Optional[str] = None,
        ef_search: Optional[int] = None,
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Execute vector similarity search.

        Args:
            label: Node label
            property_key: Property containing embeddings
            query_text_or_vector: Query vector (must be a list of floats)
            topk: Number of results
            index_name: Optional index name
            ef_search: Optional HNSW ef_search parameter

        Returns:
            List of (node_properties, similarity_score) tuples
        """
        if isinstance(query_text_or_vector, str):
            raise ValueError("query_text_or_vector must be a list of floats")

        name = index_name or f"{label.lower()}_{property_key}"

        def _work(tx):
            result = tx.run(
                """
                CALL db.index.vector.queryNodes($index, $k, $vector)
                YIELD node, score
                RETURN node, score
                """,
                index=name,
                k=topk,
                vector=query_text_or_vector,
            )
            return [
                (self._deserialize_properties(dict(record["node"])), record["score"])
                for record in result
            ]

        return self._execute_read(_work)

    # ==================== Graph Algorithms ====================

    def execute_pagerank(
        self,
        iterations: int = 20,
        damping_factor: float = 0.85,
    ) -> None:
        """Execute PageRank algorithm.

        Attempts to use GDS library, falls back to simulated PageRank.

        Args:
            iterations: Number of iterations
            damping_factor: Damping factor (default: 0.85)
        """
        try:
            self._execute_pagerank_gds(iterations, damping_factor)
        except Exception as e:
            logger.warning(f"GDS PageRank failed, using fallback: {e}")
            self._execute_pagerank_fallback(iterations, damping_factor)

        self._pagerank_executed = True

    def _execute_pagerank_gds(self, iterations: int, damping_factor: float) -> None:
        """Execute PageRank using Neo4j GDS library."""
        try:
            from graphdatascience import GraphDataScience
        except ImportError:
            raise ImportError("graphdatascience not installed")

        gds = GraphDataScience(self._uri, auth=(self._user, self._password))

        try:
            # Drop existing projection if exists
            try:
                gds.graph.drop("pagerank_graph")
            except Exception:
                pass

            # Project graph (use lowercase relationship types)
            G, _ = gds.graph.project(
                "pagerank_graph",
                ["State", "Domain"],
                {"action": {"orientation": "NATURAL"}, "manages": {"orientation": "NATURAL"}},
            )

            # Execute PageRank
            gds.pageRank.write(
                G,
                writeProperty="pagerank",
                maxIterations=iterations,
                dampingFactor=damping_factor,
            )

            G.drop()
        finally:
            gds.close()

        logger.info("PageRank executed via GDS")

    def _execute_pagerank_fallback(self, iterations: int, damping_factor: float) -> None:
        """Fallback PageRank implementation using pure Cypher.

        This is a simplified implementation for small graphs.
        For production use with large graphs, use GDS.
        """

        def _work(tx):
            # Count nodes and initialize
            result = tx.run("MATCH (n:State) RETURN count(n) AS cnt")
            node_count = result.single()["cnt"]

            if node_count == 0:
                return

            initial_rank = 1.0 / node_count

            # Initialize pagerank
            tx.run(
                "MATCH (n:State) SET n.pagerank = $rank",
                rank=initial_rank,
            )

            # Iterative update (simplified)
            for _ in range(iterations):
                tx.run(
                    """
                    MATCH (n:State)
                    OPTIONAL MATCH (m:State)-[:action]->(n)
                    WITH n, collect(m) AS inbound
                    WITH n,
                         CASE WHEN size(inbound) > 0
                              THEN reduce(s = 0.0, m IN inbound |
                                   s + m.pagerank / size((m)-[:action]->()))
                              ELSE 0.0
                         END AS incomingRank
                    SET n.pagerank = (1 - $damping) / $count + $damping * incomingRank
                    """,
                    damping=damping_factor,
                    count=node_count,
                )

        self._execute_write(_work)
        logger.info("PageRank executed via fallback")

    def get_pagerank_scores(
        self,
        start_nodes: Optional[List[str]] = None,
        target_type: Optional[str] = None,
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Get PageRank scores.

        Args:
            start_nodes: Not used (for interface compatibility)
            target_type: Node label to filter (default: State)

        Returns:
            List of (node_properties, pagerank_score) tuples
        """
        if not self._pagerank_executed:
            self.execute_pagerank()

        label = target_type or "State"

        def _work(tx):
            result = tx.run(
                f"""
                MATCH (n:{label})
                WHERE n.pagerank IS NOT NULL
                RETURN n, n.pagerank AS score
                ORDER BY score DESC
                LIMIT 100
                """
            )
            return [
                (self._deserialize_properties(dict(record["n"])), record["score"])
                for record in result
            ]

        return self._execute_read(_work)

    # ==================== Utility Methods ====================

    def run_script(self, script: str) -> Any:
        """Execute a Cypher script.

        Args:
            script: Cypher query to execute

        Returns:
            Query results
        """

        def _work(tx):
            result = tx.run(script)
            return [dict(record) for record in result]

        return self._execute_read(_work)

    def get_all_entity_labels(self) -> List[str]:
        """Get all unique node labels in the graph.

        Returns:
            List of node labels
        """

        def _work(tx):
            result = tx.run("CALL db.labels()")
            return [record[0] for record in result]

        return self._execute_read(_work)

    def clear(self) -> None:
        """Clear all data from the graph.

        WARNING: This deletes all nodes and relationships!
        """

        def _work(tx):
            tx.run("MATCH (n) DETACH DELETE n")

        self._execute_write(_work)
        self._pagerank_executed = False
        logger.warning("Graph cleared")

    def delete_nodes_by_filter(
        self,
        label: str,
        filters: Dict[str, Any],
    ) -> int:
        """Delete all nodes matching the filter criteria in one query.

        This is more efficient than deleting nodes one by one.

        TODO: For very large datasets, this may still be slow.
        Consider using APOC procedures or batched deletion:
        - CALL apoc.periodic.iterate() for batched deletion
        - Or add LIMIT and loop until all deleted

        Args:
            label: Node label
            filters: Filter criteria (e.g., {"user_id": "xxx"})

        Returns:
            Number of nodes deleted
        """
        if not filters:
            raise ValueError("Filters required for bulk deletion (safety)")

        def _work(tx):
            # Build WHERE clause
            conditions = []
            for key in filters.keys():
                conditions.append(f"n.{key} = ${key}")
            where_clause = " AND ".join(conditions)

            result = tx.run(
                f"""
                MATCH (n:{label})
                WHERE {where_clause}
                DETACH DELETE n
                RETURN count(n) AS deleted
                """,
                **filters,
            )
            record = result.single()
            return record["deleted"] if record else 0

        deleted = self._execute_write(_work)
        if deleted > 0:
            self._pagerank_executed = False
        logger.info(f"Bulk deleted {deleted} {label} nodes with filters {filters}")
        return deleted

    def delete_all_nodes_by_label(self, label: str) -> int:
        """Delete ALL nodes with the given label.

        WARNING: This deletes all nodes of this type. Use with caution.

        Args:
            label: Node label to delete

        Returns:
            Number of nodes deleted
        """
        def _work(tx):
            result = tx.run(
                f"""
                MATCH (n:{label})
                DETACH DELETE n
                RETURN count(n) AS deleted
                """
            )
            record = result.single()
            return record["deleted"] if record else 0

        deleted = self._execute_write(_work)
        if deleted > 0:
            self._pagerank_executed = False
        logger.info(f"Deleted ALL {deleted} {label} nodes")
        return deleted

    def delete_relationships_by_filter(
        self,
        rel_type: str,
        filters: Dict[str, Any],
        start_label: Optional[str] = None,
        end_label: Optional[str] = None,
    ) -> int:
        """Delete all relationships matching the filter criteria in one query.

        TODO: For very large datasets, consider batched deletion.

        Args:
            rel_type: Relationship type
            filters: Filter criteria on relationship properties
            start_label: Optional start node label
            end_label: Optional end node label

        Returns:
            Number of relationships deleted
        """
        def _work(tx):
            start_pattern = f"(a:{start_label})" if start_label else "(a)"
            end_pattern = f"(b:{end_label})" if end_label else "(b)"

            where_parts = []
            for key in filters.keys():
                where_parts.append(f"r.{key} = ${key}")
            where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""

            result = tx.run(
                f"""
                MATCH {start_pattern}-[r:{rel_type}]->{end_pattern}
                {where_clause}
                DELETE r
                RETURN count(r) AS deleted
                """,
                **filters,
            )
            record = result.single()
            deleted = record["deleted"] if record else 0

            if deleted > 0:
                self._pagerank_executed = False
                logger.info(f"Bulk deleted {deleted} {rel_type} relationships")
            else:
                logger.info(f"Bulk deleted 0 {rel_type} relationships")

            return deleted

        return self._execute_write(_work)

    def get_statistics(self) -> Dict[str, Any]:
        """Get graph statistics.

        Returns:
            Dictionary containing graph statistics
        """

        def _work(tx):
            node_result = tx.run("MATCH (n) RETURN count(n) AS count")
            node_count = node_result.single()["count"]

            rel_result = tx.run("MATCH ()-[r]->() RETURN count(r) AS count")
            rel_count = rel_result.single()["count"]

            label_result = tx.run("CALL db.labels()")
            labels = [record[0] for record in label_result]

            return {
                "num_nodes": node_count,
                "num_edges": rel_count,
                "num_labels": len(labels),
                "labels": labels,
                "is_directed": True,
                "backend": "neo4j",
            }

        return self._execute_read(_work)
