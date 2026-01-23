"""
Context building utilities for conversation history management.

Provides functions to build and format conversation context for LLM prompt injection.
Based on Eigent's build_conversation_context pattern from chat_service.py.

Features:
- Format conversation history for LLM prompts
- Collect files from working directories
- Check history length limits
- Context summarization for long histories
"""

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from .quick_task_service import TaskState

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_MAX_HISTORY_LENGTH = 100000  # 100KB
DEFAULT_MAX_CONTEXT_ENTRIES = 20
DEFAULT_MAX_FILES_TO_LIST = 50

# Directories to skip when collecting files
SKIP_DIRECTORIES = {
    'node_modules',
    '__pycache__',
    '.git',
    '.venv',
    'venv',
    '.env',
    'dist',
    'build',
    '.next',
    '.cache',
}

# File extensions to skip
SKIP_EXTENSIONS = {
    '.pyc',
    '.pyo',
    '.so',
    '.dll',
    '.dylib',
    '.exe',
    '.o',
    '.obj',
    '.class',
    '.jar',
    '.war',
}


def build_conversation_context(
    state: "TaskState",
    header: str = "=== CONVERSATION HISTORY ===",
    skip_files: bool = False,
    max_entries: Optional[int] = None,
    include_tool_calls: bool = False,
) -> str:
    """
    Build conversation context from task state history.

    Formats history for LLM prompt injection, optionally including
    file listings from working directories.

    Based on Eigent's build_conversation_context pattern.

    Args:
        state: TaskState with conversation_history
        header: Header text for the context section
        skip_files: Whether to skip file collection
        max_entries: Maximum conversation entries to include
        include_tool_calls: Whether to include tool_call entries

    Returns:
        Formatted context string for LLM prompt
    """
    if not state.conversation_history:
        return ""

    context_parts = [header]
    working_directories: Set[str] = set()

    # Determine which entries to include
    history = state.conversation_history
    if max_entries is not None:
        history = history[-max_entries:]

    for entry in history:
        # Skip tool calls unless requested
        if entry.role == 'tool_call' and not include_tool_calls:
            continue

        if entry.role == 'task_result':
            if isinstance(entry.content, dict):
                formatted = _format_task_result(entry.content, skip_files)
                context_parts.append(formatted)
                # Track working directory for file collection
                if entry.content.get('working_directory'):
                    working_directories.add(entry.content['working_directory'])
            else:
                context_parts.append(f"Task Result: {entry.content}")

        elif entry.role == 'assistant':
            content = _truncate_content(entry.content, max_length=2000)
            context_parts.append(f"Assistant: {content}")

        elif entry.role == 'user':
            content = _truncate_content(entry.content, max_length=1000)
            context_parts.append(f"User: {content}")

        elif entry.role == 'tool_call':
            if isinstance(entry.content, dict):
                tool_name = entry.content.get('name', 'unknown')
                tool_result = _truncate_content(
                    str(entry.content.get('result', '')),
                    max_length=200
                )
                context_parts.append(f"Tool [{tool_name}]: {tool_result}")

        elif entry.role == 'system':
            content = _truncate_content(entry.content, max_length=500)
            context_parts.append(f"System: {content}")

    # Collect files from working directories if not skipped
    if not skip_files and working_directories:
        files_context = _collect_working_directory_files(working_directories)
        if files_context:
            context_parts.append(files_context)

    # Add current working directory files if available
    if not skip_files and hasattr(state, '_dir_manager') and state._dir_manager:
        workspace = str(state._dir_manager.workspace)
        if workspace not in working_directories:
            current_files = _collect_working_directory_files({workspace})
            if current_files:
                context_parts.append(f"=== Current Workspace Files ===\n{current_files}")

    return "\n\n".join(context_parts)


