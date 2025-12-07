"""
Admin Dashboard API Endpoints

Provides endpoints for admin dashboard to manage users and view statistics
"""
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...database.connection import get_db_session
from ...models import User, ApiCall, MonthlyUsageStats, WorkflowQuota


router = APIRouter(prefix="/api/admin", tags=["admin"])


# Simple cache for stats (avoid expensive queries on every request)
_stats_cache = {
    "data": None,
    "timestamp": None
}
_CACHE_TTL_SECONDS = 60  # Cache for 60 seconds


# Response Models
class UserListItem(BaseModel):
    """User list item for admin dashboard"""
    user_id: str
    username: str
    email: str
    api_key_masked: str
    created_at: datetime
    is_active: bool
    trial_end_date: Optional[datetime]
    workflow_quota_used: int
    workflow_quota_limit: int
    total_tokens: int

    class Config:
        from_attributes = True


class UserDetailResponse(BaseModel):
    """Detailed user information"""
    user_id: str
    username: str
    email: str
    api_key_masked: str
    created_at: datetime
    is_active: bool
    trial_end_date: Optional[datetime]
    workflow_quota_used: int
    workflow_quota_limit: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_api_calls: int

    class Config:
        from_attributes = True


class UsageStatsResponse(BaseModel):
    """Usage statistics"""
    total_users: int
    active_users: int
    total_workflow_executions: int
    total_api_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int


class DailyUsageResponse(BaseModel):
    """Daily usage statistics"""
    date: str
    api_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    workflow_executions: int


# Dependency: Simple admin authentication
async def verify_admin(
    admin_key: str = Query(..., alias="admin_key")
) -> bool:
    """Verify admin access"""
    from ...config import get_config
    config = get_config()
    expected_key = config.get("admin.api_key", "admin-secret-key-change-me")

    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    return True


@router.get("/users", response_model=List[UserListItem])
async def list_users(
    db: Session = Depends(get_db_session),
    _admin: bool = Depends(verify_admin),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = Query(None)
):
    """List all users with pagination and search"""
    query = db.query(User)

    # Search filter
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (User.username.ilike(search_pattern)) |
            (User.email.ilike(search_pattern))
        )

    # Pagination
    users = query.offset(skip).limit(limit).all()

    # Build response
    result = []
    now = datetime.utcnow()
    current_month = now.strftime("%Y-%m")

    for user in users:
        # Get current month workflow usage
        monthly_stats = db.query(MonthlyUsageStats).filter(
            MonthlyUsageStats.user_id == user.user_id,
            MonthlyUsageStats.year_month == current_month
        ).first()

        workflow_used = monthly_stats.workflow_executions if monthly_stats else 0

        # Get workflow quota
        quota = db.query(WorkflowQuota).filter(
            WorkflowQuota.user_id == user.user_id
        ).first()

        workflow_limit = quota.monthly_limit if quota else 100

        # Get total tokens from monthly stats
        all_stats = db.query(
            func.sum(MonthlyUsageStats.total_tokens)
        ).filter(
            MonthlyUsageStats.user_id == user.user_id
        ).scalar() or 0

        result.append(UserListItem(
            user_id=str(user.user_id),
            username=user.username,
            email=user.email,
            api_key_masked=user.to_dict(include_api_key=True, mask_api_key=True).get("api_key", "N/A"),
            created_at=user.created_at,
            is_active=user.is_active,
            trial_end_date=user.trial_end_date,
            workflow_quota_used=workflow_used,
            workflow_quota_limit=workflow_limit,
            total_tokens=all_stats
        ))

    return result


@router.get("/users/{user_id}", response_model=UserDetailResponse)
async def get_user_detail(
    user_id: str,
    db: Session = Depends(get_db_session),
    _admin: bool = Depends(verify_admin)
):
    """Get detailed user information"""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get current month workflow usage
    now = datetime.utcnow()
    current_month = now.strftime("%Y-%m")

    monthly_stats = db.query(MonthlyUsageStats).filter(
        MonthlyUsageStats.user_id == user.user_id,
        MonthlyUsageStats.year_month == current_month
    ).first()

    workflow_used = monthly_stats.workflow_executions if monthly_stats else 0

    # Get workflow quota
    quota = db.query(WorkflowQuota).filter(
        WorkflowQuota.user_id == user.user_id
    ).first()

    workflow_limit = quota.monthly_limit if quota else 100

    # Get token usage stats (all time)
    token_stats = db.query(
        func.sum(MonthlyUsageStats.input_tokens).label('input'),
        func.sum(MonthlyUsageStats.output_tokens).label('output'),
        func.sum(MonthlyUsageStats.call_count).label('calls')
    ).filter(
        MonthlyUsageStats.user_id == user.user_id
    ).first()

    input_tokens = token_stats.input or 0 if token_stats else 0
    output_tokens = token_stats.output or 0 if token_stats else 0
    api_calls = token_stats.calls or 0 if token_stats else 0

    return UserDetailResponse(
        user_id=str(user.user_id),
        username=user.username,
        email=user.email,
        api_key_masked=user.to_dict(include_api_key=True, mask_api_key=True).get("api_key", "N/A"),
        created_at=user.created_at,
        is_active=user.is_active,
        trial_end_date=user.trial_end_date,
        workflow_quota_used=workflow_used,
        workflow_quota_limit=workflow_limit,
        total_input_tokens=input_tokens,
        total_output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        total_api_calls=api_calls
    )


