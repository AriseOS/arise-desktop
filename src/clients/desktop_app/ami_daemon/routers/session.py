"""
Session API

Simple REST API for session-based conversation persistence.

Endpoints:
- GET  /api/v1/session          - Get current session info and messages
- GET  /api/v1/session/history  - Get historical messages (cross-session, cursor-based)
- POST /api/v1/session/message  - Append a message
- POST /api/v1/session/new      - Force create new session
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import logging

from ..base_agent.memory.session_manager import SessionManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/session", tags=["Session"])

# Global session manager instance
_manager: Optional[SessionManager] = None


def get_manager() -> SessionManager:
    """Get or create SessionManager instance."""
    global _manager
    if _manager is None:
        _manager = SessionManager()
        logger.info(f"SessionManager initialized at {_manager.base_path}")
    return _manager


# ============== Request/Response Models ==============

class AppendMessageRequest(BaseModel):
    """Request to append a message."""
    role: str = Field(..., description="Message role: user, assistant, or system")
    content: str = Field(..., description="Message content")
    message_id: Optional[str] = Field(None, description="Message ID (auto-generated if not provided)")
    attachments: Optional[List[Dict[str, Any]]] = Field(None, description="Attachments")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadata")


class MessageResponse(BaseModel):
    """A message."""
    id: str
    role: str
    content: str
    timestamp: str
    attachments: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None
    is_context: Optional[bool] = None
    from_session: Optional[str] = None


class SessionResponse(BaseModel):
    """Current session info with messages."""
    session_id: str
    created_at: str
    updated_at: str
    message_count: int
    messages: List[MessageResponse]
    is_new_session: bool = False


class AppendMessageResponse(BaseModel):
    """Response after appending a message."""
    message_id: str
    session_id: str
    timestamp: str


class HistoryResponse(BaseModel):
    """Cross-session history response (cursor-based pagination)."""
    messages: List[MessageResponse]
    has_more: bool
    oldest_timestamp: Optional[str] = None


# ============== Endpoints ==============

@router.get("", response_model=SessionResponse)
async def get_session(limit: int = 50):
    """
    Get current session with messages.

    If session has expired (> 30 min), automatically creates a new session
    and carries context from previous session.

    Args:
        limit: Maximum messages to return (default: 50)

    Returns:
        Current session info and messages
    """
    manager = get_manager()

    # Check if this will create a new session
    current_id = manager.get_current_session_id()
    is_expired = manager._is_session_expired()

    # Get active session (may create new one if expired)
    session_id = manager.get_active_session()
    is_new_session = (current_id != session_id) or (current_id is None)

    # Get session info
    info = manager.get_session_info(session_id)
    if not info:
        info = {
            "created_at": "",
            "updated_at": "",
            "message_count": 0,
        }

    # Get messages
    messages = manager.get_messages(session_id, limit=limit)

    return SessionResponse(
        session_id=session_id,
        created_at=info.get("created_at", ""),
        updated_at=info.get("updated_at", ""),
        message_count=info.get("message_count", 0),
        messages=[
            MessageResponse(
                id=m.get("id", ""),
                role=m.get("role", ""),
                content=m.get("content", ""),
                timestamp=m.get("timestamp", ""),
                attachments=m.get("attachments"),
                metadata=m.get("metadata"),
                is_context=m.get("is_context"),
                from_session=m.get("from_session"),
            )
            for m in messages
        ],
        is_new_session=is_new_session,
    )


@router.get("/history", response_model=HistoryResponse)
async def get_history(before_timestamp: str, limit: int = 30):
    """
    Get historical messages across sessions (cursor-based pagination).

    Traverses the session chain backward from current session, filtering
    out context messages (which are duplicates carried forward).

    Args:
        before_timestamp: ISO timestamp cursor — only messages before this
        limit: Maximum messages to return (default: 30)

    Returns:
        Messages, has_more flag, and oldest_timestamp for next cursor
    """
    manager = get_manager()

    result = manager.get_history_messages(before_timestamp, limit=limit)

    return HistoryResponse(
        messages=[
            MessageResponse(
                id=m.get("id", ""),
                role=m.get("role", ""),
                content=m.get("content", ""),
                timestamp=m.get("timestamp", ""),
                attachments=m.get("attachments"),
                metadata=m.get("metadata"),
                is_context=m.get("is_context"),
                from_session=m.get("from_session"),
            )
            for m in result["messages"]
        ],
        has_more=result["has_more"],
        oldest_timestamp=result["oldest_timestamp"],
    )


@router.post("/message", response_model=AppendMessageResponse)
async def append_message(request: AppendMessageRequest):
    """
    Append a message to current session.

    If session has expired, automatically creates a new session first.

    Args:
        request: Message to append

    Returns:
        Created message info
    """
    manager = get_manager()

    # Get active session (may create new one if expired)
    session_id = manager.get_active_session()

    # Append message
    message_id = manager.append_message(
        role=request.role,
        content=request.content,
        message_id=request.message_id,
        attachments=request.attachments,
        metadata=request.metadata,
    )

    # Get updated timestamp
    info = manager.get_session_info(session_id)
    timestamp = info.get("updated_at", "") if info else ""

    return AppendMessageResponse(
        message_id=message_id,
        session_id=session_id,
        timestamp=timestamp,
    )


@router.post("/new", response_model=SessionResponse)
async def create_new_session():
    """
    Force create a new session.

    Creates new session and carries context from previous session.

    Returns:
        New session info
    """
    manager = get_manager()

    # Force new session
    session_id = manager.force_new_session()

    # Get session info
    info = manager.get_session_info(session_id)
    if not info:
        info = {
            "created_at": "",
            "updated_at": "",
            "message_count": 0,
        }

    # Get messages (context from previous session)
    messages = manager.get_messages(session_id, limit=50)

    return SessionResponse(
        session_id=session_id,
        created_at=info.get("created_at", ""),
        updated_at=info.get("updated_at", ""),
        message_count=info.get("message_count", 0),
        messages=[
            MessageResponse(
                id=m.get("id", ""),
                role=m.get("role", ""),
                content=m.get("content", ""),
                timestamp=m.get("timestamp", ""),
                attachments=m.get("attachments"),
                metadata=m.get("metadata"),
                is_context=m.get("is_context"),
                from_session=m.get("from_session"),
            )
            for m in messages
        ],
        is_new_session=True,
    )


@router.post("/touch")
async def touch_session():
    """
    Update session activity timestamp.

    Call this periodically to keep session alive without adding messages.

    Returns:
        Success status
    """
    manager = get_manager()
    manager.touch_session()
    return {"ok": True}
