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
            resolved_expression = self._resolve_variables(expression, variables)
            
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
                    return f"'{value}'"
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
        'text_agent': ['text']
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
            if agent_type not in ['text_agent', 'tool_agent', 'code_agent', 'auto']:
                errors.append(f"{step_prefix}: 不支持的 agent_type '{agent_type}'")
            
            # 验证 agent_type 特定配置
            if agent_type in self.AGENT_SPECIFIC_FIELDS:
                required_field = self.AGENT_SPECIFIC_FIELDS[agent_type][0]
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
            agent_instruction=step_config['agent_instruction'],
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
        
        return step


def load_workflow(workflow_name_or_path: str) -> Workflow:
    """
    加载工作流（便捷函数）
    
    Args:
        workflow_name_or_path: 工作流名称（内置）或文件路径
        
    Returns:
        Workflow: 工作流对象
    """
    loader = WorkflowConfigLoader()
    
    # 检查是否是文件路径
    if '/' in workflow_name_or_path or '\\' in workflow_name_or_path or '.' in workflow_name_or_path:
        return loader.load_from_file(workflow_name_or_path)
    else:
        # 尝试加载内置工作流
        return loader.load_builtin_workflow(workflow_name_or_path)


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