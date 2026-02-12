"""
Minimal base classes for step agents.

These classes are retained for the remaining specialized agent implementations
(DeveloperAgent, DocumentAgent, SocialMediumAgent, QuestionConfirmAgent).

Note: In production, agents are created via agent_factories.py (AMIAgent/AMIBrowserAgent).
These step agent classes are not instantiated in the current codebase.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..core.schemas import AgentContext

logger = logging.getLogger(__name__)


class FieldSchema(BaseModel):
    """Schema for a single input field."""
    type: str = Field(..., description="Field type: str, int, bool, dict, list, any")
    required: bool = Field(default=False, description="Whether field is required")
    description: str = Field(default="", description="Field description")
    enum: Optional[List[Any]] = Field(default=None, description="Allowed values")
    default: Optional[Any] = Field(default=None, description="Default value")
    items_type: Optional[str] = Field(default=None, description="Type of items if field is a list")


class InputSchema(BaseModel):
    """Complete input schema for an agent."""
    fields: Dict[str, FieldSchema] = Field(default_factory=dict)
    description: str = Field(default="")
    examples: List[Dict[str, Any]] = Field(default_factory=list)


class AgentMetadata(BaseModel):
    """Agent metadata."""
    name: str = Field(..., description="Agent name")
    description: str = Field(..., description="Agent description")


class BaseStepAgent(ABC):
    """Base class for step agents.

    Subclasses define INPUT_SCHEMA to specify their input requirements.
    """

    INPUT_SCHEMA: InputSchema = InputSchema()

    def __init__(self, metadata: AgentMetadata):
        self.metadata = metadata
        self.is_initialized = False

    @abstractmethod
    async def initialize(self, context: AgentContext) -> bool:
        ...

    @abstractmethod
    async def execute(self, input_data: Any, context: AgentContext):
        ...

    async def cleanup(self, context: AgentContext) -> None:
        pass
