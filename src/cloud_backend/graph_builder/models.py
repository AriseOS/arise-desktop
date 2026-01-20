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
from src.cloud_backend.memgraph.ontology.state import State
from src.cloud_backend.memgraph.ontology.intent import Intent
from src.cloud_backend.memgraph.ontology.action import Action


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
        """Add an intent to a state.

        Args:
            state_id: State ID
            intent: Intent object to add

        Raises:
            KeyError: If state_id not found
        """
        if state_id not in self.states:
            raise KeyError(f"State {state_id} not found in graph")

        state = self.states[state_id]
        state.intents.append(intent)
        if intent.id not in state.intent_ids:
            state.intent_ids.append(intent.id)

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
