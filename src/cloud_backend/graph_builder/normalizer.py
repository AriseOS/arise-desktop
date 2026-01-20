"""Event Normalizer - Convert raw recordings to normalized Events.

This module provides adapters to convert various recording formats into
the normalized Event schema. This is the first step in the Graph Builder pipeline.

Key principles:
- Strict validation of field completeness
- No semantic understanding
- Pure structural transformation
"""

import hashlib
import logging
from typing import Any
from typing import Dict
from typing import List

from .models import Event
from .models import EventTarget

logger = logging.getLogger(__name__)


class EventNormalizer:
    """Normalize raw browser recordings into Event schema.

    Adapter pattern: Different recording formats → Unified Event structure
    """

    def __init__(self):
        """Initialize Event Normalizer."""
        pass

    def normalize(self, operations: List[Dict[str, Any]]) -> List[Event]:
        """Normalize raw operations to Event list.

        Args:
            operations: List of raw operation dictionaries

        Returns:
            List of normalized Event objects

        Raises:
            ValueError: If operations format is invalid
        """
        if not isinstance(operations, list):
            raise ValueError("Operations must be a list")

        normalized_events = []
        for i, op in enumerate(operations):
            try:
                event = self._normalize_operation(op)
                normalized_events.append(event)
            except Exception as e:
                logger.warning(f"Failed to normalize operation {i}: {e}")
                continue

        logger.info(f"Normalized {len(normalized_events)}/{len(operations)} operations")
        return normalized_events

    def _normalize_operation(self, op: Dict[str, Any]) -> Event:
        """Normalize a single operation to Event.

        Args:
            op: Raw operation dictionary

        Returns:
            Normalized Event object

        Raises:
            ValueError: If required fields are missing
        """
        op_type = op.get("type")
        if not op_type:
            raise ValueError("Operation missing 'type' field")

        url = op.get("url", "")

        # Handle timestamp - support both string and int formats
        timestamp = op.get("timestamp", 0)
        if isinstance(timestamp, str):
            from datetime import datetime
            try:
                # Try "YYYY-MM-DD HH:MM:SS" format (from CDPRecorder)
                dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                timestamp = int(dt.timestamp() * 1000)
            except ValueError:
                try:
                    # Try ISO format
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    timestamp = int(dt.timestamp() * 1000)
                except Exception:
                    logger.warning(f"Failed to parse timestamp: {timestamp}")
                    timestamp = 0
        elif not isinstance(timestamp, int):
            timestamp = 0

        event_type = self._map_operation_type(op_type)

        target = None
        element = op.get("element")
        if element and isinstance(element, dict):
            target = self._extract_target(element)

        page_root = "main"
        if "iframe" in url.lower():
            page_root = "iframe"
        elif "modal" in op.get("page_title", "").lower():
            page_root = "modal"

        dom_hash = None
        if element:
            dom_hash = self._compute_dom_hash(element)

        data = self._extract_event_data(op)

        return Event(
            timestamp=timestamp,
            type=event_type,
            url=url,
            page_root=page_root,
            target=target,
            dom_hash=dom_hash,
            data=data
        )

    def _map_operation_type(self, op_type: str) -> str:
        """Map raw operation type to normalized event type.

        Args:
            op_type: Raw operation type

        Returns:
            Normalized event type: "click" | "input" | "scroll" | "navigation"
        """
        type_mapping = {
            "click": "click",
            "input": "input",
            "scroll": "scroll",
            "navigate": "navigation",
            "navigation": "navigation",
            "copy_action": "click",
            "select": "click",
            "hover": "hover",
            "dataload": "dataload"
        }

        normalized = type_mapping.get(op_type, op_type)
        return normalized

    def _extract_target(self, element: Dict[str, Any]) -> EventTarget:
        """Extract target information from element.

        Args:
            element: Element dictionary from operation

        Returns:
            EventTarget object
        """
        text_content = element.get("textContent", "")
        if isinstance(text_content, str):
            text_content = text_content.strip()[:100]
        elif text_content:
            text_content = str(text_content)[:100]
        else:
            text_content = None

        tag = element.get("tagName")
        if tag and isinstance(tag, str):
            tag = tag.lower()

        return EventTarget(
            tag=tag,
            role=element.get("role"),
            text=text_content if text_content else None,
            aria=element.get("ariaLabel"),
            href=element.get("href"),
            xpath=element.get("xpath")
        )

    def _compute_dom_hash(self, element: Dict[str, Any]) -> str:
        """Compute hash of DOM element for deduplication.

        Args:
            element: Element dictionary

        Returns:
            Hash string
        """
        hash_parts = [
            str(element.get("tagName", "")),
            str(element.get("role", "")),
            str(element.get("textContent", ""))[:50],
            str(element.get("href", ""))
        ]

        hash_string = "|".join(hash_parts)
        return hashlib.md5(hash_string.encode()).hexdigest()[:12]

    def _extract_event_data(self, op: Dict[str, Any]) -> Dict[str, Any]:
        """Extract event-specific data.

        Args:
            op: Raw operation dictionary

        Returns:
            Dictionary with event-specific data
        """
        data = {}
        op_type = op.get("type")
        op_data = op.get("data", {})

        if op_type == "scroll":
            data["direction"] = op_data.get("direction")
            data["distance"] = op_data.get("distance")
            data["height_change"] = op_data.get("height_change", 0)

        elif op_type == "input":
            data["value"] = op_data.get("value", "")

        elif op_type == "dataload":
            data["added_elements_count"] = op_data.get("added_elements_count", 0)
            data["data_elements_count"] = op_data.get("data_elements_count", 0)
            data["height_change"] = op_data.get("height_change", 0)

        elif op_type == "copy_action":
            data["copied_text"] = op_data.get("copiedText", "")

        elif op_type == "select":
            data["selected_text"] = op_data.get("selectedText", "")

        page_title = op.get("page_title")
        if page_title:
            data["page_title"] = page_title

        return data
