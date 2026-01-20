"""Intent module - Represents an operation within a state.

Intent represents an atomic operation performed within a specific State (page/screen).
Each Intent belongs to exactly one State and represents a single user action or interaction
within that state.
"""

import uuid
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class Intent(BaseModel):
    """Intent - Represents an atomic operation within a state.

    An Intent represents a single atomic-level user operation performed within
    a specific State (page/screen). Each Intent must belong to exactly one State,
    representing operations like clicks, typing, scrolling, etc. within that location.

    Key Concept:
        - One Intent = One Operation within a State
        - Multiple Intents can belong to one State
        - Intent does not cause state transitions (use Action for that)
        - Intent captures what the user did at a specific location

    Attributes:
        id: Unique identifier for this intent (auto-generated UUID if not provided).
        state_id: ID of the State this intent belongs to (required).
        type: Intent type (LLM-generated, e.g., "ClickElement", "TypeText").
        timestamp: Timestamp in milliseconds when the operation occurred.
        page_url: URL (web) or screen identifier (app) where operation occurred.
        page_title: Title of the page/screen (optional).
        element_id: Element ID that was interacted with (optional).
        element_tag: Element tag name (optional).
        element_class: Element CSS class (optional).
        xpath: XPath to the element (optional).
        css_selector: CSS selector for the element (optional).
        text: Element text content (optional).
        value: Input or selected value (optional).
        coordinates: Coordinates dict with x, y (optional).
        user_id: User ID (optional).
        session_id: Session ID (optional).
        attributes: Additional metadata.
        confidence_score: Confidence score for LLM extraction (optional).
    """

    # Unique identifier
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description='Unique identifier for this intent'
    )

    # State relationship (REQUIRED - every intent belongs to a state)
    state_id: Optional[str] = Field(
        default=None,
        description='ID of the State this intent belongs to'
    )

    # Core attributes
    type: str = Field(..., description='Intent type (LLM-generated)')
    timestamp: int = Field(..., description='Timestamp in milliseconds')

    # Page information (identifies where the operation occurred)
    page_url: str = Field(..., description='URL (web) or screen identifier (app)')
    page_title: Optional[str] = Field(
        default=None, description='Title of the page/screen')

    # Element information (what was interacted with)
    element_id: Optional[str] = Field(default=None, description='Element ID')
    element_tag: Optional[str] = Field(
        default=None, description='Element tag')
    element_class: Optional[str] = Field(
        default=None, description='Element CSS class')
    xpath: Optional[str] = Field(default=None, description='XPath')
    css_selector: Optional[str] = Field(
        default=None, description='CSS selector')

    # Content data (what was shown/entered)
    text: Optional[str] = Field(
        default=None, description='Element text content')
    value: Optional[str] = Field(
        default=None, description='Input or selected value')

    # Coordinate information
    coordinates: Optional[Dict[str, float]] = Field(
        default=None, description='Coordinates {x, y}')

    # User session information
    user_id: Optional[str] = Field(default=None, description='User ID')
    session_id: Optional[str] = Field(default=None, description='Session ID')

    # Extended attributes
    attributes: Dict[str, Any] = Field(
        default_factory=dict, description='Additional metadata')

    # Confidence (for LLM extraction)
    confidence_score: Optional[float] = Field(
        default=None, description='Confidence score', ge=0.0, le=1.0)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation of the intent.
        """
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Intent':
        """Create instance from dictionary.

        Args:
            data: Dictionary containing intent data.

        Returns:
            Intent instance.
        """
        return cls(**data)


# Backward compatibility aliases
AtomicIntent = Intent


__all__ = [
    'Intent',
    'AtomicIntent',  # Backward compatibility
]
