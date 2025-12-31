# App Backend API Reference

Base URL: `http://localhost:23432`

## Overview

App Backend (ami_daemon) provides REST API for the desktop application, handling browser automation, workflow execution, recording, and local data management.

## Endpoints

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |

---

### Browser Management

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/browser/start` | Start browser instance |
| POST | `/api/browser/stop` | Stop browser instance |
| GET | `/api/browser/status` | Get browser status |
| GET | `/api/browser/window/layout` | Get window layout |
| POST | `/api/browser/window/update` | Update window position/size |
| POST | `/api/browser/window/arrange` | Auto-arrange windows |

---

### Dashboard

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dashboard` | Get dashboard summary data |

---

### Recording

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/recording/start` | Start recording session |
| POST | `/api/recording/stop` | Stop recording session |
| POST | `/api/recording/analyze` | Analyze recording operations |
| POST | `/api/recording/update-metadata` | Update recording metadata |
| GET | `/api/recordings` | List recordings (deprecated) |
| GET | `/api/recordings/list` | List recordings |
| GET | `/api/recordings/{session_id}` | Get recording detail |
| DELETE | `/api/recordings/{session_id}` | Delete recording |
| POST | `/api/recordings/upload` | Upload recording to cloud |

---

### MetaFlow

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/metaflows/generate` | Generate MetaFlow from intent |
| POST | `/api/metaflows/from-recording` | Generate MetaFlow from recording |
| GET | `/api/metaflows` | List MetaFlows |
| GET | `/api/metaflows/{metaflow_id}` | Get MetaFlow detail |
| PUT | `/api/metaflows/{metaflow_id}` | Update MetaFlow |

---

### Workflow

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/workflows/from-metaflow` | Generate Workflow from MetaFlow |
| POST | `/api/workflows/generate` | Generate Workflow directly |
| GET | `/api/workflows` | List workflows (cloud + local merged) |
| GET | `/api/workflows/{workflow_id}/detail` | Get workflow detail |
| PUT | `/api/workflows/{workflow_id}` | Update workflow |
| DELETE | `/api/workflows/{workflow_id}` | Delete workflow |

---

### Workflow Execution

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/workflow/execute` | Execute workflow async |
| GET | `/api/workflow/status/{task_id}` | Get execution status |
| WS | `/ws/workflow/{task_id}` | WebSocket for real-time progress |

---

### Workflow History

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/workflow-history` | List execution history |
| GET | `/api/workflow-history/{run_id}` | Get run detail with logs |
| GET | `/api/workflow-history/{run_id}/for-upload` | Get run data for cloud upload |

---

### Data Collections

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/data/collections` | List data collections |
| GET | `/api/data/collections/{collection_name}` | Get collection detail |
| DELETE | `/api/data/collections/{collection_name}` | Delete collection |
| GET | `/api/data/collections/{collection_name}/export` | Export collection data |

---

### Intent Builder (Proxy to Cloud)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/intent-builder/start` | Start Intent Builder session |
| GET | `/api/intent-builder/{session_id}/stream` | Stream initial response (SSE) |
| POST | `/api/intent-builder/{session_id}/chat` | Send message and stream (SSE) |
| GET | `/api/intent-builder/{session_id}/state` | Get session state |
| DELETE | `/api/intent-builder/{session_id}` | Close session |

---

### Scraper Optimization

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/scraper-optimization/load-workspace` | Load optimization workspace |
| POST | `/api/scraper-optimization/chat` | Chat with Claude for optimization |

---

### Workflow Feedback

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/workflow-feedback` | Submit workflow execution feedback |

---

## Notes

### Endpoint Naming Issues (TODO)

Current inconsistencies to review:
1. `/api/workflow/execute` vs `/api/workflows/...` - singular vs plural
2. `/api/workflow-history` - hyphen naming
3. `/api/recording/start` vs `/api/recordings/list` - singular vs plural
4. No API versioning (e.g., `/api/v1/...`)

### Authentication

Most endpoints require `user_id` parameter or header for user identification.

### WebSocket

Real-time workflow progress uses WebSocket at `/ws/workflow/{task_id}`.
