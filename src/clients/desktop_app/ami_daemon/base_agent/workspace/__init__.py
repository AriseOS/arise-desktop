"""
Workspace management for per-task directory isolation.

Provides WorkingDirectoryManager for creating and managing isolated
working directories for each task execution.
"""

from .directory_manager import (
    WorkingDirectoryManager,
    get_working_directory,
    get_current_manager,
    set_current_manager,
    use_working_directory,
)

__all__ = [
    "WorkingDirectoryManager",
    "get_working_directory",
    "get_current_manager",
    "set_current_manager",
    "use_working_directory",
]
