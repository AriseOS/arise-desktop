"""PageInstance module - Represents a concrete page URL instance.

PageInstance represents a specific URL visit within an AbstractState (State).
Multiple PageInstances can belong to the same State, representing different
concrete URLs that are semantically the same type of page.

Example:
    State("Product Detail Page") can have multiple PageInstances:
    - PageInstance(url="example.com/products/123")
    - PageInstance(url="example.com/products/456")
"""

import uuid
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class PageInstance(BaseModel):
    """PageInstance - Represents a concrete page URL instance.

    A PageInstance represents a specific URL that was visited. Multiple
    PageInstances can belong to the same State (AbstractState), allowing
    the system to recognize that different URLs represent the same type
    of page (e.g., multiple product detail pages).

    Key Concept:
        - One PageInstance = One concrete URL visit
        - Multiple PageInstances can belong to one State
        - PageInstance enables State deduplication (same URL = same State)

    Attributes:
        id: Unique identifier for this page instance.
        url: The concrete URL that was visited (required).
        page_title: Title of the page at the time of visit.
        timestamp: When this page was visited (milliseconds).
        dom_snapshot_id: Reference to a DOM snapshot for replay (optional).
        session_id: Session ID when this page was visited (optional).
        user_id: User ID who visited this page (optional).
    """

    # Unique identifier
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this page instance"
    )

    # Core attributes (URL is required)
    url: str = Field(..., description="The concrete URL that was visited")
    page_title: Optional[str] = Field(
        default=None, description="Title of the page at the time of visit"
    )
    timestamp: int = Field(..., description="When this page was visited (milliseconds)")

    # Optional reference to DOM snapshot for replay
    dom_snapshot_id: Optional[str] = Field(
        default=None, description="Reference to a DOM snapshot for replay"
    )

    # User session information
    session_id: Optional[str] = Field(default=None, description="Session ID")
    user_id: Optional[str] = Field(default=None, description="User ID")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation of the page instance.
        """
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PageInstance":
        """Create instance from dictionary.

        Args:
            data: Dictionary containing page instance data.

        Returns:
            PageInstance instance.
        """
        return cls(**data)


__all__ = [
    "PageInstance",
]
