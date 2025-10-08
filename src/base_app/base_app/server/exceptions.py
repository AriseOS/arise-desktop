"""
API异常处理
"""
from fastapi import HTTPException


class SessionNotFoundError(HTTPException):
    """会话不存在错误"""
    def __init__(self, session_id: str):
        super().__init__(
            status_code=404,
            detail=f"Session {session_id} not found",
            headers={"X-Error-Code": "SESSION_NOT_FOUND"}
        )


class SessionPermissionError(HTTPException):
    """会话权限错误"""
    def __init__(self, session_id: str, user_id: str):
        super().__init__(
            status_code=403,
            detail=f"User {user_id} has no access to session {session_id}",
            headers={"X-Error-Code": "SESSION_PERMISSION_DENIED"}
        )


class AgentNotInitializedError(HTTPException):
    """Agent未初始化错误"""
    def __init__(self):
        super().__init__(
            status_code=503,
            detail="Agent service not initialized",
            headers={"X-Error-Code": "AGENT_NOT_INITIALIZED"}
        )


class StorageError(HTTPException):
    """存储层错误"""
    def __init__(self, message: str):
        super().__init__(
            status_code=500,
            detail=f"Storage error: {message}",
            headers={"X-Error-Code": "STORAGE_ERROR"}
        )