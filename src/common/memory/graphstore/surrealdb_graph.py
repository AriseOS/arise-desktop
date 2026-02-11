"""SurrealDB-based implementation of GraphStore.

This module provides a production-grade implementation of the GraphStore interface
using SurrealDB as the backend. It supports persistent storage, native complex types,
vector indexing (HNSW), and graph relationships.

Supports multiple connection modes:
- memory: In-memory storage (non-persistent, for testing)
- file: SurrealKV file storage (persistent, recommended for Desktop App)
- rocksdb: RocksDB storage (persistent, recommended for servers)
- server: WebSocket connection to remote SurrealDB server

Requirements:
    - surrealdb >= 1.0.0
    - nest-asyncio >= 1.6.0 (for async-to-sync conversion)

API Reference: docs/surrealdb-api-reference.md
"""

import asyncio
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple, Union

from src.common.memory.graphstore.graph_store import GraphStore
from src.common.memory.graphstore.surrealdb_config import SurrealDBConfig

logger = logging.getLogger(__name__)


class SurrealDBGraphStore(GraphStore):
    """SurrealDB-based graph store implementation.

    This implementation uses SurrealDB as the backend, providing:
    - Persistent storage with ACID transactions
    - Native vector indexing (HNSW) for semantic search
    - Graph relationships via RELATE syntax
    - Native support for complex types (no JSON serialization needed)
    - Multiple connection modes (memory, file, rocksdb, server)

    Thread-safety:
        Uses asyncio for all operations, wrapped in sync interface.
        Connection is reused across calls via _get_client() with lazy init.
        Automatic reconnection on connection failure (e.g., SurrealDB restart).
    """

    def __init__(
        self,
        url: Optional[str] = None,
        namespace: Optional[str] = None,
        database: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        vector_dimensions: int = 1024,
        config: Optional[SurrealDBConfig] = None,
        mode: Optional[str] = None,
        path: Optional[str] = None,
    ):
        """Initialize SurrealDB connection parameters.

        Can be initialized with individual parameters or a SurrealDBConfig object.

        Args:
            url: WebSocket URL for server mode (e.g., "ws://localhost:8000/rpc")
            namespace: SurrealDB namespace
            database: Database name
            username: Username for authentication
            password: Password for authentication
            vector_dimensions: Default embedding vector dimensions
            config: SurrealDBConfig object (overrides individual parameters)
            mode: Connection mode ('memory', 'file', 'rocksdb', 'server')
            path: File path for embedded modes (file/rocksdb)

        Examples:
            # Using config object (recommended)
            config = SurrealDBConfig(mode="file", path="~/.ami/memory.db")
            store = SurrealDBGraphStore(config=config)

            # Using individual parameters (legacy, defaults to server mode)
            store = SurrealDBGraphStore(url="ws://localhost:8000/rpc")

            # Using mode and path
            store = SurrealDBGraphStore(mode="file", path="~/.ami/memory.db")
        """
        # Use config if provided, otherwise build from individual params
        if config:
            self._config = config
        else:
            self._config = SurrealDBConfig(
                mode=mode or ("server" if url else "file"),
                path=path or str(SurrealDBConfig().path),
                url=url or "ws://localhost:8000/rpc",
                namespace=namespace or "ami",
                database=database or "memory",
                username=username or "root",
                password=password or "root",
                vector_dimensions=vector_dimensions,
            )

        self._namespace = self._config.namespace
        self._database = self._config.database
        self._username = self._config.username
        self._password = self._config.password
        self._vector_dimensions = self._config.vector_dimensions
        self._client = None
        self._connected = False

        # Dedicated background event loop for persistent connection
        self._bg_loop: Optional[asyncio.AbstractEventLoop] = None
        self._bg_thread: Optional[threading.Thread] = None

    def _ensure_bg_loop(self):
        """Ensure the background event loop thread is running.

        Creates a dedicated daemon thread with its own event loop.
        The client connection lives in this loop and is reused across all calls.
        """
        if self._bg_loop is not None and self._bg_loop.is_running():
            return

        ready = threading.Event()

        def _run_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._bg_loop = loop
            ready.set()
            loop.run_forever()

        self._bg_thread = threading.Thread(target=_run_loop, daemon=True)
        self._bg_thread.start()
        ready.wait()

    @staticmethod
    def _is_connection_error(exc: Exception) -> bool:
        """Check if an exception indicates a broken SurrealDB connection.

        Detects WebSocket disconnections, network errors, and stale connections
        so that _run() can trigger automatic reconnection.
        """
        # Check exception chain: __cause__ (explicit `from e`) and __context__ (implicit)
        current = exc
        seen = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            # websockets library exceptions
            type_name = type(current).__name__
            if type_name in (
                "ConnectionClosed",
                "ConnectionClosedError",
                "ConnectionClosedOK",
                "WebSocketException",
                "InvalidHandshake",
            ):
                return True

            # Python built-in connection errors
            if isinstance(current, (ConnectionError, OSError)):
                return True

            # SurrealDB SDK may wrap errors in generic Exception with message
            if isinstance(current, Exception):
                msg = str(current).lower()
                if any(
                    keyword in msg
                    for keyword in [
                        "connection",
                        "websocket",
                        "broken pipe",
                        "not established",
                        "closed",
                    ]
                ):
                    return True

            current = current.__cause__ or current.__context__

        return False

    def _run(self, coro_factory):
        """Run async coroutine with automatic reconnection on connection failure.

        All coroutines are dispatched to the dedicated background loop thread,
        which keeps the SurrealDB WebSocket client alive across calls.

        If the operation fails due to a connection error (e.g., SurrealDB restarted),
        the stale connection is discarded and a fresh connection is established,
        then the operation is retried once. If the retry also fails, the exception
        propagates normally (fail-fast).

        Args:
            coro_factory: Callable that returns a coroutine to execute.
                          Must be a factory (not a bare coroutine) so that
                          retries can create a fresh coroutine.

        Returns:
            Result from coroutine
        """
        self._ensure_bg_loop()

        try:
            future = asyncio.run_coroutine_threadsafe(coro_factory(), self._bg_loop)
            return future.result()
        except Exception as e:
            if not self._is_connection_error(e):
                raise

            logger.warning(f"SurrealDB connection lost, reconnecting: {e}")

            # Discard stale connection and retry, all within the bg_loop
            # to avoid race conditions with concurrent callers
            async def _reconnect_and_retry():
                await self._close_client()
                return await coro_factory()

            future = asyncio.run_coroutine_threadsafe(
                _reconnect_and_retry(), self._bg_loop
            )
            return future.result()

    async def _get_client(self):
        """Get the persistent connected client.

        Creates and connects the client on first call. Subsequent calls
        reuse the same client since all calls run on the same background loop.

        On first connection, also ensures the namespace and database exist
        (DEFINE ... IF NOT EXISTS) so callers don't need to handle this.

        Returns:
            Connected AsyncSurreal client
        """
        if self._client is not None and self._connected:
            return self._client

        from surrealdb import AsyncSurreal

        connection_string = self._config.get_connection_string()
        self._client = AsyncSurreal(connection_string)
        await self._client.connect()

        if not self._config.is_embedded():
            await self._client.signin({"username": self._username, "password": self._password})

        # Ensure namespace and database exist before USE
        await self._client.query(f"DEFINE NAMESPACE IF NOT EXISTS {self._namespace};")
        await self._client.query(f"USE NS {self._namespace};")
        await self._client.query(f"DEFINE DATABASE IF NOT EXISTS {self._database};")
        await self._client.use(self._namespace, self._database)

        self._connected = True
        logger.info(
            f"SurrealDB client connected: {connection_string}/{self._namespace}/{self._database}"
        )

        return self._client

    async def _close_client(self):
        """Close the current client connection."""
        if self._client is not None:
            try:
                await self._client.close()
            except Exception as e:
                logger.debug(f"Client close warning: {e}")
            finally:
                self._client = None
                self._connected = False

    def close(self) -> None:
        """Close the connection and release resources."""
        if self._bg_loop and self._bg_loop.is_running():
            if self._client and self._connected:
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self._close_client(), self._bg_loop
                    )
                    future.result(timeout=5.0)
                except Exception as e:
                    logger.warning(f"Error closing connection: {e}")

            self._bg_loop.call_soon_threadsafe(self._bg_loop.stop)
            if self._bg_thread:
                self._bg_thread.join(timeout=5.0)

            self._bg_loop = None
            self._bg_thread = None
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
        - Composite indexes for deduplication (domain+path_sig, state_id+content_hash)
        - Vector indexes (HNSW) for embedding search

        Args:
            schema: Optional schema definition (unused, for interface compatibility)
        """
        async def _init():
            client = await self._get_client()
            # Define entity tables
            tables = ["domain", "state", "cognitivephrase", "intentsequence", "pageinstance"]
            for table in tables:
                try:
                    await client.query(f"DEFINE TABLE {table} SCHEMALESS")
                except Exception as e:
                    if self._is_connection_error(e):
                        raise
                    logger.warning(f"Table {table} definition warning: {e}")

            # Define relationship tables (TYPE RELATION for graph edges)
            # Each relation specifies IN/OUT types for referential integrity
            rel_table_defs = [
                ("manages", "record<domain>", "record<state>"),
                ("has_sequence", "record<state>", "record<intentsequence>"),
                ("has_instance", "record<state>", "record<pageinstance>"),
                ("action", "record<state>", "record<state>"),
            ]
            rel_tables = [t[0] for t in rel_table_defs]
            for table, in_type, out_type in rel_table_defs:
                try:
                    await client.query(
                        f"DEFINE TABLE {table} SCHEMALESS TYPE RELATION"
                    )
                    # Define in/out fields with REFERENCE ON DELETE CASCADE
                    # so that deleting a node auto-deletes its connected edges
                    # (matching Neo4j DETACH DELETE behavior)
                    await client.query(
                        f"DEFINE FIELD in ON {table} TYPE {in_type} REFERENCE ON DELETE CASCADE"
                    )
                    await client.query(
                        f"DEFINE FIELD out ON {table} TYPE {out_type} REFERENCE ON DELETE CASCADE"
                    )
                except Exception as e:
                    if self._is_connection_error(e):
                        raise
                    logger.warning(f"Relation table {table} definition warning: {e}")

            # Create unique indexes on (in, out) for relationship tables
            # This prevents duplicate relationships between the same pair of nodes
            for table in rel_tables:
                try:
                    await client.query(
                        f"DEFINE INDEX idx_{table}_unique ON {table} FIELDS in, out UNIQUE"
                    )
                except Exception as e:
                    if self._is_connection_error(e):
                        raise
                    logger.warning(f"Unique index idx_{table}_unique warning: {e}")

            # Create unique indexes on id (matching Neo4j constraints)
            # Neo4j: CREATE CONSTRAINT domain_id FOR (d:Domain) REQUIRE d.id IS UNIQUE
            for table in tables:
                try:
                    await client.query(
                        f"DEFINE INDEX idx_{table}_id ON {table} FIELDS id UNIQUE"
                    )
                except Exception as e:
                    if self._is_connection_error(e):
                        raise
                    logger.warning(f"Index idx_{table}_id warning: {e}")

            # Create property indexes for common queries
            single_field_indexes = [
                ("state", "session_id"),
                ("state", "domain"),           # For domain-based queries
                ("state", "page_url"),         # For URL lookups
                ("domain", "domain_url"),      # For domain lookups by URL
                ("cognitivephrase", "session_id"),
                ("intentsequence", "state_id"),
                ("intentsequence", "content_hash"),  # For deduplication
                ("pageinstance", "url"),
                ("pageinstance", "session_id"),
            ]
            for table, field in single_field_indexes:
                try:
                    await client.query(
                        f"DEFINE INDEX idx_{table}_{field} ON {table} FIELDS {field}"
                    )
                except Exception as e:
                    if self._is_connection_error(e):
                        raise
                    logger.warning(f"Index idx_{table}_{field} warning: {e}")

            # Create composite indexes for deduplication (Xuanlin's path_sig logic)
            # These are critical for efficient State and IntentSequence deduplication
            composite_indexes = [
                # State deduplication: find_state_by_path_sig(domain, path_sig)
                ("state", "domain_path_sig", ["domain", "path_sig"]),
                # IntentSequence deduplication: find by state_id + content_hash
                ("intentsequence", "state_content", ["state_id", "content_hash"]),
            ]
            for table, index_name, fields in composite_indexes:
                try:
                    fields_str = ", ".join(fields)
                    await client.query(
                        f"DEFINE INDEX idx_{table}_{index_name} ON {table} FIELDS {fields_str}"
                    )
                    logger.info(f"Created composite index idx_{table}_{index_name}")
                except Exception as e:
                    if self._is_connection_error(e):
                        raise
                    logger.warning(f"Composite index idx_{table}_{index_name} warning: {e}")

            # Create vector indexes using HNSW (MTREE is deprecated)
            # Matching Neo4j: CREATE VECTOR INDEX state_embedding_vector FOR (s:State) ON s.embedding_vector
            vector_tables = ["state", "cognitivephrase", "intentsequence"]
            for table in vector_tables:
                try:
                    await client.query(
                        f"DEFINE INDEX idx_{table}_embedding ON {table} "
                        f"FIELDS embedding_vector HNSW DIMENSION {self._vector_dimensions} DIST COSINE"
                    )
                    logger.info(f"Created HNSW vector index for {table}")
                except Exception as e:
                    if self._is_connection_error(e):
                        raise
                    logger.warning(f"Vector index for {table} warning: {e}")

            logger.info("SurrealDB schema initialized")

        self._run(_init)

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
            RuntimeError: If database operation fails
        """
        if id_key not in properties:
            raise ValueError(f"Property '{id_key}' not found in node properties")

        async def _upsert():
            client = await self._get_client()
            table = label.lower()
            node_id = properties[id_key]
            # Use UPSERT with record ID: table:`id`
            record_id = f"{table}:`{node_id}`"
            try:
                result = await client.query(
                    f"UPSERT {record_id} CONTENT $props",
                    {"props": properties}
                )
                logger.debug(f"Upserted node {record_id}: {result}")
                return result
            except Exception as e:
                logger.error(f"Failed to upsert node {record_id}: {e}")
                raise RuntimeError(f"Failed to upsert node {record_id}: {e}") from e

        self._run(_upsert)

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

        async def _batch_upsert():
            client = await self._get_client()
            table = label.lower()
            # Batch upsert: execute all UPSERTs in a single async session
            # (avoids per-item _run() overhead with thread/event-loop creation)
            for props in properties_list:
                if id_key not in props:
                    raise ValueError(f"Property '{id_key}' not found in node properties")
                node_id = props[id_key]
                record_id = f"{table}:`{node_id}`"
                await client.query(
                    f"UPSERT {record_id} CONTENT $props",
                    {"props": props}
                )

        self._run(_batch_upsert)

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
        async def _get():
            client = await self._get_client()
            table = label.lower()
            # Use RecordID syntax for direct lookup: table:`id`
            record_id = f"{table}:`{id_value}`"
            try:
                result = await client.query(f"SELECT * FROM {record_id}")
                # New SDK returns list directly; check if non-empty
                if result and isinstance(result, list) and len(result) > 0:
                    node = result[0]
                    return self._clean_node(node)
                return None
            except Exception as e:
                if self._is_connection_error(e):
                    raise
                logger.warning(f"Get node {record_id} failed: {e}")
                return None

        return self._run(_get)

    @staticmethod
    def _is_record_id(v) -> bool:
        """Check if a value is a SurrealDB RecordID object."""
        return hasattr(v, 'table_name') and hasattr(v, 'id')

    @staticmethod
    def _record_id_to_str(v) -> str:
        """Extract the ID part from a RecordID, returning just the key (not table:key)."""
        if hasattr(v, 'id'):
            rid = v.id
            return str(rid) if not isinstance(rid, str) else rid
        return str(v)

    def _clean_node(self, node: Dict[str, Any]) -> Dict[str, Any]:
        """Remove SurrealDB internal fields and convert RecordID to string.

        Args:
            node: Raw node from SurrealDB

        Returns:
            Cleaned node dict without internal fields
        """
        if not node:
            return node

        cleaned = {}
        for k, v in node.items():
            # Skip internal SurrealDB fields (but keep 'id')
            if k.startswith("_"):
                continue

            # Convert RecordID objects to just the ID part (not "table:key")
            if self._is_record_id(v):
                cleaned[k] = self._record_id_to_str(v)
            else:
                cleaned[k] = v

        # Ensure 'id' field is a plain string (RecordID -> just the key)
        if 'id' in cleaned:
            v = cleaned['id']
            if self._is_record_id(v):
                cleaned['id'] = self._record_id_to_str(v)
            elif not isinstance(v, str):
                cleaned['id'] = str(v)

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
        async def _delete():
            client = await self._get_client()
            table = label.lower()
            record_id = f"{table}:`{id_value}`"
            # DELETE RETURN BEFORE returns the record if it existed, empty array if not
            result = await client.query(f"DELETE FROM {record_id} RETURN BEFORE")
            return bool(result and isinstance(result, list) and len(result) > 0)

        return self._run(_delete)

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

        async def _delete():
            client = await self._get_client()
            table = label.lower()
            count = 0
            for id_val in id_values:
                record_id = f"{table}:`{id_val}`"
                # DELETE RETURN BEFORE returns the record if it existed
                result = await client.query(f"DELETE FROM {record_id} RETURN BEFORE")
                if result and isinstance(result, list) and len(result) > 0:
                    count += 1
            return count

        return self._run(_delete)

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
        async def _query():
            client = await self._get_client()
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

            result = await client.query(query, params)
            logger.debug(f"Query '{query}' returned {len(result) if result else 0} results")
            # New SDK returns list directly, not [{"result": [...]}]
            if result and isinstance(result, list):
                return [self._clean_node(n) for n in result]
            return []

        return self._run(_query)

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

        Raises:
            RuntimeError: If database operation fails
        """
        async def _relate():
            client = await self._get_client()
            start_table = start_node_label.lower()
            end_table = end_node_label.lower()
            rel_table = rel_type.lower()

            try:
                start_record_id = f"{start_table}:`{start_node_id_value}`"
                end_record_id = f"{end_table}:`{end_node_id_value}`"
                props = properties or {}

                # Atomic upsert using DELETE + RELATE (two queries, single round-trip)
                # DELETE is idempotent and safe; RELATE always creates new edge
                # This avoids the non-atomic window between separate _run() calls
                delete_query = f"DELETE FROM {rel_table} WHERE in = {start_record_id} AND out = {end_record_id};"
                relate_query = f"RELATE {start_record_id}->{rel_table}->{end_record_id} CONTENT $props;"
                # Execute both statements in a single query call (SurrealDB supports multi-statement)
                combined = delete_query + relate_query
                logger.debug(f"[RELATE] Query: {combined}")
                result = await client.query(combined, {"props": props})
                logger.debug(f"[RELATE] Result: {result}")

            except Exception as e:
                logger.error(
                    f"Failed to upsert relationship {rel_type} "
                    f"({start_node_label}:{start_node_id_value} -> {end_node_label}:{end_node_id_value}): {e}"
                )
                raise RuntimeError(f"Failed to upsert relationship: {e}") from e

        self._run(_relate)

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

        async def _batch_relate():
            client = await self._get_client()
            start_table = start_node_label.lower()
            end_table = end_node_label.lower()
            rel_table = rel_type.lower()

            for rel in relationships:
                start_id = rel.get("start_id") or rel.get("source")
                end_id = rel.get("end_id") or rel.get("target")
                props = rel.get("properties", {})

                start_record_id = f"{start_table}:`{start_id}`"
                end_record_id = f"{end_table}:`{end_id}`"

                # DELETE + RELATE in single query call
                combined = (
                    f"DELETE FROM {rel_table} WHERE in = {start_record_id} AND out = {end_record_id};"
                    f"RELATE {start_record_id}->{rel_table}->{end_record_id} CONTENT $props;"
                )
                await client.query(combined, {"props": props})

        self._run(_batch_relate)

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
            True if relationship was deleted, False if not found
        """
        async def _delete():
            client = await self._get_client()
            start_table = start_node_label.lower()
            end_table = end_node_label.lower()
            rel_table = rel_type.lower()

            # Use RecordID comparison (consistent with upsert_relationship)
            # 'in' = start node, 'out' = end node
            start_record_id = f"{start_table}:`{start_node_id_value}`"
            end_record_id = f"{end_table}:`{end_node_id_value}`"
            # DELETE RETURN BEFORE returns the record if it existed (matches Neo4j count(r) > 0)
            query = f"DELETE FROM {rel_table} WHERE in = {start_record_id} AND out = {end_record_id} RETURN BEFORE"
            result = await client.query(query)
            return bool(result and isinstance(result, list) and len(result) > 0)

        return self._run(_delete)

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

        async def _batch_delete():
            client = await self._get_client()
            start_table = start_node_label.lower()
            end_table = end_node_label.lower()
            rel_table = rel_type.lower()

            count = 0
            for start_id, end_id in zip(start_node_id_values, end_node_id_values):
                start_record_id = f"{start_table}:`{start_id}`"
                end_record_id = f"{end_table}:`{end_id}`"
                # DELETE RETURN BEFORE to get accurate count (matches Neo4j count(r))
                query = f"DELETE FROM {rel_table} WHERE in = {start_record_id} AND out = {end_record_id} RETURN BEFORE"
                result = await client.query(query)
                if result and isinstance(result, list) and len(result) > 0:
                    count += 1
            return count

        return self._run(_batch_delete)

    # Known relation tables for querying when rel_type is not specified
    _RELATION_TABLES = ["manages", "has_sequence", "has_instance", "action"]

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
            start_node_label: Filter by start node label
            start_node_id_value: Filter by start node ID
            end_node_label: Filter by end node label
            end_node_id_value: Filter by end node ID
            rel_type: Filter by relationship type (if None, queries all relation tables)
            start_node_id_key: ID property key for start node
            end_node_id_key: ID property key for end node

        Returns:
            List of dicts with 'start', 'end', 'rel' keys
        """
        # When rel_type is None, query all known relation tables
        rel_tables = [rel_type.lower()] if rel_type else self._RELATION_TABLES

        async def _query():
            client = await self._get_client()
            all_relationships = []

            for rel_table in rel_tables:
                # Use FETCH in, out to get full node data instead of RecordID references
                query = f"SELECT * FROM {rel_table} FETCH in, out"

                conditions = []
                params = {}

                if start_node_id_value is not None:
                    # Use RecordID comparison: in = table:`id`
                    # (in.id returns full RecordID like "table:⟨uuid⟩", not plain string)
                    start_table = start_node_label.lower() if start_node_label else "state"
                    conditions.append(f"in = {start_table}:`{start_node_id_value}`")

                if end_node_id_value is not None:
                    # Use RecordID comparison: out = table:`id`
                    end_table = end_node_label.lower() if end_node_label else "state"
                    conditions.append(f"out = {end_table}:`{end_node_id_value}`")

                if conditions:
                    # Insert WHERE before FETCH
                    query = f"SELECT * FROM {rel_table} WHERE {' AND '.join(conditions)} FETCH in, out"

                result = await client.query(query, params)
                if not result or not isinstance(result, list):
                    continue

                current_rel_type = rel_type or rel_table
                for record in result:
                    start_props = record.get("in", {})
                    end_props = record.get("out", {})
                    # Extract relationship properties (exclude internal fields)
                    rel_props = {
                        k: v for k, v in record.items()
                        if k not in ["in", "out", "id"]
                    }
                    rel_props["_rel_type"] = current_rel_type

                    all_relationships.append({
                        "start": self._clean_node(start_props) if isinstance(start_props, dict) else {},
                        "end": self._clean_node(end_props) if isinstance(end_props, dict) else {},
                        "rel": rel_props,
                    })

            return all_relationships

        return self._run(_query)

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
        async def _create():
            client = await self._get_client()
            table = label.lower()
            name = index_name or f"idx_{table}_{property_key}"
            await client.query(
                f"DEFINE INDEX {name} ON {table} FIELDS {property_key}"
            )
            logger.info(f"Created index: {name}")

        self._run(_create)

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
        async def _create():
            client = await self._get_client()
            if isinstance(labels, str):
                labels_list = [labels]
            else:
                labels_list = labels

            # Define a simple analyzer if it doesn't exist
            try:
                await client.query(
                    "DEFINE ANALYZER simple_analyzer TOKENIZERS class FILTERS ascii, lowercase"
                )
            except Exception as e:
                if self._is_connection_error(e):
                    raise
                # Analyzer may already exist

            for label in labels_list:
                table = label.lower()
                for prop in property_keys:
                    name = index_name or f"idx_{table}_{prop}_search"
                    try:
                        await client.query(
                            f"DEFINE INDEX {name} ON {table} FIELDS {prop} "
                            f"FULLTEXT ANALYZER simple_analyzer BM25(1.2, 0.75)"
                        )
                        logger.info(f"Created fulltext index: {name}")
                    except Exception as e:
                        if self._is_connection_error(e):
                            raise
                        logger.warning(f"Fulltext index {name} warning: {e}")

        self._run(_create)

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
        async def _create():
            client = await self._get_client()
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
                await client.query(
                    f"DEFINE INDEX {name} ON {table} FIELDS {property_key} "
                    f"{' '.join(hnsw_parts)}"
                )
                logger.info(f"Created HNSW vector index: {name} (dim={vector_dimensions}, dist={dist})")
            except Exception as e:
                if self._is_connection_error(e):
                    raise
                logger.warning(f"Vector index {name} warning: {e}")

        self._run(_create)

    # All known tables for index lookup
    _ALL_TABLES = [
        "domain", "state", "cognitivephrase", "intentsequence",
        "manages", "has_sequence", "action",
    ]

    def delete_index(self, index_name: str) -> None:
        """Delete an index.

        Syntax: REMOVE INDEX name ON table

        SurrealDB requires the table name when removing an index. We infer it
        from the index name (idx_tablename_field convention) or try all known
        tables as fallback.

        Args:
            index_name: Name of the index to delete
        """
        async def _delete():
            client = await self._get_client()
            table_name = None

            # Try to extract table from index name: idx_tablename_field
            if index_name.startswith("idx_"):
                suffix = index_name[4:]
                # Match against known tables (longest match first)
                for t in sorted(self._ALL_TABLES, key=len, reverse=True):
                    if suffix.startswith(t + "_") or suffix == t:
                        table_name = t
                        break

            if not table_name:
                # Fallback: try removing from all known tables
                for t in self._ALL_TABLES:
                    try:
                        await client.query(f"REMOVE INDEX {index_name} ON {t}")
                        logger.info(f"Deleted index: {index_name} from {t}")
                        return
                    except Exception as e:
                        if self._is_connection_error(e):
                            raise
                        continue
                logger.warning(f"Cannot determine table for index {index_name}")
                return

            try:
                await client.query(f"REMOVE INDEX {index_name} ON {table_name}")
                logger.info(f"Deleted index: {index_name}")
            except Exception as e:
                if self._is_connection_error(e):
                    raise
                logger.warning(f"Delete index {index_name} warning: {e}")

        self._run(_delete)

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
        search_fields = search_fields or ["description"]

        # Known entity tables for searching when no label_constraints specified
        _ENTITY_TABLES = ["domain", "state", "cognitivephrase", "intentsequence"]

        async def _search():
            client = await self._get_client()
            search_labels = label_constraints or _ENTITY_TABLES

            results = []
            for label in search_labels:
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
                    result = await client.query(query, {"query": query_string})
                    # New SDK returns list directly
                    if result and isinstance(result, list):
                        results.extend([
                            {**self._clean_node(r), "_score": r.get("_score", 0)}
                            for r in result
                        ])
                except Exception as e:
                    if self._is_connection_error(e):
                        raise
                    logger.warning(f"Text search on {table} warning: {e}")

            # Sort by score and limit
            results.sort(key=lambda x: x.get("_score", 0), reverse=True)
            return results[:topk]

        return self._run(_search)

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
        if isinstance(query_text_or_vector, str):
            raise ValueError("query_text_or_vector must be a list of floats")

        async def _search():
            client = await self._get_client()
            table = label.lower()

            # HNSW index uses <|K,EF|> where EF is numeric (search candidate list size)
            # Higher EF = more accurate but slower; default 40 is a good balance
            ef_value = ef_search or 40

            # KNN query with cosine similarity calculation
            query = f"""
                SELECT *,
                    vector::similarity::cosine({property_key}, $vec) AS similarity
                FROM {table}
                WHERE {property_key} <|{topk},{ef_value}|> $vec
                ORDER BY similarity DESC
            """
            try:
                result = await client.query(query, {"vec": query_text_or_vector})

                # New SDK returns list directly
                if not result or not isinstance(result, list):
                    return []

                return [
                    (
                        {k: v for k, v in self._clean_node(r).items() if k != "similarity"},
                        # Normalize to [0,1] range matching Neo4j convention: (1 + cosine) / 2
                        (1.0 + float(r.get("similarity", 0.0))) / 2.0
                    )
                    for r in result
                ]
            except Exception as e:
                if self._is_connection_error(e):
                    raise
                logger.warning(f"Vector search warning: {e}")
                return []

        return self._run(_search)

    # ==================== Graph Traversal (Native SurrealDB) ====================

    def find_shortest_path(
        self,
        start_id: str,
        end_id: str,
        edge_type: str = "action",
        start_table: str = "state",
        end_table: str = "state",
        max_depth: int = 20,
    ) -> Optional[List[Dict[str, Any]]]:
        """Find shortest path between two nodes using SurrealDB native graph query.

        Uses SurrealDB's recursive path syntax with +shortest algorithm.

        Args:
            start_id: Starting node ID
            end_id: Target node ID
            edge_type: Edge table name (default: "action")
            start_table: Start node table (default: "state")
            end_table: End node table (default: "state")
            max_depth: Maximum search depth (default: 20)

        Returns:
            List of node dicts representing the shortest path, or None if no path found.

        Example:
            path = graph.find_shortest_path("home_page", "team_page")
            # Returns: [{"id": "home_page", ...}, {"id": "product_page", ...}, {"id": "team_page", ...}]
        """
        async def _find():
            client = await self._get_client()
            # SurrealDB shortest path syntax:
            # record.{..+shortest=target}(->edge->node)
            # Parentheses are required around the recursive traversal path
            query = f"""
                SELECT @.{{..{max_depth}+shortest={end_table}:`{end_id}`}}(->{edge_type}->{end_table}) AS path
                FROM {start_table}:`{start_id}`
            """
            try:
                result = await client.query(query)
                if result and isinstance(result, list) and len(result) > 0:
                    path = result[0].get("path", [])
                    if path:
                        # Include start node in path
                        start_node = await client.query(
                            f"SELECT * FROM {start_table}:`{start_id}`"
                        )
                        if start_node and len(start_node) > 0:
                            return [self._clean_node(start_node[0])] + [
                                self._clean_node(n) if isinstance(n, dict) else n
                                for n in path
                            ]
                        return [self._clean_node(n) if isinstance(n, dict) else n for n in path]
                return None
            except Exception as e:
                if self._is_connection_error(e):
                    raise
                logger.warning(f"Shortest path query failed: {e}")
                return None

        return self._run(_find)

    def traverse_graph(
        self,
        start_id: str,
        edge_type: str = "action",
        direction: str = "out",
        start_table: str = "state",
        end_table: str = "state",
        max_depth: int = 10,
        collect_unique: bool = True,
    ) -> List[Dict[str, Any]]:
        """Traverse graph from a starting node using native SurrealDB graph query.

        Args:
            start_id: Starting node ID
            edge_type: Edge table name (default: "action")
            direction: Traversal direction - "out" (->), "in" (<-), or "both" (<->)
            start_table: Start node table (default: "state")
            end_table: End node table (default: "state")
            max_depth: Maximum traversal depth (default: 10)
            collect_unique: If True, use +collect to get unique nodes (default: True)

        Returns:
            List of reachable node dicts

        Example:
            # Get all states reachable from home_page
            reachable = graph.traverse_graph("home_page", direction="out")

            # Get all states that can reach team_page
            sources = graph.traverse_graph("team_page", direction="in")
        """
        async def _traverse():
            client = await self._get_client()
            # Build direction syntax
            if direction == "out":
                arrow = f"->{edge_type}->{end_table}"
            elif direction == "in":
                arrow = f"<-{edge_type}<-{end_table}"
            else:  # both
                arrow = f"<->{edge_type}<->{end_table}"

            # Build recursion modifier
            modifier = "+collect" if collect_unique else ""

            # Parentheses are required around the recursive traversal path
            query = f"""
                SELECT @.{{1..{max_depth}{modifier}}}({arrow}) AS nodes
                FROM {start_table}:`{start_id}`
            """
            try:
                result = await client.query(query)
                if result and isinstance(result, list) and len(result) > 0:
                    nodes = result[0].get("nodes", [])
                    return [self._clean_node(n) if isinstance(n, dict) else n for n in nodes]
                return []
            except Exception as e:
                if self._is_connection_error(e):
                    raise
                logger.warning(f"Graph traversal failed: {e}")
                return []

        return self._run(_traverse)

    def get_outgoing_edges(
        self,
        node_id: str,
        edge_type: str = "action",
        node_table: str = "state",
        target_table: str = "state",
    ) -> List[Dict[str, Any]]:
        """Get all outgoing edges from a node using native graph query.

        Uses arrow syntax: SELECT ->edge->target FROM node

        Args:
            node_id: Source node ID
            edge_type: Edge table name (default: "action")
            node_table: Source node table (default: "state")
            target_table: Target node table (default: "state")

        Returns:
            List of dicts with edge properties and target node info
        """
        async def _get():
            client = await self._get_client()
            # Query both edge properties and target nodes
            query = f"""
                SELECT
                    ->{edge_type} AS edges,
                    ->{edge_type}->{target_table} AS targets
                FROM {node_table}:`{node_id}`
            """
            try:
                result = await client.query(query)
                if result and isinstance(result, list) and len(result) > 0:
                    edges = result[0].get("edges", [])
                    targets = result[0].get("targets", [])

                    # Combine edge and target info
                    combined = []
                    for i, edge in enumerate(edges):
                        edge_dict = self._clean_node(edge) if isinstance(edge, dict) else {"id": str(edge)}
                        if i < len(targets):
                            target = targets[i]
                            edge_dict["_target"] = self._clean_node(target) if isinstance(target, dict) else target
                        combined.append(edge_dict)
                    return combined
                return []
            except Exception as e:
                if self._is_connection_error(e):
                    raise
                logger.warning(f"Get outgoing edges failed: {e}")
                return []

        return self._run(_get)

    def get_incoming_edges(
        self,
        node_id: str,
        edge_type: str = "action",
        node_table: str = "state",
        source_table: str = "state",
    ) -> List[Dict[str, Any]]:
        """Get all incoming edges to a node using native graph query.

        Uses arrow syntax: SELECT <-edge<-source FROM node

        Args:
            node_id: Target node ID
            edge_type: Edge table name (default: "action")
            node_table: Target node table (default: "state")
            source_table: Source node table (default: "state")

        Returns:
            List of dicts with edge properties and source node info
        """
        async def _get():
            client = await self._get_client()
            query = f"""
                SELECT
                    <-{edge_type} AS edges,
                    <-{edge_type}<-{source_table} AS sources
                FROM {node_table}:`{node_id}`
            """
            try:
                result = await client.query(query)
                if result and isinstance(result, list) and len(result) > 0:
                    edges = result[0].get("edges", [])
                    sources = result[0].get("sources", [])

                    combined = []
                    for i, edge in enumerate(edges):
                        edge_dict = self._clean_node(edge) if isinstance(edge, dict) else {"id": str(edge)}
                        if i < len(sources):
                            source = sources[i]
                            edge_dict["_source"] = self._clean_node(source) if isinstance(source, dict) else source
                        combined.append(edge_dict)
                    return combined
                return []
            except Exception as e:
                if self._is_connection_error(e):
                    raise
                logger.warning(f"Get incoming edges failed: {e}")
                return []

        return self._run(_get)

    def get_state_with_sequences(
        self,
        state_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get a state with its related IntentSequences using graph traversal.

        Uses: SELECT *, ->has_sequence->intentsequence FROM state

        Args:
            state_id: State ID to query

        Returns:
            State dict with 'sequences' field containing related IntentSequences
        """
        async def _get():
            client = await self._get_client()
            query = f"""
                SELECT *,
                    ->has_sequence->intentsequence AS sequences
                FROM state:`{state_id}`
            """
            try:
                result = await client.query(query)
                if result and isinstance(result, list) and len(result) > 0:
                    state = self._clean_node(result[0])
                    # Clean sequences
                    if "sequences" in state and isinstance(state["sequences"], list):
                        state["sequences"] = [
                            self._clean_node(s) if isinstance(s, dict) else s
                            for s in state["sequences"]
                        ]
                    return state
                return None
            except Exception as e:
                if self._is_connection_error(e):
                    raise
                logger.warning(f"Get state with sequences failed: {e}")
                return None

        return self._run(_get)

    def get_workflow_path(
        self,
        start_id: str,
        end_id: str,
        max_depth: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """Get complete workflow path including states, actions, and sequences.

        Uses recursive graph query to get full path with all related data.

        Args:
            start_id: Starting state ID
            end_id: Target state ID
            max_depth: Maximum path depth (default: 10)

        Returns:
            Dict with 'path' (list of states) and 'edges' (list of actions)
        """
        async def _get():
            client = await self._get_client()
            # First find shortest path
            path_query = f"""
                SELECT @.{{..{max_depth}+shortest=state:`{end_id}`}}(->action->state) AS path_nodes
                FROM state:`{start_id}`
            """
            try:
                result = await client.query(path_query)
                if not result or not isinstance(result, list) or len(result) == 0:
                    return None

                path_nodes = result[0].get("path_nodes", [])
                if not path_nodes:
                    return None

                # Get start node
                start_result = await client.query(f"SELECT * FROM state:`{start_id}`")
                if not start_result or len(start_result) == 0:
                    return None

                states = [self._clean_node(start_result[0])]
                states.extend([self._clean_node(n) if isinstance(n, dict) else n for n in path_nodes])

                # Get actions between consecutive states
                actions = []
                for i in range(len(states) - 1):
                    source_id = states[i].get("id") if isinstance(states[i], dict) else states[i]
                    target_id = states[i + 1].get("id") if isinstance(states[i + 1], dict) else states[i + 1]

                    action_query = f"""
                        SELECT * FROM action
                        WHERE in = state:`{source_id}` AND out = state:`{target_id}`
                        LIMIT 1
                    """
                    action_result = await client.query(action_query)
                    if action_result and len(action_result) > 0:
                        actions.append(self._clean_node(action_result[0]))

                return {
                    "states": states,
                    "actions": actions,
                }
            except Exception as e:
                if self._is_connection_error(e):
                    raise
                logger.warning(f"Get workflow path failed: {e}")
                return None

        return self._run(_get)

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
        async def _run_script():
            client = await self._get_client()
            return await client.query(script)

        return self._run(_run_script)

    def get_all_entity_labels(self) -> List[str]:
        """Get all unique entity (node) labels in the database.

        Matches Neo4j's CALL db.labels() which returns only node labels,
        not relationship types. Edge tables are filtered out.

        Returns:
            List of entity table names (excludes relation tables)
        """
        async def _get():
            client = await self._get_client()
            result = await client.query("INFO FOR DB")
            # New SDK returns result directly (a dict with "tables" key)
            if result and isinstance(result, dict):
                tables = result.get("tables", {})
                # Filter out relation tables to match Neo4j db.labels() behavior
                return [t for t in tables.keys() if t not in self._RELATION_TABLES]
            return []

        return self._run(_get)

    def clear(self) -> None:
        """Clear all data from the graph.

        WARNING: This deletes all nodes and relationships!
        """
        async def _clear():
            client = await self._get_client()
            # Delete relation tables first to avoid unnecessary CASCADE overhead
            tables = [
                "manages", "has_sequence", "action",
                "domain", "state", "cognitivephrase", "intentsequence",
            ]
            for table in tables:
                try:
                    await client.query(f"DELETE FROM {table}")
                except Exception as e:
                    if self._is_connection_error(e):
                        raise
                    logger.warning(f"Clear {table} warning: {e}")
            logger.warning("Graph cleared")

        self._run(_clear)

    def get_statistics(self) -> Dict[str, Any]:
        """Get graph statistics.

        Returns:
            Dictionary with num_nodes, num_edges, num_labels, labels, etc.
        """
        async def _stats():
            client = await self._get_client()
            node_tables = ["domain", "state", "cognitivephrase", "intentsequence"]
            rel_tables = ["manages", "has_sequence", "action"]

            node_count = 0
            for table in node_tables:
                try:
                    result = await client.query(f"SELECT count() FROM {table} GROUP ALL")
                    # Result format: [{"count": N}] or []
                    if result and isinstance(result, list) and len(result) > 0:
                        node_count += result[0].get("count", 0)
                except Exception as e:
                    if self._is_connection_error(e):
                        raise

            edge_count = 0
            for table in rel_tables:
                try:
                    result = await client.query(f"SELECT count() FROM {table} GROUP ALL")
                    if result and isinstance(result, list) and len(result) > 0:
                        edge_count += result[0].get("count", 0)
                except Exception as e:
                    if self._is_connection_error(e):
                        raise

            # Get entity labels (exclude relation tables, matching Neo4j db.labels())
            try:
                info = await client.query("INFO FOR DB")
                if info and isinstance(info, dict):
                    all_tables = info.get("tables", {}).keys()
                    label_names = [t for t in all_tables if t not in rel_tables]
                else:
                    label_names = []
            except Exception as e:
                if self._is_connection_error(e):
                    raise
                label_names = []

            return {
                "num_nodes": node_count,
                "num_edges": edge_count,
                "num_labels": len(label_names),
                "labels": label_names,
                "is_directed": True,
                "backend": "surrealdb",
            }

        return self._run(_stats)

    # ==================== Bulk Operations ====================

    def delete_nodes_by_filter(
        self,
        label: str,
        filters: Dict[str, Any],
    ) -> int:
        """Delete all nodes matching the filter criteria.

        Args:
            label: Node label
            filters: Filter criteria (e.g., {"session_id": "xxx"})

        Returns:
            Number of nodes deleted

        Raises:
            ValueError: If filters is empty (safety measure)
        """
        if not filters:
            raise ValueError("Filters required for bulk deletion (safety)")

        async def _delete():
            client = await self._get_client()
            table = label.lower()
            conditions = []
            for i, key in enumerate(filters.keys()):
                conditions.append(f"{key} = $p{i}")

            params = {f"p{i}": v for i, v in enumerate(filters.values())}
            where_clause = " AND ".join(conditions)

            # Atomic DELETE RETURN BEFORE: returns all deleted records
            # (matches Neo4j's DETACH DELETE ... RETURN count(n))
            result = await client.query(
                f"DELETE FROM {table} WHERE {where_clause} RETURN BEFORE",
                params
            )
            count = len(result) if result and isinstance(result, list) else 0

            logger.info(f"Bulk deleted {count} {label} nodes with filters {filters}")
            return count

        return self._run(_delete)

    def delete_all_nodes_by_label(self, label: str) -> int:
        """Delete ALL nodes with the given label.

        WARNING: This deletes all nodes of this type. Use with caution.

        Args:
            label: Node label to delete

        Returns:
            Number of nodes deleted
        """
        async def _delete():
            client = await self._get_client()
            table = label.lower()

            # Atomic DELETE RETURN BEFORE: returns all deleted records
            # (matches Neo4j's DETACH DELETE ... RETURN count(n))
            result = await client.query(f"DELETE FROM {table} RETURN BEFORE")
            count = len(result) if result and isinstance(result, list) else 0

            logger.info(f"Deleted ALL {count} {label} nodes")
            return count

        return self._run(_delete)
