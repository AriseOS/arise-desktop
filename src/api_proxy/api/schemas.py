"""
Pydantic schemas for API request/response validation
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


# ============================================================================
# Authentication Schemas
# ============================================================================

class RegisterRequest(BaseModel):
    """User registration request"""
    username: str = Field(..., min_length=3, max_length=50, pattern="^[a-zA-Z0-9_-]+$")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)

    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "email": "john@example.com",
                "password": "SecurePassword123!"
            }
        }


class RegisterResponse(BaseModel):
    """User registration response"""
    success: bool
    user: dict
    api_key: str  # Only returned once during registration
    message: str = "User registered successfully"

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "user": {
                    "user_id": "123e4567-e89b-12d3-a456-426614174000",
                    "username": "john_doe",
                    "email": "john@example.com",
                    "is_trial_active": True,
                    "trial_end_date": "2025-01-01T00:00:00",
                },
                "api_key": "ami_abc123def456ghi789",
                "message": "User registered successfully"
            }
        }


class LoginRequest(BaseModel):
    """User login request"""
    username: str  # Can be username or email
    password: str

    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "password": "SecurePassword123!"
            }
        }


class LoginResponse(BaseModel):
    """User login response"""
    success: bool
    token: str  # JWT token
    user: dict
    api_key: str  # User's API key (masked)

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "user": {
                    "user_id": "123e4567-e89b-12d3-a456-426614174000",
                    "username": "john_doe",
                    "email": "john@example.com",
                },
                "api_key": "ami_****ghi789"
            }
        }


class UserInfoResponse(BaseModel):
    """User information response"""
    success: bool
    user: dict


# ============================================================================
# Statistics Schemas
# ============================================================================

class WorkflowExecutionRequest(BaseModel):
    """Workflow execution report request"""
    workflow_id: str
    status: str = Field(..., pattern="^(success|failed)$")
    execution_time_ms: Optional[int] = None
    metadata: Optional[dict] = None

    class Config:
        json_schema_extra = {
            "example": {
                "workflow_id": "wf_123456",
                "status": "success",
                "execution_time_ms": 5000,
                "metadata": {
                    "workflow_name": "ProductHunt Scraper",
                    "steps_completed": 5
                }
            }
        }


class QuotaStatus(BaseModel):
    """Quota status information"""
    current_usage: int
    monthly_limit: int
    remaining: int
    percentage_used: float
    warnings: List[str] = []

    class Config:
        json_schema_extra = {
            "example": {
                "current_usage": 45,
                "monthly_limit": 100,
                "remaining": 55,
                "percentage_used": 45.0,
                "warnings": []
            }
        }


class WorkflowExecutionResponse(BaseModel):
    """Workflow execution report response"""
    success: bool
    quota_status: QuotaStatus


class QuotaInfoResponse(BaseModel):
    """User quota information response"""
    success: bool
    user_id: str
    current_month: str
    quota: dict
    token_usage: dict

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "current_month": "2025-12",
                "quota": {
                    "workflow_executions": {
                        "limit": 100,
                        "used": 45,
                        "remaining": 55,
                        "percentage": 45.0
                    },
                    "trial_info": {
                        "is_trial": True,
                        "start_date": "2025-12-01",
                        "end_date": "2026-01-01",
                        "days_remaining": 15
                    }
                },
                "token_usage": {
                    "current_month": {
                        "input_tokens": 50000,
                        "output_tokens": 25000,
                        "total_tokens": 75000
                    }
                }
            }
        }


# ============================================================================
# Admin Schemas
# ============================================================================

class UserListResponse(BaseModel):
    """User list response"""
    success: bool
    users: List[dict]
    total: int
    page: int
    pages: int


class UserStatsResponse(BaseModel):
    """User statistics response"""
    success: bool
    user_id: str
    statistics: dict


# ============================================================================
# Error Schemas
# ============================================================================

class ErrorResponse(BaseModel):
    """Error response"""
    success: bool = False
    error: str
    detail: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "error": "Authentication failed",
                "detail": "Invalid username or password"
            }
        }
