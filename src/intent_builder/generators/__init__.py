"""
Workflow generation components
"""

__all__ = [
    "WorkflowGenerator",
    "PromptBuilder",
    "MetaFlowGenerator",
]

# Lazy imports to avoid circular dependencies
def __getattr__(name):
    if name == "WorkflowGenerator":
        from .workflow_generator import WorkflowGenerator
        return WorkflowGenerator
    elif name == "PromptBuilder":
        from .prompt_builder import PromptBuilder
        return PromptBuilder
    elif name == "MetaFlowGenerator":
        from .metaflow_generator import MetaFlowGenerator
        return MetaFlowGenerator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
