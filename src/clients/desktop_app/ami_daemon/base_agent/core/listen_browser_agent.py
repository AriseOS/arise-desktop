"""
ListenBrowserAgent - Browser Agent with SSE events and Memory support.

This agent provides:
- SSE events for real-time UI updates
- Memory context integration for workflow guidance
- Page operation caching for efficient Memory usage
- Full Toolkit support (Browser, NoteTaking, Search, Terminal, Human, Memory)

Note: This agent uses single-step execution via astep() following Eigent's pattern.
Task decomposition and orchestration are handled by AMITaskPlanner/AMITaskExecutor.
"""

import asyncio
import logging
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, TYPE_CHECKING

from camel.models import BaseModelBackend

from .listen_chat_agent import ListenChatAgent
from ..events import NoticeData

if TYPE_CHECKING:
    from ..tools.eigent_browser.browser_session import HybridBrowserSession
    from ..tools.toolkits import (
        BrowserToolkit,
        NoteTakingToolkit,
        SearchToolkit,
        TerminalToolkit,
        HumanToolkit,
        MemoryToolkit,
        QueryResult,
    )

logger = logging.getLogger(__name__)


# =============================================================================
# System Prompt - Import from agent_factories for consistency
# =============================================================================

# Note: The actual system prompt is defined in agent_factories.py (BROWSER_AGENT_SYSTEM_PROMPT)
# and passed during agent creation. This local prompt is a fallback for standalone usage.
LISTEN_BROWSER_AGENT_SYSTEM_PROMPT = """
<role>
You are a Senior Research Analyst, a key member of a multi-agent team. Your
primary responsibility is to conduct expert-level web research to gather,
analyze, and document information required to solve the user's task. You
operate with precision, efficiency, and a commitment to data quality.
You must use the search/browser tools to get the information you need.
</role>

<operating_environment>
- System: {platform} ({architecture})
- Working Directory: {working_directory}
- Current Date: {current_date}
</operating_environment>

<mandatory_instructions>
- You MUST use the note-taking tools to record your findings. This is a
    critical part of your role. Your notes are the primary source of
    information for your teammates. To avoid information loss, you must not
    summarize your findings. Instead, record all information in detail.
    For every piece of information you gather, you must:
    1.  **Extract ALL relevant details**: Quote all important sentences,
        statistics, or data points. Your goal is to capture the information
        as completely as possible.
    2.  **Cite your source**: Include the exact URL where you found the
        information.
    Your notes should be a detailed and complete record of the information
    you have discovered. High-quality, detailed notes are essential for the
    team's success.

- **CRITICAL URL POLICY**: You are STRICTLY FORBIDDEN from inventing,
    guessing, or constructing URLs yourself. You MUST only use URLs from
    trusted sources:
    1. URLs returned by search tools
    2. URLs found on webpages you have visited through browser tools
    3. URLs provided by the user in their request
    Fabricating or guessing URLs is considered a critical error and must
    never be done under any circumstances.

- You MUST NOT answer from your own knowledge. All information
    MUST be sourced from the web using the available tools. If you don't know
    something, find it out using your tools.

- When you complete your task, your final response must be a comprehensive
    summary of your findings, presented in a clear, detailed, and
    easy-to-read format.
</mandatory_instructions>

<workflow_guide_usage>
If a workflow_guide is provided:
1. It shows a PROVEN navigation path
2. States = page TYPES, not fixed URLs
3. Actions = how to navigate between page types
4. Adapt to current context - URLs may differ
</workflow_guide_usage>

<language_policy>
**CRITICAL**: You MUST respond in the same language as the user's original request.
- If the user writes in Chinese, ALL your outputs must be in Chinese (notes, summaries, reports).
- If the user writes in English, respond in English.
- This applies to: notes you write, summaries, and any text you generate.
</language_policy>
"""


def _build_system_prompt(working_directory: str) -> str:
    """Build the system prompt with environment info."""
    return LISTEN_BROWSER_AGENT_SYSTEM_PROMPT.format(
        platform=platform.system(),
        architecture=platform.machine(),
        working_directory=working_directory,
        current_date=datetime.now().strftime("%Y-%m-%d"),
    )


# =============================================================================
# ListenBrowserAgent
# =============================================================================

