# Ami System Flow Analysis: Complete Closed-Loop Interface

## Executive Summary

Ami implements a closed-loop system for recording user actions, converting them to workflows, and executing them. The system consists of four integrated components:

1. **Browser Extension** - Records user behavior via Chrome extension
2. **Recording Service** - Captures and stores operations on the backend
3. **Intent Builder** - Converts recorded operations to semantic workflows
4. **BaseAgent Framework** - Executes workflows with browser automation

---

## 1. USER BEHAVIOR RECORDING FLOW

### 1.1 Recording Entry Points

#### Extension UI (Frontend)
- **File**: `/src/clients/chrome-extension/src/pages/RecordPage.jsx`
- **Functionality**: React component that provides recording UI
- **Key Actions**:
  - User enters workflow title and description
  - Clicks "Start Recording" button
  - Real-time display of captured operations
  - Clicks "Stop Recording" when done

#### Recording Session Creation
```
User clicks "Start Recording"
  ↓
POST /api/recording/start
  ├─ Parameters: title, description
  ├─ User: current_user (from JWT token)
  └─ Returns: session_id, success flag

RecordingService.create_session()
  ├─ Generates unique session_id: rec_{uuid}
  ├─ Creates RecordingSession object
  ├─ Validates user doesn't have active session
  └─ Stores in active_sessions dict
```

### 1.2 Behavior Recording Architecture

#### Three-Layer Recording Stack

**Layer 1: behavior_tracker.js (Injected Script)**
- **Location**: `/src/clients/chrome-extension/public/behavior_tracker.js`
- **Execution Context**: Page-level (web_accessible_resources)
- **Capabilities**: Direct DOM access, full event tracking
- **Operation Types Captured**:
  - `click` - Element clicks (with XPath, tag, id, class)
  - `input` - Text input changes
  - `navigate` - Page navigation (URL changes)
  - `scroll` - Scroll events
  - `select` - Form element selection
  - `submit` - Form submission
  - `hover` - Mouse hover events

**Operation Data Structure**:
```json
{
  "type": "click|input|navigate|scroll|select|submit|hover",
  "url": "https://example.com/page",
  "page_title": "Page Title",
  "timestamp": "2024-11-04T12:00:00.000Z",
  "element": {
    "xpath": "//button[@id='submit']",
    "tagName": "button",
    "id": "submit",
    "className": "btn btn-primary",
    "textContent": "Submit"
  },
  "data": {
    "value": "entered_text",  // for input
    "scrollX": 0,            // for scroll
    "scrollY": 100,
    "oldValue": "",          // for input change
    "newValue": "new_value"
  }
}
```

**Layer 2: recorder.js (Content Script)**
- **Location**: `/src/clients/chrome-extension/public/recorder.js`
- **Execution Context**: Content script (can access extension APIs)
- **Responsibility**:
  1. Injects behavior_tracker.js into page
  2. Listens for operations via postMessage
  3. Forwards operations to background script
  4. Manages recording state across page navigations

**Layer 3: background.js (Service Worker)**
- **Location**: `/src/clients/chrome-extension/public/background.js`
- **Responsibility**:
  1. Stores captured operations in memory: `capturedOperations[]`
  2. Receives messages from RecordPage popup
  3. Forwards operations to backend API
  4. Manages session lifecycle

### 1.3 Recording Lifecycle

#### Start Recording
```
RecordPage.jsx
  ↓
1. POST /api/recording/start
   └─ Backend: RecordingService.create_session()
      └─ Stores session in memory

2. chrome.tabs.sendMessage to all tabs
   {action: 'startRecording', sessionId, token}
   
3. recorder.js receives message
   ├─ Saves to chrome.storage.local
   └─ Injects behavior_tracker.js

4. behavior_tracker.js initializes
   ├─ Attaches event listeners to document
   └─ Ready to capture operations
```

