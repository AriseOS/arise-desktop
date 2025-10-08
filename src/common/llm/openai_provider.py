"""
OpenAI provider implementation
"""

import os
import asyncio
import logging
from typing import Optional

from openai import OpenAI

from .base_provider import BaseProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseProvider):
    """
    OpenAI provider implementation using official SDK
    """
    
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        """
        Initialize OpenAI provider
        
        Args:
            api_key: OpenAI API key (will use OPENAI_API_KEY env var if not provided)
            model_name: Model name (defaults to gpt-3.5-turbo)
        """
        super().__init__(api_key, model_name)
        self.temperature = 0.7
        self.max_tokens = 2048
    
    async def _initialize_client(self) -> None:
        """Initialize the OpenAI client"""
        
        # Get API key from env var if not provided
        self.api_key = self.api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not provided and not found in OPENAI_API_KEY environment variable")
        
        # Set default model if not specified
        if not self.model_name:
            self.model_name = "gpt-4o"
        
        # Initialize client
        self._client = OpenAI(api_key=self.api_key)
        logger.info(f"Initialized OpenAI client with model {self.model_name}")
    
    async def generate_response(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> str:
        """
        Generate a response using OpenAI API
        
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
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            response = await asyncio.to_thread(
                self._client.chat.completions.create,
                model=self.model_name,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            logger.info(f"OpenAI API call successful, model: {self.model_name}")
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            raise