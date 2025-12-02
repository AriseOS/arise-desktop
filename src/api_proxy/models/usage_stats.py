"""
Usage statistics models
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, Date, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..database.connection import Base


class DailyUsageStats(Base):
    """Daily usage statistics per user

    Aggregates token usage by day
    """
    __tablename__ = "daily_usage_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)

    # Token statistics
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)

    # Call count
    call_count = Column(Integer, default=0, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Unique constraint: one record per user per day
    __table_args__ = (
        Index("idx_user_date", "user_id", "date", unique=True),
    )

    def __repr__(self) -> str:
        return f"<DailyUsageStats(user_id={self.user_id}, date={self.date}, tokens={self.total_tokens})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": str(self.user_id),
            "date": self.date.isoformat(),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "call_count": self.call_count,
            "created_at": self.created_at.isoformat(),
        }


class MonthlyUsageStats(Base):
    """Monthly usage statistics per user

    Aggregates token usage and workflow executions by month
    """
    __tablename__ = "monthly_usage_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    year_month = Column(String(7), nullable=False)  # Format: YYYY-MM

    # Token statistics
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)

    # Call count
    call_count = Column(Integer, default=0, nullable=False)

    # Workflow execution count (KEY METRIC)
    workflow_executions = Column(Integer, default=0, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Unique constraint: one record per user per month
    __table_args__ = (
        Index("idx_user_month", "user_id", "year_month", unique=True),
    )

    def __repr__(self) -> str:
        return f"<MonthlyUsageStats(user_id={self.user_id}, month={self.year_month}, workflows={self.workflow_executions})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": str(self.user_id),
            "year_month": self.year_month,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "call_count": self.call_count,
            "workflow_executions": self.workflow_executions,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class ApiCall(Base):
    """Detailed API call log

    Stores individual LLM API call records
    """
    __tablename__ = "api_calls"

    call_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # LLM details
    provider = Column(String(20), nullable=False)  # 'anthropic', 'openai', etc.
    model = Column(String(50), nullable=False)

    # Token usage
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)

    # Request type (for categorization)
    request_type = Column(String(50), nullable=True)  # 'intent_builder', 'workflow_execution', etc.

    # Status
    success = Column(Boolean, default=True, nullable=False)
    error_message = Column(Text, nullable=True)

    # Indexes for efficient querying
    __table_args__ = (
        Index("idx_user_timestamp", "user_id", "timestamp"),
        Index("idx_timestamp", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<ApiCall(call_id={self.call_id}, user_id={self.user_id}, provider={self.provider}, tokens={self.total_tokens})>"

    def to_dict(self) -> dict:
        return {
            "call_id": str(self.call_id),
            "user_id": str(self.user_id),
            "timestamp": self.timestamp.isoformat(),
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "request_type": self.request_type,
            "success": self.success,
            "error_message": self.error_message,
        }