class ListenBrowserAgent(ListenChatAgent):
    """
    Browser Agent with SSE events and Memory support.

    This agent:
    - Executes browser-based tasks using astep() (single-step execution)
    - Uses Memory context for workflow guidance
    - Caches page operations for efficient Memory usage
    - Emits SSE events for real-time UI updates

    Note: Task decomposition and orchestration are handled externally by
    AMITaskPlanner/AMITaskExecutor. This agent focuses on executing atomic
    browser operations.
    """

    def __init__(
        self,
        task_state: Any,
        agent_name: str,
        # Browser related
        browser_session: "HybridBrowserSession",
        # Toolkits
        browser_toolkit: "BrowserToolkit",
        note_toolkit: "NoteTakingToolkit",
        search_toolkit: Optional["SearchToolkit"] = None,
        terminal_toolkit: Optional["TerminalToolkit"] = None,
        human_toolkit: Optional["HumanToolkit"] = None,
        memory_toolkit: Optional["MemoryToolkit"] = None,
        # Working directory
        working_directory: Optional[str] = None,
        # LLM config
        model: Optional[BaseModelBackend] = None,
        # Tools for LLM (passed to parent class)
        tools: Optional[List[Any]] = None,
        **kwargs,
    ) -> None:
        """
        Initialize ListenBrowserAgent.

        Args:
            task_state: TaskState for SSE event emission.
            agent_name: Name of this agent instance.
            browser_session: HybridBrowserSession for browser operations.
            browser_toolkit: BrowserToolkit instance.
            note_toolkit: NoteTakingToolkit instance.
            search_toolkit: Optional SearchToolkit.
            terminal_toolkit: Optional TerminalToolkit.
            human_toolkit: Optional HumanToolkit.
            memory_toolkit: Optional MemoryToolkit for page operations.
            working_directory: Working directory for file operations.
            model: LLM model backend.
            tools: Tools list for LLM awareness (passed to parent).
        """
        # Build system prompt
        wd = working_directory or str(Path.home())
        system_message = _build_system_prompt(wd)

        # Initialize parent class with tools
        super().__init__(
            task_state=task_state,
            agent_name=agent_name,
            system_message=system_message,
            model=model,
            tools=tools,  # Pass tools to parent for LLM awareness
            **kwargs,
        )

        # Browser session
        self._browser_session = browser_session

        # Toolkits
        self._browser_toolkit = browser_toolkit
        self._note_toolkit = note_toolkit
        self._search_toolkit = search_toolkit
        self._terminal_toolkit = terminal_toolkit
        self._human_toolkit = human_toolkit
        self._memory_toolkit = memory_toolkit

        # Set note toolkit reference for workflow guide saving
        self.set_note_toolkit(note_toolkit)

        # Working directory
        self._working_directory = wd

        # User's original request (for context)
        self._user_request: str = ""

        # Memory context (set via set_memory_context)
        self._memory_result: Optional["QueryResult"] = None
        # Note: _workflow_guide_content and _memory_level are inherited from ListenChatAgent

        # Page operations query optimization (from upstream)
        self._last_url_missing_log_ts: float = 0.0
        self._page_ops_inflight: dict[str, asyncio.Task] = {}
        self._page_ops_checked_urls: set[str] = set()

        # Register all tools
        self._register_all_tools()

        logger.info(
            f"[ListenBrowserAgent] Initialized: {agent_name}, "
            f"working_dir={wd[:50]}..."
        )

    def _register_all_tools(self) -> None:
        """Register all toolkit tools."""
        # Browser Toolkit
        for tool in self._browser_toolkit.get_tools():
            self._internal_tools[tool.get_function_name()] = tool

        # Note Taking Toolkit
        for tool in self._note_toolkit.get_tools():
            self._internal_tools[tool.get_function_name()] = tool

        # Search Toolkit (optional)
        if self._search_toolkit:
            for tool in self._search_toolkit.get_tools():
                self._internal_tools[tool.get_function_name()] = tool

        # Terminal Toolkit (optional)
        if self._terminal_toolkit:
            for tool in self._terminal_toolkit.get_tools():
                self._internal_tools[tool.get_function_name()] = tool

        # Human Toolkit (optional)
        if self._human_toolkit:
            for tool in self._human_toolkit.get_tools():
                self._internal_tools[tool.get_function_name()] = tool

        # Memory Toolkit - query_page_operations (optional)
        if self._memory_toolkit:
            for tool in self._memory_toolkit.get_tools():
                self._internal_tools[tool.get_function_name()] = tool

        logger.info(
            f"[ListenBrowserAgent] Registered {len(self._internal_tools)} tools"
        )

    # =========================================================================
    # Memory Context Management
    # =========================================================================

    def set_memory_context(
        self,
        memory_result: "QueryResult",
        memory_level: str,
        workflow_guide: Optional[str] = None,
    ) -> None:
        """
        Set Memory context for workflow guidance.

        Args:
            memory_result: QueryResult from MemoryToolkit.query_task().
            memory_level: L1/L2/L3 memory confidence level.
            workflow_guide: Pre-formatted workflow guide text.
        """
        self._memory_result = memory_result
        self._memory_level = memory_level

        if workflow_guide:
            self._workflow_guide_content = workflow_guide

            # Save to notes for persistence
            if self._note_toolkit:
                try:
                    self._note_toolkit.create_note(
                        note_name="workflow_guide",
                        content=workflow_guide,
                        overwrite=True,
                    )
                except Exception as e:
                    logger.warning(f"Failed to save workflow_guide note: {e}")

        has_phrase = (
            memory_result.cognitive_phrase is not None
            if memory_result else False
        )
        logger.info(
            f"[ListenBrowserAgent] Memory context set: level={memory_level}, "
            f"has_cognitive_phrase={has_phrase}"
        )

    def set_user_request(self, user_request: str) -> None:
        """
        Set the user's original request for context.

        Args:
            user_request: The user's original request in their own words.
        """
        self._user_request = user_request
        logger.info(
            f"[ListenBrowserAgent] User request set: {user_request[:50]}..."
        )

    def set_current_url(self, url: str) -> None:
        """Override to trigger page-operations query on URL change."""
        super().set_current_url(url)
        if not url:
            return
        self._start_page_operations_query(url, source="url_change")

    def _is_queryable_url(self, url: str) -> bool:
        if not url:
            return False
        return url.startswith("http://") or url.startswith("https://")

    def _start_page_operations_query(self, url: str, source: str) -> None:
        """Start a background page-operations query if needed."""
        if not self._memory_toolkit:
            return
        if not self._is_queryable_url(url):
            return
        if url in self._page_ops_checked_urls:
            return
        if url in self._page_ops_inflight:
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug(
                f"[ListenBrowserAgent] No running loop; skip page operations query for {url[:80]}..."
            )
            return

        task_id = self._task_state.task_id if self._task_state else "unknown"
        logger.debug(
            f"[Task {task_id}] [Memory] Page operations query scheduled "
            f"(source={source}, url={url[:120]}...)"
        )
        self._page_ops_inflight[url] = loop.create_task(
            self._query_page_operations(url, source=source)
        )

    async def _query_page_operations(self, url: str, source: str) -> None:
        """Query Memory for page operations and cache results."""
        task_id = self._task_state.task_id if self._task_state else "unknown"
        try:
            ops = await self._memory_toolkit.query_page_operations(url)
            if ops:
                # MemoryToolkit will cache via agent reference; keep a local copy too.
                self.cache_page_operations(url, ops)
                logger.info(
                    f"[Task {task_id}] [Memory] Page operations fetched "
                    f"(source={source}, length={len(ops)})"
                )
            else:
                logger.info(
                    f"[Task {task_id}] [Memory] Page operations empty (source={source})"
                )
            # Mark as checked even if empty to avoid repeated queries
            self._page_ops_checked_urls.add(url)
        except Exception as e:
            logger.warning(
                f"[Task {task_id}] [Memory] Page operations query failed "
                f"(source={source}): {e}"
            )
        finally:
            self._page_ops_inflight.pop(url, None)

    async def _ensure_page_operations(self, url: str, source: str) -> str:
        """Ensure page operations have been queried for this URL."""
        cached = self.get_cached_page_operations(url)
        if cached:
            return cached
        if url in self._page_ops_checked_urls:
            return ""

        # Start query if not already running
        self._start_page_operations_query(url, source=source)

        # Await in-flight query for this URL if present
        task = self._page_ops_inflight.get(url)
        if task:
            try:
                await task
            except Exception:
                # Query errors are logged in _query_page_operations
                pass

        return self.get_cached_page_operations(url) or ""

    # =========================================================================
    # Browser Utilities
    # =========================================================================

    async def _get_current_url(self) -> Optional[str]:
        """
        Get the current browser URL.

        Returns the cached _current_page_url which is updated by BrowserToolkit.
        """
        return self._current_page_url

    # =========================================================================
    # Clone
    # =========================================================================

    def clone(self, with_memory: bool = False) -> "ListenBrowserAgent":
        """Clone the agent with all state preserved."""
        # Use parent's clone mechanism for base state
        base_clone = super().clone(with_memory=with_memory)

        # Create new instance with browser-specific attributes
        new_agent = ListenBrowserAgent.__new__(ListenBrowserAgent)
        new_agent.__dict__.update(base_clone.__dict__)

        # Copy browser-specific state
        new_agent._browser_session = self._browser_session
        new_agent._browser_toolkit = self._browser_toolkit
        new_agent._note_toolkit = self._note_toolkit
        new_agent._search_toolkit = self._search_toolkit
        new_agent._terminal_toolkit = self._terminal_toolkit
        new_agent._human_toolkit = self._human_toolkit
        new_agent._memory_toolkit = self._memory_toolkit
        new_agent._working_directory = self._working_directory
        new_agent._memory_result = self._memory_result

        return new_agent
