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

        # Override accept-encoding to only use compressions httpx can handle
        # httpx supports gzip, deflate, and br (brotli), but NOT zstd
        headers['accept-encoding'] = 'gzip, deflate, br'

        headers['x-api-key'] = provider_config['api_key']

        # Ensure required Anthropic headers are present
        if 'anthropic-version' not in headers and 'anthropic-version' not in [h.lower() for h in headers.keys()]:
            headers['anthropic-version'] = '2023-06-01'
            logger.info("[ProxyService] Added missing anthropic-version header")

        if 'content-type' not in headers and 'content-type' not in [h.lower() for h in headers.keys()]:
            headers['content-type'] = 'application/json'
            logger.info("[ProxyService] Added missing content-type header")

        # Construct full URL
        url = f"{provider_config['base_url']}{endpoint}"

        # Log request details
        logger.info(f"[ProxyService] Forwarding to: {url}")
        logger.info(f"[ProxyService] Headers being sent: {list(headers.keys())}")
        logger.info(f"[ProxyService] anthropic-version: {headers.get('anthropic-version', 'NOT SET')}")

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
            logger.error(f"Proxy request failed: {response.status_code}")

        # Parse response - httpx will auto-decompress if it can
        # For formats httpx can't decompress (brotli/zstd without libs), this will fail
        try:
            if response.status_code == 200:
                # Try to parse as JSON (httpx will decompress automatically)
                response_body = response.json()
            else:
                response_body = response.text
        except Exception as e:
            logger.error(f"Failed to parse response: {e}")
            # If decompression fails, we need brotli/zstd libraries
            logger.error("Response may be compressed with unsupported format (brotli/zstd)")
            logger.error("Install: pip install brotli brotlicffi")
            raise RuntimeError(f"Cannot decompress response: {e}")

        # Return decompressed, parsed response
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
