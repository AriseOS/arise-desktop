# App Backend API Documentation

## Base URL

```
http://127.0.0.1:8765
```

## Overview

App Backend provides desktop application integration for recording, workflow generation, and execution:
1. Record user operations in browser (via CDP)
2. Upload recordings to Cloud Backend → Extract intents
3. Generate MetaFlow from Intent Memory Graph
4. Generate Workflow YAML from MetaFlow
5. Execute workflows locally

## Key Features

- **Local Storage**: All recordings, MetaFlows, and Workflows are saved locally at `~/.ami/users/{user_id}/`
- **Cloud Integration**: Communicates with Cloud Backend for AI-powered generation
- **Browser Automation**: CDP-based recording and workflow execution

## API Endpoints

### Health Check

**GET** `/health`

Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "browser_ready": true
}
```

---

## Recording APIs

### Start Recording

**POST** `/api/recording/start`

Start CDP recording session in browser.

**Request Body:**
```json
{
  "url": "https://www.example.com",
  "title": "Example Task",
  "description": "Optional description",
  "task_metadata": {
    "task_description": "User's description of what they're doing"
  }
}
```

**Response:**
```json
{
  "session_id": "session_abc123",
  "status": "recording",
  "url": "https://www.example.com"
}
```

---

### Stop Recording

**POST** `/api/recording/stop`

Stop recording and save operations to local storage.

**Response:**
```json
{
  "session_id": "session_abc123",
  "operations_count": 42,
  "local_file_path": "/Users/user/.ami/users/default_user/recordings/session_abc123/operations.json"
}
```

**Notes:**
- Operations are saved to `~/.ami/users/{user_id}/recordings/{session_id}/operations.json`
- Ready to be uploaded to Cloud Backend

---

## Recording Upload API

### Upload Recording to Cloud

**POST** `/api/recordings/upload`

Upload local recording to Cloud Backend for intent extraction.

**Request Body:**
```json
{
  "session_id": "session_abc123",
  "task_description": "Search for coffee products on Google",
  "user_id": "default_user"
}
```

**Response:**
```json
{
  "recording_id": "uuid-here",
  "status": "success"
}
```

**Notes:**
- Loads operations from local storage (`~/.ami/users/{user_id}/recordings/{session_id}/`)
- Uploads to Cloud Backend with task_description
- Cloud Backend extracts intents asynchronously and adds to user's Intent Memory Graph

---

## MetaFlow APIs

### Generate MetaFlow

**POST** `/api/metaflows/generate`

Generate MetaFlow from user's Intent Memory Graph (via Cloud Backend).

**Request Body:**
```json
{
  "task_description": "Search for coffee products on Google",
  "user_id": "default_user"
}
```

**Response:**
```json
{
  "metaflow_id": "metaflow_abc123",
  "local_path": "/Users/user/.ami/users/default_user/metaflows/metaflow_abc123/metaflow.yaml"
}
```

**Notes:**
- Calls Cloud Backend `POST /api/users/{user_id}/generate_metaflow`
- Cloud Backend filters relevant intents and generates MetaFlow
- MetaFlow YAML is saved locally to `~/.ami/users/{user_id}/metaflows/{metaflow_id}/`
- Takes 30-60 seconds (LLM processing)

---

## Workflow APIs

### Generate Workflow

**POST** `/api/workflows/generate`

Generate Workflow YAML from MetaFlow (via Cloud Backend).

**Request Body:**
```json
{
  "metaflow_id": "metaflow_abc123",
  "user_id": "default_user"
}
```

**Response:**
```json
{
  "workflow_name": "workflow_20251108_160557",
  "local_path": "/Users/user/.ami/users/default_user/workflows/workflow_20251108_160557/workflow.yaml"
}
```

**Notes:**
- Calls Cloud Backend `POST /api/metaflows/{metaflow_id}/generate_workflow`
- Cloud Backend generates Workflow YAML using LLM
- Workflow YAML is saved locally to `~/.ami/users/{user_id}/workflows/{workflow_name}/`
- Takes 30-60 seconds (LLM processing)

---

### Execute Workflow

**POST** `/api/workflow/execute`

Execute a workflow asynchronously.

**Request Body:**
```json
{
  "workflow_name": "workflow_20251108_160557",
  "user_id": "default_user"
}
```

**Response:**
```json
{
  "task_id": "task_xyz789",
  "status": "started"
}
```

**Notes:**
- Executes workflow in background
- Use `/api/workflow/status/{task_id}` to track progress

---

### Get Workflow Status

**GET** `/api/workflow/status/{task_id}`

Get workflow execution status.

**Path Parameters:**
- `task_id` - Task ID from execute endpoint

**Response:**
```json
{
  "task_id": "task_xyz789",
  "status": "running",
  "progress": 50,
  "current_step": 3,
  "total_steps": 6,
  "message": "Executing step 3: Click button",
  "result": null,
  "error": null
}
```

**Status Values:**
- `pending` - Waiting to start
- `running` - Currently executing
- `completed` - Successfully finished
- `failed` - Execution failed

---

### List Workflows

**GET** `/api/workflows`

List all workflows for a user.

**Query Parameters:**
- `user_id` (optional, default: "default_user")

**Response:**
```json
{
  "workflows": [
    "workflow_20251108_160557",
    "search_coffee_workflow"
  ]
}
```

---

## Complete Flow Example

### 1. Start Recording

```bash
curl -X POST http://127.0.0.1:8765/api/recording/start \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.google.com",
    "title": "Search Coffee",
    "task_metadata": {
      "task_description": "Search for coffee products on Google"
    }
  }'
