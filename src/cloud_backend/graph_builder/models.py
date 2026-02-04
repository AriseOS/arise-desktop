"""Data models for Graph Builder.

This module defines the core data structures for the Graph Builder:
- Event: Normalized browser events (internal processing)
- Phase/Episode: Intermediate segmentation structures (internal processing)
- StateActionGraph: Complete graph representation

For graph nodes and edges, we use memgraph ontology:
- State: Page states from memgraph.ontology.state
- Intent: Operations within a state from memgraph.ontology.intent
- Action: State transitions from memgraph.ontology.action
"""

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

# Import memgraph ontology for unified data model
from src.common.memory.ontology.state import State
from src.common.memory.ontology.intent import Intent
from src.common.memory.ontology.action import Action


@dataclass
class EventTarget:
    """Normalized event target information.

    Attributes:
        tag: HTML tag name (e.g., 'button', 'a')
        role: ARIA role attribute
        text: Visible text content
        aria: ARIA label
        href: Link href attribute
        xpath: XPath selector for the element
    """

    tag: Optional[str] = None
    role: Optional[str] = None
    text: Optional[str] = None
    aria: Optional[str] = None
    href: Optional[str] = None
    xpath: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values.

        Returns:
            Dictionary representation with only non-None fields.
        """
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventTarget":
        """Create EventTarget from a dictionary."""
        if isinstance(data, cls):
            return data
        return cls(**(data or {}))


@dataclass
class Event:
    """Normalized Event structure.

    All Recording Adapters must produce this structure.
    No raw XPath only allowed.

    Attributes:
        timestamp: Unix timestamp in milliseconds
        type: Event type - "click" | "input" | "scroll" | "navigation"
        url: Page URL where event occurred
        page_root: Page context - "main" | "iframe_x" | "modal_y"
        target: Optional target element information
        dom_hash: Optional DOM structure hash for deduplication
        data: Additional event-specific data (scroll distance, input value, etc.)
    """

    timestamp: int
    type: str
    url: str
    page_root: str = "main"
    target: Optional[EventTarget] = None
    dom_hash: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary representation.

        Returns:
            Dictionary with all event fields.
        """
        result = {
            "timestamp": self.timestamp,
            "type": self.type,
            "url": self.url,
            "page_root": self.page_root,
            "data": self.data
        }
        if self.target:
            result["target"] = self.target.to_dict()
        if self.dom_hash:
            result["dom_hash"] = self.dom_hash
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """Create Event from a dictionary."""
        if isinstance(data, cls):
            return data
        payload = dict(data or {})
        target = payload.get("target")
        if isinstance(target, dict):
            payload["target"] = EventTarget.from_dict(target)
        payload.setdefault("page_root", "main")
        payload.setdefault("data", {})
        return cls(**payload)


# Note: State, Intent, and Action are now imported from memgraph.ontology
# We no longer define them here to ensure a unified ontology across the codebase

# Helper function to convert EventTarget to Intent attributes
def event_target_to_intent_attrs(target: Optional['EventTarget']) -> Dict[str, Any]:
    """Convert EventTarget to Intent attributes format.

    Args:
        target: EventTarget object

    Returns:
        Dictionary with Intent-compatible attributes
    """
    if not target:
        return {}

    return {
        "element_tag": target.tag,
        "text": target.text,
        "xpath": target.xpath,
        "aria": target.aria,
        "href": target.href,
        "role": target.role
    }


