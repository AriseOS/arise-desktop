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
from typing import Optional, List, AsyncIterator, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from src.common.config_service import ConfigService

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


@dataclass
class StreamEvent:
    """Streaming event from Claude Agent SDK"""
    type: str  # "text", "tool_use", "tool_result", "thinking", "complete", "error"
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    turn: Optional[int] = None


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
        model: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        """
        Initialize Claude Agent Provider

        Args:
            config_service: ConfigService instance to read configuration
            api_key: Anthropic API key (overrides config/env if provided)
            model: Claude model to use (overrides config if provided)
            base_url: Custom base URL for API proxy (e.g., https://api.ariseos.com)

        Raises:
            ValueError: If API key cannot be found in config, env, or parameters
        """
        # Get base_url configuration
        # Priority: parameter > config > environment variable
        if base_url:
            self.base_url = base_url
        elif config_service:
            # Read from config: llm.proxy_url (same as AnthropicProvider)
            self.base_url = config_service.get("llm.proxy_url")
        else:
            self.base_url = None

        # Get API key configuration
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
                config_service.get("llm.model") or  # Fallback to llm.model (same as AnthropicProvider)
                "claude-sonnet-4-5"
            )
        else:
            self.model = "claude-sonnet-4-5"

        logger.info(f"Initialized ClaudeAgentProvider:")
        logger.info(f"  Model: {self.model}")
        logger.info(f"  Base URL: {self.base_url if self.base_url else '(using default Anthropic endpoint)'}")
        logger.info(f"  API Key: {self.api_key[:10]}..." if self.api_key else "  API Key: (not set)")

    async def run_task(
        self,
        prompt: str,
        working_dir: Path,
        max_iterations: int = 100,
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
            max_iterations: Maximum number of iterations (default: 100)
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
                ClaudeSDKClient,  # Use ClaudeSDKClient instead of query()
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
            # Start with current environment variables (to inherit ANTHROPIC_LOG, etc.)
            env_vars = dict(os.environ)

            # Set our specific API key (override if exists in environment)
            env_vars["ANTHROPIC_API_KEY"] = self.api_key

            # Add ANTHROPIC_BASE_URL for API proxy if configured
            if self.base_url:
                env_vars["ANTHROPIC_BASE_URL"] = self.base_url
                logger.info(f"Using API Proxy base URL for Claude SDK: {self.base_url}")

            # Log if debug mode is enabled
            if env_vars.get("ANTHROPIC_LOG") == "debug":
                logger.info("ANTHROPIC_LOG=debug is set, SDK will output detailed logs")

            # Stderr callback to capture SDK internal logs
            def stderr_callback(line: str):
                """Capture stderr from Claude SDK subprocess"""
                # Always log stderr, even if empty
                if line and line.strip():
                    logger.warning(f"[Claude SDK stderr] {line.strip()}")
                else:
                    logger.debug(f"[Claude SDK stderr] (empty line)")

            options = ClaudeAgentOptions(
                model=self.model,
                cwd=str(working_dir),
                max_turns=max_iterations,
                allowed_tools=tools,
                permission_mode="bypassPermissions",  # Bypass permission checks to avoid async issues
                # Pass environment variables to the subprocess
                env=env_vars,
                # Capture stderr output
                stderr=stderr_callback,
                # Increase buffer size to prevent blocking (default is 65536)
                max_buffer_size=1024 * 1024  # 1MB buffer
            )

            # Execute the query
            turn_count = 0
            final_success = False
            last_result_message = None
            last_assistant_message = None

            logger.info("Starting to iterate over Claude SDK messages...")
            logger.info(f"Prompt length: {len(prompt)} characters")
            logger.info(f"Working directory: {working_dir}")
            logger.info(f"Model: {self.model}")
            logger.info(f"API key (first 10 chars): {self.api_key[:10]}...")
            logger.info(f"Base URL: {self.base_url}")
            logger.info("NOTE: Messages may arrive in batches after each turn completes. Please wait...")

            # Add timeout tracking
            import time
            last_message_time = time.time()
            message_count = 0
            start_time = time.time()

            # Add overall timeout to prevent infinite hanging
            import asyncio

            try:
                # Wrap everything in a timeout
                async with asyncio.timeout(max_iterations * 30):  # 30 seconds per iteration
                    # Use ClaudeSDKClient context manager (correct API)
                    async with ClaudeSDKClient(options=options) as client:
                        # Send the query
                        await client.query(prompt)
                        logger.info("Query sent to Claude SDK")

                        # Receive response messages
                        async for message in client.receive_response():
                            message_count += 1
                            current_time = time.time()
                            time_since_last = current_time - last_message_time
                            last_message_time = current_time

                            # Log all message types for debugging
                            msg_type = type(message).__name__
                            logger.info(f"📨 Received message #{message_count} (after {time_since_last:.1f}s): {msg_type}")

                            # Count assistant turns
                            if isinstance(message, AssistantMessage):
                                turn_count += 1
                                last_assistant_message = message
                                logger.info(f"🤖 AssistantMessage #{turn_count}")

                                # Log assistant message content
                                if hasattr(message, 'content'):
                                    for i, block in enumerate(message.content):
                                        if isinstance(block, TextBlock):
                                            text_preview = block.text[:200] if len(block.text) > 200 else block.text
                                            logger.info(f"   Text block {i}: {text_preview}...")
                                        elif isinstance(block, ToolUseBlock):
                                            logger.info(f"   Tool use block {i}: {block.name}")

                            # User message
                            if isinstance(message, UserMessage):
                                logger.info(f"👤 UserMessage received")

                            # System message
                            if isinstance(message, SystemMessage):
                                logger.info(f"⚙️  SystemMessage received")
                                logger.info(f"   Subtype: {message.subtype}")
                                logger.info(f"   Data: {message.data}")

                            # ResultMessage indicates task completion
                            if isinstance(message, ResultMessage):
                                last_result_message = message
                                final_success = not message.is_error
                                logger.info(f"✅ Claude Agent completed: success={final_success}, turns={message.num_turns}, duration={message.duration_ms/1000:.1f}s")
                                if not final_success:
                                    logger.error(f"   Error result: {message.result}")

                        logger.info("Query iteration completed normally")
            except Exception as query_error:
                logger.error(f"Error during query iteration: {query_error}", exc_info=True)
                raise

            total_duration = time.time() - start_time
            logger.info(f"Finished iterating messages after {total_duration:.1f}s. Total messages: {message_count}, assistant turns: {turn_count}")

            # If we got a result message, use its data
            if last_result_message:
                return AgentResult(
                    success=final_success,
                    iterations=last_result_message.num_turns,
                    error=last_result_message.result if not final_success else None
                )

            # Fallback: if we got assistant messages but no result message
            # This might happen if Claude finished normally but SDK didn't send ResultMessage
            if last_assistant_message:
                logger.warning(f"No ResultMessage received, but got {turn_count} assistant turns.")
                logger.info("Checking if task completed successfully by examining workspace...")

                # Check if script was actually generated
                script_file = working_dir / "extraction_script.py"
                if script_file.exists():
                    logger.info(f"✅ Script file found at {script_file}, treating as success")
                    return AgentResult(
                        success=True,
                        iterations=turn_count,
                        error=None
                    )
                else:
                    logger.warning(f"❌ Script file not found at {script_file}, treating as failure")
                    return AgentResult(
                        success=False,
                        iterations=turn_count,
                        error="Script file was not generated"
                    )

            # No messages at all - this is a problem
            logger.error("No messages received from Claude SDK")
            logger.info("This might indicate a problem with SDK subprocess or API connectivity")
            return AgentResult(
                success=False,
                iterations=0,
                error="No messages received from Claude SDK. Check logs for subprocess errors."
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

    async def run_task_stream(
        self,
        prompt: str,
        working_dir: Path,
        max_iterations: int = 100,
        tools: Optional[List[str]] = None,
        enable_skills: bool = False
    ) -> AsyncIterator[StreamEvent]:
        """Execute a task using Claude Agent SDK with real-time streaming"""
        working_dir = Path(working_dir)
        if not working_dir.exists() or not working_dir.is_dir():
            raise ValueError(f"Invalid working directory: {working_dir}")

        if tools is None:
            tools = ["Read", "Write", "Edit", "Bash", "Glob"]

        # Add "Skill" tool if skills are enabled
        if enable_skills and "Skill" not in tools:
            tools = tools + ["Skill"]
            logger.info("🎯 SDK Skills enabled - adding 'Skill' to allowed_tools")

        try:
            from claude_agent_sdk import (
                ClaudeSDKClient,
                ClaudeAgentOptions,
                ResultMessage,
                AssistantMessage,
                SystemMessage,
                TextBlock,
                ToolUseBlock
            )

            env_vars = dict(os.environ)
            env_vars["ANTHROPIC_API_KEY"] = self.api_key
            if self.base_url:
                env_vars["ANTHROPIC_BASE_URL"] = self.base_url

            # Configure options
            options = ClaudeAgentOptions(
                model=self.model,
                cwd=str(working_dir),
                max_turns=max_iterations,
                allowed_tools=tools,
                permission_mode="bypassPermissions",
                env=env_vars,
                max_buffer_size=1024 * 1024
            )

            # Enable skills if requested
            if enable_skills:
                options.setting_sources = ["project"]  # Load skills from .claude/skills/
                logger.info("=" * 80)
                logger.info("🎯 Claude Agent SDK Skills Configuration")
                logger.info(f"   setting_sources: ['project']")
                logger.info(f"   Skills directory: {working_dir}/.claude/skills/")
                logger.info(f"   Allowed tools: {tools}")
                logger.info("   SDK will auto-discover skills from .claude/skills/ directory")
                logger.info("=" * 80)

            turn_count = 0
            yield StreamEvent(type="thinking", content="Initializing Claude Agent...", turn=0)

            import asyncio
            async with asyncio.timeout(max_iterations * 30):
                async with ClaudeSDKClient(options=options) as client:
                    await client.query(prompt)
                    logger.info("Query sent to Claude SDK, streaming responses...")

                    async for message in client.receive_response():
                        if isinstance(message, AssistantMessage):
                            turn_count += 1
                            logger.info(f"🤖 AssistantMessage #{turn_count}")

                            if hasattr(message, 'content'):
                                for block in message.content:
                                    if isinstance(block, TextBlock):
                                        # Log full text content without truncation
                                        logger.info(f"   [Turn {turn_count}] Text: {block.text}")
                                        yield StreamEvent(
                                            type="text",
                                            content=block.text,
                                            turn=turn_count
                                        )
                                    elif isinstance(block, ToolUseBlock):
                                        # Log tool name and full input parameters
                                        tool_input = block.input if hasattr(block, 'input') else {}
                                        logger.info(f"   [Turn {turn_count}] Tool use: {block.name}")

                                        # For Bash tool, show the command explicitly
                                        if block.name == "Bash" and 'command' in tool_input:
                                            logger.info(f"      Command: {tool_input['command']}")
                                        # For Read tool, show the file path
                                        elif block.name == "Read" and 'file_path' in tool_input:
                                            logger.info(f"      File: {tool_input['file_path']}")
                                        # For Edit tool, show file path and change summary
                                        elif block.name == "Edit" and 'file_path' in tool_input:
                                            logger.info(f"      File: {tool_input['file_path']}")
                                            if 'old_string' in tool_input:
                                                old_preview = tool_input['old_string'][:100].replace('\n', '\\n')
                                                logger.info(f"      Old: {old_preview}...")
                                        # For other tools, show all input
                                        else:
                                            logger.info(f"      Input: {tool_input}")

                                        yield StreamEvent(
                                            type="tool_use",
                                            tool_name=block.name,
                                            tool_input=tool_input,
                                            turn=turn_count
                                        )

                        elif isinstance(message, SystemMessage):
                            logger.info(f"⚙️  SystemMessage: {message.subtype}")
                            if message.subtype == 'init':
                                yield StreamEvent(type="thinking", content="Claude Agent initialized", turn=0)

                        elif isinstance(message, ResultMessage):
                            logger.info(
                                f"✅ Claude Agent completed: success={not message.is_error}, "
                                f"turns={message.num_turns}, duration={message.duration_ms/1000:.1f}s"
                            )
                            if message.is_error:
                                yield StreamEvent(
                                    type="error",
                                    content=message.result or "Unknown error",
                                    turn=message.num_turns
                                )
                            else:
                                yield StreamEvent(
                                    type="complete",
                                    content=f"Task completed successfully in {message.num_turns} turns",
                                    turn=message.num_turns
                                )

        except ImportError as e:
            logger.error(f"Claude Agent SDK not installed: {e}")
            yield StreamEvent(type="error", content="Claude Agent SDK not installed", turn=0)

        except Exception as e:
            logger.error(f"Claude SDK error: {e}", exc_info=True)
            yield StreamEvent(type="error", content=str(e), turn=0)
