# Cloud Backend

Server-side services for Ami platform. Handles workflow generation, intent extraction, and centralized data storage.

## Directories

- `intent_builder/` - Intent-based workflow generation system
- `api/` - REST API endpoints (auth, etc.)
- `core/` - Core services (config, logging, middleware)
- `database/` - SQLAlchemy models
- `services/` - Business logic services
- `models/` - Data models

## Key Files

- `main.py` - FastAPI application entry point with all API routes
- `core/logging_config.py` - Structured JSON logging with context injection
- `core/middleware.py` - Request context middleware for logging

## API Endpoints

See `/docs/api/API_DESIGN_SPEC.md` Section 4 for complete Cloud Backend API specification.

All endpoints use `/api/v1/` prefix and follow RESTful conventions.

### Key Endpoint Groups

- **Auth**: `/api/v1/auth/*` - User login/register
- **Recordings**: `/api/v1/recordings/*` - Recording upload, analysis, MetaFlow generation
- **MetaFlows**: `/api/v1/metaflows/*` - MetaFlow CRUD and Workflow generation
- **Workflows**: `/api/v1/workflows/*` - Workflow CRUD, download, metadata, files
- **Executions**: `/api/v1/executions/*` - Execution reporting
- **Logs**: `/api/v1/logs/*` - Workflow log and diagnostic upload
- **Intent Builder**: `/api/v1/intent-builder/sessions/*` - AI conversation sessions (SSE)

## Logging System

### Structured JSON Logging

All logs use structured JSON format with request context:
```json
{
  "timestamp": "2025-01-15T10:30:00.123Z",
  "level": "INFO",
  "service": "cloud_backend",
  "module": "intent_builder",
  "request_id": "req_abc123",
  "user_id": "key_abc12345...",
  "message": "Generated workflow successfully",
  "extra": {"steps_count": 5}
}
```

### Request Context Injection

`RequestContextMiddleware` automatically injects:
- `request_id`: Generated per request for tracing
- `user_id`: Extracted from X-Ami-API-Key header
- `workflow_id`: Extracted from URL path
- `session_id`: Extracted from URL path

### Log Storage

Uploaded logs are stored in:
```
{storage_base}/users/{user_id}/
├── workflow_logs/{workflow_id}/{run_id}.json
└── diagnostics/{diagnostic_id}.json
```

### Loki Integration

Optional Loki integration via `logging.loki_url` config:
- Direct push using `python-logging-loki`
- Or file-based collection via Promtail

See `deploy/logging/` for Loki + Grafana deployment configuration.

## Data Flow

```
User Recording (with DOM snapshots) → Cloud Backend Storage
    ↓
intent_builder/extractors → Intent Graph
    ↓
User Query → intent_builder/generators → Workflow YAML
    ↓
[Background] Script Pre-generation → Workflow Directory
```

### Recording with DOM Snapshots

Recordings can include DOM snapshots captured during navigation:
```
recordings/{recording_id}/
├── operations.json      # User operations
├── metadata.json        # Workflow association
└── dom_snapshots/       # DOM captured at each URL
    ├── {url_hash_1}.json
    └── {url_hash_2}.json
```

### Script Pre-generation

After workflow generation, scripts are pre-generated in the background:
```
workflows/{workflow_id}/
├── workflow.yaml
├── metadata.json        # Includes script_pregeneration status
├── dom_snapshots/       # DOM snapshots from workflow execution
│   ├── url_index.json   # Maps step_id -> DOM file
│   └── {url_hash}.json  # Wrapped format: {"url":..., "step_id":..., "dom":{...}}
└── {step_id}/           # Scripts stored directly in step directory
    ├── find_element.py  # Browser agent script
    ├── task.json        # Browser task definition
    ├── extraction_script.py  # Scraper agent script
    ├── dom_tools.py     # Scraper utilities
    └── requirement.json # Scraper requirements
```

**Note**: `dom_data.json` is NOT saved permanently in step directories. During
modification sessions, it's dynamically copied from `dom_snapshots/` using the
`step_id` mapping in `url_index.json`. This ensures scripts always use the
latest DOM captured during workflow execution.

## See Also

- `intent_builder/CONTEXT.md` for workflow generation details
