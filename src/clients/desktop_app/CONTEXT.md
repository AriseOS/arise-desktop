# src/clients/desktop_app/

Desktop application built with Tauri (Rust + TypeScript) and Python daemon.

## Directories

- `src/` - Frontend source (TypeScript/React)
- `src-tauri/` - Tauri backend (Rust)
- `ami_daemon/` - Python daemon with BaseAgent runtime

## Architecture

```
Tauri Frontend (React) ←→ Tauri Backend (Rust) ←→ ami_daemon (Python)
                                                       ↓
                                                  BaseAgent
```

## See Also

- `ami_daemon/base_app/CONTEXT.md` for BaseAgent details
