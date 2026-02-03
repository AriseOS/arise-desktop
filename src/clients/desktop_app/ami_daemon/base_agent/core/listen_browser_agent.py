"""
ListenBrowserAgent - Browser Agent with Workforce integration and Memory support.

This agent combines:
- ListenChatAgent's SSE events and Workforce integration
- EigentStyleBrowserAgent's TaskOrchestrator and tool capabilities
- Memory context injection at task/subtask/page levels

Key Features:
- Internal task decomposition with Memory assistance (L1/L2/L3)
- Dynamic replan capability for discovering new items
- Page operation caching for efficient Memory usage
- Full Toolkit support (Browser, NoteTaking, Search, Terminal, Human, Memory)
"""

import asyncio
import json
import logging
import platform
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union, TYPE_CHECKING

from camel.messages import BaseMessage
from camel.models import BaseModelBackend
from camel.toolkits import FunctionTool

from .listen_chat_agent import ListenChatAgent
from ..events import (
    SubtaskStateData,
    DynamicTasksAddedData,
    TaskDecomposedData,
    NoticeData,
)
from ..events.toolkit_listen import _run_async_safely

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
# Data Structures
# =============================================================================

class SubTaskState(str, Enum):
    """State of a subtask in the internal task plan."""
    OPEN = "OPEN"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class SubTask:
    """
    Internal subtask for ListenBrowserAgent's task orchestration.

    Each subtask represents a step in the agent's execution plan,
    which may be derived from Memory (L1) or LLM decomposition (L2/L3).
    """
    id: str
    content: str
    state: SubTaskState = SubTaskState.OPEN
    result: Optional[str] = None

    # Memory hints (from cognitive_phrase)
    memory_state_id: Optional[str] = None
    memory_action_id: Optional[str] = None


# =============================================================================
# System Prompt
# =============================================================================

