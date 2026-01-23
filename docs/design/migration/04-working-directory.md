# Feature 4: Working Directory Isolation

## Current State Analysis

### Eigent Implementation

**Location:** `third-party/eigent/backend/app/model/chat.py` (lines 95-103)

Eigent uses per-task isolated working directories:

```python
def file_save_path(self, path: str | None = None):
    # Sanitize email for filesystem
    email = re.sub(r'[\\/*?:"<>|\s]', "_", self.email.split("@")[0]).strip(".")

    # Structure: ~/eigent/{email}/project_{project_id}/task_{task_id}
    save_path = Path.home() / "eigent" / email / f"project_{self.project_id}" / f"task_{self.task_id}"

    if path is not None:
        save_path = save_path / path

    save_path.mkdir(parents=True, exist_ok=True)
    return str(save_path)
```

**Directory Structure:**
```
~/.eigent/
└── {user_email}/
    └── project_{project_id}/
        ├── task_{task_id_1}/
        │   ├── output.txt
        │   ├── script.py
        │   └── camel_logs/
        ├── task_{task_id_2}/
        │   └── ...
        └── task_{task_id_3}/
            └── ...
```

**Key Features:**
1. **User isolation** - Each user (email) has separate directory
2. **Project grouping** - Tasks grouped by project
3. **Task isolation** - Each task has dedicated workspace
4. **Auto-creation** - Directories created on demand
5. **Environment variable** - Set as `file_save_path` for toolkits

**Working Directory Updates on Multi-Turn:**

```python
# From chat_controller.py (lines 153-184)
if data.task_id:
    # Create new working directory for new task
    new_folder_path = Path.home() / "eigent" / email / f"project_{id}" / f"task_{data.task_id}"
    new_folder_path.mkdir(parents=True, exist_ok=True)
    os.environ["file_save_path"] = str(new_folder_path)

    # Store in task_lock for persistence
    task_lock.new_folder_path = new_folder_path
```

### 2ami Current State

**Current Implementation:**

1. **TerminalToolkit** (terminal_toolkit.py):
```python
working_directory: Optional[str] = None
# Defaults to: Path.cwd() - process working directory
```

2. **Browser data** (browser_session.py):
```python
USER_DATA_DIR = Path.home() / ".ami" / "browser_data_quicktask"
# Single global directory for all browser sessions
```

3. **EigentStyleBrowserAgent**:
```python
def _get_working_dir() -> str:
    return str(Path.home())  # Just home directory
```

**Problems:**
- **No per-task isolation** - All tasks share same working directory
- **No user isolation** - Different users share same space
- **No project grouping** - No logical organization
- **File conflicts** - Tasks can overwrite each other's files
- **No cleanup** - Old task files accumulate

---

## Implementation Plan

### Step 1: Define Directory Structure

**Target Structure:**
```
~/.ami/
├── users/
│   └── {user_id}/
│       └── projects/
│           └── {project_id}/
│               └── tasks/
│                   └── {task_id}/
│                       ├── workspace/      # Main working directory
│                       │   ├── output/     # Generated files
│                       │   └── temp/       # Temporary files
│                       ├── logs/           # Execution logs
│                       └── browser_data/   # Task-specific browser data
└── shared/
    └── browser_profiles/  # Shared browser profiles (optional)
```

### Step 2: Create Working Directory Manager

**File:** `src/clients/desktop_app/ami_daemon/base_agent/workspace/directory_manager.py` (NEW)

