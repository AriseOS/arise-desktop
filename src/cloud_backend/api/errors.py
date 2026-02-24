"""
Structured Error Codes and Unified Error Response System

Provides:
1. ErrorCode enum with all application error codes
2. AppError exception class for raising structured errors
3. FastAPI exception handlers for unified JSON error responses
"""

from enum import Enum
from typing import Optional, Any
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorCode(str, Enum):
    """Application error codes."""

    # Auth errors (AUTH_xxx)
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_INVALID_TOKEN = "AUTH_INVALID_TOKEN"
    AUTH_TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED"
    AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
    AUTH_MISSING_FIELDS = "AUTH_MISSING_FIELDS"
    AUTH_USER_NOT_FOUND = "AUTH_USER_NOT_FOUND"
    AUTH_USER_DISABLED = "AUTH_USER_DISABLED"
    AUTH_USERNAME_EXISTS = "AUTH_USERNAME_EXISTS"
    AUTH_EMAIL_EXISTS = "AUTH_EMAIL_EXISTS"
    AUTH_WEAK_PASSWORD = "AUTH_WEAK_PASSWORD"
    AUTH_INVALID_PASSWORD = "AUTH_INVALID_PASSWORD"
    AUTH_NO_API_KEY = "AUTH_NO_API_KEY"
    AUTH_REFRESH_FAILED = "AUTH_REFRESH_FAILED"

    # Validation errors (VALIDATION_xxx)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    VALIDATION_MISSING_FIELD = "VALIDATION_MISSING_FIELD"
    VALIDATION_INVALID_VALUE = "VALIDATION_INVALID_VALUE"
    VALIDATION_FIELD_TOO_LONG = "VALIDATION_FIELD_TOO_LONG"

    # Memory errors (MEMORY_xxx)
    MEMORY_NOT_FOUND = "MEMORY_NOT_FOUND"
    MEMORY_OPERATION_FAILED = "MEMORY_OPERATION_FAILED"
    MEMORY_PHRASE_NOT_FOUND = "MEMORY_PHRASE_NOT_FOUND"
    MEMORY_PUBLIC_UNAVAILABLE = "MEMORY_PUBLIC_UNAVAILABLE"
    MEMORY_NOT_OWNED = "MEMORY_NOT_OWNED"

    # Service errors (SERVICE_xxx)
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    SERVICE_SUB2API_FAILED = "SERVICE_SUB2API_FAILED"
    SERVICE_EMBEDDING_FAILED = "SERVICE_EMBEDDING_FAILED"
    SERVICE_RERANK_DISABLED = "SERVICE_RERANK_DISABLED"
    SERVICE_LLM_FAILED = "SERVICE_LLM_FAILED"

    # Rate limit
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"

    # Generic
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_FOUND = "NOT_FOUND"
    FORBIDDEN = "FORBIDDEN"


class AppError(Exception):
    """Structured application error with error code."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int = 400,
        details: Optional[Any] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)

    def to_dict(self) -> dict:
        error = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.details is not None:
            error["details"] = self.details
        return {"success": False, "error": error}


def register_error_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = _status_to_error_code(exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": code.value,
                    "message": str(exc.detail),
                },
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = []
        for err in exc.errors():
            loc = " -> ".join(str(l) for l in err["loc"])
            errors.append({"field": loc, "message": err["msg"]})
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": {
                    "code": ErrorCode.VALIDATION_ERROR.value,
                    "message": "Request validation failed",
                    "details": errors,
                },
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": ErrorCode.INTERNAL_ERROR.value,
                    "message": "Internal server error",
                },
            },
        )


def _status_to_error_code(status_code: int) -> ErrorCode:
    """Map HTTP status code to a default ErrorCode."""
    mapping = {
        400: ErrorCode.VALIDATION_ERROR,
        401: ErrorCode.AUTH_REQUIRED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        429: ErrorCode.RATE_LIMIT_EXCEEDED,
        500: ErrorCode.INTERNAL_ERROR,
        502: ErrorCode.SERVICE_UNAVAILABLE,
        503: ErrorCode.SERVICE_UNAVAILABLE,
    }
    return mapping.get(status_code, ErrorCode.INTERNAL_ERROR)
