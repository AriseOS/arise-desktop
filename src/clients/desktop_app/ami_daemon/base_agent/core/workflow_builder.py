"""
WorkflowBuilder - 用户友好的工作流构建接口
"""
from typing import List, Dict, Any, Optional, TYPE_CHECKING
import logging

from .schemas import AgentWorkflowStep, Workflow

if TYPE_CHECKING:
    from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class WorkflowBuilder:
    """工作流构建器 - 提供用户友好的工作流构建接口"""
    
    def __init__(self, name: str, description: str, agent_instance: 'BaseAgent'):
        self.name = name
        self.description = description
        self.agent = agent_instance
        self.steps: List[AgentWorkflowStep] = []
        self.input_schema: Dict[str, Any] = {}
        self.output_schema: Dict[str, Any] = {}
        
        logger.info(f"创建工作流构建器: {name}")
    
    def add_text_step(self, 
                     name: str, 
                     instruction: str,
                     description: str = "",
                     agent_name: str = "text_agent",
                     user_task: Optional[str] = None,
                     inputs: Dict[str, Any] = None,
                     outputs: Dict[str, str] = None,
                     constraints: List[str] = None,
                     response_style: str = "professional",
                     max_length: int = 500,
                     condition: Optional[str] = None,
                     timeout: int = 300,
                     retry_count: int = 0) -> 'WorkflowBuilder':
        """
        添加文本处理步骤
        
        Args:
            name: 步骤名称
            instruction: Agent执行指令
            description: 步骤描述
            agent_name: 使用的Agent名称
            user_task: 用户具体任务内容
            inputs: 输入映射配置
            outputs: 输出映射配置
            constraints: 约束条件
            response_style: 响应风格
            max_length: 最大响应长度
            condition: 执行条件
            timeout: 超时时间
            retry_count: 重试次数
            
        Returns:
            WorkflowBuilder: 返回自身支持链式调用
        """
        step = AgentWorkflowStep(
            name=name,
            description=description or f"文本处理步骤: {name}",
            agent_type=agent_name,
            user_task=user_task,
            inputs=inputs or {},
            outputs=outputs or {},
            constraints=constraints or [],
            response_style=response_style,
            max_length=max_length,
            condition=condition,
            timeout=timeout,
            retry_count=retry_count
        )
        self.steps.append(step)
        logger.debug(f"添加文本步骤: {name}")
        return self

    def add_custom_step(self,
                       name: str,
                       agent_name: str,
                       instruction: str,
                       description: str = "",
                       user_task: Optional[str] = None,
                       inputs: Dict[str, Any] = None,
                       outputs: Dict[str, str] = None,
                       constraints: List[str] = None,
                       condition: Optional[str] = None,
                       timeout: int = 300,
                       retry_count: int = 0) -> 'WorkflowBuilder':
        """
        添加自定义Agent步骤
        
        Args:
            name: 步骤名称
            agent_name: 自定义Agent名称
            instruction: Agent执行指令
            description: 步骤描述
            user_task: 用户具体任务内容
            inputs: 输入配置
            outputs: 输出配置
            constraints: 约束条件
            condition: 执行条件
            timeout: 超时时间
            retry_count: 重试次数
            
        Returns:
            WorkflowBuilder: 返回自身支持链式调用
        """
        step = AgentWorkflowStep(
            name=name,
            description=description or f"自定义Agent步骤: {name}",
            agent_type=agent_name,
            user_task=user_task,
            inputs=inputs or {},
            outputs=outputs or {},
            constraints=constraints or [],
            condition=condition,
            timeout=timeout,
            retry_count=retry_count
        )
        self.steps.append(step)
        logger.debug(f"添加自定义步骤: {name}, Agent: {agent_name}")
        return self
    
    def set_input_schema(self, schema: Dict[str, Any]) -> 'WorkflowBuilder':
        """
        设置输入模式
        
        Args:
            schema: 输入模式定义
            
        Returns:
            WorkflowBuilder: 返回自身支持链式调用
        """
        self.input_schema = schema
        logger.debug(f"设置输入模式: {schema}")
        return self
    
    def set_output_schema(self, schema: Dict[str, Any]) -> 'WorkflowBuilder':
        """
        设置输出模式
        
        Args:
            schema: 输出模式定义
            
        Returns:
            WorkflowBuilder: 返回自身支持链式调用
        """
        self.output_schema = schema
        logger.debug(f"设置输出模式: {schema}")
        return self
    
    def add_parallel_steps(self, steps: List[AgentWorkflowStep]) -> 'WorkflowBuilder':
        """
        添加并行执行的步骤组
        
        Args:
            steps: 可以并行执行的步骤列表
            
        Returns:
            WorkflowBuilder: 返回自身支持链式调用
        """
        # 为并行步骤设置相同的并行组标识
        parallel_group_id = f"parallel_group_{len(self.steps)}"
        
        for step in steps:
            step.parallel_with = [s.name for s in steps if s.name != step.name]
            self.steps.append(step)
        
        logger.debug(f"添加并行步骤组: {[s.name for s in steps]}")
        return self
    
    def validate(self) -> List[str]:
        """
        验证工作流配置
        
        Returns:
            List[str]: 验证错误列表
        """
        errors = []
        
        if not self.steps:
            errors.append("工作流必须包含至少一个步骤")
        
        # 检查步骤名称重复
        step_names = [step.name for step in self.steps]
        if len(step_names) != len(set(step_names)):
            errors.append("步骤名称不能重复")
        
        # 检查Agent是否存在
        if self.agent and self.agent.agent_workflow_engine:
            available_agents = list(self.agent.agent_workflow_engine.AGENT_TYPES.keys())
            for step in self.steps:
                if step.agent_type not in available_agents:
                    errors.append(f"步骤 '{step.name}' 使用的Agent '{step.agent_type}' 不存在")
        
        # 检查条件表达式（简单验证）
        for step in self.steps:
            if step.condition:
                if not self._validate_condition(step.condition):
                    errors.append(f"步骤 '{step.name}' 的条件表达式无效: {step.condition}")
        
        return errors
    
    def _validate_condition(self, condition: str) -> bool:
        """
        验证条件表达式
        
        Args:
            condition: 条件表达式
            
        Returns:
            bool: 是否有效
        """
        # 简单的条件验证，检查是否包含基本的变量引用格式
        if "{{" in condition and "}}" in condition:
            return True
        
        # 检查是否是简单的布尔表达式
        if condition.lower() in ["true", "false"]:
            return True
        
        # 更复杂的验证可以在这里添加
        return False
    
    def add_if_step(self,
                    name: str,
                    condition: str,
                    then_steps: List[AgentWorkflowStep] = None,
                    else_steps: List[AgentWorkflowStep] = None,
                    description: str = "",
                    inputs: Dict[str, Any] = None,
                    outputs: Dict[str, str] = None,
                    timeout: int = 300) -> 'WorkflowBuilder':
        """
        添加if/else条件控制步骤
        
        Args:
            name: 步骤名称
            condition: 条件表达式
            then_steps: 条件为真时执行的步骤列表
            else_steps: 条件为假时执行的步骤列表（可选）
            description: 步骤描述
            inputs: 输入映射
            outputs: 输出映射
            timeout: 超时时间
            
        Returns:
            WorkflowBuilder: 返回自身支持链式调用
        """
        step = AgentWorkflowStep(
            name=name,
            description=description,
            agent_type="if",
            inputs=inputs or {},
            outputs=outputs or {},
            condition=condition,
            timeout=timeout,
            then=then_steps or [],
            else_=else_steps or []
        )
        
        self.steps.append(step)
        logger.info(f"添加if步骤: {name}")
        return self
    
    def add_while_step(self,
                       name: str,
                       condition: str,
                       loop_steps: List[AgentWorkflowStep] = None,
                       description: str = "",
                       inputs: Dict[str, Any] = None,
                       outputs: Dict[str, str] = None,
                       max_iterations: int = 10,
                       timeout: int = 300) -> 'WorkflowBuilder':
        """
        添加while循环控制步骤
        
        Args:
            name: 步骤名称
            condition: 循环条件表达式
            loop_steps: 循环体步骤列表
            description: 步骤描述
            inputs: 输入映射
            outputs: 输出映射
            max_iterations: 最大循环次数
            timeout: 超时时间
            
        Returns:
            WorkflowBuilder: 返回自身支持链式调用
        """
        step = AgentWorkflowStep(
            name=name,
            description=description,
            agent_type="while",
            inputs=inputs or {},
            outputs=outputs or {},
            condition=condition,
            timeout=timeout,
            steps=loop_steps or [],
            max_iterations=max_iterations,
            loop_timeout=timeout
        )
        
        self.steps.append(step)
        logger.info(f"添加while步骤: {name}")
        return self
    
    def build(self) -> Workflow:
        """
        构建工作流
        
        Returns:
            Workflow: 工作流实例
            
        Raises:
            ValueError: 如果工作流配置无效
        """
        # 验证工作流
        errors = self.validate()
        if errors:
            error_msg = f"工作流构建失败: {'; '.join(errors)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        workflow = Workflow(
            name=self.name,
            description=self.description,
            steps=self.steps,
            input_schema=self.input_schema,
            output_schema=self.output_schema
        )
        
        logger.info(f"工作流构建成功: {self.name}, 包含 {len(self.steps)} 个步骤")
        return workflow
    
    def get_step_count(self) -> int:
        """获取步骤数量"""
        return len(self.steps)
    
    def get_step_names(self) -> List[str]:
        """获取所有步骤名称"""
        return [step.name for step in self.steps]
    
    def remove_step(self, name: str) -> 'WorkflowBuilder':
        """
        移除指定步骤
        
        Args:
            name: 步骤名称
            
        Returns:
            WorkflowBuilder: 返回自身支持链式调用
        """
        self.steps = [step for step in self.steps if step.name != name]
        logger.debug(f"移除步骤: {name}")
        return self
    
    def insert_step(self, index: int, step: AgentWorkflowStep) -> 'WorkflowBuilder':
        """
        在指定位置插入步骤
        
        Args:
            index: 插入位置
            step: 步骤实例
            
        Returns:
            WorkflowBuilder: 返回自身支持链式调用
        """
        self.steps.insert(index, step)
        logger.debug(f"在位置 {index} 插入步骤: {step.name}")
        return self
    
    def clear_steps(self) -> 'WorkflowBuilder':
        """
        清空所有步骤
        
        Returns:
            WorkflowBuilder: 返回自身支持链式调用
        """
        self.steps.clear()
        logger.debug("清空所有步骤")
        return self
    
    def copy(self) -> 'WorkflowBuilder':
        """
        创建构建器副本
        
        Returns:
            WorkflowBuilder: 新的构建器实例
        """
        new_builder = WorkflowBuilder(
            name=f"{self.name}_copy",
            description=self.description,
            agent_instance=self.agent
        )
        new_builder.steps = self.steps.copy()
        new_builder.input_schema = self.input_schema.copy()
        new_builder.output_schema = self.output_schema.copy()
        return new_builder
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式
        
        Returns:
            Dict[str, Any]: 字典表示
        """
        return {
            "name": self.name,
            "description": self.description,
            "steps": [step.dict() for step in self.steps],
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "step_count": len(self.steps)
        }
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"WorkflowBuilder(name='{self.name}', steps={len(self.steps)})"
    
    def __repr__(self) -> str:
        """详细字符串表示"""
        return f"WorkflowBuilder(name='{self.name}', description='{self.description}', steps={len(self.steps)})"