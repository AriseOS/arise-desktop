"""
Variable Agent for handling simple variable operations without LLM

Supported operations:
- set: Initialize/combine variables
- filter: Filter list by field condition
- slice: Slice list by index or matching value
"""
import re
import logging
from typing import Any, Dict, List
from .base_agent import BaseStepAgent, AgentMetadata
from ..core.schemas import AgentOutput, AgentContext, AgentInput


class VariableAgent(BaseStepAgent):
    """
    Agent for variable operations without LLM.

    Operations:
    - set: Initialize or combine data into a single object
    - filter: Filter list items by field matching
    - slice: Slice list from index or matching value

    All operations output to {"result": ...} for consistent workflow mapping.
    """

    def __init__(self):
        """Initialize VariableAgent without LLM provider"""
        metadata = AgentMetadata(
            name="variable",
            description="Variable manipulation agent for set, filter, slice operations"
        )
        super().__init__(metadata)
        self.provider = None  # No LLM needed
        self.logger = logging.getLogger(__name__)

    async def initialize(self, context: AgentContext) -> bool:
        """Initialize Variable Agent - no LLM needed"""
        return True

    async def validate_input(self, input_data: Any) -> bool:
        """Validate input data"""
        return True

    async def execute(self, input_data: Any, context: Any) -> Any:
        """Execute variable operation based on step configuration"""
        # Extract step_config from metadata
        if hasattr(input_data, 'step_metadata'):
            step_config = input_data.step_metadata.get('step_config', {})
            if not context:
                context = input_data.step_metadata.get('context')
        else:
            step_config = input_data.get('step_config', {}) if isinstance(input_data, dict) else {}

        self.logger.debug(f"VariableAgent step_config: {step_config}")
        operation = step_config.get('operation', 'set')

        try:
            if operation == 'set':
                result = await self._handle_set(step_config, context)
            elif operation == 'filter':
                result = await self._handle_filter(step_config, context)
            elif operation == 'slice':
                result = await self._handle_slice(step_config, context)
            else:
                raise ValueError(f"Unsupported operation: {operation}. Supported: set, filter, slice")

            # ALWAYS wrap result in {"result": ...} for consistent output mapping
            return AgentOutput(
                success=True,
                data={"result": result},
                message=f"Variable operation '{operation}' completed successfully"
            )

        except Exception as e:
            return AgentOutput(
                success=False,
                data={},
                message=f"Variable operation failed: {str(e)}"
            )

    async def _handle_set(self, step_config: Dict, context: Any) -> Any:
        """
        Set operation - initialize or combine variables.

        Usage:
            operation: "set"
            data:
              url: "{{product.url}}"
              name: "{{details.0.name}}"
              price: "{{details.0.price}}"

        Output: The resolved data object
        """
        data = step_config.get('data', {})
        self.logger.debug(f"VariableAgent _handle_set input data: {data}")

        resolved_data = self._resolve_variable(data, context)

        self.logger.debug(f"VariableAgent _handle_set resolved data: {resolved_data}")
        return resolved_data

    async def _handle_filter(self, step_config: Dict, context: Any) -> List:
        """
        Filter operation - filter list by field condition.

        Usage:
            operation: "filter"
            source: "{{all_items}}"
            field: "url"
            contains: "product"    # OR
            equals: "specific_value"

        Output: Filtered list
        """
        source = self._resolve_variable(step_config.get('source'), context)

        if not isinstance(source, list):
            raise TypeError(f"Cannot filter non-list: {type(source)}")

        field = step_config.get('field')
        contains = step_config.get('contains')
        equals = step_config.get('equals')

        if not field:
            raise ValueError("Field is required for filter operation")

        result = []
        for item in source:
            if isinstance(item, dict):
                field_value = item.get(field)
            else:
                field_value = getattr(item, field, None)

            if field_value is None:
                continue

            if equals is not None:
                if str(field_value) == str(equals):
                    result.append(item)
            elif contains is not None:
                if str(contains) in str(field_value):
                    result.append(item)

        return result

    async def _handle_slice(self, step_config: Dict, context: Any) -> List:
        """
        Slice operation - slice list from index or matching value.

        Usage (by index):
            operation: "slice"
            source: "{{all_items}}"
            start: 10

        Usage (by matching value):
            operation: "slice"
            source: "{{all_items}}"
            start_value: "https://example.com/item"
            match_field: "url"

        Output: Sliced list
        """
        source = self._resolve_variable(step_config.get('source'), context)

        if not isinstance(source, list):
            raise TypeError(f"Cannot slice non-list: {type(source)}")

        # Method 1: Direct index
        start = step_config.get('start')
        if start is not None:
            return source[int(start):]

        # Method 2: Find index by matching field value
        start_value = step_config.get('start_value')
        match_field = step_config.get('match_field')

        if start_value is not None:
            if not match_field:
                raise ValueError("match_field is required when using start_value")

            for idx, item in enumerate(source):
                if isinstance(item, dict):
                    field_value = item.get(match_field)
                else:
                    field_value = getattr(item, match_field, None)

                if str(field_value) == str(start_value):
                    return source[idx:]

            self.logger.warning(f"Could not find item with {match_field}={start_value}, returning original list")
            return source

        return source

    def _resolve_variable(self, value: Any, context: Any) -> Any:
        """Resolve variable references like {{var}} or {{var.field}}"""
        # Handle dictionaries recursively
        if isinstance(value, dict):
            return {k: self._resolve_variable(v, context) for k, v in value.items()}

        # Handle lists recursively
        if isinstance(value, list):
            return [self._resolve_variable(item, context) for item in value]

        # Handle strings with variable references
        if not isinstance(value, str):
            return value

        # Complete variable reference {{var}} or {{var.field}}
        if value.startswith('{{') and value.endswith('}}') and value.count('{{') == 1:
            var_expression = value[2:-2].strip()
            if context and hasattr(context, 'variables'):
                parts = var_expression.split('.')
                result = context.variables.get(parts[0])

                if result is None:
                    return value

                for part in parts[1:]:
                    if isinstance(result, dict):
                        result = result.get(part)
                    elif isinstance(result, list) and part.isdigit():
                        idx = int(part)
                        result = result[idx] if idx < len(result) else None
                    elif hasattr(result, part):
                        result = getattr(result, part)
                    else:
                        return value

                    if result is None:
                        return value

                return result

        # String interpolation "text {{var}} more text"
        if '{{' in value and '}}' in value:
            if context and hasattr(context, 'variables'):
                pattern = r'\{\{([^}]+)\}\}'

                def replace_var(match):
                    var_expression = match.group(1).strip()
                    parts = var_expression.split('.')
                    result = context.variables.get(parts[0])

                    if result is None:
                        return match.group(0)

                    for part in parts[1:]:
                        if isinstance(result, dict):
                            result = result.get(part)
                        elif isinstance(result, list) and part.isdigit():
                            idx = int(part)
                            result = result[idx] if idx < len(result) else None
                        elif hasattr(result, part):
                            result = getattr(result, part)
                        else:
                            return match.group(0)

                        if result is None:
                            return match.group(0)

                    return str(result)

                return re.sub(pattern, replace_var, value)

        return value
