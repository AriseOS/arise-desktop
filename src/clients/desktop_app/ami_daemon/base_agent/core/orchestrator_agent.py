"""
Orchestrator Agent - Top-level coordinator that decides how to handle user requests.

The Orchestrator Agent replaces the hardcoded question_confirm classification with
an LLM-powered decision system. It has access to:
- Basic tools (search, browse_url, file operations, terminal, notes)
- A special `decompose_task` tool to trigger Workforce for complex tasks

When the user sends a message, the Orchestrator decides:
1. Reply directly (simple questions, greetings)
2. Use tools to complete the task (single tool calls)
3. Call decompose_task to trigger full Workforce execution (complex multi-step tasks)

This design follows OpenClaw's pattern where the LLM autonomously decides
the best approach, rather than using hardcoded classification rules.
"""

import asyncio
import datetime
import logging
import platform
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from camel.toolkits import FunctionTool
from camel.messages import BaseMessage

from .listen_chat_agent import ListenChatAgent
from .agent_factories import create_model_backend, _extract_callable, _get_now_str
from ..tools.toolkits import (
    NoteTakingToolkit,
    SearchToolkit,
    HumanToolkit,
    MemoryToolkit,
)

if TYPE_CHECKING:
    from ..events import SSEEmitter

logger = logging.getLogger(__name__)

# Maximum iterations for Orchestrator's tool-use loop
MAX_ORCHESTRATOR_ITERATIONS = 20


# Orchestrator System Prompt
ORCHESTRATOR_SYSTEM_PROMPT = """\
You are AMI, a coordinator in a multi-agent system.

## Your Role
You are the first point of contact for user requests. You can answer simple questions directly, or delegate complex work to your team via `decompose_task`. You yourself cannot browse websites or write code.

## Your Team
- **Browser Agent**: Browse websites, click buttons, fill forms, extract content, take screenshots, multi-page navigation
- **Developer Agent**: Write Python/JS code, execute scripts, build applications, automate tasks
- **Document Agent**: Create Word documents, Excel spreadsheets, PowerPoint presentations, PDF reports
- **Social Agent**: Send emails (Gmail), manage calendar, post to social media, access Notion

## Environment
- System: {platform_system} ({platform_machine})
- Working Directory: {working_directory}
- Current Date: {now_str}

## Your Tools
- search_google: Quick web search for simple questions
- write_note, read_note: Take notes (shared with other agents)
- ask_human_via_console: Ask user for clarification
- decompose_task: Delegate work to your team
"""


class DecomposeTaskTool:
    """
    Special tool that triggers Workforce execution for complex tasks.

    When the Orchestrator calls this tool, it signals that the current task
    should be handed off to the full Workforce pipeline (decomposition,
    user confirmation, multi-agent execution).
    """

    def __init__(self, callback: Callable[[str], Any]):
        """
        Initialize DecomposeTaskTool.

        Args:
            callback: Async function to call when decompose_task is invoked.
                     Takes the task description and returns the execution result.
        """
        self._callback = callback
        self._triggered = False
        self._task_description: Optional[str] = None

    @property
    def triggered(self) -> bool:
        """Check if decompose_task was called."""
        return self._triggered

    @property
    def task_description(self) -> Optional[str]:
        """Get the task description passed to decompose_task."""
        return self._task_description

    def reset(self) -> None:
        """Reset the trigger state."""
        self._triggered = False
        self._task_description = None

    def decompose_task(self, task_description: str) -> str:
        """
        Delegate a task to specialized agents (Browser, Developer, Document, etc.)

        Call this when the task requires browsing websites, writing code, or
        creating documents - things you cannot do yourself.

        Args:
            task_description: The user's request in their own words.
                - Summarize what the user asked for, nothing more
                - Do NOT add requirements the user didn't mention
                - Do NOT specify output formats unless user asked
                - Do NOT add "suggested steps" or implementation details
                - Keep the original intent and scope

                Good: "看看 Amazon 上卖的最好的 10 个 AI 眼镜"
                Bad:  "访问亚马逊，收集 AI 眼镜详细信息包括价格、评分、品牌..."

        Returns:
            Confirmation that the task has been queued for execution.
        """
        self._triggered = True
        self._task_description = task_description
        logger.info(f"[DecomposeTaskTool] Triggered with: {task_description[:100]}...")

        return (
            f"Task queued for Workforce execution: {task_description[:100]}...\n"
            "The Workforce will decompose this into subtasks and coordinate "
            "specialized agents. You will receive the results when complete."
        )