```python
"""
Working directory management with per-task isolation.
"""
import os
import re
import shutil
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta


class WorkingDirectoryManager:
    """
    Manages isolated working directories for tasks.

    Each task gets its own isolated workspace:
    ~/.ami/users/{user_id}/projects/{project_id}/tasks/{task_id}/
    """

    BASE_DIR = Path.home() / ".ami"
    USERS_DIR = BASE_DIR / "users"

    def __init__(
        self,
        user_id: str,
        project_id: str,
        task_id: str,
        auto_create: bool = True
    ):
        """
        Initialize directory manager for a task.

        Args:
            user_id: User identifier (email or UUID)
            project_id: Project identifier
            task_id: Task identifier
            auto_create: Whether to create directories automatically
        """
        self.user_id = self._sanitize_path_component(user_id)
        self.project_id = self._sanitize_path_component(project_id)
        self.task_id = self._sanitize_path_component(task_id)

        self._task_root = (
            self.USERS_DIR /
            self.user_id /
            "projects" /
            self.project_id /
            "tasks" /
            self.task_id
        )

        if auto_create:
            self._ensure_directories()

    @staticmethod
    def _sanitize_path_component(value: str) -> str:
        """Sanitize string for use in file path"""
        # Remove/replace invalid characters
        sanitized = re.sub(r'[\\/*?:"<>|\s]', "_", value)
        # Remove leading/trailing dots and underscores
        sanitized = sanitized.strip("._")
        # Limit length
        if len(sanitized) > 64:
            sanitized = sanitized[:64]
        return sanitized or "default"

    def _ensure_directories(self) -> None:
        """Create all required directories"""
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    @property
    def task_root(self) -> Path:
        """Root directory for this task"""
        return self._task_root

    @property
    def workspace(self) -> Path:
        """Main working directory for task execution"""
        return self._task_root / "workspace"

    @property
    def output_dir(self) -> Path:
        """Directory for generated output files"""
        return self._task_root / "workspace" / "output"

    @property
    def temp_dir(self) -> Path:
        """Directory for temporary files"""
        return self._task_root / "workspace" / "temp"

    @property
    def logs_dir(self) -> Path:
        """Directory for execution logs"""
        return self._task_root / "logs"

    @property
    def browser_data_dir(self) -> Path:
        """Directory for task-specific browser data"""
        return self._task_root / "browser_data"

    def get_file_path(self, relative_path: str) -> Path:
        """
        Get absolute path for a file within workspace.

        Args:
            relative_path: Path relative to workspace

        Returns:
            Absolute path within workspace
        """
        # Prevent path traversal
        clean_path = Path(relative_path).resolve()
        workspace_resolved = self.workspace.resolve()

        target = (self.workspace / relative_path).resolve()
        if not str(target).startswith(str(workspace_resolved)):
            raise ValueError(f"Path traversal detected: {relative_path}")

        return target

    def write_file(self, relative_path: str, content: str | bytes) -> Path:
        """
        Write file to workspace.

        Args:
            relative_path: Path relative to workspace
            content: File content (str or bytes)

        Returns:
            Absolute path of written file
        """
        file_path = self.get_file_path(relative_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        mode = "w" if isinstance(content, str) else "wb"
        with open(file_path, mode) as f:
            f.write(content)

        return file_path

    def read_file(self, relative_path: str) -> str:
        """Read file from workspace"""
        file_path = self.get_file_path(relative_path)
        return file_path.read_text()

    def list_files(self, pattern: str = "*") -> list[Path]:
        """List files in workspace matching pattern"""
        return list(self.workspace.rglob(pattern))

    def cleanup_temp(self) -> None:
        """Remove all temporary files"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
            self.temp_dir.mkdir()

    def cleanup_all(self) -> None:
        """Remove entire task directory"""
        if self._task_root.exists():
            shutil.rmtree(self._task_root)

    def get_disk_usage(self) -> int:
        """Get total disk usage in bytes"""
        total = 0
        for file_path in self._task_root.rglob("*"):
            if file_path.is_file():
                total += file_path.stat().st_size
        return total

    def to_dict(self) -> dict:
        """Serialize directory info"""
        return {
            "user_id": self.user_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "workspace": str(self.workspace),
            "output_dir": str(self.output_dir),
            "logs_dir": str(self.logs_dir),
            "disk_usage": self.get_disk_usage()
        }

    @classmethod
    def cleanup_old_tasks(
        cls,
        user_id: str,
        max_age_days: int = 7,
        max_disk_mb: int = 1000
    ) -> list[str]:
        """
        Cleanup old task directories.

        Args:
            user_id: User to cleanup
            max_age_days: Remove tasks older than this
            max_disk_mb: Maximum total disk usage in MB

        Returns:
            List of removed task directories
        """
        user_dir = cls.USERS_DIR / cls._sanitize_path_component(user_id)
        if not user_dir.exists():
            return []

        removed = []
        cutoff = datetime.now() - timedelta(days=max_age_days)

        # Collect all task directories with metadata
        tasks = []
        for project_dir in user_dir.glob("projects/*/tasks/*"):
            if project_dir.is_dir():
                mtime = datetime.fromtimestamp(project_dir.stat().st_mtime)
                size = sum(f.stat().st_size for f in project_dir.rglob("*") if f.is_file())
                tasks.append({
                    "path": project_dir,
                    "mtime": mtime,
                    "size": size
                })

        # Sort by modification time (oldest first)
        tasks.sort(key=lambda x: x["mtime"])

        total_size = sum(t["size"] for t in tasks)
        max_bytes = max_disk_mb * 1024 * 1024

        for task in tasks:
            should_remove = False

            # Remove if older than max age
            if task["mtime"] < cutoff:
                should_remove = True

            # Remove if exceeding disk quota (oldest first)
            elif total_size > max_bytes:
                should_remove = True

            if should_remove:
                try:
                    shutil.rmtree(task["path"])
                    removed.append(str(task["path"]))
                    total_size -= task["size"]
                except Exception:
                    pass

        return removed


# Singleton instance for current task (set by service)
_current_manager: Optional[WorkingDirectoryManager] = None


def get_working_directory() -> str:
    """Get current working directory path"""
    if _current_manager:
        return str(_current_manager.workspace)
    return str(Path.home())


def set_current_manager(manager: WorkingDirectoryManager) -> None:
    """Set current directory manager"""
    global _current_manager
    _current_manager = manager


def get_current_manager() -> Optional[WorkingDirectoryManager]:
    """Get current directory manager"""
    return _current_manager
```

