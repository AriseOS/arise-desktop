"""JSON Processor module for browser event processing.

This module provides classes and utilities for processing browser operation JSON
input, converting it into standardized operation sequences. It supports multiple
browser event formats and provides a unified data structure for downstream
processing by LLM systems.

Typical usage example:

    processor = JsonProcessor()
    batch = processor.process_json_input(json_data)
    is_valid, errors = processor.validate_input(batch)
    if is_valid:
        llm_format = processor.export_to_llm_format(batch)
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BrowserEvent(BaseModel):
    """Browser event data model.

    Represents a single browser interaction event with associated metadata,
    including page information, element details, and event-specific data.

    Attributes:
        event_type: Type of browser event (e.g., click, input, scroll, navigation).
        timestamp: Event timestamp in milliseconds since epoch.
        page_url: URL of the page where the event occurred.
        page_title: Title of the page (optional).
        element_tag: HTML tag name of the target element (optional).
        element_id: ID attribute of the target element (optional).
        element_class: Class attribute of the target element (optional).
        xpath: XPath expression locating the target element (optional).
        css_selector: CSS selector for the target element (optional).
        text: Text content associated with the event (optional).
        value: Input value for input events (optional).
        coordinates: Mouse coordinates as dict with 'x' and 'y' keys (optional).
        viewport_size: Browser viewport dimensions (optional).
        scroll_position: Current scroll position (optional).
        attributes: Additional custom attributes as key-value pairs.
    """

    event_type: str = Field(
        ..., description="Event type: click, input, scroll, navigation, etc."
    )
    timestamp: int = Field(..., description="Event timestamp in milliseconds")

    # Page information.
    page_url: str = Field(..., description="Page URL")
    page_title: Optional[str] = Field(default=None, description="Page title")

    # Element information.
    element_tag: Optional[str] = Field(default=None, description="Element tag name")
    element_id: Optional[str] = Field(default=None, description="Element ID")
    element_class: Optional[str] = Field(default=None, description="Element class")
    xpath: Optional[str] = Field(default=None, description="XPath selector")
    css_selector: Optional[str] = Field(default=None, description="CSS selector")

    # Event data.
    text: Optional[str] = Field(default=None, description="Text content")
    value: Optional[str] = Field(default=None, description="Input value")
    coordinates: Optional[Dict[str, int]] = Field(
        default=None, description="Coordinates as {x, y}"
    )

    # Context information.
    viewport_size: Optional[Dict[str, int]] = Field(
        default=None, description="Viewport size"
    )
    scroll_position: Optional[Dict[str, int]] = Field(
        default=None, description="Scroll position"
    )

    # Additional attributes.
    attributes: Dict[str, Any] = Field(
        default_factory=dict, description="Custom attributes"
    )


class BrowserContext(BaseModel):
    """Browser context information.

    Contains metadata about the browsing session, user, and environment
    in which the events occurred.

    Attributes:
        user_id: Unique identifier for the user (optional).
        session_id: Session identifier (optional).
        device_type: Type of device (e.g., desktop, mobile, tablet) (optional).
        browser_info: Browser name, version, and other metadata (optional).
        start_timestamp: Session start time in milliseconds (optional).
        referrer: Referring page URL (optional).
        user_agent: Browser user agent string (optional).
        language: User's language preference (optional).
        timezone: User's timezone (optional).
    """

    user_id: Optional[str] = Field(default=None, description="User ID")
    session_id: Optional[str] = Field(default=None, description="Session ID")
    device_type: Optional[str] = Field(default=None, description="Device type")
    browser_info: Optional[Dict[str, str]] = Field(
        default=None, description="Browser information"
    )

    # Session metadata.
    start_timestamp: Optional[int] = Field(
        default=None, description="Session start timestamp"
    )
    referrer: Optional[str] = Field(default=None, description="Referrer page")

    # User preferences.
    user_agent: Optional[str] = Field(default=None, description="User agent string")
    language: Optional[str] = Field(default=None, description="Language preference")
    timezone: Optional[str] = Field(default=None, description="Timezone")


class JSONInputBatch(BaseModel):
    """JSON input batch container.

    Groups multiple browser events together with shared context information,
    representing a cohesive browsing session or interaction sequence.

    Attributes:
        batch_id: Unique identifier for this batch.
        events: List of browser events in chronological order.
        context: Shared context information for all events in the batch.
        created_at: Timestamp when this batch was created.
    """

    batch_id: str = Field(..., description="Batch ID")
    events: List[BrowserEvent] = Field(..., description="List of events")
    context: BrowserContext = Field(..., description="Context information")

    created_at: datetime = Field(
        default_factory=datetime.now, description="Creation timestamp"
    )

    def get_event_count(self) -> int:
        """Returns the total number of events in this batch.

        Returns:
            Integer count of events.
        """
        return len(self.events)

    def get_time_range(self) -> tuple[int, int]:
        """Calculates the time range spanned by events in this batch.

        Returns:
            Tuple of (min_timestamp, max_timestamp). Returns (0, 0) if no events.
        """
        if not self.events:
            return (0, 0)
        timestamps = [event.timestamp for event in self.events]
        return (min(timestamps), max(timestamps))

    def get_event_types(self) -> List[str]:
        """Extracts all unique event types in this batch.

        Returns:
            List of unique event type strings.
        """
        return list(set(event.event_type for event in self.events))

    def get_pages(self) -> List[str]:
        """Extracts all unique page URLs visited in this batch.

        Returns:
            List of unique page URLs.
        """
        return list(set(event.page_url for event in self.events))


class JsonProcessor:
    """JSON input processor for browser events.

    Responsible for parsing and validating JSON-formatted browser operation input,
    converting it into standardized data structures for LLM processing. Maintains
    a cache of processed batches for efficient retrieval.

    Attributes:
        processed_batches: Dictionary mapping batch IDs to JSONInputBatch objects.
    """

    def __init__(self):
        """Initializes the JsonProcessor with an empty batch cache."""
        self.processed_batches: Dict[str, JSONInputBatch] = {}

    def process_json_input(
        self, json_data: Dict[str, Any], batch_id: Optional[str] = None
    ) -> JSONInputBatch:
        """Processes JSON input data into a structured batch.

        Parses the JSON data containing browser events and context information,
        creates a JSONInputBatch object, and caches it for later retrieval.

        Args:
            json_data: Dictionary containing 'events' and 'context' keys.
            batch_id: Optional batch identifier. Auto-generated if not provided.

        Returns:
            A JSONInputBatch object containing the parsed events and context.

        Raises:
            ValidationError: If the JSON data doesn't match the expected schema.
        """
        if batch_id is None:
            batch_id = f"batch_{uuid.uuid4().hex[:8]}"

        # Parse event list.
        events = []
        for event_data in json_data.get("events", []):
            event = BrowserEvent(**event_data)
            events.append(event)

        # Parse context information.
        context_data = json_data.get("context", {})
        context = BrowserContext(**context_data)

        # Create batch object.
        batch = JSONInputBatch(batch_id=batch_id, events=events, context=context)

        # Cache the batch.
        self.processed_batches[batch_id] = batch

        return batch

    def process_json_string(
        self, json_string: str, batch_id: Optional[str] = None
    ) -> JSONInputBatch:
        """Processes a JSON string input into a structured batch.

        Convenience wrapper around process_json_input that handles JSON parsing.

        Args:
            json_string: Raw JSON string containing events and context.
            batch_id: Optional batch identifier. Auto-generated if not provided.

        Returns:
            A JSONInputBatch object containing the parsed events and context.

        Raises:
            JSONDecodeError: If the string is not valid JSON.
            ValidationError: If the JSON data doesn't match the expected schema.
        """
        json_data = json.loads(json_string)
        return self.process_json_input(json_data, batch_id)

    def validate_input(self, batch: JSONInputBatch) -> tuple[bool, List[str]]:
        """Validates the input batch for completeness and consistency.

        Checks that the batch contains events, timestamps are in order,
        and required fields are present.

        Args:
            batch: The batch to validate.

        Returns:
            A tuple of (is_valid, error_messages). is_valid is True if all
            validation checks pass, False otherwise. error_messages contains
            descriptions of any validation failures.
        """
        errors = []

        # Validate event count.
        if not batch.events:
            errors.append("Event list is empty")

        # Validate timestamp order.
        timestamps = [event.timestamp for event in batch.events]
        if timestamps != sorted(timestamps):
            errors.append("Event timestamps are not in chronological order")

        # Validate required fields.
        for i, event in enumerate(batch.events):
            if not event.page_url:
                errors.append(f"Event {i} is missing page_url")
            if not event.event_type:
                errors.append(f"Event {i} is missing event_type")

        return (len(errors) == 0, errors)

    def get_batch(self, batch_id: str) -> Optional[JSONInputBatch]:
        """Retrieves a batch from the cache by ID.

        Args:
            batch_id: The batch identifier.

        Returns:
            The JSONInputBatch if found, None otherwise.
        """
        return self.processed_batches.get(batch_id)

    def get_batch_summary(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Generates a summary of a batch.

        Extracts key metrics and metadata from the batch including event count,
        event types, pages visited, time range, and user information.

        Args:
            batch_id: The batch identifier.

        Returns:
            A dictionary containing batch summary information, or None if the
            batch is not found.
        """
        batch = self.get_batch(batch_id)
        if not batch:
            return None

        time_range = batch.get_time_range()

        return {
            "batch_id": batch_id,
            "event_count": batch.get_event_count(),
            "event_types": batch.get_event_types(),
            "pages": batch.get_pages(),
            "time_range": {
                "start": time_range[0],
                "end": time_range[1],
                "duration_ms": time_range[1] - time_range[0],
            },
            "user_id": batch.context.user_id,
            "session_id": batch.context.session_id,
        }

    def export_to_llm_format(self, batch: JSONInputBatch) -> str:
        """Exports batch data to an LLM-friendly text format.

        Converts the structured batch data into a human-readable text description
        that is optimized for LLM understanding and analysis. Includes context,
        event details, and summary statistics.

        Args:
            batch: The batch to export.

        Returns:
            A formatted multi-line string describing the batch contents.
        """
        lines = []

        # Context information.
        lines.append("=== Browser Operation Context ===")
        lines.append(f"Batch ID: {batch.batch_id}")
        lines.append(f"User ID: {batch.context.user_id or 'N/A'}")
        lines.append(f"Session ID: {batch.context.session_id or 'N/A'}")
        lines.append(f"Device Type: {batch.context.device_type or 'N/A'}")
        lines.append("")

        # Time range.
        time_range = batch.get_time_range()
        if time_range[0] > 0:
            duration_ms = time_range[1] - time_range[0]
            lines.append(
                f"Time Range: {time_range[0]} - {time_range[1]} (Duration: {duration_ms}ms)"
            )
            lines.append("")

        # Event sequence.
        lines.append("=== Event Sequence ===")
        lines.append(f"Total Events: {len(batch.events)}")
        lines.append("")

        for i, event in enumerate(batch.events, 1):
            lines.append(f"Event #{i}:")
            lines.append(f"  Type: {event.event_type}")
            lines.append(f"  Timestamp: {event.timestamp}")
            lines.append(f"  Page: {event.page_url}")

            if event.page_title:
                lines.append(f"  Page Title: {event.page_title}")

            if event.element_tag:
                lines.append(f"  Element: <{event.element_tag}>")

            if event.element_id:
                lines.append(f"  Element ID: {event.element_id}")

            if event.xpath:
                lines.append(f"  XPath: {event.xpath}")

            if event.text:
                lines.append(f"  Text: {event.text}")

            if event.value:
                lines.append(f"  Value: {event.value}")

            if event.coordinates:
                coord_x = event.coordinates.get("x")
                coord_y = event.coordinates.get("y")
                lines.append(f"  Coordinates: ({coord_x}, {coord_y})")

            lines.append("")

        # Summary statistics.
        lines.append("=== Summary Statistics ===")
        lines.append(f"Event Types: {', '.join(batch.get_event_types())}")
        lines.append(f"Pages Visited: {', '.join(batch.get_pages())}")

        return "\n".join(lines)

    def get_statistics(self) -> Dict[str, Any]:
        """Generates aggregate statistics across all processed batches.

        Computes summary metrics including total batches, total events,
        event type distribution, and per-batch metadata.

        Returns:
            A dictionary containing:
                - total_batches: Total number of batches processed.
                - total_events: Total number of events across all batches.
                - event_type_distribution: Dictionary mapping event types to counts.
                - batches: List of per-batch metadata (batch_id, event_count, time_range).
        """
        total_batches = len(self.processed_batches)
        total_events = sum(
            batch.get_event_count() for batch in self.processed_batches.values()
        )

        event_type_counts = {}
        for batch in self.processed_batches.values():
            for event in batch.events:
                event_type = event.event_type
                event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1

        return {
            "total_batches": total_batches,
            "total_events": total_events,
            "event_type_distribution": event_type_counts,
            "batches": [
                {
                    "batch_id": batch.batch_id,
                    "event_count": batch.get_event_count(),
                    "time_range": batch.get_time_range(),
                }
                for batch in self.processed_batches.values()
            ],
        }


__all__ = [
    "BrowserEvent",
    "BrowserContext",
    "JSONInputBatch",
    "JsonProcessor",
]
