"""Ontology module for memory system.

This module defines the core ontology concepts for the memory system based on
a graph-structured semantic model:

Core Concepts:
    - Domain: Represents an app or website domain (main page/homepage).
              Domains are central hub nodes connecting to all States within that app/website.

    - State: Represents a page (web) or screen (app) where the user is located.
             States are nodes in the memory graph. Each State contains multiple
             Intents representing operations performed within that location.

    - Intent: Represents an atomic operation performed within a specific State.
              Examples: ClickElement, TypeText, Scroll. Intents belong to exactly
              one State and do not cause state transitions.

    - Action: Represents a state transition (navigation) between two States.
              Actions are edges in the memory graph connecting State nodes.
              Actions must change the page_url or screen identifier.

    - Manage: Edge connecting Domain to State, tracking visit information.
              Stores visit timestamps, visit counts, and duration data.

    - CognitivePhrase: High-level behavioral pattern composed of States and Actions,
                       representing complete user workflows or task sequences.

Key Relationships:
    - One Domain manages multiple States via Manage edges (1:N)
    - One State contains multiple Intents (1:N)
    - Actions connect two different States (N:M)
    - CognitivePhrases contain multiple States connected by Actions (1:N:M)

Semantic Model:
    Domain -> Manages (via Manage edge) -> State (Location)
    State (Location) -> Contains -> Intent (Operation)
    State -> Connected by -> Action (Transition) -> State
    States + Actions -> Compose -> CognitivePhrase (Workflow)
"""

from src.cloud_backend.memgraph.ontology.action import Action, TransitionEdge
from src.cloud_backend.memgraph.ontology.cognitive_phrase import CognitivePhrase
from src.cloud_backend.memgraph.ontology.domain import Domain, Manage
from src.cloud_backend.memgraph.ontology.intent import AtomicIntent, Intent
from src.cloud_backend.memgraph.ontology.state import SemanticState, State

__all__ = [
    # Domain related
    "Domain",
    "Manage",
    # Intent related
    "Intent",
    "AtomicIntent",  # Backward compatibility
    # State related
    "State",
    "SemanticState",  # Backward compatibility
    # Action related
    "Action",
    "TransitionEdge",  # Backward compatibility
    # CognitivePhrase related
    "CognitivePhrase",
]
