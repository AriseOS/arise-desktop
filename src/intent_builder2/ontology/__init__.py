"""Ontology module for memory system.

This module defines the core ontology concepts for the memory system:
- Intent: Atomic intent unit extracted from browser or APP events
- State: State composed of multiple Intents
- Action: Action that connects two States as edges
- CognitivePhrase: Cognitive phrase composed of States and Actions
"""

from src.ontology.action import Action
from src.ontology.action import TransitionEdge
from src.ontology.cognitive_phrase import CognitivePhrase
from src.ontology.intent import AtomicIntent
from src.ontology.intent import AtomicIntentType
from src.ontology.intent import Intent
from src.ontology.intent import IntentType
from src.ontology.state import SemanticState
from src.ontology.state import SemanticStateType
from src.ontology.state import State
from src.ontology.state import StateType

__all__ = [
    # Intent related
    'Intent',
    'IntentType',
    'AtomicIntent',  # Backward compatibility
    'AtomicIntentType',  # Backward compatibility
    # State related
    'State',
    'StateType',
    'SemanticState',  # Backward compatibility
    'SemanticStateType',  # Backward compatibility
    # Action related
    'Action',
    'TransitionEdge',  # Backward compatibility
    # CognitivePhrase related
    'CognitivePhrase',
]
