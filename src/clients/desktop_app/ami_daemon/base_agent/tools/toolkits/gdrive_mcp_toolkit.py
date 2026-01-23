"""
Google Drive MCP Toolkit

Google Drive integration via MCP server (@modelcontextprotocol/server-gdrive).
Based on Eigent's GoogleDriveMCPToolkit implementation.

References:
- MCP Server: https://www.npmjs.com/package/@modelcontextprotocol/server-gdrive
- Eigent: third-party/eigent/backend/app/utils/toolkit/google_drive_mcp_toolkit.py
"""

import logging
import os
from typing import Any, Dict, List, Optional

from .mcp_base import BaseMCPToolkit, MCPTool
from .base_toolkit import FunctionTool

logger = logging.getLogger(__name__)


class GoogleDriveMCPToolkit(BaseMCPToolkit):
    """Google Drive integration via MCP server.

    Provides file operations:
    - List files in folders
    - Read file content
    - Create files
    - Update files
    - Delete files
    - Search files

    Requires:
    - npx installed
    - GDRIVE_CREDENTIALS_PATH environment variable set
    - OAuth credentials JSON file with Drive API access

    Usage:
        toolkit = GoogleDriveMCPToolkit()
        await toolkit.initialize()

        # List files
        files = await toolkit.list_files(folder_id="root")

        # Create document
        result = await toolkit.create_file(
            name="notes.txt",
            content="My notes",
            folder_id="root"
        )
    """

    MCP_PACKAGE = "@modelcontextprotocol/server-gdrive"

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        timeout: int = 60,
    ):
        """Initialize Google Drive MCP toolkit.

        Args:
            credentials_path: Path to OAuth credentials JSON.
                Defaults to GDRIVE_CREDENTIALS_PATH env var.
            timeout: Operation timeout in seconds.
        """
        self.credentials_path = credentials_path or os.getenv("GDRIVE_CREDENTIALS_PATH")

        if not self.credentials_path:
            raise ValueError(
                "Google Drive credentials path not provided. "
                "Set GDRIVE_CREDENTIALS_PATH environment variable or pass credentials_path."
            )

        if not os.path.exists(self.credentials_path):
            raise FileNotFoundError(
                f"Google Drive credentials file not found: {self.credentials_path}"
            )

        super().__init__(
            command_or_url="npx",
            args=["-y", self.MCP_PACKAGE, self.credentials_path],
            timeout=timeout,
        )

        self._function_tools: List[FunctionTool] = []

    async def initialize(self) -> bool:
        """Initialize toolkit and build FunctionTool wrappers.

        Returns:
            True if successful
        """
        result = await super().initialize()

        # Build FunctionTool wrappers for LLM integration
        self._build_function_tools()

        logger.info(f"Google Drive MCP toolkit initialized with {len(self._function_tools)} tools")
        return result

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

            # Create FunctionTool with proper schema
            func_tool = FunctionTool(
                func=tool_executor,
                name=mcp_tool.name,
                description=mcp_tool.description,
            )
            # Override parameters with MCP schema
            func_tool.parameters = mcp_tool.input_schema

            self._function_tools.append(func_tool)

    def get_function_tools(self) -> List[FunctionTool]:
        """Get FunctionTool instances for LLM integration.

        Returns:
            List of FunctionTool instances
        """
        return self._function_tools

    # Convenience methods for common operations

    async def list_files(
        self,
        folder_id: str = "root",
        query: Optional[str] = None,
        max_results: int = 100,
    ) -> List[Dict[str, Any]]:
        """List files in a folder.

        Args:
            folder_id: Google Drive folder ID (default: root)
            query: Optional search query (Drive query format)
            max_results: Maximum number of results to return

        Returns:
            List of file metadata dictionaries
        """
        args: Dict[str, Any] = {
            "folder_id": folder_id,
            "max_results": max_results,
        }
        if query:
            args["query"] = query

        result = await self.call_tool("gdrive_list_files", args)
        return result if isinstance(result, list) else []

    async def read_file(self, file_id: str) -> str:
        """Read file content.

        Args:
            file_id: Google Drive file ID

        Returns:
            File content as string
        """
        result = await self.call_tool("gdrive_read_file", {
            "file_id": file_id
        })
        return result if isinstance(result, str) else str(result)

    async def create_file(
        self,
        name: str,
        content: str,
        folder_id: str = "root",
        mime_type: str = "text/plain",
    ) -> Dict[str, Any]:
        """Create a new file in Google Drive.

        Args:
            name: File name
            content: File content
            folder_id: Parent folder ID (default: root)
            mime_type: MIME type of the file

        Returns:
            Created file metadata
        """
        return await self.call_tool("gdrive_create_file", {
            "name": name,
            "content": content,
            "folder_id": folder_id,
            "mime_type": mime_type,
        })

    async def update_file(
        self,
        file_id: str,
        content: str,
        new_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an existing file.

        Args:
            file_id: Google Drive file ID
            content: New file content
            new_name: Optional new name for the file

        Returns:
            Updated file metadata
        """
        args: Dict[str, Any] = {
            "file_id": file_id,
            "content": content,
        }
        if new_name:
            args["name"] = new_name

        return await self.call_tool("gdrive_update_file", args)

    async def delete_file(self, file_id: str) -> Dict[str, Any]:
        """Delete a file from Google Drive.

        Args:
            file_id: Google Drive file ID

        Returns:
            Result dictionary
        """
        return await self.call_tool("gdrive_delete_file", {
            "file_id": file_id
        })

    async def search(
        self,
        query: str,
        max_results: int = 50,
    ) -> List[Dict[str, Any]]:
        """Search for files in Google Drive.

        Args:
            query: Search query (supports Drive query format)
            max_results: Maximum number of results

        Returns:
            List of matching file metadata
        """
        result = await self.call_tool("gdrive_search", {
            "query": query,
            "max_results": max_results,
        })
        return result if isinstance(result, list) else []

    async def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """Get metadata for a specific file.

        Args:
            file_id: Google Drive file ID

        Returns:
            File metadata dictionary
        """
        return await self.call_tool("gdrive_get_file", {
            "file_id": file_id
        })

    async def create_folder(
        self,
        name: str,
        parent_id: str = "root",
    ) -> Dict[str, Any]:
        """Create a new folder in Google Drive.

        Args:
            name: Folder name
            parent_id: Parent folder ID (default: root)

        Returns:
            Created folder metadata
        """
        return await self.call_tool("gdrive_create_folder", {
            "name": name,
            "parent_id": parent_id,
        })

    async def move_file(
        self,
        file_id: str,
        new_parent_id: str,
    ) -> Dict[str, Any]:
        """Move a file to a different folder.

        Args:
            file_id: Google Drive file ID
            new_parent_id: Destination folder ID

        Returns:
            Updated file metadata
        """
        return await self.call_tool("gdrive_move_file", {
            "file_id": file_id,
            "new_parent_id": new_parent_id,
        })

    async def copy_file(
        self,
        file_id: str,
        new_name: Optional[str] = None,
        folder_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Copy a file.

        Args:
            file_id: Source file ID
            new_name: Optional name for the copy
            folder_id: Optional destination folder ID

        Returns:
            Copied file metadata
        """
        args: Dict[str, Any] = {"file_id": file_id}
        if new_name:
            args["name"] = new_name
        if folder_id:
            args["folder_id"] = folder_id

        return await self.call_tool("gdrive_copy_file", args)
