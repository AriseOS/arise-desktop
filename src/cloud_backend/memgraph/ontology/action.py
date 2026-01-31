"""Action module - Represents state transitions (navigation between pages/screens).

Action represents a state transition that changes the user's location from one
State (page/screen) to another State. Actions are the edges in the memory graph
connecting State nodes.
"""

import uuid
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, model_validator


class Action(BaseModel):
    """Action - Represents a state transition (navigation/page change).

    An Action represents a transition from one State to another State,
    indicating that the user navigated from one page/screen to a different
    page/screen. Actions are the edges in the memory graph that connect
    State nodes.

    Key Concept:
        - One Action = One State Transition (navigation that changes location)
        - Action connects two different States (source -> target)
        - Action must change the page_url or screen identifier
        - Actions represent navigation events (link clicks, redirects, etc.)

    Constraint:
        - source and target must be different State IDs
        - The action should represent a meaningful navigation event

    Attributes:
        id: Unique action identifier (auto-generated if not provided).
        source: Source state ID (where the user was).
        target: Target state ID (where the user navigated to).
        type: Transition type (e.g., "click", "submit", "auto_navigate").
        timestamp: When the transition occurred (milliseconds, optional).
        trigger: Structured trigger information (ref, text, role from recording).
        user_id: User ID (optional).
        session_id: Session ID (optional).
        attributes: Additional metadata about the transition.
        weight: Edge weight for graph algorithms (default: 1.0).
        confidence: Confidence score for this transition (optional).
        description: Semantic description for retrieval (LLM-generated).
    """

    # Unique identifier (v2 - for ExecutionStep references)
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description='Unique action identifier'
    )

    # Core attributes (REQUIRED - defines the state transition)
    source: str = Field(..., description='Source state ID')
    target: str = Field(..., description='Target state ID')
    type: str = Field(
        default='user_action',
        description='Transition type (LLM-generated)'
    )

    # Time information
    timestamp: Optional[int] = Field(
        default=None,
        description='Transition timestamp in milliseconds'
    )

    # Trigger information (what caused this transition)
    trigger: Optional[Dict[str, Any]] = Field(
        default=None,
        description='Structured trigger information from recording (ref, text, role)'
    )

    # ✨ Reference to the IntentSequence that triggered this Action (v2)
    trigger_sequence_id: Optional[str] = Field(
        default=None,
        description='ID of the IntentSequence that caused this navigation (optional context)'
    )

    # User session information
    user_id: Optional[str] = Field(default=None, description='User ID')
    session_id: Optional[str] = Field(default=None, description='Session ID')

    # Transition attributes
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description='Additional metadata about the transition'
    )

    # Weight information for graph algorithms
    weight: float = Field(default=1.0, description='Edge weight')
    confidence: Optional[float] = Field(
        default=None,
        description='Confidence score',
        ge=0.0,
        le=1.0
    )

    # Semantic description
    description: Optional[str] = Field(
        default=None,
        description='Semantic description of the transition (e.g., "Click Team button to view team page")'
    )

    @model_validator(mode='after')
    def validate_state_transition(self) -> 'Action':
        """Validate that source and target are different states.

        Returns:
            Self if validation passes.

        Raises:
            ValueError: If source and target are the same.
        """
        if self.source == self.target:
            raise ValueError(
                f"Action must connect different states. "
                f"Got source=target='{self.source}'. "
                f"Actions represent state transitions (navigation), "
                f"not operations within the same state (use Intent for that)."
            )
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation of the action.
        """
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Action':
        """Create instance from dictionary.

        Args:
            data: Dictionary containing action data.

        Returns:
            Action instance.

        Raises:
            ValueError: If validation fails.
        """
        return cls(**data)


# Backward compatibility alias
TransitionEdge = Action


__all__ = [
    'Action',
    'TransitionEdge',  # Backward compatibility
]
