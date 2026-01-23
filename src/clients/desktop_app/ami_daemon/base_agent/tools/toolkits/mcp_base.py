"""
MCP Client Base Module

Provides base classes for communicating with MCP (Model Context Protocol) servers.
Based on Eigent's MCP toolkit patterns using CAMEL's MCPToolkit.

MCP allows connecting to external services (Gmail, Drive, Notion) via
standardized server protocol.

References:
- MCP Specification: https://modelcontextprotocol.io/
- Eigent: third-party/eigent/backend/app/utils/toolkit/google_gmail_mcp_toolkit.py
"""

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    """Represents a tool discovered from an MCP server.

    Each MCP server exposes a set of tools that can be called
    to perform operations (e.g., send email, list files).
    """
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)

    def to_anthropic_format(self) -> Dict[str, Any]:
        """Convert to Anthropic tool_use format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def to_openai_format(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            }
        }


class MCPClient:
    """Client for communicating with MCP servers.

    Supports both local (subprocess-based) and remote (HTTP-based) MCP servers.

    Local servers (npx-based):
        client = MCPClient(
            command_or_url="npx",
            args=["-y", "@gongrzhe/server-gmail-autoauth-mcp", "/path/to/creds"]
        )

    Remote servers (HTTP-based):
        client = MCPClient(
            command_or_url="https://mcp.notion.com/mcp"
        )
    """

    def __init__(
        self,
        command_or_url: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        working_dir: Optional[str] = None,
    ):
        """Initialize MCP client.

        Args:
            command_or_url: Command (for local) or URL (for remote) to connect
            args: Arguments for the command (local servers only)
            env: Additional environment variables
            timeout: Timeout in seconds for operations
            working_dir: Working directory for local server process
        """
        self.command_or_url = command_or_url
        self.args = args or []
        self.env = env or {}
        self.timeout = timeout
        self.working_dir = working_dir

        self._process: Optional[subprocess.Popen] = None
        self._tools: List[MCPTool] = []
        self._connected = False
        self._request_id = 0

        # For remote servers
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected

    @property
    def is_remote(self) -> bool:
        """Check if this is a remote MCP server."""
        return self.command_or_url.startswith("http")

    async def connect(self) -> bool:
        """Connect to MCP server and discover tools.

        Returns:
            True if connection successful
        """
        try:
            if self.is_remote:
                await self._connect_remote()
            else:
                await self._connect_local()

            self._connected = True
            logger.info(f"Connected to MCP server, discovered {len(self._tools)} tools")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            self._connected = False
            raise

    async def _connect_local(self) -> None:
        """Connect to local MCP server via subprocess."""
        cmd = [self.command_or_url] + self.args

        # Merge environment
        process_env = os.environ.copy()
        process_env.update(self.env)

        logger.debug(f"Starting local MCP server: {' '.join(cmd)}")

        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=process_env,
            cwd=self.working_dir,
        )

        # Wait for server to be ready (read initial output)
        await asyncio.sleep(0.5)

        # Send initialize request
        response = await self._send_jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "ami-mcp-client",
                "version": "1.0.0"
            }
        })

        # List tools
        tools_response = await self._send_jsonrpc("tools/list", {})
        self._tools = self._parse_tools(tools_response.get("tools", []))

    async def _connect_remote(self) -> None:
        """Connect to remote MCP server via HTTP."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )

        # Initialize connection
        async with self._session.post(
            f"{self.command_or_url}/initialize",
            json={
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "ami-mcp-client",
                    "version": "1.0.0"
                }
            }
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise ConnectionError(f"MCP initialize failed: {resp.status} - {text}")
            await resp.json()

        # List tools
        async with self._session.post(
            f"{self.command_or_url}/tools/list",
            json={}
        ) as resp:
            if resp.status != 200:
                raise ConnectionError(f"MCP tools/list failed: {resp.status}")
            data = await resp.json()
            self._tools = self._parse_tools(data.get("tools", []))

    async def _send_jsonrpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send JSON-RPC request to local MCP server.

        Args:
            method: RPC method name
            params: Method parameters

        Returns:
            Response data
        """
        if not self._process:
            raise RuntimeError("MCP server not started")

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params
        }

        # Write request
        request_bytes = (json.dumps(request) + "\n").encode()
        self._process.stdin.write(request_bytes)
        self._process.stdin.flush()

        # Read response (with timeout)
        try:
            response_line = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    self._process.stdout.readline
                ),
                timeout=self.timeout
            )
            response = json.loads(response_line.decode())

            if "error" in response:
                raise RuntimeError(f"MCP error: {response['error']}")

            return response.get("result", {})

        except asyncio.TimeoutError:
            raise TimeoutError(f"MCP request timed out after {self.timeout}s")

    def _parse_tools(self, tools_data: List[Dict[str, Any]]) -> List[MCPTool]:
        """Parse tools from MCP server response.

        Args:
            tools_data: List of tool definitions from server

        Returns:
            List of MCPTool instances
        """
        tools = []
        for tool_data in tools_data:
            tools.append(MCPTool(
                name=tool_data.get("name", ""),
                description=tool_data.get("description", ""),
                input_schema=tool_data.get("inputSchema", {})
            ))
        return tools

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """Call a tool on the MCP server.

        Args:
            tool_name: Name of the tool to call
            arguments: Arguments for the tool

        Returns:
            Tool execution result
        """
        if not self._connected:
            raise RuntimeError("MCP client not connected")

        if self.is_remote:
            return await self._call_tool_remote(tool_name, arguments)
        else:
            return await self._call_tool_local(tool_name, arguments)

    async def _call_tool_local(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """Call tool on local MCP server."""
        response = await self._send_jsonrpc("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        return response.get("content", response)

    async def _call_tool_remote(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """Call tool on remote MCP server."""
        if not self._session:
            raise RuntimeError("HTTP session not initialized")

        async with self._session.post(
            f"{self.command_or_url}/tools/call",
            json={
                "name": tool_name,
                "arguments": arguments
            }
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"MCP tool call failed: {resp.status} - {text}")
            data = await resp.json()
            return data.get("content", data)

    def get_tools(self) -> List[MCPTool]:
        """Get list of available tools.

        Returns:
            List of MCPTool instances
        """
        return self._tools

    def get_tool(self, name: str) -> Optional[MCPTool]:
        """Get a specific tool by name.

        Args:
            name: Tool name

        Returns:
            MCPTool if found, None otherwise
        """
        for tool in self._tools:
            if tool.name == name:
                return tool
        return None

    async def close(self) -> None:
        """Close connection to MCP server."""
        self._connected = False

        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception as e:
                logger.warning(f"Error terminating MCP process: {e}")
            self._process = None

        if self._session:
            await self._session.close()
            self._session = None

        logger.debug("MCP client closed")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


class BaseMCPToolkit:
    """Base class for MCP-based toolkits.

    Provides common functionality for Gmail, GDrive, Notion toolkits.
    """

    def __init__(
        self,
        command_or_url: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: int = 30,
    ):
        """Initialize toolkit.

        Args:
            command_or_url: MCP server command or URL
            args: Server arguments
            env: Environment variables
            timeout: Operation timeout
        """
        self._client = MCPClient(
            command_or_url=command_or_url,
            args=args,
            env=env,
            timeout=timeout
        )
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        """Check if toolkit is initialized."""
        return self._initialized

    async def initialize(self) -> bool:
        """Initialize the toolkit by connecting to MCP server.

        Returns:
            True if successful
        """
        if self._initialized:
            return True

        await self._client.connect()
        self._initialized = True
        return True

    def get_tools(self) -> List[MCPTool]:
        """Get available tools.

        Returns:
            List of MCPTool instances
        """
        return self._client.get_tools()

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """Call a tool on the MCP server.

        Args:
            tool_name: Name of the tool
            arguments: Tool arguments

        Returns:
            Tool result
        """
        if not self._initialized:
            raise RuntimeError("Toolkit not initialized, call initialize() first")
        return await self._client.call_tool(tool_name, arguments)

    async def close(self) -> None:
        """Close the toolkit connection."""
        await self._client.close()
        self._initialized = False

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
