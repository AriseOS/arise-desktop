# Google Cloud Services MCP Integration Guide

## Overview

This document describes how to integrate Google Cloud services (Gmail, Drive, Calendar) and Notion via MCP (Model Context Protocol) into the 2ami system, based on Eigent's implementation.

## Eigent's MCP Implementation

### 1. MCP Toolkit Base Architecture

Eigent uses CAMEL's `MCPToolkit` to connect to MCP servers:

```python
# From third-party/eigent/backend/app/utils/toolkit/google_gmail_mcp_toolkit.py

from camel.toolkits import MCPToolkit
from camel.toolkits.base import BaseToolkit

class GoogleGmailMCPToolkit(BaseToolkit):
    """Gmail integration via MCP server."""

    def __init__(self):
        super().__init__()
        credentials_path = os.getenv("GMAIL_CREDENTIALS_PATH")

        # Initialize MCP toolkit with npx command
        self.mcp_toolkit = MCPToolkit(
            command_or_url="npx",
            args=[
                "-y",
                "@gongrzhe/server-gmail-autoauth-mcp",
                credentials_path
            ]
        )

    def get_tools(self):
        return self.mcp_toolkit.get_tools()
```

### 2. Gmail MCP Toolkit

**Server**: `@gongrzhe/server-gmail-autoauth-mcp`

**Environment Variables**:
- `GMAIL_CREDENTIALS_PATH`: Path to Google OAuth credentials JSON

**Features**:
- Send/receive emails
- Search emails
- Manage labels
- Read attachments

```python
# Example usage
gmail_toolkit = GoogleGmailMCPToolkit()
tools = gmail_toolkit.get_tools()

# Tools available:
# - gmail_send_email(to, subject, body)
# - gmail_search(query, max_results)
# - gmail_read(email_id)
# - gmail_list_labels()
```

### 3. Google Drive MCP Toolkit

**Server**: `@modelcontextprotocol/server-gdrive`

**Environment Variables**:
- `GDRIVE_CREDENTIALS_PATH`: Path to Google OAuth credentials JSON

```python
# From third-party/eigent/backend/app/utils/toolkit/google_drive_mcp_toolkit.py

class GoogleDriveMCPToolkit(BaseToolkit):
    def __init__(self):
        super().__init__()
        credentials_path = os.getenv("GDRIVE_CREDENTIALS_PATH")

        self.mcp_toolkit = MCPToolkit(
            command_or_url="npx",
            args=[
                "-y",
                "@modelcontextprotocol/server-gdrive",
                credentials_path
            ]
        )
```

**Tools available**:
- `gdrive_list_files(folder_id, query)`
- `gdrive_read_file(file_id)`
- `gdrive_create_file(name, content, folder_id)`
- `gdrive_update_file(file_id, content)`
- `gdrive_delete_file(file_id)`
- `gdrive_search(query)`

### 4. Notion MCP Toolkit (Remote Server)

**Server**: `https://mcp.notion.com/mcp` (Remote MCP)

```python
# From third-party/eigent/backend/app/utils/toolkit/notion_mcp_toolkit.py

class NotionMCPToolkit(BaseToolkit):
    def __init__(self):
        super().__init__()
        config_dir = os.getenv("MCP_REMOTE_CONFIG_DIR", "~/.config/mcp")

        # Remote MCP connection with retry logic
        self.mcp_toolkit = MCPToolkit(
            command_or_url="https://mcp.notion.com/mcp",
            config_dir=config_dir,
            timeout=30
        )

        # Retry connection (max 3 attempts)
        self._connect_with_retry(max_retries=3)
```

**Tools available**:
- `notion_search(query)`
- `notion_get_page(page_id)`
- `notion_create_page(parent_id, title, content)`
- `notion_update_page(page_id, properties)`
- `notion_query_database(database_id, filter)`

### 5. Google Calendar Toolkit (Direct API)

Unlike the MCP-based toolkits, Calendar uses direct Google API:

