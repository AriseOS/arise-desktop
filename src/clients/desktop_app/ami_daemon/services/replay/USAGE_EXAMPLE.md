# Replay Service Usage Guide

## Overview

The Replay Service allows strict playback of recorded user sessions without any interpretation or intent extraction. It executes operations exactly as they were recorded.

## Quick Start

### 1. Basic Replay

```python
from src.clients.desktop_app.ami_daemon.services.storage_manager import StorageManager
from src.clients.desktop_app.ami_daemon.services.replay import ReplayService
from src.clients.desktop_app.ami_daemon.base_agent.tools.eigent_browser import HybridBrowserSession

# Initialize services
storage = StorageManager()
replay_service = ReplayService(storage)

# Create browser session
browser_session = HybridBrowserSession()
await browser_session.start()

try:
    # Replay a recording
    report = await replay_service.replay_recording(
        session_id="session_20260120_133153",
        user_id="user123",
        browser_session=browser_session
    )

    print(f"Replay completed with {report['execution_summary']['success_rate']*100:.1f}% success")
    print(f"Successful: {report['execution_summary']['successful']}")
    print(f"Failed: {report['execution_summary']['failed']}")

finally:
    await browser_session.close()
```

### 2. Replay with Custom Settings

```python
# Replay with custom wait times and error handling
report = await replay_service.replay_recording(
    session_id="session_20260120_133153",
    user_id="user123",
    browser_session=browser_session,
    wait_between_operations=1.0,  # Wait 1 second between operations
    stop_on_error=True,  # Stop if any operation fails
    start_from_index=5,  # Skip first 5 operations
    end_at_index=20  # Stop at operation 20
)
```

### 3. Preview Recording Before Replay

```python
# Get recording details without replaying
preview = replay_service.get_recording_preview(
    session_id="session_20260120_133153",
    user_id="user123"
)

print(f"Recording has {preview['operations_count']} operations")
print(f"Operation types: {preview['operation_summary']}")
```

### 4. Replay Single Operation (Debug Mode)

```python
# Replay just one operation for testing
result = await replay_service.replay_single_operation(
    session_id="session_20260120_133153",
    user_id="user123",
    operation_index=10,  # Replay operation at index 10
    browser_session=browser_session
)

print(f"Operation status: {result['status']}")
if result['status'] == 'failed':
    print(f"Error: {result['error']}")
```

## API Integration Example

### Add to daemon.py

```python
from src.clients.desktop_app.ami_daemon.services.replay import ReplayService

# In daemon initialization
replay_service = ReplayService(storage_manager)

# API endpoint for replay
@app.post("/api/v1/replay/{session_id}/start")
async def start_replay(
    session_id: str,
    user_id: str,
    wait_between: float = 0.5,
    stop_on_error: bool = False
):
    """Start replay of a recorded session."""

    # Get or create browser session
    browser_session = await get_browser_session(user_id)

    try:
        report = await replay_service.replay_recording(
            session_id=session_id,
            user_id=user_id,
            browser_session=browser_session,
            wait_between_operations=wait_between,
            stop_on_error=stop_on_error
        )
        return report
    except Exception as e:
        return {"error": str(e)}, 500

# API endpoint for preview
@app.get("/api/v1/replay/{session_id}/preview")
async def preview_recording(session_id: str, user_id: str):
    """Get recording preview."""
    try:
        preview = replay_service.get_recording_preview(session_id, user_id)
        return preview
    except Exception as e:
        return {"error": str(e)}, 404
```

## Replay Report Structure

```json
{
  "replay_id": "replay_session_20260120_133153_20260128_143022",
  "status": "completed",
  "recording_session_id": "session_20260120_133153",
  "recording_created_at": "2026-01-20T13:31:53.963592",
  "task_metadata": {
    "user_query": "Login to website",
    "task_description": "User logged into example.com"
  },
  "replay_range": {
    "start_index": 0,
    "end_index": 27
  },
  "execution_summary": {
    "total_operations": 27,
    "successful": 25,
    "failed": 2,
    "skipped": 0,
    "success_rate": 0.926
  },
  "timing": {
    "started_at": "2026-01-28T14:30:22.123456",
    "ended_at": "2026-01-28T14:31:05.987654",
    "duration_seconds": 43.864
  },
  "operation_results": [
    {
      "index": 0,
      "type": "navigate",
      "status": "success",
      "error": null,
      "timestamp": "2026-01-20T13:31:55.123"
    },
    {
      "index": 1,
      "type": "input",
      "status": "success",
      "error": null,
      "timestamp": "2026-01-20T13:32:01.456"
    },
    {
      "index": 2,
      "type": "click",
      "status": "failed",
      "error": "Element not found",
      "timestamp": "2026-01-20T13:32:05.789"
    }
  ]
}
```

## Operation Types Supported

| Type | Description | Execution Method |
|------|-------------|------------------|
| `navigate` | Navigate to URL | `page.goto(url)` |
| `click` | Click element | XPath location → `element.click()` |
| `input` | Fill form input | XPath location → `element.fill(value)` |
| `select` | Text selection | Triple-click on element |
| `scroll` | Scroll page | JavaScript scroll with recorded distance |
| `copy_action` | Copy text | Ctrl+C / Cmd+C simulation |
| `paste_action` | Paste text | Ctrl+V / Cmd+V simulation |
| `dataload` | Wait for dynamic content | Wait for network idle |
| `test` | Binding verification | Skipped during replay |

## Element Location Strategies

The replay executor tries multiple strategies to locate elements (in order):

1. **XPath** (most reliable) - `//input[@id='username']`
2. **ID attribute** - `#username`
3. **Name attribute** - `input[name='username']`
4. **Text content** - `text=Submit`

## Troubleshooting

### Operation Fails with "Element not found"

**Cause**: Page structure changed since recording, or element takes time to load.

**Solutions**:
- Increase `wait_between_operations` value
- Check if the page URL is the same as during recording
- Verify the element still exists in the current page

### Navigation Timeout

**Cause**: Page takes longer to load than timeout allows.

**Solutions**:
- The executor waits 30s for navigation by default
- Check network connectivity
- Verify the URL is still accessible

### Click Operation Has No Effect

**Cause**: Element might be covered by another element or not yet interactive.

**Solutions**:
- The executor waits for element to be visible and enabled
- Try increasing `wait_between_operations` to allow more time for page rendering
- Check if JavaScript frameworks need time to initialize

## Best Practices

1. **Preview before replay**: Always check the recording preview to understand what will be replayed
2. **Start slow**: Use longer `wait_between_operations` (e.g., 1.0s) for initial tests
3. **Use range replay**: Test specific sections using `start_from_index` and `end_at_index`
4. **Check reports**: Review the `operation_results` array to identify failed operations
5. **Browser state**: Ensure the browser is in a clean state before replay (no existing cookies/storage if needed)

## Differences from Workflow Execution

| Aspect | Replay | Workflow |
|--------|--------|----------|
| **Flexibility** | Strict, follows exact sequence | Adaptive, handles variations |
| **Intent** | No interpretation | Extracts and optimizes intent |
| **Element location** | Uses recorded XPath | Smart element detection |
| **Error handling** | Fails if element not found | Tries alternatives |
| **Use case** | Exact reproduction, testing | Production automation |
