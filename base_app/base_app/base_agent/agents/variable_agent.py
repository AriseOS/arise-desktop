"""
Variable Agent for handling simple variable operations without LLM
"""
import json
import re
import logging
from typing import Any, Dict, List, Optional, Union
from .base_agent import BaseStepAgent, AgentMetadata
from ..core.schemas import AgentOutput, AgentContext, AgentInput


class VariableAgent(BaseStepAgent):
    """
    Agent for handling variable operations without using LLM.
    Supports operations like set, merge, increment, extract, etc.
    """

    def __init__(self):
        """Initialize VariableAgent without LLM provider"""
        metadata = AgentMetadata(
            name="variable",
            description="Variable manipulation agent for set, merge, increment, and other operations without LLM"
        )
        super().__init__(metadata)
        self.provider = None  # No LLM needed
        self.logger = logging.getLogger(__name__)

    async def initialize(self, context: AgentContext) -> bool:
        """Initialize Variable Agent - no LLM needed"""
        return True  # Always ready since no LLM required

    async def validate_input(self, input_data: Any) -> bool:
        """Validate input data"""
        return True  # Basic validation, can be enhanced

    async def execute(self, input_data: Any, context: Any) -> Any:
        """Execute variable operation based on step configuration"""
        # Extract step_config from metadata
        if hasattr(input_data, 'step_metadata'):
            step_config = input_data.step_metadata.get('step_config', {})
            # Context is also in metadata
            if not context:
                context = input_data.step_metadata.get('context')
        else:
            # Fallback for direct dict input
            step_config = input_data.get('step_config', {}) if isinstance(input_data, dict) else {}

        # Debug logging
        self.logger.debug(f"VariableAgent step_config: {step_config}")
        operation = step_config.get('operation', 'set')

        try:
            if operation == 'set':
                result = await self._handle_set(step_config, context)
            elif operation == 'merge':
                result = await self._handle_merge(step_config, context)
            elif operation == 'increment':
                result = await self._handle_increment(step_config, context)
            elif operation == 'decrement':
                result = await self._handle_decrement(step_config, context)
            elif operation == 'extract':
                result = await self._handle_extract(step_config, context)
            elif operation == 'append':
                result = await self._handle_append(step_config, context)
            elif operation == 'update':
                result = await self._handle_update(step_config, context)
            elif operation == 'calculate':
                result = await self._handle_calculate(step_config, context)
            elif operation == 'condition_check':
                result = await self._handle_condition_check(step_config, context)
            else:
                raise ValueError(f"Unsupported operation: {operation}")

            # Wrap result in expected format for workflow engine
            output_data = {}
            if isinstance(result, dict):
                output_data = result
            else:
                # For non-dict results, use a default key
                output_data = {"result": result}

            return AgentOutput(
                success=True,
                data=output_data,
                message=f"Variable operation '{operation}' completed successfully"
            )

        except Exception as e:
            return AgentOutput(
                success=False,
                data={},
                message=f"Variable operation failed: {str(e)}"
            )

    async def _handle_set(self, step_config: Dict, context: Any) -> Dict:
        """Handle set operation - initialize variables"""
        data = step_config.get('data', {})
        self.logger.debug(f"VariableAgent _handle_set input data: {data}")

        # Resolve any variable references in data
        resolved_data = {}
        for key, value in data.items():
            resolved_data[key] = self._resolve_variable(value, context)

        self.logger.debug(f"VariableAgent _handle_set resolved data: {resolved_data}")
        return resolved_data

    async def _handle_merge(self, step_config: Dict, context: Any) -> Any:
        """Handle merge operation - merge arrays or objects"""
        source = self._resolve_variable(step_config.get('source'), context)
        data = self._resolve_variable(step_config.get('data'), context)

        if isinstance(source, list) and isinstance(data, list):
            return source + data
        elif isinstance(source, dict) and isinstance(data, dict):
            return {**source, **data}
        else:
            raise TypeError(f"Cannot merge {type(source)} with {type(data)}")

    async def _handle_increment(self, step_config: Dict, context: Any) -> Union[int, float]:
        """Handle increment operation"""
        source = self._resolve_variable(step_config.get('source'), context)
        value = step_config.get('value', 1)

        if not isinstance(source, (int, float)):
            raise TypeError(f"Cannot increment non-numeric value: {type(source)}")

        return source + value

    async def _handle_decrement(self, step_config: Dict, context: Any) -> Union[int, float]:
        """Handle decrement operation"""
        source = self._resolve_variable(step_config.get('source'), context)
        value = step_config.get('value', 1)

        if not isinstance(source, (int, float)):
            raise TypeError(f"Cannot decrement non-numeric value: {type(source)}")

        return source - value

    async def _handle_extract(self, step_config: Dict, context: Any) -> Any:
        """Handle extract operation - extract field from object"""
        source = self._resolve_variable(step_config.get('source'), context)
        field = step_config.get('field')

        if not field:
            raise ValueError("Field path is required for extract operation")

        # Support dot notation for nested fields
        fields = field.split('.')
        result = source

        for f in fields:
            if isinstance(result, dict):
                result = result.get(f)
            elif isinstance(result, list) and f.isdigit():
                idx = int(f)
                if idx < len(result):
                    result = result[idx]
                else:
                    result = None
            else:
                result = None

            if result is None:
                break

        return result

    async def _handle_append(self, step_config: Dict, context: Any) -> List:
        """Handle append operation - add item to array"""
        source = self._resolve_variable(step_config.get('source'), context)
        data = self._resolve_variable(step_config.get('data'), context)

        if not isinstance(source, list):
            raise TypeError(f"Cannot append to non-list: {type(source)}")

        result = source.copy()
        if isinstance(data, list):
            result.extend(data)
        else:
            result.append(data)

        return result

    async def _handle_update(self, step_config: Dict, context: Any) -> Dict:
        """Handle update operation - update object fields"""
        source = self._resolve_variable(step_config.get('source'), context)
        updates = self._resolve_variable(step_config.get('updates'), context)

        if not isinstance(source, dict):
            raise TypeError(f"Cannot update non-dict: {type(source)}")

        if not isinstance(updates, dict):
            raise TypeError(f"Updates must be a dict: {type(updates)}")

        result = source.copy()
        result.update(updates)
        return result

    async def _handle_calculate(self, step_config: Dict, context: Any) -> Union[int, float]:
        """Handle calculate operation - simple arithmetic"""
        expression = step_config.get('expression')
        if not expression:
            raise ValueError("Expression is required for calculate operation")

        # Resolve variables in expression
        resolved_expr = self._resolve_expression(expression, context)

        # Safe evaluation of simple arithmetic expressions
        # Only allow numbers, basic operators, and parentheses
        if not re.match(r'^[\d\s+\-*/()%.]+$', resolved_expr):
            raise ValueError(f"Invalid expression: {resolved_expr}")

        try:
            result = eval(resolved_expr)
            return result
        except Exception as e:
            raise ValueError(f"Failed to evaluate expression: {e}")

    async def _handle_condition_check(self, step_config: Dict, context: Any) -> Dict:
        """Handle condition check - evaluate condition and update has_next"""
        current_page = self._resolve_variable(step_config.get('current_page'), context)
        max_pages = self._resolve_variable(step_config.get('max_pages'), context)
        items_found = self._resolve_variable(step_config.get('items_found'), context)

        # Check if we should continue
        has_next = current_page < max_pages
        if items_found is not None and items_found == 0:
            has_next = False

        return {
            'current_page': current_page + 1,
            'has_next': has_next,
            'progress': f"Processed page {current_page}"
        }

    def _resolve_variable(self, value: Any, context: Any) -> Any:
        """Resolve variable references in value"""
        if not isinstance(value, str):
            return value

        # Check if it's a variable reference {{var}}
        if value.startswith('{{') and value.endswith('}}'):
            var_name = value[2:-2].strip()
            if context and hasattr(context, 'variables'):
                return context.variables.get(var_name, value)

        return value

    def _resolve_expression(self, expression: str, context: Any) -> str:
        """Resolve all variable references in an expression"""
        if not context or not hasattr(context, 'variables'):
            return expression

        # Find all {{var}} patterns
        pattern = r'\{\{([^}]+)\}\}'

        def replace_var(match):
            var_name = match.group(1).strip()
            value = context.variables.get(var_name)
            if value is None:
                return '0'  # Default to 0 for missing variables
            return str(value)

        return re.sub(pattern, replace_var, expression)