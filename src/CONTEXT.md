# src/

All source code for Ami platform.

## Directories

- `clients/` - Client applications (desktop app)
- `cloud_backend/` - Server-side services (API, intent builder, workflow generation)
- `common/` - Shared utilities (LLM providers, config)

## Architecture

```
User Request → cloud_backend (workflow generation)
                    ↓
              Generated Workflow
                    ↓
              clients/desktop_app/ami_daemon/base_app (execution)
```

## Import Patterns

```python
from src.common.llm import AnthropicProvider
from src.cloud_backend.intent_builder import IntentExtractor
```
