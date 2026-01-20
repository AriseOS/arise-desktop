"""Episode Segmentation - Split phases into medium-level episodes.

This module segments phases into episodes based on user action boundaries:

Rules:
- click / navigation → Episode boundary
- Consecutive inputs → Merge into one episode
- Noise episodes → Discard

Episode Signature:
- event_types: Sequence of event types
- target_roles: Sequence of target roles
- url: Episode URL

Key principles:
- Deterministic rule-based segmentation
- No LLM or semantic understanding
"""

import logging
from typing import List

from .models import Episode
from .models import Event
from .models import Phase

logger = logging.getLogger(__name__)


class EpisodeSegmenter:
    """Segment phases into medium-level episodes."""

    def __init__(self, min_episode_events: int = 1):
        """Initialize Episode Segmenter.

        Args:
            min_episode_events: Minimum events per episode (smaller episodes discarded)
        """
        self.min_episode_events = min_episode_events

    def segment(self, phases: List[Phase]) -> List[Episode]:
        """Segment phases into episodes.

        Args:
            phases: List of Phase objects

        Returns:
            List of Episode objects
        """
        if not phases:
            return []

        logger.info(f"Starting episode segmentation on {len(phases)} phases")

        all_episodes = []
        episode_id_counter = 1

        for phase in phases:
            phase_episodes = self._segment_phase(
                phase=phase,
                start_id=episode_id_counter
            )
            all_episodes.extend(phase_episodes)
            episode_id_counter += len(phase_episodes)

        # Filter noise episodes
        filtered_episodes = self._filter_noise_episodes(all_episodes)

        logger.info(
            f"Episode segmentation complete: {len(filtered_episodes)} episodes "
            f"({len(all_episodes) - len(filtered_episodes)} filtered as noise)"
        )
        return filtered_episodes

    def _segment_phase(self, phase: Phase, start_id: int) -> List[Episode]:
        """Segment a single phase into episodes.

        Args:
            phase: Phase to segment
            start_id: Starting episode ID counter

        Returns:
            List of episodes for this phase
        """
        if not phase.events:
            return []

        episodes = []
        current_episode_events = []
        episode_id_counter = start_id

        for i, event in enumerate(phase.events):
            # Check if this event should start a new episode
            should_split = self._should_start_new_episode(
                event=event,
                current_events=current_episode_events,
                prev_event=phase.events[i - 1] if i > 0 else None
            )

            if should_split and current_episode_events:
                # Create episode from current buffer
                episode = self._create_episode(
                    episode_id=f"E{episode_id_counter}",
                    events=current_episode_events
                )
                episodes.append(episode)
                episode_id_counter += 1

                # Start new episode
                current_episode_events = [event]
            else:
                # Continue current episode
                current_episode_events.append(event)

        # Add final episode
        if current_episode_events:
            episode = self._create_episode(
                episode_id=f"E{episode_id_counter}",
                events=current_episode_events
            )
            episodes.append(episode)

        return episodes

    def _should_start_new_episode(
        self,
        event: Event,
        current_events: List[Event],
        prev_event: Event | None
    ) -> bool:
        """Check if event should start a new episode.

        Rules:
        - First event in phase → No split (start of episode)
        - Click event → Split (new episode)
        - Navigation event → Split (new episode)
        - Input after non-input → Continue (inputs are grouped)
        - Other transitions → Split

        Args:
            event: Current event
            current_events: Events in current episode buffer
            prev_event: Previous event

        Returns:
            True if should start new episode
        """
        # First event - don't split
        if not current_events:
            return False

        # Click or navigation always starts new episode
        if event.type in ["click", "navigation"]:
            return True

        # If previous event was click/navigation, this starts new episode
        if prev_event and prev_event.type in ["click", "navigation"]:
            return True

        # Group consecutive inputs together
        if event.type == "input":
            if prev_event and prev_event.type == "input":
                # Same input field (based on dom_hash)
                if event.dom_hash == prev_event.dom_hash:
                    return False  # Continue same episode
                else:
                    return True  # Different input field, new episode
            else:
                return True  # First input after non-input

        # Group consecutive scrolls together
        if event.type == "scroll":
            if prev_event and prev_event.type == "scroll":
                return False  # Continue same episode
            else:
                return True  # First scroll after non-scroll

        # Default: start new episode for other transitions
        return True

    def _create_episode(
        self,
        episode_id: str,
        events: List[Event]
    ) -> Episode:
        """Create Episode object from events.

        Args:
            episode_id: Episode identifier
            events: List of events in this episode

        Returns:
            Episode object
        """
        event_types = [e.type for e in events]

        target_roles = []
        for e in events:
            if e.target and e.target.role:
                target_roles.append(e.target.role)
            else:
                target_roles.append("none")

        url = events[0].url if events else ""

        return Episode(
            episode_id=episode_id,
            events=events.copy(),
            event_types=event_types,
            target_roles=target_roles,
            url=url
        )

    def _filter_noise_episodes(self, episodes: List[Episode]) -> List[Episode]:
        """Filter out noise episodes.

        Noise episodes:
        - Episodes with fewer than min_episode_events
        - Episodes containing only scroll events (browsing, not meaningful)
        - Episodes containing only hover events

        Args:
            episodes: List of episodes

        Returns:
            Filtered episode list
        """
        filtered = []

        for episode in episodes:
            # Check minimum event count
            if len(episode.events) < self.min_episode_events:
                logger.debug(f"Filtered noise episode {episode.episode_id}: too few events")
                continue

            # Check if all events are scrolls (meaningless browsing)
            if all(e.type == "scroll" for e in episode.events):
                logger.debug(f"Filtered noise episode {episode.episode_id}: scroll-only")
                continue

            # Check if all events are hovers
            if all(e.type == "hover" for e in episode.events):
                logger.debug(f"Filtered noise episode {episode.episode_id}: hover-only")
                continue

            filtered.append(episode)

        return filtered
