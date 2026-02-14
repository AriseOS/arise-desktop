"""
AMI Browser Agent - Browser-specific agent with Memory page operations support.

Extends AMIAgent with:
- Async page operations queries on URL change
- Memory context integration (QueryResult handling)
- Background query deduplication
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .ami_agent import AMIAgent

if TYPE_CHECKING:
    from ..tools.toolkits import MemoryToolkit, QueryResult

logger = logging.getLogger(__name__)


class AMIBrowserAgent(AMIAgent):
    """
    Browser agent with Memory page operations support.

    Extends AMIAgent to:
    - Trigger background page operations queries on URL change
    - Cache and inject page operations into LLM context
    - Deduplicate queries for already-checked URLs
    """

    def __init__(self, *args, **kwargs):
        # Extract browser-specific kwargs before passing to parent
        self._memory_toolkit: Optional["MemoryToolkit"] = kwargs.pop("memory_toolkit", None)

        super().__init__(*args, **kwargs)

        # Memory context
        self._memory_result: Optional["QueryResult"] = None

        # Page operations query dedup
        self._page_ops_inflight: Dict[str, asyncio.Task] = {}
        self._page_ops_checked_urls: set = set()

    # =========================================================================
    # Memory Context
    # =========================================================================

    def set_memory_context(
        self,
        memory_result: Any = None,
        memory_level: str = "L3",
        workflow_guide: Optional[str] = None,
    ) -> None:
        """Set Memory context for workflow guidance.

        Args:
            memory_result: QueryResult from MemoryToolkit.query_task().
            memory_level: L1/L2/L3 memory confidence level.
            workflow_guide: Pre-formatted workflow guide text.
        """
        self._memory_result = memory_result
        self._memory_level = memory_level

        if workflow_guide:
            self.set_workflow_guide(workflow_guide, memory_level)

        has_phrase = (
            memory_result.cognitive_phrase is not None
            if memory_result else False
        )
        logger.info(
            f"[AMIBrowserAgent] Memory context set: level={memory_level}, "
            f"has_cognitive_phrase={has_phrase}"
        )

    def set_user_request(self, user_request: str) -> None:
        """Set the user's original request for context."""
        logger.info(f"[AMIBrowserAgent] User request set: {user_request[:50]}...")

    # =========================================================================
    # Reset (clear page ops cache for online learning)
    # =========================================================================

    def reset(self) -> None:
        """Reset conversation history and page operations cache.

        Clearing page ops state ensures the next subtask re-queries Memory,
        picking up operations saved by the previous subtask (online learning).
        """
        super().reset()
        self._page_ops_checked_urls.clear()
        self._page_ops_inflight.clear()
        self._cached_page_operations = None
        self._cached_page_operations_url = None
        self._cached_page_operations_ids = None

    def clone(self, independent_session: bool = False) -> "AMIBrowserAgent":
        """Create a lightweight clone sharing provider, tools, and memory toolkit.

        Overrides AMIAgent.clone() to preserve browser-agent-specific setup:
        - memory_toolkit (shared, stateless query interface)

        Args:
            independent_session: If True, the clone gets a new BrowserToolkit
                with its own session_id, so it connects to a different Electron
                pool page. Required for parallel subtask execution.
        """
        if independent_session:
            tools = self._clone_tools_with_new_browser_session()
        else:
            tools = list(self._tools.values())

        new_agent = AMIBrowserAgent(
            task_state=self._task_state,
            agent_name=self.agent_name,
            provider=self._provider,
            system_prompt=self._system_prompt,
            tools=tools,
            context_token_limit=self._context_token_limit,
            max_iterations=self._max_iterations,
            max_steps=self._max_steps,
            max_tokens=self._max_tokens,
            tool_result_max_chars=self._tool_result_max_chars,
            memory_toolkit=self._memory_toolkit,
        )
        new_agent._disable_shared_queue = self._disable_shared_queue

        # Wire BrowserToolkit -> agent for URL change notifications
        if independent_session:
            for tool in new_agent._tools.values():
                bound = getattr(tool.func, '__self__', None)
                if bound and hasattr(bound, 'set_agent') and hasattr(bound, '_session_id'):
                    bound.set_agent(new_agent)
                    break

        return new_agent

    def _clone_tools_with_new_browser_session(self) -> list:
        """Replace browser tools with tools from a cloned BrowserToolkit.

        Finds the BrowserToolkit instance among current tools, creates a
        clone_for_new_session(), and replaces all browser tool entries with
        tools from the new toolkit. Non-browser tools are kept as-is.
        """
        from ..tools.toolkits.browser_toolkit import BrowserToolkit

        # Find the original BrowserToolkit instance
        original_toolkit = None
        browser_tool_names = set()
        for name, tool in self._tools.items():
            bound = getattr(tool.func, '__self__', None)
            if isinstance(bound, BrowserToolkit):
                if original_toolkit is None:
                    original_toolkit = bound
                browser_tool_names.add(name)

        if original_toolkit is None:
            return list(self._tools.values())

        # Clone the toolkit with a new session
        new_toolkit = original_toolkit.clone_for_new_session()

        # Build new tools list: non-browser tools + new browser tools
        new_tools = [
            tool for name, tool in self._tools.items()
            if name not in browser_tool_names
        ]
        new_tools.extend(new_toolkit.get_tools())

        return new_tools

    # =========================================================================
    # Page Operations (URL-triggered async queries)
    # =========================================================================

    def set_current_url(self, url: str) -> None:
        """Override to trigger page-operations query on URL change."""
        super().set_current_url(url)
        if url:
            self._start_page_operations_query(url, source="url_change")

    def _is_queryable_url(self, url: str) -> bool:
        if not url:
            return False
        return url.startswith("http://") or url.startswith("https://")

    def _start_page_operations_query(self, url: str, source: str) -> None:
        """Start a background page-operations query if not already queried."""
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
            return

        task_id = self._task_state.task_id if self._task_state else "unknown"
        logger.debug(
            f"[Task {task_id}] [Memory] Page operations query scheduled "
            f"(source={source}, url={url[:120]}...)"
        )
        task = loop.create_task(self._query_page_operations(url, source=source))
        self._page_ops_inflight[url] = task

    async def _query_page_operations(self, url: str, source: str) -> None:
        """Query Memory for page operations and cache results."""
        task_id = self._task_state.task_id if self._task_state else "unknown"
        try:
            ops = await self._memory_toolkit.query_page_operations(url)
            if ops:
                self.cache_page_operations(url, ops)
                logger.info(
                    f"[Task {task_id}] [Memory] Page operations fetched "
                    f"(source={source}, length={len(ops)})"
                )
            else:
                logger.info(
                    f"[Task {task_id}] [Memory] Page operations empty (source={source})"
                )
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
        cached = self._get_cached_page_operations()
        if cached:
            return cached
        if url in self._page_ops_checked_urls:
            return ""

        self._start_page_operations_query(url, source=source)

        task = self._page_ops_inflight.get(url)
        if task:
            try:
                await task
            except Exception:
                pass

        return self._get_cached_page_operations() or ""
