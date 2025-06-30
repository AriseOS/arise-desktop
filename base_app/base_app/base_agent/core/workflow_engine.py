"""
工作流执行引擎
负责执行多步骤工作流，支持条件判断、依赖管理、错误处理等
"""
import asyncio
import logging
import re
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable

from .schemas import (
    WorkflowStep, WorkflowResult, Workflow, ExecutionContext,
    StepResult, StepType, ErrorHandling
)

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """
    工作流执行引擎
    
    核心功能：
    - 支持四种步骤类型：agent、tool、code、memory
    - 步骤依赖管理和条件判断
    - 变量引用和上下文传递
    - 错误处理和重试机制
    - 执行监控和日志记录
    """
    
    def __init__(self, agent_instance=None):
        """
        初始化工作流引擎
        
        Args:
            agent_instance: BaseAgent实例，用于调用工具和内存操作
        """
        self.agent = agent_instance
        self._step_executors = {
            StepType.AGENT: self._execute_agent_step,
            StepType.TOOL: self._execute_tool_step,
            StepType.CODE: self._execute_code_step,
            StepType.MEMORY: self._execute_memory_step
        }
    
    async def execute_workflow(
        self, 
        workflow: Workflow, 
        input_data: Dict[str, Any] = None
    ) -> WorkflowResult:
        """
        执行完整工作流
        
        Args:
            workflow: 工作流定义
            input_data: 输入数据
            
        Returns:
            WorkflowResult: 执行结果
        """
        return await self.execute_steps(
            workflow.steps, 
            workflow_id=workflow.id,
            input_data=input_data or {}
        )
    
    async def execute_steps(
        self, 
        steps: List[WorkflowStep], 
        workflow_id: str = None,
        input_data: Dict[str, Any] = None
    ) -> WorkflowResult:
        """
        执行工作流步骤列表
        
        Args:
            steps: 工作流步骤列表
            workflow_id: 工作流ID
            input_data: 输入数据
            
        Returns:
            WorkflowResult: 执行结果
        """
        start_time = time.time()
        workflow_id = workflow_id or f"workflow_{int(time.time())}"
        
        # 初始化执行上下文
        context = ExecutionContext(
            workflow_id=workflow_id,
            variables=input_data or {}
        )
        
        # 验证工作流
        if not await self.validate_workflow(steps):
            return WorkflowResult(
                success=False,
                workflow_id=workflow_id,
                error_message="工作流验证失败",
                total_execution_time=time.time() - start_time
            )
        
        logger.info(f"开始执行工作流 {workflow_id}，共 {len(steps)} 个步骤")
        
        try:
            # 执行所有步骤
            for i, step in enumerate(steps):
                context.current_step_index = i
                
                # 检查依赖
                if not await self._check_dependencies(step, context):
                    logger.warning(f"步骤 {step.name} 依赖不满足，跳过执行")
                    context.failed_steps.append(step.id)
                    continue
                
                # 检查执行条件
                if step.condition and not await self._evaluate_condition(step.condition, context):
                    logger.info(f"步骤 {step.name} 条件不满足，跳过执行")
                    continue
                
                # 执行单个步骤
                step_result = await self._execute_single_step(step, context)
                
                # 处理执行结果
                if step_result.success:
                    context.completed_steps.append(step.id)
                    context.step_results[step.id] = step_result.data
                    
                    # 存储输出变量
                    if step.output_key:
                        context.variables[step.output_key] = step_result.data
                    
                    logger.info(f"步骤 {step.name} 执行成功")
                else:
                    context.failed_steps.append(step.id)
                    logger.error(f"步骤 {step.name} 执行失败: {step_result.message}")
                    
                    # 根据错误处理策略决定是否继续
                    if step.error_handling == ErrorHandling.STOP:
                        logger.error("遇到停止错误，终止工作流执行")
                        break
            
            # 计算执行结果
            execution_time = time.time() - start_time
            success = len(context.failed_steps) == 0
            
            result = WorkflowResult(
                success=success,
                workflow_id=workflow_id,
                completed_steps=context.completed_steps,
                failed_steps=context.failed_steps,
                step_results=context.step_results,
                total_execution_time=execution_time,
                output_variables=context.variables,
                completed_at=datetime.now()
            )
            
            # 设置最终结果
            if context.step_results:
                # 使用最后一个成功步骤的结果作为最终结果
                last_result_key = context.completed_steps[-1] if context.completed_steps else None
                if last_result_key:
                    result.final_result = context.step_results.get(last_result_key)
            
            logger.info(f"工作流 {workflow_id} 执行完成，成功: {success}，耗时: {execution_time:.2f}秒")
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"工作流执行异常: {e}")
            
            return WorkflowResult(
                success=False,
                workflow_id=workflow_id,
                completed_steps=context.completed_steps,
                failed_steps=context.failed_steps,
                step_results=context.step_results,
                total_execution_time=execution_time,
                error_message=str(e),
                completed_at=datetime.now()
            )
    
    async def _execute_single_step(
        self, 
        step: WorkflowStep, 
        context: ExecutionContext
    ) -> StepResult:
        """
        执行单个步骤
        
        Args:
            step: 工作流步骤
            context: 执行上下文
            
        Returns:
            StepResult: 步骤执行结果
        """
        step_start_time = time.time()
        
        try:
            # 解析步骤参数中的变量引用
            resolved_params = await self._resolve_variables(step.params, context)
            
            # 更新步骤参数
            resolved_step = step.copy()
            resolved_step.params = resolved_params
            
            # 解析其他字段中的变量引用
            if step.agent_input:
                resolved_step.agent_input = await self._resolve_variables(step.agent_input, context)
            if step.code:
                resolved_step.code = await self._resolve_variables(step.code, context)
            if step.query:
                resolved_step.query = await self._resolve_variables(step.query, context)
            
            # 根据步骤类型执行
            executor = self._step_executors.get(step.step_type)
            if not executor:
                raise ValueError(f"不支持的步骤类型: {step.step_type}")
            
            # 执行步骤（支持重试）
            result_data = await self._execute_with_retry(
                executor, resolved_step, context, step.retry_count
            )
            
            execution_time = time.time() - step_start_time
            
            return StepResult(
                step_id=step.id,
                success=True,
                data=result_data,
                message=f"步骤 {step.name} 执行成功",
                execution_time=execution_time,
                completed_at=datetime.now()
            )
            
        except Exception as e:
            execution_time = time.time() - step_start_time
            error_msg = f"步骤 {step.name} 执行失败: {str(e)}"
            
            return StepResult(
                step_id=step.id,
                success=False,
                data=None,
                message=error_msg,
                error=str(e),
                execution_time=execution_time,
                completed_at=datetime.now()
            )
    
    async def _execute_with_retry(
        self, 
        executor: Callable, 
        step: WorkflowStep, 
        context: ExecutionContext,
        max_retries: int
    ) -> Any:
        """
        带重试的步骤执行
        
        Args:
            executor: 执行器函数
            step: 工作流步骤
            context: 执行上下文
            max_retries: 最大重试次数
            
        Returns:
            Any: 执行结果
        """
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                # 设置超时
                result = await asyncio.wait_for(
                    executor(step, context),
                    timeout=step.timeout
                )
                return result
                
            except asyncio.TimeoutError:
                last_error = f"步骤执行超时 ({step.timeout}秒)"
                logger.warning(f"步骤 {step.name} 超时，尝试 {attempt + 1}/{max_retries + 1}")
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"步骤 {step.name} 执行失败，尝试 {attempt + 1}/{max_retries + 1}: {e}")
            
            # 如果不是最后一次尝试，等待一段时间再重试
            if attempt < max_retries:
                await asyncio.sleep(1.0)  # 等待1秒再重试
        
        # 所有重试都失败
        raise Exception(f"步骤执行失败，已重试 {max_retries} 次: {last_error}")
    
    # ==================== 步骤执行器 ====================
    
    async def _execute_agent_step(
        self, 
        step: WorkflowStep, 
        context: ExecutionContext
    ) -> Any:
        """执行Agent步骤"""
        if not step.agent_name:
            raise ValueError("Agent步骤缺少agent_name参数")
        
        # TODO: 实现Agent调用逻辑
        # 这里需要实现调用其他Agent的逻辑
        logger.info(f"执行Agent步骤: {step.agent_name}")
        
        # 暂时返回模拟结果
        return {
            "agent_name": step.agent_name,
            "input": step.agent_input,
            "result": "Agent执行结果"
        }
    
    async def _execute_tool_step(
        self, 
        step: WorkflowStep, 
        context: ExecutionContext
    ) -> Any:
        """执行工具步骤"""
        if not step.tool_name or not step.action:
            raise ValueError("工具步骤缺少tool_name或action参数")
        
        if not self.agent:
            raise ValueError("工具步骤需要Agent实例")
        
        # 调用Agent的工具方法
        tool_result = await self.agent.use_tool(
            step.tool_name, 
            step.action, 
            step.params
        )
        
        if not tool_result.success:
            raise Exception(f"工具调用失败: {tool_result.message}")
        
        return tool_result.data
    
    async def _execute_code_step(
        self, 
        step: WorkflowStep, 
        context: ExecutionContext
    ) -> Any:
        """执行代码步骤"""
        if not step.code:
            raise ValueError("代码步骤缺少code参数")
        
        # 准备执行环境
        exec_globals = {
            'context': context,
            'variables': context.variables,
            'step_results': context.step_results,
            'print': print,
            'len': len,
            'str': str,
            'int': int,
            'float': float,
            'list': list,
            'dict': dict,
        }
        
        exec_locals = {}
        
        try:
            # 执行代码
            exec(step.code, exec_globals, exec_locals)
            
            # 返回result变量或最后一个表达式的值
            if 'result' in exec_locals:
                return exec_locals['result']
            elif exec_locals:
                # 返回最后定义的变量
                return list(exec_locals.values())[-1]
            else:
                return None
                
        except Exception as e:
            raise Exception(f"代码执行失败: {str(e)}")
    
    async def _execute_memory_step(
        self, 
        step: WorkflowStep, 
        context: ExecutionContext
    ) -> Any:
        """执行内存步骤"""
        if not step.memory_action:
            raise ValueError("内存步骤缺少memory_action参数")
        
        if not self.agent:
            raise ValueError("内存步骤需要Agent实例")
        
        action = step.memory_action.lower()
        
        if action == "store":
            # 存储内存
            if not step.memory_key:
                raise ValueError("存储操作缺少memory_key参数")
            
            value = step.memory_value if step.memory_value is not None else step.params.get("value")
            await self.agent.store_memory(step.memory_key, value)
            return value
            
        elif action == "get":
            # 获取内存
            if not step.memory_key:
                raise ValueError("获取操作缺少memory_key参数")
            
            default = step.params.get("default")
            return await self.agent.get_memory(step.memory_key, default)
            
        elif action == "search":
            # 搜索记忆（长期记忆）
            if not step.query:
                raise ValueError("搜索操作缺少query参数")
            
            # 检查是否有memory manager实例
            if hasattr(self.agent, 'memory_manager') and self.agent.memory_manager:
                limit = step.params.get("limit", 5)
                user_id = step.params.get("user_id")
                
                results = await self.agent.memory_manager.search_long_term_memory(
                    step.query, user_id, limit
                )
                return results
            else:
                logger.warning("长期记忆未启用，返回空结果")
                return []
                
        else:
            raise ValueError(f"不支持的内存操作: {action}")
    
    # ==================== 辅助方法 ====================
    
    async def _check_dependencies(
        self, 
        step: WorkflowStep, 
        context: ExecutionContext
    ) -> bool:
        """检查步骤依赖"""
        for dep_id in step.depends_on:
            if dep_id not in context.completed_steps:
                return False
        return True
    
    async def _evaluate_condition(
        self, 
        condition: str, 
        context: ExecutionContext
    ) -> bool:
        """评估执行条件"""
        try:
            # 替换变量引用
            resolved_condition = await self._resolve_variables(condition, context)
            
            # 准备评估环境
            eval_globals = {
                'context': context,
                'variables': context.variables,
                'step_results': context.step_results,
            }
            
            # 评估条件表达式
            result = eval(resolved_condition, eval_globals)
            return bool(result)
            
        except Exception as e:
            logger.error(f"条件评估失败: {condition}, 错误: {e}")
            return False
    
    async def _resolve_variables(
        self, 
        value: Any, 
        context: ExecutionContext
    ) -> Any:
        """解析变量引用"""
        if isinstance(value, str):
            # 匹配 {{variable_name}} 模式
            pattern = r'\{\{([^}]+)\}\}'
            
            def replace_var(match):
                var_name = match.group(1).strip()
                
                # 先在variables中查找
                if var_name in context.variables:
                    return str(context.variables[var_name])
                
                # 再在step_results中查找
                if var_name in context.step_results:
                    return str(context.step_results[var_name])
                
                # 如果找不到，保持原样
                logger.warning(f"变量 {var_name} 未找到")
                return match.group(0)
            
            return re.sub(pattern, replace_var, value)
            
        elif isinstance(value, dict):
            # 递归处理字典
            resolved = {}
            for k, v in value.items():
                resolved[k] = await self._resolve_variables(v, context)
            return resolved
            
        elif isinstance(value, list):
            # 递归处理列表
            return [await self._resolve_variables(item, context) for item in value]
            
        else:
            # 其他类型直接返回
            return value
    
    async def validate_workflow(self, steps: List[WorkflowStep]) -> bool:
        """
        验证工作流定义是否有效
        
        Args:
            steps: 工作流步骤列表
            
        Returns:
            bool: 是否有效
        """
        if not steps:
            logger.error("工作流步骤列表为空")
            return False
        
        step_ids = set()
        
        for step in steps:
            # 检查步骤ID唯一性
            if step.id in step_ids:
                logger.error(f"重复的步骤ID: {step.id}")
                return False
            step_ids.add(step.id)
            
            # 检查步骤类型特定的参数
            if step.step_type == StepType.AGENT:
                if not step.agent_name:
                    logger.error(f"Agent步骤 {step.name} 缺少agent_name参数")
                    return False
                    
            elif step.step_type == StepType.TOOL:
                if not step.tool_name or not step.action:
                    logger.error(f"工具步骤 {step.name} 缺少tool_name或action参数")
                    return False
                    
            elif step.step_type == StepType.CODE:
                if not step.code:
                    logger.error(f"代码步骤 {step.name} 缺少code参数")
                    return False
                    
            elif step.step_type == StepType.MEMORY:
                if not step.memory_action:
                    logger.error(f"内存步骤 {step.name} 缺少memory_action参数")
                    return False
            
            # 检查依赖的步骤是否存在
            for dep_id in step.depends_on:
                if dep_id not in step_ids:
                    # 检查是否是之前定义的步骤
                    if dep_id not in [s.id for s in steps[:steps.index(step)]]:
                        logger.error(f"步骤 {step.name} 依赖的步骤 {dep_id} 不存在")
                        return False
        
        return True