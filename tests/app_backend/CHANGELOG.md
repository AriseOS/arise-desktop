# App Backend Test Changelog

## 2025-11-08 - Test Reorganization

### Changes Made

1. **Moved HTTP daemon tests from `scripts/` to `tests/app_backend/`**
   - `test_http_daemon.py` - Python HTTP API tests
   - `test_http_daemon.sh` - Shell HTTP API tests

2. **Moved legacy tests to `tests/app_backend/`**
   - `test_daemon_jsonrpc.py` - Legacy JSON-RPC tests (deprecated)
   - `manual_test_daemon.sh` - Manual test script (deprecated)

3. **Deleted obsolete JSON-RPC test scripts**
   - `scripts/test_daemon_client.py`
   - `scripts/test_daemon_interactive.sh`
   - `scripts/test_daemon_list_workflows.py`
   - `scripts/test_daemon_simple.sh`
   - `scripts/test_daemon_start_recording.py`
   - `scripts/test_daemon_stop_recording.py`
   - `scripts/run_daemon_tests.sh`

### Rationale

- **HTTP API replaced JSON-RPC**: The new HTTP daemon (`daemon.py`) uses REST API instead of stdin/stdout JSON-RPC
- **Better organization**: All tests now live in `tests/` directory
- **Clear separation**: Active tests vs deprecated tests
- **Easier to find**: Test scripts are where developers expect them

### Migration Guide

**Old way (JSON-RPC):**
```bash
# Start JSON-RPC daemon
python src/app_backend/daemon_jsonrpc.py

# Run tests
python scripts/test_daemon_client.py
```

**New way (HTTP API):**
```bash
# Start HTTP daemon
./scripts/start_http_daemon.sh

# Run tests
python tests/app_backend/test_http_daemon.py
# OR
./tests/app_backend/test_http_daemon.sh
```

### What's Next

The HTTP daemon now supports:
- ✅ Recording with task_metadata
- ✅ Storage path changed to ~/ami/
- ✅ REST API endpoints for all operations
- ✅ Interactive API docs at http://localhost:8765/docs

Next steps:
- [ ] Test upload to cloud backend
- [ ] Test workflow generation from description
- [ ] Integration tests with Tauri desktop app
