# Browser-Use API Reference

This document provides a comprehensive API reference for browser-use library, focusing on DOM manipulation, browser control actions, and data structures for LLM integration.

## Core Architecture

Browser-use follows an event-driven architecture with three main components:
- **DOM Service**: Page data extraction and DOM tree management
- **Controller**: Browser action execution and coordination  
- **Event System**: Asynchronous browser event handling

## DOM Service API

### DomService Class

Primary interface for DOM tree extraction and page data access.

```python
class DomService:
    def __init__(self, browser_session: BrowserSession, logger: logging.Logger = None)
    
    async def get_dom_tree(
        self, 
        target_id: TargetID,
        initial_html_frames: list[EnhancedDOMTreeNode] = None,
        initial_total_frame_offset: DOMRect = None
    ) -> EnhancedDOMTreeNode
    
    async def get_serialized_dom_tree(
        self, 
        previous_cached_state: SerializedDOMState = None
    ) -> tuple[SerializedDOMState, EnhancedDOMTreeNode, dict[str, float]]
```

**Key Methods:**

- `get_dom_tree()`: Returns enhanced DOM tree with accessibility and snapshot data
- `get_serialized_dom_tree()`: Returns LLM-optimized DOM representation with timing info
- `_get_all_trees()`: Internal method to gather DOM, AX, and snapshot trees in parallel
- `_get_targets_for_page()`: Get main page and iframe targets for multi-frame support

### Data Structures

#### EnhancedDOMTreeNode

Core DOM node representation with enhanced metadata:

```python
@dataclass
class EnhancedDOMTreeNode:
    # Core DOM properties
    node_id: int                        # CDP DOM node ID
    backend_node_id: int               # CDP backend node ID
    node_type: NodeType                # Element, text, document, etc.
    node_name: str                     # Tag name (e.g., "DIV", "INPUT")
    node_value: str                    # Text content for text nodes
    attributes: dict[str, str]         # HTML attributes
    
    # Visibility and interaction
    is_visible: bool | None            # Computed visibility in viewport
    is_scrollable: bool | None         # Whether element can scroll
    element_index: int | None          # Index for LLM interactions (1-based)
    
    # Position and layout
    absolute_position: DOMRect | None  # Absolute coordinates in document
    
    # Enhanced data
    ax_node: EnhancedAXNode | None     # Accessibility information
    snapshot_node: EnhancedSnapshotNode | None  # Layout and styling data
    
    # Tree navigation
    parent_node: EnhancedDOMTreeNode | None
    children_nodes: list[EnhancedDOMTreeNode] | None
    
    # Frame context
    target_id: TargetID                # Target containing this node
    frame_id: str | None               # Frame ID if in iframe
    session_id: SessionID | None       # CDP session ID
    content_document: EnhancedDOMTreeNode | None  # For iframe content
    
    # Shadow DOM
    shadow_root_type: ShadowRootType | None
    shadow_roots: list[EnhancedDOMTreeNode] | None
```

**Properties and Methods:**

- `tag_name`: Lowercase tag name
- `xpath`: XPath selector for the element
- `is_actually_scrollable`: Enhanced scrollability detection 
- `scroll_info`: Detailed scroll position and bounds data
- `get_all_children_text()`: Extract text content from descendants
- `llm_representation()`: Token-efficient string representation

#### EnhancedSnapshotNode

Layout and styling information from DOM snapshot:

```python
@dataclass
class EnhancedSnapshotNode:
    is_clickable: bool | None          # Whether element accepts clicks
    cursor_style: str | None           # CSS cursor property
    
    # Coordinate systems
    bounds: DOMRect | None             # Document coordinates (ignores scroll)
    clientRects: DOMRect | None        # Viewport coordinates (with scroll)
    scrollRects: DOMRect | None        # Scrollable content area
    
    # Styling
    computed_styles: dict[str, str] | None  # CSS computed styles
    paint_order: int | None            # Paint layer order
    stacking_contexts: int | None      # Stacking context information
```

