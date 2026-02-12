"""
Orchestrator Agent - Top-level coordinator that decides how to handle user requests.

The Orchestrator Agent replaces the hardcoded question_confirm classification with
an LLM-powered decision system. It has access to:
- Basic tools (search, browse_url, file operations, terminal)
- A special `decompose_task` tool to trigger Workforce for complex tasks
- An `attach_file` tool to include file references in responses

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
import os
import platform
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .ami_agent import AMIAgent
from .ami_tool import AMITool
from .agent_factories import create_provider, _get_now_str
from ..workspace import WorkingDirectoryManager

if TYPE_CHECKING:
    from ..events import SSEEmitter

logger = logging.getLogger(__name__)

# Maximum iterations for Orchestrator's tool-use loop
MAX_ORCHESTRATOR_ITERATIONS = 20


# Orchestrator System Prompt
ORCHESTRATOR_SYSTEM_PROMPT = """\
You are AMI, a coordinator in a multi-agent system.

## Your Role
You are the first point of contact for user requests. You can:
- Answer simple questions directly or with tools
- Use terminal commands to explore user's files and help them find past work
- Delegate complex work (browsing websites, writing code, creating documents) to your team via `decompose_task`

## Your Team
- **Browser Agent**: Browse websites, click buttons, fill forms, extract content, take screenshots, multi-page navigation
- **Developer Agent**: Write Python/JS code, execute scripts, build applications, automate tasks
- **Document Agent**: Create Word documents, Excel spreadsheets, PowerPoint presentations, PDF reports
- **Social Agent**: Send emails (Gmail), manage calendar, post to social media, access Notion

## Environment
- System: {platform_system} ({platform_machine})
- Current Date: {now_str}

## User's Workspace
Task files location: `{user_workspace}`

Structure: `{{task_id}}/workspace/` - each task folder contains output files (reports, documents, data, etc.)

## Your Tools
- shell_exec: Execute terminal commands to explore user's files
- search_google: Quick web search for simple questions (weather, facts, etc.) - reply directly with search results, do NOT use decompose_task
- ask_human: Ask user for clarification
- attach_file: Attach a file to your response (user can click to open/preview it)
- decompose_task: Delegate work to your team (ONLY for tasks that require interacting with websites, writing code, or creating documents)

## Important Guidelines
When user asks to find files or past work:
1. Use shell_exec to locate the files
2. Use attach_file to attach found files to your response
3. Do NOT copy files to Desktop - just attach them directly

Example workflow:
- User: "帮我找到昨天的报告"
- You: shell_exec to find the report file
- You: attach_file to attach the found file
- You: "找到了您昨天的报告，请点击下方文件查看"

