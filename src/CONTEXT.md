# src/

All source code for Ami cloud backend platform.

## Directories

- `cloud_backend/` - Server-side services (API, intent builder, workflow generation)
- `common/` - Shared utilities (LLM providers, config)

## Import Patterns

```python
from src.common.llm import AnthropicProvider
from src.cloud_backend.intent_builder import IntentExtractor
```
