"""Reasoner Layer Prompts

Layer 5 的所有 LLM Prompt 模块
"""

from src.common.memory.reasoner.prompts.cognitive_phrase_match_prompt import (
    CognitivePhraseMatchInput,
    CognitivePhraseMatchOutput,
    CognitivePhraseMatchPrompt,
)
from src.common.memory.reasoner.prompts.state_satisfaction_prompt import (
    StateSatisfactionInput,
    StateSatisfactionOutput,
    StateSatisfactionPrompt,
)
from src.common.memory.reasoner.prompts.task_decomposition_prompt import (
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
