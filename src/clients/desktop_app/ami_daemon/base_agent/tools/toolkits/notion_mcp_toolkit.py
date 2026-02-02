"""
Notion MCP Toolkit

Notion integration via remote MCP server (https://mcp.notion.com/mcp).
Based on Eigent's NotionMCPToolkit implementation.

Unlike Gmail and GDrive which use local npx-based MCP servers,
Notion uses a remote HTTP-based MCP server provided by Notion.

References:
- Notion MCP: https://www.notion.so/help/guides/connecting-notion-to-claude
- Eigent: third-party/eigent/backend/app/utils/toolkit/notion_mcp_toolkit.py
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

from .mcp_base import BaseMCPToolkit, MCPTool
from .base_toolkit import FunctionTool

logger = logging.getLogger(__name__)


class NotionMCPToolkit(BaseMCPToolkit):
    """Notion integration via remote MCP server.

    Provides Notion operations:
    - Search pages and databases
    - Get page content
    - Create pages
    - Update pages
    - Query databases

    Requires:
    - Internet access to Notion MCP server
    - Notion workspace authentication (handled by MCP server)
    - Optional: MCP_REMOTE_CONFIG_DIR for configuration

    Usage:
        toolkit = NotionMCPToolkit()
        await toolkit.initialize()

        # Search Notion
        results = await toolkit.search("meeting notes")

        # Get page content
        page = await toolkit.get_page("page-id-xxx")

        # Create page
        new_page = await toolkit.create_page(
            parent_id="parent-page-id",
            title="New Page",
            content="Page content here"
        )
    """

    MCP_URL = "https://mcp.notion.com/mcp"

    def __init__(
        self,
        config_dir: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """Initialize Notion MCP toolkit.

        Args:
            config_dir: MCP configuration directory.
                Defaults to MCP_REMOTE_CONFIG_DIR env var or ~/.config/mcp.
            timeout: Operation timeout in seconds.
            max_retries: Maximum connection retry attempts.
        """
        self.config_dir = config_dir or os.getenv(
            "MCP_REMOTE_CONFIG_DIR",
            os.path.expanduser("~/.config/mcp")
        )
        self.max_retries = max_retries

        # Initialize with remote URL (no args for HTTP servers)
        super().__init__(
            command_or_url=self.MCP_URL,
            args=None,
            timeout=timeout,
        )

        self._function_tools: List[FunctionTool] = []

    async def initialize(self) -> bool:
        """Initialize toolkit with retry logic.

        Implements exponential backoff for connection failures.

        Returns:
            True if successful

        Raises:
            ConnectionError: If all retry attempts fail
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                result = await super().initialize()

                # Build FunctionTool wrappers for LLM integration
                self._build_function_tools()

                logger.info(
                    f"Notion MCP toolkit initialized with {len(self._function_tools)} tools "
                    f"(attempt {attempt + 1})"
                )
                return result

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Notion MCP connection attempt {attempt + 1}/{self.max_retries} failed: {e}"
                )

                if attempt < self.max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s, ...
                    wait_time = 2 ** attempt
                    logger.debug(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)

        # All retries failed
        raise ConnectionError(
            f"Failed to connect to Notion MCP after {self.max_retries} attempts: {last_error}"
        )

    def _build_function_tools(self) -> None:
        """Build FunctionTool wrappers for each MCP tool."""
        self._function_tools = []

        for mcp_tool in self.get_tools():
            # Create wrapper function
            tool_name = mcp_tool.name

            async def tool_executor(
                _tool_name: str = tool_name,
                **kwargs
            ) -> Any:
                return await self.call_tool(_tool_name, kwargs)

            # Create FunctionTool and configure it
            func_tool = FunctionTool(tool_executor)
            func_tool.set_function_name(mcp_tool.name)
            func_tool.set_function_description(mcp_tool.description)
            # Override parameters with MCP schema
            func_tool.openai_tool_schema["function"]["parameters"] = mcp_tool.input_schema

            self._function_tools.append(func_tool)

    def get_function_tools(self) -> List[FunctionTool]:
        """Get FunctionTool instances for LLM integration.

        Returns:
            List of FunctionTool instances
        """
        return self._function_tools

    # Convenience methods for common operations

    async def search(
        self,
        query: str,
        filter_type: Optional[str] = None,
        sort_direction: str = "descending",
        page_size: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search across Notion workspace.

        Args:
            query: Search query text
            filter_type: Optional filter ("page" or "database")
            sort_direction: Sort direction ("ascending" or "descending")
            page_size: Number of results to return

        Returns:
            List of search results
        """
        args: Dict[str, Any] = {
            "query": query,
            "sort_direction": sort_direction,
            "page_size": page_size,
        }
        if filter_type:
            args["filter"] = {"property": "object", "value": filter_type}

        result = await self.call_tool("notion_search", args)
        return result.get("results", []) if isinstance(result, dict) else []

    async def get_page(self, page_id: str) -> Dict[str, Any]:
        """Get a specific page.

        Args:
            page_id: Notion page ID

        Returns:
            Page content and metadata
        """
        return await self.call_tool("notion_get_page", {
            "page_id": page_id
        })

    async def get_page_content(self, page_id: str) -> List[Dict[str, Any]]:
        """Get block content of a page.

        Args:
            page_id: Notion page ID

        Returns:
            List of block content
        """
        result = await self.call_tool("notion_get_block_children", {
            "block_id": page_id
        })
        return result.get("results", []) if isinstance(result, dict) else []

    async def create_page(
        self,
        parent_id: str,
        title: str,
        content: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        icon: Optional[str] = None,
        cover: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new page.

        Args:
            parent_id: Parent page or database ID
            title: Page title
            content: Optional page content (plain text)
            properties: Optional additional properties
            icon: Optional emoji or icon URL
            cover: Optional cover image URL

        Returns:
            Created page data
        """
        args: Dict[str, Any] = {
            "parent_id": parent_id,
            "title": title,
        }

        if content:
            args["content"] = content
        if properties:
            args["properties"] = properties
        if icon:
            args["icon"] = icon
        if cover:
            args["cover"] = cover

        return await self.call_tool("notion_create_page", args)

    async def update_page(
        self,
        page_id: str,
        properties: Optional[Dict[str, Any]] = None,
        archived: Optional[bool] = None,
        icon: Optional[str] = None,
        cover: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update page properties.

        Args:
            page_id: Notion page ID
            properties: Properties to update
            archived: Set to True to archive the page
            icon: New emoji or icon URL
            cover: New cover image URL

        Returns:
            Updated page data
        """
        args: Dict[str, Any] = {"page_id": page_id}

        if properties:
            args["properties"] = properties
        if archived is not None:
            args["archived"] = archived
        if icon:
            args["icon"] = icon
        if cover:
            args["cover"] = cover

        return await self.call_tool("notion_update_page", args)

    async def append_to_page(
        self,
        page_id: str,
        content: str,
        content_type: str = "paragraph",
    ) -> Dict[str, Any]:
        """Append content to a page.

        Args:
            page_id: Notion page ID
            content: Text content to append
            content_type: Block type ("paragraph", "heading_1", "bulleted_list_item", etc.)

        Returns:
            Result of append operation
        """
        block = {
            content_type: {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": content}
                }]
            }
        }

        return await self.call_tool("notion_append_block_children", {
            "block_id": page_id,
            "children": [block]
        })

    async def query_database(
        self,
        database_id: str,
        filter: Optional[Dict[str, Any]] = None,
        sorts: Optional[List[Dict[str, Any]]] = None,
        page_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query a Notion database.

        Args:
            database_id: Notion database ID
            filter: Filter object in Notion API format
            sorts: Sort specifications
            page_size: Number of results per page

        Returns:
            List of database entries
        """
        args: Dict[str, Any] = {
            "database_id": database_id,
            "page_size": page_size,
        }

        if filter:
            args["filter"] = filter
        if sorts:
            args["sorts"] = sorts

        result = await self.call_tool("notion_query_database", args)
        return result.get("results", []) if isinstance(result, dict) else []

    async def get_database(self, database_id: str) -> Dict[str, Any]:
        """Get database metadata.

        Args:
            database_id: Notion database ID

        Returns:
            Database metadata including schema
        """
        return await self.call_tool("notion_get_database", {
            "database_id": database_id
        })

    async def create_database_entry(
        self,
        database_id: str,
        properties: Dict[str, Any],
        content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new entry in a database.

        Args:
            database_id: Notion database ID
            properties: Entry properties matching database schema
            content: Optional page content for the entry

        Returns:
            Created entry data
        """
        args: Dict[str, Any] = {
            "parent": {"database_id": database_id},
            "properties": properties,
        }

        if content:
            args["content"] = content

        return await self.call_tool("notion_create_page", args)

    async def list_users(self) -> List[Dict[str, Any]]:
        """List users in the workspace.

        Returns:
            List of user objects
        """
        result = await self.call_tool("notion_list_users", {})
        return result.get("results", []) if isinstance(result, dict) else []

    async def get_user(self, user_id: str) -> Dict[str, Any]:
        """Get user details.

        Args:
            user_id: Notion user ID

        Returns:
            User data
        """
        return await self.call_tool("notion_get_user", {
            "user_id": user_id
        })