#### DOMRect

Position and dimension information:

```python
@dataclass
class DOMRect:
    x: float                           # X coordinate
    y: float                           # Y coordinate  
    width: float                       # Width in pixels
    height: float                      # Height in pixels
```

#### SerializedDOMState

LLM-optimized DOM representation:

```python
@dataclass
class SerializedDOMState:
    _root: SimplifiedNode | None       # Simplified tree structure
    selector_map: DOMSelectorMap       # Index to node mapping
    
    def llm_representation(
        self, 
        include_attributes: list[str] = None
    ) -> str                           # Text representation for LLM
```

## Controller API

### Controller Class

Main interface for browser action execution:

```python
class Controller:
    def __init__(
        self,
        exclude_actions: list[str] = [],
        output_model: type[T] = None,
        display_files_in_done_text: bool = True
    )
    
    async def act(
        self,
        action: ActionModel,
        browser_session: BrowserSession,
        page_extraction_llm: BaseChatModel = None,
        sensitive_data: dict[str, str | dict] = None,
        available_file_paths: list[str] = None,
        file_system: FileSystem = None,
        context: Context = None
    ) -> ActionResult
```

### Action Models

All browser actions inherit from ActionModel base class:

#### Navigation Actions

```python
class SearchGoogleAction(BaseModel):
    query: str                         # Search query string

class GoToUrlAction(BaseModel):
    url: str                          # Target URL
    new_tab: bool = False             # Open in new tab

class NoParamsAction(BaseModel):      # For parameterless actions like go_back
    pass
```

#### Element Interaction Actions

```python
class ClickElementAction(BaseModel):
    index: int                        # Element index (≥1)
    while_holding_ctrl: bool = False  # Open links in new tab

class InputTextAction(BaseModel):
    index: int                        # Target element index (≥0, 0=page)
    text: str                         # Text to input
    clear_existing: bool = True       # Clear existing content

class UploadFileAction(BaseModel):
    index: int                        # File input element index
    path: str                         # Local file path
```

#### Scrolling Actions

```python
class ScrollAction(BaseModel):
    down: bool                        # True=down, False=up
    num_pages: float                  # Pages to scroll (0.5, 1.0, etc.)
    frame_element_index: int = None   # Element to find scroll container

# Built-in scroll to text method
async def scroll_to_text(text: str, browser_session: BrowserSession)
```

#### Dropdown Actions

```python
class GetDropdownOptionsAction(BaseModel):
    index: int                        # Dropdown element index (≥1)

class SelectDropdownOptionAction(BaseModel):
    index: int                        # Dropdown element index (≥1)
    text: str                         # Exact option text to select
```

#### Tab Management Actions

```python
class SwitchTabAction(BaseModel):
    url: str = None                   # URL substring to match
    tab_id: str = None               # Exact 4-char tab ID

class CloseTabAction(BaseModel):
    tab_id: str                       # 4-char tab ID to close
```

#### Keyboard Actions

```python
class SendKeysAction(BaseModel):
    keys: str                         # Key combination (e.g., "Control+T")
```

#### Completion Actions

```python
class DoneAction(BaseModel):
    text: str                         # Summary message
    success: bool                     # Task completion status
    files_to_display: list[str] = []  # Files to show user

class StructuredOutputAction(BaseModel, Generic[T]):
    success: bool = True              # Task success status
    data: T                           # Structured output data
```

### ActionResult

All actions return ActionResult with execution details:

```python
class ActionResult(BaseModel):
    # Completion status
    is_done: bool = False             # Task completion flag
    success: bool = None              # Success/failure status
    
    # Content and memory
    extracted_content: str = None     # Action output content
    long_term_memory: str = None      # Persistent memory entry
    include_extracted_content_only_once: bool = False  # Single-use content flag
    
    # Error handling
    error: str = None                 # Error message if failed
    
    # File attachments
    attachments: list[str] = None     # File paths to display
    
    # Observability
    metadata: dict = None             # Additional execution data
```

