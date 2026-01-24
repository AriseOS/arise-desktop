# base_agent/tools/

Tool integrations for agents.

## Structure

```
tools/
├── base_tool.py              # BaseTool abstract class
├── browser_session_manager.py # Browser session lifecycle
├── browser_use/              # Browser automation (based on browser-use library)
├── eigent_browser/           # Eigent browser automation (ported from CAMEL-AI/Eigent)
├── toolkits/                 # LLM tool-calling toolkits (Eigent migration)
└── android_use/              # Android automation (TODO)
```

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
| `memory_toolkit.py` | Query workflow memory |
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

## Browser Tools (browser_use/)

Built on the browser-use library. Key components:

- **BrowserSession** - Manages browser instance lifecycle
- **Controller** - Executes browser actions (click, type, scroll)
- **DomService** - DOM analysis and element extraction
- **DomExtractor** - Serializes DOM for LLM analysis

### DOM Extraction Modes

- `partial` - Visible elements only (faster, for interaction)
- `full` - All elements including hidden (for comprehensive scraping)

### Key Files in browser_use/

| File | Purpose |
|------|---------|
| `dom_extractor.py` | DOM serialization for LLM |
| `controller.py` | Browser action execution |
| `element.py` | DOM element abstraction |
| `user_behavior/monitor.py` | User behavior recording with DOM capture |

### User Behavior Monitor (user_behavior/)

Records user actions during browser sessions:
- Tracks clicks, navigation, input events
- **DOM Capture**: Captures DOM snapshots on navigation for script pre-generation

```python
monitor = SimpleUserBehaviorMonitor()
monitor.enable_dom_capture(True)  # Enable DOM capture on navigation

# After recording...
dom_snapshots = monitor.get_dom_snapshots()
# Returns: Dict[str, dict]  # URL -> DOM dict
```

## Browser Session Manager

Manages browser session lifecycle:
- Creates/reuses browser instances
- Handles session cleanup
- Supports headless/headful modes

## Eigent Browser Tools (eigent_browser/)

Ported from CAMEL-AI/Eigent project for LLM-friendly browser automation.

### Key Components

| File | Purpose |
|------|---------|
| `page_snapshot.py` | DOM → YAML-like text snapshot with `[ref=eN]` element references |
| `action_executor.py` | Execute browser actions (click, type, scroll, etc.) |
| `browser_session.py` | Multi-tab browser session management (singleton pattern) |
| `config_loader.py` | Browser config and timeout settings |
| `unified_analyzer.js` | JS script for DOM analysis and element ref assignment |

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