#### Operation Capture Loop (During Recording)
```
User Action (click, type, navigate, etc.)
  ↓
behavior_tracker.js detects event
  ├─ Constructs operation object with:
  │  ├─ Type (click, input, navigate, etc.)
  │  ├─ Element info (XPath, tag, id, class, text)
  │  ├─ URL and page title
  │  └─ Timestamp
  ↓
Sends via window.postMessage()
  {source: 'ami-tracker', operation: {...}}
  ↓
recorder.js receives via addEventListener('message')
  ↓
chrome.runtime.sendMessage to background.js
  {action: 'sendOperation', sessionId, token, operation}
  ↓
background.js:
  1. Stores locally: capturedOperations.push(operation)
  2. Sends to backend: POST /api/recording/operation
  ↓
RecordingService.add_operation()
  └─ Stores in session.operation_list[]
```

#### Stop Recording
```
User clicks "Stop Recording"
  ↓
POST /api/recording/stop
  └─ Parameters: session_id

RecordingService.stop_session()
  ├─ Sets is_recording = false
  ├─ Returns all captured operations
  └─ Keeps session in memory (for retrieval)

RecordPage.jsx
  ├─ Receives operations
  ├─ Prints to console (for debugging)
  └─ Navigates to Metaflow/Analysis page
```

### 1.4 Storage Format

**In-Memory Storage** (during recording):
```python
# File: src/app_backend/models/recording.py
class RecordingSession:
    session_id: str          # rec_{uuid}
    title: str
    description: str
    user_id: int
    created_at: datetime
    operation_list: List[dict]  # Raw operations
    is_recording: bool
```

**Database Storage** (after stop):
```python
# File: src/cloud_backend/database/models.py
class RecordingSessionDB(Base):
    id: int
    session_id: str
    user_id: int
    title: str
    description: str
    recording_data: JSON      # Full export_data structure
    operation_count: int
    started_at: datetime
    stopped_at: datetime
```

**Export JSON Structure**:
```json
{
  "session_info": {
    "session_id": "rec_abc123def456",
    "title": "Collect Product Prices",
    "description": "Scrape prices from e-commerce site",
    "start_time": "2024-11-04T12:00:00",
    "total_operations": 42
  },
  "operations": [
    {operation1},
    {operation2},
    ...
  ]
}
```

### 1.5 API Endpoints (Recording)

| Endpoint | Method | Purpose | Parameters |
|----------|--------|---------|------------|
| `/api/recording/start` | POST | Create recording session | title, description |
| `/api/recording/stop` | POST | Stop session, return ops | session_id |
| `/api/recording/status/{session_id}` | GET | Get session status | session_id |
| `/api/recording/operation` | POST | Add operation (from extension) | session_id, operation |

---

## 2. WORKFLOW GENERATION FLOW

### 2.1 Intent Extraction Pipeline

#### Input: Recorded Operations
Captured from RecordPage.jsx via `/api/recording/stop` response:
```json
{
  "operations": [
    {"type": "navigate", "url": "https://example.com", ...},
    {"type": "click", "element": {...}, ...},
    {"type": "input", "data": {"value": "search term"}, ...},
    {"type": "navigate", "url": "https://results.com", ...},
    ...
  ]
}
```

#### Step 1: Intent Extraction (IntentExtractor)
- **File**: `/src/intent_builder/extractors/intent_extractor.py`
- **Process**:
  1. **URL-based Segmentation** (Rule-based):
     - Split operations whenever URL changes
     - Each segment = one "page visit"
  
  2. **Semantic Intent Extraction** (LLM-based):
     - Analyze each segment
     - Generate 1-N semantic intents
     - Each intent has description and goal
  
  3. **Output**: List of `Intent` objects

**Example Segmentation**:
```
Segment 1: [navigate(url1), click, input]
Segment 2: [navigate(url2), click, click, input, submit]
Segment 3: [navigate(url1), input, submit]
```

#### Step 2: Intent Memory Graph Creation
- **File**: `/src/intent_builder/core/intent_memory_graph.py`
- **Structure**: Directed graph of intents
- **Nodes**: Intent objects with relationships
- **Edges**: Sequential execution or conditional

