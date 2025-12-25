# src/cloud_backend/

Server-side services for Ami platform. Handles workflow generation, intent extraction, and API endpoints.

## Directories

- `intent_builder/` - Intent-based workflow generation system
- `api/` - REST API endpoints (auth, etc.)
- `core/` - Core services (config)
- `database/` - SQLAlchemy models
- `services/` - Business logic services
- `models/` - Data models

## Key Files

- `main.py` - FastAPI application entry point

## Data Flow

```
User Recording → intent_builder/extractors → Intent Graph
User Query → intent_builder/generators → Workflow YAML
```

## See Also

- `intent_builder/CONTEXT.md` for workflow generation details
