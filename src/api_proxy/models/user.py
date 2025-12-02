"""
User model
"""
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, String

from ..database.connection import Base
from .types import UUID


class User(Base):
    """User model

    Represents a registered user in the system
    """
    __tablename__ = "users"

    # Primary key
    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Basic info
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)

    # API Key (encrypted)
    api_key = Column(String(255), unique=True, nullable=False, index=True)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)

    # Trial period
    trial_end_date = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<User(user_id={self.user_id}, username={self.username}, email={self.email})>"

    @property
    def is_trial_active(self) -> bool:
        """Check if user is still in trial period"""
        if self.trial_end_date is None:
            return False
        return datetime.utcnow() < self.trial_end_date

    @property
    def trial_days_remaining(self) -> Optional[int]:
        """Get remaining trial days"""
        if self.trial_end_date is None:
            return None
        if not self.is_trial_active:
            return 0
        delta = self.trial_end_date - datetime.utcnow()
        return delta.days

    def to_dict(self, include_api_key: bool = False, mask_api_key: bool = True) -> dict:
        """Convert user to dictionary

        Args:
            include_api_key: Whether to include API key in output
            mask_api_key: Whether to mask API key (ami_****xxxx)

        Returns:
            Dictionary representation
        """
        data = {
            "user_id": str(self.user_id),
            "username": self.username,
            "email": self.email,
            "is_active": self.is_active,
            "is_admin": self.is_admin,
            "is_trial_active": self.is_trial_active,
            "trial_end_date": self.trial_end_date.isoformat() if self.trial_end_date else None,
            "trial_days_remaining": self.trial_days_remaining,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

        if include_api_key:
            if mask_api_key and self.api_key:
                # Mask API key: ami_****xxxx (show first 4 and last 4 chars)
                if len(self.api_key) > 12:
                    masked = f"{self.api_key[:8]}****{self.api_key[-4:]}"
                else:
                    masked = "ami_****"
                data["api_key"] = masked
            else:
                data["api_key"] = self.api_key

        return data