@dataclass
class Phase:
    """Phase - macro-level segment.

    Split signals:
    - Strong (must split): URL path change, page_root change, reload
    - Weak (≥2 required): idle timeout, DOM similarity drop, operation type change

    Attributes:
        phase_id: Unique phase identifier (e.g., "P2")
        events: List of events in this phase
        start_url: URL at phase start
        end_url: URL at phase end
    """

    phase_id: str
    events: List[Event] = field(default_factory=list)
    start_url: str = ""
    end_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert phase to dictionary representation.

        Returns:
            Dictionary with all phase fields.
        """
        return {
            "phase_id": self.phase_id,
            "events": [e.to_dict() for e in self.events],
            "start_url": self.start_url,
            "end_url": self.end_url
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Phase":
        """Create Phase from a dictionary."""
        if isinstance(data, cls):
            return data
        payload = dict(data or {})
        raw_events = payload.get("events") or []
        payload["events"] = [
            Event.from_dict(event) if isinstance(event, dict) else event
            for event in raw_events
        ]
        payload.setdefault("start_url", "")
        payload.setdefault("end_url", "")
        return cls(**payload)


@dataclass
class Episode:
    """Episode - medium-level segment.

    Rules:
    - click/navigation → Episode boundary
    - Consecutive inputs merged
    - Noise episodes discarded

    Attributes:
        episode_id: Unique episode identifier
        events: List of events in this episode
        event_types: List of event types in this episode
        target_roles: List of target roles
        url: Page URL for this episode
    """

    episode_id: str
    events: List[Event] = field(default_factory=list)
    event_types: List[str] = field(default_factory=list)
    target_roles: List[str] = field(default_factory=list)
    url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert episode to dictionary representation.

        Returns:
            Dictionary with all episode fields.
        """
        return {
            "episode_id": self.episode_id,
            "events": [e.to_dict() for e in self.events],
            "event_types": self.event_types,
            "target_roles": self.target_roles,
            "url": self.url
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Episode":
        """Create Episode from a dictionary."""
        if isinstance(data, cls):
            return data
        payload = dict(data or {})
        raw_events = payload.get("events") or []
        payload["events"] = [
            Event.from_dict(event) if isinstance(event, dict) else event
            for event in raw_events
        ]
        payload.setdefault("event_types", [])
        payload.setdefault("target_roles", [])
        payload.setdefault("url", "")
        return cls(**payload)


@dataclass
class StateActionGraph:
    """Complete State/Action Graph using unified memgraph ontology.

    This graph now uses memgraph's semantic ontology:
    - States: Page/screen states (memgraph.ontology.State)
    - Intents: Operations within states (stored in State.intents)
    - Actions: State transitions only (memgraph.ontology.Action, no self-loops)

    Acceptance criteria:
    - Same recording → 100% identical graph
    - No loss of click/navigation events
    - All operations preserved as either Intents or Actions

    Attributes:
        states: Dictionary of State objects indexed by state.id
        actions: List of Action objects (state transitions only)
        phases: List of Phase objects (internal segmentation)
        episodes: List of Episode objects (internal segmentation)
    """

    states: Dict[str, State] = field(default_factory=dict)
    actions: List[Action] = field(default_factory=list)
    phases: List[Phase] = field(default_factory=list)
    episodes: List[Episode] = field(default_factory=list)

    def add_state(self, state: State) -> None:
        """Add or update a state.

        Args:
            state: State object to add or update
        """
        self.states[state.id] = state

    def add_action(self, action: Action) -> None:
        """Add an action (state transition).

        Args:
            action: Action object to add

        Raises:
            ValueError: If action is a self-loop (use Intent instead)
        """
        if action.source == action.target:
            raise ValueError(
                f"Cannot add self-loop action. Use Intent within State instead. "
                f"Got source=target='{action.source}'"
            )
        self.actions.append(action)

    def add_intent_to_state(self, state_id: str, intent: Intent) -> None:
        """Add an intent to a state (legacy, no-op).

        V2: Intents are tracked in IntentSequence objects, not on State directly.
        This method is kept for API compatibility but does nothing.

        Args:
            state_id: State ID
            intent: Intent object to add

        Raises:
            KeyError: If state_id not found
        """
        if state_id not in self.states:
            raise KeyError(f"State {state_id} not found in graph")

    def get_state(self, state_id: str) -> Optional[State]:
        """Get state by ID.

        Args:
            state_id: State identifier

        Returns:
            State object if found, None otherwise
        """
        return self.states.get(state_id)

    def to_dict(self) -> Dict[str, Any]:
        """Convert graph to dictionary representation.

        Returns:
            Dictionary with all graph components.
        """
        return {
            "states": {sid: s.to_dict() for sid, s in self.states.items()},
            "actions": [a.to_dict() for a in self.actions],
            "phases": [p.to_dict() for p in self.phases],
            "episodes": [ep.to_dict() for ep in self.episodes]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateActionGraph":
        """Create StateActionGraph from a dictionary.

        This supports legacy recordings that may use "edges" instead of "actions".
        """
        payload = data or {}

        # States
        raw_states = payload.get("states") or {}
        states: Dict[str, State] = {}
        if isinstance(raw_states, dict):
            for state_id, state_data in raw_states.items():
                if isinstance(state_data, State):
                    state = state_data
                else:
                    state_payload = dict(state_data or {})
                    # Backfill missing ID from the dictionary key when needed.
                    if state_id and not state_payload.get("id"):
                        state_payload["id"] = state_id
                    state = State.from_dict(state_payload)
                states[state.id] = state

        # Actions (support legacy "edges" key)
        raw_actions = payload.get("actions")
        if raw_actions is None:
            raw_actions = payload.get("edges", [])
        actions: List[Action] = []
        for action_data in raw_actions or []:
            if isinstance(action_data, Action):
                action = action_data
            else:
                action = Action.from_dict(dict(action_data or {}))
            actions.append(action)

        # Phases / Episodes
        phases = [
            Phase.from_dict(phase) if isinstance(phase, dict) else phase
            for phase in (payload.get("phases") or [])
        ]
        episodes = [
            Episode.from_dict(ep) if isinstance(ep, dict) else ep
            for ep in (payload.get("episodes") or [])
        ]

        return cls(
            states=states,
            actions=actions,
            phases=phases,
            episodes=episodes,
        )


# Export all models
__all__ = [
    # From memgraph ontology (re-exported for convenience)
    "State",
    "Intent",
    "Action",
    # Graph builder internal models
    "Event",
    "EventTarget",
    "Phase",
    "Episode",
    "StateActionGraph",
    # Helper function
    "event_target_to_intent_attrs",
]
