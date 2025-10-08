"""
Intent Builder - MetaFlow to Workflow Generator

从用户意图（MetaFlow）生成可执行的 BaseAgent Workflow
"""

__version__ = "0.1.0"

from .core.metaflow import MetaFlow, MetaFlowNode, LoopNode, Operation
from .generators.workflow_generator import WorkflowGenerator

__all__ = [
    "MetaFlow",
    "MetaFlowNode",
    "LoopNode",
    "Operation",
    "WorkflowGenerator",
]
