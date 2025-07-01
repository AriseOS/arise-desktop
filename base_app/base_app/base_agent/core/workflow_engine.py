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
                    
                    # 使用新的端口存储逻辑
                    self._store_step_outputs(step, step_result.data, context)
                    
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
            # 1. 优先查找llm_response_generation步骤的final_response端口 (新工作流)
            if 'llm_response_generation.final_response' in context.variables:
                result.final_result = context.variables['llm_response_generation.final_response']
                logger.info(f"使用llm_response_generation.final_response端口作为最终结果: {result.final_result}")
            # 2. 查找final_response输出变量 (向后兼容)
            elif 'final_response' in context.variables:
                result.final_result = context.variables['final_response']
                logger.info(f"使用final_response变量作为最终结果: {result.final_result}")
            # 3. 查找generate_response步骤的response端口 (旧端口模式)
            elif 'generate_response.response' in context.variables:
                result.final_result = context.variables['generate_response.response']
                logger.info(f"使用generate_response.response端口作为最终结果: {result.final_result}")
            # 4. 备用方案：使用最后一个成功步骤的结果
            elif context.step_results:
                last_result_key = context.completed_steps[-1] if context.completed_steps else None
                if last_result_key:
                    last_result = context.step_results.get(last_result_key)
                    # 如果是字典且有response或final_response键，优先使用
                    if isinstance(last_result, dict):
                        if 'final_response' in last_result:
                            result.final_result = last_result['final_response']
                        elif 'response' in last_result:
                            result.final_result = last_result['response']
                        else:
                            result.final_result = last_result
                    else:
                        result.final_result = last_result
                    logger.info(f"使用最后步骤结果作为最终结果: {result.final_result}")
            
            # 调试信息
            logger.info(f"执行完成 - 变量: {list(context.variables.keys())}, 步骤结果: {list(context.step_results.keys())}")
            
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
            # 1. 解析端口连接，获取输入数据
            input_data = await self._resolve_port_connections(step, context)
            
            # 2. 解析步骤参数中的变量引用 (保持向后兼容)
            resolved_params = await self._resolve_variables(step.params, context)
            
            # 3. 更新步骤参数
            resolved_step = step.copy()
            resolved_step.params = resolved_params
            
            # 4. 将端口输入数据添加到执行环境
            if input_data:
                context.variables.update(input_data)
            
            # 5. 解析其他字段中的变量引用
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
            
            # 构建要存储的对话记录
            value = None
            
            # 检查是否是存储对话记录
            if step.memory_key == "conversation_history":
                # 从各个端口收集信息构建完整的对话记录
                user_input_data = context.variables.get("user_input", {})
                final_response = context.variables.get("final_response", "")
                analysis_result = context.variables.get("analysis_result", {})
                
                # 提取用户输入
                if isinstance(user_input_data, dict):
                    user_input_text = user_input_data.get("user_input", "")
                else:
                    user_input_text = str(user_input_data)
                
                # 构建对话记录
                conversation_record = {
                    "user_input": user_input_text,
                    "ai_response": final_response,
                    "action_type": analysis_result.get("action_type", "unknown"),
                    "reasoning": analysis_result.get("reasoning", ""),
                    "timestamp": datetime.now().isoformat()
                }
                
                value = f"用户问: {user_input_text}\nAI答: {final_response}\n处理方式: {analysis_result.get('action_type', 'unknown')}"
            else:
                # 普通存储逻辑
                if "content" in context.variables:
                    value = context.variables["content"]
                elif step.memory_value is not None:
                    value = step.memory_value
                else:
                    value = step.params.get("value")
                
            await self.agent.store_memory(step.memory_key, value)
            return {"stored": True, "content": value}
            
        elif action == "get":
            # 获取内存
            if not step.memory_key:
                raise ValueError("获取操作缺少memory_key参数")
            
            default = step.params.get("default")
            return await self.agent.get_memory(step.memory_key, default)
            
        elif action == "search":
            # 搜索记忆（长期记忆）
            # 优先从端口连接获取查询内容
            query = None
            if "query" in context.variables:
                query_data = context.variables["query"]
                # 处理查询数据，确保是字符串格式
                if isinstance(query_data, dict):
                    # 如果是字典，提取用户输入文本
                    query = query_data.get("user_input", str(query_data))
                elif isinstance(query_data, str):
                    query = query_data
                else:
                    query = str(query_data)
            elif step.query:
                query = step.query
            else:
                raise ValueError("搜索操作缺少query参数")
            
            # 确保查询字符串不为空
            if not query or not isinstance(query, str):
                logger.warning(f"无效的查询字符串: {query}")
                return {"memories": []}
            
            # 检查是否有memory manager实例
            if hasattr(self.agent, 'memory_manager') and self.agent.memory_manager:
                limit = step.params.get("limit", 5)
                user_id = step.params.get("user_id")
                
                try:
                    results = await self.agent.memory_manager.search_long_term_memory(
                        query, user_id, limit
                    )
                    logger.debug(f"记忆搜索完成: 查询='{query}', 结果数={len(results)}")
                    return {"memories": results}
                except Exception as e:
                    logger.error(f"记忆搜索失败: {e}")
                    return {"memories": []}
            else:
                logger.warning("长期记忆未启用，返回空结果")
                return {"memories": []}
                
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
            # 先替换变量引用，但保持字符串格式
            resolved_condition = condition
            
            # 匹配 {{variable_name}} 模式
            import re
            pattern = r'\{\{([^}]+)\}\}'
            
            def replace_var(match):
                var_name = match.group(1).strip()
                
                # 先在variables中查找
                if var_name in context.variables:
                    value = context.variables[var_name]
                    # 如果是字符串，需要加引号
                    if isinstance(value, str):
                        return f"'{value}'"
                    else:
                        return str(value)
                
                # 再在step_results中查找
                if var_name in context.step_results:
                    value = context.step_results[var_name]
                    if isinstance(value, str):
                        return f"'{value}'"
                    else:
                        return str(value)
                
                # 如果找不到，记录警告并返回False
                logger.warning(f"变量 {var_name} 未找到")
                return "None"
            
            resolved_condition = re.sub(pattern, replace_var, resolved_condition)
            
            # 准备评估环境
            eval_globals = {
                '__builtins__': {},
                'True': True,
                'False': False,
                'None': None,
            }
            
            eval_locals = {}
            
            # 评估条件表达式
            result = eval(resolved_condition, eval_globals, eval_locals)
            logger.debug(f"条件评估: {condition} -> {resolved_condition} = {result}")
            return bool(result)
            
        except Exception as e:
            logger.error(f"条件评估失败: {condition}, 错误: {e}")
            logger.debug(f"解析后条件: {resolved_condition if 'resolved_condition' in locals() else 'N/A'}")
            logger.debug(f"可用变量: {list(context.variables.keys())}")
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
    
    async def _resolve_port_connections(
        self, 
        step: WorkflowStep, 
        context: ExecutionContext
    ) -> Dict[str, Any]:
        """
        解析端口连接，获取输入数据
        
        Args:
            step: 当前步骤
            context: 执行上下文
            
        Returns:
            Dict[str, Any]: 端口输入数据
        """
        input_data = {}
        
        # 处理端口连接
        for target_port, connection in step.port_connections.items():
            try:
                # 从源步骤的输出端口获取数据
                source_step_outputs = context.step_results.get(connection.source_step)
                
                if source_step_outputs and isinstance(source_step_outputs, dict):
                    # 如果源步骤输出是字典，尝试获取指定端口的数据
                    if connection.source_port in source_step_outputs:
                        input_data[target_port] = source_step_outputs[connection.source_port]
                    else:
                        logger.warning(f"端口连接警告: 源步骤 {connection.source_step} 没有输出端口 {connection.source_port}")
                else:
                    # 如果源步骤输出不是字典，直接使用整个输出
                    input_data[target_port] = source_step_outputs
                    
            except Exception as e:
                logger.error(f"端口连接解析失败: {target_port} <- {connection.source_step}.{connection.source_port}, 错误: {e}")
        
        return input_data
    
    def _store_step_outputs(
        self, 
        step: WorkflowStep, 
        step_result: Any, 
        context: ExecutionContext
    ) -> None:
        """
        存储步骤输出到端口
        
        Args:
            step: 工作流步骤
            step_result: 步骤执行结果
            context: 执行上下文
        """
        # 如果步骤定义了输出端口，按端口存储
        if step.output_ports:
            output_data = {}
            if isinstance(step_result, dict):
                # 如果结果是字典，尝试映射到输出端口
                for port in step.output_ports:
                    if port.name in step_result:
                        output_data[port.name] = step_result[port.name]
                    elif port.default_value is not None:
                        output_data[port.name] = port.default_value
                    elif port.required:
                        logger.warning(f"必需的输出端口 {port.name} 在步骤 {step.name} 中未找到")
            else:
                # 如果只有一个输出端口，直接使用结果
                if len(step.output_ports) == 1:
                    output_data[step.output_ports[0].name] = step_result
                else:
                    logger.warning(f"步骤 {step.name} 有多个输出端口但结果不是字典")
            
            # 存储到step_results和variables
            context.step_results[step.id] = output_data
            for port_name, port_value in output_data.items():
                context.variables[f"{step.id}.{port_name}"] = port_value
        else:
            # 保持向后兼容：如果没有定义输出端口，使用原有逻辑
            context.step_results[step.id] = step_result
            if step.output_key:
                context.variables[step.output_key] = step_result
    
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