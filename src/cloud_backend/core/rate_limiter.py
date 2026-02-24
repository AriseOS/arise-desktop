"""
Rate Limiting for Cloud Backend

Uses slowapi to apply per-endpoint rate limits.
Configuration is read from cloud-backend.yaml rate_limit section.

Usage in main.py:
    from core.rate_limiter import limiter, rate_limit_handler
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

    @app.post("/api/v1/auth/login")
    @limiter.limit("5/minute")
    async def login(request: Request, data: LoginRequest):
        ...
"""

import logging
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse

from core.config_service import get_config

logger = logging.getLogger(__name__)

_config = get_config()
_rate_config = _config.get("rate_limit", {})

# Rate limit strings from config
RATE_AUTH_LOGIN = _rate_config.get("auth_login", "5/minute")
RATE_AUTH_REGISTER = _rate_config.get("auth_register", "3/minute")
RATE_AUTH_PASSWORD_RESET = _rate_config.get("auth_password_reset", "3/minute")
RATE_API_DEFAULT = _rate_config.get("api_default", "60/minute")
RATE_PUBLIC_DEFAULT = _rate_config.get("public_default", "30/minute")

# Create limiter instance
_enabled = _rate_config.get("enabled", True)

limiter = Limiter(
    key_func=get_remote_address,
    enabled=_enabled,
    default_limits=[RATE_API_DEFAULT],
)


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom handler for rate limit exceeded errors."""
    logger.warning(f"Rate limit exceeded: {request.client.host} on {request.url.path}")
    return JSONResponse(
        status_code=429,
        content={
            "success": False,
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": f"Rate limit exceeded: {exc.detail}",
            },
        },
    )
