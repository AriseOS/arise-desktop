"""Reasoner Layer Prompts

Layer 5 的所有 LLM Prompt 模块
"""

from src.cloud_backend.memgraph.reasoner.prompts.cognitive_phrase_match_prompt import (
    CognitivePhraseMatchInput,
    CognitivePhraseMatchOutput,
    CognitivePhraseMatchPrompt,
)
from src.cloud_backend.memgraph.reasoner.prompts.state_satisfaction_prompt import (
    StateSatisfactionInput,
    StateSatisfactionOutput,
    StateSatisfactionPrompt,
)
from src.cloud_backend.memgraph.reasoner.prompts.task_decomposition_prompt import (
    TaskDecompositionInput,
    TaskDecompositionOutput,
    TaskDecompositionPrompt,
    TaskNode,
)

__all__ = [
    # New prompts for Reasoner-based retrieval
    "CognitivePhraseMatchPrompt",
    "CognitivePhraseMatchInput",
    "CognitivePhraseMatchOutput",
    "TaskDecompositionPrompt",
    "TaskDecompositionInput",
    "TaskDecompositionOutput",
    "TaskNode",
    "StateSatisfactionPrompt",
    "StateSatisfactionInput",
    "StateSatisfactionOutput",
]