LISTEN_BROWSER_AGENT_SYSTEM_PROMPT = """
<role>
You are a Browser Research Agent, responsible for web browsing, data collection,
and information extraction tasks. You execute tasks step by step, tracking
progress and adapting to discoveries.
</role>

<operating_environment>
- System: {platform} ({architecture})
- Working Directory: {working_directory}
- Current Date: {current_date}
</operating_environment>

<task_management>
## Task Planning Tools (TRACK YOUR PROGRESS)

1. **Check current plan**: Call `get_current_plan()` to see subtasks and progress

2. **After completing a subtask**: Call `complete_subtask(subtask_id, result)`
   - subtask_id: e.g., "1.1", "1.2"
   - result: Brief summary of what was accomplished

3. **If a subtask fails**: Call `report_subtask_failure(subtask_id, error)`

4. **If you discover multiple items** (CRITICAL!):
   Call `replan_task(reason, new_subtasks, cancelled_subtask_ids)`
   - Use when you find a list of items to process (e.g., 10 products)
   - Add ONE subtask for EACH item

Example - Processing multiple items:
```
# Found 5 products on the page
replan_task(
    reason="Found 5 products to analyze",
    new_subtasks=[
        {{"id": "2.1", "content": "Analyze product: ProductA"}},
        {{"id": "2.2", "content": "Analyze product: ProductB"}},
        {{"id": "2.3", "content": "Analyze product: ProductC"}},
        {{"id": "2.4", "content": "Analyze product: ProductD"}},
        {{"id": "2.5", "content": "Analyze product: ProductE"}}
    ]
)
```
</task_management>

<note_taking>
## Note-Taking (CRITICAL)
- Record ALL findings in detail using note tools
- Include exact URLs as sources
- Do not summarize - capture complete information
</note_taking>

<url_policy>
## URL Policy (CRITICAL)
You MUST only use URLs from:
1. Search tool results
2. Pages you have visited
3. User-provided URLs
NEVER invent or guess URLs.
</url_policy>

<workflow_guide_usage>
## Using Workflow Guide
If a workflow_guide is provided:
1. It shows a PROVEN navigation path
2. States = page TYPES, not fixed URLs
3. Actions = how to navigate between page types
4. Adapt to current context - URLs may differ
</workflow_guide_usage>
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
    Browser Agent with full EigentStyleBrowserAgent capabilities.

    Combines:
    - ListenChatAgent's SSE events and Workforce integration
    - EigentStyleBrowserAgent's Memory integration and TaskOrchestrator

    This agent can:
    - Execute browser-based tasks with full toolkit support
    - Use Memory context for task decomposition and guidance
    - Dynamically replan when discovering new items
    - Track progress through internal subtask management
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
        # Execution limits
        max_steps: int = 500,
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
            max_steps: Maximum execution steps.
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

        # Internal task management
        self._subtasks: List[SubTask] = []
        self._current_subtask_index: int = 0

        # Memory context (set by Workforce via set_memory_context)
        self._memory_result: Optional["QueryResult"] = None
        # Note: _workflow_guide_content and _memory_level are inherited from ListenChatAgent

        # Execution limits
        self._max_steps = max_steps
        self._step_count = 0

        # Register all tools
        self._register_all_tools()

        logger.info(
            f"[ListenBrowserAgent] Initialized: {agent_name}, "
            f"working_dir={wd[:50]}..."
        )

    def _register_all_tools(self) -> None:
        """Register all tools including internal task management tools."""
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

        # Internal Task Management Tools
        # These are agent instance methods that LLM can call
        task_tools = [
            FunctionTool(self.get_current_plan),
            FunctionTool(self.complete_subtask),
            FunctionTool(self.report_subtask_failure),
            FunctionTool(self.replan_task),
        ]
        for tool in task_tools:
            tool_name = tool.get_function_name()
            self._internal_tools[tool_name] = tool

            # Register with CAMEL's ChatAgent so LLM can see these tools
            # Use inherited add_tool() method which properly updates tool list
            try:
                self.add_tool(tool)
            except Exception as e:
                logger.debug(f"[ListenBrowserAgent] add_tool for {tool_name} failed: {e}")

        logger.info(
            f"[ListenBrowserAgent] Registered {len(self._internal_tools)} tools "
            f"(including 4 task management tools)"
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
        Set Memory context (called by Workforce when assigning task).

        This method receives the Memory query result from the Workforce
        and stores it for use during task execution.

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

    # =========================================================================
    # Task Execution
    # =========================================================================

    async def execute(self, task: str) -> str:
        """
        Execute a browser task.

        Flow:
        1. Decompose task with Memory assistance
        2. Run agent loop executing subtasks
        3. Support dynamic replan

        Args:
            task: Task description to execute.

        Returns:
            Final result summary.
        """
        logger.info(f"[ListenBrowserAgent] Starting task: {task[:100]}...")

        # Reset state
        self._step_count = 0
        self._subtasks = []
        self._current_subtask_index = 0

        # Step 1: Decompose task with Memory
        await self._decompose_task_with_memory(task)

        # Step 2: Run execution loop
        result = await self._run_agent_loop(task)

        return result

    async def _decompose_task_with_memory(self, task: str) -> None:
        """
        Decompose task using Memory assistance.

        - L1: Direct conversion from cognitive_phrase.execution_plan
        - L2/L3: LLM decomposition with Memory as reference
        """
        if (
            self._memory_level == "L1"
            and self._memory_result
            and self._memory_result.cognitive_phrase
        ):
            # L1: Direct conversion from cognitive_phrase
            self._subtasks = self._workflow_to_subtasks(
                self._memory_result.cognitive_phrase
            )
            logger.info(
                f"[ListenBrowserAgent] L1: Generated {len(self._subtasks)} subtasks "
                "from cognitive_phrase"
            )
        else:
            # L2/L3: LLM decomposition
            self._subtasks = await self._llm_decompose_task(
                task,
                memory_context=self._workflow_guide_content,
            )
            logger.info(
                f"[ListenBrowserAgent] {self._memory_level}: LLM generated "
                f"{len(self._subtasks)} subtasks"
            )

        # Emit task decomposed event
        await self._emit_task_decomposed_event()

    def _workflow_to_subtasks(self, phrase: Any) -> List[SubTask]:
        """
        Convert CognitivePhrase to SubTask list.

        Each execution_step becomes a subtask with Memory hints.
        """
        subtasks = []

        # Get state and action maps
        state_map = {}
        action_map = {}

        if hasattr(phrase, 'states') and phrase.states:
            state_map = {s.id: s for s in phrase.states}
        if hasattr(phrase, 'actions') and phrase.actions:
            action_map = {a.id: a for a in phrase.actions}

        # Convert execution_plan to subtasks
        if hasattr(phrase, 'execution_plan') and phrase.execution_plan:
            for step in phrase.execution_plan:
                state_id = getattr(step, 'state_id', None)
                state = state_map.get(state_id) if state_id else None

                if not state:
                    continue

                # Build subtask content
                content = f"Navigate to: {getattr(state, 'description', 'Unknown')}"
                if hasattr(state, 'page_url') and state.page_url:
                    content += f" (URL pattern: {state.page_url})"

                # Add navigation action
                nav_action_id = getattr(step, 'navigation_action_id', None)
                if nav_action_id:
                    action = action_map.get(nav_action_id)
                    if action and hasattr(action, 'description') and action.description:
                        content += f"\nAction: {action.description}"
                        if hasattr(action, 'trigger') and action.trigger:
                            trigger_text = action.trigger.get('text', '')
                            if trigger_text:
                                content += f" (click \"{trigger_text}\")"

                step_index = getattr(step, 'index', len(subtasks) + 1)
                subtask = SubTask(
                    id=f"1.{step_index}",
                    content=content,
                    state=SubTaskState.OPEN,
                    memory_state_id=state_id,
                    memory_action_id=nav_action_id,
                )
                subtasks.append(subtask)

        return subtasks

    async def _llm_decompose_task(
        self,
        task: str,
        memory_context: Optional[str] = None,
    ) -> List[SubTask]:
        """
        Use LLM to decompose task into subtasks.

        Args:
            task: The task to decompose.
            memory_context: Optional workflow guide to help LLM (unused, injected via astep).

        Returns:
            List of SubTask objects.
        """
        # Build decomposition prompt
        # Note: memory_context is NOT manually added here because astep() will
        # automatically inject workflow_guide via _inject_workflow_guide().
        # Adding it here would result in duplicate injection.
        prompt_parts = [
            "Break down this task into 2-5 actionable subtasks.",
            "Each subtask should be specific and achievable.",
            "",
            f"Task: {task}",
            "",
            "Return as numbered list:",
            "1. First subtask",
            "2. Second subtask",
            "...",
        ]

        prompt = "\n".join(prompt_parts)

        # workflow_guide is injected via _inject_workflow_guide in astep() - do NOT add manually

        # Call LLM
        response = await self.astep(prompt)

        # Parse response into subtasks
        subtasks = []
        if response and response.msg:
            lines = response.msg.content.strip().split('\n')
            for line in lines:
                # Match numbered lines like "1. Do something"
                match = re.match(r'^(\d+)\.\s*(.+)$', line.strip())
                if match:
                    subtask = SubTask(
                        id=f"1.{match.group(1)}",
                        content=match.group(2).strip(),
                        state=SubTaskState.OPEN,
                    )
                    subtasks.append(subtask)

        # Fallback: create single subtask if parsing failed
        if not subtasks:
            subtasks = [SubTask(id="1.1", content=task, state=SubTaskState.OPEN)]

        return subtasks

    async def _emit_task_decomposed_event(self) -> None:
        """Emit task_decomposed event for frontend."""
        subtasks_data = [
            {
                "id": st.id,
                "content": st.content,
                "state": st.state.value,
                "status": st.state.value,  # Backward compatibility
            }
            for st in self._subtasks
        ]
        await self._emit_event(TaskDecomposedData(
            task_id=self._task_state.task_id if self._task_state else None,
            subtasks=subtasks_data,
            total_subtasks=len(self._subtasks),
        ))

    # =========================================================================
    # Agent Loop
    # =========================================================================

    async def _run_agent_loop(self, task: str) -> str:
        """
        Run the agent execution loop.

        Each iteration:
        1. Check if all subtasks complete
        2. Build current message with context
        3. Call LLM
        4. Process tool calls
        5. Repeat until done
        """
        # Build initial message
        initial_message = self._build_initial_message(task)

        # Main loop
        while not self._all_subtasks_complete():
            # Check step limit
            self._step_count += 1
            if self._step_count > self._max_steps:
                logger.warning(f"[ListenBrowserAgent] Max steps exceeded")
                break

            # Check cancellation
            if self.is_cancelled():
                logger.info(f"[ListenBrowserAgent] Task cancelled")
                break

            # Build loop message
            loop_message = await self._build_loop_message()

            # Combine messages
            if self._step_count == 1:
                current_message = f"{initial_message}\n\n{loop_message}"
            else:
                current_message = loop_message

            # Execute step
            try:
                response = await self.astep(current_message)

                # Check for completion indicators
                if self._check_task_complete(response):
                    break

            except Exception as e:
                logger.error(f"[ListenBrowserAgent] Step error: {e}", exc_info=True)
                break

        # Return final result
        return self._get_final_result()

    def _build_initial_message(self, task: str) -> str:
        """Build the initial message for the execution loop."""
        parts = [
            f"## Task\n{task}",
            "",
            "## Instructions",
            "1. Call `get_current_plan()` to see the task breakdown",
            "2. Work through subtasks one by one",
            "3. Call `complete_subtask(id, result)` after finishing each",
            "4. **CRITICAL**: If you discover multiple items to process (e.g., a list of products):",
            "   - Call `replan_task()` to add a subtask for EACH item",
            "   - Example: Found 10 products → add 10 subtasks to process each one",
            "5. Record all findings using note tools",
        ]
        return "\n".join(parts)

    async def _build_loop_message(self) -> str:
        """
        Build message for each loop iteration.

        Includes:
        - Full plan summary with all subtask states
        - Current subtask info
        - Decision guide (if workflow_guide available)
        - Page operations (if URL changed)
        """
        parts = []

        # Full plan summary (like EigentStyleBrowserAgent)
        plan_summary = self._get_plan_summary()
        parts.append(plan_summary)

        # Decision guide for workflow following
        if self._workflow_guide_content:
            parts.append(self._build_decision_guide())

        # Query page operations if on new page
        if self._memory_toolkit:
            current_url = await self._get_current_url()
            if current_url:
                logger.debug(
                    f"[Memory] Page operations check: url={current_url[:120]}..."
                )
                cached = self.get_cached_page_operations(current_url)
                if not cached:
                    logger.debug("[Memory] Page operations cache miss, querying Memory")
                    # Query Memory for page operations
                    try:
                        ops = await self._memory_toolkit.query_page_operations(
                            current_url
                        )
                        if ops:
                            self.cache_page_operations(current_url, ops)
                            logger.debug(
                                "[Memory] Page operations appended to loop message "
                                f"(length={len(ops)})"
                            )
                            parts.append(f"\n## Page Operations (from Memory)\n{ops}")
                        else:
                            logger.debug("[Memory] Page operations query returned empty")
                    except Exception as e:
                        logger.debug(f"Page operations query failed: {e}")
                else:
                    logger.debug(
                        "[Memory] Page operations cache hit "
                        f"(length={len(cached)})"
                    )

        parts.append("\nContinue with the current subtask. When done, call `complete_subtask()` to proceed.")

        return "\n".join(parts) if parts else "Continue with the current plan."

    def _get_plan_summary(self) -> str:
        """
        Get compact plan summary for LLM context.

        Returns formatted string showing all subtasks and their states.
        Similar to EigentStyleBrowserAgent's TaskOrchestrator.get_plan_summary()
        """
        if not self._subtasks:
            return "## Current Task Plan\nNo plan created yet."

        lines = ["## Current Task Plan"]

        for i, subtask in enumerate(self._subtasks):
            if subtask.state == SubTaskState.DONE:
                status = "[x]"
                suffix = "✓"
            elif subtask.state == SubTaskState.FAILED:
                status = "[!]"
                suffix = f"FAILED: {subtask.result[:30] if subtask.result else 'unknown'}"
            elif subtask.state == SubTaskState.CANCELLED:
                status = "[-]"
                suffix = "cancelled"
            elif i == self._current_subtask_index and subtask.state == SubTaskState.OPEN:
                status = "[>]"
                suffix = "<- CURRENT"
            else:
                status = "[ ]"
                suffix = ""

            line = f"{status} [{subtask.id}] {subtask.content}"
            if suffix:
                line += f" {suffix}"
            lines.append(line)

            # Show result for completed tasks (truncated)
            if subtask.state == SubTaskState.DONE and subtask.result:
                lines.append(f"    Result: {subtask.result[:80]}...")

        completed = sum(1 for s in self._subtasks if s.state == SubTaskState.DONE)
        total = len(self._subtasks)
        lines.append(f"\nProgress: {completed}/{total} completed")

        return "\n".join(lines)

    def _build_decision_guide(self) -> str:
        """
        Build decision guide for workflow following.

        Includes the actual workflow_guide content and instructions
        on how to follow it. Ported from EigentStyleBrowserAgent.
        """
        # First, include the actual workflow guide content
        workflow_section = ""
        if self._workflow_guide_content:
            workflow_section = f"""