@router.get("/stats/overview", response_model=UsageStatsResponse)
async def get_usage_stats(
    db: Session = Depends(get_db_session),
    _admin: bool = Depends(verify_admin)
):
    """Get overall usage statistics (with 60-second cache)"""
    global _stats_cache

    # Check cache
    now = datetime.utcnow()
    if (_stats_cache["data"] is not None and
        _stats_cache["timestamp"] is not None and
        (now - _stats_cache["timestamp"]).total_seconds() < _CACHE_TTL_SECONDS):
        # Return cached data
        return _stats_cache["data"]

    # Cache miss or expired - query database
    # Total and active users
    total_users = db.query(func.count(User.user_id)).scalar() or 0
    active_users = db.query(func.count(User.user_id)).filter(User.is_active == True).scalar() or 0

    # Total workflow executions (all time)
    total_workflows = db.query(
        func.sum(MonthlyUsageStats.workflow_executions)
    ).scalar() or 0

    # Total token usage (all time)
    token_stats = db.query(
        func.sum(MonthlyUsageStats.input_tokens).label('input'),
        func.sum(MonthlyUsageStats.output_tokens).label('output'),
        func.sum(MonthlyUsageStats.call_count).label('calls')
    ).first()

    input_tokens = token_stats.input or 0 if token_stats else 0
    output_tokens = token_stats.output or 0 if token_stats else 0
    api_calls = token_stats.calls or 0 if token_stats else 0

    result = UsageStatsResponse(
        total_users=total_users,
        active_users=active_users,
        total_workflow_executions=total_workflows,
        total_api_calls=api_calls,
        total_input_tokens=input_tokens,
        total_output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens
    )

    # Update cache
    _stats_cache["data"] = result
    _stats_cache["timestamp"] = now

    return result


@router.get("/stats/daily", response_model=List[DailyUsageResponse])
async def get_daily_stats(
    db: Session = Depends(get_db_session),
    _admin: bool = Depends(verify_admin),
    days: int = Query(7, ge=1, le=90)
):
    """Get daily usage statistics"""
    # Calculate date range
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days - 1)

    # Query API calls by date
    api_calls_by_date = db.query(
        func.date(ApiCall.timestamp).label('date'),
        func.count(ApiCall.call_id).label('calls'),
        func.sum(ApiCall.input_tokens).label('input'),
        func.sum(ApiCall.output_tokens).label('output')
    ).filter(
        func.date(ApiCall.timestamp) >= start_date
    ).group_by(
        func.date(ApiCall.timestamp)
    ).all()

    # Build date-indexed dictionary
    api_dict = {str(row.date): row for row in api_calls_by_date}

    # Build response for all days
    result = []
    current_date = start_date
    while current_date <= end_date:
        date_str = str(current_date)
        api_row = api_dict.get(date_str)

        result.append(DailyUsageResponse(
            date=date_str,
            api_calls=api_row.calls if api_row else 0,
            input_tokens=api_row.input or 0 if api_row else 0,
            output_tokens=api_row.output or 0 if api_row else 0,
            total_tokens=(api_row.input or 0) + (api_row.output or 0) if api_row else 0,
            workflow_executions=0  # TODO: Add daily workflow tracking
        ))

        current_date += timedelta(days=1)

    return result


@router.post("/users/{user_id}/quota")
async def update_user_quota(
    user_id: str,
    new_limit: int = Query(..., ge=0, le=10000),
    db: Session = Depends(get_db_session),
    _admin: bool = Depends(verify_admin)
):
    """Update user's workflow execution quota"""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get or create quota record
    quota = db.query(WorkflowQuota).filter(
        WorkflowQuota.user_id == user.user_id
    ).first()

    if quota:
        quota.monthly_limit = new_limit
    else:
        # Create new quota record
        now = datetime.utcnow()
        quota = WorkflowQuota(
            user_id=user.user_id,
            monthly_limit=new_limit,
            current_month=now.strftime("%Y-%m"),
            current_usage=0
        )
        db.add(quota)

    db.commit()

    return {
        "success": True,
        "message": f"Quota updated for user {user.username}",
        "user_id": str(user_id),
        "new_limit": new_limit
    }


@router.post("/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: str,
    db: Session = Depends(get_db_session),
    _admin: bool = Depends(verify_admin)
):
    """Enable or disable user account"""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = not user.is_active
    db.commit()

    return {
        "success": True,
        "message": f"User {user.username} {'activated' if user.is_active else 'deactivated'}",
        "user_id": str(user_id),
        "is_active": user.is_active
    }


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    db: Session = Depends(get_db_session),
    _admin: bool = Depends(verify_admin)
):
    """Delete user account and all associated data"""
    from uuid import UUID

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    user = db.query(User).filter(User.user_id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    username = user.username

    # Delete associated data (cascade should handle this, but explicit deletion for clarity)
    # Delete workflow quota
    db.query(WorkflowQuota).filter(WorkflowQuota.user_id == user_uuid).delete()

    # Delete monthly usage stats
    db.query(MonthlyUsageStats).filter(MonthlyUsageStats.user_id == user_uuid).delete()

    # Delete API calls
    db.query(ApiCall).filter(ApiCall.user_id == user_uuid).delete()

    # Delete user
    db.delete(user)
    db.commit()

    return {
        "success": True,
        "message": f"User {username} and all associated data deleted successfully",
        "user_id": str(user_id)
    }
