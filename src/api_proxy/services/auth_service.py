"""
Authentication service

Handles password hashing, JWT token generation, and API key validation
"""
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from ..config import get_config


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Authentication service"""

    def __init__(self):
        config = get_config()
        self.jwt_secret = config.get_jwt_secret_key()
        self.jwt_algorithm = config.get_jwt_algorithm()
        self.jwt_expire_minutes = config.get_jwt_expire_minutes()

    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt

        Args:
            password: Plain text password

        Returns:
            Hashed password
        """
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash

        Args:
            plain_password: Plain text password
            hashed_password: Hashed password

        Returns:
            True if password matches, False otherwise
        """
        return pwd_context.verify(plain_password, hashed_password)

    def create_access_token(self, user_id: str, username: str, is_admin: bool = False) -> str:
        """Create JWT access token

        Args:
            user_id: User ID
            username: Username
            is_admin: Whether user is admin

        Returns:
            JWT token string
        """
        expires = datetime.utcnow() + timedelta(minutes=self.jwt_expire_minutes)

        payload = {
            "sub": user_id,  # Subject (user ID)
            "username": username,
            "is_admin": is_admin,
            "exp": expires,  # Expiration time
            "iat": datetime.utcnow(),  # Issued at
        }

        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        return token

    def decode_access_token(self, token: str) -> Optional[dict]:
        """Decode and validate JWT access token

        Args:
            token: JWT token string

        Returns:
            Payload dict if valid, None if invalid or expired
        """
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return payload
        except JWTError:
            return None

    def extract_user_id_from_token(self, token: str) -> Optional[str]:
        """Extract user ID from JWT token

        Args:
            token: JWT token string

        Returns:
            User ID if valid, None otherwise
        """
        payload = self.decode_access_token(token)
        if payload:
            return payload.get("sub")
        return None


# Singleton instance
_auth_service: AuthService = None


def get_auth_service() -> AuthService:
    """Get authentication service instance (singleton)"""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