```python
# From third-party/eigent/backend/app/utils/toolkit/google_calendar_toolkit.py

class GoogleCalendarToolkit(BaseToolkit):
    def __init__(self, credentials_path: str = None):
        self.credentials_path = credentials_path or os.getenv("GCAL_CREDENTIALS_PATH")
        self.service = self._build_service()

    def _build_service(self):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(self.credentials_path)
        return build('calendar', 'v3', credentials=creds)

    def list_events(self, calendar_id='primary', max_results=10):
        events_result = self.service.events().list(
            calendarId=calendar_id,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        return events_result.get('items', [])

    def create_event(self, summary, start, end, description=''):
        event = {
            'summary': summary,
            'description': description,
            'start': {'dateTime': start},
            'end': {'dateTime': end},
        }
        return self.service.events().insert(
            calendarId='primary',
            body=event
        ).execute()
```

---

## Migration Plan for 2ami

### Phase 1: Create MCP Toolkit Base

Create a unified MCP toolkit interface that doesn't depend on CAMEL:

```python
# src/clients/desktop_app/ami_daemon/base_agent/tools/toolkits/mcp_base.py

import asyncio
import subprocess
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json

@dataclass
class MCPTool:
    """Represents a tool from an MCP server."""
    name: str
    description: str
    input_schema: Dict[str, Any]

class MCPClient:
    """Client for communicating with MCP servers."""

    def __init__(
        self,
        command_or_url: str,
        args: List[str] = None,
        env: Dict[str, str] = None,
        timeout: int = 30
    ):
        self.command_or_url = command_or_url
        self.args = args or []
        self.env = env or {}
        self.timeout = timeout
        self._process: Optional[subprocess.Popen] = None
        self._tools: List[MCPTool] = []

    async def connect(self):
        """Connect to MCP server and discover tools."""
        if self.command_or_url.startswith("http"):
            # Remote MCP server
            await self._connect_remote()
        else:
            # Local MCP server via npx/command
            await self._connect_local()

    async def _connect_local(self):
        """Connect to local MCP server (npx-based)."""
        cmd = [self.command_or_url] + self.args
        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, **self.env}
        )
        # Send initialize request and get tools
        response = await self._send_request("initialize", {})
        self._tools = self._parse_tools(response.get("tools", []))

    async def _connect_remote(self):
        """Connect to remote MCP server."""
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.command_or_url}/initialize",
                json={},
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as resp:
                data = await resp.json()
                self._tools = self._parse_tools(data.get("tools", []))

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the MCP server."""
        return await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

    def get_tools(self) -> List[MCPTool]:
        """Get list of available tools."""
        return self._tools

    async def close(self):
        """Close connection to MCP server."""
        if self._process:
            self._process.terminate()
            self._process = None
```

### Phase 2: Gmail MCP Toolkit

```python
# src/clients/desktop_app/ami_daemon/base_agent/tools/toolkits/gmail_mcp_toolkit.py

import os
from typing import List
from .mcp_base import MCPClient
from .base_toolkit import FunctionTool

class GmailMCPToolkit:
    """Gmail integration via MCP server."""

    def __init__(self, credentials_path: str = None):
        self.credentials_path = credentials_path or os.getenv("GMAIL_CREDENTIALS_PATH")
        self._client: MCPClient = None
        self._tools: List[FunctionTool] = []

    async def initialize(self):
        """Initialize MCP connection."""
        self._client = MCPClient(
            command_or_url="npx",
            args=[
                "-y",
                "@gongrzhe/server-gmail-autoauth-mcp",
                self.credentials_path
            ]
        )
        await self._client.connect()
        self._build_tools()

    def _build_tools(self):
        """Convert MCP tools to FunctionTool instances."""
        for mcp_tool in self._client.get_tools():
            # Create async wrapper for each tool
            async def tool_func(tool_name=mcp_tool.name, **kwargs):
                return await self._client.call_tool(tool_name, kwargs)

            self._tools.append(FunctionTool(
                func=tool_func,
                name=mcp_tool.name,
                description=mcp_tool.description,
                input_schema=mcp_tool.input_schema
            ))

    def get_tools(self) -> List[FunctionTool]:
        return self._tools

    # Convenience methods
    async def send_email(self, to: str, subject: str, body: str) -> dict:
        """Send an email."""
        return await self._client.call_tool("gmail_send_email", {
            "to": to,
            "subject": subject,
            "body": body
        })

    async def search_emails(self, query: str, max_results: int = 10) -> List[dict]:
        """Search emails."""
        return await self._client.call_tool("gmail_search", {
            "query": query,
            "max_results": max_results
        })

    async def close(self):
        if self._client:
            await self._client.close()
```

