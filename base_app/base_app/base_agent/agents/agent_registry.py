"""
Agent Registry - Agent注册中心
"""
from typing import Dict, List, Optional

from .base_agent import BaseStepAgent, AgentMetadata


class AgentRegistry:
    """Agent注册中心"""
    
    def __init__(self):
        self._agents: Dict[str, BaseStepAgent] = {}
        self._agent_metadata: Dict[str, AgentMetadata] = {}
    
    def register_agent(self, agent: BaseStepAgent) -> bool:
        """注册Agent"""
        try:
            agent_name = agent.metadata.name
            
            # 存储Agent实例和元数据
            self._agents[agent_name] = agent
            self._agent_metadata[agent_name] = agent.metadata
            
            return True
            
        except Exception as e:
            print(f"注册Agent失败: {str(e)}")
            return False
    
    def unregister_agent(self, agent_name: str) -> bool:
        """注销Agent"""
        try:
            if agent_name not in self._agents:
                return False
            
            # 从能力索引中移除
            # 删除Agent和元数据
            del self._agents[agent_name]
            del self._agent_metadata[agent_name]
            
            return True
            
        except Exception as e:
            print(f"注销Agent失败: {str(e)}")
            return False
    
    def get_agent(self, agent_name: str) -> Optional[BaseStepAgent]:
        """获取Agent实例"""
        return self._agents.get(agent_name)
    
    def get_agent_metadata(self, agent_name: str) -> Optional[AgentMetadata]:
        """获取Agent元数据"""
        return self._agent_metadata.get(agent_name)
    
    def list_agents(self) -> List[AgentMetadata]:
        """列出所有Agent"""
        return list(self._agent_metadata.values())
    
    def list_agent_names(self) -> List[str]:
        """列出所有Agent名称"""
        return list(self._agents.keys())
    
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
            "total_agents": len(self._agents),
        }