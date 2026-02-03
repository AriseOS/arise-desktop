# base_agent/workspace/

Per-task directory isolation for agent execution.

## Key Files

| File | Purpose |
|------|---------|
| `directory_manager.py` | `WorkingDirectoryManager` class - manages isolated directories |
| `__init__.py` | Exports: `WorkingDirectoryManager`, `get_working_directory`, `get_current_manager`, `set_current_manager`, `use_working_directory` |

## Directory Structure

Each task gets an isolated workspace:

```
~/.ami/
└── users/{user_id}/
    ├── browser_data/               # User-level (shared across ALL tasks)
    └── projects/{project_id}/
        └── tasks/{task_id}/        # Task-level isolation
            ├── workspace/          # Main working directory
            │   ├── output/         # Generated output files
            │   └── temp/           # Temporary files (auto-cleaned)
            ├── notes/              # Task notes (markdown)
            ├── logs/               # Execution logs
            └── browser_data/       # Task-specific browser data (optional)
```

## Critical Design Decision: Unified Workspace

**All agents (Browser, Developer, Document, Multi-Modal, Social) share the SAME workspace directory.**

This is intentional for cross-agent data sharing:

1. **Notes sharing**: Browser Agent writes findings via `write_note()`, other agents read via `read_note()`
2. **File sharing**: All agents can access files in the same `workspace/` directory
3. **Terminal commands**: `TerminalToolkit` executes in the shared workspace

From `agent_factories.py`:
```python
# Use working_directory for notes so files can be accessed by shell in same directory
notes_dir = working_directory
```

## How Workspace is Configured

1. **Task creation** (`TaskState.__post_init__`):
   ```python
   self._dir_manager = WorkingDirectoryManager(
       user_id=self.user_id,
       project_id=self.project_id,
       task_id=self.task_id,
   )
   ```

2. **Passed to Agent factories**:
   ```python
   browser_agent = create_browser_agent(
       working_directory=task_state.working_directory,  # All agents get same path
       ...
   )
   ```

3. **Injected into System Prompt**:
   ```
   - **Working Directory**: `{working_directory}`
   ```

## Context Variable Mechanism

Uses `ContextVar` for async/concurrent safety:

```python
_current_manager_var: ContextVar[Optional[WorkingDirectoryManager]]

# Environment variables for external tools
os.environ["AMI_WORKING_DIR"] = str(manager.workspace)
os.environ["AMI_TASK_ID"] = manager.task_id
```

## Browser Data Isolation

Two levels of browser data isolation:

| Level | Path | Use Case |
|-------|------|----------|
| User-level | `~/.ami/users/{user_id}/browser_data/` | Preserve login sessions across tasks |
| Task-level | `{task_root}/browser_data/` | Complete isolation (optional) |

Default: User-level (shared) to preserve login sessions.

## Related Documentation

- Design doc: `docs/design/migration/04-working-directory.md`
- Agent factories: `base_agent/core/agent_factories.py`
- Toolkits using workspace: `base_agent/tools/toolkits/terminal_toolkit.py`, `note_taking_toolkit.py`