### Phase 3: Google Drive MCP Toolkit

```python
# src/clients/desktop_app/ami_daemon/base_agent/tools/toolkits/gdrive_mcp_toolkit.py

import os
from typing import List, Optional
from .mcp_base import MCPClient
from .base_toolkit import FunctionTool

class GoogleDriveMCPToolkit:
    """Google Drive integration via MCP server."""

    def __init__(self, credentials_path: str = None):
        self.credentials_path = credentials_path or os.getenv("GDRIVE_CREDENTIALS_PATH")
        self._client: MCPClient = None

    async def initialize(self):
        self._client = MCPClient(
            command_or_url="npx",
            args=[
                "-y",
                "@modelcontextprotocol/server-gdrive",
                self.credentials_path
            ]
        )
        await self._client.connect()

    async def list_files(
        self,
        folder_id: str = "root",
        query: str = None,
        max_results: int = 100
    ) -> List[dict]:
        """List files in a folder."""
        return await self._client.call_tool("gdrive_list_files", {
            "folder_id": folder_id,
            "query": query,
            "max_results": max_results
        })

    async def read_file(self, file_id: str) -> str:
        """Read file content."""
        return await self._client.call_tool("gdrive_read_file", {
            "file_id": file_id
        })

    async def create_file(
        self,
        name: str,
        content: str,
        folder_id: str = "root",
        mime_type: str = "text/plain"
    ) -> dict:
        """Create a new file."""
        return await self._client.call_tool("gdrive_create_file", {
            "name": name,
            "content": content,
            "folder_id": folder_id,
            "mime_type": mime_type
        })

    async def search(self, query: str) -> List[dict]:
        """Search for files."""
        return await self._client.call_tool("gdrive_search", {
            "query": query
        })
```

### Phase 4: Notion MCP Toolkit

```python
# src/clients/desktop_app/ami_daemon/base_agent/tools/toolkits/notion_mcp_toolkit.py

import os
import asyncio
from typing import List, Optional, Dict, Any
from .mcp_base import MCPClient
from .base_toolkit import FunctionTool

class NotionMCPToolkit:
    """Notion integration via remote MCP server."""

    MCP_URL = "https://mcp.notion.com/mcp"

    def __init__(self, config_dir: str = None, max_retries: int = 3):
        self.config_dir = config_dir or os.getenv(
            "MCP_REMOTE_CONFIG_DIR",
            os.path.expanduser("~/.config/mcp")
        )
        self.max_retries = max_retries
        self._client: MCPClient = None

    async def initialize(self):
        """Initialize with retry logic."""
        for attempt in range(self.max_retries):
            try:
                self._client = MCPClient(
                    command_or_url=self.MCP_URL,
                    timeout=30
                )
                await self._client.connect()
                return
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

    async def search(self, query: str) -> List[dict]:
        """Search across Notion workspace."""
        return await self._client.call_tool("notion_search", {"query": query})

    async def get_page(self, page_id: str) -> dict:
        """Get a specific page."""
        return await self._client.call_tool("notion_get_page", {"page_id": page_id})

    async def create_page(
        self,
        parent_id: str,
        title: str,
        content: str = None,
        properties: Dict[str, Any] = None
    ) -> dict:
        """Create a new page."""
        return await self._client.call_tool("notion_create_page", {
            "parent_id": parent_id,
            "title": title,
            "content": content,
            "properties": properties or {}
        })

    async def query_database(
        self,
        database_id: str,
        filter: Dict[str, Any] = None,
        sorts: List[Dict[str, Any]] = None
    ) -> List[dict]:
        """Query a Notion database."""
        return await self._client.call_tool("notion_query_database", {
            "database_id": database_id,
            "filter": filter,
            "sorts": sorts
        })
```

