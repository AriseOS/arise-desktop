"""
Workflow Configuration Loader
Supports v2 YAML format workflow configuration files.

v2 format features:
  - apiVersion: "ami.io/v2"
  - name and description at top level
  - steps use 'agent' field
  - foreach/if/while use dedicated keys (foreach:, if:, while:)
"""
import yaml
import json
import re
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List, Union, Optional
from enum import Enum

from ..core.schemas import AgentWorkflowStep, Workflow


logger = logging.getLogger(__name__)


class WorkflowVersion(str, Enum):
    """Workflow format version"""
    V1 = "v1"
    V2 = "v2"


def get_workflows_base_dir() -> Path:
    """Get workflows base directory (supports PyInstaller)"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / 'base_app' / 'base_agent' / 'workflows'
    else:
        return Path(__file__).parent


class WorkflowFormat(str, Enum):
    """Supported workflow configuration file formats"""
    YAML = "yaml"
    JSON = "json"


class ConditionEvaluator:
    """
    Condition expression evaluator.

    Supports operators: ==, !=, >, <, >=, <=, and, or, not
    Supports variable references: {{var}}, {{item.field}}

    The expression parameter can be:
    - str: Expression to evaluate (e.g., "{{var}} > 0", "{{flag}}")
    - bool: Already resolved boolean value (from workflow variable resolution)
    - int/float: Numeric values (truthy evaluation)
    - list/dict: Collection values (truthy if non-empty)
    - None: Evaluates to False
    """

    SAFE_BUILTINS = {
        "True": True,
        "False": False,
        "None": None,
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
    }

    def evaluate(self, expression: Any, variables: Dict[str, Any]) -> bool:
        """Evaluate a condition expression.

        Args:
            expression: Condition to evaluate. Can be a string expression,
                or a pre-resolved value (bool, int, list, etc.) from
                workflow variable resolution.
            variables: Context variables for resolving {{var}} references.

        Returns:
            bool: Evaluation result.
        """
        # Handle pre-resolved values (from _resolve_step_variables)
        if isinstance(expression, bool):
            return expression

        if expression is None:
            return False

        if not isinstance(expression, str):
            # int, float, list, dict, etc. - use Python truthy rules
            return bool(expression)

        # Empty or whitespace-only string
        if not expression.strip():
            return False

        # String expression - resolve variables and evaluate
        try:
            resolved = self._resolve_variables(expression, variables)
            result = eval(resolved, {"__builtins__": {}}, {**self.SAFE_BUILTINS, **variables})
            return bool(result)
        except Exception as e:
            logger.warning(f"Condition evaluation failed: {expression}, error: {e}")
            return False

    def _resolve_variables(self, expression: str, variables: Dict[str, Any]) -> str:
        """Resolve {{variable}} and {{item.field}} references in expression."""
        def replace_var(match):
            var_path = match.group(1).strip()
            parts = var_path.split('.')

            value = variables.get(parts[0])
            if value is None:
                return "None"

            for part in parts[1:]:
                if isinstance(value, dict):
                    value = value.get(part)
                elif hasattr(value, part):
                    value = getattr(value, part)
                else:
                    value = None
                if value is None:
                    return "None"

            if isinstance(value, str):
                escaped = value.replace("\\", "\\\\").replace("'", "\\'")
                return f"'{escaped}'"
            elif isinstance(value, bool):
                return "True" if value else "False"
            elif value is None:
                return "None"
            elif isinstance(value, (list, dict)):
                return repr(value)
            else:
                return str(value)

        return re.sub(r'\{\{([^}]+)\}\}', replace_var, expression)


class WorkflowValidator:
    """Workflow configuration validator (v2 format)"""

    VALID_AGENT_TYPES = [
        'text_agent', 'variable', 'scraper_agent',
        'browser_agent', 'storage_agent',
        'autonomous_browser_agent', 'tavily_agent',
        'if', 'while', 'foreach'
    ]

    CONTROL_FLOW_KEYS = ['if', 'while', 'foreach']

    def validate(self, config: Dict[str, Any], version: WorkflowVersion) -> List[str]:
        """Validate configuration file, return list of errors"""
        errors = []

        api_version = config.get('apiVersion', '')
        if not api_version.startswith('ami.io/v'):
            errors.append("apiVersion must start with 'ami.io/v'")

        if version == WorkflowVersion.V1:
            errors.append("v1 format is no longer supported")
        else:
            errors.extend(self._validate_v2(config))

        return errors

    def _validate_v2(self, config: Dict[str, Any]) -> List[str]:
        """Validate v2 format"""
        errors = []

        if 'name' not in config:
            errors.append("v2 format requires top-level 'name' field")

        if 'steps' not in config:
            errors.append("Missing required field: steps")
        elif not isinstance(config['steps'], list) or len(config['steps']) == 0:
            errors.append("steps must be a non-empty list")
        else:
            errors.extend(self._validate_steps_v2(config['steps']))

        return errors

    def _validate_steps_v2(self, steps: List[Dict], prefix: str = "steps") -> List[str]:
        """Validate v2 format steps"""
        errors = []
        step_ids = set()

        for i, step in enumerate(steps):
            step_prefix = f"{prefix}[{i}]"
            is_control_flow = any(key in step for key in self.CONTROL_FLOW_KEYS)

            if is_control_flow:
                errors.extend(self._validate_control_flow_step_v2(step, step_prefix))
            else:
                step_id = step.get('id')
                if step_id:
                    if step_id in step_ids:
                        errors.append(f"{step_prefix}: Duplicate step ID '{step_id}'")
                    step_ids.add(step_id)

                agent = step.get('agent')
                if not agent:
                    errors.append(f"{step_prefix}: Missing 'agent' field")
                elif agent not in self.VALID_AGENT_TYPES:
                    errors.append(f"{step_prefix}: Unsupported agent '{agent}'")

        return errors

    def _validate_control_flow_step_v2(self, step: Dict, prefix: str) -> List[str]:
        """Validate v2 control flow steps"""
        errors = []

        if 'foreach' in step:
            if 'do' not in step and 'steps' not in step:
                errors.append(f"{prefix}: foreach requires 'do' field")
            else:
                sub_steps = step.get('do') or step.get('steps', [])
                errors.extend(self._validate_steps_v2(sub_steps, f"{prefix}.do"))

        elif 'if' in step:
            if 'then' not in step:
                errors.append(f"{prefix}: if requires 'then' field")
            else:
                errors.extend(self._validate_steps_v2(step['then'], f"{prefix}.then"))
            if 'else' in step:
                errors.extend(self._validate_steps_v2(step['else'], f"{prefix}.else"))

        elif 'while' in step:
            if 'do' not in step and 'steps' not in step:
                errors.append(f"{prefix}: while requires 'do' field")
            else:
                sub_steps = step.get('do') or step.get('steps', [])
                errors.extend(self._validate_steps_v2(sub_steps, f"{prefix}.do"))

        return errors


class WorkflowConfigLoader:
    """Workflow configuration loader - v2 format with auto-detection"""

    def __init__(self):
        self.validator = WorkflowValidator()
        self.condition_evaluator = ConditionEvaluator()

    def detect_version(self, config: Dict[str, Any]) -> WorkflowVersion:
        """Detect workflow configuration version"""
        api_version = config.get('apiVersion', '')
        if 'v2' in api_version:
            return WorkflowVersion.V2

        if 'metadata' in config and 'kind' in config:
            return WorkflowVersion.V1

        if 'name' in config and 'metadata' not in config:
            return WorkflowVersion.V2

        return WorkflowVersion.V1

    def load_from_string(
        self,
        yaml_content: str,
        workflow_name: Optional[str] = None,
        workflow_id: Optional[str] = None
    ) -> Workflow:
        """Load workflow from YAML string"""
        config = yaml.safe_load(yaml_content)
        if not config:
            raise ValueError("Empty YAML configuration")

        return self._load_from_config(config, workflow_name, workflow_id)

    def load_from_file(self, file_path: Union[str, Path]) -> Workflow:
        """Load workflow from configuration file"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Workflow configuration file not found: {file_path}")

        config = self._parse_file(path)
        return self._load_from_config(config)

    def _load_from_config(
        self,
        config: Dict[str, Any],
        fallback_name: Optional[str] = None,
        workflow_id: Optional[str] = None
    ) -> Workflow:
        """Load workflow from configuration dict (internal)"""
        version = self.detect_version(config)
        logger.info(f"Detected workflow version: {version.value}")

        errors = self.validator.validate(config, version)
        if errors:
            error_msg = f"Configuration validation failed ({version.value}):\n" + "\n".join(f"- {error}" for error in errors)
            raise ValueError(error_msg)

        if version == WorkflowVersion.V1:
            raise ValueError(
                "v1 format is no longer supported. Please upgrade to v2 format:\n"
                "- Remove 'kind: Workflow' and 'metadata' container\n"
                "- Move 'metadata.name' to top-level 'name'\n"
                "- Change 'agent_type' to 'agent'\n"
                "- Change foreach/if/while from agent_type values to dedicated keys"
            )
        else:
            return self._create_workflow_from_v2(config, workflow_id)

    def load_builtin_workflow(self, workflow_name: str) -> Workflow:
        """Load built-in workflow"""
        workflows_dir = get_workflows_base_dir()
        builtin_dir = workflows_dir / "builtin"
        workflow_file = builtin_dir / f"{workflow_name}.yaml"

        if not workflow_file.exists():
            for ext in ['.yml', '.json']:
                alt_file = builtin_dir / f"{workflow_name}{ext}"
                if alt_file.exists():
                    workflow_file = alt_file
                    break
            else:
                raise FileNotFoundError(f"Built-in workflow '{workflow_name}' not found (searched: {builtin_dir})")

        return self.load_from_file(workflow_file)

    def load_user_workflow(self, workflow_name: str) -> Workflow:
        """Load user workflow"""
        workflows_dir = get_workflows_base_dir()
        user_dir = workflows_dir / "user"
        workflow_file = user_dir / f"{workflow_name}.yaml"

        if not workflow_file.exists():
            for ext in ['.yml', '.json']:
                alt_file = user_dir / f"{workflow_name}{ext}"
                if alt_file.exists():
                    workflow_file = alt_file
                    break
            else:
                raise FileNotFoundError(f"User workflow '{workflow_name}' not found (searched: {user_dir})")

        return self.load_from_file(workflow_file)

    def list_builtin_workflows(self) -> List[str]:
        """List all built-in workflows"""
        workflows_dir = get_workflows_base_dir()
        builtin_dir = workflows_dir / "builtin"
        if not builtin_dir.exists():
            return []

        workflows = []
        for file_path in builtin_dir.glob("*.yaml"):
            workflows.append(file_path.stem)
        for file_path in builtin_dir.glob("*.yml"):
            workflows.append(file_path.stem)
        for file_path in builtin_dir.glob("*.json"):
            workflows.append(file_path.stem)

        return sorted(set(workflows))

    def _parse_file(self, file_path: Path) -> Dict[str, Any]:
        """Parse configuration file"""
        format = self._detect_format(file_path)
        content = file_path.read_text(encoding='utf-8')

        if format == WorkflowFormat.YAML:
            return yaml.safe_load(content)
        elif format == WorkflowFormat.JSON:
            return json.loads(content)
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")

    def _detect_format(self, file_path: Path) -> WorkflowFormat:
        """Detect file format"""
        suffix = file_path.suffix.lower()

        if suffix in ['.yaml', '.yml']:
            return WorkflowFormat.YAML
        elif suffix in ['.json']:
            return WorkflowFormat.JSON
        else:
            content = file_path.read_text(encoding='utf-8').strip()
            if content.startswith('{'):
                return WorkflowFormat.JSON
            else:
                return WorkflowFormat.YAML

    def _create_workflow_from_v2(
        self,
        config: Dict[str, Any],
        workflow_id: Optional[str] = None
    ) -> Workflow:
        """Create workflow object from v2 format configuration"""
        name = config['name']
        description = config.get('description', '')

        steps = []
        for step_config in config['steps']:
            step = self._create_step_from_v2(step_config)
            steps.append(step)

        input_schema = {}
        if 'input' in config:
            input_name = config['input']
            input_schema = {input_name: {'type': 'string', 'required': True}}
        elif 'inputs' in config:
            raw_inputs = config['inputs']
            if isinstance(raw_inputs, dict):
                for k, v in raw_inputs.items():
                    if isinstance(v, str):
                        input_schema[k] = {'type': v, 'required': True}
                    else:
                        input_schema[k] = v

        workflow = Workflow(
            name=name,
            workflow_id=workflow_id,
            description=description,
            version='1.0.0',
            steps=steps,
            input_schema=input_schema,
            output_schema=config.get('outputs', {}),
            max_execution_time=config.get('config', {}).get('max_execution_time', 3600),
            enable_parallel=config.get('config', {}).get('enable_parallel', False),
            enable_cache=config.get('config', {}).get('enable_cache', True),
            tags=[],
            author='Ami'
        )

        return workflow

    def _create_step_from_v2(self, step_config: Dict[str, Any]) -> AgentWorkflowStep:
        """Create workflow step object from v2 format"""
        if 'foreach' in step_config:
            return self._create_foreach_step_v2(step_config)
        elif 'if' in step_config:
            return self._create_if_step_v2(step_config)
        elif 'while' in step_config:
            return self._create_while_step_v2(step_config)

        agent_type = step_config.get('agent', '')

        step = AgentWorkflowStep(
            id=step_config.get('id', ''),
            name=step_config.get('name', ''),
            description=step_config.get('description', ''),
            agent_type=agent_type,
            user_task=step_config.get('user_task')
        )

        step.inputs = step_config.get('inputs', {})
        step.outputs = step_config.get('outputs', {})

        if 'condition' in step_config:
            condition = step_config['condition']
            if isinstance(condition, dict) and 'expression' in condition:
                step.condition = condition['expression']
            elif isinstance(condition, str):
                step.condition = condition

        if agent_type == 'variable':
            inputs = step_config.get('inputs', {})
            step.operation = inputs.get('operation')
            step.data = inputs.get('data')
            step.source = inputs.get('source')
            step.field = inputs.get('field')
            step.value = inputs.get('value')
            step.expression = inputs.get('expression')
            step.updates = inputs.get('updates')
            step.current_page = inputs.get('current_page')
            step.max_pages = inputs.get('max_pages')
            step.items_found = inputs.get('items_found')

        return step

    def _create_foreach_step_v2(self, step_config: Dict[str, Any]) -> AgentWorkflowStep:
        """Create foreach control flow step (v2 format)"""
        source = step_config['foreach']
        item_var = step_config.get('as', 'item')
        sub_steps = step_config.get('do') or step_config.get('steps', [])

        step = AgentWorkflowStep(
            id=step_config.get('id', ''),
            name=step_config.get('name', f'foreach_{item_var}'),
            description=step_config.get('description', ''),
            agent_type='foreach',
            source=source,
            item_var=item_var,
            index_var=step_config.get('index_var', 'index'),
            max_iterations=step_config.get('max_iterations'),
            steps=[self._create_step_from_v2(s) for s in sub_steps]
        )
        return step

    def _create_if_step_v2(self, step_config: Dict[str, Any]) -> AgentWorkflowStep:
        """Create if control flow step (v2 format)"""
        condition = step_config['if']

        step = AgentWorkflowStep(
            id=step_config.get('id', ''),
            name=step_config.get('name', 'if_condition'),
            description=step_config.get('description', ''),
            agent_type='if',
            condition=condition,
            then=[self._create_step_from_v2(s) for s in step_config.get('then', [])],
            else_=[self._create_step_from_v2(s) for s in step_config.get('else', [])]
        )
        return step

    def _create_while_step_v2(self, step_config: Dict[str, Any]) -> AgentWorkflowStep:
        """Create while control flow step (v2 format)"""
        condition = step_config['while']
        sub_steps = step_config.get('do') or step_config.get('steps', [])

        step = AgentWorkflowStep(
            id=step_config.get('id', ''),
            name=step_config.get('name', 'while_loop'),
            description=step_config.get('description', ''),
            agent_type='while',
            condition=condition,
            max_iterations=step_config.get('max_iterations'),
            steps=[self._create_step_from_v2(s) for s in sub_steps]
        )
        return step