## Browser Session API

Core browser session management and CDP integration:

```python
class BrowserSession:
    # Element access
    async def get_element_by_index(self, index: int) -> EnhancedDOMTreeNode | None
    async def get_selector_map(self) -> DOMSelectorMap
    
    # Tab management
    async def get_tabs(self) -> list[TargetInfo]
    async def get_current_page_url(self) -> str
    async def get_target_id_from_tab_id(self, tab_id: str) -> TargetID
    async def get_target_id_from_url(self, url: str) -> TargetID
    
    # CDP session management
    async def get_or_create_cdp_session(
        self, 
        target_id: TargetID = None,
        focus: bool = False
    ) -> CDPSession
    
    # Frame handling
    async def get_all_frames(self) -> tuple[dict, dict]
    
    # Element classification
    def is_file_input(self, element: EnhancedDOMTreeNode) -> bool
```

## Event System API

Browser-use uses an event-driven architecture for all browser operations:

### Core Events

```python
# Navigation Events
class NavigateToUrlEvent:
    url: str
    new_tab: bool = False

class GoBackEvent:
    pass

# Interaction Events  
class ClickElementEvent:
    node: EnhancedDOMTreeNode
    while_holding_ctrl: bool = False

class TypeTextEvent:
    node: EnhancedDOMTreeNode
    text: str
    clear_existing: bool = True

class ScrollEvent:
    direction: str                    # "up" or "down"
    amount: int                       # Pixels to scroll
    node: EnhancedDOMTreeNode = None  # Target element

class ScrollToTextEvent:
    text: str                         # Text to scroll to

# File Operations
class UploadFileEvent:
    node: EnhancedDOMTreeNode         # File input element
    file_path: str                    # Source file path

# Tab Management
class SwitchTabEvent:
    target_id: TargetID              # Target tab ID

class CloseTabEvent:
    target_id: TargetID              # Tab to close

# Keyboard Events
class SendKeysEvent:
    keys: str                         # Key sequence

# Dropdown Events
class GetDropdownOptionsEvent:
    node: EnhancedDOMTreeNode         # Dropdown element

class SelectDropdownOptionEvent:
    node: EnhancedDOMTreeNode         # Dropdown element  
    text: str                         # Option text
```

### Event Dispatching

```python
# Dispatch pattern used throughout controller
event = browser_session.event_bus.dispatch(EventClass(...))
await event
result = await event.event_result(raise_if_any=True, raise_if_none=False)
```

## Agent Integration API

### AgentOutput

LLM response structure for agent execution:

```python
class AgentOutput(BaseModel):
    thinking: str = None              # Agent reasoning (optional)
    evaluation_previous_goal: str     # Assessment of previous step
    memory: str                       # Current step summary  
    next_goal: str                    # Next objective
    action: list[ActionModel]         # Actions to execute (≥1)
```

### AgentHistory

Track execution history with full context:

```python
class AgentHistory(BaseModel):
    model_output: AgentOutput         # LLM response
    result: list[ActionResult]        # Action execution results
    state: BrowserStateHistory        # Browser state snapshot
    metadata: StepMetadata            # Timing and performance data

class AgentHistoryList(BaseModel):
    history: list[AgentHistory]       # Execution steps
    usage: UsageSummary               # Token usage statistics
    
    # Analysis methods
    def is_done(self) -> bool
    def is_successful(self) -> bool | None  
    def has_errors(self) -> bool
    def urls(self) -> list[str]
    def screenshot_paths(self, n_last: int = None) -> list[str]
    def action_names(self) -> list[str]
    def extracted_content(self) -> list[str]
```

## Configuration API

### AgentSettings  

Comprehensive agent configuration:

