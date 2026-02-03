"""SurrealDB-based implementation of GraphStore.

This module provides a production-grade implementation of the GraphStore interface
using SurrealDB as the backend. It supports persistent storage, native complex types,
vector indexing (HNSW), and graph relationships.

Requirements:
    - surrealdb >= 1.0.0
    - nest-asyncio >= 1.6.0 (for async-to-sync conversion)

API Reference: docs/surrealdb-api-reference.md
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from src.cloud_backend.memgraph.graphstore.graph_store import GraphStore

logger = logging.getLogger(__name__)


class SurrealDBGraphStore(GraphStore):
    """SurrealDB-based graph store implementation.

    This implementation uses SurrealDB as the backend, providing:
    - Persistent storage with ACID transactions
    - Native vector indexing (HNSW) for semantic search
    - Graph relationships via RELATE syntax
    - Native support for complex types (no JSON serialization needed)

    Thread-safety:
        Uses asyncio for all operations, wrapped in sync interface.
        Connection is reused across calls via _ensure_connected().
    """

    def __init__(
        self,
        url: str,
        namespace: str,
        database: str,
        username: str,
        password: str,
        vector_dimensions: int = 1024,
    ):
        """Initialize SurrealDB connection parameters.

        Args:
            url: WebSocket URL (e.g., "ws://localhost:8000/rpc")
            namespace: SurrealDB namespace
            database: Database name
            username: Username for authentication
            password: Password for authentication
            vector_dimensions: Default embedding vector dimensions
        """
        self._url = url
        self._namespace = namespace
        self._database = database
        self._username = username
        self._password = password
        self._vector_dimensions = vector_dimensions
        self._client = None
        self._connected = False
        self._loop = None

    def _get_or_create_loop(self):
        """Get the existing event loop or create a new one.

        Returns:
            Event loop for async operations
        """
        try:
            loop = asyncio.get_running_loop()
            # If we're in a running loop, apply nest_asyncio
            import nest_asyncio
            nest_asyncio.apply()
            return loop
        except RuntimeError:
            # No running loop, create a new one
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
            return self._loop

    def _run(self, coro):
        """Run async coroutine in sync context.

        Handles both cases:
        1. No running event loop: creates and runs a new loop
        2. Running event loop: uses nest_asyncio for nested execution

        Args:
            coro: Coroutine to execute

        Returns:
            Result from coroutine
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Running inside an existing event loop (e.g., FastAPI)
            import nest_asyncio
            nest_asyncio.apply()
            # Use run_until_complete on the existing loop
            return loop.run_until_complete(coro)
        else:
            # No running loop, use asyncio.run()
            return asyncio.run(coro)

    def _ensure_connected(self):
        """Ensure connection is established."""
        if not self._connected:
            self._run(self._connect())

    async def _connect(self):
        """Connect to SurrealDB."""
        try:
            from surrealdb import Surreal
        except ImportError:
            raise ImportError(
                "surrealdb package is required. Install with: pip install surrealdb"
            )

        self._client = Surreal(self._url)
        await self._client.connect()
        await self._client.signin({"user": self._username, "pass": self._password})
        await self._client.use(self._namespace, self._database)
        self._connected = True
        logger.info(
            f"Connected to SurrealDB: {self._url}/{self._namespace}/{self._database}"
        )

    def close(self) -> None:
        """Close the connection and release resources."""
        if self._client and self._connected:
            try:
                self._run(self._client.close())
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
            self._connected = False
            self._client = None
            logger.info("SurrealDB connection closed")

    def initialize_schema(self, schema: Any = None) -> None:
        """Initialize database schema with tables and indexes.

        Creates:
        - Entity tables: domain, state, cognitivephrase, intentsequence
        - Relationship tables: manages, has_sequence, action
        - Unique indexes on id field
        - Property indexes for common queries
        - Vector indexes (HNSW) for embedding search

        Args:
            schema: Optional schema definition (unused, for interface compatibility)
        """
        self._ensure_connected()

        async def _init():
            # Define entity tables
            tables = ["domain", "state", "cognitivephrase", "intentsequence"]
            for table in tables:
                try:
                    await self._client.query(f"DEFINE TABLE {table} SCHEMALESS")
                except Exception as e:
                    logger.warning(f"Table {table} definition warning: {e}")

            # Define relationship tables (TYPE RELATION for graph edges)
            rel_tables = ["manages", "has_sequence", "action"]
            for table in rel_tables:
                try:
                    await self._client.query(
                        f"DEFINE TABLE {table} SCHEMALESS TYPE RELATION"
                    )
                except Exception as e:
                    logger.warning(f"Relation table {table} definition warning: {e}")

            # Create unique indexes on (in, out) for relationship tables
            # This prevents duplicate relationships between the same pair of nodes
            for table in rel_tables:
                try:
                    await self._client.query(
                        f"DEFINE INDEX idx_{table}_unique ON {table} FIELDS in, out UNIQUE"
                    )
                except Exception as e:
                    logger.warning(f"Unique index idx_{table}_unique warning: {e}")

            # Create unique indexes on id
            for table in tables:
                try:
                    await self._client.query(
                        f"DEFINE INDEX idx_{table}_id ON {table} FIELDS id UNIQUE"
                    )
                except Exception as e:
                    logger.warning(f"Index idx_{table}_id warning: {e}")

            # Create property indexes for common queries
            indexes = [
                ("state", "user_id"),
                ("state", "session_id"),
                ("domain", "user_id"),
                ("cognitivephrase", "user_id"),
                ("intentsequence", "state_id"),
            ]
            for table, field in indexes:
                try:
                    await self._client.query(
                        f"DEFINE INDEX idx_{table}_{field} ON {table} FIELDS {field}"
                    )
                except Exception as e:
                    logger.warning(f"Index idx_{table}_{field} warning: {e}")

            # Create vector indexes using HNSW (MTREE is deprecated)
            # Syntax: DEFINE INDEX name ON table FIELDS field HNSW DIMENSION dim DIST metric
            vector_tables = ["state", "cognitivephrase", "intentsequence"]
            for table in vector_tables:
                try:
                    await self._client.query(
                        f"DEFINE INDEX idx_{table}_embedding ON {table} "
                        f"FIELDS embedding_vector HNSW DIMENSION {self._vector_dimensions} DIST COSINE"
                    )
                    logger.info(f"Created HNSW vector index for {table}")
                except Exception as e:
                    logger.warning(f"Vector index for {table} warning: {e}")

            logger.info("SurrealDB schema initialized")

        self._run(_init())

    # ==================== Node Operations ====================

    def upsert_node(
        self,
        label: str,
        properties: Dict[str, Any],
        id_key: str = "id",
        extra_labels: Tuple[str, ...] = ("Entity",),
    ) -> None:
        """Insert or update a single node.

        Uses SurrealDB UPSERT with record ID syntax: table:`id`

        Args:
            label: Node label (table name)
            properties: Node properties including the ID
            id_key: Property key for unique identifier (default: 'id')
            extra_labels: Additional labels (unused in SurrealDB)

        Raises:
            ValueError: If id_key not in properties
        """
        self._ensure_connected()

        if id_key not in properties:
            raise ValueError(f"Property '{id_key}' not found in node properties")

        async def _upsert():
            table = label.lower()
            node_id = properties[id_key]
            # Use UPSERT with record ID: table:`id`
            record_id = f"{table}:`{node_id}`"
            await self._client.query(
                f"UPSERT {record_id} CONTENT $props",
                {"props": properties}
            )

        self._run(_upsert())

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

        for props in properties_list:
            self.upsert_node(label, props, id_key, extra_labels)

    def batch_preprocess_node_properties(
        self,
        node_batch: List[Tuple[str, Dict[str, Any]]],
        extra_labels: Tuple[str, ...] = ("Entity",),
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Preprocess node properties before batch insertion.

        SurrealDB natively supports complex types (lists, dicts, etc.),
        so no preprocessing is needed.

        Args:
            node_batch: List of (label, properties) tuples
            extra_labels: Additional labels (unused)

        Returns:
            Unmodified input
        """
        return node_batch

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
        self._ensure_connected()

        async def _get():
            table = label.lower()
            result = await self._client.query(
                f"SELECT * FROM {table} WHERE {id_key} = $id LIMIT 1",
                {"id": id_value}
            )
            if result and result[0]["result"]:
                node = result[0]["result"][0]
                return self._clean_node(node)
            return None

        return self._run(_get())

    def _clean_node(self, node: Dict[str, Any]) -> Dict[str, Any]:
        """Remove SurrealDB internal fields from node.

        Args:
            node: Raw node from SurrealDB

        Returns:
            Cleaned node dict without internal fields
        """
        if not node:
            return node
        # Remove internal SurrealDB fields (those starting with _)
        cleaned = {k: v for k, v in node.items() if not k.startswith("_")}
        return cleaned

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
            True if node was deleted
        """
        self._ensure_connected()

        async def _delete():
            table = label.lower()
            await self._client.query(
                f"DELETE FROM {table} WHERE {id_key} = $id",
                {"id": id_value}
            )
            return True

        return self._run(_delete())

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

        self._ensure_connected()

        async def _delete():
            table = label.lower()
            await self._client.query(
                f"DELETE FROM {table} WHERE {id_key} IN $ids",
                {"ids": id_values}
            )
            return len(id_values)

        return self._run(_delete())

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
        self._ensure_connected()

        async def _query():
            table = label.lower()
            query = f"SELECT * FROM {table}"

            params = {}
            if filters:
                conditions = []
                for i, (key, value) in enumerate(filters.items()):
                    param = f"p{i}"
                    conditions.append(f"{key} = ${param}")
                    params[param] = value
                query += " WHERE " + " AND ".join(conditions)

            if limit:
                query += f" LIMIT {limit}"

            result = await self._client.query(query, params)
            if result and result[0]["result"]:
                return [self._clean_node(n) for n in result[0]["result"]]
            return []

        return self._run(_query())

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
        """Insert or update a relationship using RELATE syntax.

        SurrealDB RELATE syntax: RELATE @from -> @table -> @to

        Args:
            start_node_label: Label of the start node
            start_node_id_value: ID value of the start node
            end_node_label: Label of the end node
            end_node_id_value: ID value of the end node
            rel_type: Relationship type (edge table name)
            properties: Relationship properties
            upsert_nodes: Whether to create nodes if not exist (unused)
            start_node_id_key: ID property key for start node
            end_node_id_key: ID property key for end node
        """
        self._ensure_connected()

        async def _relate():
            start_table = start_node_label.lower()
            end_table = end_node_label.lower()
            rel_table = rel_type.lower()

            # Implement upsert semantics:
            # 1. First, delete any existing relationship between these two nodes
            # 2. Then create the new relationship
            # This is needed because SurrealDB doesn't support UPSERT on relation tables
            # and RELATE always creates a new edge
            query = f"""
                LET $start = (SELECT * FROM {start_table} WHERE {start_node_id_key} = $start_id)[0];
                LET $end = (SELECT * FROM {end_table} WHERE {end_node_id_key} = $end_id)[0];
                IF $start AND $end THEN
                    -- Delete existing relationship if any
                    DELETE FROM {rel_table} WHERE in = $start.id AND out = $end.id;
                    -- Create new relationship
                    RELATE $start->{rel_table}->$end CONTENT $props;
                END;
            """
            await self._client.query(query, {
                "start_id": start_node_id_value,
                "end_id": end_node_id_value,
                "props": properties or {},
            })

        self._run(_relate())

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
            relationships: List of dicts with start_id/source, end_id/target, properties
            upsert_nodes: Whether to create nodes if not exist
            start_node_id_key: ID property key for start nodes
            end_node_id_key: ID property key for end nodes
        """
        if not relationships:
            return

        for rel in relationships:
            start_id = rel.get("start_id") or rel.get("source")
            end_id = rel.get("end_id") or rel.get("target")
            props = rel.get("properties", {})

            self.upsert_relationship(
                start_node_label,
                start_id,
                end_node_label,
                end_id,
                rel_type,
                props,
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
    ) -> bool:
        """Delete a relationship.

        In SurrealDB, relationships are stored in edge tables with 'in' and 'out' fields.
        We query by the id properties of the connected nodes.

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
        self._ensure_connected()

        async def _delete():
            rel_table = rel_type.lower()

            # Delete by querying the in/out node properties
            # 'in' points to start node, 'out' points to end node
            query = f"""
                DELETE FROM {rel_table}
                WHERE in.{start_node_id_key} = $start_id
                AND out.{end_node_id_key} = $end_id
            """
            await self._client.query(query, {
                "start_id": start_node_id_value,
                "end_id": end_node_id_value,
            })
            return True

        return self._run(_delete())

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

        count = 0
        for start_id, end_id in zip(start_node_id_values, end_node_id_values):
            if self.delete_relationship(
                start_node_label,
                start_id,
                end_node_label,
                end_id,
                rel_type,
                start_node_id_key,
                end_node_id_key,
            ):
                count += 1

        return count

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

        In SurrealDB, edge tables have 'in' (start) and 'out' (end) fields
        that reference the connected nodes.

        Args:
            start_node_label: Filter by start node label (unused, inferred from rel_type)
            start_node_id_value: Filter by start node ID
            end_node_label: Filter by end node label (unused, inferred from rel_type)
            end_node_id_value: Filter by end node ID
            rel_type: Filter by relationship type (required)
            start_node_id_key: ID property key for start node
            end_node_id_key: ID property key for end node

        Returns:
            List of dicts with 'start', 'end', 'rel' keys
        """
        self._ensure_connected()

        async def _query():
            if not rel_type:
                return []

            rel_table = rel_type.lower()
            # Query edge table, selecting in/out as start/end nodes
            query = f"SELECT *, in AS start_node, out AS end_node FROM {rel_table}"

            conditions = []
            params = {}

            if start_node_id_value is not None:
                conditions.append(f"in.{start_node_id_key} = $start_id")
                params["start_id"] = start_node_id_value

            if end_node_id_value is not None:
                conditions.append(f"out.{end_node_id_key} = $end_id")
                params["end_id"] = end_node_id_value

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            result = await self._client.query(query, params)
            if not result or not result[0]["result"]:
                return []

            relationships = []
            for record in result[0]["result"]:
                start_props = record.get("start_node", {})
                end_props = record.get("end_node", {})
                # Extract relationship properties (exclude internal fields)
                rel_props = {
                    k: v for k, v in record.items()
                    if k not in ["start_node", "end_node", "in", "out", "id"]
                }
                rel_props["_rel_type"] = rel_type

                relationships.append({
                    "start": self._clean_node(start_props) if isinstance(start_props, dict) else {},
                    "end": self._clean_node(end_props) if isinstance(end_props, dict) else {},
                    "rel": rel_props,
                })

            return relationships

        return self._run(_query())

    # ==================== Index Operations ====================

    def create_index(
        self,
        label: str,
        property_key: str,
        index_name: Optional[str] = None,
    ) -> None:
        """Create a property index.

        Syntax: DEFINE INDEX name ON table FIELDS field

        Args:
            label: Node label (table name)
            property_key: Property to index
            index_name: Optional index name
        """
        self._ensure_connected()

        async def _create():
            table = label.lower()
            name = index_name or f"idx_{table}_{property_key}"
            await self._client.query(
                f"DEFINE INDEX {name} ON {table} FIELDS {property_key}"
            )
            logger.info(f"Created index: {name}")

        self._run(_create())

    def create_text_index(
        self,
        labels: Union[str, List[str]],
        property_keys: List[str],
        index_name: Optional[str] = None,
    ) -> None:
        """Create a fulltext search index with BM25 ranking.

        Syntax: DEFINE INDEX name ON table FIELDS field FULLTEXT ANALYZER analyzer BM25

        Note: SurrealDB requires an analyzer to be defined first. We use a simple
        ascii analyzer for basic text search.

        Args:
            labels: Node label(s)
            property_keys: List of properties to index
            index_name: Optional index name
        """
        self._ensure_connected()

        async def _create():
            if isinstance(labels, str):
                labels_list = [labels]
            else:
                labels_list = labels

            # Define a simple analyzer if it doesn't exist
            try:
                await self._client.query(
                    "DEFINE ANALYZER simple_analyzer TOKENIZERS class FILTERS ascii, lowercase"
                )
            except Exception:
                pass  # Analyzer may already exist

            for label in labels_list:
                table = label.lower()
                for prop in property_keys:
                    name = index_name or f"idx_{table}_{prop}_search"
                    try:
                        await self._client.query(
                            f"DEFINE INDEX {name} ON {table} FIELDS {prop} "
                            f"FULLTEXT ANALYZER simple_analyzer BM25(1.2, 0.75)"
                        )
                        logger.info(f"Created fulltext index: {name}")
                    except Exception as e:
                        logger.warning(f"Fulltext index {name} warning: {e}")

        self._run(_create())

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
        """Create a vector index using HNSW algorithm.

        Syntax: DEFINE INDEX name ON table FIELDS field HNSW DIMENSION dim DIST metric [EFC efc] [M m]

        Note: MTREE is deprecated in recent SurrealDB versions, use HNSW instead.

        Args:
            label: Node label
            property_key: Property containing vector embeddings
            index_name: Optional index name
            vector_dimensions: Vector dimension size
            metric_type: Distance metric ('cosine', 'euclidean', 'manhattan')
            hnsw_m: HNSW M parameter (max connections per node, default: 12)
            hnsw_ef_construction: HNSW EFC parameter (construction exploration, default: 150)
        """
        self._ensure_connected()

        async def _create():
            table = label.lower()
            name = index_name or f"idx_{table}_{property_key}_vec"

            # Map metric type
            dist_map = {
                "cosine": "COSINE",
                "euclidean": "EUCLIDEAN",
                "manhattan": "MANHATTAN",
            }
            dist = dist_map.get(metric_type.lower(), "COSINE")

            # Build HNSW clause
            hnsw_parts = [f"HNSW DIMENSION {vector_dimensions} DIST {dist}"]
            if hnsw_ef_construction:
                hnsw_parts.append(f"EFC {hnsw_ef_construction}")
            if hnsw_m:
                hnsw_parts.append(f"M {hnsw_m}")

            try:
                await self._client.query(
                    f"DEFINE INDEX {name} ON {table} FIELDS {property_key} "
                    f"{' '.join(hnsw_parts)}"
                )
                logger.info(f"Created HNSW vector index: {name} (dim={vector_dimensions}, dist={dist})")
            except Exception as e:
                logger.warning(f"Vector index {name} warning: {e}")

        self._run(_create())

    def delete_index(self, index_name: str, table: Optional[str] = None) -> None:
        """Delete an index.

        Syntax: REMOVE INDEX name ON table

        Args:
            index_name: Name of the index to delete
            table: Table name (extracted from index_name if not provided)
        """
        self._ensure_connected()

        async def _delete():
            # Try to extract table from index name if not provided
            # Index names are typically: idx_tablename_field
            if table:
                table_name = table.lower()
            elif index_name.startswith("idx_"):
                parts = index_name[4:].split("_")
                table_name = parts[0] if parts else None
            else:
                table_name = None

            if not table_name:
                logger.warning(f"Cannot determine table for index {index_name}")
                return

            try:
                await self._client.query(f"REMOVE INDEX {index_name} ON {table_name}")
                logger.info(f"Deleted index: {index_name}")
            except Exception as e:
                logger.warning(f"Delete index {index_name} warning: {e}")

        self._run(_delete())

    # ==================== Search Operations ====================

    def text_search(
        self,
        query_string: str,
        label_constraints: Optional[List[str]] = None,
        topk: int = 10,
        index_name: Optional[str] = None,
        search_fields: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute fulltext search with BM25 ranking.

        Uses the @@ operator with search::score() for relevance scoring.
        Syntax: SELECT *, search::score(1) AS score FROM table WHERE field @1@ $query

        Args:
            query_string: Search query string
            label_constraints: Tables to search
            topk: Maximum results per table
            index_name: Index to search (unused, SurrealDB auto-selects)
            search_fields: Fields to search (default: ["description"])

        Returns:
            List of matching node dictionaries with _score field
        """
        self._ensure_connected()

        search_fields = search_fields or ["description"]

        async def _search():
            if not label_constraints:
                return []

            results = []
            for label in label_constraints:
                table = label.lower()

                # Build search conditions for each field
                # Each field needs a unique number for score reference
                conditions = []
                score_parts = []
                for i, field in enumerate(search_fields):
                    conditions.append(f"{field} @{i}@ $query")
                    score_parts.append(f"search::score({i})")

                # Calculate total score
                score_expr = " + ".join(score_parts) if len(score_parts) > 1 else score_parts[0]

                query = f"""
                    SELECT *, ({score_expr}) AS _score
                    FROM {table}
                    WHERE {' OR '.join(conditions)}
                    ORDER BY _score DESC
                    LIMIT {topk}
                """
                try:
                    result = await self._client.query(query, {"query": query_string})
                    if result and result[0]["result"]:
                        results.extend([
                            {**self._clean_node(r), "_score": r.get("_score", 0)}
                            for r in result[0]["result"]
                        ])
                except Exception as e:
                    logger.warning(f"Text search on {table} warning: {e}")

            # Sort by score and limit
            results.sort(key=lambda x: x.get("_score", 0), reverse=True)
            return results[:topk]

        return self._run(_search())

    def vector_search(
        self,
        label: str,
        property_key: str,
        query_text_or_vector: Union[str, List[float]],
        topk: int = 10,
        index_name: Optional[str] = None,
        ef_search: Optional[int] = None,
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Execute vector similarity search using KNN operator.

        Uses the <|k, metric|> operator for exact KNN or <|k, ef|> for HNSW approximate search.
        Syntax: SELECT *, vector::distance::knn() AS dist FROM table WHERE field <|k, COSINE|> $vec

        Args:
            label: Node label
            property_key: Property containing embeddings
            query_text_or_vector: Query vector (must be a list of floats)
            topk: Number of results to return
            index_name: Optional index name (unused, auto-selected)
            ef_search: HNSW search parameter (use number instead of metric name for ANN)

        Returns:
            List of (node_properties, similarity_score) tuples
        """
        self._ensure_connected()

        if isinstance(query_text_or_vector, str):
            raise ValueError("query_text_or_vector must be a list of floats")

        async def _search():
            table = label.lower()

            # Use either metric name for exact KNN or number for HNSW ANN
            if ef_search:
                knn_param = str(ef_search)  # HNSW approximate search
            else:
                knn_param = "COSINE"  # Exact KNN with cosine distance

            # KNN query with similarity calculation
            # Note: vector::distance::knn() returns distance, we compute similarity separately
            query = f"""
                SELECT *,
                    vector::similarity::cosine({property_key}, $vec) AS similarity
                FROM {table}
                WHERE {property_key} <|{topk},{knn_param}|> $vec
                ORDER BY similarity DESC
            """
            try:
                result = await self._client.query(query, {"vec": query_text_or_vector})

                if not result or not result[0]["result"]:
                    return []

                return [
                    (
                        {k: v for k, v in self._clean_node(r).items() if k != "similarity"},
                        float(r.get("similarity", 0.0))
                    )
                    for r in result[0]["result"]
                ]
            except Exception as e:
                logger.warning(f"Vector search warning: {e}")
                return []

        return self._run(_search())

    # ==================== Graph Algorithms ====================

    def execute_pagerank(
        self,
        iterations: int = 20,
        damping_factor: float = 0.85,
    ) -> None:
        """Execute PageRank algorithm.

        Note: PageRank is not natively supported in SurrealDB.
        This is a no-op implementation for interface compatibility.

        Args:
            iterations: Number of iterations (unused)
            damping_factor: Damping factor (unused)
        """
        logger.info("PageRank not supported in SurrealDB - skipping")

    def get_pagerank_scores(
        self,
        start_nodes: Optional[List[str]] = None,
        target_type: Optional[str] = None,
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Get PageRank scores.

        Note: PageRank is not natively supported in SurrealDB.
        Returns empty list for interface compatibility.

        Args:
            start_nodes: Starting nodes (unused)
            target_type: Target node type (unused)

        Returns:
            Empty list
        """
        return []

    # ==================== Utility Methods ====================

    def run_script(self, script: str) -> Any:
        """Execute a SurrealQL script.

        Args:
            script: SurrealQL query to execute

        Returns:
            Query results
        """
        self._ensure_connected()

        async def _run_script():
            return await self._client.query(script)

        return self._run(_run_script())

    def get_all_entity_labels(self) -> List[str]:
        """Get all unique table names in the database.

        Uses INFO FOR DB to get database metadata.

        Returns:
            List of table names
        """
        self._ensure_connected()

        async def _get():
            result = await self._client.query("INFO FOR DB")
            if result and result[0]["result"]:
                tables = result[0]["result"].get("tables", {})
                return list(tables.keys())
            return []

        return self._run(_get())

    def clear(self) -> None:
        """Clear all data from the graph.

        WARNING: This deletes all nodes and relationships!
        """
        self._ensure_connected()

        async def _clear():
            tables = [
                "domain", "state", "cognitivephrase", "intentsequence",
                "manages", "has_sequence", "action"
            ]
            for table in tables:
                try:
                    await self._client.query(f"DELETE FROM {table}")
                except Exception as e:
                    logger.warning(f"Clear {table} warning: {e}")
            logger.warning("Graph cleared")

        self._run(_clear())

    def get_statistics(self) -> Dict[str, Any]:
        """Get graph statistics.

        Returns:
            Dictionary with num_nodes, num_edges, num_labels, labels, etc.
        """
        self._ensure_connected()

        async def _stats():
            node_tables = ["domain", "state", "cognitivephrase", "intentsequence"]
            rel_tables = ["manages", "has_sequence", "action"]

            node_count = 0
            for table in node_tables:
                try:
                    result = await self._client.query(f"SELECT count() FROM {table} GROUP ALL")
                    if result and result[0]["result"]:
                        node_count += result[0]["result"][0].get("count", 0)
                except Exception:
                    pass

            edge_count = 0
            for table in rel_tables:
                try:
                    result = await self._client.query(f"SELECT count() FROM {table} GROUP ALL")
                    if result and result[0]["result"]:
                        edge_count += result[0]["result"][0].get("count", 0)
                except Exception:
                    pass

            labels = await self._client.query("INFO FOR DB")
            label_names = []
            if labels and labels[0]["result"]:
                label_names = list(labels[0]["result"].get("tables", {}).keys())

            return {
                "num_nodes": node_count,
                "num_edges": edge_count,
                "num_labels": len(label_names),
                "labels": label_names,
                "is_directed": True,
                "backend": "surrealdb",
            }

        return self._run(_stats())

    # ==================== Bulk Operations ====================

    def delete_nodes_by_filter(
        self,
        label: str,
        filters: Dict[str, Any],
    ) -> int:
        """Delete all nodes matching the filter criteria.

        Args:
            label: Node label
            filters: Filter criteria (e.g., {"user_id": "xxx"})

        Returns:
            Number of nodes deleted

        Raises:
            ValueError: If filters is empty (safety measure)
        """
        if not filters:
            raise ValueError("Filters required for bulk deletion (safety)")

        self._ensure_connected()

        async def _delete():
            table = label.lower()
            conditions = []
            for i, key in enumerate(filters.keys()):
                conditions.append(f"{key} = $p{i}")

            params = {f"p{i}": v for i, v in enumerate(filters.values())}
            where_clause = " AND ".join(conditions)

            # Get count first
            count_result = await self._client.query(
                f"SELECT count() FROM {table} WHERE {where_clause} GROUP ALL",
                params
            )
            count = 0
            if count_result and count_result[0]["result"]:
                count = count_result[0]["result"][0].get("count", 0)

            # Delete
            await self._client.query(
                f"DELETE FROM {table} WHERE {where_clause}",
                params
            )

            logger.info(f"Bulk deleted {count} {label} nodes with filters {filters}")
            return count

        return self._run(_delete())

    def delete_all_nodes_by_label(self, label: str) -> int:
        """Delete ALL nodes with the given label.

        WARNING: This deletes all nodes of this type. Use with caution.

        Args:
            label: Node label to delete

        Returns:
            Number of nodes deleted
        """
        self._ensure_connected()

        async def _delete():
            table = label.lower()

            # Get count first
            count_result = await self._client.query(
                f"SELECT count() FROM {table} GROUP ALL"
            )
            count = 0
            if count_result and count_result[0]["result"]:
                count = count_result[0]["result"][0].get("count", 0)

            # Delete all
            await self._client.query(f"DELETE FROM {table}")

            logger.info(f"Deleted ALL {count} {label} nodes")
            return count

        return self._run(_delete())