### Step 3: Integrate with TaskState

**File:** `src/clients/desktop_app/ami_daemon/services/quick_task_service.py`

```python
from ..base_agent.workspace.directory_manager import WorkingDirectoryManager

@dataclass
class TaskState:
    task_id: str
    task: str
    user_id: str = "default"
    project_id: str = "default"

    # ... existing fields ...

    # Working directory manager
    _dir_manager: Optional[WorkingDirectoryManager] = None

    def __post_init__(self):
        # Initialize directory manager
        self._dir_manager = WorkingDirectoryManager(
            user_id=self.user_id,
            project_id=self.project_id,
            task_id=self.task_id
        )

        # Set environment variable for toolkits
        os.environ["AMI_WORKING_DIR"] = str(self._dir_manager.workspace)
        os.environ["AMI_TASK_ID"] = self.task_id

    @property
    def working_directory(self) -> str:
        """Get working directory path"""
        return str(self._dir_manager.workspace)

    @property
    def dir_manager(self) -> WorkingDirectoryManager:
        """Get directory manager"""
        return self._dir_manager

    def get_output_path(self, filename: str) -> str:
        """Get path for output file"""
        return str(self._dir_manager.output_dir / filename)

    def write_output(self, filename: str, content: str) -> str:
        """Write file to output directory"""
        return str(self._dir_manager.write_file(f"output/{filename}", content))
```

### Step 4: Update Terminal Toolkit

**File:** `src/clients/desktop_app/ami_daemon/base_agent/tools/toolkits/terminal_toolkit.py`

```python
from ..workspace.directory_manager import get_working_directory, get_current_manager

class TerminalToolkit(BaseToolkit):

    def __init__(self, working_directory: Optional[str] = None):
        """
        Initialize terminal toolkit.

        Args:
            working_directory: Override working directory (uses task workspace if None)
        """
        self._custom_working_dir = working_directory

    @property
    def working_directory(self) -> Path:
        """Get effective working directory"""
        if self._custom_working_dir:
            return Path(self._custom_working_dir)

        # Try to get from task state
        if self._task_state and hasattr(self._task_state, 'working_directory'):
            return Path(self._task_state.working_directory)

        # Fall back to global manager
        return Path(get_working_directory())

    @listen_toolkit(
        inputs=lambda self, cmd, **kw: f"$ {cmd}"
    )
    async def execute_command(
        self,
        command: str,
        timeout: int = 120,
        allow_dangerous: bool = False
    ) -> str:
        """
        Execute shell command in task working directory.

        Commands run in isolated workspace:
        ~/.ami/users/{user}/projects/{project}/tasks/{task}/workspace/

        Args:
            command: Shell command to execute
            timeout: Timeout in seconds
            allow_dangerous: Allow dangerous commands (rm -rf, etc.)

        Returns:
            Command output (stdout + stderr)
        """
        # Validate command
        if not allow_dangerous:
            self._check_dangerous_command(command)

        # Execute in working directory
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(self.working_directory),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={
                **os.environ,
                "HOME": str(self.working_directory.parent),  # Isolate home
                "PWD": str(self.working_directory)
            }
        )

        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            return stdout.decode('utf-8', errors='replace')
        except asyncio.TimeoutError:
            process.kill()
            return f"Command timed out after {timeout} seconds"
```

