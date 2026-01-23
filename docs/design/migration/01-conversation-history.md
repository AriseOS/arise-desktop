# Feature 1: Conversation History & Context Management

## Current State Analysis

### Eigent Implementation

**Location:** `third-party/eigent/backend/app/service/task.py` (lines 260-363)

Eigent uses `TaskLock` class to manage conversation history:

```python
class TaskLock:
    conversation_history: List[Dict[str, Any]]
    """Store conversation history for context"""
    last_task_result: str
    """Store the last task execution result"""

    def add_conversation(self, role: str, content: str | dict):
        """Add a conversation entry to history"""
        self.conversation_history.append({
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat()
        })

    def get_recent_context(self, max_entries: int = None) -> str:
        """Get recent conversation context as a formatted string"""
        if not self.conversation_history:
            return ""
        context = "=== Recent Conversation ===\n"
        history_to_use = self.conversation_history if max_entries is None else self.conversation_history[-max_entries:]
        for entry in history_to_use:
            context += f"{entry['role']}: {entry['content']}\n"
        return context
```

Key features:
1. **Timestamp tracking** - Each conversation entry has ISO timestamp
2. **Role-based entries** - Supports roles: `user`, `assistant`, `task_result`
3. **Length management** - `check_conversation_history_length()` caps at 100KB
4. **Context building** - `build_conversation_context()` formats history for LLM prompt

### 2ami Current State

**Location:** `src/clients/desktop_app/ami_daemon/services/quick_task_service.py` (lines 33-70)

Current `TaskState` has:
```python
@dataclass
class TaskState:
    task_id: str
    task: str
    start_url: Optional[str]
    status: str  # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    plan: List[Dict[str, Any]]
    progress: float  # 0.0 to 1.0
    tools_called: List[Dict[str, Any]]  # Tool call history
    notes_content: str  # Notes created during execution
    loop_iteration: int
    # ... timestamps and queues
```

**Missing:**
- No `conversation_history` field
- No multi-turn context preservation
- Each task starts fresh without context from previous tasks

---

## Implementation Plan

### Step 1: Extend TaskState with Conversation History

**File:** `src/clients/desktop_app/ami_daemon/services/quick_task_service.py`

```python
from datetime import datetime
from typing import List, Dict, Any, Optional

@dataclass
class ConversationEntry:
    """Single conversation entry"""
    role: str  # 'user', 'assistant', 'task_result', 'tool_call'
    content: str | Dict[str, Any]
    timestamp: str  # ISO format

    def to_dict(self) -> Dict[str, Any]:
        return {
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp
        }

@dataclass
class TaskState:
    # ... existing fields ...

    # NEW: Conversation history for multi-turn context
    conversation_history: List[ConversationEntry] = field(default_factory=list)
    last_task_result: Optional[str] = None
    max_history_length: int = 100000  # 100KB max

    def add_conversation(self, role: str, content: str | Dict[str, Any]) -> None:
        """Add a conversation entry to history"""
        entry = ConversationEntry(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat()
        )
        self.conversation_history.append(entry)
        self._trim_history_if_needed()

    def _trim_history_if_needed(self) -> None:
        """Trim history if exceeds max length"""
        total_length = sum(
            len(str(e.content)) for e in self.conversation_history
        )
        while total_length > self.max_history_length and len(self.conversation_history) > 1:
            removed = self.conversation_history.pop(0)
            total_length -= len(str(removed.content))

    def get_recent_context(self, max_entries: Optional[int] = None) -> str:
        """Get recent conversation context as formatted string"""
        if not self.conversation_history:
            return ""

        context = "=== Recent Conversation ===\n"
        history = self.conversation_history
        if max_entries is not None:
            history = history[-max_entries:]

        for entry in history:
            if entry.role == 'task_result' and isinstance(entry.content, dict):
                context += f"Task Result:\n"
                if 'summary' in entry.content:
                    context += f"  Summary: {entry.content['summary']}\n"
                if 'files_created' in entry.content:
                    context += f"  Files: {entry.content['files_created']}\n"
            else:
                context += f"{entry.role.title()}: {entry.content}\n"
            context += "\n"

        return context

    def get_history_length(self) -> int:
        """Get total character length of conversation history"""
        return sum(len(str(e.content)) for e in self.conversation_history)
```

### Step 2: Add Context Building Utility

**File:** `src/clients/desktop_app/ami_daemon/services/context_builder.py` (NEW)

