"""
对话API路由
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import StreamingResponse

from ..models.requests import ChatMessageRequest, CreateSessionRequest
from ..models.responses import (
    ChatResponse, SessionListResponse, SessionHistoryResponse, 
    SessionInfo, OperationResponse
)
from ..core.agent_service import AgentService
import logging
logger = logging.getLogger(__name__)


chat_router = APIRouter()


def get_agent_service(request: Request) -> AgentService:
    """依赖注入：获取Agent服务"""
    if not hasattr(request.app.state, 'agent_service') or not request.app.state.agent_service:
        logger.error("Agent service is None or not available")
        raise HTTPException(status_code=503, detail="Agent service not available")
    return request.app.state.agent_service


@chat_router.post("/message", response_model=ChatResponse)
async def send_message(
    request: ChatMessageRequest,
    agent_service: AgentService = Depends(get_agent_service)
):
    """发送消息到Agent"""
    try:
        result = await agent_service.send_message(
            message=request.message,
            session_id=request.session_id or "",
            user_id=request.user_id
        )
        
        if result["success"]:
            return ChatResponse(**result)
        else:
            raise HTTPException(
                status_code=500, 
                detail=result.get("error", "Failed to process message")
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@chat_router.post("/session", response_model=SessionInfo)
async def create_session(
    request: CreateSessionRequest,
    agent_service: AgentService = Depends(get_agent_service)
):
    """创建新会话"""
    try:
        session = agent_service.get_or_create_session(
            session_id="",
            user_id=request.user_id,
            title=request.title or ""
        )
        
        return SessionInfo(
            session_id=session.session_id,
            title=session.title,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            message_count=len(session.messages)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@chat_router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    user_id: str = Query(..., description="用户ID"),
    agent_service: AgentService = Depends(get_agent_service)
):
    """获取用户的会话列表"""
    try:
        sessions = agent_service.list_sessions(user_id)
        return SessionListResponse(
            sessions=[SessionInfo(**session) for session in sessions],
            total=len(sessions)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@chat_router.get("/sessions/{session_id}/history", response_model=SessionHistoryResponse)
async def get_session_history(
    session_id: str,
    limit: int = Query(50, ge=1, le=100, description="消息数量限制"),
    agent_service: AgentService = Depends(get_agent_service)
):
    """获取会话历史"""
    try:
        messages = agent_service.get_session_history(session_id, limit)
        
        if messages is None:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return SessionHistoryResponse(
            session_id=session_id,
            messages=messages,
            total=len(messages)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@chat_router.delete("/sessions/{session_id}", response_model=OperationResponse)
async def delete_session(
    session_id: str,
    user_id: str = Query(..., description="用户ID"),
    agent_service: AgentService = Depends(get_agent_service)
):
    """删除会话"""
    try:
        success = agent_service.delete_session(session_id, user_id)
        
        if not success:
            raise HTTPException(
                status_code=404, 
                detail="Session not found or permission denied"
            )
        
        return OperationResponse(
            success=True,
            message="Session deleted successfully",
            timestamp=agent_service.start_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@chat_router.get("/sessions/{session_id}")
async def get_session_info(
    session_id: str,
    agent_service: AgentService = Depends(get_agent_service)
):
    """获取会话信息"""
    try:
        session = agent_service.sessions.get(session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return SessionInfo(
            session_id=session.session_id,
            title=session.title,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            message_count=len(session.messages)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))