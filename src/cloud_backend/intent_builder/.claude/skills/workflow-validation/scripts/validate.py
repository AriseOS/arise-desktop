#!/usr/bin/env python3
"""
Workflow Validation Script for Claude Agent

Usage:
    python validate.py workflow.yaml
    python validate.py -              # Read from stdin
    echo 'yaml content' | python validate.py -

Validates workflow YAML and prints human-readable results.
"""

import sys
import re
import yaml
from typing import Dict, List, Any, Set, Tuple
from dataclasses import dataclass, field


# Valid agent types (must match BaseApp's supported types)
# See: agent_workflow_engine.py _register_builtin_agents()
VALID_AGENT_TYPES = {
    "browser_agent",
    "scraper_agent",
    "storage_agent",
    "variable",
    "foreach",
    "if",
    "while",
    "text_agent",
    "code_agent",
    "tool_agent",
    "autonomous_browser_agent",
}

# Required fields at different levels
REQUIRED_ROOT_FIELDS = ["apiVersion", "kind", "metadata", "steps"]
REQUIRED_METADATA_FIELDS = ["name", "description"]

# Agent-specific required fields
# Format: { agent_type: { "step": [...], "inputs": [...] } }
# - "step": fields required at step level
# - "inputs": fields required inside step.inputs
AGENT_SPECIFIC_FIELDS = {
    "code_agent": {"step": ["code"], "inputs": []},
    "text_agent": {"step": [], "inputs": ["instruction"]},  # instruction is inside inputs
    "variable": {"step": [], "inputs": []},
    "scraper_agent": {"step": [], "inputs": []},
    "browser_agent": {"step": [], "inputs": []},
    "storage_agent": {"step": [], "inputs": []},
    "tool_agent": {"step": [], "inputs": []},
    "foreach": {"step": ["source", "steps"], "inputs": []},
    "if": {"step": ["condition", "then"], "inputs": []},
    "while": {"step": ["condition", "steps"], "inputs": []},
}


@dataclass
class ValidationResult:
    """Result of workflow validation"""
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_string(self) -> str:
        """Convert to human-readable string"""
        if self.valid and not self.warnings:
            return "VALIDATION PASSED"

        parts = []
        if not self.valid:
            parts.append("VALIDATION FAILED")
            parts.append(f"Errors ({len(self.errors)}):")
            for i, error in enumerate(self.errors, 1):
                parts.append(f"  {i}. {error}")

        if self.warnings:
            parts.append(f"Warnings ({len(self.warnings)}):")
            for i, warning in enumerate(self.warnings, 1):
                parts.append(f"  {i}. {warning}")

        if self.valid:
            parts.insert(0, "VALIDATION PASSED (with warnings)")

        return "\n".join(parts)


