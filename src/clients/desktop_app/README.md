# Ami Desktop App

Desktop application for recording user operations and executing workflows.

## Features

✅ **Record Tab:**
- Start/Stop recording user browser operations
- Configure starting URL, title, and description
- Generate workflow from recording (calls Cloud Backend)
- Operations saved locally and uploaded to Cloud Backend

✅ **Execute Tab:**
- List all available workflows
- Execute workflows
- Real-time execution status monitoring
- View execution results

## Architecture

```
Desktop App (Tauri)
├── Frontend (React + Vite)
│   └── User interface for recording and execution
└── Rust Backend
    └── PythonDaemon
        ↓ JSON-RPC over stdin/stdout
        Python App Backend Daemon
        ├── CDPRecorder (Browser recording)
        ├── WorkflowExecutor (Workflow execution)
        ├── CloudClient (API calls)
        └── BrowserManager (Persistent browser session)
```

## Prerequisites

1. **Rust** (for Tauri)
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   ```

2. **Node.js** (v16+)
   ```bash
   # Check version
   node --version
   npm --version
   ```

3. **Python** (3.11+) with dependencies
   ```bash
   # Already installed if you set up app_backend
   pip install -r ../../requirements.txt
pip install -r ./ami_daemon/requirements.txt
   ```

## Setup

### Python Environment (3.11+)

`browser-use>=0.1.0` that powers the daemon only publishes wheels for Python ≥3.11. Install Python 3.11 via **Homebrew** (`brew install python@3.11`) or **pyenv** (`pyenv install 3.11.8`), then recreate your `.venv` with that interpreter before installing `requirements.txt` and `ami_daemon/requirements.txt`.

### 1. Install Frontend Dependencies

```bash
cd src/desktop_app
npm install
```

### 2. Install Tauri CLI

```bash
npm install --save-dev @tauri-apps/cli
```

## Development

### Run in Development Mode

```bash
cd src/desktop_app

# This will:
# 1. Start Vite dev server (frontend)
# 2. Start Tauri (Rust backend)
# 3. Launch Python daemon automatically
npm run tauri dev
```

**Note:** Make sure you run this from the project root directory `/Users/shenyouren/workspace/arise-project/ami/ami/`, otherwise Python daemon won't find `src/app_backend/daemon.py`.

### Build for Production

```bash
cd src/desktop_app
npm run tauri build
```

The built app will be in `src/desktop_app/src-tauri/target/release/`.

## Usage

### 1. Record Workflow

1. Click **"📹 Record"** tab
2. Fill in:
   - **Starting URL**: e.g., `https://www.google.com`
   - **Workflow Title**: e.g., `Search coffee products`
   - **Description**: Describe what the workflow does
3. Click **"🔴 Start Recording"**
4. **A browser window will open** - perform your operations
5. Click **"⏹️ Stop Recording"** when done
6. Click **"✨ Generate Workflow"** (takes 30-60 seconds)
   - Operations uploaded to Cloud Backend
   - MetaFlow generated
   - Workflow YAML generated and downloaded

### 2. Execute Workflow

1. Click **"▶️ Execute"** tab
2. Select a workflow from the dropdown
3. Click **"▶️ Execute Workflow"**
4. Monitor real-time execution status:
   - Progress percentage
   - Current step / Total steps
   - Status message
   - Results (when completed)

## Workflow Files

- **Recordings**: `storage/app_backend/recordings/default_user/`
- **Workflows**: `storage/app_backend/workflows/default_user/`
- **Execution Results**: `storage/app_backend/executions/default_user/`

## Troubleshooting

### Daemon fails to start

**Error:** `Failed to initialize Python daemon`

**Solution:**
- Make sure you're running from project root
- Check Python is in PATH: `which python`
- Verify app_backend dependencies: `pip install -r requirements.txt`

### Browser doesn't open for recording

**Error:** `Failed to start recording`

**Solution:**
- Check Python daemon logs in console
- Ensure Chromium is installed: `playwright install chromium`

### Workflow generation hangs

**Issue:** "Generating workflow..." shows for > 2 minutes

**Solution:**
- Check Cloud Backend is running and accessible
- Cloud Backend API might be slow (30-60s is normal)
- Check network connectivity

## API Reference

### Tauri Commands (called from frontend)

#### `start_recording(url, title, description)`
Start recording user operations

#### `stop_recording()`
Stop recording and save to local storage

#### `generate_workflow(session_id, title, description)`
Generate workflow from recording (full flow)

#### `execute_workflow(workflow_name)`
Execute workflow asynchronously

#### `get_workflow_status(task_id)`
Get execution status (for polling)

#### `list_workflows()`
List all user workflows

## Development Notes

- **Hot Reload**: Frontend auto-reloads, but Rust backend requires restart
- **Python Daemon**: Starts automatically with Tauri, stops on app close
- **Browser Session**: Persistent across recordings (stays open)
- **Logs**: Python daemon logs appear in Tauri console (stderr)
