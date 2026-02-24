"""
Pydantic Request/Response Models for all API endpoints.

Provides typed models for input validation, serialization,
and automatic OpenAPI documentation generation.
"""

from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field, EmailStr


# ===== Auth Schemas =====

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50, description="Username or email")
    password: str = Field(..., min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str
    username: str


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class RegisterResponse(BaseModel):
    success: bool = True
    access_token: str
    refresh_token: str
    user_id: str
    username: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    access_token: str


class CredentialsResponse(BaseModel):
    api_key: str


class UserProfileResponse(BaseModel):
    user_id: str
    username: str
    email: str
    role: str = "user"  # "admin" or "user"
    status: str = "active"  # "active" or "disabled"
    plan: str = "free"
    created_at: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)


class SuccessResponse(BaseModel):
    success: bool = True
    message: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=128)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


# ===== API Key Management Schemas =====

class ApiKeyItem(BaseModel):
    id: Optional[int] = None
    name: str
    key_preview: str  # Masked: sk-xxx...xxx
    created_at: Optional[str] = None


class ApiKeyListResponse(BaseModel):
    success: bool = True
    keys: List[ApiKeyItem]


class CreateApiKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)


class CreateApiKeyResponse(BaseModel):
    success: bool = True
    key: str  # Full key shown only once
    name: str
    id: Optional[int] = None


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


# ===== Admin Schemas =====

class AdminUserItem(BaseModel):
    user_id: str
    username: str
    email: str
    plan: str
    is_active: bool
    is_admin: bool
    created_at: Optional[str] = None


class AdminUserListResponse(BaseModel):
    success: bool = True
    users: List[AdminUserItem]
    total: int


class AdminSetPlanRequest(BaseModel):
    plan: str = Field(..., pattern="^(free|pro|enterprise)$")


class AdminSetActiveRequest(BaseModel):
    is_active: bool


class AdminSystemHealthResponse(BaseModel):
    success: bool = True
    database: str  # ok / error
    surrealdb: str  # ok / error / not_configured
    sub2api: str  # ok / error
    users_total: int
    users_active: int


# ===== Version Check Schemas =====

class VersionCheckRequest(BaseModel):
    version: str = Field(default="0.0.0")
    platform: str = Field(default="unknown")


class VersionCheckResponse(BaseModel):
    compatible: bool
    minimum_version: str
    client_version: str
    update_url: Optional[str] = None
    message: Optional[str] = None


# ===== Memory Schemas =====

class MemoryAddRequest(BaseModel):
    operations: List[Any] = Field(..., min_length=1)
    session_id: Optional[str] = None
    snapshots: Optional[Any] = None
    generate_embeddings: bool = True
    skip_cognitive_phrase: bool = False


class MemoryAddResponse(BaseModel):
    success: bool = True
    states_added: int = 0
    states_merged: int = 0
    page_instances_added: int = 0
    intent_sequences_added: int = 0
    actions_added: int = 0
    processing_time_ms: int = 0


class PhraseQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)


class MemoryQueryRequest(BaseModel):
    target: str = Field(default="")
    current_state: Optional[str] = None
    start_state: Optional[str] = None
    end_state: Optional[str] = None
    as_type: Optional[str] = None
    top_k: int = Field(default=10, ge=1, le=100)


class StateByUrlRequest(BaseModel):
    url: str = Field(..., min_length=1)


class SharePhraseRequest(BaseModel):
    phrase_id: str = Field(..., min_length=1)


class UnpublishPhraseRequest(BaseModel):
    phrase_id: str = Field(..., min_length=1)


class WorkflowQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)


class PlanRouteRequest(BaseModel):
    target: str = Field(..., min_length=1)
    session_id: Optional[str] = None


class PlanWithMemoryRequest(BaseModel):
    task: str = Field(..., min_length=1)


class LearnFromExecutionRequest(BaseModel):
    execution_data: Dict[str, Any] = Field(...)


# ===== Test Schemas =====

class TestEmbeddingRequest(BaseModel):
    text: str = Field(default="hello world")


class TestRerankRequest(BaseModel):
    query: str = Field(default="search engine")
    documents: List[str] = Field(default=["Google is a search engine", "Python is a programming language"])


# ===== Error Response Schema (for OpenAPI docs) =====

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail
