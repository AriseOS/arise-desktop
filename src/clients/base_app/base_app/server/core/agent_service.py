"""
Agent服务层 - BaseAgent的应用层封装
负责会话管理、API格式化、并发处理等应用层逻辑
"""
import asyncio
import time
import uuid
from typing import Dict, Optional, List, Any
from datetime import datetime
import logging

from ...base_agent.core import BaseAgent, AgentConfig, AgentStatus
from src.common.config_service import ConfigService
from ..storage import SessionStorage, SQLiteSessionStorage, SessionModel, MessageModel

logger = logging.getLogger(__name__)



# 移除内存Session类，使用持久化存储


class AgentService:
    """
    Agent服务类 - BaseAgent的应用层封装
    
    职责：
    1. 会话管理和对话历史
    2. API响应格式化
    3. 并发请求处理
    4. BaseAgent生命周期管理
    """
    
    def __init__(self, config_service: ConfigService, storage: Optional[SessionStorage] = None):
        self.config_service = config_service
        self.agent: Optional[BaseAgent] = None
        self.start_time = time.time()
        self._lock = asyncio.Lock()
        
        # 初始化存储
        if storage is None:
            # 使用配置服务初始化存储，让存储自己从配置读取路径
            self.storage = SQLiteSessionStorage(config_service=config_service)
        else:
            self.storage = storage
        
        # 初始化存储和Agent
        self._initialized = False
        
    async def initialize(self):
        """异步初始化存储和Agent"""
        if not self._initialized:
            await self.storage.initialize()
            self._initialize_agent()
            self._initialized = True
            logger.info("AgentService initialized successfully")
    
    def _initialize_agent(self):
        """初始化BaseAgent实例"""
        try:
            agent_config = self._build_agent_config()
            memory_enabled = self.config_service.get("agent.memory.enabled", False)
            memory_config = self.config_service.get("agent.memory.config", {})
            
            self.agent = BaseAgent(
                config=agent_config,
                enable_memory=memory_enabled,
                memory_config=memory_config
            )
            
            # 工具现在由BaseAgent自动注册，不需要手动注册
            
        except Exception as e:
            raise RuntimeError(f"Failed to initialize BaseAgent: {e}")
    
    def _build_agent_config(self) -> AgentConfig:
        """构建Agent配置"""
        config_data = self.config_service.get("agent", {})
        
        # 正确读取嵌套配置
        llm_config = config_data.get("llm", {})
        tools_config = config_data.get("tools", {})
        enabled_tools = tools_config.get("enabled", [])
        
        return AgentConfig(
            name=config_data.get("name", "BaseApp Agent"),
            llm_provider=llm_config.get("provider", "openai"),
            llm_model=llm_config.get("model", "gpt-4o"),
            api_key=llm_config.get("api_key", ""),
            enable_logging=True,
            tools=enabled_tools
        )
    
    async def send_message(
        self, 
        message: str, 
        session_id: str, 
        user_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送消息到Agent并返回响应
        
        Args:
            message: 用户消息
            session_id: 会话ID（必填）
            user_id: 用户ID
            **kwargs: 额外参数
            
        Returns:
            包含响应内容和元数据的字典
        """
        if not self._initialized:
            await self.initialize()
            
        async with self._lock:
            try:
                # 验证会话是否存在
                session = await self.storage.get_session(session_id)
                if not session:
                    raise ValueError(f"Session {session_id} not found")
                
                # 验证用户权限
                if session.user_id != user_id:
                    raise PermissionError(f"User {user_id} has no access to session {session_id}")
                
                # 创建用户消息
                user_message = MessageModel(
                    session_id=session_id,
                    role="user",
                    content=message
                )
                
                # 保存用户消息
                user_msg = await self.storage.add_message(user_message)
                
                # 调用BaseAgent处理消息
                start_time = time.time()
                response = await self.agent.process_user_input(message, user_id)
                processing_time = time.time() - start_time
                
                # 创建Agent响应消息
                assistant_message = MessageModel(
                    session_id=session_id,
                    role="assistant",
                    content=response,
                    metadata={"processing_time": processing_time}
                )
                
                # 保存Agent响应
                assistant_msg = await self.storage.add_message(assistant_message)
                
                return {
                    "success": True,
                    "session_id": session_id,
                    "user_message": user_msg.to_api_format(),
                    "assistant_message": assistant_msg.to_api_format(),
                    "processing_time": processing_time
                }
                
            except (ValueError, PermissionError) as e:
                logger.warning(f"Session validation error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "session_id": session_id
                }
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "session_id": session_id
                }
    
    async def create_session(self, user_id: str, title: str = "") -> SessionModel:
        """创建新会话"""
        if not self._initialized:
            await self.initialize()
            
        session = SessionModel(
            user_id=user_id,
            title=title or f"对话_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        
        return await self.storage.create_session(session)
    
    async def get_session_history(self, session_id: str, limit: int = 50) -> Optional[List[Dict]]:
        """获取会话历史"""
        if not self._initialized:
            await self.initialize()
            
        messages = await self.storage.get_session_messages(session_id, limit)
        if messages:
            return [msg.to_api_format() for msg in messages]
        return None
    
    async def list_sessions(self, user_id: str) -> List[Dict]:
        """列出用户的所有会话"""
        if not self._initialized:
            await self.initialize()
            
        sessions = await self.storage.list_user_sessions(user_id)
        user_sessions = []
        
        for session in sessions:
            message_count = await self.storage.get_message_count(session.session_id)
            user_sessions.append({
                "session_id": session.session_id,
                "title": session.title,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "message_count": message_count
            })
        
        return user_sessions
    
    async def delete_session(self, session_id: str, user_id: str) -> bool:
        """删除会话"""
        if not self._initialized:
            await self.initialize()
            
        # 验证会话存在和权限
        session = await self.storage.get_session(session_id)
        if session and session.user_id == user_id:
            return await self.storage.delete_session(session_id)
        return False
    
    def get_agent_status(self) -> Dict[str, Any]:
        """获取Agent状态信息"""
        if not self.agent:
            return {"status": "not_initialized"}
        
        return {
            "status": "ready" if self.agent and self._initialized else "not_ready",
            "uptime": time.time() - self.start_time,
            "agent_name": self.agent.config.name if self.agent else None,
            "memory_enabled": self.agent.memory_manager is not None if self.agent else False,
            "tools": self.agent.get_registered_tools() if self.agent else [],
            "active_sessions": 0,  # 不再使用内存会话统计
            "total_conversations": 0  # 需要通过数据库查询
        }
    
    def get_agent_config(self) -> Dict[str, Any]:
        """获取Agent配置"""
        if not self.agent:
            return {}
        
        return {
            "name": self.agent.config.name,
            "llm_provider": self.agent.config.llm_provider,
            "llm_model": self.agent.config.llm_model,
            "tools": self.agent.config.tools,
            "memory_enabled": self.agent.memory_manager is not None
        }
    
    async def restart_agent(self) -> Dict[str, Any]:
        """重启Agent"""
        try:
            # 重新初始化Agent（会话数据已在数据库中）
            self._initialize_agent()
            
            return {
                "success": True,
                "message": "Agent restarted successfully",
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def shutdown(self):
        """优雅关闭服务"""
        # 清理资源
        if self.agent and hasattr(self.agent, 'shutdown'):
            await self.agent.shutdown()
        
        # 关闭存储连接
        if hasattr(self, 'storage') and self.storage:
            await self.storage.close()
            
        logger.info("AgentService shutdown completed")