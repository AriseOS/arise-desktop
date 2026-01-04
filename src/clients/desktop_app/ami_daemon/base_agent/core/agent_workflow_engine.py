"""
Agent工作流执行引擎
基于Agent-as-Step架构的工作流执行引擎
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Type

from .schemas import (
    AgentWorkflowStep, WorkflowResult, StepResult,
    AgentContext, AgentInput, AgentOutput
)
from ..agents import TextAgent
from ..agents.base_agent import BaseStepAgent
from ..agents.browser_agent import BrowserAgent
from ..agents.variable_agent import VariableAgent
from ..agents.scraper_agent import ScraperAgent
from ..agents.storage_agent import StorageAgent
from ..agents.autonomous_browser_agent import AutonomousBrowserAgent

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependency
def _get_condition_evaluator():
    from ..workflows.workflow_loader import ConditionEvaluator
    return ConditionEvaluator()


class AgentWorkflowEngine:
    """基于Agent的工作流执行引擎"""

    # 预定义 Agent 类型映射
    AGENT_TYPES: Dict[str, Type[BaseStepAgent]] = {
        'text_agent': TextAgent,
        'variable': VariableAgent,
        'scraper_agent': ScraperAgent,
        'storage_agent': StorageAgent,
        'browser_agent': BrowserAgent,
        'autonomous_browser_agent': AutonomousBrowserAgent,
    }

    def __init__(self, agent_instance=None):
        self.agent = agent_instance
        self.condition_evaluator = _get_condition_evaluator()
        self._config_service = getattr(self.agent, 'config_service', None) if self.agent else None

    def _create_agent(self, agent_type: str, config: Optional[Dict] = None) -> BaseStepAgent:
        """创建 Agent 实例"""
        agent_class = self.AGENT_TYPES.get(agent_type)
        if not agent_class:
            raise ValueError(f"Unknown agent type: {agent_type}")

        config = config or {}

        # ScraperAgent 需要特殊处理
        if agent_type == 'scraper_agent':
            return ScraperAgent(
                config_service=self._config_service,
                extraction_method=config.get('extraction_method', 'llm'),
                dom_scope=config.get('dom_scope', 'partial'),
                debug_mode=config.get('debug_mode', False)
            )

        return agent_class()

    async def _execute_agent(
        self,
        agent_type: str,
        input_data: Any,
        context: AgentContext,
        agent_config: Optional[Dict] = None
    ) -> Any:
        """执行指定 Agent"""
        agent = self._create_agent(agent_type, agent_config)

        # 初始化 Agent
        if not agent.is_initialized:
            success = await agent.initialize(context)
            if not success:
                raise RuntimeError(f"Agent {agent_type} 初始化失败")

        # 验证输入
        if not await agent.validate_input(input_data):
            raise ValueError(f"Agent {agent_type} 输入数据验证失败")

        # 执行 Agent
        try:
            return await agent.execute(input_data, context)
        except Exception as e:
            await agent.cleanup(context)
            raise e
    
    async def execute_workflow(
        self,
        steps: List[AgentWorkflowStep],
        workflow_id: str = None,
        input_data: Dict[str, Any] = None,
        step_callback: Optional[Any] = None,
        log_callback: Optional[Any] = None
    ) -> WorkflowResult:
        """Execute agent workflow with optional step progress callback

        Args:
            steps: List of workflow steps
            workflow_id: Optional workflow ID
            input_data: Input data dict
            step_callback: Optional async callback function(step_index, step_name, status, result)
                          Called when step starts (status='in_progress') and completes (status='completed'/'failed')
            log_callback: Optional async callback function(level, message, metadata)
                         Called for detailed execution logs from agents
        """
        start_time = time.time()
        workflow_id = workflow_id or f"agent_workflow_{int(time.time())}"

        # Initialize execution context
        context = AgentContext(
            workflow_id=workflow_id,
            step_id="",
            user_id=getattr(self.agent, 'user_id', 'default_user'),
            variables=input_data or {},
            agent_instance=self.agent,
            tools_registry=getattr(self.agent, 'tools_registry', None),
            memory_manager=getattr(self.agent, 'memory_manager', None),
            logger=logger,
            log_callback=log_callback
        )

        executed_steps = []
        last_step_output = None

        try:
            for step_index, step in enumerate(steps):
                # Update context
                context.step_id = step.id

                # Notify step start
                if step_callback:
                    try:
                        await step_callback(step_index, step.name, 'in_progress', None)
                    except Exception as e:
                        logger.warning(f"Step callback error (start): {e}")

                # Execute step based on type
                if step.agent_type == "if":
                    step_result = await self._execute_if_step(step, context)
                elif step.agent_type == "while":
                    step_result = await self._execute_while_step(step, context)
                elif step.agent_type == "foreach":
                    step_result = await self._execute_foreach_step(step, context)
                else:
                    # Check execution condition for normal steps
                    if step.condition and not await self._evaluate_condition(step.condition, context):
                        logger.info(f"Step {step.name} condition not met, skipping")
                        continue

                    # Execute normal agent step
                    step_result = await self._execute_agent_step(step, context)
                # Update context variables
                if step_result.success and step.outputs:
                    await self._update_context_variables(step_result, step.outputs, context)
                    # Update last step output
                    last_step_output = await self._extract_step_outputs(step_result, step.outputs)

                executed_steps.append(step_result)

                # Notify step completion
                if step_callback:
                    try:
                        step_status = 'completed' if step_result.success else 'failed'
                        await step_callback(step_index, step.name, step_status, step_result.data)
                    except Exception as e:
                        logger.warning(f"Step callback error (complete): {e}")

                # Stop if step failed and no continue flag
                if not step_result.success:
                    logger.error(f"Step execution failed [step_id={step.id}, name={step.name}, agent_type={step.agent_type}]: {step_result.message}")
                    break
            
            # 提取final_response作为最终结果
            final_result = context.variables.get('final_response', 
                "抱歉，系统未能生成有效回复。请联系开发者检查workflow配置，确保有步骤输出到final_response变量。")
            
            return WorkflowResult(
                success=True,
                workflow_id=workflow_id,
                steps=executed_steps,
                final_result=final_result,
                total_execution_time=time.time() - start_time
            )

        except Exception as e:
            logger.error(f"工作流执行失败: {str(e)}")
            return WorkflowResult(
                success=False,
                workflow_id=workflow_id,
                error_message=str(e),
                steps=executed_steps,
                total_execution_time=time.time() - start_time
            )
        finally:
            # 清理context的浏览器会话（如果有）
            await context.cleanup_browser_session()
    
    async def _execute_agent_step(
        self,
        step: AgentWorkflowStep,
        context: AgentContext
    ) -> StepResult:
        """执行Agent步骤 - 统一入口处理变量解析"""
        step_start_time = time.time()

        try:
            # 统一变量解析：获取解析后的字典
            resolved_dict = self._resolve_step_variables(step, context)

            # 确定Agent类型
            agent_type = step.agent_type

            # 获取解析后的inputs
            resolved_inputs = resolved_dict.get('inputs', {})

            # 构建Agent输入
            agent_input = await self._build_agent_input(step, agent_type, resolved_inputs, context)

            # 提取agent配置（从step的agent_config字段或inputs中）
            agent_config = {}

            # 1. 从step的agent_config字段获取（如果有）
            if hasattr(step, 'agent_config'):
                agent_config.update(step.agent_config)

            # 2. 从inputs中提取特定的配置参数
            config_keys = ['extraction_method', 'dom_scope', 'debug_mode']
            for key in config_keys:
                if key in resolved_inputs:
                    agent_config[key] = resolved_inputs[key]

            # 执行Agent
            result = await self._execute_agent(
                agent_type,
                agent_input,
                context,
                agent_config
            )

            return StepResult(
                step_id=step.id,
                success=getattr(result, 'success', True),
                data=result,
                message=f"Agent {agent_type} 执行成功",
                execution_time=time.time() - step_start_time
            )

        except Exception as e:
            logger.error(f"Agent步骤执行失败 [step_id={step.id}, name={step.name}, agent_type={step.agent_type}]: {str(e)}")
            return StepResult(
                step_id=step.id,
                success=False,
                data=None,
                message=str(e),
                execution_time=time.time() - step_start_time
            )
    
    async def _build_agent_input(
        self, 
        step: AgentWorkflowStep, 
        agent_type: str, 
        resolved_input: Dict[str, Any],
        context: AgentContext
    ) -> AgentInput:
        """构建Agent输入对象 - 直接传递原始数据"""
        
        # 构建metadata，包含agent特定的配置
        metadata = {
            "expected_outputs": step.outputs,
            "constraints": getattr(step, 'constraints', []),
        }
        
        # 根据agent类型添加特定的metadata
        if agent_type == "text_agent":
            metadata.update({
                "response_style": getattr(step, 'response_style', 'professional'),
                "max_length": getattr(step, 'max_length', 1000)
            })
        elif agent_type == "variable":
            # Variable agent uses step_config for operation details
            # Use resolved_input instead of step attributes to get parsed values
            resolved_data = resolved_input.get('data', {})
            logger.info(f"🔍 [VariableAgent] step_id={step.id}, resolved_data type: {type(resolved_data)}, preview: {str(resolved_data)[:200]}")

            metadata.update({
                "step_config": {
                    "operation": resolved_input.get('operation', 'set'),
                    "data": resolved_data,
                    "source": resolved_input.get('source', None),
                    "field": resolved_input.get('field', None),
                    "value": resolved_input.get('value', None),
                    "expression": resolved_input.get('expression', None),
                    "updates": resolved_input.get('updates', None),
                    "current_page": resolved_input.get('current_page', None),
                    "max_pages": resolved_input.get('max_pages', None),
                    "items_found": resolved_input.get('items_found', None),
                    # slice operation parameters
                    "start": resolved_input.get('start', None),
                    "start_value": resolved_input.get('start_value', None),
                    "match_field": resolved_input.get('match_field', None),
                    # filter operation parameters
                    "contains": resolved_input.get('contains', None),
                    "equals": resolved_input.get('equals', None)
                },
                "context": context
            })

        return AgentInput(
            instruction="",                      # No longer used
            data=resolved_input,                 # 解析后的输入数据
            step_metadata=metadata
        )
    
    
    def _resolve_step_variables(self, step: AgentWorkflowStep, context: AgentContext) -> Dict[str, Any]:
        """统一的步骤变量解析入口 - 返回解析后的字典，而不是重建step对象

        这是唯一的变量解析入口，所有步骤执行前都会调用此方法

        Args:
            step: 原始步骤对象
            context: 执行上下文

        Returns:
            解析后的字典，包含所有解析后的值
        """
        # 1. 将step转换为字典
        step_dict = step.model_dump()

        # 2. 递归解析字典中的所有值
        resolved_dict = self._resolve_value_recursive(step_dict, context)

        return resolved_dict

    def _resolve_value_recursive(self, value: Any, context: AgentContext) -> Any:
        """递归解析值中的所有变量引用

        Args:
            value: 要解析的值（可能是字符串、字典、列表或其他类型）
            context: Agent执行上下文

        Returns:
            解析后的值
        """
        if isinstance(value, str):
            # 解析字符串中的变量
            return self._resolve_string_with_variables(value, context)
        elif isinstance(value, dict):
            # 递归解析字典中的所有值
            resolved_dict = {}
            for sub_key, sub_value in value.items():
                resolved_dict[sub_key] = self._resolve_value_recursive(sub_value, context)
            return resolved_dict
        elif isinstance(value, list):
            # 递归解析列表中的所有元素
            return [self._resolve_value_recursive(item, context) for item in value]
        else:
            # 其他类型直接返回
            return value

    def _resolve_variable(self, var_expression: str, context: AgentContext) -> Any:
        """解析变量表达式，支持嵌套属性访问（如 {{current_item.name}}）

        Args:
            var_expression: 变量表达式（如 "current_item.name"）
            context: Agent执行上下文

        Returns:
            解析后的值

        Raises:
            ValueError: 如果变量不存在或无法访问嵌套属性
        """
        parts = var_expression.split('.')
        value = context.variables.get(parts[0])

        # 如果变量不存在，抛出错误
        if value is None:
            available_vars = list(context.variables.keys())
            raise ValueError(
                f"Variable '{parts[0]}' not found in context.\n"
                f"  Trying to resolve: {{{{{{var_expression}}}}}}\n"
                f"  Available variables: {available_vars}"
            )

        # 遍历嵌套属性
        for part in parts[1:]:
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list):
                # Support list index access and auto-unwrap single-item lists
                if part.isdigit():
                    # Explicit index access: {{list.0.field}} or {{list.1.field}}
                    idx = int(part)
                    if 0 <= idx < len(value):
                        value = value[idx]
                    else:
                        # Return None for out-of-range access (graceful degradation)
                        logger.warning(
                            f"List index {idx} out of range (list has {len(value)} items). "
                            f"Returning None for: {var_expression}"
                        )
                        return None
                elif part == 'length':
                    # Support .length as syntax sugar for len() (JavaScript-style)
                    value = len(value)
                    logger.debug(f"Resolved list.length to {value} for: {var_expression}")
                elif len(value) == 1:
                    # Auto-unwrap single-item list: {{list.field}} → {{list.0.field}}
                    # This makes scraper_agent output more ergonomic for single-item extraction
                    logger.debug(f"Auto-unwrapping single-item list for property access: {var_expression}")
                    value = value[0]
                    # Continue resolving the property on the unwrapped item
                    if isinstance(value, dict):
                        value = value.get(part)
                    elif hasattr(value, part):
                        value = getattr(value, part)
                    else:
                        raise ValueError(
                            f"Cannot access property '{part}' on unwrapped list item of type {type(value).__name__}.\n"
                            f"  Trying to resolve: {{{{{{var_expression}}}}}}\n"
                            f"  Available properties: {list(value.keys()) if isinstance(value, dict) else 'N/A'}"
                        )
                else:
                    raise ValueError(
                        f"Cannot access property '{part}' on a list with {len(value)} items.\n"
                        f"  Trying to resolve: {{{{{{var_expression}}}}}}\n"
                        f"  Hint: Use numeric index to access specific item (e.g., {{{{list.0.{part}}}}})"
                    )
            elif hasattr(value, part):
                value = getattr(value, part)
            else:
                raise ValueError(
                    f"Cannot access property '{part}' on {type(value).__name__}.\n"
                    f"  Trying to resolve: {{{{{{var_expression}}}}}}\n"
                    f"  Available properties: {list(value.keys()) if isinstance(value, dict) else 'N/A'}"
                )

            # Allow None values to pass through - this is normal for optional/missing fields
            # Don't raise error, just return None and let the workflow continue
            if value is None:
                logger.debug(f"Property '{part}' resolved to None in expression: {var_expression}")
                return None

        return value


    def _resolve_string_with_variables(self, text: str, context: AgentContext) -> Any:
        """解析字符串中的所有变量引用

        支持以下格式：
        - "{{variable}}" - 完整变量，直接返回变量值（可能是任意类型）
        - "prefix {{variable}} suffix" - 字符串模板，变量会被转换为字符串后替换
        - "{{var1}}/{{var2}}" - 多个变量的字符串模板

        Args:
            text: 包含变量引用的字符串
            context: Agent执行上下文

        Returns:
            解析后的值（可能是字符串或其他类型）
        """
        import re

        # 查找所有 {{variable}} 模式
        pattern = r'\{\{([^}]+)\}\}'
        matches = list(re.finditer(pattern, text))

        if not matches:
            # 没有变量，直接返回原文本
            return text

        # 如果整个字符串就是一个变量引用（如 "{{variable}}"）
        if len(matches) == 1 and matches[0].group(0) == text:
            var_expression = matches[0].group(1).strip()
            return self._resolve_variable(var_expression, context)

        # 否则是字符串模板，需要替换所有变量
        result = text
        for match in matches:
            var_expression = match.group(1).strip()
            var_value = self._resolve_variable(var_expression, context)

            # 将变量值转换为字符串
            if var_value is None:
                var_str = f"{{{{{var_expression}}}}}"  # 保留未解析的变量
            else:
                var_str = str(var_value)

            # 替换变量引用
            result = result.replace(match.group(0), var_str)

        return result
    
    async def _update_context_variables(
        self, 
        step_result: StepResult, 
        outputs: Dict[str, str], 
        context: AgentContext
    ):
        """更新上下文变量"""
        if not step_result.data or not isinstance(step_result.data, AgentOutput):
            return
        
        agent_output = step_result.data
        for output_key, var_name in outputs.items():
            if output_key in agent_output.data:
                context.variables[var_name] = agent_output.data[output_key]
                logger.debug(f"更新上下文变量: {var_name} = {agent_output.data[output_key]}")
    
    async def _extract_step_outputs(
        self, 
        step_result: StepResult, 
        outputs: Dict[str, str]
    ) -> Any:
        """提取当前步骤的输出值"""
        if not step_result.data or not outputs or not isinstance(step_result.data, AgentOutput):
            return None
        
        agent_output = step_result.data
        step_outputs = {}
        
        for output_key, var_name in outputs.items():
            if output_key in agent_output.data:
                step_outputs[var_name] = agent_output.data[output_key]
        
        # 如果只有一个输出，直接返回值；否则返回字典
        if len(step_outputs) == 1:
            return list(step_outputs.values())[0]
        elif len(step_outputs) > 1:
            return step_outputs
        else:
            return None
    
    async def _evaluate_condition(self, condition: str, context: AgentContext) -> bool:
        """评估条件表达式"""
        return self.condition_evaluator.evaluate(condition, context.variables)
    
    async def _execute_if_step(self, step: AgentWorkflowStep, context: AgentContext) -> StepResult:
        """执行if/else条件控制步骤 - 统一入口处理变量解析"""
        step_start_time = time.time()

        try:
            # 统一变量解析：获取解析后的字典
            resolved_dict = self._resolve_step_variables(step, context)

            # 评估条件（使用解析后的condition）
            resolved_condition = resolved_dict.get('condition', step.condition)
            condition_result = await self._evaluate_condition(resolved_condition, context)
            logger.info(f"If条件 '{step.condition}' 评估结果: {condition_result}")

            # 选择执行分支
            branch_executed = "then" if condition_result else "else"
            sub_steps = step.then if condition_result else step.else_
            
            sub_step_results = []
            branch_success = True
            
            # 执行选中分支的步骤
            if sub_steps:
                for sub_step in sub_steps:
                    sub_result = await self._execute_single_step(sub_step, context)
                    sub_step_results.append(sub_result)
                    
                    if not sub_result.success:
                        branch_success = False
                        break
                        
                    # 更新上下文变量
                    if sub_result.success and sub_step.outputs:
                        await self._update_context_variables(sub_result, sub_step.outputs, context)
            
            return StepResult(
                step_id=step.id,
                success=branch_success,
                data=None,
                message=f"If条件执行完成，分支: {branch_executed}",
                execution_time=time.time() - step_start_time,
                step_type="if",
                condition_result=condition_result,
                branch_executed=branch_executed,
                sub_step_results=sub_step_results
            )

        except Exception as e:
            logger.error(f"If步骤执行失败: {str(e)}")
            return StepResult(
                step_id=step.id,
                success=False,
                data=None,
                message=str(e),
                execution_time=time.time() - step_start_time,
                step_type="if"
            )
    
    async def _execute_while_step(self, step: AgentWorkflowStep, context: AgentContext) -> StepResult:
        """执行while循环控制步骤 - 统一入口处理变量解析"""
        step_start_time = time.time()

        try:
            # 统一变量解析：获取解析后的字典
            resolved_dict = self._resolve_step_variables(step, context)

            max_iterations = step.max_iterations  # None means no limit
            loop_timeout = step.loop_timeout or 3600
            iterations_executed = 0
            sub_step_results = []
            exit_reason = "condition_false"

            while max_iterations is None or iterations_executed < max_iterations:
                # 检查超时
                if time.time() - step_start_time > loop_timeout:
                    exit_reason = "timeout"
                    break
                
                # 评估循环条件（使用解析后的condition）
                resolved_condition = resolved_dict.get('condition', step.condition)
                condition_result = await self._evaluate_condition(resolved_condition, context)
                logger.info(f"While条件 '{step.condition}' 评估结果: {condition_result} (第{iterations_executed + 1}次)")
                
                if not condition_result:
                    exit_reason = "condition_false"
                    break
                
                # 执行循环体步骤
                iteration_success = True
                iteration_results = []

                if step.steps:
                    for sub_step in step.steps:
                        sub_result = await self._execute_single_step(sub_step, context)
                        iteration_results.append(sub_result)
                        
                        if not sub_result.success:
                            iteration_success = False
                            exit_reason = "step_failed"
                            break
                            
                        # 更新上下文变量
                        if sub_result.success and sub_step.outputs:
                            await self._update_context_variables(sub_result, sub_step.outputs, context)
                
                sub_step_results.extend(iteration_results)
                iterations_executed += 1
                
                if not iteration_success:
                    break
            
            if max_iterations is not None and iterations_executed >= max_iterations:
                exit_reason = "max_iterations_reached"

            return StepResult(
                step_id=step.id,
                success=True,
                data=None,
                message=f"While循环执行完成，迭代{iterations_executed}次，退出原因: {exit_reason}",
                execution_time=time.time() - step_start_time,
                step_type="while",
                iterations_executed=iterations_executed,
                exit_reason=exit_reason,
                sub_step_results=sub_step_results
            )

        except Exception as e:
            logger.error(f"While步骤执行失败: {str(e)}")
            return StepResult(
                step_id=step.id,
                success=False,
                data=None,
                message=str(e),
                execution_time=time.time() - step_start_time,
                step_type="while"
            )
    
    async def _execute_foreach_step(self, step: AgentWorkflowStep, context: AgentContext) -> StepResult:
        """执行foreach循环控制步骤 - 只解析 source，不解析子步骤"""
        step_start_time = time.time()

        try:
            # 只解析 source 变量，不解析子步骤（子步骤会在每次迭代中单独解析）
            source_var = step.source
            if not source_var:
                raise ValueError("foreach步骤缺少source配置")

            # 解析 source 变量
            if isinstance(source_var, str) and source_var.startswith('{{') and source_var.endswith('}}'):
                var_expr = source_var[2:-2].strip()
                source_list = self._resolve_variable(var_expr, context)
            else:
                source_list = source_var

            max_iterations = step.max_iterations  # None means no limit
            loop_timeout = step.loop_timeout or 600

            if not source_list:
                raise ValueError("foreach步骤的source解析后为空")

            if not isinstance(source_list, list):
                raise ValueError(f"source 必须解析为列表，当前类型: {type(source_list)}, 值: {source_list}")

            logger.info(f"Foreach循环开始，遍历 {len(source_list)} 个元素")

            # 获取配置
            item_var = step.item_var or "item"
            index_var = step.index_var or "index"

            iterations_executed = 0
            sub_step_results = []
            exit_reason = "completed"

            # 遍历列表
            for index, item in enumerate(source_list):
                # 检查迭代次数限制
                if max_iterations is not None and iterations_executed >= max_iterations:
                    exit_reason = "max_iterations_reached"
                    logger.warning(f"达到最大迭代次数 {max_iterations}，停止遍历")
                    break

                # 检查超时
                if time.time() - step_start_time > loop_timeout:
                    exit_reason = "timeout"
                    logger.warning(f"达到超时限制 {loop_timeout}秒，停止遍历")
                    break

                # 设置当前项和索引到上下文
                context.variables[item_var] = item
                context.variables[index_var] = index

                logger.info(f"Foreach迭代 {index + 1}/{len(source_list)}: {item_var}={item}")

                # 执行循环体步骤
                iteration_success = True
                iteration_results = []

                if step.steps:
                    for sub_step in step.steps:
                        sub_result = await self._execute_single_step(sub_step, context)
                        iteration_results.append(sub_result)

                        if not sub_result.success:
                            iteration_success = False
                            exit_reason = "step_failed"
                            logger.error(f"Foreach迭代 {index + 1} 中的步骤失败: {sub_step.name}")
                            break

                        # 更新上下文变量
                        if sub_result.success and sub_step.outputs:
                            await self._update_context_variables(sub_result, sub_step.outputs, context)

                sub_step_results.extend(iteration_results)
                iterations_executed += 1

                if not iteration_success:
                    break

            # 清理循环变量
            if item_var in context.variables:
                del context.variables[item_var]
            if index_var in context.variables:
                del context.variables[index_var]

            return StepResult(
                step_id=step.id,
                success=True,
                data=None,
                message=f"Foreach循环执行完成，遍历{iterations_executed}/{len(source_list)}个元素，退出原因: {exit_reason}",
                execution_time=time.time() - step_start_time,
                step_type="foreach",
                iterations_executed=iterations_executed,
                exit_reason=exit_reason,
                sub_step_results=sub_step_results
            )

        except Exception as e:
            logger.error(f"Foreach步骤执行失败: {str(e)}")
            return StepResult(
                step_id=step.id,
                success=False,
                data=None,
                message=str(e),
                execution_time=time.time() - step_start_time,
                step_type="foreach"
            )

    async def _execute_single_step(self, step: AgentWorkflowStep, context: AgentContext) -> StepResult:
        """执行单个步骤（可能是Agent步骤或控制流步骤）"""
        # 更新上下文
        original_step_id = context.step_id
        context.step_id = step.id
        
        try:
            if step.agent_type == "if":
                return await self._execute_if_step(step, context)
            elif step.agent_type == "while":
                return await self._execute_while_step(step, context)
            elif step.agent_type == "foreach":
                return await self._execute_foreach_step(step, context)
            else:
                # 检查普通步骤的执行条件
                if step.condition and not await self._evaluate_condition(step.condition, context):
                    logger.info(f"步骤 {step.name} 条件不满足，跳过执行")
                    return StepResult(
                        step_id=step.id,
                        success=True,
                        data=None,
                        message="条件不满足，跳过执行",
                        execution_time=0.0
                    )

                return await self._execute_agent_step(step, context)
        finally:
            # 恢复原来的step_id
            context.step_id = original_step_id
    
    async def execute_step(
        self,
        step: AgentWorkflowStep,
        variables: Dict[str, Any],
        workflow_id: str = None,
        log_callback: Optional[Any] = None
    ) -> StepResult:
        """Execute a single step with provided variables.

        This is useful for debugging or testing individual steps without
        running the entire workflow.

        Args:
            step: The step to execute
            variables: Variables to inject into context (simulates prior step outputs)
            workflow_id: Optional workflow ID for context
            log_callback: Optional callback for execution logs

        Returns:
            StepResult: Result of the step execution
        """
        workflow_id = workflow_id or f"single_step_{int(time.time())}"

        # Create context with provided variables
        context = AgentContext(
            workflow_id=workflow_id,
            step_id=step.id,
            user_id=getattr(self.agent, 'user_id', 'default_user'),
            variables=variables,
            agent_instance=self.agent,
            tools_registry=getattr(self.agent, 'tools_registry', None),
            memory_manager=getattr(self.agent, 'memory_manager', None),
            logger=logger,
            log_callback=log_callback
        )

        try:
            return await self._execute_single_step(step, context)
        finally:
            await context.cleanup_browser_session()

    async def execute_workflow_from(
        self,
        steps: List[AgentWorkflowStep],
        start_from: str,
        variables: Dict[str, Any],
        workflow_id: str = None,
        step_callback: Optional[Any] = None,
        log_callback: Optional[Any] = None
    ) -> WorkflowResult:
        """Execute workflow starting from a specific step.

        This is useful for resuming execution or debugging from a specific point.
        You must provide the variables that would have been set by prior steps.

        Args:
            steps: List of all workflow steps
            start_from: Step ID to start execution from
            variables: Variables to inject (simulates prior step outputs)
            workflow_id: Optional workflow ID
            step_callback: Optional step progress callback
            log_callback: Optional log callback

        Returns:
            WorkflowResult: Result of the workflow execution
        """
        # Find start index
        start_index = None
        for i, step in enumerate(steps):
            if step.id == start_from:
                start_index = i
                break

        if start_index is None:
            return WorkflowResult(
                success=False,
                workflow_id=workflow_id or "unknown",
                error_message=f"Step '{start_from}' not found in workflow",
                steps=[],
                total_execution_time=0.0
            )

        # Execute from start_index
        return await self.execute_workflow(
            steps=steps[start_index:],
            workflow_id=workflow_id,
            input_data=variables,
            step_callback=step_callback,
            log_callback=log_callback
        )

    def find_step_by_id(self, steps: List[AgentWorkflowStep], step_id: str) -> Optional[AgentWorkflowStep]:
        """Find a step by ID, including nested steps in control flow.

        Args:
            steps: List of workflow steps
            step_id: The step ID to find

        Returns:
            The step if found, None otherwise
        """
        for step in steps:
            if step.id == step_id:
                return step

            # Search in nested steps
            if step.agent_type in ('if', 'while', 'foreach'):
                if step.then:
                    found = self.find_step_by_id(step.then, step_id)
                    if found:
                        return found
                if step.else_:
                    found = self.find_step_by_id(step.else_, step_id)
                    if found:
                        return found
                if step.steps:
                    found = self.find_step_by_id(step.steps, step_id)
                    if found:
                        return found

        return None

    def get_agent_stats(self) -> Dict[str, Any]:
        """Get Agent statistics"""
        return {
            "total_agents": len(self.AGENT_TYPES),
            "available_agents": list(self.AGENT_TYPES.keys())
        }