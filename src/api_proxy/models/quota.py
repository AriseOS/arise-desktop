"""
Workflow quota management model
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from ..database.connection import Base


class WorkflowQuota(Base):
    """Workflow execution quota per user

    Tracks monthly workflow execution limits and usage
    """
    __tablename__ = "workflow_quotas"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)

    # Quota settings
    monthly_limit = Column(Integer, default=100, nullable=False)

    # Current month tracking
    current_month = Column(String(7), nullable=False)  # Format: YYYY-MM
    current_usage = Column(Integer, default=0, nullable=False)

    # Notification tracking
    overage_notified = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<WorkflowQuota(user_id={self.user_id}, usage={self.current_usage}/{self.monthly_limit})>"

    @property
    def remaining(self) -> int:
        """Get remaining quota"""
        return max(0, self.monthly_limit - self.current_usage)

    @property
    def percentage_used(self) -> float:
        """Get percentage of quota used"""
        if self.monthly_limit == 0:
            return 100.0
        return (self.current_usage / self.monthly_limit) * 100

    @property
    def is_over_limit(self) -> bool:
        """Check if usage exceeds limit"""
        return self.current_usage > self.monthly_limit

    @property
    def overage_amount(self) -> int:
        """Get amount over limit"""
        if not self.is_over_limit:
            return 0
        return self.current_usage - self.monthly_limit

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "user_id": str(self.user_id),
            "monthly_limit": self.monthly_limit,
            "current_month": self.current_month,
            "current_usage": self.current_usage,
            "remaining": self.remaining,
            "percentage_used": round(self.percentage_used, 2),
            "is_over_limit": self.is_over_limit,
            "overage_amount": self.overage_amount,
            "overage_notified": self.overage_notified,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
