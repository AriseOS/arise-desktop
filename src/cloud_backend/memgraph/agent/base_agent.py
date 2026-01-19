"""Base Agent - Abstract base class for all agents.

Agents are responsible for executing workflows by interpreting workflow steps
and performing actions in their respective environments (browser, app, etc.).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentResult:
    """Result from agent execution.

    Attributes:
        success: Whether the execution was successful.
        steps_executed: Number of workflow steps successfully executed.
        total_steps: Total number of steps in the workflow.
        error: Error message if execution failed.
        metadata: Additional metadata about the execution.
        logs: Execution logs for debugging.
    """
    success: bool
    steps_executed: int = 0
    total_steps: int = 0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)

    def add_log(self, message: str) -> None:
        """Add a log message.

        Args:
            message: Log message to add.
        """
        self.logs.append(message)


class BaseAgent(ABC):
    """Base Agent - Abstract base class for all agents.

    An agent takes a workflow and executes it in its target environment.
    Different agents can implement execution for different environments:
    - AppAgent: Controls mobile/desktop apps
    - APIAgent: Makes API calls
    etc.

    NOTE: Browser-related agents have been removed from this module.

    Attributes:
        llm_client: LLM client for generating actions from workflow steps.
        config: Agent configuration.
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """Initialize base agent.

        Args:
            llm_client: LLM client for interpreting workflow steps.
            config: Agent-specific configuration.
        """
        self.llm_client = llm_client
        self.config = config or {}

    @abstractmethod
    def execute(self, workflow: Dict[str, Any]) -> AgentResult:
        """Execute a workflow.

        Args:
            workflow: Workflow dictionary with steps to execute.

        Returns:
            AgentResult with execution status and details.
        """
        pass

    @abstractmethod
    def setup(self) -> bool:
        """Set up the agent's environment.

        Returns:
            True if setup successful, False otherwise.
        """
        pass

    @abstractmethod
    def teardown(self) -> None:
        """Clean up the agent's environment."""
        pass

    def validate_workflow(self, workflow: Dict[str, Any]) -> bool:
        """Validate workflow format.

        Args:
            workflow: Workflow dictionary to validate.

        Returns:
            True if workflow is valid, False otherwise.
        """
        if not isinstance(workflow, dict):
            return False

        if 'steps' not in workflow:
            return False

        if not isinstance(workflow['steps'], list):
            return False

        return True


__all__ = ['BaseAgent', 'AgentResult']
