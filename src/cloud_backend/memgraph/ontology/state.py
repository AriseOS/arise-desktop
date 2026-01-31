"""State module - Represents an abstract page/screen state.

State (also known as AbstractState) represents a class of pages/screens,
not a specific URL. Multiple concrete URLs (PageInstances) can belong
to the same State if they represent the same type of page.

Example:
    State("Product Detail Page") can have multiple PageInstances:
    - PageInstance(url="example.com/products/123")
    - PageInstance(url="example.com/products/456")

States are connected by Actions (state transitions/navigation).
IntentSequences are stored as independent graph nodes linked via HAS_SEQUENCE relationships.
"""

import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


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
        instances: List of PageInstance objects (concrete URLs belonging to this state).
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
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "State":
        """Create instance from dictionary.

        Args:
            data: Dictionary containing state data.

        Returns:
            State instance.
        """
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

        # Drop legacy intent_sequences field if present in data
        data.pop("intent_sequences", None)

        return cls(**data)

    def add_instance(self, instance) -> None:
        """Add a PageInstance to this state.

        Args:
            instance: PageInstance to add.
        """
        self.instances.append(instance)

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
