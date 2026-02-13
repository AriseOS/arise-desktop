"""
AMI Agent - Lightweight agent with Anthropic-native tool-calling loop.

Replaces CAMEL's ChatAgent + ListenChatAgent with a simpler implementation:
- Direct Anthropic API calls (no OpenAI format conversion)
- Context truncation instead of summarization (preserves conversation structure)
- SSE event emission for agent/toolkit activate/deactivate
- Workflow guide injection, page operations cache
- Cancellation, pause/resume, step counting
"""

import asyncio
import inspect
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from src.common.llm import AnthropicProvider
from src.common.llm.base_provider import (
    ToolCallResponse,
    ToolUseBlock,
    TextBlock,
)

from .ami_tool import AMITool
from ..events import (
    ActivateAgentData,
    AgentReportData,
    DeactivateAgentData,
    ActivateToolkitData,
    DeactivateToolkitData,
    NoticeData,
    AgentThinkingData,
)

logger = logging.getLogger(__name__)

# Tool name prefix to Toolkit name mapping
_TOOL_PREFIX_TO_TOOLKIT = {
    "browser": "Browser Toolkit",
    "shell": "Terminal Toolkit",
    "terminal": "Terminal Toolkit",
    "search": "Search Toolkit",
    "human": "Human Toolkit",
    "memory": "Memory Toolkit",
    "task": "Task Planning Toolkit",
    "calendar": "Calendar Toolkit",
    "get": "Task Planning Toolkit",
    "complete": "Task Planning Toolkit",
    "report": "Task Planning Toolkit",
    "replan": "Replan Toolkit",
    "write": "File Toolkit",
    "read": "File Toolkit",
    "file": "File Toolkit",
    "list": "File Toolkit",
}


def _infer_toolkit_name(tool_name: str) -> str:
    """Infer toolkit name from tool function name."""
    prefix = tool_name.split("_")[0].lower() if "_" in tool_name else tool_name.lower()
    if prefix in _TOOL_PREFIX_TO_TOOLKIT:
        return _TOOL_PREFIX_TO_TOOLKIT[prefix]
    return f"{prefix.title()} Toolkit"


def _is_collection_type(annotation) -> bool:
    """Check if a type annotation is a list or dict type (including generics)."""
    import typing
    origin = getattr(annotation, "__origin__", None)
    if origin in (list, dict):
        return True
    if annotation in (list, dict):
        return True
    # Handle Union types (e.g., Optional[List[str]])
    if origin is typing.Union:
        args = getattr(annotation, "__args__", ())
        return any(_is_collection_type(a) for a in args if a is not type(None))
    return False


