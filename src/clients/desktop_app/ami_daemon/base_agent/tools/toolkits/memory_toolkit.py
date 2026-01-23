"""
MemoryToolkit - Query Ami's Workflow Memory for task guidance.

Ported from CAMEL-AI/Eigent project.
Enables agents to search historical workflows using Ami's Memory API,
providing guidance for task execution based on past experiences.
"""

import logging
from typing import Any, Dict, List, Optional

from .base_toolkit import BaseToolkit, FunctionTool
from ...events import listen_toolkit

logger = logging.getLogger(__name__)

# Try to import httpx for async HTTP requests
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.warning("httpx not available, MemoryToolkit will have limited functionality")


class MemoryToolkit(BaseToolkit):
    """Toolkit for querying workflow memory.

    Enables agents to search historical workflows using Ami's Memory API.
    This helps agents learn from past experiences and execute tasks more efficiently.

    Usage:
        - Call query_similar_workflows() BEFORE starting a task
        - Use the returned paths to guide execution strategy
        - Follow the intent sequences for page-specific operations

    Uses @listen_toolkit for automatic event emission on public methods.
    """

    # Agent name for event tracking
    agent_name: str = "memory_agent"

    def __init__(
        self,
        memory_api_base_url: str,
        ami_api_key: str,
        user_id: str,
        timeout: Optional[float] = 30.0,
    ) -> None:
        """Initialize MemoryToolkit.

        Args:
            memory_api_base_url: Base URL of Ami's cloud backend (e.g., "http://localhost:8000").
            ami_api_key: User's Ami API key for authentication.
            user_id: User ID for memory isolation.
            timeout: HTTP request timeout in seconds.
        """
        super().__init__(timeout=timeout)
        self._memory_api_base_url = memory_api_base_url.rstrip("/")
        self._ami_api_key = ami_api_key
        self._user_id = user_id

        logger.info(
            f"MemoryToolkit initialized (user_id={user_id}, api_base_url={memory_api_base_url})"
        )

    @listen_toolkit(
        inputs=lambda self, task_description, domain=None, **kw: f"Querying memory: {task_description[:50]}{'...' if len(task_description) > 50 else ''}",
        return_msg=lambda r: f"Found {r.count('Path ')} workflow paths" if "Path" in r else r[:100]
    )
    async def query_similar_workflows(
        self,
        task_description: str,
        domain: Optional[str] = None,
        top_k: int = 3,
        min_score: float = 0.5,
    ) -> str:
        """Query memory for similar historical workflows.

        Use this tool BEFORE starting a task to find relevant past workflows
        that can guide your execution strategy. The memory system uses semantic
        search to find workflows that match your task description.

        Args:
            task_description: Natural language description of the task you want to perform.
                Be specific about what you want to accomplish.
                Example: "Search for AI products on Product Hunt and view team information"
            domain: Optional domain filter to narrow results (e.g., "producthunt.com").
                Use this when you know which website the task is on.
            top_k: Number of similar workflows to return (default: 3).
                Increase for more options, decrease for faster response.
            min_score: Minimum similarity score threshold between 0 and 1 (default: 0.5).
                Higher values return more relevant but fewer results.

        Returns:
            Formatted string with similar workflow paths including:
            - Path description and similarity score
            - Step-by-step states (pages) with URLs
            - Intent sequences (what operations to perform on each page)
            - Actions (how to navigate between pages)

            If no similar workflows are found, returns a message indicating
            this is a new type of task.
        """
        if not HTTPX_AVAILABLE:
            return "Memory query unavailable: httpx library not installed."

        logger.info(
            f"Querying similar workflows: task={task_description[:100]}, "
            f"domain={domain}, top_k={top_k}, min_score={min_score}"
        )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self._memory_api_base_url}/api/v1/memory/query",
                    json={
                        "user_id": self._user_id,
                        "query": task_description,
                        "top_k": top_k,
                        "min_score": min_score,
                        "domain": domain,
                    },
                    headers={"X-Ami-API-Key": self._ami_api_key},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                result = response.json()

            if not result.get("success"):
                error_msg = result.get("message", "Unknown error")
                logger.warning(f"Memory query failed: {error_msg}")
                return f"Memory query failed: {error_msg}"

            paths = result.get("paths", [])
            if not paths:
                logger.info("No similar workflows found")
                return (
                    "No similar workflows found in memory. "
                    "This appears to be a new type of task. "
                    "Proceed with your own planning and exploration."
                )

            # Format results for LLM consumption
            output = self._format_paths_for_llm(paths, result.get("decomposed", {}))

            logger.info(f"Memory query successful: {len(paths)} paths found")
            return output

        except httpx.HTTPStatusError as e:
            error_msg = f"Memory API error: HTTP {e.response.status_code}"
            logger.error(f"{error_msg} - {e.response.text[:200]}")
            return f"{error_msg}. Proceeding without memory guidance."
        except httpx.TimeoutException:
            logger.warning("Memory query timed out")
            return "Memory query timed out. Proceeding without memory guidance."
        except Exception as e:
            logger.error(f"Memory query error: {e}")
            return f"Memory query failed: {str(e)}. Proceeding without memory guidance."

    @listen_toolkit(
        inputs=lambda self, task_description, domain=None, **kw: f"Querying memory (sync): {task_description[:50]}{'...' if len(task_description) > 50 else ''}",
        return_msg=lambda r: f"Found {r.count('Path ')} workflow paths" if "Path" in r else r[:100]
    )
    def query_similar_workflows_sync(
        self,
        task_description: str,
        domain: Optional[str] = None,
        top_k: int = 3,
        min_score: float = 0.5,
    ) -> str:
        """Synchronous version of query_similar_workflows.

        Note: This method cannot be called from within an async context.
        Use the async version query_similar_workflows() instead.

        Args:
            task_description: Natural language description of the task.
            domain: Optional domain filter.
            top_k: Number of results to return.
            min_score: Minimum similarity score.

        Returns:
            Formatted string with similar workflow paths.
        """
        import asyncio

        try:
            # Check if we're already in an async context
            asyncio.get_running_loop()
            raise RuntimeError(
                "query_similar_workflows_sync() cannot be called from within an async context. "
                "Use 'await query_similar_workflows()' instead."
            )
        except RuntimeError as e:
            if "no running event loop" in str(e):
                # No running loop, safe to use asyncio.run()
                return asyncio.run(
                    self.query_similar_workflows(task_description, domain, top_k, min_score)
                )
            raise

    def _format_paths_for_llm(self, paths: List[Dict], decomposed: Dict) -> str:
        """Format workflow paths into a readable string for LLM.

        Args:
            paths: List of path objects from memory API.
            decomposed: Decomposed query info (target_query, key_queries).

        Returns:
            Formatted string describing the workflow paths.
        """
        output = f"Found {len(paths)} relevant workflow paths from memory:\n\n"

        # Show query decomposition if available
        if decomposed:
            target_query = decomposed.get("target_query")
            key_queries = decomposed.get("key_queries", [])
            if target_query or key_queries:
                output += "**Query Analysis**:\n"
                if target_query:
                    output += f"  - Target: {target_query}\n"
                if key_queries:
                    output += f"  - Key pages: {', '.join(key_queries)}\n"
                output += "\n"

        for i, path in enumerate(paths, 1):
            score = path.get("score", 0)
            description = path.get("description", "Unknown path")
            start_url = path.get("start_url", "N/A")
            path_length = path.get("path_length", 0)
            steps = path.get("steps", [])

            output += f"### Path {i} (score: {score:.2f})\n"
            output += f"**Description**: {description}\n"
            output += f"**Start URL**: {start_url}\n"
            output += f"**Length**: {path_length} steps\n\n"

            if steps:
                output += "**Steps**:\n"
                for j, step in enumerate(steps, 1):
                    output += self._format_step(j, step)
                output += "\n"

            output += "---\n\n"

        output += (
            "**Recommendation**: Use the above paths as guidance. "
            "Start from the suggested URL and follow the operations on each page. "
            "Adapt as needed based on the current page state.\n"
        )

        return output

    def _format_step(self, step_num: int, step: Dict) -> str:
        """Format a single step for display.

        Args:
            step_num: Step number (1-indexed).
            step: Step data containing state, action, intent_sequence.

        Returns:
            Formatted string for this step.
        """
        output = ""
        state = step.get("state", {})
        action = step.get("action")
        intent_seq = step.get("intent_sequence")

        # State info
        state_desc = (
            state.get("description")
            or state.get("page_title")
            or state.get("page_url", "Unknown page")
        )
        page_url = state.get("page_url", "N/A")

        output += f"  {step_num}. **Page**: {state_desc}\n"
        output += f"     URL: {page_url}\n"

        # Intent sequence (what to do on this page)
        if intent_seq:
            intents = intent_seq.get("intents", [])
            if intents:
                output += f"     **Operations on this page**:\n"
                for intent in intents[:5]:  # Limit to first 5 intents
                    intent_type = intent.get("type", "unknown")
                    intent_text = intent.get("text") or intent.get("value", "")
                    if intent_text:
                        output += f"       - {intent_type}: {intent_text}\n"
                    else:
                        output += f"       - {intent_type}\n"

                if len(intents) > 5:
                    output += f"       - ... and {len(intents) - 5} more operations\n"

        # Action to next state
        if action:
            action_desc = action.get("description") or action.get("type", "navigate")
            output += f"     → **Next**: {action_desc}\n"

        output += "\n"
        return output

    def is_available(self) -> bool:
        """Check if memory functionality is available.

        Returns:
            True if httpx is installed and API credentials are configured.
        """
        return HTTPX_AVAILABLE and bool(self._memory_api_base_url and self._ami_api_key)

    def get_tools(self) -> List[FunctionTool]:
        """Return a list of FunctionTool objects for this toolkit.

        Returns:
            List of FunctionTool objects.
        """
        return [
            FunctionTool(self.query_similar_workflows),
        ]

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "Memory Toolkit"
