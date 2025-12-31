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
- `src/pages/RecordingPage.jsx` - Recording page with real-time operation feedback
- `src/pages/MyWorkflowsPage.jsx` - Workflow list and management

### RecordingPage Real-time Feedback

`RecordingPage` displays captured operations in real-time during recording:
- Polls `GET /api/v1/recordings/current/operations` every 500ms
- Shows operation type (click, input, navigate, etc.) with icons
- Displays element text, input values, and URLs
- Auto-scrolls to latest operation

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
