"""SurrealDB configuration module.

Supports connection URLs:
- file://path - File storage (persistent, recommended)
- rocksdb://path - RocksDB storage (persistent)
- surrealkv://path - SurrealKV file storage (persistent)
- memory:// - In-memory storage (non-persistent)
- ws://host:port - WebSocket connection to remote SurrealDB server
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Supported embedded storage schemes
EMBEDDED_SCHEMES = ("file://", "rocksdb://", "surrealkv://", "memory://", "mem://")


@dataclass
class SurrealDBConfig:
    """SurrealDB connection configuration.

    Attributes:
        url: Connection URL (file://path, rocksdb://path, surrealkv://path, or ws://host:port)
        namespace: SurrealDB namespace
        database: SurrealDB database name
        username: Username for authentication (server mode only)
        password: Password for authentication (server mode only)
        vector_dimensions: Default embedding vector dimensions

    Examples:
        # Desktop App (local file storage - recommended)
        config = SurrealDBConfig(url="file://~/.ami/memory.db")

        # Desktop App (RocksDB storage)
        config = SurrealDBConfig(url="rocksdb://~/.ami/memory.db")

        # Cloud Backend (remote server)
        config = SurrealDBConfig(url="ws://localhost:8000")
    """

    url: str = field(
        default_factory=lambda: os.getenv(
            "SURREALDB_URL", f"file://{Path.home() / '.ami' / 'memory.db'}"
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

    # Legacy fields for backward compatibility
    _mode: Optional[str] = field(default=None, repr=False)
    path: Optional[str] = None

    def __post_init__(self):
        """Handle legacy mode/path fields."""
        # If legacy fields are provided, convert to url
        if self._mode == "file" and self.path:
            expanded_path = os.path.expanduser(self.path)
            self.url = f"file://{expanded_path}"
        elif self._mode == "server" and not self.url.startswith("ws"):
            # Keep existing url if it's already a ws:// url
            pass

    @property
    def mode(self) -> str:
        """Get the connection mode based on URL.

        Returns:
            'embedded' for file/memory URLs, 'server' for ws:// URLs
        """
        if self.is_embedded():
            # More specific mode names
            if self.url.startswith("file://"):
                return "file"
            elif self.url.startswith("rocksdb://"):
                return "rocksdb"
            elif self.url.startswith("surrealkv://"):
                return "surrealkv"
            elif self.url.startswith("memory://") or self.url.startswith("mem://"):
                return "memory"
            return "embedded"
        else:
            return "server"

    def get_connection_string(self) -> str:
        """Get the connection string.

        Returns:
            Connection URL with path expanded
        """
        # Check for embedded file-based schemes
        for scheme in ("file://", "rocksdb://", "surrealkv://"):
            if self.url.startswith(scheme):
                # Expand ~ in path
                path = self.url.replace(scheme, "")
                expanded_path = os.path.expanduser(path)
                # Ensure parent directory exists
                Path(expanded_path).parent.mkdir(parents=True, exist_ok=True)
                return f"{scheme}{expanded_path}"

        return self.url

    def is_embedded(self) -> bool:
        """Check if using embedded mode (no separate server needed).

        Returns:
            True if using embedded URL scheme (file://, rocksdb://, surrealkv://, memory://)
        """
        return any(self.url.startswith(scheme) for scheme in EMBEDDED_SCHEMES)
