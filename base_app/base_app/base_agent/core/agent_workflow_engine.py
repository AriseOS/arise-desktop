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
                # # 检查条件
                # if step.condition and not await self._evaluate_condition(step.condition, context):
                #     logger.info(f"步骤 {step.name} 条件不满足，跳过执行")
                #     continue
                
                # 更新上下文
                context.step_id = step.id
                
                # 执行Agent步骤
                step_result = await self._execute_agent_step(step, context)
                print(f"step_result: {step_result}")
                
                # 更新上下文变量
                print(f"step_outputs: {step.outputs}")
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
            
            # 解析步骤输入数据
            resolved_input = await self._resolve_step_input(step, context)
            
            # 构建Agent输入
            agent_input = await self._build_agent_input(step, agent_type, resolved_input, context)
            print(f"agent_input {agent_input}")
            
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
    ) -> AgentInput:
        """构建Agent输入对象 - 统一的AgentInput"""
        
        # 构建完整的提示词，包含指令、输入数据和输出要求
        complete_prompt = self._build_complete_prompt(step, resolved_input, context)
        
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
        
        return AgentInput(
            instruction=complete_prompt,
            data=resolved_input,
            metadata=metadata
        )
    
    def _build_complete_prompt(
        self, 
        step: AgentWorkflowStep, 
        resolved_input: Dict[str, Any], 
        context: AgentContext
    ) -> str:
        """构建完整的大模型提示词，包含指令、输入和输出要求"""
        
        prompt_parts = []
        
        # 1. 添加任务指令
        prompt_parts.append(f"## 任务指令\n{step.agent_instruction}")
        
        # 2. 添加输入数据
        if resolved_input:
            prompt_parts.append("## 输入数据")
            for key, value in resolved_input.items():
                if isinstance(value, (dict, list)):
                    prompt_parts.append(f"**{key}**:\n```json\n{self._format_json_value(value)}\n```")
                else:
                    prompt_parts.append(f"**{key}**: {value}")
        
        # 3. 添加输出格式要求
        if step.outputs:
            prompt_parts.append("## 输出格式要求")
            prompt_parts.append("请严格按照以下JSON格式返回结果：")
            
            # 构建JSON模板
            output_template = {}
            for output_key, output_type in step.outputs.items():
                output_template[output_key] = f"<{output_type}>"
            
            prompt_parts.append("```json")
            prompt_parts.append(self._format_json_value(output_template))
            prompt_parts.append("```")
            
            # 添加字段说明
            prompt_parts.append("**字段说明：**")
            for output_key, output_type in step.outputs.items():
                prompt_parts.append(f"- **{output_key}**: {output_type}")
        
        # 4. 添加执行要求
        prompt_parts.append("""## 执行要求
1. 仔细阅读任务指令，理解要完成的具体任务
2. 基于提供的输入数据进行处理和分析
3. 严格按照输出格式要求返回结构化数据
4. 确保所有输出字段都填充准确、完整的内容
5. 输出必须是有效的JSON格式，以便后续工作流步骤正确解析

现在开始执行任务：""")
        
        return "\n\n".join(prompt_parts)
    
    def _format_json_value(self, value) -> str:
        """格式化JSON值"""
        import json
        return json.dumps(value, ensure_ascii=False, indent=2)
    
    
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
    
    def get_agent_stats(self) -> Dict[str, Any]:
        """获取Agent统计信息"""
        return {
            "registry_stats": self.agent_registry.get_agent_stats(),
            "available_agents": self.agent_executor.list_available_agents()
        }