# Core Module

Core utilities for the App Backend daemon.

## Files

- `config_service.py` - Application configuration management (YAML-based)
- `logging_config.py` - Logging configuration with rotating file handlers

## Logging Architecture

The logging system follows a separation principle:

| Log Type | Location | Content |
|----------|----------|---------|
| System logs | `~/.ami/logs/app.log` | App startup/shutdown, service status, config, network |
| Error logs | `~/.ami/logs/error.log` | WARNING and above only |
| Workflow logs | `~/.ami/users/{user_id}/workflows/{workflow_id}/executions/{task_id}/log.jsonl` | Per-execution step details |

### Features

- **Rotating file handler**: 10MB per file, 5 backups (configurable)
- **JSON format**: Structured logs for easy parsing and upload
- **Separate error log**: Quick access to warnings and errors
- **Console output**: Human-readable format for development

### Usage

```python
from src.clients.desktop_app.ami_daemon.core import setup_logging, get_logger

# Initialize logging (call once at startup)
log_dir = setup_logging()

# Get a logger
logger = get_logger(__name__)
logger.info("Something happened", extra={"key": "value"})
```

### Configuration

In `config/app-backend.yaml`:

```yaml
logging:
  level: INFO
  dir: ${storage.base_path}/logs
  max_bytes: 10485760  # 10 MB
  backup_count: 5
```
