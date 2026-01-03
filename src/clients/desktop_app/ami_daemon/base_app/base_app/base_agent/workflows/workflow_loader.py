"""
工作流配置文件加载器
支持YAML格式的工作流配置文件，包含条件执行、错误处理等高级特性
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


def get_workflows_base_dir() -> Path:
    """Get workflows base directory (supports PyInstaller)"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running in PyInstaller bundle
        # Workflows are at {_MEIPASS}/base_app/base_agent/workflows/
        return Path(sys._MEIPASS) / 'base_app' / 'base_agent' / 'workflows'
    else:
        # Running from source
        return Path(__file__).parent


class WorkflowFormat(str, Enum):
    """支持的工作流配置文件格式"""
    YAML = "yaml"
    JSON = "json"


class ConditionEvaluator:
    """
    Condition expression evaluator.

    Supports operators: ==, !=, >, <, >=, <=, and, or, not
    Supports variable references: {{var}}, {{item.field}}
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

    def evaluate(self, expression: str, variables: Dict[str, Any]) -> bool:
        """
        Evaluate a condition expression.

        Args:
            expression: Condition like "{{count}} > 0" or "{{status}} == 'done'"
            variables: Variable dict

        Returns:
            bool: Evaluation result
        """
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

            # Get root variable
            value = variables.get(parts[0])
            if value is None:
                return "None"

            # Traverse nested properties
            for part in parts[1:]:
                if isinstance(value, dict):
                    value = value.get(part)
                elif hasattr(value, part):
                    value = getattr(value, part)
                else:
                    value = None
                if value is None:
                    return "None"

            # Convert to Python literal
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
    """工作流配置验证器 (v2 简化格式)"""

    VALID_AGENT_TYPES = [
        'text_agent', 'variable', 'scraper_agent',
        'browser_agent', 'storage_agent', 'tool_agent',
        'autonomous_browser_agent'
    ]

    CONTROL_FLOW_KEYS = ['if', 'while', 'foreach']

    def validate(self, config: Dict[str, Any]) -> List[str]:
        """验证配置文件，返回错误列表"""
        errors = []

        # 验证 API 版本 (v2 格式)
        api_version = config.get('apiVersion', '')
        if not api_version.startswith('ami.io/v'):
            errors.append("apiVersion 必须以 'ami.io/v' 开头")

        # 验证必填字段
        if 'name' not in config:
            errors.append("缺少必填字段: name")

        if 'steps' not in config:
            errors.append("缺少必填字段: steps")
        elif not isinstance(config['steps'], list) or len(config['steps']) == 0:
            errors.append("steps 必须是非空列表")
        else:
            errors.extend(self._validate_steps(config['steps']))

        return errors

    def _validate_steps(self, steps: List[Dict], prefix: str = "steps") -> List[str]:
        """验证步骤配置"""
        errors = []
        step_ids = set()

        for i, step in enumerate(steps):
            step_prefix = f"{prefix}[{i}]"

            # 检查是否是控制流
            is_control_flow = any(key in step for key in self.CONTROL_FLOW_KEYS)

            if is_control_flow:
                errors.extend(self._validate_control_flow_step(step, step_prefix))
            else:
                errors.extend(self._validate_agent_step(step, step_prefix, step_ids))

        return errors

    def _validate_agent_step(self, step: Dict, prefix: str, step_ids: set) -> List[str]:
        """验证 Agent 步骤"""
        errors = []

        # 检查 id (必须唯一)
        step_id = step.get('id')
        if step_id:
            if step_id in step_ids:
                errors.append(f"{prefix}: 重复的步骤ID '{step_id}'")
            step_ids.add(step_id)

        # 检查 agent_type (兼容旧格式) 或 agent (新格式)
        agent_type = step.get('agent_type') or step.get('agent')
        if not agent_type:
            errors.append(f"{prefix}: 缺少 agent_type 或 agent 字段")
        elif agent_type not in self.VALID_AGENT_TYPES:
            errors.append(f"{prefix}: 不支持的 agent 类型 '{agent_type}'")

        return errors

    def _validate_control_flow_step(self, step: Dict, prefix: str) -> List[str]:
        """验证控制流步骤"""
        errors = []

        if 'foreach' in step:
            # foreach 需要 do 或 steps
            if 'do' not in step and 'steps' not in step:
                errors.append(f"{prefix}: foreach 需要 do 或 steps 字段")
            else:
                sub_steps = step.get('do') or step.get('steps', [])
                errors.extend(self._validate_steps(sub_steps, f"{prefix}.do"))

        elif 'if' in step:
            # if 需要 then
            if 'then' not in step:
                errors.append(f"{prefix}: if 需要 then 字段")
            else:
                errors.extend(self._validate_steps(step['then'], f"{prefix}.then"))

            # else 是可选的
            if 'else' in step:
                errors.extend(self._validate_steps(step['else'], f"{prefix}.else"))

        elif 'while' in step:
            # while 需要 do 或 steps
            if 'do' not in step and 'steps' not in step:
                errors.append(f"{prefix}: while 需要 do 或 steps 字段")
            else:
                sub_steps = step.get('do') or step.get('steps', [])
                errors.extend(self._validate_steps(sub_steps, f"{prefix}.do"))

        return errors


class WorkflowConfigLoader:
    """工作流配置加载器"""

    def __init__(self):
        self.validator = WorkflowValidator()
        self.condition_evaluator = ConditionEvaluator()

    def load_from_file(self, file_path: Union[str, Path]) -> Workflow:
        """
        从配置文件加载工作流

        Args:
            file_path: 配置文件路径

        Returns:
            Workflow: 工作流对象

        Raises:
            ValueError: 配置文件验证失败
            FileNotFoundError: 文件不存在
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"工作流配置文件不存在: {file_path}")

        # 解析配置文件
        config = self._parse_file(path)

        # 验证配置
        errors = self.validator.validate(config)
        if errors:
            error_msg = "配置文件验证失败:\n" + "\n".join(f"- {error}" for error in errors)
            raise ValueError(error_msg)

        # 转换为工作流对象
        return self._create_workflow_from_config(config)

    def load_builtin_workflow(self, workflow_name: str) -> Workflow:
        """
        加载内置工作流

        Args:
            workflow_name: 工作流名称

        Returns:
            Workflow: 工作流对象
        """
        workflows_dir = get_workflows_base_dir()
        builtin_dir = workflows_dir / "builtin"
        workflow_file = builtin_dir / f"{workflow_name}.yaml"

        if not workflow_file.exists():
            # 尝试查找其他格式
            for ext in ['.yml', '.json']:
                alt_file = builtin_dir / f"{workflow_name}{ext}"
                if alt_file.exists():
                    workflow_file = alt_file
                    break
            else:
                raise FileNotFoundError(f"内置工作流 '{workflow_name}' 不存在 (searched: {builtin_dir})")

        return self.load_from_file(workflow_file)

    def load_user_workflow(self, workflow_name: str) -> Workflow:
        """
        加载用户工作流

        Args:
            workflow_name: 工作流名称

        Returns:
            Workflow: 工作流对象
        """
        workflows_dir = get_workflows_base_dir()
        user_dir = workflows_dir / "user"
        workflow_file = user_dir / f"{workflow_name}.yaml"

        if not workflow_file.exists():
            # 尝试查找其他格式
            for ext in ['.yml', '.json']:
                alt_file = user_dir / f"{workflow_name}{ext}"
                if alt_file.exists():
                    workflow_file = alt_file
                    break
            else:
                raise FileNotFoundError(f"用户工作流 '{workflow_name}' 不存在 (searched: {user_dir})")

        return self.load_from_file(workflow_file)

    def list_builtin_workflows(self) -> List[str]:
        """列出所有内置工作流"""
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
        """解析配置文件"""
        format = self._detect_format(file_path)
        content = file_path.read_text(encoding='utf-8')

        if format == WorkflowFormat.YAML:
            return yaml.safe_load(content)
        elif format == WorkflowFormat.JSON:
            return json.loads(content)
        else:
            raise ValueError(f"不支持的文件格式: {file_path.suffix}")

    def _detect_format(self, file_path: Path) -> WorkflowFormat:
        """检测文件格式"""
        suffix = file_path.suffix.lower()

        if suffix in ['.yaml', '.yml']:
            return WorkflowFormat.YAML
        elif suffix in ['.json']:
            return WorkflowFormat.JSON
        else:
            # 尝试根据内容判断
            content = file_path.read_text(encoding='utf-8').strip()
            if content.startswith('{'):
                return WorkflowFormat.JSON
            else:
                return WorkflowFormat.YAML

    def _create_workflow_from_config(self, config: Dict[str, Any]) -> Workflow:
        """从配置创建工作流对象 (支持 v1 和 v2 格式)"""
        # v2 格式: name 在顶层
        # v1 格式: name 在 metadata 中
        if 'metadata' in config:
            # v1 格式兼容
            metadata = config['metadata']
            name = metadata['name']
            description = metadata.get('description', '')
            version = metadata.get('version', '1.0.0')
            tags = metadata.get('tags', [])
            author = metadata.get('author', 'Ami')
        else:
            # v2 格式
            name = config['name']
            description = config.get('description', '')
            version = '1.0.0'
            tags = []
            author = 'Ami'

        # 创建工作流步骤
        steps = []
        for step_config in config['steps']:
            step = self._create_workflow_step(step_config)
            steps.append(step)

        # 处理 inputs (v2 简化格式支持 input: url 或 inputs: {url: string})
        input_schema = {}
        if 'input' in config:
            # 单个 input 简写
            input_name = config['input']
            input_schema = {input_name: {'type': 'string', 'required': True}}
        elif 'inputs' in config:
            raw_inputs = config['inputs']
            if isinstance(raw_inputs, dict):
                for k, v in raw_inputs.items():
                    if isinstance(v, str):
                        # 简化格式: url: string
                        input_schema[k] = {'type': v, 'required': True}
                    else:
                        # 完整格式
                        input_schema[k] = v

        # 创建工作流对象
        workflow = Workflow(
            name=name,
            description=description,
            version=version,
            steps=steps,
            input_schema=input_schema,
            output_schema=config.get('outputs', {}),
            max_execution_time=config.get('config', {}).get('max_execution_time', 3600),
            enable_parallel=config.get('config', {}).get('enable_parallel', False),
            enable_cache=config.get('config', {}).get('enable_cache', True),
            tags=tags,
            author=author
        )

        return workflow

    def _create_workflow_step(self, step_config: Dict[str, Any]) -> AgentWorkflowStep:
        """创建工作流步骤对象 (支持 v1 和 v2 格式)"""
        # 检测是否是控制流语法 (v2 新格式)
        if 'foreach' in step_config:
            return self._create_foreach_step(step_config)
        elif 'if' in step_config:
            return self._create_if_step(step_config)
        elif 'while' in step_config:
            return self._create_while_step(step_config)

        # Agent 步骤
        # 支持 agent_type (v1) 和 agent (v2)
        agent_type = step_config.get('agent_type') or step_config.get('agent')

        step = AgentWorkflowStep(
            id=step_config.get('id', ''),
            name=step_config.get('name', ''),
            description=step_config.get('description', ''),
            agent_type=agent_type,
            user_task=step_config.get('user_task')
        )

        # 输入输出配置
        step.inputs = step_config.get('inputs', {})
        step.outputs = step_config.get('outputs', {})

        # 条件配置
        if 'condition' in step_config:
            condition = step_config['condition']
            if isinstance(condition, dict) and 'expression' in condition:
                step.condition = condition['expression']
            elif isinstance(condition, str):
                step.condition = condition

        # v1 格式控制流 (agent_type == 'if'/'while'/'foreach')
        if agent_type == 'if':
            if 'then' in step_config:
                step.then = [self._create_workflow_step(s) for s in step_config['then']]
            if 'else' in step_config:
                step.else_ = [self._create_workflow_step(s) for s in step_config['else']]

        elif agent_type == 'while':
            if 'steps' in step_config:
                step.steps = [self._create_workflow_step(s) for s in step_config['steps']]
            step.max_iterations = step_config.get('max_iterations')
            step.loop_timeout = step_config.get('timeout', 3600)

        elif agent_type == 'foreach':
            if 'steps' in step_config:
                step.steps = [self._create_workflow_step(s) for s in step_config['steps']]
            step.source = step_config.get('source')
            step.item_var = step_config.get('item_var', 'item')
            step.index_var = step_config.get('index_var', 'index')
            step.max_iterations = step_config.get('max_iterations')
            step.loop_timeout = step_config.get('loop_timeout', 3600)

        elif agent_type == 'variable':
            # Variable Agent 特有配置
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

    def _create_foreach_step(self, step_config: Dict[str, Any]) -> AgentWorkflowStep:
        """创建 foreach 控制流步骤 (v2 格式)"""
        source = step_config['foreach']  # foreach: "{{items}}"
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
            loop_timeout=step_config.get('loop_timeout', 3600),
            steps=[self._create_workflow_step(s) for s in sub_steps]
        )
        return step

    def _create_if_step(self, step_config: Dict[str, Any]) -> AgentWorkflowStep:
        """创建 if 控制流步骤 (v2 格式)"""
        condition = step_config['if']  # if: "{{count}} > 0"

        step = AgentWorkflowStep(
            id=step_config.get('id', ''),
            name=step_config.get('name', 'if_condition'),
            description=step_config.get('description', ''),
            agent_type='if',
            condition=condition,
            then=[self._create_workflow_step(s) for s in step_config.get('then', [])],
            else_=[self._create_workflow_step(s) for s in step_config.get('else', [])]
        )
        return step

    def _create_while_step(self, step_config: Dict[str, Any]) -> AgentWorkflowStep:
        """创建 while 控制流步骤 (v2 格式)"""
        condition = step_config['while']  # while: "{{has_next}}"
        sub_steps = step_config.get('do') or step_config.get('steps', [])

        step = AgentWorkflowStep(
            id=step_config.get('id', ''),
            name=step_config.get('name', 'while_loop'),
            description=step_config.get('description', ''),
            agent_type='while',
            condition=condition,
            max_iterations=step_config.get('max_iterations'),
            loop_timeout=step_config.get('timeout', 3600),
            steps=[self._create_workflow_step(s) for s in sub_steps]
        )
        return step


def load_workflow(workflow_name_or_path: str) -> Workflow:
    """
    加载工作流（便捷函数）

    Args:
        workflow_name_or_path: 工作流名称（内置或用户）或文件路径

    Returns:
        Workflow: 工作流对象
    """
    loader = WorkflowConfigLoader()

    # 检查是否是文件路径
    if '/' in workflow_name_or_path or '\\' in workflow_name_or_path or '.' in workflow_name_or_path:
        return loader.load_from_file(workflow_name_or_path)
    else:
        # 先尝试加载内置工作流
        try:
            return loader.load_builtin_workflow(workflow_name_or_path)
        except FileNotFoundError:
            # 再尝试加载用户工作流
            try:
                return loader.load_user_workflow(workflow_name_or_path)
            except FileNotFoundError:
                raise FileNotFoundError(f"工作流 '{workflow_name_or_path}' 在内置和用户目录中都不存在")


def list_workflows() -> Dict[str, List[str]]:
    """
    列出所有可用的工作流

    Returns:
        Dict: {'builtin': [...], 'user': [...]}
    """
    loader = WorkflowConfigLoader()

    # 内置工作流
    builtin_workflows = loader.list_builtin_workflows()

    # 用户工作流
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
