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
    AgentContext, TextAgentInput, ToolAgentInput, CodeAgentInput
)
from ..agents import (
    AgentRegistry, AgentRouter, AgentExecutor,
    TextAgent, ToolAgent, CodeAgent
)

logger = logging.getLogger(__name__)


class AgentWorkflowEngine:
    """基于Agent的工作流执行引擎"""
    
    def __init__(self, agent_instance=None):
        self.agent = agent_instance
        self.agent_registry = AgentRegistry()
        self.agent_executor = AgentExecutor(self.agent_registry)
        self.agent_router = AgentRouter(self.agent_registry)
        
        # 注册内置Agent
        self._register_builtin_agents()
    
    def _register_builtin_agents(self):
        """注册内置Agent"""
        # 注册Text Agent
        text_agent = TextAgent()
        self.agent_registry.register_agent(text_agent)
        
        # 注册Tool Agent
        tool_agent = ToolAgent()
        self.agent_registry.register_agent(tool_agent)
        
        # 注册Code Agent (使用标准名称)
        code_agent = CodeAgent("python")
        # 修改Code Agent的名称为标准名称
        code_agent.metadata.name = "code_agent"
        self.agent_registry.register_agent(code_agent)
        
        logger.info(f"已注册内置Agent: {self.agent_registry.list_agent_names()}")
    
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
                # 检查条件
                if step.condition and not await self._evaluate_condition(step.condition, context):
                    logger.info(f"步骤 {step.name} 条件不满足，跳过执行")
                    continue
                
                # 更新上下文
                context.step_id = step.id
                
                # 执行Agent步骤
                step_result = await self._execute_agent_step(step, context)
                
                # 更新上下文变量
                if step_result.success and step.outputs:
                    await self._update_context_variables(step_result, step.outputs, context)
                    # 更新最后一步的输出
                    last_step_output = await self._extract_step_outputs(step_result, step.outputs)
                
                executed_steps.append(step_result)
                
                # 如果步骤失败且没有设置继续执行，则停止
                if not step_result.success:
                    logger.error(f"步骤 {step.name} 执行失败: {step_result.message}")
                    break
            
            return WorkflowResult(
                success=True,
                workflow_id=workflow_id,
                steps=executed_steps,
                final_result=last_step_output if last_step_output is not None else context.variables, 
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
            if agent_type == "auto":
                # 自动路由选择Agent，使用agent_instruction
                agent_type = await self.agent_router.route_to_agent(step.agent_instruction, context)
                logger.info(f"自动路由选择Agent: {agent_type}")
            
            # 解析步骤输入数据
            resolved_input = await self._resolve_step_input(step, context)
            
            # 构建Agent输入
            agent_input = await self._build_agent_input(step, agent_type, resolved_input, context)
            
            # 执行Agent
            result = await self.agent_executor.execute_agent(
                agent_type,
                agent_input,
                context
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
    ) -> Any:
        """构建Agent输入对象"""
        # 从输入中获取任务描述，如果没有则使用agent_instruction
        task_description = resolved_input.get("task_description", step.agent_instruction)
        
        if agent_type == "text_agent":
            return TextAgentInput(
                question=resolved_input.get("question", task_description),
                context_data=resolved_input.get("context_data", {}),
                response_style=step.response_style,
                max_length=step.max_length
            )
        
        elif agent_type == "tool_agent":
            return ToolAgentInput(
                task_description=task_description,
                context_data=resolved_input.get("context_data", {}),
                constraints=step.constraints,
                allowed_tools=step.allowed_tools,
                fallback_tools=step.fallback_tools,
                confidence_threshold=step.confidence_threshold
            )
        
        elif agent_type == "code_agent":
            return CodeAgentInput(
                task_description=task_description,
                input_data=resolved_input.get("input_data", {}),
                expected_output_format=step.expected_output_format,
                constraints=step.constraints,
                libraries_allowed=step.allowed_libraries
            )
        
        else:
            raise ValueError(f"不支持的Agent类型: {agent_type}")
    
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
        if not step_result.data:
            return
        
        for output_key, var_name in outputs.items():
            if hasattr(step_result.data, output_key):
                value = getattr(step_result.data, output_key)
                context.variables[var_name] = value
                logger.debug(f"更新上下文变量: {var_name} = {value}")
            elif isinstance(step_result.data, dict) and output_key in step_result.data:
                context.variables[var_name] = step_result.data[output_key]
                logger.debug(f"更新上下文变量: {var_name} = {step_result.data[output_key]}")
    
    async def _extract_step_outputs(
        self, 
        step_result: StepResult, 
        outputs: Dict[str, str]
    ) -> Any:
        """提取当前步骤的输出值"""
        if not step_result.data or not outputs:
            return None
        
        step_outputs = {}
        for output_key, var_name in outputs.items():
            if hasattr(step_result.data, output_key):
                value = getattr(step_result.data, output_key)
                step_outputs[var_name] = value
            elif isinstance(step_result.data, dict) and output_key in step_result.data:
                step_outputs[var_name] = step_result.data[output_key]
        
        # 如果只有一个输出，直接返回值；否则返回字典
        if len(step_outputs) == 1:
            return list(step_outputs.values())[0]
        elif len(step_outputs) > 1:
            return step_outputs
        else:
            return None
    
    async def _evaluate_condition(self, condition: str, context: AgentContext) -> bool:
        """评估执行条件"""
        try:
            # 简单的条件评估，可以后续扩展
            # 替换变量引用
            import re
            def replace_var(match):
                var_name = match.group(1).strip()
                value = context.variables.get(var_name, None)
                if value is None:
                    return "None"
                elif isinstance(value, str):
                    return f"'{value}'"
                else:
                    return str(value)
            
            resolved_condition = re.sub(r'\{\{([^}]+)\}\}', replace_var, condition)
            
            # 安全的条件评估
            allowed_names = {
                "True": True, "False": False, "None": None,
                "true": True, "false": False, "null": None,  # 支持小写布尔值
                "and": lambda a, b: a and b,
                "or": lambda a, b: a or b,
                "not": lambda a: not a,
            }
            
            return eval(resolved_condition, {"__builtins__": {}}, allowed_names)
            
        except Exception as e:
            logger.warning(f"条件评估失败: {condition}, 错误: {str(e)}")
            return True  # 默认执行
    
    def get_agent_stats(self) -> Dict[str, Any]:
        """获取Agent统计信息"""
        return {
            "registry_stats": self.agent_registry.get_agent_stats(),
            "available_agents": self.agent_executor.list_available_agents()
        }