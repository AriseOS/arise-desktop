# base_agent/tools/

Tool integrations for agents.

## Structure

```
tools/
├── base_tool.py              # BaseTool abstract class
├── browser_use/              # Browser automation (DEPRECATED - use eigent_browser)
├── eigent_browser/           # Eigent browser automation (primary browser system)
├── toolkits/                 # LLM tool-calling toolkits (Eigent migration)
└── android_use/              # Android automation (TODO)
```

## Browser Session Management

Browser sessions are managed through two mechanisms:

### 1. Agent-level: BrowserToolkit with session_id mode (for Workforce)

BrowserToolkit supports session_id mode for clone-safe browser access:

```python
from .toolkits import BrowserToolkit

# Create toolkit with session_id (clone-safe)
toolkit = BrowserToolkit(
    session_id="task_123",  # Use task_id for session isolation
    headless=False,
    user_data_dir="/path/to/browser/data",
)

# Session is created on-demand when first browser tool is called
# Multiple agent clones with same session_id share the same browser
```

**Key features:**
- Clone-safe: session_id is a string, safe to copy during agent cloning
- On-demand: Browser is only started when first tool is called
- Shared: Same session_id = same browser instance (via HybridBrowserSession singleton)

### 2. Daemon-level: BrowserManager (for UI/window management)

BrowserManager in services layer provides global browser control:

```python
from src.clients.desktop_app.ami_daemon.services.browser_manager import BrowserManager

browser_manager = BrowserManager(config_service=config)
await browser_manager.start_browser(headless=False)

# Get the session
session = browser_manager.global_session

# Navigate
await session.visit("https://example.com")
```

**Key Features:**
- Single global HybridBrowserSession for UI-controlled browser
- Health monitoring and automatic reconnection
- Window layout management

## Toolkits (toolkits/)

LLM function-calling toolkits ported from Eigent/CAMEL-AI:

| File | Purpose |
|------|---------|
| `base_toolkit.py` | BaseToolkit and FunctionTool base classes |
| `mcp_base.py` | MCP client for local/remote MCP servers |
| `gmail_mcp_toolkit.py` | Gmail via MCP (@gongrzhe/server-gmail-autoauth-mcp) |
| `gdrive_mcp_toolkit.py` | Google Drive via MCP (@modelcontextprotocol/server-gdrive) |
| `calendar_toolkit.py` | Google Calendar via direct API |
| `notion_mcp_toolkit.py` | Notion via remote MCP (https://mcp.notion.com/mcp) |
| `browser_toolkit.py` | Browser automation tools |
| `terminal_toolkit.py` | Shell command execution |
| `search_toolkit.py` | Web search (Google/DuckDuckGo) |
| `human_toolkit.py` | Human-in-the-loop interaction |
| `memory_toolkit.py` | Query memory system |
| `note_taking_toolkit.py` | Markdown note management (for data storage) |
| `task_planning_toolkit.py` | Task decomposition and re-planning (from CAMEL) |

### Task Planning Toolkit

Enables agents to manage their own task execution via decomposition and re-planning:

```python
from .toolkits import TaskPlanningToolkit

toolkit = TaskPlanningToolkit(task_id="my_task")

# Decompose a complex task
subtasks = toolkit.decompose_task(
    original_task_content="Research AI companies and create report",
    sub_task_contents=[
        "Search for top AI companies",
        "Extract product info from each company",
        "Compile findings into summary"
    ]
)

# Update task progress
toolkit.update_task_state("task.main.1", "RUNNING")
# ... execute subtask ...
toolkit.update_task_state("task.main.1", "DONE", result="Found 5 companies")

# Re-plan if needed
new_subtasks = toolkit.replan_tasks(
    original_task_content="Research AI companies and create report",
    sub_task_contents=[
        "Focus on GenAI companies only",
        "Get funding information",
        "Write executive summary"
    ]
)
```

**Key distinction:**
- `TaskPlanningToolkit`: For managing task plans (decomposition, progress, re-planning)
- `NoteTakingToolkit`: For storing extracted data and findings

### MCP Integration

MCP (Model Context Protocol) enables integration with external services:

```python
from .toolkits import GmailMCPToolkit, GoogleDriveMCPToolkit

# Gmail
gmail = GmailMCPToolkit()
await gmail.initialize()
await gmail.send_email("user@example.com", "Subject", "Body")

# Google Drive
gdrive = GoogleDriveMCPToolkit()
await gdrive.initialize()
files = await gdrive.list_files()
```

## BaseTool Interface

```python
class BaseTool(ABC):
    async def execute(self, action: str, params: Dict) -> ToolResult
    def get_available_actions(self) -> List[str]
```

## Eigent Browser Tools (eigent_browser/) - PRIMARY

Ported from CAMEL-AI/Eigent project for LLM-friendly browser automation.
**This is the primary browser system, replacing browser-use.**

### Key Components

| File | Purpose |
|------|---------|
| `page_snapshot.py` | DOM → YAML-like text snapshot with `[ref=eN]` element references |
| `action_executor.py` | Execute browser actions (click, type, scroll, etc.) |
| `browser_session.py` | Multi-tab browser session management (singleton pattern) |
| `browser_launcher.py` | Subprocess-based Chrome launch with CDP (anti-detection) |
| `behavior_recorder.py` | User behavior recording for HybridBrowserSession |
| `config_loader.py` | Browser config and timeout settings |
| `unified_analyzer.js` | JS script for DOM analysis and element ref assignment |
| `scripts/behavior_tracker.js` | JS script for user behavior capture |

### Snapshot Format

Page snapshot converts DOM to LLM-friendly text format:
```yaml
- Page Snapshot
  url: https://example.com
  title: Example Page
  viewport: 1280x720
  elements:
    - button [ref=e1] "Click me"
    - input [ref=e2] placeholder="Search..."
    - a [ref=e3] href="/about" "About Us"
```

### Action Execution

ActionExecutor uses `[aria-ref='eN']` CSS selectors to locate elements:
```python
executor = ActionExecutor(page)
await executor.execute({"type": "click", "ref": "e1"})
await executor.execute({"type": "type", "ref": "e2", "text": "hello"})
```

### Browser Session Singleton

HybridBrowserSession uses singleton pattern per event-loop and session-id:
- Prevents multiple browser instances
- Supports multi-tab management
- Stealth mode for anti-detection

### Behavior Recording (behavior_recorder.py)

Pluggable user behavior recording for HybridBrowserSession:

```python
from .eigent_browser.behavior_recorder import BehaviorRecorder
from .eigent_browser.browser_session import HybridBrowserSession

# Create session and recorder
session = HybridBrowserSession(headless=False, stealth=True)
recorder = BehaviorRecorder(enable_dom_capture=True)

# Start recording
await session.ensure_browser()
await recorder.start_recording(session)
await session.visit("https://example.com")

# ... user performs actions in browser ...

# Stop and get results
result = await recorder.stop_recording()
# result = {
#     "session_id": "session_20250126_143022",
#     "operations": [...],  # List of user operations
#     "dom_snapshots": {...},  # URL -> DOM snapshot
# }
```

**Key features:**
- CDP binding for JavaScript → Python communication
- Multi-tab auto-setup (hooks into tab registration)
- DOM snapshot capture on navigation
- Operation deduplication (navigation events)

## Browser Tools (browser_use/) - DEPRECATED

**Note: This module is deprecated. Use eigent_browser instead.**

Previously built on the browser-use library. All browser automation has been migrated to use eigent_browser directly via BrowserToolkit's session_id mode.

**Remaining files:** Only `user_behavior/monitor.py` is still used by `cdp_recorder.py` for behavior recording. Other files are legacy and should not be used in new code.
