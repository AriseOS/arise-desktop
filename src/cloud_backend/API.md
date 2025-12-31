# Cloud Backend API Reference

Base URL: `https://api.ariseos.com` (Production) / `http://localhost:8000` (Development)

## Overview

Cloud Backend provides server-side services for the Ami platform, including authentication, workflow generation, intent extraction, and resource synchronization.

## Authentication

Most endpoints require `X-Ami-API-Key` header for authentication.

## Endpoints

### Health & Root

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/` | Root path |

---

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/login` | User login (username/password) |
| POST | `/api/auth/register` | User registration |

---

### Recordings

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/recordings/upload` | Upload recording, add intents to graph |
| POST | `/api/analyze_recording` | Analyze recording operations with AI |
| GET | `/api/recordings` | List all recordings for user |
| GET | `/api/recordings/{recording_id}` | Get recording detail |

---

### MetaFlow Generation

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/users/{user_id}/generate_metaflow` | Generate MetaFlow from Intent Graph |
| POST | `/api/recordings/{recording_id}/generate_metaflow` | Generate MetaFlow from recording |

---

### MetaFlows

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/metaflows` | List all MetaFlows for user |
| GET | `/api/metaflows/{metaflow_id}` | Get MetaFlow detail |
| PUT | `/api/metaflows/{metaflow_id}` | Update MetaFlow YAML |

---

### Workflow Generation & Management

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/metaflows/{metaflow_id}/generate_workflow` | Generate Workflow from MetaFlow |
| GET | `/api/workflows` | List all Workflows for user |
| GET | `/api/users/{user_id}/workflows` | List Workflows (RESTful style) |
| GET | `/api/workflows/{workflow_id}` | Get Workflow detail |
| PUT | `/api/workflows/{workflow_id}` | Update Workflow YAML |
| GET | `/api/workflows/{workflow_id}/download` | Download Workflow YAML |
| DELETE | `/api/workflows/{workflow_id}` | Delete Workflow |

---

### Workflow Resource Sync

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/workflows/{workflow_id}/metadata` | Get workflow metadata |
| PUT | `/api/workflows/{workflow_id}/metadata` | Save workflow metadata |
| GET | `/api/workflows/{workflow_id}/files` | Get workflow file |
| PUT | `/api/workflows/{workflow_id}/files` | Save workflow file |

---

### Executions

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/executions/report` | Report execution statistics |

---

### Intent Builder Agent

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/intent-builder/start` | Start Intent Builder session |
| GET | `/api/intent-builder/{session_id}/stream` | Stream initial response (SSE) |
| POST | `/api/intent-builder/{session_id}/chat` | Send message and stream (SSE) |
| GET | `/api/intent-builder/{session_id}/state` | Get session state |
| GET | `/api/intent-builder/sessions/{session_id}/status` | Get session status |
| DELETE | `/api/intent-builder/{session_id}` | Close session |

---

## Planned Endpoints (TODO)

### Workflow Execution Logs

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/executions/logs` | Upload workflow execution logs |
| GET | `/api/executions/logs` | Query execution logs (via Loki) |

### App Logs

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/logs/app` | Upload app system logs |

---

## Notes

### Endpoint Naming Issues (TODO)

Current inconsistencies to review:
1. `/api/users/{user_id}/workflows` vs `/api/workflows` - duplicate functionality
2. `/api/analyze_recording` vs `/api/recordings/...` - inconsistent nesting
3. `/api/users/{user_id}/generate_metaflow` - action in path, not RESTful
4. No API versioning (e.g., `/api/v1/...`)

### SSE Streaming

Intent Builder endpoints use Server-Sent Events (SSE) for streaming responses.

### Storage

- Recordings and workflows stored in cloud storage
- Metadata stored in PostgreSQL
- Execution logs to be stored in Loki (planned)
