"""
Cloud Backend Middleware

Provides request context injection for logging and tracing.
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


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to inject request context for logging.

    Extracts:
    - request_id: Generated unique ID for this request
    - user_id: From X-Ami-API-Key header or request body
    - workflow_id: From request path if present
    - session_id: From request path if present
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate request ID
        request_id = generate_request_id()

        # Extract user_id from header
        user_id: Optional[str] = None
        api_key = request.headers.get("x-ami-api-key")
        if api_key:
            # Use first 8 chars of API key as user identifier for logging
            # (Don't log full key for security)
            user_id = f"key_{api_key[:8]}..."

        # Extract workflow_id and session_id from path
        workflow_id: Optional[str] = None
        session_id: Optional[str] = None
        path = request.url.path

        # Parse path for IDs
        # e.g., /api/v1/workflows/{workflow_id}/...
        # e.g., /api/v1/intent-builder/sessions/{session_id}/...
        path_parts = path.split("/")
        for i, part in enumerate(path_parts):
            if part == "workflows" and i + 1 < len(path_parts):
                workflow_id = path_parts[i + 1]
            elif part == "sessions" and i + 1 < len(path_parts):
                session_id = path_parts[i + 1]
            elif part == "executions" and i + 1 < len(path_parts):
                # execution_id could also be useful
                pass

        # Set context for this request
        set_request_context(
            request_id=request_id,
            user_id=user_id,
            workflow_id=workflow_id,
            session_id=session_id,
        )

        # Add request_id to response headers for tracing
        start_time = time.time()

        try:
            response = await call_next(request)

            # Calculate request duration
            duration_ms = int((time.time() - start_time) * 1000)

            # Add tracing headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration_ms}ms"

            # Log request completion
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
            # Log error
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
            # Clear context after request
            clear_request_context()