```

### 2. Perform Actions in Browser

User performs actions in the controlled browser...

### 3. Stop Recording

```bash
curl -X POST http://127.0.0.1:8765/api/recording/stop
```

Response:
```json
{
  "session_id": "session_abc123",
  "operations_count": 16,
  "local_file_path": "~/.ami/users/default_user/recordings/session_abc123/operations.json"
}
```

### 4. Upload to Cloud Backend

```bash
curl -X POST http://127.0.0.1:8765/api/recordings/upload \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_abc123",
    "task_description": "Search for coffee products on Google"
  }'
```

Wait a few seconds for intent extraction to complete on Cloud Backend...

### 5. Generate MetaFlow

```bash
curl -X POST http://127.0.0.1:8765/api/metaflows/generate \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Search for coffee products on Google"
  }'
```

Response:
```json
{
  "metaflow_id": "metaflow_abc123",
  "local_path": "~/.ami/users/default_user/metaflows/metaflow_abc123/metaflow.yaml"
}
```

### 6. Generate Workflow

```bash
curl -X POST http://127.0.0.1:8765/api/workflows/generate \
  -H "Content-Type: application/json" \
  -d '{
    "metaflow_id": "metaflow_abc123"
  }'
```

Response:
```json
{
  "workflow_name": "workflow_20251108_160557",
  "local_path": "~/.ami/users/default_user/workflows/workflow_20251108_160557/workflow.yaml"
}
```

### 7. Execute Workflow

```bash
curl -X POST http://127.0.0.1:8765/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_name": "workflow_20251108_160557"
  }'
```

### 8. Check Status

```bash
curl http://127.0.0.1:8765/api/workflow/status/task_xyz789
```

---

## Local Storage Structure

```
~/.ami/users/{user_id}/
├── recordings/              # Browser recordings (CDP)
│   └── {session_id}/
│       └── operations.json
├── metaflows/              # Downloaded MetaFlows
│   └── {metaflow_id}/
│       ├── metaflow.yaml
│       └── task_description.txt
└── workflows/              # Downloaded Workflows
    └── {workflow_name}/
        ├── workflow.yaml
        └── executions/     # Execution history
            └── {task_id}/
                └── result.json
```

---

## Architecture

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│  Desktop App    │         │  App Backend    │         │  Cloud Backend  │
│  (Browser UI)   │         │  (Local Daemon) │         │  (AI Service)   │
└─────────────────┘         └─────────────────┘         └─────────────────┘
        │                           │                           │
        │  1. Start Recording       │                           │
        ├──────────────────────────>│                           │
        │                           │                           │
        │  2. CDP Events            │                           │
        ├──────────────────────────>│                           │
        │                           │                           │
        │  3. Stop Recording        │                           │
        ├──────────────────────────>│                           │
        │                           │  Save to ~/.ami/          │
        │                           │                           │
        │  4. Upload Recording      │                           │
        ├──────────────────────────>│  Upload operations        │
        │                           ├──────────────────────────>│
        │                           │                           │  Extract intents
        │                           │                           │  (async)
        │                           │                           │
        │  5. Generate MetaFlow     │                           │
        ├──────────────────────────>│  Request MetaFlow         │
        │                           ├──────────────────────────>│
        │                           │                           │  Filter intents
        │                           │  MetaFlow YAML            │  Generate MetaFlow
        │                           │<──────────────────────────┤
        │                           │  Save to ~/.ami/          │
        │                           │                           │
        │  6. Generate Workflow     │                           │
        ├──────────────────────────>│  Request Workflow         │
        │                           ├──────────────────────────>│
        │                           │                           │  Generate Workflow
        │                           │  Workflow YAML            │  (LLM)
        │                           │<──────────────────────────┤
        │                           │  Save to ~/.ami/          │
        │                           │                           │
        │  7. Execute Workflow      │                           │
        ├──────────────────────────>│                           │
        │                           │  Execute locally          │
        │                           │  (Browser automation)     │
```

---

## Interactive API Documentation

When daemon is running, view interactive API docs at:
- **Swagger UI**: http://127.0.0.1:8765/docs
- **ReDoc**: http://127.0.0.1:8765/redoc
