"""
Toolkits for Browser Agent.

Ported from CAMEL-AI/Eigent project to provide tool-calling capabilities.
These toolkits enable the EigentStyleBrowserAgent to use function calling
with Anthropic's tool_use API.

Available Toolkits:
- NoteTakingToolkit: Create and manage markdown notes
- SearchToolkit: Web search (Google API or DuckDuckGo fallback)
- TerminalToolkit: Shell command execution with safety controls
- HumanToolkit: Human-in-the-loop interaction
- BrowserToolkit: Browser automation (click, type, navigate, etc.)
- MemoryToolkit: Query workflow memory for task guidance
- TaskPlanningToolkit: Task decomposition and re-planning (from CAMEL)

MCP-based Toolkits (Eigent migration):
- GmailMCPToolkit: Gmail via MCP server (@gongrzhe/server-gmail-autoauth-mcp)
- GoogleDriveMCPToolkit: Google Drive via MCP (@modelcontextprotocol/server-gdrive)
- NotionMCPToolkit: Notion via remote MCP (https://mcp.notion.com/mcp)

Direct API Toolkits:
- GoogleCalendarToolkit: Google Calendar via direct API
"""

from .base_toolkit import BaseToolkit, FunctionTool
from .note_taking_toolkit import NoteTakingToolkit
from .search_toolkit import SearchToolkit
from .terminal_toolkit import TerminalToolkit
from .human_toolkit import HumanToolkit
from .browser_toolkit import BrowserToolkit
from .memory_toolkit import MemoryToolkit
from .task_planning_toolkit import TaskPlanningToolkit

# MCP base classes and toolkits
from .mcp_base import MCPClient, MCPTool, BaseMCPToolkit
from .gmail_mcp_toolkit import GmailMCPToolkit
from .gdrive_mcp_toolkit import GoogleDriveMCPToolkit
from .notion_mcp_toolkit import NotionMCPToolkit

# Direct API toolkits
from .calendar_toolkit import GoogleCalendarToolkit

__all__ = [
    # Base classes
    "BaseToolkit",
    "FunctionTool",

    # Original toolkits
    "NoteTakingToolkit",
    "SearchToolkit",
    "TerminalToolkit",
    "HumanToolkit",
    "BrowserToolkit",
    "MemoryToolkit",

    # Task planning (uses TaskOrchestrator)
    "TaskPlanningToolkit",

    # MCP base classes
    "MCPClient",
    "MCPTool",
    "BaseMCPToolkit",

    # MCP-based toolkits (Eigent migration)
    "GmailMCPToolkit",
    "GoogleDriveMCPToolkit",
    "NotionMCPToolkit",

    # Direct API toolkits
    "GoogleCalendarToolkit",
]