#### Step 3: MetaFlow Generation
- **File**: `/src/intent_builder/generators/metaflow_generator.py`
- **Input**: IntentMemoryGraph
- **Output**: MetaFlow YAML
- **MetaFlow Structure**:
```yaml
metadata:
  name: "workflow_name"
  version: "1.0"

task_description: "High-level task description"

nodes:
  - id: "intent_0"
    name: "Navigate to home page"
    description: "Open the product listing page"
    type: "navigation"
    actions:
      - url: "https://example.com"
    success_condition: "page_loaded"
    next: "intent_1"

  - id: "intent_1"
    name: "Search for products"
    description: "Enter search term and submit"
    type: "interaction"
    actions:
      - xpath: "//input[@id='search']"
        action: "input"
        value: "product keyword"
      - xpath: "//button[@id='submit']"
        action: "click"
    next: "intent_2"

relationships:
  - source: "intent_0"
    target: "intent_1"
    type: "sequential"

convergence:
  - intents: ["intent_0", "intent_1"]
    type: "sequential_execution"
```

### 2.2 Workflow Generation from MetaFlow

#### Step 1: Prompt Building
- **File**: `/src/intent_builder/generators/prompt_builder.py`
- **Input**: MetaFlow YAML
- **Output**: LLM prompt requesting workflow YAML
- **Prompt Structure**:
  1. Task description
  2. MetaFlow nodes and relationships
  3. Instructions for workflow generation
  4. Expected YAML schema

#### Step 2: LLM-Based Workflow Generation
- **File**: `/src/intent_builder/generators/workflow_generator.py`
- **Process**:
  1. Build prompt from MetaFlow
  2. Call LLM (OpenAI/Anthropic)
  3. Parse response to YAML
  4. Validate YAML structure
  5. Return final workflow

#### Step 3: Workflow YAML Output
- **Format**: BaseAgent-compatible YAML
- **Structure**:
```yaml
apiVersion: ami.io/v1
kind: Workflow
metadata:
  name: product-collection-workflow
  version: 1.0

inputs:
  - name: search_keyword
    type: string
    required: true

outputs:
  - name: products
    type: array

steps:
  - id: step_1
    name: Open Product Page
    agent_type: browser_agent
    config:
      action: navigate
      url: https://example.com/products

  - id: step_2
    name: Search Products
    agent_type: tool_agent
      1. Find the search input field (XPath: //input[@id='search'])
      2. Enter the search keyword
      3. Click the submit button
    config:
      tool: browser
      actions:
        - action: fill_input
          selector: "//input[@id='search']"
          value: "{{search_keyword}}"
        - action: click
          selector: "//button[@id='submit']"

  - id: step_3
    name: Extract Results
    agent_type: code_agent
    config:
      code: |
        products = []
        for item in page.select(".product-item"):
          products.append({
            "name": item.select_one(".product-name").text,
            "price": item.select_one(".product-price").text
          })
        return products

  - id: step_4
    name: Return Results
    agent_type: variable
    config:
      assign:
        output_products: "{{products}}"

final_response:
  type: outputs
  return: products
```

### 2.3 API Endpoints (Workflow Generation)

Currently integrated in extension pages:
- **RecordPage.jsx** → `onNavigate('metaflow', {recordingData})`
- **MetaflowPage.jsx** → Displays/edits MetaFlow
- **WorkflowGenerationPage.jsx** → Generates final workflow

---

## 3. WORKFLOW EXECUTION FLOW

### 3.1 Workflow Execution Entry Points

#### API Endpoint
```
GET /api/agents/workflow/{workflow_name}/execute
  ├─ Parameters: workflow_name (e.g., "allegro-coffee-collection-workflow")
  ├─ Returns: task_id
  └─ Executes in background (async)
```

#### Execution Flow
```
API Request
  ↓
Backend (main.py, execute_workflow function)
  ├─ Generate task_id
  ├─ Initialize task status in workflow_tasks dict
  └─ Create async task: run_workflow_async()

run_workflow_async()
  ├─ Load WorkflowLoader: load_workflow(workflow_name)
  ├─ Create BaseAgent instance
  │  └─ Pass user_id for Memory isolation
  ├─ Initialize BaseAgent
  ├─ Execute: await base_agent.run_workflow(workflow)
  └─ Return WorkflowResult

Task Status Tracking
  └─ GET /api/agents/workflow/task/{task_id}/status
```

### 3.2 BaseAgent Workflow Execution

