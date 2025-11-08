# Cloud Backend Manual Tests

Manual test scripts for Cloud Backend API endpoints using real Allegro coffee collection data.

**Important**: These tests simulate a remote client scenario where Cloud Backend runs on a server,
and test scripts run on a client machine. All generated files (MetaFlows, Workflows) are downloaded
via HTTP to the local `downloads/` directory.

## Prerequisites

1. Cloud Backend running on `http://localhost:9000`
2. LLM API key configured (`ANTHROPIC_API_KEY` or `OPENAI_API_KEY`)

## Test Data

Tests use real user operations from `tests/fixtures/test_data/coffee_allegro/fixtures/user_operations.json`:
- **Task**: Collect coffee product information from Allegro including product name, price, and sales count
- **Operations**: 16 real browser operations (navigate, click, scroll, extract data)
- **Source**: Allegro.pl coffee category page

## Test Scripts

### 1. Upload Recording

```bash
python tests/cloud_backend/manual/1_test_upload_recording.py
```

Uploads real Allegro coffee operations to Cloud Backend. Backend will:
- Save recording to `~/.ami/users/default_user/recordings/{recording_id}/`
- Extract intents in background using user's task description
- Add intents to user's Intent Memory Graph at `~/.ami/users/default_user/intent_graph.json`

**What's uploaded:**
- Task description: "Collect coffee product information from Allegro including product name, price, and sales count"
- 16 operations from real Allegro browsing session

### 2. Generate MetaFlow

```bash
# Use default task description (Allegro coffee collection)
python tests/cloud_backend/manual/2_test_generate_metaflow.py

# Or provide custom task description
python tests/cloud_backend/manual/2_test_generate_metaflow.py "Collect coffee products with prices"
```

Generates MetaFlow from user's Intent Memory Graph based on task description, then downloads to local.

**What happens:**
1. Cloud Backend generates MetaFlow on server (filters relevant intents from cumulative Intent Graph)
2. Test script downloads MetaFlow YAML via HTTP
3. Saves to `tests/cloud_backend/manual/downloads/{metaflow_id}/metaflow.yaml`

### 3. Generate Workflow

```bash
python tests/cloud_backend/manual/3_test_generate_workflow.py
```

Generates Workflow YAML from MetaFlow using LLM, then downloads to local.

**What happens:**
1. Cloud Backend generates Workflow on server (uses LLM to convert MetaFlow to Workflow)
2. Test script downloads Workflow YAML via HTTP
3. Saves to `tests/cloud_backend/manual/downloads/{workflow_name}/workflow.yaml`

### 4. View Downloaded Workflows

```bash
python tests/cloud_backend/manual/4_test_download_workflow.py
```

View workflows that have been downloaded to local directory. Since workflows are automatically downloaded in test 3, this script just helps you inspect the local files.

### 5. List Workflows

```bash
python tests/cloud_backend/manual/5_test_list_workflows.py
```

Lists all workflows for a user.

## Storage Structure

### Server-side (Cloud Backend)

```
~/.ami/users/{user_id}/
├── intent_graph.json          # User's Intent Memory Graph (cumulative)
├── recordings/                # User operations
│   └── {recording_id}/
│       └── operations.json
├── metaflows/                 # Generated MetaFlows
│   └── {metaflow_id}/
│       ├── metaflow.yaml
│       └── task_description.txt
└── workflows/                 # Generated Workflows
    └── {workflow_name}/
        ├── workflow.yaml
        └── metaflow.yaml
```

### Client-side (Test Scripts)

```
tests/cloud_backend/manual/
└── downloads/                 # Downloaded files
    ├── {metaflow_id}/
    │   ├── metaflow.yaml
    │   └── task_description.txt
    └── {workflow_name}/
        └── workflow.yaml
```

## Notes

- **Remote client simulation**: Tests simulate Cloud Backend running on server, test scripts running on client
- **HTTP downloads**: All generated files (MetaFlows, Workflows) are downloaded via HTTP to local `downloads/` directory
- **Intent Graph is cumulative**: Each recording adds more intents to the user's graph (server-side)
- **MetaFlow generation**: Filters relevant intents from the graph based on task description
- **LLM operations**: Intent extraction, MetaFlow generation, Workflow generation take 30-120 seconds
