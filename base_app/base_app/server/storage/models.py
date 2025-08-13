"""
会话和消息的数据模型
"""
from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import uuid


class SessionModel(BaseModel):
    """持久化会话模型"""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="会话唯一标识")
    user_id: str = Field(..., description="用户ID")
    title: str = Field(..., description="会话标题")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="最后更新时间")
    status: str = Field(default="active", description="会话状态：active/archived/deleted")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="会话元数据")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionModel':
        """从字典创建实例"""
        # 处理datetime字段
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('updated_at'), str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        
        return cls(**data)


class MessageModel(BaseModel):
    """持久化消息模型"""
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="消息唯一标识")
    session_id: str = Field(..., description="所属会话ID")
    role: str = Field(..., description="角色：user/assistant")
    content: str = Field(..., description="消息内容")
    timestamp: datetime = Field(default_factory=datetime.now, description="消息时间")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="消息元数据")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "message_id": self.message_id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MessageModel':
        """从字典创建实例"""
        # 处理datetime字段
        if isinstance(data.get('timestamp'), str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        
        return cls(**data)

    def to_api_format(self) -> Dict[str, Any]:
        """转换为API响应格式"""
        return {
            "id": self.message_id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }