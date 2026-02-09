"""
Anthropic provider implementation with Budget Tracking

Integrates with BudgetController for token usage tracking and cost management.
Based on Eigent's browser_use token tracking pattern.
"""

import os
import asyncio
import logging
import json
import random
from typing import Optional, List, Dict, Any, Callable

from anthropic import Anthropic, APIStatusError, APIConnectionError

# Retry configuration
MAX_RETRIES = 6
RETRY_BASE_DELAY = 2.0  # Base delay in seconds
RETRY_MAX_DELAY = 60.0  # Cap at 60 seconds
# Status codes that should trigger a retry (server errors and rate limits)
# Note: 400 included because some API proxies return 400 with internal server errors
RETRYABLE_STATUS_CODES = {400, 429, 500, 502, 503, 504}


def _retry_delay(attempt: int, base: float = RETRY_BASE_DELAY, max_delay: float = RETRY_MAX_DELAY) -> float:
    """Calculate retry delay with exponential backoff + jitter.

    Delay: min(base * 2^attempt + jitter, max_delay)
    Example sequence: ~2s, ~4s, ~8s, ~16s, ~32s, ~60s
    """
    delay = min(base * (2 ** attempt), max_delay)
    jitter = random.uniform(0, delay * 0.25)  # 0-25% jitter
    return delay + jitter

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
        self._on_retry: Optional[Callable] = None  # Retry notification callback
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

    def set_on_retry_callback(self, callback: Callable) -> None:
        """Set callback for retry notifications.

        Called with (attempt, max_retries, delay, error_message) before each retry sleep.
        """
        self._on_retry = callback

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

    async def _notify_retry(self, attempt: int, delay: float, error_msg: str) -> None:
        """Notify retry callback before sleeping."""
        if not self._on_retry:
            return
        try:
            if asyncio.iscoroutinefunction(self._on_retry):
                await self._on_retry(attempt, MAX_RETRIES, delay, error_msg)
            else:
                self._on_retry(attempt, MAX_RETRIES, delay, error_msg)
        except Exception as e:
            logger.warning(f"Failed to emit retry notification: {e}")

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
    
    def _get_proxy_from_env(self) -> Optional[str]:
        """Get proxy from environment variables only (ignore system proxy settings).

        This explicitly reads from environment variables and ignores system-level
        proxy settings (e.g., macOS System Preferences / Clash) to ensure
        predictable behavior when connecting to CRS proxy.

        Returns:
            Proxy URL string or None if not set
        """
        return (
            os.environ.get("HTTPS_PROXY")
            or os.environ.get("https_proxy")
            or os.environ.get("HTTP_PROXY")
            or os.environ.get("http_proxy")
            or os.environ.get("ALL_PROXY")
            or os.environ.get("all_proxy")
        )

    async def _initialize_client(self) -> None:
        """Initialize the Anthropic client"""

        # Get API key from env var if not provided
        self.api_key = self.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Anthropic API key not provided and not found in ANTHROPIC_API_KEY environment variable")

        # Set default model if not specified
        if not self.model_name:
            self.model_name = "claude-sonnet-4-5-20250929"

        # Create custom httpx client to bypass system proxy detection
        # Anthropic SDK uses urllib.request.getproxies() which reads macOS System Preferences
        # This causes issues when Clash/V2Ray modifies system proxy settings
        # We explicitly get proxy from env vars only (like cloud_client.py does)
        import httpx
        proxy = self._get_proxy_from_env()
        if proxy:
            logger.info(f"Using proxy from environment: {proxy}")
        else:
            logger.info("No proxy from environment, bypassing system proxy settings")

        http_client = httpx.Client(
            timeout=120.0,  # 2 minute timeout for API calls
            proxy=proxy,  # None disables auto-detection, explicit URL enables proxy
        )

        # Initialize client with custom http_client
        client_kwargs = {
            "api_key": self.api_key,
            "http_client": http_client,
        }

        # Add custom base_url if provided (for API proxy)
        # SDK only reads ANTHROPIC_BASE_URL env var when base_url param is None,
        # so explicit param always takes priority - no env var workaround needed.
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
            logger.info(f"Using custom base URL: {self.base_url}")

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

                    logger.info(f"Anthropic API call successful")

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
                if e.status_code in RETRYABLE_STATUS_CODES:
                    last_exception = e
                    if attempt < MAX_RETRIES - 1:
                        delay = _retry_delay(attempt)
                        logger.info(f"Retryable status {e.status_code}, retrying in {delay:.1f}s... (attempt {attempt + 1}/{MAX_RETRIES})")
                        await self._notify_retry(attempt + 1, delay, f"API error {e.status_code}")
                        await asyncio.sleep(delay)
                        continue
                raise
            except APIConnectionError as e:
                last_exception = e
                logger.error(f"Anthropic API Connection Error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    delay = _retry_delay(attempt)
                    logger.info(f"Connection error, retrying in {delay:.1f}s...")
                    await self._notify_retry(attempt + 1, delay, f"Connection error: {e}")
                    await asyncio.sleep(delay)
                continue
            except Exception as e:
                logger.error(f"Error calling Anthropic API: {e}")
                logger.error(f"Error type: {type(e).__name__}")
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

                # Use asyncio.to_thread() to run sync client in thread pool
                # Only include tools parameter if there are tools (Anthropic may reject empty list)
                create_kwargs = {
                    "model": self.model_name,
                    "max_tokens": max_tokens,
                    "system": system_prompt,
                    "messages": messages,
                }
                if tools:
                    create_kwargs["tools"] = tools

                # Log the full prompt being sent to the model
                logger.info("=" * 80)
                logger.info("[LLM Request] System prompt (first 1000 chars):")
                logger.info(system_prompt[:1000] if len(system_prompt) > 1000 else system_prompt)
                logger.info("-" * 40)
                for i, msg in enumerate(messages):
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        content_preview = content[:2000] if len(content) > 2000 else content
                    else:
                        content_preview = str(content)[:2000]
                    logger.info(f"[LLM Request] Message {i} ({role}): {content_preview}")
                    # Check if workflow guide is in the message
                    if "Memory Guidance" in str(content):
                        logger.info("[LLM Request] ✅ WORKFLOW GUIDE DETECTED in message!")
                logger.info("=" * 80)

                response = await asyncio.to_thread(
                    self._client.messages.create,
                    **create_kwargs,
                )

                logger.info(f"Anthropic API call successful (stop={response.stop_reason}, blocks={len(response.content)})")

                # Log full response for debugging
                for i, block in enumerate(response.content):
                    if hasattr(block, 'type'):
                        if block.type == "text":
                            logger.info(f"[LLM Response] Block {i} text: {block.text[:500] if block.text else '(empty)'}")
                        elif block.type == "tool_use":
                            logger.info(f"[LLM Response] Block {i} tool_use: {block.name}({json.dumps(block.input, ensure_ascii=False)[:200]})")

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
                if e.status_code in RETRYABLE_STATUS_CODES:
                    last_exception = e
                    if attempt < MAX_RETRIES - 1:
                        delay = _retry_delay(attempt)
                        logger.info(f"Retryable status {e.status_code}, retrying in {delay:.1f}s... (attempt {attempt + 1}/{MAX_RETRIES})")
                        await self._notify_retry(attempt + 1, delay, f"API error {e.status_code}")
                        await asyncio.sleep(delay)
                        continue
                raise
            except APIConnectionError as e:
                last_exception = e
                logger.error(f"Anthropic API Connection Error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    delay = _retry_delay(attempt)
                    logger.info(f"Connection error, retrying in {delay:.1f}s...")
                    await self._notify_retry(attempt + 1, delay, f"Connection error: {e}")
                    await asyncio.sleep(delay)
                continue
            except Exception as e:
                logger.error(f"Error calling Anthropic API with tools: {e}")
                logger.error(f"Error type: {type(e).__name__}")
                raise

        # All retries exhausted
        logger.error(f"All {MAX_RETRIES} retry attempts failed for generate_with_tools")
        raise last_exception
