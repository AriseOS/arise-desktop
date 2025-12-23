"""
Anthropic provider implementation
"""

import os
import asyncio
import logging
import json
from typing import Optional

from anthropic import Anthropic, APIStatusError, APIConnectionError

from .base_provider import BaseProvider

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseProvider):
    """
    Anthropic provider implementation using official SDK
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        """
        Initialize Anthropic provider

        Args:
            api_key: Anthropic API key (will use ANTHROPIC_API_KEY env var if not provided)
            model_name: Model name (defaults to claude-sonnet-4-5-20250929)
            base_url: Custom base URL for API proxy (defaults to official Anthropic API)
        """
        super().__init__(api_key, model_name)
        self.base_url = base_url
        self.temperature = 0.7
        self.max_tokens = 8192  # Increased from 2048 to handle large MetaFlow generation
    
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
        
        try:
            messages = [
                {"role": "user", "content": user_prompt}
            ]

            logger.info(f"Calling Anthropic API...")
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
            logger.error(f"Anthropic API Connection Error: {e}")
            raise
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