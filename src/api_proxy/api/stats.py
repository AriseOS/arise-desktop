"""
Statistics API endpoints
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database.connection import get_db_session
from ..services.user_service import get_user_service
from ..services.stats_service import get_stats_service
from ..models import User
from .schemas import (
    WorkflowExecutionRequest,
    WorkflowExecutionResponse,
    QuotaInfoResponse,
    QuotaStatus,
    ErrorResponse,
)
from .proxy import validate_api_key


router = APIRouter()
user_service = get_user_service()
stats_service = get_stats_service()


@router.post(
    "/workflow-execution",
    response_model=WorkflowExecutionResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid API key"},
    }
)
async def report_workflow_execution(
    request: WorkflowExecutionRequest,
    user: User = Depends(validate_api_key),
    db: Session = Depends(get_db_session)
):
    """Report workflow execution

    Called by App Backend when a workflow completes.
    Only successful executions count toward quota.

    Request body:
        - workflow_id: Workflow identifier
        - status: 'success' or 'failed'
        - execution_time_ms: Execution time in milliseconds (optional)
        - metadata: Additional metadata (optional)

    Returns:
        WorkflowExecutionResponse with quota status and warnings

    Raises:
        HTTPException 401: If API key is invalid
    """
    # Record workflow execution
    is_success = request.status == "success"

    quota_status_dict = stats_service.record_workflow_execution(
        db=db,
        user_id=user.user_id,
        workflow_id=request.workflow_id,
        success=is_success
    )

    # Convert to Pydantic model
    quota_status = QuotaStatus(**quota_status_dict)

    return WorkflowExecutionResponse(
        success=True,
        quota_status=quota_status
    )


@router.get(
    "/quota",
    response_model=QuotaInfoResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid API key"},
    }
)
async def get_quota_info(
    user: User = Depends(validate_api_key),
    db: Session = Depends(get_db_session)
):
    """Get user quota information

    Returns current usage, limits, and token statistics.

    Returns:
        QuotaInfoResponse with detailed quota and usage information

    Raises:
        HTTPException 401: If API key is invalid
    """
    current_month = datetime.utcnow().strftime("%Y-%m")

    # Get workflow quota
    quota = stats_service.get_user_quota(db, user.user_id)

    if quota is None:
        # Create default quota if doesn't exist
        quota_dict = {
            "workflow_executions": {
                "limit": 100,
                "used": 0,
                "remaining": 100,
                "percentage": 0.0
            }
        }
    else:
        quota_dict = {
            "workflow_executions": {
                "limit": quota.monthly_limit,
                "used": quota.current_usage,
                "remaining": quota.remaining,
                "percentage": round(quota.percentage_used, 2)
            }
        }

    # Add trial info
    quota_dict["trial_info"] = {
        "is_trial": user.is_trial_active,
        "start_date": user.created_at.date().isoformat(),
        "end_date": user.trial_end_date.date().isoformat() if user.trial_end_date else None,
        "days_remaining": user.trial_days_remaining
    }

    # Get monthly token usage
    monthly_stats = stats_service.get_monthly_stats(db, user.user_id, current_month)

    if monthly_stats is None:
        token_usage = {
            "current_month": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0
            }
        }
    else:
        token_usage = {
            "current_month": {
                "input_tokens": monthly_stats.input_tokens,
                "output_tokens": monthly_stats.output_tokens,
                "total_tokens": monthly_stats.total_tokens
            }
        }

    return QuotaInfoResponse(
        success=True,
        user_id=str(user.user_id),
        current_month=current_month,
        quota=quota_dict,
        token_usage=token_usage
    )
