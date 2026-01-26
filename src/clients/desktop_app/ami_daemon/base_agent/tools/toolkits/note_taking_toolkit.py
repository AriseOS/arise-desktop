"""
NoteTakingToolkit - Markdown note management for agents.

Ported from CAMEL-AI/Eigent project.
Provides tools for creating, reading, appending to, and listing notes.
All notes are stored as `.md` files in a task-specific working directory.

Working directory isolation:
- If initialized with notes_directory, uses that directory
- Otherwise, uses the current task's notes_dir from WorkingDirectoryManager
- Falls back to ~/.ami/notes if no manager is set

Event emission:
- Uses @listen_toolkit decorator for automatic activate/deactivate events
"""

import logging
import threading
import time
from pathlib import Path
from typing import List, Optional

from .base_toolkit import BaseToolkit, FunctionTool
from ...workspace import get_current_manager
from ...events import listen_toolkit

logger = logging.getLogger(__name__)


def get_task_notes_directory() -> Path:
    """Get the notes directory for the current task.

    Requires an active WorkingDirectoryManager to be set.

    Returns:
        Path to the task's notes directory.

    Raises:
        RuntimeError: If no WorkingDirectoryManager is set.
    """
    manager = get_current_manager()
    if not manager:
        raise RuntimeError(
            "No WorkingDirectoryManager set. "
            "NoteTakingToolkit requires a task context with WorkingDirectoryManager."
        )
    return manager.notes_dir


