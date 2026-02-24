"""
JWT Token Management for Cloud Backend.

Cloud Backend issues its own JWT tokens. User authentication (password
verification) is delegated to sub2api. This module only handles:
1. JWT access/refresh token creation and verification
2. Token payload management (sub = sub2api user_id)
3. Encryption of embedded sub2api JWT tokens (s2a claim)
"""
import os
import logging
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from cryptography.fernet import Fernet, InvalidToken
from core.config_service import get_config

logger = logging.getLogger(__name__)

_config = get_config()

# JWT configuration - read env var name and algorithm from yaml
_secret_key_env = _config.get("auth.secret_key_env", "JWT_SECRET_KEY")
SECRET_KEY = os.environ.get(_secret_key_env)
if not SECRET_KEY:
    raise RuntimeError(
        f"{_secret_key_env} environment variable is required. "
        "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )

ALGORITHM = _config.get("auth.algorithm", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = _config.get("auth.access_token_expire_minutes", 60)
REFRESH_TOKEN_EXPIRE_DAYS = _config.get("auth.refresh_token_expire_days", 30)

# Fernet key for encrypting embedded sub2api JWTs (s2a claim).
# Derived from JWT_SECRET_KEY so no extra env var needed.
_fernet_key = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest())
_fernet = Fernet(_fernet_key)


def encrypt_s2a(plaintext: str) -> str:
    """Encrypt a sub2api JWT before embedding in our JWT."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_s2a(ciphertext: str) -> Optional[str]:
    """Decrypt an embedded sub2api JWT. Returns None if decryption fails."""
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        return None


class AuthService:
    """JWT token creation and verification. No local user database."""

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token with type='access'."""
        to_encode = data.copy()
        # Encrypt s2a before embedding
        if "s2a" in to_encode and to_encode["s2a"]:
            to_encode["s2a"] = encrypt_s2a(to_encode["s2a"])
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire, "type": "access"})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    def create_refresh_token(self, data: dict) -> str:
        """Create JWT refresh token with type='refresh' (30-day expiry)."""
        to_encode = data.copy()
        # Encrypt s2a before embedding
        if "s2a" in to_encode and to_encode["s2a"]:
            to_encode["s2a"] = encrypt_s2a(to_encode["s2a"])
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    def verify_token(self, token: str, expected_type: Optional[str] = None) -> Optional[dict]:
        """Verify JWT token and return payload. Optionally check token type.

        Automatically decrypts the s2a claim if present.
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            if expected_type and payload.get("type") != expected_type:
                return None
            # Decrypt s2a if present
            if payload.get("s2a"):
                decrypted = decrypt_s2a(payload["s2a"])
                payload["s2a"] = decrypted  # None if decryption failed
            return payload
        except JWTError:
            return None


# Global auth service instance
auth_service = AuthService()
