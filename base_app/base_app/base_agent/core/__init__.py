"""
BaseAgent 核心模块
提供 Agent 基础框架、工作流引擎和数据结构
"""

from .base_agent import BaseAgent
from .workflow_engine import WorkflowEngine
from .schemas import (
    # Agent 相关
    AgentConfig, AgentResult, AgentState, AgentStatus, AgentPriority,
    AgentCapabilitySpec, InterfaceSpec, ExtensionSpec,
    
    # 工作流相关
    WorkflowStep, Workflow, WorkflowResult, 
    ExecutionContext, StepResult, StepType, ErrorHandling
)

__all__ = [
    # 核心类
    "BaseAgent",
    "WorkflowEngine",
    
    # Agent 数据结构
    "AgentConfig",
    "AgentResult", 
    "AgentState",
    "AgentStatus",
    "AgentPriority",
    "AgentCapabilitySpec",
    "InterfaceSpec",
    "ExtensionSpec",
    
    # 工作流数据结构
    "WorkflowStep",
    "Workflow",
    "WorkflowResult",
    "ExecutionContext",
    "StepResult", 
    "StepType",
    "ErrorHandling"
]