#### BaseAgent Architecture
- **File**: `/src/base_app/base_app/base_agent/core/base_agent.py`
- **Core Components**:
  1. **AgentConfig**: Configuration for agent
  2. **Tools**: Registered tools (browser, code, etc.)
  3. **MemoryManager**: User-bound memory system
  4. **WorkflowEngine**: Executes workflow steps
  5. **StateManager**: Tracks execution state

#### Workflow Loading
- **File**: `/src/base_app/base_app/base_agent/workflows/workflow_loader.py`
- **Process**:
  1. Load YAML workflow definition
  2. Validate schema and required fields
  3. Create Workflow object with steps
  4. Return ready-to-execute workflow

**Workflow Loading Steps**:
```python
workflow = load_workflow(workflow_name)
# Loads from: src/base_app/base_agent/workflows/builtin/{name}.yaml
# OR from: tests/test_data/{name}/workflow.yaml

# Validates:
# - API version: ami.io/v1
# - Kind: Workflow
# - Required metadata fields
# - Step definitions
# - Input/output schemas
```

#### Step Execution Engine
- **File**: `/src/base_app/base_app/base_agent/core/agent_workflow_engine.py`
- **Process**:
  1. For each step in workflow.steps:
     - Get step definition
     - Determine step type (browser_agent, tool_agent, code_agent, variable)
     - Execute appropriate agent type
     - Capture output to workflow context
     - Check conditions for next step
  2. Handle errors per ErrorHandling config
  3. Return final result

#### Agent Types (Step Implementations)

**1. BrowserAgent** - Browser automation
```yaml
agent_type: browser_agent
config:
  action: navigate
  url: https://example.com
```

**2. ToolAgent** - Use integrated tools (browser, code execution)
```yaml
agent_type: tool_agent
config:
  tool: browser
  actions:
    - action: click
      selector: "#submit"
```

**3. CodeAgent** - Execute Python code
```yaml
agent_type: code_agent
config:
  code: |
    result = input_data.split(',')
    return result
```

**4. TextAgent** - LLM-based natural language processing
```yaml
agent_type: text_agent
config:
  text: "Analyze and summarize: {{extracted_content}}"
```

**5. VariableAgent** - Assign variables
```yaml
agent_type: variable
config:
  assign:
    output_var: "{{processed_data}}"
```

### 3.3 Memory System

#### Memory Isolation
- **User-bound Design**: Memory binds to users, not agent instances
- **Architecture**:
```python
BaseAgent(config, user_id="user_123")
  └─ MemoryManager(user_id="user_123")
      ├─ Variables: In-process dict
      ├─ KVStorage: SQLite {user_id}/kv.db
      └─ LongTermMemory: SQLite {user_id}/memory.db
```

#### Memory Layers
1. **Variables** - Runtime variables passed between steps
2. **KVStorage** - Persistent key-value storage (survives agent restart)
3. **LongTermMemory** - Semantic memory for future workflows

### 3.4 Tools Integration

#### Browser Tool
- **File**: `/src/base_app/base_app/base_agent/tools/browser_use/browser_tool.py`
- **Session Management**: Global browser session or per-workflow
- **Capabilities**:
  - Navigate to URLs
  - Click elements (CSS selector or XPath)
  - Fill form inputs
  - Extract text/data
  - Wait for conditions
  - Screenshot capture

#### Tool Execution Format
```python
result = await agent.use_tool(
    tool_name='browser',
    action='navigate',
    params={'url': 'https://example.com'}
)
# Returns: ToolResult(success=True, data=response, status=ToolStatus.SUCCESS)
```

### 3.5 Execution Results

#### Workflow Result Structure
```python
WorkflowResult(
    success=True,
    final_result={...},     # Output from final_response step
    step_results=[...],     # Results from each step
    execution_time_ms=1234,
    state=AgentState(...)   # Final agent state
)
```

#### Result Persistence
- **Storage**: SQLite database in storage.db
- **Query Endpoint**: `GET /api/agents/workflow/{workflow_name}/results`
- **Parameters**: begin, end, limit date range filtering

---

## 4. CURRENT EXTENSION STATUS

### 4.1 Extension Architecture