# Character-based token estimate
def _estimate_tokens(text: str) -> int:
    """Estimate token count from text (rough: ~4 chars per token)."""
    return max(len(text) // 4, 1)


def _estimate_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    """Estimate total tokens across all messages."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += _estimate_tokens(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if "text" in block:
                        total += _estimate_tokens(block["text"])
                    elif "content" in block:
                        total += _estimate_tokens(str(block["content"]))
        total += 10  # overhead per message
    return total


@dataclass
class AMIAgentResponse:
    """Response from AMIAgent.astep()."""
    text: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    stop_reason: str = "end_turn"


class AMIAgent:
    """
    Lightweight agent with Anthropic-native tool-calling loop.

    Replaces CAMEL's ChatAgent + ListenChatAgent (~1,712 lines) with ~500 lines.

    Key differences from CAMEL:
    - Messages stored in Anthropic format (no OpenAI intermediate)
    - Context truncation instead of summarization (preserves structure)
    - Direct AnthropicProvider calls (no AMIModelBackend adapter)
    - SSE events for frontend agent timeline

    Usage:
        provider = AnthropicProvider(api_key=key, model_name=model, base_url=url)
        agent = AMIAgent(task_state, "BrowserAgent", provider=provider,
                         system_prompt="...", tools=tools)
        response = await agent.astep("Search for AI trends")
    """

    def __init__(
        self,
        task_state: Any,
        agent_name: str,
        provider: AnthropicProvider,
        system_prompt: str = "",
        tools: Optional[List[AMITool]] = None,
        context_token_limit: int = 180_000,
        max_iterations: int = 50,
        max_steps: int = 1000,
        max_tokens: int = 16384,
        tool_result_max_chars: int = 100_000,
    ):
        """Initialize AMIAgent.

        Args:
            task_state: TaskState for SSE event emission.
            agent_name: Display name for SSE events.
            provider: AnthropicProvider instance for LLM calls.
            system_prompt: System prompt for the agent.
            tools: List of AMITool instances available to the agent.
            context_token_limit: Token limit for context truncation.
            max_iterations: Max tool-calling iterations per astep() call.
            max_steps: Max total astep() calls before raising error.
            max_tokens: Max tokens per LLM response.
            tool_result_max_chars: Max characters per tool result before truncation.
        """
        self._task_state = task_state
        self.agent_name = agent_name
        self._provider = provider
        self._system_prompt = system_prompt
        self._max_iterations = max_iterations
        self._max_steps = max_steps
        self._max_tokens = max_tokens
        self._context_token_limit = context_token_limit
        self._tool_result_max_chars = tool_result_max_chars

        # Process ID for SSE events
        self.process_task_id: str = ""
        self.agent_id: str = agent_name

        # Tool registry: name -> AMITool
        self._tools: Dict[str, AMITool] = {}
        if tools:
            for tool in tools:
                name = tool.get_function_name()
                self._tools[name] = tool

        # Conversation history (Anthropic native format)
        self._messages: List[Dict[str, Any]] = []

        # Workflow guide for Memory-based navigation
        self._workflow_guide_content: Optional[str] = None
        self._memory_level: str = "L3"

        # Workflow hints for step-by-step tracking
        self._workflow_hints: List[Dict[str, Any]] = []
        self._current_hint_index: int = 0

        # Page operations cache (L3 Memory)
        self._cached_page_operations: Optional[str] = None
        self._cached_page_operations_url: Optional[str] = None
        self._cached_page_operations_ids: Optional[List[str]] = None
        self._current_page_url: Optional[str] = None

        # Progress callback
        self._progress_callback: Optional[Callable] = None

        # Step counting
        self._step_count: int = 0

        # Per-agent steering queue: messages injected via InjectMessageTool
        # bypass the shared TaskState queue and go directly to this agent.
        self._injected_steering_queue: asyncio.Queue = asyncio.Queue()

        # When True, _check_steering_queue() only checks per-agent queue,
        # never falls back to shared _user_message_queue. Must be set when
        # agent runs under Persistent Orchestrator — the Orchestrator owns
        # the shared queue and routes messages via inject_steering_message().
        self._disable_shared_queue: bool = False

        # Early-stop flag: set by ReplanToolkit.replan_split_and_handoff
        # to force astep() to stop after the current tool-call round.
        self._should_stop_after_tool: bool = False

        # Model-visible snapshot export
        self._export_model_visible_snapshots: bool = False
        self._snapshot_export_subdir: str = "model_visible_snapshots"
        self._snapshot_export_counter: int = 0

        logger.info(f"[AMIAgent] Created: {agent_name}, tools={list(self._tools.keys())}")

    # =========================================================================
    # Tool Management
    # =========================================================================

    def add_tool(self, tool: AMITool) -> None:
        """Register a tool for LLM use."""
        name = tool.get_function_name()
        self._tools[name] = tool

    def get_tool(self, name: str) -> Optional[AMITool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def remove_tool(self, name: str) -> None:
        """Remove a tool by name."""
        self._tools.pop(name, None)

    def _get_anthropic_tools(self) -> List[Dict[str, Any]]:
        """Get all tools in Anthropic schema format."""
        return [tool.to_anthropic_schema() for tool in self._tools.values()]

    # =========================================================================
    # Workflow Guide & Memory
    # =========================================================================

    def set_workflow_guide(self, content: str, memory_level: str = "L2") -> None:
        """Set workflow guide content for injection into messages."""
        self._workflow_guide_content = content
        self._memory_level = memory_level
        logger.info(
            f"[AMIAgent] {self.agent_name} workflow guide set "
            f"(level={memory_level}, {len(content)} chars)"
        )

    def set_memory_context(
        self,
        memory_result: Any = None,
        memory_level: str = "L3",
        workflow_guide: Optional[str] = None,
    ) -> None:
        """Set memory context (called by AMITaskExecutor)."""
        if workflow_guide:
            self.set_workflow_guide(workflow_guide, memory_level)

    # =========================================================================
    # Workflow Hints
    # =========================================================================

    def set_workflow_hints(self, hints: List[Dict[str, Any]]) -> None:
        """Set workflow hints for step-by-step execution tracking."""
        self._workflow_hints = hints
        self._current_hint_index = 0
        if hints:
            self._register_workflow_hint_tool()

    def workflow_hint_done(self, summary: str = "") -> str:
        """Mark current workflow hint as complete and advance to next."""
        if not self._workflow_hints:
            return "No workflow hints available."
        if self._current_hint_index >= len(self._workflow_hints):
            return "All workflow hints already completed."

        completed = self._workflow_hints[self._current_hint_index]
        logger.info(
            f"[AMIAgent] {self.agent_name} hint {self._current_hint_index + 1} "
            f"completed: {completed.get('description', 'N/A')[:50]}"
        )
        self._current_hint_index += 1

        if self._current_hint_index >= len(self._workflow_hints):
            return (
                f"All {len(self._workflow_hints)} workflow hints completed. "
                "Continue with any remaining task requirements."
            )
        next_hint = self._workflow_hints[self._current_hint_index]
        return (
            f"Hint completed. Next step:\n\n"
            f"**Step {self._current_hint_index + 1}/{len(self._workflow_hints)}**\n"
            f"Action: {next_hint.get('description', 'N/A')}\n"
            f"Target: {next_hint.get('target_description', 'N/A')}"
        )

    def _register_workflow_hint_tool(self) -> None:
        """Register workflow_hint_done as an LLM-callable tool."""
        if "workflow_hint_done" in self._tools:
            return
        hint_tool = AMITool(self.workflow_hint_done)
        self._tools["workflow_hint_done"] = hint_tool
        logger.info(f"[AMIAgent] {self.agent_name} registered workflow_hint_done tool")

    def _get_current_hint_context(self) -> str:
        """Get context string for the current workflow hint."""
        if not self._workflow_hints or self._current_hint_index >= len(self._workflow_hints):
            return ""
        hint = self._workflow_hints[self._current_hint_index]
        total = len(self._workflow_hints)
        current = self._current_hint_index + 1
        return (
            f"\n## Current Memory Hint (Step {current}/{total})\n"
            f"**Action:** {hint.get('description', hint.get('type', 'Unknown'))}\n"
            f"**Target:** {hint.get('target_description', 'Next page')}\n\n"
            f"Remember: This is a GUIDE. Adapt to your actual task goal.\n"
            f"Call `workflow_hint_done` when this navigation step is complete.\n"
        )

    @property
    def workflow_hints_progress(self) -> Dict[str, Any]:
        """Get workflow hints progress information."""
        return {
            "current_step": self._current_hint_index + 1,
            "total_steps": len(self._workflow_hints),
            "completed": self._current_hint_index >= len(self._workflow_hints),
            "has_hints": len(self._workflow_hints) > 0,
        }

    # =========================================================================
    # Page Operations Cache (L3 Memory)
    # =========================================================================

    def set_current_url(self, url: str) -> None:
        """Set current browser URL. Clears stale cache if URL changed."""
        old_url = self._current_page_url
        self._current_page_url = url
        if old_url and url != old_url:
            self._clear_page_operations_cache()

    def cache_page_operations(
        self,
        url: str,
        operations: str,
        intent_sequence_ids: Optional[List[str]] = None,
    ) -> None:
        """Cache page operations query result."""
        previous_url = self._cached_page_operations_url
        self._cached_page_operations = operations
        self._cached_page_operations_url = url
        if intent_sequence_ids is not None:
            self._cached_page_operations_ids = intent_sequence_ids
        elif previous_url != url:
            self._cached_page_operations_ids = None

    def _clear_page_operations_cache(self) -> None:
        """Clear the page operations cache."""
        self._cached_page_operations = None
        self._cached_page_operations_url = None
        self._cached_page_operations_ids = None

    def _get_cached_page_operations(self) -> Optional[str]:
        """Get cached page operations if current URL matches."""
        if (
            self._cached_page_operations
            and self._cached_page_operations_url
            and self._cached_page_operations_url == self._current_page_url
        ):
            return self._cached_page_operations
        return None

    # =========================================================================
    # Progress & Control
    # =========================================================================

    def set_progress_callback(self, callback: Callable) -> None:
        """Set callback for progress updates."""
        self._progress_callback = callback

    def set_max_steps(self, max_steps: int) -> None:
        """Set maximum execution steps."""
        self._max_steps = max_steps

    def reset_step_count(self) -> None:
        """Reset the step counter."""
        self._step_count = 0

    @property
    def step_count(self) -> int:
        """Get current step count."""
        return self._step_count

    def is_cancelled(self) -> bool:
        """Check if the task has been cancelled."""
        if self._task_state and hasattr(self._task_state, '_cancel_event'):
            return self._task_state._cancel_event.is_set()
        return False

    def enable_model_visible_snapshot_export(
        self,
        enabled: bool = True,
        export_subdir: str = "model_visible_snapshots",
    ) -> None:
        """Enable exporting model-visible page snapshots to workspace."""
        self._export_model_visible_snapshots = enabled
        if export_subdir:
            self._snapshot_export_subdir = export_subdir

    def set_task_state(self, task_state: Any) -> None:
        """Update the task state for event emission."""
        self._task_state = task_state

    def inject_steering_message(self, message: str) -> None:
        """Inject a steering message directly to this agent (non-blocking).

        Used by InjectMessageTool to route messages to a specific child agent
        without going through the shared TaskState queue.
        """
        self._injected_steering_queue.put_nowait(message)

    def _check_steering_queue(self) -> Optional[str]:
        """Non-blocking check for steering messages.

        Checks per-agent injected queue first.
        If _disable_shared_queue is False, also falls back to shared TaskState queue.
        When running under Persistent Orchestrator, _disable_shared_queue is True
        so the Orchestrator exclusively owns the shared queue.
        """
        # Check per-agent injected queue first (from InjectMessageTool)
        try:
            return self._injected_steering_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

        # Skip shared queue if disabled (Persistent Orchestrator mode)
        if self._disable_shared_queue:
            return None

        # Fallback to shared TaskState queue (legacy non-orchestrator mode)
        if not self._task_state:
            return None
        queue = getattr(self._task_state, "_user_message_queue", None)
        if queue is None:
            return None
        try:
            return queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    # =========================================================================
    # Core Execution Loop
    # =========================================================================

    async def astep(self, input_message: str) -> AMIAgentResponse:
        """Execute a full tool-calling loop until LLM stops calling tools.

        This is the main entry point. It:
        1. Enriches message with workflow guide + page operations
        2. Appends user message to conversation history
        3. Loops: call LLM → if tool_use, execute tools, append results → repeat
        4. Returns when LLM produces end_turn or max iterations reached

        Args:
            input_message: The user/task message to process.

        Returns:
            AMIAgentResponse with final text, all tool calls made, and stop reason.
        """
        # Check cancellation
        if self.is_cancelled():
            raise asyncio.CancelledError("Task was cancelled")

        # Step counting
        self._step_count += 1
        if self._step_count > self._max_steps:
            raise RuntimeError(f"Maximum steps exceeded: {self._max_steps}")

        task_id = self._task_state.task_id if self._task_state else None

        # Enrich message with workflow guide and page operations
        enriched = self._enrich_message(input_message)

        # Append user message to conversation
        self._messages.append({"role": "user", "content": enriched})

        # Emit activation event
        await self._emit_event(ActivateAgentData(
            task_id=task_id,
            agent_name=self.agent_name,
            agent_id=self.agent_id,
            process_task_id=self.process_task_id,
            message=enriched[:500],
        ))

        # Notify progress
        await self._notify_progress("step_started", {
            "step": self._step_count,
            "max_steps": self._max_steps,
            "agent_name": self.agent_name,
        })

        all_tool_calls: List[Dict[str, Any]] = []
        final_text = ""
        stop_reason = "end_turn"
        error_info = None

        try:
            iteration = 0
            while iteration < self._max_iterations:
                # Check cancellation
                if self.is_cancelled():
                    raise asyncio.CancelledError("Task was cancelled")

                # Truncate old context if needed
                self._maybe_truncate_old_results()

                # Call LLM
                tools_schema = self._get_anthropic_tools()
                response = await self._provider.generate_with_tools(
                    system_prompt=self._system_prompt,
                    messages=self._messages,
                    tools=tools_schema if tools_schema else [],
                    max_tokens=self._max_tokens,
                )

                # Append assistant response to conversation
                self._messages.append({
                    "role": "assistant",
                    "content": self._response_to_content_blocks(response),
                })

                # Extract text
                response_text = response.get_text()
                if response_text:
                    final_text = response_text

                # Emit thinking event
                if response_text:
                    await self._emit_event(AgentThinkingData(
                        task_id=task_id,
                        agent_name=self.agent_name,
                        thinking=response_text[:500],
                        step=self._step_count,
                    ))
                    # Also emit as agent_report so it shows in chat UI
                    if response.has_tool_use():
                        await self._emit_event(AgentReportData(
                            task_id=task_id,
                            message=response_text[:300],
                            report_type="thinking",
                        ))

                # Check if LLM wants to use tools
                if not response.has_tool_use():
                    stop_reason = response.stop_reason
                    break

                # Execute tools and collect results
                tool_results = []
                tool_uses = response.get_tool_uses()
                steering_message = None

                for i, tool_use in enumerate(tool_uses):
                    all_tool_calls.append({
                        "id": tool_use.id,
                        "name": tool_use.name,
                        "input": tool_use.input,
                    })

                    result_content = await self._execute_tool(
                        tool_use.name, tool_use.input, tool_use.id, task_id
                    )

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result_content,
                    })

                    # Check for steering message after each tool call
                    steering_message = self._check_steering_queue()
                    if steering_message:
                        # Skip remaining tool calls with "Skipped" results
                        for skipped in tool_uses[i + 1:]:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": skipped.id,
                                "content": "Skipped: user sent a new message.",
                                "is_error": True,
                            })
                        logger.info(
                            f"[AMIAgent] {self.agent_name} steering: "
                            f"skipped {len(tool_uses) - i - 1} remaining tools"
                        )
                        break

                # Append tool results (and steering message if any) as user message
                # Anthropic requires user/assistant alternation, so steering text
                # goes into the same user message as tool results.
                if steering_message:
                    tool_results.append({
                        "type": "text",
                        "text": (
                            f"[USER MESSAGE] The user has sent a new message "
                            f"while you were working. Read it carefully and adjust "
                            f"your plan accordingly:\n\n{steering_message}"
                        ),
                    })
                    logger.info(
                        f"[AMIAgent] {self.agent_name} injected steering message: "
                        f"{steering_message[:100]}..."
                    )
                self._messages.append({"role": "user", "content": tool_results})

                # Check early-stop flag (set by replan_split_and_handoff)
                if self._should_stop_after_tool:
                    stop_reason = "handoff"
                    logger.info(
                        f"[AMIAgent] {self.agent_name} stopping after handoff"
                    )
                    break

                iteration += 1

                # Approaching iteration limit: force a final LLM call without
                # tools so the model summarises what it has instead of
                # requesting yet another tool call.
                if iteration >= self._max_iterations:
                    logger.warning(
                        f"[AMIAgent] {self.agent_name} approaching max iterations "
                        f"({iteration}/{self._max_iterations}), forcing final output"
                    )
                    # Inject a nudge so the model knows it must conclude now
                    self._messages.append({
                        "role": "user",
                        "content": (
                            "You have used all available tool calls. "
                            "Based on everything you have gathered so far, "
                            "produce your final output NOW. "
                            "Do NOT request any more tools."
                        ),
                    })
                    final_response = await self._provider.generate_with_tools(
                        system_prompt=self._system_prompt,
                        messages=self._messages,
                        tools=[],  # no tools — force text output
                        max_tokens=self._max_tokens,
                    )
                    self._messages.append({
                        "role": "assistant",
                        "content": self._response_to_content_blocks(final_response),
                    })
                    forced_text = final_response.get_text()
                    if forced_text:
                        final_text = forced_text
                    stop_reason = "max_iterations"
                    break

            if iteration >= self._max_iterations:
                logger.warning(
                    f"[AMIAgent] {self.agent_name} hit max iterations ({self._max_iterations})"
                )
                stop_reason = "max_iterations"

        except Exception as e:
            error_info = e
            logger.error(f"[AMIAgent] {self.agent_name} error: {e}", exc_info=True)

        # Emit deactivation
        await self._emit_event(DeactivateAgentData(
            task_id=task_id,
            agent_name=self.agent_name,
            agent_id=self.agent_id,
            process_task_id=self.process_task_id,
            message=final_text[:500] if final_text else "",
            tokens_used=0,
        ))

        # Notify progress
        await self._notify_progress("step_completed", {
            "step": self._step_count,
            "max_steps": self._max_steps,
            "agent_name": self.agent_name,
            "success": error_info is None,
        })

        if error_info is not None:
            raise error_info

        return AMIAgentResponse(
            text=final_text,
            tool_calls=all_tool_calls,
            stop_reason=stop_reason,
        )

    # =========================================================================
    # Tool Execution
    # =========================================================================

    @staticmethod
    def _sanitize_tool_name(name: str) -> str:
        """Sanitize tool name from LLM response.

        Some API proxies leak raw text formatting into tool names
        (e.g., '<tool_call>write_excel' instead of 'write_excel').
        Strip known prefixes to handle this gracefully.
        """
        # Strip XML-like tags that proxies may inject (e.g., <tool_call>)
        cleaned = re.sub(r"<[^>]+>", "", name).strip()
        return cleaned or name

    async def _execute_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_call_id: str,
        task_id: Optional[str],
    ) -> str:
        """Execute a single tool and return result string.

        Handles:
        - Tool name sanitization (proxy compatibility)
        - Sync/async dispatch
        - SSE toolkit activate/deactivate events
        - @listen_toolkit decorator bypass
        - Result truncation
        - Error handling
        """
        # Sanitize tool name (API proxies may inject tags like <tool_call>)
        tool_name = self._sanitize_tool_name(tool_name)

        tool = self._tools.get(tool_name)
        if tool is None:
            error_msg = f"Unknown tool: {tool_name}"
            logger.error(f"[AMIAgent] {error_msg}")
            return error_msg

        # Infer toolkit name for SSE events
        toolkit_display_name = self._resolve_toolkit_name(tool)

        # Check for @listen_toolkit decorator
        has_listen_decorator = hasattr(tool.func, "__wrapped__")

        # Emit activation (skip if decorator handles it)
        if not has_listen_decorator:
            await self._emit_event(ActivateToolkitData(
                task_id=task_id,
                agent_name=self.agent_name,
                toolkit_name=toolkit_display_name,
                method_name=tool_name,
                message=json.dumps(tool_input, ensure_ascii=False)[:500],
            ))

        result_str = ""
        try:
            # Filter out unexpected kwargs to handle LLM hallucinated parameters
            sig = inspect.signature(tool.func)
            valid_params = set(sig.parameters.keys()) - {"self", "cls"}
            has_var_keyword = any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in sig.parameters.values()
            )
            if not has_var_keyword:
                filtered_input = {
                    k: v for k, v in tool_input.items() if k in valid_params
                }
                dropped = set(tool_input.keys()) - set(filtered_input.keys())
                if dropped:
                    logger.warning(
                        f"[AMIAgent] Dropped unexpected params for {tool_name}: {dropped}"
                    )
                tool_input = filtered_input

            # Auto-deserialize JSON strings for list/dict parameters.
            # Some API proxies serialize array/object params as JSON strings
            # (e.g., data='[["a","b"]]' instead of data=[["a","b"]]).
            for param_name, param in sig.parameters.items():
                if param_name in tool_input and isinstance(tool_input[param_name], str):
                    annotation = param.annotation
                    if annotation != inspect.Parameter.empty and _is_collection_type(annotation):
                        try:
                            parsed = json.loads(tool_input[param_name])
                            if isinstance(parsed, (list, dict)):
                                tool_input[param_name] = parsed
                                logger.debug(
                                    f"[AMIAgent] Auto-deserialized JSON string param '{param_name}' for {tool_name}"
                                )
                        except (json.JSONDecodeError, TypeError):
                            pass  # Not valid JSON, leave as string

            # Execute tool
            if tool.is_async:
                result = await tool.func(**tool_input)
            else:
                result = await asyncio.to_thread(tool.func, **tool_input)

            # Convert result to string
            if isinstance(result, str):
                result_str = result
            elif isinstance(result, dict):
                result_str = json.dumps(result, ensure_ascii=False, indent=2)
            elif isinstance(result, (list, tuple)):
                result_str = json.dumps(result, ensure_ascii=False, indent=2)
            else:
                result_str = str(result)

        except Exception as e:
            result_str = f"Tool execution failed: {e}"
            logger.error(
                f"[AMIAgent] Tool {tool_name} execution failed: {e}", exc_info=True
            )

        # Truncate if too long
        was_truncated = False
        if len(result_str) > self._tool_result_max_chars:
            was_truncated = True
            result_str = result_str[:self._tool_result_max_chars] + "\n...[truncated]"

        # Export model-visible snapshot if enabled
        if self._export_model_visible_snapshots and "Page Snapshot" in result_str:
            self._write_model_visible_snapshot(tool_name, result_str, was_truncated)

        # Emit deactivation (skip if decorator handles it)
        if not has_listen_decorator:
            await self._emit_event(DeactivateToolkitData(
                task_id=task_id,
                agent_name=self.agent_name,
                toolkit_name=toolkit_display_name,
                method_name=tool_name,
                message=result_str[:500],
            ))

        return result_str

    def _resolve_toolkit_name(self, tool: AMITool) -> str:
        """Resolve toolkit display name from tool metadata."""
        # Check tool-level attribute
        if hasattr(tool, "_toolkit_name"):
            return tool._toolkit_name

        # Check wrapped function
        func = tool.func
        if hasattr(func, "_toolkit_name"):
            return func._toolkit_name
        if hasattr(func, "__func__") and hasattr(func.__func__, "_toolkit_name"):
            return func.__func__._toolkit_name

        # Check toolkit instance
        if hasattr(func, "__self__"):
            toolkit_instance = func.__self__
            if hasattr(toolkit_instance, "toolkit_name") and callable(toolkit_instance.toolkit_name):
                return toolkit_instance.toolkit_name()

        # Fallback: infer from function name
        return _infer_toolkit_name(tool.get_function_name())

    # =========================================================================
    # Message Enrichment
    # =========================================================================

    def _enrich_message(self, message: str) -> str:
        """Enrich input message with workflow guide and page operations."""
        parts = [message]

        # Inject workflow guide
        if self._workflow_guide_content:
            # Skip if already present (e.g., from AMITaskExecutor._build_prompt)
            if "## Workflow Guide" not in message and "## Memory Guidance" not in message and "## Reference: Historical Workflow" not in message:
                parts.append(self._build_workflow_guide_section())

        # Inject current hint context
        hint_ctx = self._get_current_hint_context()
        if hint_ctx:
            parts.append(hint_ctx)

        # Inject cached page operations
        cached_ops = self._get_cached_page_operations()
        if cached_ops:
            task_id = self._task_state.task_id if self._task_state else "unknown"
            logger.info(
                f"[Task {task_id}] [Memory] Injected page operations "
                f"(url={self._current_page_url[:120] if self._current_page_url else '?'}..., "
                f"length={len(cached_ops)})"
            )
            parts.append(
                f"\n## Available Page Operations (from Memory)\n"
                f"The following operations were recorded from previous user sessions on this page type.\n\n"
                f"{cached_ops}\n\n"
                f"**How to use these signals:**\n"
                f"- **Numbered operations**: These are known interaction patterns for this page. Use them as guidance.\n"
                f"- **[INFINITE SCROLL]**: The page uses lazy loading — scroll down repeatedly to load all content before extracting data.\n"
                f"- **[IMPORTANT DATA]**: The user previously highlighted/selected this text, indicating it is valuable. "
                f"Prioritize extracting similar data fields.\n"
                f"- **[EXTRACTED DATA]**: The user previously copied this content. Treat as confirmed high-value data to collect.\n"
                f"- **Navigation options**: Known links/buttons that lead to other pages."
            )

        return "\n".join(parts) if len(parts) > 1 else message

    def _build_workflow_guide_section(self) -> str:
        """Build the workflow guide section based on memory level."""
        if self._memory_level == "L1":
            header = (
                "## Memory Guidance [L1 - Complete Path]\n"
                "**Confidence**: High - This is a previously successful complete workflow.\n"
                "**Instructions**: Follow the steps STRICTLY in order."
            )
        elif self._memory_level == "L2":
            header = (
                "## Memory Guidance [L2 - Partial Match]\n"
                "**Confidence**: Medium - This is a partial navigation path from similar tasks.\n"
                "**Instructions**: Use as reference, adapt as needed."
            )
        else:
            header = (
                "## Memory Guidance [L3 - No Direct Match]\n"
                "**Confidence**: Low - No complete workflow found.\n"
                "**Instructions**: Use your own judgment."
            )
        return f"\n{header}\n\n{self._workflow_guide_content}"

    # =========================================================================
    # Context Management (Truncation, NOT Summarization)
    # =========================================================================

    def _maybe_truncate_old_results(self) -> None:
        """Truncate old tool_result blocks when context grows too large.

        Strategy:
        - Estimate token count across all messages
        - If over threshold, find oldest tool_result blocks
        - Replace their content with "[Truncated - old result]"
        - Preserve conversation STRUCTURE (LLM sees it called a tool)
        - Never truncate: last 4 message pairs (8 messages)

        This preserves the conversation flow while reducing tokens.
        The LLM still knows WHAT it did, just not the full output.
        """
        estimated = _estimate_messages_tokens(self._messages)
        if estimated < self._context_token_limit:
            return

        logger.info(
            f"[AMIAgent] {self.agent_name} context too large "
            f"({estimated} tokens > {self._context_token_limit}), truncating old results"
        )

        # Protect last 8 messages from truncation
        protected_count = 8
        truncatable = self._messages[:-protected_count] if len(self._messages) > protected_count else []

        truncated_count = 0
        for msg in truncatable:
            content = msg.get("content")
            if not isinstance(content, list):
                continue

            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_result":
                    continue

                current_content = block.get("content", "")
                if isinstance(current_content, str) and len(current_content) > 200:
                    block["content"] = "[Truncated - old tool result]"
                    truncated_count += 1

        if truncated_count > 0:
            new_estimated = _estimate_messages_tokens(self._messages)
            logger.info(
                f"[AMIAgent] Truncated {truncated_count} old tool results "
                f"({estimated} -> {new_estimated} tokens)"
            )

    # =========================================================================
    # Response Conversion
    # =========================================================================

    @staticmethod
    def _response_to_content_blocks(response: ToolCallResponse) -> List[Dict[str, Any]]:
        """Convert ToolCallResponse to Anthropic message content blocks."""
        blocks = []
        for item in response.content:
            if isinstance(item, TextBlock):
                blocks.append({"type": "text", "text": item.text})
            elif isinstance(item, ToolUseBlock):
                blocks.append({
                    "type": "tool_use",
                    "id": item.id,
                    "name": item.name,
                    "input": item.input,
                })
            else:
                # Unknown block type, try to serialize
                if hasattr(item, "text"):
                    blocks.append({"type": "text", "text": item.text})
                elif hasattr(item, "name"):
                    blocks.append({
                        "type": "tool_use",
                        "id": getattr(item, "id", ""),
                        "name": item.name,
                        "input": getattr(item, "input", {}),
                    })
        # Ensure at least one block
        if not blocks:
            blocks.append({"type": "text", "text": ""})
        return blocks

    # =========================================================================
    # Model-Visible Snapshot Export
    # =========================================================================

    def _write_model_visible_snapshot(
        self,
        func_name: str,
        content: str,
        was_truncated: bool,
    ) -> None:
        """Export model-visible page snapshot to workspace."""
        if not self._export_model_visible_snapshots:
            return

        dir_manager = (
            getattr(self._task_state, "dir_manager", None) if self._task_state else None
        )
        if not dir_manager:
            return

        try:
            self._snapshot_export_counter += 1
            safe_tool = re.sub(r"[^A-Za-z0-9_-]+", "_", func_name) or "tool"
            filename = (
                f"{self._snapshot_export_subdir}/"
                f"snapshot_{self._snapshot_export_counter:04d}_{safe_tool}.md"
            )
            header = [
                "# Model-visible page snapshot",
                f"tool: {func_name}",
                f"truncated: {str(was_truncated).lower()}",
                f"timestamp_utc: {datetime.now(timezone.utc).isoformat()}",
                "",
            ]
            dir_manager.write_file(filename, "\n".join(header) + content)
        except Exception as e:
            logger.warning(f"[AMIAgent] Failed to export snapshot: {e}")

    # =========================================================================
    # SSE Event Emission
    # =========================================================================

    async def _emit_event(self, event: Any) -> None:
        """Emit an SSE event via task state."""
        if self._task_state and hasattr(self._task_state, 'put_event'):
            try:
                await self._task_state.put_event(event)
            except Exception as e:
                logger.debug(f"[AMIAgent] Failed to emit event: {e}")

    async def _notify_progress(self, event: str, data: Dict[str, Any]) -> None:
        """Notify progress callback if set."""
        if self._progress_callback:
            try:
                if asyncio.iscoroutinefunction(self._progress_callback):
                    await self._progress_callback(event, data)
                else:
                    self._progress_callback(event, data)
            except Exception as e:
                logger.error(f"[AMIAgent] Progress callback failed: {e}")

    # =========================================================================
    # Conversation Management
    # =========================================================================

    def reset(self) -> None:
        """Reset conversation history."""
        self._messages.clear()
        self._step_count = 0
        self._should_stop_after_tool = False

    def clone(self) -> "AMIAgent":
        """Create a lightweight clone sharing provider and tools but with fresh state.

        Used by Persistent Orchestrator to give each parallel executor its own
        agent instance, avoiding conversation history and state corruption when
        multiple executors use the same agent type simultaneously.

        The clone shares:
        - Provider (LLM client — stateless, thread-safe)
        - Tools (bound methods on toolkit instances — stateless callables)
        - System prompt, config (max_iterations, max_tokens, etc.)

        The clone gets fresh:
        - Conversation history (_messages)
        - Step count, steering queue, control flags
        """
        new_agent = AMIAgent(
            task_state=self._task_state,
            agent_name=self.agent_name,
            provider=self._provider,
            system_prompt=self._system_prompt,
            tools=list(self._tools.values()),
            context_token_limit=self._context_token_limit,
            max_iterations=self._max_iterations,
            max_steps=self._max_steps,
            max_tokens=self._max_tokens,
            tool_result_max_chars=self._tool_result_max_chars,
        )
        new_agent._disable_shared_queue = self._disable_shared_queue
        return new_agent

    def get_messages(self) -> List[Dict[str, Any]]:
        """Get current conversation messages."""
        return self._messages.copy()
