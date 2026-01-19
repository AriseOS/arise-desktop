"""Graph Builder - Build State/Action Graph from recordings.

This is the main entry point that orchestrates the entire pipeline:
Recording → Normalize → Noise Reduce → Phase → Episode → Graph

Key principles:
- Completely deterministic (same recording → same graph)
- No LLM usage
- No semantic understanding
- Pure structural transformation

Acceptance criteria:
- 100% reproducibility
- No loss of click/navigation events
"""

import hashlib
import logging
from typing import Any
from typing import Dict
from typing import List

from .episode_segmenter import EpisodeSegmenter
from .models import Action
from .models import Episode
from .models import Event
from .models import event_target_to_intent_attrs
from .models import Intent
from .models import State
from .models import StateActionGraph
from .noise_reducer import NoiseReducer
from .normalizer import EventNormalizer
from .phase_segmenter import PhaseSegmenter

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Build State/Action Graph from browser recordings.

    This class orchestrates the complete pipeline:
    1. Event Normalization (raw ops → Events)
    2. Noise Reduction (filter & merge)
    3. Phase Segmentation (macro-level)
    4. Episode Segmentation (medium-level)
    5. Graph Construction (States with Intents + Actions)

    Now produces memgraph-compatible output:
    - States contain Intents (operations within state)
    - Actions represent state transitions only
    """

    def __init__(
        self,
        idle_threshold_ms: int = 3000,
        scroll_merge_window_ms: int = 500,
        input_debounce_ms: int = 500,
        hover_merge_window_ms: int = 200,
        user_id: str = None,
        session_id: str = None
    ):
        """Initialize Graph Builder.

        Args:
            idle_threshold_ms: Idle duration threshold
            scroll_merge_window_ms: Scroll merge window
            input_debounce_ms: Input debounce window
            hover_merge_window_ms: Hover merge window
            user_id: User ID for attribution (optional)
            session_id: Session ID for grouping (optional)
        """
        self.normalizer = EventNormalizer()
        self.noise_reducer = NoiseReducer(
            idle_threshold_ms=idle_threshold_ms,
            scroll_merge_window_ms=scroll_merge_window_ms,
            input_debounce_ms=input_debounce_ms,
            hover_merge_window_ms=hover_merge_window_ms
        )
        self.phase_segmenter = PhaseSegmenter(
            idle_threshold_ms=idle_threshold_ms
        )
        self.episode_segmenter = EpisodeSegmenter()
        self.user_id = user_id
        self.session_id = session_id

    def build(self, operations: List[Dict[str, Any]]) -> StateActionGraph:
        """Build State/Action Graph from raw operations.

        Args:
            operations: Raw operation list from recording

        Returns:
            StateActionGraph object

        Raises:
            ValueError: If operations are invalid
        """
        logger.info("="*70)
        logger.info("Starting Graph Builder Pipeline")
        logger.info("="*70)

        # Step 1: Normalize events
        logger.info("Step 1/5: Event Normalization")
        events = self.normalizer.normalize(operations)
        logger.info(f"  → {len(events)} normalized events")

        # Step 2: Noise reduction
        logger.info("Step 2/5: Noise Reduction")
        events = self.noise_reducer.reduce(events)
        logger.info(f"  → {len(events)} events after noise reduction")

        # Step 3: Phase segmentation
        logger.info("Step 3/5: Phase Segmentation")
        phases = self.phase_segmenter.segment(events)
        logger.info(f"  → {len(phases)} phases created")

        # Step 4: Episode segmentation
        logger.info("Step 4/5: Episode Segmentation")
        episodes = self.episode_segmenter.segment(phases)
        logger.info(f"  → {len(episodes)} episodes created")

        # Step 5: Build graph
        logger.info("Step 5/5: Graph Construction")
        graph = self._build_graph(episodes, phases)
        total_intents = sum(len(s.intents) for s in graph.states.values())
        logger.info(f"  → {len(graph.states)} states, {total_intents} intents, {len(graph.actions)} actions")

        logger.info("="*70)
        logger.info("Graph Builder Pipeline Complete")
        logger.info("="*70)

        return graph

    def _build_graph(
        self,
        episodes: List[Episode],
        phases: List
    ) -> StateActionGraph:
        """Build State/Action Graph from episodes using memgraph ontology.

        New behavior:
        - Operations within same state → Intent objects (stored in State.intents)
        - Operations causing state transitions → Action objects
        - No self-loop Actions (memgraph constraint)

        Args:
            episodes: List of episodes
            phases: List of phases (for context)

        Returns:
            StateActionGraph with memgraph-compatible State/Intent/Action structure
        """
        graph = StateActionGraph(phases=phases, episodes=episodes)

        if not episodes:
            return graph

        # Track state sequence
        state_id_counter = 1
        intent_id_counter = 1
        action_id_counter = 1

        # Build states and intents/actions from episodes
        for episode in episodes:
            if not episode.events:
                continue

            # Create or get state for episode start
            start_state = self._get_or_create_state(
                graph=graph,
                event=episode.events[0],
                state_id_counter=state_id_counter
            )
            if start_state.id not in graph.states:
                graph.add_state(start_state)
                state_id_counter += 1

            # Process each event in episode
            current_state_id = start_state.id

            for i, event in enumerate(episode.events):
                # Skip non-action events (dataload, etc.)
                if event.type not in ["click", "input", "scroll", "navigation"]:
                    continue

                # Determine if this event causes a state transition
                causes_transition = False
                next_state = None

                if event.type == "navigation":
                    # Navigation always changes state
                    causes_transition = True
                    next_state = self._get_or_create_state(
                        graph=graph,
                        event=event,
                        state_id_counter=state_id_counter
                    )
                elif i + 1 < len(episode.events):
                    # Check if next event is in a different state
                    next_event = episode.events[i + 1]
                    if next_event.url != event.url or next_event.page_root != event.page_root:
                        causes_transition = True
                        next_state = self._get_or_create_state(
                            graph=graph,
                            event=next_event,
                            state_id_counter=state_id_counter
                        )

                if causes_transition and next_state:
                    # State transition: create Action
                    if next_state.id not in graph.states:
                        graph.add_state(next_state)
                        state_id_counter += 1

                    # Only create Action if it's actually a state transition (no self-loop)
                    if next_state.id != current_state_id:
                        action = self._create_action(
                            action_id=f"A{action_id_counter}",
                            from_state_id=current_state_id,
                            to_state_id=next_state.id,
                            event=event
                        )
                        graph.add_action(action)
                        action_id_counter += 1

                        # Update current state
                        current_state_id = next_state.id
                    else:
                        # Same state - treat as Intent
                        intent = self._create_intent(
                            intent_id=f"I{intent_id_counter}",
                            state_id=current_state_id,
                            event=event
                        )
                        graph.add_intent_to_state(current_state_id, intent)
                        intent_id_counter += 1
                else:
                    # No state transition: create Intent within current state
                    intent = self._create_intent(
                        intent_id=f"I{intent_id_counter}",
                        state_id=current_state_id,
                        event=event
                    )
                    graph.add_intent_to_state(current_state_id, intent)
                    intent_id_counter += 1

        return graph

    def _get_or_create_state(
        self,
        graph: StateActionGraph,
        event: Event,
        state_id_counter: int
    ) -> State:
        """Get existing state or create new memgraph State for event.

        Args:
            graph: Current graph
            event: Event to get state for
            state_id_counter: Counter for new state IDs

        Returns:
            memgraph State object
        """
        # Create state signature
        state_key = self._create_state_key(event)

        # Check if state already exists
        for state in graph.states.values():
            if self._create_state_key_from_state(state) == state_key:
                return state

        # Create new memgraph State
        state = State(
            id=f"S{state_id_counter}",
            page_url=event.url,
            page_title=None,  # Not available in events
            timestamp=event.timestamp,
            end_timestamp=None,  # Will be updated later if needed
            duration=None,
            intents=[],  # Will be populated as we process events
            intent_ids=[],
            user_id=self.user_id,
            session_id=self.session_id,
            attributes={
                "page_root": event.page_root,
                "dom_hash": event.dom_hash,
            },
            description=f"Page: {event.url}",  # Basic description
            embedding_vector=None  # Can be populated later with LLM
        )

        return state

    def _create_state_key(self, event: Event) -> str:
        """Create unique key for state identification.

        Args:
            event: Event

        Returns:
            State key string
        """
        key_parts = [
            event.url,
            event.page_root
        ]
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()

    def _create_state_key_from_state(self, state: State) -> str:
        """Create state key from memgraph State object.

        Args:
            state: memgraph State object

        Returns:
            State key string
        """
        page_root = state.attributes.get("page_root", "main")
        key_parts = [
            state.page_url,
            page_root
        ]
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()

    def _create_intent(
        self,
        intent_id: str,
        state_id: str,
        event: Event
    ) -> Intent:
        """Create Intent object from event (operation within state).

        Args:
            intent_id: Intent identifier
            state_id: State ID this intent belongs to
            event: Event that represents the intent

        Returns:
            memgraph Intent object
        """
        # Extract element information from event target
        target_attrs = event_target_to_intent_attrs(event.target)

        # Generate human-readable description
        description = self._generate_intent_description(event)

        return Intent(
            id=intent_id,
            state_id=state_id,
            type=event.type,  # "click", "input", "scroll"
            timestamp=event.timestamp,
            page_url=event.url,
            page_title=None,
            element_tag=target_attrs.get("element_tag"),
            xpath=target_attrs.get("xpath"),
            text=target_attrs.get("text"),
            value=event.data.get("value"),
            user_id=self.user_id,
            session_id=self.session_id,
            attributes={
                "page_root": event.page_root,
                "dom_hash": event.dom_hash,
                "raw_data": event.data,
                "aria": target_attrs.get("aria"),
                "href": target_attrs.get("href"),
                "role": target_attrs.get("role"),
            }
        )

    def _create_action(
        self,
        action_id: str,
        from_state_id: str,
        to_state_id: str,
        event: Event
    ) -> Action:
        """Create Action object from event (state transition).

        Args:
            action_id: Action identifier
            from_state_id: Source state ID
            to_state_id: Destination state ID
            event: Event that caused the transition

        Returns:
            memgraph Action object
        """
        # Classify action type for memgraph
        action_type = self._classify_action_type(event)

        # Extract target info if available
        target_attrs = event_target_to_intent_attrs(event.target) if event.target else {}

        return Action(
            source=from_state_id,
            target=to_state_id,
            type=action_type,
            timestamp=event.timestamp,
            trigger_intent_id=action_id,  # Use action_id as trigger reference
            user_id=self.user_id,
            session_id=self.session_id,
            attributes={
                "raw_action_type": event.type,
                "target_element": target_attrs,
                "data": event.data,
                "page_root": event.page_root,
            },
            weight=1.0,
            confidence=None
        )

    def _generate_intent_description(self, event: Event) -> str:
        """Generate human-readable description for Intent.

        Args:
            event: Event object

        Returns:
            Description string
        """
        action_type = event.type
        target = event.target
        data = event.data

        if action_type == "click":
            if target and target.text:
                return f"Click on '{target.text}'"
            elif target and target.role:
                return f"Click {target.role}"
            else:
                return "Click element"

        elif action_type == "input":
            value = data.get("value", "")
            field_type = data.get("field_type", "field")
            return f"Input '{value}' into {field_type}"

        elif action_type == "scroll":
            direction = data.get("direction", "down")
            distance = data.get("distance", "")
            if distance:
                return f"Scroll {direction} {distance}px"
            return f"Scroll {direction}"

        else:
            return f"{action_type.title()} action"

    def _classify_action_type(self, event: Event) -> str:
        """Classify action type for memgraph Action.

        Args:
            event: Event object

        Returns:
            Action type string (e.g., "ClickLink", "Navigate")
        """
        action_type = event.type

        if action_type == "navigation":
            return "Navigate"

        elif action_type == "click":
            target = event.target
            if target:
                if target.role == "link" or target.tag == "a":
                    return "ClickLink"
                elif target.role == "button":
                    button_text = target.text or ""
                    if "submit" in button_text.lower():
                        return "SubmitForm"
                    elif "search" in button_text.lower():
                        return "Search"
                    else:
                        return "ClickButton"
            return "Click"

        elif action_type == "input":
            return "InputTrigger"

        else:
            return action_type.title()
