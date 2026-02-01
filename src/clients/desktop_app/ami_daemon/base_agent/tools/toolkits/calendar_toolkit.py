"""
Google Calendar Toolkit

Google Calendar integration via direct Google API (not MCP).
Based on Eigent's GoogleCalendarToolkit implementation.

Unlike MCP-based toolkits, this uses the Google Calendar API directly
for more fine-grained control over calendar operations.

References:
- Google Calendar API: https://developers.google.com/calendar/api
- Eigent: third-party/eigent/backend/app/utils/toolkit/google_calendar_toolkit.py
"""

import atexit
import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Any, Dict, List, Optional

from .base_toolkit import BaseToolkit, FunctionTool

logger = logging.getLogger(__name__)

# Shared thread pool for Google API calls
_google_api_executor: Optional[ThreadPoolExecutor] = None


def _get_executor() -> ThreadPoolExecutor:
    """Get or create shared thread pool executor for Google API calls."""
    global _google_api_executor
    if _google_api_executor is None:
        _google_api_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gcal_")
    return _google_api_executor


def _cleanup_executor() -> None:
    """Clean up shared thread pool executor on exit."""
    global _google_api_executor
    if _google_api_executor is not None:
        try:
            _google_api_executor.shutdown(wait=False)
            logger.debug("Google Calendar executor shutdown")
        except Exception as e:
            logger.warning(f"Error during Google Calendar executor cleanup: {e}")
        finally:
            _google_api_executor = None


# Register cleanup on exit
atexit.register(_cleanup_executor)