class NoteTakingToolkit(BaseToolkit):
    """A toolkit for managing and interacting with markdown note files.

    This toolkit provides tools for creating, reading, appending to, and
    listing notes. All notes are stored as `.md` files in a task-specific
    working directory and are tracked in a registry.

    Uses @listen_toolkit for automatic event emission on public methods.
    """

    # Agent name for event tracking
    agent_name: str = "note_agent"

    def __init__(
        self,
        task_id: Optional[str] = None,
        working_directory: Optional[str] = None,
        notes_directory: Optional[str] = None,
        timeout: Optional[float] = None,
        use_task_workspace: bool = True,
    ) -> None:
        """Initialize the NoteTakingToolkit.

        Args:
            task_id: The task identifier (for logging/tracking only).
            working_directory: Alias for notes_directory (deprecated, for backward compat).
            notes_directory: Explicit directory path (overrides WorkingDirectoryManager).
            timeout: The timeout for the toolkit operations.
            use_task_workspace: If True (default), requires WorkingDirectoryManager.
        """
        super().__init__(timeout=timeout)

        self.task_id = task_id

        # Explicit directory takes precedence
        explicit_dir = notes_directory or working_directory

        if explicit_dir:
            path = Path(explicit_dir)
        else:
            # Require WorkingDirectoryManager
            path = get_task_notes_directory()

        self.working_directory = path
        self.working_directory.mkdir(parents=True, exist_ok=True)
        self.registry_file = self.working_directory / ".note_register"
        self.registry: List[str] = []
        self._registry_lock = threading.Lock()
        self._load_registry()
        logger.info(f"NoteTakingToolkit initialized at {self.working_directory}")

    def _load_registry(self) -> None:
        """Load the note registry from file."""
        max_retries = 5
        retry_delay = 0.1

        for attempt in range(max_retries):
            try:
                if self.registry_file.exists():
                    content = self.registry_file.read_text(encoding='utf-8').strip()
                    self.registry = content.split('\n') if content else []
                else:
                    self.registry = []
                return
            except (IOError, OSError):
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                else:
                    self.registry = []

    def _save_registry(self) -> None:
        """Save the note registry to file using atomic write."""
        max_retries = 5
        retry_delay = 0.1

        for attempt in range(max_retries):
            try:
                temp_file = self.registry_file.with_suffix('.tmp')
                temp_file.write_text('\n'.join(self.registry), encoding='utf-8')
                temp_file.replace(self.registry_file)
                return
            except (IOError, OSError):
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                else:
                    raise

    def _register_note(self, note_name: str) -> None:
        """Register a new note in the registry (thread-safe)."""
        with self._registry_lock:
            self._load_registry()
            if note_name not in self.registry:
                self.registry.append(note_name)
                self._save_registry()

    @listen_toolkit(
        inputs=lambda self, note_name, content: f"Appending to note: {note_name}",
        return_msg=lambda r: r
    )
    def append_note(self, note_name: str, content: str) -> str:
        """Appends content to a note.

        If the note does not exist, it will be created with the given content.
        If the note already exists, the new content will be added to the end.

        Args:
            note_name: The name of the note (without the .md extension).
            content: The content to append to the note.

        Returns:
            A message confirming that the content was appended or created.
        """
        try:
            self._load_registry()
            note_path = self.working_directory / f"{note_name}.md"

            if note_name not in self.registry or not note_path.exists():
                self.create_note(note_name, content)
                return f"Note '{note_name}' created with content added."

            with note_path.open("a", encoding="utf-8") as f:
                f.write(content + "\n")
            logger.debug(f"Appended content to note: {note_name}")
            return f"Content successfully appended to '{note_name}.md'."
        except Exception as e:
            logger.error(f"Error appending note: {e}")
            return f"Error appending note: {e}"

    @listen_toolkit(
        inputs=lambda self, note_name, content, **kw: f"Creating note: {note_name}",
        return_msg=lambda r: r
    )
    def create_note(
        self, note_name: str, content: str, overwrite: bool = False
    ) -> str:
        """Creates a new note with a unique name.

        Args:
            note_name: The name for your new note (without the .md extension).
            content: The initial content to write in the note.
            overwrite: Whether to overwrite an existing note. Defaults to False.

        Returns:
            A message confirming the creation or an error message.
        """
        try:
            note_path = self.working_directory / f"{note_name}.md"
            existed_before = note_path.exists()

            if existed_before and not overwrite:
                return f"Error: Note '{note_name}.md' already exists."

            note_path.write_text(content, encoding="utf-8")
            self._register_note(note_name)

            if existed_before and overwrite:
                logger.info(f"Note overwritten: {note_name}")
                return f"Note '{note_name}.md' successfully overwritten."
            else:
                logger.info(f"Note created: {note_name}")
                return f"Note '{note_name}.md' successfully created."
        except Exception as e:
            logger.error(f"Error creating note: {e}")
            return f"Error creating note: {e}"

    @listen_toolkit(
        inputs=lambda self: "Listing all notes",
        return_msg=lambda r: f"Found {len(r.split(chr(10))) - 1} notes" if "Available notes" in r else r
    )
    def list_note(self) -> str:
        """Lists all the notes you have created.

        Returns:
            A string containing a list of available notes and their sizes.
        """
        try:
            self._load_registry()
            if not self.registry:
                return "No notes have been created yet."

            notes_info = []
            for note_name in self.registry:
                note_path = self.working_directory / f"{note_name}.md"
                if note_path.exists():
                    size = note_path.stat().st_size
                    notes_info.append(f"- {note_name}.md ({size} bytes)")
                else:
                    notes_info.append(f"- {note_name}.md (file missing)")

            return "Available notes:\n" + "\n".join(notes_info)
        except Exception as e:
            logger.error(f"Error listing notes: {e}")
            return f"Error listing notes: {e}"

    @listen_toolkit(
        inputs=lambda self, note_name=None: f"Reading note: {note_name}" if note_name else "Reading all notes",
        return_msg=lambda r: r[:100] + "..." if len(r) > 100 else r
    )
    def read_note(self, note_name: Optional[str] = None) -> str:
        """Reads the content of a specific note or all notes.

        Args:
            note_name: The name of the note to read (without .md extension).
                If None or empty string, reads all notes.

        Returns:
            The content of the specified note(s).
        """
        try:
            self._load_registry()

            # Read specific note if name provided
            if note_name:
                if note_name not in self.registry:
                    return f"Error: Note '{note_name}' is not registered."
                note_path = self.working_directory / f"{note_name}.md"
                if not note_path.exists():
                    return f"Note file '{note_path.name}' does not exist."
                return note_path.read_text(encoding="utf-8")

            # Read all notes if name is None or empty
            if not self.registry:
                return "No notes have been created yet."

            all_notes = []
            for registered_note in self.registry:
                note_path = self.working_directory / f"{registered_note}.md"
                if note_path.exists():
                    content = note_path.read_text(encoding="utf-8")
                    all_notes.append(f"=== {registered_note}.md ===\n{content}")
                else:
                    all_notes.append(f"=== {registered_note}.md ===\n[File not found]")

            return "\n\n".join(all_notes)
        except Exception as e:
            logger.error(f"Error reading note: {e}")
            return f"Error reading note: {e}"

    # ========== Internal methods for workflow hints ==========

    def _create_workflow_hints_note(self, hints: List[dict]) -> str:
        """Create the workflow_hints.md note with Memory guidance.

        This is called internally at the start of a task to store workflow hints.
        Task planning is handled separately by TaskPlanningToolkit.

        Args:
            hints: List of workflow hint dicts from Memory/Reasoner.

        Returns:
            The content of the created note.
        """
        content = "# Workflow Hints (Memory Reference)\n\n"
        content += "These are navigation hints from similar past workflows.\n"
        content += "Use them as GUIDES, not scripts - adapt to achieve the actual task goal.\n\n"

        if not hints:
            content += "_No workflow hints available._\n"
        else:
            content += "## Steps\n\n"
            for i, hint in enumerate(hints):
                desc = hint.get("description", hint.get("type", "Unknown action"))
                target = hint.get("target_description", "")
                content += f"{i + 1}. **{desc}**"
                if target:
                    content += f"\n   - Target: {target}"
                content += "\n\n"

        self.create_note("workflow_hints", content, overwrite=True)
        return content

    def _create_loop_tracking_note(self, loop_id: str, items: List[str]) -> str:
        """Create a loop tracking note for iterative tasks.

        Args:
            loop_id: Identifier for this loop (e.g., "product_collection").
            items: List of items to iterate through.

        Returns:
            The content of the created note.
        """
        content = f"# Loop: {loop_id}\n\n"
        content += f"Total items: {len(items)}\n\n"
        content += "## Items\n\n"

        for i, item in enumerate(items):
            content += f"- [ ] {i + 1}. {item}\n"

        content += "\n## Collected Data\n\n"
        content += "_No data collected yet._\n"

        note_name = f"loop_{loop_id}"
        self.create_note(note_name, content, overwrite=True)
        return content

    def _update_loop_item(self, loop_id: str, item_num: int, data: str = "") -> str:
        """Mark a loop item as complete and optionally store collected data.

        Args:
            loop_id: The loop identifier.
            item_num: The item number (1-based).
            data: Optional data collected for this item.

        Returns:
            Confirmation message.
        """
        try:
            note_name = f"loop_{loop_id}"
            content = self.read_note(note_name)
            if content.startswith("Error:"):
                return content

            # Update the checkbox
            lines = content.split("\n")
            updated_lines = []

            for line in lines:
                if f"- [ ] {item_num}." in line:
                    line = line.replace("- [ ]", "- [x]")
                updated_lines.append(line)

            # Add collected data if provided
            if data:
                # Find "## Collected Data" section
                final_lines = []
                in_data_section = False
                for line in updated_lines:
                    final_lines.append(line)
                    if "## Collected Data" in line:
                        in_data_section = True
                    elif in_data_section and line.strip() == "_No data collected yet._":
                        final_lines[-1] = f"### Item {item_num}\n{data}"
                        in_data_section = False

                if in_data_section:
                    final_lines.append(f"\n### Item {item_num}\n{data}")
                updated_lines = final_lines

            new_content = "\n".join(updated_lines)
            self.create_note(note_name, new_content, overwrite=True)
            return f"Loop {loop_id}: Item {item_num} marked complete"
        except Exception as e:
            logger.error(f"Error updating loop item: {e}")
            return f"Error updating loop item: {e}"

    def get_tools(self) -> List[FunctionTool]:
        """Return a list of FunctionTool objects for this toolkit.

        Returns:
            List of FunctionTool objects.
        """
        return [
            FunctionTool(self.append_note),
            FunctionTool(self.read_note),
            FunctionTool(self.create_note),
            FunctionTool(self.list_note),
        ]

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "Note Taking Toolkit"
