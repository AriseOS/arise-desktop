# DOM Capture & Script Pre-generation Test Guide

This guide covers testing the new features implemented in Phase 6 and Phase 7.

## Overview of Changes

### 1. DOM Capture During Recording (Phase 6.1-6.3)
**Files Modified:**
- `src/clients/desktop_app/ami_daemon/base_app/base_app/base_agent/tools/browser_use/user_behavior/monitor.py`
- `src/clients/desktop_app/ami_daemon/services/cloud_client.py`
- `src/cloud_backend/main.py`
- `src/cloud_backend/services/storage_service.py`

**New Capabilities:**
- Monitor captures DOM on navigation events
- Recording upload includes DOM snapshots
- Cloud Backend stores DOM snapshots

### 2. Script Generation Module (Phase 7.1-7.3)
**Files Created:**
- `src/common/script_generation/__init__.py`
- `src/common/script_generation/types.py`
- `src/common/script_generation/templates.py`
- `src/common/script_generation/browser_script_generator.py`
- `src/common/script_generation/scraper_script_generator.py`
- `src/common/script_generation/CONTEXT.md`

**Files Modified:**
- `src/clients/desktop_app/ami_daemon/base_app/base_app/base_agent/agents/browser_agent.py`
- `src/clients/desktop_app/ami_daemon/base_app/base_app/base_agent/agents/scraper_agent.py`

### 3. Script Pre-generation Service (Phase 6.4 + 7.4)
**Files Created:**
- `src/cloud_backend/intent_builder/services/script_pregeneration_service.py`

**Files Modified:**
- `src/cloud_backend/intent_builder/services/__init__.py`
- `src/cloud_backend/main.py` (added `_pregenerate_scripts_background`)

---

## Test Cases

### Test 1: DOM Capture in Monitor

**Purpose:** Verify DOM is captured when navigation occurs during recording.

**Prerequisites:**
- Desktop app running
- Browser session available

**Steps:**
```python
from src.clients.desktop_app.ami_daemon.base_app.base_app.base_agent.tools.browser_use.user_behavior.monitor import SimpleUserBehaviorMonitor

# 1. Create monitor
monitor = SimpleUserBehaviorMonitor()

# 2. Enable DOM capture
monitor.enable_dom_capture(True)

# 3. Start monitoring (requires browser session)
await monitor.start_monitoring(browser_session)

# 4. Navigate to a page (user action or programmatic)
# ... user navigates to https://example.com ...

# 5. Check DOM snapshots
dom_snapshots = monitor.get_dom_snapshots()
print(f"Captured {len(dom_snapshots)} DOM snapshots")
for url, dom in dom_snapshots.items():
    print(f"  URL: {url}")
    print(f"  DOM keys: {list(dom.keys())[:5]}...")

# 6. Stop monitoring
await monitor.stop_monitoring()
```

**Expected Result:**
- `dom_snapshots` contains URL -> DOM dict mappings
- Each DOM dict has keys like `tag`, `text`, `xpath`, `children`, `interactive_index`

---

### Test 2: Recording Upload with DOM Snapshots

**Purpose:** Verify DOM snapshots are uploaded with recording.

**Prerequisites:**
- Cloud Backend running (`uvicorn src.cloud_backend.main:app`)
- Valid API key

**Steps:**
```python
from src.clients.desktop_app.ami_daemon.services.cloud_client import CloudClient

client = CloudClient(
    base_url="http://localhost:8000",
    user_api_key="ami_test_key"
)

# Test data
operations = [
    {"type": "navigate", "url": "https://example.com", "timestamp": "..."},
    {"type": "click", "xpath": "//button[@id='submit']", "timestamp": "..."}
]

dom_snapshots = {
    "https://example.com": {
        "tag": "html",
        "children": [{"tag": "body", "text": "Example", "interactive_index": 1}]
    }
}

# Upload with DOM snapshots
recording_id = await client.upload_recording(
    operations=operations,
    task_description="Test recording",
    user_id="test_user",
    dom_snapshots=dom_snapshots
)

print(f"Recording uploaded: {recording_id}")
```

