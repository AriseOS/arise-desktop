"""
Anthropic provider implementation with Budget Tracking

Integrates with BudgetController for token usage tracking and cost management.
Based on Eigent's browser_use token tracking pattern.
"""

import os
import asyncio
import logging
import json
from typing import Optional, List, Dict, Any, Callable

from anthropic import Anthropic, APIStatusError, APIConnectionError

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2.0

from .base_provider import (
    BaseProvider,
    ToolCallResponse,
    ToolUseBlock,
    TextBlock,
)

logger = logging.getLogger(__name__)

# Import budget tracking (lazy to avoid circular imports)
_budget_imports = {}

def _get_budget_classes():
    """Lazy import budget tracking classes."""
    if not _budget_imports:
        try:
            from src.clients.desktop_app.ami_daemon.base_agent.core.token_usage import TokenUsage
            from src.clients.desktop_app.ami_daemon.base_agent.core.budget_controller import (
                BudgetController, BudgetConfig
            )
            _budget_imports['TokenUsage'] = TokenUsage
            _budget_imports['BudgetController'] = BudgetController
            _budget_imports['BudgetConfig'] = BudgetConfig
            _budget_imports['available'] = True
        except ImportError:
            _budget_imports['available'] = False
    return _budget_imports


class AnthropicProvider(BaseProvider):
    """
    Anthropic provider implementation using official SDK.

    Integrates with BudgetController for:
    - Token usage tracking per call
    - Cost calculation and budget enforcement
    - Event emission for frontend visibility
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        budget_controller: Optional[Any] = None,
        on_usage: Optional[Callable] = None,
    ):
        """
        Initialize Anthropic provider

        Args:
            api_key: Anthropic API key (will use ANTHROPIC_API_KEY env var if not provided)
            model_name: Model name (defaults to claude-sonnet-4-5-20250929)
            base_url: Custom base URL for API proxy (defaults to official Anthropic API)
            budget_controller: Optional BudgetController for cost tracking
            on_usage: Optional callback for token usage events (for SSE emission)
        """
        super().__init__(api_key, model_name)
        self.base_url = base_url
        self.temperature = 0.7
        self.max_tokens = 8192  # Increased from 2048 to handle large MetaFlow generation

        # Budget tracking (Eigent Migration)
        self._budget_controller = budget_controller
        self._on_usage = on_usage
        self._total_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
            "num_calls": 0,
            "estimated_cost": 0.0,
        }

    def set_budget_controller(self, controller: Any) -> None:
        """Set budget controller for token tracking.

        Args:
            controller: BudgetController instance
        """
        self._budget_controller = controller

    def set_on_usage_callback(self, callback: Callable) -> None:
        """Set callback for token usage events.

        Args:
            callback: Async or sync function to call with usage data
        """
        self._on_usage = callback

    def get_total_usage(self) -> Dict[str, Any]:
        """Get cumulative token usage for this provider instance."""
        return self._total_usage.copy()

    def _record_usage(self, response) -> Optional[Dict[str, Any]]:
        """Record token usage from API response.

        Args:
            response: Anthropic API response object

        Returns:
            Token usage dictionary for event emission
        """
        if not hasattr(response, 'usage'):
            return None

        # Debug: Log the full usage object for non-Claude models
        if not self.model_name.startswith('claude'):
            logger.info(f"[DEBUG] Non-Claude model usage object:")
            logger.info(f"  Model: {self.model_name}")
            logger.info(f"  Usage type: {type(response.usage)}")
            logger.info(f"  Usage attributes: {dir(response.usage)}")
            logger.info(f"  Usage dict: {vars(response.usage) if hasattr(response.usage, '__dict__') else 'N/A'}")
            logger.info(f"  input_tokens: {getattr(response.usage, 'input_tokens', None)}")
            logger.info(f"  output_tokens: {getattr(response.usage, 'output_tokens', None)}")
            logger.info(f"  cache_creation_input_tokens: {getattr(response.usage, 'cache_creation_input_tokens', None)}")
            logger.info(f"  cache_read_input_tokens: {getattr(response.usage, 'cache_read_input_tokens', None)}")

        usage_data = {
            "input_tokens": getattr(response.usage, 'input_tokens', 0) or 0,
            "output_tokens": getattr(response.usage, 'output_tokens', 0) or 0,
            "cache_creation_tokens": getattr(response.usage, 'cache_creation_input_tokens', 0) or 0,
            "cache_read_tokens": getattr(response.usage, 'cache_read_input_tokens', 0) or 0,
            "model": self.model_name,
        }

        # Update cumulative usage
        self._total_usage["input_tokens"] += usage_data["input_tokens"]
        self._total_usage["output_tokens"] += usage_data["output_tokens"]
        self._total_usage["cache_creation_tokens"] += usage_data["cache_creation_tokens"]
        self._total_usage["cache_read_tokens"] += usage_data["cache_read_tokens"]
        self._total_usage["num_calls"] += 1

        # Record with budget controller if available
        budget_imports = _get_budget_classes()
        if self._budget_controller and budget_imports.get('available'):
            TokenUsage = budget_imports['TokenUsage']
            token_usage = TokenUsage(
                input_tokens=usage_data["input_tokens"],
                output_tokens=usage_data["output_tokens"],
                cache_creation_tokens=usage_data["cache_creation_tokens"],
                cache_read_tokens=usage_data["cache_read_tokens"],
                model=self.model_name,
            )
            can_continue = self._budget_controller.record_usage(token_usage)
            usage_data["budget_can_continue"] = can_continue
            usage_data["estimated_cost"] = token_usage.cost
            self._total_usage["estimated_cost"] += token_usage.cost

            # Check if should use fallback model
            if self._budget_controller.should_use_fallback_model():
                fallback = self._budget_controller.get_current_model(self.model_name)
                if fallback != self.model_name:
                    logger.info(f"Budget throttle: switching from {self.model_name} to {fallback}")
                    self.model_name = fallback
                    usage_data["model_switched_to"] = fallback

        # Emit usage event via callback
        if self._on_usage:
            self._emit_usage_event(usage_data)

        logger.info(f"Token usage: in={usage_data['input_tokens']}, out={usage_data['output_tokens']}, "
                   f"cache_create={usage_data['cache_creation_tokens']}, cache_read={usage_data['cache_read_tokens']}")

        return usage_data

    def _emit_usage_event(self, usage_data: Dict[str, Any]) -> None:
        """Emit token usage event via callback."""
        try:
            if asyncio.iscoroutinefunction(self._on_usage):
                # Schedule async callback
                try:
                    loop = asyncio.get_running_loop()
                    asyncio.create_task(self._on_usage(usage_data))
                except RuntimeError:
                    # No event loop, skip async emission
                    pass
            else:
                self._on_usage(usage_data)
        except Exception as e:
            logger.warning(f"Failed to emit usage event: {e}")
    
    async def _initialize_client(self) -> None:
        """Initialize the Anthropic client"""

        # Get API key from env var if not provided
        self.api_key = self.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Anthropic API key not provided and not found in ANTHROPIC_API_KEY environment variable")

        # Set default model if not specified
        if not self.model_name:
            self.model_name = "claude-sonnet-4-5-20250929"

        # Initialize client with timeout
        client_kwargs = {
            "api_key": self.api_key,
            "timeout": 120.0,  # 2 minute timeout for API calls
        }

        # Add custom base_url if provided (for API proxy)
        # IMPORTANT: If we explicitly set base_url, we need to ensure
        # the environment variable doesn't override it
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
            logger.info(f"Using custom base URL: {self.base_url}")
            # Temporarily save and remove env var to prevent override
            saved_base_url = os.environ.get("ANTHROPIC_BASE_URL")
            if saved_base_url:
                logger.info(f"Temporarily overriding ANTHROPIC_BASE_URL env var (was: {saved_base_url})")
                del os.environ["ANTHROPIC_BASE_URL"]

            self._client = Anthropic(**client_kwargs)

            # Restore env var
            if saved_base_url:
                os.environ["ANTHROPIC_BASE_URL"] = saved_base_url
        else:
            # Use environment variable if no explicit base_url
            self._client = Anthropic(**client_kwargs)

        logger.info(f"Initialized Anthropic client with model {self.model_name}")
    
    async def generate_response(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> str:
        """
        Generate a response using Anthropic API

        Args:
            system_prompt: System instruction for the model
            user_prompt: User's input prompt

        Returns:
            Generated response text
        """
        if self._client is None:
            await self._initialize_client()

        messages = [
            {"role": "user", "content": user_prompt}
        ]

        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Calling Anthropic API... (attempt {attempt + 1}/{MAX_RETRIES})")
                logger.info(f"  Client type: {type(self._client)}")
                logger.info(f"  Client base_url: {self._client.base_url}")

                # Make the API call and catch any errors
                try:
                    response = await asyncio.to_thread(
                        self._client.messages.create,
                        model=self.model_name,
                        system=system_prompt,  # Claude uses separate system parameter
                        messages=messages,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens
                    )

                    logger.info(f"Anthropic API call successful, model: {self.model_name}")
                    logger.info(f"Response type: {type(response)}")
                    logger.info(f"Response: {response}")

                    # Record token usage (Eigent Migration)
                    self._record_usage(response)

                    return response.content[0].text

                except json.JSONDecodeError as json_err:
                    logger.error(f"JSONDecodeError caught! {json_err}")
                    logger.error(f"  This means API Proxy returned invalid/empty JSON")

                    # The JSONDecodeError is raised from httpx response.json()
                    # Let's trace back through the exception to find the response
                    import sys
                    tb = sys.exc_info()[2]

                    # Walk up the traceback to find local variables
                    logger.error("Searching for httpx response in exception traceback...")
                    frame = tb.tb_frame
                    while frame:
                        local_vars = frame.f_locals
                        logger.error(f"  Frame: {frame.f_code.co_name}, locals: {list(local_vars.keys())[:10]}")

                        # Look for 'response' or 'self' that might be httpx.Response
                        if 'response' in local_vars:
                            resp = local_vars['response']
                            logger.error(f"  Found 'response': {type(resp)}")

                            # If it's httpx.Response, print its content
                            if hasattr(resp, 'content'):
                                logger.error(f"  ✅ Found httpx Response!")
                                logger.error(f"    Status: {resp.status_code}")
                                logger.error(f"    Headers: {dict(resp.headers)}")
                                logger.error(f"    Content length: {len(resp.content)}")
                                logger.error(f"    Content (bytes): {resp.content}")
                                logger.error(f"    Content (text): {resp.text}")
                                break

                        frame = frame.f_back

                    raise

            except APIStatusError as e:
                logger.error(f"Anthropic API Status Error: {e.status_code}")
                logger.error(f"Response body: {e.body}")
                raise
            except APIConnectionError as e:
                last_exception = e
                logger.error(f"Anthropic API Connection Error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    logger.info(f"Retrying in {RETRY_DELAY_SECONDS} seconds...")
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                continue
            except Exception as e:
                logger.error(f"Error calling Anthropic API: {e}")
                logger.error(f"Error type: {type(e).__name__}")

                # Try to get the underlying httpx response
                if hasattr(e, '__cause__'):
                    logger.error(f"Underlying cause: {e.__cause__}")

                # For JSONDecodeError, the httpx response should be in the exception chain
                # Try to extract it
                import sys
                exc_info = sys.exc_info()
                logger.error(f"Exception chain: {exc_info}")

                # Try to access the httpx response from Anthropic SDK internals
                try:
                    # The response might be stored in the exception or somewhere in the SDK
                    import traceback
                    tb_lines = traceback.format_exception(*exc_info)
                    for line in tb_lines:
                        logger.error(f"  {line.strip()}")
                except:
                    pass

                raise

        # All retries exhausted
        logger.error(f"All {MAX_RETRIES} retry attempts failed for generate_response")
        raise last_exception

    async def generate_with_tools(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_tokens: int = 4096,
    ) -> ToolCallResponse:
        """
        Generate a response with tool calling support.

        Uses asyncio.to_thread() to wrap the synchronous Anthropic client,
        preventing event loop blocking during the API call.

        Args:
            system_prompt: System instruction for the model
            messages: Conversation messages in Anthropic format:
                [{"role": "user", "content": "..."}, {"role": "assistant", "content": [...]}]
            tools: List of tool definitions in Anthropic format:
                [{"name": "...", "description": "...", "input_schema": {...}}]
            max_tokens: Maximum tokens in response

        Returns:
            ToolCallResponse containing content blocks and stop reason
        """
        if self._client is None:
            await self._initialize_client()

        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Calling Anthropic API with tools... (attempt {attempt + 1}/{MAX_RETRIES})")
                logger.info(f"  Model: {self.model_name}")
                logger.info(f"  Tools count: {len(tools)}")
                logger.info(f"  Messages count: {len(messages)}")

                # Use asyncio.to_thread() to run sync client in thread pool
                response = await asyncio.to_thread(
                    self._client.messages.create,
                    model=self.model_name,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=messages,
                    tools=tools,
                )

                logger.info(f"Anthropic API call successful")
                logger.info(f"  Stop reason: {response.stop_reason}")
                logger.info(f"  Content blocks: {len(response.content)}")

                # Record token usage (Eigent Migration)
                self._record_usage(response)

                # Convert response to our dataclass format
                content_blocks = []
                for block in response.content:
                    if hasattr(block, 'type'):
                        if block.type == "text":
                            content_blocks.append(TextBlock(text=block.text))
                        elif block.type == "tool_use":
                            content_blocks.append(ToolUseBlock(
                                id=block.id,
                                name=block.name,
                                input=block.input,
                            ))

                return ToolCallResponse(
                    content=content_blocks,
                    stop_reason=response.stop_reason,
                )

            except APIStatusError as e:
                logger.error(f"Anthropic API Status Error: {e.status_code}")
                logger.error(f"Response body: {e.body}")
                raise
            except APIConnectionError as e:
                last_exception = e
                logger.error(f"Anthropic API Connection Error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    logger.info(f"Retrying in {RETRY_DELAY_SECONDS} seconds...")
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                continue
            except Exception as e:
                logger.error(f"Error calling Anthropic API with tools: {e}")
                logger.error(f"Error type: {type(e).__name__}")
                raise

        # All retries exhausted
        logger.error(f"All {MAX_RETRIES} retry attempts failed for generate_with_tools")
        raise last_exception