"""
Cloud Backend Logging Configuration

Provides structured JSON logging with request context injection.
Designed for integration with Loki/Grafana.

Features:
- JSON format output for structured logging
- Request context injection (user_id, request_id, workflow_id)
- Contextvars for passing context through async call chains
- File handler for Promtail collection
- Optional Loki handler for direct log shipping
"""

import json
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

# ============================================================================
# Context Variables for Request Tracking
# ============================================================================

request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
workflow_id_var: ContextVar[Optional[str]] = ContextVar("workflow_id", default=None)
session_id_var: ContextVar[Optional[str]] = ContextVar("session_id", default=None)


def get_request_context() -> Dict[str, Optional[str]]:
    """Get current request context from contextvars."""
    return {
        "request_id": request_id_var.get(),
        "user_id": user_id_var.get(),
        "workflow_id": workflow_id_var.get(),
        "session_id": session_id_var.get(),
    }


def set_request_context(
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    session_id: Optional[str] = None,
):
    """Set request context in contextvars."""
    if request_id:
        request_id_var.set(request_id)
    if user_id:
        user_id_var.set(user_id)
    if workflow_id:
        workflow_id_var.set(workflow_id)
    if session_id:
        session_id_var.set(session_id)


def clear_request_context():
    """Clear all request context."""
    request_id_var.set(None)
    user_id_var.set(None)
    workflow_id_var.set(None)
    session_id_var.set(None)


def generate_request_id() -> str:
    """Generate a new request ID."""
    return f"req_{uuid.uuid4().hex[:12]}"


# ============================================================================
# JSON Formatter
# ============================================================================


class JSONFormatter(logging.Formatter):
    """
    Format log records as JSON with context injection.

    Output format:
    {
        "timestamp": "2025-01-15T10:30:00.123Z",
        "level": "INFO",
        "service": "cloud_backend",
        "module": "intent_builder",
        "request_id": "req_abc123",
        "user_id": "user_123",
        "workflow_id": "wf_456",
        "message": "Generated workflow successfully",
        "extra": {"steps_count": 5}
    }
    """

    def __init__(self, service_name: str = "cloud_backend"):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        # Get current request context
        context = get_request_context()

        # Build base log entry
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "module": record.name,
            "message": record.getMessage(),
        }

        # Add request context (only if set)
        if context["request_id"]:
            log_entry["request_id"] = context["request_id"]
        if context["user_id"]:
            log_entry["user_id"] = context["user_id"]
        if context["workflow_id"]:
            log_entry["workflow_id"] = context["workflow_id"]
        if context["session_id"]:
            log_entry["session_id"] = context["session_id"]

        # Add extra fields from record
        extra = {}
        for key, value in record.__dict__.items():
            if key not in (
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "exc_info",
                "exc_text",
                "thread",
                "threadName",
                "message",
                "taskName",
            ):
                extra[key] = value

        if extra:
            log_entry["extra"] = extra

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False, default=str)


# ============================================================================
# Setup Functions
# ============================================================================


def setup_logging(
    service_name: str = "cloud_backend",
    level: str = "INFO",
    json_format: bool = True,
    log_file: Optional[str] = None,
    max_bytes: int = 100 * 1024 * 1024,  # 100MB
    backup_count: int = 5,
    loki_url: Optional[str] = None,
) -> None:
    """
    Configure logging for Cloud Backend.

    Args:
        service_name: Service name for log entries
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_format: Use JSON format (True) or plain text (False)
        log_file: Path to log file (enables file logging for Promtail)
        max_bytes: Max size per log file before rotation
        backup_count: Number of backup files to keep
        loki_url: Optional Loki push URL for direct shipping
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create formatter
    if json_format:
        formatter = JSONFormatter(service_name)
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler for Promtail collection
    if log_file:
        log_path = Path(log_file).expanduser().resolve()
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Use RotatingFileHandler to prevent log files from growing too large
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, level.upper()))
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        logging.info(f"File logging enabled: {log_path}")

    # Optional: Loki handler for direct log shipping
    if loki_url:
        try:
            from logging_loki import LokiHandler

            loki_handler = LokiHandler(
                url=loki_url,
                tags={"service": service_name},
                version="1",
            )
            loki_handler.setLevel(getattr(logging, level.upper()))
            root_logger.addHandler(loki_handler)
            logging.info(f"Loki handler configured: {loki_url}")
        except ImportError:
            logging.warning(
                "python-logging-loki not installed, skipping Loki handler"
            )


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)
