# App Backend (ami_daemon)

Desktop application backend daemon providing REST API for workflow execution, recording, and browser automation.

## Directory Structure

### Local Storage (`~/.ami/`)

```
~/.ami/
├── logs/                           # System logs (app.log, error.log)
│   ├── app.log                     # Main system log (rotating, 10MB x 5)
│   └── error.log                   # Errors only (WARNING+)
│
├── device_id                       # Persistent device identifier
│
├── databases/
│   ├── kv.db                       # Key-value store
│   └── storage.db                  # General storage
│
├── browser_data/                   # Browser profile data
│
└── users/
    └── {user_id}/
        ├── recordings/
        │   └── {session_id}/
        │       └── operations.json
        │
        ├── metaflows/
        │   └── {metaflow_id}/
        │       └── metaflow.yaml
        │
        └── workflows/
            └── {workflow_id}/
                ├── workflow.yaml       # Workflow definition
                └── executions/         # Execution history (per workflow)
                    └── {execution_id}/
                        ├── result.json # Execution result (existing)
                        ├── meta.json   # Execution metadata (NEW)
                        └── log.jsonl   # Step-by-step logs (NEW)
```

### Log Separation Principle

| Log Type | Location | Content | Rotation |
|----------|----------|---------|----------|
| System logs | `~/.ami/logs/app.log` | App startup/shutdown, service status | 10MB x 5 |
| Error logs | `~/.ami/logs/error.log` | WARNING and above | 10MB x 5 |
| Workflow logs | `~/.ami/users/{user_id}/workflows/{workflow_id}/executions/{execution_id}/log.jsonl` | Per-step execution details | Per execution |

### Retention Policy

| Data Type | Retention | Cleanup |
|-----------|-----------|---------|
| System logs | 50MB total | Automatic rotation |
| Workflow executions | 60 days | On app startup |
| Cloud upload | Last 5 per workflow | Cloud-side limit |

## Key Files

- `daemon.py` - Main FastAPI application entry point
- `core/config_service.py` - Configuration management
- `core/logging_config.py` - Logging with rotation
- `services/storage_manager.py` - File storage operations
- `services/workflow_executor.py` - Workflow execution engine
- `services/workflow_history.py` - Execution history management
- `services/browser_manager.py` - Browser automation
- `services/cloud_client.py` - Cloud Backend API client

## API Endpoints

See `/docs/api/API_DESIGN_SPEC.md` for complete API specification.

All endpoints use `/api/v1/` prefix and follow RESTful conventions.

### Key Endpoint Groups

- **Browser**: `/api/v1/browser/*` - Browser lifecycle and window management
- **Recordings**: `/api/v1/recordings/*` - Recording CRUD and analysis
- **MetaFlows**: `/api/v1/metaflows/*` - MetaFlow CRUD and generation
- **Workflows**: `/api/v1/workflows/*` - Workflow CRUD and execution
- **Executions**: `/api/v1/executions/*` - Execution history, logs, feedback
- **Data Collections**: `/api/v1/data/collections/*` - Scraped data management
- **Intent Builder**: `/api/v1/intent-builder/sessions/*` - AI conversation sessions
- **Agents**: `/api/v1/agents/*` - Agent-based services (scraper-optimizer)

## Execution Flow

```
1. User triggers workflow execution
2. WorkflowExecutor.execute_workflow_async() creates task and history run
3. WorkflowHistoryManager.create_run() creates meta.json and log.jsonl
4. BaseAgent executes each step with step_progress_callback
5. step_progress_callback logs each step to log.jsonl via history.log_step()
6. On completion, update meta.json via history.update_run_status()
7. StorageManager saves result.json (existing behavior)
8. Auto-upload execution log to Cloud Backend via cloud_client.upload_execution_log()
9. Mark execution as uploaded via history.mark_as_uploaded()
```

## Auto Log Upload

Workflow execution logs are automatically uploaded to Cloud Backend after completion:
- Triggered in `WorkflowExecutor._upload_execution_log()` after status update
- Uses `CloudClient.upload_execution_log()` to POST to `/api/v1/logs/workflow`
- Fire-and-forget: upload failure doesn't affect workflow status
- Uploads: meta.json + log.jsonl + workflow.yaml + device_info

## Diagnostic Package

Users can upload diagnostic logs via the bug icon in bottom navigation:
- Endpoint: `POST /api/v1/app/diagnostic`
- Collects: system logs (last 1000 lines), recent 20 executions, device info
- Uses `CloudClient.upload_diagnostic()` to POST to Cloud Backend

## Key Data Structures

### WorkflowHistoryManager Context Tracking

The `WorkflowExecutor` tracks history context per task:
```python
_task_context: Dict[str, tuple[str, str, str]]  # task_id -> (user_id, workflow_id, execution_id)
```

This allows proper routing of history calls to the correct execution directory.
