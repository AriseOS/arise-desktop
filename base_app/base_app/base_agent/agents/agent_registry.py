"""
Agent Registry - Agent注册中心
"""
from typing import Dict, List, Optional, Callable, Any

from .base_agent import BaseStepAgent, AgentMetadata


class AgentRegistry:
    """Agent注册中心 - 使用工厂模式为每个步骤创建独立的Agent实例"""

    def __init__(self):
        # 存储工厂函数，而不是实例
        self._agent_factories: Dict[str, Callable[[Optional[Dict]], BaseStepAgent]] = {}
        self._agent_metadata: Dict[str, AgentMetadata] = {}

    def register_agent_factory(self, agent_name: str, factory: Callable[[Optional[Dict]], BaseStepAgent]) -> bool:
        """注册Agent工厂函数

        Args:
            agent_name: Agent名称
            factory: 工厂函数，接受配置字典，返回Agent实例
        """
        try:
            # 存储工厂函数
            self._agent_factories[agent_name] = factory

            # 创建临时实例以获取元数据
            temp_instance = factory({})
            self._agent_metadata[agent_name] = temp_instance.metadata

            return True

        except Exception as e:
            print(f"注册Agent工厂失败: {str(e)}")
            return False

    def unregister_agent(self, agent_name: str) -> bool:
        """注销Agent"""
        try:
            if agent_name not in self._agent_factories:
                return False

            # 删除工厂和元数据
            del self._agent_factories[agent_name]
            del self._agent_metadata[agent_name]

            return True

        except Exception as e:
            print(f"注销Agent失败: {str(e)}")
            return False

    def create_agent(self, agent_name: str, config: Optional[Dict] = None) -> Optional[BaseStepAgent]:
        """创建新的Agent实例

        Args:
            agent_name: Agent名称
            config: Agent配置，将传递给工厂函数

        Returns:
            新创建的Agent实例，如果失败返回None
        """
        factory = self._agent_factories.get(agent_name)
        if not factory:
            return None

        try:
            return factory(config or {})
        except Exception as e:
            print(f"创建Agent实例失败: {str(e)}")
            return None

    def get_agent_metadata(self, agent_name: str) -> Optional[AgentMetadata]:
        """获取Agent元数据"""
        return self._agent_metadata.get(agent_name)

    def list_agents(self) -> List[AgentMetadata]:
        """列出所有Agent"""
        return list(self._agent_metadata.values())

    def list_agent_names(self) -> List[str]:
        """列出所有Agent名称"""
        return list(self._agent_factories.keys())

    def search_agents(self, query: str) -> List[AgentMetadata]:
        """搜索Agent（根据名称、描述、标签）"""
        results = []
        query_lower = query.lower()

        for metadata in self._agent_metadata.values():
            # 搜索名称
            if query_lower in metadata.name.lower():
                results.append(metadata)
                continue

            # 搜索描述
            if query_lower in metadata.description.lower():
                results.append(metadata)
                continue

            # 搜索标签
            for tag in metadata.tags:
                if query_lower in tag.lower():
                    results.append(metadata)
                    break

        return results

    def get_agent_stats(self) -> Dict[str, int]:
        """获取Agent统计信息"""
        return {
            "total_agents": len(self._agent_factories),
        }