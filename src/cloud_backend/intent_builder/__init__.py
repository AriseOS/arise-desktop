"""
Intent Builder - Recording to Workflow Generator

Generates executable BaseAgent Workflows from user recordings.

Architecture:
    Recording → IntentExtractor → WorkflowBuilder (Claude Agent + Skills) → Validator → Workflow

Main entry points:
- WorkflowService: Unified API for generation and dialogue
- WorkflowBuilder: One-shot workflow generation
- WorkflowBuilderSession: Interactive session with dialogue support
"""

__version__ = "0.4.0"

# Core types
from .core.intent import Intent, generate_intent_id
from .core.intent_memory_graph import IntentMemoryGraph, IntentStorageBackend
from .core.operation import Operation
from .storage.in_memory_storage import InMemoryIntentStorage

# New workflow generation (Claude Agent SDK based)
from .agents import (
    WorkflowBuilder,
    WorkflowBuilderSession,
    GenerationResult,
    StreamEvent,
    DialogueMessage,
    SessionState,
)

# Validators
from .validators import (
    WorkflowValidator,
    FullValidationResult,
    RuleValidator,
    ValidationResult,
    SemanticValidator,
    SemanticValidationResult,
)

# Service layer
from .services import (
    WorkflowService,
    GenerationRequest,
    GenerationResponse,
    ChatRequest,
    ChatResponse,
    GenerationStatus,
)

__all__ = [
    # Core types
    "Intent",
    "generate_intent_id",
    "IntentMemoryGraph",
    "IntentStorageBackend",
    "InMemoryIntentStorage",
    "Operation",

    # Workflow generation
    "WorkflowBuilder",
    "WorkflowBuilderSession",
    "GenerationResult",
    "StreamEvent",
    "DialogueMessage",
    "SessionState",

    # Validators
    "WorkflowValidator",
    "FullValidationResult",
    "RuleValidator",
    "ValidationResult",
    "SemanticValidator",
    "SemanticValidationResult",

    # Service layer
    "WorkflowService",
    "GenerationRequest",
    "GenerationResponse",
    "ChatRequest",
    "ChatResponse",
    "GenerationStatus",
]