def load_workflow(workflow_name_or_path: str) -> Workflow:
    """
    Load workflow (convenience function)

    Args:
        workflow_name_or_path: Workflow name (built-in or user) or file path

    Returns:
        Workflow: Workflow object
    """
    loader = WorkflowConfigLoader()

    if '/' in workflow_name_or_path or '\\' in workflow_name_or_path or '.' in workflow_name_or_path:
        return loader.load_from_file(workflow_name_or_path)
    else:
        try:
            return loader.load_builtin_workflow(workflow_name_or_path)
        except FileNotFoundError:
            try:
                return loader.load_user_workflow(workflow_name_or_path)
            except FileNotFoundError:
                raise FileNotFoundError(f"Workflow '{workflow_name_or_path}' not found in built-in or user directories")


def list_workflows() -> Dict[str, List[str]]:
    """
    List all available workflows

    Returns:
        Dict: {'builtin': [...], 'user': [...]}
    """
    loader = WorkflowConfigLoader()

    builtin_workflows = loader.list_builtin_workflows()

    user_workflows = []
    user_dir = Path(__file__).parent / "user"
    if user_dir.exists():
        for file_path in user_dir.glob("*.yaml"):
            user_workflows.append(file_path.stem)
        for file_path in user_dir.glob("*.yml"):
            user_workflows.append(file_path.stem)
        for file_path in user_dir.glob("*.json"):
            user_workflows.append(file_path.stem)

    return {
        'builtin': builtin_workflows,
        'user': sorted(set(user_workflows))
    }
