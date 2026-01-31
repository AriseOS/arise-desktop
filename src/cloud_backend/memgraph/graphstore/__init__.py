"""Graph storage module.

Provides abstract interface and multiple implementations for graph data storage.

Backends:
    - NetworkXGraph: In-memory implementation using NetworkX (default, for development)
    - Neo4jGraphStore: Persistent implementation using Neo4j (for production)
    - MemoryGraph: Simple dict-based in-memory storage

Usage:
    # Using factory function
    from src.cloud_backend.memgraph.graphstore import create_graph_store

    # Development (in-memory)
    store = create_graph_store("networkx")

    # Production (Neo4j)
    store = create_graph_store("neo4j")
"""

from typing import Optional, Union

from src.cloud_backend.memgraph.graphstore.graph_store import GraphStore
from src.cloud_backend.memgraph.graphstore.memory_graph import MemoryGraph
from src.cloud_backend.memgraph.graphstore.networkx_graph import NetworkXGraph


def create_graph_store(
    backend: str = "networkx",
    **kwargs,
) -> GraphStore:
    """Factory function to create GraphStore instance.

    Args:
        backend: Backend type - "networkx", "neo4j", or "memory"
        **kwargs: Backend-specific configuration:
            For "networkx":
                - directed: bool (default: True)
            For "neo4j":
                - uri: str (default: from NEO4J_URI env var)
                - user: str (default: from NEO4J_USER env var)
                - password: str (default: from NEO4J_PASSWORD env var)
                - database: str (default: "neo4j")
                - config: Neo4jConfig instance (alternative to individual params)
            For "memory":
                No additional kwargs

    Returns:
        GraphStore instance

    Raises:
        ValueError: If backend is unknown
        ImportError: If neo4j package not installed (for neo4j backend)

    Examples:
        # In-memory for development
        store = create_graph_store("networkx")

        # Neo4j with environment variables
        store = create_graph_store("neo4j")

        # Neo4j with explicit configuration
        store = create_graph_store(
            "neo4j",
            uri="neo4j://localhost:7687",
            user="neo4j",
            password="password",
        )
    """
    if backend == "networkx":
        directed = kwargs.get("directed", True)
        return NetworkXGraph(directed=directed)

    elif backend == "neo4j":
        from src.cloud_backend.memgraph.graphstore.neo4j_graph import Neo4jGraphStore
        from src.cloud_backend.memgraph.graphstore.neo4j_config import Neo4jConfig

        # Use provided config or create from kwargs/env
        config = kwargs.get("config")
        if config is None:
            config = Neo4jConfig(
                uri=kwargs.get("uri", Neo4jConfig().uri),
                user=kwargs.get("user", Neo4jConfig().user),
                password=kwargs.get("password", Neo4jConfig().password),
                database=kwargs.get("database", Neo4jConfig().database),
                max_pool_size=kwargs.get("max_pool_size", Neo4jConfig().max_pool_size),
                connection_timeout=kwargs.get("connection_timeout", Neo4jConfig().connection_timeout),
                vector_dimensions=kwargs.get("vector_dimensions", Neo4jConfig().vector_dimensions),
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

    elif backend == "memory":
        return MemoryGraph()

    else:
        raise ValueError(
            f"Unknown backend: {backend}. "
            f"Available backends: networkx, neo4j, memory"
        )


__all__ = [
    "GraphStore",
    "MemoryGraph",
    "NetworkXGraph",
    "create_graph_store",
]
