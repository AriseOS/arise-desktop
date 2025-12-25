"""
In-memory Intent storage backend

Simple memory-based implementation for MVP.
All data is stored in memory and lost when process exits.
Supports JSON serialization for persistence.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.cloud_backend.intent_builder.core.intent import Intent
from src.cloud_backend.intent_builder.core.intent_memory_graph import IntentStorageBackend


class InMemoryIntentStorage(IntentStorageBackend):
    """In-memory implementation of IntentStorageBackend

    Stores all intents and edges in memory using Python data structures.

    Characteristics:
    - Fast: All operations are O(1) or O(N) in memory
    - Simple: No external dependencies
    - Volatile: Data is lost when process exits
    - Thread-safe: Not thread-safe (use locks if needed)

    Use Cases:
    - MVP development
    - Testing
    - Small datasets
    - Single-process applications

    Attributes:
        _intents: Dictionary mapping intent ID to Intent
        _edges: List of (from_id, to_id) tuples
        _created_at: Storage creation timestamp
        _last_updated: Last update timestamp

    Example:
        >>> storage = InMemoryIntentStorage()
        >>> storage.add_intent(intent1)
        >>> storage.add_edge(intent1.id, intent2.id)
        >>> all_intents = storage.get_all_intents()
    """

    def __init__(self):
        """Initialize empty in-memory storage"""
        self._intents: Dict[str, Intent] = {}
        self._edges: List[Tuple[str, str]] = []
        self._created_at: datetime = datetime.now()
        self._last_updated: datetime = datetime.now()

    def add_intent(self, intent: Intent) -> None:
        """Add an intent to memory storage

        If intent ID already exists, it will be overwritten.

        Args:
            intent: Intent to add
        """
        self._intents[intent.id] = intent

    def get_intent(self, intent_id: str) -> Optional[Intent]:
        """Get an intent by ID

        Args:
            intent_id: Intent ID

        Returns:
            Intent if found, None otherwise
        """
        return self._intents.get(intent_id)

    def get_all_intents(self) -> List[Intent]:
        """Get all intents

        Returns:
            List of all intents (order not guaranteed)
        """
        return list(self._intents.values())

    def add_edge(self, from_id: str, to_id: str) -> None:
        """Add an edge between two intents

        MVP: Does not check for duplicates or validate intent existence.

        Args:
            from_id: Source intent ID
            to_id: Target intent ID
        """
        self._edges.append((from_id, to_id))

    def get_edges(self) -> List[Tuple[str, str]]:
        """Get all edges

        Returns:
            List of (from_id, to_id) tuples
        """
        return list(self._edges)

    def get_successors(self, intent_id: str) -> List[str]:
        """Get successor intent IDs

        Args:
            intent_id: Intent ID

        Returns:
            List of successor intent IDs (may contain duplicates if edges are duplicated)
        """
        return [to_id for from_id, to_id in self._edges if from_id == intent_id]

    def get_predecessors(self, intent_id: str) -> List[str]:
        """Get predecessor intent IDs

        Args:
            intent_id: Intent ID

        Returns:
            List of predecessor intent IDs
        """
        return [from_id for from_id, to_id in self._edges if to_id == intent_id]

    def get_metadata(self) -> Dict[str, datetime]:
        """Get storage metadata

        Returns:
            Dictionary with 'created_at' and 'last_updated' timestamps
        """
        return {
            "created_at": self._created_at,
            "last_updated": self._last_updated
        }

    def update_timestamp(self) -> None:
        """Update last_updated timestamp"""
        self._last_updated = datetime.now()

    def clear(self) -> None:
        """Clear all data from storage

        Useful for testing and resetting state.
        """
        self._intents.clear()
        self._edges.clear()
        self._last_updated = datetime.now()

    def __len__(self) -> int:
        """Return number of intents stored

        Returns:
            Number of intents
        """
        return len(self._intents)

    def __contains__(self, intent_id: str) -> bool:
        """Check if intent ID exists in storage

        Args:
            intent_id: Intent ID to check

        Returns:
            True if intent exists, False otherwise
        """
        return intent_id in self._intents

    def __repr__(self) -> str:
        """String representation of storage

        Returns:
            String showing storage stats
        """
        return (
            f"InMemoryIntentStorage("
            f"intents={len(self._intents)}, "
            f"edges={len(self._edges)}, "
            f"created={self._created_at.isoformat()})"
        )

    # === Persistence Operations ===

    def save(self, filepath: str) -> None:
        """Save storage to JSON file

        Args:
            filepath: Path to output JSON file

        Example:
            >>> storage.save("intent_graph.json")
        """
        data = {
            "intents": {
                intent_id: intent.to_dict()
                for intent_id, intent in self._intents.items()
            },
            "edges": self._edges,
            "metadata": {
                "created_at": self._created_at.isoformat(),
                "last_updated": self._last_updated.isoformat(),
                "version": "2.0"
            }
        }

        # Ensure parent directory exists
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, filepath: str) -> None:
        """Load storage from JSON file

        Replaces current storage content with data from file.

        Args:
            filepath: Path to JSON file

        Example:
            >>> storage.load("intent_graph.json")
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Clear existing data
        self._intents.clear()
        self._edges.clear()

        # Load intents
        for intent_id, intent_dict in data["intents"].items():
            self._intents[intent_id] = Intent.from_dict(intent_dict)

        # Load edges
        self._edges = [tuple(edge) for edge in data["edges"]]

        # Load metadata
        metadata = data.get("metadata", {})
        if "created_at" in metadata:
            self._created_at = datetime.fromisoformat(metadata["created_at"])
        if "last_updated" in metadata:
            self._last_updated = datetime.fromisoformat(metadata["last_updated"])

    @staticmethod
    def from_file(filepath: str) -> "InMemoryIntentStorage":
        """Create storage instance from JSON file

        Args:
            filepath: Path to JSON file

        Returns:
            InMemoryIntentStorage instance with loaded data

        Example:
            >>> storage = InMemoryIntentStorage.from_file("intent_graph.json")
        """
        storage = InMemoryIntentStorage()
        storage.load(filepath)
        return storage
