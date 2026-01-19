"""Thinker module - LLM-driven workflow processing and semantic extraction.

This module provides production-grade LLM-driven functionality to process user
workflows from web/app interactions and transform them into structured semantic
representations:

Architecture (LLM-Driven):
    1. Domain Extraction: Identify apps/websites using LLM
    2. State+Intent Extraction: Extract pages and operations using LLM
    3. Action Extraction: Identify state transitions using LLM
    4. Manage Generation: Connect domains to states with visit metadata
    5. Memory Storage: Store all structures to graph-based memory

Core Components:
    - WorkflowProcessor: Main orchestrator for the complete pipeline
    - DomainExtractor: LLM-driven domain extraction
    - StateIntentExtractor: LLM-driven state and intent extraction
    - ActionExtractor: LLM-driven action (transition) extraction
    - ManageGenerator: Domain-state connection generator
"""

# LLM-driven pipeline components
from src.cloud_backend.memgraph.thinker.action_extractor import ActionExtractor, ActionExtractionResult
from src.cloud_backend.memgraph.thinker.domain_extractor import DomainExtractor, DomainExtractionResult
from src.cloud_backend.memgraph.thinker.manage_generator import ManageGenerator, ManageGenerationResult
from src.cloud_backend.memgraph.thinker.state_intent_extractor import (
    StateIntentExtractor,
    StateIntentExtractionResult,
)
from src.cloud_backend.memgraph.thinker.workflow_processor import (
    WorkflowProcessor,
    WorkflowProcessingResult,
)

__all__ = [
    # LLM-driven pipeline
    "WorkflowProcessor",
    "WorkflowProcessingResult",
    "DomainExtractor",
    "DomainExtractionResult",
    "StateIntentExtractor",
    "StateIntentExtractionResult",
    "ActionExtractor",
    "ActionExtractionResult",
    "ManageGenerator",
    "ManageGenerationResult",
]