### Step 5: Update Browser Session

**File:** `src/clients/desktop_app/ami_daemon/base_agent/tools/eigent_browser/browser_session.py`

```python
from ..workspace.directory_manager import get_current_manager

class HybridBrowserSession:

    @classmethod
    def get_user_data_dir(cls, task_state: Optional['TaskState'] = None) -> Path:
        """
        Get browser user data directory.

        For task isolation, each task can have its own browser profile.
        """
        if task_state and hasattr(task_state, 'dir_manager'):
            # Task-specific browser data
            return task_state.dir_manager.browser_data_dir

        # Shared browser data (default)
        manager = get_current_manager()
        if manager:
            return manager.browser_data_dir

        # Fallback to global
        return Path.home() / ".ami" / "browser_data_quicktask"

    async def create_session(
        self,
        task_state: Optional['TaskState'] = None,
        headless: bool = True
    ) -> 'BrowserContext':
        """Create browser session with task-specific data dir"""
        user_data_dir = self.get_user_data_dir(task_state)
        user_data_dir.mkdir(parents=True, exist_ok=True)

        # Launch browser with isolated profile
        browser = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=headless,
            # ... other options
        )
        return browser
```

### Step 6: Update Service Layer

**File:** `src/clients/desktop_app/ami_daemon/services/quick_task_service.py`

```python
from ..base_agent.workspace.directory_manager import (
    WorkingDirectoryManager,
    set_current_manager
)

class QuickTaskService:

    async def create_task(
        self,
        task: str,
        user_id: str = "default",
        project_id: str = "default",
        task_id: Optional[str] = None,
        start_url: Optional[str] = None
    ) -> TaskState:
        """
        Create new task with isolated working directory.

        Directory structure:
        ~/.ami/users/{user_id}/projects/{project_id}/tasks/{task_id}/
        """
        if task_id is None:
            task_id = str(uuid.uuid4())

        state = TaskState(
            task_id=task_id,
            task=task,
            user_id=user_id,
            project_id=project_id,
            start_url=start_url,
            status="PENDING"
        )

        # Set as current manager for toolkits
        set_current_manager(state.dir_manager)

        # Store state
        self._task_states[task_id] = state

        logger.info(
            f"Created task {task_id} with workspace: {state.working_directory}"
        )

        return state

    async def continue_task(
        self,
        task_id: str,
        new_task: str,
        new_task_id: Optional[str] = None
    ) -> TaskState:
        """
        Continue task with optional new working directory.

        If new_task_id is provided, creates new workspace while
        preserving conversation history.
        """
        old_state = self._task_states.get(task_id)
        if not old_state:
            raise ValueError(f"Task {task_id} not found")

        if new_task_id:
            # Create new workspace for new task
            new_state = TaskState(
                task_id=new_task_id,
                task=new_task,
                user_id=old_state.user_id,
                project_id=old_state.project_id,
                status="PENDING",
                # Preserve conversation history
                conversation_history=old_state.conversation_history.copy()
            )

            # Update current manager
            set_current_manager(new_state.dir_manager)

            self._task_states[new_task_id] = new_state
            return new_state
        else:
            # Continue in same workspace
            old_state.task = new_task
            old_state.status = "RUNNING"
            return old_state

    async def cleanup_old_tasks(
        self,
        user_id: str,
        max_age_days: int = 7
    ) -> int:
        """Cleanup old task directories"""
        removed = WorkingDirectoryManager.cleanup_old_tasks(
            user_id=user_id,
            max_age_days=max_age_days
        )
        return len(removed)
```

### Step 7: Router Updates

**File:** `src/clients/desktop_app/ami_daemon/routers/quick_task.py`