def _format_task_result(result: Dict, skip_files: bool = False) -> str:
    """
    Format a task result for context.

    Args:
        result: Task result dict with task, summary, status, files_created
        skip_files: Whether to skip file listing

    Returns:
        Formatted task result string
    """
    parts = ["Task Result:"]

    if result.get('task'):
        task_text = _truncate_content(result['task'], max_length=200)
        parts.append(f"  Task: {task_text}")

    if result.get('summary'):
        summary_text = _truncate_content(result['summary'], max_length=500)
        parts.append(f"  Summary: {summary_text}")

    if result.get('status'):
        parts.append(f"  Status: {result['status']}")

    if not skip_files and result.get('files_created'):
        files = result['files_created']
        if isinstance(files, list):
            files = ', '.join(str(f) for f in files[:10])
            if len(result['files_created']) > 10:
                files += f" ... (+{len(result['files_created']) - 10} more)"
        parts.append(f"  Files Created: {files}")

    if result.get('working_directory'):
        parts.append(f"  Working Directory: {result['working_directory']}")

    return "\n".join(parts)


def _truncate_content(content, max_length: int = 1000) -> str:
    """Truncate content to max length with ellipsis."""
    if content is None:
        return ""
    content_str = str(content) if not isinstance(content, str) else content
    if len(content_str) > max_length:
        return content_str[:max_length] + "..."
    return content_str


def _collect_working_directory_files(
    directories: Set[str],
    max_files: int = DEFAULT_MAX_FILES_TO_LIST,
) -> str:
    """
    Collect file listing from working directories.

    Args:
        directories: Set of directory paths to scan
        max_files: Maximum number of files to list

    Returns:
        Formatted file listing string
    """
    all_files: List[str] = []

    for directory in directories:
        try:
            dir_path = Path(directory)
            if not dir_path.exists():
                continue

            for root, dirs, files in os.walk(dir_path):
                # Skip hidden and ignored directories
                dirs[:] = [
                    d for d in dirs
                    if not d.startswith('.')
                    and d not in SKIP_DIRECTORIES
                ]

                for file in files:
                    # Skip hidden files and ignored extensions
                    if file.startswith('.'):
                        continue
                    ext = Path(file).suffix.lower()
                    if ext in SKIP_EXTENSIONS:
                        continue

                    file_path = os.path.join(root, file)
                    try:
                        rel_path = os.path.relpath(file_path, directory)
                        all_files.append(rel_path)
                    except ValueError:
                        # On Windows, relpath can fail across drives
                        all_files.append(file_path)

                    if len(all_files) >= max_files * 2:
                        # Stop scanning if we have enough candidates
                        break

        except PermissionError:
            logger.debug(f"Permission denied accessing: {directory}")
        except Exception as e:
            logger.debug(f"Error scanning directory {directory}: {e}")

    if not all_files:
        return ""

    # Sort and limit
    all_files = sorted(set(all_files))[:max_files]

    parts = ["Generated Files:"]
    for f in all_files:
        parts.append(f"  - {f}")

    if len(all_files) == max_files:
        parts.append(f"  ... (showing first {max_files} files)")

    return "\n".join(parts)


def check_history_length(
    state: "TaskState",
    max_length: int = DEFAULT_MAX_HISTORY_LENGTH,
) -> Tuple[bool, int]:
    """
    Check if conversation history exceeds maximum length.

    Based on Eigent's check_conversation_history_length pattern.

    Args:
        state: TaskState with conversation_history
        max_length: Maximum allowed length in characters

    Returns:
        Tuple of (is_exceeded, total_length)
    """
    total_length = state.get_history_length()
    return total_length > max_length, total_length


# Warning threshold for context usage (80%)
CONTEXT_WARNING_THRESHOLD = 0.80


async def check_and_emit_context_warning(
    state: "TaskState",
    max_length: int = DEFAULT_MAX_HISTORY_LENGTH,
    warning_threshold: float = CONTEXT_WARNING_THRESHOLD,
) -> bool:
    """
    Check context usage and emit SSE warning if above threshold.

    Emits a context_warning event when conversation history reaches
    the warning threshold (default 80%) of max allowed length.

    Based on Eigent's pattern for proactive context management.

    Args:
        state: TaskState with conversation_history and put_event method
        max_length: Maximum allowed length in characters
        warning_threshold: Threshold percentage (0.0-1.0) to trigger warning

    Returns:
        True if warning was emitted, False otherwise
    """
    total_length = state.get_history_length()
    usage_percent = (total_length / max_length) * 100 if max_length > 0 else 0

    if usage_percent >= (warning_threshold * 100):
        # Check if state supports event emission
        if hasattr(state, 'put_event'):
            try:
                from ..base_agent.events import ContextWarningData

                await state.put_event(ContextWarningData(
                    task_id=getattr(state, 'task_id', None),
                    current_length=total_length,
                    max_length=max_length,
                    usage_percent=round(usage_percent, 1),
                    message=f"Conversation history at {usage_percent:.0f}% capacity ({total_length:,}/{max_length:,} chars)",
                    entries_count=len(state.conversation_history) if state.conversation_history else 0,
                ))
                logger.warning(
                    f"Context usage warning: {usage_percent:.1f}% "
                    f"({total_length:,}/{max_length:,} chars)"
                )
                return True
            except Exception as e:
                logger.debug(f"Failed to emit context warning: {e}")

    return False