#### Files Structure
```
/src/clients/chrome-extension/
├── public/
│   ├── manifest.json                 # Extension manifest (MV3)
│   ├── background.js                 # Service worker
│   ├── content.js                    # Content script
│   ├── recorder.js                   # Recording controller
│   ├── behavior_tracker.js           # DOM-level tracker (injected)
│   └── popup.html/popup.js          # Popup UI
├── src/
│   ├── App.jsx                       # Main app component
│   ├── pages/
│   │   ├── RecordPage.jsx           # Recording interface
│   │   ├── MetaflowPage.jsx         # MetaFlow visualization
│   │   ├── WorkflowGenerationPage.jsx # Workflow generation
│   │   ├── MyWorkflowsPage.jsx      # Saved workflows list
│   │   ├── WorkflowResultPage.jsx   # Results display
│   │   ├── WorkflowDetailPage.jsx   # Workflow details
│   │   ├── WorkflowAnalysisPage.jsx # Analysis/composition
│   │   ├── ChatPage.jsx             # Chat interface
│   │   ├── LoginPage.jsx            # Authentication
│   │   ├── IntentionPage.jsx        # Intention setting
│   │   └── AboutPage.jsx            # About/help
│   ├── components/
│   │   ├── StatusMessage.jsx        # Status notifications
│   │   └── CustomNode.jsx           # ReactFlow nodes
│   └── config/
│       ├── workflows.js             # Sample workflows
│       ├── metaflows.js             # Sample metaflows
│       └── index.js                 # Configuration
└── vite.config.js                   # Build config
```

### 4.2 Extension Capabilities

#### Currently Implemented
✓ Recording user operations (click, input, navigate, scroll, etc.)
✓ Session management (start/stop recording)
✓ Operation storage (in-memory + backend)
✓ Extension popup UI with recording interface
✓ MetaFlow visualization (prepared for rendering)
✓ Workflow generation page (prepared)
✓ User authentication (login page)
✓ Storage of recorded sessions (database)

#### Partially Implemented
◐ MetaFlow visualization (UI prepared, integration needs work)
◐ Workflow execution from extension (backend ready, UI needs completion)
◐ Workflow composition/analysis (page structure exists)

#### Not Yet Implemented
✗ Real-time MetaFlow generation from operations
✗ In-browser workflow execution with result display
✗ Workflow editing and testing
✗ Advanced operation filtering and cleanup

### 4.3 Existing API Integrations

#### Authentication
```javascript
POST /api/login
  ├─ Parameters: username, password
  ├─ Returns: access_token, token_type, user info
  └─ Stored: chrome.storage.local

POST /api/register
  └─ Create new user account
```

#### Recording APIs (Fully Implemented)
```javascript
POST /api/recording/start          // Create session
POST /api/recording/stop           // Stop and get operations
GET /api/recording/status/{id}     // Session status
POST /api/recording/operation      // Add operation
```

#### Workflow Execution (Backend Ready)
```javascript
GET /api/agents/workflow/{name}/execute   // Start execution
GET /api/agents/workflow/task/{id}/status // Get task status
GET /api/agents/workflow/{name}/results   // Get execution results
```

#### Agent APIs (Partial)
```javascript
GET /api/agents/{agent_id}/workflow       // Get workflow definition
POST /api/agents/build                    // Build new agent
GET /api/agents/list                      // List user agents
```

### 4.4 Data Flow in Current Extension

```
User Interface (RecordPage.jsx)
  ↓
Chrome Extension Messages
  ├─ background.js (Operation storage)
  └─ Content Scripts (Page injection)
  ↓
Recording Service (Backend)
  ├─ POST /api/recording/start
  ├─ POST /api/recording/operation (streaming)
  └─ POST /api/recording/stop
  ↓
Frontend Pages (MetaflowPage, WorkflowGenerationPage)
  ├─ Display captured operations
  ├─ Show generated MetaFlow (if auto-generated)
  └─ Generate final workflow YAML
  ↓
Backend Workflow Execution
  ├─ GET /api/agents/workflow/{name}/execute
  ├─ Task status polling
  └─ GET /api/agents/workflow/{name}/results
```

---

## 5. IDENTIFIED GAPS & ARCHITECTURE ISSUES

