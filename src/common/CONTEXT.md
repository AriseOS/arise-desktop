# src/common/

Shared utilities used by cloud backend modules.

## Directories

- `llm/` - LLM provider abstraction (Anthropic, OpenAI, Claude Agent SDK)
- `script_generation/` - Reusable script generators for browser/scraper workflows
- `agent/` - Agent utilities
- `memory/` - Memory utilities

## Key Files

- `config_service.py` - Configuration loading and management
- `resource_types.py` - Resource type definitions
- `timestamp_utils.py` - Timestamp utilities

## script_generation/

Reusable script generation module used by:
- **Cloud Backend** (Intent Builder) - pre-generation during workflow creation

See `script_generation/CONTEXT.md` for details.