```python
class AgentSettings(BaseModel):
    # Vision and UI
    use_vision: bool = True
    vision_detail_level: Literal['auto', 'low', 'high'] = 'auto'
    use_vision_for_planner: bool = False
    
    # Execution control
    max_failures: int = 3
    retry_delay: int = 10
    max_actions_per_step: int = 10
    
    # Output and validation
    validate_output: bool = False
    generate_gif: bool | str = False
    
    # Memory and history
    max_history_items: int = None
    save_conversation_path: str | Path = None
    
    # Prompt customization
    override_system_message: str = None
    extend_system_message: str = None
    include_attributes: list[str] = DEFAULT_INCLUDE_ATTRIBUTES
    
    # Reasoning modes
    use_thinking: bool = True
    flash_mode: bool = False          # Simplified fast execution mode
    
    # LLM configuration
    page_extraction_llm: BaseChatModel = None
    planner_llm: BaseChatModel = None
    planner_interval: int = 1
    calculate_cost: bool = False
    llm_timeout: int = 60
    step_timeout: int = 180
```

## Constants and Enums

### NodeType

DOM node type enumeration:

```python
class NodeType(Enum):
    ELEMENT_NODE = 1                  # HTML elements
    TEXT_NODE = 3                     # Text content
    COMMENT_NODE = 8                  # HTML comments  
    DOCUMENT_NODE = 9                 # Document root
    DOCUMENT_FRAGMENT_NODE = 11       # Document fragments
```

### Default Attributes

Attributes included in LLM representation:

```python
DEFAULT_INCLUDE_ATTRIBUTES = [
    # Form and interaction
    'title', 'type', 'checked', 'name', 'role', 'value', 'placeholder',
    
    # Accessibility
    'alt', 'aria-label', 'aria-expanded', 'aria-checked',
    
    # State information  
    'data-state', 'data-date-format',
    
    # Accessibility properties
    'selected', 'expanded', 'pressed', 'disabled', 'required',
    'valuenow', 'keyshortcuts', 'haspopup', 'multiselectable',
    'valuetext', 'level', 'busy', 'live',
    
    # Accessibility name (text content)
    'ax_name'
]
```

## Error Handling

### Exception Patterns

```python
# Standard error extraction
def extract_llm_error_message(error: Exception) -> str:
    # Extracts clean error message from <llm_error_msg> tags
    # Falls back to str(error) if no tags found

# Controller action error handling
try:
    result = await controller.act(action, browser_session)
    if result.error:
        # Handle action-specific error
        logger.error(result.error)
except Exception as e:
    # Handle system-level exception
    clean_msg = extract_llm_error_message(e)
    return ActionResult(error=clean_msg)
```

### Common Error Types

- `BrowserError`: Browser-specific failures (network, navigation, etc.)
- `ValidationError`: Invalid action parameters or model validation
- `TimeoutError`: CDP or action timeout failures
- `RateLimitError`: LLM API rate limiting

## Usage Examples

### Basic DOM Extraction

```python
dom_service = DomService(browser_session)
dom_tree = await dom_service.get_dom_tree(target_id)

# Access element properties
for child in dom_tree.children:
    if child.element_index and child.is_visible:
        print(f"Interactive element {child.element_index}: {child.tag_name}")
        if child.scroll_info:
            print(f"  Scroll info: {child.get_scroll_info_text()}")
```

### Action Execution

```python
controller = Controller()

# Navigate to page
result = await controller.act(
    GoToUrlAction(url="https://example.com"),
    browser_session
)

# Interact with elements
if not result.error:
    result = await controller.act(
        ClickElementAction(index=5, while_holding_ctrl=True),
        browser_session
    )
```

### Structured Output

```python
from pydantic import BaseModel

class ProductInfo(BaseModel):
    name: str
    price: float
    availability: bool

# Configure controller for structured output
controller = Controller(output_model=ProductInfo)

# Final result will be validated against ProductInfo schema
result = await controller.act(
    StructuredOutputAction(
        success=True,
        data=ProductInfo(name="Widget", price=19.99, availability=True)
    ),
    browser_session
)
```

This API reference provides complete coverage of browser-use's core functionality for DOM manipulation, browser control, and LLM integration. All methods and classes include proper type hints and comprehensive documentation for reliable programmatic usage.