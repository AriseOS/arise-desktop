"""
Claude Agent Provider implementation

This provider wraps the Claude Agent SDK to provide multi-turn iterative
code generation capabilities. Unlike AnthropicProvider which handles single-turn
conversations, this provider enables Claude to:
- Generate code files
- Test the generated code
- Analyze errors and iteratively fix issues
- Use tools like Read, Write, Edit, Bash, and Glob

Primary use case: ScraperAgent script generation with iterative refinement
"""

import os
import logging
from pathlib import Path
from typing import Optional, List, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from src.base_app.base_app.server.core.config_service import ConfigService

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """
    Result of Claude Agent execution

    Attributes:
        success: Whether the task completed successfully
        iterations: Number of iterations Claude performed
        error: Error message if task failed
    """
    success: bool
    iterations: int
    error: Optional[str] = None


class ClaudeAgentProvider:
    """
    Claude Agent SDK wrapper for multi-turn iterative tasks

    This provider does NOT inherit from BaseProvider because it has fundamentally
    different semantics - it performs multi-turn iterative execution rather than
    single request-response cycles.

    Design principles:
    - Stateless: No instance state, all data in working_dir
    - Simple: Minimal configuration, focus on core functionality
    - Flexible: Configurable tools and iteration limits per task
    """

    def __init__(
        self,
        config_service: Optional["ConfigService"] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        Initialize Claude Agent Provider

        Args:
            config_service: ConfigService instance to read configuration
            api_key: Anthropic API key (overrides config/env if provided)
            model: Claude model to use (overrides config if provided)

        Raises:
            ValueError: If API key cannot be found in config, env, or parameters
        """
        # Priority: parameter > config > environment variable
        if api_key:
            self.api_key = api_key
        elif config_service:
            # Read from config: claude_agent.api_key (fallback to agent.llm.api_key)
            self.api_key = (
                config_service.get("claude_agent.api_key") or
                config_service.get("agent.llm.api_key") or
                os.environ.get("ANTHROPIC_API_KEY")
            )
        else:
            self.api_key = os.environ.get("ANTHROPIC_API_KEY")

        if not self.api_key:
            raise ValueError(
                "Anthropic API key not provided. Please either:\n"
                "1. Pass api_key parameter, or\n"
                "2. Set claude_agent.api_key in baseapp.yaml, or\n"
                "3. Set ANTHROPIC_API_KEY environment variable"
            )

        # Get model configuration
        if model:
            self.model = model
        elif config_service:
            self.model = (
                config_service.get("claude_agent.model") or
                "claude-sonnet-4-5"
            )
        else:
            self.model = "claude-sonnet-4-5"

        logger.info(f"Initialized ClaudeAgentProvider with model {self.model}")

    async def run_task(
        self,
        prompt: str,
        working_dir: Path,
        max_iterations: int = 50,
        tools: Optional[List[str]] = None
    ) -> AgentResult:
        """
        Execute a task using Claude Agent SDK with multi-turn iteration

        Claude will:
        1. Read the prompt and any existing files in working_dir
        2. Generate/modify files using Write/Edit tools
        3. Test the code using Bash tool
        4. Analyze errors and iteratively fix issues
        5. Repeat until success or max_iterations reached

        Args:
            prompt: Task description for Claude (should include requirements,
                   context files, expected output format, etc.)
            working_dir: Directory where Claude can read/write files
            max_iterations: Maximum number of iterations (default: 5)
            tools: List of tools Claude can use. Default: ["Read", "Write", "Edit", "Bash", "Glob"]

        Returns:
            AgentResult with success status, iteration count, and any error message

        Raises:
            ValueError: If working_dir doesn't exist or isn't accessible
            RuntimeError: If Claude SDK encounters system errors (network, API limits, etc.)
        """
        # Validate working directory
        working_dir = Path(working_dir)
        if not working_dir.exists():
            raise ValueError(f"Working directory does not exist: {working_dir}")
        if not working_dir.is_dir():
            raise ValueError(f"Working directory is not a directory: {working_dir}")

        # Set default tools if not specified
        if tools is None:
            tools = ["Read", "Write", "Edit", "Bash", "Glob"]

        logger.info(
            f"Starting Claude Agent task in {working_dir} "
            f"with max_turns={max_iterations}"
        )

        try:
            # Import Claude SDK here to avoid import errors if SDK not installed
            from claude_agent_sdk import (
                query,
                ClaudeAgentOptions,
                ResultMessage,
                AssistantMessage,
                UserMessage,
                SystemMessage,
                TextBlock,
                ToolUseBlock,
                ToolResultBlock
            )

            # Configure SDK options using ClaudeAgentOptions class
            options = ClaudeAgentOptions(
                model=self.model,
                cwd=str(working_dir),
                max_turns=max_iterations,
                allowed_tools=tools,
                permission_mode="acceptEdits",
                # Pass API key through env dict to the subprocess
                env={"ANTHROPIC_API_KEY": self.api_key}
            )

            # Execute the query
            turn_count = 0
            final_success = False
            last_result_message = None

            async for message in query(prompt=prompt, options=options):
                # Count assistant turns
                if isinstance(message, AssistantMessage):
                    turn_count += 1

                # ResultMessage indicates task completion
                if isinstance(message, ResultMessage):
                    last_result_message = message
                    final_success = not message.is_error
                    logger.info(f"Claude Agent completed: success={final_success}, turns={message.num_turns}, duration={message.duration_ms/1000:.1f}s")

            # If we got a result message, use its data
            if last_result_message:
                return AgentResult(
                    success=final_success,
                    iterations=last_result_message.num_turns,
                    error=last_result_message.result if not final_success else None
                )

            # Fallback if no result message received
            return AgentResult(
                success=False,
                iterations=turn_count,
                error="No result message received from Claude SDK"
            )

        except ImportError as e:
            error_msg = (
                "Claude Agent SDK not installed. "
                "Please install with: pip install claude-agent-sdk"
            )
            logger.error(f"{error_msg}: {e}")
            raise RuntimeError(error_msg) from e

        except Exception as e:
            # System errors (network, API limits, etc.) are raised as exceptions
            error_msg = f"Claude SDK error: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
