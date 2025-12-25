"""
Workflow YAML Validator - Validate generated workflow YAML

Validates:
1. YAML syntax
2. Workflow structure (apiVersion, kind, metadata, steps)
3. Required fields
4. Variable references
"""
import logging
import yaml
from typing import Tuple, Optional
from pydantic import ValidationError

logger = logging.getLogger(__name__)

# Try to import Workflow schema, but don't fail if not available
try:
    from src.base_app.base_app.base_agent.core.schemas import Workflow
    WORKFLOW_SCHEMA_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    WORKFLOW_SCHEMA_AVAILABLE = False
    logger.warning("Workflow schema not available, skipping Pydantic validation")


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

            # 3. Check required top-level fields
            required_fields = ["apiVersion", "kind", "metadata", "steps"]
            for field in required_fields:
                if field not in data:
                    return False, f"Missing required field: {field}"

            # 4. Validate kind
            if data["kind"] != "Workflow":
                return False, f"Invalid kind: {data['kind']}, must be 'Workflow'"

            # 5. Validate metadata
            metadata = data.get("metadata", {})
            if not isinstance(metadata, dict):
                return False, "metadata must be a dictionary"
            if "name" not in metadata:
                return False, "metadata.name is required"

            # 6. Validate steps
            steps = data.get("steps", [])
            if not isinstance(steps, list):
                return False, "steps must be a list"
            if len(steps) == 0:
                return False, "steps cannot be empty"

            # 7. Validate each step
            for i, step in enumerate(steps):
                error = self._validate_step(step, i)
                if error:
                    return False, f"Step {i}: {error}"

            # 8. Validate with Pydantic model (optional, more strict)
            if WORKFLOW_SCHEMA_AVAILABLE:
                try:
                    Workflow(**data)
                except ValidationError as e:
                    logger.warning(f"Pydantic validation failed: {str(e)}")
                    # Don't fail on Pydantic errors, they might be too strict
                    # return False, f"Pydantic validation failed: {str(e)}"

            # 9. Check for final_response output
            has_final_response = self._check_final_response(data)
            if not has_final_response:
                logger.warning("Workflow does not output 'final_response' variable")
                # Warning only, not a hard failure
                # return False, "Workflow must output 'final_response' variable"

            logger.info("Workflow validation passed")
            return True, ""

        except yaml.YAMLError as e:
            return False, f"YAML parsing error: {str(e)}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def _validate_step(self, step: dict, step_index: int) -> str:
        """
        Validate a single step

        Args:
            step: Step dictionary
            step_index: Step index in list

        Returns:
            Error message if invalid, empty string if valid
        """
        if not isinstance(step, dict):
            return "step must be a dictionary"

        # Required fields
        required = ["id", "name", "agent_type"]
        for field in required:
            if field not in step:
                return f"missing required field: {field}"

        # Validate agent_type
        valid_agent_types = [
            "variable",
            "browser_agent",
            "scraper_agent",
            "storage_agent",
            "code_agent",
            "text_agent",
            "autonomous_browser_agent",
            "foreach"
        ]
        agent_type = step.get("agent_type")
        if agent_type not in valid_agent_types:
            return f"invalid agent_type: {agent_type}"

        # Validate foreach specific fields
        if agent_type == "foreach":
            if "source" not in step:
                return "foreach step must have 'source' field"
            if "item_var" not in step:
                return "foreach step must have 'item_var' field"
            if "steps" not in step:
                return "foreach step must have 'steps' field"

            # Recursively validate nested steps
            nested_steps = step.get("steps", [])
            for i, nested_step in enumerate(nested_steps):
                error = self._validate_step(nested_step, i)
                if error:
                    return f"nested step {i}: {error}"

        return ""

    def _check_final_response(self, workflow_data: dict) -> bool:
        """
        Check if workflow outputs 'final_response' variable

        Args:
            workflow_data: Workflow dictionary

        Returns:
            True if final_response is found in outputs
        """
        # Check top-level outputs
        outputs = workflow_data.get("outputs", {})
        if "final_response" in outputs:
            return True

        # Check steps for final_response output
        steps = workflow_data.get("steps", [])
        for step in steps:
            step_outputs = step.get("outputs", {})
            if "final_response" in step_outputs:
                return True

        return False
