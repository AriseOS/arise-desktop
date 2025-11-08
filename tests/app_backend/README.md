# App Backend Tests

Tests for the App Backend HTTP daemon service.

## Test Files

### Workflow Tests

Complete workflow from recording to executable YAML:

- **`1_test_recording.py`** - Record user operations with browser
- **`2_test_upload_recording.py`** - Upload operations to Cloud Backend
- **`3_test_generate_metaflow.py`** - Generate MetaFlow from user description
- **`4_test_generate_workflow.py`** - Generate workflow YAML from MetaFlow

See [WORKFLOW_TESTS.md](./WORKFLOW_TESTS.md) for detailed documentation.

### Legacy Tests (JSON-RPC over stdin/stdout)

- **`test_daemon_jsonrpc.py`** - Tests for old JSON-RPC daemon (deprecated)
- **`manual_test_daemon.sh`** - Manual testing script for JSON-RPC daemon (deprecated)

## Running Tests

### Prerequisites

1. **Start App Backend HTTP Daemon:**
   ```bash
   ./scripts/start_http_daemon.sh
   ```

2. **Start Cloud Backend (for tests 2-4):**
   ```bash
   ./scripts/start_cloud_backend.sh
   ```

3. **Set LLM API Key (for tests 3-4):**
   ```bash
   export ANTHROPIC_API_KEY=your_key
   # OR
   export OPENAI_API_KEY=your_key
   ```

### Run Tests Individually

```bash
# Test 1: Record user operations
python tests/app_backend/1_test_recording.py

# Test 2: Upload to Cloud Backend
python tests/app_backend/2_test_upload_recording.py

# Test 3: Generate MetaFlow (with custom description)
python tests/app_backend/3_test_generate_metaflow.py "Your task description"

# Test 4: Generate Workflow YAML
python tests/app_backend/4_test_generate_workflow.py
```

## Test Coverage

The HTTP daemon tests cover:

1. **Health Check** - `GET /health`
2. **List Workflows** - `GET /api/workflows`
3. **Start Recording** - `POST /api/recording/start`
4. **Stop Recording** - `POST /api/recording/stop`
5. **Generate Workflow** - `POST /api/workflow/generate`
6. **Execute Workflow** - `POST /api/workflow/execute`
7. **Get Workflow Status** - `GET /api/workflow/status/{task_id}`

## API Documentation

When daemon is running, view interactive API docs at:
- Swagger UI: http://127.0.0.1:8765/docs
- ReDoc: http://127.0.0.1:8765/redoc
