# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Fractal Documentation System

**Core Principle**: Documentation lives with code, forming a fractal structure where each level describes its own scope.

### Documentation Rules

**File Naming:**
- Each code directory MAY have a `CONTEXT.md` file describing that directory's purpose, structure, and key concepts
- `CONTEXT.md` is the context documentation for that directory - models should read it first

**Before Modifying Code:**
1. Check if `CONTEXT.md` exists in the target directory
2. Read `CONTEXT.md` to understand context, patterns, and constraints
3. Proceed with code changes

**After Modifying Code:**
1. Update the `CONTEXT.md` in the same directory to reflect changes
2. If changes affect parent directory's scope, update parent's `CONTEXT.md`
3. NEVER create new documentation files - only update existing `CONTEXT.md` files
4. Keep documentation concise - prefer code references over prose

**Documentation Content Guidelines:**
- Focus on "what" and "why", not "how to use"
- List key files/directories with one-line descriptions
- Document patterns, constraints, and architectural decisions
- Reference child `CONTEXT.md` files for details, don't duplicate
- Maximum ~200 lines per `CONTEXT.md` to avoid context exhaustion

**What NOT to Document:**
- Installation/setup instructions (that's for humans)
- API usage examples (code is self-documenting)
- Changelog/history (use git)
- TODOs (use issue tracker)

## Project Structure

```
Ami/
├── src/
│   ├── cloud_backend/           # FastAPI server (Memory-as-a-Service + Auth proxy)
│   │   ├── api/                 # Routes, schemas, errors
│   │   ├── core/                # Config, rate limiting, middleware
│   │   ├── services/            # Sub2API client, storage
│   │   └── config/              # cloud-backend.yaml
│   └── common/                  # Shared utilities
│       ├── memory/              # Memory system (SurrealDB graph store)
│       └── llm/                 # LLM provider abstraction
├── web/                         # Vue 3 + TypeScript management frontend
└── deploy/                      # Docker Compose, Caddy, SurrealDB configs
```

## Key Paths

- Cloud Backend: `src/cloud_backend/`
- Memory System: `src/common/memory/`
- LLM Providers: `src/common/llm/`
- Config: `src/cloud_backend/config/cloud-backend.yaml`

## Environment

- Python dependencies use **venv**: activate with `source .venv/bin/activate` before running any Python commands
- Server logs: `~/ami-server/logs/`

## Debugging Tools

- **`scripts/parse_task_log.py`** — Parses agent task execution logs (`~/.ami/logs/app.log`) to extract key events, useful for analyzing how an agent completed a task. Run `python scripts/parse_task_log.py` (auto-detects latest task) or `--task-id <id>` for a specific task.

## Development Commands

```bash
# Python backend (ensure venv is activated)
pip install -e ".[cloud,memory]"
./scripts/start_cloud_backend.sh

# Code quality
black . --line-length 88
isort . --profile black
```

## Claude Code Work Mode

**Minimalist Approach:**
- Simplest solution that meets requirements
- No over-engineering or premature optimization
- No backward compatibility unless explicitly requested

**Fail-Fast Philosophy ("Let It Crash"):**
- Never mock data or interfaces in production code
- Problems should fail immediately and loudly
- Avoid defensive fallbacks that hide issues
- Prefer explicit errors over silent degradation
- Examples:
  - ✅ `raise RuntimeError("WorkingDirectoryManager required")`
  - ❌ `workspace = fallback_path or default_path or global_path`
  - ✅ `if not api_key: raise ValueError("API key required")`
  - ❌ `api_key = provided_key or env_key or mock_key or "default"`

**Implementation Quality:**
- Do NOT consider backward compatibility - just implement the right solution
- Do NOT mock data or interfaces - implement real functionality
- Do NOT add fallback logic - fail explicitly when requirements are not met
- Do NOT skimp on tokens - read all relevant context thoroughly
- Every feature must be fully implemented, not partially or with stubs
- Re-read design documents when context is lost or when crossing module boundaries
- Read all related context code before starting implementation of any feature

**Testing:**
- DO NOT automatically run tests
- Only create test scripts when explicitly requested

**Task Completion Checklist:**
- After completing a major task, verify the feature is fully implemented
- After completing a major task, check for bugs in the implementation

**Code Style:**
- English only for comments, logs, and identifiers
- Prefer clarity over cleverness
- Remove unused code aggressively
