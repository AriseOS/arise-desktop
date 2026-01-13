"""
Workflow Execution Engine
Based on Agent-as-Step architecture
"""
import asyncio
import logging
import re
import time
import traceback
from typing import List, Dict, Any, Optional, Type

from .schemas import (
    AgentWorkflowStep, WorkflowResult, StepResult,
    AgentContext, AgentInput, AgentOutput, StopSignal
)
from ..agents.base_agent import BaseStepAgent

logger = logging.getLogger(__name__)


def _get_condition_evaluator():
    """Lazy import to avoid circular dependency"""
    from ..workflows.loader import ConditionEvaluator
    return ConditionEvaluator()


class WorkflowEngine:
    """Workflow execution engine based on Agent-as-Step architecture"""

    # Agent type mapping - lazy loaded to avoid circular imports
    _agent_types_loaded: bool = False
    _AGENT_TYPES: Dict[str, Type[BaseStepAgent]] = {}

    @classmethod
    def _load_agent_types(cls):
        """Lazy load agent type mapping"""
        if cls._agent_types_loaded:
            return

        from ..agents.text_agent import TextAgent
        from ..agents.browser_agent import BrowserAgent
        from ..agents.variable_agent import VariableAgent
        from ..agents.scraper_agent import ScraperAgent
        from ..agents.storage_agent import StorageAgent
        from ..agents.autonomous_browser_agent import AutonomousBrowserAgent

        cls._AGENT_TYPES = {
            'text_agent': TextAgent,
            'variable': VariableAgent,
            'scraper_agent': ScraperAgent,
            'storage_agent': StorageAgent,
            'browser_agent': BrowserAgent,
            'autonomous_browser_agent': AutonomousBrowserAgent,
        }
        cls._agent_types_loaded = True

    @property
    def AGENT_TYPES(self) -> Dict[str, Type[BaseStepAgent]]:
        """Get agent type mapping (lazy loaded)"""
        self._load_agent_types()
        return self._AGENT_TYPES

    def __init__(self, agent_instance=None):
        self.agent = agent_instance
        self.condition_evaluator = _get_condition_evaluator()
        self._config_service = getattr(self.agent, 'config_service', None) if self.agent else None

    def _create_agent(self, agent_type: str, config: Optional[Dict] = None) -> BaseStepAgent:
        """Create agent instance"""
        agent_class = self.AGENT_TYPES.get(agent_type)
        if not agent_class:
            raise ValueError(f"Unknown agent type: {agent_type}")

        config = config or {}

        # ScraperAgent needs special handling
        if agent_type == 'scraper_agent':
            from ..agents.scraper_agent import ScraperAgent
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
        """Execute specified agent"""
        agent = self._create_agent(agent_type, agent_config)

        # Initialize agent
        if not agent.is_initialized:
            success = await agent.initialize(context)
            if not success:
                raise RuntimeError(f"Agent {agent_type} initialization failed")

        # Validate input
        if not await agent.validate_input(input_data):
            raise ValueError(f"Agent {agent_type} input validation failed")

        # Execute agent
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
        log_callback: Optional[Any] = None,
        stop_signal: Optional[StopSignal] = None
    ) -> WorkflowResult:
        """Execute workflow with optional step progress callback and stop support

        Args:
            steps: List of workflow steps
            workflow_id: Optional workflow ID
            input_data: Input data dict
            step_callback: Optional async callback function(step_index, step_name, status, result)
                          Called when step starts (status='in_progress') and completes (status='completed'/'failed')
            log_callback: Optional async callback function(level, message, metadata)
                         Called for detailed execution logs from agents
            stop_signal: Optional StopSignal for cooperative workflow stopping
        """
        start_time = time.time()
        workflow_id = workflow_id or f"workflow_{int(time.time())}"

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
        workflow_success = True
        failed_step_error = None

        try:
            for step_index, step in enumerate(steps):
                # ===== CHECK STOP SIGNAL =====
                if stop_signal and stop_signal.is_stop_requested():
                    logger.info(f"Stop requested before step {step_index}: {step.name}")
                    return WorkflowResult(
                        success=False,
                        stopped=True,
                        workflow_id=workflow_id,
                        steps=executed_steps,
                        error_message="Workflow stopped by user request",
                        total_execution_time=time.time() - start_time
                    )

                # Update context
                context.step_id = step.id

                # Notify step start
                if step_callback:
                    try:
                        await step_callback(step_index, step.name, 'in_progress', None)
                    except Exception as e:
                        logger.warning(f"Step callback error (start): {e}")

                # Execute step based on type (pass stop_signal to control flow steps)
                if step.agent_type == "if":
                    step_result = await self._execute_if_step(step, context, stop_signal)
                elif step.agent_type == "while":
                    step_result = await self._execute_while_step(step, context, stop_signal)
                elif step.agent_type == "foreach":
                    step_result = await self._execute_foreach_step(step, context, stop_signal)
                else:
                    # Check execution condition for normal steps
                    if step.condition and not await self._evaluate_condition(step.condition, context):
                        logger.info(f"Step {step.name} condition not met, skipping")
                        continue

                    # Execute normal agent step
                    step_result = await self._execute_agent_step(step, context)

                # Check if control flow step was stopped
                if hasattr(step_result, 'exit_reason') and step_result.exit_reason == 'stopped':
                    logger.info(f"Workflow stopped during control flow step: {step.name}")
                    return WorkflowResult(
                        success=False,
                        stopped=True,
                        workflow_id=workflow_id,
                        steps=executed_steps,
                        error_message="Workflow stopped by user request",
                        total_execution_time=time.time() - start_time
                    )

                # Update context variables
                if step_result.success and step.outputs:
                    await self._update_context_variables(step_result, step.outputs, context)

                executed_steps.append(step_result)

                # Notify step completion
                if step_callback:
                    try:
                        step_status = 'completed' if step_result.success else 'failed'
                        await step_callback(step_index, step.name, step_status, step_result.data)
                    except Exception as e:
                        logger.warning(f"Step callback error (complete): {e}")

                # Stop if step failed
                if not step_result.success:
                    workflow_success = False
                    failed_step_error = f"Step '{step.name}' (id={step.id}, agent={step.agent_type}) failed: {step_result.message}"
                    logger.error(f"Step execution failed [step_id={step.id}, name={step.name}, agent_type={step.agent_type}]: {step_result.message}")
                    break

            # Extract final_response as final result
            final_result = context.variables.get('final_response',
                "Sorry, system failed to generate a valid response. Please check workflow configuration.")

            return WorkflowResult(
                success=workflow_success,
                workflow_id=workflow_id,
                steps=executed_steps,
                final_result=final_result,
                error_message=failed_step_error,
                total_execution_time=time.time() - start_time
            )

        except asyncio.CancelledError:
            # Must re-raise to allow force cancel to work
            logger.info(f"Workflow {workflow_id} cancelled")
            raise

        except Exception as e:
            logger.error(f"Workflow execution failed: {str(e)}")
            return WorkflowResult(
                success=False,
                workflow_id=workflow_id,
                error_message=str(e),
                steps=executed_steps,
                total_execution_time=time.time() - start_time
            )
        finally:
            await context.cleanup_browser_session()

    async def _execute_agent_step(
        self,
        step: AgentWorkflowStep,
        context: AgentContext
    ) -> StepResult:
        """Execute agent step with unified variable resolution"""
        step_start_time = time.time()

        try:
            # Resolve variables
            resolved_dict = self._resolve_step_variables(step, context)
            agent_type = step.agent_type
            resolved_inputs = resolved_dict.get('inputs', {})

            # Debug: log resolved inputs for troubleshooting
            logger.debug(f"[{step.id}] agent_type={agent_type}, resolved_inputs keys: {list(resolved_inputs.keys())}")
            if agent_type == 'storage_agent':
                logger.info(f"[{step.id}] storage_agent inputs: operation={resolved_inputs.get('operation')}, collection={resolved_inputs.get('collection')}, data_type={type(resolved_inputs.get('data'))}")

            # Build agent input
            agent_input = await self._build_agent_input(step, agent_type, resolved_inputs, context)

            # Extract agent config
            agent_config = {}
            if hasattr(step, 'agent_config'):
                agent_config.update(step.agent_config)

            config_keys = ['extraction_method', 'dom_scope', 'debug_mode']
            for key in config_keys:
                if key in resolved_inputs:
                    agent_config[key] = resolved_inputs[key]

            # Execute agent
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
                message=f"Agent {agent_type} executed successfully",
                execution_time=time.time() - step_start_time
            )

        except asyncio.CancelledError:
            # Must re-raise to allow force cancel to work
            logger.info(f"Agent step {step.id} cancelled")
            raise

        except Exception as e:
            error_traceback = traceback.format_exc()
            logger.error(f"Agent step failed [step_id={step.id}, name={step.name}, agent_type={step.agent_type}]: {str(e)}\n{error_traceback}")
            return StepResult(
                step_id=step.id,
                success=False,
                data=None,
                message=str(e),
                error=error_traceback,
                execution_time=time.time() - step_start_time
            )

    async def _build_agent_input(
        self,
        step: AgentWorkflowStep,
        agent_type: str,
        resolved_input: Dict[str, Any],
        context: AgentContext
    ) -> AgentInput:
        """Build agent input object"""
        metadata = {
            "expected_outputs": step.outputs,
            "constraints": getattr(step, 'constraints', []),
        }

        if agent_type == "text_agent":
            metadata.update({
                "response_style": getattr(step, 'response_style', 'professional'),
                "max_length": getattr(step, 'max_length', 1000)
            })
        elif agent_type == "variable":
            resolved_data = resolved_input.get('data', {})
            logger.debug(f"[VariableAgent] step_id={step.id}, resolved_data type: {type(resolved_data)}")

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
                    "items": resolved_input.get('items', None),
                    "start": resolved_input.get('start', None),
                    "start_value": resolved_input.get('start_value', None),
                    "match_field": resolved_input.get('match_field', None),
                    "contains": resolved_input.get('contains', None),
                    "equals": resolved_input.get('equals', None)
                },
                "context": context
            })

        return AgentInput(
            data=resolved_input,
            step_metadata=metadata
        )

    def _resolve_step_variables(self, step: AgentWorkflowStep, context: AgentContext) -> Dict[str, Any]:
        """Unified step variable resolution entry point"""
        step_dict = step.model_dump()
        resolved_dict = self._resolve_value_recursive(step_dict, context)
        return resolved_dict

    def _resolve_value_recursive(self, value: Any, context: AgentContext) -> Any:
        """Recursively resolve all variable references in a value"""
        if isinstance(value, str):
            return self._resolve_string_with_variables(value, context)
        elif isinstance(value, dict):
            resolved_dict = {}
            for sub_key, sub_value in value.items():
                resolved_dict[sub_key] = self._resolve_value_recursive(sub_value, context)
            return resolved_dict
        elif isinstance(value, list):
            return [self._resolve_value_recursive(item, context) for item in value]
        else:
            return value

    def _resolve_variable(self, var_expression: str, context: AgentContext) -> Any:
        """Resolve variable expression with nested property access support"""
        parts = var_expression.split('.')
        value = context.variables.get(parts[0])

        if value is None:
            available_vars = list(context.variables.keys())
            raise ValueError(
                f"Variable '{parts[0]}' not found in context.\n"
                f"  Trying to resolve: {{{{{var_expression}}}}}\n"
                f"  Available variables: {available_vars}"
            )

        for part in parts[1:]:
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list):
                if part.isdigit():
                    idx = int(part)
                    if 0 <= idx < len(value):
                        value = value[idx]
                    else:
                        logger.warning(f"List index {idx} out of range for: {var_expression}")
                        return None
                elif part == 'length':
                    value = len(value)
                elif len(value) == 1:
                    logger.debug(f"Auto-unwrapping single-item list for: {var_expression}")
                    value = value[0]
                    if isinstance(value, dict):
                        value = value.get(part)
                    elif hasattr(value, part):
                        value = getattr(value, part)
                    else:
                        raise ValueError(f"Cannot access property '{part}' on unwrapped list item")
                else:
                    raise ValueError(
                        f"Cannot access property '{part}' on a list with {len(value)} items.\n"
                        f"  Hint: Use numeric index (e.g., {{{{list.0.{part}}}}})"
                    )
            elif hasattr(value, part):
                value = getattr(value, part)
            else:
                raise ValueError(f"Cannot access property '{part}' on {type(value).__name__}")

            if value is None:
                logger.debug(f"Property '{part}' resolved to None in: {var_expression}")
                return None

        return value

    def _resolve_string_with_variables(self, text: str, context: AgentContext) -> Any:
        """Resolve all variable references in a string"""
        pattern = r'\{\{([^}]+)\}\}'
        matches = list(re.finditer(pattern, text))

        if not matches:
            return text

        # If the entire string is a single variable reference
        if len(matches) == 1 and matches[0].group(0) == text:
            var_expression = matches[0].group(1).strip()
            return self._resolve_variable(var_expression, context)

        # String template with multiple variables
        result = text
        for match in matches:
            var_expression = match.group(1).strip()
            var_value = self._resolve_variable(var_expression, context)

            if var_value is None:
                var_str = f"{{{{{var_expression}}}}}"
            else:
                var_str = str(var_value)

            result = result.replace(match.group(0), var_str)

        return result

    async def _update_context_variables(
        self,
        step_result: StepResult,
        outputs: Dict[str, str],
        context: AgentContext
    ):
        """Update context variables from step result"""
        if not step_result.data or not isinstance(step_result.data, AgentOutput):
            return

        agent_output = step_result.data

        if "result" in agent_output.data:
            for output_key, var_name in outputs.items():
                if output_key == "result":
                    context.variables[var_name] = agent_output.data["result"]
                    logger.debug(f"Updated context variable: {var_name}")
        else:
            # Legacy format compatibility
            for output_key, var_name in outputs.items():
                if output_key in agent_output.data:
                    context.variables[var_name] = agent_output.data[output_key]
                    logger.warning(f"[Legacy] Updated context variable: {var_name}")

    async def _evaluate_condition(self, condition: Any, context: AgentContext) -> bool:
        """Evaluate condition expression.

        Args:
            condition: Can be a string expression or pre-resolved value
                (bool, int, list, etc.) from variable resolution.
            context: Agent context containing variables.

        Returns:
            bool: Evaluation result.
        """
        return self.condition_evaluator.evaluate(condition, context.variables)

    async def _execute_if_step(
        self,
        step: AgentWorkflowStep,
        context: AgentContext,
        stop_signal: Optional[StopSignal] = None
    ) -> StepResult:
        """Execute if/else control flow step"""
        step_start_time = time.time()

        try:
            resolved_dict = self._resolve_step_variables(step, context)
            resolved_condition = resolved_dict.get('condition', step.condition)
            condition_result = await self._evaluate_condition(resolved_condition, context)
            logger.info(f"If condition '{step.condition}' evaluated to: {condition_result}")

            branch_executed = "then" if condition_result else "else"
            sub_steps = step.then if condition_result else step.else_

            sub_step_results = []
            branch_success = True
            exit_reason = None

            if sub_steps:
                for sub_step in sub_steps:
                    # Check stop signal before each sub-step
                    if stop_signal and stop_signal.is_stop_requested():
                        exit_reason = "stopped"
                        logger.info(f"If step stopped during branch execution")
                        break

                    sub_result = await self._execute_single_step(sub_step, context, stop_signal)
                    sub_step_results.append(sub_result)

                    # Check if sub-step was stopped
                    if hasattr(sub_result, 'exit_reason') and sub_result.exit_reason == 'stopped':
                        exit_reason = "stopped"
                        break

                    if not sub_result.success:
                        branch_success = False
                        break

                    if sub_result.success and sub_step.outputs:
                        await self._update_context_variables(sub_result, sub_step.outputs, context)

            return StepResult(
                step_id=step.id,
                success=branch_success and exit_reason != "stopped",
                data=None,
                message=f"If step completed, branch: {branch_executed}",
                execution_time=time.time() - step_start_time,
                step_type="if",
                condition_result=condition_result,
                branch_executed=branch_executed,
                exit_reason=exit_reason,
                sub_step_results=sub_step_results
            )

        except asyncio.CancelledError:
            logger.info(f"If step {step.id} cancelled")
            raise

        except Exception as e:
            error_traceback = traceback.format_exc()
            logger.error(f"If step failed: {str(e)}\n{error_traceback}")
            return StepResult(
                step_id=step.id,
                success=False,
                data=None,
                message=str(e),
                error=error_traceback,
                execution_time=time.time() - step_start_time,
                step_type="if"
            )

    async def _execute_while_step(
        self,
        step: AgentWorkflowStep,
        context: AgentContext,
        stop_signal: Optional[StopSignal] = None
    ) -> StepResult:
        """Execute while loop control flow step"""
        step_start_time = time.time()

        try:
            resolved_dict = self._resolve_step_variables(step, context)
            max_iterations = step.max_iterations
            loop_timeout = step.loop_timeout  # None means no timeout
            iterations_executed = 0
            sub_step_results = []
            exit_reason = "condition_false"

            while max_iterations is None or iterations_executed < max_iterations:
                # ===== CHECK STOP SIGNAL =====
                if stop_signal and stop_signal.is_stop_requested():
                    exit_reason = "stopped"
                    logger.info(f"While loop stopped at iteration {iterations_executed}")
                    break

                if loop_timeout and time.time() - step_start_time > loop_timeout:
                    exit_reason = "timeout"
                    break

                resolved_condition = resolved_dict.get('condition', step.condition)
                condition_result = await self._evaluate_condition(resolved_condition, context)
                logger.info(f"While condition '{step.condition}' evaluated to: {condition_result} (iteration {iterations_executed + 1})")

                if not condition_result:
                    exit_reason = "condition_false"
                    break

                iteration_success = True
                iteration_results = []

                if step.steps:
                    for sub_step in step.steps:
                        sub_result = await self._execute_single_step(sub_step, context, stop_signal)
                        iteration_results.append(sub_result)

                        # Check if sub-step was stopped
                        if hasattr(sub_result, 'exit_reason') and sub_result.exit_reason == 'stopped':
                            exit_reason = "stopped"
                            iteration_success = False
                            break

                        if not sub_result.success:
                            iteration_success = False
                            exit_reason = "step_failed"
                            break

                        if sub_result.success and sub_step.outputs:
                            await self._update_context_variables(sub_result, sub_step.outputs, context)

                sub_step_results.extend(iteration_results)
                iterations_executed += 1

                if not iteration_success:
                    break

            if max_iterations is not None and iterations_executed >= max_iterations and exit_reason == "condition_false":
                exit_reason = "max_iterations_reached"

            return StepResult(
                step_id=step.id,
                success=(exit_reason not in ("stopped", "step_failed")),
                data=None,
                message=f"While loop completed, {iterations_executed} iterations, exit: {exit_reason}",
                execution_time=time.time() - step_start_time,
                step_type="while",
                iterations_executed=iterations_executed,
                exit_reason=exit_reason,
                sub_step_results=sub_step_results
            )

        except asyncio.CancelledError:
            logger.info(f"While step {step.id} cancelled")
            raise

        except Exception as e:
            error_traceback = traceback.format_exc()
            logger.error(f"While step failed: {str(e)}\n{error_traceback}")
            return StepResult(
                step_id=step.id,
                success=False,
                data=None,
                message=str(e),
                error=error_traceback,
                execution_time=time.time() - step_start_time,
                step_type="while"
            )

    async def _execute_foreach_step(
        self,
        step: AgentWorkflowStep,
        context: AgentContext,
        stop_signal: Optional[StopSignal] = None
    ) -> StepResult:
        """Execute foreach loop control flow step"""
        step_start_time = time.time()

        try:
            source_var = step.source
            if not source_var:
                raise ValueError("foreach step missing source configuration")

            # Resolve source variable
            if isinstance(source_var, str) and source_var.startswith('{{') and source_var.endswith('}}'):
                var_expr = source_var[2:-2].strip()
                source_list = self._resolve_variable(var_expr, context)
            else:
                source_list = source_var

            max_iterations = step.max_iterations
            loop_timeout = step.loop_timeout  # None means no timeout

            if not source_list:
                raise ValueError("foreach step source resolved to empty")

            if not isinstance(source_list, list):
                raise ValueError(f"source must resolve to list, got: {type(source_list)}")

            logger.info(f"Foreach loop starting, iterating over {len(source_list)} items")

            item_var = step.item_var or "item"
            index_var = step.index_var or "index"

            iterations_executed = 0
            sub_step_results = []
            exit_reason = "completed"

            for index, item in enumerate(source_list):
                # ===== CHECK STOP SIGNAL =====
                if stop_signal and stop_signal.is_stop_requested():
                    exit_reason = "stopped"
                    logger.info(f"Foreach loop stopped at iteration {iterations_executed}")
                    break

                if max_iterations is not None and iterations_executed >= max_iterations:
                    exit_reason = "max_iterations_reached"
                    logger.warning(f"Max iterations {max_iterations} reached")
                    break

                if loop_timeout and time.time() - step_start_time > loop_timeout:
                    exit_reason = "timeout"
                    logger.warning(f"Timeout {loop_timeout}s reached")
                    break

                context.variables[item_var] = item
                context.variables[index_var] = index

                logger.info(f"Foreach iteration {index + 1}/{len(source_list)}")

                iteration_success = True
                iteration_results = []

                if step.steps:
                    for sub_step in step.steps:
                        sub_result = await self._execute_single_step(sub_step, context, stop_signal)
                        iteration_results.append(sub_result)

                        # Check if sub-step was stopped
                        if hasattr(sub_result, 'exit_reason') and sub_result.exit_reason == 'stopped':
                            exit_reason = "stopped"
                            iteration_success = False
                            break

                        if not sub_result.success:
                            iteration_success = False
                            exit_reason = "step_failed"
                            logger.error(f"Foreach iteration {index + 1} step failed: {sub_step.name}")
                            break

                        if sub_result.success and sub_step.outputs:
                            await self._update_context_variables(sub_result, sub_step.outputs, context)

                sub_step_results.extend(iteration_results)
                iterations_executed += 1

                if not iteration_success:
                    break

            # Cleanup loop variables
            if item_var in context.variables:
                del context.variables[item_var]
            if index_var in context.variables:
                del context.variables[index_var]

            return StepResult(
                step_id=step.id,
                success=(exit_reason not in ("stopped", "step_failed")),
                data=None,
                message=f"Foreach completed, {iterations_executed}/{len(source_list)} items, exit: {exit_reason}",
                execution_time=time.time() - step_start_time,
                step_type="foreach",
                iterations_executed=iterations_executed,
                exit_reason=exit_reason,
                sub_step_results=sub_step_results
            )

        except asyncio.CancelledError:
            logger.info(f"Foreach step {step.id} cancelled")
            raise

        except Exception as e:
            error_traceback = traceback.format_exc()
            logger.error(f"Foreach step failed: {str(e)}\n{error_traceback}")
            return StepResult(
                step_id=step.id,
                success=False,
                data=None,
                message=str(e),
                error=error_traceback,
                execution_time=time.time() - step_start_time,
                step_type="foreach"
            )

    async def _execute_single_step(
        self,
        step: AgentWorkflowStep,
        context: AgentContext,
        stop_signal: Optional[StopSignal] = None
    ) -> StepResult:
        """Execute a single step (agent or control flow)"""
        original_step_id = context.step_id
        context.step_id = step.id

        try:
            if step.agent_type == "if":
                return await self._execute_if_step(step, context, stop_signal)
            elif step.agent_type == "while":
                return await self._execute_while_step(step, context, stop_signal)
            elif step.agent_type == "foreach":
                return await self._execute_foreach_step(step, context, stop_signal)
            else:
                if step.condition and not await self._evaluate_condition(step.condition, context):
                    logger.info(f"Step {step.name} condition not met, skipping")
                    return StepResult(
                        step_id=step.id,
                        success=True,
                        data=None,
                        message="Condition not met, skipped",
                        execution_time=0.0
                    )

                return await self._execute_agent_step(step, context)
        finally:
            context.step_id = original_step_id

    async def execute_step(
        self,
        step: AgentWorkflowStep,
        variables: Dict[str, Any],
        workflow_id: str = None,
        log_callback: Optional[Any] = None
    ) -> StepResult:
        """Execute a single step with provided variables (for debugging)"""
        workflow_id = workflow_id or f"single_step_{int(time.time())}"

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
        """Execute workflow starting from a specific step (for resuming/debugging)"""
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

        return await self.execute_workflow(
            steps=steps[start_index:],
            workflow_id=workflow_id,
            input_data=variables,
            step_callback=step_callback,
            log_callback=log_callback
        )

    def find_step_by_id(self, steps: List[AgentWorkflowStep], step_id: str) -> Optional[AgentWorkflowStep]:
        """Find a step by ID, including nested steps in control flow"""
        for step in steps:
            if step.id == step_id:
                return step

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
        """Get agent statistics"""
        return {
            "total_agents": len(self.AGENT_TYPES),
            "available_agents": list(self.AGENT_TYPES.keys())
        }
