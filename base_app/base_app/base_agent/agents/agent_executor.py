"""
Agent Executor - Agent执行器
"""
from typing import Any, Dict, Optional

from .agent_registry import AgentRegistry
from .base_agent import BaseStepAgent
from ..core.schemas import AgentContext


class AgentExecutor:
    """Agent执行器"""
    
    def __init__(self, registry: AgentRegistry):
        self.registry = registry
    
    async def execute_agent(
        self,
        agent_name: str,
        input_data: Any,
        context: AgentContext,
        agent_config: Optional[Dict] = None
    ) -> Any:
        """执行指定Agent

        Args:
            agent_name: Agent名称
            input_data: 输入数据
            context: 执行上下文
            agent_config: Agent配置，用于创建实例
        """
        # 为每次执行创建新的Agent实例
        agent = self.registry.create_agent(agent_name, agent_config)
        if not agent:
            raise ValueError(f"Agent {agent_name} 未找到")

        # 初始化Agent
        if not agent.is_initialized:
            success = await agent.initialize(context)
            if not success:
                raise RuntimeError(f"Agent {agent_name} 初始化失败")

        # 验证输入
        if not await agent.validate_input(input_data):
            raise ValueError(f"Agent {agent_name} 输入数据验证失败")

        # 执行Agent
        try:
            result = await agent.execute(input_data, context)
            return result
        except Exception as e:
            # 只在异常时清理，不在正常执行后清理
            # 因为workflow中多个step可能共享资源（如浏览器会话）
            await agent.cleanup(context)
            raise e
    
    async def execute_agent_with_retry(
        self,
        agent_name: str,
        input_data: Any,
        context: AgentContext,
        agent_config: Optional[Dict] = None,
        max_retries: int = 3
    ) -> Any:
        """带重试机制的Agent执行"""
        last_error = None

        for attempt in range(max_retries):
            try:
                return await self.execute_agent(agent_name, input_data, context, agent_config)
            except Exception as e:
                last_error = e
                if context.logger:
                    context.logger.warning(f"Agent {agent_name} 第{attempt + 1}次执行失败: {str(e)}")

                if attempt < max_retries - 1:
                    # 不是最后一次尝试，继续重试
                    continue
                else:
                    # 最后一次尝试也失败了
                    break

        # 所有重试都失败了
        raise RuntimeError(f"Agent {agent_name} 执行失败，已重试{max_retries}次。最后错误: {str(last_error)}")
    
    def get_agent_info(self, agent_name: str) -> Dict[str, Any]:
        """获取Agent信息"""
        metadata = self.registry.get_agent_metadata(agent_name)
        if not metadata:
            return {}
        
        return {
            "name": metadata.name,
            "description": metadata.description,
            "version": metadata.version,
            "capabilities": [cap.value for cap in metadata.capabilities],
            "input_schema": metadata.input_schema,
            "output_schema": metadata.output_schema,
            "author": metadata.author,
            "tags": metadata.tags
        }
    
    def list_available_agents(self) -> Dict[str, Dict[str, Any]]:
        """列出所有可用Agent"""
        agents_info = {}
        for agent_name in self.registry.list_agent_names():
            agents_info[agent_name] = self.get_agent_info(agent_name)
        return agents_info