"""Neo4j connection configuration module.

This module provides configuration management for Neo4j connections,
supporting both environment variables and programmatic configuration.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Neo4jConfig:
    """Neo4j connection configuration.

    Attributes:
        uri: Neo4j connection URI (e.g., "neo4j://localhost:7687")
        user: Username for authentication
        password: Password for authentication
        database: Database name (default: "neo4j")
        max_pool_size: Maximum connection pool size
        connection_timeout: Connection timeout in seconds
        vector_dimensions: Default embedding vector dimensions
    """

    uri: str = field(default_factory=lambda: os.getenv("NEO4J_URI", "neo4j://localhost:7687"))
    user: str = field(default_factory=lambda: os.getenv("NEO4J_USER", "neo4j"))
    password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", ""))
    database: str = field(default_factory=lambda: os.getenv("NEO4J_DATABASE", "neo4j"))
    max_pool_size: int = field(default_factory=lambda: int(os.getenv("NEO4J_MAX_POOL_SIZE", "50")))
    connection_timeout: float = field(
        default_factory=lambda: float(os.getenv("NEO4J_CONNECTION_TIMEOUT", "30.0"))
    )
    vector_dimensions: int = field(
        default_factory=lambda: int(os.getenv("NEO4J_VECTOR_DIMENSIONS", "768"))
    )

    @classmethod
    def from_env(cls) -> "Neo4jConfig":
        """Create configuration from environment variables.

        Returns:
            Neo4jConfig instance with values from environment.
        """
        return cls()

    def validate(self) -> None:
        """Validate configuration values.

        Raises:
            ValueError: If required configuration is missing or invalid.
        """
        if not self.uri:
            raise ValueError("NEO4J_URI is required")
        if not self.user:
            raise ValueError("NEO4J_USER is required")
        if not self.password:
            raise ValueError("NEO4J_PASSWORD is required")
        if self.max_pool_size < 1:
            raise ValueError("NEO4J_MAX_POOL_SIZE must be >= 1")
        if self.connection_timeout <= 0:
            raise ValueError("NEO4J_CONNECTION_TIMEOUT must be > 0")
        if self.vector_dimensions < 1 or self.vector_dimensions > 4096:
            raise ValueError("NEO4J_VECTOR_DIMENSIONS must be between 1 and 4096")

    def __repr__(self) -> str:
        """Return string representation with password masked."""
        return (
            f"Neo4jConfig(uri='{self.uri}', user='{self.user}', "
            f"password='***', database='{self.database}', "
            f"max_pool_size={self.max_pool_size}, "
            f"connection_timeout={self.connection_timeout}, "
            f"vector_dimensions={self.vector_dimensions})"
        )
