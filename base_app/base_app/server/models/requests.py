"""
API请求模型
"""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class ChatMessageRequest(BaseModel):
    """聊天消息请求"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "你好，请帮我分析一下今天的天气",
                "session_id": "session_123",
                "user_id": "user_456"
            }
        }
    )
    
    message: str = Field(..., description="用户消息", min_length=1)
    session_id: Optional[str] = Field(None, description="会话ID")
    user_id: str = Field(..., description="用户ID")


class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "user_456",
                "title": "天气查询对话"
            }
        }
    )
    
    user_id: str = Field(..., description="用户ID")
    title: Optional[str] = Field(None, description="会话标题")


class UpdateAgentConfigRequest(BaseModel):
    """更新Agent配置请求"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "config": {
                    "name": "My Custom Agent",
                    "llm_model": "gpt-4",
                    "tools": ["browser", "memory"]
                }
            }
        }
    )
    
    config: Dict[str, Any] = Field(..., description="Agent配置")