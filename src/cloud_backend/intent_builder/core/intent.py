"""
Intent data structures

Based on: docs/intent_builder/02_intent_specification.md
"""
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .operation import Operation


def generate_intent_id(description: str) -> str:
    """Generate Intent ID based on description hash

    Args:
        description: Intent description text

    Returns:
        Intent ID in format "intent_<hash8>"

    Example:
        >>> generate_intent_id("Navigate to Allegro homepage")
        'intent_a3f5b2c1'
    """
    hash_value = hashlib.md5(description.encode('utf-8')).hexdigest()[:8]
    return f"intent_{hash_value}"


# Operation is now imported from operation.py - unified definition used by Intent and MetaFlow


@dataclass
class Intent:
    """Intent data structure

    Represents a semantic abstraction of user operations - a complete subtask unit.

    Design Principles:
    - Minimal design: Only core fields, avoid over-engineering
    - Semantic first: Rely on description for understanding and retrieval
    - Complete operations: Preserve original operation sequence for full context
    - Extensible: Simple structure, easy to add fields in future

    Attributes:
        id: Unique identifier (generated from description hash)
        description: Natural language description of the intent (semantic, human-readable)
        operations: Sequence of user operations to complete this intent
        created_at: Creation timestamp
        source_session_id: Source session ID for tracking

    Example:
        >>> intent = Intent(
        ...     id="intent_a3f5b2c1",
        ...     description="Navigate to Allegro e-commerce website homepage",
        ...     operations=[
        ...         Operation(
        ...             type="navigate",
        ...             url="https://allegro.pl/",
        ...             page_title="Allegro - Strona Główna"
        ...         )
        ...     ],
        ...     created_at=datetime.now(),
        ...     source_session_id="session_001"
        ... )
    """

    # Core fields
    id: str
    description: str
    operations: List[Operation]

    # Metadata
    created_at: datetime
    source_session_id: str

    def __post_init__(self):
        """Validate Intent data after initialization"""
        if not self.description:
            raise ValueError("Intent description cannot be empty")
        if not self.operations:
            raise ValueError("Intent must have at least one operation")
        if not self.id.startswith("intent_"):
            raise ValueError(f"Invalid intent ID format: {self.id}")

    @classmethod
    def create(
        cls,
        description: str,
        operations: List[Operation],
        source_session_id: str,
        created_at: Optional[datetime] = None
    ) -> "Intent":
        """Create an Intent with auto-generated ID

        Args:
            description: Intent description
            operations: List of operations
            source_session_id: Source session ID
            created_at: Creation time (defaults to now)

        Returns:
            Intent instance with generated ID

        Example:
            >>> intent = Intent.create(
            ...     description="Navigate to homepage",
            ...     operations=[Operation(type="navigate", url="https://example.com")],
            ...     source_session_id="session_001"
            ... )
        """
        intent_id = generate_intent_id(description)
        if created_at is None:
            created_at = datetime.now()

        return cls(
            id=intent_id,
            description=description,
            operations=operations,
            created_at=created_at,
            source_session_id=source_session_id
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert Intent to dictionary for serialization

        Returns:
            Dictionary representation of Intent
        """
        return {
            "id": self.id,
            "description": self.description,
            # Pydantic Operation has model_dump() method
            "operations": [op.model_dump(by_alias=True, exclude_none=True) for op in self.operations],
            "created_at": self.created_at.isoformat(),
            "source_session_id": self.source_session_id
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Intent":
        """Create Intent from dictionary

        Args:
            data: Dictionary containing Intent data

        Returns:
            Intent instance
        """
        # Pydantic Operation can be created directly from dict
        operations = [Operation(**op) for op in data["operations"]]

        return cls(
            id=data["id"],
            description=data["description"],
            operations=operations,
            created_at=datetime.fromisoformat(data["created_at"]),
            source_session_id=data["source_session_id"]
        )
