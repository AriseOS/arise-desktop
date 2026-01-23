# Frontend Migration Plan

**Status: IMPLEMENTED**

## Overview

This document outlines the migration of frontend features from eigent to 2ami QuickTaskPage, enabling full support for the 4 backend migration features.

## Current State

| Feature | 2ami QuickTaskPage | eigent Frontend | Gap |
|---------|-------------------|-----------------|-----|
| Conversation History | ❌ None | ✅ ChatBox components | Need full implementation |
| Event System | WebSocket | SSE + 59 event types | Need migration |
| Toolkit Display | Basic tool history | Full toolkit status UI | Need upgrade |
| Working Directory | ❌ None | File browser + Terminal | Need implementation |

## Migration Priority

1. **SSE Event System** - Foundation for all other features
2. **Conversation History UI** - Core interaction
3. **Toolkit Status Display** - Enhanced UX
4. **Working Directory Browser** - Advanced feature

---

## Phase 1: SSE Event System Migration

### 1.1 Replace WebSocket with SSE

**Current** (`QuickTaskPage.jsx`):
```javascript
const ws = new WebSocket(wsUrl);
ws.onmessage = (event) => { ... };
```

**Target**:
```javascript
import { fetchEventSource } from '@microsoft/fetch-event-source';

fetchEventSource(sseUrl, {
  signal: abortController.signal,
  onmessage(event) {
    const data = JSON.parse(event.data);
    handleSSEEvent(data);
  }
});
```

### 1.2 Event Type Mapping

Backend events (from `action_types.py`) to frontend handlers:

| Backend Event | Frontend Action |
|---------------|-----------------|
| `task_started` | Set status to running |
| `agent_created` | Add agent to list |
| `agent_activated` | Update agent status |
| `toolkit_started` | Show toolkit executing |
| `toolkit_completed` | Update toolkit result |
| `tool_started` | Add to tool history |
| `tool_completed` | Update tool result |
| `human_question` | Show question modal |
| `message_added` | Add to conversation |
| `task_completed` | Set status to completed |
| `task_failed` | Set status to failed |

### 1.3 Files to Modify

- `src/clients/desktop_app/src/pages/QuickTaskPage.jsx`
- `src/clients/desktop_app/src/utils/sseClient.js` (new)

---

## Phase 2: Conversation History UI

### 2.1 Component Structure

```
components/
├── ChatBox/
│   ├── index.jsx              # Main container
│   ├── MessageList.jsx        # Scrollable message list
│   ├── MessageItem/
│   │   ├── UserMessage.jsx    # User message card
│   │   ├── AgentMessage.jsx   # Agent message card
│   │   └── NoticeCard.jsx     # System notice
│   └── InputBox.jsx           # Message input
```

### 2.2 Message Types

```javascript
// From backend ConversationEntry
const MessageType = {
  USER: 'user',
  ASSISTANT: 'assistant',
  SYSTEM: 'system',
  TOOL_RESULT: 'tool_result'
};
```

### 2.3 State Structure

```javascript
const [conversation, setConversation] = useState({
  messages: [],      // ConversationEntry[]
  summary: null,     // Conversation summary
  metadata: {}       // Additional context
});
```

---

## Phase 3: Toolkit Status Display

### 3.1 Component Structure

```
components/
├── TaskBox/
│   ├── TaskCard.jsx           # Task card with progress
│   ├── TaskItem.jsx           # Individual task item
│   └── TaskState.jsx          # Status filter tags
├── ToolkitStatus/
│   ├── ToolkitCard.jsx        # Toolkit execution card
│   └── ToolkitProgress.jsx    # Progress indicator
```

### 3.2 Toolkit Status States

```javascript
const ToolkitStatus = {
  PENDING: 'pending',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed'
};
```

### 3.3 Data Structure

```javascript
// From backend toolkit events
const toolkitEvent = {
  toolkit_name: string,
  method_name: string,
  status: ToolkitStatus,
  message: string,
  inputs: object,
  outputs: object,
  timestamp: string
};
```

---

## Phase 4: Working Directory Browser

### 4.1 Component Structure

```
components/
├── Workspace/
│   ├── FileBrowser.jsx        # File tree browser
│   ├── FileItem.jsx           # File/folder item
│   └── Terminal.jsx           # Terminal output (xterm.js)
```

### 4.2 File Operations

```javascript
// API endpoints
GET  /api/v1/workspace/{task_id}/files
GET  /api/v1/workspace/{task_id}/file/{path}
POST /api/v1/workspace/{task_id}/file/{path}
```

### 4.3 Terminal Integration