### 5.1 Gaps in Current Implementation

#### Gap 1: No Automatic MetaFlow Generation from Operations
**Issue**: After recording stops, operations are passed to frontend but MetaFlow generation is manual/LLM-based
**Location**: RecordPage.jsx → MetaflowPage.jsx transition
**Missing**: Automatic IntentExtractor integration on frontend

**Proposed Solution**:
- Call backend endpoint: `POST /api/intents/extract`
- Input: operations list
- Output: IntentMemoryGraph or MetaFlow YAML
- Integrate into recording flow

#### Gap 2: No Direct Workflow Execution from Extension
**Issue**: Workflow can be executed via API but no UI in extension to trigger and monitor execution
**Location**: Extension pages (WorkflowDetailPage, MyWorkflowsPage)
**Missing**: Execute button + real-time result streaming

**Proposed Solution**:
- Add "Execute" button to WorkflowDetailPage
- WebSocket connection for real-time progress
- Result display with step-by-step output

#### Gap 3: Incomplete Workflow Composition/Analysis
**Issue**: WorkflowAnalysisPage exists but lacks integration
**Location**: `/src/clients/chrome-extension/src/pages/WorkflowAnalysisPage.jsx`
**Missing**: Ability to compose workflows, test intents, refine operations

**Proposed Solution**:
- Link to cross-market-product-selection composition example
- Enable step-by-step refinement of workflows
- Save intermediate analysis results

#### Gap 4: Missing Operation Cleanup/Filtering
**Issue**: No way to remove/edit operations after recording
**Location**: RecordPage.jsx
**Missing**: Operation editing interface

**Proposed Solution**:
- Add "Edit Operations" mode in RecordPage
- Allow deletion of noisy/unnecessary operations
- Preview impact on MetaFlow generation

#### Gap 5: No Workflow Parameter Binding UI
**Issue**: Workflows have input parameters but extension doesn't have UI to set them before execution
**Location**: WorkflowExecutionPage (missing)
**Missing**: Parameter input form generation

**Proposed Solution**:
- Introspect workflow `inputs` section
- Generate dynamic form for parameters
- Pass parameters to execution API

### 5.2 Architectural Improvements Needed

#### Issue 1: Recording Service Not Persistent Enough
**Current**: In-memory storage cleared on restart
**Solution**: Save to database immediately (done) but also implement:
- Auto-save intervals during recording
- Ability to resume interrupted recordings
- Backup operations to IndexedDB in extension

#### Issue 2: Missing Progressive Feedback
**Current**: User doesn't see real-time feedback until stop
**Solution**: 
- Show operation count in real-time
- Display last captured operation type
- Show connection status to backend

#### Issue 3: No Error Recovery for Network Failures
**Current**: Lost operations if network drops during recording
**Solution**:
- Queue operations locally if backend unavailable
- Retry with exponential backoff
- Merge operations when connection restored

#### Issue 4: Limited MetaFlow Customization
**Current**: Auto-generated MetaFlow is rigid
**Solution**:
- Allow manual node editing
- Add condition/branching support in UI
- Test individual nodes before execution

---

## 6. COMPLETE API REFERENCE

### 6.1 Recording APIs

#### Start Recording Session
```http
POST /api/recording/start HTTP/1.1
Content-Type: application/json
Authorization: Bearer {token}

{
  "title": "Collect Product Prices",
  "description": "Scrape prices from e-commerce site"
}

Response 200:
{
  "success": true,
  "session_id": "rec_abc123def456",
  "message": "Recording started"
}
```

#### Add Operation (During Recording)
```http
POST /api/recording/operation HTTP/1.1
Content-Type: application/json
Authorization: Bearer {token}

{
  "session_id": "rec_abc123def456",
  "operation": {
    "type": "click",
    "url": "https://example.com/products",
    "page_title": "Products",
    "timestamp": "2024-11-04T12:00:00Z",
    "element": {
      "xpath": "//button[@id='filter']",
      "tagName": "button",
      "id": "filter",
      "className": "btn-primary",
      "textContent": "Filter"
    },
    "data": {}
  }
}

Response 200:
{
  "success": true,
  "operation_count": 5
}
```

