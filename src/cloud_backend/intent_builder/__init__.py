"""
Intent Builder - MetaFlow to Workflow Generator

从用户意图（MetaFlow）生成可执行的 BaseAgent Workflow
"""

__version__ = "0.1.0"

from .core.intent import Intent, generate_intent_id
from .core.intent_memory_graph import IntentMemoryGraph, IntentStorageBackend
from .core.metaflow import MetaFlow, MetaFlowNode, LoopNode, Operation
# from .generators.workflow_generator import WorkflowGenerator  # TODO: Fix dependencies
from .storage.in_memory_storage import InMemoryIntentStorage

__all__ = [
    # Intent layer
    "Intent",
    "generate_intent_id",
    "IntentMemoryGraph",
    "IntentStorageBackend",
    "InMemoryIntentStorage",
    # MetaFlow layer
    "MetaFlow",
    "MetaFlowNode",
    "LoopNode",
    "Operation",
    # Generators
    # "WorkflowGenerator",  # TODO: Fix dependencies
]