Use `@xterm/xterm` package (same as eigent):
```javascript
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
```

---

## Implementation Checklist

### Phase 1: SSE Event System
- [x] Create `sseClient.js` utility (uses native fetch, no external dependency needed)
- [x] Replace WebSocket with SSE in QuickTaskPage
- [x] Map 59 event types to handlers
- [x] Add AbortController for cleanup

### Phase 2: Conversation History
- [x] Create ChatBox component (`src/components/ChatBox/index.jsx`)
- [x] Create MessageList component (`src/components/ChatBox/MessageList.jsx`)
- [x] Create UserMessage component (`src/components/ChatBox/MessageItem/UserMessage.jsx`)
- [x] Create AgentMessage component (`src/components/ChatBox/MessageItem/AgentMessage.jsx`)
- [x] Create NoticeCard component (`src/components/ChatBox/MessageItem/NoticeCard.jsx`)
- [x] Add auto-scroll behavior
- [x] Add Markdown rendering (using existing react-markdown)

### Phase 3: Toolkit Status
- [x] Create TaskCard component (`src/components/TaskBox/TaskCard.jsx`)
- [x] Create TaskState component (`src/components/TaskBox/TaskState.jsx`)
- [x] Add status filtering
- [x] Add progress indicator

### Phase 4: Working Directory
- [x] Create FileBrowser component (`src/components/Workspace/FileBrowser.jsx`)
- [x] Create TerminalOutput component (`src/components/Workspace/TerminalOutput.jsx`)
- [x] Connect to backend workspace API

---

## CSS Styles

All new components should follow existing style patterns in:
- `src/clients/desktop_app/src/styles/QuickTaskPage.css`

New style files:
- `ChatBox.css`
- `TaskBox.css`
- `Workspace.css`

---

## Testing

1. **SSE Connection**: Verify event stream connects and receives events
2. **Message Display**: Verify all message types render correctly
3. **Toolkit Status**: Verify toolkit events update UI in real-time
4. **File Browser**: Verify file listing and content display
5. **Terminal**: Verify terminal output updates correctly

---

## Dependencies

No new dependencies required. Implementation uses:
- Native `fetch` API for SSE streaming
- Existing `react-markdown` for markdown rendering
- Simple terminal output display (not full xterm.js)

---

## Files Created

```
src/clients/desktop_app/src/
├── utils/
│   └── sseClient.js              # SSE client utility
├── components/
│   ├── ChatBox/
│   │   ├── index.jsx             # Main ChatBox component
│   │   ├── MessageList.jsx       # Message list with auto-scroll
│   │   ├── ChatBox.css           # ChatBox styles
│   │   └── MessageItem/
│   │       ├── index.js          # Exports
│   │       ├── UserMessage.jsx   # User message card
│   │       ├── AgentMessage.jsx  # Agent message card
│   │       └── NoticeCard.jsx    # System notice card
│   ├── TaskBox/
│   │   ├── index.js              # Exports
│   │   ├── TaskCard.jsx          # Task progress card
│   │   ├── TaskState.jsx         # Status filter badges
│   │   └── TaskBox.css           # TaskBox styles
│   ├── Workspace/
│   │   ├── index.js              # Exports
│   │   ├── FileBrowser.jsx       # File tree browser
│   │   ├── FilePreview.jsx       # File content preview
│   │   ├── TerminalOutput.jsx    # Terminal output display
│   │   └── Workspace.css         # Workspace styles
│   ├── AgentNode/
│   │   ├── index.js              # Exports
│   │   ├── AgentNode.jsx         # Single agent display
│   │   ├── AgentsPanel.jsx       # Multi-agent container
│   │   └── AgentStatusBar.jsx    # Compact agent status bar
│   ├── TokenUsage/
│   │   ├── index.js              # Exports
│   │   ├── TokenUsage.jsx        # Token usage display
│   │   └── BudgetConfigDialog.jsx # Budget configuration dialog
│   └── HumanInteraction/
│       ├── index.js              # Exports
│       ├── HumanInteractionModal.jsx  # Human interaction modal
│       ├── HumanInteractionCard.jsx   # Inline interaction card
│       └── HumanMessagesContainer.jsx # Toast messages container
└── pages/
    └── QuickTaskPage.jsx         # Updated with SSE and new components
```

---

## Additional Components (Not Yet Implemented)

The following components are referenced in CSS but not yet implemented:

- **TaskDecomposition**: Task decomposition panel (eigent's task breakdown flow - skipped per user request)
- **IntegrationList**: Integration/plugin management list
- **DecompositionSummary**: Compact summary of decomposed subtasks