#### Stop Recording Session
```http
POST /api/recording/stop HTTP/1.1
Content-Type: application/json
Authorization: Bearer {token}

{
  "session_id": "rec_abc123def456"
}

Response 200:
{
  "success": true,
  "session_id": "rec_abc123def456",
  "operations": [...],
  "operation_count": 42
}
```

#### Get Recording Status
```http
GET /api/recording/status/rec_abc123def456 HTTP/1.1
Authorization: Bearer {token}

Response 200:
{
  "session_id": "rec_abc123def456",
  "title": "Collect Product Prices",
  "description": "Scrape prices...",
  "is_recording": false,
  "operation_count": 42,
  "created_at": "2024-11-04T12:00:00"
}
```

### 6.2 Workflow Execution APIs

#### Execute Workflow
```http
GET /api/agents/workflow/allegro-coffee-collection-workflow/execute HTTP/1.1
Authorization: Bearer {token}

Response 200:
{
  "success": true,
  "task_id": "task_allegro-coffee-collection-workflow_abc12345",
  "message": "Workflow allegro-coffee-collection-workflow execution started",
  "workflow_name": "allegro-coffee-collection-workflow",
  "user_id": 1,
  "timestamp": "2024-11-04T12:00:00Z"
}
```

#### Get Task Status
```http
GET /api/agents/workflow/task/task_allegro-coffee-collection-workflow_abc12345/status HTTP/1.1
Authorization: Bearer {token}

Response 200:
{
  "task_id": "task_...",
  "workflow_name": "allegro-coffee-collection-workflow",
  "status": "running|completed|failed",
  "progress": 50,
  "message": "Executing step 2 of 4",
  "user_id": 1,
  "started_at": "2024-11-04T12:00:00Z",
  "completed_at": null,
  "result": null,
  "error": null
}
```

#### Get Workflow Results
```http
GET /api/agents/workflow/allegro-coffee-collection-workflow/results?begin=2024-11-01&end=2024-11-04&limit=10 HTTP/1.1
Authorization: Bearer {token}

Response 200:
{
  "workflow_name": "allegro-coffee-collection-workflow",
  "results": [
    {
      "id": 1,
      "execution_timestamp": "2024-11-04T12:00:00Z",
      "execution_time_ms": 1234,
      "status": "success",
      "result_data": {...}
    }
  ],
  "total": 1
}
```

---

## 7. KEY FILE LOCATIONS REFERENCE

| Component | File | Purpose |
|-----------|------|---------|
| **Recording** | `/src/app_backend/models/recording.py` | RecordingSession dataclass |
| | `/src/clients/chrome-extension/public/behavior_tracker.js` | DOM operation capture |
| | `/src/clients/chrome-extension/public/recorder.js` | Recording controller |
| | `/src/clients/chrome-extension/src/pages/RecordPage.jsx` | Recording UI |
| **Intent Extraction** | `/src/intent_builder/extractors/intent_extractor.py` | IntentExtractor class |
| | `/src/intent_builder/core/intent.py` | Intent data model |
| | `/src/intent_builder/core/intent_memory_graph.py` | Graph structure |
| **MetaFlow** | `/src/intent_builder/core/metaflow.py` | MetaFlow data model |
| | `/src/intent_builder/generators/metaflow_generator.py` | MetaFlow generation |
| **Workflow** | `/src/intent_builder/generators/workflow_generator.py` | Workflow YAML generation |
| | `/src/base_app/base_app/base_agent/workflows/workflow_loader.py` | Workflow loading & validation |
| **BaseAgent** | `/src/base_app/base_app/base_agent/core/base_agent.py` | Core BaseAgent class |
| | `/src/base_app/base_app/base_agent/core/agent_workflow_engine.py` | Workflow execution engine |
| | `/src/base_app/base_app/base_agent/agents/` | Agent type implementations |
| **Backend APIs** | `/src/cloud_backend/main.py` | FastAPI endpoints |
| **Extension** | `/src/clients/chrome-extension/public/manifest.json` | Extension manifest |
| | `/src/clients/chrome-extension/public/background.js` | Service worker |

---

## 8. EXECUTION EXAMPLES

### 8.1 Complete Recording to Execution Flow