```python
"""
Context building utilities for conversation history management.
"""
import os
from pathlib import Path
from typing import Optional, Set
from .quick_task_service import TaskState


def build_conversation_context(
    state: TaskState,
    header: str = "=== CONVERSATION HISTORY ===",
    skip_files: bool = False
) -> str:
    """
    Build conversation context from task state history.
    Formats history for LLM prompt injection.
    """
    if not state.conversation_history:
        return ""

    context_parts = [header]
    working_directories: Set[str] = set()

    for entry in state.conversation_history:
        if entry.role == 'task_result':
            if isinstance(entry.content, dict):
                formatted = _format_task_result(entry.content, skip_files)
                context_parts.append(formatted)
                if entry.content.get('working_directory'):
                    working_directories.add(entry.content['working_directory'])
        elif entry.role == 'assistant':
            context_parts.append(f"Assistant: {entry.content}")
        elif entry.role == 'user':
            context_parts.append(f"User: {entry.content}")
        elif entry.role == 'tool_call':
            # Optionally include tool calls
            if isinstance(entry.content, dict):
                tool_name = entry.content.get('name', 'unknown')
                context_parts.append(f"Tool Call: {tool_name}")

    # Collect files from working directories if not skipped
    if not skip_files and working_directories:
        files_context = _collect_working_directory_files(working_directories)
        if files_context:
            context_parts.append(files_context)

    return "\n\n".join(context_parts)


def _format_task_result(result: dict, skip_files: bool = False) -> str:
    """Format a task result for context"""
    parts = ["Task Result:"]

    if result.get('task'):
        parts.append(f"  Task: {result['task']}")
    if result.get('summary'):
        parts.append(f"  Summary: {result['summary']}")
    if result.get('status'):
        parts.append(f"  Status: {result['status']}")
    if not skip_files and result.get('files_created'):
        parts.append(f"  Files Created: {', '.join(result['files_created'])}")

    return "\n".join(parts)


def _collect_working_directory_files(directories: Set[str]) -> str:
    """Collect file listing from working directories"""
    all_files = []

    for directory in directories:
        try:
            if os.path.exists(directory):
                for root, dirs, files in os.walk(directory):
                    # Skip hidden and common ignored directories
                    dirs[:] = [d for d in dirs if not d.startswith('.')
                               and d not in ['node_modules', '__pycache__', 'venv']]
                    for file in files:
                        if not file.startswith('.') and not file.endswith(('.pyc', '.tmp')):
                            file_path = os.path.join(root, file)
                            all_files.append(os.path.abspath(file_path))
        except Exception:
            continue

    if not all_files:
        return ""

    parts = ["Generated Files:"]
    for f in sorted(all_files)[:50]:  # Limit to 50 files
        parts.append(f"  - {f}")

    if len(all_files) > 50:
        parts.append(f"  ... and {len(all_files) - 50} more files")

    return "\n".join(parts)


def check_history_length(state: TaskState, max_length: int = 100000) -> tuple[bool, int]:
    """
    Check if conversation history exceeds maximum length.

    Returns:
        tuple: (is_exceeded, total_length)
    """
    total_length = state.get_history_length()
    return total_length > max_length, total_length
```

### Step 3: Integrate with Agent Execution

**File:** `src/clients/desktop_app/ami_daemon/base_agent/agents/eigent_style_browser_agent.py`

Add context injection before LLM call:

```python
async def _execute_with_context(self, task: str, state: TaskState) -> str:
    """Execute task with conversation history context"""

    # Build context from history
    context = build_conversation_context(state, skip_files=False)

    # Check if context is too long
    exceeded, length = check_history_length(state)
    if exceeded:
        # Summarize or truncate
        context = state.get_recent_context(max_entries=10)

    # Inject context into system prompt
    enhanced_prompt = f"""
{context}

=== CURRENT TASK ===
{task}
"""

    # Execute with enhanced prompt
    result = await self._run_agent_loop(enhanced_prompt)

    # Record task result in history
    state.add_conversation('task_result', {
        'task': task,
        'summary': result.get('summary', ''),
        'status': 'completed',
        'working_directory': state.working_directory
    })

    return result
```

### Step 4: Preserve Context Across Tasks

**File:** `src/clients/desktop_app/ami_daemon/services/quick_task_service.py`

Modify task continuation logic:

```python
async def continue_task(self, task_id: str, new_task: str) -> TaskState:
    """Continue a task with new instruction, preserving context"""

    state = self._task_states.get(task_id)
    if not state:
        raise ValueError(f"Task {task_id} not found")

    # Preserve conversation history even if task was done
    if state.status == 'COMPLETED':
        state.status = 'RUNNING'
        # Note: conversation_history and last_task_result are preserved

    # Add new user message to history
    state.add_conversation('user', new_task)

    # Update task
    state.task = new_task
    state.updated_at = datetime.now().isoformat()

    # Execute with context
    await self._execute_task_with_context(state)

    return state
```

---

## Migration Checklist

- [ ] Add `ConversationEntry` dataclass
- [ ] Extend `TaskState` with conversation fields
- [ ] Implement `add_conversation()` method
- [ ] Implement `get_recent_context()` method
- [ ] Implement `_trim_history_if_needed()` method
- [ ] Create `context_builder.py` utility module
- [ ] Integrate context building in agent execution
- [ ] Add context preservation in task continuation
- [ ] Add SSE event for context length warning
- [ ] Add unit tests for conversation history management

---

## Testing Strategy

1. **Unit Tests:**
   - Test conversation entry creation
   - Test history trimming at max length
   - Test context formatting

2. **Integration Tests:**
   - Test multi-turn conversation flow
   - Test context preservation across task completion
   - Test history length management under load

3. **Manual Testing:**
   - Start task, complete it, continue with follow-up
   - Verify context is properly injected into LLM prompt
   - Verify history trimming doesn't lose critical context
