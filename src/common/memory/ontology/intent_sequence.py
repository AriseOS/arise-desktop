"""IntentSequence module - Represents an ordered sequence of operations.

IntentSequence represents a series of related operations (Intents) performed
within a single State (page). Each IntentSequence has a semantic description
and embedding vector for retrieval.

Example:
    State("Login Page") can have multiple IntentSequences:
    - IntentSequence(description="Login with username and password",
                     intents=[click_username, type_admin, click_password, type_123, click_login])
    - IntentSequence(description="Forgot password",
                     intents=[click_forgot_password])
"""

import uuid
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from src.common.memory.ontology.intent import Intent


class IntentSequence(BaseModel):
    """IntentSequence - Represents an ordered sequence of operations.

    An IntentSequence groups related Intents that were performed together
    within a State. Each sequence has a semantic description for retrieval
    and supports deduplication by description.

    Key Concept:
        - One IntentSequence = One coherent operation flow within a State
        - Multiple IntentSequences can belong to one State
        - Deduplication: Same description = same sequence (only keep one)
        - Supports semantic search via description + embedding_vector

    Attributes:
        id: Unique identifier for this intent sequence.
        session_id: Session ID when this sequence was recorded.
        timestamp: When this sequence started (milliseconds).
        description: Natural language description of the sequence.
        embedding_vector: Embedding vector for semantic search.
        intents: Ordered list of Intent objects in this sequence.
    """

    # Unique identifier
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this intent sequence"
    )

    # Session information
    session_id: Optional[str] = Field(
        default=None, description="Session ID when this sequence was recorded"
    )

    # Time information
    timestamp: int = Field(
        ..., description="When this sequence started (milliseconds)"
    )

    # Semantic description and embedding for retrieval
    description: Optional[str] = Field(
        default=None,
        description="Natural language description of the sequence (e.g., 'Login with username and password')"
    )
    semantic: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured semantic fields for stable retrieval (label/intent/keywords/retrieval_text)"
    )
    embedding_vector: Optional[List[float]] = Field(
        default=None, description="Embedding vector for semantic search"
    )

    # Ordered list of intents
    intents: List[Union[Intent, Dict[str, Any]]] = Field(
        default_factory=list,
        description="Ordered list of Intent objects in this sequence"
    )

    # ✨ Navigation markers (v2)
    causes_navigation: bool = Field(
        default=False,
        description="Whether this sequence causes page navigation"
    )
    navigation_target_state_id: Optional[str] = Field(
        default=None,
        description="If causes_navigation=True, the target State ID"
    )

    # Deduplication hash (computed from intents content)
    content_hash: Optional[str] = Field(
        default=None,
        description="MD5 hash of intents content for deduplication"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation of the intent sequence.
        """
        data = self.model_dump()
        # Handle intents - convert Intent objects to dicts
        if self.intents:
            data["intents"] = [
                intent.to_dict() if hasattr(intent, "to_dict") else intent
                for intent in self.intents
            ]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntentSequence":
        """Create instance from dictionary.

        Args:
            data: Dictionary containing intent sequence data.

        Returns:
            IntentSequence instance.
        """
        # Convert intent dicts to Intent objects if needed
        if "intents" in data and data["intents"]:
            intents = []
            for intent_data in data["intents"]:
                if isinstance(intent_data, dict):
                    intents.append(Intent.from_dict(intent_data))
                else:
                    intents.append(intent_data)
            data["intents"] = intents
        return cls(**data)

    def get_intent_count(self) -> int:
        """Get the number of intents in this sequence.

        Returns:
            Number of intents.
        """
        return len(self.intents)

    def is_empty(self) -> bool:
        """Check if this sequence has no intents.

        Returns:
            True if the sequence has no intents.
        """
        return len(self.intents) == 0


__all__ = [
    "IntentSequence",
]
