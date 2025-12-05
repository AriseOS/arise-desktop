"""
Statistics tracking service
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import ApiCall, DailyUsageStats, MonthlyUsageStats, WorkflowQuota
from ..config import get_config


class StatsService:
    """Service for tracking and querying usage statistics"""

    def __init__(self):
        self.config = get_config()

    def record_api_call(
        self,
        db: Session,
        user_id: UUID,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        request_type: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> ApiCall:
        """Record an API call

        Args:
            db: Database session
            user_id: User ID
            provider: LLM provider (e.g., 'anthropic')
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            request_type: Type of request (optional)
            success: Whether call was successful
            error_message: Error message if failed

        Returns:
            Created ApiCall object
        """
        total_tokens = input_tokens + output_tokens

        # Create API call record
        api_call = ApiCall(
            user_id=user_id,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            request_type=request_type,
            success=success,
            error_message=error_message,
        )
        db.add(api_call)

        # Update daily stats
        today = datetime.utcnow().date()
        daily_stats = db.query(DailyUsageStats).filter(
            DailyUsageStats.user_id == user_id,
            DailyUsageStats.date == today
        ).first()

        if daily_stats is None:
            daily_stats = DailyUsageStats(
                user_id=user_id,
                date=today,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                call_count=1,
            )
            db.add(daily_stats)
        else:
            daily_stats.input_tokens += input_tokens
            daily_stats.output_tokens += output_tokens
            daily_stats.total_tokens += total_tokens
            daily_stats.call_count += 1

        # Update monthly stats
        current_month = datetime.utcnow().strftime("%Y-%m")
        monthly_stats = db.query(MonthlyUsageStats).filter(
            MonthlyUsageStats.user_id == user_id,
            MonthlyUsageStats.year_month == current_month
        ).first()

        if monthly_stats is None:
            monthly_stats = MonthlyUsageStats(
                user_id=user_id,
                year_month=current_month,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                call_count=1,
            )
            db.add(monthly_stats)
        else:
            monthly_stats.input_tokens += input_tokens
            monthly_stats.output_tokens += output_tokens
            monthly_stats.total_tokens += total_tokens
            monthly_stats.call_count += 1

        try:
            db.commit()
            db.refresh(api_call)
        except Exception as e:
            db.rollback()
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to commit API call stats: {e}")
            # Don't raise - stats recording failure shouldn't break the API call
            # Just log the error and continue

        return api_call

    def record_workflow_execution(
        self,
        db: Session,
        user_id: UUID,
        workflow_id: str,
        success: bool = True
    ) -> dict:
        """Record a workflow execution and update quota

        Only successful executions count toward quota.

        Args:
            db: Database session
            user_id: User ID
            workflow_id: Workflow ID
            success: Whether execution was successful

        Returns:
            dict with quota status and warnings
        """
        current_month = datetime.utcnow().strftime("%Y-%m")

        # Get or create workflow quota
        quota = db.query(WorkflowQuota).filter(
            WorkflowQuota.user_id == user_id
        ).first()

        if quota is None:
            quota = WorkflowQuota(
                user_id=user_id,
                monthly_limit=self.config.quota.trial_workflow_limit,
                current_month=current_month,
                current_usage=0,
            )
            db.add(quota)
            db.flush()

        # Check if month has changed (reset quota)
        if quota.current_month != current_month:
            quota.current_month = current_month
            quota.current_usage = 0
            quota.overage_notified = False

        # Only increment for successful executions
        if success:
            quota.current_usage += 1

            # Update monthly stats
            monthly_stats = db.query(MonthlyUsageStats).filter(
                MonthlyUsageStats.user_id == user_id,
                MonthlyUsageStats.year_month == current_month
            ).first()

            if monthly_stats is None:
                monthly_stats = MonthlyUsageStats(
                    user_id=user_id,
                    year_month=current_month,
                    workflow_executions=1,
                )
                db.add(monthly_stats)
            else:
                monthly_stats.workflow_executions += 1

        db.commit()
        db.refresh(quota)

        # Generate quota status and warnings
        return self._get_quota_status(quota)

    def _get_quota_status(self, quota: WorkflowQuota) -> dict:
        """Get quota status with warnings

        Args:
            quota: WorkflowQuota object

        Returns:
            dict with quota status and warnings
        """
        percentage = quota.percentage_used
        warnings = []

        # Check warning thresholds
        thresholds = self.config.quota.warning_thresholds

        if percentage >= thresholds[2]:  # 120%
            warnings.append(
                f"You have used {quota.current_usage} of {quota.monthly_limit} "
                f"workflow executions this month. Please consider upgrading your plan."
            )
        elif percentage >= thresholds[1]:  # 100%
            warnings.append(
                f"You have reached your monthly quota of {quota.monthly_limit} executions. "
                f"You can continue using the service up to {int(quota.monthly_limit * 1.2)} executions."
            )
        elif percentage >= thresholds[0]:  # 80%
            warnings.append(
                f"You have used {quota.current_usage} of {quota.monthly_limit} "
                f"workflow executions this month ({percentage:.0f}%)."
            )

        return {
            "current_usage": quota.current_usage,
            "monthly_limit": quota.monthly_limit,
            "remaining": quota.remaining,
            "percentage_used": round(percentage, 2),
            "warnings": warnings,
        }

    def get_user_quota(self, db: Session, user_id: UUID) -> Optional[WorkflowQuota]:
        """Get user's workflow quota

        Args:
            db: Database session
            user_id: User ID

        Returns:
            WorkflowQuota object if exists, None otherwise
        """
        return db.query(WorkflowQuota).filter(
            WorkflowQuota.user_id == user_id
        ).first()

    def get_monthly_stats(self, db: Session, user_id: UUID, year_month: str) -> Optional[MonthlyUsageStats]:
        """Get monthly statistics for a user

        Args:
            db: Database session
            user_id: User ID
            year_month: Month in format YYYY-MM

        Returns:
            MonthlyUsageStats object if exists, None otherwise
        """
        return db.query(MonthlyUsageStats).filter(
            MonthlyUsageStats.user_id == user_id,
            MonthlyUsageStats.year_month == year_month
        ).first()


# Singleton instance
_stats_service: StatsService = None


def get_stats_service() -> StatsService:
    """Get statistics service instance (singleton)"""
    global _stats_service
    if _stats_service is None:
        _stats_service = StatsService()
    return _stats_service
