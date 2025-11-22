"""
Anthropic provider implementation
"""

import os
import asyncio
import logging
from typing import Optional

from anthropic import Anthropic

from .base_provider import BaseProvider

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseProvider):
    """
    Anthropic provider implementation using official SDK
    """
    
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        """
        Initialize Anthropic provider
        
        Args:
            api_key: Anthropic API key (will use ANTHROPIC_API_KEY env var if not provided)
            model_name: Model name (defaults to claude-sonnet-4-5-20250929)
        """
        super().__init__(api_key, model_name)
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
        self._client = Anthropic(
            api_key=self.api_key,
            timeout=120.0  # 2 minute timeout for API calls
        )
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
            
            response = await asyncio.to_thread(
                self._client.messages.create,
                model=self.model_name,
                system=system_prompt,  # Claude uses separate system parameter
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            logger.info(f"Anthropic API call successful, model: {self.model_name}")
            return response.content[0].text
            
        except Exception as e:
            logger.error(f"Error calling Anthropic API: {e}")
            raise