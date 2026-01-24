"""
AMI Model Backend - Adapter for CAMEL to use AMI's LLM providers.

This adapter wraps AMI's LLM providers (AnthropicProvider, OpenAIProvider)
to be compatible with CAMEL's BaseModelBackend interface.

This allows CAMEL's ChatAgent and Workforce to use AMI's:
- CRS proxy routing
- Budget tracking
- Token usage monitoring
- Consistent API calling patterns
"""

import json
import logging
import asyncio
from typing import Any, Dict, List, Optional, Type, Union

from pydantic import BaseModel

from camel.models.base_model import BaseModelBackend
from camel.messages import OpenAIMessage
from camel.types import (
    ChatCompletion,
    ChatCompletionChunk,
    ModelType,
    UnifiedModelType,
)
from camel.utils import BaseTokenCounter

# Import AMI's LLM providers
from src.common.llm import AnthropicProvider

logger = logging.getLogger(__name__)


class SimpleTokenCounter(BaseTokenCounter):
    """
    Simple token counter that estimates tokens by character count.

    This is used as a fallback when OpenAITokenCounter is not available.
    Actual token usage is tracked by the AMI provider.
    """

    def count_tokens_from_messages(self, messages: List[OpenAIMessage]) -> int:
        """Estimate token count from messages."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                # Rough estimate: ~4 chars per token
                total += len(content) // 4
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "")
                        total += len(text) // 4
        return max(total, 1)

    def encode(self, text: str) -> List[int]:
        """Encode text into token IDs (simple byte-based encoding)."""
        # Simple encoding: each character becomes a token ID
        return [ord(c) for c in text]

    def decode(self, token_ids: List[int]) -> str:
        """Decode token IDs back to text."""
        # Simple decoding: convert token IDs back to characters
        return "".join(chr(tid) for tid in token_ids if 0 <= tid < 0x110000)


class AMIModelBackend(BaseModelBackend):
    """
    CAMEL-compatible model backend that uses AMI's LLM providers.

    This adapter allows CAMEL's agents to use AMI's LLM infrastructure:
    - Routes through CRS proxy (api.ariseos.com/api)
    - Uses Anthropic SDK with proper API format
    - Integrates with budget tracking
    - Maintains consistent token counting

    Usage:
        backend = AMIModelBackend(
            model_type="claude-sonnet-4-20250514",
            api_key="your-api-key",
            url="https://api.ariseos.com/api",
        )
        agent = ChatAgent(model=backend, ...)
    """

    def __init__(
        self,
        model_type: Union[ModelType, str],
        model_config_dict: Optional[Dict[str, Any]] = None,
        api_key: Optional[str] = None,
        url: Optional[str] = None,
        token_counter: Optional[BaseTokenCounter] = None,
        timeout: Optional[float] = 120.0,
        max_retries: int = 3,
    ) -> None:
        """
        Initialize AMI Model Backend.

        Args:
            model_type: Model name (e.g., 'claude-sonnet-4-20250514', 'glm-4.7')
            model_config_dict: Additional model configuration
            api_key: API key for LLM calls
            url: Base URL for API (CRS proxy URL)
            token_counter: Token counter instance
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        super().__init__(
            model_type=model_type,
            model_config_dict=model_config_dict or {},
            api_key=api_key,
            url=url,
            token_counter=token_counter,
            timeout=timeout,
            max_retries=max_retries,
        )

        # Create AMI provider
        # Use AnthropicProvider for all models since CRS uses Anthropic format
        self._provider = AnthropicProvider(
            api_key=api_key,
            model_name=str(model_type),
            base_url=url,
        )

        # Token counter - use a simple implementation since we track tokens in provider
        self._token_counter_instance = token_counter or SimpleTokenCounter()

        logger.info(f"[AMIModelBackend] Initialized with model={model_type}, url={url}")

    @property
    def token_counter(self) -> BaseTokenCounter:
        """Get the token counter."""
        return self._token_counter_instance

    def _run(
        self,
        messages: List[OpenAIMessage],
        response_format: Optional[Type[BaseModel]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ChatCompletion:
        """
        Run synchronous model call.

        Converts OpenAI format messages to Anthropic format and calls the provider.

        Args:
            messages: Messages in OpenAI format
            response_format: Response format (not used for Anthropic)
            tools: Tool definitions

        Returns:
            ChatCompletion response
        """
        # Run async in sync context
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already in async context, create a new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._async_run(messages, response_format, tools)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self._async_run(messages, response_format, tools)
                )
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self._async_run(messages, response_format, tools))

    async def _arun(
        self,
        messages: List[OpenAIMessage],
        response_format: Optional[Type[BaseModel]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ChatCompletion:
        """
        Run asynchronous model call.

        Args:
            messages: Messages in OpenAI format
            response_format: Response format
            tools: Tool definitions

        Returns:
            ChatCompletion response
        """
        return await self._async_run(messages, response_format, tools)

    async def _async_run(
        self,
        messages: List[OpenAIMessage],
        response_format: Optional[Type[BaseModel]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ChatCompletion:
        """
        Internal async implementation.

        Converts messages and calls AMI provider.
        """
        # Extract system message and convert to Anthropic format
        system_prompt = ""
        anthropic_messages = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                # Anthropic uses separate system parameter
                if isinstance(content, str):
                    system_prompt = content
                elif isinstance(content, list):
                    # Handle structured content
                    system_prompt = " ".join(
                        block.get("text", "") for block in content
                        if isinstance(block, dict) and block.get("type") == "text"
                    )
            elif role == "tool":
                # Convert OpenAI tool result to Anthropic format
                # Tool results should be sent as user message with tool_result block
                tool_call_id = msg.get("tool_call_id", "")
                tool_content = content if isinstance(content, str) else json.dumps(content)
                anthropic_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_call_id,
                            "content": tool_content,
                        }
                    ]
                })
            elif role == "assistant":
                # Handle assistant messages with tool_calls
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    # Convert to Anthropic format with tool_use blocks
                    assistant_content = []
                    if content:
                        if isinstance(content, str):
                            assistant_content.append({"type": "text", "text": content})
                        elif isinstance(content, list):
                            # Already structured content
                            for block in content:
                                if isinstance(block, dict):
                                    assistant_content.append(block)
                    for tc in tool_calls:
                        func = tc.get("function", {})
                        args = func.get("arguments", "{}")
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}
                        assistant_content.append({
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": func.get("name", ""),
                            "input": args,
                        })
                    anthropic_messages.append({
                        "role": "assistant",
                        "content": assistant_content if assistant_content else [{"type": "text", "text": ""}],
                    })
                else:
                    # Regular assistant message
                    if isinstance(content, str):
                        anthropic_messages.append({"role": "assistant", "content": content})
                    elif isinstance(content, list):
                        anthropic_messages.append({"role": "assistant", "content": content})
                    else:
                        anthropic_messages.append({"role": "assistant", "content": str(content) if content else ""})
            elif role == "user":
                # Regular user message - handle both string and structured content
                if isinstance(content, str):
                    anthropic_messages.append({"role": "user", "content": content})
                elif isinstance(content, list):
                    # Structured content (e.g., with images or tool_result)
                    anthropic_messages.append({"role": "user", "content": content})
                else:
                    anthropic_messages.append({"role": "user", "content": str(content) if content else ""})
            elif role == "function":
                # Legacy OpenAI function role - convert to tool result
                # This is deprecated but some code might still use it
                func_name = msg.get("name", "")
                tool_content = content if isinstance(content, str) else json.dumps(content)
                logger.warning(f"[AMIModelBackend] Deprecated 'function' role used, converting to tool_result")
                anthropic_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": func_name,  # Use function name as fallback ID
                            "content": tool_content,
                        }
                    ]
                })
            else:
                # Unknown role - skip or log warning
                logger.warning(f"[AMIModelBackend] Unknown message role: {role}, skipping")

        # Ensure there's at least one message
        if not anthropic_messages:
            anthropic_messages = [{"role": "user", "content": "Hello"}]

        logger.info(f"[AMIModelBackend] Calling provider with {len(anthropic_messages)} messages")

        if tools:
            # Use tool calling
            anthropic_tools = self._convert_tools_to_anthropic(tools)
            response = await self._provider.generate_with_tools(
                system_prompt=system_prompt,
                messages=anthropic_messages,
                tools=anthropic_tools,
                max_tokens=self.model_config_dict.get("max_tokens", 4096),
            )

            # Convert response to ChatCompletion format
            return self._convert_tool_response_to_chat_completion(response)
        else:
            # Simple text generation - use generate_with_tools but without tools
            # This preserves full message history
            response = await self._provider.generate_with_tools(
                system_prompt=system_prompt,
                messages=anthropic_messages,
                tools=[],  # Empty tools list
                max_tokens=self.model_config_dict.get("max_tokens", 4096),
            )

            # Extract text from response
            text_parts = []
            for block in response.content:
                if hasattr(block, 'text'):
                    text_parts.append(block.text)

            response_text = "\n".join(text_parts) if text_parts else ""

            # Convert to ChatCompletion format
            return self._create_chat_completion(response_text)

    def _convert_tools_to_anthropic(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert OpenAI tool format to Anthropic format."""
        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                anthropic_tools.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {}),
                })
            else:
                # Already in Anthropic format or compatible
                anthropic_tools.append(tool)
        return anthropic_tools

    def _convert_tool_response_to_chat_completion(
        self, response
    ) -> ChatCompletion:
        """Convert AMI ToolCallResponse to CAMEL ChatCompletion."""
        from camel.types import (
            ChatCompletionMessage,
            Choice,
        )

        # Build content and tool_calls
        content_parts = []
        tool_calls = []

        for i, block in enumerate(response.content):
            if hasattr(block, 'text'):
                content_parts.append(block.text)
            elif hasattr(block, 'name'):
                # ToolUseBlock - arguments must be valid JSON string
                arguments = "{}"
                if block.input:
                    if isinstance(block.input, str):
                        arguments = block.input
                    else:
                        # Convert dict to JSON string (not Python str() which uses single quotes)
                        arguments = json.dumps(block.input)

                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": arguments,
                    },
                })

        content = "\n".join(content_parts) if content_parts else None

        # Create message
        message = ChatCompletionMessage(
            role="assistant",
            content=content,
            tool_calls=tool_calls if tool_calls else None,
        )

        # Map stop reason
        finish_reason = "stop"
        if response.stop_reason == "tool_use":
            finish_reason = "tool_calls"
        elif response.stop_reason == "end_turn":
            finish_reason = "stop"

        choice = Choice(
            index=0,
            message=message,
            finish_reason=finish_reason,
        )

        return ChatCompletion(
            id="ami-" + str(id(response)),
            choices=[choice],
            created=0,
            model=str(self.model_type),
            object="chat.completion",
        )

    def _create_chat_completion(self, text: str) -> ChatCompletion:
        """Create a ChatCompletion from text response."""
        from camel.types import (
            ChatCompletionMessage,
            Choice,
        )

        message = ChatCompletionMessage(
            role="assistant",
            content=text,
        )

        choice = Choice(
            index=0,
            message=message,
            finish_reason="stop",
        )

        return ChatCompletion(
            id="ami-text-" + str(hash(text))[:8],
            choices=[choice],
            created=0,
            model=str(self.model_type),
            object="chat.completion",
        )

    def check_model_config(self) -> None:
        """Check model configuration validity."""
        pass  # No special validation needed

    @property
    def stream(self) -> bool:
        """Whether streaming is enabled."""
        return self.model_config_dict.get("stream", False)