## Workflow Guide (Navigation Reference)
The following is a previously successful navigation path for a similar task:

{self._workflow_guide_content}

"""

        # Then add the decision guide with strong emphasis
        decision_guide = """## Decision Guide (CRITICAL - FOLLOW THE WORKFLOW!)
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

4. **If you find multiple items** (e.g., 10 products):
   - Call `replan_task()` to add subtasks for each item
   - Example: Found 5 products → add subtasks "Process product 1", "Process product 2", etc.

5. **Don't skip steps** - Follow the workflow order exactly

IMPORTANT: If you discover more items than expected, use `replan_task()` to add new subtasks!
"""
        return workflow_section + decision_guide

    def _all_subtasks_complete(self) -> bool:
        """Check if all subtasks are complete."""
        if not self._subtasks:
            return True

        for st in self._subtasks:
            if st.state in (SubTaskState.OPEN, SubTaskState.RUNNING):
                return False
        return True

    def _check_task_complete(self, response: Any) -> bool:
        """Check if response indicates task completion."""
        if not response or not response.msg or not response.msg.content:
            return False

        content = response.msg.content.lower()
        # Check for completion indicators
        return (
            "all subtasks completed" in content
            or "task completed" in content
            or "finished all" in content
        )

    def _get_current_subtask(self) -> Optional[SubTask]:
        """Get the current subtask to work on."""
        for st in self._subtasks:
            if st.state == SubTaskState.OPEN:
                return st
        return None

    def _advance_to_next_subtask(self) -> None:
        """
        Advance _current_subtask_index to the next OPEN subtask.

        This is called after completing a subtask to update the index.
        """
        for i, st in enumerate(self._subtasks):
            if st.state == SubTaskState.OPEN:
                self._current_subtask_index = i
                return
        # No more open subtasks
        self._current_subtask_index = len(self._subtasks)

    async def _get_current_url(self) -> Optional[str]:
        """
        Get the current browser URL.

        Returns the cached _current_page_url which is updated by BrowserToolkit.
        """
        return self._current_page_url

    def _get_final_result(self) -> str:
        """Get final result summary."""
        completed = [st for st in self._subtasks if st.state == SubTaskState.DONE]
        failed = [st for st in self._subtasks if st.state == SubTaskState.FAILED]

        parts = [
            f"## Execution Summary",
            f"- Total subtasks: {len(self._subtasks)}",
            f"- Completed: {len(completed)}",
            f"- Failed: {len(failed)}",
            f"- Steps taken: {self._step_count}",
        ]

        if completed:
            parts.append("\n## Completed Subtasks")
            for st in completed:
                parts.append(f"- [{st.id}] {st.content[:50]}...")
                if st.result:
                    parts.append(f"  Result: {st.result[:100]}...")

        return "\n".join(parts)

    # =========================================================================
    # Internal Task Management Tools (LLM callable)
    # =========================================================================

    def get_current_plan(self) -> str:
        """
        Get the current task plan and progress.

        Returns:
            Formatted string showing subtasks and their states.
        """
        if not self._subtasks:
            return "No task plan available. The task has not been decomposed yet."

        lines = ["## Current Task Plan\n"]

        for i, subtask in enumerate(self._subtasks):
            state_emoji = {
                SubTaskState.OPEN: "[ ]",
                SubTaskState.RUNNING: "[*]",
                SubTaskState.DONE: "[x]",
                SubTaskState.FAILED: "[!]",
                SubTaskState.CANCELLED: "[-]",
            }.get(subtask.state, "[?]")

            current_marker = " <- CURRENT" if subtask.state == SubTaskState.OPEN and i == self._current_subtask_index else ""
            lines.append(
                f"{state_emoji} [{subtask.id}] {subtask.content}{current_marker}"
            )

            if subtask.result:
                lines.append(f"    Result: {subtask.result[:100]}...")

        completed = sum(1 for s in self._subtasks if s.state == SubTaskState.DONE)
        total = len(self._subtasks)
        lines.append(f"\nProgress: {completed}/{total} completed")

        return "\n".join(lines)

    def complete_subtask(self, subtask_id: str, result: str) -> str:
        """
        Mark a subtask as completed with the given result.

        Args:
            subtask_id: The ID of the subtask to complete (e.g., "1.1", "1.2").
            result: Brief summary of what was accomplished.

        Returns:
            Confirmation message and next subtask info.
        """
        subtask = self._find_subtask(subtask_id)
        if not subtask:
            return f"Error: Subtask '{subtask_id}' not found"

        subtask.state = SubTaskState.DONE
        subtask.result = result

        # Emit SSE event
        _run_async_safely(self._emit_event(SubtaskStateData(
            task_id=self._task_state.task_id if self._task_state else None,
            subtask_id=subtask_id,
            state="DONE",
            result=result[:200] if result else None,
        )))

        # Advance to next subtask
        self._advance_to_next_subtask()

        # Find next subtask
        next_subtask = self._get_current_subtask()
        if next_subtask:
            return (
                f"Subtask '{subtask_id}' completed.\n\n"
                f"Next subtask:\n"
                f"[{next_subtask.id}] {next_subtask.content}"
            )
        else:
            return (
                f"Subtask '{subtask_id}' completed.\n\n"
                "All subtasks completed! Please provide a final summary."
            )

    def report_subtask_failure(self, subtask_id: str, error: str) -> str:
        """
        Report that a subtask has failed.

        Args:
            subtask_id: The ID of the failed subtask.
            error: Description of what went wrong.

        Returns:
            Instructions for handling the failure.
        """
        subtask = self._find_subtask(subtask_id)
        if not subtask:
            return f"Error: Subtask '{subtask_id}' not found"

        subtask.state = SubTaskState.FAILED
        subtask.result = f"FAILED: {error}"

        # Emit SSE event
        _run_async_safely(self._emit_event(SubtaskStateData(
            task_id=self._task_state.task_id if self._task_state else None,
            subtask_id=subtask_id,
            state="FAILED",
            result=error[:200] if error else None,
        )))

        return (
            f"Subtask '{subtask_id}' marked as failed.\n\n"
            f"Options:\n"
            f"1. Call replan_task() to adjust the plan\n"
            f"2. Skip this subtask and continue with the next one\n"
            f"3. Retry with a different approach"
        )

    def replan_task(
        self,
        reason: str,
        new_subtasks: List[Dict[str, str]],
        cancelled_subtask_ids: Optional[List[str]] = None,
    ) -> str:
        """
        Adjust the task plan by adding new subtasks or cancelling existing ones.

        Use this when you discover:
        - More items to process than expected
        - A subtask needs to be split
        - The original plan doesn't match the situation

        Args:
            reason: Why the replan is needed.
            new_subtasks: List of new subtasks, each with 'id' and 'content'.
            cancelled_subtask_ids: Optional list of subtask IDs to cancel.

        Returns:
            Updated plan summary.
        """
        logger.info(f"[ListenBrowserAgent] Replan requested: {reason}")

        # Cancel specified subtasks
        if cancelled_subtask_ids:
            for subtask_id in cancelled_subtask_ids:
                subtask = self._find_subtask(subtask_id)
                if subtask:
                    subtask.state = SubTaskState.CANCELLED

        # Add new subtasks
        for new_task_data in new_subtasks:
            new_subtask = SubTask(
                id=new_task_data.get("id", f"2.{len(self._subtasks) + 1}"),
                content=new_task_data.get("content", ""),
                state=SubTaskState.OPEN,
            )
            self._subtasks.append(new_subtask)

        # Emit replan event
        _run_async_safely(self._emit_event(DynamicTasksAddedData(
            task_id=self._task_state.task_id if self._task_state else None,
            new_tasks=[
                {"id": t.get("id", ""), "content": t.get("content", ""), "state": "OPEN", "status": "OPEN"}
                for t in new_subtasks
            ],
            reason=reason,
            total_tasks_now=len(self._subtasks),
            total_tasks=len(self._subtasks),
        )))

        return f"Plan updated: {reason}\n\n{self.get_current_plan()}"

    def _find_subtask(self, subtask_id: str) -> Optional[SubTask]:
        """Find a subtask by ID."""
        for st in self._subtasks:
            if st.id == subtask_id:
                return st
        return None

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

        # Copy task state
        new_agent._subtasks = [
            SubTask(
                id=st.id,
                content=st.content,
                state=st.state,
                result=st.result,
                memory_state_id=st.memory_state_id,
                memory_action_id=st.memory_action_id,
            )
            for st in self._subtasks
        ]
        new_agent._current_subtask_index = self._current_subtask_index
        new_agent._memory_result = self._memory_result

        return new_agent
