"""
Agent工作流执行引擎
基于Agent-as-Step架构的工作流执行引擎
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

from .schemas import (
    AgentWorkflowStep, WorkflowResult, StepResult, 
    AgentContext, AgentInput, AgentOutput
)
from ..agents import (
    AgentRegistry, AgentRouter, AgentExecutor,
    TextAgent, ToolAgent, CodeAgent
)
from ..agents.variable_agent import VariableAgent
from ..agents.scraper_agent import ScraperAgent
from ..workflows.workflow_loader import ConditionEvaluator

logger = logging.getLogger(__name__)


class AgentWorkflowEngine:
    """基于Agent的工作流执行引擎"""
    
    def __init__(self, agent_instance=None):
        self.agent = agent_instance
        self.agent_registry = AgentRegistry()
        self.agent_executor = AgentExecutor(self.agent_registry)
        self.agent_router = AgentRouter(self.agent_registry)
        self.condition_evaluator = ConditionEvaluator()
        
        # 注册内置Agent
        self._register_builtin_agents()
    
    def _register_builtin_agents(self):
        """注册内置Agent工厂函数"""
        # 获取config_service
        config_service = getattr(self.agent, 'config_service', None) if self.agent else None

        # 注册Text Agent工厂
        self.agent_registry.register_agent_factory(
            "text_agent",
            lambda config: TextAgent()
        )

        # 注册Tool Agent工厂
        self.agent_registry.register_agent_factory(
            "tool_agent",
            lambda config: ToolAgent()
        )

        # 注册Code Agent工厂
        def create_code_agent(config):
            agent = CodeAgent("python")
            agent.metadata.name = "code_agent"
            return agent

        self.agent_registry.register_agent_factory(
            "code_agent",
            create_code_agent
        )

        # 注册Variable Agent工厂
        self.agent_registry.register_agent_factory(
            "variable",
            lambda config: VariableAgent()
        )

        # 注册Scraper Agent工厂 - 支持默认配置
        def create_scraper_agent(config):
            # 可以从config传递默认值，运行时还能覆盖
            return ScraperAgent(
                config_service=config_service,
                extraction_method=config.get('extraction_method', 'llm'),  # 默认用llm
                dom_scope=config.get('dom_scope', 'partial'),
                debug_mode=config.get('debug_mode', False)
            )

        self.agent_registry.register_agent_factory(
            "scraper_agent",
            create_scraper_agent
        )

        logger.info(f"已注册内置Agent工厂: {self.agent_registry.list_agent_names()}")
    
    async def execute_workflow(
        self,
        steps: List[AgentWorkflowStep],
        workflow_id: str = None,
        input_data: Dict[str, Any] = None
    ) -> WorkflowResult:
        """执行Agent工作流"""
        start_time = time.time()
        workflow_id = workflow_id or f"agent_workflow_{int(time.time())}"

        # 初始化执行上下文
        context = AgentContext(
            workflow_id=workflow_id,
            step_id="",
            variables=input_data or {},
            agent_instance=self.agent,
            tools_registry=getattr(self.agent, 'tools_registry', None),
            memory_manager=getattr(self.agent, 'memory_manager', None),
            logger=logger
        )
        
        executed_steps = []
        last_step_output = None  # 跟踪最后一步的输出
        
        try:
            for step in steps:
                # 更新上下文
                context.step_id = step.id
                
                # 根据步骤类型执行不同逻辑
                if step.agent_type == "if":
                    step_result = await self._execute_if_step(step, context)
                elif step.agent_type == "while": 
                    step_result = await self._execute_while_step(step, context)
                else:
                    # 检查普通步骤的执行条件
                    if step.condition and not await self._evaluate_condition(step.condition, context):
                        logger.info(f"步骤 {step.name} 条件不满足，跳过执行")
                        continue
                    
                    # 执行普通Agent步骤
                    step_result = await self._execute_agent_step(step, context)
                print(f"step_result: {step_result}")
                
                # 更新上下文变量
                if step_result.success and step.outputs:
                    await self._update_context_variables(step_result, step.outputs, context)
                    # 更新最后一步的输出
                    last_step_output = await self._extract_step_outputs(step_result, step.outputs)
                print(f"last_step_output {last_step_output}")
                
                executed_steps.append(step_result)
                
                # 如果步骤失败且没有设置继续执行，则停止
                if not step_result.success:
                    logger.error(f"步骤 {step.name} 执行失败: {step_result.message}")
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
        """执行Agent步骤"""
        step_start_time = time.time()

        try:
            # 确定Agent类型
            agent_type = step.agent_type

            # 解析步骤输入数据
            resolved_input = await self._resolve_step_input(step, context)

            # 构建Agent输入
            agent_input = await self._build_agent_input(step, agent_type, resolved_input, context)
            print(f"agent_input {agent_input}")

            # 提取agent配置（从step的agent_config字段或inputs中）
            agent_config = {}

            # 1. 从step的agent_config字段获取（如果有）
            if hasattr(step, 'agent_config'):
                agent_config.update(step.agent_config)

            # 2. 从inputs中提取特定的配置参数
            config_keys = ['extraction_method', 'dom_scope', 'debug_mode']
            for key in config_keys:
                if key in resolved_input:
                    agent_config[key] = resolved_input[key]

            # 执行Agent
            result = await self.agent_executor.execute_agent(
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
            logger.error(f"Agent步骤执行失败: {str(e)}")
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
        if agent_type == "tool_agent":
            metadata.update({
                "allowed_tools": getattr(step, 'allowed_tools', []),
                "fallback_tools": getattr(step, 'fallback_tools', []),
                "confidence_threshold": getattr(step, 'confidence_threshold', 0.7)
            })
        elif agent_type == "code_agent":
            metadata.update({
                "expected_output_format": getattr(step, 'expected_output_format', 'any'),
                "libraries_allowed": getattr(step, 'allowed_libraries', ['json', 'math', 'datetime', 're'])
            })
        elif agent_type == "text_agent":
            metadata.update({
                "response_style": getattr(step, 'response_style', 'professional'),
                "max_length": getattr(step, 'max_length', 1000)
            })
        elif agent_type == "variable":
            # Variable agent uses step_config for operation details
            step_data = getattr(step, 'data', {})
            logger.debug(f"Variable agent step.data: {step_data}")
            metadata.update({
                "step_config": {
                    "operation": getattr(step, 'operation', 'set'),
                    "data": step_data,
                    "source": getattr(step, 'source', None),
                    "field": getattr(step, 'field', None),
                    "value": getattr(step, 'value', None),
                    "expression": getattr(step, 'expression', None),
                    "updates": getattr(step, 'updates', None),
                    "current_page": getattr(step, 'current_page', None),
                    "max_pages": getattr(step, 'max_pages', None),
                    "items_found": getattr(step, 'items_found', None)
                },
                "context": context
            })

        return AgentInput(
            instruction=step.agent_instruction,  # 原始指令
            data=resolved_input,                 # 解析后的输入数据
            step_metadata=metadata
        )
    
    
    async def _resolve_step_input(
        self, 
        step: AgentWorkflowStep, 
        context: AgentContext
    ) -> Dict[str, Any]:
        """解析步骤输入数据"""
        resolved_input = {}
        
        for key, value in step.inputs.items():
            if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                var_name = value[2:-2].strip()
                resolved_input[key] = context.variables.get(var_name, value)
            elif isinstance(value, dict):
                # 递归解析嵌套字典
                resolved_dict = {}
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, str) and sub_value.startswith("{{") and sub_value.endswith("}}"):
                        var_name = sub_value[2:-2].strip()
                        resolved_dict[sub_key] = context.variables.get(var_name, sub_value)
                    else:
                        resolved_dict[sub_key] = sub_value
                resolved_input[key] = resolved_dict
            else:
                resolved_input[key] = value
        
        return resolved_input
    
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
        """执行if/else条件控制步骤"""
        step_start_time = time.time()
        
        try:
            # 评估条件
            condition_result = await self._evaluate_condition(step.condition, context)
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
        """执行while循环控制步骤"""
        step_start_time = time.time()
        max_iterations = step.max_iterations or 10
        loop_timeout = step.loop_timeout or 300
        
        try:
            iterations_executed = 0
            sub_step_results = []
            exit_reason = "condition_false"
            
            while iterations_executed < max_iterations:
                # 检查超时
                if time.time() - step_start_time > loop_timeout:
                    exit_reason = "timeout"
                    break
                
                # 评估循环条件
                condition_result = await self._evaluate_condition(step.condition, context)
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
            
            if iterations_executed >= max_iterations:
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
    
    def get_agent_stats(self) -> Dict[str, Any]:
        """获取Agent统计信息"""
        return {
            "registry_stats": self.agent_registry.get_agent_stats(),
            "available_agents": self.agent_executor.list_available_agents()
        }