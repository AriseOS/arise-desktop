# App Backend

Local Execution Engine and Cloud Proxy for Ami system.

## Overview

App Backend runs on the user's computer and provides:

1. **Recording Control** - Capture user operations via Extension
2. **Execution Control** - Run workflows locally using BaseAgent
3. **Cloud Proxy** - Unified Cloud Backend API access
4. **Local Storage** - Workflow and execution result caching

## Quick Start

### Install Dependencies

```bash
cd src/app_backend
pip install -r requirements.txt
```

### Run Server

```bash
python main.py
```

Server starts on `http://localhost:8000`

### Configuration

Edit `config/app-backend.yaml` or use environment variables:

```bash
export APP_BACKEND_SERVER_PORT=8001
export APP_BACKEND_CLOUD_API_URL=http://localhost:9000
```

## API Endpoints

### Recording

```
POST /api/recording/start          # Start recording session
POST /api/recording/operation      # Add operation
POST /api/recording/stop           # Stop and upload
POST /api/recording/generate       # Generate workflow
```

### Execution

```
POST /api/workflows/{name}/execute # Execute workflow
GET  /api/workflows/tasks/{id}/status  # Get task status
GET  /api/workflows                # List workflows
GET  /api/workflows/{name}/results # Get execution history
```

### WebSocket

```
ws://localhost:8000/ws/recording   # Recording events
ws://localhost:8000/ws/execution   # Execution progress
```

### Health Check

```
GET /health
```

## Development

See `docs/platform/app_backend_design.md` for detailed design.

## Storage Structure

```
~/.ami/
├── users/{user_id}/
│   ├── workflows/              # Workflow YAML cache
│   ├── recordings/             # Recording data
│   └── cache/
└── logs/
    └── app-backend.log
```
