# base_agent/tools/

Tool integrations for agents.

## Structure

```
tools/
├── base_tool.py              # BaseTool abstract class
├── browser_session_manager.py # Browser session lifecycle
├── browser_use/              # Browser automation (based on browser-use library)
└── android_use/              # Android automation (TODO)
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