### Phase 5: Google Calendar Toolkit (Direct API)

```python
# src/clients/desktop_app/ami_daemon/base_agent/tools/toolkits/calendar_toolkit.py

import os
from datetime import datetime, timedelta
from typing import List, Optional
from .base_toolkit import FunctionTool

class GoogleCalendarToolkit:
    """Google Calendar integration via direct API."""

    def __init__(self, credentials_path: str = None):
        self.credentials_path = credentials_path or os.getenv("GCAL_CREDENTIALS_PATH")
        self._service = None

    async def initialize(self):
        """Initialize Google Calendar service."""
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(
            self.credentials_path,
            scopes=['https://www.googleapis.com/auth/calendar']
        )
        self._service = build('calendar', 'v3', credentials=creds)

    def get_tools(self) -> List[FunctionTool]:
        """Get FunctionTool instances for LLM."""
        return [
            FunctionTool(self.list_events),
            FunctionTool(self.create_event),
            FunctionTool(self.update_event),
            FunctionTool(self.delete_event),
            FunctionTool(self.get_free_busy),
        ]

    async def list_events(
        self,
        calendar_id: str = 'primary',
        time_min: str = None,
        time_max: str = None,
        max_results: int = 10
    ) -> List[dict]:
        """List calendar events.

        Args:
            calendar_id: Calendar ID (default: primary)
            time_min: Start time in ISO format
            time_max: End time in ISO format
            max_results: Maximum number of events to return
        """
        now = datetime.utcnow()
        time_min = time_min or now.isoformat() + 'Z'
        time_max = time_max or (now + timedelta(days=30)).isoformat() + 'Z'

        events_result = self._service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        return events_result.get('items', [])

    async def create_event(
        self,
        summary: str,
        start: str,
        end: str,
        description: str = '',
        location: str = '',
        attendees: List[str] = None,
        calendar_id: str = 'primary'
    ) -> dict:
        """Create a calendar event.

        Args:
            summary: Event title
            start: Start time in ISO format
            end: End time in ISO format
            description: Event description
            location: Event location
            attendees: List of attendee email addresses
        """
        event = {
            'summary': summary,
            'description': description,
            'location': location,
            'start': {'dateTime': start, 'timeZone': 'UTC'},
            'end': {'dateTime': end, 'timeZone': 'UTC'},
        }

        if attendees:
            event['attendees'] = [{'email': email} for email in attendees]

        return self._service.events().insert(
            calendarId=calendar_id,
            body=event
        ).execute()

    async def get_free_busy(
        self,
        time_min: str,
        time_max: str,
        calendars: List[str] = None
    ) -> dict:
        """Get free/busy information.

        Args:
            time_min: Start of time range
            time_max: End of time range
            calendars: List of calendar IDs to check
        """
        calendars = calendars or ['primary']
        body = {
            'timeMin': time_min,
            'timeMax': time_max,
            'items': [{'id': cal_id} for cal_id in calendars]
        }

        return self._service.freebusy().query(body=body).execute()
```

---

## Configuration

### Environment Variables

Add to `.env` or system environment:

```bash
# Gmail MCP
GMAIL_CREDENTIALS_PATH=/path/to/gmail-credentials.json

# Google Drive MCP
GDRIVE_CREDENTIALS_PATH=/path/to/gdrive-credentials.json

# Google Calendar (Direct API)
GCAL_CREDENTIALS_PATH=/path/to/gcal-credentials.json

# Notion MCP
MCP_REMOTE_CONFIG_DIR=~/.config/mcp
NOTION_API_KEY=secret_xxx  # If using direct Notion API instead
```

### Google OAuth Setup

1. Create project in Google Cloud Console
2. Enable APIs: Gmail, Drive, Calendar
3. Create OAuth credentials
4. Download credentials JSON
5. Run initial auth flow to generate token