async def create_orchestrator_agent(
    task_state: Any,
    task_id: str,
    working_directory: str,
    notes_directory: Optional[str] = None,
    browser_data_directory: Optional[str] = None,
    headless: bool = False,
    memory_api_base_url: Optional[str] = None,
    ami_api_key: Optional[str] = None,
    user_id: Optional[str] = None,
    llm_api_key: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    decompose_callback: Optional[Callable[[str], Any]] = None,
) -> tuple[ListenChatAgent, DecomposeTaskTool]:
    """
    Create the Orchestrator Agent with all basic toolkits and decompose_task.

    The Orchestrator is the top-level agent that receives all user messages.
    It decides whether to:
    - Reply directly (simple queries)
    - Use tools (single operations)
    - Call decompose_task for Workforce execution (complex tasks)

    Args:
        task_state: TaskState for SSE event emission
        task_id: Task identifier (used as session_id for browser)
        working_directory: Directory for file operations
        notes_directory: Directory for notes (defaults to working_directory)
        browser_data_directory: Directory for browser user data
        headless: Whether to run browser in headless mode
        memory_api_base_url: API URL for memory service
        ami_api_key: AMI API key
        user_id: User identifier
        llm_api_key: LLM API key
        llm_model: LLM model name
        llm_base_url: LLM base URL
        decompose_callback: Callback function for decompose_task tool

    Returns:
        Tuple of (ListenChatAgent, DecomposeTaskTool)
    """
    logger.info(f"[OrchestratorAgent] Creating for task {task_id}")
    logger.info(f"[OrchestratorAgent] Working directory: {working_directory}")

    agent_name = "orchestrator_agent"
    notes_dir = notes_directory or working_directory

    # Initialize toolkits (lightweight - no browser/terminal for Orchestrator)
    note_toolkit = NoteTakingToolkit(notes_directory=notes_dir)
    note_toolkit.set_task_state(task_state)

    search_toolkit = SearchToolkit()
    search_toolkit.set_task_state(task_state)

    human_toolkit = HumanToolkit()
    human_toolkit.set_task_state(task_state)

    tools = [
        *[_extract_callable(t) for t in note_toolkit.get_tools()],
        *[_extract_callable(t) for t in search_toolkit.get_tools()],
        *[_extract_callable(t) for t in human_toolkit.get_tools()],
    ]

    # Add memory toolkit if configured
    if memory_api_base_url and ami_api_key and user_id:
        memory_toolkit = MemoryToolkit(
            memory_api_base_url=memory_api_base_url,
            ami_api_key=ami_api_key,
            user_id=user_id,
        )
        memory_toolkit.set_task_state(task_state)
        tools.extend([_extract_callable(t) for t in memory_toolkit.get_tools()])
        logger.info("[OrchestratorAgent] MemoryToolkit added")

    # Create and add decompose_task tool
    decompose_tool = DecomposeTaskTool(
        callback=decompose_callback or (lambda x: x)
    )
    # Set toolkit name for SSE event display
    decompose_tool.decompose_task.__func__._toolkit_name = "orchestrator"
    tools.append(decompose_tool.decompose_task)
    logger.info("[OrchestratorAgent] DecomposeTaskTool added")

    # Build system prompt
    system_message = ORCHESTRATOR_SYSTEM_PROMPT.format(
        platform_system=platform.system(),
        platform_machine=platform.machine(),
        working_directory=working_directory,
        now_str=_get_now_str(),
    )

    # Create model configuration
    model_config = None
    if llm_api_key and llm_model:
        model_config = create_model_backend(
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
        )

    # Create the agent
    agent = ListenChatAgent(
        task_state=task_state,
        agent_name=agent_name,
        system_message=system_message,
        model=model_config,
        tools=tools,
        agent_id=f"{agent_name}_{task_id}",
    )

    # Set NoteTakingToolkit reference
    agent.set_note_toolkit(note_toolkit)

    # Set agent reference in toolkits (for memory caching)
    if memory_api_base_url and ami_api_key and user_id:
        memory_toolkit.set_agent(agent)

    logger.info(f"[OrchestratorAgent] Created with {len(tools)} tools (including decompose_task)")
    return agent, decompose_tool


async def run_orchestrator(
    orchestrator: ListenChatAgent,
    decompose_tool: DecomposeTaskTool,
    user_message: str,
    max_iterations: int = MAX_ORCHESTRATOR_ITERATIONS,
) -> str:
    """
    Run the Orchestrator Agent until it completes or calls decompose_task.

    This function implements a complete execution loop similar to ChatAgent.run(),
    allowing the Orchestrator to make multiple tool calls before producing a final
    response.

    The loop terminates when:
    1. LLM produces a response without tool calls (task complete)
    2. decompose_task is called (hand off to Workforce)
    3. Max iterations reached (safety limit)

    Args:
        orchestrator: The Orchestrator ListenChatAgent instance
        decompose_tool: The DecomposeTaskTool to monitor for triggers
        user_message: The user's input message
        max_iterations: Maximum tool-use iterations (default 20)

    Returns:
        The Orchestrator's final response content
    """
    logger.info(f"[OrchestratorAgent] Starting execution for: {user_message[:100]}...")

    # Reset decompose_tool state
    decompose_tool.reset()

    # First step with user message
    response = await orchestrator.astep(user_message)
    final_content = response.msg.content if response.msg else ""

    # Log LLM response details for debugging
    tool_calls = response.info.get("tool_calls") or []
    logger.info(f"[OrchestratorAgent] LLM response content: {final_content[:300] if final_content else '(empty)'}")
    logger.info(f"[OrchestratorAgent] LLM tool_calls: {[tc.func_name if hasattr(tc, 'func_name') else str(tc) for tc in tool_calls]}")

    iteration = 1
    while iteration < max_iterations:
        # Check if decompose_task was called
        if decompose_tool.triggered:
            logger.info(f"[OrchestratorAgent] decompose_task triggered at iteration {iteration}")
            break

        # Check if there are pending tool calls
        # CAMEL's ChatAgent returns tool_calls in info when tools were executed
        tool_calls = response.info.get("tool_calls") or []

        # If no tool calls or LLM already gave a final response, we're done
        if not tool_calls:
            logger.info(f"[OrchestratorAgent] Completed at iteration {iteration} (no tool calls)")
            break

        # CAMEL ChatAgent handles tool execution internally during astep.
        # After tool execution, we need to continue the conversation.
        # Use a continuation prompt to let the agent process tool results.
        iteration += 1
        logger.debug(f"[OrchestratorAgent] Iteration {iteration}, continuing after tool execution")

        # Continue with a prompt that asks the agent to proceed
        response = await orchestrator.astep("Continue based on the tool results above.")

        # Accumulate content
        if response.msg and response.msg.content:
            final_content = response.msg.content

    if iteration >= max_iterations:
        logger.warning(f"[OrchestratorAgent] Reached max iterations ({max_iterations})")

    logger.info(f"[OrchestratorAgent] Final response: {final_content[:200]}...")

    return final_content
