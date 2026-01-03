"""
Intent Builder Services

New API service layer for workflow generation.
Replaces the old MetaFlowGenerator + WorkflowGenerator flow.

Main entry points:
- WorkflowService: Unified service for workflow generation and dialogue
- ScriptPregenerationService: Pre-generates scripts for workflow steps
"""

from .workflow_service import (
    WorkflowService,
    GenerationRequest,
    GenerationResponse,
    ChatRequest,
    ChatResponse,
    GenerationStatus,
)
from .script_pregeneration_service import ScriptPregenerationService

__all__ = [
    "WorkflowService",
    "GenerationRequest",
    "GenerationResponse",
    "ChatRequest",
    "ChatResponse",
    "GenerationStatus",
    "ScriptPregenerationService",
]
