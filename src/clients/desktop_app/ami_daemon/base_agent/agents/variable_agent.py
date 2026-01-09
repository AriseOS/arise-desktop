"""
Variable Agent for handling simple variable operations without LLM

Supported operations:
- set: Initialize/combine variables (uses 'data' field)
- filter: Filter list by field condition (uses 'data' field)
- slice: Slice list by start/end index (uses 'data' field)
- extend: Extend list with new elements (uses 'data' for list, 'items' for new elements)

All operations use 'data' as the unified input field.
All operations output to {"result": ...} for consistent workflow mapping.
"""
import re
import logging
from typing import Any, Dict, List
from .base_agent import BaseStepAgent, AgentMetadata, InputSchema, FieldSchema
from ..core.schemas import AgentOutput, AgentContext, AgentInput


class VariableAgent(BaseStepAgent):
    """
    Agent for variable operations without LLM.

    Operations:
    - set: Initialize or combine data into a single object
    - filter: Filter list items by field matching
    - slice: Slice list from index or matching value
    - extend: Extend list with new elements

    All operations output to {"result": ...} for consistent workflow mapping.
    """

    INPUT_SCHEMA = InputSchema(
        description="Variable manipulation agent for set, filter, slice, extend operations (no LLM required)",
        fields={
            "operation": FieldSchema(
                type="str",
                required=True,
                enum=["set", "filter", "slice", "extend"],
                description="Operation type"
            ),
            "data": FieldSchema(
                type="any",
                required=True,
                description="Input data: dict for set, list for filter/slice/extend"
            ),
            "field": FieldSchema(
                type="str",
                required_when="operation == 'filter'",
                description="Field name to filter by"
            ),
            "contains": FieldSchema(
                type="str",
                required=False,
                description="Substring to match (for filter operation)"
            ),
            "equals": FieldSchema(
                type="any",
                required=False,
                description="Exact value to match (for filter operation)"
            ),
            "start": FieldSchema(
                type="int",
                required=False,
                description="Start index for slice operation"
            ),
            "end": FieldSchema(
                type="int",
                required=False,
                description="End index for slice operation"
            ),
            "start_value": FieldSchema(
                type="any",
                required=False,
                description="Value to match for finding slice start position"
            ),
            "match_field": FieldSchema(
                type="str",
                required=False,
                description="Field name to match start_value against"
            ),
            "items": FieldSchema(
                type="any",
                required=False,
                description="Items to add (for extend operation)"
            ),
        },
        examples=[
            {
                "operation": "set",
                "data": {"name": "John", "age": 30}
            },
            {
                "operation": "filter",
                "data": [{"name": "A", "price": 10}, {"name": "B", "price": 20}],
                "field": "price",
                "equals": 10
            },
            {
                "operation": "slice",
                "data": [1, 2, 3, 4, 5],
                "start": 1,
                "end": 4
            },
            {
                "operation": "extend",
                "data": [1, 2, 3],
                "items": [4, 5]
            }
        ]
    )

    def __init__(self):
        """Initialize VariableAgent without LLM provider"""
        metadata = AgentMetadata(
            name="variable",
            description="Variable manipulation agent for set, filter, slice, extend operations"
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
            elif operation == 'extend':
                result = await self._handle_extend(step_config, context)
            else:
                raise ValueError(f"Unsupported operation: {operation}. Supported: set, filter, slice, extend")

            # 统一契约：所有操作都输出到 {"result": ...}
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
            data: "{{all_items}}"
            field: "url"
            contains: "product"    # OR
            equals: "specific_value"

        Output: Filtered list
        """
        data = step_config.get('data')
        if data is None:
            raise ValueError("'data' field is required for filter operation")

        resolved_data = self._resolve_variable(data, context)

        if not isinstance(resolved_data, list):
            raise TypeError(f"Cannot filter non-list: {type(resolved_data)}")

        field = step_config.get('field')
        contains = step_config.get('contains')
        equals = step_config.get('equals')

        if not field:
            raise ValueError("Field is required for filter operation")

        result = []
        for item in resolved_data:
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
        Slice operation - slice list by start/end index or matching value.

        Usage (by index):
            operation: "slice"
            data: "{{all_items}}"
            start: 0
            end: 10

        Usage (by matching value):
            operation: "slice"
            data: "{{all_items}}"
            start_value: "https://example.com/item"
            match_field: "url"

        Output: Sliced list
        """
        data = step_config.get('data')
        if data is None:
            raise ValueError("'data' field is required for slice operation")

        resolved_data = self._resolve_variable(data, context)

        if not isinstance(resolved_data, list):
            raise TypeError(f"Cannot slice non-list: {type(resolved_data)}")

        # Method 1: Direct index slicing with start and/or end
        start = step_config.get('start')
        end = step_config.get('end')

        if start is not None or end is not None:
            start_idx = int(start) if start is not None else None
            end_idx = int(end) if end is not None else None
            return resolved_data[start_idx:end_idx]

        # Method 2: Find index by matching field value
        start_value = step_config.get('start_value')
        match_field = step_config.get('match_field')

        if start_value is not None:
            if not match_field:
                raise ValueError("match_field is required when using start_value")

            for idx, item in enumerate(resolved_data):
                if isinstance(item, dict):
                    field_value = item.get(match_field)
                else:
                    field_value = getattr(item, match_field, None)

                if str(field_value) == str(start_value):
                    return resolved_data[idx:]

            self.logger.warning(f"Could not find item with {match_field}={start_value}, returning original list")
            return resolved_data

        return resolved_data

    async def _handle_extend(self, step_config: Dict, context: Any) -> List:
        """
        Extend operation - extend list with new elements.

        Usage:
            operation: "extend"
            data: "{{all_items}}"
            items: "{{new_items}}"     # Can be single item or list

        Output: List with extended elements
        """
        data = step_config.get('data')
        if data is None:
            raise ValueError("'data' field is required for extend operation")

        resolved_data = self._resolve_variable(data, context)

        if not isinstance(resolved_data, list):
            raise TypeError(f"Cannot extend non-list: {type(resolved_data)}")

        items = step_config.get('items')
        if items is None:
            raise ValueError("'items' field is required for extend operation")

        resolved_items = self._resolve_variable(items, context)

        # Create new list (don't mutate original)
        result = list(resolved_data)

        # Extend with items (if items is a list, extend; otherwise append single item)
        if isinstance(resolved_items, list):
            result.extend(resolved_items)
        else:
            result.append(resolved_items)

        return result

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
