"""
Core data structures for BaseAgent system
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr
import logging

logger = logging.getLogger(__name__)


# ==================== Agent Core Schemas ====================

class AgentStatus(str, Enum):
    CREATED = "created"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"


class AgentPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentConfig(BaseModel):
    name: str = Field(..., description="Agent name")
    description: str = Field(default="", description="Agent description")
    version: str = Field(default="1.0.0", description="Version")
    priority: AgentPriority = Field(default=AgentPriority.MEDIUM, description="Execution priority")

    # LLM config
    llm_provider: str = Field(default="openai", description="LLM provider")
    llm_model: str = Field(default="gpt-4o", description="LLM model")
    api_key: str = Field(default="", description="API key")

    # Tool config
    tools: List[str] = Field(default_factory=list, description="Enabled tools")

    # Feature flags
    enable_logging: bool = Field(default=True, description="Enable logging")
    enable_persistence: bool = Field(default=False, description="Enable persistence")
    enable_monitoring: bool = Field(default=False, description="Enable monitoring")

    # Execution config
    max_execution_time: int = Field(default=3600, description="Max execution time (seconds)")
    max_memory_mb: int = Field(default=1024, description="Max memory usage (MB)")
    log_level: str = Field(default="INFO", description="Log level")


class AgentState(BaseModel):
    agent_id: str = Field(..., description="Agent ID")
    status: AgentStatus = Field(default=AgentStatus.CREATED, description="Current status")

    # Time info
    created_at: datetime = Field(default_factory=datetime.now, description="Created time")
    started_at: Optional[datetime] = Field(default=None, description="Started time")
    completed_at: Optional[datetime] = Field(default=None, description="Completed time")

    # Execution info
    execution_count: int = Field(default=0, description="Execution count")
    current_task: Optional[str] = Field(default=None, description="Current task")
    current_step: Optional[str] = Field(default=None, description="Current step")
    step_index: int = Field(default=0, description="Current step index")

    # Performance info
    total_execution_time: float = Field(default=0.0, description="Total execution time")
    memory_usage_mb: float = Field(default=0.0, description="Memory usage (MB)")

    # Error info
    last_error: Optional[str] = Field(default=None, description="Last error")
    error_count: int = Field(default=0, description="Error count")


class AgentResult(BaseModel):
    success: bool = Field(..., description="Whether execution succeeded")
    data: Any = Field(default=None, description="Return data")
    message: str = Field(default="", description="Execution message")

    # Execution info
    execution_time: float = Field(default=0.0, description="Execution time (seconds)")
    task_id: Optional[str] = Field(default=None, description="Task ID")
    step_count: int = Field(default=0, description="Execution step count")

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extra metadata")
    timestamp: datetime = Field(default_factory=datetime.now, description="Execution timestamp")


# ==================== Agent-as-Step Schemas ====================

class AgentInput(BaseModel):
    data: Dict[str, Any] = Field(default_factory=dict, description="Input data")
    step_metadata: Dict[str, Any] = Field(default_factory=dict, description="Step metadata")


class AgentOutput(BaseModel):
    success: bool = Field(..., description="Whether execution succeeded")
    data: Dict[str, Any] = Field(default_factory=dict, description="Output data")
    message: str = Field(default="", description="Execution message")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata")


class AgentContext(BaseModel):
    workflow_id: str = Field(..., description="Task ID (for data isolation)")
    step_id: str = Field(..., description="Current step ID")
    user_id: str = Field(default="default_user", description="User ID")
    browser_session_id: str = Field(default="global", description="Browser session ID")

    # Data context
    variables: Dict[str, Any] = Field(default_factory=dict, description="Context variables")
    step_results: Dict[str, Any] = Field(default_factory=dict, description="Step results")

    # Execution environment
    agent_instance: Optional[Any] = Field(default=None, description="BaseAgent instance")
    tools_registry: Optional[Any] = Field(default=None, description="Tool registry")
    memory_manager: Optional[Any] = Field(default=None, description="Memory manager")

    # Execution control
    timeout: Optional[int] = Field(default=None, description="Timeout, None means no timeout")
    retry_count: int = Field(default=0, description="Retry count")

    # Logging and monitoring
    logger: Optional[Any] = Field(default=None, description="Logger")
    log_callback: Optional[Any] = Field(default=None, description="Log callback (async callable)")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Execution metrics")

    # Private field - browser session info
    _browser_session_info: Optional[Any] = PrivateAttr(default=None)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    async def get_browser_session(self):
        """Get browser session (lazy load)."""
        if not self._browser_session_info:
            browser_manager = getattr(self.agent_instance, 'browser_manager', None)

            if not browser_manager:
                error_msg = (
                    "BrowserManager is required but not found in agent_instance. "
                    "BaseAgent must be initialized with browser_manager parameter."
                )
                if self.logger:
                    self.logger.error(error_msg)
                else:
                    logger.error(error_msg)
                raise RuntimeError(error_msg)

            session = browser_manager.global_session

            if not session:
                error_msg = (
                    "Browser session not found in BrowserManager. "
                    "BrowserManager.start_browser() must be called first."
                )
                if self.logger:
                    self.logger.error(error_msg)
                else:
                    logger.error(error_msg)
                raise RuntimeError(error_msg)

            self._browser_session_info = session

            if self.logger:
                self.logger.info(
                    f"AgentContext retrieved browser session from BrowserManager"
                )
            else:
                logger.info(
                    f"AgentContext retrieved browser session from BrowserManager"
                )

        return self._browser_session_info

    async def cleanup_browser_session(self):
        """Clean up browser session reference."""
        if self._browser_session_info:
            if self.logger:
                self.logger.info(
                    "AgentContext cleanup browser session reference "
                    "(actual session managed by BrowserManager)"
                )
            else:
                logger.info(
                    "AgentContext cleanup browser session reference "
                    "(actual session managed by BrowserManager)"
                )

            self._browser_session_info = None


# ==================== Extension Schemas ====================

class InterfaceSpec(BaseModel):
    method_name: str = Field(..., description="Method name")
    description: str = Field(..., description="Method description")
    parameters: Dict[str, str] = Field(default_factory=dict, description="Parameter definitions")
    return_type: str = Field(..., description="Return type")
    is_async: bool = Field(default=False, description="Whether async")
    is_required: bool = Field(default=False, description="Whether required")
    example_usage: str = Field(default="", description="Usage example")


class ExtensionSpec(BaseModel):
    name: str = Field(..., description="Extension point name")
    description: str = Field(..., description="Extension point description")
    extension_type: str = Field(..., description="Extension type")
    parameters: Dict[str, str] = Field(default_factory=dict, description="Parameter definitions")
    how_to_extend: str = Field(..., description="How to extend")
    example: str = Field(default="", description="Extension example")


class AgentCapabilitySpec(BaseModel):
    name: str = Field(..., description="Agent name")
    description: str = Field(..., description="Agent description")
    interfaces: Dict[str, InterfaceSpec] = Field(default_factory=dict, description="Interface definitions")
    supported_tools: List[str] = Field(default_factory=list, description="Supported tools")
    extension_points: Dict[str, ExtensionSpec] = Field(default_factory=dict, description="Extension points")
