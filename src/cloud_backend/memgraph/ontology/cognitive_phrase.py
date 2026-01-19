"""CognitivePhrase module - Cognitive phrase composed of States and Actions.

CognitivePhrase represents a cognitive phrase composed of multiple State
and Action units.
"""

import uuid
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator


class CognitivePhrase(BaseModel):
    """CognitivePhrase - Cognitive phrase representing a workflow pattern.

    Represents a cognitive phrase composed of States and Actions forming
    a complete workflow path. All cognitive phrases are stored permanently
    with unique IDs for tracking and analysis.

    Attributes:
        id: Unique cognitive phrase identifier (auto-generated using UUID).
        description: Natural language description of the workflow process.
        user_id: User ID.
        session_id: Session ID.
        start_timestamp: Start timestamp in milliseconds.
        end_timestamp: End timestamp in milliseconds.
        duration: Duration in milliseconds.
        state_path: Ordered list of state IDs in the workflow.
        action_path: Ordered list of action types in the workflow.
        embedding_vector: Vector representation for semantic search.
        access_count: Number of times accessed (for tracking).
        last_access_time: Last access timestamp (for tracking).
        created_at: Creation timestamp.
    """

    # Core identifiers
    id: Optional[str] = Field(
        default=None, description='Unique cognitive phrase identifier')

    # Natural language description of the workflow
    description: str = Field(
        ..., description='Natural language description of the workflow process')

    # User session information
    user_id: str = Field(..., description='User ID')
    session_id: str = Field(..., description='Session ID')

    # Time information
    start_timestamp: int = Field(
        ..., description='Start timestamp in milliseconds')
    end_timestamp: int = Field(
        ..., description='End timestamp in milliseconds')
    duration: int = Field(
        ..., description='Duration in milliseconds')

    # Workflow path (ordered sequence of states and actions)
    state_path: List[str] = Field(
        ..., description='Ordered list of state IDs in the workflow path')
    action_path: List[str] = Field(
        ..., description='Ordered list of action types between states')

    # Vector representation for semantic search
    embedding_vector: Optional[List[float]] = Field(
        default=None, description='Embedding vector for semantic search')

    # Access tracking
    access_count: int = Field(
        default=0, description='Number of times accessed (for tracking)')
    last_access_time: Optional[int] = Field(
        default=None, description='Last access timestamp in milliseconds')
    created_at: int = Field(
        ..., description='Creation timestamp in milliseconds')

    @model_validator(mode='before')
    @classmethod
    def generate_id(cls, data: Any) -> Any:
        """Auto-generate ID if not provided.

        Args:
            data: Input data dictionary.

        Returns:
            Data with ID generated if missing.
        """
        if isinstance(data, dict):
            if not data.get('id'):
                data['id'] = str(uuid.uuid4())
        return data

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation of the cognitive phrase.
        """
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CognitivePhrase':
        """Create instance from dictionary.

        Args:
            data: Dictionary containing cognitive phrase data.

        Returns:
            CognitivePhrase instance.
        """
        return cls(**data)

    def record_access(self, timestamp: Optional[int] = None) -> None:
        """Record an access to this cognitive phrase for tracking.

        Args:
            timestamp: Access timestamp in milliseconds. If None, uses current time.
        """
        import time
        self.access_count += 1
        self.last_access_time = timestamp if timestamp is not None else int(time.time() * 1000)


__all__ = [
    'CognitivePhrase',
]
