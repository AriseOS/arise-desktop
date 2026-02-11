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
import re
from typing import Any
from typing import Dict
from typing import List
from urllib.parse import urlparse
from urllib.parse import urlunparse

from src.common.memory.ontology.intent_sequence import IntentSequence
from src.common.memory.ontology.page_instance import PageInstance
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
        trigger_resolution_window_ms: int = 15000,
        session_id: str = None
    ):
        """Initialize Graph Builder.

        Args:
            idle_threshold_ms: Idle duration threshold
            scroll_merge_window_ms: Scroll merge window
            input_debounce_ms: Input debounce window
            hover_merge_window_ms: Hover merge window
            trigger_resolution_window_ms: Max time gap to associate a navigation
                Action with the most recent in-state Intent (e.g., prior click)
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
        self.trigger_resolution_window_ms = trigger_resolution_window_ms
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
        logger.info(f"  → {len(graph.states)} states, {len(graph.actions)} actions")

        logger.info("="*70)
        logger.info("Graph Builder Pipeline Complete")
        logger.info("="*70)

        return graph

    def _build_graph(
        self,
        episodes: List[Episode],
        phases: List
    ) -> StateActionGraph:
        """Build State/Action Graph using memgraph ontology as the standard.

        Important design decision:
        - Episodes and phases are retained as metadata only.
        - The graph is constructed from the global event stream order (memgraph standard).

        Behavior:
        - Canonical URL defines State identity (query/fragment do not split states)
        - Operations within a State → Intent objects
        - State transitions (canonical URL change) → Action edges
        - Each continuous State visit becomes one IntentSequence
        - No self-loop Actions (memgraph constraint)

        Args:
            episodes: List of episodes (metadata only)
            phases: List of phases (source of the global event stream)

        Returns:
            StateActionGraph with memgraph-compatible State/Intent/Action structure
        """
        graph = StateActionGraph(phases=phases, episodes=episodes)

        if not phases:
            return graph

        # Deterministic counters with session-scoped prefixes to avoid cross-recording collisions
        state_id_counter = 1
        intent_id_counter = 1
        action_id_counter = 1
        sequence_id_counter = 1
        instance_id_counter = 1
        # Per-state URL dedup: {state_id: set(urls)}
        seen_instance_urls_by_state: dict[str, set] = {}

        action_event_types = {"click", "input", "scroll", "navigation"}

        # Flatten the global event stream from phases (episodes are NOT used for graph topology)
        events: List[Event] = []
        for phase in phases:
            events.extend(phase.events)

        if not events:
            return graph

        # Sort by timestamp for deterministic ordering across phases
        events.sort(key=lambda e: e.timestamp)

        current_state_id: str | None = None
        active_sequence: IntentSequence | None = None
        active_sequence_state_id: str | None = None
        # Track recent intents per state to better resolve transition triggers
        last_intent_by_state: dict[str, Intent] = {}
        last_click_intent_by_state: dict[str, Intent] = {}

        def finalize_active_sequence() -> None:
            """Finalize the active IntentSequence.

            V2: IntentSequences are stored as independent graph nodes via
            IntentSequenceManager, not embedded in State objects. graph_builder
            is a legacy component and does not persist sequences.
            """
            nonlocal active_sequence, active_sequence_state_id
            active_sequence = None
            active_sequence_state_id = None

        def ensure_state(event: Event) -> State | None:
            """Get or create the canonical State for an event, adding it to the graph if needed."""
            nonlocal state_id_counter
            canonical_url = self._canonicalize_url(event.url)
            if not canonical_url or canonical_url.lower() == "unknown":
                return None

            state, is_new_state = self._get_or_create_state(
                graph=graph,
                event=event,
                state_id_counter=state_id_counter,
            )
            if is_new_state:
                graph.add_state(state)
                state_id_counter += 1
            return state

        def ensure_active_sequence(state_id: str, timestamp: int) -> IntentSequence:
            """Ensure there is an active IntentSequence for the given state visit."""
            nonlocal active_sequence, active_sequence_state_id, sequence_id_counter
            if active_sequence and active_sequence_state_id == state_id:
                return active_sequence

            finalize_active_sequence()
            sequence_id = self._make_scoped_id("SEQ", sequence_id_counter)
            active_sequence = IntentSequence(
                id=sequence_id,
                session_id=self.session_id,
                timestamp=timestamp,
                intents=[],
            )
            sequence_id_counter += 1
            active_sequence_state_id = state_id
            return active_sequence

        def add_intent(
            state: State,
            event: Event,
            extra_attributes: Dict[str, Any] | None = None,
        ) -> Intent:
            """Create an intent, attach it to the state, and append it to the active sequence."""
            nonlocal intent_id_counter
            sequence = ensure_active_sequence(state.id, event.timestamp)

            intent_id = self._make_scoped_id("I", intent_id_counter)
            intent = self._create_intent(
                intent_id=intent_id,
                state_id=state.id,
                event=event,
                page_url_override=state.page_url,
                extra_attributes=extra_attributes,
            )
            intent_id_counter += 1

            graph.add_intent_to_state(state.id, intent)
            sequence.intents.append(intent)
            return intent

        # Build states, intent sequences, and actions from the global event stream
        for event in events:
            if event.type not in action_event_types:
                continue

            event_state = ensure_state(event)
            if not event_state:
                continue

            event_canonical_url = event_state.page_url

            if current_state_id is None:
                current_state_id = event_state.id

            current_state = graph.states.get(current_state_id)
            if not current_state:
                current_state = event_state
                current_state_id = event_state.id

            # State transition is defined by canonical URL change (memgraph standard)
            is_transition = (
                current_state.page_url
                and event_canonical_url
                and current_state.page_url != event_canonical_url
            )

            if is_transition:
                # For navigation events, try to associate the transition with the
                # most recent in-state click/intent (within a time window).
                previous_candidate: Intent | None = None
                if event.type == "navigation":
                    previous_candidate = (
                        last_click_intent_by_state.get(current_state.id)
                        or last_intent_by_state.get(current_state.id)
                    )

                # Create a trigger intent in the source state that references the target URL
                trigger_attrs = {
                    "is_transition_trigger": True,
                    "transition_target_url": event.url,
                    "transition_target_canonical_url": event_canonical_url,
                }
                trigger_intent = add_intent(current_state, event, extra_attributes=trigger_attrs)
                # Update recent-intent indices for the source state
                last_intent_by_state[current_state.id] = trigger_intent
                if trigger_intent.type == "click":
                    last_click_intent_by_state[current_state.id] = trigger_intent

                def is_recent(candidate: Intent | None) -> bool:
                    """Check whether a candidate intent is recent enough to use as trigger."""
                    if not candidate:
                        return False
                    if not getattr(candidate, "timestamp", None):
                        return False
                    return (event.timestamp - candidate.timestamp) <= self.trigger_resolution_window_ms

                resolved_trigger = (
                    previous_candidate if is_recent(previous_candidate) else trigger_intent
                )

                # Update source state temporal bounds without adding incorrect instances
                current_state.end_timestamp = max(
                    current_state.end_timestamp or current_state.timestamp,
                    event.timestamp,
                )
                current_state.duration = (
                    current_state.end_timestamp - current_state.timestamp
                    if current_state.end_timestamp
                    else None
                )

                # Capture the active sequence ID before finalizing
                trigger_sequence_id = active_sequence.id if active_sequence else None

                # Finalize the source state's sequence before leaving it
                finalize_active_sequence()

                # Create action edge between states (no self-loops)
                if event_state.id != current_state.id:
                    action_id = self._make_scoped_id("A", action_id_counter)
                    action = self._create_action(
                        action_id=action_id,
                        from_state_id=current_state.id,
                        to_state_id=event_state.id,
                        event=event,
                        trigger_sequence_id=trigger_sequence_id,
                    )
                    graph.add_action(action)
                    action_id_counter += 1

                # Enter the target state and update it with the concrete URL visit
                current_state_id = event_state.id
                state_seen = seen_instance_urls_by_state.setdefault(event_state.id, set())
                instance_id_counter, pi = self._update_state_with_event_instance(
                    state=event_state,
                    event=event,
                    instance_id_counter=instance_id_counter,
                    seen_urls=state_seen,
                )
                if pi:
                    graph.page_instances.append(pi)
                continue

            # Normal in-state operation
            state_seen = seen_instance_urls_by_state.setdefault(current_state.id, set())
            instance_id_counter, pi = self._update_state_with_event_instance(
                state=current_state,
                event=event,
                instance_id_counter=instance_id_counter,
                seen_urls=state_seen,
            )
            if pi:
                graph.page_instances.append(pi)
            intent = add_intent(current_state, event)
            # Update recent-intent indices for trigger resolution
            last_intent_by_state[current_state.id] = intent
            if intent.type == "click":
                last_click_intent_by_state[current_state.id] = intent

        # Finalize any remaining sequence at end of stream
        finalize_active_sequence()

        return graph

    def _get_or_create_state(
        self,
        graph: StateActionGraph,
        event: Event,
        state_id_counter: int,
    ) -> tuple[State, bool]:
        """Get existing state or create new memgraph State for event.

        Args:
            graph: Current graph
            event: Event to get state for
            state_id_counter: Counter for new state IDs

        Returns:
            Tuple of (memgraph State object, is_new_state)
        """
        canonical_url = self._canonicalize_url(event.url)

        # Create state signature (memgraph standard: canonical URL only)
        state_key = self._create_state_key(canonical_url)

        # Check if state already exists
        for state in graph.states.values():
            if self._create_state_key_from_state(state) == state_key:
                return state, False

        # Create new memgraph State
        state_id = self._make_scoped_id("S", state_id_counter)
        domain = self._extract_domain(canonical_url)
        state = State(
            id=state_id,
            page_url=canonical_url,
            page_title=None,  # Not available in events
            timestamp=event.timestamp,
            end_timestamp=None,  # Will be updated later if needed
            duration=None,
            instances=[],
            session_id=self.session_id,
            domain=domain,
            attributes={
                "canonical_url": canonical_url,
                # page_root is metadata only (does not define state identity)
                "page_roots": [event.page_root] if event.page_root else [],
                "dom_hashes": [event.dom_hash] if event.dom_hash else [],
                "last_seen_url": event.url,
                "last_page_root": event.page_root,
                "last_dom_hash": event.dom_hash,
            },
            description=f"Page: {canonical_url}",  # Basic description
            embedding_vector=None  # Can be populated later with LLM
        )

        return state, True

    def _create_state_key(self, canonical_url: str) -> str:
        """Create unique key for state identification.

        Args:
            canonical_url: Canonicalized URL (without query/fragment)

        Returns:
            State key string
        """
        return hashlib.md5(canonical_url.encode()).hexdigest()

    def _create_state_key_from_state(self, state: State) -> str:
        """Create state key from memgraph State object.

        Args:
            state: memgraph State object

        Returns:
            State key string
        """
        canonical_url = self._canonicalize_url(state.page_url)
        return hashlib.md5(canonical_url.encode()).hexdigest()

    def _create_intent(
        self,
        intent_id: str,
        state_id: str,
        event: Event,
        page_url_override: str | None = None,
        extra_attributes: Dict[str, Any] | None = None,
    ) -> Intent:
        """Create Intent object from event (operation within state).

        Args:
            intent_id: Intent identifier
            state_id: State ID this intent belongs to
            event: Event that represents the intent
            page_url_override: Canonical page URL for the state (memgraph standard)
            extra_attributes: Additional attributes to merge into intent.attributes

        Returns:
            memgraph Intent object
        """
        # Extract element information from event target
        target_attrs = event_target_to_intent_attrs(event.target)

        # Generate human-readable description
        description = self._generate_intent_description(event)

        canonical_event_url = self._canonicalize_url(event.url)
        intent_page_url = page_url_override or canonical_event_url

        attributes = {
            "canonical_event_url": canonical_event_url,
            "original_event_url": event.url,
            # page_root is metadata only
            "page_root": event.page_root,
            "dom_hash": event.dom_hash,
            "raw_data": event.data,
            "aria": target_attrs.get("aria"),
            "href": target_attrs.get("href"),
            "role": target_attrs.get("role"),
        }
        if extra_attributes:
            attributes.update(extra_attributes)

        # Store legacy xpath-based fields in attributes (Intent model uses ref-based format)
        if target_attrs.get("element_tag"):
            attributes["element_tag"] = target_attrs["element_tag"]
        if target_attrs.get("xpath"):
            attributes["xpath"] = target_attrs["xpath"]

        return Intent(
            id=intent_id,
            state_id=state_id,
            type=event.type,  # "click", "input", "scroll"
            timestamp=event.timestamp,
            page_url=intent_page_url,
            page_title=None,
            element_role=target_attrs.get("role"),
            text=target_attrs.get("text"),
            value=event.data.get("value"),
            session_id=self.session_id,
            description=description,
            attributes=attributes
        )

    def _create_action(
        self,
        action_id: str,
        from_state_id: str,
        to_state_id: str,
        event: Event,
        trigger_sequence_id: str | None = None,
    ) -> Action:
        """Create Action object from event (state transition).

        Args:
            action_id: Action identifier
            from_state_id: Source state ID
            to_state_id: Destination state ID
            event: Event that caused the transition
            trigger_sequence_id: ID of the IntentSequence that triggered this transition

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
            trigger_sequence_id=trigger_sequence_id,
            session_id=self.session_id,
            attributes={
                "action_id": action_id,
                "raw_action_type": event.type,
                "target_element": target_attrs,
                "data": event.data,
                "page_root": event.page_root,
                "canonical_event_url": self._canonicalize_url(event.url),
                "original_event_url": event.url,
            },
            weight=1.0,
            confidence=None
        )

    def _update_state_with_event_instance(
        self,
        state: State,
        event: Event,
        instance_id_counter: int,
        seen_urls: set,
    ) -> tuple[int, "PageInstance | None"]:
        """Update a State with concrete URL metadata from an event.

        PageInstances are collected independently (not nested in State).

        Args:
            state: State to update
            event: Event providing concrete URL and metadata
            instance_id_counter: Counter for deterministic PageInstance IDs
            seen_urls: Set of URLs already added as PageInstances (for dedup)

        Returns:
            Tuple of (updated instance_id_counter, PageInstance or None)
        """
        if state.attributes is None:
            state.attributes = {}

        # Update temporal bounds
        state.end_timestamp = max(state.end_timestamp or event.timestamp, event.timestamp)
        state.duration = (state.end_timestamp - state.timestamp) if state.end_timestamp else None

        # Track page_root/dom_hash as metadata only
        page_roots = state.attributes.setdefault("page_roots", [])
        if event.page_root and event.page_root not in page_roots:
            page_roots.append(event.page_root)

        dom_hashes = state.attributes.setdefault("dom_hashes", [])
        if event.dom_hash and event.dom_hash not in dom_hashes:
            dom_hashes.append(event.dom_hash)

        state.attributes["last_seen_url"] = event.url
        state.attributes["last_page_root"] = event.page_root
        state.attributes["last_dom_hash"] = event.dom_hash
        state.attributes["canonical_url"] = state.page_url
        # Backward compatibility: keep single-value fields alongside history lists
        if event.page_root:
            state.attributes["page_root"] = event.page_root
        if event.dom_hash:
            state.attributes["dom_hash"] = event.dom_hash

        # Create PageInstance for this concrete URL visit (dedup by URL string)
        created_instance = None
        if event.url and event.url not in seen_urls:
            instance_id = self._make_scoped_id("PI", instance_id_counter)
            created_instance = PageInstance(
                id=instance_id,
                url=event.url,
                page_title=None,
                timestamp=event.timestamp,
                session_id=self.session_id,
            )
            # Tag with parent state ID
            created_instance._parent_state_id = state.id
            seen_urls.add(event.url)
            instance_id_counter += 1

        return instance_id_counter, created_instance

    def _make_scoped_id(self, prefix: str, counter: int) -> str:
        """Create deterministic, session-scoped IDs to avoid cross-recording collisions."""
        session_prefix = self._session_prefix()
        return f"{prefix}_{session_prefix}_{counter}"

    def _session_prefix(self) -> str:
        """Get a short, stable session prefix for ID scoping."""
        if not self.session_id:
            return "session"

        sanitized = re.sub(r"[^A-Za-z0-9]+", "", self.session_id)
        # Use a low-collision prefix: readable tail + deterministic hash suffix
        readable = sanitized[-8:] if sanitized else "session"
        hash_part = hashlib.md5(self.session_id.encode()).hexdigest()[:6]
        return f"{readable}_{hash_part}"

    def _canonicalize_url(self, url: str) -> str:
        """Canonicalize URL for State identity.

        Rules (as agreed):
        - query params and fragments do NOT define state identity
        - page_root is metadata only
        """
        if not url:
            return ""

        try:
            parsed = urlparse(url)

            # If parsing yields no scheme/netloc, treat as opaque and return as-is
            if not parsed.scheme and not parsed.netloc:
                base = url.split("#", 1)[0]
                base = base.split("?", 1)[0]
                return base or url

            scheme = parsed.scheme.lower()
            netloc = parsed.netloc.lower()
            path = parsed.path or "/"

            # Drop params, query, and fragment
            return urlunparse((scheme, netloc, path, "", "", ""))
        except Exception:
            return url

    def _extract_domain(self, url: str) -> str | None:
        """Extract domain from URL for memgraph State.domain."""
        try:
            parsed = urlparse(url)
            return parsed.netloc or None
        except Exception:
            return None

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
