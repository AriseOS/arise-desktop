"""
LLM API proxy service

Forwards requests to Anthropic API and tracks token usage
"""
import httpx
import logging
from typing import Any, Dict, Optional

from ..config import get_config

logger = logging.getLogger(__name__)


class ProxyService:
    """Service for proxying LLM API requests"""

    def __init__(self):
        self.config = get_config()
        self.timeout = self.config.get("llm.timeout_seconds", 300)

        # Store provider configurations
        self.providers = {
            'anthropic': {
                'api_key': self.config.get_anthropic_api_key(),
                'base_url': self.config.get("llm.anthropic.base_url", "https://api.anthropic.com"),
            }
        }

        # Add OpenAI if configured (not supported yet)
        openai_key = self.config.get("llm.openai.api_key")
        if openai_key:
            self.providers['openai'] = {
                'api_key': openai_key,
                'base_url': self.config.get("llm.openai.base_url", "https://api.openai.com/v1"),
            }

        self.default_provider = self.config.get("llm.default_provider", "anthropic")

    async def forward_request(
        self,
        provider: str,
        endpoint: str,
        method: str,
        headers: Dict[str, str],
        body: Optional[Dict[str, Any]] = None
    ) -> tuple[int, Dict[str, str], Any]:
        """Forward request to LLM provider

        Args:
            provider: Provider name ('anthropic', 'openai', etc.)
            endpoint: API endpoint (e.g., '/v1/messages')
            method: HTTP method (GET, POST, etc.)
            headers: Request headers (will be modified)
            body: Request body (for POST requests)

        Returns:
            tuple of (status_code, response_headers, response_body)

        Raises:
            ValueError: If provider not configured
            httpx.HTTPError: If request fails
        """
        # Get provider config
        if provider not in self.providers:
            raise ValueError(f"Provider '{provider}' not configured")

        provider_config = self.providers[provider]

        # Replace user's API key with system's real key
        headers = headers.copy()

        # Filter out headers that should not be forwarded
        # These headers must be set by httpx or will cause 403 errors
        headers_to_remove = [
            'host',              # Must match destination server
            'content-length',    # Will be set automatically by httpx
            'content-encoding',  # May cause decompression issues
            'transfer-encoding', # May cause issues with chunked encoding
            'connection',        # Hop-by-hop header
        ]
        for header in headers_to_remove:
            headers.pop(header, None)
            headers.pop(header.lower(), None)

        headers['x-api-key'] = provider_config['api_key']

        # Construct full URL
        url = f"{provider_config['base_url']}{endpoint}"

        # Make request
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            if method.upper() == 'POST':
                response = await client.post(url, headers=headers, json=body)
            elif method.upper() == 'GET':
                response = await client.get(url, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

        # Log errors only
        if response.status_code != 200:
            logger.error(f"Proxy request failed: {response.status_code} - {response.text[:200]}")

        # Parse response body
        # Read the response content first to ensure it's fully loaded
        try:
            # Force read the response to handle streaming/compressed content
            await response.aread()

            if response.status_code == 200:
                # Try to parse as JSON
                response_body = response.json()
            else:
                response_body = response.text
        except Exception as e:
            logger.error(f"Failed to parse response: {e}")
            logger.error(f"Response headers: {dict(response.headers)}")
            logger.error(f"Response content (first 100 bytes): {response.content[:100]}")
            # If JSON parsing fails, try to get text
            try:
                response_body = response.text
            except:
                # If text also fails, return raw bytes as string
                response_body = str(response.content)

        # Return response
        return (
            response.status_code,
            dict(response.headers),
            response_body
        )

    async def forward_anthropic_request(
        self,
        endpoint: str,
        method: str,
        headers: Dict[str, str],
        body: Optional[Dict[str, Any]] = None
    ) -> tuple[int, Dict[str, str], Any]:
        """Forward request to Anthropic API (backward compatibility)

        Args:
            endpoint: API endpoint (e.g., '/v1/messages')
            method: HTTP method (GET, POST, etc.)
            headers: Request headers
            body: Request body

        Returns:
            tuple of (status_code, response_headers, response_body)
        """
        return await self.forward_request('anthropic', endpoint, method, headers, body)

    def extract_token_usage(self, response_body: Dict[str, Any]) -> tuple[int, int]:
        """Extract token usage from Anthropic response

        Args:
            response_body: Response body from Anthropic API

        Returns:
            tuple of (input_tokens, output_tokens)
        """
        if not isinstance(response_body, dict):
            return (0, 0)

        usage = response_body.get('usage', {})
        input_tokens = usage.get('input_tokens', 0)
        output_tokens = usage.get('output_tokens', 0)

        return (input_tokens, output_tokens)

    def extract_model_name(self, request_body: Dict[str, Any]) -> str:
        """Extract model name from request body

        Args:
            request_body: Request body

        Returns:
            Model name
        """
        return request_body.get('model', 'unknown')


# Singleton instance
_proxy_service: ProxyService = None


def get_proxy_service() -> ProxyService:
    """Get proxy service instance (singleton)"""
    global _proxy_service
    if _proxy_service is None:
        _proxy_service = ProxyService()
    return _proxy_service