class GoogleCalendarToolkit(BaseToolkit):
    """Google Calendar integration via direct API.

    Provides calendar operations:
    - List events
    - Create events
    - Update events
    - Delete events
    - Get free/busy information
    - List calendars

    Requires:
    - google-api-python-client package
    - google-auth package
    - GCAL_CREDENTIALS_PATH environment variable set
    - OAuth credentials with Calendar API access

    Usage:
        toolkit = GoogleCalendarToolkit()
        await toolkit.initialize()

        # List upcoming events
        events = await toolkit.list_events(max_results=10)

        # Create event
        event = await toolkit.create_event(
            summary="Meeting",
            start="2024-01-15T10:00:00Z",
            end="2024-01-15T11:00:00Z"
        )
    """

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        timeout: int = 30,
    ):
        """Initialize Google Calendar toolkit.

        Args:
            credentials_path: Path to OAuth credentials JSON.
                Defaults to GCAL_CREDENTIALS_PATH env var.
            timeout: Operation timeout in seconds.
        """
        super().__init__(timeout=timeout)

        self.credentials_path = credentials_path or os.getenv("GCAL_CREDENTIALS_PATH")

        if not self.credentials_path:
            raise ValueError(
                "Google Calendar credentials path not provided. "
                "Set GCAL_CREDENTIALS_PATH environment variable or pass credentials_path."
            )

        if not os.path.exists(self.credentials_path):
            raise FileNotFoundError(
                f"Google Calendar credentials file not found: {self.credentials_path}"
            )

        self._service = None
        self._initialized = False
        self._function_tools: List[FunctionTool] = []

    @property
    def is_initialized(self) -> bool:
        """Check if toolkit is initialized."""
        return self._initialized

    async def initialize(self) -> bool:
        """Initialize Google Calendar service.

        Returns:
            True if successful
        """
        if self._initialized:
            return True

        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError(
                "Google Calendar API requires 'google-api-python-client' and 'google-auth' packages. "
                "Install with: pip install google-api-python-client google-auth"
            )

        try:
            # Run sync initialization in thread pool
            loop = asyncio.get_running_loop()

            def _init_service():
                creds = Credentials.from_authorized_user_file(
                    self.credentials_path,
                    scopes=['https://www.googleapis.com/auth/calendar']
                )
                return build('calendar', 'v3', credentials=creds)

            self._service = await loop.run_in_executor(_get_executor(), _init_service)
            self._initialized = True

            # Build FunctionTool wrappers
            self._build_function_tools()

            logger.info(f"Google Calendar toolkit initialized with {len(self._function_tools)} tools")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Google Calendar: {e}")
            raise

    def _build_function_tools(self) -> None:
        """Build FunctionTool wrappers for calendar methods."""
        self._function_tools = [
            FunctionTool(
                func=self.list_events,
                name="calendar_list_events",
                description="List calendar events within a time range",
            ),
            FunctionTool(
                func=self.create_event,
                name="calendar_create_event",
                description="Create a new calendar event",
            ),
            FunctionTool(
                func=self.update_event,
                name="calendar_update_event",
                description="Update an existing calendar event",
            ),
            FunctionTool(
                func=self.delete_event,
                name="calendar_delete_event",
                description="Delete a calendar event",
            ),
            FunctionTool(
                func=self.get_event,
                name="calendar_get_event",
                description="Get details of a specific calendar event",
            ),
            FunctionTool(
                func=self.get_free_busy,
                name="calendar_get_free_busy",
                description="Get free/busy information for calendars",
            ),
            FunctionTool(
                func=self.list_calendars,
                name="calendar_list_calendars",
                description="List all accessible calendars",
            ),
            FunctionTool(
                func=self.quick_add,
                name="calendar_quick_add",
                description="Create event using natural language (like Google's quick add)",
            ),
        ]

    def get_tools(self) -> List[FunctionTool]:
        """Get FunctionTool instances for LLM integration.

        Returns:
            List of FunctionTool instances
        """
        return self._function_tools

    def get_function_tools(self) -> List[FunctionTool]:
        """Alias for get_tools() for consistency with MCP toolkits.

        Returns:
            List of FunctionTool instances
        """
        return self._function_tools

    async def _run_sync(self, func, *args, **kwargs):
        """Run a synchronous function in the thread pool.

        Args:
            func: Sync function to run
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            _get_executor(),
            partial(func, *args, **kwargs)
        )

    async def list_events(
        self,
        calendar_id: str = "primary",
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        max_results: int = 10,
        query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List calendar events.

        Args:
            calendar_id: Calendar ID (default: primary)
            time_min: Start time in ISO format (default: now)
            time_max: End time in ISO format (default: 30 days from now)
            max_results: Maximum number of events to return
            query: Optional text search query

        Returns:
            List of event dictionaries
        """
        if not self._initialized:
            raise RuntimeError("Toolkit not initialized, call initialize() first")

        now = datetime.now(timezone.utc)

        if not time_min:
            time_min = now.isoformat()
        if not time_max:
            time_max = (now + timedelta(days=30)).isoformat()

        request_params = {
            "calendarId": calendar_id,
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }

        if query:
            request_params["q"] = query

        def _list():
            return self._service.events().list(**request_params).execute()

        events_result = await self._run_sync(_list)
        return events_result.get("items", [])

    async def create_event(
        self,
        summary: str,
        start: str,
        end: str,
        description: str = "",
        location: str = "",
        attendees: Optional[List[str]] = None,
        calendar_id: str = "primary",
        timezone_str: str = "UTC",
        reminders: Optional[Dict[str, Any]] = None,
        recurrence: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a calendar event.

        Args:
            summary: Event title
            start: Start time in ISO format
            end: End time in ISO format
            description: Event description
            location: Event location
            attendees: List of attendee email addresses
            calendar_id: Calendar ID (default: primary)
            timezone_str: Timezone for the event
            reminders: Custom reminder settings
            recurrence: Recurrence rules (RRULE format)

        Returns:
            Created event data
        """
        if not self._initialized:
            raise RuntimeError("Toolkit not initialized, call initialize() first")

        event: Dict[str, Any] = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": {"dateTime": start, "timeZone": timezone_str},
            "end": {"dateTime": end, "timeZone": timezone_str},
        }

        if attendees:
            event["attendees"] = [{"email": email} for email in attendees]

        if reminders:
            event["reminders"] = reminders

        if recurrence:
            event["recurrence"] = recurrence

        def _insert():
            return self._service.events().insert(
                calendarId=calendar_id,
                body=event,
                sendUpdates="all" if attendees else "none",
            ).execute()

        return await self._run_sync(_insert)

    async def update_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        summary: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Update an existing calendar event.

        Args:
            event_id: Event ID to update
            calendar_id: Calendar ID (default: primary)
            summary: New event title
            start: New start time in ISO format
            end: New end time in ISO format
            description: New event description
            location: New event location
            attendees: New list of attendee emails

        Returns:
            Updated event data
        """
        if not self._initialized:
            raise RuntimeError("Toolkit not initialized, call initialize() first")

        def _update():
            # Get existing event
            event = self._service.events().get(
                calendarId=calendar_id,
                eventId=event_id,
            ).execute()

            # Update fields if provided
            if summary is not None:
                event["summary"] = summary
            if description is not None:
                event["description"] = description
            if location is not None:
                event["location"] = location
            if start is not None:
                event["start"]["dateTime"] = start
            if end is not None:
                event["end"]["dateTime"] = end
            if attendees is not None:
                event["attendees"] = [{"email": email} for email in attendees]

            return self._service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event,
                sendUpdates="all" if attendees else "none",
            ).execute()

        return await self._run_sync(_update)

    async def delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        send_updates: str = "all",
    ) -> Dict[str, Any]:
        """Delete a calendar event.

        Args:
            event_id: Event ID to delete
            calendar_id: Calendar ID (default: primary)
            send_updates: Notification setting ("all", "externalOnly", "none")

        Returns:
            Empty dict on success
        """
        if not self._initialized:
            raise RuntimeError("Toolkit not initialized, call initialize() first")

        def _delete():
            self._service.events().delete(
                calendarId=calendar_id,
                eventId=event_id,
                sendUpdates=send_updates,
            ).execute()

        await self._run_sync(_delete)
        return {"deleted": True, "event_id": event_id}

    async def get_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """Get details of a specific event.

        Args:
            event_id: Event ID
            calendar_id: Calendar ID (default: primary)

        Returns:
            Event data dictionary
        """
        if not self._initialized:
            raise RuntimeError("Toolkit not initialized, call initialize() first")

        def _get():
            return self._service.events().get(
                calendarId=calendar_id,
                eventId=event_id,
            ).execute()

        return await self._run_sync(_get)

    async def get_free_busy(
        self,
        time_min: str,
        time_max: str,
        calendars: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Get free/busy information.

        Args:
            time_min: Start of time range in ISO format
            time_max: End of time range in ISO format
            calendars: List of calendar IDs to check (default: primary)

        Returns:
            Free/busy information
        """
        if not self._initialized:
            raise RuntimeError("Toolkit not initialized, call initialize() first")

        calendars = calendars or ["primary"]
        body = {
            "timeMin": time_min,
            "timeMax": time_max,
            "items": [{"id": cal_id} for cal_id in calendars],
        }

        def _query():
            return self._service.freebusy().query(body=body).execute()

        return await self._run_sync(_query)

    async def list_calendars(self) -> List[Dict[str, Any]]:
        """List all accessible calendars.

        Returns:
            List of calendar dictionaries
        """
        if not self._initialized:
            raise RuntimeError("Toolkit not initialized, call initialize() first")

        def _list():
            return self._service.calendarList().list().execute()

        calendar_list = await self._run_sync(_list)
        return calendar_list.get("items", [])

    async def quick_add(
        self,
        text: str,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """Create event using natural language.

        Uses Google's quick add feature to parse natural language
        event descriptions.

        Args:
            text: Natural language event description
                  (e.g., "Meeting with John tomorrow at 3pm")
            calendar_id: Calendar ID (default: primary)

        Returns:
            Created event data
        """
        if not self._initialized:
            raise RuntimeError("Toolkit not initialized, call initialize() first")

        def _quick_add():
            return self._service.events().quickAdd(
                calendarId=calendar_id,
                text=text,
            ).execute()

        return await self._run_sync(_quick_add)

    async def close(self) -> None:
        """Close the toolkit (cleanup if needed)."""
        self._service = None
        self._initialized = False
        logger.debug("Google Calendar toolkit closed")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
