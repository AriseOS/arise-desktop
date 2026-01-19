"""State module - Represents a page or screen state.

State represents a page (web) or screen (app) where the user is currently located.
Each State contains multiple Intents (operations performed in that state).
States are connected by Actions (state transitions/navigation).
"""

import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class State(BaseModel):
    """State - Represents a page or screen state.

    A State represents the current page (web) or screen (app) where the user is located.
    It contains all Intents (operations) that occurred within this state.
    States are connected by Actions when navigation/transition occurs.

    Key Concept:
        - One State = One Page/Screen (current location)
        - Multiple Intents belong to one State (operations within that location)
        - Actions connect States (navigation that changes location)

    Attributes:
        id: Unique state identifier (auto-generated if not provided).
        page_url: URL (web) or screen identifier (app) - identifies the location.
        page_title: Title of the page/screen (optional).
        timestamp: When user first entered this state (milliseconds).
        end_timestamp: When user left this state (milliseconds, optional).
        duration: How long user stayed in this state (milliseconds, optional).
        intents: List of Intents (operations) performed in this state.
        intent_ids: List of Intent IDs for reference (optional).
        user_id: User ID (optional).
        session_id: Session ID (optional).
        attributes: Additional metadata (optional).
        description: Natural language description of the state and its intents (optional).
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

    # Contained intents (operations within this state)
    intents: List[Any] = Field(
        default_factory=list, description="List of Intents (operations) in this state"
    )
    intent_ids: Optional[List[str]] = Field(
        default=None, description="List of Intent IDs"
    )

    # User session information
    user_id: Optional[str] = Field(default=None, description="User ID")
    session_id: Optional[str] = Field(default=None, description="Session ID")

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
        # Handle intents
        if self.intents:
            data["intents"] = [
                intent.to_dict() if hasattr(intent, "to_dict") else intent
                for intent in self.intents
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
        return cls(**data)


# Backward compatibility aliases
SemanticState = State


__all__ = [
    "State",
    "SemanticState",  # Backward compatibility
]
