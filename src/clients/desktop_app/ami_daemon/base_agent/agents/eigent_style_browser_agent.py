"""
EigentStyleBrowserAgent - Full Tool-calling architecture ported from CAMEL-AI/Eigent.

This agent implements the complete Eigent Tool-calling architecture:
1. Tool-calling mode (using Anthropic tool_use API)
2. Complete Toolkit system (NoteTaking, Search, Terminal, Human, Browser)
3. Eigent-style System Prompt
4. Memory Path reference capability (preserved from existing system)

This agent:
- Uses LLM function calling instead of fixed JSON output format
- Supports parallel tool execution
- Has automatic memory management
- Includes note-taking for research documentation
"""

import asyncio
import json
import logging
import platform
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
from urllib.parse import urlsplit, urlunsplit

import aiohttp

from .base_agent import BaseStepAgent, AgentMetadata, InputSchema, FieldSchema
from ..core.schemas import AgentContext, AgentInput, AgentOutput
from ..tools.eigent_browser.browser_session import HybridBrowserSession
from ..tools.toolkits import (
    FunctionTool,
    NoteTakingToolkit,
    SearchToolkit,
    TerminalToolkit,
    HumanToolkit,
    BrowserToolkit,
    MemoryToolkit,
    TaskPlanningToolkit,
)
from ..core.task_orchestrator import TaskOrchestrator, OrchestratorConfig, SubTaskState
from ..workspace import get_working_directory, get_current_manager
from ..events import set_process_task

# Import from common/llm module
from src.common.llm import (
    AnthropicProvider,
    ToolCallResponse,
    ToolUseBlock,
    TextBlock,
)

logger = logging.getLogger(__name__)


def _get_browser_data_dir(explicit_dir: Optional[str] = None) -> Optional[str]:
    """Get browser data directory for the agent.

    Args:
        explicit_dir: Explicit directory path (from input_data).
            If provided, uses this directory.
            Otherwise, tries current task manager, then falls back to global.
    """
    try:
        if explicit_dir:
            path = Path(explicit_dir)
        else:
            # Try to get from current task manager
            manager = get_current_manager()
            if manager:
                path = manager.browser_data_dir
            else:
                # Fallback to global directory
                path = Path.home() / ".ami" / "browser_data_quicktask"

        path.mkdir(parents=True, exist_ok=True)
        return str(path)
    except Exception as e:
        logger.warning(f"Failed to create browser_data dir: {e}")
        return None


def _get_notes_dir(explicit_dir: Optional[str] = None) -> str:
    """Get notes directory for the agent.

    Args:
        explicit_dir: Explicit directory path (from input_data).
    """
    if explicit_dir:
        path = Path(explicit_dir)
    else:
        manager = get_current_manager()
        if manager:
            path = manager.notes_dir
        else:
            path = Path.home() / ".ami" / "notes"

    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _get_working_dir(explicit_dir: Optional[str] = None) -> str:
    """Get working directory for terminal commands.

    Args:
        explicit_dir: Explicit directory path (from input_data).
    """
    if explicit_dir:
        return explicit_dir
    return get_working_directory()


# Log-sanitization helpers for memory content
_MAX_GUIDE_LINES = 30
_MAX_GUIDE_CHARS = 4096
_MAX_LINE_LEN = 200
_MAX_LOG_STEPS = 8


