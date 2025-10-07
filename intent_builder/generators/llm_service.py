"""
LLM Service - Call LLM API to generate workflow YAML

Supports multiple LLM providers (Claude, OpenAI)
"""
import os
import logging
from typing import Optional
import anthropic
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LLMService:
    """LLM service for workflow generation"""

    def __init__(
        self,
        provider: str = "anthropic",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 8000
    ):
        """
        Initialize LLM service

        Args:
            provider: LLM provider ("anthropic" or "openai")
            model: Model name (defaults to best available)
            api_key: API key (uses env var if not provided)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
        """
        self.provider = provider
        self.temperature = temperature
        self.max_tokens = max_tokens

        if provider == "anthropic":
            self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
            if not self.api_key:
                raise ValueError("ANTHROPIC_API_KEY not set. Please set it via environment variable or constructor.")
            self.model = model or "claude-sonnet-4-20250514"
            self.client = anthropic.AsyncAnthropic(api_key=self.api_key)
        elif provider == "openai":
            self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
            if not self.api_key:
                raise ValueError("OPENAI_API_KEY not set. Please set it via environment variable or constructor.")
            self.model = model or "gpt-4-turbo-preview"
            self.client = AsyncOpenAI(api_key=self.api_key)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        logger.info(f"Initialized LLM service: {provider}/{self.model}")

    async def generate(self, prompt: str) -> str:
        """
        Generate workflow YAML from prompt

        Args:
            prompt: Complete prompt for generation

        Returns:
            Generated workflow YAML string
        """
        logger.info(f"Calling {self.provider} API with {len(prompt)} chars prompt")

        if self.provider == "anthropic":
            return await self._generate_anthropic(prompt)
        elif self.provider == "openai":
            return await self._generate_openai(prompt)

    async def _generate_anthropic(self, prompt: str) -> str:
        """Generate using Anthropic Claude API"""
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        # Extract text from response
        result = response.content[0].text

        # Extract YAML if wrapped in code blocks
        result = self._extract_yaml(result)

        logger.info(f"Generated {len(result)} chars response")
        return result

    async def _generate_openai(self, prompt: str) -> str:
        """Generate using OpenAI API"""
        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        result = response.choices[0].message.content

        # Extract YAML if wrapped in code blocks
        result = self._extract_yaml(result)

        logger.info(f"Generated {len(result)} chars response")
        return result

    def _extract_yaml(self, text: str) -> str:
        """
        Extract YAML from markdown code blocks if present

        Args:
            text: Raw LLM response

        Returns:
            Extracted YAML string
        """
        # Check for ```yaml code blocks
        if "```yaml" in text:
            start = text.find("```yaml") + 7
            end = text.find("```", start)
            return text[start:end].strip()

        # Check for ``` code blocks
        if "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            return text[start:end].strip()

        # Return as-is if no code blocks
        return text.strip()
