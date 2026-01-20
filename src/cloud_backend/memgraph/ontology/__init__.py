"""Ontology module for memory system.

This module defines the core ontology concepts for the memory system based on
a graph-structured semantic model:

Core Concepts:
    - Domain: Represents an app or website domain (main page/homepage).
              Domains are central hub nodes connecting to all States within that app/website.

    - State: Represents an abstract page type (graph node). Multiple concrete URLs
             (PageInstances) can belong to the same State. This enables deduplication
             and semantic search on page types.

    - PageInstance: Represents a concrete URL visit. Multiple PageInstances can
                    belong to the same State (e.g., multiple product detail pages).

    - Intent: Represents an atomic operation performed within a specific State.
              Examples: ClickElement, TypeText, Scroll.

    - IntentSequence: Ordered sequence of Intents with semantic description.
                      Enables retrieval of operation flows within a State.

    - Action: Represents a state transition (navigation) between two States.
              Actions are edges in the memory graph connecting State nodes.

    - Manage: Edge connecting Domain to State, tracking visit information.

    - CognitivePhrase: High-level behavioral pattern composed of States and Actions,
                       representing complete user workflows or task sequences.

Key Relationships:
    - One Domain manages multiple States via Manage edges (1:N)
    - One State contains multiple PageInstances (1:N) - URL deduplication
    - One State contains multiple IntentSequences (1:N) - operation flows
    - Actions connect two different States (N:M)
    - CognitivePhrases contain multiple States connected by Actions (1:N:M)

Semantic Model:
    Domain -> Manages (via Manage edge) -> State (AbstractState)
    State -> Contains -> PageInstance (concrete URL)
    State -> Contains -> IntentSequence (operation flow)
    IntentSequence -> Contains -> Intent (atomic operation)
    State -> Connected by -> Action (Transition) -> State
    States + Actions -> Compose -> CognitivePhrase (Workflow)
"""

from src.cloud_backend.memgraph.ontology.action import Action, TransitionEdge
from src.cloud_backend.memgraph.ontology.cognitive_phrase import CognitivePhrase
from src.cloud_backend.memgraph.ontology.domain import Domain, Manage
from src.cloud_backend.memgraph.ontology.intent import AtomicIntent, Intent
from src.cloud_backend.memgraph.ontology.intent_sequence import IntentSequence
from src.cloud_backend.memgraph.ontology.page_instance import PageInstance
from src.cloud_backend.memgraph.ontology.state import SemanticState, State

__all__ = [
    # Domain related
    "Domain",
    "Manage",
    # Intent related
    "Intent",
    "AtomicIntent",  # Backward compatibility
    # IntentSequence related
    "IntentSequence",
    # PageInstance related
    "PageInstance",
    # State related
    "State",
    "SemanticState",  # Backward compatibility
    # Action related
    "Action",
    "TransitionEdge",  # Backward compatibility
    # CognitivePhrase related
    "CognitivePhrase",
]
