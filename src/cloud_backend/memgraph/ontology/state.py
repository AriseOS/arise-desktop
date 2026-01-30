"""State module - Represents an abstract page/screen state.

State (also known as AbstractState) represents a class of pages/screens,
not a specific URL. Multiple concrete URLs (PageInstances) can belong
to the same State if they represent the same type of page.

Example:
    State("Product Detail Page") can have multiple PageInstances:
    - PageInstance(url="example.com/products/123")
    - PageInstance(url="example.com/products/456")

States are connected by Actions (state transitions/navigation).
Each State contains IntentSequences (ordered operation sequences).
"""

import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from src.cloud_backend.memgraph.ontology.intent_sequence import IntentSequence
    from src.cloud_backend.memgraph.ontology.page_instance import PageInstance


class State(BaseModel):
    """State - Represents an abstract page/screen state (graph node).

    A State represents a class of pages (e.g., "Product Detail Page"),
    not a specific URL. This enables:
    - Multiple URLs → One State (deduplication)
    - Semantic search on page types
    - Path finding between page types

    Key Concept:
        - One State = One type of page (AbstractState)
        - Multiple PageInstances belong to one State (concrete URLs)
        - Multiple IntentSequences belong to one State (operation flows)
        - Actions connect States (navigation that changes location)

    Attributes:
        id: Unique state identifier (auto-generated if not provided).
        page_url: Primary URL for this state (for backward compatibility).
        page_title: Title of the page/screen (optional).
        timestamp: When this state was first created (milliseconds).
        end_timestamp: When user left this state (milliseconds, optional).
        duration: How long user stayed in this state (milliseconds, optional).
        intents: List of Intents - DEPRECATED, use intent_sequences instead.
        intent_ids: List of Intent IDs for reference (optional).
        instances: List of PageInstance objects (concrete URLs belonging to this state).
        intent_sequences: List of IntentSequence objects (operation flows in this state).
        user_id: User ID (optional).
        session_id: Session ID (optional).
        domain: Domain this state belongs to (e.g., "taobao.com").
        attributes: Additional metadata (optional).
        description: Natural language description of the state (e.g., "Product Detail Page").
        embedding_vector: Embedding vector for semantic search (optional).
    """

    # Core identifiers
    id: Optional[str] = Field(default=None, description="Unique state identifier")

    # Location information (REQUIRED - identifies where the user is)
    page_url: str = Field(..., description="URL (web) or screen identifier (app)")
    page_title: Optional[str] = Field(default=None, description="Title of the page/screen")

    # Time information
    timestamp: int = Field(..., description="When user entered this state (milliseconds)")
    end_timestamp: Optional[int] = Field(
        default=None, description="When user left this state (milliseconds)"
    )
    duration: Optional[int] = Field(
        default=None, description="Duration spent in this state (milliseconds)"
    )

    # Page instances (concrete URLs belonging to this abstract state)
    instances: List[Any] = Field(
        default_factory=list,
        description="List of PageInstance objects (concrete URLs)"
    )

    # NEW: Intent sequences (ordered operation flows in this state)
    intent_sequences: List[Any] = Field(
        default_factory=list,
        description="List of IntentSequence objects (operation flows)"
    )

    # User session information
    user_id: Optional[str] = Field(default=None, description="User ID")
    session_id: Optional[str] = Field(default=None, description="Session ID")

    # NEW: Domain this state belongs to
    domain: Optional[str] = Field(
        default=None, description="Domain this state belongs to (e.g., 'taobao.com')"
    )

    # Additional metadata
    attributes: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    # Description and embedding for semantic search
    description: Optional[str] = Field(
        default=None, description="Natural language description of the state and its intents"
    )
    embedding_vector: Optional[List[float]] = Field(
        default=None, description="Embedding vector for semantic search"
    )

    @model_validator(mode="before")
    @classmethod
    def generate_id(cls, data: Any) -> Any:
        """Auto-generate ID if not provided.

        Args:
            data: Input data dictionary.

        Returns:
            Data with ID generated if missing.
        """
        if isinstance(data, dict):
            if not data.get("id"):
                data["id"] = str(uuid.uuid4())
        return data

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation of the state.
        """
        data = self.model_dump()
        # Handle instances
        if self.instances:
            data["instances"] = [
                instance.to_dict() if hasattr(instance, "to_dict") else instance
                for instance in self.instances
            ]
        # Handle intent_sequences
        if self.intent_sequences:
            data["intent_sequences"] = [
                seq.to_dict() if hasattr(seq, "to_dict") else seq
                for seq in self.intent_sequences
            ]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "State":
        """Create instance from dictionary.

        Args:
            data: Dictionary containing state data.

        Returns:
            State instance.
        """
        # Import here to avoid circular imports
        from src.cloud_backend.memgraph.ontology.intent_sequence import IntentSequence
        from src.cloud_backend.memgraph.ontology.page_instance import PageInstance

        # Convert instance dicts to PageInstance objects if needed
        if "instances" in data and data["instances"]:
            instances = []
            for inst_data in data["instances"]:
                if isinstance(inst_data, dict):
                    instances.append(PageInstance.from_dict(inst_data))
                else:
                    instances.append(inst_data)
            data["instances"] = instances

        # Convert intent_sequences dicts to IntentSequence objects if needed
        if "intent_sequences" in data and data["intent_sequences"]:
            sequences = []
            for seq_data in data["intent_sequences"]:
                if isinstance(seq_data, dict):
                    sequences.append(IntentSequence.from_dict(seq_data))
                else:
                    sequences.append(seq_data)
            data["intent_sequences"] = sequences

        return cls(**data)

    def add_instance(self, instance: "PageInstance") -> None:
        """Add a PageInstance to this state.

        Args:
            instance: PageInstance to add.
        """
        self.instances.append(instance)

    def add_intent_sequence(self, sequence: "IntentSequence") -> bool:
        """DEPRECATED: V2 uses IntentSequenceManager for graph storage.

        This method is kept for in-memory operations only. For graph persistence,
        use IntentSequenceManager.create_sequence() and link_to_state().

        Adds an IntentSequence to this state's in-memory list with deduplication.

        Args:
            sequence: IntentSequence to add.

        Returns:
            True if added, False if duplicate was found.
        """
        # Compute hash of new sequence's intents
        new_hash = self._compute_intents_hash(sequence)

        for existing in self.intent_sequences:
            # Check by intents content hash (primary)
            existing_hash = self._compute_intents_hash(existing)
            if new_hash and existing_hash and new_hash == existing_hash:
                return False  # Duplicate found

            # Fallback: check by description if both have description
            if sequence.description:
                existing_desc = (
                    existing.description
                    if hasattr(existing, "description")
                    else existing.get("description")
                )
                if existing_desc and existing_desc == sequence.description:
                    return False  # Duplicate found

        self.intent_sequences.append(sequence)
        return True

    def _compute_intents_hash(self, sequence: Union["IntentSequence", Dict]) -> Optional[str]:
        """Compute a hash of the intents in a sequence for deduplication.

        Args:
            sequence: IntentSequence or dict.

        Returns:
            Hash string, or None if cannot compute.
        """
        import hashlib
        import json

        try:
            if hasattr(sequence, "intents"):
                intents = sequence.intents
            else:
                intents = sequence.get("intents", [])

            if not intents:
                return None

            # Build a canonical representation
            intent_keys = []
            for intent in intents:
                if hasattr(intent, "type"):
                    key = f"{intent.type}:{intent.text or ''}:{intent.value or ''}"
                elif isinstance(intent, dict):
                    key = f"{intent.get('type', '')}:{intent.get('text', '')}:{intent.get('value', '')}"
                else:
                    continue
                intent_keys.append(key)

            if not intent_keys:
                return None

            content = "|".join(intent_keys)
            return hashlib.md5(content.encode()).hexdigest()
        except Exception:
            return None

    def get_all_urls(self) -> List[str]:
        """Get all URLs from instances.

        Returns:
            List of URLs from all PageInstances.
        """
        urls = []
        for instance in self.instances:
            url = instance.url if hasattr(instance, "url") else instance.get("url")
            if url:
                urls.append(url)
        return urls

    def has_url(self, url: str) -> bool:
        """Check if this state has a specific URL in its instances.

        Args:
            url: URL to check.

        Returns:
            True if the URL exists in instances.
        """
        return url in self.get_all_urls()


# Backward compatibility aliases
SemanticState = State


__all__ = [
    "State",
    "SemanticState",  # Backward compatibility
]