def _truncate_text(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    if max_len <= 15:
        return value[:max_len]
    return value[: max_len - 14] + "...(truncated)"


def _sanitize_text(value: Optional[str], max_len: int = _MAX_LINE_LEN) -> str:
    if not value:
        return ""
    text = str(value)
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "<redacted_email>", text)
    text = re.sub(r"\+?\d[\d\-\s\(\)]{7,}\d", "<redacted_phone>", text)
    text = re.sub(r"\b[a-zA-Z0-9_\-]{20,}\b", "<redacted_token>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _truncate_text(text, max_len)


def _sanitize_url(url: Optional[str]) -> str:
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        netloc = parts.netloc.split("@")[-1]
        cleaned = urlunsplit((parts.scheme, netloc, parts.path, "", ""))
        return _sanitize_text(cleaned, max_len=_MAX_LINE_LEN)
    except Exception:
        return _sanitize_text(url, max_len=_MAX_LINE_LEN)


def _sanitize_guide(content: str) -> str:
    lines = content.splitlines()
    out_lines: List[str] = []
    total_chars = 0
    for line in lines[:_MAX_GUIDE_LINES]:
        sanitized = _sanitize_text(line, max_len=_MAX_LINE_LEN)
        if total_chars + len(sanitized) + 1 > _MAX_GUIDE_CHARS:
            remaining = _MAX_GUIDE_CHARS - total_chars
            if remaining > 0:
                sanitized = _truncate_text(sanitized, remaining)
                out_lines.append(sanitized)
            break
        out_lines.append(sanitized)
        total_chars += len(sanitized) + 1
    if len(lines) > _MAX_GUIDE_LINES or total_chars >= _MAX_GUIDE_CHARS:
        out_lines.append("[workflow_guide truncated]")
    return "\n".join(out_lines)


# Eigent-style System Prompt ported from eigent/backend/app/utils/agent.py
EIGENT_STYLE_SYSTEM_PROMPT = """
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
## Task Planning (CRITICAL - TRACK YOUR PROGRESS)
You will receive a pre-decomposed task plan. Use the task planning tools to track progress:

1. **Check current plan**: Call `get_current_plan()` to see the task breakdown and current progress

2. **After completing a subtask**: Call `complete_subtask(subtask_id, result)` to mark it done
   - subtask_id: The ID of the completed subtask (e.g., "1.1", "1.2")
   - result: A brief summary of what was accomplished

3. **If a subtask fails**: Call `report_subtask_failure(subtask_id, error)` to report the failure
   - The system may trigger automatic replanning

4. **If plan needs adjustment**: Call `replan_task(reason, new_subtasks, cancelled_subtask_ids)` to modify the plan
   - reason: Why the replan is needed
   - new_subtasks: List of new subtasks to add
   - cancelled_subtask_ids: Optional list of subtask IDs to cancel

Example workflow:
```
get_current_plan()
# Review the plan, then start working on current subtask
# ... execute the subtask ...
complete_subtask("1.1", "Found 5 competitor sites via Google search")
# ... work on next subtask ...
complete_subtask("1.2", "Extracted pricing from all 5 sites")
# ... and so on
```

## Note-Taking (CRITICAL FOR PROGRESS TRACKING)
- You MUST use the note-taking tools to record your findings. This is a
  critical part of your role. Your notes are the primary source of
  information for your teammates. To avoid information loss, you must not
  summarize your findings. Instead, record all information in detail.
  For every piece of information you gather, you must:
  1. Extract ALL relevant details: Quote all important sentences,
     statistics, or data points. Your goal is to capture the information
     as completely as possible.
  2. Cite your source: Include the exact URL where you found the
     information.
  Your notes should be a detailed and complete record of the information
  you have discovered.

## Processing Multiple Items (USE REPLAN!)
- When you discover multiple items to process (e.g., 10 products on a page):
  1. **IMMEDIATELY call `replan_task`** to create a subtask for EACH item
  2. The system will track progress for you - no need to remember manually
  3. Complete each subtask with `complete_subtask` when done

  Example: You're on a leaderboard with 10 products to analyze:
  ```
  # When you see 10 products, call replan_task:
  replan_task(
      reason="Found 10 products to analyze individually",
      new_subtasks=[
          {{"id": "2.1", "content": "Analyze Product A: visit detail page, check team"}},
          {{"id": "2.2", "content": "Analyze Product B: visit detail page, check team"}},
          ... # one subtask per product
          {{"id": "2.10", "content": "Analyze Product J: visit detail page, check team"}},
      ],
      cancelled_subtask_ids=["1.2"]  # Cancel the vague "analyze all products" task
  )
  ```

  **DO NOT** try to process all items in a single subtask - you will lose track!

## URL Policy
- CRITICAL URL POLICY: You are STRICTLY FORBIDDEN from inventing,
  guessing, or constructing URLs yourself. You MUST only use URLs from
  trusted sources:
  1. URLs returned by search tools (search_google)
  2. URLs found on webpages you have visited through browser tools
  3. URLs provided by the user in their request
  Fabricating or guessing URLs is considered a critical error.

## Other Requirements
- You MUST NOT answer from your own knowledge. All information
  MUST be sourced from the web using the available tools.

- When you complete your task, your final response must be a comprehensive
  summary of your findings, presented in a clear, detailed format.

- When encountering verification challenges (like login, CAPTCHAs or
  robot checks), you MUST request help using the ask_human tool.

- You MUST diligently complete all tasks in the task plan. Do not skip steps
  or take shortcuts because a task seems tedious or repetitive. If the task
  requires processing 50 items, you MUST process all 50 items.

- If workflow hints are provided, you MUST follow the workflow hints logic
  to actually navigate and retrieve the data. The hints show the correct
  path - use them as your guide, but you must actually perform the actions
  and extract real data from the pages you visit.
</mandatory_instructions>

<capabilities>
Your capabilities include:
- **Task Planning Tools** (TRACK YOUR PROGRESS):
  * `get_current_plan`: View current task breakdown and progress
  * `complete_subtask`: Mark a subtask as done with result summary
  * `report_subtask_failure`: Report when a subtask fails
  * `replan_task`: Adjust plan when new information emerges
- Search and get information from the web using the search tools.
- Use the rich browser related toolset to investigate websites.
- Use the terminal tools to perform local operations. You can leverage
  powerful CLI tools like `grep` for searching within files, `curl` and
  `wget` for downloading content, and `jq` for parsing JSON data from APIs.
- Use the note-taking tools to record your findings.
- Use the human toolkit to ask for help when you are stuck.
- **IMPORTANT**: Use the memory toolkit (`query_similar_workflows`) to search
  for similar historical workflows BEFORE starting a complex task. This can
  provide valuable guidance on:
  * Previously successful navigation paths
  * Page-specific operations and interactions
  * Common patterns for similar tasks
</capabilities>

<workflow_guide>
## Workflow Guide (Navigation Reference)

A **workflow_guide** note may be available that contains a navigation path from previous
successful workflows. This is a REFERENCE, not a script.

### How to Use the Workflow Guide

1. **Check if it exists**: Call `read_note("workflow_guide")` when you need navigation help
2. **Interpret the content**:
   - **States**: Represent page TYPES (not fixed URLs). Example: "产品详情页" means any product detail page
   - **Actions**: Show HOW to navigate between page types
   - **URLs**: Are REFERENCE examples only - actual URLs may differ (e.g., /weekly/2026/3 vs /weekly/2026/4)
3. **Follow the path**: Use the navigation steps to reach your target page type
4. **Adapt to your task**: Once at the target page, focus on YOUR task goals

### When to Read the Workflow Guide

- When you need to navigate to a specific type of page
- When you're unsure how to reach a certain section of a website
- When you want to follow a proven navigation path

### Important Notes

- The workflow_guide is a GUIDE, not exact instructions
- URLs in the guide are examples - adapt to current context
- Focus on reaching the right PAGE TYPE, not matching exact URLs
</workflow_guide>

<batch_processing>
## Efficient Batch Processing

When dealing with multiple items (e.g., a list of products, search results, entries):

### Step 1: Extract All Items with URLs
1. Call `browser_get_page_snapshot(include_links=True)` to get all links on the page
2. Save the full link list to a note with `create_note` — this is your index for later
3. Scroll down and repeat if the page has more items below the fold

### Step 2: Replan with URLs in Subtask Content
When creating subtasks for each item, **always include the URL** in the subtask content:
- GOOD: `"Visit DataFast detail page (https://producthunt.com/products/datafast), extract team info"`
- BAD: `"Visit DataFast detail page, extract team info"`
This way you can navigate directly without going back to the list page.

### Step 3: Process Each Item Efficiently
- Use `browser_visit_page(url)` to go directly to each item — do NOT navigate back to the list page to click
- Extract the information you need from the current page
- If you only need names/text visible on the page, read them from the snapshot — do NOT click into sub-pages unnecessarily
- Save findings to notes with `append_note`, then call `complete_subtask`
</batch_processing>

<web_search_workflow>
Your approach depends on available search tools:

**If Google Search is Available:**
- Initial Search: Start with `search_google` to get a list of relevant URLs
- Browser-Based Exploration: Use the browser tools to investigate the URLs

**If Google Search is NOT Available:**
- **MUST start with direct website search**: Use `browser_visit_page` to go
  directly to popular search engines and informational websites such as:
  * General search: google.com, bing.com, duckduckgo.com
  * Academic: scholar.google.com, pubmed.ncbi.nlm.nih.gov
  * News: news.google.com, bbc.com/news, reuters.com
  * Technical: stackoverflow.com, github.com
  * Reference: wikipedia.org, britannica.com
- **Manual search process**: Type your query into the search boxes on these
  sites using `browser_type` and submit with `browser_enter`
- **Extract URLs from results**: Only use URLs that appear in the search
  results on these websites

**Common Browser Operations (both scenarios):**
- **Navigation and Exploration**: Use `browser_visit_page` to open URLs.
  `browser_visit_page` provides a snapshot of currently visible
  interactive elements, not the full page text. To see more content on
  long pages, Navigate with `browser_click`, `browser_back`, and
  `browser_forward`.
- **Click behavior**: When you click a link, if it opens in a new tab,
  the browser automatically switches to the new tab. Your next snapshot
  will show the new page content. You don't need to manually manage tabs.
- **Interaction**: Use `browser_type` to fill out forms and
  `browser_enter` to submit or confirm search.

- In your response, you should mention the URLs you have visited and processed.

- When encountering verification challenges (like login, CAPTCHAs or
  robot checks), you MUST request help using the human toolkit.
</web_search_workflow>
"""


class EigentStyleBrowserAgent(BaseStepAgent):
    """
    Eigent-style Browser Agent with full Tool-calling architecture.

    This agent uses Anthropic's tool_use API for function calling,
    supporting all 5 Eigent toolkits:
    - NoteTakingToolkit: Create and manage markdown notes
    - SearchToolkit: Web search (Google API or DuckDuckGo fallback)
    - TerminalToolkit: Shell command execution with safety controls
    - HumanToolkit: Human-in-the-loop interaction
    - BrowserToolkit: Browser automation
    """

    INPUT_SCHEMA = InputSchema(
        description="Eigent-style browser agent with Tool-calling architecture",
        fields={
            "task": FieldSchema(
                type="str",
                required=True,
                description="Task description in natural language"
            ),
            "headless": FieldSchema(
                type="bool",
                required=False,
                default=False,
                description="Whether to run browser in headless mode"
            ),
        },
        examples=[
            {
                "task": "Search for the top 5 trending products on Product Hunt today and take notes",
            },
            {
                "task": "Research and compare pricing for iPhone 15 Pro across different retailers",
            }
        ]
    )

    def __init__(self):
        metadata = AgentMetadata(
            name="eigent_style_browser_agent",
            description="Eigent-style Browser Agent with full Tool-calling architecture",
            version="1.0.0",
            tags=["browser", "eigent", "tool-calling", "research", "web"],
        )
        super().__init__(metadata)

        # LLM Provider (from common/llm module)
        self._llm_provider: Optional[AnthropicProvider] = None

        # Browser session
        self._session: Optional[HybridBrowserSession] = None

        # Toolkits (initialized in execute)
        self._note_toolkit: Optional[NoteTakingToolkit] = None
        self._search_toolkit: Optional[SearchToolkit] = None
        self._terminal_toolkit: Optional[TerminalToolkit] = None
        self._human_toolkit: Optional[HumanToolkit] = None
        self._browser_toolkit: Optional[BrowserToolkit] = None
        self._memory_toolkit: Optional[MemoryToolkit] = None

        # Memory API configuration (set via set_memory_config)
        self._memory_api_base_url: Optional[str] = None
        self._ami_api_key: Optional[str] = None
        self._user_id: Optional[str] = None

        # All tools for LLM
        self._tools: List[FunctionTool] = []
        self._tool_map: Dict[str, FunctionTool] = {}

        # Conversation memory
        self._messages: List[Dict[str, Any]] = []

        # Callbacks
        self._progress_callback: Optional[Callable] = None
        self._human_ask_callback: Optional[Callable] = None
        self._human_message_callback: Optional[Callable] = None

        # Task state for event emission (set via set_task_state)
        self._task_state: Optional[Any] = None

        # Execution tracking
        self._step_count: int = 0
        self._max_steps: int = 1000

        # Cancellation support
        self._cancel_event: Optional[asyncio.Event] = None

        # Workflow hints (from Reasoner/Memory)
        self._workflow_hints: List[Dict[str, Any]] = []
        self._current_hint_index: int = 0

        # Workflow guide content (from CognitivePhrase or Path)
        # Stored for injection into each LLM call
        self._workflow_guide_content: Optional[str] = None

    def set_progress_callback(self, callback: Callable):
        """Set callback for progress updates."""
        self._progress_callback = callback

    def set_human_callbacks(
        self,
        ask_callback: Optional[Callable] = None,
        message_callback: Optional[Callable] = None
    ):
        """Set callbacks for human interaction."""
        self._human_ask_callback = ask_callback
        self._human_message_callback = message_callback

    def set_memory_config(
        self,
        memory_api_base_url: str,
        ami_api_key: str,
        user_id: str,
    ):
        """Set Memory API configuration for MemoryToolkit.

        Args:
            memory_api_base_url: Base URL of Ami's cloud backend.
            ami_api_key: User's Ami API key for authentication.
            user_id: User ID for memory isolation.
        """
        self._memory_api_base_url = memory_api_base_url
        self._ami_api_key = ami_api_key
        self._user_id = user_id
        logger.info(f"Memory config set: api_base_url={memory_api_base_url}, user_id={user_id}")

    def set_task_state(self, task_state: Any):
        """Set task state for event emission via toolkit decorators.

        This enables @listen_toolkit decorators to emit events through
        the task's event queue for real-time progress tracking.

        Also extracts the cancel_event from TaskState for cancellation support.

        Args:
            task_state: TaskState instance with put_event() method.
        """
        self._task_state = task_state

        # Extract cancel event from TaskState for cancellation support
        if hasattr(task_state, '_cancel_event'):
            self._cancel_event = task_state._cancel_event
            logger.info("Cancel event linked from TaskState")

        logger.info(f"Task state set for event emission")

    def is_cancelled(self) -> bool:
        """Check if the task has been cancelled.

        Returns:
            True if cancellation was requested.
        """
        if self._cancel_event is not None:
            return self._cancel_event.is_set()
        return False

    async def _notify_progress(self, event: str, data: Dict[str, Any]):
        """Notify progress to callback if set."""
        if self._progress_callback:
            try:
                if asyncio.iscoroutinefunction(self._progress_callback):
                    await self._progress_callback(event, data)
                else:
                    self._progress_callback(event, data)
            except Exception as e:
                logger.error(f"Progress callback failed for {event}: {e}")
                import traceback
                logger.error(traceback.format_exc())
        else:
            logger.warning(f"[_notify_progress] No callback set, skipping event: {event}")

    async def initialize(self, context: AgentContext) -> bool:
        """Initialize the agent with LLM provider from common/llm module."""
        try:
            llm_api_key = None
            llm_base_url = None
            llm_model = None

            # Extract configuration from context.variables (set by quick_task_service)
            if context.variables:
                llm_api_key = context.variables.get("llm_api_key")
                llm_model = context.variables.get("llm_model")
                llm_base_url = context.variables.get("llm_base_url")

            # Fallback: try to extract from agent_instance.provider (legacy path)
            if not llm_api_key and context.agent_instance and hasattr(context.agent_instance, 'provider'):
                provider = context.agent_instance.provider
                if hasattr(provider, 'api_key') and provider.api_key:
                    llm_api_key = provider.api_key
                if hasattr(provider, 'model_name') and provider.model_name:
                    llm_model = provider.model_name
                if hasattr(provider, 'base_url') and provider.base_url:
                    llm_base_url = provider.base_url

            # Create AnthropicProvider from common/llm module
            self._llm_provider = AnthropicProvider(
                api_key=llm_api_key,
                model_name=llm_model,
                base_url=llm_base_url,
            )

            # Initialize the provider (creates the client)
            await self._llm_provider._initialize_client()

            logger.info(f"EigentStyleBrowserAgent initialized with model: {self._llm_provider.model_name}")
            self.is_initialized = True
            return True

        except Exception as e:
            import traceback
            logger.error(f"EigentStyleBrowserAgent initialization failed: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    async def validate_input(self, input_data: Any) -> bool:
        """Validate input data."""
        if isinstance(input_data, (dict, AgentInput)):
            return True
        return False

    async def _workflow_hint_done(self, summary: str = "") -> str:
        """Mark the current workflow hint as complete and advance to the next one.

        Call this when you have successfully completed the navigation or action
        described in the current memory hint. This advances to the next hint
        in the workflow guide.

        Args:
            summary: Optional brief summary of what was accomplished in this step.

        Returns:
            Information about the next hint, or completion message if no more hints.
        """
        if not self._workflow_hints:
            return "No workflow hints active. Continue with your task using your judgment."

        # Log completion of current hint
        if self._current_hint_index < len(self._workflow_hints):
            completed_hint = self._workflow_hints[self._current_hint_index]
            logger.info(f"[Workflow] Hint {self._current_hint_index + 1} completed: {completed_hint.get('description', '')}")
            if summary:
                logger.info(f"[Workflow] Summary: {summary}")

        # Advance to next hint
        self._current_hint_index += 1

        # Check if there are more hints
        if self._current_hint_index >= len(self._workflow_hints):
            return f"""All {len(self._workflow_hints)} workflow hints completed.

You may now:
- Continue with any remaining aspects of the user's task
- Iterate through more items if the task requires "all" of something
- Provide a final summary and complete the task
"""

        # Return info about next hint
        next_hint = self._workflow_hints[self._current_hint_index]
        return f"""Hint {self._current_hint_index} completed. Moving to next hint.

## Next Hint (Step {self._current_hint_index + 1}/{len(self._workflow_hints)})
**Action:** {next_hint.get('description', next_hint.get('type', 'Unknown'))}
**Target:** {next_hint.get('target_description', 'Next page')}

Remember: This is a GUIDE. Adapt to your actual task goal.
"""

    def _initialize_toolkits(
        self,
        task_id: Optional[str] = None,
        working_directory: Optional[str] = None,
        notes_directory: Optional[str] = None,
    ):
        """Initialize all toolkits and collect tools.

        Args:
            task_id: Optional task identifier for directory isolation.
            working_directory: Explicit working directory for terminal commands.
            notes_directory: Explicit notes directory for note-taking.
        """
        self._task_id = task_id

        # Get directories (uses explicit or falls back to task workspace)
        effective_working_dir = _get_working_dir(working_directory)
        effective_notes_dir = _get_notes_dir(notes_directory)

        logger.info(f"Initializing toolkits with working_dir={effective_working_dir}, notes_dir={effective_notes_dir}")

        # Initialize toolkits with workspace isolation
        self._note_toolkit = NoteTakingToolkit(
            task_id=task_id,
            notes_directory=effective_notes_dir,
            use_task_workspace=True,  # Will use current manager if no explicit dir
        )
        self._search_toolkit = SearchToolkit()
        self._terminal_toolkit = TerminalToolkit(
            working_directory=effective_working_dir,
            safe_mode=True,
            use_task_workspace=True,  # Will use current manager if no explicit dir
        )
        self._human_toolkit = HumanToolkit(
            ask_callback=self._human_ask_callback,
            message_callback=self._human_message_callback,
        )
        self._browser_toolkit = BrowserToolkit(
            session=self._session,
            return_snapshot=True,
        )

        # Initialize MemoryToolkit if configured
        if self._memory_api_base_url and self._ami_api_key and self._user_id:
            self._memory_toolkit = MemoryToolkit(
                memory_api_base_url=self._memory_api_base_url,
                ami_api_key=self._ami_api_key,
                user_id=self._user_id,
            )
            logger.info("MemoryToolkit initialized")
        else:
            self._memory_toolkit = None
            logger.info("MemoryToolkit not configured (missing api_base_url, api_key, or user_id)")

        # Initialize TaskOrchestrator for task management (single-agent mode)
        # This handles task decomposition, state tracking, and SSE events
        # Note: Pass _sse_emitter from TaskState, not TaskState itself
        sse_emitter = None
        if self._task_state and hasattr(self._task_state, '_sse_emitter'):
            sse_emitter = self._task_state._sse_emitter
        self._task_orchestrator = TaskOrchestrator(
            task_id=task_id,
            emitter=sse_emitter,
            llm_client=self._llm_provider if hasattr(self, '_llm_provider') else None,
            config=OrchestratorConfig(
                single_agent_mode=True,
                max_retries_per_subtask=3,
            ),
        )
        logger.info(f"TaskOrchestrator initialized for task {task_id}")

        # Initialize TaskPlanningToolkit as interface to TaskOrchestrator
        # This provides LLM-callable tools: complete_subtask, replan_task, etc.
        self._task_planning_toolkit = TaskPlanningToolkit(
            orchestrator=self._task_orchestrator,
            task_id=task_id,
        )
        logger.info("TaskPlanningToolkit initialized with orchestrator")

        # Collect all tools
        self._tools = [
            *self._note_toolkit.get_tools(),
            *self._search_toolkit.get_tools(),
            *self._terminal_toolkit.get_tools(),
            *self._human_toolkit.get_tools(),
            *self._browser_toolkit.get_tools(),
            *self._task_planning_toolkit.get_tools(),  # Task planning tools
        ]

        # Add memory tools if available
        if self._memory_toolkit:
            self._tools.extend(self._memory_toolkit.get_tools())

        # Add workflow hint control tool (will be functional during agent loop)
        workflow_hint_tool = FunctionTool(self._workflow_hint_done)
        self._tools.append(workflow_hint_tool)

        # Build tool map for quick lookup
        self._tool_map = {tool.name: tool for tool in self._tools}

        # Set task state on all toolkits for event emission via @listen_toolkit
        if self._task_state:
            all_toolkits = [
                self._note_toolkit,
                self._search_toolkit,
                self._terminal_toolkit,
                self._human_toolkit,
                self._browser_toolkit,
                self._memory_toolkit,
                self._task_planning_toolkit,  # Include task planning toolkit
            ]
            for toolkit in all_toolkits:
                if toolkit and hasattr(toolkit, 'set_task_state'):
                    toolkit.set_task_state(self._task_state)
            logger.info("Task state propagated to all toolkits for event emission")

        toolkit_count = 7 if self._memory_toolkit else 6  # +1 for task planning
        logger.info(f"Initialized {len(self._tools)} tools from {toolkit_count} toolkits")

    def _build_tools_schema(self) -> List[Dict[str, Any]]:
        """Build Anthropic tools schema."""
        return [tool.to_anthropic_tool() for tool in self._tools]

    def _build_system_prompt(self) -> str:
        """Build the system prompt with environment info."""
        return EIGENT_STYLE_SYSTEM_PROMPT.format(
            platform=platform.system(),
            architecture=platform.machine(),
            working_directory=_get_working_dir(),
            current_date=datetime.now().strftime("%Y-%m-%d"),
        )

    def _estimate_message_size(self, messages: List[Dict[str, Any]]) -> int:
        """Roughly estimate the character count of messages for logging."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        total += len(str(item.get("content", "")))
                        total += len(str(item.get("text", "")))
        return total

    async def _call_llm(self) -> ToolCallResponse:
        """Call LLM with tools using AnthropicProvider."""
        system_prompt = self._build_system_prompt()
        tools_schema = self._build_tools_schema()

        msg_size = self._estimate_message_size(self._messages)
        logger.info(f"[_call_llm] msgs={len(self._messages)}, tools={len(tools_schema)}, size={msg_size:,}")

        response = await self._llm_provider.generate_with_tools(
            system_prompt=system_prompt,
            messages=self._messages,
            tools=tools_schema,
            max_tokens=4096,
        )
        logger.debug("[_call_llm] LLM call completed")

        return response

    def _extract_text_response(self, response: ToolCallResponse) -> str:
        """Extract text content from response."""
        return response.get_text()

    async def _execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Execute a tool and return the result as string.

        Uses set_process_task context manager to track tool execution
        for @listen_toolkit event emission.
        """
        tool = self._tool_map.get(tool_name)
        if not tool:
            return f"Error: Unknown tool '{tool_name}'"

        # Generate process task ID for event tracking
        task_id = getattr(self._task_state, 'task_id', None) if self._task_state else None
        process_task_id = f"{task_id or 'agent'}:{tool_name}:{self._step_count}"

        try:
            # Notify tool execution start
            await self._notify_progress("tool_started", {
                "tool": tool_name,
                "input": tool_input,
                "step": self._step_count,
            })

            # Execute the tool with process task context for event emission
            async with set_process_task(process_task_id):
                if asyncio.iscoroutinefunction(tool.func):
                    result = await tool.func(**tool_input)
                else:
                    result = tool.func(**tool_input)

            result_str = str(result) if result is not None else "(no output)"

            # Notify tool execution complete
            await self._notify_progress("tool_completed", {
                "tool": tool_name,
                "input": tool_input,
                "result": result_str[:500],  # Truncate for logging
                "step": self._step_count,
            })

            logger.debug(f"Tool {tool_name} executed successfully")
            return result_str

        except Exception as e:
            error_msg = f"Error executing {tool_name}: {str(e)}"
            logger.error(error_msg)

            await self._notify_progress("tool_failed", {
                "tool": tool_name,
                "input": tool_input,
                "error": str(e),
                "step": self._step_count,
            })

            return error_msg

    async def _call_reasoner(self, task: str) -> Optional[Dict[str, Any]]:
        """Call Reasoner API to get a workflow plan.

        Args:
            task: Task description.

        Returns:
            Reasoner result dict if successful, None otherwise.
        """
        if not self._memory_api_base_url or not self._ami_api_key or not self._user_id:
            logger.info("Reasoner not configured (missing api_base_url, api_key, or user_id)")
            return None

        try:
            # Build the API URL for Reasoner
            # The Reasoner endpoint is at /api/v1/reasoner/plan
            # memory_api_base_url is typically "http://localhost:9000" or "https://api.ariseos.com/api"
            base = self._memory_api_base_url.rstrip("/")
            if base.endswith("/api"):
                # Already has /api suffix (e.g., https://api.ariseos.com/api)
                api_url = f"{base}/v1/reasoner/plan"
            else:
                # Need to add /api prefix (e.g., http://localhost:9000)
                api_url = f"{base}/api/v1/reasoner/plan"

            headers = {
                "Content-Type": "application/json",
                "X-Ami-Api-Key": self._ami_api_key,
            }

            payload = {
                "target": task,
                "user_id": self._user_id,
            }

            logger.info(f"Calling Reasoner API: {api_url}")

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("success") and result.get("workflow"):
                            logger.info(f"Reasoner returned workflow with {len(result.get('states', []))} states, {len(result.get('actions', []))} actions")
                            return result
                        else:
                            logger.info(f"Reasoner returned no workflow: {result.get('message', 'no result')}")
                            return None
                    else:
                        error_text = await resp.text()
                        logger.warning(f"Reasoner API returned {resp.status}: {error_text[:200]}")
                        return None

        except asyncio.TimeoutError:
            logger.warning("Reasoner API call timed out")
            return None
        except Exception as e:
            logger.warning(f"Reasoner API call failed: {e}")
            return None

    def _build_workflow_hints(self, workflow_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract workflow hints from Reasoner result.

        Converts states and actions into a list of hint dicts that can guide the agent.

        Args:
            workflow_result: The result from Reasoner containing states, actions.

        Returns:
            List of hint dicts with description, type, target info.
        """
        states = workflow_result.get("states", [])
        actions = workflow_result.get("actions", [])

        # === DEBUG LOGGING ===
        logger.info(f"[_build_workflow_hints] Received {len(states)} states, {len(actions)} actions")

        # Log raw states
        for i, state in enumerate(states):
            if isinstance(state, dict):
                state_id = state.get("id", "?")
                state_desc = state.get("description", "")[:50]
                state_url = state.get("page_url", "")[:50]
            else:
                state_id = getattr(state, "id", "?")
                state_desc = (getattr(state, "description", "") or "")[:50]
                state_url = (getattr(state, "page_url", "") or "")[:50]
            logger.info(f"[_build_workflow_hints] State {i}: id={state_id}, desc={state_desc}, url={state_url}")

        # Log raw actions
        for i, action in enumerate(actions):
            if isinstance(action, dict):
                action_desc = action.get("description", "")[:80]
                action_type = action.get("type", "")
                action_source = action.get("source", "")
                action_target = action.get("target", "")
            else:
                action_desc = (getattr(action, "description", "") or "")[:80]
                action_type = getattr(action, "type", "") or ""
                action_source = getattr(action, "source", "") or ""
                action_target = getattr(action, "target", "") or ""
            logger.info(f"[_build_workflow_hints] Action {i}: type={action_type}, source={action_source}, target={action_target}, desc={action_desc}")
        # === END DEBUG LOGGING ===

        # Build state lookup by ID
        state_by_id = {}
        for state in states:
            state_id = state.get("id") if isinstance(state, dict) else getattr(state, "id", None)
            if state_id:
                state_by_id[state_id] = state

        hints = []
        for action in actions:
            # Extract action info
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
                target_description = target_state.description or target_state.page_title or ""
                target_url = target_state.page_url or ""
            else:
                target_description = target_state.get("description", "") or target_state.get("page_title", "")
                target_url = target_state.get("page_url", "")

            hints.append({
                "description": action_description,
                "type": action_type,
                "target_description": target_description,
                "target_url": target_url,
            })

        return hints

    def _format_paths_for_sse(self, reasoner_result: Optional[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """Format workflow paths for SSE event (L1 memory_level event).

        Args:
            reasoner_result: The Reasoner API result.

        Returns:
            Simplified path info for SSE event, or None if no result.
        """
        if not reasoner_result:
            return None

        states = reasoner_result.get("states", [])
        actions = reasoner_result.get("actions", [])

        if not states:
            return None

        paths = []
        for i, state in enumerate(states):
            # Extract state info (handle both dict and object)
            if isinstance(state, dict):
                state_desc = state.get("description", "")
                state_url = state.get("page_url", "")
            else:
                state_desc = getattr(state, "description", "") or ""
                state_url = getattr(state, "page_url", "") or ""

            path_entry = {
                "step": i + 1,
                "description": state_desc[:100],  # Truncate for SSE
                "url_pattern": state_url[:100] if state_url else None,
            }

            # Add action to next state if available
            if i < len(actions):
                action = actions[i]
                if isinstance(action, dict):
                    action_desc = action.get("description", "")
                else:
                    action_desc = getattr(action, "description", "") or ""
                path_entry["action"] = action_desc[:80] if action_desc else None

            paths.append(path_entry)

        return paths

    def _format_workflow_hints_for_prompt(
        self,
        reasoner_result: Optional[Dict[str, Any]],
        memory_level: str,
    ) -> str:
        """Format Memory/Reasoner result into prompt context for LLM.

        This creates a structured memory guidance section that helps the LLM
        understand and use the workflow hints appropriately.

        Args:
            reasoner_result: The Reasoner API result containing states and actions.
            memory_level: The determined memory level ("L1", "L2", or "L3").

        Returns:
            Formatted string for injection into LLM prompt.
        """
        if not reasoner_result or memory_level == "L3":
            return """## Memory Guidance [L3]
No complete path found in memory. You will receive real-time page information as you navigate.
Use your judgment to complete the task step by step."""

        states = reasoner_result.get("states", [])
        actions = reasoner_result.get("actions", [])
        method = reasoner_result.get("metadata", {}).get("method", "unknown")

        if memory_level == "L1":
            # L1: Complete path guidance
            header = f"""## Memory Guidance [L1 - Complete Path]
**Source**: CognitivePhrase match (previously recorded workflow)
**Confidence**: High - this exact workflow pattern was successful before

**IMPORTANT**: This path is a GUIDE, not a script. You must:
- Follow the general navigation pattern
- Adapt to current page content (items may have changed)
- Make decisions based on the user's specific task goal

### Suggested Navigation Path ({len(states)} steps):
"""
        else:
            # L2: Partial match guidance
            header = f"""## Memory Guidance [L2 - Partial Match]
**Source**: TaskDAG analysis found {len(states)} relevant page states
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
                intent_sequences = state.get("intent_sequences", [])
            else:
                state_desc = getattr(state, "description", "Unknown page") or "Unknown page"
                state_url = getattr(state, "page_url", "") or ""
                intent_sequences = getattr(state, "intent_sequences", []) or []

            step_line = f"\n**Step {i + 1}**: {state_desc}"
            if state_url:
                step_line += f"\n  URL Pattern: {state_url}"

            # Add available operations from intent_sequences
            if intent_sequences:
                step_line += "\n  Available operations:"
                for seq in intent_sequences[:3]:  # Limit to 3 operations
                    if isinstance(seq, dict):
                        seq_desc = seq.get("description", "")
                        intents = seq.get("intents", [])
                    else:
                        seq_desc = getattr(seq, "description", "") or ""
                        intents = getattr(seq, "intents", []) or []

                    if seq_desc:
                        step_line += f"\n    - {seq_desc}"
                        # Add selector hints for first intent
                        if intents:
                            intent = intents[0]
                            if isinstance(intent, dict):
                                selector = intent.get("css_selector") or intent.get("xpath", "")
                            else:
                                selector = getattr(intent, "css_selector", "") or getattr(intent, "xpath", "") or ""
                            if selector:
                                step_line += f" (selector: {selector})"

            # Add action to next state
            if i < len(actions):
                action = actions[i]
                if isinstance(action, dict):
                    action_desc = action.get("description", "")
                    action_type = action.get("type", "")
                else:
                    action_desc = getattr(action, "description", "") or ""
                    action_type = getattr(action, "type", "") or ""

                if action_desc:
                    step_line += f"\n  → Next: {action_desc}"
                elif action_type:
                    step_line += f"\n  → Next: {action_type}"

            path_lines.append(step_line)

        return header + "\n".join(path_lines)

    def _build_task_message(self, task: str) -> str:
        """Build the initial task message (legacy notes-based approach).

        DEPRECATED: Use _build_task_message_with_plan() instead.
        This method is kept for backward compatibility but is no longer
        the primary way to build task messages.

        The new approach uses TaskOrchestrator for task decomposition and
        tracking instead of notes-based task_plan.md files.

        Args:
            task: The user's task description.

        Returns:
            Formatted message string with task and notes instructions.
        """
        # Redirect to new method if orchestrator is available
        if hasattr(self, '_task_orchestrator') and self._task_orchestrator:
            plan_summary = self._task_orchestrator.get_plan_summary()
            return self._build_task_message_with_plan(task, plan_summary)

        # Legacy fallback for cases without orchestrator
        message = f"""## Your Task
{task}

## Workflow Guidance

If available, read `workflow_hints.md` for navigation guidance from similar past workflows.

## Starting Point

Begin executing the task step by step.
"""
        return message

    def _build_task_message_with_plan(
        self,
        task: str,
        plan_summary: str,
    ) -> str:
        """Build initial task message with plan summary.

        Args:
            task: The user's task description.
            plan_summary: Current plan summary from TaskOrchestrator.

        Returns:
            Formatted message string with task and plan.
        """
        message = f"""## Your Task
{task}

{plan_summary}

## How to Progress Through the Plan

For each subtask:
1. Execute the actions needed to complete the subtask
2. When done, call `complete_subtask(subtask_id, result)` to mark it complete
3. The system will show you the next subtask

## Important Tools

- `complete_subtask(subtask_id, result)` - Mark a subtask as done
- `replan_task(reason, new_subtasks, cancelled_ids)` - Adjust the plan if needed
- `get_current_plan()` - View current plan and progress
- `read_note("workflow_guide")` - Read navigation guidance if available

## When to Replan

Call `replan_task()` when you discover:
- The website structure is different than expected
- There are more/fewer items than anticipated
- A better approach becomes apparent

## Starting Point

Look at the current task in the plan above, and begin execution.
If you need navigation help, check the `workflow_guide` note.
"""
        return message

    def _inject_plan_summary_to_messages(self, plan_summary: str) -> None:
        """Inject updated plan summary and workflow hints into the message history.

        This modifies the last user message (if it's a tool_result) to include
        a plan status reminder and workflow guidance, ensuring LLM sees current
        progress and navigation hints at every step.

        Args:
            plan_summary: Current plan summary from TaskOrchestrator.
        """
        # Only inject after first iteration (initial message already has plan)
        if len(self._messages) < 3:
            return

        # Build the injection content: plan summary + workflow hints
        workflow_hint_section = ""
        if self._workflow_guide_content:
            workflow_hint_section = f"""

## Workflow Guide (Navigation Reference)
The following is a previously successful navigation path for a similar task:

{self._workflow_guide_content}

## Decision Guide (CRITICAL - FOLLOW THE WORKFLOW!)
**You MUST strictly follow the workflow's Action instructions, not take shortcuts!**

To determine your NEXT ACTION:
1. **Check current page**: What page type are you on? (match to a Step in workflow)
2. **Read the Action**: Look at the "➡️ To reach next page type: Action:" for your current step
3. **Execute EXACTLY that action**: Find the element described in the Action and click it
   - If Action says "点击导航栏中的排行榜链接" → find and click the "排行榜/Leaderboard" link in nav bar
   - If Action says "点击周排行榜链接" → find and click the "Weekly" tab/link
   - Do NOT take shortcuts like clicking "See all of last week's products" if that's not the Action!

**WRONG**: "I see a shortcut to weekly products, let me click that instead"
**RIGHT**: "Workflow says click '排行榜' link in nav bar, let me find that element"

Example:
- Current page: Product Hunt homepage (Step 2)
- Workflow Action: "点击导航栏中的'排行榜'链接进入每日排行榜页面"
- I should find "Leaderboard" or "排行榜" in the navigation bar and click it
- I should NOT click "See all of last week's products" even if it seems faster
"""

        injection_text = f"\n\n---\n{plan_summary}{workflow_hint_section}\n\nContinue with the current subtask. When done, call `complete_subtask()` to proceed."

        # Find the last user message
        for i in range(len(self._messages) - 1, -1, -1):
            msg = self._messages[i]
            if msg.get("role") == "user":
                content = msg.get("content", "")

                # If it's a list (tool_result), append plan reminder
                if isinstance(content, list):
                    # Add plan summary as a text content block
                    plan_reminder = {
                        "type": "text",
                        "text": injection_text,
                    }
                    content.append(plan_reminder)
                    msg["content"] = content
                    logger.debug(f"Injected plan summary and workflow hints into tool_result message")

                # If it's a string, append plan summary
                elif isinstance(content, str):
                    # Don't re-inject if already contains plan marker
                    if "## Current Task Plan" not in content:
                        msg["content"] = f"{content}{injection_text}"
                        logger.debug(f"Appended plan summary and workflow hints to user message")

                break  # Only modify the last user message

    def _inject_memory_context_to_messages(self, memory_context: str) -> None:
        """DEPRECATED: Memory context is now saved as workflow_guide note.

        This method is kept for backward compatibility but is no longer used.
        The LLM can now read the workflow_guide note directly using read_note().

        Args:
            memory_context: Formatted memory context string.
        """
        logger.warning("_inject_memory_context_to_messages is deprecated. Use workflow_guide note instead.")
        # No-op: Memory context is now saved as workflow_guide note
        pass

    def _get_current_hint_context(self) -> str:
        """Get context string for the current workflow hint.

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

    async def _execute_reasoner_workflow(self, workflow_result: Dict[str, Any], task: str = "") -> str:
        """Execute a workflow returned by Reasoner using LLM-Guided Execution.

        New Logic:
        - States tell Agent "where to go" (target page type)
        - Actions tell Agent "how to get there" (what to click)
        - LLM decides actual actions based on current page + action guidance

        Flow: State[0] → Action[0] → State[1] → Action[1] → State[2] ...

        Args:
            workflow_result: The result from Reasoner containing states, actions, and workflow.
            task: The original task description (user's goal).

        Returns:
            Result message describing the execution outcome.
        """
        states = workflow_result.get("states", [])
        actions = workflow_result.get("actions", [])

        logger.info(f"[LLM-Guided] Task: '{task[:100] if task else 'EMPTY'}'")
        logger.info(f"[LLM-Guided] Workflow: {len(states)} states, {len(actions)} actions")

        await self._notify_progress("reasoner_workflow_started", {
            "num_states": len(states),
            "num_actions": len(actions),
            "method": workflow_result.get("metadata", {}).get("method", "unknown"),
        })

        executed_steps = 0
        errors = []

        try:
            # Build state lookup by ID for action matching
            state_by_id = {}
            for state in states:
                state_id = state.get("id") if isinstance(state, dict) else getattr(state, "id", None)
                if state_id:
                    state_by_id[state_id] = state

            # Execute transitions: for each action, navigate from current state to next state
            for i, action in enumerate(actions):
                # Extract action info
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
                    target_description = target_state.description or target_state.page_title or ""
                    target_title = target_state.page_title or ""
                else:
                    target_description = target_state.get("description", "") or target_state.get("page_title", "")
                    target_title = target_state.get("page_title", "")

                logger.info(f"[LLM-Guided] Step {i+1}/{len(actions)}: {action_description or action_type}")
                logger.info(f"[LLM-Guided] Target: {target_description or target_title}")

                # Get current page snapshot
                snapshot = ""
                if self._session:
                    try:
                        snapshot = await self._session.get_snapshot()
                    except Exception as e:
                        logger.warning(f"[LLM-Guided] Failed to get snapshot: {e}")

                # Ask LLM to execute this navigation step
                llm_decision = await self._ask_llm_for_navigation(
                    task=task,
                    step_index=i + 1,
                    total_steps=len(actions),
                    action_description=action_description,
                    action_type=action_type,
                    target_page_description=target_description,
                    target_page_title=target_title,
                    snapshot=snapshot,
                )

                # Execute LLM's decision
                step_result = await self._execute_llm_decision(llm_decision)
                if step_result.get("success"):
                    executed_steps += step_result.get("executed_count", 1)
                    await self._notify_progress("reasoner_step_completed", {
                        "step_index": i,
                        "action": action_description or action_type,
                        "success": True,
                    })
                else:
                    error_msg = f"Step {i+1} failed: {step_result.get('error', 'unknown')}"
                    errors.append(error_msg)
                    logger.error(f"[LLM-Guided] {error_msg}")
                    await self._notify_progress("reasoner_step_failed", {
                        "step_index": i,
                        "action": action_description or action_type,
                        "error": step_result.get("error", "unknown"),
                    })
                    # Continue to next step even if this one failed

            # Final summary
            if errors:
                summary = f"LLM-Guided workflow completed with {len(errors)} errors. Executed {executed_steps} steps."
                for err in errors[:5]:
                    summary += f"\n- {err}"
            else:
                summary = f"LLM-Guided workflow completed successfully. Executed {executed_steps} steps."

            await self._notify_progress("reasoner_workflow_completed", {
                "executed_steps": executed_steps,
                "errors": len(errors),
                "success": len(errors) == 0,
            })

            return summary

        except Exception as e:
            logger.exception(f"[LLM-Guided] Workflow execution failed: {e}")
            return f"LLM-Guided workflow failed: {e}"

    async def _ask_llm_for_navigation(
        self,
        task: str,
        step_index: int,
        total_steps: int,
        action_description: str,
        action_type: str,
        target_page_description: str,
        target_page_title: str,
        snapshot: str,
    ) -> Dict[str, Any]:
        """Ask LLM to execute a navigation step based on action guidance.

        Args:
            task: User's original task goal.
            step_index: Current step index (1-based).
            total_steps: Total number of steps.
            action_description: How to navigate (from Memory Action.description).
            action_type: Type of action (e.g., "ClickLink").
            target_page_description: Description of the target page.
            target_page_title: Title of the target page.
            snapshot: Current page snapshot.

        Returns:
            Dict with LLM's decision (tool calls to execute).
        """
        # Build navigation guidance
        navigation_guide = action_description if action_description else f"Perform {action_type} to reach the next page"

        context_prompt = f"""You are an intelligent agent executing a task.

## YOUR TASK GOAL
{task}

## Current Step: {step_index}/{total_steps}

## What You Need To Do
{navigation_guide}

## Target Page (Where You Need To Go)
- Page Type: {target_page_description or "Next page in workflow"}
- Page Title: {target_page_title or "Unknown"}

## Current Page Snapshot
{snapshot[:4000] if snapshot else "(No snapshot available)"}

## Instructions
1. Look at the current page and find the element that matches the navigation guidance
2. Click that element to navigate to the target page
3. Don't navigate to URLs directly - click the appropriate element instead
4. The guidance shows the pattern from memory - adapt to what's actually on the current page

## Important for Your Task
- If your task requires "all items" but guidance shows one item, you may need to iterate
- If your task mentions "current/latest" but page shows old dates, find the current equivalent
- Always keep your actual task goal in mind

Execute the appropriate browser action now."""

        # Call LLM with tools
        self._messages = [{"role": "user", "content": context_prompt}]

        try:
            response = await self._call_llm()
            return {
                "success": True,
                "response": response,
                "has_tool_calls": response.has_tool_use() if response else False,
            }
        except Exception as e:
            logger.error(f"[LLM-Guided] LLM call failed: {e}")
            return {"success": False, "error": str(e)}

    async def _execute_llm_decision(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the tool calls decided by LLM.

        Args:
            decision: Dict containing LLM's response with tool calls.

        Returns:
            Dict with execution result.
        """
        if not decision.get("success"):
            return decision

        response = decision.get("response")
        if not response:
            return {"success": True, "executed_count": 0, "message": "No response from LLM"}

        if not decision.get("has_tool_calls"):
            # LLM decided no action needed
            text_response = self._extract_text_response(response)
            logger.info(f"[LLM-Guided] LLM decided no action needed: {text_response[:100]}")
            return {"success": True, "executed_count": 0, "message": text_response}

        # Execute tool calls
        tool_uses = response.get_tool_uses()
        executed_count = 0
        errors = []

        for tool_use in tool_uses:
            try:
                await self._notify_progress("tool_started", {
                    "tool": tool_use.name,
                    "input": tool_use.input,
                })

                result = await self._execute_tool(tool_use.name, tool_use.input)

                if "Error" in result:
                    errors.append(f"{tool_use.name}: {result}")
                else:
                    executed_count += 1

                await self._notify_progress("tool_completed", {
                    "tool": tool_use.name,
                    "result": result[:200] if result else "",
                })

            except Exception as e:
                errors.append(f"{tool_use.name}: {str(e)}")
                await self._notify_progress("tool_failed", {
                    "tool": tool_use.name,
                    "error": str(e),
                })

        if errors:
            return {
                "success": False,
                "executed_count": executed_count,
                "error": "; ".join(errors),
            }
        return {"success": True, "executed_count": executed_count}

    async def _execute_intent(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single Intent (atomic operation).

        Maps Intent types to browser toolkit actions.
        Handles both standard intent types and special cases like 'dataload'.

        Args:
            intent: Intent dict containing type, selector, text, value, etc.

        Returns:
            Dict with success status and optional error message.
        """
        intent_type = intent.get("type", "").lower()
        selector = intent.get("css_selector", "") or intent.get("xpath", "")
        text = intent.get("text", "")
        value = intent.get("value", "")

        if not self._browser_toolkit:
            return {"success": False, "error": "Browser toolkit not initialized"}

        try:
            # Map intent types to browser toolkit methods
            if intent_type in ["click", "clickelement", "click_element"]:
                if selector:
                    result = await self._browser_toolkit.browser_click(selector=selector)
                elif text:
                    result = await self._browser_toolkit.browser_click(element_text=text)
                else:
                    return {"success": False, "error": "Click requires selector or text"}

            elif intent_type in ["type", "typetext", "type_text", "input"]:
                input_text = value or text
                if selector and input_text:
                    result = await self._browser_toolkit.browser_type(
                        input_text=input_text,
                        selector=selector,
                    )
                else:
                    return {"success": False, "error": "Type requires selector and text/value"}

            elif intent_type in ["enter", "press_enter", "submit"]:
                result = await self._browser_toolkit.browser_enter(selector=selector if selector else None)

            elif intent_type in ["scroll", "scroll_down"]:
                result = await self._browser_toolkit.browser_scroll(direction="down")

            elif intent_type in ["scroll_up"]:
                result = await self._browser_toolkit.browser_scroll(direction="up")

            elif intent_type in ["select", "selectoption", "select_option"]:
                if selector and (value or text):
                    result = await self._browser_toolkit.browser_select(
                        value=value or text,
                        selector=selector,
                    )
                else:
                    return {"success": False, "error": "Select requires selector and value"}

            elif intent_type in ["navigate", "goto", "visit"]:
                url = value or text or intent.get("page_url", "")
                if url:
                    result = await self._browser_toolkit.browser_visit_page(url=url)
                else:
                    return {"success": False, "error": "Navigate requires URL"}

            # Special handling for data-related intents (recorded during page load, not executable)
            elif intent_type in ["dataload", "pageload", "load", "wait"]:
                # These intents represent page state observations, not executable actions
                # They indicate data was loaded or page finished loading - skip them
                logger.debug(f"[Intent] Skipping non-executable intent type: {intent_type}")
                return {"success": True, "skipped": True, "reason": f"Non-executable intent type: {intent_type}"}

            else:
                logger.warning(f"[Intent] Unknown intent type: {intent_type}, skipping")
                return {"success": True, "skipped": True, "reason": f"Unknown intent type: {intent_type}"}

            # Check result for errors
            if "Error" in result:
                return {"success": False, "error": result}
            return {"success": True, "result": result}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _run_agent_loop(
        self,
        task: str,
        cognitive_phrase: Optional[Any] = None,
        path: Optional[Any] = None,
        conversation_context: Optional[str] = None,
    ) -> str:
        """Main Tool-calling loop with task orchestration and plan tracking.

        This implements an enhanced Eigent/CAMEL pattern with:
        1. Task decomposition at start (using TaskOrchestrator with Memory context)
        2. Loop continues until all subtasks are done (orchestrator.all_done())
        3. Plan summary injected into context each iteration
        4. LLM calls complete_subtask() to progress through subtasks
        5. MessageHistoryManager prunes tool calls and summarizes when token limit approached

        Memory-first strategy:
        - cognitive_phrase: User-recorded complete workflow (highest value)
        - path: Retrieved navigation path from memory graph

        Args:
            task: The user's task description.
            cognitive_phrase: Optional CognitivePhrase from memory.
            path: Optional Path from memory.
            conversation_context: Optional conversation history context.
        """
        # Import memory types
        from ..tools.toolkits.memory_toolkit import MemoryToolkit

        # === Initialize Message History Manager ===
        from ..core.task_orchestrator import MessageHistoryManager
        history_manager = MessageHistoryManager(max_tokens=100000)
        history_manager.set_llm_provider(self._llm_provider)

        # === Store workflow guide as a note (before task decomposition) ===
        memory_source = "none"
        if cognitive_phrase:
            memory_source = "cognitive_phrase"
            workflow_guide_content = MemoryToolkit.format_cognitive_phrase(cognitive_phrase)
            phrase_desc = _sanitize_text(getattr(cognitive_phrase, "description", ""), max_len=120)
            logger.info(
                "[Agent Loop] Using CognitivePhrase: states=%d actions=%d desc=%s",
                len(cognitive_phrase.states),
                len(cognitive_phrase.actions),
                phrase_desc or "N/A",
            )
            for i, state in enumerate(cognitive_phrase.states[:_MAX_LOG_STEPS]):
                state_desc = _sanitize_text(getattr(state, "description", ""), max_len=120)
                state_url = _sanitize_url(getattr(state, "page_url", None))
                action_desc = "N/A"
                if i < len(cognitive_phrase.actions):
                    action = cognitive_phrase.actions[i]
                    action_desc = _sanitize_text(getattr(action, "description", ""), max_len=120)
                logger.info(
                    "[Memory] phrase step %d: state=%s url=%s action=%s",
                    i + 1,
                    state_desc or "N/A",
                    state_url or "N/A",
                    action_desc or "N/A",
                )
        elif path:
            memory_source = "path"
            workflow_guide_content = MemoryToolkit.format_navigation_path(path.states, path.actions)
            logger.info(
                "[Agent Loop] Using Path: states=%d actions=%d",
                len(path.states),
                len(path.actions),
            )
            # Log path details (sanitized, truncated)
            for i, state in enumerate(path.states[:_MAX_LOG_STEPS]):
                action_desc = "N/A"
                if i < len(path.actions):
                    action = path.actions[i]
                    if isinstance(action, dict):
                        action_desc = _sanitize_text(action.get("description"), max_len=120)
                    else:
                        action_desc = _sanitize_text(getattr(action, "description", ""), max_len=120)
                state_desc = _sanitize_text(
                    getattr(state, "description", None) if state else None,
                    max_len=120,
                )
                state_url = _sanitize_url(getattr(state, "page_url", None) if state else None)
                logger.info(
                    "[Memory] path step %d: state=%s url=%s action=%s",
                    i + 1,
                    state_desc or "N/A",
                    state_url or "N/A",
                    action_desc or "N/A",
                )
        else:
            workflow_guide_content = None
            logger.info("[Agent Loop] No memory guidance available")

        # Store workflow guide content for injection into each LLM call
        self._workflow_guide_content = workflow_guide_content

        # Save workflow guide to note if available
        if workflow_guide_content and self._note_toolkit:
            try:
                result = self._note_toolkit.create_note(
                    note_name="workflow_guide",
                    content=workflow_guide_content,
                    overwrite=True
                )
                logger.info(f"[Agent Loop] Workflow guide saved as note: {result}")
            except Exception as e:
                logger.warning(f"[Agent Loop] Failed to save workflow guide note: {e}")
        if workflow_guide_content:
            sanitized_guide = _sanitize_guide(workflow_guide_content)
            logger.info("[Memory] workflow_guide (sanitized, truncated):\n%s", sanitized_guide)

        # === Decompose task into subtasks using TaskOrchestrator ===
        # Pass memory context to help guide decomposition
        logger.info("[Agent Loop] Decomposing task into subtasks...")
        try:
            subtasks = await self._task_orchestrator._decompose_task(
                task,
                cognitive_phrase=cognitive_phrase,
                path=path,
            )
            logger.info(f"[Agent Loop] Task decomposed into {len(subtasks)} subtasks")
        except Exception as e:
            logger.warning(f"[Agent Loop] Task decomposition failed: {e}, proceeding without decomposition")
            # Create a single subtask for the entire task
            from ..core.task_orchestrator import SubTask
            subtask = SubTask(id="1.1", content=task)
            self._task_orchestrator.subtasks["1.1"] = subtask

        # ========== Wait for user confirmation before proceeding ==========
        # Emit subtasks to frontend for user review
        subtask_list = [
            {"id": st.id, "content": st.content, "state": st.state.value}
            for st in self._task_orchestrator.subtasks.values()
        ]
        await self._notify_progress("subtasks_pending_confirmation", {
            "task": task,
            "subtasks": subtask_list,
            "memory_source": memory_source,
        })
        logger.info(f"[Agent Loop] Waiting for subtask confirmation ({len(subtask_list)} subtasks)...")

        # Wait for confirmation from frontend (with 30s timeout for auto-confirm)
        if self._task_state and hasattr(self._task_state, 'wait_for_subtask_confirmation'):
            confirmed = await self._task_state.wait_for_subtask_confirmation(timeout=30.0)
            if not confirmed:
                logger.info("[Agent Loop] Subtask confirmation cancelled, exiting")
                return "Task cancelled: subtasks not confirmed."

            # Check if user edited the subtasks
            edited_subtasks = self._task_state.get_confirmed_subtasks()
            if edited_subtasks:
                # Update orchestrator with user-edited subtasks
                logger.info(f"[Agent Loop] Applying {len(edited_subtasks)} user-edited subtasks")
                self._task_orchestrator.update_subtasks_from_confirmation(edited_subtasks)
        else:
            # No task state available, proceed immediately (fallback)
            logger.warning("[Agent Loop] No task state for confirmation, proceeding immediately")

        logger.info("[Agent Loop] Subtasks confirmed, proceeding with execution")
        # ==================================================================

        # Build initial message with plan summary (workflow_guide is now in notes)
        plan_summary = self._task_orchestrator.get_plan_summary()
        # Add a hint about workflow_guide if it was saved
        workflow_hint = ""
        if workflow_guide_content and self._note_toolkit:
            workflow_hint = "\n\n**Tip**: A `workflow_guide` note is available with navigation guidance. Use `read_note(\"workflow_guide\")` if you need help navigating."
        initial_message = self._build_task_message_with_plan(task, plan_summary) + workflow_hint

        # Inject conversation context if available
        if conversation_context:
            initial_message = f"""{conversation_context}

=== CURRENT TASK ===
{initial_message}"""
            logger.info(f"[Agent Loop] Added conversation context ({len(conversation_context)} chars)")

        self._messages = [{"role": "user", "content": initial_message}]
        self._step_count = 0

        # Debug: Log the initial message sent to LLM
        logger.info("=" * 80)
        logger.info("[Agent Loop] INITIAL MESSAGE TO LLM:")
        logger.info("=" * 80)
        # Log in chunks to avoid truncation
        for i in range(0, len(initial_message), 2000):
            logger.info(f"[Initial Message Part {i//2000 + 1}]\n{initial_message[i:i+2000]}")
        logger.info("=" * 80)

        await self._notify_progress("agent_started", {
            "task": task,
            "has_cognitive_phrase": cognitive_phrase is not None,
            "has_path": path is not None,
            "has_conversation_context": bool(conversation_context),
            "num_subtasks": len(self._task_orchestrator.subtasks),
            "notes_dir": str(self._note_toolkit.working_directory) if self._note_toolkit else None,
            "memory_source": memory_source,
        })

        # Main loop: continue until all subtasks are done OR max steps reached OR cancelled
        while self._step_count < self._max_steps:
            self._step_count += 1

            # Check if task was cancelled
            if self.is_cancelled():
                logger.info("[Agent Loop] Task cancelled, exiting loop")
                await self._notify_progress("agent_cancelled", {
                    "steps": self._step_count,
                    "reason": "Task cancelled by user",
                })
                return "Task cancelled by user."

            # Check if all subtasks are done (exit condition)
            if self._task_orchestrator.all_done():
                logger.info("[Agent Loop] All subtasks completed, exiting loop")
                final_result = self._task_orchestrator.get_plan_summary()
                await self._notify_progress("agent_completed", {
                    "steps": self._step_count,
                    "response": "All subtasks completed successfully.",
                    "plan_summary": final_result,
                })
                return f"Task completed successfully.\n\n{final_result}"

            # Only schedule a new subtask if none is currently RUNNING
            current_subtask = self._task_orchestrator.get_current_subtask()
            if not current_subtask:
                current_subtask = self._task_orchestrator.get_next_subtask()
                if current_subtask and current_subtask.state == SubTaskState.OPEN:
                    self._task_orchestrator.mark_running(current_subtask.id)
                    logger.info(f"[Agent Loop] Started subtask {current_subtask.id}: {current_subtask.content[:50]}")

                    # === Query Memory for subtask navigation guidance ===
                    if self._memory_toolkit and self._memory_toolkit.is_available() and self._browser_toolkit:
                        try:
                            page_title = await self._browser_toolkit.get_page_title()
                            if page_title:
                                nav_result = await self._memory_toolkit.query_navigation(
                                    start_state=page_title,
                                    end_state=current_subtask.content,
                                )
                                if nav_result.success and (nav_result.states or nav_result.actions):
                                    nav_guide = MemoryToolkit.format_navigation_path(
                                        nav_result.states, nav_result.actions
                                    )
                                    if nav_guide and self._note_toolkit:
                                        nav_guide = (
                                            "## Memory Reference (参考信息)\n\n"
                                            "以下是 Memory 中记录的相关路径，仅供参考。\n"
                                            "页面可能已变化，前面步骤可能出错导致当前状态与预期不符。\n"
                                            "请结合实际页面内容判断。\n\n"
                                            + nav_guide
                                        )
                                        self._note_toolkit.create_note(
                                            note_name="navigation_guide",
                                            content=nav_guide,
                                            overwrite=True,
                                        )
                                        logger.info(
                                            f"[Memory] Navigation guide saved for subtask {current_subtask.id}: "
                                            f"{len(nav_result.states)} states"
                                        )
                                else:
                                    logger.debug("[Memory] No navigation path found for subtask")
                        except Exception as e:
                            logger.warning(f"[Memory] Navigation query failed: {e}")

            # === Manage message history (prune + summarize if needed) ===
            self._messages = history_manager.prune_tool_calls(self._messages)
            self._messages = await history_manager.manage_history(self._messages)

            # Get updated plan summary and inject into messages
            plan_summary = self._task_orchestrator.get_plan_summary()
            self._inject_plan_summary_to_messages(plan_summary)

            # Call LLM
            try:
                response = await self._call_llm()
            except Exception as e:
                import traceback
                logger.error(f"LLM call failed: {e}")
                logger.error(f"LLM call traceback:\n{traceback.format_exc()}")
                return f"Error: LLM call failed - {str(e)}"

            # Check for tool_use blocks using ToolCallResponse API
            tool_uses = response.get_tool_uses()

            # Extract LLM's reasoning/thinking from text blocks
            llm_reasoning = self._extract_text_response(response)
            if llm_reasoning:
                logger.info(f"[LLM Reasoning] {llm_reasoning[:500]}")
                await self._notify_progress("llm_reasoning", {
                    "step": self._step_count,
                    "reasoning": llm_reasoning,
                })

            if not response.has_tool_use():
                # No tool calls - check if this is intentional completion or LLM forgot
                if self._task_orchestrator.all_done():
                    await self._notify_progress("agent_completed", {
                        "steps": self._step_count,
                        "response": llm_reasoning[:500] if llm_reasoning else "",
                    })
                    return llm_reasoning or "Task completed."
                else:
                    # LLM stopped but tasks remain - remind it to continue
                    logger.warning("[Agent Loop] LLM stopped but subtasks remain, prompting to continue")
                    remaining = self._task_orchestrator.get_plan_summary()
                    self._messages.append({
                        "role": "user",
                        "content": f"You stopped but there are still subtasks to complete. Please continue.\n\n{remaining}",
                    })
                    continue  # Re-enter loop

            # Execute all tools and collect results
            tool_results = []
            for tool_use in tool_uses:
                # Check for cancellation before executing each tool
                if self.is_cancelled():
                    logger.info("[Agent Loop] Task cancelled during tool execution")
                    await self._notify_progress("agent_cancelled", {
                        "steps": self._step_count,
                        "reason": "Task cancelled by user",
                    })
                    return "Task cancelled by user."

                # Log why LLM decided to use this tool
                logger.info(f"[Tool Call] {tool_use.name}: {tool_use.input}")

                await self._notify_progress("tool_started", {
                    "step": self._step_count,
                    "tool": tool_use.name,
                    "input": tool_use.input,
                    "reasoning": llm_reasoning[:300] if llm_reasoning else "",
                })

                result = await self._execute_tool(tool_use.name, tool_use.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result,
                })

                await self._notify_progress("tool_completed", {
                    "step": self._step_count,
                    "tool": tool_use.name,
                    "result": result[:200] if result else "",
                })

            # Add assistant response and tool results to messages
            # Convert ToolCallResponse content to serializable format
            assistant_content = []
            for block in response.content:
                if isinstance(block, TextBlock):
                    assistant_content.append({
                        "type": "text",
                        "text": block.text,
                    })
                elif isinstance(block, ToolUseBlock):
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

            self._messages.append({"role": "assistant", "content": assistant_content})
            self._messages.append({"role": "user", "content": tool_results})

            await self._notify_progress("loop_iteration", {
                "step": self._step_count,
                "tools_called": [t.name for t in tool_uses],
                "subtasks_completed": len(self._task_orchestrator.completed_tasks),
                "subtasks_total": len(self._task_orchestrator.subtasks),
            })

            # === Wait for user confirmation if replan occurred ===
            if self._task_orchestrator.replan_pending_confirmation:
                self._task_orchestrator.replan_pending_confirmation = False
                subtask_list = [
                    {"id": st.id, "content": st.content, "state": st.state.value}
                    for st in self._task_orchestrator.subtasks.values()
                    if st.state not in (SubTaskState.DELETED, SubTaskState.DONE)
                ]
                await self._notify_progress("subtasks_pending_confirmation", {
                    "task": "Replan",
                    "subtasks": subtask_list,
                    "memory_source": "replan",
                })
                logger.info(f"[Agent Loop] Waiting for replan confirmation ({len(subtask_list)} subtasks)...")

                if self._task_state and hasattr(self._task_state, 'wait_for_subtask_confirmation'):
                    confirmed = await self._task_state.wait_for_subtask_confirmation(timeout=30.0)
                    if not confirmed:
                        logger.info("[Agent Loop] Replan confirmation cancelled, exiting")
                        return "Task cancelled: replan not confirmed."

                    edited_subtasks = self._task_state.get_confirmed_subtasks()
                    if edited_subtasks:
                        logger.info(f"[Agent Loop] Applying {len(edited_subtasks)} user-edited subtasks from replan")
                        self._task_orchestrator.update_subtasks_from_confirmation(edited_subtasks)

                logger.info("[Agent Loop] Replan confirmed, continuing execution")

        # Max steps reached
        logger.warning(f"Agent reached max steps ({self._max_steps})")
        return f"Task processing stopped after {self._max_steps} steps. Partial results may be in notes."

    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        """Execute the browser automation task.

        Execution strategy (Reasoner-first mode):
        1. Call Reasoner API to get a workflow plan
        2. If Reasoner returns a successful workflow -> execute it directly
        3. If Reasoner returns nothing -> fallback to agent loop (LLM step-by-step)
        """
        try:
            # Parse input
            task = ""
            headless = False
            reasoner_result = None  # Pre-fetched Reasoner result from service layer
            use_reasoner = True  # Whether to call Reasoner if no pre-fetched result

            task_id = None  # Task ID for directory isolation
            # Workspace directories from TaskState
            working_directory = None
            notes_directory = None
            browser_data_directory = None

            # Conversation context from previous tasks
            conversation_context = ""

            if isinstance(input_data, AgentInput):
                if input_data.data:
                    task = input_data.data.get("task", "")
                    task_id = input_data.data.get("task_id")
                    headless = input_data.data.get("headless", False)
                    reasoner_result = input_data.data.get("reasoner_result")  # Pre-fetched
                    use_reasoner = input_data.data.get("use_reasoner", True)
                    # Workspace directories
                    working_directory = input_data.data.get("working_directory")
                    notes_directory = input_data.data.get("notes_directory")
                    browser_data_directory = input_data.data.get("browser_data_directory")
                    # Conversation context for multi-turn tasks
                    conversation_context = input_data.data.get("conversation_context", "")
            elif isinstance(input_data, dict):
                task = input_data.get("task", "")
                task_id = input_data.get("task_id")
                headless = input_data.get("headless", False)
                reasoner_result = input_data.get("reasoner_result")
                use_reasoner = input_data.get("use_reasoner", True)
                # Workspace directories
                working_directory = input_data.get("working_directory")
                notes_directory = input_data.get("notes_directory")
                browser_data_directory = input_data.get("browser_data_directory")
                # Conversation context for multi-turn tasks
                conversation_context = input_data.get("conversation_context", "")

            if not task:
                return AgentOutput(
                    success=False,
                    message="Missing task description",
                    data={}
                )

            logger.info(f"EigentStyleBrowserAgent executing task: {task[:100]}...")
            if working_directory:
                logger.info(f"Using workspace: {working_directory}")

            # Initialize browser session with task-specific data directory
            # Use context.browser_session_id for session sharing across workflow steps
            browser_data_dir = _get_browser_data_dir(browser_data_directory)
            session_id = getattr(context, 'browser_session_id', None) or "default"
            logger.info(f"Using browser session_id: {session_id}")

            self._session = HybridBrowserSession(
                headless=headless,
                stealth=True,
                user_data_dir=browser_data_dir,
                session_id=session_id,
            )

            # Initialize toolkits with task isolation
            self._initialize_toolkits(
                task_id=task_id,
                working_directory=working_directory,
                notes_directory=notes_directory,
            )

            # === PHASE 1: MANDATORY MEMORY QUERY ===
            # Query Memory before task decomposition (Memory-first strategy)
            # 1. First try cognitive_phrase (user-recorded workflow)
            # 2. If not found, try path (retrieved navigation path)
            cognitive_phrase = None
            path = None
            memory_source = "none"
            execution_mode = "agent_loop"

            if self._memory_toolkit and self._memory_toolkit.is_available():
                logger.info("[Memory] Querying Memory before task decomposition...")
                await self._notify_progress("memory_query_started", {"task": task})

                # Use V2 query_task API (returns QueryResult with cognitive_phrase or path)
                memory_result = await self._memory_toolkit.query_task(task)

                if memory_result.cognitive_phrase:
                    # L1: Complete workflow replay from cognitive phrase
                    cognitive_phrase = memory_result.cognitive_phrase
                    memory_source = "cognitive_phrase"
                    execution_mode = "agent_loop_with_workflow"
                    logger.info(
                        f"[Memory] Found CognitivePhrase: {cognitive_phrase.id} "
                        f"with {len(cognitive_phrase.states)} states"
                    )
                elif memory_result.subtasks:
                    # L3: Subtask decomposition with per-subtask navigation guidance
                    # Build subtask plan with navigation info for each subtask
                    from ..tools.toolkits.memory_toolkit import CognitivePhrase as MemPath
                    # Collect all states/actions across subtasks that found results
                    all_states = []
                    all_actions = []
                    subtask_plan = []
                    for st in memory_result.subtasks:
                        subtask_info = {
                            "task_id": st.task_id,
                            "target": st.target,
                            "found": st.found,
                            "states": st.states,
                            "actions": st.actions,
                        }
                        subtask_plan.append(subtask_info)
                        if st.found:
                            all_states.extend(st.states)
                            all_actions.extend(st.actions)

                    if all_states:
                        path = MemPath(
                            id="subtask_composed_path",
                            description="Subtask-decomposed navigation path",
                            states=all_states,
                            actions=all_actions,
                        )
                        memory_source = "subtasks"
                        execution_mode = "agent_loop_with_path"
                        logger.info(
                            f"[Memory] Found subtask plan with {len(memory_result.subtasks)} subtasks, "
                            f"{len(all_states)} states total"
                        )
                    else:
                        memory_source = "subtasks_no_nav"
                        logger.info(
                            f"[Memory] Subtask plan with {len(memory_result.subtasks)} subtasks but no navigation states"
                        )

                    # Store subtask plan for agent loop to use
                    self._subtask_plan = subtask_plan
                elif memory_result.states and not memory_result.subtasks:
                    # L2: Overall navigation path (no subtask decomposition)
                    from ..tools.toolkits.memory_toolkit import CognitivePhrase as MemPath
                    path = MemPath(
                        id="composed_path",
                        description="Composed navigation path",
                        states=memory_result.states,
                        actions=memory_result.actions,
                    )
                    memory_source = "path"
                    execution_mode = "agent_loop_with_path"
                    logger.info(
                        f"[Memory] Found Path with {len(path.states)} states"
                    )
                else:
                    logger.info("[Memory] No workflow or path found")
            else:
                logger.info("[Memory] Memory not available, skipping query")

            # Emit memory_query_result SSE event
            await self._notify_progress("memory_query_result", {
                "source": memory_source,
                "has_cognitive_phrase": cognitive_phrase is not None,
                "has_path": path is not None,
                "states_count": (
                    len(cognitive_phrase.states) if cognitive_phrase
                    else len(path.states) if path
                    else 0
                ),
            })

            # Store memory context for later use
            self._cognitive_phrase = cognitive_phrase
            self._memory_path = path

            # Run agent loop with memory context
            result = await self._run_agent_loop(
                task,
                cognitive_phrase=cognitive_phrase,
                path=path,
                conversation_context=conversation_context,
            )

            # Collect notes if any
            notes_content = ""
            if self._note_toolkit:
                try:
                    notes_content = self._note_toolkit.read_note()
                except Exception:
                    pass

            # Get the actual result data from completed subtasks
            # This is important for workflow integration - the last subtask's result
            # contains the extracted data that needs to be passed to the next step
            final_result = None
            if self._task_orchestrator:
                final_result = self._task_orchestrator.get_final_result()

            return AgentOutput(
                success=True,
                data={
                    "result": final_result if final_result is not None else result,
                    "task": task,
                    "steps_taken": self._step_count,
                    "notes": notes_content,
                    "messages": self._messages,
                    "execution_mode": execution_mode,
                    "memory_source": memory_source,
                    "plan_summary": result,  # Keep the plan summary for debugging
                },
                message=f"Task completed ({execution_mode}): {task[:100]}"
            )

        except Exception as e:
            import traceback
            error_msg = f"EigentStyleBrowserAgent execution failed: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return AgentOutput(
                success=False,
                message=error_msg,
                data={"steps_taken": self._step_count}
            )

    async def cleanup(self, context: AgentContext, close_browser: bool = False):
        """Clean up browser session, toolkits, and reset state.

        Args:
            context: Agent context
            close_browser: If True, actually close the browser session.
                          If False (default), only clear local reference to allow
                          session reuse across workflow steps.
        """
        # Handle browser session
        if self._session:
            if close_browser:
                # Actually close the browser (used at workflow end)
                try:
                    await self._session.close()
                    logger.info("Browser session closed")
                except Exception as e:
                    logger.warning(f"Error closing browser session: {e}")
            else:
                # Just clear reference, keep session alive for next step
                logger.debug("Clearing browser session reference (session kept alive for reuse)")
            self._session = None

        # Reset toolkits (they don't have async cleanup, just reset references)
        self._note_toolkit = None
        self._search_toolkit = None
        self._terminal_toolkit = None
        self._human_toolkit = None
        self._browser_toolkit = None
        self._memory_toolkit = None

        # Reset LLM provider
        self._llm_provider = None

        # Reset state
        self._messages = []
        self._step_count = 0
        self._tools = []
        self._tool_map = {}
