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
│   ├── clients/desktop_app/     # Desktop application (Tauri + Python daemon)
│   │   └── ami_daemon/base_app/ # BaseAgent framework implementation
│   ├── cloud_backend/           # Server-side services
│   │   └── intent_builder/      # Intent-based workflow generation
│   └── common/                  # Shared utilities
│       └── llm/                 # LLM provider abstraction
└── docs/                        # Human-readable docs (NOT for models - use CONTEXT.md instead)
```

## Key Paths

- BaseAgent: `src/clients/desktop_app/ami_daemon/base_app/`
- Intent Builder: `src/cloud_backend/intent_builder/`
- LLM Providers: `src/common/llm/`
- Desktop App: `src/clients/desktop_app/`

## Environment

- Python dependencies use **venv**: activate with `source .venv/bin/activate` before running any Python commands
- Client logs: `~/.ami/logs/app.log`
- Server logs: `~/ami-server/logs/`

## Development Commands

```bash
# Python backend (ensure venv is activated)
pip install -r requirements.txt
uvicorn src.cloud_backend.main:app --reload

# Desktop app
cd src/clients/desktop_app && npm run tauri dev

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

**Testing:**
- DO NOT automatically run tests
- Only create test scripts when explicitly requested

**Code Style:**
- English only for comments, logs, and identifiers
- Prefer clarity over cleverness
- Remove unused code aggressively
