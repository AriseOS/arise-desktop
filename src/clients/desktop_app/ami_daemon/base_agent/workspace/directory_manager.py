"""
Working directory management with per-task isolation.

Provides isolated working directories for each task execution:
~/.ami/users/{user_id}/projects/{project_id}/tasks/{task_id}/

Features:
- User isolation: Each user has separate directory tree
- Project grouping: Tasks grouped by project
- Task isolation: Each task has dedicated workspace
- Auto-creation: Directories created on demand
- Cleanup: Automatic cleanup of old tasks
"""

import logging
import os
import re
import shutil
from contextvars import ContextVar
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Generator, List, Optional, Union

logger = logging.getLogger(__name__)


class WorkingDirectoryManager:
    """
    Manages isolated working directories for tasks.

    Each task gets its own isolated workspace:
    ~/.ami/users/{user_id}/projects/{project_id}/tasks/{task_id}/

    Directory structure:
        workspace/      - Main working directory for task execution
        logs/           - Execution logs
        browser_data/   - Task-specific browser profile
    """

    BASE_DIR = Path.home() / ".ami"
    USERS_DIR = BASE_DIR / "users"

    def __init__(
        self,
        user_id: str,
        project_id: str,
        task_id: str,
        auto_create: bool = True,
    ):
        """
        Initialize directory manager for a task.

        Args:
            user_id: User identifier (email or UUID). Sanitized for filesystem.
            project_id: Project identifier. Sanitized for filesystem.
            task_id: Task identifier. Sanitized for filesystem.
            auto_create: Whether to create directories automatically.
        """
        self.user_id = self._sanitize_path_component(user_id)
        self.project_id = self._sanitize_path_component(project_id)
        self.task_id = self._sanitize_path_component(task_id)

        self._task_root = (
            self.USERS_DIR
            / self.user_id
            / "projects"
            / self.project_id
            / "tasks"
            / self.task_id
        )
        self._workspace_override: Optional[Path] = None

        if auto_create:
            self._ensure_directories()

        logger.info(f"WorkingDirectoryManager initialized: {self._task_root}")

    @staticmethod
    def _sanitize_path_component(value: str) -> str:
        """
        Sanitize string for use in file path.

        Removes/replaces invalid characters and limits length.

        Args:
            value: Raw string value.

        Returns:
            Sanitized string safe for filesystem paths.
        """
        if not value:
            return "default"

        # Remove/replace invalid characters for filesystem
        # Windows: \ / : * ? " < > |
        # Also replace whitespace with underscore
        sanitized = re.sub(r'[\\/*?:"<>|\s@]', "_", value)

        # Remove leading/trailing dots and underscores
        sanitized = sanitized.strip("._")

        # Collapse multiple underscores
        sanitized = re.sub(r"_+", "_", sanitized)

        # Limit length to 64 characters
        if len(sanitized) > 64:
            sanitized = sanitized[:64]

        return sanitized or "default"

    def _ensure_directories(self) -> None:
        """Create all required directories."""
        try:
            self.workspace.mkdir(parents=True, exist_ok=True)
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            # Browser data created on demand to save space
        except Exception as e:
            logger.error(f"Failed to create directories: {e}")
            raise

    @property
    def task_root(self) -> Path:
        """Root directory for this task."""
        return self._task_root

    @property
    def workspace(self) -> Path:
        """Main working directory for task execution."""
        if self._workspace_override is not None:
            return self._workspace_override
        return self._task_root / "workspace"

    def create_child_manager(self, subfolder: str) -> "WorkingDirectoryManager":
        """Create child manager with workspace in a subdirectory.

        Args:
            subfolder: Name for the subdirectory (will be sanitized).

        Returns:
            New WorkingDirectoryManager whose workspace points to
            {parent_workspace}/{sanitized_subfolder}/.
        """
        sanitized = self._sanitize_path_component(subfolder)
        child = WorkingDirectoryManager.__new__(WorkingDirectoryManager)
        child.user_id = self.user_id
        child.project_id = self.project_id
        child.task_id = self.task_id
        child._task_root = self._task_root
        child._workspace_override = self.workspace / sanitized
        child._workspace_override.mkdir(parents=True, exist_ok=True)
        return child

    @property
    def logs_dir(self) -> Path:
        """Directory for execution logs."""
        return self._task_root / "logs"

    @property
    def browser_data_dir(self) -> Path:
        """
        Directory for user-level browser data (shared across all tasks).

        Uses user-level directory instead of task-level to:
        1. Preserve login sessions across tasks
        2. Share cookies and authentication state
        3. Avoid re-login for each new task

        Path: ~/.ami/users/{user_id}/browser_data/
        """
        path = self.USERS_DIR / self.user_id / "browser_data"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def task_browser_data_dir(self) -> Path:
        """
        Directory for task-specific browser data (isolated per task).

        Use this only when task isolation is required.
        For most cases, use browser_data_dir instead.

        Path: ~/.ami/users/{user_id}/projects/{project_id}/tasks/{task_id}/browser_data/
        """
        path = self._task_root / "browser_data"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_file_path(self, relative_path: str) -> Path:
        """
        Get absolute path for a file within workspace.

        Includes path traversal protection.

        Args:
            relative_path: Path relative to workspace.

        Returns:
            Absolute path within workspace.

        Raises:
            ValueError: If path traversal is detected.
        """
        # Resolve the target path
        target = (self.workspace / relative_path).resolve()
        workspace_resolved = self.workspace.resolve()

        # Check for path traversal
        try:
            target.relative_to(workspace_resolved)
        except ValueError:
            raise ValueError(f"Path traversal detected: {relative_path}")

        return target

    def write_file(self, relative_path: str, content: Union[str, bytes]) -> Path:
        """
        Write file to workspace.

        Args:
            relative_path: Path relative to workspace.
            content: File content (str or bytes).

        Returns:
            Absolute path of written file.
        """
        file_path = self.get_file_path(relative_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        mode = "w" if isinstance(content, str) else "wb"
        encoding = "utf-8" if isinstance(content, str) else None

        with open(file_path, mode, encoding=encoding) as f:
            f.write(content)

        logger.debug(f"File written: {file_path}")
        return file_path

    def read_file(self, relative_path: str) -> str:
        """
        Read file from workspace.

        Args:
            relative_path: Path relative to workspace.

        Returns:
            File content as string.

        Raises:
            FileNotFoundError: If file does not exist.
        """
        file_path = self.get_file_path(relative_path)
        return file_path.read_text(encoding="utf-8")

    def file_exists(self, relative_path: str) -> bool:
        """Check if file exists in workspace."""
        try:
            file_path = self.get_file_path(relative_path)
            return file_path.exists()
        except ValueError:
            return False

    def list_files(self, pattern: str = "*", directory: Optional[Path] = None) -> List[Path]:
        """
        List files matching pattern.

        Args:
            pattern: Glob pattern to match (default: "*").
            directory: Directory to search in (default: workspace).

        Returns:
            List of matching file paths.
        """
        search_dir = directory or self.workspace
        return list(search_dir.rglob(pattern))

    def cleanup_all(self) -> None:
        """Remove entire task directory (not allowed on child managers)."""
        if self._workspace_override is not None:
            raise RuntimeError(
                "Cannot cleanup_all from a child manager — "
                "would delete the entire parent task directory"
            )
        if self._task_root.exists():
            try:
                shutil.rmtree(self._task_root)
                logger.info(f"Cleaned task directory: {self._task_root}")
            except Exception as e:
                logger.warning(f"Failed to clean task directory: {e}")

    def get_disk_usage(self) -> int:
        """
        Get total disk usage in bytes.

        For child managers, scopes to the child workspace subdirectory.
        For parent managers, scopes to the entire task directory.

        Returns:
            Total size of all files in the scoped directory.
        """
        root = self.workspace if self._workspace_override is not None else self._task_root
        total = 0
        try:
            for file_path in root.rglob("*"):
                if file_path.is_file():
                    total += file_path.stat().st_size
        except Exception as e:
            logger.warning(f"Failed to calculate disk usage: {e}")
        return total

    def get_disk_usage_mb(self) -> float:
        """Get total disk usage in megabytes."""
        return self.get_disk_usage() / (1024 * 1024)

    def to_dict(self) -> Dict:
        """
        Serialize directory info to dict.

        Returns:
            Dict with directory paths and metadata.
        """
        return {
            "user_id": self.user_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "task_root": str(self._task_root),
            "workspace": str(self.workspace),
            "logs_dir": str(self.logs_dir),
            "browser_data_dir": str(self.USERS_DIR / self.user_id / "browser_data"),
            "task_browser_data_dir": str(self._task_root / "browser_data"),
            "disk_usage_bytes": self.get_disk_usage(),
        }

    @classmethod
    def cleanup_old_tasks(
        cls,
        user_id: str,
        max_age_days: int = 7,
        max_disk_mb: int = 1000,
    ) -> List[str]:
        """
        Cleanup old task directories for a user.

        Removes tasks that are:
        - Older than max_age_days
        - Or when total disk usage exceeds max_disk_mb (oldest first)

        Args:
            user_id: User to cleanup.
            max_age_days: Remove tasks older than this (default: 7).
            max_disk_mb: Maximum total disk usage in MB (default: 1000).

        Returns:
            List of removed task directory paths.
        """
        sanitized_user_id = cls._sanitize_path_component(user_id)
        user_dir = cls.USERS_DIR / sanitized_user_id

        if not user_dir.exists():
            return []

        removed = []
        cutoff = datetime.now() - timedelta(days=max_age_days)

        # Collect all task directories with metadata
        tasks = []
        for project_dir in user_dir.glob("projects/*"):
            if not project_dir.is_dir():
                continue
            tasks_dir = project_dir / "tasks"
            if not tasks_dir.exists():
                continue

            for task_dir in tasks_dir.iterdir():
                if not task_dir.is_dir():
                    continue
                try:
                    mtime = datetime.fromtimestamp(task_dir.stat().st_mtime)
                    size = sum(
                        f.stat().st_size
                        for f in task_dir.rglob("*")
                        if f.is_file()
                    )
                    tasks.append({
                        "path": task_dir,
                        "mtime": mtime,
                        "size": size,
                    })
                except Exception as e:
                    logger.warning(f"Failed to get task info for {task_dir}: {e}")

        # Sort by modification time (oldest first)
        tasks.sort(key=lambda x: x["mtime"])

        total_size = sum(t["size"] for t in tasks)
        max_bytes = max_disk_mb * 1024 * 1024

        for task in tasks:
            should_remove = False

            # Remove if older than max age
            if task["mtime"] < cutoff:
                should_remove = True
                reason = "age"

            # Remove if exceeding disk quota (oldest first)
            elif total_size > max_bytes:
                should_remove = True
                reason = "quota"

            if should_remove:
                try:
                    shutil.rmtree(task["path"])
                    removed.append(str(task["path"]))
                    total_size -= task["size"]
                    logger.info(f"Removed old task ({reason}): {task['path']}")
                except Exception as e:
                    logger.warning(f"Failed to remove {task['path']}: {e}")

        return removed

    @classmethod
    def get_user_tasks(cls, user_id: str) -> List[Dict]:
        """
        Get all tasks for a user.

        Args:
            user_id: User identifier.

        Returns:
            List of task info dicts.
        """
        sanitized_user_id = cls._sanitize_path_component(user_id)
        user_dir = cls.USERS_DIR / sanitized_user_id

        if not user_dir.exists():
            return []

        tasks = []
        for project_dir in user_dir.glob("projects/*"):
            if not project_dir.is_dir():
                continue

            project_id = project_dir.name
            tasks_dir = project_dir / "tasks"

            if not tasks_dir.exists():
                continue

            for task_dir in tasks_dir.iterdir():
                if not task_dir.is_dir():
                    continue
                try:
                    mtime = datetime.fromtimestamp(task_dir.stat().st_mtime)
                    tasks.append({
                        "user_id": user_id,
                        "project_id": project_id,
                        "task_id": task_dir.name,
                        "path": str(task_dir),
                        "modified_at": mtime.isoformat(),
                    })
                except Exception:
                    pass

        return tasks


# ContextVar for task-isolated manager access (thread/async-safe)
# This replaces the global _current_manager to support concurrent tasks
_current_manager_var: ContextVar[Optional[WorkingDirectoryManager]] = ContextVar(
    'current_manager', default=None
)


def get_current_manager() -> Optional[WorkingDirectoryManager]:
    """
    Get the current WorkingDirectoryManager for this context.

    Uses ContextVar for proper isolation in concurrent/async environments.
    Each task/coroutine maintains its own manager reference.

    Returns:
        Current manager or None if not set.
    """
    return _current_manager_var.get()


def set_current_manager(manager: Optional[WorkingDirectoryManager]) -> None:
    """
    Set the current WorkingDirectoryManager for this context.

    Uses ContextVar for proper isolation in concurrent/async environments.

    Args:
        manager: Manager instance to set as current.
    """
    _current_manager_var.set(manager)
    if manager:
        # Set environment variable for external tools
        os.environ["AMI_WORKING_DIR"] = str(manager.workspace)
        os.environ["AMI_TASK_ID"] = manager.task_id
        logger.debug(f"Set current manager: {manager.task_id}")


@contextmanager
def use_working_directory(manager: WorkingDirectoryManager) -> Generator[WorkingDirectoryManager, None, None]:
    """
    Context manager for temporarily setting the working directory manager.

    Ensures proper cleanup even if an exception occurs.
    Based on Eigent's set_process_task pattern.

    Args:
        manager: WorkingDirectoryManager to use within the context.

    Yields:
        The manager instance.

    Usage:
        with use_working_directory(manager):
            # All operations here use this manager
            toolkit.execute()
    """
    token = _current_manager_var.set(manager)
    if manager:
        os.environ["AMI_WORKING_DIR"] = str(manager.workspace)
        os.environ["AMI_TASK_ID"] = manager.task_id
    try:
        yield manager
    finally:
        _current_manager_var.reset(token)
        # Note: We don't clear env vars here as another task might have set them


def get_working_directory() -> str:
    """
    Get current working directory path.

    Returns the task workspace if a manager is set,
    otherwise returns user's home directory.

    Returns:
        Working directory path as string.
    """
    manager = _current_manager_var.get()
    if manager:
        return str(manager.workspace)
    return str(Path.home())
