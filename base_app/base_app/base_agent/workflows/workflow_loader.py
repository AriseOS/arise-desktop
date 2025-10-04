"""
工作流配置文件加载器
支持YAML格式的工作流配置文件，包含条件执行、错误处理等高级特性
"""
import yaml
import json
import re
import logging
from pathlib import Path
from typing import Dict, Any, List, Union, Optional
from enum import Enum

from ..core.schemas import AgentWorkflowStep, Workflow


logger = logging.getLogger(__name__)


class WorkflowFormat(str, Enum):
    """支持的工作流配置文件格式"""
    YAML = "yaml"
    JSON = "json"


class ConditionEvaluator:
    """条件表达式评估器"""
    
    def __init__(self):
        # 安全的内置函数和变量
        self.safe_builtins = {
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
        安全地评估条件表达式
        
        Args:
            expression: 条件表达式，如 "{{intent_type}} == 'tool'"
            variables: 变量字典
            
        Returns:
            bool: 评估结果
        """
        try:
            # 替换变量引用 {{variable}} -> variables['variable']
            print(f"expression {expression}, \t variables {variables}")
            resolved_expression = self._resolve_variables(expression, variables)
            print(f"resolved_expression {resolved_expression}")
            
            # 构建安全的执行环境
            safe_dict = {**self.safe_builtins, **variables}
            
            # 评估表达式
            result = eval(resolved_expression, {"__builtins__": {}}, safe_dict)
            return bool(result)
            
        except Exception as e:
            logger.warning(f"条件表达式评估失败: {expression}, 错误: {str(e)}")
            return False
    
    def _resolve_variables(self, expression: str, variables: Dict[str, Any]) -> str:
        """解析表达式中的变量引用"""
        def replace_var(match):
            var_name = match.group(1).strip()
            if var_name in variables:
                value = variables[var_name]
                if isinstance(value, str):
                    # 对字符串进行转义处理，避免引号冲突
                    escaped_value = value.replace("'", "\\'").replace('"', '\\"')
                    return f"'{escaped_value}'"
                elif value is None:
                    return "None"
                else:
                    return str(value)
            else:
                logger.warning(f"变量 {var_name} 未找到，使用 None")
                return "None"
        
        # 替换 {{variable}} 格式的变量引用
        return re.sub(r'\{\{([^}]+)\}\}', replace_var, expression)


class WorkflowValidator:
    """工作流配置验证器"""
    
    REQUIRED_FIELDS = {
        'metadata': ['name'],
        'steps': ['id', 'name', 'agent_type', 'agent_instruction']
    }
    
    AGENT_SPECIFIC_FIELDS = {
        'tool_agent': ['tools'],
        'code_agent': ['code'],
        'text_agent': ['text'],
        'variable': [],  # Variable agent doesn't require specific fields
        'scraper_agent': []  # Scraper agent doesn't require specific fields
    }
    
    def validate(self, config: Dict[str, Any]) -> List[str]:
        """验证配置文件，返回错误列表"""
        errors = []
        
        # 验证 API 版本和类型
        if config.get('apiVersion') != 'agentcrafter.io/v1':
            errors.append("apiVersion 必须是 'agentcrafter.io/v1'")
        
        if config.get('kind') != 'Workflow':
            errors.append("kind 必须是 'Workflow'")
        
        # 验证必填字段
        errors.extend(self._validate_required_fields(config))
        
        # 验证步骤配置
        errors.extend(self._validate_steps(config.get('steps', [])))
        
        # 验证输入输出定义
        errors.extend(self._validate_inputs_outputs(config))
        
        # 验证final_response要求
        errors.extend(self._validate_final_response_requirement(config))
        
        return errors
    
    def _validate_required_fields(self, config: Dict[str, Any]) -> List[str]:
        """验证必填字段"""
        errors = []
        
        for section, fields in self.REQUIRED_FIELDS.items():
            if section not in config:
                errors.append(f"缺少必填部分: {section}")
                continue
            
            section_data = config[section]
            if section == 'steps':
                # steps 是列表，需要特殊处理
                if not isinstance(section_data, list) or len(section_data) == 0:
                    errors.append("steps 必须是非空列表")
            else:
                # 其他部分验证必填字段
                for field in fields:
                    if field not in section_data:
                        errors.append(f"{section}.{field} 是必填字段")
        
        return errors
    
    def _validate_steps(self, steps: List[Dict]) -> List[str]:
        """验证步骤配置"""
        errors = []
        step_ids = set()
        
        for i, step in enumerate(steps):
            step_prefix = f"steps[{i}]"
            
            # 检查重复ID
            step_id = step.get('id')
            if step_id in step_ids:
                errors.append(f"{step_prefix}: 重复的步骤ID '{step_id}'")
            step_ids.add(step_id)
            
            # 验证 agent_type
            agent_type = step.get('agent_type')
            if agent_type not in ['text_agent', 'tool_agent', 'code_agent', 'variable', 'scraper_agent', 'if', 'while', 'foreach']:
                errors.append(f"{step_prefix}: 不支持的 agent_type '{agent_type}'")
            
            # 验证控制流特定配置
            if agent_type == 'if':
                if 'condition' not in step:
                    errors.append(f"{step_prefix}: if类型必须有condition字段")
                if 'then' not in step:
                    errors.append(f"{step_prefix}: if类型必须有then字段")
                # else字段是可选的
            elif agent_type == 'while':
                if 'condition' not in step:
                    errors.append(f"{step_prefix}: while类型必须有condition字段")
                if 'steps' not in step:
                    errors.append(f"{step_prefix}: while类型必须有steps字段")
            elif agent_type == 'foreach':
                if 'source' not in step:
                    errors.append(f"{step_prefix}: foreach类型必须有source字段")
                if 'steps' not in step:
                    errors.append(f"{step_prefix}: foreach类型必须有steps字段")
            elif agent_type in self.AGENT_SPECIFIC_FIELDS:
                # 验证普通agent类型特定配置
                required_fields = self.AGENT_SPECIFIC_FIELDS[agent_type]
                if required_fields:  # Only check if there are required fields
                    required_field = required_fields[0]
                    if required_field not in step:
                        errors.append(f"{step_prefix}: {agent_type} 类型缺少 {required_field} 配置")
            
            # 验证条件表达式格式（如果存在）
            if 'condition' in step:
                condition = step['condition']
                if isinstance(condition, dict) and 'expression' in condition:
                    # 基本的表达式格式检查
                    expr = condition['expression']
                    if not isinstance(expr, str) or len(expr.strip()) == 0:
                        errors.append(f"{step_prefix}: condition.expression 必须是非空字符串")
        
        return errors
    
    def _validate_inputs_outputs(self, config: Dict[str, Any]) -> List[str]:
        """验证输入输出定义"""
        errors = []
        
        # 验证工作流输入定义
        inputs = config.get('inputs', {})
        for input_name, input_def in inputs.items():
            if not isinstance(input_def, dict):
                errors.append(f"inputs.{input_name} 必须是字典格式")
                continue
            
            if 'type' not in input_def:
                errors.append(f"inputs.{input_name}.type 是必填字段")
        
        # 验证工作流输出定义
        outputs = config.get('outputs', {})
        for output_name, output_def in outputs.items():
            if not isinstance(output_def, dict):
                errors.append(f"outputs.{output_name} 必须是字典格式")
                continue
            
            if 'type' not in output_def:
                errors.append(f"outputs.{output_name}.type 是必填字段")
        
        return errors
    
    def _validate_final_response_requirement(self, config: Dict[str, Any]) -> List[str]:
        """验证workflow必须有步骤输出final_response"""
        errors = []
        
        def check_steps_for_final_response(step_list):
            for step in step_list:
                step_outputs = step.get('outputs', {})
                if 'final_response' in step_outputs.values():
                    return True

                # 递归检查控制流中的步骤
                if step.get('agent_type') == 'if':
                    if 'then' in step and check_steps_for_final_response(step['then']):
                        return True
                    if 'else' in step and check_steps_for_final_response(step['else']):
                        return True
                elif step.get('agent_type') in ['while', 'foreach']:
                    if 'steps' in step and check_steps_for_final_response(step['steps']):
                        return True
            return False
        
        steps = config.get('steps', [])
        if not check_steps_for_final_response(steps):
            errors.append("workflow中必须有至少一个步骤的outputs映射到final_response变量")
        
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
        builtin_dir = Path(__file__).parent / "builtin"
        workflow_file = builtin_dir / f"{workflow_name}.yaml"

        if not workflow_file.exists():
            # 尝试查找其他格式
            for ext in ['.yml', '.json']:
                alt_file = builtin_dir / f"{workflow_name}{ext}"
                if alt_file.exists():
                    workflow_file = alt_file
                    break
            else:
                raise FileNotFoundError(f"内置工作流 '{workflow_name}' 不存在")

        return self.load_from_file(workflow_file)

    def load_user_workflow(self, workflow_name: str) -> Workflow:
        """
        加载用户工作流

        Args:
            workflow_name: 工作流名称

        Returns:
            Workflow: 工作流对象
        """
        user_dir = Path(__file__).parent / "user"
        workflow_file = user_dir / f"{workflow_name}.yaml"

        if not workflow_file.exists():
            # 尝试查找其他格式
            for ext in ['.yml', '.json']:
                alt_file = user_dir / f"{workflow_name}{ext}"
                if alt_file.exists():
                    workflow_file = alt_file
                    break
            else:
                raise FileNotFoundError(f"用户工作流 '{workflow_name}' 不存在")

        return self.load_from_file(workflow_file)
    
    def list_builtin_workflows(self) -> List[str]:
        """列出所有内置工作流"""
        builtin_dir = Path(__file__).parent / "builtin"
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
        """从配置创建工作流对象"""
        metadata = config['metadata']
        
        # 创建工作流步骤
        steps = []
        for step_config in config['steps']:
            step = self._create_workflow_step(step_config)
            steps.append(step)
        
        # 创建工作流对象
        workflow = Workflow(
            name=metadata['name'],
            description=metadata.get('description', ''),
            version=metadata.get('version', '1.0.0'),
            steps=steps,
            input_schema=config.get('inputs', {}),
            output_schema=config.get('outputs', {}),
            max_execution_time=config.get('config', {}).get('max_execution_time', 3600),
            enable_parallel=config.get('config', {}).get('enable_parallel', False),
            enable_cache=config.get('config', {}).get('enable_cache', True),
            tags=metadata.get('tags', []),
            author=metadata.get('author', 'AgentCrafter')
        )
        
        return workflow
    
    def _create_workflow_step(self, step_config: Dict[str, Any]) -> AgentWorkflowStep:
        """创建工作流步骤对象"""
        # 基础配置
        step = AgentWorkflowStep(
            id=step_config['id'],
            name=step_config['name'],
            description=step_config.get('description', ''),
            agent_type=step_config['agent_type'],
            agent_instruction=step_config.get('agent_instruction', ''),
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
        
        # 控制流配置
        if step_config['agent_type'] == 'if':
            # 处理then分支
            if 'then' in step_config:
                step.then = [self._create_workflow_step(sub_step) for sub_step in step_config['then']]
            
            # 处理else分支（可选）
            if 'else' in step_config:
                step.else_ = [self._create_workflow_step(sub_step) for sub_step in step_config['else']]
        
        elif step_config['agent_type'] == 'while':
            # 处理循环体
            if 'steps' in step_config:
                step.steps = [self._create_workflow_step(sub_step) for sub_step in step_config['steps']]

            # 处理循环限制配置
            step.max_iterations = step_config.get('max_iterations', 10)
            step.loop_timeout = step_config.get('timeout', 300)

        elif step_config['agent_type'] == 'foreach':
            # 处理foreach循环体
            if 'steps' in step_config:
                step.steps = [self._create_workflow_step(sub_step) for sub_step in step_config['steps']]

            # 处理foreach配置
            step.source = step_config.get('source')  # 源列表变量
            step.item_var = step_config.get('item_var', 'item')  # 当前项变量名
            step.index_var = step_config.get('index_var', 'index')  # 当前索引变量名
            step.max_iterations = step_config.get('max_iterations', 100)  # 最大迭代次数
            step.loop_timeout = step_config.get('loop_timeout', 600)  # 超时时间

        elif step_config['agent_type'] == 'variable':
            # 处理Variable Agent特有配置 - 从inputs中获取
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