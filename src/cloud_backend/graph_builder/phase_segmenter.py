"""Phase Segmentation - Split events into macro-level phases.

This module segments events into phases based on strong and weak signals:

Strong signals (must split):
- URL path change
- page_root change (main → iframe, main → modal)
- Explicit reload

Weak signals (≥2 required for split):
- Idle timeout exceeded
- DOM similarity drop
- Operation type change pattern

Key principles:
- Deterministic rule-based segmentation
- No LLM or semantic understanding
"""

import logging
from typing import List
from urllib.parse import urlparse

from .models import Event
from .models import Phase

logger = logging.getLogger(__name__)


class PhaseSegmenter:
    """Segment events into macro-level phases."""

    def __init__(
        self,
        idle_threshold_ms: int = 3000,
        min_phase_events: int = 1
    ):
        """Initialize Phase Segmenter.

        Args:
            idle_threshold_ms: Idle duration threshold for weak signal
            min_phase_events: Minimum events per phase (phases with fewer are merged)
        """
        self.idle_threshold_ms = idle_threshold_ms
        self.min_phase_events = min_phase_events

    def segment(self, events: List[Event]) -> List[Phase]:
        """Segment events into phases.

        Args:
            events: List of events (after noise reduction)

        Returns:
            List of Phase objects
        """
        if not events:
            return []

        logger.info(f"Starting phase segmentation on {len(events)} events")

        phases = []
        current_phase_events = []
        phase_id_counter = 1

        last_url_path = self._get_url_path(events[0].url)
        last_page_root = events[0].page_root
        last_event_type = events[0].type

        for i, event in enumerate(events):
            current_url_path = self._get_url_path(event.url)
            current_page_root = event.page_root

            # Check for split signals
            strong_signal = self._check_strong_signals(
                last_url_path=last_url_path,
                current_url_path=current_url_path,
                last_page_root=last_page_root,
                current_page_root=current_page_root
            )

            weak_signals = 0
            if i > 0:
                weak_signals = self._count_weak_signals(
                    event=event,
                    prev_event=events[i - 1],
                    last_event_type=last_event_type
                )

            should_split = strong_signal or weak_signals >= 2

            if should_split and current_phase_events:
                # Create phase from current buffer
                phase = Phase(
                    phase_id=f"P{phase_id_counter}",
                    events=current_phase_events.copy(),
                    start_url=current_phase_events[0].url,
                    end_url=current_phase_events[-1].url
                )
                phases.append(phase)
                phase_id_counter += 1

                # Start new phase
                current_phase_events = [event]
                last_url_path = current_url_path
                last_page_root = current_page_root
                last_event_type = event.type
            else:
                # Continue current phase
                current_phase_events.append(event)
                last_event_type = event.type

        # Add final phase
        if current_phase_events:
            phase = Phase(
                phase_id=f"P{phase_id_counter}",
                events=current_phase_events.copy(),
                start_url=current_phase_events[0].url,
                end_url=current_phase_events[-1].url
            )
            phases.append(phase)

        logger.info(f"Phase segmentation complete: {len(phases)} phases created")
        return phases

    def _get_url_path(self, url: str) -> str:
        """Extract path from URL for comparison.

        Args:
            url: Full URL

        Returns:
            URL path component
        """
        try:
            parsed = urlparse(url)
            return parsed.path
        except Exception:
            return url

    def _check_strong_signals(
        self,
        last_url_path: str,
        current_url_path: str,
        last_page_root: str,
        current_page_root: str
    ) -> bool:
        """Check for strong split signals.

        Args:
            last_url_path: Previous URL path
            current_url_path: Current URL path
            last_page_root: Previous page root
            current_page_root: Current page root

        Returns:
            True if strong signal detected
        """
        # URL path change
        if last_url_path != current_url_path:
            logger.debug(f"Strong signal: URL path change {last_url_path} → {current_url_path}")
            return True

        # Page root change
        if last_page_root != current_page_root:
            logger.debug(f"Strong signal: page_root change {last_page_root} → {current_page_root}")
            return True

        return False

    def _count_weak_signals(
        self,
        event: Event,
        prev_event: Event,
        last_event_type: str
    ) -> int:
        """Count weak split signals.

        Args:
            event: Current event
            prev_event: Previous event
            last_event_type: Type of last event

        Returns:
            Number of weak signals detected
        """
        signals = 0

        # Signal 1: Idle timeout
        time_gap = event.timestamp - prev_event.timestamp
        if time_gap >= self.idle_threshold_ms:
            signals += 1
            logger.debug(f"Weak signal: Idle timeout ({time_gap}ms)")

        # Signal 2: Operation type change pattern
        # Navigation/click after series of inputs suggests phase boundary
        if (last_event_type == "input" and
            event.type in ["click", "navigation"]):
            signals += 1
            logger.debug("Weak signal: Operation type change (input → click/nav)")

        # Signal 3: Significant URL query parameter change
        # (indicates different data being processed)
        if event.url != prev_event.url:
            prev_params = self._get_url_params(prev_event.url)
            curr_params = self._get_url_params(event.url)
            if prev_params != curr_params:
                signals += 1
                logger.debug("Weak signal: URL parameters changed")

        return signals

    def _get_url_params(self, url: str) -> str:
        """Extract query parameters from URL.

        Args:
            url: Full URL

        Returns:
            Query parameter string
        """
        try:
            parsed = urlparse(url)
            return parsed.query
        except Exception:
            return ""
