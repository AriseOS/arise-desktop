"""Graph storage module.

Provides abstract interface and multiple implementations for graph data storage.

Backends:
    - NetworkXGraph: In-memory implementation using NetworkX (for development)
    - SurrealDBGraphStore: Persistent implementation using SurrealDB (production)
    - Neo4jGraphStore: Production implementation using Neo4j (Cloud Backend)
    - MemoryGraph: Simple dict-based in-memory storage

SurrealDB Connection Modes:
    - file: SurrealKV file storage (persistent, for Desktop App)
    - server: WebSocket connection to remote SurrealDB server (for Cloud Backend)

Usage:
    from src.common.memory.graphstore import create_graph_store, SurrealDBConfig

    # Development (in-memory)
    store = create_graph_store("networkx")

    # Desktop App (local file storage)
    config = SurrealDBConfig(mode="file", path="~/.ami/memory.db")
    store = create_graph_store("surrealdb", config=config)

    # Cloud Backend (Neo4j)
    store = create_graph_store("neo4j", uri="bolt://localhost:7687", user="neo4j", password="xxx")

    # Cloud Backend (remote server)
    config = SurrealDBConfig(mode="server", url="ws://localhost:8000/rpc")
    store = create_graph_store("surrealdb", config=config)
"""

from src.common.memory.graphstore.graph_store import GraphStore
from src.common.memory.graphstore.memory_graph import MemoryGraph
from src.common.memory.graphstore.networkx_graph import NetworkXGraph
from src.common.memory.graphstore.surrealdb_config import SurrealDBConfig
from src.common.memory.graphstore.neo4j_config import Neo4jConfig


def create_graph_store(
    backend: str = "networkx",
    **kwargs,
) -> GraphStore:
    """Factory function to create GraphStore instance.

    Args:
        backend: Backend type - "networkx", "surrealdb", or "memory"
        **kwargs: Backend-specific configuration:
            For "networkx":
                - directed: bool (default: True)
            For "surrealdb":
                - config: SurrealDBConfig object (recommended)
                - mode: str - 'memory', 'file', 'rocksdb', 'server'
                - path: str - file path for embedded modes
                - url: str - WebSocket URL for server mode
                - namespace: str
                - database: str
                - username: str
                - password: str
                - vector_dimensions: int (default: 1024)
            For "memory":
                No additional kwargs

    Returns:
        GraphStore instance

    Raises:
        ValueError: If backend is unknown
        ImportError: If required package not installed

    Examples:
        # In-memory for development
        store = create_graph_store("networkx")

        # Desktop App (local file storage)
        config = SurrealDBConfig(mode="file", path="~/.ami/memory.db")
        store = create_graph_store("surrealdb", config=config)

        # Cloud Backend (RocksDB)
        store = create_graph_store("surrealdb", mode="rocksdb", path="/var/lib/ami/memory")

        # Remote server
        store = create_graph_store("surrealdb", mode="server", url="ws://localhost:8000/rpc")
    """
    if backend == "networkx":
        directed = kwargs.get("directed", True)
        return NetworkXGraph(directed=directed)

    elif backend == "surrealdb":
        from src.common.memory.graphstore.surrealdb_graph import (
            SurrealDBGraphStore,
        )

        config = kwargs.get("config")
        if config is None:
            # Build config from kwargs
            config = SurrealDBConfig(
                url=kwargs.get("url", "ws://localhost:8000/rpc"),
                namespace=kwargs.get("namespace", "ami"),
                database=kwargs.get("database", "memory"),
                username=kwargs.get("username", "root"),
                password=kwargs.get("password", "root"),
                vector_dimensions=kwargs.get("vector_dimensions", 1024),
            )

        return SurrealDBGraphStore(config=config)

    elif backend == "memory":
        return MemoryGraph()

    elif backend == "neo4j":
        from src.common.memory.graphstore.neo4j_graph import Neo4jGraphStore

        config = kwargs.get("config")
        if config is None:
            # Build config from kwargs - use Neo4jConfig's field names
            config = Neo4jConfig(
                uri=kwargs.get("uri", "bolt://localhost:7687"),
                user=kwargs.get("user", "neo4j"),
                password=kwargs.get("password", "password"),
                database=kwargs.get("database", "neo4j"),
                max_pool_size=kwargs.get("max_pool_size", 50),
                connection_timeout=kwargs.get("connection_timeout", 30.0),
                vector_dimensions=kwargs.get("vector_dimensions", 1024),
            )

        return Neo4jGraphStore(
            uri=config.uri,
            user=config.user,
            password=config.password,
            database=config.database,
            max_connection_pool_size=config.max_pool_size,
            connection_timeout=config.connection_timeout,
            vector_dimensions=config.vector_dimensions,
        )

    else:
        raise ValueError(
            f"Unknown backend: {backend}. "
            f"Available backends: networkx, surrealdb, neo4j, memory"
        )


__all__ = [
    "GraphStore",
    "MemoryGraph",
    "NetworkXGraph",
    "SurrealDBConfig",
    "Neo4jConfig",
    "create_graph_store",
]
