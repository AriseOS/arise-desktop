"""SurrealDB configuration module."""
import os
from dataclasses import dataclass, field


@dataclass
class SurrealDBConfig:
    """SurrealDB connection configuration.

    Attributes:
        url: WebSocket URL for SurrealDB connection.
        namespace: SurrealDB namespace.
        database: SurrealDB database name.
        username: Username for authentication.
        password: Password for authentication.
        vector_dimensions: Default embedding vector dimensions.
    """

    url: str = field(
        default_factory=lambda: os.getenv(
            "SURREALDB_URL", "ws://localhost:8000/rpc"
        )
    )
    namespace: str = field(
        default_factory=lambda: os.getenv("SURREALDB_NAMESPACE", "ami")
    )
    database: str = field(
        default_factory=lambda: os.getenv("SURREALDB_DATABASE", "memory")
    )
    username: str = field(
        default_factory=lambda: os.getenv("SURREALDB_USER", "root")
    )
    password: str = field(
        default_factory=lambda: os.getenv("SURREALDB_PASSWORD", "root")
    )
    vector_dimensions: int = field(
        default_factory=lambda: int(
            os.getenv("SURREALDB_VECTOR_DIMENSIONS", "1024")
        )
    )
