"""
IntentMemoryGraph - Semantic layer for Intent storage and retrieval

Based on: docs/intent_builder/03_intent_memory_graph_specification.md

Architecture:
- Semantic Layer (this file): Defines the interface and business logic
- Persistence Layer: Different storage implementations (in-memory, JSON, SQLite, SurrealDB, etc.)
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from src.cloud_backend.intent_builder.core.intent import Intent


class IntentStorageBackend(ABC):
    """Abstract base class for Intent storage backends

    This interface allows different persistence implementations:
    - InMemoryIntentStorage: Memory-based (for MVP)
    - JSONIntentStorage: JSON file-based
    - SQLiteIntentStorage: SQLite database
    - SurrealDBIntentStorage: Graph database (future)
    """

    @abstractmethod
    def add_intent(self, intent: Intent) -> None:
        """Add an intent to storage

        Args:
            intent: Intent to add
        """
        pass

    @abstractmethod
    def get_intent(self, intent_id: str) -> Optional[Intent]:
        """Get an intent by ID

        Args:
            intent_id: Intent ID

        Returns:
            Intent if found, None otherwise
        """
        pass

    @abstractmethod
    def get_all_intents(self) -> List[Intent]:
        """Get all intents

        Returns:
            List of all intents
        """
        pass

    @abstractmethod
    def add_edge(self, from_id: str, to_id: str) -> None:
        """Add an edge between two intents

        Args:
            from_id: Source intent ID
            to_id: Target intent ID
        """
        pass

    @abstractmethod
    def get_edges(self) -> List[Tuple[str, str]]:
        """Get all edges

        Returns:
            List of (from_id, to_id) tuples
        """
        pass

    @abstractmethod
    def get_successors(self, intent_id: str) -> List[str]:
        """Get successor intent IDs

        Args:
            intent_id: Intent ID

        Returns:
            List of successor intent IDs
        """
        pass

    @abstractmethod
    def get_metadata(self) -> Dict[str, datetime]:
        """Get storage metadata

        Returns:
            Dictionary with 'created_at' and 'last_updated'
        """
        pass

    @abstractmethod
    def update_timestamp(self) -> None:
        """Update last_updated timestamp"""
        pass


class IntentMemoryGraph:
    """Intent Memory Graph - Semantic layer for Intent management

    This class provides high-level operations for managing intents and their relationships.
    It delegates actual storage to a backend implementation (IntentStorageBackend).

    Responsibilities:
    - Store and manage Intent nodes
    - Record connections between Intents (execution order)
    - Support Intent retrieval and querying
    - Provide semantic similarity search (future)

    Design:
    - Backend-agnostic: Works with any IntentStorageBackend implementation
    - Business logic layer: Encapsulates graph semantics
    - Simple API: Easy to use and extend

    Attributes:
        storage: Storage backend implementation

    Example:
        >>> from src.cloud_backend.intent_builder.storage.in_memory_storage import InMemoryIntentStorage
        >>> storage = InMemoryIntentStorage()
        >>> graph = IntentMemoryGraph(storage)
        >>> graph.add_intent(intent1)
        >>> graph.add_edge(intent1.id, intent2.id)
    """

    def __init__(self, storage: IntentStorageBackend):
        """Initialize IntentMemoryGraph with a storage backend

        Args:
            storage: Storage backend implementation
        """
        self.storage = storage

    # === Write Operations ===

    def add_intent(self, intent: Intent) -> None:
        """Add an intent to the graph

        Behavior:
        - If intent ID already exists, it will be overwritten (MVP: no deduplication)
        - Updates last_updated timestamp

        Args:
            intent: Intent to add

        Example:
            >>> intent = Intent.create(
            ...     description="Navigate to homepage",
            ...     operations=[...],
            ...     source_session_id="session_001"
            ... )
            >>> graph.add_intent(intent)
        """
        self.storage.add_intent(intent)
        self.storage.update_timestamp()

    def add_edge(self, from_id: str, to_id: str) -> None:
        """Add an edge between two intents

        Semantics: from_intent executes, then to_intent executes (temporal order)

        Behavior:
        - MVP: Does not check for duplicates (allows duplicate edges)
        - MVP: Does not validate that intent IDs exist
        - Updates last_updated timestamp

        Args:
            from_id: Source intent ID
            to_id: Target intent ID

        Example:
            >>> graph.add_edge("intent_a3f5b2c1", "intent_b7e4c8d2")
        """
        self.storage.add_edge(from_id, to_id)
        self.storage.update_timestamp()

    # === Read Operations ===

    def get_intent(self, intent_id: str) -> Optional[Intent]:
        """Get an intent by ID

        Args:
            intent_id: Intent ID

        Returns:
            Intent if found, None otherwise

        Example:
            >>> intent = graph.get_intent("intent_a3f5b2c1")
            >>> if intent:
            ...     print(intent.description)
        """
        return self.storage.get_intent(intent_id)

    def get_all_intents(self) -> List[Intent]:
        """Get all intents in the graph

        Returns:
            List of all intents

        Example:
            >>> intents = graph.get_all_intents()
            >>> print(f"Total intents: {len(intents)}")
        """
        return self.storage.get_all_intents()

    def get_successors(self, intent_id: str) -> List[Intent]:
        """Get successor intents of a given intent

        Args:
            intent_id: Intent ID

        Returns:
            List of successor intents (intents that follow this one)

        Example:
            >>> successors = graph.get_successors("intent_a3f5b2c1")
            >>> for s in successors:
            ...     print(f"Next: {s.description}")
        """
        successor_ids = self.storage.get_successors(intent_id)
        successors = []
        for sid in successor_ids:
            intent = self.storage.get_intent(sid)
            if intent:
                successors.append(intent)
        return successors

    def get_edges(self) -> List[Tuple[str, str]]:
        """Get all edges in the graph

        Returns:
            List of (from_id, to_id) tuples

        Example:
            >>> edges = graph.get_edges()
            >>> for from_id, to_id in edges:
            ...     print(f"{from_id} -> {to_id}")
        """
        return self.storage.get_edges()

    # === Metadata ===

    def get_metadata(self) -> Dict[str, datetime]:
        """Get graph metadata

        Returns:
            Dictionary with 'created_at' and 'last_updated' timestamps

        Example:
            >>> meta = graph.get_metadata()
            >>> print(f"Created: {meta['created_at']}")
            >>> print(f"Updated: {meta['last_updated']}")
        """
        return self.storage.get_metadata()

    # === Statistics ===

    def get_stats(self) -> Dict[str, int]:
        """Get graph statistics

        Returns:
            Dictionary with node and edge counts

        Example:
            >>> stats = graph.get_stats()
            >>> print(f"Intents: {stats['num_intents']}")
            >>> print(f"Edges: {stats['num_edges']}")
        """
        return {
            "num_intents": len(self.storage.get_all_intents()),
            "num_edges": len(self.storage.get_edges())
        }

    # === Retrieval (Placeholder for Future) ===

    async def retrieve_similar(self, query: str, limit: int = 5) -> List[Intent]:
        """Retrieve intents similar to the query (semantic similarity)

        NOTE: This is a placeholder for future implementation.
        Requires integration with embedding service.

        Algorithm:
        1. Compute query embedding
        2. Compute embeddings for all intent descriptions
        3. Calculate cosine similarity
        4. Filter by threshold (e.g., > 0.6)
        5. Sort and return top-K

        Args:
            query: Natural language query
            limit: Maximum number of results

        Returns:
            List of similar intents, sorted by similarity

        Example:
            >>> similar = await graph.retrieve_similar(
            ...     "collect product information from category page",
            ...     limit=3
            ... )
        """
        # TODO: Implement semantic similarity search
        # Requires: EmbeddingService integration
        raise NotImplementedError(
            "Semantic similarity search requires embedding service integration. "
            "Will be implemented in future iteration."
        )
