"""
BaseAgent 核心模块
提供 Agent 基础框架、工作流引擎和数据结构
"""

from .base_agent import BaseAgent
from .agent_workflow_engine import AgentWorkflowEngine
from .schemas import (
    # Agent 相关
    AgentConfig, AgentResult, AgentState, AgentStatus, AgentPriority,
    AgentCapabilitySpec, InterfaceSpec, ExtensionSpec,
    
    # 工作流相关
    AgentWorkflowStep, Workflow, WorkflowResult, 
    ExecutionContext, StepResult, StepType, ErrorHandling
)

__all__ = [
    # 核心类
    "BaseAgent",
    "AgentWorkflowEngine",
    
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
    "AgentWorkflowStep",
    "Workflow",
    "WorkflowResult",
    "ExecutionContext",
    "StepResult", 
    "StepType",
    "ErrorHandling"
]