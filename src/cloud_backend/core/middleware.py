"""
Cloud Backend Middleware

Provides:
1. Request context injection for logging and tracing
2. Security response headers (X-Content-Type-Options, X-Frame-Options, etc.)
"""

import time
import logging
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .logging_config import (
    generate_request_id,
    set_request_context,
    clear_request_context,
)

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security response headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # HSTS: only add when behind HTTPS (Caddy handles TLS termination)
        # The Strict-Transport-Security header is added by Caddy, not here,
        # to avoid issues when running locally over HTTP during development.
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to inject request context for logging.

    Extracts:
    - request_id: Generated unique ID for this request
    - user_id: From JWT Authorization header (for logging only)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate request ID
        request_id = generate_request_id()

        # Extract user_id from JWT token (for logging only, not for auth)
        user_id: Optional[str] = None
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                from api.auth import auth_service
                payload = auth_service.verify_token(auth_header[7:])
                if payload:
                    user_id = f"user_{payload.get('sub', 'unknown')}"
            except Exception:
                pass

        # Set context for this request
        set_request_context(
            request_id=request_id,
            user_id=user_id,
        )

        # Add request_id to response headers for tracing
        start_time = time.time()
        path = request.url.path

        try:
            response = await call_next(request)

            duration_ms = int((time.time() - start_time) * 1000)

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration_ms}ms"

            logger.info(
                f"{request.method} {path} {response.status_code} ({duration_ms}ms)",
                extra={
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )

            return response

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"{request.method} {path} ERROR: {e} ({duration_ms}ms)",
                extra={
                    "method": request.method,
                    "path": path,
                    "error": str(e),
                    "duration_ms": duration_ms,
                },
                exc_info=True,
            )
            raise

        finally:
            clear_request_context()
