"""
Agent服务层 - BaseAgent的应用层封装
负责会话管理、API格式化、并发处理等应用层逻辑
"""
import asyncio
import time
import uuid
from typing import Dict, Optional, List, Any
from datetime import datetime

from base_app.base_agent.core import BaseAgent, AgentConfig, AgentStatus
from .config_service import ConfigService



class Session:
    """会话管理"""
    
    def __init__(self, session_id: str, user_id: str, title: str = ""):
        self.session_id = session_id
        self.user_id = user_id
        self.title = title or f"对话_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.messages: List[Dict[str, Any]] = []
    
    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None):
        """添加消息到会话"""
        message = {
            "id": str(uuid.uuid4()),
            "role": role,  # "user" or "assistant"
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        self.messages.append(message)
        self.updated_at = datetime.now()
        return message
    
    def get_recent_messages(self, limit: int = 10) -> List[Dict]:
        """获取最近的消息"""
        return self.messages[-limit:] if limit > 0 else self.messages


class AgentService:
    """
    Agent服务类 - BaseAgent的应用层封装
    
    职责：
    1. 会话管理和对话历史
    2. API响应格式化
    3. 并发请求处理
    4. BaseAgent生命周期管理
    """
    
    def __init__(self, config_service: ConfigService):
        self.config_service = config_service
        self.agent: Optional[BaseAgent] = None
        self.sessions: Dict[str, Session] = {}
        self.start_time = time.time()
        self._lock = asyncio.Lock()
        
        # 初始化Agent
        self._initialize_agent()
    
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
            
            # 注册工具
            self._register_tools(agent_config.tools)
            
        except Exception as e:
            raise RuntimeError(f"Failed to initialize BaseAgent: {e}")
    
    def _register_tools(self, enabled_tools: List[str]):
        """根据配置注册工具"""
        print(f"🔧 开始注册工具，enabled_tools: {enabled_tools}")
        
        if not self.agent:
            print("❌ Agent实例为空，无法注册工具")
            return
            
        if not enabled_tools:
            print("⚠️ 没有启用的工具配置")
            return
        
        for tool_name in enabled_tools:
            try:
                if tool_name == "browser" or tool_name == "browser_use":
                    from base_app.base_agent.tools.browser_use import BrowserTool
                    browser_tool = BrowserTool()
                    self.agent.register_tool('browser_use', browser_tool)
                    print(f"✓ 成功注册工具: browser_use (配置名: {tool_name})")
                    
                    # 验证注册结果
                    registered_tools = self.agent.get_registered_tools()
                    print(f"📋 当前已注册工具: {registered_tools}")
                else:
                    print(f"⚠️ 未知工具: {tool_name}")
            except Exception as e:
                print(f"❌ 注册工具失败 {tool_name}: {e}")
                import traceback
                traceback.print_exc()
    
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
            session_id: 会话ID
            user_id: 用户ID
            **kwargs: 额外参数
            
        Returns:
            包含响应内容和元数据的字典
        """
        async with self._lock:
            try:
                # 获取或创建会话
                session = self.get_or_create_session(session_id, user_id)
                
                # 添加用户消息到会话历史
                user_msg = session.add_message("user", message)
                
                # 调用BaseAgent处理消息
                start_time = time.time()
                response = await self.agent.process_user_input(message, user_id)
                processing_time = time.time() - start_time
                
                # 添加Agent响应到会话历史
                assistant_msg = session.add_message(
                    "assistant", 
                    response,
                    {"processing_time": processing_time}
                )
                
                return {
                    "success": True,
                    "session_id": session_id,
                    "user_message": user_msg,
                    "assistant_message": assistant_msg,
                    "processing_time": processing_time
                }
                
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "session_id": session_id
                }
    
    def get_or_create_session(self, session_id: str, user_id: str, title: str = "") -> Session:
        """获取或创建会话"""
        if session_id not in self.sessions:
            if not session_id:
                session_id = str(uuid.uuid4())
            self.sessions[session_id] = Session(session_id, user_id, title)
        return self.sessions[session_id]
    
    def get_session_history(self, session_id: str, limit: int = 50) -> Optional[List[Dict]]:
        """获取会话历史"""
        session = self.sessions.get(session_id)
        if session:
            return session.get_recent_messages(limit)
        return None
    
    def list_sessions(self, user_id: str) -> List[Dict]:
        """列出用户的所有会话"""
        user_sessions = []
        for session in self.sessions.values():
            if session.user_id == user_id:
                user_sessions.append({
                    "session_id": session.session_id,
                    "title": session.title,
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                    "message_count": len(session.messages)
                })
        
        # 按更新时间倒序排列
        return sorted(user_sessions, key=lambda x: x["updated_at"], reverse=True)
    
    def delete_session(self, session_id: str, user_id: str) -> bool:
        """删除会话"""
        session = self.sessions.get(session_id)
        if session and session.user_id == user_id:
            del self.sessions[session_id]
            return True
        return False
    
    def get_agent_status(self) -> Dict[str, Any]:
        """获取Agent状态信息"""
        if not self.agent:
            return {"status": "not_initialized"}
        
        return {
            "status": "ready" if self.agent else "not_ready",
            "uptime": time.time() - self.start_time,
            "agent_name": self.agent.config.name if self.agent else None,
            "memory_enabled": self.agent.memory_manager is not None if self.agent else False,
            "tools": self.agent.get_registered_tools() if self.agent else [],
            "active_sessions": len(self.sessions),
            "total_conversations": sum(len(s.messages) // 2 for s in self.sessions.values())
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
            # 保存当前会话
            old_sessions = self.sessions.copy()
            
            # 重新初始化Agent
            self._initialize_agent()
            
            # 恢复会话
            self.sessions = old_sessions
            
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
        
        # 可以在这里保存会话到持久化存储
        self.sessions.clear()