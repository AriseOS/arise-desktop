"""LLM Configuration Checker.

This module provides utilities for validating LLM client configurations,
ensuring that all required settings are properly configured before use.
"""

import os
from typing import Any, Dict, List, Optional

from src.cloud_backend.memgraph.services.llm.llm_client import LLMClient, LLMProvider


class ConfigValidationError(Exception):
    """Exception raised when LLM configuration validation fails.

    Attributes:
        message: Explanation of the validation error.
        provider: The LLM provider that failed validation.
        missing_fields: List of missing or invalid configuration fields.
    """

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        missing_fields: Optional[List[str]] = None,
    ) -> None:
        """Initializes a ConfigValidationError.

        Args:
            message: Explanation of the validation error.
            provider: The LLM provider that failed validation.
            missing_fields: List of missing or invalid configuration fields.
        """
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.missing_fields = missing_fields or []


class LLMConfigChecker:
    """Validates LLM client configurations.

    This class provides methods to check whether LLM clients are properly
    configured with valid API keys, endpoints, and other required settings.

    Example usage:
        checker = LLMConfigChecker()
        is_valid = checker.check_openai_config(api_key="your-key")
        client_valid = checker.check_client(my_llm_client)
    """

    @staticmethod
    def check_openai_config(
        api_key: Optional[str] = None,
        api_client: Optional[Any] = None,
        model_name: Optional[str] = None,
    ) -> bool:
        """Validates OpenAI configuration.

        Args:
            api_key: The OpenAI API key. If None, checks environment variable.
            api_client: An initialized OpenAI client instance.
            model_name: The model name to validate.

        Returns:
            True if configuration is valid, False otherwise.
        """
        # Check API key
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY")

        if not api_key and not api_client:
            return False

        # If client is provided, check its structure
        if api_client:
            if not hasattr(api_client, "chat"):
                return False
            if not hasattr(api_client.chat, "completions"):
                return False

        # Check model name if provided
        if model_name:
            valid_prefixes = ["gpt-4", "gpt-3.5", "gpt-3", "text-davinci"]
            if not any(model_name.startswith(prefix) for prefix in valid_prefixes):
                # Not necessarily invalid, but might be a custom model
                pass

        return True

    @staticmethod
    def check_anthropic_config(
        api_key: Optional[str] = None,
        api_client: Optional[Any] = None,
        model_name: Optional[str] = None,
    ) -> bool:
        """Validates Anthropic Claude configuration.

        Args:
            api_key: The Anthropic API key. If None, checks environment variable.
            api_client: An initialized Anthropic client instance.
            model_name: The model name to validate.

        Returns:
            True if configuration is valid, False otherwise.
        """
        # Check API key
        if not api_key:
            api_key = os.getenv("ANTHROPIC_API_KEY")

        if not api_key and not api_client:
            return False

        # If client is provided, check its structure
        if api_client:
            if not hasattr(api_client, "messages"):
                return False

        # Check model name if provided
        if model_name:
            valid_prefixes = ["claude-3", "claude-2", "claude-instant"]
            if not any(model_name.startswith(prefix) for prefix in valid_prefixes):
                # Not necessarily invalid, but might be a custom model
                pass

        return True

    @staticmethod
    def check_client(client: LLMClient) -> bool:
        """Validates an LLM client instance.

        This method calls the client's check_config() method to validate
        its configuration.

        Args:
            client: The LLM client instance to validate.

        Returns:
            True if the client is properly configured, False otherwise.
        """
        if not client:
            return False

        return client.check_config()

    @staticmethod
    def validate_client(client: LLMClient, raise_on_error: bool = True) -> bool:
        """Validates an LLM client and optionally raises an exception on failure.

        Args:
            client: The LLM client instance to validate.
            raise_on_error: If True, raises ConfigValidationError on failure.

        Returns:
            True if the client is valid.

        Raises:
            ConfigValidationError: If validation fails and raise_on_error is True.
        """
        is_valid = LLMConfigChecker.check_client(client)

        if not is_valid and raise_on_error:
            provider = (
                client.provider.value if hasattr(client, "provider") else "unknown"
            )
            raise ConfigValidationError(
                f"LLM client configuration validation failed for provider: {provider}",
                provider=provider,
            )

        return is_valid

    @staticmethod
    def get_config_issues(client: LLMClient) -> List[str]:
        """Identifies specific configuration issues with a client.

        Args:
            client: The LLM client instance to check.

        Returns:
            A list of configuration issue descriptions. Empty if valid.
        """
        issues = []

        if not client:
            issues.append("Client is None")
            return issues

        # Check basic client structure
        if not hasattr(client, "client"):
            issues.append("Missing 'client' attribute")

        if not hasattr(client, "model_name") or not client.model_name:
            issues.append("Missing or empty 'model_name'")

        if not hasattr(client, "provider"):
            issues.append("Missing 'provider' attribute")

        # Provider-specific checks
        if hasattr(client, "provider"):
            if client.provider == LLMProvider.OPENAI:
                if not hasattr(client, "chat"):
                    issues.append("OpenAI client missing 'chat' interface")
            elif client.provider == LLMProvider.ANTHROPIC:
                if not hasattr(client, "messages"):
                    issues.append("Anthropic client missing 'messages' interface")

        return issues

    @staticmethod
    def create_validation_report(clients: Dict[str, LLMClient]) -> Dict[str, Any]:
        """Creates a detailed validation report for multiple clients.

        Args:
            clients: A dictionary mapping client names to client instances.

        Returns:
            A dictionary containing validation results for each client:
            {
                "valid_count": int,
                "invalid_count": int,
                "results": {
                    "client_name": {
                        "valid": bool,
                        "issues": List[str]
                    }
                }
            }
        """
        report = {"valid_count": 0, "invalid_count": 0, "results": {}}

        for name, client in clients.items():
            is_valid = LLMConfigChecker.check_client(client)
            issues = LLMConfigChecker.get_config_issues(client)

            report["results"][name] = {"valid": is_valid, "issues": issues}

            if is_valid:
                report["valid_count"] += 1
            else:
                report["invalid_count"] += 1

        return report


def check_all_env_configs() -> Dict[str, bool]:
    """Checks all LLM provider environment configurations.

    Returns:
        A dictionary mapping provider names to their configuration status:
        {
            "openai": bool,
            "anthropic": bool
        }
    """
    return {
        "openai": LLMConfigChecker.check_openai_config(),
        "anthropic": LLMConfigChecker.check_anthropic_config(),
    }
