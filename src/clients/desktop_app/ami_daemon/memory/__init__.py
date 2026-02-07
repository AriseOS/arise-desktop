"""Memory module for Desktop App.

Provides access to both local and public memory services via common/memory.

- Local Memory: SurrealDB embedded, stored in ~/.ami/memory.db
- Public Memory: Cloud Backend (accessed via HTTP, not initialized locally)

Usage:
    from src.common.memory import (
        # Multi-tenant (new API)
        init_memory_services,
        get_private_memory,
        get_public_memory,
        share_phrase,
        # Local memory (Desktop App)
        get_local_memory_service,
        init_local_memory_service,
    )
"""

# Re-export from common/memory for convenience
from src.common.memory import (
    MemoryService,
    MemoryServiceConfig,
    # Multi-tenant (new API)
    init_memory_services,
    get_private_memory,
    get_public_memory,
    share_phrase,
    # Local memory (Desktop App)
    get_local_memory_service,
    set_local_memory_service,
    init_local_memory_service,
    # Public memory (backward compat)
    get_public_memory_service,
    # Default (backward compatible)
    get_memory_service,
    set_memory_service,
    init_memory_service,
)

__all__ = [
    "MemoryService",
    "MemoryServiceConfig",
    # Multi-tenant (new API)
    "init_memory_services",
    "get_private_memory",
    "get_public_memory",
    "share_phrase",
    # Local
    "get_local_memory_service",
    "set_local_memory_service",
    "init_local_memory_service",
    # Public (backward compat)
    "get_public_memory_service",
    # Default
    "get_memory_service",
    "set_memory_service",
    "init_memory_service",
]
