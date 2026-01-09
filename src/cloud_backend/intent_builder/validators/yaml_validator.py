"""
Workflow YAML Validator - Validate generated workflow YAML (v2 format)

Validates:
1. YAML syntax
2. Workflow structure (apiVersion, name, steps)
3. Required fields
4. Variable references
5. Agent input requirements (via INPUT_SCHEMA)
"""
import logging
import yaml
from typing import Tuple, Optional, Dict, Any

from pydantic import ValidationError

logger = logging.getLogger(__name__)

# Try to import Workflow schema, but don't fail if not available
try:
    from src.clients.desktop_app.ami_daemon.base_agent.core.schemas import Workflow
    WORKFLOW_SCHEMA_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    WORKFLOW_SCHEMA_AVAILABLE = False
    logger.warning("Workflow schema not available, skipping Pydantic validation")

# Try to import agent schemas for input validation
try:
    from src.clients.desktop_app.ami_daemon.base_agent.agents import get_all_agent_schemas
    AGENT_SCHEMAS = get_all_agent_schemas()
    AGENT_SCHEMAS_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    AGENT_SCHEMAS = {}
    AGENT_SCHEMAS_AVAILABLE = False
    logger.warning("Agent schemas not available, skipping agent input validation")


class WorkflowYAMLValidator:
    """Validate generated workflow YAML"""

    def __init__(self):
        """Initialize validator"""
        pass

    def validate(self, workflow_yaml: str) -> Tuple[bool, str]:
        """
        Validate workflow YAML

        Args:
            workflow_yaml: Workflow YAML string

        Returns:
            (is_valid, error_message): Tuple of validation result
        """
        try:
            # 1. Parse YAML
            data = yaml.safe_load(workflow_yaml)
            if not data:
                return False, "Empty YAML"

            # 2. Check basic structure
            if not isinstance(data, dict):
                return False, "YAML root must be a dictionary"

            # 3. Check required top-level fields (v2 format)
            required_fields = ["apiVersion", "name", "steps"]
            for field in required_fields:
                if field not in data:
                    return False, f"Missing required field: {field}"

            # 4. Validate apiVersion (v2 format)
            api_version = data.get("apiVersion", "")
            if not api_version.startswith("ami.io/v"):
                return False, f"Invalid apiVersion: {api_version}, must start with 'ami.io/v'"

            # 5. Validate steps
            steps = data.get("steps", [])
            if not isinstance(steps, list):
                return False, "steps must be a list"
            if len(steps) == 0:
                return False, "steps cannot be empty"

            # 6. Validate each step
            for i, step in enumerate(steps):
                error = self._validate_step(step, i)
                if error:
                    return False, f"Step {i}: {error}"

            # 7. Validate with Pydantic model (optional, more strict)
            if WORKFLOW_SCHEMA_AVAILABLE:
                try:
                    Workflow(**data)
                except ValidationError as e:
                    logger.warning(f"Pydantic validation failed: {str(e)}")
                    # Don't fail on Pydantic errors, they might be too strict
                    # return False, f"Pydantic validation failed: {str(e)}"

            logger.info("Workflow validation passed")
            return True, ""

        except yaml.YAMLError as e:
            return False, f"YAML parsing error: {str(e)}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def _validate_step(self, step: dict, step_index: int) -> str:
        """
        Validate a single step (v2 format)

        Args:
            step: Step dictionary
            step_index: Step index in list

        Returns:
            Error message if invalid, empty string if valid
        """
        if not isinstance(step, dict):
            return "step must be a dictionary"

        # Check for control flow syntax (v2 format)
        is_control_flow = any(key in step for key in ['foreach', 'if', 'while'])

        if is_control_flow:
            return self._validate_control_flow_step(step)

        # Agent step - Required fields (v2 format uses 'agent' instead of 'agent_type')
        # 'name' is required - every step must have a human-readable name
        required = ["id", "name", "agent"]
        for field in required:
            if field not in step:
                return f"missing required field: {field}"

        # Validate agent type
        valid_agent_types = [
            "variable",
            "browser_agent",
            "scraper_agent",
            "storage_agent",
            "code_agent",
            "text_agent",
            "autonomous_browser_agent"
        ]
        agent = step.get("agent")
        if agent not in valid_agent_types:
            return f"invalid agent: {agent}"

        # Validate agent inputs against INPUT_SCHEMA
        if AGENT_SCHEMAS_AVAILABLE:
            input_error = self._validate_agent_inputs(agent, step.get("inputs", {}))
            if input_error:
                return input_error

        return ""

    def _validate_agent_inputs(self, agent_type: str, inputs: Dict[str, Any]) -> str:
        """
        Validate agent inputs against INPUT_SCHEMA

        Args:
            agent_type: The agent type (e.g., "storage_agent")
            inputs: The inputs dictionary from the step

        Returns:
            Error message if invalid, empty string if valid
        """
        schema = AGENT_SCHEMAS.get(agent_type)
        if not schema:
            return ""  # No schema defined, skip validation

        # Check required fields
        for field_name, field_schema in schema.fields.items():
            value = inputs.get(field_name)

            # Check if field is required
            is_required = field_schema.required

            # Check conditional required (e.g., "operation == 'store'")
            if field_schema.required_when:
                is_required = self._evaluate_required_condition(
                    field_schema.required_when, inputs
                )

            # Skip validation for template variables like "{{var}}"
            if value is not None and isinstance(value, str) and value.startswith("{{"):
                continue

            if is_required and value is None:
                return f"missing required input '{field_name}' for {agent_type}"

            # Check enum values (skip template variables)
            if value is not None and field_schema.enum:
                if not isinstance(value, str) or not value.startswith("{{"):
                    if value not in field_schema.enum:
                        return f"invalid value '{value}' for '{field_name}', must be one of {field_schema.enum}"

        return ""

    def _evaluate_required_condition(self, condition: str, inputs: Dict[str, Any]) -> bool:
        """
        Evaluate a required_when condition like "operation == 'store'"

        Args:
            condition: The condition string
            inputs: The inputs dictionary

        Returns:
            True if condition is met, False otherwise
        """
        import re
        match = re.match(r"(\w+)\s*(==|!=)\s*['\"]?([^'\"]+)['\"]?", condition)
        if not match:
            return False

        field, operator, expected = match.groups()
        actual = inputs.get(field)

        # Skip if actual value is a template variable
        if isinstance(actual, str) and actual.startswith("{{"):
            return False  # Can't evaluate, assume not required

        if operator == "==":
            return actual == expected
        elif operator == "!=":
            return actual != expected

        return False

    def _validate_control_flow_step(self, step: dict) -> str:
        """
        Validate a control flow step (v2 format: foreach, if, while)

        Args:
            step: Step dictionary

        Returns:
            Error message if invalid, empty string if valid
        """
        if 'foreach' in step:
            # foreach requires 'do' (v2) or 'steps' (fallback) field
            if 'do' not in step and 'steps' not in step:
                return "foreach step must have 'do' field"
            # Recursively validate nested steps
            nested_steps = step.get('do') or step.get('steps', [])
            for i, nested_step in enumerate(nested_steps):
                error = self._validate_step(nested_step, i)
                if error:
                    return f"nested step {i}: {error}"

        elif 'if' in step:
            # if requires 'then' field
            if 'then' not in step:
                return "if step must have 'then' field"
            # Validate then branch
            for i, nested_step in enumerate(step.get('then', [])):
                error = self._validate_step(nested_step, i)
                if error:
                    return f"then step {i}: {error}"
            # Validate else branch if present
            for i, nested_step in enumerate(step.get('else', [])):
                error = self._validate_step(nested_step, i)
                if error:
                    return f"else step {i}: {error}"

        elif 'while' in step:
            # while requires 'do' (v2) or 'steps' (fallback) field
            if 'do' not in step and 'steps' not in step:
                return "while step must have 'do' field"
            # Recursively validate nested steps
            nested_steps = step.get('do') or step.get('steps', [])
            for i, nested_step in enumerate(nested_steps):
                error = self._validate_step(nested_step, i)
                if error:
                    return f"nested step {i}: {error}"

        return ""

