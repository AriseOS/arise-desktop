"""PageInstance module - Represents a concrete page URL instance.

PageInstance represents a specific URL visit within an AbstractState (State).
Multiple PageInstances can belong to the same State, representing different
concrete URLs that are semantically the same type of page.

Example:
    State("Product Detail Page") can have multiple PageInstances:
    - PageInstance(url="example.com/products/123")
    - PageInstance(url="example.com/products/456")
"""

import hashlib
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, model_validator


def _url_to_id(url: str) -> str:
    """Generate a deterministic ID from URL.

    Same URL always produces the same ID, enabling natural upsert dedup.
    """
    return hashlib.md5(url.encode()).hexdigest()


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
        - ID is derived from URL (deterministic), so upsert naturally deduplicates

    Attributes:
        id: Deterministic identifier derived from URL.
        url: The concrete URL that was visited (required).
        page_title: Title of the page at the time of visit.
        timestamp: When this page was visited (milliseconds).
        snapshot_text: Page accessibility tree text snapshot (optional).
        session_id: Session ID when this page was visited (optional).
    """

    # Unique identifier — deterministic from URL for natural dedup
    id: str = Field(
        default="",
        description="Deterministic identifier derived from URL"
    )

    # Core attributes (URL is required)
    url: str = Field(..., description="The concrete URL that was visited")
    page_title: Optional[str] = Field(
        default=None, description="Title of the page at the time of visit"
    )
    timestamp: int = Field(..., description="When this page was visited (milliseconds)")

    # Page snapshot text (accessibility tree)
    snapshot_text: Optional[str] = Field(
        default=None, description="Page accessibility tree text snapshot"
    )

    # Session information
    session_id: Optional[str] = Field(default=None, description="Session ID")

    @model_validator(mode="after")
    def _set_id_from_url(self) -> "PageInstance":
        """Auto-generate deterministic ID from URL if not already set."""
        if not self.id:
            self.id = _url_to_id(self.url)
        return self

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
        # Copy to avoid mutating caller's dict
        data = {k: v for k, v in data.items() if k != "dom_snapshot_id"}
        return cls(**data)


__all__ = [
    "PageInstance",
]
