"""Noise Reduction - Filter and merge redundant events.

This module removes noise from normalized events using deterministic rules:
- Merge consecutive hover events
- Merge consecutive scroll events
- Deduplicate rapid input changes (keep only final value)
- Mark idle periods as phase boundaries

Key principles:
- Rule-based only (no LLM)
- Deterministic (same input → same output)
- No semantic understanding
"""

import logging
from typing import List
from typing import Optional

from .models import Event

logger = logging.getLogger(__name__)


class NoiseReducer:
    """Reduce noise from event stream using deterministic rules."""

    # Thresholds for noise detection
    IDLE_THRESHOLD_MS = 3000  # 3 seconds idle → potential phase boundary
    SCROLL_MERGE_WINDOW_MS = 500  # Merge scrolls within 500ms
    INPUT_DEBOUNCE_MS = 500  # Keep only final input within 500ms
    HOVER_MERGE_WINDOW_MS = 200  # Merge hovers within 200ms

    def __init__(
        self,
        idle_threshold_ms: int = IDLE_THRESHOLD_MS,
        scroll_merge_window_ms: int = SCROLL_MERGE_WINDOW_MS,
        input_debounce_ms: int = INPUT_DEBOUNCE_MS,
        hover_merge_window_ms: int = HOVER_MERGE_WINDOW_MS
    ):
        """Initialize Noise Reducer.

        Args:
            idle_threshold_ms: Threshold for idle period detection (ms)
            scroll_merge_window_ms: Window for merging scroll events (ms)
            input_debounce_ms: Debounce window for input events (ms)
            hover_merge_window_ms: Window for merging hover events (ms)
        """
        self.idle_threshold_ms = idle_threshold_ms
        self.scroll_merge_window_ms = scroll_merge_window_ms
        self.input_debounce_ms = input_debounce_ms
        self.hover_merge_window_ms = hover_merge_window_ms

    def reduce(self, events: List[Event]) -> List[Event]:
        """Apply noise reduction to event list.

        Args:
            events: List of normalized events

        Returns:
            Filtered and merged event list
        """
        if not events:
            return []

        logger.info(f"Starting noise reduction on {len(events)} events")

        # Step 1: Merge consecutive hovers
        events = self._merge_hovers(events)

        # Step 2: Merge consecutive scrolls
        events = self._merge_scrolls(events)

        # Step 3: Deduplicate rapid inputs
        events = self._deduplicate_inputs(events)

        # Step 4: Mark idle periods
        events = self._mark_idle_periods(events)

        # Step 5: Remove meaningless events
        events = self._remove_noise_events(events)

        logger.info(f"Noise reduction complete: {len(events)} events remaining")
        return events

    def _merge_hovers(self, events: List[Event]) -> List[Event]:
        """Merge consecutive hover events.

        Args:
            events: Event list

        Returns:
            Event list with merged hovers
        """
        if not events:
            return []

        merged = []
        hover_buffer = []

        for event in events:
            if event.type == "hover":
                hover_buffer.append(event)
            else:
                # Flush hover buffer (keep only last hover)
                if hover_buffer:
                    merged.append(hover_buffer[-1])
                    hover_buffer = []
                merged.append(event)

        # Flush remaining hovers
        if hover_buffer:
            merged.append(hover_buffer[-1])

        if len(merged) < len(events):
            logger.debug(f"Merged {len(events) - len(merged)} hover events")

        return merged

    def _merge_scrolls(self, events: List[Event]) -> List[Event]:
        """Merge consecutive scroll events within time window.

        Args:
            events: Event list

        Returns:
            Event list with merged scrolls
        """
        if not events:
            return []

        merged = []
        scroll_buffer = []
        scroll_start_time = 0

        for event in events:
            if event.type == "scroll":
                if not scroll_buffer:
                    scroll_start_time = event.timestamp
                    scroll_buffer.append(event)
                elif event.timestamp - scroll_start_time <= self.scroll_merge_window_ms:
                    scroll_buffer.append(event)
                else:
                    # Flush buffer - create merged scroll
                    if scroll_buffer:
                        merged_scroll = self._create_merged_scroll(scroll_buffer)
                        merged.append(merged_scroll)
                    scroll_buffer = [event]
                    scroll_start_time = event.timestamp
            else:
                # Flush scroll buffer
                if scroll_buffer:
                    merged_scroll = self._create_merged_scroll(scroll_buffer)
                    merged.append(merged_scroll)
                    scroll_buffer = []
                merged.append(event)

        # Flush remaining scrolls
        if scroll_buffer:
            merged_scroll = self._create_merged_scroll(scroll_buffer)
            merged.append(merged_scroll)

        if len(merged) < len(events):
            logger.debug(f"Merged {len(events) - len(merged)} scroll events")

        return merged

    def _create_merged_scroll(self, scroll_events: List[Event]) -> Event:
        """Create a single merged scroll event from multiple scrolls.

        Args:
            scroll_events: List of scroll events to merge

        Returns:
            Merged scroll event
        """
        if not scroll_events:
            raise ValueError("Cannot merge empty scroll list")

        if len(scroll_events) == 1:
            return scroll_events[0]

        # Use first event as base
        merged = Event(
            timestamp=scroll_events[0].timestamp,
            type="scroll",
            url=scroll_events[-1].url,
            page_root=scroll_events[-1].page_root,
            target=scroll_events[-1].target,
            dom_hash=scroll_events[-1].dom_hash,
            data={}
        )

        # Accumulate scroll distances (handle None values)
        total_distance = sum(
            e.data.get("distance", 0) or 0 for e in scroll_events
        )
        total_height_change = sum(
            e.data.get("height_change", 0) or 0 for e in scroll_events
        )

        merged.data["distance"] = total_distance
        merged.data["height_change"] = total_height_change
        merged.data["direction"] = scroll_events[-1].data.get("direction", "down")
        merged.data["merged_count"] = len(scroll_events)

        return merged

    def _deduplicate_inputs(self, events: List[Event]) -> List[Event]:
        """Deduplicate rapid input changes, keeping only final value.

        Args:
            events: Event list

        Returns:
            Event list with deduplicated inputs
        """
        if not events:
            return []

        merged = []
        input_buffer = []
        input_start_time = 0
        last_dom_hash = None

        for event in events:
            if event.type == "input":
                current_hash = event.dom_hash

                # Same input field
                if current_hash == last_dom_hash:
                    if not input_buffer:
                        input_start_time = event.timestamp
                        input_buffer.append(event)
                    elif event.timestamp - input_start_time <= self.input_debounce_ms:
                        input_buffer.append(event)
                    else:
                        # Flush buffer (keep last input)
                        if input_buffer:
                            merged.append(input_buffer[-1])
                        input_buffer = [event]
                        input_start_time = event.timestamp
                else:
                    # Different input field - flush buffer
                    if input_buffer:
                        merged.append(input_buffer[-1])
                    input_buffer = [event]
                    input_start_time = event.timestamp
                    last_dom_hash = current_hash
            else:
                # Flush input buffer
                if input_buffer:
                    merged.append(input_buffer[-1])
                    input_buffer = []
                    last_dom_hash = None
                merged.append(event)

        # Flush remaining inputs
        if input_buffer:
            merged.append(input_buffer[-1])

        if len(merged) < len(events):
            logger.debug(f"Deduplicated {len(events) - len(merged)} input events")

        return merged

    def _mark_idle_periods(self, events: List[Event]) -> List[Event]:
        """Mark idle periods in event metadata.

        Args:
            events: Event list

        Returns:
            Event list with idle markers
        """
        if len(events) < 2:
            return events

        for i in range(1, len(events)):
            time_gap = events[i].timestamp - events[i - 1].timestamp

            if time_gap >= self.idle_threshold_ms:
                # Mark this event as after idle
                events[i].data["after_idle"] = True
                events[i].data["idle_duration_ms"] = time_gap
                logger.debug(
                    f"Idle period detected: {time_gap}ms between events {i-1} and {i}"
                )

        return events

    def _remove_noise_events(self, events: List[Event]) -> List[Event]:
        """Remove meaningless noise events.

        Rules:
        - Remove hovers that don't lead to any action
        - Remove dataload events (they are system events, not user intent)

        Args:
            events: Event list

        Returns:
            Filtered event list
        """
        filtered = []

        for i, event in enumerate(events):
            # Skip dataload events (system events, not user actions)
            if event.type == "dataload":
                continue

            # Skip standalone hovers (hovers not followed by click)
            if event.type == "hover":
                # Check if next event is a click on same element
                if i + 1 < len(events):
                    next_event = events[i + 1]
                    if (next_event.type == "click" and
                        next_event.dom_hash == event.dom_hash):
                        # This hover leads to click, keep it
                        filtered.append(event)
                    else:
                        # Standalone hover, skip it
                        continue
                else:
                    # Last event is hover, skip it
                    continue
            else:
                filtered.append(event)

        if len(filtered) < len(events):
            logger.debug(f"Removed {len(events) - len(filtered)} noise events")

        return filtered