## Language Policy
**CRITICAL**: You MUST respond in the same language as the user's input.
- If the user writes in Chinese, respond in Chinese.
- If the user writes in English, respond in English.
- This applies to ALL your responses and outputs.
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
                - Copy the user's original wording as closely as possible
                - Do NOT rephrase, translate, or substitute any keywords
                - Do NOT add requirements the user didn't mention
                - Do NOT specify output formats unless user asked
                - Do NOT add "suggested steps" or implementation details

        Returns:
            Confirmation that the task has been queued for execution.
        """
        if self._triggered:
            return (
                "Task already delegated and is being executed. "
                "Do NOT call decompose_task again. "
                "Summarize your plan to the user and stop."
            )

        self._triggered = True
        self._task_description = task_description
        logger.info(f"[DecomposeTaskTool] Triggered with: {task_description[:100]}...")

        return (
            "Task delegated successfully. The team will now execute this task. "
            "Summarize what you plan to do for the user."
        )


class AttachFileTool:
    """
    Tool for attaching files to Orchestrator's response.

    When the Orchestrator finds files that the user requested, it can use this
    tool to attach them to the response. The frontend will display these as
    clickable file cards with previews.
    """

    def __init__(self):
        """Initialize AttachFileTool."""
        self._attached_files: List[str] = []

    @property
    def attached_files(self) -> List[str]:
        """Get list of attached file paths."""
        return self._attached_files

    def reset(self) -> None:
        """Reset attached files list."""
        self._attached_files = []

    def attach_file(self, file_path: str) -> str:
        """
        Attach a file to your response so user can view/open it directly.

        Use this when you find a file the user asked for. The file will appear
        as a clickable card in the chat - user can preview or open it.

        Args:
            file_path: Absolute path to the file to attach.
                      Must be an existing file or directory.

        Returns:
            Confirmation message.
        """
        # Expand user home directory
        expanded_path = os.path.expanduser(file_path)

        # Validate file exists
        if not os.path.exists(expanded_path):
            return f"Error: File not found: {file_path}"

        # Store absolute path
        abs_path = os.path.abspath(expanded_path)

        # Avoid duplicates
        if abs_path not in self._attached_files:
            self._attached_files.append(abs_path)
            logger.info(f"[AttachFileTool] Attached: {abs_path}")

        file_type = "folder" if os.path.isdir(abs_path) else "file"
        return f"Successfully attached {file_type}: {os.path.basename(abs_path)}"


async def create_orchestrator_agent(
    task_state: Any,
    task_id: str,
    working_directory: str,
    browser_data_directory: Optional[str] = None,
    headless: bool = False,
    memory_api_base_url: Optional[str] = None,
    ami_api_key: Optional[str] = None,
    user_id: Optional[str] = None,
    llm_api_key: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    decompose_callback: Optional[Callable[[str], Any]] = None,
) -> tuple[AMIAgent, DecomposeTaskTool, AttachFileTool]:
    """
    Create the Orchestrator Agent with all basic toolkits and decompose_task.

    Args:
        task_state: TaskState for SSE event emission
        task_id: Task identifier (used as session_id for browser)
        working_directory: Directory for current task (passed to decompose_task/Workforce)
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
        Tuple of (AMIAgent, DecomposeTaskTool, AttachFileTool)
    """
    logger.info(f"[OrchestratorAgent] Creating for task {task_id}")
    logger.info(f"[OrchestratorAgent] Working directory: {working_directory}")

    agent_name = "orchestrator_agent"

    # Determine user workspace root (for Orchestrator to explore all user files)
    user_workspace = str(WorkingDirectoryManager.USERS_DIR / (user_id or "default") / "projects" / "default" / "tasks")
    logger.info(f"[OrchestratorAgent] User workspace: {user_workspace}")

    # Lazy import to avoid circular dependency (toolkits -> base_toolkit -> ami_tool -> core/__init__ -> orchestrator_agent)
    from ..tools.toolkits import (
        SearchToolkit,
        HumanToolkit,
        MemoryToolkit,
        TerminalToolkit,
    )

    # Initialize toolkits
    search_toolkit = SearchToolkit()
    search_toolkit.set_task_state(task_state)

    human_toolkit = HumanToolkit()
    human_toolkit.set_task_state(task_state)

    # Terminal toolkit for Orchestrator - uses user workspace root (not task workspace)
    terminal_toolkit = TerminalToolkit(working_directory=user_workspace)
    terminal_toolkit.set_task_state(task_state)
    logger.info("[OrchestratorAgent] TerminalToolkit added (user workspace root)")

    tools = [
        *search_toolkit.get_tools(),
        *human_toolkit.get_tools(),
        *terminal_toolkit.get_tools(),
    ]

    # Add memory toolkit if configured
    if memory_api_base_url and ami_api_key and user_id:
        memory_toolkit = MemoryToolkit(
            memory_api_base_url=memory_api_base_url,
            ami_api_key=ami_api_key,
            user_id=user_id,
        )
        memory_toolkit.set_task_state(task_state)
        tools.extend(memory_toolkit.get_tools())
        logger.info("[OrchestratorAgent] MemoryToolkit added")

    # Create and add decompose_task tool (wrap bound method in AMITool)
    decompose_tool = DecomposeTaskTool(
        callback=decompose_callback or (lambda x: x)
    )
    decompose_ami_tool = AMITool(decompose_tool.decompose_task)
    decompose_ami_tool._toolkit_name = "Orchestrator"
    tools.append(decompose_ami_tool)
    logger.info("[OrchestratorAgent] DecomposeTaskTool added")

    # Create and add attach_file tool
    attach_tool = AttachFileTool()
    attach_ami_tool = AMITool(attach_tool.attach_file)
    attach_ami_tool._toolkit_name = "Orchestrator"
    tools.append(attach_ami_tool)
    logger.info("[OrchestratorAgent] AttachFileTool added")

    # Build system prompt
    system_message = ORCHESTRATOR_SYSTEM_PROMPT.format(
        platform_system=platform.system(),
        platform_machine=platform.machine(),
        user_workspace=user_workspace,
        now_str=_get_now_str(),
    )

    # Create provider
    provider = create_provider(
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
    )

    # Create the agent
    agent = AMIAgent(
        task_state=task_state,
        agent_name=agent_name,
        provider=provider,
        system_prompt=system_message,
        tools=tools,
    )

    # Set agent reference in toolkits (for memory caching)
    if memory_api_base_url and ami_api_key and user_id:
        memory_toolkit.set_agent(agent)

    logger.info(f"[OrchestratorAgent] Created with {len(tools)} tools (including decompose_task, attach_file)")
    return agent, decompose_tool, attach_tool


async def run_orchestrator(
    orchestrator: AMIAgent,
    decompose_tool: DecomposeTaskTool,
    attach_tool: AttachFileTool,
    user_message: str,
    max_iterations: int = MAX_ORCHESTRATOR_ITERATIONS,
) -> tuple[str, List[str]]:
    """
    Run the Orchestrator Agent until it completes or calls decompose_task.

    AMIAgent.astep() handles multi-turn tool execution internally.
    We just need to call it once and check if decompose_task was triggered.

    Args:
        orchestrator: The Orchestrator AMIAgent instance
        decompose_tool: The DecomposeTaskTool to monitor for triggers
        attach_tool: The AttachFileTool to collect attached files
        user_message: The user's input message
        max_iterations: Unused (kept for API compatibility)

    Returns:
        Tuple of (final_content, attached_file_paths)
    """
    logger.info(f"[OrchestratorAgent] Starting execution for: {user_message[:100]}...")

    # Reset tool states
    decompose_tool.reset()
    attach_tool.reset()

    # Single call to astep — handles multi-turn tool execution internally
    response = await orchestrator.astep(user_message)
    final_content = response.text

    # Log response
    logger.info(
        f"[OrchestratorAgent] Completed: content={final_content[:100] if final_content else '(empty)'}, "
        f"tool_calls={len(response.tool_calls)}, decompose_triggered={decompose_tool.triggered}"
    )

    attached_files = attach_tool.attached_files
    logger.info(f"[OrchestratorAgent] Final response: {final_content[:200]}... | Attached files: {len(attached_files)}")

    return final_content, attached_files
