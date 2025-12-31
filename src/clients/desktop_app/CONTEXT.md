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

## Key Frontend Pages

- `src/pages/ExecutionHistoryPage.jsx` - Workflow execution history viewer
- `src/pages/QuickStartPage.jsx` - Recording start page
- `src/pages/MyWorkflowsPage.jsx` - Workflow list and management

## Logging & Diagnostics

### Execution History UI

`ExecutionHistoryPage` displays workflow execution history:
- List of all executions with status filter
- Detail modal showing step logs
- Manual log upload button

### Diagnostic Upload

Bug icon in bottom navigation triggers diagnostic upload:
- Calls `api.uploadDiagnostic()` → `POST /api/v1/app/diagnostic`
- Collects system logs and recent executions
- Uploaded to Cloud Backend for debugging

## See Also

- `ami_daemon/CONTEXT.md` for backend daemon details
- `ami_daemon/base_app/CONTEXT.md` for BaseAgent details
