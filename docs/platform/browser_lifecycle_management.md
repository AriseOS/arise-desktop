# Browser Lifecycle Management Design

**Version**: 1.0
**Date**: 2025-11-15
**Status**: Design Phase

## Table of Contents

- [Overview](#overview)
- [Requirements Analysis](#requirements-analysis)
- [User Scenarios](#user-scenarios)
- [State Machine Design](#state-machine-design)
- [Architecture Design](#architecture-design)
- [Implementation Plan](#implementation-plan)
- [API Specification](#api-specification)

---

## Overview

### Background

The current browser management implementation has the following limitations:

1. **Browser lifecycle is bound to daemon startup/shutdown** - browser starts with daemon and runs continuously
2. **No user control** - users cannot show/hide or start/stop the browser from the frontend
3. **Static headless configuration** - cannot switch between headless and headed modes at runtime
4. **Poor window management** - browser window appears separately without integration with the app
5. **No auto-recovery** - when browser is closed or crashes, system cannot recover automatically

### Goals

1. **On-demand browser management** - start browser only when needed, close when done
2. **User-controllable** - frontend can control browser state (start/stop/show/hide)
3. **Window integration** - automatic window arrangement for better user experience
4. **Auto-recovery** - detect connection loss and recover appropriately
5. **Transparent state** - frontend always knows browser status

---

## Requirements Analysis

### Confirmed User Requirements

Based on user feedback, the following requirements are confirmed:

#### 1. Recording End
✅ **Browser automatically closes after recording stops**
- No need to keep browser running after recording
- Clean resource usage

#### 2. User Manually Closes Browser
✅ **Stop recording and notify user**
- Detect CDP disconnection
- Save recorded operations so far
- Frontend displays: "Browser was closed. Recording stopped. X operations saved."
- Do not auto-restart (respect user action)

#### 3. Workflow Execution
✅ **Display browser during execution**
- User needs to see execution progress
- Start browser in headed mode (`headless=False`)
- Auto-arrange windows
- User can observe each step

#### 4. Window Arrangement
✅ **User-adjustable layout with browser taking more space**
- Initial layout: App 30-40% (left), Browser 60-70% (right)
- Remember user's manual adjustments
- Restore user preference on next launch

#### 5. App Exit
✅ **Browser automatically closes when app exits**
- Clean shutdown
- No orphaned browser processes

---

## User Scenarios

### Scenario 1: Application Startup

**User Action**: Launch Ami Desktop App

**System Behavior**:
```
App starts
    ↓
BrowserManager initializes (but does NOT start browser)
    ↓
App displays ready state
    ↓
Browser: NOT_STARTED
```

**Rationale**:
- Save resources when user doesn't need browser immediately
- Faster app startup

---

### Scenario 2: Start Recording

**User Action**: Click "Start Recording" button

**System Behavior**:
```
User clicks "Start Recording"
    ↓
Check browser state
    ↓ NOT_STARTED
Start browser (headless=False)
    ↓
Wait for browser ready (2-3 seconds)
    ↓
Auto-arrange windows:
    - App: Left 35%
    - Browser: Right 65%
    ↓
Navigate to target URL
    ↓
Start monitoring user operations
    ↓
Browser: RUNNING
Recording: IN_PROGRESS
```

**User Experience**:
- Browser window appears automatically
- Windows arranged side-by-side
- User can immediately start demonstrating

---

### Scenario 3: User Hides Browser During Recording

**User Action**: Click "Hide Browser" button (future feature)

**System Behavior**:
```
User clicks "Hide Browser"
    ↓
Minimize browser window
    ↓
App shows: "Browser Hidden - Click to Show"
    ↓
Recording continues in background
    ↓
Browser: RUNNING (but window hidden)
```

**Note**: This is a future enhancement, not in initial scope.

---

### Scenario 4: Recording End

**User Action**: Click "Stop Recording" button

**System Behavior**:
```
User clicks "Stop Recording"
    ↓
Stop monitoring
    ↓
Save operations to local storage
    ↓
Close browser
    ↓
Display summary: "Recording saved: X operations"
    ↓
Browser: STOPPED
```

**User Experience**:
- Clean end to recording session
- Browser automatically closes
- Resources freed

---

### Scenario 5: User Manually Closes Browser During Recording

**User Action**: Click browser window's X button

**System Behavior**:
```
User closes browser window
    ↓
CDP connection lost detected
    ↓
Health check detects disconnection
    ↓
Check process exists? NO (user closed)
    ↓
Stop recording immediately
    ↓
Save operations recorded so far
    ↓
Notify frontend:
    "Browser was closed. Recording stopped.
     Saved X operations."
    ↓
Browser: STOPPED
Recording: STOPPED
```

**User Experience**:
- Recording stops gracefully
- No data loss - operations are saved
- Clear notification about what happened

**Important**: Do NOT auto-restart browser - respect user action.

---

### Scenario 6: Execute Workflow

**User Action**: Click "Execute Workflow" button

**System Behavior**:
```
User clicks "Execute Workflow"
    ↓
Check browser state
    ↓ NOT_STARTED or STOPPED
Start browser (headless=False)
    ↓
Wait for browser ready
    ↓
Auto-arrange windows
    ↓
Execute workflow steps
    ↓
Display progress in browser
    ↓
Workflow completes
    ↓
Option A: Keep browser running
Option B: Close browser after execution
```

**User Experience**:
- User sees each automation step
- Browser window shows execution progress
- Transparent execution

---

### Scenario 7: Browser Crashes

**System Behavior**:
```
CDP connection lost detected
    ↓
Check process exists?
    ↓ NO (process died)
Check last known state:

Case A: Recording in progress
    ↓
    Save operations so far
    ↓
    Stop recording
    ↓
    Notify: "Browser crashed. Recording stopped. X operations saved."
    ↓
    Browser: ERROR → STOPPED

Case B: Idle state
    ↓
    Mark as stopped
    ↓
    Notify: "Browser closed unexpectedly"
    ↓
    Browser: STOPPED
```

**Note**: Do not auto-restart on crash - let user decide next action.

---

### Scenario 8: User Manually Starts Browser

**User Action**: Click "Open Browser" button in app (future feature)

**System Behavior**:
```
User clicks "Open Browser"
    ↓
Check browser state
    ↓
Case A: Already running
    ↓
    Show notification: "Browser already running"
    ↓
    If window hidden: restore window

Case B: Not running
    ↓
    Start browser (headless=False)
    ↓
    Auto-arrange windows
    ↓
    Navigate to about:blank or user homepage
    ↓
    Browser: RUNNING
```

---

### Scenario 9: Application Exit

**User Action**: Close Ami Desktop App

**System Behavior**:
```
App receives shutdown signal
    ↓
Check if tasks in progress:

Case A: Recording or execution in progress
    ↓
    Show confirmation:
        "Tasks in progress. Exit anyway?"
        [Cancel] [Save & Exit] [Exit Without Saving]
    ↓
    If "Save & Exit":
        Save current state
        Stop tasks
        Close browser
        Exit app

Case B: No active tasks
    ↓
    Close browser
    ↓
    Cleanup resources
    ↓
    Exit app
```

---

## State Machine Design

### Browser States

```
┌─────────────┐
│ NOT_STARTED │ ← Initial state
└──────┬──────┘
       │ start_browser()
       ↓
┌─────────────┐
│  STARTING   │ ← Starting browser (2-3 seconds)
└──────┬──────┘
       │ startup_complete
       ↓
┌─────────────┐
│   RUNNING   │ ← Browser running, window visible
└──┬───┬───┬──┘
   │   │   │
   │   │   └─→ stop_browser() ──→ ┌──────────┐
   │   │                          │ STOPPING │
   │   │                          └────┬─────┘
   │   │                               │
   │   │                               ↓
   │   │                          ┌─────────┐
   │   │                          │ STOPPED │ ← Browser stopped
   │   │                          └─────────┘
   │   │
   │   └─→ connection_lost (user closed) ──→ STOPPED
   │
   └─→ connection_lost (crash) ──→ ┌─────────┐
                                    │  ERROR  │ ← Error state
                                    └────┬────┘
                                         │
                                         └─→ STOPPED
```

### State Transitions

| Current State | Event | Next State | Actions |
|--------------|-------|------------|---------|
| NOT_STARTED | start_browser() | STARTING | Initialize browser session |
| STARTING | startup_complete | RUNNING | Mark as ready, start health check |
| STARTING | startup_failed | ERROR | Log error, cleanup |
| RUNNING | stop_browser() | STOPPING | Stop health check, close session |
| RUNNING | connection_lost (user) | STOPPED | Save state, notify user |
| RUNNING | connection_lost (crash) | ERROR | Save state, notify error |
| STOPPING | cleanup_complete | STOPPED | Clear resources |
| ERROR | - | STOPPED | Auto-transition after logging |
| STOPPED | start_browser() | STARTING | Restart browser |

---

## Architecture Design

### Component Overview

```
┌─────────────────────────────────────────────────────────┐
│                  App Backend (daemon.py)                 │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────────────────────────┐              │
│  │       BrowserManager                 │              │
│  │  ─────────────────────────           │              │
│  │  - state: BrowserState               │              │
│  │  - session_manager                   │              │
│  │  - global_session                    │              │
│  │  - browser_pid                       │              │
│  │  - health_check_task                 │              │
│  │                                       │              │
│  │  Methods:                             │              │
│  │  + start_browser(headless)           │              │
│  │  + stop_browser(force)               │              │
│  │  + get_status()                      │              │
│  │  - _health_check_loop()              │              │
│  │  - _check_cdp_alive()                │              │
│  │  - _handle_connection_lost()         │              │
│  └────────────┬─────────────────────────┘              │
│               │                                          │
│               ↓                                          │
│  ┌──────────────────────────────────────┐              │
│  │   BrowserWindowManager               │              │
│  │  ─────────────────────────           │              │
│  │  - platform: str                     │              │
│  │  - user_preference: dict             │              │
│  │                                       │              │
│  │  Methods:                             │              │
│  │  + arrange_windows(app_rect, pid)    │              │
│  │  + save_user_preference()            │              │
│  │  + restore_layout()                  │              │
│  │  - _set_window_position_macos()      │              │
│  │  - _set_window_position_windows()    │              │
│  │  - _set_window_position_linux()      │              │
│  │  - _get_screen_size()                │              │
│  └──────────────────────────────────────┘              │
│                                                          │
│  ┌──────────────────────────────────────┐              │
│  │   BrowserEventNotifier               │              │
│  │  ─────────────────────────           │              │
│  │  - callbacks: List[Callable]         │              │
│  │                                       │              │
│  │  Methods:                             │              │
│  │  + subscribe(callback)               │              │
│  │  + notify(event_type, data)          │              │
│  └──────────────────────────────────────┘              │
│                                                          │
└─────────────────────────────────────────────────────────┘
                         ↑ HTTP API
                         │
┌─────────────────────────────────────────────────────────┐
│              Desktop App (Tauri Frontend)                │
│  ────────────────────────────────────────               │
│  - Browser status indicator                             │
│  - Recording control buttons                            │
│  - Window position adjustment                           │
│  - Event notifications                                  │
└─────────────────────────────────────────────────────────┘
```

### Component Responsibilities

#### BrowserManager

**Purpose**: Core browser lifecycle management

**Responsibilities**:
1. Start/stop browser processes
2. Maintain browser state machine
3. Health check and connection monitoring
4. Handle connection loss events
5. Notify frontend of state changes

**Key Methods**:
- `start_browser(headless: bool)`: Start browser on demand
- `stop_browser(force: bool)`: Gracefully stop browser
- `get_status()`: Return current browser state and details
- `_health_check_loop()`: Continuous health monitoring
- `_check_cdp_alive()`: Validate CDP connection
- `_handle_connection_lost()`: Handle disconnection scenarios

#### BrowserWindowManager

**Purpose**: Cross-platform window positioning and layout management

**Responsibilities**:
1. Auto-arrange app and browser windows
2. Save/restore user window preferences
3. Platform-specific window control (macOS/Windows/Linux)
4. Screen size detection

**Key Methods**:
- `arrange_windows(app_rect, browser_pid)`: Position windows side-by-side
- `save_user_preference(app_rect, browser_rect)`: Persist user layout
- `_set_window_position_*()`: Platform-specific window APIs

**Platform APIs**:
- **macOS**: AppleScript for window control
- **Windows**: Win32 API (SetWindowPos)
- **Linux**: wmctrl command-line tool

#### BrowserEventNotifier

**Purpose**: Event-driven communication between components

**Responsibilities**:
1. Subscribe/notify pattern for browser events
2. Decouple browser manager from other components
3. Enable frontend notifications

**Events**:
- `browser_started`: Browser successfully started
- `browser_stopped`: Browser stopped
- `browser_closed`: User manually closed browser
- `browser_crashed`: Browser process crashed
- `connection_lost`: CDP connection lost

---

## Implementation Plan

### Phase 1: Core Browser Management (2-3 days)

**Objectives**:
- Implement BrowserManager with state machine
- Health check mechanism
- Connection loss detection

**Tasks**:
1. Create `BrowserState` enum
2. Refactor `BrowserManager` to support on-demand startup
3. Implement `start_browser()` and `stop_browser()` methods
4. Add health check loop
5. Implement connection loss handler
6. Unit tests for state transitions

**Deliverables**:
- `src/app_backend/services/browser_manager.py` (refactored)
- `tests/unit/test_browser_manager.py`

---

### Phase 2: Window Management (3-4 days)

**Objectives**:
- Cross-platform window positioning
- User preference storage

**Tasks**:
1. Create `BrowserWindowManager` class
2. Implement macOS window control (AppleScript)
3. Implement Windows window control (Win32 API)
4. Implement Linux window control (wmctrl)
5. Add screen size detection
6. Implement preference save/restore
7. Integration tests on all platforms

**Deliverables**:
- `src/app_backend/services/window_manager.py`
- `~/.ami/window_preference.json` (user config)
- `tests/integration/test_window_manager.py`

---

### Phase 3: API Integration (1 day)

**Objectives**:
- Expose browser control to frontend
- Modify existing recording/execution APIs

**Tasks**:
1. Add `/api/browser/start` endpoint
2. Add `/api/browser/stop` endpoint
3. Add `/api/browser/status` endpoint
4. Add `/api/browser/windows/save-preference` endpoint
5. Modify `/api/recording/start` to auto-start browser
6. Modify `/api/recording/stop` to auto-close browser
7. API documentation

**Deliverables**:
- `src/app_backend/daemon.py` (updated)
- `docs/platform/browser_management_api.md`

---

### Phase 4: Event Notification (1-2 days)

**Objectives**:
- Event-driven architecture
- Frontend notifications

**Tasks**:
1. Create `BrowserEventNotifier` class
2. Integrate with `BrowserManager`
3. Subscribe `CDPRecorder` to browser events
4. Add WebSocket support for real-time notifications (optional)
5. Integration tests

**Deliverables**:
- `src/app_backend/services/event_notifier.py`
- Updated `CDPRecorder` to handle browser_closed event

---

### Phase 5: Frontend Integration (2-3 days)

**Objectives**:
- UI for browser status
- User preference UI

**Tasks**:
1. Add browser status indicator to UI
2. Add "Close Browser" button (if needed)
3. Window layout adjustment controls
4. Event notification display
5. E2E tests

**Deliverables**:
- Updated frontend components
- E2E test suite

---

### Timeline

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1 | 2-3 days | None |
| Phase 2 | 3-4 days | Phase 1 |
| Phase 3 | 1 day | Phase 1 |
| Phase 4 | 1-2 days | Phase 1 |
| Phase 5 | 2-3 days | Phase 1, 2, 3, 4 |
| **Total** | **9-13 days** | |

---

## API Specification

### Browser Control APIs

#### POST /api/browser/start

Start browser on demand.

**Request Body**:
```json
{
  "headless": false
}
```

**Response**:
```json
{
  "status": "started",
  "pid": 12345,
  "state": "running"
}
```

**Status Codes**:
- `200`: Browser started successfully
- `409`: Browser already running
- `500`: Failed to start browser

---

#### POST /api/browser/stop

Stop browser gracefully.

**Request Body**: None

**Response**:
```json
{
  "status": "stopped"
}
```

**Status Codes**:
- `200`: Browser stopped successfully
- `404`: Browser not running
- `500`: Failed to stop browser

---

#### GET /api/browser/status

Get current browser status.

**Response**:
```json
{
  "state": "running",
  "pid": 12345,
  "is_running": true,
  "session_exists": true,
  "window_visible": true,
  "last_health_check": "2025-11-15T10:30:00Z"
}
```

**Browser States**:
- `not_started`: Browser has not been started
- `starting`: Browser is starting up
- `running`: Browser is running normally
- `stopping`: Browser is shutting down
- `stopped`: Browser has stopped
- `error`: Browser encountered an error

---

#### POST /api/browser/windows/save-preference

Save user's window layout preference.

**Request Body**:
```json
{
  "app_rect": {
    "x": 0,
    "y": 0,
    "width": 600,
    "height": 1080
  },
  "browser_rect": {
    "x": 600,
    "y": 0,
    "width": 1320,
    "height": 1080
  }
}
```

**Response**:
```json
{
  "status": "saved"
}
```

---

### Modified Recording APIs

#### POST /api/recording/start

**New Behavior**:
1. Check if browser is running
2. If not, start browser (headless=False)
3. Wait for browser ready
4. Auto-arrange windows (app 35% left, browser 65% right)
5. Navigate to target URL
6. Start recording

**Request/Response**: Same as before

---

#### POST /api/recording/stop

**New Behavior**:
1. Stop recording
2. Save operations
3. **Close browser automatically**
4. Return recording summary

**Request/Response**: Same as before

---

### Event Notifications

#### Browser Events (Future: WebSocket)

**Event Types**:

1. **browser_started**
```json
{
  "event": "browser_started",
  "data": {
    "pid": 12345,
    "timestamp": "2025-11-15T10:30:00Z"
  }
}
```

2. **browser_stopped**
```json
{
  "event": "browser_stopped",
  "data": {
    "reason": "user_request",
    "timestamp": "2025-11-15T10:35:00Z"
  }
}
```

3. **browser_closed**
```json
{
  "event": "browser_closed",
  "data": {
    "reason": "user_action",
    "timestamp": "2025-11-15T10:32:00Z",
    "operations_saved": 42
  }
}
```

4. **browser_crashed**
```json
{
  "event": "browser_crashed",
  "data": {
    "timestamp": "2025-11-15T10:31:00Z",
    "error": "Process terminated unexpectedly"
  }
}
```

---

## Window Layout Specification

### Default Layout

**Screen**: 1920x1080 (example)

```
┌──────────────────────────────────────────────────────┐
│                     Screen (1920x1080)                │
├────────────────────┬─────────────────────────────────┤
│                    │                                  │
│   Ami App (35%)    │    Browser Window (65%)         │
│   672 x 1080       │    1248 x 1080                  │
│                    │                                  │
│  ┌──────────────┐  │  ┌────────────────────────────┐ │
│  │ Recording UI │  │  │  Chrome Browser            │ │
│  │              │  │  │                            │ │
│  │ - Start Rec  │  │  │  User demonstrates tasks   │ │
│  │ - Stop Rec   │  │  │                            │ │
│  │ - Status     │  │  │                            │ │
│  │              │  │  │                            │ │
│  └──────────────┘  │  └────────────────────────────┘ │
│                    │                                  │
└────────────────────┴─────────────────────────────────┘
```

### User Preference

**Saved in**: `~/.ami/window_preference.json`

**Format**:
```json
{
  "app_rect": {
    "x": 0,
    "y": 0,
    "width": 600,
    "height": 1080
  },
  "browser_rect": {
    "x": 600,
    "y": 0,
    "width": 1320,
    "height": 1080
  },
  "version": "1.0",
  "last_updated": "2025-11-15T10:30:00Z"
}
```

---

## Testing Strategy

### Unit Tests

**BrowserManager**:
- State transitions
- Health check logic
- Connection loss handling
- Error scenarios

**BrowserWindowManager**:
- Screen size detection
- Window positioning calculations
- Preference save/load

### Integration Tests

**Browser Lifecycle**:
- Start browser → Arrange windows → Stop browser
- Connection loss detection → State update
- User closes browser → Recording stops

**Window Management**:
- Auto-arrange on different screen sizes
- Restore user preference
- Cross-platform compatibility

### E2E Tests

**Recording Flow**:
1. User starts recording
2. Browser appears and arranges automatically
3. User demonstrates task
4. User stops recording
5. Browser closes automatically

**User Closes Browser**:
1. Recording in progress
2. User closes browser window
3. Recording stops
4. Notification displayed
5. Operations saved

---

## Future Enhancements

### Phase 2 Features (Future)

1. **Show/Hide Browser**
   - Hide browser window without closing process
   - Restore window position

2. **Screenshot Stream**
   - Headless mode with screenshot preview
   - Embed browser view in app

3. **Multi-Browser Support**
   - Support different browsers (Firefox, Edge)
   - Browser selection in settings

4. **Advanced Window Management**
   - Drag-and-drop window resizing
   - Multiple monitor support
   - Saved layouts (e.g., "recording mode", "execution mode")

5. **Auto-Recovery**
   - Automatic browser restart on crash (during execution)
   - State restoration after recovery

---

## Appendix

### Platform-Specific Implementation Notes

#### macOS

**Window Control**: AppleScript
```applescript
tell application "System Events"
    set appProcess to first process whose unix id is {pid}
    tell appProcess
        set position of window 1 to {x, y}
        set size of window 1 to {width, height}
    end tell
end tell
```

**Permissions Required**:
- Accessibility permissions for window control
- User must grant permission in System Preferences

#### Windows

**Window Control**: Win32 API (ctypes)
```python
import ctypes
ctypes.windll.user32.SetWindowPos(
    hwnd, None, x, y, width, height, 0
)
```

**Challenges**:
- Find window handle by PID
- Handle multiple windows from same process

#### Linux

**Window Control**: wmctrl
```bash
wmctrl -lp  # List windows with PIDs
wmctrl -i -r {window_id} -e 0,{x},{y},{width},{height}
```

**Dependencies**:
- `wmctrl` package must be installed
- Works with X11 (not Wayland by default)

---

## Changelog

### Version 1.0 (2025-11-15)
- Initial design document
- Requirements analysis from user feedback
- State machine design
- Architecture specification
- Implementation plan

---

## References

- [App Backend Design](./app_backend_design.md)
- [Desktop App UI Design](./desktop_app_ui_design.md)
- [Desktop App Features](./desktop_app_features.md)
