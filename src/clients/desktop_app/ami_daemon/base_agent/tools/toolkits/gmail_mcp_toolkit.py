"""
Gmail MCP Toolkit

Gmail integration via MCP server (@gongrzhe/server-gmail-autoauth-mcp).
Based on Eigent's GoogleGmailMCPToolkit implementation.

References:
- MCP Server: https://www.npmjs.com/package/@gongrzhe/server-gmail-autoauth-mcp
- Eigent: third-party/eigent/backend/app/utils/toolkit/google_gmail_mcp_toolkit.py
"""

import logging
import os
from typing import Any, Dict, List, Optional

from .mcp_base import BaseMCPToolkit, MCPTool
from .base_toolkit import FunctionTool

logger = logging.getLogger(__name__)


class GmailMCPToolkit(BaseMCPToolkit):
    """Gmail integration via MCP server.

    Provides email operations:
    - Send emails
    - Search emails
    - Read emails
    - Manage labels

    Requires:
    - npx installed
    - GMAIL_CREDENTIALS_PATH environment variable set
    - OAuth credentials JSON file with Gmail API access

    Usage:
        toolkit = GmailMCPToolkit()
        await toolkit.initialize()

        # Send email
        result = await toolkit.send_email(
            to="user@example.com",
            subject="Hello",
            body="Message content"
        )

        # Search emails
        emails = await toolkit.search_emails("from:boss@company.com")
    """

    MCP_PACKAGE = "@gongrzhe/server-gmail-autoauth-mcp"

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        timeout: int = 60,
    ):
        """Initialize Gmail MCP toolkit.

        Args:
            credentials_path: Path to OAuth credentials JSON.
                Defaults to GMAIL_CREDENTIALS_PATH env var.
            timeout: Operation timeout in seconds.
        """
        self.credentials_path = credentials_path or os.getenv("GMAIL_CREDENTIALS_PATH")

        if not self.credentials_path:
            raise ValueError(
                "Gmail credentials path not provided. "
                "Set GMAIL_CREDENTIALS_PATH environment variable or pass credentials_path."
            )

        if not os.path.exists(self.credentials_path):
            raise FileNotFoundError(
                f"Gmail credentials file not found: {self.credentials_path}"
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

        logger.info(f"Gmail MCP toolkit initialized with {len(self._function_tools)} tools")
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

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an email.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text or HTML)
            cc: CC recipients (comma-separated)
            bcc: BCC recipients (comma-separated)

        Returns:
            Result dictionary with message ID
        """
        args: Dict[str, Any] = {
            "to": to,
            "subject": subject,
            "body": body,
        }
        if cc:
            args["cc"] = cc
        if bcc:
            args["bcc"] = bcc

        return await self.call_tool("gmail_send_email", args)

    async def search_emails(
        self,
        query: str,
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for emails.

        Args:
            query: Gmail search query (e.g., "from:user@example.com")
            max_results: Maximum number of results to return

        Returns:
            List of email summaries
        """
        result = await self.call_tool("gmail_search", {
            "query": query,
            "max_results": max_results
        })
        return result if isinstance(result, list) else []

    async def read_email(self, email_id: str) -> Dict[str, Any]:
        """Read a specific email.

        Args:
            email_id: Gmail message ID

        Returns:
            Email content and metadata
        """
        return await self.call_tool("gmail_read", {
            "email_id": email_id
        })

    async def list_labels(self) -> List[Dict[str, Any]]:
        """List all Gmail labels.

        Returns:
            List of labels with IDs and names
        """
        result = await self.call_tool("gmail_list_labels", {})
        return result if isinstance(result, list) else []

    async def get_inbox_summary(self, count: int = 5) -> List[Dict[str, Any]]:
        """Get summary of recent inbox emails.

        Args:
            count: Number of recent emails to fetch

        Returns:
            List of email summaries
        """
        return await self.search_emails("in:inbox", max_results=count)

    async def get_unread_count(self) -> int:
        """Get count of unread emails.

        Returns:
            Number of unread emails
        """
        emails = await self.search_emails("is:unread", max_results=100)
        return len(emails)
