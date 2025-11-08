# App Backend Manual Tests

Manual test scripts for App Backend API endpoints.

These tests demonstrate the complete flow from browser recording to workflow execution.

## Prerequisites

1. **Start App Backend:**
   ```bash
   python src/app_backend/daemon.py
   ```

2. **Start Cloud Backend (for tests 1-3):**
   ```bash
   ./scripts/start_cloud_backend.sh
   ```

3. **Set LLM API Key (for tests 2-3):**
   ```bash
   export ANTHROPIC_API_KEY=your_key
   # OR
   export OPENAI_API_KEY=your_key
   ```

## Test Scripts

### Test 0: Record User Operations

```bash
python tests/app_backend/manual/0_test_recording.py
```

**What it does:**
- Opens browser with CDP enabled
- User performs actions (e.g., search on Google)
- Records all operations
- Saves to `~/.ami/users/default_user/recordings/{session_id}/`

**Output:**
- Session ID
- Number of operations recorded
- Local file path

---

### Test 1: Upload Recording to Cloud Backend

```bash
# Use latest recording
python tests/app_backend/manual/1_test_upload.py

# Or specify session_id and task description
python tests/app_backend/manual/1_test_upload.py session_abc123 "Search for coffee on Google"
```

**What it does:**
- Loads recording from local storage
- Uploads to Cloud Backend with task description
- Cloud Backend extracts intents asynchronously

**Output:**
- Recording ID from Cloud Backend
- Confirmation that intent extraction started

**Note:** Wait a few seconds for intent extraction to complete before running test 2.

---

### Test 2: Generate MetaFlow

```bash
# Use default task description
python tests/app_backend/manual/2_test_generate_metaflow.py

# Or provide custom task description
python tests/app_backend/manual/2_test_generate_metaflow.py "Search for coffee on Google"
```

**What it does:**
- Calls Cloud Backend to generate MetaFlow
- Cloud Backend filters relevant intents from Intent Memory Graph
- Downloads MetaFlow YAML and saves locally

**Output:**
- MetaFlow ID
- Local file path: `~/.ami/users/default_user/metaflows/{metaflow_id}/metaflow.yaml`

**Duration:** 30-60 seconds (LLM processing)

---

### Test 3: Generate Workflow

```bash
# Use latest MetaFlow
python tests/app_backend/manual/3_test_generate_workflow.py

# Or specify MetaFlow ID
python tests/app_backend/manual/3_test_generate_workflow.py metaflow_abc123
```

**What it does:**
- Calls Cloud Backend to generate Workflow from MetaFlow
- Downloads Workflow YAML and saves locally
- Displays preview of generated workflow

**Output:**
- Workflow name
- Local file path: `~/.ami/users/default_user/workflows/{workflow_name}/workflow.yaml`
- Preview of first 10 lines

**Duration:** 30-60 seconds (LLM processing)

---

### Test 4: Execute Workflow

```bash
# Use latest workflow
python tests/app_backend/manual/4_test_execute.py

# Or specify workflow name
python tests/app_backend/manual/4_test_execute.py workflow_20251108_160557
```

**What it does:**
- Loads workflow from local storage
- Executes workflow using browser automation
- Monitors progress in real-time

**Output:**
- Task ID
- Real-time progress updates
- Final execution result

**Note:** Browser window will open and automate the workflow steps.

---

## Complete Flow Example

### Step-by-Step Execution

```bash
# 1. Record user operations
python tests/app_backend/manual/0_test_recording.py
# → Perform actions in browser, press ENTER when done
# → Output: session_abc123

# 2. Upload to Cloud Backend
python tests/app_backend/manual/1_test_upload.py session_abc123 "Search for coffee on Google"
# → Wait a few seconds for intent extraction
# → Output: recording_id

# 3. Generate MetaFlow
python tests/app_backend/manual/2_test_generate_metaflow.py "Search for coffee on Google"
# → Wait 30-60 seconds
# → Output: metaflow_abc123

# 4. Generate Workflow
python tests/app_backend/manual/3_test_generate_workflow.py metaflow_abc123
# → Wait 30-60 seconds
# → Output: workflow_20251108_160557

# 5. Execute Workflow
python tests/app_backend/manual/4_test_execute.py workflow_20251108_160557
# → Watch browser automation in real-time
# → Output: execution result
```

---

## Storage Structure

All data is stored locally at:

```
~/.ami/users/default_user/
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

## API Endpoints Tested

| Test | API Endpoint | Method | Description |
|------|-------------|--------|-------------|
| 0 | `/api/recording/start` | POST | Start CDP recording |
| 0 | `/api/recording/stop` | POST | Stop and save recording |
| 1 | `/api/recordings/upload` | POST | Upload to Cloud Backend |
| 2 | `/api/metaflows/generate` | POST | Generate MetaFlow |
| 3 | `/api/workflows/generate` | POST | Generate Workflow |
| 4 | `/api/workflow/execute` | POST | Execute workflow |
| 4 | `/api/workflow/status/{task_id}` | GET | Monitor execution |

---

## Notes

- **Recording (Test 0):** All operations are recorded locally first
- **Upload (Test 1):** Intent extraction happens asynchronously on Cloud Backend
- **MetaFlow (Test 2):** Generated from cumulative Intent Memory Graph
- **Workflow (Test 3):** Executable YAML generated from MetaFlow
- **Execution (Test 4):** Runs locally using browser automation

---

## Troubleshooting

### Cannot connect to App Backend
```bash
# Check if daemon is running
curl http://127.0.0.1:8765/health

# Start daemon
python src/app_backend/daemon.py
```

### Cannot connect to Cloud Backend
```bash
# Check if Cloud Backend is running
curl http://localhost:9000/health

# Start Cloud Backend
./scripts/start_cloud_backend.sh
```

### Browser not opening
- Check App Backend logs
- Verify CDP recorder is initialized
- Try restarting App Backend daemon

### LLM timeout
- Increase timeout in test scripts
- Check LLM API key is set
- Check internet connection
