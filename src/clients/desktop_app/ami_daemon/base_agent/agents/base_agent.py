"""
Base Agent class for Agent-as-Step architecture
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Literal, Union
from pydantic import BaseModel, Field

from ..core.schemas import AgentContext

logger = logging.getLogger(__name__)


class FieldSchema(BaseModel):
    """Schema for a single input field"""
    type: str = Field(..., description="Field type: str, int, bool, dict, list, any")
    required: bool = Field(default=False, description="Whether field is required")
    description: str = Field(default="", description="Field description")
    enum: Optional[List[Any]] = Field(default=None, description="Allowed values")
    default: Optional[Any] = Field(default=None, description="Default value")
    required_when: Optional[str] = Field(default=None, description="Condition when field is required, e.g. 'operation == store'")
    items_type: Optional[str] = Field(default=None, description="Type of items if field is a list")
    nested: Optional[Dict[str, 'FieldSchema']] = Field(default=None, description="Nested schema for dict fields")


class InputSchema(BaseModel):
    """Complete input schema for an agent"""
    fields: Dict[str, FieldSchema] = Field(default_factory=dict, description="Field definitions")
    description: str = Field(default="", description="Schema description")
    examples: List[Dict[str, Any]] = Field(default_factory=list, description="Example inputs")


class AgentMetadata(BaseModel):
    """Agent metadata"""
    name: str = Field(..., description="Agent name")
    description: str = Field(..., description="Agent description")


class BaseStepAgent(ABC):
    """Base class for step agents in Agent-as-Step architecture

    Subclasses should define INPUT_SCHEMA to specify their input requirements.
    This enables:
    1. Automatic input validation
    2. Documentation generation
    3. Workflow builder integration
    """

    # Subclasses should override this with their input schema
    INPUT_SCHEMA: InputSchema = InputSchema(
        fields={},
        description="Base agent with no specific input requirements"
    )

    def __init__(self, metadata: AgentMetadata):
        self.metadata = metadata
        self.is_initialized = False

    @classmethod
    def get_input_schema(cls) -> InputSchema:
        """Get input schema for this agent type

        Returns:
            InputSchema: The input schema definition
        """
        return cls.INPUT_SCHEMA

    @classmethod
    def get_schema_dict(cls) -> Dict[str, Any]:
        """Get input schema as a dict (for serialization)

        Returns:
            Dict: The input schema as a dictionary
        """
        return cls.INPUT_SCHEMA.model_dump()

    @classmethod
    def validate_against_schema(cls, input_data: Dict[str, Any], context_vars: Optional[Dict[str, Any]] = None) -> tuple[bool, Optional[str]]:
        """Validate input data against the INPUT_SCHEMA

        Args:
            input_data: The input data to validate
            context_vars: Optional context variables for evaluating required_when conditions

        Returns:
            Tuple of (is_valid, error_message)
        """
        schema = cls.INPUT_SCHEMA
        context_vars = context_vars or {}

        for field_name, field_schema in schema.fields.items():
            value = input_data.get(field_name)

            # Check required
            is_required = field_schema.required
            if field_schema.required_when:
                # Evaluate condition like "operation == 'store'"
                try:
                    is_required = cls._evaluate_condition(field_schema.required_when, input_data)
                except Exception as e:
                    logger.warning(f"Failed to evaluate required_when condition '{field_schema.required_when}': {e}")
                    is_required = False

            if is_required and value is None:
                return False, f"Required field '{field_name}' is missing"

            # Skip further validation if value is None and not required
            if value is None:
                continue

            # Check type
            if not cls._check_type(value, field_schema.type, field_schema.items_type):
                return False, f"Field '{field_name}' has wrong type: expected {field_schema.type}, got {type(value).__name__}"

            # Check enum
            if field_schema.enum is not None and value not in field_schema.enum:
                return False, f"Field '{field_name}' has invalid value '{value}', must be one of {field_schema.enum}"

        return True, None

    @staticmethod
    def _check_type(value: Any, expected_type: str, items_type: Optional[str] = None) -> bool:
        """Check if value matches expected type"""
        if expected_type == "any":
            return True

        type_map = {
            "str": str,
            "int": int,
            "float": (int, float),
            "bool": bool,
            "dict": dict,
            "list": list,
        }

        # Handle union types like "str|dict"
        if "|" in expected_type:
            return any(
                BaseStepAgent._check_type(value, t.strip(), items_type)
                for t in expected_type.split("|")
            )

        expected_python_type = type_map.get(expected_type)
        if expected_python_type is None:
            return True  # Unknown type, skip validation

        if not isinstance(value, expected_python_type):
            return False

        # Check list items type
        if expected_type == "list" and items_type and isinstance(value, list):
            return all(BaseStepAgent._check_type(item, items_type) for item in value)

        return True

    @staticmethod
    def _evaluate_condition(condition: str, data: Dict[str, Any]) -> bool:
        """Evaluate a simple condition like "operation == 'store'" """
        # Simple parser for conditions like "field == 'value'" or "field != 'value'"
        import re

        match = re.match(r"(\w+)\s*(==|!=)\s*['\"]?([^'\"]+)['\"]?", condition)
        if not match:
            return False

        field, operator, expected = match.groups()
        actual = data.get(field)

        if operator == "==":
            return actual == expected
        elif operator == "!=":
            return actual != expected

        return False

    @abstractmethod
    async def initialize(self, context: AgentContext) -> bool:
        """Initialize agent"""
        pass

    @abstractmethod
    async def execute(self, input_data: Any, context: AgentContext) -> Any:
        """Execute agent task"""
        pass

    async def validate_input(self, input_data: Any) -> bool:
        """Validate input data

        Default implementation uses INPUT_SCHEMA for validation.
        Subclasses can override for custom validation logic.
        """
        from ..core.schemas import AgentInput

        # Handle AgentInput wrapper
        if isinstance(input_data, AgentInput):
            input_data = input_data.data

        if not isinstance(input_data, dict):
            logger.error(f"Input validation failed: expected dict, got {type(input_data).__name__}")
            return False

        is_valid, error = self.validate_against_schema(input_data)
        if not is_valid:
            logger.error(f"Input validation failed: {error}")
        return is_valid

    async def cleanup(self, context: AgentContext) -> None:
        """Cleanup resources"""
        pass