class RuleValidator:
    """Rule-based workflow validator"""

    def validate(self, workflow: Dict[str, Any]) -> ValidationResult:
        errors = []
        warnings = []

        # 1. Check required root fields
        errors.extend(self._check_required_fields(workflow))

        # 2. Check metadata fields
        if "metadata" in workflow:
            errors.extend(self._check_metadata(workflow["metadata"]))

        # 3. Check agent types
        errors.extend(self._check_agent_types(workflow))

        # 4. Check variable references
        var_errors, var_warnings = self._check_variables(workflow)
        errors.extend(var_errors)
        warnings.extend(var_warnings)

        # 5. Check control flow structures
        errors.extend(self._check_control_flow_structure(workflow))

        # 6. Check agent-specific required fields
        errors.extend(self._check_agent_specific_fields(workflow))

        # 7. Check step IDs are unique
        errors.extend(self._check_unique_step_ids(workflow))

        # 8. Check final_response requirement
        fr_errors, fr_warnings = self._check_final_response(workflow)
        errors.extend(fr_errors)
        warnings.extend(fr_warnings)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def _check_required_fields(self, workflow: Dict) -> List[str]:
        errors = []
        for f in REQUIRED_ROOT_FIELDS:
            if f not in workflow:
                errors.append(f"Missing required field: '{f}'")
        return errors

    def _check_metadata(self, metadata: Dict) -> List[str]:
        errors = []
        for f in REQUIRED_METADATA_FIELDS:
            if f not in metadata:
                errors.append(f"Missing required field: 'metadata.{f}'")
        return errors

    def _check_agent_types(self, workflow: Dict) -> List[str]:
        errors = []
        steps = workflow.get("steps", [])

        def check_steps(steps: List[Dict], path: str = "steps"):
            for i, step in enumerate(steps):
                step_path = f"{path}[{i}]"
                step_id = step.get("id", f"index_{i}")
                agent_type = step.get("agent_type")

                if agent_type is None:
                    if "control_type" not in step:
                        errors.append(f"Step '{step_id}' at {step_path} missing 'agent_type'")
                elif agent_type not in VALID_AGENT_TYPES:
                    errors.append(
                        f"Invalid agent_type '{agent_type}' at step '{step_id}'. "
                        f"Valid types: {', '.join(sorted(VALID_AGENT_TYPES))}"
                    )

                if agent_type == "foreach" and "steps" in step:
                    check_steps(step["steps"], f"{step_path}.steps")
                if "then_steps" in step:
                    check_steps(step["then_steps"], f"{step_path}.then_steps")
                if "else_steps" in step:
                    check_steps(step["else_steps"], f"{step_path}.else_steps")

        check_steps(steps)
        return errors

    def _check_variables(self, workflow: Dict) -> Tuple[List[str], List[str]]:
        errors = []
        warnings = []
        defined_vars: Set[str] = set()

        for var_name in workflow.get("inputs", {}).keys():
            defined_vars.add(var_name)

        steps = workflow.get("steps", [])
        self._check_steps_variables(steps, defined_vars, errors, warnings, set())

        return errors, warnings

    def _check_steps_variables(
        self,
        steps: List[Dict],
        defined_vars: Set[str],
        errors: List[str],
        warnings: List[str],
        loop_vars: Set[str]
    ):
        for step in steps:
            step_id = step.get("id", "unknown")
            agent_type = step.get("agent_type")

            self._check_var_references(
                step.get("inputs", {}),
                defined_vars | loop_vars,
                errors,
                f"step '{step_id}' inputs"
            )

            if "condition" in step:
                self._check_var_references(
                    step["condition"],
                    defined_vars | loop_vars,
                    errors,
                    f"step '{step_id}' condition"
                )

            for var_name in step.get("outputs", {}).values():
                if isinstance(var_name, str):
                    defined_vars.add(var_name)

            if agent_type == "foreach":
                item_var = step.get("item_var", "item")
                index_var = step.get("index_var", "index")
                source = step.get("source", "")

                self._check_var_references(
                    {"source": source},
                    defined_vars | loop_vars,
                    errors,
                    f"step '{step_id}' foreach source"
                )

                new_loop_vars = loop_vars | {item_var, index_var}
                if "steps" in step:
                    self._check_steps_variables(
                        step["steps"],
                        defined_vars.copy(),
                        errors,
                        warnings,
                        new_loop_vars
                    )

            if "then_steps" in step:
                self._check_steps_variables(
                    step["then_steps"],
                    defined_vars.copy(),
                    errors,
                    warnings,
                    loop_vars
                )
            if "else_steps" in step:
                self._check_steps_variables(
                    step["else_steps"],
                    defined_vars.copy(),
                    errors,
                    warnings,
                    loop_vars
                )

    def _check_var_references(
        self,
        obj: Any,
        defined_vars: Set[str],
        errors: List[str],
        context: str
    ):
        if isinstance(obj, str):
            refs = re.findall(r'\{\{(\w+)(?:[\.\[\]\w]*)*\}\}', obj)
            for var_name in refs:
                if var_name not in defined_vars:
                    errors.append(
                        f"Undefined variable '{{{{{var_name}}}}}' referenced in {context}"
                    )
        elif isinstance(obj, dict):
            for value in obj.values():
                self._check_var_references(value, defined_vars, errors, context)
        elif isinstance(obj, list):
            for item in obj:
                self._check_var_references(item, defined_vars, errors, context)

    def _check_control_flow_structure(self, workflow: Dict) -> List[str]:
        errors = []
        steps = workflow.get("steps", [])

        def check_steps(steps: List[Dict], path: str = "steps"):
            for i, step in enumerate(steps):
                step_path = f"{path}[{i}]"
                step_id = step.get("id", f"index_{i}")
                agent_type = step.get("agent_type")

                if agent_type == "foreach":
                    if "source" not in step:
                        errors.append(
                            f"foreach step '{step_id}' at {step_path} missing required 'source' field"
                        )
                    if "steps" not in step:
                        errors.append(
                            f"foreach step '{step_id}' at {step_path} missing required 'steps' field"
                        )
                    else:
                        check_steps(step["steps"], f"{step_path}.steps")

                elif agent_type == "if":
                    if "condition" not in step:
                        errors.append(
                            f"if step '{step_id}' at {step_path} missing required 'condition' field"
                        )
                    if "then" not in step and "then_steps" not in step:
                        errors.append(
                            f"if step '{step_id}' at {step_path} missing required 'then' field"
                        )
                    if "then" in step:
                        check_steps(step["then"], f"{step_path}.then")
                    if "then_steps" in step:
                        check_steps(step["then_steps"], f"{step_path}.then_steps")
                    if "else" in step:
                        check_steps(step["else"], f"{step_path}.else")
                    if "else_steps" in step:
                        check_steps(step["else_steps"], f"{step_path}.else_steps")

                elif agent_type == "while":
                    if "condition" not in step:
                        errors.append(
                            f"while step '{step_id}' at {step_path} missing required 'condition' field"
                        )
                    if "steps" not in step:
                        errors.append(
                            f"while step '{step_id}' at {step_path} missing required 'steps' field"
                        )
                    else:
                        check_steps(step["steps"], f"{step_path}.steps")

        check_steps(steps)
        return errors

    def _check_agent_specific_fields(self, workflow: Dict) -> List[str]:
        errors = []
        steps = workflow.get("steps", [])

        def check_steps(steps: List[Dict], path: str = "steps"):
            for i, step in enumerate(steps):
                step_path = f"{path}[{i}]"
                step_id = step.get("id", f"index_{i}")
                agent_type = step.get("agent_type")

                if agent_type in AGENT_SPECIFIC_FIELDS:
                    field_config = AGENT_SPECIFIC_FIELDS[agent_type]

                    # Check step-level required fields
                    for f in field_config.get("step", []):
                        if f not in step:
                            errors.append(
                                f"Step '{step_id}' ({agent_type}) at {step_path} missing required '{f}' field"
                            )

                    # Check inputs-level required fields
                    step_inputs = step.get("inputs", {})
                    for f in field_config.get("inputs", []):
                        if f not in step_inputs:
                            errors.append(
                                f"Step '{step_id}' ({agent_type}) at {step_path} missing required 'inputs.{f}' field"
                            )

                if "steps" in step:
                    check_steps(step["steps"], f"{step_path}.steps")
                if "then" in step:
                    check_steps(step["then"], f"{step_path}.then")
                if "then_steps" in step:
                    check_steps(step["then_steps"], f"{step_path}.then_steps")
                if "else" in step:
                    check_steps(step["else"], f"{step_path}.else")
                if "else_steps" in step:
                    check_steps(step["else_steps"], f"{step_path}.else_steps")

        check_steps(steps)
        return errors

    def _check_final_response(self, workflow: Dict) -> Tuple[List[str], List[str]]:
        errors = []
        warnings = []
        steps = workflow.get("steps", [])

        def has_final_response(steps: List[Dict]) -> bool:
            for step in steps:
                outputs = step.get("outputs", {})
                if isinstance(outputs, dict):
                    if "final_response" in outputs.values():
                        return True

                if "steps" in step and has_final_response(step["steps"]):
                    return True
                if "then" in step and has_final_response(step["then"]):
                    return True
                if "then_steps" in step and has_final_response(step["then_steps"]):
                    return True
                if "else" in step and has_final_response(step["else"]):
                    return True
                if "else_steps" in step and has_final_response(step["else_steps"]):
                    return True

            return False

        if not has_final_response(steps):
            warnings.append(
                "No step outputs 'final_response'. Workflow may not return a result."
            )

        return errors, warnings

    def _check_unique_step_ids(self, workflow: Dict) -> List[str]:
        errors = []
        seen_ids: Set[str] = set()
        steps = workflow.get("steps", [])

        def collect_ids(steps: List[Dict], path: str = "steps"):
            for i, step in enumerate(steps):
                step_id = step.get("id")
                step_path = f"{path}[{i}]"

                if step_id:
                    if step_id in seen_ids:
                        errors.append(f"Duplicate step id '{step_id}' at {step_path}")
                    else:
                        seen_ids.add(step_id)

                if "steps" in step:
                    collect_ids(step["steps"], f"{step_path}.steps")
                if "then_steps" in step:
                    collect_ids(step["then_steps"], f"{step_path}.then_steps")
                if "else_steps" in step:
                    collect_ids(step["else_steps"], f"{step_path}.else_steps")

        collect_ids(steps)
        return errors


def validate_yaml(yaml_content: str) -> str:
    """Validate YAML content and return result string."""
    try:
        workflow = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        return f"YAML parse error: {e}"

    if not isinstance(workflow, dict):
        return "Invalid workflow: expected a YAML dictionary/object"

    validator = RuleValidator()
    result = validator.validate(workflow)
    return result.to_string()


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate.py <workflow.yaml>")
        print("       python validate.py -  # Read from stdin")
        sys.exit(1)

    filepath = sys.argv[1]

    if filepath == "-":
        yaml_content = sys.stdin.read()
    else:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                yaml_content = f.read()
        except FileNotFoundError:
            print(f"Error: File not found: {filepath}")
            sys.exit(1)
        except Exception as e:
            print(f"Error reading file: {e}")
            sys.exit(1)

    result = validate_yaml(yaml_content)
    print(result)

    if "VALIDATION FAILED" in result:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