**Expected Result:**
- Recording is created successfully
- Server logs show "DOM snapshots: 1 URLs"

---

### Test 3: DOM Snapshots Storage

**Purpose:** Verify DOM snapshots are stored correctly on Cloud Backend.

**Prerequisites:**
- Test 2 completed successfully

**Steps:**
```bash
# Check storage directory
ls ~/ami-server/users/test_user/recordings/{recording_id}/

# Expected:
# operations.json
# dom_snapshots/
#   {url_hash}.json

# Check DOM snapshot content
cat ~/ami-server/users/test_user/recordings/{recording_id}/dom_snapshots/*.json
```

**Expected Result:**
- `dom_snapshots/` directory exists
- Contains JSON files with `url`, `dom`, `captured_at` fields

---

### Test 4: Script Generation Module (Unit Test)

**Purpose:** Verify script generators work independently.

**Steps:**
```python
import asyncio
from pathlib import Path
from src.common.script_generation import (
    BrowserScriptGenerator,
    ScraperScriptGenerator,
    BrowserTask,
    ScraperRequirement
)

async def test_browser_generator():
    generator = BrowserScriptGenerator()

    task = BrowserTask(
        task="Click the login button",
        operation="click",
        xpath_hints={"target": "//*[@id='login']"}
    )

    dom_dict = {
        "tag": "html",
        "children": [{
            "tag": "button",
            "id": "login",
            "text": "Login",
            "interactive_index": 1,
            "xpath": "//*[@id='login']"
        }]
    }

    result = await generator.generate(
        task=task,
        dom_dict=dom_dict,
        working_dir=Path("/tmp/test_browser_script"),
        api_key="your-api-key"
    )

    print(f"Success: {result.success}")
    print(f"Script path: {result.script_path}")
    if result.script_content:
        print(f"Script length: {len(result.script_content)} chars")

async def test_scraper_generator():
    generator = ScraperScriptGenerator()

    requirement = ScraperRequirement(
        user_description="Extract product names",
        output_format={"name": "Product name", "price": "Price"}
    )

    dom_dict = {
        "tag": "html",
        "children": [{
            "tag": "div",
            "class": "product",
            "children": [
                {"tag": "span", "class": "name", "text": "Product A"},
                {"tag": "span", "class": "price", "text": "$99"}
            ]
        }]
    }

    result = await generator.generate(
        requirement=requirement,
        dom_dict=dom_dict,
        working_dir=Path("/tmp/test_scraper_script"),
        api_key="your-api-key"
    )

    print(f"Success: {result.success}")
    print(f"Script path: {result.script_path}")

asyncio.run(test_browser_generator())
asyncio.run(test_scraper_generator())
```

**Expected Result:**
- Both generators return `success=True`
- Script files created in working directories
- `find_element.py` / `extraction_script.py` contain valid Python code

---

### Test 5: Script Pre-generation Service (Unit Test)

**Purpose:** Verify ScriptPregenerationService processes workflow correctly.

**Steps:**
```python
import asyncio
from pathlib import Path
from src.cloud_backend.intent_builder.services import ScriptPregenerationService

async def test_pregeneration():
    service = ScriptPregenerationService(
        api_key="your-api-key"
    )

    workflow_yaml = """
apiVersion: "ami.io/v2"
name: test-workflow
steps:
  - id: navigate
    agent: browser_agent
    inputs:
      target_url: "https://example.com"

  - id: click-login
    agent: browser_agent
    inputs:
      operation: click
      task: "Click login button"
      xpath_hints: ["//*[@id='login']"]

  - id: extract-data
    agent: scraper_agent
    inputs:
      extraction_method: script
      data_requirements:
        user_description: "Extract products"
        output_format:
          name: "Product name"
"""

    dom_snapshots = {
        "https://example.com": {
            "tag": "html",
            "children": [
                {"tag": "button", "id": "login", "text": "Login", "interactive_index": 1},
                {"tag": "div", "class": "product", "text": "Product A"}
            ]
        }
    }

    result = await service.pregenerate_scripts(
        workflow_yaml=workflow_yaml,
        dom_snapshots=dom_snapshots,
        workflow_dir=Path("/tmp/test_workflow")
    )

    print(f"Success: {result['success']}")
    print(f"Total steps: {result['total_steps']}")
    print(f"Generated: {result['generated']}")
    print(f"Skipped: {result['skipped']}")
    print(f"Failed: {result['failed']}")
    print(f"Details: {result['details']}")

asyncio.run(test_pregeneration())
```

