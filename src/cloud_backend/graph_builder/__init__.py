"""
Graph Builder - LLM-free Recording to Graph conversion using unified memgraph ontology

This module converts raw browser recordings into structured State/Action Graphs
using purely deterministic rules (NO LLM).

NEW: Now uses memgraph ontology for unified data model:
- States contain Intents (operations within state)
- Actions represent state transitions only (no self-loops)
- Direct compatibility with WorkflowMemory storage

Design principles:
- 100% deterministic (same recording → same graph)
- Rule-based only (no AI/LLM)
- No semantic understanding
- No business logic
- Pure structural compression
- Unified ontology with memgraph

Based on: /design.md Section 3
"""

# Export memgraph ontology models
from .models import Action
from .models import Intent
from .models import State

# Export graph_builder specific models
from .models import Event
from .models import EventTarget
from .models import Phase
from .models import Episode
from .models import StateActionGraph

# Export pipeline components
from .normalizer import EventNormalizer
from .noise_reducer import NoiseReducer
from .phase_segmenter import PhaseSegmenter
from .episode_segmenter import EpisodeSegmenter
from .graph_builder import GraphBuilder

__all__ = [
    # Memgraph ontology (unified models)
    "State",
    "Intent",
    "Action",
    # Graph builder internal models
    "Event",
    "EventTarget",
    "Phase",
    "Episode",
    "StateActionGraph",
    # Pipeline components
    "EventNormalizer",
    "NoiseReducer",
    "PhaseSegmenter",
    "EpisodeSegmenter",
    "GraphBuilder",
]
