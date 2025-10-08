"""
API响应模型
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    """消息响应"""
    id: str = Field(..., description="消息ID")
    role: str = Field(..., description="角色：user 或 assistant")
    content: str = Field(..., description="消息内容")
    timestamp: str = Field(..., description="时间戳")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")


class ChatResponse(BaseModel):
    """聊天响应"""
    success: bool = Field(..., description="是否成功")
    session_id: str = Field(..., description="会话ID")
    user_message: MessageResponse = Field(..., description="用户消息")
    assistant_message: MessageResponse = Field(..., description="助手消息")
    processing_time: float = Field(..., description="处理时间（秒）")
    error: Optional[str] = Field(None, description="错误信息")


class SessionInfo(BaseModel):
    """会话信息"""
    session_id: str = Field(..., description="会话ID")
    title: str = Field(..., description="会话标题")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")
    message_count: int = Field(..., description="消息数量")


class SessionListResponse(BaseModel):
    """会话列表响应"""
    sessions: List[SessionInfo] = Field(..., description="会话列表")
    total: int = Field(..., description="总数")


class SessionHistoryResponse(BaseModel):
    """会话历史响应"""
    session_id: str = Field(..., description="会话ID")
    messages: List[MessageResponse] = Field(..., description="消息列表")
    total: int = Field(..., description="消息总数")


class AgentStatusResponse(BaseModel):
    """Agent状态响应"""
    status: str = Field(..., description="Agent状态")
    uptime: float = Field(..., description="运行时间（秒）")
    agent_name: Optional[str] = Field(None, description="Agent名称")
    memory_enabled: bool = Field(..., description="是否启用内存")
    tools: List[str] = Field(..., description="工具列表")
    active_sessions: int = Field(..., description="活跃会话数")
    total_conversations: int = Field(..., description="总对话数")


class AgentConfigResponse(BaseModel):
    """Agent配置响应"""
    name: str = Field(..., description="Agent名称")
    llm_provider: str = Field(..., description="LLM提供商")
    llm_model: str = Field(..., description="LLM模型")
    tools: List[str] = Field(..., description="工具列表")
    memory_enabled: bool = Field(..., description="是否启用内存")


class SystemHealthResponse(BaseModel):
    """系统健康状态响应"""
    status: str = Field(..., description="系统状态")
    timestamp: str = Field(..., description="检查时间")
    services: Dict[str, str] = Field(..., description="服务状态")
    uptime: float = Field(..., description="运行时间")


class SystemInfoResponse(BaseModel):
    """系统信息响应"""
    app_name: str = Field(..., description="应用名称")
    app_version: str = Field(..., description="应用版本")
    python_version: str = Field(..., description="Python版本")
    platform: str = Field(..., description="运行平台")
    memory_usage: Dict[str, Any] = Field(..., description="内存使用情况")


class OperationResponse(BaseModel):
    """通用操作响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    timestamp: str = Field(..., description="时间戳")
    data: Optional[Dict[str, Any]] = Field(None, description="额外数据")