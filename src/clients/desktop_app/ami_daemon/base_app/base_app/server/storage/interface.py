"""
会话存储抽象接口
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from .models import SessionModel, MessageModel


class SessionStorage(ABC):
    """会话存储抽象接口"""

    @abstractmethod
    async def create_session(self, session: SessionModel) -> SessionModel:
        """创建新会话"""
        pass

    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[SessionModel]:
        """根据ID获取会话"""
        pass

    @abstractmethod
    async def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """更新会话信息"""
        pass

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        pass

    @abstractmethod
    async def list_user_sessions(self, user_id: str, limit: int = 50, offset: int = 0) -> List[SessionModel]:
        """获取用户的会话列表"""
        pass

    @abstractmethod
    async def add_message(self, message: MessageModel) -> MessageModel:
        """添加消息到会话"""
        pass

    @abstractmethod
    async def get_session_messages(self, session_id: str, limit: int = 50, offset: int = 0) -> List[MessageModel]:
        """获取会话的消息列表"""
        pass

    @abstractmethod
    async def delete_session_messages(self, session_id: str) -> bool:
        """删除会话的所有消息"""
        pass

    @abstractmethod
    async def get_message_count(self, session_id: str) -> int:
        """获取会话的消息数量"""
        pass

    @abstractmethod
    async def close(self):
        """关闭存储连接"""
        pass

    @abstractmethod
    async def initialize(self):
        """初始化存储（创建表等）"""
        pass