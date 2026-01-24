"""
EigentStyleBrowserAgent - Full Tool-calling architecture ported from CAMEL-AI/Eigent.

This agent implements the complete Eigent Tool-calling architecture:
1. Tool-calling mode (using Anthropic tool_use API)
2. Complete Toolkit system (NoteTaking, Search, Terminal, Human, Browser)
3. Eigent-style System Prompt
4. Memory Path reference capability (preserved from existing system)

Unlike the ReAct-based EigentBrowserAgent, this agent:
- Uses LLM function calling instead of fixed JSON output format
- Supports parallel tool execution
- Has automatic memory management
- Includes note-taking for research documentation
"""

import asyncio
import copy
import json
import logging
import platform
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

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

- CRITICAL URL POLICY: You are STRICTLY FORBIDDEN from inventing,
  guessing, or constructing URLs yourself. You MUST only use URLs from
  trusted sources:
  1. URLs returned by search tools (search_google)
  2. URLs found on webpages you have visited through browser tools
  3. URLs provided by the user in their request
  Fabricating or guessing URLs is considered a critical error.

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

<memory_guided_workflow>
**Before starting a task**, consider using the memory toolkit:
1. Call `query_similar_workflows` with a description of your task
2. If similar workflows are found, review the suggested steps and URLs
3. Use the memory guidance to inform your navigation strategy
4. Adapt the suggestions based on the current page state

