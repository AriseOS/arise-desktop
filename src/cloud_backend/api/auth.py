"""
User Authentication System - JWT-based auth for Cloud Backend
"""
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from passlib.context import CryptContext
from jose import JWTError, jwt
from sqlalchemy import or_
from sqlalchemy.orm import Session
from database.models import User
from core.config_service import get_config

logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration - SECRET_KEY must be set as environment variable
SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY environment variable is required. "
        "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

_config = get_config()
REFRESH_TOKEN_EXPIRE_DAYS = _config.get("auth.refresh_token_expire_days", 30)


class AuthService:
    def __init__(self):
        self.pwd_context = pwd_context

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        return self.pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """Generate password hash"""
        return self.pwd_context.hash(password)

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        """Create JWT access token with type='access'"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire, "type": "access"})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    def create_refresh_token(self, data: dict) -> str:
        """Create JWT refresh token with type='refresh' (30-day expiry)"""
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    def verify_token(self, token: str, expected_type: Optional[str] = None) -> Optional[dict]:
        """Verify JWT token and return payload. Optionally check token type."""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            if expected_type and payload.get("type") != expected_type:
                return None
            return payload
        except JWTError:
            return None

    def authenticate_user(self, db: Session, username: str, password: str) -> Optional[User]:
        """Authenticate user by username or email and password"""
        user = db.query(User).filter(
            or_(User.username == username, User.email == username)
        ).first()
        if not user:
            logger.warning(f"Authentication failed: user not found: {username}")
            return None

        if not user.is_active:
            logger.warning(f"Authentication failed: account disabled: {username}")
            return None

        if not self.verify_password(password, user.hashed_password):
            logger.warning(f"Authentication failed: invalid password for user: {username}")
            return None

        logger.info(f"Authentication successful: {username}")
        return user

    def create_user(self, db: Session, username: str, email: str, password: str, full_name: str = None) -> User:
        """Create a new user"""
        if db.query(User).filter(User.username == username).first():
            raise ValueError("Username already exists")

        if db.query(User).filter(User.email == email).first():
            raise ValueError("Email already exists")

        hashed_password = self.get_password_hash(password)
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            full_name=full_name
        )
        db.add(user)
        try:
            db.commit()
        except Exception:
            db.rollback()
            # UNIQUE constraint violation from race condition
            raise ValueError("Username or email already exists")
        db.refresh(user)
        return user

    def get_current_user(self, db: Session, token: str) -> Optional[User]:
        """Get current user from token"""
        payload = self.verify_token(token)
        if payload is None:
            return None

        user_id = payload.get("sub")
        if user_id is None:
            return None

        user = db.query(User).filter(User.id == int(user_id)).first()
        return user


# Global auth service instance
auth_service = AuthService()
