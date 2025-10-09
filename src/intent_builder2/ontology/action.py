"""Action module - Action connecting two States.

Action represents an action that connects two State units as an edge.
"""

from typing import Any
from typing import Dict
from typing import Optional

from pydantic import BaseModel
from pydantic import Field


class Action(BaseModel):
    """Action - Action connecting two States.

    Represents an action that connects two State units as an edge.
    In the memory graph, it represents the transition relationship
    between states.

    Attributes:
        source: Source state ID.
        target: Target state ID.
        type: Transition type.
        timestamp: Transition timestamp in milliseconds (optional).
        attributes: Transition attributes.
        weight: Edge weight.
        confidence: Confidence score (optional).
    """

    # Core attributes
    source: str = Field(..., description='Source state ID')
    target: str = Field(..., description='Target state ID')
    type: str = Field(default='user_action', description='Transition type')

    # Time information
    timestamp: Optional[int] = Field(
        default=None, description='Transition timestamp in milliseconds')

    # Transition attributes
    attributes: Dict[str, Any] = Field(
        default_factory=dict, description='Transition attributes')

    # Weight information
    weight: float = Field(default=1.0, description='Edge weight')
    confidence: Optional[float] = Field(
        default=None, description='Confidence score', ge=0.0, le=1.0)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation of the action.
        """
        return self.model_dump()


# Backward compatibility alias
TransitionEdge = Action


__all__ = [
    'Action',
    'TransitionEdge',  # Backward compatibility
]
