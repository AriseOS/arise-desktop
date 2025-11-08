# Ami Tests

Test directory organized by system architecture (v2.0)

---

## 📂 Directory Structure

```
tests/
├── cloud_backend/          # Cloud Backend tests
│   ├── test_storage_service.py
│   ├── test_workflow_generation.py
│   └── test_api_endpoints.py
│
├── app_backend/            # App Backend HTTP daemon tests
│   ├── test_http_daemon.py          # Python HTTP API tests
│   ├── test_http_daemon.sh          # Shell HTTP API tests
│   ├── test_daemon_jsonrpc.py       # Legacy JSON-RPC tests
│   ├── manual_test_daemon.sh        # Legacy manual tests
│   └── README.md                    # App Backend test docs
│
├── integration/            # Integration tests
│   ├── test_integration.py         # Full system integration
│   ├── intent_builder/             # Intent Builder tests
│   └── workflow/                   # Workflow execution tests
│
├── unit/                   # Unit tests for core modules
│   ├── baseagent/         # BaseAgent framework tests
│   └── intent_builder/    # Intent Builder unit tests
│
├── fixtures/               # Shared test data
│   └── test_data/
│       ├── coffee_allegro/
│       ├── kickstarter_projects/
│       └── producthunt_products/
│
└── README.md               # This file
```

---

## 🚀 Quick Start

### Using Helper Scripts (Recommended)

**Run Cloud Backend Tests:**
```bash
./scripts/run_cloud_tests.sh
```

**Run Integration Tests:**
```bash
# First start both backends
./scripts/start_both_backends.sh

# Then in another terminal
./scripts/run_integration_test.sh
```

### Using pytest Directly

**Run all tests:**
```bash
pytest tests/ -v
```

**Run specific test categories:**
```bash
# Cloud Backend tests
pytest tests/cloud_backend/ -v

# App Backend tests
pytest tests/app_backend/ -v

# Integration tests
pytest tests/integration/ -v

# Unit tests
pytest tests/unit/ -v
```

**Run specific test file:**
```bash
pytest tests/cloud_backend/test_workflow_generation.py -v
```

**Run specific test function:**
```bash
pytest tests/cloud_backend/test_workflow_generation.py::test_generate_workflow_from_operations -v
```

**Run App Backend HTTP tests:**
```bash
# Python tests
python tests/app_backend/test_http_daemon.py

# Shell tests
./tests/app_backend/test_http_daemon.sh
```

---

## 🧪 Test Categories

### 1. Cloud Backend Tests (`tests/cloud-backend/`)

Tests for Cloud Backend functionality:
- **Storage Service**: File system operations
- **Workflow Generation**: LLM-based workflow generation
- **API Endpoints**: REST API functionality

**Requirements:**
- Cloud Backend running on localhost:9000
- LLM API key (ANTHROPIC_API_KEY or OPENAI_API_KEY)

### 2. App Backend Tests (`tests/app_backend/`)

Tests for App Backend HTTP daemon:
- **HTTP API Tests**: Recording, workflow generation, execution
- **Legacy JSON-RPC Tests**: Deprecated stdin/stdout communication

**Requirements:**
- App Backend HTTP daemon running on localhost:8765

See `tests/app_backend/README.md` for detailed test documentation.

### 3. Integration Tests (`tests/integration/`)

End-to-end system tests:
- **test_integration.py**: Full recording → generation → execution flow
- **intent_builder/**: Intent extraction and workflow generation
- **workflow/**: Workflow execution tests

**Requirements:**
- Both App Backend (port 8000) and Cloud Backend (port 9000) running

### 4. Unit Tests (`tests/unit/`)

Component-level tests:
- **baseagent/**: BaseAgent framework components
- **intent_builder/**: Intent Builder modules

---

## 🗂️ Test Fixtures

**Location**: `tests/fixtures/test_data/`

Real-world recording data for testing:
- `coffee_allegro/` - Coffee product scraping from Allegro
- `kickstarter_projects/` - Project data from Kickstarter
- `producthunt_products/` - Product data from ProductHunt

Each fixture includes:
- `fixtures/user_operations.json` - User operation recordings
- `output/` - Expected outputs (intent_graph, metaflow, workflow)

---

## 📋 Prerequisites

### Environment Variables

**Required:**
```bash
# LLM API Key (required for generation tests)
export ANTHROPIC_API_KEY=your_key
# OR
export OPENAI_API_KEY=your_key
```

**Optional:**
```bash
# Test environment configuration
export TEST_STORAGE_PATH=~/.ami-test
export TEST_CLOUD_URL=http://localhost:9000
export TEST_LOCAL_URL=http://localhost:8000
```

### Dependencies

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov httpx

# Install backend dependencies
cd src/local-backend && pip install -r requirements.txt
cd ../cloud-backend && pip install -r requirements.txt
```

---

## 📊 Test Coverage

Generate coverage report:
```bash
pytest tests/ --cov=src --cov-report=html
```

View report:
```bash
open htmlcov/index.html
```

---

## 🛠️ Helper Scripts

All test scripts are located in `scripts/`:

- **start_http_daemon.sh** - Start App Backend HTTP daemon
- **start_cloud_backend.sh** - Start Cloud Backend only
- **start_both_backends.sh** - Start both backends
- **run_cloud_tests.sh** - Run Cloud Backend tests (auto-starts if needed)
- **run_integration_test.sh** - Run full integration test
- **run_desktop_app.sh** - Start Tauri desktop app (if using)

---

**Version**: v2.0
**Updated**: 2025-11-08