This is especially useful for:
- Navigating complex multi-step workflows (e.g., checkout processes)
- Finding specific information on familiar websites
- Repeating tasks that have been done before
</memory_guided_workflow>

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

        # Workflow hints (from Reasoner/Memory)
        self._workflow_hints: List[Dict[str, Any]] = []
        self._current_hint_index: int = 0

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

        Args:
            task_state: TaskState instance with put_event() method.
        """
        self._task_state = task_state
        logger.info(f"Task state set for event emission")

    async def _notify_progress(self, event: str, data: Dict[str, Any]):
        """Notify progress to callback if set."""
        # Debug: Log callback status for key events
        if event in ("llm_reasoning", "agent_started", "agent_completed"):
            logger.info(f"[_notify_progress] event={event}, callback_set={self._progress_callback is not None}")

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

        # Initialize TaskPlanningToolkit for task decomposition
        # Uses task_id from context for proper event emission
        # Note: task_state is set later via set_task_state() along with other toolkits
        self._task_planning_toolkit = TaskPlanningToolkit(
            task_id=self._context.task_id if self._context else "default",
        )
        logger.info("TaskPlanningToolkit initialized")

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

    def _clean_snapshot_content(self, content: str) -> str:
        """Clean snapshot content by removing interactive element markers.

        This removes [ref=eXX] markers and simplifies element descriptions
        since historical snapshots are for context only, not interaction.

        Args:
            content: The original snapshot content.

        Returns:
            Cleaned content with markers removed.
        """
        if not content:
            return content

        # Remove [ref=eXX] markers - they're only useful for current snapshot
        cleaned = re.sub(r'\[ref=e\d+\]', '', content)

        # Remove excessive whitespace that results from cleaning
        cleaned = re.sub(r' +', ' ', cleaned)
        cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned)

        return cleaned.strip()

    def _clean_tool_result_content(self, content: str) -> str:
        """Clean a tool result string, removing snapshot data if present.

        Browser tool results typically have format:
        "Some status message\n\n[snapshot content with refs]"

        We keep the status message but clean or truncate the snapshot.

        Args:
            content: The tool result string.

        Returns:
            Cleaned content.
        """
        if not content:
            return content

        # Check if this looks like a browser tool result with snapshot
        # Snapshots typically contain [ref=eXX] markers or element descriptions
        if '[ref=e' not in content and '- link ' not in content and '- button ' not in content:
            # Not a browser snapshot, return as-is (but truncate if very long)
            if len(content) > 5000:
                return content[:5000] + f"\n... [truncated, total {len(content)} chars]"
            return content

        # Split into status message and snapshot
        parts = content.split('\n\n', 1)
        if len(parts) == 1:
            # No clear separator, just clean the whole thing
            return self._clean_snapshot_content(content)

        status_msg = parts[0]
        snapshot = parts[1] if len(parts) > 1 else ""

        # For historical snapshots, provide a summary instead of full content
        # Count interactive elements as a rough indicator
        ref_count = len(re.findall(r'\[ref=e\d+\]', snapshot))

        if ref_count > 0:
            # This is a snapshot - replace with summary
            cleaned_summary = f"[Previous page snapshot: {ref_count} interactive elements - details cleaned to save context]"
            return f"{status_msg}\n\n{cleaned_summary}"
        else:
            # Clean but keep the content
            cleaned = self._clean_snapshot_content(snapshot)
            if len(cleaned) > 2000:
                cleaned = cleaned[:2000] + f"\n... [truncated]"
            return f"{status_msg}\n\n{cleaned}"

    def _clean_historical_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Clean historical messages by removing old snapshot data.

        This preserves:
        - The most recent tool results (last user message) - kept intact
        - Status messages from all tool results
        - Summary of what pages were visited

        This removes/cleans:
        - Full snapshot content from older messages
        - [ref=eXX] markers from historical snapshots

        Args:
            messages: The full message history.

        Returns:
            Cleaned message history for LLM consumption.
        """
        if len(messages) <= 2:
            # Only initial message or one round - nothing to clean
            return messages

        # Deep copy to avoid modifying original
        cleaned_messages = copy.deepcopy(messages)

        # Clean all but the last user message (which contains current tool results)
        for i, msg in enumerate(cleaned_messages[:-1]):
            if msg.get("role") == "user":
                content = msg.get("content")

                # Handle tool_result format (list of tool results)
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_result":
                            original_content = item.get("content", "")
                            if isinstance(original_content, str):
                                item["content"] = self._clean_tool_result_content(original_content)

                # Handle plain string content (less common)
                elif isinstance(content, str):
                    msg["content"] = self._clean_tool_result_content(content)

        return cleaned_messages

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
        """Call LLM with tools using AnthropicProvider.

        Uses the common/llm module's AnthropicProvider which handles
        async wrapping internally via asyncio.to_thread().

        Before sending to LLM, cleans historical snapshots to reduce token usage.
        """
        system_prompt = self._build_system_prompt()
        tools_schema = self._build_tools_schema()

        # Clean historical messages to reduce token count
        # This removes old snapshot content while preserving context
        original_size = self._estimate_message_size(self._messages)
        cleaned_messages = self._clean_historical_messages(self._messages)
        cleaned_size = self._estimate_message_size(cleaned_messages)

        if original_size != cleaned_size:
            reduction = original_size - cleaned_size
            reduction_pct = (reduction / original_size * 100) if original_size > 0 else 0
            logger.info(f"[Snapshot Clean] Reduced message size: {original_size:,} -> {cleaned_size:,} chars ({reduction_pct:.1f}% reduction)")

        response = await self._llm_provider.generate_with_tools(
            system_prompt=system_prompt,
            messages=cleaned_messages,
            tools=tools_schema,
            max_tokens=4096,
        )

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

    def _build_task_message(self, task: str) -> str:
        """Build the initial task message with notes-based task management.

        Args:
            task: The user's task description.

        Returns:
            Formatted message string with task and notes instructions.
        """
        message = f"""## Your Task
{task}

## Task Management System

I have created the following notes for this task:

1. **workflow_hints.md** - Contains navigation guidance from similar past workflows.
   - Read this to understand HOW to navigate (what to click, where to go)
   - These are GUIDES, not scripts - adapt them to your actual task

2. **task_plan.md** - Contains your task plan with checkboxes.
   - Read this at the START of each step to know what to do next
   - Update checkboxes when you complete steps: `- [ ]` → `- [x]`
   - Add progress notes using append_note

## Critical Rules

**Before EVERY action:**
1. Read `task_plan` to know your current step
2. If needed, read `workflow_hints` for navigation guidance

**For iterative tasks (collecting "all items", "every product", etc.):**
1. First, identify all items to process on the list page
2. Use `browser_get_page_info` to get each item's URL/title before clicking
3. Create a loop tracking note: `loop_<name>.md` with all items and their URLs
4. Process each item one by one:
   - Click to enter item detail page
   - Use `browser_get_page_info` to confirm and record the URL
   - Collect the data you need
   - Use `browser_back` to return to list
5. Mark each item complete in the loop note: `- [ ] 1. Item` → `- [x] 1. Item`
6. Continue until ALL items in the loop note are checked

**After completing a step:**
1. Update task_plan.md to mark the step done
2. Record any collected data using append_note

**Example loop note format:**
```
# Loop: product_collection

## Items (with URLs for reference)
- [ ] 1. Product A | https://example.com/product-a
- [ ] 2. Product B | https://example.com/product-b
- [ ] 3. Product C | https://example.com/product-c

## Collected Data
_Results will be added here_
```

## Starting Point

Read `task_plan` now to see your steps, then begin execution.
"""
        return message

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
        workflow_hints: Optional[List[Dict[str, Any]]] = None,
        conversation_context: Optional[str] = None,
    ) -> str:
        """Main Tool-calling loop with optional workflow hints and conversation context.

        This implements the Eigent/CAMEL ChatAgent.step() pattern:
        1. Send user message to LLM
        2. If LLM returns tool_use blocks, execute tools
        3. Add tool results to messages
        4. Repeat until LLM returns text-only response

        Key notes mechanism:
        - workflow_hints.md: Stores Memory guidance for reference
        - task_plan.md: Tracks task steps and completion status
        - loop_*.md: Tracks iterative operations (created by LLM when needed)

        Args:
            task: The user's task description.
            workflow_hints: Optional list of action hints from Memory/Reasoner.
                Each hint is a dict with 'description', 'type', 'target_description', etc.
                These are GUIDES, not scripts - LLM adapts them to the actual task.
            conversation_context: Optional conversation history context from previous tasks.
                Injected into prompt for multi-turn task continuation.
        """
        # Track current workflow hint index
        self._current_hint_index = 0
        self._workflow_hints = workflow_hints or []

        # === Initialize task notes ===
        # Create workflow_hints.md and task_plan.md at the start
        if self._note_toolkit:
            logger.info("[Agent Loop] Initializing task notes...")
            self._note_toolkit._create_workflow_hints_note(self._workflow_hints)
            self._note_toolkit._create_task_plan_note(task, self._workflow_hints)
            logger.info(f"[Agent Loop] Task notes created at {self._note_toolkit.working_directory}")

        # Build initial message with workflow context and conversation history
        initial_message = self._build_task_message(task)

        # Inject conversation context if available (for multi-turn tasks)
        if conversation_context:
            initial_message = f"""{conversation_context}

=== CURRENT TASK ===
{initial_message}"""
            logger.info(f"[Agent Loop] Added conversation context ({len(conversation_context)} chars)")

        self._messages = [{"role": "user", "content": initial_message}]
        self._step_count = 0

        await self._notify_progress("agent_started", {
            "task": task,
            "has_workflow_hints": bool(workflow_hints),
            "has_conversation_context": bool(conversation_context),
            "num_hints": len(self._workflow_hints),
            "notes_dir": str(self._note_toolkit.working_directory) if self._note_toolkit else None,
        })

        while self._step_count < self._max_steps:
            self._step_count += 1

            # Call LLM
            try:
                response = await self._call_llm()
            except Exception as e:
                logger.error(f"LLM call failed: {e}")
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
                # No tool calls - return final response
                await self._notify_progress("agent_completed", {
                    "steps": self._step_count,
                    "response": llm_reasoning[:500] if llm_reasoning else "",
                })
                return llm_reasoning or "Task completed."

            # Execute all tools and collect results
            tool_results = []
            for tool_use in tool_uses:
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
            })

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
            browser_data_dir = _get_browser_data_dir(browser_data_directory)
            self._session = HybridBrowserSession(
                headless=headless,
                stealth=True,
                user_data_dir=browser_data_dir,
            )

            # Initialize toolkits with task isolation
            self._initialize_toolkits(
                task_id=task_id,
                working_directory=working_directory,
                notes_directory=notes_directory,
            )

            # === UNIFIED AGENT LOOP WITH OPTIONAL WORKFLOW HINTS ===
            # Both modes now use the same agent loop, with workflow hints as guidance
            workflow_hints = None
            execution_mode = "agent_loop"

            # Get workflow hints from Reasoner result if available
            if reasoner_result:
                logger.info("[Agent Loop] Using pre-fetched Reasoner result as workflow hints")
                workflow_hints = self._build_workflow_hints(reasoner_result)
                execution_mode = "agent_loop_with_hints"
                logger.info(f"[Agent Loop] Built {len(workflow_hints)} workflow hints")
            elif use_reasoner:
                # Call Reasoner API to get hints
                logger.info("[Agent Loop] Calling Reasoner API for workflow hints...")
                await self._notify_progress("reasoner_query_started", {"task": task})

                reasoner_result = await self._call_reasoner(task)

                if reasoner_result:
                    workflow_hints = self._build_workflow_hints(reasoner_result)
                    execution_mode = "agent_loop_with_hints"
                    logger.info(f"[Agent Loop] Reasoner returned {len(workflow_hints)} workflow hints")
                else:
                    logger.info("[Agent Loop] Reasoner returned no workflow, running without hints")
                    await self._notify_progress("reasoner_fallback", {
                        "reason": "No workflow returned by Reasoner"
                    })

            # Run unified agent loop (with or without hints)
            result = await self._run_agent_loop(
                task,
                workflow_hints=workflow_hints,
                conversation_context=conversation_context,
            )

            # Collect notes if any
            notes_content = ""
            if self._note_toolkit:
                try:
                    notes_content = self._note_toolkit.read_note()
                except Exception:
                    pass

            return AgentOutput(
                success=True,
                data={
                    "result": result,
                    "task": task,
                    "steps_taken": self._step_count,
                    "notes": notes_content,
                    "messages": self._messages,
                    "execution_mode": execution_mode,
                    "reasoner_used": reasoner_result is not None,
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

    async def cleanup(self, context: AgentContext):
        """Clean up browser session, toolkits, and reset state."""
        # Close browser session
        if self._session:
            try:
                await self._session.close()
            except Exception as e:
                logger.warning(f"Error closing browser session: {e}")
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
