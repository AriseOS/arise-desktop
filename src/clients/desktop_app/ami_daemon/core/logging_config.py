"""
Logging configuration module for App Backend.

Provides rotating file handlers for system logs with the following features:
- Rotating file handler (10MB per file, 5 backups)
- Separate error log file
- JSON format for easy parsing
- Console output for development

Log separation principle:
- System logs (app.log): App startup/shutdown, service status, config loading, network
- Workflow execution logs: Written separately to workflow_history/runs/{run_id}/log.jsonl
"""

import logging
import logging.handlers
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }

        # Standard LogRecord attributes to exclude from extra
        standard_attrs = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs",
            "pathname", "process", "processName", "relativeCreated",
            "stack_info", "exc_info", "exc_text", "thread", "threadName",
            "message", "asctime", "taskName"  # taskName is added by asyncio
        }

        # Add extra fields if present
        if hasattr(record, "__dict__"):
            extra_keys = set(record.__dict__.keys()) - standard_attrs
            if extra_keys:
                extra_data = {k: record.__dict__[k] for k in extra_keys}
                # Filter out None values
                extra_data = {k: v for k, v in extra_data.items() if v is not None}
                if extra_data:
                    log_data["extra"] = extra_data

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False, default=str)


class ReadableFormatter(logging.Formatter):
    """Human-readable formatter for console output."""

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )


# Module-level state
_logging_configured = False
_log_dir: Optional[Path] = None


def setup_logging(
    log_dir: Optional[Path] = None,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> Path:
    """
    Configure logging with rotating file handlers.

    Args:
        log_dir: Directory for log files. Defaults to ~/.ami/logs
        console_level: Log level for console output
        file_level: Log level for file output
        max_bytes: Maximum size per log file before rotation (default 10MB)
        backup_count: Number of backup files to keep (default 5)

    Returns:
        Path to the log directory
    """
    global _logging_configured, _log_dir

    if _logging_configured:
        return _log_dir

    # Set default log directory
    if log_dir is None:
        log_dir = Path.home() / ".ami" / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)
    _log_dir = log_dir

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Clear any existing handlers
    root_logger.handlers.clear()

    # Console handler - human readable format
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(ReadableFormatter())
    root_logger.addHandler(console_handler)

    # Main app log - rotating file handler with JSON format
    app_log_file = log_dir / "app.log"
    app_handler = logging.handlers.RotatingFileHandler(
        filename=app_log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    app_handler.setLevel(file_level)
    app_handler.setFormatter(JsonFormatter())
    root_logger.addHandler(app_handler)

    # Error log - only WARNING and above
    error_log_file = log_dir / "error.log"
    error_handler = logging.handlers.RotatingFileHandler(
        filename=error_log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(JsonFormatter())
    root_logger.addHandler(error_handler)

    _logging_configured = True

    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(
        "Logging configured",
        extra={
            "log_dir": str(log_dir),
            "app_log": str(app_log_file),
            "error_log": str(error_log_file),
            "max_bytes": max_bytes,
            "backup_count": backup_count,
        }
    )

    return log_dir


def get_log_dir() -> Optional[Path]:
    """Get the configured log directory."""
    return _log_dir


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)
