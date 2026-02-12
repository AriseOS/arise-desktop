"""
Toolkits for Agent System.

Ported from CAMEL-AI/Eigent project to provide tool-calling capabilities.
These toolkits enable agents to use function calling with Anthropic's tool_use API.

Core Toolkits:
- SearchToolkit: Web search (Google API or DuckDuckGo fallback)
- TerminalToolkit: Shell command execution with safety controls
- HumanToolkit: Human-in-the-loop interaction
- BrowserToolkit: Browser automation (click, type, navigate, etc.)
- MemoryToolkit: Query memory system for task guidance
- TaskPlanningToolkit: Task decomposition and re-planning (from CAMEL)

Document Toolkits (for DocumentAgent):
- FileToolkit: File reading and writing (txt, md, html, json, csv, docx, pdf)
- PPTXToolkit: PowerPoint presentation creation
- ExcelToolkit: Excel spreadsheet operations
- MarkItDownToolkit: Document reading and conversion to markdown

Multi-Modal Toolkits (for MultiModalAgent):
- VideoDownloaderToolkit: Video download from YouTube, Vimeo, etc. (uses yt-dlp)
- ImageAnalysisToolkit: Image analysis using vision models
- AudioAnalysisToolkit: Audio transcription and question answering
- ImageGenerationToolkit: Image generation using DALL-E and other models

MCP-based Toolkits (for SocialMediumAgent and others):
- GmailMCPToolkit: Gmail via MCP server (@gongrzhe/server-gmail-autoauth-mcp)
- GoogleDriveMCPToolkit: Google Drive via MCP (@modelcontextprotocol/server-gdrive)
- NotionMCPToolkit: Notion via remote MCP (https://mcp.notion.com/mcp)

Direct API Toolkits:
- GoogleCalendarToolkit: Google Calendar via direct API
"""

from .base_toolkit import BaseToolkit, FunctionTool
from .search_toolkit import SearchToolkit
from .terminal_toolkit import TerminalToolkit
from .human_toolkit import HumanToolkit
from .browser_toolkit import BrowserToolkit
from .memory_toolkit import MemoryToolkit
from .task_planning_toolkit import TaskPlanningToolkit
from .replan_toolkit import ReplanToolkit
# Document toolkits (for DocumentAgent)
from .file_toolkit import FileToolkit
from .pptx_toolkit import PPTXToolkit
from .excel_toolkit import ExcelToolkit
from .markitdown_toolkit import MarkItDownToolkit

# Multi-modal toolkits (for MultiModalAgent)
from .video_downloader_toolkit import VideoDownloaderToolkit
from .image_analysis_toolkit import ImageAnalysisToolkit
from .audio_analysis_toolkit import AudioAnalysisToolkit
from .image_generation_toolkit import ImageGenerationToolkit

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

    # Core toolkits
    "SearchToolkit",
    "TerminalToolkit",
    "HumanToolkit",
    "BrowserToolkit",
    "MemoryToolkit",

    # Task planning
    "TaskPlanningToolkit",
    "ReplanToolkit",

    # Document toolkits (for DocumentAgent)
    "FileToolkit",
    "PPTXToolkit",
    "ExcelToolkit",
    "MarkItDownToolkit",

    # Multi-modal toolkits (for MultiModalAgent)
    "VideoDownloaderToolkit",
    "ImageAnalysisToolkit",
    "AudioAnalysisToolkit",
    "ImageGenerationToolkit",

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
