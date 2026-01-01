"""
Intent Builder Agents

This module contains Claude Agent SDK-based agents for workflow generation.

Main components:
- WorkflowBuilder: One-shot workflow generation from Intent sequences
- WorkflowBuilderSession: Interactive session for workflow generation and dialogue

The session-based approach supports multi-turn conversation where users can:
1. Generate initial workflow from intents
2. Ask questions about the workflow
3. Request modifications via natural language
4. Get explanations of specific steps
"""

from .workflow_builder import (
    WorkflowBuilder,
    WorkflowBuilderSession,
    GenerationResult,
    StreamEvent,
    DialogueMessage,
    SessionState,
)

__all__ = [
    "WorkflowBuilder",
    "WorkflowBuilderSession",
    "GenerationResult",
    "StreamEvent",
    "DialogueMessage",
    "SessionState",
]