def summarize_context_if_needed(
    state: "TaskState",
    max_length: int = DEFAULT_MAX_HISTORY_LENGTH,
    target_entries: int = 10,
) -> str:
    """
    Get context, summarizing if history is too long.

    If history exceeds max_length, returns only recent entries.

    Args:
        state: TaskState with conversation_history
        max_length: Maximum allowed length
        target_entries: Number of entries to keep when summarizing

    Returns:
        Context string (full or summarized)
    """
    exceeded, length = check_history_length(state, max_length)

    if exceeded:
        logger.info(
            f"History length ({length}) exceeds max ({max_length}), "
            f"using last {target_entries} entries"
        )
        return state.get_recent_context(max_entries=target_entries)

    return build_conversation_context(state)


def build_enhanced_prompt(
    state: "TaskState",
    current_task: str,
    include_context: bool = True,
    max_context_entries: Optional[int] = DEFAULT_MAX_CONTEXT_ENTRIES,
) -> str:
    """
    Build enhanced prompt with conversation context.

    Combines conversation history with current task for LLM prompt.
    Based on Eigent's prompt construction pattern.

    Args:
        state: TaskState with conversation_history
        current_task: Current task description
        include_context: Whether to include conversation context
        max_context_entries: Maximum context entries to include

    Returns:
        Enhanced prompt string
    """
    parts = []

    # Add conversation context if available and requested
    if include_context and state.conversation_history:
        context = build_conversation_context(
            state,
            max_entries=max_context_entries,
            skip_files=False,
        )
        if context:
            parts.append(context)

    # Add current task section
    parts.append("=== CURRENT TASK ===")
    parts.append(current_task)

    # Add working directory info
    if hasattr(state, 'working_directory') and state.working_directory:
        parts.append(f"\nWorking Directory: {state.working_directory}")

    return "\n\n".join(parts)


def record_task_completion(
    state: "TaskState",
    summary: str,
    files_created: Optional[List[str]] = None,
    status: str = "completed",
) -> None:
    """
    Record task completion in conversation history.

    Adds a task_result entry with completion information.

    Args:
        state: TaskState to update
        summary: Summary of what was accomplished
        files_created: List of created file paths
        status: Task status (completed, failed, etc.)
    """
    result_content = {
        'task': state.task,
        'summary': summary,
        'status': status,
        'working_directory': state.working_directory if hasattr(state, 'working_directory') else None,
    }

    if files_created:
        result_content['files_created'] = files_created

    state.add_conversation('task_result', result_content)
    logger.debug(f"Recorded task completion: {status}")


def record_user_message(state: "TaskState", message: str) -> None:
    """
    Record user message in conversation history.

    Args:
        state: TaskState to update
        message: User's message
    """
    state.add_conversation('user', message)


def record_assistant_response(state: "TaskState", response: str) -> None:
    """
    Record assistant response in conversation history.

    Args:
        state: TaskState to update
        response: Assistant's response
    """
    state.add_conversation('assistant', response)


def record_tool_call(
    state: "TaskState",
    tool_name: str,
    tool_input: Optional[Dict] = None,
    tool_result: Optional[str] = None,
) -> None:
    """
    Record tool call in conversation history.

    Args:
        state: TaskState to update
        tool_name: Name of the tool called
        tool_input: Tool input parameters
        tool_result: Tool execution result
    """
    content = {
        'name': tool_name,
        'input': tool_input,
        'result': tool_result,
    }
    state.add_conversation('tool_call', content)
