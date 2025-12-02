"""
User management service
"""
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..models import User, WorkflowQuota
from ..config import get_config
from .auth_service import get_auth_service
from .encryption_service import get_encryption_service


class UserService:
    """Service for user management operations"""

    def __init__(self):
        self.auth_service = get_auth_service()
        self.encryption_service = get_encryption_service()
        self.config = get_config()

    def create_user(
        self,
        db: Session,
        username: str,
        email: str,
        password: str,
        is_admin: bool = False
    ) -> User:
        """Create a new user

        Args:
            db: Database session
            username: Username (unique)
            email: Email address (unique)
            password: Plain text password
            is_admin: Whether user is admin

        Returns:
            Created User object

        Raises:
            IntegrityError: If username or email already exists
        """
        # Hash password
        password_hash = self.auth_service.hash_password(password)

        # Generate API key (stored in plaintext for simplicity)
        api_key = self.encryption_service.generate_api_key()

        # Calculate trial end date
        trial_duration_days = self.config.get("quota.trial.trial_period_days", 30)
        trial_end_date = datetime.utcnow() + timedelta(days=trial_duration_days)

        # Create user
        user = User(
            username=username,
            email=email,
            password_hash=password_hash,
            api_key=api_key,
            is_admin=is_admin,
            trial_end_date=trial_end_date,
        )

        db.add(user)
        db.flush()  # Get user_id without committing

        # Create workflow quota
        current_month = datetime.utcnow().strftime("%Y-%m")
        trial_workflow_limit = self.config.get("quota.trial.workflow_executions_per_month", 50)
        quota = WorkflowQuota(
            user_id=user.user_id,
            monthly_limit=trial_workflow_limit,
            current_month=current_month,
            current_usage=0,
        )
        db.add(quota)

        db.commit()
        db.refresh(user)

        return user

    def get_user_by_id(self, db: Session, user_id: UUID) -> Optional[User]:
        """Get user by ID

        Args:
            db: Database session
            user_id: User ID

        Returns:
            User object if found, None otherwise
        """
        return db.query(User).filter(User.user_id == user_id).first()

    def get_user_by_username(self, db: Session, username: str) -> Optional[User]:
        """Get user by username

        Args:
            db: Database session
            username: Username

        Returns:
            User object if found, None otherwise
        """
        return db.query(User).filter(User.username == username).first()

    def get_user_by_email(self, db: Session, email: str) -> Optional[User]:
        """Get user by email

        Args:
            db: Database session
            email: Email address

        Returns:
            User object if found, None otherwise
        """
        return db.query(User).filter(User.email == email).first()

    def get_user_by_api_key(self, db: Session, api_key: str) -> Optional[User]:
        """Get user by API key

        Args:
            db: Database session
            api_key: API key (plaintext)

        Returns:
            User object if found, None otherwise
        """
        # Look up user by API key (stored in plaintext)
        return db.query(User).filter(User.api_key == api_key).first()

    def authenticate_user(self, db: Session, username: str, password: str) -> Optional[User]:
        """Authenticate user with username and password

        Args:
            db: Database session
            username: Username or email
            password: Plain text password

        Returns:
            User object if authenticated, None otherwise
        """
        # Try username first
        user = self.get_user_by_username(db, username)

        # Try email if username not found
        if user is None:
            user = self.get_user_by_email(db, username)

        # Check if user exists and password is correct
        if user is None:
            return None

        if not self.auth_service.verify_password(password, user.password_hash):
            return None

        # Check if user is active
        if not user.is_active:
            return None

        return user

    def get_plaintext_api_key(self, user: User) -> str:
        """Get plaintext API key for a user

        Args:
            user: User object

        Returns:
            Plaintext API key
        """
        return user.api_key

    def validate_api_key(self, db: Session, api_key: str) -> Optional[User]:
        """Validate API key and return associated user

        Args:
            db: Database session
            api_key: Plaintext API key

        Returns:
            User object if valid, None otherwise
        """
        user = self.get_user_by_api_key(db, api_key)

        if user is None:
            return None

        # Check if user is active
        if not user.is_active:
            return None

        return user


# Singleton instance
_user_service: UserService = None


def get_user_service() -> UserService:
    """Get user service instance (singleton)"""
    global _user_service
    if _user_service is None:
        _user_service = UserService()
    return _user_service
