"""
Agent Factories - Create configured ListenChatAgent instances for Workforce.

These factory functions create ListenChatAgent instances with the appropriate
toolkits for different agent types (browser, developer, document, etc.).

Modeled after Eigent's agent factory pattern in app/utils/agent.py.
"""

import datetime
import logging
import platform
import uuid
from typing import Any, List, Optional

from camel.toolkits import ToolkitMessageIntegration

from .listen_chat_agent import ListenChatAgent
from .ami_model_backend import AMIModelBackend
from ..tools.toolkits import (
    NoteTakingToolkit,
    SearchToolkit,
    TerminalToolkit,
    HumanToolkit,
    BrowserToolkit,
    MemoryToolkit,
)
from ..workspace import get_working_directory

logger = logging.getLogger(__name__)


def create_model_backend(
    llm_api_key: str,
    llm_model: str,
    llm_base_url: Optional[str] = None,
):
    """
    Create AMI model backend for CAMEL agents.

    Uses AMIModelBackend which wraps AMI's LLM providers to:
    - Route through CRS proxy (api.ariseos.com/api)
    - Use Anthropic SDK with proper API format
    - Integrate with budget tracking

    Args:
        llm_api_key: API key for LLM calls
        llm_model: Model name (e.g., 'claude-sonnet-4-20250514', 'glm-4.7')
        llm_base_url: Base URL for API (CRS proxy URL)

    Returns:
        AMIModelBackend instance configured with API key and model.
    """
    logger.info(f"[AgentFactory] Creating AMI model backend: model={llm_model}, url={llm_base_url}")

    return AMIModelBackend(
        model_type=llm_model,
        api_key=llm_api_key,
        url=llm_base_url,
    )

# System prompt for browser agent
BROWSER_AGENT_SYSTEM_PROMPT = """
<role>
You are a Senior Research Analyst, a key member of a multi-agent team. Your
primary responsibility is to conduct expert-level web research to gather,
analyze, and document information required to solve the user's task. You
operate with precision, efficiency, and a commitment to data quality.
You must use the search/browser tools to get the information you need.
</role>

<environment>
Platform: {platform}
Architecture: {architecture}
Working Directory: {working_directory}
Current Date: {current_date}
</environment>

<capabilities>
- Web browsing and research using browser tools
- Terminal command execution for file operations
- Note-taking and documentation
- Search engine queries
- Human interaction for clarification
</capabilities>

<rules>
1. Always verify information from multiple sources when possible
2. Document your findings using the note-taking tools
3. Use search tools before browsing for general queries
4. Ask for human clarification when instructions are ambiguous
5. Report progress and findings clearly
</rules>
"""


def create_browser_agent(
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
) -> ListenChatAgent:
    """
    Create a configured ListenChatAgent for browser-based research tasks.

    This factory function creates a ListenChatAgent with:
    - BrowserToolkit for web interaction
    - TerminalToolkit for command execution
    - NoteTakingToolkit for documentation
    - SearchToolkit for web search
    - HumanToolkit for user interaction
    - MemoryToolkit (optional) for knowledge retrieval

    Args:
        task_state: TaskState for SSE event emission
        task_id: Task identifier
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

    Returns:
        Configured ListenChatAgent instance
    """
    logger.info(f"[AgentFactory] Creating browser agent for task {task_id}")
    logger.info(f"[AgentFactory] Working directory: {working_directory}")

    agent_name = "browser_agent"
    notes_dir = notes_directory or working_directory

    # Initialize toolkits
    note_toolkit = NoteTakingToolkit(
        notes_directory=notes_dir,
    )
    note_toolkit.set_task_state(task_state)

    search_toolkit = SearchToolkit()
    search_toolkit.set_task_state(task_state)

    terminal_toolkit = TerminalToolkit(
        working_directory=working_directory,
    )
    terminal_toolkit.set_task_state(task_state)

    human_toolkit = HumanToolkit()
    human_toolkit.set_task_state(task_state)

    browser_toolkit = BrowserToolkit()
    browser_toolkit.set_task_state(task_state)
    # Note: headless and browser_data_directory are handled by the session,
    # which is set later by the agent when browser actions are executed

    # Collect tools - extract the underlying callable from our FunctionTool wrappers
    # CAMEL's ChatAgent expects callable functions, not our custom FunctionTool objects
    def extract_callable(tool):
        """Extract callable function from our custom FunctionTool wrapper."""
        if hasattr(tool, 'func'):
            # Our custom FunctionTool - extract the underlying callable
            return tool.func
        # Already a callable or CAMEL FunctionTool
        return tool

    tools = [
        *[extract_callable(t) for t in note_toolkit.get_tools()],
        *[extract_callable(t) for t in search_toolkit.get_tools()],
        *[extract_callable(t) for t in terminal_toolkit.get_tools()],
        *[extract_callable(t) for t in human_toolkit.get_tools()],
        *[extract_callable(t) for t in browser_toolkit.get_tools()],
    ]

    # Add memory toolkit if configured
    if memory_api_base_url and ami_api_key and user_id:
        memory_toolkit = MemoryToolkit(
            memory_api_base_url=memory_api_base_url,
            ami_api_key=ami_api_key,
            user_id=user_id,
        )
        memory_toolkit.set_task_state(task_state)
        tools.extend([extract_callable(t) for t in memory_toolkit.get_tools()])
        logger.info("[AgentFactory] MemoryToolkit added")

    # Build system prompt
    system_message = BROWSER_AGENT_SYSTEM_PROMPT.format(
        platform=platform.system(),
        architecture=platform.machine(),
        working_directory=working_directory,
        current_date=datetime.datetime.now().strftime("%Y-%m-%d"),
    )

    # Create model configuration using shared factory
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
        agent_id=f"{agent_name}_{task_id}_{uuid.uuid4().hex[:8]}",
    )

    logger.info(f"[AgentFactory] Browser agent created with {len(tools)} tools")
    return agent


def create_developer_agent(
    task_state: Any,
    task_id: str,
    working_directory: str,
    llm_api_key: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
) -> ListenChatAgent:
    """
    Create a configured ListenChatAgent for development tasks.

    This is a placeholder for future implementation.
    """
    raise NotImplementedError("Developer agent not yet implemented")


def create_document_agent(
    task_state: Any,
    task_id: str,
    working_directory: str,
    llm_api_key: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
) -> ListenChatAgent:
    """
    Create a configured ListenChatAgent for document creation tasks.

    This is a placeholder for future implementation.
    """
    raise NotImplementedError("Document agent not yet implemented")
