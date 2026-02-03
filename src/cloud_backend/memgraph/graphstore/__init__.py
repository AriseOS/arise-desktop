"""Graph storage module.

Provides abstract interface and multiple implementations for graph data storage.

Backends:
    - NetworkXGraph: In-memory implementation using NetworkX (default, for development)
    - Neo4jGraphStore: Persistent implementation using Neo4j (production option 1)
    - SurrealDBGraphStore: Persistent implementation using SurrealDB (production option 2)
    - MemoryGraph: Simple dict-based in-memory storage

Usage:
    # Using factory function
    from src.cloud_backend.memgraph.graphstore import create_graph_store

    # Development (in-memory)
    store = create_graph_store("networkx")

    # Production (Neo4j)
    store = create_graph_store("neo4j")

    # Production (SurrealDB)
    store = create_graph_store("surrealdb")
"""

from src.cloud_backend.memgraph.graphstore.graph_store import GraphStore
from src.cloud_backend.memgraph.graphstore.memory_graph import MemoryGraph
from src.cloud_backend.memgraph.graphstore.networkx_graph import NetworkXGraph


def create_graph_store(
    backend: str = "networkx",
    **kwargs,
) -> GraphStore:
    """Factory function to create GraphStore instance.

    Args:
        backend: Backend type - "networkx", "neo4j", "surrealdb", or "memory"
        **kwargs: Backend-specific configuration:
            For "networkx":
                - directed: bool (default: True)
            For "neo4j":
                - uri: str (default: from NEO4J_URI env var)
                - user: str (default: from NEO4J_USER env var)
                - password: str (default: from NEO4J_PASSWORD env var)
                - database: str (default: from NEO4J_DATABASE env var)
            For "surrealdb":
                - url: str (default: from SURREALDB_URL env var)
                - namespace: str (default: from SURREALDB_NAMESPACE env var)
                - database: str (default: from SURREALDB_DATABASE env var)
                - username: str (default: from SURREALDB_USER env var)
                - password: str (default: from SURREALDB_PASSWORD env var)
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

        # Neo4j
        store = create_graph_store("neo4j", uri="neo4j://localhost:7687")

        # SurrealDB
        store = create_graph_store("surrealdb", url="ws://localhost:8000/rpc")
    """
    if backend == "networkx":
        directed = kwargs.get("directed", True)
        return NetworkXGraph(directed=directed)

    elif backend == "neo4j":
        from src.cloud_backend.memgraph.graphstore.neo4j_graph import (
            Neo4jGraphStore,
        )
        from src.cloud_backend.memgraph.graphstore.neo4j_config import (
            Neo4jConfig,
        )

        config = kwargs.get("config")
        if config is None:
            defaults = Neo4jConfig()
            config = Neo4jConfig(
                uri=kwargs.get("uri", defaults.uri),
                user=kwargs.get("user", defaults.user),
                password=kwargs.get("password", defaults.password),
                database=kwargs.get("database", defaults.database),
            )

        return Neo4jGraphStore(
            uri=config.uri,
            user=config.user,
            password=config.password,
            database=config.database,
        )

    elif backend == "surrealdb":
        from src.cloud_backend.memgraph.graphstore.surrealdb_graph import (
            SurrealDBGraphStore,
        )
        from src.cloud_backend.memgraph.graphstore.surrealdb_config import (
            SurrealDBConfig,
        )

        config = kwargs.get("config")
        if config is None:
            defaults = SurrealDBConfig()
            config = SurrealDBConfig(
                url=kwargs.get("url", defaults.url),
                namespace=kwargs.get("namespace", defaults.namespace),
                database=kwargs.get("database", defaults.database),
                username=kwargs.get("username", defaults.username),
                password=kwargs.get("password", defaults.password),
                vector_dimensions=kwargs.get(
                    "vector_dimensions", defaults.vector_dimensions
                ),
            )

        return SurrealDBGraphStore(
            url=config.url,
            namespace=config.namespace,
            database=config.database,
            username=config.username,
            password=config.password,
            vector_dimensions=config.vector_dimensions,
        )

    elif backend == "memory":
        return MemoryGraph()

    else:
        raise ValueError(
            f"Unknown backend: {backend}. "
            f"Available backends: networkx, neo4j, surrealdb, memory"
        )


__all__ = [
    "GraphStore",
    "MemoryGraph",
    "NetworkXGraph",
    "create_graph_store",
]
