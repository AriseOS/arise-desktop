"""
Intent Builder Agent - Main agent class for multi-turn MetaFlow and Workflow generation
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional, AsyncIterator, TYPE_CHECKING
from dataclasses import dataclass

from src.intent_builder.validators.yaml_validator import WorkflowYAMLValidator
from .system_prompt import get_system_prompt

if TYPE_CHECKING:
    from src.common.config_service import ConfigService

logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    """SSE streaming event from IntentBuilderAgent"""
    type: str  # "thinking", "tool_use", "tool_result", "text", "complete", "error"
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    result: Optional[dict] = None

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization"""
        data = {"type": self.type}
        if self.content:
            data["content"] = self.content
        if self.tool_name:
            data["tool_name"] = self.tool_name
        if self.tool_input:
            data["tool_input"] = self.tool_input
        if self.result:
            data["result"] = self.result
        return data


class IntentBuilderAgent:
    """
    Multi-turn conversational agent for generating MetaFlow and Workflow.

    This agent guides users through two phases:
    1. MetaFlow Generation - creating intent flow from user operations
    2. Workflow Generation - converting MetaFlow to executable workflow

    The agent reads domain knowledge from documentation and uses tools
    (Read, Write, Edit, Bash) to generate and modify files.
    """

    def __init__(
        self,
        working_dir: str,
        user_operations_path: str = None,
        intent_graph_path: str = None,
        config_service: Optional["ConfigService"] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        user_api_key: Optional[str] = None
    ):
        """
        Initialize Intent Builder Agent.

        Args:
            working_dir: Working directory for generated files
            user_operations_path: Path to user operations JSON
            intent_graph_path: Path to intent graph JSON
            config_service: ConfigService instance to read configuration
            api_key: Anthropic API key (overrides config/env if provided) - DEPRECATED, use user_api_key
            model: Claude model to use (overrides config if provided)
            user_api_key: User's Ami API key for API Proxy (preferred method)
        """
        self.working_dir = Path(working_dir)
        self.user_operations_path = user_operations_path
        self.intent_graph_path = intent_graph_path
        self.config_service = config_service

        # API key priority: user_api_key > api_key parameter > config > environment variable
        # user_api_key: Ami API key for API Proxy (ami_xxxxx format)
        # api_key: Legacy Anthropic API key (fallback when API Proxy is disabled)
        if user_api_key:
            self.api_key = user_api_key
        elif api_key:
            self.api_key = api_key
        elif config_service:
            self.api_key = (
                config_service.get("claude_agent.api_key") or
                config_service.get("agent.llm.api_key") or
                os.environ.get("ANTHROPIC_API_KEY")
            )
        else:
            self.api_key = os.environ.get("ANTHROPIC_API_KEY")

        if not self.api_key:
            raise ValueError(
                "API key not provided. Please either:\n"
                "1. Pass user_api_key parameter (Ami API key for API Proxy), or\n"
                "2. Pass api_key parameter (Anthropic API key), or\n"
                "3. Set claude_agent.api_key in config, or\n"
                "4. Set ANTHROPIC_API_KEY environment variable"
            )

        # Model configuration
        if model:
            self.model = model
        elif config_service:
            self.model = config_service.get("claude_agent.model") or "claude-sonnet-4-5"
        else:
            self.model = "claude-sonnet-4-5"

        # Ensure working directory exists
        self.working_dir.mkdir(parents=True, exist_ok=True)

        # Output paths
        self.metaflow_path = self.working_dir / "metaflow.yaml"
        self.workflow_path = self.working_dir / "workflow.yaml"

        # State
        self.phase = "metaflow"  # "metaflow" or "workflow"
        self.metaflow_confirmed = False
        self.workflow_confirmed = False

        # Validator
        self.validator = WorkflowYAMLValidator()

        # Conversation history (for internal tracking)
        self.messages = []

        # System prompt
        self.system_prompt = get_system_prompt(str(self.working_dir))

        # Claude SDK client (initialized on first use)
        self._client = None
        self._connected = False

        logger.info(f"IntentBuilderAgent initialized with working_dir: {working_dir}, model: {self.model}")

    async def start(self, user_query: str, task_description: str = None) -> str:
        """
        Start the agent with initial user query.

        Args:
            user_query: User's task description/query
            task_description: Optional additional task context

        Returns:
            Agent's initial response
        """
        # Build initial context
        context = self._build_initial_context(user_query, task_description)

        # Add to conversation
        self.messages.append({
            "role": "user",
            "content": context
        })

        # Get agent response
        response = await self._get_agent_response()

        return response

    async def chat(self, user_message: str) -> str:
        """
        Continue conversation with user message.

        Args:
            user_message: User's message (feedback, confirmation, modification request)

        Returns:
            Agent's response
        """
        # Add user message
        self.messages.append({
            "role": "user",
            "content": user_message
        })

        # Check for phase transitions
        if self._should_transition_to_workflow(user_message):
            self.phase = "workflow"
            self.metaflow_confirmed = True
            logger.info("Transitioning to workflow generation phase")

        if self._should_complete(user_message):
            self.workflow_confirmed = True
            logger.info("Workflow confirmed, generation complete")

        # Get agent response
        response = await self._get_agent_response()

        return response

    def validate_workflow(self, workflow_yaml: str) -> tuple[bool, str]:
        """
        Validate generated workflow.

        Args:
            workflow_yaml: Workflow YAML string

        Returns:
            (is_valid, error_message)
        """
        return self.validator.validate(workflow_yaml)

    def get_state(self) -> dict:
        """
        Get current agent state.

        Returns:
            State dictionary with phase, confirmation status, file paths
        """
        return {
            "phase": self.phase,
            "metaflow_confirmed": self.metaflow_confirmed,
            "workflow_confirmed": self.workflow_confirmed,
            "metaflow_path": str(self.metaflow_path),
            "workflow_path": str(self.workflow_path),
            "message_count": len(self.messages)
        }

    def _build_initial_context(self, user_query: str, task_description: str = None) -> str:
        """Build initial context message for the agent."""
        context_parts = []

        # User query
        context_parts.append(f"## User Query\n\n{user_query}")

        # Task description
        if task_description:
            context_parts.append(f"## Task Description\n\n{task_description}")

        # File paths
        context_parts.append(f"""## Input Files

- User Operations: `{self.user_operations_path or 'user_operations.json'}`
- Intent Graph: `{self.intent_graph_path or 'intent_graph.json'}`

## Output Files

- MetaFlow: `{self.metaflow_path}`
- Workflow: `{self.workflow_path}`

## Instructions

Please start by reading the input files and relevant documentation, then generate the MetaFlow.
Present the MetaFlow to me for review before proceeding to Workflow generation.
""")

        return "\n\n".join(context_parts)

    async def _ensure_connected(self) -> None:
        """Ensure Claude SDK client is connected."""
        if self._connected and self._client:
            return

        try:
            from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

            # Get API proxy base URL from config
            proxy_base_url = None
            if self.config_service:
                use_proxy = self.config_service.get("llm.use_proxy", True)
                if use_proxy:
                    proxy_base_url = self.config_service.get("llm.proxy_url", "http://127.0.0.1:8080")
                    logger.info(f"Using API proxy: {proxy_base_url}")

            # Configure SDK options
            env_vars = {"ANTHROPIC_API_KEY": self.api_key}
            if proxy_base_url:
                env_vars["ANTHROPIC_BASE_URL"] = proxy_base_url

            options = ClaudeAgentOptions(
                model=self.model,
                cwd=str(self.working_dir),
                max_turns=25,
                allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
                permission_mode="acceptEdits",
                system_prompt=self.system_prompt,
                env=env_vars
            )

            # Create and connect client
            self._client = ClaudeSDKClient(options=options)
            await self._client.connect()
            self._connected = True

            logger.info("Claude SDK client connected successfully")

        except ImportError as e:
            error_msg = (
                "Claude Agent SDK not installed. "
                "Please install with: pip install claude-agent-sdk"
            )
            logger.error(f"{error_msg}: {e}")
            raise RuntimeError(error_msg) from e

    async def _get_agent_response(self) -> str:
        """
        Get response from Claude using ClaudeSDKClient.

        This method:
        1. Ensures the SDK client is connected
        2. Sends the last user message
        3. Streams responses and handles tool calls
        4. Returns the final text response

        Returns:
            Agent's text response
        """
        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ResultMessage,
                TextBlock,
                ToolUseBlock
            )

            # Ensure connected
            await self._ensure_connected()

            # Get the last user message
            if not self.messages:
                raise RuntimeError("No messages to send")

            last_message = self.messages[-1]
            if last_message["role"] != "user":
                raise RuntimeError("Last message must be from user")

            user_content = last_message["content"]

            # Send query to Claude
            logger.info(f"Sending query to Claude: {user_content[:100]}...")
            await self._client.query(user_content)

            # Collect response
            response_text = []
            tool_uses = []

            async for message in self._client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_text.append(block.text)
                            logger.debug(f"Received text: {block.text[:50]}...")
                        elif isinstance(block, ToolUseBlock):
                            tool_uses.append({
                                "name": block.name,
                                "input": block.input
                            })
                            logger.debug(f"Tool use: {block.name}")

                elif isinstance(message, ResultMessage):
                    logger.info(
                        f"Claude response complete: "
                        f"turns={message.num_turns}, "
                        f"cost=${message.total_cost_usd or 0:.4f}, "
                        f"duration={message.duration_ms/1000:.1f}s"
                    )

                    if message.is_error:
                        error_msg = message.result or "Unknown error"
                        logger.error(f"Claude returned error: {error_msg}")
                        return f"Error: {error_msg}"

            # Combine all text blocks
            full_response = "\n".join(response_text)

            # Add assistant response to conversation history
            self.messages.append({
                "role": "assistant",
                "content": full_response
            })

            return full_response

        except Exception as e:
            logger.error(f"Error getting agent response: {e}")
            raise

    async def chat_stream(self, user_message: str) -> AsyncIterator[StreamEvent]:
        """
        Continue conversation with streaming events (for Lovable-style UI).

        Args:
            user_message: User's message (feedback, confirmation, modification request)

        Yields:
            StreamEvent objects for real-time UI updates
        """
        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ResultMessage,
                TextBlock,
                ToolUseBlock,
                ToolResultBlock
            )

            logger.info(f"[chat_stream] Starting - message: {user_message[:100]}...")
            logger.info(f"[chat_stream] Current state - connected: {self._connected}, client: {self._client is not None}")

            # Add user message to history
            self.messages.append({
                "role": "user",
                "content": user_message
            })
            logger.info(f"[chat_stream] Added message to history, total messages: {len(self.messages)}")

            # Check for phase transitions
            if self._should_transition_to_workflow(user_message):
                self.phase = "workflow"
                self.metaflow_confirmed = True
                logger.info("Transitioning to workflow generation phase")

            if self._should_complete(user_message):
                self.workflow_confirmed = True
                logger.info("Workflow confirmed, generation complete")

            # Reconnect for each chat to avoid SDK state issues
            # This is a workaround for Claude SDK potentially not handling multiple queries correctly
            logger.info("[chat_stream] Reconnecting Claude SDK client for new query...")
            if self._client and self._connected:
                try:
                    await self._client.disconnect()
                    logger.info("[chat_stream] Disconnected previous SDK client")
                except Exception as e:
                    logger.warning(f"[chat_stream] Error disconnecting: {e}")
                self._client = None
                self._connected = False

            await self._ensure_connected()
            logger.info("[chat_stream] Claude SDK client ready")

            # Send query to Claude
            logger.info(f"[chat_stream] Sending query to Claude: {user_message[:100]}...")
            await self._client.query(user_message)
            logger.info("[chat_stream] Query sent, waiting for responses...")

            # Collect response text for history
            response_text = []

            # Stream events
            logger.info("[chat_stream] Starting to receive responses from Claude SDK...")
            message_count = 0
            async for message in self._client.receive_response():
                message_count += 1
                logger.info(f"[chat_stream] Received message #{message_count}, type: {type(message).__name__}")
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_text.append(block.text)
                            yield StreamEvent(
                                type="text",
                                content=block.text
                            )
                        elif isinstance(block, ToolUseBlock):
                            yield StreamEvent(
                                type="tool_use",
                                tool_name=block.name,
                                tool_input=block.input
                            )
                        elif isinstance(block, ToolResultBlock):
                            # Tool results contain the output
                            content = block.content
                            if isinstance(content, list):
                                content = str(content)
                            yield StreamEvent(
                                type="tool_result",
                                content=content[:500] if content else None  # Truncate for display
                            )

                elif isinstance(message, ResultMessage):
                    logger.info(
                        f"Claude response complete: "
                        f"turns={message.num_turns}, "
                        f"cost=${message.total_cost_usd or 0:.4f}, "
                        f"duration={message.duration_ms/1000:.1f}s"
                    )

                    if message.is_error:
                        yield StreamEvent(
                            type="error",
                            content=message.result or "Unknown error"
                        )
                    else:
                        # Add response to history
                        full_response = "\n".join(response_text)
                        self.messages.append({
                            "role": "assistant",
                            "content": full_response
                        })

                        # Read updated YAML content to return to frontend
                        # Frontend will handle saving to Cloud + Local
                        updated_yaml = None
                        if self.phase == "metaflow" and self.metaflow_path.exists():
                            try:
                                with open(self.metaflow_path, 'r', encoding='utf-8') as f:
                                    updated_yaml = f.read()
                            except Exception as e:
                                logger.warning(f"Failed to read updated metaflow: {e}")
                        elif self.phase == "workflow" and self.workflow_path.exists():
                            try:
                                with open(self.workflow_path, 'r', encoding='utf-8') as f:
                                    updated_yaml = f.read()
                            except Exception as e:
                                logger.warning(f"Failed to read updated workflow: {e}")

                        # Yield complete event with state and updated content
                        yield StreamEvent(
                            type="complete",
                            result={
                                "phase": self.phase,
                                "metaflow_confirmed": self.metaflow_confirmed,
                                "workflow_confirmed": self.workflow_confirmed,
                                "metaflow_path": str(self.metaflow_path),
                                "workflow_path": str(self.workflow_path),
                                "turns": message.num_turns,
                                "cost_usd": message.total_cost_usd,
                                "duration_ms": message.duration_ms,
                                "updated_yaml": updated_yaml
                            }
                        )

            logger.info(f"[chat_stream] Finished receiving {message_count} messages from Claude SDK")

        except Exception as e:
            logger.error(f"[chat_stream] Error in chat_stream: {e}")
            import traceback
            logger.error(f"[chat_stream] Traceback: {traceback.format_exc()}")
            yield StreamEvent(
                type="error",
                content=str(e)
            )

    async def start_stream(self, user_query: str, task_description: str = None) -> AsyncIterator[StreamEvent]:
        """
        Start the agent with streaming events (for Lovable-style UI).

        Args:
            user_query: User's task description/query
            task_description: Optional additional task context

        Yields:
            StreamEvent objects for real-time UI updates
        """
        # Build initial context
        context = self._build_initial_context(user_query, task_description)

        # Stream the response
        async for event in self.chat_stream(context):
            yield event

    async def disconnect(self) -> None:
        """Disconnect from Claude SDK client."""
        if self._client and self._connected:
            await self._client.disconnect()
            self._connected = False
            self._client = None
            logger.info("Claude SDK client disconnected")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - disconnect client."""
        await self.disconnect()
        return False

    def _should_transition_to_workflow(self, message: str) -> bool:
        """Check if user message indicates MetaFlow is confirmed."""
        # Simple keyword check - in real implementation, agent would track this
        confirm_keywords = [
            "proceed", "continue", "looks good", "confirm", "yes",
            "go ahead", "generate workflow", "next phase"
        ]
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in confirm_keywords)

    def _should_complete(self, message: str) -> bool:
        """Check if user message indicates Workflow is confirmed."""
        if self.phase != "workflow":
            return False

        confirm_keywords = [
            "looks good", "confirm", "yes", "complete", "done",
            "perfect", "that's correct", "approved"
        ]
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in confirm_keywords)


async def run_agent(
    working_dir: str,
    user_query: str,
    user_operations_path: str = None,
    intent_graph_path: str = None,
    task_description: str = None,
    config_service: Optional["ConfigService"] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    user_api_key: Optional[str] = None
):
    """
    Run the Intent Builder Agent interactively.

    Args:
        working_dir: Working directory for files
        user_query: Initial user query
        user_operations_path: Path to user operations
        intent_graph_path: Path to intent graph
        task_description: Optional task description
        config_service: ConfigService instance to read configuration
        api_key: Anthropic API key (overrides config/env if provided) - DEPRECATED
        model: Claude model to use (overrides config if provided)
        user_api_key: User's Ami API key for API Proxy (preferred method)

    This function runs an interactive loop:
    1. Start agent with initial query
    2. Print agent response
    3. Get user input
    4. Send to agent
    5. Repeat until complete
    """
    async with IntentBuilderAgent(
        working_dir=working_dir,
        user_operations_path=user_operations_path,
        intent_graph_path=intent_graph_path,
        config_service=config_service,
        api_key=api_key,
        model=model,
        user_api_key=user_api_key
    ) as agent:
        # Start conversation
        print("\n" + "="*60)
        print("Intent Builder Agent")
        print("="*60)
        print(f"\nUser Query: {user_query}\n")

        response = await agent.start(user_query, task_description)
        print(f"\nAgent:\n{response}\n")

        # Interactive loop
        while not agent.workflow_confirmed:
            user_input = input("\nYou: ").strip()
            if not user_input:
                continue

            if user_input.lower() in ["quit", "exit", "q"]:
                print("Exiting...")
                break

            response = await agent.chat(user_input)
            print(f"\nAgent:\n{response}\n")

            # Show state
            state = agent.get_state()
            print(f"[Phase: {state['phase']}, Messages: {state['message_count']}]")

        print("\n" + "="*60)
        print("Generation Complete")
        print("="*60)
        print(f"MetaFlow: {agent.metaflow_path}")
        print(f"Workflow: {agent.workflow_path}")