```
1. USER STARTS RECORDING
   RecordPage.jsx: User enters title "Collect Amazon Prices"
                    ↓
   POST /api/recording/start
                    ↓
   Backend creates session: rec_xyz123
                    ↓
   chrome.tabs.sendMessage('startRecording', rec_xyz123)
                    ↓
   Content script injects behavior_tracker.js

2. USER PERFORMS ACTIONS
   User navigates to amazon.com
   User searches for "laptop"
   User clicks filters
   User scrolls results
                    ↓
   Each action captured by behavior_tracker.js
                    ↓
   Sent via postMessage → recorder.js → background.js
                    ↓
   POST /api/recording/operation (for each operation)

3. USER STOPS RECORDING
   Click "Stop Recording" button
                    ↓
   POST /api/recording/stop
                    ↓
   Returns: 42 operations captured
                    ↓
   RecordPage.jsx navigates to MetaflowPage
                    ↓
   Operations passed to MetaflowPage component

4. GENERATE METAFLOW
   Option A: Auto-generate via backend
            POST /api/intents/extract (future endpoint)
            Returns: MetaFlow YAML with 5 nodes
   
   Option B: Manual in UI
            User sees captured operations
            Customizes MetaFlow interactively

5. GENERATE WORKFLOW
   MetaflowPage → WorkflowGenerationPage
                    ↓
   WorkflowGenerator.generate(metaflow)
                    ↓
   LLM generates workflow.yaml
                    ↓
   Validate YAML structure
                    ↓
   Save to backend: POST /api/agents/build

6. EXECUTE WORKFLOW
   WorkflowDetailPage: Click "Execute"
                    ↓
   GET /api/agents/workflow/amazon-laptop-prices/execute
                    ↓
   Backend creates task: task_amazon-laptop-prices_abc123
                    ↓
   BaseAgent loads workflow.yaml
                    ↓
   For each step:
     - Execute agent type
     - Capture output
     - Update task status
   
   Background: GET /api/agents/workflow/task/task_.../status
              (polling every 1 second)
   
                    ↓
   Workflow completes
                    ↓
   Results saved to database
                    ↓
   Display: WorkflowResultPage
            Shows extracted prices, execution time, step details
```

### 8.2 Sample Workflow YAML Generated

```yaml
apiVersion: ami.io/v1
kind: Workflow
metadata:
  name: amazon-laptop-collection
  version: 1.0

inputs:
  - name: search_keyword
    type: string
    description: Product to search for
    default: laptop

outputs:
  - name: products
    type: array
    description: Collected product information

steps:
  - id: navigate_amazon
    name: Navigate to Amazon
    agent_type: browser_agent
    config:
      action: navigate
      url: https://www.amazon.com

  - id: search_products
    name: Search for Products
    agent_type: tool_agent
      1. Find the search input field
      2. Enter the keyword {{search_keyword}}
      3. Click the search button
      4. Wait for results to load
    config:
      tool: browser
      actions:
        - action: fill_input
          selector: "#twotabsearchtextbox"
          value: "{{search_keyword}}"
        - action: click
          selector: ".s-button"
        - action: wait
          condition: "page_has_results"
          timeout: 10

  - id: extract_results
    name: Extract Product Information
    agent_type: code_agent
    config:
      code: |
        import json
        products = []
        for item in page.select("[data-component-type='s-search-result']"):
          try:
            product = {
              "name": item.select_one("h2 a span").text,
              "price": item.select_one("[class*='a-price-whole']").text,
              "rating": item.select_one("[class*='a-star-small'] span").text
            }
            products.append(product)
          except:
            pass
        return json.dumps(products, ensure_ascii=False)

  - id: format_output
    name: Format Results
    agent_type: variable
    config:
      assign:
        final_products: "{{products}}"

final_response:
  type: outputs
  return: final_products
```

---

## CONCLUSION

The Ami system provides a complete closed-loop interface for:
1. Recording user behavior via Chrome extension
2. Extracting semantic intents from operations
3. Generating executable workflows
4. Running workflows with browser automation
5. Storing and retrieving results

The current implementation covers the core pipeline, with remaining gaps primarily in UI integration, error recovery, and advanced workflow customization features.