---

## Integration with EigentStyleBrowserAgent

Add MCP toolkits to the agent initialization:

```python
# In eigent_style_browser_agent.py

async def _initialize_toolkits(self, ...):
    # Existing toolkits
    self._note_toolkit = NoteTakingToolkit(...)
    self._browser_toolkit = BrowserToolkit(...)

    # New MCP toolkits (optional, based on config)
    if os.getenv("GMAIL_CREDENTIALS_PATH"):
        self._gmail_toolkit = GmailMCPToolkit()
        await self._gmail_toolkit.initialize()
        self._tools.extend(self._gmail_toolkit.get_tools())

    if os.getenv("GDRIVE_CREDENTIALS_PATH"):
        self._gdrive_toolkit = GoogleDriveMCPToolkit()
        await self._gdrive_toolkit.initialize()
        self._tools.extend(self._gdrive_toolkit.get_tools())

    if os.getenv("GCAL_CREDENTIALS_PATH"):
        self._calendar_toolkit = GoogleCalendarToolkit()
        await self._calendar_toolkit.initialize()
        self._tools.extend(self._calendar_toolkit.get_tools())

    # Notion (requires user authentication)
    if os.getenv("MCP_REMOTE_CONFIG_DIR"):
        try:
            self._notion_toolkit = NotionMCPToolkit()
            await self._notion_toolkit.initialize()
            self._tools.extend(self._notion_toolkit.get_tools())
        except Exception as e:
            logger.warning(f"Notion MCP not available: {e}")
```

---

## File Structure

```
src/clients/desktop_app/ami_daemon/base_agent/tools/toolkits/
├── __init__.py                 # Export all toolkits
├── base_toolkit.py             # FunctionTool base class
├── mcp_base.py                 # NEW: MCPClient base
├── gmail_mcp_toolkit.py        # NEW: Gmail via MCP
├── gdrive_mcp_toolkit.py       # NEW: Google Drive via MCP
├── calendar_toolkit.py         # NEW: Google Calendar direct API
├── notion_mcp_toolkit.py       # NEW: Notion via MCP
├── browser_toolkit.py          # Existing
├── note_taking_toolkit.py      # Existing
├── search_toolkit.py           # Existing
├── terminal_toolkit.py         # Existing
├── human_toolkit.py            # Existing
└── memory_toolkit.py           # Existing
```

---

## Testing

### Unit Tests

```python
# tests/test_mcp_toolkits.py

@pytest.mark.asyncio
async def test_gmail_toolkit():
    toolkit = GmailMCPToolkit(credentials_path="test-creds.json")
    await toolkit.initialize()

    # Search emails
    results = await toolkit.search_emails("from:test@example.com")
    assert isinstance(results, list)

@pytest.mark.asyncio
async def test_gdrive_toolkit():
    toolkit = GoogleDriveMCPToolkit()
    await toolkit.initialize()

    # List files
    files = await toolkit.list_files()
    assert isinstance(files, list)
```

### Integration Tests

```python
@pytest.mark.integration
async def test_agent_with_gmail():
    agent = EigentStyleBrowserAgent()
    await agent.initialize(context)

    result = await agent.execute({
        "task": "Find emails from john@example.com and summarize them"
    }, context)

    assert result.success
    assert "gmail" in result.data.get("tools_used", [])
```

---

## Security Considerations

1. **Credentials Storage**: Store OAuth credentials securely, not in repo
2. **Token Refresh**: Implement automatic token refresh for long-running tasks
3. **Scope Limitation**: Request minimum necessary OAuth scopes
4. **Audit Logging**: Log all MCP tool calls for security audit

---

## References

- MCP Specification: https://modelcontextprotocol.io/
- Gmail MCP Server: https://www.npmjs.com/package/@gongrzhe/server-gmail-autoauth-mcp
- Google Drive MCP: https://www.npmjs.com/package/@modelcontextprotocol/server-gdrive
- Notion MCP: https://www.notion.so/help/guides/connecting-notion-to-claude