**Expected Result:**
- `navigate` step skipped (no script needed)
- `click-login` step generates `find_element.py`
- `extract-data` step generates `extraction_script.py`

---

### Test 6: End-to-End Integration Test

**Purpose:** Full flow from recording to workflow with pre-generated scripts.

**Prerequisites:**
- Cloud Backend running
- Desktop app with recording capability

**Steps:**

1. **Record actions with DOM capture enabled:**
   ```
   - Open browser to target website
   - Enable recording with DOM capture
   - Perform actions (navigate, click, extract)
   - Stop recording
   ```

2. **Upload recording:**
   ```
   POST /api/v1/recordings
   {
     "user_id": "test_user",
     "user_api_key": "...",
     "task_description": "Test automation",
     "operations": [...],
     "dom_snapshots": {...}
   }
   ```

3. **Generate workflow:**
   ```
   POST /api/v1/workflows/generate-stream
   {
     "user_id": "test_user",
     "recording_id": "...",
     ...
   }
   ```

4. **Wait for background script generation (check logs):**
   ```
   tail -f /path/to/logs
   # Look for:
   # "🔧 Background: Starting script pre-generation..."
   # "✅ Background: Script pre-generation complete..."
   ```

5. **Verify workflow directory:**
   ```bash
   ls ~/ami-server/users/test_user/workflows/{workflow_id}/

   # Expected structure:
   # workflow.yaml
   # metadata.json
   # {step_id}/              # Scripts stored directly in step directory
   #   dom_data.json
   #   find_element.py       # browser agent script
   #   task.json             # browser agent config
   #   extraction_script.py  # scraper agent script
   #   requirement.json      # scraper agent config
   #   dom_tools.py          # DOM utilities
   ```

6. **Check workflow metadata:**
   ```bash
   cat ~/ami-server/users/test_user/workflows/{workflow_id}/metadata.json

   # Should contain:
   # {
   #   "script_pregeneration": {
   #     "completed": true,
   #     "generated": N,
   #     "skipped": M,
   #     "failed": 0,
   #     "details": [...]
   #   }
   # }
   ```

**Expected Result:**
- Recording uploaded with DOM snapshots
- Workflow generated successfully
- Scripts pre-generated in background
- Workflow metadata updated with generation status

---

## Troubleshooting

### DOM Capture Not Working
- Check `enable_dom_capture(True)` was called
- Verify browser_session is properly connected
- Check logs for `capture_dom_snapshot` errors

### Script Generation Fails
- Verify API key is valid
- Check Claude Agent SDK connection
- Review working directory permissions
- Check logs for LLM errors

### Pre-generation Not Triggered
- Verify recording has DOM snapshots (`has_dom_snapshots: true`)
- Check `recording_id` is passed to workflow generation
- Review Cloud Backend logs for background task errors

---

## Files for Manual Inspection

After running tests, inspect these locations:

| Location | Purpose |
|----------|---------|
| `~/ami-server/users/{user}/recordings/{id}/dom_snapshots/` | Stored DOM snapshots |
| `~/ami-server/users/{user}/workflows/{id}/metadata.json` | Script generation status |
| `~/ami-server/users/{user}/workflows/{id}/{step_id}/` | Generated scripts |
| `/tmp/test_*` | Unit test working directories |

---

## Quick Validation Checklist

- [ ] Monitor captures DOM on navigate (Test 1)
- [ ] Recording upload accepts `dom_snapshots` (Test 2)
- [ ] DOM snapshots stored in recordings dir (Test 3)
- [ ] BrowserScriptGenerator works (Test 4)
- [ ] ScraperScriptGenerator works (Test 4)
- [ ] ScriptPregenerationService processes workflow (Test 5)
- [ ] End-to-end flow works (Test 6)
- [ ] Workflow metadata shows script generation status (Test 6)