```python
from ..base_agent.workspace.directory_manager import WorkingDirectoryManager

@router.post("/task")
async def create_task(request: CreateTaskRequest):
    """Create task with user/project context"""
    state = await quick_task_service.create_task(
        task=request.task,
        user_id=request.user_id or "default",
        project_id=request.project_id or "default",
        task_id=request.task_id,
        start_url=request.start_url
    )

    return {
        "task_id": state.task_id,
        "workspace": state.working_directory,
        "status": state.status
    }


@router.get("/task/{task_id}/files")
async def list_task_files(task_id: str):
    """List files in task workspace"""
    state = quick_task_service.get_task_state(task_id)
    if not state:
        return {"error": "Task not found"}

    files = state.dir_manager.list_files()
    return {
        "task_id": task_id,
        "workspace": state.working_directory,
        "files": [str(f.relative_to(state.dir_manager.workspace)) for f in files],
        "disk_usage": state.dir_manager.get_disk_usage()
    }


@router.delete("/task/{task_id}/files")
async def cleanup_task_files(task_id: str, temp_only: bool = True):
    """Cleanup task files"""
    state = quick_task_service.get_task_state(task_id)
    if not state:
        return {"error": "Task not found"}

    if temp_only:
        state.dir_manager.cleanup_temp()
    else:
        state.dir_manager.cleanup_all()

    return {"status": "cleaned"}


@router.post("/cleanup")
async def cleanup_old_tasks(
    user_id: str = "default",
    max_age_days: int = 7
):
    """Cleanup old task directories"""
    count = await quick_task_service.cleanup_old_tasks(
        user_id=user_id,
        max_age_days=max_age_days
    )
    return {"removed_tasks": count}
```

---

## Migration Checklist

- [ ] Create `workspace/` package directory
- [ ] Create `directory_manager.py` module
- [ ] Implement `WorkingDirectoryManager` class
- [ ] Add path sanitization for user/project/task IDs
- [ ] Add path traversal prevention
- [ ] Update `TaskState` with directory manager
- [ ] Add `working_directory` property
- [ ] Update `TerminalToolkit` to use task workspace
- [ ] Update `BrowserSession` for task-specific browser data
- [ ] Update `QuickTaskService.create_task()` with user/project context
- [ ] Add `continue_task()` with new workspace option
- [ ] Add task file listing endpoint
- [ ] Add cleanup endpoint
- [ ] Add automatic cleanup for old tasks
- [ ] Update environment variables setup
- [ ] Add disk usage tracking
- [ ] Add unit tests for directory manager
- [ ] Add integration tests for workspace isolation

---

## Directory Lifecycle

```
Task Creation:
┌─────────────────────────────────────────────────────────────┐
│  POST /task                                                 │
│  {task: "...", user_id: "user@example.com", project_id: "p1"}│
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  WorkingDirectoryManager.create()                           │
│  ~/.ami/users/user_example_com/projects/p1/tasks/{task_id}/ │
│  ├── workspace/                                             │
│  │   ├── output/                                            │
│  │   └── temp/                                              │
│  ├── logs/                                                  │
│  └── browser_data/                                          │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Task Execution (in workspace/)                             │
│  - Terminal commands run here                               │
│  - Files created/edited here                                │
│  - Browser downloads saved here                             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Task Completion                                            │
│  - Temp files cleaned (optional)                            │
│  - Output files preserved                                   │
│  - Logs preserved                                           │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼ (after 7 days)
┌─────────────────────────────────────────────────────────────┐
│  Auto Cleanup                                               │
│  - Remove entire task directory                             │
│  - Free disk space                                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Security Considerations

1. **Path Traversal Prevention:**
   - All paths resolved and checked against workspace root
   - Symbolic links not followed outside workspace
   - Parent directory references (`..`) blocked

2. **User Isolation:**
   - Each user has separate directory tree
   - No cross-user file access
   - Permissions set to user-only (700)

3. **Disk Quota:**
   - Per-user disk usage tracking
   - Automatic cleanup when quota exceeded
   - Warning events for high usage

4. **Sensitive Files:**
   - Browser data isolated per task
   - Credentials not shared between tasks
   - Auto-cleanup removes sensitive data

---

## Testing Strategy

1. **Unit Tests:**
   - Test path sanitization
   - Test directory creation
   - Test path traversal prevention
   - Test cleanup logic

2. **Integration Tests:**
   - Test full task lifecycle
   - Test multi-user isolation
   - Test workspace persistence across task continuation

3. **Manual Testing:**
   - Create multiple tasks, verify isolation
   - Run terminal commands, verify working directory
   - Test cleanup and disk usage
