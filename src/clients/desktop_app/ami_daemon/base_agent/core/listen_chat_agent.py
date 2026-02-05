"""
ListenChatAgent - CAMEL ChatAgent with SSE event emission.

Ported from Eigent's ListenChatAgent to work with AMI's TaskState event system.
This agent wraps CAMEL's ChatAgent to emit SSE events for:
- Agent activation/deactivation
- Toolkit activation/deactivation
- Budget warnings
"""

import atexit
import asyncio
import concurrent.futures
import json
import logging
import re
from datetime import datetime
from threading import Event
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel

from camel.agents import ChatAgent
from camel.agents.chat_agent import (
    StreamingChatAgentResponse,
    AsyncStreamingChatAgentResponse,
)
from camel.agents._types import ToolCallRequest
from camel.memories import AgentMemory
from camel.messages import BaseMessage
from camel.models import BaseModelBackend, ModelManager, ModelProcessingError
from camel.responses import ChatAgentResponse
from camel.terminators import ResponseTerminator
from camel.toolkits import FunctionTool, RegisteredAgentToolkit
from camel.types.agents import ToolCallingRecord
from camel.types import ModelPlatformType, ModelType

from ..events import (
    ActivateAgentData,
    DeactivateAgentData,
    ActivateToolkitData,
    DeactivateToolkitData,
    NoticeData,
    AgentThinkingData,
)
from ..events.toolkit_listen import _run_async_safely

logger = logging.getLogger(__name__)

# Tool name prefix to Toolkit name mapping
# Used to infer toolkit name from tool function name when no decorator is present
_TOOL_PREFIX_TO_TOOLKIT = {
    "browser": "Browser Toolkit",
    "shell": "Terminal Toolkit",
    "terminal": "Terminal Toolkit",
    "search": "Search Toolkit",
    "note": "Note Taking Toolkit",
    "human": "Human Toolkit",
    "memory": "Memory Toolkit",
    "task": "Task Planning Toolkit",
    "calendar": "Calendar Toolkit",
    # Internal task management tools (ListenBrowserAgent)
    "get": "Task Planning Toolkit",      # get_current_plan
    "complete": "Task Planning Toolkit", # complete_subtask
    "report": "Task Planning Toolkit",   # report_subtask_failure
    "replan": "Task Planning Toolkit",   # replan_task
}


def _infer_toolkit_name(tool_name: str) -> str:
    """Infer toolkit name from tool function name.

    Used as fallback when tool has no decorator or toolkit instance.

    Args:
        tool_name: Tool function name (e.g., "complete_subtask", "browser_click")

    Returns:
        Toolkit name (e.g., "Task Planning Toolkit", "Browser Toolkit")
    """
    # Extract prefix (first word before underscore)
    prefix = tool_name.split("_")[0].lower() if "_" in tool_name else tool_name.lower()

    # Look up in mapping
    if prefix in _TOOL_PREFIX_TO_TOOLKIT:
        return _TOOL_PREFIX_TO_TOOLKIT[prefix]

    # Fallback: Title case the prefix
    return f"{prefix.title()} Toolkit"


# Shared thread pool executor for sync-to-async tool execution
# BUG-13: This is intentionally global to be shared across agents
# The pool is limited to 4 workers and cleaned up at process exit
_tool_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
_tool_executor_ref_count: int = 0  # BUG-13 fix: Track usage for optional cleanup


def _get_tool_executor() -> concurrent.futures.ThreadPoolExecutor:
    """Get or create shared thread pool executor for tool execution."""
    global _tool_executor, _tool_executor_ref_count
    if _tool_executor is None:
        _tool_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="tool_exec_"
        )
    _tool_executor_ref_count += 1
    return _tool_executor


def _release_tool_executor() -> None:
    """
    BUG-13 fix: Release a reference to the tool executor.

    Call this when an agent is done to allow optional cleanup.
    The executor is only shut down when all references are released
    AND force_cleanup is called, or at process exit.
    """
    global _tool_executor_ref_count
    if _tool_executor_ref_count > 0:
        _tool_executor_ref_count -= 1


def _cleanup_tool_executor(force: bool = False) -> None:
    """
    Clean up shared thread pool executor.

    Args:
        force: If True, shutdown immediately. If False, only shutdown
               when no references remain.
    """
    global _tool_executor, _tool_executor_ref_count
    if _tool_executor is not None:
        if force or _tool_executor_ref_count <= 0:
            try:
                _tool_executor.shutdown(wait=False)
                logger.debug("Tool executor shutdown")
            except Exception as e:
                logger.warning(f"Error during tool executor cleanup: {e}")
            finally:
                _tool_executor = None
                _tool_executor_ref_count = 0


# Register cleanup on exit
atexit.register(lambda: _cleanup_tool_executor(force=True))


