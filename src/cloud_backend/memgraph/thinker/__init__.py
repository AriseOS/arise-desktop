"""Thinker module - URL-based workflow processing and semantic extraction.

This module provides URL-based workflow processing functionality to transform
user workflows from web/app interactions into structured semantic representations.

New Architecture (URL-based):
    1. Parse and validate input events
    2. Segment events by URL (split by navigate events)
    3. For each segment:
       - Find or create State using URL index (real-time merge)
       - Add PageInstance (concrete URL visit)
       - Create IntentSequence (ordered operations)
    4. Create Actions between adjacent segments
    5. Extract Domains and create Manage edges
    6. Generate descriptions using LLM
    7. Generate embeddings batch
    8. Store all structures to memory

Core Components:
    - WorkflowProcessor: Main orchestrator for the complete pipeline
    - URLSegment: Represents events that occurred on the same URL
    - WorkflowProcessingResult: Contains all extracted structures
"""

from src.cloud_backend.memgraph.thinker.workflow_processor import (
    URLSegment,
    WorkflowProcessor,
    WorkflowProcessingResult,
)

__all__ = [
    "WorkflowProcessor",
    "WorkflowProcessingResult",
    "URLSegment",
]