class ListenChatAgent(ChatAgent):
    """
    CAMEL ChatAgent with SSE event emission for AMI.

    This agent extends CAMEL's ChatAgent to:
    - Emit activate_agent/deactivate_agent events on step()
    - Emit activate_toolkit/deactivate_toolkit events on tool execution
    - Handle budget exceeded errors
    - Support streaming responses with proper event emission

    Unlike Eigent's version which uses get_task_lock(), this uses
    a TaskState instance directly for event emission.
    """

    def __init__(
        self,
        task_state: Any,  # TaskState from quick_task_service
        agent_name: str,
        system_message: BaseMessage | str | None = None,
        model: (
            BaseModelBackend
            | ModelManager
            | Tuple[str, str]
            | str
            | ModelType
            | Tuple[ModelPlatformType, ModelType]
            | List[BaseModelBackend]
            | List[str]
            | List[ModelType]
            | List[Tuple[str, str]]
            | List[Tuple[ModelPlatformType, ModelType]]
            | None
        ) = None,
        memory: AgentMemory | None = None,
        message_window_size: int | None = None,
        token_limit: int | None = None,
        output_language: str | None = None,
        tools: List[FunctionTool | Callable[..., Any]] | None = None,
        toolkits_to_register_agent: List[RegisteredAgentToolkit] | None = None,
        external_tools: (
            List[FunctionTool | Callable[..., Any] | Dict[str, Any]] | None
        ) = None,
        response_terminators: List[ResponseTerminator] | None = None,
        scheduling_strategy: str = "round_robin",
        max_iteration: int | None = None,
        agent_id: str | None = None,
        stop_event: Event | None = None,
        tool_execution_timeout: float | None = None,
        mask_tool_output: bool = False,
        pause_event: asyncio.Event | None = None,
        prune_tool_calls_from_memory: bool = False,
        enable_snapshot_clean: bool = False,
        step_timeout: float | None = 900,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            system_message=system_message,
            model=model,
            memory=memory,
            message_window_size=message_window_size,
            token_limit=token_limit,
            output_language=output_language,
            tools=tools,
            toolkits_to_register_agent=toolkits_to_register_agent,
            external_tools=external_tools,
            response_terminators=response_terminators,
            scheduling_strategy=scheduling_strategy,
            max_iteration=max_iteration,
            agent_id=agent_id,
            stop_event=stop_event,
            tool_execution_timeout=tool_execution_timeout,
            mask_tool_output=mask_tool_output,
            pause_event=pause_event,
            prune_tool_calls_from_memory=prune_tool_calls_from_memory,
            enable_snapshot_clean=enable_snapshot_clean,
            step_timeout=step_timeout,
            **kwargs,
        )
        self._task_state = task_state
        self.agent_name = agent_name
        self.process_task_id: str = ""

        # Workflow guide for Memory-based navigation hints
        self._workflow_guide_content: Optional[str] = None
        self._memory_level: str = "L3"  # L1=strong, L2=medium, L3=weak guidance

        # Workflow hints for step-by-step execution tracking
        self._workflow_hints: List[Dict[str, Any]] = []
        self._current_hint_index: int = 0

        # IntentSequence cache for page operations (L3 Memory)
        self._cached_page_operations: Optional[str] = None
        self._cached_page_operations_url: Optional[str] = None
        self._cached_page_operations_ids: Optional[List[str]] = None
        self._current_page_url: Optional[str] = None  # Track current browser URL

        # Progress callback for external notifications (P2)
        self._progress_callback: Optional[Callable] = None

        # Human interaction callbacks (P2)
        self._human_ask_callback: Optional[Callable] = None
        self._human_message_callback: Optional[Callable] = None

        # Step counting for execution limits (P3)
        self._step_count: int = 0
        self._max_steps: int = 1000

        # NoteTakingToolkit reference for saving workflow guide to file
        self._note_toolkit: Optional[Any] = None

        # Export model-visible snapshots (quick-task only)
        self._export_model_visible_snapshots: bool = False
        self._snapshot_export_subdir: str = "model_visible_snapshots"
        self._snapshot_export_counter: int = 0
        self._current_tool_call_id: Optional[str] = None

        logger.info(f"[ListenChatAgent] Created: {agent_name}, agent_id={agent_id}")

    def enable_model_visible_snapshot_export(
        self,
        enabled: bool = True,
        export_subdir: str = "model_visible_snapshots",
    ) -> None:
        """Enable exporting model-visible page snapshots to workspace."""
        self._export_model_visible_snapshots = enabled
        if export_subdir:
            self._snapshot_export_subdir = export_subdir
        logger.info(
            f"[ListenChatAgent] Model-visible snapshot export "
            f"{'enabled' if enabled else 'disabled'}: {self._snapshot_export_subdir}"
        )

    def _write_model_visible_snapshot(
        self,
        func_name: str,
        content: str,
        was_truncated: bool,
    ) -> None:
        if not self._export_model_visible_snapshots:
            return

        dir_manager = getattr(self._task_state, "dir_manager", None) if self._task_state else None
        if not dir_manager:
            return

        try:
            self._snapshot_export_counter += 1
            tool_call_id = self._current_tool_call_id or "unknown"
            safe_tool = re.sub(r"[^A-Za-z0-9_-]+", "_", func_name) or "tool"
            safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", tool_call_id) or "unknown"
            filename = (
                f"{self._snapshot_export_subdir}/"
                f"snapshot_{self._snapshot_export_counter:04d}_{safe_tool}_{safe_id}.md"
            )

            header = [
                "# Model-visible page snapshot",
                f"tool: {func_name}",
                f"tool_call_id: {tool_call_id}",
                f"truncated: {str(was_truncated).lower()}",
                f"timestamp_utc: {datetime.utcnow().isoformat()}Z",
                "",
            ]
            dir_manager.write_file(filename, "\n".join(header) + content)
        except Exception as e:
            logger.warning(f"[ListenChatAgent] Failed to export model-visible snapshot: {e}")

    def _truncate_tool_result(
        self, func_name: str, result: Any
    ) -> Tuple[Any, bool]:
        truncated_result, was_truncated = super()._truncate_tool_result(func_name, result)

        if self._export_model_visible_snapshots:
            result_for_memory = truncated_result if was_truncated else result
            content_str = self._serialize_tool_result(result_for_memory)
            if content_str and "Page Snapshot" in content_str:
                self._write_model_visible_snapshot(func_name, content_str, was_truncated)

        return truncated_result, was_truncated

    def _record_tool_calling(
        self,
        func_name: str,
        args: Dict[str, Any],
        result: Any,
        tool_call_id: str,
        mask_output: bool = False,
        extra_content: Optional[Dict[str, Any]] = None,
    ):
        self._current_tool_call_id = tool_call_id
        try:
            return super()._record_tool_calling(
                func_name=func_name,
                args=args,
                result=result,
                tool_call_id=tool_call_id,
                mask_output=mask_output,
                extra_content=extra_content,
            )
        finally:
            self._current_tool_call_id = None

    def set_task_state(self, task_state: Any) -> None:
        """Update the task state for event emission."""
        self._task_state = task_state

    def _build_conversation_text_from_messages(
        self,
        messages: List[Any],
        include_summaries: bool = False,
    ) -> Tuple[str, List[str]]:
        """Build conversation text from messages for summarization.

        This override fixes a bug in CAMEL where tool result messages don't include
        the tool name (OpenAI's tool message format doesn't have 'name' field).
        We build a tool_call_id -> func_name mapping first, then use it to resolve
        tool names in tool result messages.

        Args:
            messages: List of messages to convert.
            include_summaries: Whether to include [CONTEXT_SUMMARY] messages.

        Returns:
            Tuple of (formatted conversation text, list of user messages).
        """
        conversation_lines = []
        user_messages: List[str] = []

        # First pass: build tool_call_id -> func_name mapping
        tool_call_id_to_name: Dict[str, str] = {}
        for message in messages:
            tool_calls = message.get('tool_calls')
            if tool_calls and isinstance(tool_calls, (list, tuple)):
                for tool_call in tool_calls:
                    if isinstance(tool_call, dict):
                        tc_id = tool_call.get('id', '')
                        func_name = tool_call.get('function', {}).get('name', '')
                        if tc_id and func_name:
                            tool_call_id_to_name[tc_id] = func_name
                    else:
                        # Handle object format
                        tc_id = getattr(tool_call, 'id', '') or getattr(
                            getattr(tool_call, 'function', None), 'id', ''
                        )
                        func_name = getattr(
                            getattr(tool_call, 'function', None), 'name', ''
                        )
                        if tc_id and func_name:
                            tool_call_id_to_name[tc_id] = func_name

        # Second pass: build conversation text
        for message in messages:
            role = message.get('role', 'unknown')
            content = message.get('content', '')

            # Skip summary messages if include_summaries is False
            if not include_summaries and isinstance(content, str):
                if content.startswith('[CONTEXT_SUMMARY]'):
                    continue

            # Handle tool call messages (assistant calling tools)
            tool_calls = message.get('tool_calls')
            if tool_calls and isinstance(tool_calls, (list, tuple)):
                for tool_call in tool_calls:
                    if isinstance(tool_call, dict):
                        func_name = tool_call.get('function', {}).get('name', 'unknown_tool')
                        func_args_str = tool_call.get('function', {}).get('arguments', '{}')
                    else:
                        func_name = getattr(
                            getattr(tool_call, 'function', None), 'name', 'unknown_tool'
                        )
                        func_args_str = getattr(
                            getattr(tool_call, 'function', None), 'arguments', '{}'
                        )

                    # Format arguments
                    try:
                        args_dict = json.loads(func_args_str) if func_args_str else {}
                        args_formatted = ', '.join(f"{k}={v}" for k, v in args_dict.items())
                    except (json.JSONDecodeError, ValueError, TypeError):
                        args_formatted = func_args_str

                    conversation_lines.append(f"[TOOL CALL] {func_name}({args_formatted})")

            # Handle tool response messages
            elif role == 'tool':
                # Try to get tool name from message, then fall back to tool_call_id mapping
                tool_name = message.get('name')
                if not tool_name:
                    tool_call_id = message.get('tool_call_id', '')
                    tool_name = tool_call_id_to_name.get(tool_call_id, 'unknown_tool')

                result_content = content if content else str(message.get('content', ''))
                # Truncate very long results for readability
                if len(result_content) > 500:
                    result_content = result_content[:500] + '...[truncated]'
                conversation_lines.append(f"[TOOL RESULT] {tool_name} → {result_content}")

            # Handle regular content messages (user/assistant/system)
            elif content:
                content = str(content)
                if role == 'user':
                    user_messages.append(content)
                conversation_lines.append(f"{role}: {content}")

        return "\n".join(conversation_lines).strip(), user_messages

    def set_progress_callback(self, callback: Callable) -> None:
        """Set callback for progress updates (P2).

        Args:
            callback: Async or sync function that receives (event, data) args.
        """
        self._progress_callback = callback
        logger.debug(f"[ListenChatAgent] {self.agent_name} progress callback set")

    def set_human_callbacks(
        self,
        ask_callback: Optional[Callable] = None,
        message_callback: Optional[Callable] = None
    ) -> None:
        """Set callbacks for human interaction (P2).

        Args:
            ask_callback: Called when agent needs to ask user a question.
            message_callback: Called when agent wants to send a message to user.
        """
        self._human_ask_callback = ask_callback
        self._human_message_callback = message_callback
        logger.debug(f"[ListenChatAgent] {self.agent_name} human callbacks set")

    async def _notify_progress(self, event: str, data: Dict[str, Any]) -> None:
        """Notify progress to callback if set (P2).

        Args:
            event: Event type (e.g., "step_started", "tool_executed", etc.).
            data: Event data dictionary.
        """
        if self._progress_callback:
            try:
                if asyncio.iscoroutinefunction(self._progress_callback):
                    await self._progress_callback(event, data)
                else:
                    self._progress_callback(event, data)
            except Exception as e:
                logger.error(f"[ListenChatAgent] Progress callback failed for {event}: {e}")

    def set_max_steps(self, max_steps: int) -> None:
        """Set maximum execution steps (P3).

        Args:
            max_steps: Maximum number of steps before stopping.
        """
        self._max_steps = max_steps
        logger.debug(f"[ListenChatAgent] {self.agent_name} max_steps set to {max_steps}")

    def reset_step_count(self) -> None:
        """Reset the step counter (P3)."""
        self._step_count = 0

    @property
    def step_count(self) -> int:
        """Get current step count (P3)."""
        return self._step_count

    def set_note_toolkit(self, note_toolkit: Any) -> None:
        """Set NoteTakingToolkit reference for saving workflow guide to file.

        Args:
            note_toolkit: NoteTakingToolkit instance.
        """
        self._note_toolkit = note_toolkit
        logger.debug(f"[ListenChatAgent] {self.agent_name} note_toolkit set")

    def set_workflow_guide(self, content: str, memory_level: str = "L2") -> None:
        """Set workflow guide content to inject into every LLM call.

        This enables Memory-based navigation guidance where historical
        successful workflows are used to guide the agent's actions.

        The workflow guide is also saved to notes/workflow_guide.md for
        persistence and user visibility.

        Args:
            content: Formatted workflow guide from MemoryToolkit.
            memory_level: Memory confidence level (L1=high, L2=medium, L3=low).
                - L1: Complete cognitive_phrase match, follow strictly
                - L2: Partial path match, use as reference
                - L3: No match, use judgment
        """
        self._workflow_guide_content = content
        self._memory_level = memory_level
        logger.info(
            f"[ListenChatAgent] {self.agent_name} workflow guide set "
            f"(level={memory_level}, {len(content)} chars)"
        )

        # Save workflow guide to note if NoteTakingToolkit is available
        if self._note_toolkit:
            try:
                result = self._note_toolkit.create_note(
                    note_name="workflow_guide",
                    content=content,
                    overwrite=True
                )
                logger.info(f"[ListenChatAgent] Workflow guide saved as note: {result}")
            except Exception as e:
                logger.warning(f"[ListenChatAgent] Failed to save workflow guide note: {e}")

    def is_cancelled(self) -> bool:
        """Check if the task has been cancelled.

        Returns:
            True if cancellation was requested.
        """
        if self._task_state and hasattr(self._task_state, '_cancel_event'):
            return self._task_state._cancel_event.is_set()
        return False

    # ===== Workflow Hints (Step-by-step execution tracking) =====

    def set_workflow_hints(self, hints: List[Dict[str, Any]]) -> None:
        """Set workflow hints for step-by-step execution tracking.

        Workflow hints are individual steps extracted from the workflow_guide
        that the LLM can mark as complete using workflow_hint_done().

        This method also registers the workflow_hint_done tool so the LLM
        can call it during execution.

        Args:
            hints: List of hint dictionaries with 'description' and optional
                   'target_description', 'action_type', etc.
        """
        self._workflow_hints = hints
        self._current_hint_index = 0
        logger.info(
            f"[ListenChatAgent] {self.agent_name} workflow hints set "
            f"({len(hints)} steps)"
        )

        # Auto-register workflow_hint_done tool when hints are set
        if hints:
            self.register_workflow_hint_tool()

    def workflow_hint_done(self, summary: str = "") -> str:
        """Mark current workflow hint as complete and advance to next.

        This method is designed to be called by the LLM as a tool to track
        progress through the workflow steps.

        Args:
            summary: Brief summary of what was accomplished in this step.

        Returns:
            Information about the next hint, or completion message.
        """
        if not self._workflow_hints:
            return "No workflow hints available."

        if self._current_hint_index >= len(self._workflow_hints):
            return "All workflow hints already completed."

        # Log completion of current hint
        completed_hint = self._workflow_hints[self._current_hint_index]
        logger.info(
            f"[ListenChatAgent] {self.agent_name} hint {self._current_hint_index + 1} "
            f"completed: {completed_hint.get('description', 'N/A')[:50]}"
        )

        # Advance to next step
        self._current_hint_index += 1

        if self._current_hint_index >= len(self._workflow_hints):
            return (
                f"All {len(self._workflow_hints)} workflow hints completed. "
                "Continue with any remaining task requirements."
            )

        # Return info about next step
        next_hint = self._workflow_hints[self._current_hint_index]
        return f"""Hint completed. Next step:

**Step {self._current_hint_index + 1}/{len(self._workflow_hints)}**
Action: {next_hint.get('description', 'N/A')}
Target: {next_hint.get('target_description', 'N/A')}
"""

    def get_workflow_hint_done_tool(self) -> FunctionTool:
        """Get workflow_hint_done as a FunctionTool for LLM registration.

        This allows the LLM to call workflow_hint_done() as a tool to mark
        workflow steps as complete during execution.

        Returns:
            FunctionTool wrapping workflow_hint_done method.

        Example usage:
            agent = ListenChatAgent(...)
            hint_tool = agent.get_workflow_hint_done_tool()
            # Add to agent's tools during execution setup
        """
        return FunctionTool(self.workflow_hint_done)

    def register_workflow_hint_tool(self) -> None:
        """Register workflow_hint_done as an LLM-callable tool.

        This adds the workflow_hint_done method to the agent's internal tools
        AND registers its schema so the LLM can call it.

        Should be called after set_workflow_hints() when workflow hints are active.

        Note: Due to CAMEL's architecture, we need to register both the tool
        and its schema. The tool goes into _internal_tools for execution,
        and the schema goes into model_backend for LLM visibility.
        """
        if not self._workflow_hints:
            logger.debug(
                f"[ListenChatAgent] {self.agent_name} skipping hint tool registration "
                "(no workflow hints set)"
            )
            return

        hint_tool = self.get_workflow_hint_done_tool()
        tool_name = hint_tool.get_function_name()

        # Check if already registered
        if tool_name in self._internal_tools:
            logger.debug(
                f"[ListenChatAgent] {self.agent_name} workflow_hint_done already registered"
            )
            return

        # Register the tool for execution
        self._internal_tools[tool_name] = hint_tool

        # Register with CAMEL's ChatAgent so LLM can see the tool
        # Use inherited add_tool() method which properly updates tool list
        try:
            self.add_tool(hint_tool)
        except Exception as e:
            logger.debug(f"[ListenChatAgent] add_tool for {tool_name} failed: {e}")

        logger.info(
            f"[ListenChatAgent] {self.agent_name} registered workflow_hint_done tool "
            f"(schema added)"
        )

    def get_current_hint(self) -> Optional[Dict[str, Any]]:
        """Get the current workflow hint.

        Returns:
            Current hint dictionary or None if no hints or all completed.
        """
        if not self._workflow_hints:
            return None
        if self._current_hint_index >= len(self._workflow_hints):
            return None
        return self._workflow_hints[self._current_hint_index]

    def _get_current_hint_context(self) -> str:
        """Get context string for the current workflow hint.

        This is injected into the message to guide the LLM on the current step.

        Returns:
            Context string describing current hint, or empty if no hints.
        """
        if not self._workflow_hints or self._current_hint_index >= len(self._workflow_hints):
            return ""

        hint = self._workflow_hints[self._current_hint_index]
        total = len(self._workflow_hints)
        current = self._current_hint_index + 1

        context = f"""
## Current Memory Hint (Step {current}/{total})
**Action:** {hint.get('description', hint.get('type', 'Unknown'))}
**Target:** {hint.get('target_description', 'Next page')}

Remember: This is a GUIDE. Adapt to your actual task goal.
Call `workflow_hint_done` when this navigation step is complete.
"""
        return context

    @property
    def workflow_hints_progress(self) -> Dict[str, Any]:
        """Get workflow hints progress information.

        Returns:
            Dictionary with current_step, total_steps, and completed status.
        """
        return {
            "current_step": self._current_hint_index + 1,
            "total_steps": len(self._workflow_hints),
            "completed": self._current_hint_index >= len(self._workflow_hints),
            "has_hints": len(self._workflow_hints) > 0,
        }

    # ===== IntentSequence Cache (L3 Memory - Page Operations) =====

    def set_current_url(self, url: str) -> None:
        """Set the current browser URL for cache management.

        This should be called by BrowserToolkit or the execution loop after
        each browser navigation to enable proper cache invalidation.

        Args:
            url: The current browser URL.
        """
        old_url = self._current_page_url
        self._current_page_url = url

        # Check if URL changed and clear stale cache
        if old_url and url != old_url:
            self.check_and_clear_stale_cache(url)
            logger.debug(
                f"[ListenChatAgent] {self.agent_name} URL changed: "
                f"{old_url[:30]}... -> {url[:30]}..."
            )

    def cache_page_operations(
        self,
        url: str,
        operations: str,
        intent_sequence_ids: Optional[List[str]] = None,
    ) -> None:
        """Cache page operations query result.

        Called when query_page_operations returns results. The cache is used
        to inject page operations into subsequent LLM calls while on the same page.

        Args:
            url: The URL for which operations were queried.
            operations: Formatted string of available operations on this page.
            intent_sequence_ids: Optional list of IntentSequence IDs associated
                with these operations.
        """
        previous_url = self._cached_page_operations_url
        self._cached_page_operations = operations
        self._cached_page_operations_url = url
        if intent_sequence_ids is not None:
            self._cached_page_operations_ids = intent_sequence_ids
        elif previous_url != url:
            # Avoid leaking IDs across pages when caller doesn't provide IDs.
            self._cached_page_operations_ids = None
        logger.debug(
            f"[ListenChatAgent] {self.agent_name} cached page operations "
            f"for {url[:50]}... ({len(operations)} chars)"
        )

    def clear_page_operations_cache(self) -> None:
        """Clear the page operations cache.

        Called when URL changes to invalidate stale cache.
        """
        if self._cached_page_operations:
            logger.debug(
                f"[ListenChatAgent] {self.agent_name} cleared page operations cache"
            )
        self._cached_page_operations = None
        self._cached_page_operations_url = None
        self._cached_page_operations_ids = None

    def get_cached_page_operations(self, current_url: str) -> Optional[str]:
        """Get cached page operations if URL matches.

        Args:
            current_url: The current page URL to check against cache.

        Returns:
            Cached operations string if URL matches, None otherwise.
        """
        if (
            self._cached_page_operations
            and self._cached_page_operations_url
            and self._cached_page_operations_url == current_url
        ):
            return self._cached_page_operations
        return None

    def check_and_clear_stale_cache(self, current_url: str) -> bool:
        """Check if URL changed and clear cache if stale.

        Args:
            current_url: The current page URL.

        Returns:
            True if cache was cleared (URL changed), False otherwise.
        """
        if (
            self._cached_page_operations_url
            and current_url != self._cached_page_operations_url
        ):
            self.clear_page_operations_cache()
            return True
        return False

    def _check_and_inject_page_operations_cache(
        self,
        current_url: str,
        message: Union[BaseMessage, str]
    ) -> Union[BaseMessage, str]:
        """Check URL change and inject cached page operations if available.

        This method:
        1. Clears stale cache if URL changed
        2. Injects cached page operations into the message if available

        Args:
            current_url: The current page URL.
            message: Original input message.

        Returns:
            Message with page operations injected (if cache hit) or original.
        """
        # Check for stale cache (URL changed)
        self.check_and_clear_stale_cache(current_url)

        # Inject if we have cached operations for this URL
        cached_ops = self.get_cached_page_operations(current_url)
        if cached_ops:
            task_id = self._task_state.task_id if self._task_state else "unknown"
            intent_ids = self._cached_page_operations_ids or []
            if intent_ids:
                preview = ", ".join(intent_ids[:10])
                if len(intent_ids) > 10:
                    preview = f"{preview}...(+{len(intent_ids) - 10})"
                logger.info(
                    f"[Task {task_id}] [Memory] Injected page operations "
                    f"from IntentSequence ids=[{preview}] "
                    f"(url={current_url[:120]}..., length={len(cached_ops)})"
                )
            else:
                logger.info(
                    f"[Task {task_id}] [Memory] Injected page operations "
                    f"(no intent_sequence_ids) "
                    f"(url={current_url[:120]}..., length={len(cached_ops)})"
                )
            return self._inject_page_operations_to_messages(message, cached_ops)
        return message

    def _inject_page_operations_to_messages(
        self,
        message: Union[BaseMessage, str],
        page_operations: str,
    ) -> Union[BaseMessage, str]:
        """Inject cached page operations into the message.

        This provides the LLM with previously-learned operations for the
        current page, avoiding repeated query_page_operations calls.

        Args:
            message: Original input message.
            page_operations: Formatted string of page operations from IntentSequence.

        Returns:
            Message with page operations appended.
        """
        logger.debug(
            "[Memory] Injecting page operations into message "
            f"(length={len(page_operations)})"
        )
        operations_section = f"""

## Available Page Operations (from Memory)
The following operations have been recorded for this page type:

{page_operations}

Use these operations as guidance for interacting with this page.
"""
        if isinstance(message, BaseMessage):
            new_content = f"{message.content}{operations_section}"
            return message.create_new_instance(new_content)
        else:
            return f"{message}{operations_section}"

    # ===== P2: Workflow Hints Building and Formatting =====

    # Log-sanitization constants for memory content (P3)
    _MAX_GUIDE_LINES: int = 30
    _MAX_GUIDE_CHARS: int = 4096
    _MAX_LINE_LEN: int = 200

    def _sanitize_guide(self, content: str) -> str:
        """Sanitize workflow guide content to prevent prompt overflow (P3).

        Truncates content to reasonable limits while preserving structure.

        Args:
            content: Raw workflow guide content.

        Returns:
            Sanitized and truncated content.
        """
        lines = content.splitlines()
        out_lines: List[str] = []
        total_chars = 0

        for line in lines[:self._MAX_GUIDE_LINES]:
            # Truncate individual lines
            if len(line) > self._MAX_LINE_LEN:
                line = line[:self._MAX_LINE_LEN - 14] + "...(truncated)"

            if total_chars + len(line) + 1 > self._MAX_GUIDE_CHARS:
                remaining = self._MAX_GUIDE_CHARS - total_chars
                if remaining > 0:
                    line = line[:remaining]
                    out_lines.append(line)
                break

            out_lines.append(line)
            total_chars += len(line) + 1

        if len(lines) > self._MAX_GUIDE_LINES or total_chars >= self._MAX_GUIDE_CHARS:
            out_lines.append("[workflow_guide truncated]")

        return "\n".join(out_lines)

    def _build_workflow_hints(
        self,
        workflow_result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract workflow hints from Reasoner/Memory result (P2).

        Converts states and actions into a list of hint dicts that can
        guide the agent through step-by-step execution.

        Args:
            workflow_result: Result containing 'states' and 'actions' lists.

        Returns:
            List of hint dicts with description, type, target info.
        """
        states = workflow_result.get("states", [])
        actions = workflow_result.get("actions", [])

        logger.debug(
            f"[ListenChatAgent] Building workflow hints: "
            f"{len(states)} states, {len(actions)} actions"
        )

        # Build state lookup by ID
        state_by_id: Dict[str, Any] = {}
        for state in states:
            state_id = (
                state.get("id") if isinstance(state, dict)
                else getattr(state, "id", None)
            )
            if state_id:
                state_by_id[state_id] = state

        hints = []
        for action in actions:
            # Extract action info (handle both dict and object)
            if hasattr(action, 'description'):
                action_description = action.description or ""
                action_type = action.type or ""
                target_state_id = action.target
            else:
                action_description = action.get("description", "")
                action_type = action.get("type", "")
                target_state_id = action.get("target", "")

            # Get target state info
            target_state = state_by_id.get(target_state_id, {})
            if hasattr(target_state, 'description'):
                target_description = (
                    target_state.description or target_state.page_title or ""
                )
                target_url = target_state.page_url or ""
            else:
                target_description = (
                    target_state.get("description", "") or
                    target_state.get("page_title", "")
                )
                target_url = target_state.get("page_url", "")

            hints.append({
                "description": action_description,
                "type": action_type,
                "target_description": target_description,
                "target_url": target_url,
            })

        return hints

    def _format_workflow_hints_for_prompt(
        self,
        workflow_result: Optional[Dict[str, Any]],
        memory_level: str,
    ) -> str:
        """Format Memory/Reasoner result into prompt context for LLM (P2).

        Creates a structured memory guidance section appropriate for
        the memory level.

        Args:
            workflow_result: The result containing states and actions.
            memory_level: The determined memory level ("L1", "L2", or "L3").

        Returns:
            Formatted string for injection into LLM prompt.
        """
        if not workflow_result or memory_level == "L3":
            return """## Memory Guidance [L3]
No complete path found in memory. Use your judgment to complete the task step by step."""

        states = workflow_result.get("states", [])
        actions = workflow_result.get("actions", [])

        if memory_level == "L1":
            header = f"""## Memory Guidance [L1 - Complete Path]
**Confidence**: High - this exact workflow pattern was successful before

**IMPORTANT**: This path is a GUIDE, not a script. You must:
- Follow the general navigation pattern
- Adapt to current page content (items may have changed)
- Make decisions based on the user's specific task goal

### Suggested Navigation Path ({len(states)} steps):
"""
        else:  # L2
            header = f"""## Memory Guidance [L2 - Partial Match]
**Confidence**: Medium - some steps have memory support

### Available Page Information:
"""

        # Build path description
        path_lines = []
        for i, state in enumerate(states):
            # Extract state info
            if isinstance(state, dict):
                state_desc = state.get("description", "Unknown page")
                state_url = state.get("page_url", "")
            else:
                state_desc = (
                    getattr(state, "description", "Unknown page") or "Unknown page"
                )
                state_url = getattr(state, "page_url", "") or ""

            step_line = f"\n**Step {i + 1}**: {state_desc}"
            if state_url:
                step_line += f"\n  URL Pattern: {state_url}"

            # Add action to next state
            if i < len(actions):
                action = actions[i]
                if isinstance(action, dict):
                    action_desc = action.get("description", "")
                else:
                    action_desc = getattr(action, "description", "") or ""

                if action_desc:
                    step_line += f"\n  → Next: {action_desc}"

            path_lines.append(step_line)

        result = header + "\n".join(path_lines)
        return self._sanitize_guide(result)

    def _inject_workflow_guide(
        self,
        message: Union[BaseMessage, str]
    ) -> Union[BaseMessage, str]:
        """Inject workflow guide into the input message.

        The injection content varies based on memory_level:
        - L1: Strong guidance with strict following instructions
        - L2: Medium guidance with reference suggestions
        - L3: Weak guidance, use judgment

        Args:
            message: Original input message (BaseMessage or str).

        Returns:
            Message with workflow guide appended.
        """
        if not self._workflow_guide_content:
            return message

        # Check if workflow guide is already injected to avoid duplication
        # This can happen when _build_loop_message() already added _build_decision_guide()
        msg_content = message.content if isinstance(message, BaseMessage) else message
        if "## Workflow Guide" in msg_content or "## Memory Guidance" in msg_content:
            logger.debug("[ListenChatAgent] Skipping workflow guide injection - already present")
            return message

        # Build header based on memory level
        if self._memory_level == "L1":
            header = """## Memory Guidance [L1 - Complete Path]
**Confidence**: High - This is a previously successful complete workflow.
**Instructions**: Follow the steps STRICTLY in order. Do NOT skip or modify steps."""
            decision_guide = """## Decision Guide (CRITICAL - FOLLOW STRICTLY!)
You have a complete, previously successful workflow. Follow it exactly:
1. Identify your current step in the workflow
2. Execute the EXACT action specified for that step
3. Do NOT take shortcuts or modify the approach
4. Mark each step complete before moving to the next"""
        elif self._memory_level == "L2":
            header = """## Memory Guidance [L2 - Partial Match]
**Confidence**: Medium - This is a partial navigation path from similar tasks.
**Instructions**: Use as reference, adapt as needed for your specific task."""
            decision_guide = """## Decision Guide (USE AS REFERENCE)
You have a partial navigation path. Use it as guidance:
1. Check if your current page matches a step in the path
2. If yes, follow the suggested action
3. If the path doesn't cover your current situation, use your judgment
4. The path shows the general direction, but may need adaptation"""
        else:  # L3
            header = """## Memory Guidance [L3 - No Direct Match]
**Confidence**: Low - No complete workflow found for this task.
**Instructions**: Use your own judgment to complete the task."""
            decision_guide = """## Decision Guide (USE YOUR JUDGMENT)
No matching workflow found. Proceed with:
1. Analyze the current page and task requirements
2. Choose the most logical action to progress
3. Document your findings as you go"""

        # Add current hint context if workflow hints are active
        current_hint_context = self._get_current_hint_context()

        workflow_section = f"""

{header}

{self._workflow_guide_content}

{decision_guide}
{current_hint_context}"""
        if isinstance(message, BaseMessage):
            # Append to BaseMessage content
            new_content = f"{message.content}{workflow_section}"
            return message.create_new_instance(new_content)
        else:
            # String message
            return f"{message}{workflow_section}"

    async def _emit_event(self, event: Any) -> None:
        """Emit an event via task state."""
        if self._task_state and hasattr(self._task_state, 'put_event'):
            await self._task_state.put_event(event)

    def step(
        self,
        input_message: BaseMessage | str,
        response_format: type[BaseModel] | None = None,
    ) -> ChatAgentResponse | StreamingChatAgentResponse:
        """Execute a step with workflow guide injection and SSE event emission."""
        task_id = self._task_state.task_id if self._task_state else None

        # Inject workflow guide into input message if available (same as astep)
        if self._workflow_guide_content:
            input_message = self._inject_workflow_guide(input_message)

        # P1: Inject cached page operations if available for current URL
        if self._current_page_url and self._cached_page_operations:
            input_message = self._check_and_inject_page_operations_cache(
                self._current_page_url, input_message
            )

        # Emit activation event (safely handles both sync and async contexts)
        _run_async_safely(self._emit_event(ActivateAgentData(
            task_id=task_id,
            agent_name=self.agent_name,
            agent_id=self.agent_id,
            process_task_id=self.process_task_id,
            message=(
                input_message.content
                if isinstance(input_message, BaseMessage)
                else input_message
            )[:500],
        )))

        error_info = None
        message = None
        res = None
        total_tokens = 0

        logger.debug(f"[ListenChatAgent] {self.agent_name} starting step")

        try:
            res = super().step(input_message, response_format)
        except ModelProcessingError as e:
            res = None
            error_info = e
            if "Budget has been exceeded" in str(e):
                message = "Budget has been exceeded"
                logger.warning(f"[ListenChatAgent] {self.agent_name} budget exceeded")
                _run_async_safely(self._emit_event(NoticeData(
                    task_id=task_id,
                    level="error",
                    title="Budget Exceeded",
                    message="The budget for this task has been exceeded",
                )))
            else:
                message = str(e)
                logger.error(f"[ListenChatAgent] {self.agent_name} model error: {e}")
        except Exception as e:
            res = None
            error_info = e
            logger.error(f"[ListenChatAgent] {self.agent_name} error: {e}", exc_info=True)
            message = f"Error processing message: {e!s}"

        if res is not None:
            if isinstance(res, StreamingChatAgentResponse):
                # Wrap streaming response to emit deactivation at end
                def _stream_with_deactivate():
                    last_response: ChatAgentResponse | None = None
                    accumulated_content = ""
                    try:
                        for chunk in res:
                            last_response = chunk
                            if chunk.msg and chunk.msg.content:
                                accumulated_content += chunk.msg.content
                            yield chunk
                    finally:
                        tokens = 0
                        if last_response:
                            usage_info = (
                                last_response.info.get("usage")
                                or last_response.info.get("token_usage")
                                or {}
                            )
                            if usage_info:
                                tokens = usage_info.get("total_tokens", 0)
                        _run_async_safely(self._emit_event(DeactivateAgentData(
                            task_id=task_id,
                            agent_name=self.agent_name,
                            agent_id=self.agent_id,
                            process_task_id=self.process_task_id,
                            message=accumulated_content[:500],
                            total_tokens=tokens,
                        )))

                return StreamingChatAgentResponse(_stream_with_deactivate())

            message = res.msg.content if res.msg else ""
            usage_info = res.info.get("usage") or res.info.get("token_usage") or {}
            total_tokens = usage_info.get("total_tokens", 0) if usage_info else 0
            logger.info(f"[ListenChatAgent] {self.agent_name} completed, tokens={total_tokens}")

        assert message is not None

        # Emit deactivation event (safely handles both sync and async contexts)
        _run_async_safely(self._emit_event(DeactivateAgentData(
            task_id=task_id,
            agent_name=self.agent_name,
            agent_id=self.agent_id,
            process_task_id=self.process_task_id,
            message=message[:500] if message else "",
            total_tokens=total_tokens,
        )))

        if error_info is not None:
            raise error_info
        assert res is not None
        return res

    async def astep(
        self,
        input_message: BaseMessage | str,
        response_format: type[BaseModel] | None = None,
    ) -> ChatAgentResponse | AsyncStreamingChatAgentResponse:
        """Execute an async step with workflow guide injection and SSE event emission."""
        # P0: Check for cancellation at the start of each step
        if self.is_cancelled():
            logger.info(f"[ListenChatAgent] {self.agent_name} cancelled before astep")
            raise asyncio.CancelledError("Task was cancelled")

        # P3: Increment step count and check limit
        self._step_count += 1
        if self._step_count > self._max_steps:
            logger.warning(
                f"[ListenChatAgent] {self.agent_name} exceeded max steps "
                f"({self._step_count}/{self._max_steps})"
            )
            raise RuntimeError(f"Maximum steps exceeded: {self._max_steps}")

        task_id = self._task_state.task_id if self._task_state else None

        # Inject workflow guide into input message if available
        if self._workflow_guide_content:
            input_message = self._inject_workflow_guide(input_message)

        # P1: Inject cached page operations if available for current URL
        if self._current_page_url and self._cached_page_operations:
            input_message = self._check_and_inject_page_operations_cache(
                self._current_page_url, input_message
            )

        # P2: Notify progress callback of step start
        await self._notify_progress("step_started", {
            "step": self._step_count,
            "max_steps": self._max_steps,
            "agent_name": self.agent_name,
        })

        # Emit activation event
        await self._emit_event(ActivateAgentData(
            task_id=task_id,
            agent_name=self.agent_name,
            agent_id=self.agent_id,
            process_task_id=self.process_task_id,
            message=(
                input_message.content
                if isinstance(input_message, BaseMessage)
                else input_message
            )[:500],
        ))

        error_info = None
        message = None
        res = None
        total_tokens = 0

        logger.debug(f"[ListenChatAgent] {self.agent_name} starting async step")

        try:
            res = await super().astep(input_message, response_format)
            if isinstance(res, AsyncStreamingChatAgentResponse):
                res = await res._get_final_response()
        except ModelProcessingError as e:
            res = None
            error_info = e
            if "Budget has been exceeded" in str(e):
                message = "Budget has been exceeded"
                logger.warning(f"[ListenChatAgent] {self.agent_name} budget exceeded")
                await self._emit_event(NoticeData(
                    task_id=task_id,
                    level="error",
                    title="Budget Exceeded",
                    message="The budget for this task has been exceeded",
                ))
            else:
                message = str(e)
                logger.error(f"[ListenChatAgent] {self.agent_name} model error: {e}")
        except Exception as e:
            res = None
            error_info = e
            logger.error(f"[ListenChatAgent] {self.agent_name} async error: {e}", exc_info=True)
            message = f"Error processing message: {e!s}"

        if res is not None:
            message = res.msg.content if res.msg else ""
            usage_info = res.info.get("usage") or res.info.get("token_usage") or {}
            total_tokens = usage_info.get("total_tokens", 0)
            logger.info(f"[ListenChatAgent] {self.agent_name} completed, tokens={total_tokens}")

            # Emit thinking event for frontend AgentTab display
            # This shows the agent's response/reasoning in the timeline
            tool_calls = res.info.get("tool_calls") or []
            if message:
                # LLM returned text content - use as thinking
                thinking_preview = message[:500] if len(message) > 500 else message
                await self._emit_event(AgentThinkingData(
                    task_id=task_id,
                    agent_name=self.agent_name,
                    thinking=thinking_preview,
                    step=self._step_count,
                ))
            elif tool_calls:
                # LLM only returned tool calls - show what tools are being called
                tool_names = []
                for tc in tool_calls:
                    if hasattr(tc, 'func_name'):
                        tool_names.append(tc.func_name)
                    elif hasattr(tc, 'function') and hasattr(tc.function, 'name'):
                        tool_names.append(tc.function.name)
                    elif isinstance(tc, dict):
                        tool_names.append(tc.get('name', tc.get('function', {}).get('name', 'unknown')))
                if tool_names:
                    thinking_preview = f"Calling tools: {', '.join(tool_names)}"
                    await self._emit_event(AgentThinkingData(
                        task_id=task_id,
                        agent_name=self.agent_name,
                        thinking=thinking_preview,
                        step=self._step_count,
                    ))

        assert message is not None

        # P2: Notify progress callback of step completion
        await self._notify_progress("step_completed", {
            "step": self._step_count,
            "max_steps": self._max_steps,
            "agent_name": self.agent_name,
            "total_tokens": total_tokens,
            "success": error_info is None,
        })

        # Emit deactivation event
        await self._emit_event(DeactivateAgentData(
            task_id=task_id,
            agent_name=self.agent_name,
            agent_id=self.agent_id,
            process_task_id=self.process_task_id,
            message=message[:500] if message else "",
            total_tokens=total_tokens,
        ))

        if error_info is not None:
            raise error_info
        assert res is not None
        return res

    def _execute_tool(self, tool_call_request: ToolCallRequest) -> ToolCallingRecord:
        """Execute a tool with SSE event emission."""
        func_name = tool_call_request.tool_name
        tool: FunctionTool = self._internal_tools[func_name]
        task_id = self._task_state.task_id if self._task_state else None

        # Route async functions to async execution
        if asyncio.iscoroutinefunction(tool.func):
            # Handle both running and non-running event loop cases
            try:
                asyncio.get_running_loop()
                # We're in an async context - can't use asyncio.run()
                # Use shared thread pool to run the async tool
                future = _get_tool_executor().submit(
                    asyncio.run,
                    self._aexecute_tool(tool_call_request)
                )
                return future.result()
            except RuntimeError:
                # No running event loop, we can use asyncio.run()
                return asyncio.run(self._aexecute_tool(tool_call_request))

        args = tool_call_request.args
        tool_call_id = tool_call_request.tool_call_id

        # Check for @listen_toolkit decorator
        has_listen_decorator = hasattr(tool.func, "__wrapped__")

        try:
            # Get toolkit name
            toolkit_name = None
            if hasattr(tool, "_toolkit_name"):
                toolkit_name = tool._toolkit_name
            elif hasattr(tool, "func"):
                func = tool.func
                if hasattr(func, "_toolkit_name"):
                    toolkit_name = func._toolkit_name
                elif hasattr(func, "__func__") and hasattr(func.__func__, "_toolkit_name"):
                    toolkit_name = func.__func__._toolkit_name
                elif hasattr(func, "__self__"):
                    toolkit_instance = func.__self__
                    if hasattr(toolkit_instance, "toolkit_name") and callable(toolkit_instance.toolkit_name):
                        toolkit_name = toolkit_instance.toolkit_name()
            if not toolkit_name:
                # Infer toolkit name from function name prefix
                toolkit_name = _infer_toolkit_name(func_name)

            logger.debug(f"[ListenChatAgent] {self.agent_name} executing tool: {func_name}")

            # Emit activation if not handled by decorator
            if not has_listen_decorator:
                _run_async_safely(self._emit_event(ActivateToolkitData(
                    task_id=task_id,
                    agent_name=self.agent_name,
                    toolkit_name=toolkit_name,
                    method_name=func_name,
                    message=json.dumps(args, ensure_ascii=False)[:500],
                )))

            raw_result = tool(**args)

            if self.mask_tool_output:
                self._secure_result_store[tool_call_id] = raw_result
                result = "[Tool executed successfully, output masked]"
                mask_flag = True
            else:
                result = raw_result
                mask_flag = False

            # Prepare result message
            if isinstance(result, str):
                result_msg = result[:500]
            else:
                result_str = repr(result)
                result_msg = result_str[:500]

            # Emit deactivation if not handled by decorator
            if not has_listen_decorator:
                _run_async_safely(self._emit_event(DeactivateToolkitData(
                    task_id=task_id,
                    agent_name=self.agent_name,
                    toolkit_name=toolkit_name,
                    method_name=func_name,
                    message=result_msg,
                )))

        except Exception as e:
            error_msg = f"Error executing tool '{func_name}': {e!s}"
            result = f"Tool execution failed: {error_msg}"
            mask_flag = False
            logger.error(f"[ListenChatAgent] Tool execution failed: {e}", exc_info=True)

        return self._record_tool_calling(
            func_name,
            args,
            result,
            tool_call_id,
            mask_output=mask_flag,
            extra_content=tool_call_request.extra_content,
        )

    async def _aexecute_tool(self, tool_call_request: ToolCallRequest) -> ToolCallingRecord:
        """Execute a tool asynchronously with SSE event emission."""
        func_name = tool_call_request.tool_name
        tool: FunctionTool = self._internal_tools[func_name]
        task_id = self._task_state.task_id if self._task_state else None
        args = tool_call_request.args
        tool_call_id = tool_call_request.tool_call_id

        # Get toolkit name
        toolkit_name = None
        if hasattr(tool, "_toolkit_name"):
            toolkit_name = tool._toolkit_name
        elif hasattr(tool, "func"):
            # Check func itself or its __func__ (for bound methods)
            func = tool.func
            if hasattr(func, "_toolkit_name"):
                toolkit_name = func._toolkit_name
            elif hasattr(func, "__func__") and hasattr(func.__func__, "_toolkit_name"):
                toolkit_name = func.__func__._toolkit_name
            elif hasattr(func, "__self__"):
                toolkit_instance = func.__self__
                if hasattr(toolkit_instance, "toolkit_name") and callable(toolkit_instance.toolkit_name):
                    toolkit_name = toolkit_instance.toolkit_name()
        if not toolkit_name:
            # Infer toolkit name from function name prefix
            toolkit_name = _infer_toolkit_name(func_name)

        logger.debug(f"[ListenChatAgent] {self.agent_name} executing async tool: {func_name}")

        # Emit activation event
        await self._emit_event(ActivateToolkitData(
            task_id=task_id,
            agent_name=self.agent_name,
            toolkit_name=toolkit_name,
            method_name=func_name,
            message=json.dumps(args, ensure_ascii=False)[:500],
        ))

        try:
            # Execute tool based on its type
            if hasattr(tool, "func") and hasattr(tool.func, "async_call"):
                if hasattr(tool, "is_async") and not tool.is_async:
                    result = tool(**args)
                    if asyncio.iscoroutine(result):
                        result = await result
                else:
                    result = await tool.func.async_call(**args)
            elif hasattr(tool, "async_call") and callable(tool.async_call):
                if hasattr(tool, "is_async") and not tool.is_async:
                    result = tool(**args)
                    if asyncio.iscoroutine(result):
                        result = await result
                else:
                    result = await tool.async_call(**args)
            elif hasattr(tool, "func") and asyncio.iscoroutinefunction(tool.func):
                result = await tool.func(**args)
            elif asyncio.iscoroutinefunction(tool):
                result = await tool(**args)
            else:
                result = tool(**args)
                if asyncio.iscoroutine(result):
                    result = await result

        except Exception as e:
            error_msg = f"Error executing async tool '{func_name}': {e!s}"
            result = {"error": error_msg}
            logger.error(f"[ListenChatAgent] Async tool execution failed: {e}", exc_info=True)

        # Prepare result message
        if isinstance(result, str):
            result_msg = result[:500]
        else:
            result_str = repr(result)
            result_msg = result_str[:500]

        # Emit deactivation event
        await self._emit_event(DeactivateToolkitData(
            task_id=task_id,
            agent_name=self.agent_name,
            toolkit_name=toolkit_name,
            method_name=func_name,
            message=result_msg,
        ))

        return self._record_tool_calling(
            func_name,
            args,
            result,
            tool_call_id,
            extra_content=tool_call_request.extra_content,
        )

    def clone(self, with_memory: bool = False) -> ChatAgent:
        """Clone the agent with all Memory state preserved."""
        system_message = None if with_memory else self._original_system_message
        cloned_tools, toolkits_to_register = self._clone_tools()

        new_agent = ListenChatAgent(
            task_state=self._task_state,
            agent_name=self.agent_name,
            system_message=system_message,
            model=self.model_backend.models,
            memory=None,
            message_window_size=getattr(self.memory, "window_size", None),
            token_limit=getattr(self.memory.get_context_creator(), "token_limit", None),
            output_language=self._output_language,
            tools=cloned_tools,
            toolkits_to_register_agent=toolkits_to_register,
            external_tools=[schema for schema in self._external_tool_schemas.values()],
            response_terminators=self.response_terminators,
            scheduling_strategy=self.model_backend.scheduling_strategy.__name__,
            max_iteration=self.max_iteration,
            stop_event=self.stop_event,
            tool_execution_timeout=self.tool_execution_timeout,
            mask_tool_output=self.mask_tool_output,
            pause_event=self.pause_event,
            prune_tool_calls_from_memory=self.prune_tool_calls_from_memory,
            step_timeout=self.step_timeout,
        )

        new_agent.process_task_id = self.process_task_id

        # Preserve workflow guide and memory level
        new_agent._workflow_guide_content = self._workflow_guide_content
        new_agent._memory_level = self._memory_level

        # Preserve NoteTakingToolkit reference
        new_agent._note_toolkit = self._note_toolkit

        # Preserve workflow hints state
        new_agent._workflow_hints = self._workflow_hints.copy()
        new_agent._current_hint_index = self._current_hint_index

        # Preserve IntentSequence cache
        new_agent._cached_page_operations = self._cached_page_operations
        new_agent._cached_page_operations_url = self._cached_page_operations_url
        new_agent._cached_page_operations_ids = self._cached_page_operations_ids
        new_agent._current_page_url = self._current_page_url

        # Preserve callbacks (P2)
        new_agent._progress_callback = self._progress_callback
        new_agent._human_ask_callback = self._human_ask_callback
        new_agent._human_message_callback = self._human_message_callback

        # Preserve step counting (P3)
        new_agent._step_count = self._step_count
        new_agent._max_steps = self._max_steps

        if with_memory:
            context_records = self.memory.retrieve()
            for context_record in context_records:
                new_agent.memory.write_record(context_record.memory_record)

        return new_agent
